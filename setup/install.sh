#!/bin/bash
# coordinator-claude installer
#
# Copies plugins to ~/.claude and registers them in Claude Code's JSON config files.
#
# Usage:
#   setup/install.sh [--non-interactive] [--plugins coordinator,web-dev,...]
#
# --non-interactive  Skip prompts; install default-on plugins only
# --plugins LIST     Comma-separated list of plugins to install (coordinator always included)

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"

# Plugin metadata: name|default|version|description
# Note: deep-research is now a standalone plugin at github.com/oduffy-delphi/deep-research-claude
# Install it separately: claude plugin install deep-research from deep-research-claude marketplace
PLUGIN_REGISTRY=(
  "coordinator|on|1.1.0|Core pipeline and workflow skills (always enabled)"
  "web-dev|on|1.0.0|Palí + Fru reviewers"
  "data-science|on|1.0.0|Camelia reviewer"
  "game-dev|off|1.1.0|Sid reviewer (Unreal Engine)"
  "notebooklm|on|1.1.0|Media research via NotebookLM"
  "remember|on|1.0.0|Automatic session memory"
)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

detect_platform() {
  case "$(uname -s)" in
    Linux*)   PLATFORM="linux" ;;
    Darwin*)  PLATFORM="darwin" ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="gitbash" ;;
    *)        PLATFORM="unknown" ;;
  esac

  # Detect WSL under Linux
  if [[ "$PLATFORM" == "linux" ]] && grep -qi microsoft /proc/version 2>/dev/null; then
    PLATFORM="wsl"
  fi
}

# Convert a POSIX path to the native OS path format required by JSON config files.
native_path() {
  local path="$1"
  case "$PLATFORM" in
    gitbash)
      cygpath -w "$path" 2>/dev/null || echo "$path"
      ;;
    wsl)
      # Convert /mnt/c/... -> C:\...
      echo "$path" | sed 's|^/mnt/\([a-z]\)/|\U\1:\\|; s|/|\\|g'
      ;;
    *)
      echo "$path"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

NON_INTERACTIVE=false
PLUGINS_ARG=""

for arg in "$@"; do
  case "$arg" in
    --non-interactive) NON_INTERACTIVE=true ;;
    --plugins=*)       PLUGINS_ARG="${arg#--plugins=}" ;;
    --plugins)         shift; PLUGINS_ARG="$1" ;;
    -h|--help)
      echo "Usage: setup/install.sh [--non-interactive] [--plugins coordinator,web-dev,...]"
      exit 0
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

check_prerequisites() {
  if ! command -v claude &>/dev/null; then
    echo "ERROR: Claude Code CLI not found on PATH."
    echo "Install from: https://docs.anthropic.com/en/docs/claude-code"
    exit 1
  fi

  if command -v python3 &>/dev/null; then
    PYTHON="python3"
  elif command -v python &>/dev/null; then
    PYTHON="python"
  else
    echo "ERROR: python3 (or python) not found on PATH."
    echo "Install Python 3 from: https://python.org"
    exit 1
  fi

  if ! command -v jq &>/dev/null; then
    echo ""
    echo "WARNING: jq not found on PATH."
    echo "Hook scripts degrade gracefully for basic JSON parsing, but the"
    echo "some hook scripts use jq for JSON parsing."
    echo ""
    echo "Install jq:"
    echo "  macOS:   brew install jq"
    echo "  Linux:   sudo apt install jq  (or your distro's package manager)"
    echo "  Windows: winget install jqlang.jq"
    echo ""
    if [[ "$NON_INTERACTIVE" == true ]]; then
      echo "Continuing without jq (non-interactive mode)."
    else
      read -r -p "Continue without jq? [y/N]: " jq_confirm
      jq_confirm="${jq_confirm:-N}"
      if [[ ! "$jq_confirm" =~ ^[Yy]$ ]]; then
        echo "Install jq and re-run the installer."
        exit 1
      fi
    fi
  fi

  # Optional tools — enhance functionality but not required
  local optional_missing=()

  if ! command -v shellcheck &>/dev/null; then
    optional_missing+=("shellcheck — lints .sh files on commit (winget install koalaman.shellcheck)")
  fi

  if ! command -v scc &>/dev/null && [[ ! -x "$HOME/bin/scc" ]] && [[ ! -x "$HOME/bin/scc.exe" ]]; then
    optional_missing+=("scc — code statistics in session orientation (winget install BenBoyter.scc)")
  fi

  if [[ ${#optional_missing[@]} -gt 0 ]]; then
    echo ""
    echo "OPTIONAL: These tools enhance coordinator functionality but are not required:"
    for tool in "${optional_missing[@]}"; do
      echo "  - $tool"
    done
    echo ""
    echo "All features degrade gracefully without them."
  fi
}

# ---------------------------------------------------------------------------
# Plugin selection
# ---------------------------------------------------------------------------

# Associative array: plugin name -> selected (true/false)
declare -A SELECTED

build_default_selection() {
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name default
    name="$(echo "$entry" | cut -d'|' -f1)"
    default="$(echo "$entry" | cut -d'|' -f2)"
    if [[ "$default" == "on" ]]; then
      SELECTED["$name"]=true
    else
      SELECTED["$name"]=false
    fi
  done
  # coordinator is always on
  SELECTED["coordinator"]=true
}

apply_plugins_arg() {
  # Reset all to false, then enable what was requested
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name
    name="$(echo "$entry" | cut -d'|' -f1)"
    SELECTED["$name"]=false
  done
  SELECTED["coordinator"]=true

  IFS=',' read -ra requested <<< "$PLUGINS_ARG"
  for plugin in "${requested[@]}"; do
    plugin="$(echo "$plugin" | tr -d '[:space:]')"
    if [[ -n "${SELECTED[$plugin]+_}" ]]; then
      SELECTED["$plugin"]=true
    else
      echo "WARNING: Unknown plugin '$plugin' in --plugins list — skipping."
    fi
  done
}

interactive_selection() {
  echo "Select plugins to install:"
  echo ""
  echo "  [*] coordinator    — Core pipeline and workflow skills (always enabled)"

  declare -A CHOICES
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name default version description
    name="$(echo "$entry" | cut -d'|' -f1)"
    default="$(echo "$entry" | cut -d'|' -f2)"
    description="$(echo "$entry" | cut -d'|' -f4)"
    [[ "$name" == "coordinator" ]] && continue

    local prompt_default
    if [[ "$default" == "on" ]]; then
      prompt_default="Y"
    else
      prompt_default="n"
    fi

    read -r -p "  [$prompt_default] $name — $description [Y/n]: " choice
    choice="${choice:-$prompt_default}"
    if [[ "$choice" =~ ^[Yy]$ ]]; then
      SELECTED["$name"]=true
    else
      SELECTED["$name"]=false
    fi
  done
  echo ""
}

select_plugins() {
  build_default_selection

  if [[ -n "$PLUGINS_ARG" ]]; then
    apply_plugins_arg
  elif [[ "$NON_INTERACTIVE" == false ]]; then
    interactive_selection
  fi
  # else: non-interactive with no --plugins arg => use defaults (already set)
}

# ---------------------------------------------------------------------------
# File copy
# ---------------------------------------------------------------------------

copy_plugins() {
  local plugins_target="$CLAUDE_DIR/plugins/coordinator-claude"
  PLUGINS_TARGET="$plugins_target"
  mkdir -p "$plugins_target"

  echo "Copying plugins..."
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name
    name="$(echo "$entry" | cut -d'|' -f1)"
    if [[ "${SELECTED[$name]}" == true ]]; then
      cp -r "$REPO_ROOT/plugins/$name" "$plugins_target/$name"
      echo "  OK: $name"
    fi
  done

  # Copy marketplace manifest (required for Claude Code to discover plugins)
  copy_marketplace_manifest
  echo ""
}

copy_marketplace_manifest() {
  local src="$REPO_ROOT/.claude-plugin/marketplace.json"
  local dest_dir="$PLUGINS_TARGET/.claude-plugin"
  local dest="$dest_dir/marketplace.json"

  if [[ ! -f "$src" ]]; then
    echo "  WARN: marketplace.json not found in repo — plugins may not load"
    return
  fi

  mkdir -p "$dest_dir"

  # Build JSON list of selected plugin names
  local selected_json="["
  local first=true
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name
    name="$(echo "$entry" | cut -d'|' -f1)"
    if [[ "${SELECTED[$name]}" == true ]]; then
      [[ "$first" == false ]] && selected_json+=","
      selected_json+="\"$name\""
      first=false
    fi
  done
  selected_json+="]"

  # Strip pluginRoot (installed layout is flat) and remove unselected plugins
  # so Claude Code doesn't error on missing directories.
  run_python "$src" "$dest" "$selected_json" <<'PYEOF'
import sys, json

src_file = sys.argv[1]
dest_file = sys.argv[2]
selected = set(json.loads(sys.argv[3]))

with open(src_file, 'r') as f:
    data = json.load(f)

if "metadata" in data and "pluginRoot" in data["metadata"]:
    del data["metadata"]["pluginRoot"]

data["plugins"] = [p for p in data.get("plugins", []) if p["name"] in selected]

with open(dest_file, 'w') as f:
    json.dump(data, f, indent=2)
PYEOF

  echo "  OK: marketplace manifest ($(echo "$selected_json" | tr -cd ',' | wc -c | tr -d ' ') + 1 plugins)"
}

# ---------------------------------------------------------------------------
# JSON helpers (inline Python)
# ---------------------------------------------------------------------------

run_python() {
  $PYTHON - "$@"
}

# known_marketplaces.json
register_marketplace() {
  local marketplace_file="$CLAUDE_DIR/plugins/known_marketplaces.json"
  local native_plugins_dir
  native_plugins_dir="$(native_path "$PLUGINS_TARGET")"

  run_python "$marketplace_file" "$native_plugins_dir" "$TIMESTAMP" <<'PYEOF'
import sys, json, os

marketplace_file = sys.argv[1]
native_plugins_dir = sys.argv[2]
timestamp = sys.argv[3]

if os.path.exists(marketplace_file):
    with open(marketplace_file, 'r') as f:
        data = json.load(f)
else:
    data = {}

data["coordinator-claude"] = {
    "source": {
        "source": "directory",
        "path": native_plugins_dir
    },
    "installLocation": native_plugins_dir,
    "lastUpdated": timestamp
}

with open(marketplace_file, 'w') as f:
    json.dump(data, f, indent=2)

print(f"  OK: known_marketplaces.json updated")
PYEOF
}

# installed_plugins.json
register_installed_plugins() {
  local installed_file="$CLAUDE_DIR/plugins/installed_plugins.json"
  local plugins_target_native
  plugins_target_native="$(native_path "$PLUGINS_TARGET")"

  # Build a JSON object of selected plugins + their versions
  local plugins_json="{"
  local first=true
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name version
    name="$(echo "$entry" | cut -d'|' -f1)"
    version="$(echo "$entry" | cut -d'|' -f3)"
    if [[ "${SELECTED[$name]}" == true ]]; then
      [[ "$first" == false ]] && plugins_json+=","
      plugins_json+="\"$name\":\"$version\""
      first=false
    fi
  done
  plugins_json+="}"

  run_python "$installed_file" "$plugins_target_native" "$TIMESTAMP" "$plugins_json" <<'PYEOF'
import sys, json, os

installed_file = sys.argv[1]
plugins_target = sys.argv[2]
timestamp = sys.argv[3]
selected_plugins = json.loads(sys.argv[4])

if os.path.exists(installed_file):
    with open(installed_file, 'r') as f:
        data = json.load(f)
else:
    data = {}

data["version"] = 2
if "plugins" not in data:
    data["plugins"] = {}

for name, version in selected_plugins.items():
    key = f"{name}@coordinator-claude"
    install_path = os.path.join(plugins_target, name)
    data["plugins"][key] = [{
        "scope": "user",
        "installPath": install_path,
        "version": version,
        "installedAt": timestamp,
        "lastUpdated": timestamp
    }]

with open(installed_file, 'w') as f:
    json.dump(data, f, indent=2)

print(f"  OK: installed_plugins.json updated ({len(selected_plugins)} plugins)")
PYEOF
}

# settings.json
register_settings() {
  local settings_file="$CLAUDE_DIR/settings.json"
  local native_plugins_dir
  native_plugins_dir="$(native_path "$PLUGINS_TARGET")"

  # Build JSON objects for selected and available plugin names
  local selected_json="{"
  local first=true
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name
    name="$(echo "$entry" | cut -d'|' -f1)"
    if [[ "${SELECTED[$name]}" == true ]]; then
      [[ "$first" == false ]] && selected_json+=","
      selected_json+="\"$name\":true"
      first=false
    fi
  done
  selected_json+="}"

  run_python "$settings_file" "$native_plugins_dir" "$selected_json" <<'PYEOF'
import sys, json, os

settings_file = sys.argv[1]
native_plugins_dir = sys.argv[2]
selected_plugins = json.loads(sys.argv[3])  # {name: True}

if os.path.exists(settings_file):
    with open(settings_file, 'r') as f:
        data = json.load(f)
else:
    data = {}

if "enabledPlugins" not in data:
    data["enabledPlugins"] = {}

# Only write entries for selected (installed) plugins
for name in selected_plugins:
    key = f"{name}@coordinator-claude"
    data["enabledPlugins"][key] = True

if "extraKnownMarketplaces" not in data:
    data["extraKnownMarketplaces"] = {}

data["extraKnownMarketplaces"]["coordinator-claude"] = {
    "source": {
        "source": "directory",
        "path": native_plugins_dir
    }
}

# Ensure background subagents can use Edit/Write tools
# (defaultMode: "dontAsk" doesn't propagate to background agents)
if "permissions" not in data:
    data["permissions"] = {}
if "allow" not in data["permissions"]:
    data["permissions"]["allow"] = []
for tool in ["Edit", "Write"]:
    if tool not in data["permissions"]["allow"]:
        data["permissions"]["allow"].append(tool)

with open(settings_file, 'w') as f:
    json.dump(data, f, indent=2)

print(f"  OK: settings.json updated")
PYEOF
}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

validate_installation() {
  echo "Validating installation..."
  local errors=0

  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name
    name="$(echo "$entry" | cut -d'|' -f1)"
    if [[ "${SELECTED[$name]}" == true ]]; then
      if [[ -d "$PLUGINS_TARGET/$name" ]]; then
        echo "  OK: plugin dir exists — $name"
      else
        echo "  FAIL: plugin dir missing — $PLUGINS_TARGET/$name"
        errors=$((errors + 1))
      fi
    fi
  done

  local marketplace_file="$CLAUDE_DIR/plugins/known_marketplaces.json"
  if [[ -f "$marketplace_file" ]]; then
    if $PYTHON -c "import json; d=json.load(open('$marketplace_file')); assert 'coordinator-claude' in d" 2>/dev/null; then
      echo "  OK: known_marketplaces.json has coordinator-claude entry"
    else
      echo "  FAIL: known_marketplaces.json missing coordinator-claude entry"
      errors=$((errors + 1))
    fi
  fi

  local manifest="$PLUGINS_TARGET/.claude-plugin/marketplace.json"
  if [[ -f "$manifest" ]]; then
    echo "  OK: marketplace manifest exists"
  else
    echo "  FAIL: marketplace manifest missing — $manifest"
    errors=$((errors + 1))
  fi

  local installed_file="$CLAUDE_DIR/plugins/installed_plugins.json"
  if [[ -f "$installed_file" ]]; then
    local found
    found=$($PYTHON -c "
import json; d=json.load(open('$installed_file'))
plugins = d.get('plugins', {})
print(sum(1 for k in plugins if k.endswith('@coordinator-claude')))
" 2>/dev/null || echo "0")
    echo "  OK: installed_plugins.json has $found coordinator-claude plugin(s)"
  fi

  if [[ "$errors" -gt 0 ]]; then
    echo ""
    echo "WARNING: $errors validation error(s) detected. Review output above."
  fi
  echo ""
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_summary() {
  echo "Installation summary"
  echo "===================="
  echo ""
  echo "Target: $PLUGINS_TARGET"
  echo ""
  echo "Plugins installed:"
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name version
    name="$(echo "$entry" | cut -d'|' -f1)"
    version="$(echo "$entry" | cut -d'|' -f3)"
    if [[ "${SELECTED[$name]}" == true ]]; then
      echo "  + $name ($version)"
    fi
  done
  echo ""
  echo "Next step: restart Claude Code, then run /session-start to verify plugins loaded."
  echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  detect_platform

  CLAUDE_DIR=""
  case "$PLATFORM" in
    linux|darwin|gitbash|wsl|unknown)
      CLAUDE_DIR="$HOME/.claude"
      ;;
  esac

  echo "coordinator-claude installer"
  echo "============================"
  echo ""
  echo "Platform : $PLATFORM"
  echo "Repo root: $REPO_ROOT"
  echo "Claude dir: $CLAUDE_DIR"
  echo ""

  check_prerequisites
  echo "claude CLI : found"
  echo "Python     : $PYTHON"
  echo ""

  select_plugins

  if [[ "$NON_INTERACTIVE" == false && -z "$PLUGINS_ARG" ]]; then
    read -r -p "Proceed with installation? [Y/n]: " confirm
    confirm="${confirm:-Y}"
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
      echo "Cancelled."
      exit 0
    fi
    echo ""
  fi

  copy_plugins

  echo "Registering JSON config files..."
  register_marketplace
  register_installed_plugins
  register_settings
  echo ""

  validate_installation
  print_summary
}

main
