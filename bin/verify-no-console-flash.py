# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-no-console-flash.py — CLI trampoline over claude-klabauter coordinator_core.ops.verify_no_console_flash.

Guards against console-window flashes on Windows: spawning any native
console-subsystem .exe (python.exe, node.exe, powershell.exe) without an
explicit CREATE_NO_WINDOW / windowsHide:true suppression allocates a fresh
conhost.exe window that briefly flashes. Flags variable-interpreter, heredoc,
bare-literal, array-form, and unsuppressed powershell/pwsh spawn shapes
across *.sh, *.json, and coordinator-auto-push under the coordinator-claude
tree.
"""
# flashes. The only reliable suppression is CREATE_NO_WINDOW / windowsHide:true
#   (1) variable-interpreter:  "${PYTHON:-python3}", "$PYTHON", $PYTHON_BIN, "${NODE...}"
#   (5) hooks.json commands:   ARCHITECTURALLY EXEMPT (2026-06-14) — Claude Code is the
#   b) The line carries CREATE_NO_WINDOW, windowsHide, or -WindowStyle Hidden
#   2 — TRANSPORT failure: engine-root resolution failed or the ported op module
from __future__ import annotations

import os
import sys

def _prepare_claude_klabauter_root() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()


def main(argv: "list[str] | None" = None) -> int:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"verify-no-console-flash.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.verify_no_console_flash", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"verify-no-console-flash.py: coordinator_core.ops.verify_no_console_flash not importable: {exc}",
            file=sys.stderr,
        )
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
