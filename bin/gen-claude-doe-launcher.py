# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
gen-claude-doe-launcher.py — CLI trampoline over claude-klabauter
coordinator_core.ops.gen_claude_doe_launcher.

Renders the Windows-native claude-doe launcher(s) (claude-doe.cmd, claude-doe.ps1)
from the coordinator templates into ${CLAUDE_HOME:-$HOME}/.local/bin/. Windows-only:
a clean no-op (exit 0) on macOS/Linux. See the claude-klabauter module's own docstring for the
full design rationale (Git-for-Windows PATH gap, dynamic-root-discovery templates,
idempotent atomic writes, --check-only dry-run safety).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Usage:
  gen-claude-doe-launcher.py              -- install/refresh the launcher(s)
  gen-claude-doe-launcher.py --check-only -- validate without mutating live files
  gen-claude-doe-launcher.py --template-dir <path>  -- override template source dir

Exit codes: 0 on success (including the non-Windows no-op skip); 1 on any failure
(unknown argument, missing/invalid --template-dir, template not found, or a
engine-root/import resolution failure) -- this is an install-step gate
(install-maximalist.py wraps it in `run_required`), so failures must block the
install rather than being swallowed, unlike the never-block auto-push shape.

Port of: coordinator/bin/gen-claude-doe-launcher.py (bash body retired on cutover;
see git log)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys

def _default_template_dir() -> str:
    """Mirror the bash oracle's `${_script_dir}/../templates/bin` default.

    Resolved via `coordinator_data_root.data_root()`'s co-located/DoE-resident
    two-rung chain, not a bare `__file__`-relative walk: the 2026-07-22
    executable-surface migration moved this trampoline into claude-klabauter
    while `templates/` stayed in DoE-claude (DR-047 contract/engine split), so
    a `${script_dir}/../templates` walk no longer lands anywhere.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_data_root import data_root

    return os.path.join(str(data_root("templates")), "bin")


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the shared
    in-process runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so the launcher
    files it declares become a session scope-touch claim. Without that, the
    launchers this generator writes are orphans at the `scoped_git_commit`
    sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"gen-claude-doe-launcher.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except ImportError as exc:
        print(
            "gen-claude-doe-launcher.py: coordinator_core.cli_entry not importable: "
            f"{exc}",
            file=sys.stderr,
        )
        return 1

    argv = (sys.argv[1:] if argv is None else argv)
    if "--template-dir" not in argv and "-h" not in argv and "--help" not in argv:
        try:
            argv = argv + ["--template-dir", _default_template_dir()]
        except RuntimeError as exc:
            print(
                f"gen-claude-doe-launcher.py: could not resolve a default "
                f"--template-dir: {exc}",
                file=sys.stderr,
            )
            return 1

    try:
        code = run_op_main("coordinator_core.ops.gen_claude_doe_launcher", argv)
    except ImportError as exc:
        print(
            "gen-claude-doe-launcher.py: "
            f"coordinator_core.ops.gen_claude_doe_launcher not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
