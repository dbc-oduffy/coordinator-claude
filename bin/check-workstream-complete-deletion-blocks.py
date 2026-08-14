# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-workstream-complete-deletion-blocks.py — CLI trampoline over claude-klabauter
coordinator_core.ops.ceremony.commit_gates.

Validates Step 2.67 commit-body "Deleted (Step 2.67):" / "Kept (Step 2.67):"
blocks against staged git reality. Called from `/workstream-complete` Step 3
step 1.5 between stage and commit — a fail-loud gate (never silently no-ops on
a claude-klabauter-link failure, unlike a never-block hook such as coordinator-auto-push).

Finish-strangler port (DR-059): the bash implementation (awk two-pass block
parser + git diff-cached scoping + F3 inverse check) has been fully ported to
coordinator_core/ops/ceremony/commit_gates.py (deletion_block_gate() +
CLI entry point main(), 16 tests in
coordinator_core/ops/ceremony/tests/test_commit_gates.py) as part of the
`wsc_tail` pure-Python rebuild (docs/plans/2026-07-16-wsc-pure-python-tail-rebuild.md
§ C3). This file is now a thin DoE-side (contract) trampoline over that claude-klabauter
(engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).

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

Exit codes (reproduced verbatim from the bash original — see
coordinator_core.ops.ceremony.commit_gates.main() for the authoritative
docstring):
  0 — all claims match staged reality (gate green; safe to commit)
  1 — claim mismatch (fix commit body or re-stage)
  2 — usage error (missing arg, msg_file unreadable) — ALSO used when the
      claude-klabauter link itself cannot be resolved/imported (fail-loud: this is a
      commit-blocking gate, so a broken engine link must never silently pass).
  3 — environment error (not in a git repo)

Spec backlink: docs/plans/2026-06-15-workstream-complete-self-clean.md (Chunk 6)
Spec backlink: pln-rebuild-the-wsc-commit-ceremon-f7c2a0 § C3 (AC10)
Doctrine: docs/wiki/cruft-sweep-cadence.md § Three-layer design (Layer 3)

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
any paths the op declares via `declare_write` become a session scope-touch
claim (this op is a read-only staged-vs-commit-body validator — it writes
nothing — so it declares none; routing it is a baseline-shrink, not a
behavior change).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        # This is a commit-blocking gate — a broken claude-klabauter link must fail
        # loud (exit 2, same class as the bash original's usage-error exit),
        # never silently pass a commit through unchecked.
        print(
            f"check-workstream-complete-deletion-blocks.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ImportError as exc:
        print(
            "check-workstream-complete-deletion-blocks.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.ceremony.commit_gates", sys.argv[1:])
    except ImportError as exc:
        print(
            "check-workstream-complete-deletion-blocks.py: "
            f"coordinator_core.ops.ceremony.commit_gates not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
