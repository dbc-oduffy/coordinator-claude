#!/usr/bin/env bash
# mint-deliverable-id.sh — Mint or carry a deliverable_id for the fleet artifact spine.
#
# Purpose: Shared minting helper for all four authoring surfaces (coordinator-doc-new,
#          roadmap-planning, handoff, spinoff) so identity is minted identically everywhere.
#          Three paths:
#            carry      — --deliverable-id supplied → echo it unchanged (never re-mint)
#            stub       — --stub-id supplied → emit "dlv-<stub_id>" (D1: reuse stub identity)
#            slug       — --slug supplied → mint "dlv-<slug>-<6hex>" (uniqueness not crypto)
#          Logs which path was taken to stderr ("carry" / "mint-from-stub" / "mint-from-slug").
#
# Spec backlink: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § D1, C3a
#
# Usage:
#   mint-deliverable-id.sh --deliverable-id <existing>   # carry (idempotent)
#   mint-deliverable-id.sh --stub-id <stub_id>           # reuse stub identity
#   mint-deliverable-id.sh --slug <slug>                 # mint new with time hash
#
# Output: the deliverable_id on stdout; carry/mint path on stderr.
# Exit:   0 on success, 1 on usage error.

set -euo pipefail

# Bash >=4 guard (BSD macOS ships 3.2; brew bash required)
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Argument parsing — exactly one of --deliverable-id / --stub-id / --slug
# ---------------------------------------------------------------------------
DELIVERABLE_ID=""
STUB_ID=""
SLUG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deliverable-id)
      DELIVERABLE_ID="${2:-}"
      shift 2
      ;;
    --stub-id)
      STUB_ID="${2:-}"
      shift 2
      ;;
    --slug)
      SLUG="${2:-}"
      shift 2
      ;;
    -h|--help)
      grep '^# ' "$0" | sed 's/^# //'
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate: exactly one path must be selected
# ---------------------------------------------------------------------------
_MODE_COUNT=0
[[ -n "$DELIVERABLE_ID" ]] && (( _MODE_COUNT++ )) || true
[[ -n "$STUB_ID"        ]] && (( _MODE_COUNT++ )) || true
[[ -n "$SLUG"           ]] && (( _MODE_COUNT++ )) || true

if [[ "$_MODE_COUNT" -eq 0 ]]; then
  echo "ERROR: one of --deliverable-id, --stub-id, or --slug is required" >&2
  echo "Usage: mint-deliverable-id.sh --deliverable-id <id> | --stub-id <id> | --slug <slug>" >&2
  exit 1
fi

if [[ "$_MODE_COUNT" -gt 1 ]]; then
  echo "ERROR: --deliverable-id, --stub-id, and --slug are mutually exclusive" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# sha1 helper — prefer shasum (BSD/macOS), fall back to sha1sum (GNU/Linux)
# ---------------------------------------------------------------------------
_sha1_hex() {
  local input="$1"
  if command -v shasum &>/dev/null; then
    printf '%s' "$input" | shasum -a 1 | awk '{print $1}'
  elif command -v sha1sum &>/dev/null; then
    printf '%s' "$input" | sha1sum | awk '{print $1}'
  else
    echo "ERROR: neither shasum nor sha1sum found in PATH" >&2
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Path: carry — existing deliverable_id supplied; never re-mint
# ---------------------------------------------------------------------------
if [[ -n "$DELIVERABLE_ID" ]]; then
  echo "mint-deliverable-id: carry path — using existing id: ${DELIVERABLE_ID}" >&2
  printf '%s\n' "$DELIVERABLE_ID"
  exit 0
fi

# ---------------------------------------------------------------------------
# Path: stub — earliest artifact is a roadmap-spinoff stub; reuse its stub_id (D1)
# ---------------------------------------------------------------------------
if [[ -n "$STUB_ID" ]]; then
  RESULT="dlv-${STUB_ID}"
  echo "mint-deliverable-id: mint-from-stub path — minted: ${RESULT}" >&2
  printf '%s\n' "$RESULT"
  exit 0
fi

# ---------------------------------------------------------------------------
# Path: slug — plan or handoff with no parent stub; mint dlv-<slug>-<6hex>
# The 6hex is derived from slug + epoch-seconds + PID + RANDOM for uniqueness.
# Uniqueness is the goal; this is not cryptographic.
# ---------------------------------------------------------------------------
_HASH_INPUT="${SLUG}|$(date +%s)|$$|${RANDOM}"
_FULL_HASH="$(_sha1_hex "$_HASH_INPUT")"
_SIX_HEX="${_FULL_HASH:0:6}"
RESULT="dlv-${SLUG}-${_SIX_HEX}"
echo "mint-deliverable-id: mint-from-slug path — minted: ${RESULT}" >&2
printf '%s\n' "$RESULT"
exit 0
