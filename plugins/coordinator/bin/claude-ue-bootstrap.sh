#!/bin/bash
# claude-ue-bootstrap.sh <project-dir>
#
# Drops <project-dir>/.claude/settings.json with the UE plugin enable block.
# Idempotent: skips write if the override is already present; merges with
# existing settings if a non-UE settings.json is already there.
#
# Usage:
#   ~/.claude/bin/claude-ue-bootstrap.sh /x/DroneSim
#   ~/.claude/bin/claude-ue-bootstrap.sh /x/project-rag
#   ~/.claude/bin/claude-ue-bootstrap.sh /x/claude-unreal-holodeck
#   ~/.claude/bin/claude-ue-bootstrap.sh ~/.claude
#
# Merge path requires jq. No-existing-settings fast path is pure shell (no jq needed).
set -e
PROJECT="${1:-$(pwd)}"
SETTINGS="$PROJECT/.claude/settings.json"
mkdir -p "$PROJECT/.claude"

# Fast path: no existing settings.json — write via here-doc, no jq needed
if [[ ! -f "$SETTINGS" ]]; then
  TMP="$SETTINGS.tmp.$$"
  cat > "$TMP" <<'ENDJSON'
{
  "enabledPlugins": {
    "holodeck-control@claude-unreal-holodeck": true,
    "holodeck-docs@claude-unreal-holodeck": true,
    "holodeck@claude-unreal-holodeck": true,
    "game-dev@coordinator-claude": true
  }
}
ENDJSON
  mv -f "$TMP" "$SETTINGS"
  echo "wrote UE override to $SETTINGS (no jq needed)"
  exit 0
fi

# Merge path: existing settings.json present — jq required
command -v jq >/dev/null 2>&1 || {
  echo "WARNING: jq not on PATH — cannot merge with existing $SETTINGS" >&2
  echo "Install jq via: chocolatey (choco install jq), scoop (scoop install jq), or apt (apt-get install jq)" >&2
  exit 0
}

OVERRIDE='{
  "enabledPlugins": {
    "holodeck-control@claude-unreal-holodeck": true,
    "holodeck-docs@claude-unreal-holodeck": true,
    "holodeck@claude-unreal-holodeck": true,
    "game-dev@coordinator-claude": true
  }
}'

if jq -e '.enabledPlugins["holodeck-control@claude-unreal-holodeck"] == true' "$SETTINGS" >/dev/null 2>&1; then
  echo "$SETTINGS already carries UE override — no change"
  exit 0
fi
TMP="$SETTINGS.tmp.$$"
jq --argjson new "$OVERRIDE" '. * $new' "$SETTINGS" > "$TMP"
mv -f "$TMP" "$SETTINGS"
echo "merged UE override into $SETTINGS"
