#!/usr/bin/env bash
# gen-doe-root-pointer.sh — project the DoE repo root into a cold-readable pointer file.
#
# Purpose: reads repos.doe_claude from the machine-local registry and writes
# ${CLAUDE_HOME:-$HOME}/.claude/.doe-root (one line, the DoE repo root, no trailing
# junk) so that cold-terminal consumers (the claude() shim, inline resolver fallbacks)
# can cat the pointer with zero tool dependency, solving the cold-PATH chicken-and-egg.
#
# Spec backlink: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md § C1
# Design: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md § Design decisions
#         (pointer is a projected cache; registry = source of truth; dry-run lesson cited)
#
# Resolution order for DoE clone root:
#   1. REPO_DOE_CLAUDE env var (operator override, also used by install sandbox tests)
#   2. machine-local get repos.doe_claude  (registry — primary)
#   3. fail-loud with remediation
#
# Recast (thin caller): docs/plans/2026-07-09-resolver-unification-v3split-01.md § C3 —
# this script does NOT delegate to resolve-coordinator-clone.sh's --clone-root
# verb (unlike claude-doe / coordinator-doe-root.sh). --clone-root's rung 3 is
# the .doe-root pointer file — the very file THIS script writes. Falling
# through to it here would read back a value this script is in the middle of
# refreshing, risking a stale read on the write path. This is the same
# deliberate omission documented below (rungs 1-2 only, no OSS-fallback
# rungs) — AC8 names claude-doe and coordinator-doe-root.sh as the OSS-fallback
# beneficiaries; this writer is intentionally excluded.
#
# Usage:
#   gen-doe-root-pointer.sh             — write (or refresh) the live pointer
#   gen-doe-root-pointer.sh --check-only — validate without mutating the live pointer
#
# Idempotency: if the live pointer already contains the correct value, the file is not
# rewritten (avoids spurious mtime churn and concurrent-write races in steady state).
#
# Dry-run safety: --check-only writes to a temp path, validates the content, then
# discards. The live ~/.claude/.doe-root is byte-unchanged after any --check-only run.
# (Lesson: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md § Design
# decisions "Dry-run must not mutate live config".)
#
# Fail-loud contract: if repos.doe_claude is unset/empty in both the env override and
# the registry, the script exits non-zero with a stderr message and a remediation hint.
#
# DR-148: targets bash >= 4 + BSD coreutils. No GNU-isms (no sed -i, no realpath,
# no grep -P, no date -d). mktemp uses a form portable to macOS BSD mktemp.
# No bash-4-only features used in this script body, but the guard is present per
# DR-148 policy (consistency + future-proofing if a caller chains with declare -A etc).
#
# Negative-spec: does NOT clone the DoE repo, does NOT edit any registry key, does NOT
# write any file other than ~/.claude/.doe-root (and a temp file that is discarded in
# --check-only mode).

# ---------------------------------------------------------------------------
# Bash >= 4 guard — must be reachable on bash 3.2 (DR-148). Uses only POSIX-safe
# constructs: ${v:-default} and [ -lt ] so the test parses on 3.2.
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  printf 'gen-doe-root-pointer.sh: bash >= 4 required (got %s)\n' "${BASH_VERSION:-unknown}" >&2
  printf '  Remediation: brew install bash   (macOS) or apt-get install bash (Linux)\n' >&2
  exit 1
fi

set -euo pipefail

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
CHECK_ONLY=0
for _arg in "$@"; do
  case "$_arg" in
    --check-only) CHECK_ONLY=1 ;;
    --help|-h)
      printf 'Usage: %s [--check-only]\n' "$(basename "$0")" >&2
      printf '  (no flag)    Write or refresh ~/.claude/.doe-root from the registry.\n' >&2
      printf '  --check-only Validate without mutating the live pointer (dry-run-safe).\n' >&2
      exit 0
      ;;
    *)
      printf 'gen-doe-root-pointer.sh: unknown argument: %s\n' "$_arg" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Locate machine-local binary: co-located sibling first, then PATH.
# Mirrors the resolution pattern in coordinator/bin/claude-doe.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"

_resolve_machine_local() {
  local ml_bin="$SCRIPT_DIR/machine-local"
  if [ -x "$ml_bin" ]; then
    printf '%s' "$ml_bin"
    return 0
  fi
  if command -v machine-local >/dev/null 2>&1; then
    printf '%s' "machine-local"
    return 0
  fi
  return 1
}

# ---------------------------------------------------------------------------
# Resolve the DoE clone root
# ---------------------------------------------------------------------------
_resolve_doe_root() {
  # Tier 1: explicit env override (install sandbox tests / operator pin).
  if [ -n "${REPO_DOE_CLAUDE:-}" ]; then
    printf '%s' "$REPO_DOE_CLAUDE"
    return 0
  fi

  # Tier 2: machine-local registry.
  local ml_bin
  if ! ml_bin="$(_resolve_machine_local)"; then
    printf 'gen-doe-root-pointer.sh: machine-local not found — cannot read registry\n' >&2
    printf '  Remediation: run /coordinator:install (Phase 3) to install machine-local,\n' >&2
    printf '  or set REPO_DOE_CLAUDE=<path> to bypass the registry lookup.\n' >&2
    return 1
  fi

  local resolved
  if ! resolved="$("$ml_bin" get repos.doe_claude 2>/dev/null)"; then
    printf 'gen-doe-root-pointer.sh: machine-local get repos.doe_claude failed\n' >&2
    printf '  Remediation: machine-local set repos.doe_claude <path>  then /coordinator:install\n' >&2
    return 1
  fi

  if [ -z "$resolved" ]; then
    printf 'gen-doe-root-pointer.sh: repos.doe_claude is unset in the registry\n' >&2
    printf '  Remediation: machine-local set repos.doe_claude <path>  then /coordinator:install\n' >&2
    return 1
  fi

  printf '%s' "$resolved"
}

# ---------------------------------------------------------------------------
# Resolve and validate the DoE root
# ---------------------------------------------------------------------------
DOE_ROOT=""
if ! DOE_ROOT="$(_resolve_doe_root)"; then
  exit 1
fi

# Strip any trailing slash for a canonical single-line value.
DOE_ROOT="${DOE_ROOT%/}"

if [ ! -d "$DOE_ROOT" ]; then
  printf 'gen-doe-root-pointer.sh: DoE root not found at "%s"\n' "$DOE_ROOT" >&2
  printf '  Remediation: confirm repos.doe_claude in the registry is a valid directory,\n' >&2
  printf '  or set REPO_DOE_CLAUDE=<path>  then /coordinator:install\n' >&2
  exit 1
fi

if [ ! -d "$DOE_ROOT/coordinator" ]; then
  printf 'gen-doe-root-pointer.sh: coordinator/ subdir absent at "%s/coordinator"\n' "$DOE_ROOT" >&2
  printf '  Remediation: confirm the DoE clone has coordinator/ populated (W4.2 cutover required).\n' >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Compute the target pointer path
# ---------------------------------------------------------------------------
POINTER_FILE="${CLAUDE_HOME:-$HOME}/.claude/.doe-root"

# ---------------------------------------------------------------------------
# --check-only path: generate to a temp file, validate, discard.
# The live $POINTER_FILE is never touched.
# ---------------------------------------------------------------------------
if [ "$CHECK_ONLY" = 1 ]; then
  _tmp="$(mktemp "${TMPDIR:-/tmp}/gen-doe-root-pointer.XXXXXX")"
  trap 'rm -f "$_tmp"' EXIT

  printf '%s\n' "$DOE_ROOT" > "$_tmp"

  # Validate: the temp file must contain exactly the resolved root.
  _written="$(cat "$_tmp")"
  if [ "$_written" != "$DOE_ROOT" ]; then
    printf 'gen-doe-root-pointer.sh: --check-only validation failed (wrote "%s", expected "%s")\n' \
      "$_written" "$DOE_ROOT" >&2
    exit 1
  fi

  printf 'gen-doe-root-pointer.sh: --check-only OK — would write "%s" to %s (not written)\n' \
    "$DOE_ROOT" "$POINTER_FILE" >&2
  # Temp file discarded by EXIT trap — live pointer byte-unchanged.
  exit 0
fi

# ---------------------------------------------------------------------------
# Live write path: idempotent — skip if the pointer already holds the correct value.
# ---------------------------------------------------------------------------
if [ -f "$POINTER_FILE" ]; then
  _existing="$(cat "$POINTER_FILE" 2>/dev/null || true)"
  if [ "$_existing" = "$DOE_ROOT" ]; then
    # Already correct — no-op (no mtime churn, no race).
    exit 0
  fi
fi

# Ensure the parent directory exists (first install before ~/.claude/ exists).
_pointer_dir="$(dirname "$POINTER_FILE")"
if [ ! -d "$_pointer_dir" ]; then
  mkdir -p "$_pointer_dir"
fi

# Atomic write: write to a sibling temp file then rename into place.
# Same-filesystem mv is atomic on POSIX; avoids a partial-read by a concurrent cat.
_tmp_live="$(mktemp "${_pointer_dir}/.doe-root.tmp.XXXXXX")"
trap 'rm -f "$_tmp_live"' EXIT

printf '%s\n' "$DOE_ROOT" > "$_tmp_live"
mv -f "$_tmp_live" "$POINTER_FILE"

# Trap no longer needs to clean up (mv succeeded); disarm without error.
trap - EXIT

printf 'gen-doe-root-pointer.sh: wrote "%s" to %s\n' "$DOE_ROOT" "$POINTER_FILE" >&2

exit 0
