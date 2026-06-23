#!/usr/bin/env bash
# platform-localize.sh — SessionStart hook that localizes settings for this machine.
#
# ARCHITECTURE (see also: settings-manifest.md)
#
#   settings.json          (tracked)    — union of what ALL machines need
#   settings.local.json    (gitignored) — per-machine overrides (this hook writes it)
#   known_marketplaces.json (gitignored) — CC plugin discovery cache
#   registry.local.toml    (gitignored) — per-machine repo paths
#
# This hook writes settings.local.json to override what doesn't apply HERE:
#   - extraKnownMarketplaces with correct absolute paths for this filesystem
#   - enabledPlugins set to false for plugins whose infrastructure is absent
#   - known_marketplaces.json patched (CC reads this, not extraKnownMarketplaces — #51806)
#
# DETECTION SIGNAL: machine-local/registry.local.toml repo values.
# If a repo key is empty OR the path doesn't exist on disk, plugins
# depending on that repo are disabled.
# The plugin_infra_requirements dict in the Python block below is the
# canonical, executable mapping of plugin → required registry key.
# To gate a new plugin: add it there AND to settings-manifest.md.
#
# Idempotent: compares before writing — no disk churn if already correct.
# Non-blocking: <100ms typical (28ms measured on Apple M1).

set -euo pipefail
trap 'echo "[platform-localize] FAILED (exit $?)" >&2' ERR

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SETTINGS_LOCAL="$CLAUDE_HOME/settings.local.json"
KNOWN_MARKETPLACES="$CLAUDE_HOME/plugins/known_marketplaces.json"
PLUGINS_DIR="$CLAUDE_HOME/plugins"
REGISTRY_LOCAL="$CLAUDE_HOME/machine-local/registry.local.toml"

# ---------------------------------------------------------------------------
# Python resolver
# ---------------------------------------------------------------------------
PYTHON=""
if command -v python3 &>/dev/null; then PYTHON=python3
elif command -v python &>/dev/null; then PYTHON=python
fi
[[ -z "$PYTHON" ]] && exit 0

# ---------------------------------------------------------------------------
# Main logic in Python for JSON/TOML manipulation
# ---------------------------------------------------------------------------
"$PYTHON" - "$CLAUDE_HOME" "$PLUGINS_DIR" "$SETTINGS_LOCAL" "$KNOWN_MARKETPLACES" "$REGISTRY_LOCAL" <<'PYEOF'  # verify-no-console-flash: allow (install-time localize template; runs once at setup)
import sys, json, os, re, datetime

claude_home = sys.argv[1]
plugins_dir = sys.argv[2]
settings_local_path = sys.argv[3]
known_mp_path = sys.argv[4]
registry_local_path = sys.argv[5]

# --- Read registry.local.toml ---
# Simple line parser: only handles the "key" = "value" format used by the
# coordinator's registry files. Bare values (schema = 1), arrays, and
# tables are intentionally skipped — they're not repo-path entries.
# If Python 3.11+ is available, tomllib would be cleaner, but we avoid
# the version dependency for a SessionStart hook that must run everywhere.
registry = {}
if os.path.isfile(registry_local_path):
    try:
        with open(registry_local_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("["):
                    continue
                m = re.match(r'^"?([^"=]+)"?\s*=\s*"([^"]*)"', line)
                if m:
                    registry[m.group(1).strip()] = m.group(2).strip()
    except OSError:
        pass

def repo_available(key):
    """Check if a registry repo key points to a directory that exists on disk."""
    val = registry.get(key, "").strip()
    return bool(val and os.path.isdir(val))

# --- Discover marketplace directories under ~/.claude/plugins/ ---
# Scans immediate children of plugins/ for .claude-plugin/ manifests.
# Does NOT recurse into plugins/marketplaces/ (those are URL-sourced
# clones handled by extraKnownMarketplaces URL entries in settings.json).
marketplace_dirs = {}
if os.path.isdir(plugins_dir):
    for entry in sorted(os.listdir(plugins_dir)):
        if os.path.isdir(os.path.join(plugins_dir, entry, ".claude-plugin")):
            marketplace_dirs[entry] = os.path.join(plugins_dir, entry)

# External marketplace repos live outside ~/.claude/plugins/ and are
# discovered via registry.local.toml repo keys.
#
# EXTENSION POINT: if adding a gated plugin whose marketplace lives at
# an external path, add a row here AND in plugin_infra_requirements below.
# See the four-step authoring checklist at plugin_infra_requirements.
external_marketplaces = {
    # Example: "my-addon": "repos.my_addon",
}
for mp_name, reg_key in external_marketplaces.items():
    repo_path = registry.get(reg_key, "").strip()
    if repo_path and os.path.isdir(repo_path):
        marketplace_dirs[mp_name] = repo_path

# --- Read existing settings.local.json to preserve manual entries ---
existing_local = {}
if os.path.isfile(settings_local_path):
    try:
        with open(settings_local_path) as f:
            existing_local = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass

local_settings = {}

# --- extraKnownMarketplaces: correct absolute paths for this machine ---
extra_mp = {}
for mp_name, mp_path in sorted(marketplace_dirs.items()):
    extra_mp[mp_name] = {"source": {"source": "directory", "path": mp_path}}
if extra_mp:
    local_settings["extraKnownMarketplaces"] = extra_mp

# --- enabledPlugins: disable plugins whose infrastructure isn't here ---
# CANONICAL MAPPING: plugin key -> registry.local.toml key that must
# resolve to an existing directory for the plugin to be useful.
#
# To add a gated plugin:
#   1. Add the row here
#   2. If the marketplace is external, also add to external_marketplaces above
#   3. Add the registry key to machine-local/registry.toml (tracked, declares it)
#   4. Add a row to settings-manifest.md § Plugin Infrastructure Requirements
#   5. On machines with the infra: `machine-local set <key> <path>`
#
# Plugins NOT listed here are universally available (no gating).
plugin_infra_requirements = {
    # Example: "my-plugin@my-marketplace": "repos.my_repo",
}

plugin_overrides = {}
for plugin_key, reg_key in plugin_infra_requirements.items():
    if not repo_available(reg_key):
        plugin_overrides[plugin_key] = False

# Preserve any manual enabledPlugins entries from existing settings.local.json
existing_plugins = existing_local.get("enabledPlugins", {})
for k, v in existing_plugins.items():
    if k not in plugin_overrides:
        plugin_overrides[k] = v

if plugin_overrides:
    local_settings["enabledPlugins"] = plugin_overrides

# --- Preserve any other manual entries the user added ---
for k, v in existing_local.items():
    if k not in local_settings and k not in ("extraKnownMarketplaces", "enabledPlugins"):
        local_settings[k] = v

# --- Atomic write helper ---
def atomic_write(path, content):
    """Write content to path atomically via tmp + os.replace."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(content)
    os.replace(tmp, path)

# --- Write settings.local.json only if changed ---
new_content = json.dumps(local_settings, indent=2) + "\n"
existing_content = ""
if os.path.isfile(settings_local_path):
    try:
        with open(settings_local_path) as f:
            existing_content = f.read()
    except OSError:
        pass

if new_content != existing_content:
    atomic_write(settings_local_path, new_content)

# --- Patch known_marketplaces.json (load-bearing for discovery, bug #51806) ---
existing_km = {}
if os.path.isfile(known_mp_path):
    try:
        with open(known_mp_path) as f:
            existing_km = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass

changed = False

# Update/add entries for discovered marketplaces.
# Required-field invariant: every entry MUST carry `lastUpdated` (ISO 8601 string) —
# Claude Code's known_marketplaces schema rejects entries without it and the
# `/plugin` command refuses to enumerate. See validate-json-schemas.py.
now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
for mp_name, mp_path in marketplace_dirs.items():
    entry = existing_km.get(mp_name, {})
    current_src = entry.get("source", {})
    current_path = current_src.get("path", "") if isinstance(current_src, dict) else ""
    has_last_updated = isinstance(entry.get("lastUpdated"), str)
    if current_path != mp_path or entry.get("installLocation", "") != mp_path or not has_last_updated:
        existing_km[mp_name] = {
            "source": {"source": "directory", "path": mp_path},
            "installLocation": mp_path,
            "lastUpdated": entry.get("lastUpdated") if has_last_updated else now_iso,
        }
        changed = True

# Backfill `lastUpdated` on any pre-existing entries the hook doesn't own
# (URL-sourced git/github entries written by Claude Code itself). Older CC
# versions wrote these without the field; the new schema requires it.
for mp_name, entry in list(existing_km.items()):
    if not isinstance(entry, dict):
        continue
    if not isinstance(entry.get("lastUpdated"), str):
        entry["lastUpdated"] = now_iso
        existing_km[mp_name] = entry
        changed = True

# --- Self-heal coordinator-claude's own marketplace registration ---
# `claude plugin marketplace add <clone-path>` registers a *directory* source
# that Claude Code resolves from that path on every load and never copies into
# ~/.claude. Move or delete the clone and the installed plugins orphan
# (/reload-plugins -> 0 plugins) even though the payload is still cached. When we
# detect exactly that broken state — coordinator-claude registered as a
# directory source whose path no longer exists, while the plugin payload is
# still cached under ~/.claude/plugins/cache/coordinator-claude/ — rewrite the
# entry to the public GitHub source so Claude Code re-caches it self-containedly.
# Conservative by design: a directory source whose path STILL EXISTS is left
# untouched (it may be a contributor's intentional dev-loop install, where the
# clone IS the runtime source on purpose — see CONTRIBUTING.md), and so is any
# source already pointing inside ~/.claude.
# Ordering: runs AFTER the lastUpdated backfill loop above, so the entry written
# here carries lastUpdated directly and needs no backfill pass.
COORDINATOR_MP = "coordinator-claude"
COORDINATOR_GITHUB_REPO = "dbc-oduffy/coordinator-claude"
coord_entry = existing_km.get(COORDINATOR_MP)
if isinstance(coord_entry, dict):
    coord_src = coord_entry.get("source", {})
    if isinstance(coord_src, dict) and coord_src.get("source") == "directory":
        coord_path = coord_src.get("path", "")
        cache_present = os.path.isdir(os.path.join(plugins_dir, "cache", COORDINATOR_MP))
        claude_home_prefix = os.path.abspath(claude_home) + os.sep
        path_under_claude_home = bool(coord_path) and \
            os.path.abspath(coord_path).startswith(claude_home_prefix)
        if coord_path and not os.path.exists(coord_path) \
                and cache_present and not path_under_claude_home:
            # installLocation = the marketplaces/ cache path Claude Code itself
            # writes for a github source (and `validate-json-schemas.py` requires a
            # string installLocation on EVERY entry, github included). CC populates
            # the dir on resolve — the same shape `claude plugin marketplace add
            # <github>` produces.
            existing_km[COORDINATOR_MP] = {
                "source": {"source": "github", "repo": COORDINATOR_GITHUB_REPO},
                "installLocation": os.path.join(plugins_dir, "marketplaces", COORDINATOR_MP),
                "lastUpdated": now_iso,
            }
            changed = True
            sys.stderr.write(
                "[platform-localize] repaired coordinator-claude marketplace: "
                "clone-bound directory source '%s' is missing; rewrote to GitHub "
                "source (run /reload-plugins to reload)\n" % coord_path
            )

# Remove stale directory-source entries for marketplaces no longer on disk.
# Only touch entries this hook owns (source.source == "directory"); leave
# URL-sourced entries (git, github) untouched. coordinator-claude is excluded —
# its disposition is owned by the self-heal block above (repair, never blanket
# delete), so a CLI/clone install is never silently dropped here.
stale_keys = []
for mp_name, entry in existing_km.items():
    if mp_name == COORDINATOR_MP:
        continue
    src = entry.get("source", {})
    if isinstance(src, dict) and src.get("source") == "directory":
        if mp_name not in marketplace_dirs:
            stale_keys.append(mp_name)
for k in stale_keys:
    del existing_km[k]
    changed = True

if changed:
    atomic_write(known_mp_path, json.dumps(existing_km, indent=2) + "\n")

PYEOF
