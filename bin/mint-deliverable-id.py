# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
mint-deliverable-id.py — CLI trampoline over claude-klabauter coordinator_core.ops.mint_deliverable_id.

Port of: mint-deliverable-id.sh (DoE b5a4192c, 2026-07-20). The bash implementation (deliverable_id minting for the
fleet artifact spine — carry / mint-from-stub / mint-from-slug paths) has been
fully ported to coordinator_core/ops/mint_deliverable_id.py, with a co-located
pytest test_mint_deliverable_id.py. This file is now a thin DoE-side (contract)
trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Exit convention: this is a fail-loud compute helper (mints an identity value
that callers rely on being correct), NOT a never-block hook like auto-push —
a claude-klabauter-link failure exits 1, matching the bash oracle's usage-error exit
code, so a broken link surfaces immediately to the calling authoring surface
rather than silently degrading identity minting.

Spec backlink: pln-fleet-deliverable-spine-identity-and-facets-2b331c § D1, C3a
               docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _resolve_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import — this op declares no writes (pure stdout minting),
    so this changes nothing behaviorally, but keeps every operator CLI on the
    one recording seam uniformly.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        print(f"mint-deliverable-id: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"mint-deliverable-id: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.mint_deliverable_id", sys.argv[1:])
    except ImportError as exc:
        print(
            f"mint-deliverable-id: coordinator_core.ops.mint_deliverable_id not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
