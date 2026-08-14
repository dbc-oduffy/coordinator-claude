# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
install-shell-init-guard-seam.py — CLI trampoline over claude-klabauter
coordinator_core.ops.install_shell_init_guard_seam.

Collapses coordinator/commands/install.md (DoE-claude repo) Step 3.5b.1's two
literal bash fences (lines 932 and 950 of the source doc) into one call —
see coordinator_core.ops.install_shell_init_guard_seam's own docstring for
the full design rationale and negative-spec.

Spec backlink: DoE-claude:pln-extirpate-pasted-code-from-em--0f42e9 § M3/D9

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
bare in-process `main` call, so the rc block this seam writes becomes a
session scope-touch claim instead of an orphan at the `scoped_git_commit`
sink.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"install-shell-init-guard-seam.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"install-shell-init-guard-seam.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.install_shell_init_guard_seam", sys.argv[1:])
    except ImportError as exc:
        print(
            f"install-shell-init-guard-seam.py: coordinator_core.ops.install_shell_init_guard_seam "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
