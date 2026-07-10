#!/usr/bin/env bash
# bin/classify-dispatch-shape.sh — Post-hoc dispatch-shape observer (Flag 9)
#
# Purpose: Given a plan slug, read the plan's ## Dispatch Ledger to identify
# gate-groups where parallel execution was permitted, then count distinct
# EXECUTOR-CLASS agentIds in the EM session's dispatched-agents.txt. If
# N > 1 parallel-permitted chunks were declared but only 1 distinct executor
# was observed, emit a question-framed offer (never a verdict).
#
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md § C3
#
# BINDING CONSTRAINTS (from the Staff Engineer re-review — APPROVED_WITH_NOTES):
# - F1: Exclude `inline (EM)` ledger rows from the denominator. Count only
#        `runs: parallel` rows.
# - F2: Offer text MUST be question-framed (ask, never accuse). Acknowledge
#        pilot-then-expand as a valid shape that also presents as 1 agent.
# - F3: Filter agentId count to EXECUTOR-CLASS subagent_type only (exclude
#        reviewers, scouts, personas). Executor-class: `general-purpose`,
#        `coordinator:executor`, `feature-dev:*`. Non-executor: any
#        `coordinator:*` except executor, any `data-science:*` staff/reviewer,
#        `coordinator:staff-eng`, `coordinator:review-integrator`, persona names.
# - F4: Use a BOUNDED per-gate-group window derived from the gate-group's
#        record span as best the records allow (em_sid session dir). Whole-session
#        is the bound — finer granularity is not available without chunk-ids in
#        the records (which are FORBIDDEN per the anti-scope above).
#
# FORBIDDEN MECHANISMS:
# - No temporal-overlap computation (dispatched-at is Agent RETURN-time, not
#   dispatch-time; foreground dispatches are always recorded strictly serial).
# - No chunk-id-substring correlation (no chunk-id field exists in the records).
#
# FIDELITY LIMIT (stated in offer text):
# The records do not carry a plan slug. Attribution is scoped to the em_sid
# session directory. A multi-plan session will mix agents from other plans —
# this is stated in the offer text so the EM can evaluate accordingly.
# The classifier detects the gross serial-grind antipattern; fine-grained
# interleaving within a session is not distinguishable from the records.
#
# OFFER SHAPE: exit 0 always. Finding to stderr only. Silent on pass.
#
# Usage:
#   classify-dispatch-shape.sh <plan-slug>
#   classify-dispatch-shape.sh --plan-file <path/to/plan.md>
#
# Examples:
#   classify-dispatch-shape.sh 2026-06-22-invariant-verification-observers
#   classify-dispatch-shape.sh --plan-file docs/plans/2026-06-22-foo.md

# --- bash >= 4 guard (must be reachable on 3.2 — no bash-4 syntax before this) ---
# Review: code-reviewer — offer-shape constraint: exit 0 always, even on bash version mismatch
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  echo "classify-dispatch-shape.sh: requires bash >= 4 (found ${BASH_VERSION})." >&2
  echo "  brew install bash  # macOS" >&2
  exit 0
fi

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
PLAN_FILE=""
PLAN_SLUG=""

if [[ $# -eq 0 ]]; then
  echo "Usage: classify-dispatch-shape.sh <plan-slug>" >&2
  echo "       classify-dispatch-shape.sh --plan-file <path>" >&2
  exit 0
fi

if [[ "$1" == "--plan-file" ]]; then
  if [[ $# -lt 2 ]]; then
    echo "classify-dispatch-shape.sh: --plan-file requires a path argument" >&2
    exit 0
  fi
  PLAN_FILE="$2"
else
  PLAN_SLUG="$1"
  # Resolve plan file from slug: look under docs/plans/ relative to repo root
  # or relative to cwd
  for search_dir in "$(pwd)/docs/plans" "${REPO_ROOT}/../../docs/plans" "${REPO_ROOT}/../docs/plans"; do
    if [[ -d "$search_dir" ]]; then
      candidate="${search_dir}/${PLAN_SLUG}.md"
      if [[ -f "$candidate" ]]; then
        PLAN_FILE="$candidate"
        break
      fi
      # Try prefix-match when slug has no date
      found="$(find "$search_dir" -maxdepth 1 -name "*${PLAN_SLUG}*.md" 2>/dev/null | head -1)"
      if [[ -n "$found" ]]; then
        PLAN_FILE="$found"
        break
      fi
    fi
  done
fi

if [[ -z "$PLAN_FILE" ]] || [[ ! -f "$PLAN_FILE" ]]; then
  # Soft failure — observer must not block the workstream
  echo "classify-dispatch-shape.sh: plan file not found for '${PLAN_SLUG:-$PLAN_FILE}' — skipping check" >&2
  exit 0
fi

# ---------------------------------------------------------------------------
# Parse the Dispatch Ledger for parallel-permitted gate-groups (F1)
# ---------------------------------------------------------------------------
# We scan the ## Dispatch Ledger table rows that match:
#   runs: parallel   (column 7 in the table — "inline (EM) / parallel / after #N")
#   gate-kind: none | output-consumption-content | contract-change
#   (exclude file-write-overlap and output-consumption-runtime which ARE serial gates)
#
# Table header shape (from execute-plan SKILL.md Phase 1.6):
#   | dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |
# Column indices (1-based after splitting on |):
#   2=dispatch#  3=chunk-id  4=brief  5=write-files  6=gate-kind  7=runs  8=est-min  9=status
#
# We use awk to parse. grep -A to scope to the ledger section first.

in_ledger=0
parallel_chunk_count=0
declare -A gate_groups  # gate_group_key -> parallel_chunk_count

# Read the plan and extract rows from ## Dispatch Ledger
while IFS= read -r line; do
  # Detect section start
  if echo "$line" | grep -qF '## Dispatch Ledger'; then
    in_ledger=1
    continue
  fi
  # Detect section end (another ## heading)
  if [[ $in_ledger -eq 1 ]] && echo "$line" | grep -qE '^## '; then
    in_ledger=0
    continue
  fi
  # Skip if not in ledger
  [[ $in_ledger -eq 0 ]] && continue
  # Skip non-table rows (header, separator, empty)
  echo "$line" | grep -qE '^\|' || continue
  # Review: code-reviewer — tightened separator regex to GFM shape (requires at least two
  # pipe-delimited cells of dashes/colons/spaces) to avoid false-positive matches on data rows.
  echo "$line" | grep -qE '^\|[ :-]+(\|[ :-]+)+\|?$' && continue   # GFM separator line
  echo "$line" | grep -qi 'dispatch #\|chunk-id\|gate-kind' && continue  # header

  # Extract gate-kind (col 6) and runs (col 7) from pipe-delimited row
  # Using awk for portability (BSD awk + GNU awk compatible)
  gate_kind="$(echo "$line" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $6); print $6}')"
  runs_val="$(echo "$line" | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $7); print $7}')"

  # F1: Count only `runs: parallel` rows; skip `inline (EM)` and `after #N`
  if [[ "$runs_val" != "parallel" ]]; then
    continue
  fi

  # Parallel-permitted gate-kinds: none, output-consumption-content, contract-change
  # Serial gate-kinds (NOT parallel-permitted): file-write-overlap, output-consumption-runtime
  case "$gate_kind" in
    none|output-consumption-content|contract-change)
      parallel_chunk_count=$((parallel_chunk_count + 1))
      ;;
    *)
      # file-write-overlap, output-consumption-runtime, or unknown — not parallel-permitted
      ;;
  esac
done < "$PLAN_FILE"

# If no parallel-permitted chunks were found, nothing to observe
if [[ $parallel_chunk_count -le 1 ]]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Locate em_sid session directory (F4: bounded window)
# ---------------------------------------------------------------------------
# dispatched-agents.txt lives at .git/coordinator-sessions/<em_sid>/dispatched-agents.txt
# We use CLAUDE_CODE_SESSION_ID if available, else scan all session dirs
# Scoped to a single em_sid dir (the bounded window) to avoid cross-session mixing.

GIT_DIR="$(git -C "$(dirname "$PLAN_FILE")" rev-parse --git-dir 2>/dev/null || git rev-parse --git-dir 2>/dev/null || true)"
SESSIONS_DIR="${GIT_DIR}/coordinator-sessions"

AGENTS_FILE=""
if [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]] && [[ -d "${SESSIONS_DIR}/${CLAUDE_CODE_SESSION_ID}" ]]; then
  AGENTS_FILE="${SESSIONS_DIR}/${CLAUDE_CODE_SESSION_ID}/dispatched-agents.txt"
elif [[ -n "${em_sid:-}" ]] && [[ -d "${SESSIONS_DIR}/${em_sid}" ]]; then
  AGENTS_FILE="${SESSIONS_DIR}/${em_sid}/dispatched-agents.txt"
else
  # Fall back: use the most-recently-modified session dir
  # Review: code-reviewer — removed dead latest_mtime/mtime vars and incoherent two-pass
  # selection; find|xargs ls -t|head -1 is the only selection needed.
  if [[ -d "$SESSIONS_DIR" ]]; then
    newest="$(find "$SESSIONS_DIR" -maxdepth 2 -name "dispatched-agents.txt" -print0 2>/dev/null \
      | xargs -0 -r ls -t 2>/dev/null | head -1)"
    [[ -n "$newest" ]] && AGENTS_FILE="$newest"
  fi
fi

if [[ -z "$AGENTS_FILE" ]] || [[ ! -f "$AGENTS_FILE" ]]; then
  # No dispatched-agents.txt found — cannot observe; exit silently
  exit 0
fi

# ---------------------------------------------------------------------------
# Resolve em_sid for offer text
# ---------------------------------------------------------------------------
em_sid_display=""
if [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
  em_sid_display="${CLAUDE_CODE_SESSION_ID}"
elif [[ -n "${em_sid:-}" ]]; then
  em_sid_display="${em_sid}"
else
  # Derive from path: .git/coordinator-sessions/<em_sid>/dispatched-agents.txt
  em_sid_display="$(basename "$(dirname "$AGENTS_FILE")")"
fi

# ---------------------------------------------------------------------------
# Count distinct EXECUTOR-CLASS agentIds (F3)
# ---------------------------------------------------------------------------
# dispatched-agents.txt columns (tab-separated): agentId | model | subagent_type | dispatched-at
#
# EXECUTOR-CLASS subagent_type values (implementation patterns observed in real records):
#   general-purpose, coordinator:executor, feature-dev:*
# NON-EXECUTOR (excluded):
#   coordinator:staff-eng, coordinator:review-integrator
#   coordinator:staff-data-sci, coordinator:*-reviewer, persona names (the Staff Engineer, the Game Dev Reviewer, etc.)
#
# The classification rule: a subagent_type is executor-class iff it matches
#   general-purpose  OR  coordinator:executor  OR  feature-dev:*
# All others are non-executor (reviewer, scout, persona, or specialty worker).

distinct_executor_count=0
declare -A seen_agents

while IFS=$'\t' read -r agent_id model subagent_type dispatched_at; do
  # Skip blank/comment lines
  [[ -z "$agent_id" ]] && continue
  [[ "$agent_id" == \#* ]] && continue

  # F3: executor-class filter
  is_executor=0
  case "$subagent_type" in
    general-purpose|"coordinator:executor"|feature-dev:*)
      is_executor=1
      ;;
    *)
      is_executor=0
      ;;
  esac

  [[ $is_executor -eq 0 ]] && continue

  # Count distinct agentIds (dedup)
  if [[ -z "${seen_agents[$agent_id]+_}" ]]; then
    seen_agents[$agent_id]=1
    distinct_executor_count=$((distinct_executor_count + 1))
  fi
done < "$AGENTS_FILE"

# ---------------------------------------------------------------------------
# Evaluate signal: N parallel-permitted chunks but only 1 executor agent
# ---------------------------------------------------------------------------
# Signal fires ONLY when:
#   parallel_chunk_count > 1  (multiple parallel-permitted chunks declared)
#   distinct_executor_count == 1  (only 1 executor agent observed in session)
#
# F2: Offer must be question-framed and acknowledge pilot-then-expand.

if [[ $parallel_chunk_count -gt 1 ]] && [[ $distinct_executor_count -eq 1 ]]; then
  cat >&2 <<EOF
[classify-dispatch-shape] DISPATCH SHAPE QUESTION

The plan's Dispatch Ledger declares ${parallel_chunk_count} parallel-permitted chunks
(gate-kind: none / output-consumption-content / contract-change; runs: parallel),
but only 1 distinct executor agent is attributable to session ${em_sid_display}.

Was this a serial grind (one agent handling chunks sequentially), or an intentional
pilot-then-expand shape, or did the EM author some chunks inline?

If serial grind: consider re-dispatching with true fan-out parallelism — e.g.
  bash ~/.claude/plugins/coordinator/bin/fan-out-dispatch.sh <tsv>

If intentional (pilot-then-expand / inline EM / other valid shape): no action needed.

Fidelity note: records are scoped to session ${em_sid_display} from
  ${AGENTS_FILE}
Multi-plan sessions may include agents from other plans. This classifier detects
the gross serial-grind antipattern; fine-grained interleaving within a session is
not distinguishable from the available records.

EOF
fi

# Offer-shaped: always exit 0, regardless of finding
exit 0
