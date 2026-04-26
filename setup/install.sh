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

# Set restrictive umask before any JSON writes so user config files don't
# inherit world-readable perms (issue #16).
umask 077

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"

# Minimum claude CLI version we'll warn about. Plugin manifest schema (plugin.json
# with .claude-plugin/ layout, marketplace.json with metadata.pluginRoot) was
# stable by 2.0.0. We warn-don't-fail below this floor.
CLAUDE_CLI_MIN_VERSION="2.0.0"

# Plugin metadata: name|default|source_kind|description
#
# default values:
#   on       — installed by default, included in non-interactive runs
#   off      — not installed by default, can be selected via --plugins or prompt
#   optional — NOT installed by default and NOT shown in main interactive list.
#              Prompted for separately as an opt-in add-on. Used for plugins
#              that aren't shipped locally (e.g., npm-sourced) or that carry
#              dependencies the average user shouldn't take by default.
#
# source_kind values:
#   local  — plugin source is plugins/<name>/ in this repo; copied to install dir
#   npm    — plugin source is an npm package per marketplace.json. NOT copied
#            from the repo (it doesn't exist locally). Registration in the
#            marketplace manifest is sufficient — Claude Code resolves npm
#            sources when the plugin is enabled.
#   github — plugin source is a separate github repo; NOT installed by this
#            script, user installs separately (e.g., deep-research).
#
# Versions are read dynamically from each plugin's plugin.json at install time
# (issue #2 — eliminates the class of version-mismatch bug). Non-local plugins
# have no local plugin.json; they are tracked only in the marketplace manifest.
PLUGIN_REGISTRY=(
  "coordinator|on|local|Core pipeline and workflow skills (always enabled)"
  "web-dev|on|local|Palí + Fru reviewers"
  "data-science|on|local|Camelia reviewer"
  "game-dev|off|local|Sid reviewer (Unreal Engine)"
  "notebooklm|optional|npm|Media research via NotebookLM (npm-sourced add-on)"
  "remember|on|local|Automatic session memory"
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
#
# Branch logic (issue #4):
#   - gitbash: prefer cygpath if present (Git for Windows ships it; plain MSYS
#     may not). Falls back to a sed translation that handles /c/foo -> C:\foo.
#   - wsl:     translate /mnt/c/... -> C:\... using GNU sed's \U (uppercase)
#     replacement. \U is GNU-sed-only — fine on WSL/Linux, not portable to BSD
#     sed (macOS), but we never call this branch there.
#   - default: pass through unchanged.
native_path() {
  local path="$1"
  case "$PLATFORM" in
    gitbash)
      if command -v cygpath &>/dev/null; then
        cygpath -w "$path" 2>/dev/null || echo "$path"
      else
        # Fallback: /c/foo/bar -> C:\foo\bar. Uppercase drive letter via sed
        # (GNU sed \U is available in MSYS2/Git Bash's bundled GNU sed).
        echo "$path" | sed 's|^/\([a-z]\)/|\U\1:\\|; s|/|\\|g'
      fi
      ;;
    wsl)
      # GNU sed only — safe on WSL since WSL = Linux = GNU sed.
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
# Optional add-on overrides: "" = ask (or skip in non-interactive), true/false = explicit.
NOTEBOOKLM_OPT=""

for arg in "$@"; do
  case "$arg" in
    --non-interactive) NON_INTERACTIVE=true ;;
    --plugins=*)       PLUGINS_ARG="${arg#--plugins=}" ;;
    --plugins)         shift; PLUGINS_ARG="$1" ;;
    --install-notebooklm) NOTEBOOKLM_OPT=true ;;
    --no-notebooklm)      NOTEBOOKLM_OPT=false ;;
    -h|--help)
      cat <<'USAGE'
Usage: setup/install.sh [OPTIONS]

  --non-interactive       Skip prompts; install default-on plugins only.
  --plugins LIST          Comma-separated list of plugins to install
                          (coordinator always included).
  --install-notebooklm    Opt in to the NotebookLM add-on (npm-sourced).
  --no-notebooklm         Skip the NotebookLM add-on prompt.
  -h, --help              Show this help.
USAGE
      exit 0
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

# Compare two dotted version strings. Returns 0 if $1 >= $2, else 1.
version_ge() {
  local a="$1" b="$2"
  # Use sort -V if available; fall back to a simple per-component comparison.
  if printf '%s\n%s\n' "$b" "$a" | sort -V -C 2>/dev/null; then
    return 0
  fi
  return 1
}

check_prerequisites() {
  if ! command -v claude &>/dev/null; then
    echo "ERROR: Claude Code CLI not found on PATH."
    echo "Install from: https://docs.anthropic.com/en/docs/claude-code"
    exit 1
  fi

  # Issue #8: check claude CLI version (warn-don't-fail).
  local claude_version_raw claude_version=""
  claude_version_raw="$(claude --version 2>/dev/null || true)"
  # Parse first dotted-number sequence from output (e.g., "claude 2.1.3 (build ...)" -> 2.1.3)
  claude_version="$(printf '%s' "$claude_version_raw" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
  if [[ -n "$claude_version" ]]; then
    if version_ge "$claude_version" "$CLAUDE_CLI_MIN_VERSION"; then
      echo "claude CLI : $claude_version (>= $CLAUDE_CLI_MIN_VERSION)"
    else
      echo "WARNING: claude CLI version $claude_version is below recommended floor $CLAUDE_CLI_MIN_VERSION."
      echo "         Plugin manifest schema may not be supported. Continuing anyway."
    fi
  else
    echo "WARNING: could not parse claude --version output. Continuing."
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
    echo "Hook scripts degrade gracefully for basic JSON parsing, but"
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
# Plugin source-kind helpers
# ---------------------------------------------------------------------------

# Read field N (1-indexed) from a registry entry by plugin name.
# fields: 1=name, 2=default, 3=source_kind, 4=description
plugin_field() {
  local name="$1" field="$2" entry
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local entry_name
    entry_name="$(echo "$entry" | cut -d'|' -f1)"
    if [[ "$entry_name" == "$name" ]]; then
      echo "$entry" | cut -d'|' -f"$field"
      return 0
    fi
  done
  return 1
}

# Read version from plugin.json for local plugins. Returns empty string for
# non-local plugins or if plugin.json is missing.
read_plugin_version() {
  local name="$1"
  local source_kind
  source_kind="$(plugin_field "$name" 3)"
  if [[ "$source_kind" != "local" ]]; then
    echo ""
    return 0
  fi
  local plugin_json="$REPO_ROOT/plugins/$name/.claude-plugin/plugin.json"
  if [[ ! -f "$plugin_json" ]]; then
    echo ""
    return 0
  fi
  $PYTHON -c "import json; print(json.load(open('$plugin_json')).get('version', ''))" 2>/dev/null || echo ""
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
    # "optional" plugins are off by default — handled by the add-on prompt below.
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

  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name default description
    name="$(echo "$entry" | cut -d'|' -f1)"
    default="$(echo "$entry" | cut -d'|' -f2)"
    description="$(echo "$entry" | cut -d'|' -f4)"
    [[ "$name" == "coordinator" ]] && continue
    # Optional add-ons are prompted separately after core selection.
    [[ "$default" == "optional" ]] && continue

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

  prompt_optional_addons
}

# Track whether NotebookLM was opted in (for the install summary).
NOTEBOOKLM_INSTALLED=false

# Prompt for opt-in add-ons. Currently: notebooklm.
#
# Resolution order for whether to install notebooklm:
#   1. --install-notebooklm / --no-notebooklm flag (explicit override).
#   2. --plugins list explicitly mentioning notebooklm (apply_plugins_arg
#      already toggled SELECTED — treat as explicit opt-in).
#   3. Interactive prompt if stdin is a TTY and not --non-interactive.
#   4. Otherwise: skip cleanly with a printed note.
prompt_optional_addons() {
  # If the registry doesn't contain notebooklm (e.g., trimmed registry), skip.
  if [[ -z "${SELECTED[notebooklm]+_}" ]]; then
    return 0
  fi

  # Explicit flag wins.
  if [[ "$NOTEBOOKLM_OPT" == true ]]; then
    SELECTED["notebooklm"]=true
    NOTEBOOKLM_INSTALLED=true
    echo "NotebookLM add-on: enabled (--install-notebooklm)"
    echo ""
    return 0
  fi
  if [[ "$NOTEBOOKLM_OPT" == false ]]; then
    SELECTED["notebooklm"]=false
    echo "NotebookLM add-on: skipped (--no-notebooklm)"
    echo ""
    return 0
  fi

  # --plugins list explicitly named it.
  if [[ -n "$PLUGINS_ARG" && "${SELECTED[notebooklm]}" == true ]]; then
    NOTEBOOKLM_INSTALLED=true
    echo "NotebookLM add-on: enabled (via --plugins)"
    echo ""
    return 0
  fi

  # Non-interactive with no opt-in signal => skip cleanly.
  if [[ "$NON_INTERACTIVE" == true ]]; then
    SELECTED["notebooklm"]=false
    echo "NotebookLM add-on: skipped (non-interactive default)."
    echo "  Re-run with --install-notebooklm to enable later."
    echo ""
    return 0
  fi

  # Interactive prompt — only if stdin is a TTY.
  if [[ -t 0 ]]; then
    echo ""
    echo "Optional add-on:"
    echo "  notebooklm — Media research via NotebookLM (npm-sourced)"
    echo "  Resolved on enable by Claude Code from the marketplace manifest."
    read -r -p "Install the NotebookLM optional add-on? [y/N]: " nlm_choice
    nlm_choice="${nlm_choice:-N}"
    if [[ "$nlm_choice" =~ ^[Yy]$ ]]; then
      SELECTED["notebooklm"]=true
      NOTEBOOKLM_INSTALLED=true
    else
      SELECTED["notebooklm"]=false
      echo "Skipped. Re-run setup or pass --install-notebooklm to enable later."
    fi
    echo ""
  else
    SELECTED["notebooklm"]=false
    echo "NotebookLM add-on: skipped (no TTY for prompt)."
    echo "  Re-run with --install-notebooklm to enable later."
    echo ""
  fi
}

# ---------------------------------------------------------------------------
# File copy
# ---------------------------------------------------------------------------

# Track plugins where existing target was preserved (collision summary).
COLLISIONS=()
# Track plugins skipped because they have no local source (npm/github).
SKIPPED_NONLOCAL=()

copy_plugins() {
  local plugins_target="$CLAUDE_DIR/plugins/coordinator-claude"
  PLUGINS_TARGET="$plugins_target"
  mkdir -p "$plugins_target"

  echo "Copying plugins..."
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name source_kind
    name="$(echo "$entry" | cut -d'|' -f1)"
    source_kind="$(echo "$entry" | cut -d'|' -f3)"
    if [[ "${SELECTED[$name]}" != true ]]; then
      continue
    fi

    # Issue #1: skip cp -r for non-local plugins (npm, github). They are
    # registered via marketplace.json but their bits live elsewhere.
    if [[ "$source_kind" != "local" ]]; then
      echo "  SKIP: $name (source_kind=$source_kind — registered via marketplace, not copied)"
      SKIPPED_NONLOCAL+=("$name")
      continue
    fi

    local src="$REPO_ROOT/plugins/$name"
    local dest="$plugins_target/$name"

    if [[ ! -d "$src" ]]; then
      echo "  ERROR: source directory missing for local plugin '$name': $src"
      exit 1
    fi

    # Issue #7: don't clobber silently. If dest exists, back it up to .bak
    # (overwriting any prior .bak), then proceed.
    if [[ -d "$dest" ]]; then
      local backup="$dest.bak"
      rm -rf "$backup"
      mv "$dest" "$backup"
      echo "  BACKUP: $name (existing -> $(basename "$backup"))"
      COLLISIONS+=("$name")
    fi

    cp -r "$src" "$dest"
    echo "  OK: $name"
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

  # Issue #10: rewrite relative source paths. After install the layout is flat
  # (plugins live at $PLUGINS_TARGET/<name>), so "./plugins/coordinator" in the
  # source manifest becomes "./coordinator" in the installed manifest. Object
  # sources (npm, github) pass through unchanged.
  #
  # Also strips pluginRoot (irrelevant in installed flat layout) and removes
  # unselected plugins so Claude Code doesn't error on missing directories.
  run_python "$src" "$dest" "$selected_json" <<'PYEOF'
import sys, json, os, tempfile

src_file = sys.argv[1]
dest_file = sys.argv[2]
selected = set(json.loads(sys.argv[3]))

with open(src_file, 'r') as f:
    data = json.load(f)

if "metadata" in data and "pluginRoot" in data["metadata"]:
    del data["metadata"]["pluginRoot"]

new_plugins = []
for p in data.get("plugins", []):
    if p["name"] not in selected:
        continue
    src_field = p.get("source")
    # Rewrite string sources like "./plugins/<name>" -> "./<name>" (flat layout).
    if isinstance(src_field, str) and src_field.startswith("./plugins/"):
        p["source"] = "./" + src_field[len("./plugins/"):]
    new_plugins.append(p)
data["plugins"] = new_plugins

# Atomic write (issue #3 pattern, applied to copy too for consistency).
tmp = dest_file + ".tmp"
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
os.replace(tmp, dest_file)
PYEOF

  # Issue #11: count via Python len() instead of comma-counting (which yields 1
  # when zero plugins are selected).
  local plugin_count
  plugin_count=$($PYTHON -c "import json; print(len(json.loads('$selected_json')))")
  echo "  OK: marketplace manifest ($plugin_count plugins)"
}

# ---------------------------------------------------------------------------
# JSON helpers (inline Python)
# ---------------------------------------------------------------------------

run_python() {
  $PYTHON - "$@"
}

# Track whether settings.json got Edit/Write appended to permissions.allow
# (issue #15 — surface this in the install summary).
PERMS_APPENDED=()

# known_marketplaces.json
register_marketplace() {
  local marketplace_file="$CLAUDE_DIR/plugins/known_marketplaces.json"
  local native_plugins_dir
  native_plugins_dir="$(native_path "$PLUGINS_TARGET")"

  # Issue #3: atomic write with backup.
  run_python "$marketplace_file" "$native_plugins_dir" "$TIMESTAMP" <<'PYEOF'
import sys, json, os, shutil

marketplace_file = sys.argv[1]
native_plugins_dir = sys.argv[2]
timestamp = sys.argv[3]

if os.path.exists(marketplace_file):
    with open(marketplace_file, 'r') as f:
        data = json.load(f)
    # Backup prior contents before replace.
    shutil.copy2(marketplace_file, marketplace_file + ".bak")
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

# Atomic: write to .tmp then os.replace.
tmp = marketplace_file + ".tmp"
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
os.replace(tmp, marketplace_file)

print("  OK: known_marketplaces.json updated")
PYEOF
}

# installed_plugins.json
register_installed_plugins() {
  local installed_file="$CLAUDE_DIR/plugins/installed_plugins.json"
  local plugins_target_native
  plugins_target_native="$(native_path "$PLUGINS_TARGET")"

  # Build a JSON object of selected plugins + their versions.
  # Issue #2: read versions dynamically from each plugin.json. Non-local plugins
  # (npm/github) have no local plugin.json; they get a placeholder version since
  # the marketplace registration carries the real source-of-truth.
  local plugins_json="{"
  local first=true
  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name source_kind version
    name="$(echo "$entry" | cut -d'|' -f1)"
    source_kind="$(echo "$entry" | cut -d'|' -f3)"
    if [[ "${SELECTED[$name]}" != true ]]; then
      continue
    fi

    if [[ "$source_kind" == "local" ]]; then
      version="$(read_plugin_version "$name")"
      if [[ -z "$version" ]]; then
        echo "  WARN: could not read version for $name from plugin.json — using 0.0.0"
        version="0.0.0"
      fi
    else
      # Non-local plugins are not tracked in installed_plugins.json by this
      # installer (no local install path); skip them.
      continue
    fi

    [[ "$first" == false ]] && plugins_json+=","
    plugins_json+="\"$name\":\"$version\""
    first=false
  done
  plugins_json+="}"

  # Issue #3: atomic write with backup.
  run_python "$installed_file" "$plugins_target_native" "$TIMESTAMP" "$plugins_json" <<'PYEOF'
import sys, json, os, shutil

installed_file = sys.argv[1]
plugins_target = sys.argv[2]
timestamp = sys.argv[3]
selected_plugins = json.loads(sys.argv[4])

if os.path.exists(installed_file):
    with open(installed_file, 'r') as f:
        data = json.load(f)
    shutil.copy2(installed_file, installed_file + ".bak")
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

tmp = installed_file + ".tmp"
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
os.replace(tmp, installed_file)

print(f"  OK: installed_plugins.json updated ({len(selected_plugins)} plugins)")
PYEOF
}

# settings.json
register_settings() {
  local settings_file="$CLAUDE_DIR/settings.json"
  local native_plugins_dir
  native_plugins_dir="$(native_path "$PLUGINS_TARGET")"

  # Build JSON objects for selected plugin names
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

  # Issue #3: atomic write with backup.
  # Issue #15: emit which permissions were appended on stdout so we can surface
  # it in the install summary.
  local perms_output
  perms_output="$(run_python "$settings_file" "$native_plugins_dir" "$selected_json" <<'PYEOF'
import sys, json, os, shutil

settings_file = sys.argv[1]
native_plugins_dir = sys.argv[2]
selected_plugins = json.loads(sys.argv[3])  # {name: True}

if os.path.exists(settings_file):
    with open(settings_file, 'r') as f:
        data = json.load(f)
    shutil.copy2(settings_file, settings_file + ".bak")
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
# (defaultMode: "dontAsk" doesn't propagate to background agents).
# Track which were actually appended so the installer can surface this.
if "permissions" not in data:
    data["permissions"] = {}
if "allow" not in data["permissions"]:
    data["permissions"]["allow"] = []
appended = []
for tool in ["Edit", "Write"]:
    if tool not in data["permissions"]["allow"]:
        data["permissions"]["allow"].append(tool)
        appended.append(tool)

tmp = settings_file + ".tmp"
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
os.replace(tmp, settings_file)

print("  OK: settings.json updated")
if appended:
    # Magic marker the shell parses to populate PERMS_APPENDED.
    print("PERMS_APPENDED=" + ",".join(appended))
PYEOF
)"
  echo "$perms_output" | grep -v '^PERMS_APPENDED=' || true
  local perms_line
  perms_line="$(echo "$perms_output" | grep '^PERMS_APPENDED=' || true)"
  if [[ -n "$perms_line" ]]; then
    IFS=',' read -ra _appended <<< "${perms_line#PERMS_APPENDED=}"
    for t in "${_appended[@]}"; do
      PERMS_APPENDED+=("$t")
    done
  fi
}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

validate_installation() {
  echo "Validating installation..."
  local errors=0

  for entry in "${PLUGIN_REGISTRY[@]}"; do
    local name source_kind
    name="$(echo "$entry" | cut -d'|' -f1)"
    source_kind="$(echo "$entry" | cut -d'|' -f3)"
    if [[ "${SELECTED[$name]}" == true && "$source_kind" == "local" ]]; then
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

  # Issue #9: validation failure must be fatal.
  if [[ "$errors" -gt 0 ]]; then
    echo ""
    echo "ERROR: $errors validation error(s) detected. Installation is incomplete."
    echo "Review the FAIL lines above; backups (.bak) of any modified JSON files were preserved."
    exit 1
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
    local name source_kind version
    name="$(echo "$entry" | cut -d'|' -f1)"
    source_kind="$(echo "$entry" | cut -d'|' -f3)"
    if [[ "${SELECTED[$name]}" == true ]]; then
      if [[ "$source_kind" == "local" ]]; then
        version="$(read_plugin_version "$name")"
        echo "  + $name ($version)"
      else
        echo "  + $name (registered via $source_kind, not copied)"
      fi
    fi
  done
  echo ""

  # Issue #15: surface permissions changes explicitly.
  if (( ${#PERMS_APPENDED[@]} > 0 )); then
    echo "Settings changes:"
    echo "  Added $(IFS=', '; echo "${PERMS_APPENDED[*]}") to permissions.allow"
    echo ""
  fi

  if (( ${#COLLISIONS[@]} > 0 )); then
    echo "Existing plugin directories were preserved as <name>.bak:"
    for c in "${COLLISIONS[@]}"; do
      echo "  - $c.bak"
    done
    echo ""
  fi

  if (( ${#SKIPPED_NONLOCAL[@]} > 0 )); then
    echo "Plugins registered via marketplace (no local copy):"
    for s in "${SKIPPED_NONLOCAL[@]}"; do
      echo "  - $s"
    done
    echo ""
  fi

  # Optional add-on status.
  if [[ -n "${SELECTED[notebooklm]+_}" ]]; then
    if [[ "$NOTEBOOKLM_INSTALLED" == true ]]; then
      echo "NotebookLM add-on: installed"
    else
      echo "NotebookLM add-on: skipped (run setup again or enable manually to add)"
    fi
    echo ""
  fi

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
