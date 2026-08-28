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
        print(f"install-shell-init-guard-seam.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"install-shell-init-guard-seam.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.install_shell_init_guard_seam", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"install-shell-init-guard-seam.py: coordinator_core.ops.install_shell_init_guard_seam "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
