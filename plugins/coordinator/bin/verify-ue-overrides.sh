#!/bin/bash
# verify-ue-overrides.sh
#
# Purpose: Walks the known UE-context directories and asserts each carries the
# expected UE plugin override in .claude/settings.json. Exits 0 on success,
# 1 with diagnostic output on failure.
#
# Spec backlink: docs/plans/2026-05-20-coordinator-doctor-wiki.md § Chunk 10
# (MISSED-2: hardcoded Striker paths + vacuous-pass on missing dirs)
#
# Wired into /workday-complete Step 1 (validate phase). Run manually at any
# time to surface stale or deleted overrides.
#
# Requirements: bin/machine-local on PATH or resolvable from SCRIPT_DIR;
#   jq OR node on PATH for settings.json parsing.
#
# machine-local keys consumed (must be set in registry.local.toml):
#   repos.claude_unreal_holodeck  — root of the claude-unreal-holodeck repo
#   repos.project_rag             — root of the project-rag repo
#   repos.dronesim                — root of the DroneSim UE project (optional;
#                                   skipped if unset on this machine)
#
# If machine-local is absent or a required key is not set, the script fails
# loud with a remediation hint. This is intentional: a missing registry is a
# configuration gap that needs to be fixed, not silently skipped.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"

# ---------------------------------------------------------------------------
# machine-local resolver
# ---------------------------------------------------------------------------
# Locate the machine-local binary relative to this script so the check works
# even when ~/.claude/bin is not on PATH (e.g. in CI or a fresh install).
ML_BIN=""
if command -v machine-local >/dev/null 2>&1; then
  ML_BIN="machine-local"
elif [[ -x "$HOME/.claude/bin/machine-local" ]]; then
  ML_BIN="$HOME/.claude/bin/machine-local"
elif [[ -x "$SCRIPT_DIR/machine-local" ]]; then
  ML_BIN="$SCRIPT_DIR/machine-local"
fi

# Fail loud if machine-local is unavailable — the registry substrate must exist
# before this verification step can run.
if [[ -z "$ML_BIN" ]]; then
  echo "ERROR: machine-local not found on PATH and not at $SCRIPT_DIR/machine-local" >&2
  echo "Remediation: verify your coordinator install — see" >&2
  echo "  ~/.claude/plugins/coordinator/docs/wiki/machine-local-registry.md § Verifying registry health" >&2
  exit 1
fi

# Resolve a machine-local key; fail loud with remediation if key is not set.
# (Fail-loud variant. The sibling script bin/verify-plan-coverage-sync.sh
#  defines a skip-friendly `resolve_key_or_empty` for optional consumers;
#  here we want hard-fail because UE-context dirs are load-bearing.)
resolve_key() {
  local key="$1"
  local val
  val="$("$ML_BIN" get "$key" 2>/dev/null)" || {
    echo "ERROR: machine-local key '$key' not set on this machine" >&2
    echo "Remediation: populate the key in ~/.claude/machine-local/registry.local.toml" >&2
    echo "  See ~/.claude/plugins/coordinator/docs/wiki/machine-local-registry.md § Verifying registry health" >&2
    exit 1
  }
  echo "$val"
}

# Resolve a machine-local key; print empty on miss (caller decides skip vs fail).
# Used for optional UE-context dirs like DroneSim that may not be registered on
# every machine.
resolve_key_or_empty() {
  local key="$1"
  [[ -z "$ML_BIN" ]] && return 0
  "$ML_BIN" get "$key" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Resolve UE-context directory roots from the machine-local registry.
# ---------------------------------------------------------------------------
HOLODECK_ROOT="$(resolve_key "repos.claude_unreal_holodeck")"
PROJECT_RAG_ROOT="$(resolve_key "repos.project_rag")"

# DroneSim is an optional UE-context dir; include only if repos.dronesim is set
# on this machine. (Previously hardcoded as /x/DroneSim, then skipped pending
# baseline registry key; key now exists and resolves when present.)
NAMED_DIRS=(
  "$HOLODECK_ROOT"
  "$PROJECT_RAG_ROOT"
  "$HOME/.claude"
)
_DRONESIM_ROOT="$(resolve_key_or_empty "repos.dronesim")"
if [[ -n "$_DRONESIM_ROOT" ]]; then
  NAMED_DIRS+=("$_DRONESIM_ROOT")
fi

# ---------------------------------------------------------------------------
# settings.json reader (jq or node fallback)
# ---------------------------------------------------------------------------
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

# Plugins required to be enabled in each UE-context settings.json.
EXPECTED_KEYS=(
  "holodeck-control@claude-unreal-holodeck"
  "holodeck@claude-unreal-holodeck"
)

# Either-vendor sets: at least one entry from each set must be enabled. Avoids
# the dual-vendor conflict where two plugins claim the same agent surface (e.g.
# game-dev is vendored by both coordinator-claude and claude-unreal-holodeck;
# the holodeck-vendored variant is preferred when present, but only one should
# be active per machine to keep agent routing unambiguous).
EITHER_VENDOR_GAME_DEV=(
  "game-dev@claude-unreal-holodeck"
  "game-dev@coordinator-claude"
)
FAIL=0

for dir in "${NAMED_DIRS[@]}"; do
  # Fail loud on missing directories — a resolved registry path that doesn't
  # exist on disk is a configuration gap, not an acceptable skip condition.
  # The old silent-continue shape masked stale or wrong registry values.
  if [[ ! -d "$dir" ]]; then
    echo "ERROR: resolved directory '$dir' does not exist on this machine" >&2
    echo "  Check the machine-local registry value that resolved to this path." >&2
    echo "  Remediation: ~/.claude/plugins/coordinator/docs/wiki/machine-local-registry.md § Verifying registry health" >&2
    FAIL=1
    continue
  fi

  # $HOME/.claude has no .claude sub-dir; its settings.json is at $dir/settings.json directly.
  # All other named dirs are UE-context project roots with a .claude/settings.json sub-path.
  if [[ "$dir" == "$HOME/.claude" ]]; then
    SETTINGS="$dir/settings.json"
  else
    SETTINGS="$dir/.claude/settings.json"
  fi
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

  # Either-vendor check: at least one game-dev vendor must be enabled.
  game_dev_ok=0
  for key in "${EITHER_VENDOR_GAME_DEV[@]}"; do
    val=$(read_key "$SETTINGS" "$key")
    [[ "$val" == "true" ]] && game_dev_ok=1
  done
  if [[ "$game_dev_ok" -eq 0 ]]; then
    echo "WRONG: $SETTINGS — no game-dev vendor enabled (expected at least one of: ${EITHER_VENDOR_GAME_DEV[*]})" >&2
    FAIL=1
  fi
done

[[ $FAIL -eq 0 ]] && echo "all known UE-context dirs carry the expected override"
exit $FAIL
