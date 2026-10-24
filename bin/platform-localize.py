"""platform-localize.py — door-eligible engine entrypoint for `platform-localize`.

The door resolves exactly `{engine_root}/coordinator/bin/<name>.py`; this file is
that name-aligned entrypoint over `coordinator_core.hooks.platform_localize.main`.
Distinct from `coordinator/templates/bin/platform-localize.py`, the installed
copy the retained `.cmd` leg uses.

`platform_localize.main` takes no flags, so `--help`/`-h` is answered here before
the implementation is imported; any other argument passes through unchanged.
Exit codes: 3 on a transport failure, otherwise the implementation's own code.
"""
from __future__ import annotations

import sys

_USAGE = "usage: platform-localize  (takes no flags; localizes settings.local.json for this machine)"


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.hooks.platform_localize import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args and args[0] in ("--help", "-h"):
        print(_USAGE)
        return 0
    try:
        op_main = _import_main()
    except (RuntimeError, ImportError) as exc:
        print(f"platform-localize.py: engine resolution failed: {exc}", file=sys.stderr)
        print("platform_localize: error (see stderr)")
        return 3
    return op_main(args)


if __name__ == "__main__":
    sys.exit(main())
