"""lib/read_mirrors.py — plugin.mirrors registry parser.

Port of: read-mirrors.sh (DoE 721a71f4, 2026-07-21). Single source of truth
for parsing plugin.mirrors entries out of a machine-local registry TOML.

Spec backlink: docs/plans/2026-05-28-reverse-drift-gate-meta-repo-coverage.md §Chunk 3a
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E3-c)
Extracted from: check-plugin-drift.py::_read_all_mirrors (pre-extraction bash lib)

Zero-callers note (chunk E3-c): both former consumers named in the retired
bash version's docstring (check-plugin-drift.py, list-reverse-drift-cmds.py)
have since migrated to claude-klabauter's coordinator_core.plugin_health.drift /
coordinator_core.ops.list_reverse_drift_cmds and no longer invoke this file —
confirmed on disk 2026-07-21 (neither imports/subprocess-calls this module
or _read_all_mirrors). This module carries the retired bash version's exact
parsing contract forward for any future direct caller; it is not wired into
either current drift gate.

Negative-spec:
  - Does NOT resolve the registry path — caller passes it as an argument.
  - Does NOT filter by propagation_mode — emits every entry; caller filters.
"""
from __future__ import annotations

import pathlib
import sys

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]


def read_all_mirrors(registry_path: str) -> list[dict[str, str]]:
    """Returns a list of mirror-entry dicts (keys: plugin_name, source_path,
    live_path, track_ref, dist_name, propagation_mode, reverse_drift_cmd).
    Empty list when the registry is absent or has no plugin.mirrors entries —
    mirrors the bash oracle's NO_MIRRORS/exit-0 degrade.
    """
    path = pathlib.Path(registry_path)
    if not path.exists():
        return []

    data = tomllib.loads(path.read_text(encoding="utf-8"))

    # Build the mirrors dict from two sources:
    # 1. Nested table form: [plugin.mirrors.<name>] entries.
    # 2. Flat dotted-key form: "plugin.mirrors.<name>.<field>" = "..." —
    #    written by `machine-local set` (flat string keys, not TOML tables).
    # Both forms are valid registry writes; both must be visible to the probe.
    mirrors: dict[str, dict[str, str]] = {}

    nested = data.get("plugin", {}).get("mirrors", {})
    if isinstance(nested, dict):
        for plugin_name, entry in nested.items():
            if isinstance(entry, dict):
                mirrors[plugin_name] = dict(entry)

    prefix = "plugin.mirrors."
    for raw_key, raw_val in data.items():
        if not isinstance(raw_key, str) or not raw_key.startswith(prefix):
            continue
        rest = raw_key[len(prefix):]  # e.g. "example-game-repo.propagation_mode"
        parts = rest.split(".", 1)
        if len(parts) != 2:
            continue
        plugin_name, field = parts
        mirrors.setdefault(plugin_name, {})
        # Only set if not already present from the nested-table form (nested wins).
        if field not in mirrors[plugin_name]:
            mirrors[plugin_name][field] = raw_val

    results: list[dict[str, str]] = []
    for plugin_name, entry in mirrors.items():
        results.append(
            {
                "plugin_name": plugin_name,
                "source_path": entry.get("source_path", ""),
                "live_path": entry.get("live_path", ""),
                "track_ref": entry.get("track_ref", "origin/main"),
                "dist_name": entry.get("dist_name", plugin_name.replace("-", "_")),
                "propagation_mode": entry.get("propagation_mode", ""),
                "reverse_drift_cmd": entry.get("reverse_drift_cmd", ""),
            }
        )
    return results


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: read_mirrors.py <registry-path>", file=sys.stderr)
        return 2

    try:
        entries = read_all_mirrors(argv[1])
    except Exception as exc:  # noqa: BLE001 - mirrors bash oracle's catch-all
        print(f"ERROR: failed to parse registry: {exc}", file=sys.stderr)
        return 2

    if not entries:
        print("NO_MIRRORS")
        return 0

    for e in entries:
        print(
            "|".join(
                (
                    e["plugin_name"],
                    e["source_path"],
                    e["live_path"],
                    e["track_ref"],
                    e["dist_name"],
                    e["propagation_mode"],
                    e["reverse_drift_cmd"],
                )
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
