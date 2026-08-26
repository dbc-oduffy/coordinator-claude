"""bootstrap-repo.py — git-as-revert single-repo bootstrap primitive.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.bootstrap_repo. Runs the ensure-git / assert-clean /
scaffold / conflict-warn / commit pipeline for one repo, git commit acting
as the revert mechanism if scaffolding needs to be undone. Seeds
COORDINATOR_ROOT so the op's sibling-script resolver
(check-install-divergence.py) finds this DoE clone. Called per-repo by
bootstrap-orchestrate.py.
"""
# coordinator/lib/bootstrap-repo.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.bootstrap_repo.
#
# Full port (DR-059/BIG_PORT wave): the bash implementation (git-as-revert
# bootstrap primitive — ensure-git/assert-clean/scaffold/conflict-warn/commit
# pipeline) has been fully ported to coordinator_core/ops/bootstrap_repo.py
# (claude-klabauter-resident, 16 co-located tests in test_bootstrap_repo.py). This file is
# now a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module,
# per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).
#
# Sibling-script resolution: the ported op needs to find a DoE-resident
# sibling (bin/check-install-divergence.py; canonical structure scaffolding
# now routes to the claude-klabauter coordinator_core.install.scaffold_structure CLI)
# that is NOT part of this port. This trampoline computes its own coordinator
# root (it lives at coordinator/lib/bootstrap-repo.py, so coordinator/ is one
# level up) and sets COORDINATOR_ROOT in the environment (if not already set)
# before importing the op — the op's own rung-1 resolver reads that var, mirroring
# the convention already used by coordinator_core.ops.learn_lessons_roots /
# coordinator_doe_root.
#
# Usage / flags / exit codes: unchanged from the bash oracle — see the op
# module's own docstring (coordinator_core/ops/bootstrap_repo.py) for the full
# business-code table; `--help` on this trampoline prints the identical text
# via the op. TRANSPORT failure (engine-root resolution or op-import failure,
# below) is a DEDICATED exit code 5, distinct from the op's business codes
# 0-4 — a caller checking rc==1 for "usage error / git not available" must
# not conflate that with "the claude-klabauter link is down and nothing ran at all."
# Review: code-reviewer F1 — 0-4 are all business codes; reusing 1 for
# transport failure violates the porter addendum's A3/A3b exit-code-collision
# rule. Matches the sibling trampolines' (verify-no-console-flash.py,
# migrate-state-to-claude-klabauter.sh, parse-completeness-item.py) dedicated-code
# convention.
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 2
#              + docs/plans/2026-07-16-bash-clean-slate-residual-migration.md (BIG_PORT wave)

from __future__ import annotations

import os
import sys

_THIS_FILE = os.path.abspath(__file__)
_LIB_DIR_SELF = os.path.dirname(_THIS_FILE)  # coordinator/lib
_COORDINATOR_ROOT = os.path.dirname(_LIB_DIR_SELF)  # coordinator/
_BIN_LIB_DIR = os.path.join(_COORDINATOR_ROOT, "bin", "lib")

if _BIN_LIB_DIR not in sys.path:
    sys.path.insert(0, _BIN_LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    Also seeds COORDINATOR_ROOT (this trampoline's own coordinator/ tree) into
    the environment, if not already set, so the op's sibling-script resolver
    (check-install-divergence.py) finds THIS
    DoE clone rather than falling through its ~/.claude-install-layout rungs.
    """
    os.environ.setdefault("COORDINATOR_ROOT", _COORDINATOR_ROOT)
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.bootstrap_repo import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"bootstrap-repo.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(5)
    except ImportError as exc:
        print(
            f"bootstrap-repo.py: coordinator_core.ops.bootstrap_repo not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(5)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
