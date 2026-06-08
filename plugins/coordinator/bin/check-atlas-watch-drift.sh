#!/usr/bin/env bash
# check-atlas-watch-drift.sh — aggregate per-system `<name>.watch.sh` outputs
# into one line per atlas system, plus a default-on STALE walk over
# `last_attested` frontmatter (currency timestamp; bumped by audits AND bare re-attestations).
#
# Spec backlink: docs/plans/2026-06-04-architecture-audit-atlas-refresh-gate.md § C2
# Spec backlink: docs/plans/2026-06-08-atlas-attested-clock-split.md (last_attested as currency signal)
#
# Behavior summary (always exits 0 — informational):
#   1. Enumerate atlas pages at `docs/architecture/systems/*.md`.
#   2. For each system <name>:
#        - If `docs/architecture/systems/<name>.watch.sh` exists:
#            * Run `bash <path>` with cwd = repo root.
#            * Non-zero exit → emit `ERROR <name>: <name>.watch.sh exit=<N>`.
#            * Malformed stdout (not exactly one line matching
#              `^(FRESH|DRIFT|MISSING) <name>( .*)?$`) → emit
#              `MALFORMED <name>: <name>.watch.sh output unparseable`.
#            * Otherwise emit the line verbatim.
#        - Else (no `.watch.sh`): emit `FRESH <name> (no watch script)`.
#   3. STALE walk (default-on, suppressible via `--no-stale-walk`):
#      For each atlas page, parse frontmatter `last_attested:` date. If age in
#      days exceeds `--stale-days N` (default 30), emit
#      `STALE <name> last_attested=<date> age=<N>d`.
#
# CLI: --stale-days N              (default 30; alias --last-attested-stale-days;
#                                   accepts legacy --last-mapped-stale-days)
#      --no-stale-walk             (suppress STALE walk entirely)
#
# Negative-spec: does NOT modify any atlas page, does NOT trigger any audit,
# does NOT read or write `Last full audit`. Pure read.
#
# Portability: BSD-coreutils + bash 3.2 + Git-Bash. Mirrors date-arithmetic
# idiom of check-arch-audit-staleness.sh:89-95.

set -euo pipefail

STALE_THRESHOLD_DAYS=30
RUN_STALE_WALK=1

# ---------------------------------------------------------------------------
# Parse args.
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stale-days|--last-attested-stale-days|--last-mapped-stale-days)
      # Canonical: --stale-days. Aliases: --last-attested-stale-days (explicit
      # post-2026-06-08 clock-split naming); --last-mapped-stale-days (legacy
      # pre-clock-split name; accepted silently so existing callers keep working).
      if [[ $# -lt 2 ]]; then
        echo "ERROR check-atlas-watch-drift: $1 requires a value" >&2
        exit 0
      fi
      STALE_THRESHOLD_DAYS="$2"
      shift 2
      ;;
    --no-stale-walk)
      RUN_STALE_WALK=0
      shift
      ;;
    *)
      echo "ERROR check-atlas-watch-drift: unknown arg '$1'" >&2
      exit 0
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Locate repo root.
# ---------------------------------------------------------------------------
REPO_ROOT=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
fi

if [[ -z "$REPO_ROOT" ]]; then
  # No repo context — nothing to walk. Always-exit-0 contract preserved.
  exit 0
fi

SYSTEMS_DIR="$REPO_ROOT/docs/architecture/systems"

if [[ ! -d "$SYSTEMS_DIR" ]]; then
  # No atlas directory — nothing to walk.
  exit 0
fi

# ---------------------------------------------------------------------------
# Date-to-epoch helper (BSD / GNU portable).
# Echoes epoch seconds for YYYY-MM-DD, or empty string on parse failure.
# Review: when neither GNU nor BSD branch produces an epoch, function returns
# empty AND the STALE-walk emits a warning to stderr — detect-then-silently-pick
# is a footgun (coordinator CLAUDE.md § Implementation Standards).
# ---------------------------------------------------------------------------
date_to_epoch() {
  local d="$1"
  local e=""
  if date --version >/dev/null 2>&1; then
    e=$(date -d "$d" +%s 2>/dev/null || echo "")
  else
    e=$(date -j -f "%Y-%m-%d" "$d" +%s 2>/dev/null || echo "")
  fi
  printf '%s' "$e"
}

TODAY_EPOCH=$(date +%s)

# ---------------------------------------------------------------------------
# Per-system walk: enumerate atlas pages, run `.watch.sh` siblings.
# ---------------------------------------------------------------------------
# Use a literal glob; if no matches, bash leaves the pattern unchanged. Guard.
shopt -s nullglob 2>/dev/null || true

cd "$REPO_ROOT"

ATLAS_PAGES=( "$SYSTEMS_DIR"/*.md )

for atlas in "${ATLAS_PAGES[@]}"; do
  [[ -f "$atlas" ]] || continue
  base=$(basename "$atlas" .md)
  watch_script="$SYSTEMS_DIR/$base.watch.sh"

  if [[ -f "$watch_script" ]]; then
    # Run script with cwd = repo root, capture stdout+exit.
    set +e
    out=$(bash "$watch_script" 2>/dev/null)
    rc=$?
    set -e

    if (( rc != 0 )); then
      echo "ERROR $base: $base.watch.sh exit=$rc"
      continue
    fi

    # Validate stdout: must be exactly one non-empty line matching the contract.
    # Review: total_lines variable removed — line_count (awk non-empty count) covers empty-string case (line_count=0) already.
    line_count=$(printf '%s' "$out" | awk 'NF{c++} END{print c+0}')

    if (( line_count != 1 )); then
      echo "MALFORMED $base: $base.watch.sh output unparseable"
      continue
    fi

    # Strip trailing newline(s) for parsing.
    first_line=$(printf '%s' "$out" | head -n 1)
    # Split first token + remainder.
    first_tok="${first_line%% *}"
    rest="${first_line#"$first_tok"}"
    rest="${rest# }"  # drop one separating space
    second_tok="${rest%% *}"

    if [[ "$first_tok" == "FRESH" || "$first_tok" == "DRIFT" || "$first_tok" == "MISSING" ]] \
       && [[ "$second_tok" == "$base" ]]; then
      echo "$first_line"
    else
      echo "MALFORMED $base: $base.watch.sh output unparseable"
    fi
  else
    echo "FRESH $base (no watch script)"
  fi
done

# ---------------------------------------------------------------------------
# STALE walk (default-on): emit STALE for any atlas whose last_attested age
# exceeds the threshold.
# ---------------------------------------------------------------------------
if (( RUN_STALE_WALK == 1 )); then
  for atlas in "${ATLAS_PAGES[@]}"; do
    [[ -f "$atlas" ]] || continue
    base=$(basename "$atlas" .md)

    # Extract last_attested from frontmatter (grep+sed idiom mirroring
    # check-arch-audit-staleness.sh:64-73).
    line=$(grep -m1 '^last_attested:' "$atlas" 2>/dev/null || true)
    [[ -z "$line" ]] && continue

    last_date=$(printf '%s\n' "$line" \
      | sed -n 's/^last_attested:[[:space:]]*\([0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]\).*/\1/p')
    [[ -z "$last_date" ]] && continue

    last_epoch=$(date_to_epoch "$last_date")
    if [[ -z "$last_epoch" ]]; then
      echo "STALE-walk: skipped $base — no portable date-to-epoch on this platform (last_attested=$last_date)" >&2
      continue
    fi

    age_days=$(( (TODAY_EPOCH - last_epoch) / 86400 ))
    # (( ... )) && ... is safe under set -e — condition is in an AND-OR list, exempt from set -e exit.
    (( age_days < 0 )) && age_days=0

    if (( age_days > STALE_THRESHOLD_DAYS )); then
      echo "STALE $base last_attested=$last_date age=${age_days}d"
    fi
  done
fi

exit 0
