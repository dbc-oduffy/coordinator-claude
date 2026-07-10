#!/usr/bin/env bash
# rollup-derive.sh — derive an artifact's roll-up ship-state from its resolving
#                     commits, on demand, with no cached/stored state.
#
# Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C5
#
# Purpose: answer "which commits resolve <artifact-id>, and are they shipped?"
# by (1) finding every commit whose message carries a `Resolves: <artifact-id>`
# trailer (the format pinned by C4 — coordinator/docs/wiki/resolves-commit-trailer.md),
# and (2) delegating the "shipped?" question to check-shipped-on-main.sh. This
# script RE-DERIVES on every call; it never reads or writes a stored roll-up
# state (canonical-artifact-shapes.md: liveness/roll-up-state is derived, not
# stored — see the plan's Anti-scope section).
#
# Contract (four tokens, one emitted per call, plus the resolving SHA list):
#   shipped              — check-shipped-on-main.sh exit 0: all resolving
#                           commits are ancestors of origin/main.
#   not-shipped           — check-shipped-on-main.sh exit 1: >=1 resolving
#                           commit is not on origin/main.
#   unknown-error         — check-shipped-on-main.sh exit 2: not a git repo,
#                           or origin/main unreachable. PROPAGATED as its own
#                           token — never collapsed into not-shipped, since
#                           "could not determine" != "confirmed not shipped".
#   no-resolving-commits  — zero commits found with a `Resolves: <artifact-id>`
#                           trailer. This is a VACUOUS PASS, not an error — the
#                           normal pre-adoption state (mirrors the Session-Id:
#                           trailer's documented zero-match semantics in
#                           coordinator/docs/wiki/workstream-complete-review.md).
#
# Negative-spec: does NOT store, cache, or stamp a roll-up result anywhere.
# Does NOT collapse "unknown" into "not-shipped" — that would let a
# promotion decision treat "could not determine" as "confirmed not shipped".
#
# Guarded per DR-148 (bash >=4 + BSD coreutils; no GNU-only flags used here).

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}) — uses mapfile. On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SHIPPED="${SCRIPT_DIR}/check-shipped-on-main.sh"
PARSE_RESOLVES="${SCRIPT_DIR}/parse-resolves-trailer.sh"

usage() {
  cat <<'EOF'
Usage: rollup-derive.sh <artifact-id>

Derives the roll-up ship-state of <artifact-id> by finding all commits whose
message carries a `Resolves: <artifact-id>` trailer, then checking whether
those commits are all on origin/main.

Re-derives every call. Never reads or writes a stored roll-up state.

Output (stdout):
  <token>
  <resolving-sha> [<resolving-sha> ...]   (omitted if no-resolving-commits)

Tokens:
  shipped               all resolving commits are on origin/main
  not-shipped           >=1 resolving commit is not on origin/main
  unknown-error         repo/ref error (not a git repo, or origin/main unreachable)
  no-resolving-commits  no commits found with a Resolves: <artifact-id> trailer
EOF
}

if [[ $# -lt 1 || "$1" == "--help" || "$1" == "-h" ]]; then
  usage
  [[ $# -lt 1 ]] && exit 1
  exit 0
fi

ARTIFACT_ID="$1"

if [[ -z "$ARTIFACT_ID" ]]; then
  echo "rollup-derive: artifact-id must not be empty" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: find resolving commits via the pinned trailer format.
# Trailer format (pinned by C4): "Resolves: <artifact-id>" — exact string,
# one per line, multiple lines allowed per commit.
# ---------------------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "unknown-error"
  echo "rollup-derive: not inside a git repository" >&2
  exit 0
fi

# Review: code-reviewer (F1, P1) — plain substring --grep is only a CANDIDATE
# filter, not the exact match. --grep --fixed-strings is an unanchored
# substring match against the full commit message: a prefix-sharing
# artifact-id (e.g. querying `hnd-abc` against a commit carrying
# `Resolves: hnd-abc-def456`) would false-positive-match under substring
# comparison alone. Each candidate SHA below is re-checked via the exact-value
# primitive (parse-resolves-trailer.sh, C4) and kept only on a true `==` match
# against ARTIFACT_ID — never on substring containment.
mapfile -t CANDIDATE_SHAS < <(
  git log --all --format='%H' --grep="Resolves: ${ARTIFACT_ID}" --fixed-strings 2>/dev/null || true
)

RESOLVING_SHAS=()
for candidate_sha in "${CANDIDATE_SHAS[@]:-}"; do
  [[ -z "$candidate_sha" ]] && continue
  mapfile -t candidate_ids < <("$PARSE_RESOLVES" "$candidate_sha" 2>/dev/null || true)
  for candidate_id in "${candidate_ids[@]:-}"; do
    if [[ "$candidate_id" == "$ARTIFACT_ID" ]]; then
      RESOLVING_SHAS+=("$candidate_sha")
      break
    fi
  done
done

if [[ ${#RESOLVING_SHAS[@]} -eq 0 ]]; then
  echo "no-resolving-commits"
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 2: pass resolving SHAs to check-shipped-on-main.sh; propagate its
# three exit codes into our four-token contract (exit 2 -> unknown-error,
# never collapsed into not-shipped).
# ---------------------------------------------------------------------------
set +e
"$CHECK_SHIPPED" "${RESOLVING_SHAS[@]}" >/dev/null 2>&1
SHIPPED_RC=$?
set -e

case "$SHIPPED_RC" in
  0) echo "shipped" ;;
  1) echo "not-shipped" ;;
  2) echo "unknown-error" ;;
  *)
    echo "unknown-error"
    echo "rollup-derive: check-shipped-on-main.sh exited unexpected code ${SHIPPED_RC}" >&2
    ;;
esac

printf '%s\n' "${RESOLVING_SHAS[@]}"

exit 0
