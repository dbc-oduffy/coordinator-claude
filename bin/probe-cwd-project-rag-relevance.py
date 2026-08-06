#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
probe-cwd-project-rag-relevance.py — CLI trampoline over claude-klabauter
coordinator_core.ops.probe_cwd_project_rag_relevance.

Port of: probe-cwd-project-rag-relevance.sh (DoE b5a4192c, 2026-07-20). The bash implementation (workstream-start
gift-shape signal for project-RAG visibility — AC-9 visibility matrix,
settings-home-seam registry lookup, whoami UE-detection subprocess probe,
MCP-health + engine-corpus sentinel reads) has been fully ported to
coordinator_core/ops/probe_cwd_project_rag_relevance.py (claude-klabauter), with a
co-located pytest (test_probe_cwd_project_rag_relevance.py). This file is now
a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module, per
DR-047 (DoE owns contract, claude-klabauter owns engine).

Variant #1 port — PRISTINE, no claude-klabauter shim borrows this module; nothing else
imports coordinator_core.ops.probe_cwd_project_rag_relevance.

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

Always exits 0 — this probe is advisory, never gating. Preserved verbatim in
the ported module's main().

Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md § Chunk 3
DoE-side test oracle (run against this trampoline, must pass unchanged):
    coordinator/tests/test_probe_cwd_project_rag_relevance.sh
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.probe_cwd_project_rag_relevance import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"probe-cwd-project-rag-relevance.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            "probe-cwd-project-rag-relevance.sh: "
            f"coordinator_core.ops.probe_cwd_project_rag_relevance not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
