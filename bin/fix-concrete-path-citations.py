"""
coordinator/bin/fix-concrete-path-citations.py — thin CLI wrapper over
coordinator_core.ops.session.fix_concrete_path_citations.

Purpose: the remediation half of `guard_concrete_path_citations` (this
repo's write-time and commit-time hard-deny guard). The guard's own deny
text names this command as the fix; this file is the entrypoint it points
at. Forwards argv verbatim to the module's own `main(argv)`, which already
owns family discovery, classification (substitute/marker/report-only), and
the dry-run/--apply split — this wrapper never reimplements any of it.

Usage:
    python3 coordinator/bin/fix-concrete-path-citations.py [--root PATH] [--only FAMILY_ID] [--apply] [--list-families]

Default is dry-run; --apply is required to write anything, and only
`substitute`-classified findings are ever rewritten.

Spec backlink: this module's own docstring
(coordinator_core/ops/session/fix_concrete_path_citations.py) carries the
full design rationale (three-outcome classification, machine-local-derived
family discovery, CRLF-safety, idempotency) — this trampoline does not
duplicate it.

DR-276: routed through `coordinator_core.cli_entry.run_op_main` so that any
`--apply` rewrite the op declares via `declare_write()` becomes a session
scope-touch claim instead of landing unclaimed as an orphan at the
`scoped_git_commit` sink. A dry-run (no `--apply`) declares nothing, so this
adoption is a pure no-op for the default invocation shape.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {_exc}", file=sys.stderr)
        return 1

    from coordinator_core.cli_entry import run_op_main

    return run_op_main("coordinator_core.ops.session.fix_concrete_path_citations", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
