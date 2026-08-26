from __future__ import annotations
"""
detect-hardware.py — CLI trampoline over claude-klabauter coordinator_core.ops.detect_hardware.

Finish-strangler port: the bash implementation (cross-platform CPU/RAM/GPU
audit, persisted into hardware.local.toml via the machine-local --concern
writer) has been fully ported to coordinator_core/ops/detect_hardware.py, with
tests in the co-located test_detect_hardware.py. This file is now a thin
DoE-side (contract) trampoline over that claude-klabauter (engine) module, per DR-047
(DoE owns contract/generator, claude-klabauter owns engine).

Shebang note: the SHEBANG line above is `python3` — irrelevant on Windows,
where the `.cmd` sibling launcher (not this shebang) resolves the interpreter;
`python3` is not on PATH on a clean Windows install (only `python`/`py` are),
which is exactly why the `.cmd` shim exists instead of relying on this line.

Renamed to the `.py` suffix (POSIX-exec drain, 2026-08-14) — the one real
caller (test_hardware_audit_ssot.py) already invokes via `sys.executable`
explicitly rather than relying on the shebang/exec bit, so the suffix carried
no functional weight. doctor-probes.toml and docs/install/bin-inventory.json
are prose/manifest references, updated alongside this rename.

Exit convention: this is a fail-loud script (a config-writer, not a
never-block hook shape) — the bash oracle exits 1 when machine-local is
missing or a required probe (cores/RAM) is undetectable. This trampoline
mirrors that: engine-root resolution failure or an unimportable engine module
both exit 1 (not 0), matching the oracle's own fail-loud posture rather than
the auto-push "never block a commit" exemption.

Usage: detect-hardware.py   (no arguments)

Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md §C4
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "lib")
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
    from coordinator_core.ops.detect_hardware import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # Fail-loud: the bash oracle exits 1 on any unresolvable prerequisite
        # (missing machine-local, undetectable cores/RAM); an unresolvable
        # engine link is the same class of failure.
        print(f"detect-hardware: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"detect-hardware: coordinator_core.ops.detect_hardware not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
