#!/usr/bin/env bash
# coordinator-handoff-archive.sh — canonical handoff-archive ceremony (D4 divergence-kill).
#
# Purpose: single implementation of the handoff archive operation, replacing the inline
# archive blocks in /handoff Step 1 (chain shape) and /workstream-complete Step 2.7
# (normal shape). Chunk C3b adds the --supersede shape (status:consumed +
# deployment_state:abandoned mutation via the authorized-writer path).
#
# Usage:
#   coordinator-handoff-archive.sh <handoff-path> [--stamp-shipped] [--exclude <path>] [--supersede]
#   coordinator-handoff-archive.sh <handoff-path> --stamp-only [--exclude <path>]
#
# Modes / flag model:
#   default (chain)  — live-children guard + YYYY-MM git mv; NO stamp
#   --stamp-shipped  — stamp_shipped_in (--allow-branch-tip-fallback) + Session-Id-trailer
#                      verify + live-children guard + YYYY-MM git mv
#   --stamp-only     — live-children guard; if safe: stamp_shipped_in + Session-Id-trailer
#                      verify + deployment_state:shipped; NO git mv (file stays in
#                      state/handoffs/ for sweep-shipped-handoffs.sh to archive later).
#                      Mutually exclusive with --stamp-shipped (and --supersede, which implies
#                      --stamp-shipped). Guard exit 0/2 → do NOT stamp; exit 0 (retention is
#                      not an error). Guard exit 1 → stamp in place; exit 0.
#   --supersede      — status:consumed + deployment_state:abandoned via cs_supersede_handoff;
#                      implies --stamp-shipped; trailer-verify suppressed (trusts branch-tip fallback)
#   NOTE: --supersede implies --stamp-shipped (enforced per spec § C3b).
#   NOTE: --stamp-only and --stamp-shipped are mutually exclusive (exit 2 if both given).
# Review: code-reviewer A-F2 — updated stale stub comment to reflect real implemented contract.
#
# Flags:
#   --exclude <path>  — passed through to handoff-has-live-children.sh; repeatable;
#                       chain mode (/handoff) passes --exclude "$HANDOFF_FILE" so the
#                       just-written successor is dropped from the live set before the scan
#   --stamp-shipped   — activates stamp_shipped_in + Session-Id-trailer verify (normal/wsc)
#   --stamp-only      — stamp in place without git mv (Step 2.7 demotion; sweep archives later)
#   --supersede       — C3b extension point; currently a named stub that exits non-zero
#
# Live-children guard (UNCONDITIONAL — runs in all modes, no flag):
#   guard exit 1 (safe-to-archive)         → proceed (git mv for default/stamp-shipped/supersede;
#                                             stamp-in-place for --stamp-only)
#   guard exit 0 (has-live-children)       → DO-NOT-stamp/move; log to stderr; exit 0
#   guard exit 2 (indeterminate/fail-closed) → DO-NOT-stamp/move; log to stderr; exit 0
#   Retention is not an error. DO NOT fall through on exit 2 — fail-open archiving is
#   the exact corruption this guard exists to prevent.
#
# git mv:
#   Derives YYYY-MM from handoff filename prefix; creates archive/handoffs/YYYY-MM/.
#   Flat fallback (archive/handoffs/<bn>) for filenames with no YYYY-MM date prefix.
#   On git mv failure (already moved by concurrent session): log to stderr + exit 0.
#
# Intentional reconciliation #1 (flat→YYYY-MM for chain): chain-archival now uses YYYY-MM
#   subfolder, matching wsc+supersede convention and the real on-disk archive tree layout.
#   Flat fallback only for filenames without a YYYY-MM date prefix.
#
# Intentional reconciliation #2 (universal live-children guard): the supersede path
#   currently has no guard in handoff/SKILL.md; this script adds it unconditionally to
#   all modes as fail-closed correctness (archiving a live merge-parent orphans children).
#
# Spec: docs/plans/2026-06-30-session-terminator-mechanism-unification.md § C3a/C3b
# Caller (post-Wave-2 repoint): /handoff Step 1 (C5); /workstream-complete Step 2.7 (C6)
# BSD-portable bash>=4; GNU-isms guarded per DR-148.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash>=4 guard — must be reachable on bash 3.2 (plain comparison, no bash-4 syntax)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "coordinator-handoff-archive.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Plugin root — never hardcoded; survives marketplace-install layout
# ---------------------------------------------------------------------------
_doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then
  echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2
  exit 1
fi
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}"
# shellcheck source=../lib/coordinator-trusted-root-guard.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/coordinator-trusted-root-guard.sh"
coordinator_trusted_root_guard --mode=fail-loud --root="$PLUGIN_ROOT" --site="$0"

# Source the state-root seam — must precede coordinator_state_root calls (C4 per-repo repoint)
_CSR_LIB_DIR="${PLUGIN_ROOT}/lib"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

# ---------------------------------------------------------------------------
# DR-210 facade router — source shared helper (strang-01 C8)
# Cold-fallback note (Design pin 4 / P3): legacy_* functions below access
# PLUGIN_ROOT (set above via direct .doe-root file read) — NEVER via
# 'machine-local get' CLI (unreachable in a cold session-init-hook shell).
# Both this script and sweep-shipped-handoffs.sh are session-init-hook-invoked;
# the direct-file-read cold-fallback path is load-bearing.
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"

# ---------------------------------------------------------------------------
# DR-210 legacy functions — verbatim capture of the three inline node calls
# that previously bypassed the lib (strang-01 C8 body-swap).
# Called ONLY on State 1 (coordinator_core.client absent on disk).
# Variables (PLUGIN_ROOT, handoff_abs, matched_sha) are resolved at call time
# from the enclosing script scope (bash closures — not subshells).
# ---------------------------------------------------------------------------

# legacy_stamp_sibling_correction: verbatim capture of the sibling-SHA
# correction node call (stamp-shipped-in.js). Shared by both the
# --stamp-shipped path and the --stamp-only path (identical invocation).
legacy_stamp_sibling_correction() {
  node "${PLUGIN_ROOT}/bin/stamp-shipped-in.js" \
    --handoff "$handoff_abs" --sha "${matched_sha:0:8}" \
    || echo "coordinator-handoff-archive.sh: WARNING stamp correction failed" >&2
}

# legacy_ship: verbatim capture of the handoff-transition.js ship call in
# --stamp-only path (sets deployment_state:shipped).
legacy_ship() {
  node "${PLUGIN_ROOT}/bin/handoff-transition.js" ship --handoff "$handoff_abs" \
    || echo "coordinator-handoff-archive.sh: WARNING deployment_state:shipped write failed for ${handoff_abs}" >&2
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
HANDOFF_PATH=""
DO_STAMP=0
DO_STAMP_ONLY=0
DO_SUPERSEDE=0
EXCLUDE_PATHS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stamp-shipped)
      DO_STAMP=1
      shift
      ;;
    --stamp-only)
      DO_STAMP_ONLY=1
      shift
      ;;
    --supersede)
      DO_SUPERSEDE=1
      shift
      ;;
    --exclude)
      if [[ -z "${2-}" ]]; then
        echo "coordinator-handoff-archive.sh: --exclude requires an argument" >&2
        exit 2
      fi
      EXCLUDE_PATHS+=("$2")
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "coordinator-handoff-archive.sh: unknown flag: $1" >&2
      exit 2
      ;;
    *)
      if [[ -z "$HANDOFF_PATH" ]]; then
        HANDOFF_PATH="$1"
      else
        echo "coordinator-handoff-archive.sh: unexpected extra argument: $1" >&2
        exit 2
      fi
      shift
      ;;
  esac
done

# Remaining positional after --
if [[ $# -gt 0 && -z "$HANDOFF_PATH" ]]; then
  HANDOFF_PATH="$1"
fi

if [[ -z "$HANDOFF_PATH" ]]; then
  cat >&2 <<'EOF'
coordinator-handoff-archive.sh: usage:
  coordinator-handoff-archive.sh <handoff-path> [--stamp-shipped] [--exclude <path>] [--supersede]
  coordinator-handoff-archive.sh <handoff-path> --stamp-only [--exclude <path>]
EOF
  exit 2
fi

if [[ ! -f "$HANDOFF_PATH" ]]; then
  echo "coordinator-handoff-archive.sh: handoff not found: ${HANDOFF_PATH}" >&2
  exit 2
fi

# Resolve to absolute path (guard requires it for cd-based resolution)
handoff_abs="$(cd "$(dirname "$HANDOFF_PATH")" && pwd)/$(basename "$HANDOFF_PATH")"

# ---------------------------------------------------------------------------
# --supersede implies --stamp-shipped (enforced per spec § C3b).
# Trailer-verify is stamp-shipped-path-only (NOT supersede) — guarded below.
# ---------------------------------------------------------------------------
if [[ "$DO_SUPERSEDE" -eq 1 ]]; then
  DO_STAMP=1
fi

# --stamp-only and --stamp-shipped are mutually exclusive.
# --supersede also triggers this check because it sets DO_STAMP=1 above.
if [[ "$DO_STAMP_ONLY" -eq 1 && "$DO_STAMP" -eq 1 ]]; then
  echo "coordinator-handoff-archive.sh: --stamp-only and --stamp-shipped (or --supersede) are mutually exclusive — do not combine them" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# --stamp-shipped: stamp_shipped_in + Session-Id-trailer verify
# Trailer-verify is --stamp-shipped-path-only (NOT --supersede) per spec § C3a/C3b.
# ---------------------------------------------------------------------------
if [[ "$DO_STAMP" -eq 1 ]]; then
  # Call stamp_shipped_in in a subshell to isolate set -u from the stamp lib's
  # 'local sha' pattern (stamp_shipped_in declares 'local sha' without explicit
  # initialization; referencing it with set -u active triggers "unbound variable"
  # on some bash builds before the fallback branch assigns it).
  # Review: code-reviewer F7 — capture subshell exit; surface stamp State-3 failures as a
  # warning (archive.sh own exit remains 0 — retention is not an error, but a broken stamp
  # engine should be visible to the operator).
  _stamp_shipped_rc=0
  (
    set +u
    # shellcheck source=/dev/null
    source "${PLUGIN_ROOT}/lib/coordinator-archive-stamp.sh"
    stamp_shipped_in "$handoff_abs" --allow-branch-tip-fallback
  ) || _stamp_shipped_rc=$?
  if [[ "$_stamp_shipped_rc" -ne 0 ]]; then
    echo "coordinator-handoff-archive.sh: WARNING stamp_shipped_in exited ${_stamp_shipped_rc} — stamp transport failure (State-3); archival continues" >&2
  fi

  # Session-Id-trailer verification of the stamped SHA.
  # Trailer-verify is --stamp-shipped-path-only (NOT --supersede) per spec § C3a/C3b.
  # Only meaningful when CLAUDE_CODE_SESSION_ID is set (the per-session platform var).
  if [[ "$DO_SUPERSEDE" -eq 0 && -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
    # Read back the stamped SHA from frontmatter (strip leading/trailing whitespace)
    stamped_sha="$(awk '
      !infm && /^---[[:space:]]*$/ { infm=1; next }
      infm && /^---[[:space:]]*$/ { exit }
      infm && /^shipped_in:/ { val=$0; sub(/^shipped_in:[[:space:]]*/, "", val); print val; exit }
    ' "$handoff_abs" 2>/dev/null || true)"
    stamped_sha="${stamped_sha// /}"  # strip any remaining spaces (portable; no sed -E)

    if [[ -n "$stamped_sha" && "$stamped_sha" != "null" ]]; then
      trailer="$(git show --format='%(trailers:key=Session-Id)' --no-patch "$stamped_sha" 2>/dev/null || true)"
      if [[ "$trailer" != *"${CLAUDE_CODE_SESSION_ID}"* ]]; then
        # Stamp landed a sibling session's branch-tip commit; walk git log for this session's SHA
        matched_sha=""
        while IFS= read -r candidate; do
          cand_trailer="$(git show --format='%(trailers:key=Session-Id)' --no-patch "$candidate" 2>/dev/null || true)"
          if [[ "$cand_trailer" == *"${CLAUDE_CODE_SESSION_ID}"* ]]; then
            matched_sha="$candidate"
            break
          fi
        done < <(git log --format=%H -n 20 HEAD 2>/dev/null || true)

        if [[ -n "$matched_sha" ]]; then
          echo "coordinator-handoff-archive.sh: stamped SHA (${stamped_sha}) belongs to sibling session; correcting to ${matched_sha:0:8}" >&2
          _stamp_params="$(jq -cn --arg hp "$handoff_abs" --arg sha "${matched_sha:0:8}" '{handoff_path:$hp,sha:$sha}')"
          strangle_route_mutation "handoff.stamp" "legacy_stamp_sibling_correction" "$_stamp_params"
        else
          echo "coordinator-handoff-archive.sh: no session-matched SHA in last 20 commits; shipped_in recorded as-is" >&2
        fi
      fi
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Live-children guard — UNCONDITIONAL (all modes, no flag)
# AC9: the guard call below is intentionally NOT wrapped in any
# DO_STAMP / DO_STAMP_ONLY / DO_SUPERSEDE conditional. Do not move it
# behind a flag — archiving a live merge-parent orphans children.
# Tri-state contract: exit 1 = safe-to-archive → proceed; exit 0 OR exit 2 = DO-NOT-move
# ---------------------------------------------------------------------------
guard="${PLUGIN_ROOT}/bin/handoff-has-live-children.sh"

if [[ ! -f "$guard" ]]; then
  echo "coordinator-handoff-archive.sh: live-children guard not found: ${guard}" >&2
  exit 2
fi

# Build exclude args array (bash-4 safe with the nounset-friendly empty-array expansion)
guard_args=()
for exc in "${EXCLUDE_PATHS[@]+"${EXCLUDE_PATHS[@]}"}"; do
  guard_args+=("--exclude" "$exc")
done

# The guard call is SHARED by all archive modes (default chain-archival, --stamp-shipped,
# --supersede, --stamp-only). Exit 0/1/2 are the only expected return codes (DR-215 removes
# the UDS version-sentinel gate; invoke has no skew concept, so exit 3 can never occur).
# Negative-spec: do NOT pass skew-degrade flags to the guard — that contract is retired.

guard_exit=0
bash "$guard" "${guard_args[@]+"${guard_args[@]}"}" "$handoff_abs" || guard_exit=$?

if [[ "$guard_exit" -ne 1 ]]; then
  # exit 0 = has-live-children; exit 2 = indeterminate/fail-closed
  # → DO-NOT-move in all cases. Retention is not an error: exit 0 to let the caller continue.
  if [[ "$guard_exit" -eq 0 ]]; then
    echo "coordinator-handoff-archive.sh: predecessor retained — still a live merge-parent of another active handoff" >&2
  else
    echo "coordinator-handoff-archive.sh: guard indeterminate (exit ${guard_exit}) — fail-closed; predecessor retained to avoid data loss" >&2
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# --stamp-only: stamp_shipped_in + deployment_state:shipped; then exit (no git mv).
# Guard has cleared (guard_exit=1 = safe). Stamp the handoff in place and let the
# async sweep-shipped-handoffs.sh janitor pick it up later for the git mv step.
# ---------------------------------------------------------------------------
if [[ "$DO_STAMP_ONLY" -eq 1 ]]; then
  # stamp_shipped_in — identical call to --stamp-shipped (with branch-tip fallback).
  # Review: code-reviewer F7 — capture subshell exit; surface stamp State-3 failures.
  _stamp_only_rc=0
  (
    set +u
    # shellcheck source=/dev/null
    source "${PLUGIN_ROOT}/lib/coordinator-archive-stamp.sh"
    stamp_shipped_in "$handoff_abs" --allow-branch-tip-fallback
  ) || _stamp_only_rc=$?
  if [[ "$_stamp_only_rc" -ne 0 ]]; then
    echo "coordinator-handoff-archive.sh: WARNING stamp_shipped_in exited ${_stamp_only_rc} — stamp transport failure (State-3); --stamp-only continues" >&2
  fi

  # Session-Id-trailer verification of the stamped SHA (same as --stamp-shipped path).
  # Only meaningful when CLAUDE_CODE_SESSION_ID is set (the per-session platform var).
  if [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
    stamped_sha="$(awk '
      !infm && /^---[[:space:]]*$/ { infm=1; next }
      infm && /^---[[:space:]]*$/ { exit }
      infm && /^shipped_in:/ { val=$0; sub(/^shipped_in:[[:space:]]*/, "", val); print val; exit }
    ' "$handoff_abs" 2>/dev/null || true)"
    stamped_sha="${stamped_sha// /}"

    if [[ -n "$stamped_sha" && "$stamped_sha" != "null" ]]; then
      trailer="$(git show --format='%(trailers:key=Session-Id)' --no-patch "$stamped_sha" 2>/dev/null || true)"
      if [[ "$trailer" != *"${CLAUDE_CODE_SESSION_ID}"* ]]; then
        matched_sha=""
        while IFS= read -r candidate; do
          cand_trailer="$(git show --format='%(trailers:key=Session-Id)' --no-patch "$candidate" 2>/dev/null || true)"
          if [[ "$cand_trailer" == *"${CLAUDE_CODE_SESSION_ID}"* ]]; then
            matched_sha="$candidate"
            break
          fi
        done < <(git log --format=%H -n 20 HEAD 2>/dev/null || true)

        if [[ -n "$matched_sha" ]]; then
          echo "coordinator-handoff-archive.sh: stamped SHA (${stamped_sha}) belongs to sibling session; correcting to ${matched_sha:0:8}" >&2
          _stamp_params="$(jq -cn --arg hp "$handoff_abs" --arg sha "${matched_sha:0:8}" '{handoff_path:$hp,sha:$sha}')"
          strangle_route_mutation "handoff.stamp" "legacy_stamp_sibling_correction" "$_stamp_params"
        else
          echo "coordinator-handoff-archive.sh: no session-matched SHA in last 20 commits; shipped_in recorded as-is" >&2
        fi
      fi
    fi
  fi

  # Ensure deployment_state: shipped is set.
  # sweep-shipped-handoffs.sh matches on BOTH deployment_state:shipped AND a resolvable
  # shipped_in: SHA; stamp_shipped_in above only sets shipped_in: — this call sets the
  # deployment_state field via the authorized-writer path (handoff-transition.js ship).
  _ship_params="$(jq -cn --arg hp "$handoff_abs" '{verb:"ship",handoff_path:$hp}')"
  strangle_route_mutation "handoff.transition" "legacy_ship" "$_ship_params" || exit $?

  exit 0
fi

# ---------------------------------------------------------------------------
# --supersede: status:consumed + deployment_state:abandoned mutation
# Authorized-writer path — uses cs_supersede_handoff (coordinator-archive-stamp.sh
# family) which delegates to handoff-transition.js supersede (Bash-driven node write,
# structurally invisible to the Edit-only consumed-handoff freeze hook).
# Called BEFORE git mv — mutation must target the LIVE state/handoffs/ path.
# example-orchestration-hub's native handoff_transition.py _resolve_path deliberately rejects any
# path outside state/handoffs/ (mutation verbs are live-only by design); calling
# this on the post-mv archive path raises "handoff_path escapes state/handoffs/"
# on any machine where the native op is resolvable, silently swallowing the
# mutation (root-caused 2026-07-08). Runs here, parallel to stamp_shipped_in
# above, only after the live-children guard has cleared (guard_exit == 1) —
# a handoff the guard decided to RETAIN never reaches this point (guard exits
# 0/2 return early above, before this line).
# Trailer-verify does NOT run in supersede mode (per spec § C3b — supersede trusts
# stamp_shipped_in --allow-branch-tip-fallback; no additional trailer assertion).
# A failed mutation is NOT swallowed as a warning — fail loud so the caller does
# not commit a half-superseded handoff (git mv of an unmutated file would silently
# ship a handoff with stale deployment_state).
# ---------------------------------------------------------------------------
if [[ "$DO_SUPERSEDE" -eq 1 ]]; then
  supersede_rc=0
  (
    # shellcheck source=/dev/null
    source "${PLUGIN_ROOT}/lib/coordinator-archive-stamp.sh"
    cs_supersede_handoff "$handoff_abs"
  ) || supersede_rc=$?
  if [[ "$supersede_rc" -ne 0 ]]; then
    echo "coordinator-handoff-archive.sh: ERROR: cs_supersede_handoff exited ${supersede_rc} for ${handoff_abs}" >&2
    exit "$supersede_rc"
  fi
fi

# ---------------------------------------------------------------------------
# YYYY-MM git mv — derive from handoff filename date prefix
# ---------------------------------------------------------------------------
# Resolve repo root via the per-repo state-root seam (C4 seam-adoption).
# coordinator_state_root (no flag) returns $EXAMPLE_ORCHESTRATION_HUB_ROOT/state for the meta-repo,
# or $GIT_ROOT/state for sibling repos — strip /state to get the git-mv target.
_cha_state_root="$(coordinator_state_root)" || {
  echo "coordinator-handoff-archive.sh: cannot resolve per-repo state root via coordinator_state_root" >&2
  exit 2
}
repo_root="${_cha_state_root%/state}"

bn="$(basename "$handoff_abs")"
ym="${bn:0:7}"

# Validate YYYY-MM prefix: four digits, hyphen, two digits
if [[ "$ym" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
  dest_dir="${repo_root}/archive/handoffs/${ym}"
  dest_rel="archive/handoffs/${ym}/${bn}"
else
  # Flat fallback for filenames without a YYYY-MM date prefix (e.g. install batons)
  dest_dir="${repo_root}/archive/handoffs"
  dest_rel="archive/handoffs/${bn}"
fi

mkdir -p "${dest_dir}"

src_rel="state/handoffs/${bn}"

if ! git -C "${repo_root}" mv "${src_rel}" "${dest_rel}" 2>/dev/null; then
  echo "coordinator-handoff-archive.sh: git mv failed — file may already have been moved by a concurrent session; continuing" >&2
fi

exit 0
