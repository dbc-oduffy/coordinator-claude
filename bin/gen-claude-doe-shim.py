# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# Finish-strangler port (BIG_PORT): the bash implementation (renders the claude()

from __future__ import annotations

import sys

def _default_template_path(shell_family: str = "bash") -> str:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_data_root import data_file

    stem = "claude-doe-shim.ps1.tmpl" if shell_family == "powershell" else "claude-doe-shim.sh.tmpl"
    return str(data_file("templates", "shell", stem))


def _shell_family_from_argv(argv: list[str]) -> str:
    for i, arg in enumerate(argv):
        if arg == "--shell" and i + 1 < len(argv):
            return argv[i + 1]
    from coordinator_core.ops.gen_claude_doe_shim import _default_shell_family

    return _default_shell_family()


def _import_runner():
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
            f"gen-claude-doe-shim.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 2
    except ImportError as exc:
        print(
            "gen-claude-doe-shim.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    argv = (sys.argv[1:] if argv is None else argv)
    if "--template" not in argv and "-h" not in argv and "--help" not in argv:
        try:
            argv = argv + ["--template", _default_template_path(_shell_family_from_argv(argv))]
        except RuntimeError as exc:
            print(
                f"gen-claude-doe-shim.py: could not resolve a default "
                f"--template: {exc}",
                file=sys.stderr,
            )
            return 1

    try:
        code = run_op_main("coordinator_core.ops.gen_claude_doe_shim", argv)
    except ImportError as exc:
        print(
            "gen-claude-doe-shim.py: "
            f"coordinator_core.ops.gen_claude_doe_shim not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
