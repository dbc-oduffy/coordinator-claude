#!/usr/bin/env bash
# append-plan-session.sh — DR-216 facade router: plan.append_session (strang-10).
#
# Purpose: routes plan.append_session through the example-orchestration-hub cc_invoke (native-primary)
# with the original script body preserved as legacy_append_plan_session (disk-absence
# fallback). Three-state routing model (Design pin 3):
#   State 1 (seam absent on disk) -> legacy_append_plan_session (current bash body, verbatim).
#   State 2 (seam present + invoke succeeds) -> native op ran; legacy NOT run.
#   State 3 (seam present + cc_invoke fails) -> exit 2; NEVER fall back to legacy.
#
# Spec backlink: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md
#
# Usage (unchanged from pre-facade — zero caller repoints):
#   append-plan-session.sh <absolute-or-repo-relative-plan-path>
#
# Exit 0: success or idempotent no-op (legacy path), or native op succeeded.
# Exit 2: native-path transport failure (fail-closed).
# Non-zero + stderr: malformed frontmatter or unresolvable session id (legacy path).
set -euo pipefail

# ---------------------------------------------------------------------------
# DR-216 facade router -- source shared helper (must precede legacy fn definition).
# Cold-fallback self-location: legacy_append_plan_session resolves its lib paths via
# BASH_SOURCE[0]-relative lookup inside the function body (unchanged from pre-facade).
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"
# Source coordinator-session.sh for facade-side session_id resolution (4-tier chain).
# native path only — dead on State-1 (legacy path), which re-parses "$@" and sources
# coordinator-session.sh itself inside legacy_append_plan_session.
# shellcheck source=../lib/coordinator-session.sh
source "${_FACADE_SCRIPT_DIR}/../lib/coordinator-session.sh"

# ---------------------------------------------------------------------------
# legacy_append_plan_session -- the pre-facade script body, preserved verbatim.
# Called ONLY on State 1 (coordinator_core.invoke absent on disk).
# BASH_SOURCE[0]-relative self-location inside the function is unchanged and safe.
# ---------------------------------------------------------------------------
legacy_append_plan_session() {
# append-plan-session.sh — Append a per-session record to a plan doc's agent_sessions:
#                          frontmatter array.
#
# Purpose: Idempotent helper that records which coordinator session worked a plan.
#          Fires after a successful cs_claim_plan in execute-plan Phase 1.5 Step 0,
#          reusing the same resolved session id — never re-derives it.
#
# Spec backlink: docs/plans/2026-06-27-ccos-2-plan-session-linkage.md § C2
#
# Encoding contract for agent_sessions: entries (block-style YAML list-of-string):
#   Each entry is the string "<session_id>|<status>|<created_at>"
#   - session_id : resolved session id (UUID-shaped, no '|')
#   - status     : OPEN string; value "working" at this fire point (NOT a closed enum)
#   - created_at : ISO-8601 UTC (from _cs_now_iso in coordinator-session.sh)
# All three fields guaranteed non-empty at write time.
# Consumers: do NOT use IFS='|' read -ra if any future field could be empty
#   (read -ra silently drops trailing empty fields).
#
# Usage: append-plan-session.sh <absolute-or-repo-relative-plan-path>
# Exit 0: success or idempotent no-op.
# Non-zero + stderr: malformed frontmatter or unresolvable session id.
#
# Concurrency:
#   Layer 2 (this script): mkdir-atomic per-plan-basename edit lock under
#     .git/coordinator-sessions/agent-sessions-locks/<plan-basename>.
#   Layer 3: dedup-on-session-id — idempotent even if the lock is bypassed.
#   Cross-machine residual: the lock and cs_claim_plan are per-machine .git/
#   constructs; two sessions on DIFFERENT machines can both append concurrently,
#   producing a git merge conflict at EOF. This is a named limitation of Fork A
#   (agent_sessions lives in a single shared plan file). See plan § Design fork.

set -euo pipefail

# Bash >=4 guard — (( )) and BASH_VERSINFO exist since bash 2.x so this is safe on 3.2.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Source coordinator-session.sh for _cs_resolve_session_id and _cs_now_iso.
# NEVER re-derive the resolution chain — source the canonical library.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/coordinator-session.sh
source "${SCRIPT_DIR}/../lib/coordinator-session.sh"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
  echo "Usage: append-plan-session.sh <plan-path>" >&2
  exit 1
fi

plan_file="$1"

# Resolve to absolute path
if [[ "${plan_file}" != /* ]]; then
  plan_file="$(pwd)/${plan_file}"
fi

if [[ ! -f "${plan_file}" ]]; then
  echo "ERROR: plan file not found: ${plan_file}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve session id — canonical 4-tier chain from coordinator-session.sh
# ---------------------------------------------------------------------------

session_id="$(_cs_resolve_session_id)"

if [[ -z "${session_id}" ]]; then
  echo "ERROR: cannot resolve session id (COORDINATOR_SESSION_ID / CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID not set and no sentinel found)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Locate .git dir portably via git rev-parse --git-dir
# ---------------------------------------------------------------------------

git_dir="$(git rev-parse --git-dir 2>/dev/null)" || {
  echo "ERROR: not inside a git repository" >&2
  exit 1
}
if [[ "${git_dir}" != /* ]]; then
  git_dir="$(pwd)/${git_dir}"
fi

# ---------------------------------------------------------------------------
# Acquire short mkdir-atomic edit lock.
# Poll every 100 ms (sleep 0.1), up to 2 s ceiling (20 iterations × 100 ms).
# POSIX-atomic on BSD/macOS — no flock. NOT date +%s%N (not BSD-portable).
# Lock dir is under .git (per-machine, not adjacent to the plan file).
# ---------------------------------------------------------------------------

plan_basename="$(basename "${plan_file}")"
locks_dir="${git_dir}/coordinator-sessions/agent-sessions-locks"
lockdir="${locks_dir}/${plan_basename}"

mkdir -p "${locks_dir}" 2>/dev/null || true

trap 'rmdir "${lockdir}" 2>/dev/null || true' EXIT

COUNTER=0
while ! mkdir "${lockdir}" 2>/dev/null; do
  COUNTER=$(( COUNTER + 1 ))
  if (( COUNTER >= 20 )); then
    echo "ERROR: timeout acquiring edit lock for ${plan_basename} (stale lock at ${lockdir}?)" >&2
    exit 1
  fi
  sleep 0.1
done

# ---------------------------------------------------------------------------
# Validate frontmatter: must begin with --- fence
# ---------------------------------------------------------------------------

first_line=""
read -r first_line < "${plan_file}" || true
if [[ "${first_line}" != "---" ]]; then
  echo "ERROR: malformed frontmatter in ${plan_file} (no leading --- fence)" >&2
  exit 1
fi

# Read all lines into array; locate closing --- fence
mapfile -t lines < "${plan_file}"
total_lines=${#lines[@]}

close_idx=-1
for (( i=1; i<total_lines; i++ )); do
  if [[ "${lines[$i]}" == "---" ]]; then
    close_idx=$i
    break
  fi
done

if (( close_idx < 0 )); then
  echo "ERROR: malformed frontmatter in ${plan_file} (no closing --- fence)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Parse agent_sessions: block; dedup-on-session-id (Layer 3).
# APPEND-ONLY — never rewrite or reorder peer lines.
# ---------------------------------------------------------------------------

in_agent_sessions=0
agent_sessions_key_idx=-1
last_entry_idx=-1

for (( i=1; i<close_idx; i++ )); do
  line="${lines[$i]}"

  if [[ "${line}" == "agent_sessions:" ]]; then
    in_agent_sessions=1
    agent_sessions_key_idx=$i
    continue
  fi

  if (( in_agent_sessions )); then
    if [[ "${line}" =~ ^[[:space:]]*-[[:space:]] ]]; then
      last_entry_idx=$i
      # Extract session_id: strip leading "  - " and surrounding quotes
      entry_raw="${line#*- }"
      entry_raw="${entry_raw#\"}"
      entry_raw="${entry_raw%\"}"
      existing_sid="${entry_raw%%|*}"
      if [[ "${existing_sid}" == "${session_id}" ]]; then
        exit 0  # Idempotent no-op: this session already recorded
      fi
    elif [[ -n "${line}" && ! "${line}" =~ ^[[:space:]] ]]; then
      in_agent_sessions=0
    fi
  fi
done

# ---------------------------------------------------------------------------
# Build new encoded-string entry: "<session_id>|working|<created_at>"
# ---------------------------------------------------------------------------

created_at="$(_cs_now_iso)"
new_entry="${session_id}|working|${created_at}"
new_line="  - \"${new_entry}\""

# ---------------------------------------------------------------------------
# Build modified file content — append-only, peer lines untouched
# ---------------------------------------------------------------------------

new_lines=()

if (( agent_sessions_key_idx >= 0 )); then
  # Key exists: insert after the last list entry, or right after the key if no entries yet
  insert_after=$(( last_entry_idx >= 0 ? last_entry_idx : agent_sessions_key_idx ))
  for (( i=0; i<total_lines; i++ )); do
    new_lines+=("${lines[$i]}")
    if (( i == insert_after )); then
      new_lines+=("${new_line}")
    fi
  done
else
  # Key absent: insert agent_sessions: block immediately before the closing ---
  for (( i=0; i<total_lines; i++ )); do
    if (( i == close_idx )); then
      new_lines+=("agent_sessions:")
      new_lines+=("${new_line}")
    fi
    new_lines+=("${lines[$i]}")
  done
fi

# ---------------------------------------------------------------------------
# Atomic write: mktemp adjacent to target + mv
# X's at the END, no suffix after X's (BSD/macOS does NOT randomize a
# trailing suffix — predictable names → collisions). Mirrors session.sh:161.
# ---------------------------------------------------------------------------

tmp_file="$(mktemp "${plan_file}.XXXXXX")"
trap 'rm -f "${tmp_file}" 2>/dev/null || true; rmdir "${lockdir}" 2>/dev/null || true' EXIT

printf '%s\n' "${new_lines[@]}" > "${tmp_file}"
mv "${tmp_file}" "${plan_file}"

exit 0
}

# ---------------------------------------------------------------------------
# Build plan.append_session params JSON from CLI args.
# Maps positional <plan-path> arg and facade-resolved session_id to op param names
# (plan_path, session_id). status defaults to "working" inside the op; created_at
# is generated by the op when absent. Empty session_id -> null so the op falls back
# to its own CLAUDE_CODE_SESSION_ID env resolution.
# ---------------------------------------------------------------------------
_PLAN_PATH="${1:-}"
if [[ -n "$_PLAN_PATH" && "${_PLAN_PATH}" != /* ]]; then
  _PLAN_PATH="$(pwd)/${_PLAN_PATH}"
fi

_SESSION_ID="$(_cs_resolve_session_id 2>/dev/null || true)"

_PARAMS="$(jq -cn \
  --arg plan_path  "$_PLAN_PATH" \
  --arg session_id "$_SESSION_ID" \
  '{
    plan_path:  $plan_path,
    session_id: (if $session_id == "" then null else $session_id end)
  }')"

# ---------------------------------------------------------------------------
# Path-scope gate (native op noun-confinement, DR-216 D2(iv)):
# The plan.append_session op enforces that plan_path must be within docs/plans/
# of the caller's repo (returns no_op: true for out-of-scope paths). Route
# out-of-scope paths directly to legacy so callers on non-plans/ paths (test
# fixtures, ad-hoc invocations) retain the unconstrained legacy behavior.
# In-scope paths (containing /docs/plans/) take the full three-state route.
# ---------------------------------------------------------------------------
if [[ "${_PLAN_PATH}" != */docs/plans/* ]]; then
  legacy_append_plan_session "$@"
else
  # Three-state facade dispatch.
  # strangle_route decides: seam-absent -> legacy_append_plan_session "$@";  # popup-safe-env-suppressed
  #                         seam-present -> coordinator_core.invoke plan.append_session.
  # "$@" forwarded verbatim so legacy_append_plan_session receives original CLI args unchanged.
  strangle_route_mutation "plan.append_session" "legacy_append_plan_session" "$_PARAMS" "$@"
fi
