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

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import resolve_colocated_claude_klabauter_root  # noqa: E402

try:
    _REPO_ROOT = Path(resolve_colocated_claude_klabauter_root(__file__))
except RuntimeError as _exc:
    print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coordinator_core.cli_entry import run_op_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_op_main("coordinator_core.ops.session.fix_concrete_path_citations", sys.argv[1:]))
