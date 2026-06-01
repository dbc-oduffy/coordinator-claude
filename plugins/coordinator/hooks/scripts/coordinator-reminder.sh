#!/bin/bash
# Context-aware coordinator reminder
# Emits light-touch reminder + capability catalog for all project repos.
# Spec backlink: docs/plans/2026-05-08-coordinator-setup-onboarding-friction-fixes.md § Chunk 6

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Find repo root (works regardless of CWD)
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

# project_type is a single string; project_subtypes is a YAML list.
PROJECT_TYPE=""
PROJECT_SUBTYPES=""

if [ -n "$REPO_ROOT" ]; then
  LOCAL_MD="$REPO_ROOT/coordinator.local.md"
  if [ -f "$LOCAL_MD" ]; then
    IN_FRONTMATTER=false
    IN_SUBTYPES=false
    while IFS= read -r line; do
      if [ "$line" = "---" ]; then
        if $IN_FRONTMATTER; then break; else IN_FRONTMATTER=true; continue; fi
      fi
      $IN_FRONTMATTER || continue
      # project_type: <single string>
      if echo "$line" | grep -qE '^project_type:[[:space:]]+[^[:space:]]'; then
        PROJECT_TYPE=$(echo "$line" | sed 's/^project_type:[[:space:]]*//')
        IN_SUBTYPES=false
        continue
      fi
      # project_subtypes: (list header)
      if echo "$line" | grep -qE '^project_subtypes:[[:space:]]*$'; then
        IN_SUBTYPES=true
        continue
      fi
      # project_subtypes list items:   - foo
      if $IN_SUBTYPES; then
        if echo "$line" | grep -qE '^[[:space:]]+-[[:space:]]'; then
          val=$(echo "$line" | sed 's/^[[:space:]]*-[[:space:]]*//')
          PROJECT_SUBTYPES="${PROJECT_SUBTYPES:+$PROJECT_SUBTYPES }$val"
        else
          IN_SUBTYPES=false
        fi
      fi
    done < "$LOCAL_MD"
  fi
fi

# Light-touch reminder + capability catalog for all project repos
cat <<'EOF'
## Quick Orient (always, before first tool call)
Before responding to the user's opening message, silently read `tasks/orientation_cache.md` if it exists and isn't already in context. Don't announce it. Do NOT read `tasks/lessons.md` at boot — it's a capture queue processed by `/learn-lessons`, not a must-see memo (load-bearing lessons live in `docs/wiki/` and are surfaced on demand by the prior-art-checker). If the user's message is vague/strategic/implies continuation, invoke `/workstream-start` for the full ceremony (which deliberately surveys lessons — PM-invoked, not EM-judged). If it's a specific actionable request, quick orient and go.

## Coordinator Infrastructure
Available for complex work:
- /review (plan artifacts) or /review-code (code artifacts) — route artifacts to domain + architecture reviewers
- /enrich-and-review — enrich specs with codebase research
- For executor dispatch, follow docs/wiki/delegate-execution.md
Use these when they add value. For direct requests, just do the work.
EOF

# Capability catalog (all projects)
CATALOG="$PLUGIN_ROOT/capability-catalog.md"
if [ -f "$CATALOG" ]; then
  # Strip HTML comments, emit everything else
  grep -v '^<!--' "$CATALOG"
fi
