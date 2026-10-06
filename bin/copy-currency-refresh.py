"""copy-currency-refresh -- off-boot recompute of the git-derived `Copies:` answers.

The boot banner (`project-orientation.py::copies_banner`) only reads
`<settings_home>/machine-local/copy-currency.json`. This CLI is the one place that
computes what the cache holds: the engine-mirror `publish_lag` answer and the
plugin-mirror commit times and hooks.json registration parity, each keyed by the HEADs
read in-process before computing. It stores refresh inputs only, never a time-based
verdict. Spawns: 2 inside `publish_lag`, 2 for the plugin-mirror commit times.

Usage: copy-currency-refresh.py [--cache PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

# Writes the machine-local copies cache under settings home, outside the tracked tree.
GENERATES = []

#: Pointer files naming the doctrine checkout. Trap: the engine mirror ships
#: coordinator/bin without coordinator/hooks, so self-location alone fails there.
_ROOT_POINTERS = (
    Path.home() / ".claude" / ".coordinator-content-root",
    Path.home() / ".coordinator-claude-settings" / ".coordinator-content-root",
)


def resolve_scripts_dir() -> Path:
    """hooks/scripts holding project-orientation.py: plugin-root env, self-location, then pointers."""
    candidates = []
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        candidates.append(Path(env_root) / "hooks" / "scripts")
    candidates.append(Path(__file__).resolve().parents[1] / "hooks" / "scripts")
    for pointer in _ROOT_POINTERS:
        try:
            root = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if root:
            candidates.append(Path(root) / "coordinator" / "hooks" / "scripts")
    for candidate in candidates:
        if (candidate / "project-orientation.py").is_file():
            return candidate
    return candidates[1]


_SCRIPTS_DIR = resolve_scripts_dir()


def load_orientation():
    """Load project-orientation.py by path; its cache-key and resolution helpers are the boot path's."""
    spec = importlib.util.spec_from_file_location(
        "project_orientation_for_refresh", _SCRIPTS_DIR / "project-orientation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def find_import_origin() -> dict:
    """Where `coordinator_core` imports from under this interpreter; the spec is located, never imported."""
    try:
        spec = importlib.util.find_spec("coordinator_core")
    except (ImportError, ValueError) as exc:
        return {"error": f"coordinator_core spec lookup failed ({type(exc).__name__}: {exc})", "executable": sys.executable}
    locations = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
    if not locations and spec is not None and spec.origin:
        locations = [str(Path(spec.origin).parent)]
    if not locations:
        return {"error": "coordinator_core not found on this interpreter's import path", "executable": sys.executable}
    return {"package_dir": str(locations[0]), "executable": sys.executable}


def _engine_entry(po, ctx, publish_lag: Optional[Callable], now_epoch: float, origin: Optional[Callable] = None) -> dict:
    cc = po._copies_mod("_copy_currency")
    eml = po._copies_mod("_copy_leg_engine_mirror")
    key = po.copies_engine_key(ctx)
    entry: dict = {"key": key, "computed_at": now_epoch, "lag": None}
    # `authoring_root` is the contract name: the publish transform renames codename identifiers.
    authoring_root = getattr(ctx, "authoring_root", None)
    if ctx.live_tree or not authoring_root or not ctx.engine_root or not key["stamp"]:
        return entry
    entry["import_origin"] = (origin or find_import_origin)()
    try:
        fn = publish_lag
        if fn is None:
            fn, reason = cc.resolve_engine_symbol(eml.PUBLISH_LAG_SYMBOL, ctx.engine_root)
            if fn is None:
                entry["error"] = reason
                return entry
        lag = fn(Path(ctx.engine_root), Path(authoring_root))
        if lag is not None:
            entry["lag"] = {
                "engine_commits_behind": getattr(lag, "engine_commits_behind", None),
                "stamp_sha": getattr(lag, "stamp_sha", "") or "",
            }
    except Exception as exc:  # noqa: BLE001 -- recorded; the boot renders it could-not-check
        entry["error"] = f"{type(exc).__name__}: {exc}"
    return entry


def _plugin_entry(po, ctx, commit_times: Optional[Callable], now_epoch: float) -> Optional[dict]:
    pml = po._copies_mod("_copy_leg_plugin_mirror")
    source, mirror, reason = po.resolve_plugin_pair(ctx)
    if reason:
        return None
    entry: dict = {
        "key": po.copies_plugin_key(source, mirror),
        "computed_at": now_epoch,
        "times": None,
        "parity": None,
    }
    try:
        times = (commit_times or pml.git_commit_times)(source, mirror)
        if times is None:
            entry["times_error"] = "commit times unavailable"
        else:
            entry["times"] = [int(times[0]), int(times[1])]
    except Exception as exc:  # noqa: BLE001
        entry["times_error"] = f"{type(exc).__name__}: {exc}"
    try:
        parity = pml.check_registration_parity(source, mirror)
        entry["parity"] = {
            "dropped": list(parity.dropped),
            "missing": list(parity.missing),
            "unverifiable": list(parity.unverifiable),
        }
    except Exception as exc:  # noqa: BLE001
        entry["parity_error"] = f"registration parity not computed ({type(exc).__name__}: {exc})"
    return entry


def compute_cache(
    po,
    ctx,
    publish_lag: Optional[Callable] = None,
    commit_times: Optional[Callable] = None,
    now_epoch: Optional[float] = None,
    import_origin: Optional[Callable] = None,
) -> dict:
    """The full cache document. HEADs are read before the git work so a commit landing
    mid-refresh makes the next boot a miss, never a false hit."""
    now_epoch = time.time() if now_epoch is None else now_epoch
    eml = po._copies_mod("_copy_leg_engine_mirror")
    pml = po._copies_mod("_copy_leg_plugin_mirror")
    cache: dict = {"schema": po._COPIES_CACHE_SCHEMA, eml.COPY: _engine_entry(po, ctx, publish_lag, now_epoch, import_origin)}
    plugin = _plugin_entry(po, ctx, commit_times, now_epoch)
    if plugin is not None:
        cache[pml.COPY] = plugin
    return cache


def write_cache_atomic(path: Path, data: dict) -> None:
    """Write via a sibling temp file and `os.replace`; a failed write leaves the prior cache intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def refresh(
    po=None,
    ctx=None,
    cache_path: Optional[Path] = None,
    publish_lag: Optional[Callable] = None,
    commit_times: Optional[Callable] = None,
    now_epoch: Optional[float] = None,
    import_origin: Optional[Callable] = None,
) -> dict:
    """Recompute and write the cache; returns the document written."""
    po = po or load_orientation()
    ctx = ctx or po.default_copies_context()
    data = compute_cache(po, ctx, publish_lag, commit_times, now_epoch, import_origin)
    write_cache_atomic(cache_path or po.copies_cache_path(), data)
    return data


def _summary(data: dict, path: Path) -> str:
    parts = []
    for copy, entry in data.items():
        if not isinstance(entry, dict):
            continue
        bad = entry.get("error") or entry.get("times_error") or entry.get("parity_error")
        parts.append(f"{copy} {'could-not-compute: ' + str(bad) if bad else 'ok'}")
    return f"copy-currency-refresh: wrote {path} ({'; '.join(parts)})"


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", help="cache file to write (default: the boot path's)")
    args = parser.parse_args(argv)
    po = load_orientation()
    path = Path(args.cache) if args.cache else po.copies_cache_path()
    try:
        data = refresh(po, cache_path=path)
    except Exception as exc:  # noqa: BLE001
        print(f"copy-currency-refresh: failed ({type(exc).__name__}: {exc}); prior cache left intact", file=sys.stderr)
        return 1
    print(_summary(data, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
