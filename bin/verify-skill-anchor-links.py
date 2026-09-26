# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-skill-anchor-links.py — dead-anchor gate for `<path>.md § <section>` citations.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.verify_skill_anchor_links. Resolution is PATH-DIRECTED:
each `<path>.md § <section>` citation is checked against the file that citation
itself names, never against a union of doctrine files. An OPTIONAL manifest at
<doe_root>/coordinator/doctrine-surfaces.json (override:
COORDINATOR_DOCTRINE_MANIFEST) supplies an alias map so home-relative citations
such as `~/.claude/CLAUDE.md` become checkable; its ABSENCE is not an error —
those citations simply stay QUALIFIED rather than resolved.

Invoked from `/update-docs` Phase 11h. Exit codes are three distinct outcomes,
not a clean/dirty pair: 0 = checked, clean; 1 = checked, DEAD anchors found;
2 = COULD NOT CHECK (manifest present but broken, or plugin root unresolvable).
A 2 is never a finding about the citations — it means the gate never ran.

This trampoline's OWN failures are could-not-check conditions and exit 2 on the
same contract as the op's: engine root unresolvable, and the op module not
importable once it is. Neither says anything about the citations, so neither may
report 1 — a gate that could not load reporting a DEAD-anchor finding is the
false-signal class this gate exists to catch.
"""
from __future__ import annotations
import os
import sys


def _import_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"verify-skill-anchor-links: COULD NOT CHECK — engine root did not resolve, "
            f"so the op backing this gate was never located and no citation was read: {exc}",
            file=sys.stderr,
        )
        return 2
    except ImportError as exc:
        print(
            f"verify-skill-anchor-links: COULD NOT CHECK — engine root resolved but "
            f"coordinator_core.cli_entry was not importable from it, "
            f"so no citation was read: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        code = run_op_main("coordinator_core.ops.verify_skill_anchor_links", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"verify-skill-anchor-links: COULD NOT CHECK — engine root resolved but "
            f"coordinator_core.ops.verify_skill_anchor_links was not importable from it, "
            f"so no citation was read: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
