#!/bin/bash
# coordinator-session-loe.sh — Read helper: compute LoE (Level of Effort) metrics
# for a coordinator session and emit a t-shirt size.
#
# Purpose: reads three signals for a given session (total agent dispatches,
# Opus-model dispatches, EM token consumption) and applies the threshold table
# from coordinator/config/loe-thresholds.yaml to produce a t-shirt size.
# Consumed by /session-end, /handoff, and chain-aggregation (Chunk 5).
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
# § Chunk 2 — coordinator-session-loe.sh read helper (plan lines 100–144).
#
# Concurrency posture:  read-only against per-session sentinel files — safe
#   under concurrent reads; single-writer per session_id (the hook that appends
#   dispatched-agents.txt). No locking needed on the read side.
# Idempotency posture:  deterministic given a fixed session_id and fixed
#   dispatched-agents.txt contents; same input -> same output every invocation.
# Resume strategy:      stateless — re-running on the same session yields
#   identical output as long as the sentinel files haven't changed.

set -uo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

FORMAT="json"
INCLUDE_CHILDREN=false
SESSION_ID=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${COORDINATOR_DIR}/config/loe-thresholds.yaml"

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-id)
      SESSION_ID="$2"; shift 2 ;;
    --format)
      FORMAT="$2"; shift 2 ;;
    --include-children)
      INCLUDE_CHILDREN=true; shift ;;
    -h|--help)
      cat <<'EOF'
Usage: coordinator-session-loe.sh [OPTIONS]

Options:
  --session-id <sid>           Session UUID (default: read .current-session-id)
  --format <json|yaml-frontmatter|tsv>
                               Output format (default: json)
  --include-children           Sum descendant sessions (for chain aggregation)
  -h, --help                   Show this help

Output JSON example:
  {"agent_dispatches": 26, "opus_dispatches": 4, "em_tokens": 482000, "tshirt": "L"}

yaml-frontmatter example:
  loe:
    agent_dispatches: 26
    opus_dispatches: 4
    em_tokens: null
    tshirt: "L"
EOF
      exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve git root + sessions base
# ---------------------------------------------------------------------------

GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "Error: not inside a git repo" >&2; exit 1
}
SESSIONS_BASE="${GIT_ROOT}/.git/coordinator-sessions"

# ---------------------------------------------------------------------------
# Resolve session ID
# ---------------------------------------------------------------------------

if [[ -z "$SESSION_ID" ]]; then
  CURRENT_FILE="${SESSIONS_BASE}/.current-session-id"
  if [[ -f "$CURRENT_FILE" ]]; then
    SESSION_ID=$(cat "$CURRENT_FILE" 2>/dev/null || true)
  fi
  if [[ -z "$SESSION_ID" ]]; then
    echo "Error: no --session-id and .current-session-id not found at ${CURRENT_FILE}" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Count agent_dispatches and opus_dispatches for one session dir
# ---------------------------------------------------------------------------

count_session() {
  local sid="$1"
  local session_dir="${SESSIONS_BASE}/${sid}"
  local agents_file="${session_dir}/dispatched-agents.txt"

  local ad=0
  local od=0

  if [[ -f "$agents_file" ]]; then
    # Count total lines (each line = one unique dispatched agent, deduped at write time).
    # Legacy bare-agentId lines count as dispatches with unknown model (Sonnet default).
    ad=$(wc -l < "$agents_file" 2>/dev/null || echo 0)
    # Strip whitespace from wc output
    ad="${ad//[[:space:]]/}"
    [[ -z "$ad" ]] && ad=0

    # Count Opus dispatches: column 2 (model field) matching ^opus.
    # Legacy 1-column records have no tab -> cut -f2 returns the full line (no tab = field 1
    # and field 2 are the same), which won't match ^opus, so legacy rows count 0 Opus. Correct.
    od=$(cut -f2 "$agents_file" 2>/dev/null | grep -c '^opus' 2>/dev/null || echo 0)
    od="${od//[[:space:]]/}"
    [[ -z "$od" ]] && od=0
  fi

  echo "$ad $od"
}

# ---------------------------------------------------------------------------
# Main session counts
# ---------------------------------------------------------------------------

read -r AGENT_DISPATCHES OPUS_DISPATCHES <<< "$(count_session "$SESSION_ID")"

# ---------------------------------------------------------------------------
# --include-children: find descendant sessions and sum
# ---------------------------------------------------------------------------

if [[ "$INCLUDE_CHILDREN" == true ]]; then
  # Children are sessions where .agents/<agentId>/em-session-id.txt points to
  # a session, and that child session itself dispatched further agents.
  # For chain-aggregation: enumerate all session dirs, check if their
  # dispatched-agents.txt exists, and sum. This is intentionally broad —
  # Chunk 5 (chain-aggregation) will apply a tighter ancestor-walk filter.
  # Here we sum all sessions whose meta.json has a 'parent_session' field
  # matching SESSION_ID, falling back to scanning the .agents/ backpointer map.
  AGENTS_DIR="${SESSIONS_BASE}/.agents"
  if [[ -d "$AGENTS_DIR" ]]; then
    while IFS= read -r -d '' bp_file; do
      child_em_sid=$(cat "$bp_file" 2>/dev/null || true)
      [[ -z "$child_em_sid" ]] && continue
      [[ "$child_em_sid" == "$SESSION_ID" ]] && continue  # skip self
      child_dir="${SESSIONS_BASE}/${child_em_sid}"
      [[ ! -d "$child_dir" ]] && continue
      # Only count if this child dispatched agents itself (is an EM session)
      [[ ! -f "${child_dir}/dispatched-agents.txt" ]] && continue
      read -r c_ad c_od <<< "$(count_session "$child_em_sid")"
      AGENT_DISPATCHES=$(( AGENT_DISPATCHES + c_ad ))
      OPUS_DISPATCHES=$(( OPUS_DISPATCHES + c_od ))
    done < <(find "$AGENTS_DIR" -name "em-session-id.txt" -print0 2>/dev/null)
  fi
fi

# ---------------------------------------------------------------------------
# EM token probe — speculative; degrade gracefully if env vars absent.
# CLAUDE_SESSION_INPUT_TOKENS and CLAUDE_SESSION_OUTPUT_TOKENS are not
# documented env vars in Claude Code as of 2026-05 — they may not exist.
# The plan acknowledges this (F6) and instructs graceful-degrade to null.
# ---------------------------------------------------------------------------

EM_TOKENS_RAW=""
if [[ -n "${CLAUDE_SESSION_INPUT_TOKENS:-}" && -n "${CLAUDE_SESSION_OUTPUT_TOKENS:-}" ]]; then
  EM_TOKENS_RAW=$(( CLAUDE_SESSION_INPUT_TOKENS + CLAUDE_SESSION_OUTPUT_TOKENS ))
fi
# Validate it's a non-negative integer
if [[ -n "$EM_TOKENS_RAW" ]] && [[ ! "$EM_TOKENS_RAW" =~ ^[0-9]+$ ]]; then
  EM_TOKENS_RAW=""
fi

# ---------------------------------------------------------------------------
# T-shirt computation from loe-thresholds.yaml
# ---------------------------------------------------------------------------
# Thresholds (parsed inline — avoids a yq/python dependency).
# Table is hard-coded here to match config/loe-thresholds.yaml exactly.
# If the config file is edited, this inline table must be updated to match.
# The config file is the canonical reference; this inline copy is a fallback
# for portability (avoids requiring a YAML parser at runtime).
#
# Format: "tier ad_threshold od_threshold token_threshold"
# Ordered from HIGHEST to LOWEST so we return on first match.
TSHIRT_TABLE=(
  "XL 50 6 1000000"
  "L  30 3 600000"
  "M  15 2 300000"
  "S   5 1 150000"
  "XS  0 0 50000"
)
# Dogfood-fix 2026-05-19: S.od was 0, making XS structurally unreachable
# under any-criterion semantics (every session has opus_dispatches >= 0).
# Tightened S.od=1, M.od=2 to preserve the escalation curve.

# T-shirt = highest tier T where for at least one criterion C, session[C] >= threshold[T][C].
# We iterate from highest to lowest and return the first tier the session qualifies for.
TSHIRT="XS"  # floor — every session with any dispatches qualifies for at least XS
for entry in "${TSHIRT_TABLE[@]}"; do
  read -r tier ad_thresh od_thresh tok_thresh <<< "$entry"
  tier="${tier//[[:space:]]/}"

  qualifies=false

  # agent_dispatches criterion
  if (( AGENT_DISPATCHES >= ad_thresh )); then
    qualifies=true
  fi

  # opus_dispatches criterion
  if (( OPUS_DISPATCHES >= od_thresh )); then
    qualifies=true
  fi

  # em_tokens criterion (only when tokens are available)
  if [[ -n "$EM_TOKENS_RAW" ]] && (( EM_TOKENS_RAW >= tok_thresh )); then
    qualifies=true
  fi

  if [[ "$qualifies" == true ]]; then
    TSHIRT="$tier"
    break
  fi
done

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

# JSON representation of em_tokens (null when absent, integer when present)
if [[ -n "$EM_TOKENS_RAW" ]]; then
  EM_TOKENS_JSON="$EM_TOKENS_RAW"
  EM_TOKENS_YAML="$EM_TOKENS_RAW"
else
  EM_TOKENS_JSON="null"
  EM_TOKENS_YAML="null"
fi

case "$FORMAT" in
  json)
    printf '{"agent_dispatches": %d, "opus_dispatches": %d, "em_tokens": %s, "tshirt": "%s"}\n' \
      "$AGENT_DISPATCHES" "$OPUS_DISPATCHES" "$EM_TOKENS_JSON" "$TSHIRT"
    ;;

  yaml-frontmatter)
    # Paste-ready into a completion entry's loe: block.
    cat <<EOF
loe:
  agent_dispatches: ${AGENT_DISPATCHES}
  opus_dispatches: ${OPUS_DISPATCHES}
  em_tokens: ${EM_TOKENS_YAML}
  tshirt: "${TSHIRT}"
EOF
    ;;

  tsv)
    # Tab-separated: session_id  agent_dispatches  opus_dispatches  em_tokens  tshirt
    printf '%s\t%d\t%d\t%s\t%s\n' \
      "$SESSION_ID" "$AGENT_DISPATCHES" "$OPUS_DISPATCHES" "$EM_TOKENS_JSON" "$TSHIRT"
    ;;

  *)
    echo "Error: unknown format '${FORMAT}'. Use: json | yaml-frontmatter | tsv" >&2
    exit 1
    ;;
esac
