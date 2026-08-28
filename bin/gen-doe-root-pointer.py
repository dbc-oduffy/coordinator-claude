# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
gen-doe-root-pointer.py — CLI trampoline over claude-klabauter coordinator_core.ops.gen_doe_root_pointer.

Finish-strangler port (DOE-PORT R1, variant #1 — pristine, no claude-klabauter shim borrows this
script): the bash implementation (reads repos.doe_claude from the machine-local registry,
writes ~/.claude/.doe-root, --check-only dry-run mode) has been fully ported to
coordinator_core/ops/gen_doe_root_pointer.py per DR-047 (DoE owns contract/generator,
Claude-klabauter owns engine). This file is now a thin DoE-side (contract) trampoline over that
Claude-klabauter (engine) module.

Spec backlink: DoE-claude:pln-coordinator-maximalist-install-e73afa § C1
Prior bash implementation: see git log (gen-doe-root-pointer.py, 223 lines, retired on
this cutover).
"""

from __future__ import annotations

import os
import sys

def _import_runner():
    """Resolve the engine root and import the in-process runner.

    DR-276: routes through `coordinator_core.cli_entry.run_op_main` rather
    than calling the op's `main` directly, so the pointer file this op
    writes becomes a session scope-touch claim instead of an orphan at the
    `scoped_git_commit` sink.
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
        print(f"gen-doe-root-pointer.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"gen-doe-root-pointer.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.gen_doe_root_pointer", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"gen-doe-root-pointer.py: coordinator_core.ops.gen_doe_root_pointer not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
