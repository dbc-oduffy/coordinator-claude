#!/usr/bin/env python3
"""general-work-root: resolve or create the machine-local general-work landing folder.

Verbs: `path`, `ensure` (creates the root, converges the coordinator-repo tree, commits only the
paths it seeded); `--json` emits {"root", "exists", "git"}. Exit 3 on a refused root (prints the
conflict and names the override key), exit 2 when the `_general_work` implementation is unresolvable.
Authored in claude-klabauter; DoE consumes it. `coordinator_core.install.general_work_ensure` loads this file
and calls `main(["ensure", "--json"])`.
"""
import argparse
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

_REGISTRY_KEY = "repos.coordinator_claude"


def _scripts_dirs() -> "Iterator[Path]":
    """Candidate dirs holding DoE's `_general_work.py`: the mirror-shaped sibling, then the registered coordinator-claude root."""
    here = Path(__file__).resolve().parent
    yield here.parent / "hooks" / "scripts"
    lib = str(here / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    from cc_invoke import place_engine_root_on_path

    place_engine_root_on_path(str(here.parent.parent))
    try:
        from coordinator_core import machine_resolver

        root = machine_resolver.registry_get(_REGISTRY_KEY)
    except Exception:
        root = None
    if root:
        yield Path(root) / "hooks" / "scripts"
        yield Path(root) / "coordinator" / "hooks" / "scripts"


def _load_general_work() -> "ModuleType | None":
    """Load `_general_work` with its hooks dir on `sys.path` (it imports siblings); None when unresolved."""
    for scripts in _scripts_dirs():
        target = scripts / "_general_work.py"
        if not target.is_file():
            continue
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        spec = importlib.util.spec_from_file_location("_general_work", target)
        module = importlib.util.module_from_spec(spec)
        sys.modules["_general_work"] = module
        spec.loader.exec_module(module)
        return module
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="general-work-root")
    ap.add_argument("verb", choices=("path", "ensure"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        general_work = _load_general_work()
    except Exception as exc:
        print(f"general-work-root: _general_work unloadable: {exc}", file=sys.stderr)
        return 2
    if general_work is None:
        print(
            f"general-work-root: _general_work unresolvable; register {_REGISTRY_KEY} to a coordinator-claude checkout",
            file=sys.stderr,
        )
        return 2
    try:
        root = general_work.ensure_root() if args.verb == "ensure" else general_work.resolve_root()
    except general_work.RootRefused as exc:
        print(
            f"general-work-root: refused: {exc.root} conflicts with {exc.conflict}; "
            f"set {general_work.KEY} to a folder outside every checkout",
            file=sys.stderr,
        )
        print(exc.conflict)
        return 3
    if args.json:
        print(json.dumps({"root": str(root), "exists": root.exists(), "git": (root / ".git").exists()}))
    else:
        print(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
