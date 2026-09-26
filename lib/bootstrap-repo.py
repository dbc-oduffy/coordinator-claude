"""bootstrap-repo.py — git-as-revert single-repo bootstrap primitive.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.bootstrap_repo. Runs the ensure-git / assert-clean /
scaffold / conflict-warn / commit pipeline for one repo, git commit acting
as the revert mechanism if scaffolding needs to be undone. Seeds
COORDINATOR_ROOT so the op's sibling-script resolver
(check-install-divergence.py) finds this DoE clone. Called per-repo by
bootstrap-orchestrate.py.
"""
# Full port (DR-059/BIG_PORT wave): the bash implementation (git-as-revert
# level up) and sets COORDINATOR_ROOT in the environment (if not already set)
# via the op. TRANSPORT failure (engine-root resolution or op-import failure,
# below) is a DEDICATED exit code 5, distinct from the op's business codes
#              + docs/plans/2026-07-16-bash-clean-slate-residual-migration.md (BIG_PORT wave)

from __future__ import annotations

import os
import sys

_THIS_FILE = os.path.abspath(__file__)
_LIB_DIR_SELF = os.path.dirname(_THIS_FILE)
_COORDINATOR_ROOT = os.path.dirname(_LIB_DIR_SELF)
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
