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
        rest = raw_key[len(prefix):]
        parts = rest.split(".", 1)
        if len(parts) != 2:
            continue
        plugin_name, field = parts
        mirrors.setdefault(plugin_name, {})
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
