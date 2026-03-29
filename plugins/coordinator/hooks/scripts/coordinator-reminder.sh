#!/bin/bash
# Context-aware coordinator reminder
# Full EM model for project_type: meta (~/.claude repo)
# Light-touch reminder for all other projects

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- EM session marker ---
# Read hook input to get session_id, then write marker file.
# Used by nudge-em-delegation.sh to distinguish EM from subagents.
# SessionStart only fires for the top-level session, not subagents.
if command -v timeout &>/dev/null; then
  _HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  _HOOK_INPUT=$(cat)
fi
if command -v jq &>/dev/null; then
  _SID=$(echo "$_HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  if [[ -n "$_SID" ]]; then
    touch "/tmp/em-session-${_SID}"
  fi
fi

# Find repo root (works regardless of CWD)
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

# Default: no coordinator.local.md found
PROJECT_TYPE=""

if [ -n "$REPO_ROOT" ]; then
  LOCAL_MD="$REPO_ROOT/.claude/coordinator.local.md"
  if [ -f "$LOCAL_MD" ]; then
    # Extract project_type from YAML frontmatter
    PROJECT_TYPE=$(sed -n '/^---$/,/^---$/{ /^project_type:/{ s/^project_type:[[:space:]]*//; p; } }' "$LOCAL_MD")
  fi
fi

if [ "$PROJECT_TYPE" = "meta" ]; then
  # Full EM operating model for the orchestration infrastructure repo
  cat <<'EOF'
# Coordinator — Meta Project Mode
You are the EM operating on your own orchestration infrastructure.
- Flight recorder (TaskCreate): create IMMEDIATELY when a goal is set
- Research 2+ queries → delegate to Explore/Enricher agents
- Code implementation → delegate to Executor agents
- Reviews → /review-dispatch (Patrik + Zolí apply to infrastructure code too)
- 2+ independent tasks → parallel dispatch
- Write-ahead status: update Status fields BEFORE starting work, not after
- Agent outputs → write to disk immediately, verify before proceeding
- Skills/templates are tested infrastructure — follow them, don't improvise
- Review findings: accept the judgment of reviewers with domain expertise. Implement ALL items — P0s, P2s, nitpicks, everything. Every finding is an opportunity to meet or exceed their quality bar. Only escalate to the PM if a finding changes scope, or push back if you believe the reviewer is genuinely wrong (state why).
EOF
else
  # Light-touch reminder + capability catalog for project repos
  cat <<'EOF'
Coordinator infrastructure is available for complex work:
- /review-dispatch — route artifacts to domain + architecture reviewers
- /enrich-and-review — enrich specs with codebase research
- /delegate-execution — dispatch executor agents for implementation
Use these when they add value. For direct requests, just do the work.
EOF

  # --- Capability catalog (all projects except meta) ---
  CATALOG="$PLUGIN_ROOT/capability-catalog.md"
  if [ -f "$CATALOG" ]; then
    # Strip HTML comments, emit everything else
    grep -v '^<!--' "$CATALOG"
  fi
fi
