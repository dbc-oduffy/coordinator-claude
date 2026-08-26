"""check-install-singularity.py — canonical-install-locus invariant probe.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.install.check_install_singularity. Detects accidental
coordinator install splits — more than one location claiming to be the
canonical coordinator install — and fails loud with remediation. Invoked
as install.md Step 7.5's "canonical-locus integrity gate" and a
doctor-sentinel P-18 probe.
"""
# check-install-singularity.py — CLI trampoline over claude-klabauter
# coordinator_core.install.check_install_singularity.
#
# Finish-strangler port: the bash implementation (canonical-install-locus
# invariant probe — detects accidental coordinator install splits) has been
# fully ported to coordinator_core/install/check_install_singularity.py, with
# tests in the co-located test_check_install_singularity.py. This file is now
# a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module, per
# DR-047 (DoE owns contract/generator, claude-klabauter owns engine).
#
# Exit convention: this is a fail-loud gate/validator script (install.md
# Step 7.5 "canonical-locus integrity gate", a `run_required` step; also a
# doctor-sentinel P-18 probe treated as red-on-nonzero) — codes:
#   0 — install singularity confirmed, or consented dev-loop override active
#   1 — accidental split detected (remediation printed to stderr)
#   2 — the claude-klabauter module's OWN internal-error floor (an unhandled exception
#       inside check_install_singularity.py's run()) — reserved exclusively
#       for that case; never used by this trampoline.
#   3 — this trampoline's OWN transport failure: engine-root resolution
#       failed, or the engine module could not be imported. Dedicated code
#       (not 2) so a caller's exit-code branch can distinguish "the engine
#       ran and hit an internal bug" (2, fix the ported check) from "the
#       engine could never be reached at all" (3, fix engine-root/venv
#       resolution) — these have different remediation paths. Matches the
#       pattern used by the sibling `gen-settings-hooks.py` trampoline in
#       this same port wave, which also reserves a code distinct from its
#       own business codes for transport failure
#       (PORTER-BRIEF-ADDENDUM rule 3b; review-integrator F4,
#       2026-07-17 BIG_PORT Wave B review).
#
# Usage: check-install-singularity.py   (no arguments)
#
# Spec backlink:
#   docs/plans/2026-06-26-coordinator-install-update-friction-fix-slate.md § C-R1b
#   tasks/install-friction-triage/cluster-B-path-venv-registration.md § ISSUE #4
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
#   (BIG_PORT Wave B, item check-install-singularity)
from __future__ import annotations

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
    from coordinator_core.install.check_install_singularity import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # Transport failure -- dedicated exit 3 (see exit-convention block
        # above); distinct from the module's own internal-error floor (2)
        # and never overloads the business codes 0/1.
        print(f"check-install-singularity: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"check-install-singularity: coordinator_core.install.check_install_singularity "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
