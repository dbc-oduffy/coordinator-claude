#!/bin/bash
# Context-aware coordinator reminder
# Full EM model for project_type: meta (~/.claude repo)
# Light-touch reminder for all other projects

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Find repo root (works regardless of CWD)
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

# Default: no coordinator.local.md found
PROJECT_TYPES=""

if [ -n "$REPO_ROOT" ]; then
  LOCAL_MD="$REPO_ROOT/coordinator.local.md"
  if [ -f "$LOCAL_MD" ]; then
    # Extract project_type(s) from YAML frontmatter
    # Supports both single value (project_type: meta) and list (project_type:\n  - unreal\n  - data-science)
    IN_FRONTMATTER=false
    IN_PROJECT_TYPE=false
    PROJECT_TYPES=""
    while IFS= read -r line; do
      if [ "$line" = "---" ]; then
        if $IN_FRONTMATTER; then break; else IN_FRONTMATTER=true; continue; fi
      fi
      $IN_FRONTMATTER || continue
      # Single-value: project_type: foo
      if echo "$line" | grep -qE '^project_type:[[:space:]]+[^[:space:]]'; then
        val=$(echo "$line" | sed 's/^project_type:[[:space:]]*//')
        PROJECT_TYPES="$val"
        IN_PROJECT_TYPE=false
        continue
      fi
      # List header: project_type:
      if echo "$line" | grep -qE '^project_type:[[:space:]]*$'; then
        IN_PROJECT_TYPE=true
        continue
      fi
      # List item:   - foo
      if $IN_PROJECT_TYPE; then
        if echo "$line" | grep -qE '^[[:space:]]+-[[:space:]]'; then
          val=$(echo "$line" | sed 's/^[[:space:]]*-[[:space:]]*//')
          PROJECT_TYPES="${PROJECT_TYPES:+$PROJECT_TYPES }$val"
        else
          IN_PROJECT_TYPE=false
        fi
      fi
    done < "$LOCAL_MD"
  fi
fi

# Check if a type is in the list
has_type() { echo " $PROJECT_TYPES " | grep -q " $1 "; }

if has_type "meta"; then
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
