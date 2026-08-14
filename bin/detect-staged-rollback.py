"""
detect-staged-rollback — CLI trampoline over the engine-repo's
coordinator_core.ops.detect_staged_rollback.

Read-and-report only against git; never mutates a repo. This IS wired into
Claude-klabauter's commit path — it is the sole entry in
coordinator_core.ops.install_claude_klabauter_precommit_hook._GATE_REGISTRY, the
registry that installs `.git/hooks/pre-commit`, which invokes this trampoline
directly. See the module docstring on
coordinator_core.ops.detect_staged_rollback for the two checks it runs (a
staged-blob rollback detector and a staged mass-deletion tripwire), their
thresholds, and their independent overrides.

Usage:
    detect-staged-rollback [repo-root]
    detect-staged-rollback --help

    repo-root defaults to the current working directory. `--help`/`-h` and
    unknown-option handling live in the op, not here — this trampoline
    forwards argv verbatim so both callers (bareword CLI and `python -m`)
    get the same usage surface.

Exit codes:
    0 — clean (no rollback candidates, or candidates below threshold, or
        COORDINATOR_OVERRIDE_PRECOMMIT_STAGED_ROLLBACK set; and no
        mass-deletion finding, or one below threshold, or
        COORDINATOR_OVERRIDE_PRECOMMIT_MASS_DELETION set)
    1 — a staged-rollback finding crossed the breadth/depth threshold, and/or
        a mass-deletion finding crossed the ratio/floor threshold
    2 — CLAUDE_KLABAUTER_ROOT resolution / import failure (this trampoline's own
        transport failure) OR a usage error from the op (unknown option).
        Both mean "the check never ran"; the stderr message distinguishes
        them.

Direct-import variant (mirrors coordinator/bin/check-registry-codename-leak.py
and coordinator/bin/pickup-assemble): a plain in-process function call after
resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop — this op is read-only and has no
IPC-scoped state to route through, so the direct-import shape fits over
route_mutation.
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
    from coordinator_core.ops.detect_staged_rollback import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"detect-staged-rollback: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"detect-staged-rollback: coordinator_core.ops.detect_staged_rollback not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
