"""
handoff-carry-gate — CLI trampoline over claude-klabauter coordinator_core.ops.handoff_carry_gate.

Mechanizes the disposition gate for `## Carried Forward` items
(DoE-claude coordinator/schemas/handoff.schema.json `carried_items`,
coordinator/skills/handoff/SKILL.md § Cascading unresolved items) into a
single fail-loud tool call: every item must declare a carry_id and a
sanctioned disposition, and a terminal disposition must name its detail.
Carry DEPTH is not checked — carries are indefinite (DR-278).

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
  handoff-carry-gate check <handoff-path>

Output: one `REFUSED: ...` line per gated item, to stderr, when refused.
Exit codes: 0 — every carried item declares its state; 1 — one or more items
refused; 2 — internal error (bad usage, path not found, unparseable
frontmatter).

Spec backlink: coordinator_core/ops/handoff_carry_gate.py
"""
from __future__ import annotations

import os
import sys

def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
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
        print(f"handoff-carry-gate: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"handoff-carry-gate: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        code = run_op_main("coordinator_core.ops.handoff_carry_gate", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"handoff-carry-gate: coordinator_core.ops.handoff_carry_gate not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
