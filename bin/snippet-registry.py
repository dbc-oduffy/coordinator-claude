from __future__ import annotations

import os
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
_REPO_ROOT = os.path.dirname(os.path.dirname(_BIN_DIR))

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put `_REPO_ROOT` on `sys.path` so `machine_local_resolve.py`'s own
    module-level `coordinator_core.win_portability` import resolves, AND
    bootstrap `coordinator/bin/lib` onto `sys.path` via `import lib`.
    Idempotent.

    What moved, and what did NOT: the `_REPO_ROOT` single-line mutation used
    to run at MODULE scope, which made every import of this file mutate the
    `sys.path` of a warm server ~50 sessions share. That line is preserved
    exactly; only the trigger moved.

    The `import lib` call is NOT that carried-over mutation -- it is a fix
    folded in here (2026-08-29 review-finding sweep, Finding 4). This
    function used to insert `_REPO_ROOT` only, which reads as protection for
    `_resolve_plugin_root()`'s `from coordinator_data_root import data_root`
    below while providing none: `coordinator_data_root` lives under
    `coordinator/bin/lib/`, not the repo root, so that import resolved only
    because `main()`'s own later `import lib` call happened to run first on
    every real invocation path. A mid-module entry into
    `_resolve_plugin_root()` that never reaches `main()` raised
    `ModuleNotFoundError` on `coordinator_data_root`.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    _BOOTSTRAP_DONE = True


def _resolve_plugin_root() -> Path:
    """Resolve the coordinator root consumer relative paths (e.g. "agents/...")
    resolve against — CLAUDE_PLUGIN_ROOT override always wins; otherwise the
    parent of the resolved snippets/ data dir (co-located or DoE-resident per
    `coordinator_data_root.data_root()`), since that parent IS the coordinator
    root under either layout.
    """
    _bootstrap_engine()
    from coordinator_data_root import data_root

    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env)
    return data_root("snippets").parent


def main(argv: "list[str] | None" = None) -> int:
    _bootstrap_engine()
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
    import coordinator_core  # noqa: F401

    from machine_local_resolve import resolve_machine_local_bin

    args = (sys.argv[1:] if argv is None else argv)
    subcommand = args[0] if args else ""

    if subcommand in ("--help", "-h"):
        print("Usage: snippet-registry <subcommand> [args]")
        print("  list-snippets")
        print("  list-consumers <snippet-name>")
        print("  list-for <consumer-path>")
        return 0

    claude_klabauter_root = require_dispatch_engine_on_path()
    try:
        from coordinator_core.snippet_sync import registry as reg
    except ImportError as exc:
        print(
            f"snippet-registry: coordinator_core.snippet_sync.registry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    plugin_root = _resolve_plugin_root()
    registry_toml = plugin_root / "snippets" / "registry.toml"
    machine_local_bin = resolve_machine_local_bin(script_dir)

    try:
        data = reg.load_registry(registry_toml)
    except reg.RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    if subcommand == "list-snippets":
        for name in reg.list_snippets(data):
            print(name)
        return 0

    if subcommand == "list-consumers":
        if len(args) < 2:
            print("Usage: snippet-registry list-consumers <snippet-name>", file=sys.stderr)
            return 1
        try:
            consumers = reg.resolve_consumers(
                data, args[1], plugin_root, machine_local_bin=machine_local_bin
            )
        except reg.RegistryError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        for path in consumers:
            print(str(path).replace(os.sep, "/"))
        return 0

    if subcommand == "list-for":
        if len(args) < 2:
            print("Usage: snippet-registry list-for <consumer-path>", file=sys.stderr)
            return 1
        for name in reg.list_for(data, args[1], plugin_root, machine_local_bin=machine_local_bin):
            print(name)
        return 0

    if subcommand == "":
        print("Usage: snippet-registry <subcommand> [args]", file=sys.stderr)
        print("  list-snippets", file=sys.stderr)
        print("  list-consumers <snippet-name>", file=sys.stderr)
        print("  list-for <consumer-path>", file=sys.stderr)
        return 1

    print(f"ERROR: snippet-registry: unknown subcommand '{subcommand}'", file=sys.stderr)
    print("  Known subcommands: list-snippets, list-consumers, list-for", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
