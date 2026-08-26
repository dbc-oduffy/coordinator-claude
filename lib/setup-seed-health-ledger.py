# skills/repo-setup/SKILL.md Phase 3j invokes this file as
# `"$PYTHON_BIN" "${PYTHON_ARGS[@]}" "${_PLUGIN_ROOT}/lib/setup-seed-health-ledger.py" "$(pwd)"`.
"""
setup-seed-health-ledger.py — CLI trampoline over claude-klabauter
coordinator_core.ops.setup_seed_health_ledger.

Finish-strangler port: the bash implementation (repo-setup-time helper that
seeds a skeleton state/health-ledger.md so workday-complete Step 4 can append
without a "create if missing" branch) has been fully ported to
coordinator_core/ops/setup_seed_health_ledger.py, with a co-located pytest
suite (test_setup_seed_health_ledger.py). This file is now a thin DoE-side
(contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine).

Renamed from setup-seed-health-ledger.sh (2026-07-22 bash-kill campaign):
this file's body has been pure Python since the finish-strangler port; the
`.sh` suffix was a naming leftover that still paid the launcher-indirection
tax on Windows (DR-076 requires a `.cmd` sibling for any bareword bin/lib
entrypoint, `.sh` or not). Renaming to `.py` makes the on-disk suffix match
the actual interpreter and removes the last `.sh`-suffixed polyglot in this
directory. Spec backlink: tasks/debash-consolidated/frontier-2026-07-21.md.

Usage:
  setup-seed-health-ledger.py [REPO_ROOT]

  REPO_ROOT — path to the target repo root; defaults to current working
  directory.

Exit codes: 0 — ledger seeded or already present (idempotent no-op); 1 — bad
REPO_ROOT, or state/ directory/ledger file could not be created (fail-loud —
this is a setup-time gate/config-writer, not a never-block hook).

Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
"""

from __future__ import annotations

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
    from coordinator_core.ops.setup_seed_health_ledger import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # Fail-loud: this is a setup-time gate/config-writer (matches the
        # bash original's own exit-1 posture on ambiguity), not a never-block
        # hook -- a broken claude-klabauter link must not silently skip the seed step.
        print(f"setup-seed-health-ledger: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"setup-seed-health-ledger: coordinator_core.ops.setup_seed_health_ledger not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
