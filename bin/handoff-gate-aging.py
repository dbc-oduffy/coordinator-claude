"""
handoff-gate-aging — CLI trampoline over claude-klabauter coordinator_core.ops.handoff_gate_aging.

Mechanizes the 14d/7d awaiting_gate handoff aging-reconcile predicate (pickup/SKILL.md
§ Step 3.4d, docs/wiki/spinoff-handoffs.md § Awaiting_gate aging § Thresholds) into a
single fail-loud tool call.

No longer force-invoked by workday-start.md's morning ceremony (2026-07-27,
docs/plans/2026-07-26-gate-resolution-widen-and-migrate.md § C16 — see
coordinator_core.ops.handoff_gate_aging's module docstring for the dry-run
evidence and the surviving consumer). Still installed and runnable ad hoc;
`compute_aging_verdict` in coordinator_core.pickup_assemble consumes
`check_one` directly (in-process, not via this trampoline) as supplementary
evidence for the `jgate` judgment point.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here).

Usage:
  handoff-gate-aging <handoff-path>       # single-file check
  handoff-gate-aging <directory>          # scan *.md files, one level (maxdepth 1)

Output: one `STALE: <file> (...)` line per stale handoff, to stdout.
Exit codes: 0 — none stale; 1 — one or more stale (fail loud); 2 — internal error.

Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C5c
Port of: coordinator/bin/handoff-gate-aging.sh (67202df6, 2026-07-16)
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md § T1b chunk B3
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"handoff-gate-aging: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"handoff-gate-aging: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.handoff_gate_aging", sys.argv[1:])
    except ImportError as exc:
        print(
            f"handoff-gate-aging: coordinator_core.ops.handoff_gate_aging not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
