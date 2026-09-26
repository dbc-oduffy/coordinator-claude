# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-complete-entry.py — CLI trampoline over the claude-klabauter workstream
completion-entry scaffolder.

Scaffolds a pre-filled workstream completion entry — the mechanical spine of
/workstream-complete Step 2.6 — leaving up to two model-residue placeholders
for the caller to fill (<!-- NATURE-INFER --> when --nature is omitted, and a
<!-- PROSE: ... --> title/body slot). Idempotent per governing-plan-slug chain
filename; never seeds the commits: field (owned by
reconcile-completion-commits.py --append).
"""
#   <!-- NATURE-INFER -->  — present only when --nature is omitted
#        DEDICATED code, distinct from the 0/1/2 business states above (this is a
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md (BIG_PORT Wave B)

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
        print(f"coordinator-complete-entry.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"coordinator-complete-entry.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    try:
        code = run_op_main(
            "coordinator_core.ops.coordinator_complete_entry", (sys.argv[1:] if argv is None else argv)
        )
    except ImportError as exc:
        print(
            f"coordinator-complete-entry.py: coordinator_core.ops.coordinator_complete_entry "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    return code


if __name__ == "__main__":
    sys.exit(main())
