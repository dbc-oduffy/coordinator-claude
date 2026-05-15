#!/bin/bash
# verify-ue-overrides.sh
#
# Walks the known UE-context directories and asserts each carries the expected
# UE plugin override in .claude/settings.json. Exits 0 on success, 1 with
# diagnostic output on failure.
#
# Wired into /workday-complete Step 1 (validate phase). Run manually at any
# time to surface stale or deleted overrides.
#
# Requirements: jq OR node on PATH.
set -e

# to_native: translate MSYS-style paths (/x/foo) to native Windows (X:\foo) so
# node/jq receive a path their stdlib can open. No-op on non-MSYS.
to_native() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    echo "$1"
  fi
}

if command -v jq >/dev/null 2>&1; then
  read_key() { jq -r ".enabledPlugins[\"$2\"] // \"missing\"" "$1"; }
elif command -v node >/dev/null 2>&1; then
  read_key() {
    local p
    p="$(to_native "$1")"
    node -e "const j=JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'));process.stdout.write(String((j.enabledPlugins||{})[process.argv[2]]??'missing'))" "$p" "$2"
  }
else
  echo "ERROR: neither jq nor node on PATH — verify-ue-overrides.sh needs one" >&2
  echo "Install: choco install jq / scoop install jq / apt-get install jq (or install node)" >&2
  exit 1
fi

NAMED_DIRS=("/x/DroneSim" "/x/project-rag" "/x/claude-unreal-holodeck" "$HOME/.claude")
EXPECTED_KEYS=(
  "holodeck-control@claude-unreal-holodeck"
  "holodeck-docs@claude-unreal-holodeck"
  "holodeck@claude-unreal-holodeck"
  "game-dev@claude-unreal-holodeck"
  "game-dev@coordinator-claude"
)
FAIL=0

for dir in "${NAMED_DIRS[@]}"; do
  [[ -d "$dir" ]] || {
    echo "skip: $dir does not exist (acceptable if dir was moved/removed)" >&2
    continue
  }
  SETTINGS="$dir/.claude/settings.json"
  if [[ ! -f "$SETTINGS" ]]; then
    echo "MISSING: $SETTINGS — run ~/.claude/bin/claude-ue-bootstrap.sh $dir" >&2
    FAIL=1
    continue
  fi
  for key in "${EXPECTED_KEYS[@]}"; do
    val=$(read_key "$SETTINGS" "$key")
    if [[ "$val" != "true" ]]; then
      echo "WRONG: $SETTINGS [$key] = $val (expected true)" >&2
      FAIL=1
    fi
  done
done

[[ $FAIL -eq 0 ]] && echo "all known UE-context dirs carry the expected override"
exit $FAIL
