#!/usr/bin/env bash
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
# bash 4.3+ guard (system admission gate — see below)
# ---------------------------------------------------------------------------
# This installer is the SYSTEM ADMISSION GATE — it must require what the installed
# coordinator needs to run, not merely what this script uses. The installer itself
# uses an associative array (declare -A SELECTED, bash 4.0+), but it installs
# `coordinator-safe-commit` — the commit helper invoked on essentially every commit —
# which uses `local -n` namerefs (bash 4.3+). So the floor is bash 4.3, enforced here
# at install time rather than letting the helper abort cryptically on the user's first
# commit. macOS ships bash 3.2 (2007, frozen on GPLv2) as /bin/bash; install a current
# bash via Homebrew and run the installer with it. Linux, WSL, and Git Bash for Windows
# all ship bash 4.3+ already. (BASH_VERSINFO and (( )) exist since bash 2.x, so the
# guard itself runs fine on 3.2 — it executes well before the first declare -A.)
# Policy: DR-148-require-bash4-on-macos. Cf. the per-script 4.0 guard in
# name-personas.sh, which is downstream of this gate and only uses declare -A.
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
  echo "ERROR: the coordinator-claude installer requires bash 4.3 or later." >&2
  echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
  echo "" >&2
  echo "  macOS ships bash 3.2 as /bin/bash. Install Homebrew (https://brew.sh), then a" >&2
  echo "  current bash, and re-run the installer with it:" >&2
  echo "      brew install bash" >&2
  echo '      "$(brew --prefix)/bin/bash" setup/install.sh' >&2
  echo "" >&2
  echo "  (Pass the same flags you used here after the script path. Linux, WSL, and" >&2
  echo "   Git Bash for Windows ship bash 4.3+ — if you hit this there, upgrade bash via" >&2
  echo "   your package manager.)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"

# Minimum claude CLI version we'll warn about. Plugin manifest schema (plugin.json
# with .claude-plugin/ layout, marketplace.json with metadata.pluginRoot) was
# stable by 2.0.0. We warn-don't-fail below this floor.
CLAUDE_CLI_MIN_VERSION="2.0.0"

# Minimum Node.js version required by the NotebookLM optional add-on
# (resolves via `npx -y notebooklm-mcp` at runtime). Matches Anthropic's stated
# floor for Claude Code.
NODE_MIN_VERSION="18"

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
  "web-dev|on|local|Front-End and UX reviewers"
  "data-science|on|local|Data Science reviewer"
  "deep-research|on|local|Multi-agent deep research pipelines (web/repo/structured)"
  "game-dev|off|local|Game Dev reviewer (Unreal Engine)"
  "notebooklm|optional|npm|Media research via NotebookLM (npm-sourced add-on)"
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
PROFILE_ARG=""
# Optional add-on overrides: "" = ask (or skip in non-interactive), true/false = explicit.
NOTEBOOKLM_OPT=""
# codex-review-gate skill is bundled inside the coordinator plugin but is an
# opt-in add-on. The skill wraps the external openai/codex-plugin-cc — most
# users don't run Codex, so default installs strip the skill out post-copy.
CODEX_OPT=""
# Naming add-on: optional persona-naming prompt at end of install.
# "" = ask in TTY (default skip); true = force prompt-yes; false = force skip.
NAMING_OPT=""

for arg in "$@"; do
  case "$arg" in
    --non-interactive) NON_INTERACTIVE=true ;;
    --plugins=*)       PLUGINS_ARG="${arg#--plugins=}" ;;
    --plugins)         shift; PLUGINS_ARG="$1" ;;
    --profile=*)       PROFILE_ARG="${arg#--profile=}" ;;
    --profile)         shift; PROFILE_ARG="$1" ;;
    --install-notebooklm) NOTEBOOKLM_OPT=true ;;
    --no-notebooklm)      NOTEBOOKLM_OPT=false ;;
    --enable-codex)       CODEX_OPT=true ;;
    --no-codex)           CODEX_OPT=false ;;
    --name-personas)      NAMING_OPT=true ;;
    --no-naming)          NAMING_OPT=false ;;
    -h|--help)
      cat <<'USAGE'
Usage: setup/install.sh [OPTIONS]

  --profile NAME          Install a preset plugin bundle (mutually exclusive
                          with --plugins):
                            core      coordinator only — minimal footprint
                            standard  coordinator, web-dev, data-science
                                      (excludes deep-research; opt in via
                                      --profile full or explicit --plugins)
                            full      coordinator, deep-research, web-dev,
                                      data-science, game-dev
  --non-interactive       Skip prompts; install default-on plugins only.
  --plugins LIST          Comma-separated list of plugins to install
                          (coordinator always included). Use --profile for
                          common presets; --plugins for fine-grained control.
  --install-notebooklm    Opt in to the NotebookLM add-on (npm-sourced).
  --no-notebooklm         Skip the NotebookLM add-on prompt.
  --enable-codex          Opt in to the codex-review-gate skill (requires
                          the external openai/codex-plugin-cc plugin).
  --no-codex              Skip the codex-review-gate prompt.
  --name-personas         Force-prompt for persona naming at end of install
                          (even in non-interactive mode, where it is
                          otherwise skipped).
  --no-naming             Skip the persona-naming prompt entirely.
  -h, --help              Show this help.
USAGE
      exit 0
      ;;
  esac
done

# ---------------------------------------------------------------------------
# --profile alias resolution
# ---------------------------------------------------------------------------
# --profile is a thin alias over --plugins. Resolve it first so the rest of
# the script only needs to reason about PLUGINS_ARG.
#
# Profiles are pinned (not computed dynamically) — "full" enumerates every
# locally-installable plugin explicitly so future registry additions don't
# silently expand it.
if [[ -n "$PROFILE_ARG" ]]; then
  if [[ -n "$PLUGINS_ARG" ]]; then
    echo "ERROR: --profile and --plugins are mutually exclusive."
    echo "       Use --profile for preset bundles or --plugins for a custom list."
    exit 1
  fi
  case "$PROFILE_ARG" in
    core)
      # Minimal footprint: coordinator pipeline only.
      PLUGINS_ARG="coordinator"
      ;;
    standard)
      # Common default for most users. Excludes deep-research because it
      # dispatches Agent Teams — opt in deliberately via --profile full or
      # --plugins coordinator,deep-research,...
      PLUGINS_ARG="coordinator,web-dev,data-science"
      ;;
    full)
      # All locally-installable plugins. Pinned explicitly — do not change to
      # "all default-on" or a dynamic expansion.
      PLUGINS_ARG="coordinator,deep-research,web-dev,data-science,game-dev"
      ;;
    *)
      echo "ERROR: Unknown profile '$PROFILE_ARG'."
      echo "       Valid profiles: core, standard, full"
      exit 1
      ;;
  esac
  echo "Profile '$PROFILE_ARG' resolved to --plugins $PLUGINS_ARG"
  echo ""
fi

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

# Compare two dotted version strings. Returns 0 if $1 >= $2, else 1.
version_ge() {
  local a="$1" b="$2"
  # Prefer `sort -V` (GNU coreutils). BSD/macOS `sort` has no -V even under a
  # Homebrew bash, so probe support once and fall back to a dotted-component
  # numeric compare — otherwise every comparison silently returned "below floor".
  if printf '%s\n' 1 2 | sort -V >/dev/null 2>&1; then
    if printf '%s\n%s\n' "$b" "$a" | sort -V -C 2>/dev/null; then
      return 0
    fi
    return 1
  fi
  # Fallback: compare up to three dotted numeric components (strip any
  # non-numeric suffix like -beta; treat missing components as 0).
  # IFS=. read -ra splits on dots WITHOUT pathname expansion — an unquoted
  # `local -a av=($a)` would glob-expand if a version string ever contained * or ?.
  local i an bn
  local -a av bv
  IFS=. read -ra av <<< "$a"
  IFS=. read -ra bv <<< "$b"
  for i in 0 1 2; do
    an="${av[i]:-0}"; bn="${bv[i]:-0}"
    an="${an%%[!0-9]*}"; bn="${bn%%[!0-9]*}"
    an="${an:-0}"; bn="${bn:-0}"
    if (( 10#$an > 10#$bn )); then return 0; fi
    if (( 10#$an < 10#$bn )); then return 1; fi
  done
  return 0
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

  # node/npm — surfaced here as warn-only. Hard-failed later (see
  # check_notebooklm_prereqs) ONLY if the user opts into the NotebookLM add-on,
  # which resolves via `npx -y notebooklm-mcp` at runtime.
  NODE_VERSION=""
  NPM_PRESENT=false
  if command -v node &>/dev/null; then
    NODE_VERSION="$(node --version 2>/dev/null | grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+' | head -1 | sed 's/^v//' || true)"
  fi
  if command -v npm &>/dev/null || command -v npm.cmd &>/dev/null; then
    NPM_PRESENT=true
  fi
  if [[ -n "$NODE_VERSION" ]]; then
    local node_major
    node_major="$(echo "$NODE_VERSION" | cut -d. -f1)"
    if [[ "$node_major" -lt "$NODE_MIN_VERSION" ]]; then
      echo "node       : $NODE_VERSION (below recommended $NODE_MIN_VERSION+ for NotebookLM add-on)"
    else
      echo "node       : $NODE_VERSION"
    fi
  else
    echo "node       : not found (only required for the NotebookLM add-on)"
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
  prompt_codex_addon
}

# Track whether NotebookLM was opted in (for the install summary).
NOTEBOOKLM_INSTALLED=false

# Track whether codex-review-gate was opted in (for the install summary +
# post-copy strip step in copy_plugins).
CODEX_INSTALLED=false

# Prompt for the codex-review-gate skill. Unlike notebooklm this is not a
# separate plugin — the skill ships inside the coordinator plugin and is
# stripped out of the install if not opted in. Resolution order mirrors
# prompt_optional_addons: explicit flag → non-interactive default off → TTY
# prompt → no-TTY default off.
prompt_codex_addon() {
  if [[ "$CODEX_OPT" == true ]]; then
    CODEX_INSTALLED=true
    echo "codex-review-gate skill: enabled (--enable-codex)"
    echo ""
    return 0
  fi
  if [[ "$CODEX_OPT" == false ]]; then
    CODEX_INSTALLED=false
    echo "codex-review-gate skill: skipped (--no-codex)"
    echo ""
    return 0
  fi

  if [[ "$NON_INTERACTIVE" == true ]]; then
    CODEX_INSTALLED=false
    echo "codex-review-gate skill: skipped (non-interactive default)."
    echo "  Re-run with --enable-codex to add it later."
    echo ""
    return 0
  fi

  if [[ -t 0 ]]; then
    echo ""
    echo "Optional add-on:"
    echo "  codex-review-gate — Run Codex (openai/codex-plugin-cc) as an"
    echo "  independent-model second-opinion review in /workweek-complete and"
    echo "  /bug-sweep --codex-verify. Requires the codex-plugin-cc plugin"
    echo "  installed and the Codex CLI authenticated separately."
    read -r -p "Install the codex-review-gate skill? [y/N]: " codex_choice
    codex_choice="${codex_choice:-N}"
    if [[ "$codex_choice" =~ ^[Yy]$ ]]; then
      CODEX_INSTALLED=true
    else
      CODEX_INSTALLED=false
      echo "Skipped. Re-run setup or pass --enable-codex to add it later."
    fi
    echo ""
  else
    CODEX_INSTALLED=false
    echo "codex-review-gate skill: skipped (no TTY for prompt)."
    echo "  Re-run with --enable-codex to add it later."
    echo ""
  fi
}

# Prompt for optional persona naming. The publish repo ships nameless
# (role-distinct reviewers referred to by articulated role labels: "the Staff
# Engineer", "the Game Dev Reviewer", etc.). Some users find names easier to
# think with — this prompt offers the binding once at install time.
#
# Resolution order mirrors prompt_codex_addon:
#   1. --no-naming → skip silently.
#   2. --name-personas → force-prompt path (even in non-interactive).
#   3. NON_INTERACTIVE → skip silently (no prompt, no output).
#   4. No TTY → skip silently.
#   5. TTY → suggest, three responses (yes / later / skip), default skip.
#
# This prompt is a *suggestion*, never a prescription. The default state is
# nameless. The publish repo never assumes the user wants names.
prompt_naming_addon() {
  if [[ "$NAMING_OPT" == false ]]; then
    return 0
  fi

  if [[ "$NAMING_OPT" != true && "$NON_INTERACTIVE" == true ]]; then
    return 0
  fi

  if [[ "$NAMING_OPT" != true && ! -t 0 ]]; then
    return 0
  fi

  local naming_script
  naming_script="$(dirname "${BASH_SOURCE[0]}")/name-personas.sh"

  echo ""
  echo "Optional: persona naming"
  echo "  You'll be working with seven role-distinct reviewer agents (the Staff Engineer,"
  echo "  the Game Dev Reviewer, etc.). Some people find it easier to think of them as"
  echo "  named collaborators — others prefer role labels alone. Naming is optional."
  echo ""
  read -r -p "Name your reviewers now? [y/later/N]: " naming_choice
  naming_choice="${naming_choice:-N}"

  case "$naming_choice" in
    [Yy]|[Yy][Ee][Ss])
      if [[ ! -x "$naming_script" ]]; then
        echo "  Could not find $naming_script — run it manually whenever you'd like."
        echo ""
        return 0
      fi
      echo ""
      echo "  Naming flow: enter a name for each role, or press Enter to keep the role label as-is."
      echo ""
      local -a naming_args=()
      local -a roles=(
        "the Staff Engineer"
        "the Ambition Advocate"
        "the VP-Product Reviewer"
        "the Game Dev Reviewer"
        "the Front-End Reviewer"
        "the UX Reviewer"
        "the Data Science Reviewer"
      )
      for role in "${roles[@]}"; do
        read -r -p "  Name for ${role}? (Enter to skip): " chosen_name
        if [[ -n "$chosen_name" ]]; then
          naming_args+=("$role" "$chosen_name")
        fi
      done
      if (( ${#naming_args[@]} == 0 )); then
        echo ""
        echo "  No names entered — leaving role labels in place."
        echo "  Run setup/name-personas.sh whenever you'd like."
        echo ""
      else
        echo ""
        echo "  Binding names via setup/name-personas.sh..."
        echo ""
        bash "$naming_script" "${naming_args[@]}"
      fi
      ;;
    [Ll]|[Ll][Aa][Tt][Ee][Rr])
      echo "  Run setup/name-personas.sh whenever you'd like."
      echo ""
      ;;
    *)
      echo "  Skipped. Reviewers remain role-distinct under their role labels."
      echo ""
      ;;
  esac
}

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
# Conditional prereqs (after plugin selection)
# ---------------------------------------------------------------------------

# Hard-fail if user opted into NotebookLM but doesn't have Node.js / npm.
# The NotebookLM MCP server is invoked as `npx -y notebooklm-mcp` — without
# node + npm + npx the add-on cannot start, and the user would only discover
# this at first /notebooklm-research call (a much more painful failure mode).
check_notebooklm_prereqs() {
  if [[ -z "${SELECTED[notebooklm]+_}" ]] || [[ "${SELECTED[notebooklm]}" != true ]]; then
    return 0
  fi

  local fail=false
  if [[ -z "$NODE_VERSION" ]]; then
    echo "ERROR: NotebookLM add-on selected but node not found on PATH."
    echo "       The notebooklm-mcp server runs via 'npx -y notebooklm-mcp'."
    echo "       Install Node.js $NODE_MIN_VERSION+ from https://nodejs.org/"
    echo "       (winget install OpenJS.NodeJS.LTS / brew install node /"
    echo "        sudo apt install nodejs)"
    fail=true
  else
    local node_major
    node_major="$(echo "$NODE_VERSION" | cut -d. -f1)"
    if [[ "$node_major" -lt "$NODE_MIN_VERSION" ]]; then
      echo "ERROR: NotebookLM add-on selected but node $NODE_VERSION is below"
      echo "       the required $NODE_MIN_VERSION+ floor. Upgrade Node.js."
      fail=true
    fi
  fi

  if [[ "$NPM_PRESENT" != true ]]; then
    echo "ERROR: NotebookLM add-on selected but npm not found on PATH."
    echo "       npm ships with the Node.js LTS installer — reinstall node."
    fail=true
  fi

  if [[ "$fail" == true ]]; then
    echo ""
    echo "Re-run setup without --install-notebooklm (or answer 'n' at the prompt)"
    echo "to skip the add-on, or install Node.js and re-run."
    exit 1
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

    # codex-review-gate is bundled inside the coordinator plugin but is an
    # opt-in add-on (it wraps the external openai/codex-plugin-cc). Strip it
    # from the install when the user didn't opt in — this keeps the default
    # /workweek-complete and /bug-sweep flows free of Codex steps without
    # requiring command-file variants.
    if [[ "$name" == "coordinator" && "$CODEX_INSTALLED" != true ]]; then
      local codex_skill="$dest/skills/codex-review-gate"
      if [[ -d "$codex_skill" ]]; then
        rm -rf "$codex_skill"
        echo "  STRIPPED: coordinator/skills/codex-review-gate (opt in via --enable-codex)"
      fi
    fi
  done

  # Shebang-scan: chmod +x every shebanged file in the installed plugins tree.
  # Runs once after all cp -r copies complete so it catches all plugin files
  # regardless of source-repo index mode (defense against core.fileMode=false drift).
  # Null-delimited find avoids word-splitting on filenames with spaces (F2 fix).
  # Process substitution requires bash 4+ — gated by the bash 4.3 admission guard above.
  # Spec backlink: docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 7
  echo "Fixing exec bits on installed plugin shebanged files..."
  # Review: reviewer — null-delimited form prevents word-splitting on paths with spaces
  while IFS= read -r -d '' _pf; do
    head -c 2 "$_pf" 2>/dev/null | grep -q '^#!' && chmod +x "$_pf"
  done < <(find "$plugins_target" -type f -print0)

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
# Setup/ percolation mechanism delivery
# ---------------------------------------------------------------------------
#
# Mirrors the Step 3d delivery loop that ships in
# coordinator/lib/install-substrate.sh — copies the publish/percolation
# scripts from the just-copied coordinator plugin templates into
# ~/.claude/setup/ so fresh users have a working `bash ~/.claude/setup/publish.sh`
# entry point without re-cloning the publish repo.
#
# Why a minimal mirror and not a subprocess call to install-substrate.sh:
#   install-substrate.sh is the coordinator /setup Phase 3 driver — it
#   requires CLAUDE_PLUGIN_ROOT, hard-fails on any missing template dir, and
#   executes machine-local substrate seeding + bin/ resolver installation +
#   Windows PATH/AppX health checks. Invoking it from this installer would
#   either run those side-effects out of band (wrong phase) or require a
#   --setup-only flag that install-substrate.sh does not expose. The
#   _install_one semantics for the setup/ files specifically are simple
#   enough (existence check, no diff-preservation needed — operators don't
#   customize publish.sh) that mirroring the loop is cheaper than refactoring
#   install-substrate.sh to expose a partial-invocation surface.
#
# Single source of truth: the file list (publish.sh, publish_sync.py,
# publish-targets.example.sh, .percolate-identity.example, and the
# percolate-hooks/README.md doctrine file) plus the exec-flag rule are now
# declared in coordinator/lib/setup-templates-manifest.sh, sourced below.
# Both this function and install-substrate.sh read from that manifest — the
# dual-source-of-truth concern that prompted the "refactor only if it churns"
# deferral has been resolved. Spec: archive/specs/2026-05-27-cqcs-cluster7-lib-consolidation.md
deliver_setup_templates() {
  local setup_src="$PLUGINS_TARGET/coordinator/templates/setup"
  local setup_dest="$CLAUDE_DIR/setup"

  # Silent skip if the coordinator plugin's setup templates aren't on disk.
  # This happens when --plugins excluded coordinator (impossible — coordinator
  # is always selected) or when an older coordinator plugin without the
  # templates/setup/ directory got copied. Either way, not an installer fault.
  if [[ ! -d "$setup_src" ]]; then
    echo "  SKIP: ~/.claude/setup/ delivery (coordinator templates/setup/ not present at $setup_src)"
    return 0
  fi

  # File list is the single source of truth in the plugin's lib/ manifest.
  # HARD-FAIL on a missing manifest — do NOT silent-skip. The manifest ships
  # inside the same plugin tree copy_plugins() just laid down, so its absence
  # means a corrupt/incomplete plugin copy (CRLF mangling that breaks the source,
  # a publish.sh lib/ glob miss, or a stale plugin tree) — that is fatal, not a
  # benign older-plugin case. A silent `return 0` here would deliver ZERO setup/
  # files and exit success on the OSS clean-install path, re-introducing the exact
  # install-surface failure this plan exists to prevent. This matches File B's
  # posture (install-substrate.sh hard-fails on the same missing dependency) — the
  # two consumers MUST share one failure posture, not opposite ones.
  local manifest="$PLUGINS_TARGET/coordinator/lib/setup-templates-manifest.sh"
  if [[ ! -f "$manifest" ]]; then
    echo "  ERROR: setup-templates-manifest.sh not found at $manifest" >&2
    echo "  ERROR: ~/.claude/setup/ percolation mechanism will NOT be installed." >&2
    echo "  ERROR: This indicates a corrupt or incomplete coordinator plugin copy." >&2
    echo "  ERROR: Reinstall the coordinator plugin and re-run the installer." >&2
    exit 1
  fi
  source "$manifest"

  mkdir -p "$setup_dest"
  echo "Delivering ~/.claude/setup/ percolation scripts..."
  for f in "${SETUP_TEMPLATE_FILES[@]}"; do
    local src_file="$setup_src/$f"
    local dest_file="$setup_dest/$f"
    if [[ ! -f "$src_file" ]]; then
      echo "  WARN: template missing — $src_file (skipping)"
      continue
    fi
    if [[ -f "$dest_file" ]]; then
      echo "  KEEP: setup/$f (operator-preserved)"
    else
      cp "$src_file" "$dest_file"
      echo "  OK:   setup/$f"
    fi
  done

  # percolate-hooks/ doctrine README — subdirectory destination — also manifest-driven.
  # Only the generic README ships; per-target hook subdirs
  # (~/.claude/setup/percolate-hooks/<target>/) are operator-authored.
  for hf in "${SETUP_TEMPLATE_HOOK_FILES[@]}"; do
    mkdir -p "$setup_dest/$(dirname "$hf")"
    local hooks_src="$setup_src/$hf"
    local hooks_dest="$setup_dest/$hf"
    if [[ -f "$hooks_src" ]]; then
      if [[ -f "$hooks_dest" ]]; then
        echo "  KEEP: setup/$hf (operator-preserved)"
      else
        cp "$hooks_src" "$hooks_dest"
        echo "  OK:   setup/$hf"
      fi
    else
      echo "  WARN: template missing — $hooks_src (skipping)"
    fi
  done

  # Shebang-scan: walk the installed setup tree and chmod +x any file whose
  # first 2 bytes are '#!'. This replaces the hardcoded SETUP_TEMPLATE_EXEC_FILES[]
  # whitelist — the scan catches newly-added shebanged files automatically, without
  # requiring a manifest update. Null-delimited find avoids word-splitting on
  # filenames with spaces (F2 fix). Process substitution requires bash 4+ — gated
  # by the bash 4.3 admission guard at the top of this script.
  # Spec backlink: docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 7
  # Review: reviewer — null-delimited form prevents word-splitting on paths with spaces
  while IFS= read -r -d '' _ef; do
    head -c 2 "$_ef" 2>/dev/null | grep -q '^#!' && chmod +x "$_ef"
  done < <(find "$setup_dest" -type f -print0)
  echo ""

  # Install the OSS publish-repo pre-commit exec-bit drift gate.
  # Mirrors the meta-repo pattern (install-meta-repo-precommit-hook.sh) but
  # identity-guards to this OSS repo root, not $HOME/.claude.
  # Pass REPO_ROOT so the installer can canonical-compare without hardcoding
  # any machine-specific path. Offer-shape: prints and continues on foreign hook;
  # never blocks install on gate-installation failure.
  # Spec backlink: docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 5
  local _hook_installer="$REPO_ROOT/coordinator/bin/install-publish-repo-precommit-hook.sh"
  # Review: reviewer — avoid TOCTOU between -x check and bash call; invoke directly
  # with || true so a missing or non-executable file is silently swallowed rather
  # than aborting install. The gate installer is idempotent and offer-shape (exit 0
  # on all skip paths), so direct invocation is safe.
  echo "Installing OSS exec-bit pre-commit gate..."
  bash "$_hook_installer" "$REPO_ROOT" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Bin essentials delivery
# ---------------------------------------------------------------------------
#
# Delivers a minimal set of bin/ scripts that the plugin's hooks.json
# references from ~/.claude/bin/. The full bin/ family is delivered by
# install-substrate.sh (Phase 3 of /setup), but these specific scripts
# are needed at first SessionStart — before /setup has run — because
# hooks.json fires immediately after the plugin loads.

deliver_bin_essentials() {
  local bin_src="$PLUGINS_TARGET/coordinator/templates/bin"
  local bin_dst="$CLAUDE_DIR/bin"

  if [[ ! -d "$bin_src" ]]; then
    echo "  SKIP: bin essentials (coordinator templates/bin/ not present)"
    return 0
  fi

  mkdir -p "$bin_dst"
  echo "Delivering ~/.claude/bin/ essentials..."

  # platform-localize.sh — SessionStart hook for cross-machine portability
  local f="platform-localize.sh"
  if [[ -f "$bin_src/$f" ]]; then
    if [[ ! -f "$bin_dst/$f" ]]; then
      cp "$bin_src/$f" "$bin_dst/$f"
      chmod +x "$bin_dst/$f"
      echo "  OK:   bin/$f"
    else
      chmod +x "$bin_dst/$f" 2>/dev/null || true
      echo "  KEEP: bin/$f (operator-preserved)"
    fi
  fi

  # settings-manifest.md — companion doc for settings.json portability
  local manifest_src="$PLUGINS_TARGET/coordinator/templates/settings-manifest.md"
  local manifest_dst="$CLAUDE_DIR/settings-manifest.md"
  if [[ -f "$manifest_src" ]]; then
    if [[ ! -f "$manifest_dst" ]]; then
      cp "$manifest_src" "$manifest_dst"
      echo "  OK:   settings-manifest.md"
    else
      echo "  KEEP: settings-manifest.md (operator-preserved)"
    fi
  fi
  echo ""
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
# Install-side version sentinel
# ---------------------------------------------------------------------------
#
# Plants $CLAUDE_DIR/plugins/coordinator-claude/version.txt (40-hex SHA, LF)
# immediately after copy_plugins so the /coordinator-update skill's divergence
# classifier has a baseline anchor for the SHA this install was installed from.
#
# Resolution: $PLUGINS_TARGET/coordinator/bin/install-sentinel-write is
# delivered as part of the coordinator plugin tree copy_plugins() just laid
# down. Invoke it via $PYTHON (resolved in check_prerequisites).
#
# Posture: WARN-don't-FAIL — a missing writer binary means the install
# succeeded; the sentinel is only the update skill's baseline anchor (advisory).
# Never exit non-zero on sentinel failure.
write_install_sentinel() {
  local writer="$PLUGINS_TARGET/coordinator/bin/install-sentinel-write"
  if [[ ! -f "$writer" ]]; then
    echo "WARNING: install-sentinel-write not found at $writer — version.txt NOT written."
    echo "         The coordinator install succeeded; re-run the installer to plant the"
    echo "         update baseline, or run /coordinator-update for the first time without it."
    return 0
  fi
  if "$PYTHON" "$writer" --path "$PLUGINS_TARGET" --source "$REPO_ROOT"; then
    echo "  OK: version.txt (update baseline) written at $PLUGINS_TARGET/version.txt"
  else
    echo "WARNING: install-sentinel-write exited non-zero — version.txt may be incomplete."
    echo "         The coordinator install succeeded; /coordinator-update will degrade"
    echo "         to baseline-free two-way mode on first run."
  fi
  echo ""
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

  # Consumer-side presence check for the OSS-only coordinator-update skill.
  # This skill is injected into the publish tree by the publish-side hook
  # (20-inject-oss-only-skills.sh) but is NOT present in the source-is-live
  # meta-repo tree. A partial copy, permission error, or interrupted install
  # can silently drop it — the user gets an inert /coordinator-update verb
  # with no diagnostic. Fail loud here so the installer surfaces the gap.
  local coordinator_update_skill="$PLUGINS_TARGET/coordinator/skills/coordinator-update"
  if [[ -d "$coordinator_update_skill" ]]; then
    echo "  OK: coordinator-update skill present"
  else
    echo "  FAIL: coordinator-update skill missing — $coordinator_update_skill"
    echo "        Re-run the installer to restore it."
    errors=$((errors + 1))
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

  if [[ "$CODEX_INSTALLED" == true ]]; then
    echo "codex-review-gate skill: installed"
    echo "  Requires openai/codex-plugin-cc + 'codex login' to actually run."
  else
    echo "codex-review-gate skill: skipped (re-run with --enable-codex to add)"
  fi
  echo ""

  # Update baseline sentinel note.
  local sentinel="$PLUGINS_TARGET/version.txt"
  if [[ -f "$sentinel" ]]; then
    echo "Update baseline: version.txt written at $sentinel"
    echo "  Run /coordinator-update to check for upstream changes later."
  else
    echo "Update baseline: version.txt NOT written (writer missing — re-run installer to plant it)."
  fi
  echo ""

  echo "Next step: restart Claude Code, then run /workstream-start to verify plugins loaded."
  echo ""

  echo "Hit a rough edge getting this working? Patch it — then send the fix back."
  echo "A script-only install was whack-a-mole across machines, so we lean on agents"
  echo "and on you: open a PR, file an issue, or paste a rough note. Don't polish it —"
  echo "what you changed and why is worth more to us than clean code. Details:"
  echo "  https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md"
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

  # Run conditional prereqs gate now that selection is known.
  check_notebooklm_prereqs

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
  deliver_setup_templates
  deliver_bin_essentials
  write_install_sentinel

  echo "Registering JSON config files..."
  register_marketplace
  register_installed_plugins
  register_settings
  echo ""

  validate_installation
  print_summary
  prompt_naming_addon
}

main
