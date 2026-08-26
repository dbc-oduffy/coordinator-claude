# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""validate-install-contract.py — CLI trampoline over claude-klabauter coordinator_core.ops.validate_install_contract.

Validates a repo's agent-install-manifest.json against the packageability
contract (docs/wiki/agent-install-contract.md § Packageability) — completeness
rules that JSON-schema shape alone can't express (functional probes,
required_env_vars, entry-point contract properties, tested_platforms,
configurable_locations discovery/default/override). Scoped to the manifest at
the invoking repo's own root (or --manifest-path); not wired into any
cross-repo/fleet-shared hook.
"""
# validate-install-contract — CLI trampoline over claude-klabauter
# coordinator_core.ops.validate_install_contract.
#
# PURPOSE: reads a repo's agent-install-manifest.json and validates it against
# the packageability contract (docs/wiki/agent-install-contract.md §
# Packageability) — the per-point completeness rules that JSON-schema
# required/type shape alone can't express: functional-probe present per
# system_prerequisites/direct_deps entry, required_env_vars present-even-if-
# empty, entry-point contract properties declared on standalone_setup_script/
# programmatic_entry_point, tested_platforms declared, every
# configurable_locations[] entry carries discovery.candidates + default +
# override. Full check-point rationale lives in the claude-klabauter module's own
# docstring (coordinator_core/ops/validate_install_contract.py) — this file is
# a thin CLI shim, not the logic.
#
# SCOPE (hard, do not widen): this script validates ONLY the manifest at the
# repo root it is invoked from (or --manifest-path) — a repo's own manifest,
# at that repo's own request. It is NOT auto-wired into any cross-repo/fleet-
# shared hook; wiring it into a hook that fires against a sibling repo's not-
# yet-compliant manifest would regress that sibling. See
# docs/plans/2026-07-11-packageability-contract-fleet-doctrine.md § Anti-scope.
#
# Finish-strangler port (DR-059, DR-047): the bash+jq implementation (303
# lines) has been fully ported to
# coordinator_core/ops/validate_install_contract.py (claude-klabauter), with a
# co-located pytest suite (coordinator_core/ops/test_validate_install_
# contract.py, 37 tests). This file is now a thin DoE-side (contract)
# trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
# contract/generator, claude-klabauter owns engine). The `jq` and `bash >= 4.3`
# runtime preconditions from the bash oracle are gone — this is a
# pure-Python port, no external binary dependency.
#
# Exit-code contract (business codes — from coordinator_core.ops.
# validate_install_contract.main(), unchanged from the bash oracle):
#   0 — compliant, OR not opted into the contract, OR no manifest declared
#   1 — one or more packageability findings, OR a CLI usage error
# Exit-code contract (THIS trampoline's own added layer — claude-klabauter-link/import
# transport failure, dedicated code per porter-brief addendum § 3b, chosen as
# the lowest code unused by the business contract above):
#   2 — engine-root resolution failed, or coordinator_core.ops.
#       validate_install_contract is not importable (claude-klabauter-link/transport
#       failure — distinct from any business 0/1 outcome above, so a caller
#       cannot misclassify a real claude-klabauter-link outage as "compliant" or
#       "has findings").
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Spec backlink: DoE-claude:pln-fleet-packageability-contract--d44c4c § C4
# Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _resolve_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here -- this is a low-frequency CLI/hook-adjacent
    validator, not a hot per-commit path, but the direct-import shape is
    still strictly cheaper than a second subprocess hop for a synchronous
    check-and-print CLI.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import — this op declares no writes (pure read/validate/
    print), so this changes nothing behaviorally, but keeps every operator
    CLI on the one recording seam uniformly.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        print(
            f"validate-install-contract.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ImportError as exc:
        print(
            "validate-install-contract.py: coordinator_core.cli_entry not importable: "
            f"{exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.validate_install_contract", sys.argv[1:])
    except ImportError as exc:
        print(
            "validate-install-contract.py: coordinator_core.ops.validate_install_contract "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
