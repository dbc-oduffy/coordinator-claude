#!/usr/bin/env bash
# coordinator-session-loe.sh — Read helper: compute LoE (Level of Effort) metrics
# for a coordinator session and emit a t-shirt size.
#
# Purpose: reads three signals for a given session (total agent dispatches,
# Opus-model dispatches, EM token consumption) and applies the threshold table
# from coordinator/config/loe-thresholds.yaml to produce a t-shirt size.
# Consumed by /workstream-complete, /handoff, and chain-aggregation (Chunk 5).
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
# Library source
# ---------------------------------------------------------------------------

_LOE_LIB="${SCRIPT_DIR}/../lib/coordinator-session.sh"
if [[ ! -f "$_LOE_LIB" ]]; then
  echo "ERROR: coordinator-session.sh not found at ${_LOE_LIB}" >&2
  exit 1
fi
# shellcheck source=../lib/coordinator-session.sh
source "$_LOE_LIB"

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

# Resolution: explicit --session-id flag (set above at parse time) is highest priority.
# If not provided, delegate to cs_resolve_session_id which runs the full ambiguity-aware
# 4-tier chain: $COORDINATOR_SESSION_ID → $CLAUDE_SESSION_ID → $CLAUDE_CODE_SESSION_ID
# → tier-4 sentinel (fail-empty under concurrency, per coordinator-session.sh).
if [[ -z "$SESSION_ID" ]]; then
  SESSION_ID=$(cs_resolve_session_id)
fi
if [[ -z "$SESSION_ID" ]]; then
  echo "Error: no --session-id, CLAUDE_CODE_SESSION_ID unset, and .current-session-id unresolvable (absent or ambiguous under concurrent sessions). Escape hatch: export CLAUDE_SESSION_ID=<harness-id>" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Count agent_dispatches and opus_dispatches for one session dir
# ---------------------------------------------------------------------------

count_session() {
  local sid="$1"
  local session_dir="${SESSIONS_BASE}/${sid}"
  local agents_file="${session_dir}/dispatched-agents.txt"

  local ad=""
  local od=""

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
    # NOTE: grep -c prints its count (incl. "0") AND exits 1 on zero matches.
    # `|| echo 0` would then fire too, concatenating stdout to "00" (octal-parsed,
    # malformed LoE frontmatter). Use `|| true` to swallow the exit without a 2nd write;
    # the `[[ -z "$od" ]] && od=0` guard below covers a genuinely-empty result.
    od=$(cut -f2 "$agents_file" 2>/dev/null | grep -ci opus 2>/dev/null || true)
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
      [[ "$c_ad" =~ ^[0-9]+$ ]] || c_ad=0
      [[ "$c_od" =~ ^[0-9]+$ ]] || c_od=0
      if [[ -n "$AGENT_DISPATCHES" ]]; then
        AGENT_DISPATCHES=$(( AGENT_DISPATCHES + c_ad )) || true
      else
        AGENT_DISPATCHES="$c_ad"
      fi
      if [[ -n "$OPUS_DISPATCHES" ]]; then
        OPUS_DISPATCHES=$(( OPUS_DISPATCHES + c_od )) || true
      else
        OPUS_DISPATCHES="$c_od"
      fi
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
if [[ -n "${CLAUDE_SESSION_INPUT_TOKENS:-}" && -n "${CLAUDE_SESSION_OUTPUT_TOKENS:-}" ]] &&
   [[ "${CLAUDE_SESSION_INPUT_TOKENS}" =~ ^[0-9]+$ ]] &&
   [[ "${CLAUDE_SESSION_OUTPUT_TOKENS}" =~ ^[0-9]+$ ]]; then
  EM_TOKENS_RAW=$(( CLAUDE_SESSION_INPUT_TOKENS + CLAUDE_SESSION_OUTPUT_TOKENS )) || true
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
TSHIRT="null"  # null until a criterion fires; XS is the lowest qualifying tier (null when both ad and od absent)
for entry in "${TSHIRT_TABLE[@]}"; do
  read -r tier ad_thresh od_thresh tok_thresh <<< "$entry"
  tier="${tier//[[:space:]]/}"

  qualifies=false

  # agent_dispatches criterion
  if [[ -n "$AGENT_DISPATCHES" ]] && (( AGENT_DISPATCHES >= ad_thresh )); then
    qualifies=true
  fi

  # opus_dispatches criterion
  if [[ -n "$OPUS_DISPATCHES" ]] && (( OPUS_DISPATCHES >= od_thresh )); then
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

# JSON/YAML representation of agent_dispatches / opus_dispatches
# (null when dispatched-agents.txt absent, integer when present — mirrors EM_TOKENS_RAW pattern)
if [[ -n "$AGENT_DISPATCHES" ]]; then
  AGENT_DISPATCHES_JSON="$AGENT_DISPATCHES"
  AGENT_DISPATCHES_YAML="$AGENT_DISPATCHES"
else
  AGENT_DISPATCHES_JSON="null"
  AGENT_DISPATCHES_YAML="null"
fi

if [[ -n "$OPUS_DISPATCHES" ]]; then
  OPUS_DISPATCHES_JSON="$OPUS_DISPATCHES"
  OPUS_DISPATCHES_YAML="$OPUS_DISPATCHES"
else
  OPUS_DISPATCHES_JSON="null"
  OPUS_DISPATCHES_YAML="null"
fi

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
    printf '{"agent_dispatches": %s, "opus_dispatches": %s, "em_tokens": %s, "tshirt": "%s"}\n' \
      "$AGENT_DISPATCHES_JSON" "$OPUS_DISPATCHES_JSON" "$EM_TOKENS_JSON" "$TSHIRT"
    ;;

  yaml-frontmatter)
    # Paste-ready into a completion entry's loe: block.
    cat <<EOF
loe:
  agent_dispatches: ${AGENT_DISPATCHES_YAML}
  opus_dispatches: ${OPUS_DISPATCHES_YAML}
  em_tokens: ${EM_TOKENS_YAML}
  tshirt: "${TSHIRT}"
EOF
    ;;

  tsv)
    # Tab-separated: session_id  agent_dispatches  opus_dispatches  em_tokens  tshirt
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$SESSION_ID" "$AGENT_DISPATCHES_JSON" "$OPUS_DISPATCHES_JSON" "$EM_TOKENS_JSON" "$TSHIRT"
    ;;

  *)
    echo "Error: unknown format '${FORMAT}'. Use: json | yaml-frontmatter | tsv" >&2
    exit 1
    ;;
esac
