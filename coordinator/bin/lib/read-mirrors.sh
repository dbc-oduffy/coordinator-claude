#!/usr/bin/env bash
# bin/lib/read-mirrors.sh — sourceable plugin.mirrors registry parser.
#
# Purpose: single source of truth for parsing plugin.mirrors entries out of a
# machine-local registry TOML. Defines _read_all_mirrors(); sourced by both
# check-plugin-drift.sh (forward-drift gate) and list-reverse-drift-cmds.sh
# (reverse-drift gate reader) so the nested-and-flat-key parsing logic lives in
# exactly one place.
#
# Spec backlink: docs/plans/2026-05-28-reverse-drift-gate-meta-repo-coverage.md §Chunk 3a
# Extracted from: check-plugin-drift.sh::_read_all_mirrors (lines 61-123, pre-extraction)
#
# Negative-spec:
#   - Does NOT resolve the registry path — caller passes it as $1.
#   - Prefers the caller-exported $PYTHON; falls back to `python3` when unset.
#     (Both shipping callers export $PYTHON before sourcing, so the fallback is
#     a safety net, not the normal path.)
#   - Does NOT filter by propagation_mode — emits every entry; caller filters.

# Emits one pipe-delimited line per plugin.mirrors entry:
#   <plugin_name>|<source_path>|<live_path>|<track_ref>|<dist_name>|<prop_mode>|<reverse_drift_cmd>
# Pipe delimiter (not tab): empty fields must survive `IFS='|' read`. Tab is
# IFS-whitespace and would collapse empty fields, shifting columns.
# Prints "NO_MIRRORS" and returns 0 when the registry has no plugin.mirrors.
_read_all_mirrors() {
    local registry_path="$1"
    bash "$(dirname "${BASH_SOURCE[0]}")/../../lib/spawn-hidden.sh" --stdin-mode=safe "${PYTHON:-python3}" - "$registry_path" <<'PYEOF' | tr -d '\r'
import sys, pathlib
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("ERROR: tomllib/tomli not available", file=sys.stderr)
        sys.exit(2)
registry_path = pathlib.Path(sys.argv[1])
if not registry_path.exists():
    sys.exit(0)
try:
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"ERROR: failed to parse registry: {e}", file=sys.stderr)
    sys.exit(2)

# Build the mirrors dict from two sources:
# 1. Nested table form: [plugin.mirrors.<name>] entries (data["plugin"]["mirrors"])
# 2. Flat dotted-key form: "plugin.mirrors.<name>.<field>" = "..." top-level keys
#    written by `machine-local set` (which uses flat string keys, not TOML tables).
# Both forms are valid registry writes; both must be visible to the probe.
mirrors = {}
# Source 1: nested tables (coordinator-claude, project-rag style).
nested = data.get("plugin", {}).get("mirrors", {})
if isinstance(nested, dict):
    for plugin_name, entry in nested.items():
        if isinstance(entry, dict):
            mirrors[plugin_name] = dict(entry)

# Source 2: flat dotted-key form (`"plugin.mirrors.<name>.<field>" = "..."`) —
# emitted by `machine-local set` which writes flat string keys.
PREFIX = "plugin.mirrors."
for raw_key, raw_val in data.items():
    if not isinstance(raw_key, str) or not raw_key.startswith(PREFIX):
        continue
    rest = raw_key[len(PREFIX):]  # e.g. "holodeck.propagation_mode"
    parts = rest.split(".", 1)
    if len(parts) != 2:
        continue
    plugin_name, field = parts
    if plugin_name not in mirrors:
        mirrors[plugin_name] = {}
    # Only set if not already present from the nested-table form (nested wins).
    if field not in mirrors[plugin_name]:
        mirrors[plugin_name][field] = raw_val

if not mirrors:
    print("NO_MIRRORS")
    sys.exit(0)
for plugin_name, entry in mirrors.items():
    prop_mode   = entry.get("propagation_mode", "")
    source_path = entry.get("source_path", "")
    live_path   = entry.get("live_path", "")
    track_ref   = entry.get("track_ref", "origin/main")
    dist_name   = entry.get("dist_name", plugin_name.replace("-", "_"))
    rev_cmd     = entry.get("reverse_drift_cmd", "")
    print(f"{plugin_name}|{source_path}|{live_path}|{track_ref}|{dist_name}|{prop_mode}|{rev_cmd}")
PYEOF
}
