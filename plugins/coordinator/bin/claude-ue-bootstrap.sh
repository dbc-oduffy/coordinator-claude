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

# to_native: translate MSYS-style paths (/x/foo) to native Windows form (X:\foo)
# for tools (node, jq) that don't understand the MSYS prefix. No-op on non-MSYS.
to_native() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    echo "$1"
  fi
}

# Fast path: no existing settings.json — write via here-doc, no jq needed
if [[ ! -f "$SETTINGS" ]]; then
  TMP="$SETTINGS.tmp.$$"
  cat > "$TMP" <<'ENDJSON'
{
  "enabledPlugins": {
    "holodeck-control@claude-unreal-holodeck": true,
    "holodeck-docs@claude-unreal-holodeck": true,
    "holodeck@claude-unreal-holodeck": true,
    "game-dev@claude-unreal-holodeck": true,
    "game-dev@coordinator-claude": true
  }
}
ENDJSON
  mv -f "$TMP" "$SETTINGS"
  echo "wrote UE override to $SETTINGS (no jq needed)"
  exit 0
fi

# Merge path: existing settings.json present — prefer jq, fall back to node.
EXPECTED_KEYS=(
  "holodeck-control@claude-unreal-holodeck"
  "holodeck-docs@claude-unreal-holodeck"
  "holodeck@claude-unreal-holodeck"
  "game-dev@claude-unreal-holodeck"
  "game-dev@coordinator-claude"
)
SETTINGS_NATIVE="$(to_native "$SETTINGS")"

if command -v jq >/dev/null 2>&1; then
  OVERRIDE='{
    "enabledPlugins": {
      "holodeck-control@claude-unreal-holodeck": true,
      "holodeck-docs@claude-unreal-holodeck": true,
      "holodeck@claude-unreal-holodeck": true,
      "game-dev@claude-unreal-holodeck": true,
      "game-dev@coordinator-claude": true
    }
  }'
  if jq -e '
    .enabledPlugins["holodeck-control@claude-unreal-holodeck"] == true
    and .enabledPlugins["holodeck-docs@claude-unreal-holodeck"] == true
    and .enabledPlugins["holodeck@claude-unreal-holodeck"] == true
    and .enabledPlugins["game-dev@claude-unreal-holodeck"] == true
    and .enabledPlugins["game-dev@coordinator-claude"] == true
  ' "$SETTINGS" >/dev/null 2>&1; then
    echo "$SETTINGS already carries UE override — no change"
    exit 0
  fi
  TMP="$SETTINGS.tmp.$$"
  jq --argjson new "$OVERRIDE" '. * $new' "$SETTINGS" > "$TMP"
  mv -f "$TMP" "$SETTINGS"
  echo "merged UE override into $SETTINGS (via jq)"
  exit 0
fi

if command -v node >/dev/null 2>&1; then
  KEYS_JOINED="$(IFS=,; echo "${EXPECTED_KEYS[*]}")"
  node -e '
    const fs = require("fs");
    const path = process.argv[1];
    const keys = process.argv[2].split(",");
    const j = JSON.parse(fs.readFileSync(path, "utf8"));
    j.enabledPlugins = j.enabledPlugins || {};
    let changed = false;
    for (const k of keys) {
      if (j.enabledPlugins[k] !== true) { j.enabledPlugins[k] = true; changed = true; }
    }
    if (!changed) { console.log("already carries UE override — no change"); process.exit(0); }
    fs.writeFileSync(path, JSON.stringify(j, null, 2) + "\n", "utf8");
    console.log("merged UE override (via node)");
  ' "$SETTINGS_NATIVE" "$KEYS_JOINED"
  exit 0
fi

echo "ERROR: neither jq nor node on PATH — cannot merge with existing $SETTINGS" >&2
echo "Install jq (choco install jq / scoop install jq / apt-get install jq) or node." >&2
exit 1
