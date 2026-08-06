#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
install-health-run.py — CLI trampoline over claude-klabauter coordinator_core.ops.install_health_run.

Finish-strangler port: the bash orchestrator (iterate bin/install-health/*.sh
in lexicographic order, run each via `bash <script>`, continue past
individual failures, aggregate a non-zero exit iff any sub-script failed) has
been fully ported to coordinator_core/ops/install_health_run.py, including a
byte-parity reimplementation of the shared trusted-root-guard's fail-loud
trust-core (coordinator/lib/coordinator-trusted-root-guard.sh, retired
bd8cc0e9, 2026-07-22). This port
covers the orchestrator, not its sub-scripts — but the sub-scripts
themselves are no longer uniformly bash: 2026-07-22 killed the two
Claude-klabauter-owned bash drop-ins (ensure-python3-exe-shim.sh,
check-windows-ssh-binary.sh; see cross-repo memo to claude-klabauter for the
functional specs claude-klabauter needs to reimplement natively) and
seed-skill-overrides.sh is already a python3 trampoline. The ported
orchestrator's `*.sh` glob matches any drop-in by extension regardless of
its interpreter, so this is not a wiring change.

Exit convention: FAIL-LOUD. install-health-run.py is a REQUIRED install step
(install-maximalist.py's `run_required`), not an advisory hook — CLAUDE_KLABAUTER_ROOT
resolution failure or an untrusted plugin root both exit 1, matching the
original script's own `--mode=fail-loud` trust-guard call.

DR-276: this trampoline calls `coordinator_core.ops.install_health_run.main`
with its own `script_path=` keyword — a shape `run_op_main`'s plain
`op_main(list(argv))` call cannot express — so it wraps the call in
`coordinator_core.cli_entry.recording_declared_writes` instead of routing
through `run_op_main`, giving it the same declared-write session scope-touch
claim without dropping the `script_path` argument (never repoint a CLI at a
narrower entrypoint contract than the one it already calls).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import recording_declared_writes
    from coordinator_core.ops.install_health_run import main as _op_main
    return _op_main, recording_declared_writes


def main() -> None:
    try:
        op_main, recording_declared_writes = _import_main()
    except RuntimeError as exc:
        print(f"install-health-run.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"install-health-run.py: coordinator_core.ops.install_health_run not importable: {exc}", file=sys.stderr)
        sys.exit(1)

    with recording_declared_writes():
        code = op_main(sys.argv[1:], script_path=os.path.abspath(__file__))
    sys.exit(code)


if __name__ == "__main__":
    main()
