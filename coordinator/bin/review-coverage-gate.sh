#!/usr/bin/env bash
# review-coverage-gate.sh — chain-end code-review coverage gate for
# /workstream-complete Step 2.9 and /merge-to-main.
#
# Purpose: verifies mechanically that every commit in a workstream's chain diff
# is covered by at least one code-reviewer trail record. Closes the gap where
# a confident EM substitutes handoff prose for per-commit review reconciliation.
#
# Output (stdout): one line in the form:
#   range=<range> chain_commits=N covered=M uncovered=K VERDICT={COVERED|UNCOVERED}
# On UNCOVERED: also emits one "uncovered: <sha> <subject>" line per gap to stderr.
#
# Exit: 0 on both COVERED and UNCOVERED (verdict-line shape, matching
# review-brightline-gate.sh). The calling skill parses VERDICT and halts on
# UNCOVERED — this gate never owns the halt.
#
# Usage:
#   review-coverage-gate.sh [--scope-paths <pathspec>...] [<range>]
#
#   <range>                  git rev-range; default: $(git merge-base origin/main HEAD)..HEAD
#   --scope-paths <paths>... Scope the CHAIN set to commits touching these paths (via
#                            `git rev-list --no-merges <range> -- <paths>`). The REVIEWED
#                            set is NEVER path-filtered — any session's trail record that
#                            covers a commit credits that commit, regardless of which paths
#                            the record was scoped to.
#
# Missing/empty --scope-paths: falls back to unscoped whole-chain (not an error).
# See Design § "Scope filtering — asymmetric by design" for the full rationale.
#
# Key design decisions (see plan Design § for full rationale):
#
#   --no-merges on chain_set (DELIBERATE):
#     Merge commits carry no authored diff that requires review. Additionally,
#     path-history-simplification without --no-merges can non-deterministically
#     include merge commits on shared branches, making chain_set non-reproducible.
#     Merge commits are excluded from chain_set by design, not by accident.
#
#   Unscoped reviewed_set (DELIBERATE — opposite of review-brightline-gate.sh):
#     review-brightline-gate.sh narrows to --session-id to avoid false PARTITION-
#     MANDATORY verdicts from peer commits that are already reviewed. The coverage
#     gate must do the REVERSE: credit ALL sessions' trail records toward the union
#     reviewed_set. A commit reviewed by any session is covered. Scoping reviewed_set
#     to one session would cause false UNCOVERED verdicts on multi-session features —
#     exactly the failure shape this gate is designed to catch.
#
# Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C3

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Script-dir resolution — locate sibling scripts portably
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../lib"
CORE="${LIB_DIR}/review-coverage-core.sh"
LIST_RECORDS="${SCRIPT_DIR}/list-review-trail-records.sh"

if [[ ! -f "$CORE" ]]; then
  echo "ERROR: review-coverage-core.sh not found at $CORE" >&2
  exit 1
fi
if [[ ! -f "$LIST_RECORDS" ]]; then
  echo "ERROR: list-review-trail-records.sh not found at $LIST_RECORDS" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Argument parsing: --scope-paths and optional positional range
# ---------------------------------------------------------------------------
declare -a SCOPE_PATHS=()
RANGE_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope-paths)
      shift
      # Consume all remaining non-flag args as pathspecs until we see a bare --
      # or a known flag.
      while [[ $# -gt 0 && "$1" != "--" && "$1" != --* ]]; do
        SCOPE_PATHS+=("$1")
        shift
      done
      ;;
    --)
      shift
      # Everything after -- is the range
      if [[ $# -gt 0 ]]; then
        RANGE_ARG="$1"
        shift
      fi
      ;;
    -*)
      echo "review-coverage-gate.sh: unknown option: $1" >&2
      exit 1
      ;;
    *)
      RANGE_ARG="$1"
      shift
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve the chain range
# ---------------------------------------------------------------------------
# Review: code-reviewer F4 — validate the caller-supplied range against the same
# no-leading-dash pattern the core applies to untrusted trail-JSON sha_range. The
# core's SAFE_RANGE protects trail data, not this gate's own positional range arg;
# without this guard a leading-dash range (e.g. "--output=/x..y") would reach
# `git rev-list` as a flag. Hardening the direct-invocation path to parity with the
# trail-JSON path.
if [[ -n "${RANGE_ARG:-}" ]]; then
  if ! [[ "$RANGE_ARG" =~ ^[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*\.\.\.?[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*$ ]]; then
    echo "review-coverage-gate.sh: unsafe range argument: ${RANGE_ARG}" >&2
    exit 1
  fi
fi

if [[ -z "${RANGE_ARG:-}" ]]; then
  MERGE_BASE=$(git merge-base origin/main HEAD 2>/dev/null) || {
    echo "review-coverage-gate.sh: cannot resolve origin/main — pass a range explicitly" >&2
    exit 1
  }
  RANGE="${MERGE_BASE}..HEAD"
else
  RANGE="$RANGE_ARG"
fi

# ---------------------------------------------------------------------------
# Compute reviewed_set — union across ALL trail records (live + archive),
# ALL sessions, ALL verdicts except pending.
#
# DELIBERATELY UNSCOPED — see file-top docstring for why the brightline
# --session-id approach does NOT transfer here: brightline narrows to avoid
# peer false-positives; coverage must widen to credit peer reviews.
#
# The reviewed_set is populated by calling review-coverage-core.sh with the
# full list of trail paths from list-review-trail-records.sh. The core handles:
#   - JSON-OR-JSONL dual-shape parse
#   - SAFE_RANGE argument-injection validation
#   - scope_kind filter (plan/integration records skipped)
#   - verdict filter (pending excluded; ok/warn/blocked/waived/absent included)
# ---------------------------------------------------------------------------

# Collect trail paths (newline-separated) from the archive-aware lister.
# Empty trail dir → zero lines → empty reviewed_set → all commits UNCOVERED.
# (No crash; the core handles an empty input list gracefully.)
TRAIL_PATHS=""
TRAIL_PATHS=$(bash "$LIST_RECORDS" 2>/dev/null) || true

# Build the reviewed_set: call the shared core CLI with trail paths as positional args.
# We pass them via xargs to avoid argument-list length limits on large trail histories.
declare -a REVIEWED_SET_ARRAY=()
if [[ -n "$TRAIL_PATHS" ]]; then
  # Use a while-read loop (skipping empties) to collect paths; then call core with them.
  # mapfile <<< "$VAR" produces a trailing empty-string element; the loop avoids that.
  # Review: code-reviewer — mapfile trailing empty element is untidy; while-read skips empties
  declare -a TRAIL_PATH_ARRAY=()
  while IFS= read -r p; do [[ -n "$p" ]] && TRAIL_PATH_ARRAY+=("$p"); done <<< "$TRAIL_PATHS"
  # Call the shared core: --reviewed-set <paths...>.
  # --on-record-error skip: the gate scans the FULL archive (hundreds of historical
  # records, some malformed or non-record sidecars sharing the trail dir); an ancient
  # corrupt file must not abort coverage of today's chain. Skips are warned (stderr
  # flows through, NOT suppressed) and are fail-safe — an unparseable record credits
  # no commits, so its coverage is simply uncounted (commits surface as more review).
  # Review: code-reviewer — comment said --on-parse-error but the flag is --on-record-error
  REVIEWED_OUTPUT=$(bash "$CORE" --reviewed-set --on-record-error skip "${TRAIL_PATH_ARRAY[@]}") || {
    echo "review-coverage-gate.sh: review-coverage-core.sh failed" >&2
    exit 1
  }
  if [[ -n "$REVIEWED_OUTPUT" ]]; then
    mapfile -t REVIEWED_SET_ARRAY <<< "$REVIEWED_OUTPUT"
  fi
fi

# Build a lookup set for O(1) membership tests.
declare -A REVIEWED_LOOKUP=()
for sha in "${REVIEWED_SET_ARRAY[@]}"; do
  [[ -n "$sha" ]] && REVIEWED_LOOKUP["$sha"]=1
done

# ---------------------------------------------------------------------------
# Compute chain_set — commits in the range, excluding merges, optionally
# scoped to --scope-paths.
#
# --no-merges is DELIBERATE: merge commits carry no authored diff that requires
# review; path-history-simplification without --no-merges can non-deterministically
# include merge commits on shared branches, making chain_set non-reproducible.
# ---------------------------------------------------------------------------
declare -a REV_LIST_CMD=("git" "rev-list" "--no-merges" "$RANGE")
if [[ ${#SCOPE_PATHS[@]} -gt 0 ]]; then
  REV_LIST_CMD+=("--" "${SCOPE_PATHS[@]}")
fi

CHAIN_OUTPUT=$("${REV_LIST_CMD[@]}" 2>/dev/null) || {
  echo "review-coverage-gate.sh: git rev-list failed for range '$RANGE'" >&2
  exit 1
}

declare -a CHAIN_SET_ARRAY=()
if [[ -n "$CHAIN_OUTPUT" ]]; then
  mapfile -t CHAIN_SET_ARRAY <<< "$CHAIN_OUTPUT"
fi

# ---------------------------------------------------------------------------
# Compute coverage: uncovered = chain_set - reviewed_set
# Zero-commit chain → COVERED (no divide-by-zero, no crash).
# ---------------------------------------------------------------------------
CHAIN_COUNT=${#CHAIN_SET_ARRAY[@]}
UNCOVERED_COUNT=0
declare -a UNCOVERED_SHAS=()

for sha in "${CHAIN_SET_ARRAY[@]}"; do
  [[ -z "$sha" ]] && continue
  if [[ -z "${REVIEWED_LOOKUP[$sha]:-}" ]]; then
    UNCOVERED_SHAS+=("$sha")
    UNCOVERED_COUNT=$(( UNCOVERED_COUNT + 1 ))
  fi
done

COVERED_COUNT=$(( CHAIN_COUNT - UNCOVERED_COUNT ))

# ---------------------------------------------------------------------------
# Emit verdict line (stdout) — shape matches review-brightline-gate.sh.
# On UNCOVERED, emit one "uncovered: <sha> <subject>" per gap to stderr.
# ---------------------------------------------------------------------------
if [[ $UNCOVERED_COUNT -eq 0 ]]; then
  VERDICT="COVERED"
else
  VERDICT="UNCOVERED"
fi

printf 'range=%s chain_commits=%d covered=%d uncovered=%d VERDICT=%s\n' \
  "$RANGE" "$CHAIN_COUNT" "$COVERED_COUNT" "$UNCOVERED_COUNT" "$VERDICT"

if [[ "$VERDICT" == "UNCOVERED" ]]; then
  for sha in "${UNCOVERED_SHAS[@]}"; do
    subject=$(git log --format='%s' -1 "$sha" 2>/dev/null || echo "<unknown>")
    printf 'uncovered: %s %s\n' "$sha" "$subject" >&2
  done
fi

exit 0
