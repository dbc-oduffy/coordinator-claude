"""bootstrap-orchestrate.py — multi-repo bootstrap orchestrator over working-repos.yaml.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.bootstrap_orchestrate. Discovers repos from
working-repos.yaml, drives EXPRESS/CUSTOM selection, delegates per-repo
bootstrap to bootstrap-repo.py, and stamps install currency. Seeds
COORDINATOR_ROOT so the op's sibling-script resolver
(lib/coordinator-currency.sh) finds this DoE clone.
"""
# coordinator/lib/bootstrap-orchestrate.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.bootstrap_orchestrate.
#
# Full port (DR-059/BIG_PORT wave): the bash implementation (working-repos.yaml
# discovery, EXPRESS/CUSTOM selection, per-repo bootstrap-repo.py delegation,
# currency stamping) has been fully ported to
# coordinator_core/ops/bootstrap_orchestrate.py (claude-klabauter-resident, co-located
# test_bootstrap_orchestrate.py). This file is now a thin DoE-side (contract)
# trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
# contract/generator, claude-klabauter owns engine).
#
# Sibling-script resolution: the ported op needs to find one DoE-resident
# sibling (`lib/coordinator-currency.sh`, NOT part of this port — see the
# op module's own docstring "Cross-boundary currency delegation" section).
# This trampoline computes its own coordinator root (it lives at
# coordinator/lib/bootstrap-orchestrate.py, so coordinator/ is one level up)
# and sets COORDINATOR_ROOT in the environment (if not already set) before
# importing the op — mirroring the identical convention used by
# `bootstrap-repo.sh`'s own trampoline.
#
# Usage / flags / exit codes: unchanged from the bash oracle — see the op
# module's own docstring (coordinator_core/ops/bootstrap_orchestrate.py) for
# the full business-code table; `--help` on this trampoline prints the
# identical text via the op. TRANSPORT failure (CLAUDE_KLABAUTER_ROOT resolution or
# op-import failure, below) is a DEDICATED exit code 5, distinct from the
# op's business codes 0-3 — a caller checking rc==1 for "usage error /
# missing prerequisite" must not conflate that with "the claude-klabauter link is down
# and nothing ran at all." Matches the sibling trampolines'
# (bootstrap-repo.py, verify-no-console-flash.py, migrate-state-to-claude-klabauter.sh,
# parse-completeness-item.py) dedicated-code convention.
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 4
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
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    Also seeds COORDINATOR_ROOT (this trampoline's own coordinator/ tree) into
    the environment, if not already set, so the op's sibling-script resolver
    (lib/coordinator-currency.sh) finds THIS DoE clone rather than falling
    through its ~/.claude-install-layout rungs.
    """
    os.environ.setdefault("COORDINATOR_ROOT", _COORDINATOR_ROOT)
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.bootstrap_orchestrate import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"bootstrap-orchestrate.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(5)
    except ImportError as exc:
        print(
            f"bootstrap-orchestrate.py: coordinator_core.ops.bootstrap_orchestrate not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(5)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
