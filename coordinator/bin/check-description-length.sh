#!/bin/bash
# check-description-length.sh — assert each enabled SKILL.md description fits its budget.
# Three-tier limit:
#   - description-budget: <N> frontmatter field → use N
#   - PM-gated skill (description starts with "PM-GATED" / "**PM-GATED**") → use 175
#   - default → use 150
#
# NOTE: assumes single-line description; double-quoted with escaped \" inside not supported
# (warn-and-skip on multi-line; double-escape edge case is unhandled — flag and acceptable
# for current 12 skills).
set -euo pipefail
PLUGINS_ROOT="$HOME/.claude/plugins"
FAIL=0
DEFAULT_LIMIT=150
PM_GATED_LIMIT=175

while IFS= read -r skill_md; do
  # Extract frontmatter block (between the two `---` lines at top of file)
  frontmatter=$(awk '/^---$/{n++; next} n==1' "$skill_md")
  # grep returning no-match exits 1 — wrap with `|| true` so set -euo pipefail
  # doesn't kill the loop silently for skills lacking the optional field.
  desc=$(printf '%s\n' "$frontmatter" | { grep '^description:' || true; } | sed -E 's/^description:[[:space:]]*"?(.*)"?$/\1/' | sed 's/"$//')
  # If description spans multiple lines (folded YAML), warn and skip — single-line assumed
  desc_lines=$(printf '%s\n' "$frontmatter" | grep -c '^description:' || true)
  if [[ "${desc_lines:-0}" -gt 1 ]]; then
    echo "WARN: $skill_md has multi-line description; skipping (validator assumes single-line)" >&2
    continue
  fi
  # Determine limit
  budget=$(printf '%s\n' "$frontmatter" | { grep '^description-budget:' || true; } | sed -E 's/^description-budget:[[:space:]]*([0-9]+).*$/\1/')
  if [[ -n "$budget" ]]; then
    limit=$budget
  elif [[ "$desc" =~ ^PM-GATED || "$desc" =~ ^\*\*PM-GATED ]]; then
    limit=$PM_GATED_LIMIT
  else
    limit=$DEFAULT_LIMIT
  fi
  # Char count
  count=${#desc}
  if [[ $count -gt $limit ]]; then
    echo -e "$skill_md\t$count\t$limit\tfail" >&2
    FAIL=1
  else
    echo -e "$skill_md\t$count\t$limit\tpass"
  fi
done < <(find "$PLUGINS_ROOT" -name "SKILL.md" -type f -not -path "*/cache/*" -not -path "*/marketplaces/*")

if [[ $FAIL -eq 1 ]]; then
  echo "ERROR: one or more SKILL descriptions exceed their budget" >&2
  exit 1
fi
echo "all SKILL descriptions within budget"
exit 0
