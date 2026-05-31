#!/usr/bin/env bash
# list-review-trail-records.sh — Emit the union of live and archived review-trail records.
#
# Purpose: canonical reader for tasks/review-trail/**/*.json AND
# archive/review-trail/**/*.json, sorted by basename (ascending =
# chronological, since basenames are YYYY-MM-DD-HHMMSS-{sid}.json prefixed).
# Absent directories are silently skipped (fresh-install case).
#
# Spec backlink: docs/plans/2026-05-28-archive-aware-review-oracle-and-audit-skill.md § Chunk C0
#
# Usage:
#   list-review-trail-records.sh [--date-prefix YYYY-MM-DD] [--print0]
#
# Options:
#   --date-prefix YYYY-MM-DD   Only emit records whose basename starts with this prefix.
#   --print0                   Separate records with NUL instead of newlines (safe for
#                              downstream xargs -0 or read -d '' pipelines).
#
# Exit codes:
#   0  — success (including empty result — absent dirs are not errors)
#   1  — tool failure (find or sort returned non-zero)
#
# Sort mechanism: sort by basename, NOT by full path.
#   archive/review-trail/week-2026-05-25/2026-05-19-foo.json has an earlier
#   basename than archive/review-trail/week-2026-05-18/2026-05-20-bar.json,
#   but its full-path sort-order would be reversed across the week-subdir
#   boundary. awk extracts basename as the primary sort key.

set -uo pipefail

# ---------------------------------------------------------------------------
# Repo root discovery — use the CALLER's repo (git rev-parse --show-toplevel),
# matching the writer pattern in coordinator-write-review-trail.sh:185-207.
# COORDINATOR_ROOT is an explicit override for tests.
# Rationale: the script lives in ~/.claude/plugins/coordinator/bin/
# but the records live in the CONSUMER repo's tasks/review-trail/ and
# archive/review-trail/. A SCRIPT_DIR-derived default would read from the plugin
# directory (which contains no records) and silently return zero records on every
# non-meta-repo invocation. Use git toplevel of cwd.
# ---------------------------------------------------------------------------

if [[ -z "${COORDINATOR_ROOT:-}" ]]; then
  COORDINATOR_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -z "${COORDINATOR_ROOT}" ]]; then
    echo "list-review-trail-records.sh: cwd is not a git repo and COORDINATOR_ROOT is not set — cannot resolve tasks/review-trail/" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

DATE_PREFIX=""
PRINT0=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date-prefix)
      DATE_PREFIX="${2:-}"
      shift 2
      ;;
    --print0)
      PRINT0=true
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "list-review-trail-records.sh: unknown option: $1" >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Directory locations (relative to coordinator root)
# ---------------------------------------------------------------------------

LIVE_DIR="${COORDINATOR_ROOT}/tasks/review-trail"
ARCHIVE_DIR="${COORDINATOR_ROOT}/archive/review-trail"

# ---------------------------------------------------------------------------
# Collect records from a directory tree, absent-dir-safe.
# Emits: basename<TAB>fullpath lines (unsorted, written to temp file).
# ---------------------------------------------------------------------------

TMPFILE=""
cleanup() {
  # Remove the primary tempfile AND any --date-prefix intermediate (which exists
  # transiently between grep > .filtered and mv .filtered TMPFILE — a real grep
  # error between those lines would leave the intermediate behind otherwise).
  # The trailing `:` (true) guarantees cleanup() returns 0 regardless of which
  # branch the [[ ]]s took — otherwise a failed [[ ]] as the last statement
  # would leak as the script's exit code via the EXIT trap.
  [[ -n "${TMPFILE}" && -f "${TMPFILE}" ]] && rm -f "${TMPFILE}"
  [[ -n "${TMPFILE}" && -f "${TMPFILE}.filtered" ]] && rm -f "${TMPFILE}.filtered"
  :
}
trap cleanup EXIT

TMPFILE="$(mktemp)"

collect() {
  local dir="$1"
  [[ -d "${dir}" ]] || return 0
  # -L follows symlinks; -name '*.json' restricts to trail records.
  # awk -F'/' extracts the last path component (basename) as the sort key.
  # Assumes POSIX-style '/' separators — safe under Git-Bash/WSL/macOS/Linux which is
  # where coordinator bin/ scripts run; GNU find under Git-Bash on Windows emits '/'
  # even when the underlying paths are Windows-native.
  # The explicit `|| return $?` is load-bearing: collect is invoked at the call site
  # with `|| exit $?`, which disables `set -e` inside this function body — a `find`
  # or `awk` failure here would otherwise be swallowed silently without the explicit
  # return. Do not remove as "redundant under set -e" without verifying the call shape.
  find -L "${dir}" -name '*.json' \
    | awk -F'/' '{print $NF"\t"$0}' \
    >> "${TMPFILE}" || return $?
}

collect "${LIVE_DIR}"   || exit $?
collect "${ARCHIVE_DIR}" || exit $?

# ---------------------------------------------------------------------------
# Apply --date-prefix filter (match on the basename column, field 1).
# ---------------------------------------------------------------------------

if [[ -n "${DATE_PREFIX}" ]]; then
  # Validate DATE_PREFIX shape — must be YYYY-MM-DD. Unvalidated input would
  # interpolate into a grep -E pattern; ERE metacharacters (`.`, `[`, etc.) or
  # arbitrary user input ('.*', '[invalid') would either over-match or error.
  if [[ ! "${DATE_PREFIX}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "list-review-trail-records.sh: --date-prefix must be YYYY-MM-DD, got: ${DATE_PREFIX}" >&2
    exit 1
  fi
  # grep exits 1 on no-match; that is a valid empty result, not an error.
  # Capture exit explicitly so we don't conflate the no-match case with a real grep error.
  # DATE_PREFIX is validated above to be ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ — only `-` and digits,
  # neither of which is an ERE metacharacter, so direct -E interpolation is safe.
  set +e
  grep -E "^${DATE_PREFIX}" "${TMPFILE}" > "${TMPFILE}.filtered"
  GREP_RC=$?
  set -e
  if [[ ${GREP_RC} -ne 0 && ${GREP_RC} -ne 1 ]]; then
    exit ${GREP_RC}
  fi
  mv "${TMPFILE}.filtered" "${TMPFILE}"
fi

# ---------------------------------------------------------------------------
# Sort by basename (field 1), then extract full paths (field 2 onward).
# sort -t$'\t' -k1,1 sorts on the basename column only.
# cut -f2- removes the basename prefix column.
# ---------------------------------------------------------------------------

SORTED="$(sort -t$'\t' -k1,1 "${TMPFILE}" | cut -f2-)" || exit $?

# ---------------------------------------------------------------------------
# Emit — NUL-separated or newline-separated.
# ---------------------------------------------------------------------------

if [[ -z "${SORTED}" ]]; then
  # Empty result — exit 0, zero output.
  exit 0
fi

if "${PRINT0}"; then
  # printf '%s\0' emits each path followed by a NUL byte.
  # NOTE: <<< herestring appends an implicit trailing newline, which would
  # otherwise produce a final empty iteration and a spurious lone NUL byte —
  # xargs -0 consumers see this as an empty entry. Skip empty lines.
  while IFS= read -r path; do
    [[ -n "${path}" ]] || continue
    printf '%s\0' "${path}"
  done <<< "${SORTED}"
else
  printf '%s\n' "${SORTED}"
fi
