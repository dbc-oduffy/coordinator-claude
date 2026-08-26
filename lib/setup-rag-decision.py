"""setup-rag-decision.py — CLI trampoline over claude-klabauter coordinator_core.ops.setup_rag_decision.

RAG-index decision resolver for /repo-setup: a three-branch UE/daemon decision tree
that idempotently writes tripwire-block markers. Invoked by
coordinator/skills/repo-setup/SKILL.md as a subprocess (never sourced — this port is
executable-only, unlike the retired bash oracle's dual standalone/sourced contract).
The decision logic itself lives in coordinator_core/ops/setup_rag_decision.py.
"""
# The sole live caller (coordinator/skills/repo-setup/SKILL.md) invokes this
# file as `"$PYTHON_BIN" "${PYTHON_ARGS[@]}" "${_PLUGIN_ROOT}/lib/setup-rag-decision.py" --root "$(pwd)"`
# (subprocess, never `source` — see that skill's own doc: sourcing a
# fail-loud helper would terminate the repo-setup shell).
#
# setup-rag-decision.py — CLI trampoline over claude-klabauter coordinator_core.ops.setup_rag_decision.
#
# Finish-strangler port (DR-059): the bash implementation (RAG-index decision
# resolver for /repo-setup — three-branch UE/daemon decision tree, idempotent
# tripwire-block writer) has been fully ported to
# coordinator_core/ops/setup_rag_decision.py (28 co-located pytest cases).
# This file is now a thin DoE-side (contract) trampoline over that claude-klabauter
# (engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns
# engine).
#
# Scope note (NOT a regression — see the claude-klabauter module's own negative-spec):
# the bash oracle offered a dual standalone/sourced CLI contract; this port
# is EXECUTABLE-ONLY. The sole live caller never sources this file (its own
# doc forbids it), and a Python file cannot be `source`d by bash anyway — so
# the sourced contract is intentionally dropped, not silently lost.
#
# Usage (standalone):
#   setup-rag-decision.py [--root <path>] [--dry-run] [--help]
#
# Exit codes:
#   0  Decision resolved and action taken (or dry-run completed).
#   1  Usage error or unambiguous-detection failure (fail-loud).
#   2  Transport failure: the engine root unresolvable, or
#      coordinator_core.ops.setup_rag_decision not importable. A DEDICATED
#      code, distinct from 1, per porter-brief addendum §3b (transport
#      failure must never collide with a business exit code). The sole live
#      caller (coordinator/skills/repo-setup/SKILL.md) only branches on
#      rc==0 vs rc!=0, so widening the contract from {0,1} to {0,1,2} is
#      safe — it does not need 1 and 2 to stay collapsed.
#
# Spec backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1c (AC3)
#                docs/plans/2026-07-16-bash-clean-slate-residual-migration.md

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.setup_rag_decision import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"setup-rag-decision: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"setup-rag-decision: coordinator_core.ops.setup_rag_decision not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
