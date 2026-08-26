# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-schema-registry-sync.py — SSOT drift gate over the schema registry.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.verify_schema_registry_sync. Checks that every
schemas/*.yaml carrying an applies_to: has a corresponding query --type
recognised by bin/query-records.js at runtime, so a new schema wired into
schemas/ but forgotten in query-records.js TYPE_TO_GLOB fails loudly instead
of silently drifting. Consumer: SSOT drift verification at cadence/CI gates.
"""
from __future__ import annotations
# verify-schema-registry-sync.sh — CLI trampoline over claude-klabauter
# coordinator_core.ops.verify_schema_registry_sync.
#
# SSOT drift gate: every schemas/*.yaml with an applies_to: must have a
# corresponding query --type recognised by bin/query-records.js at runtime.
# Adding a new schema without wiring it into query-records.js TYPE_TO_GLOB
# causes this script to fail loudly, making "add schema, forget
# query-records" impossible.
#
# Finish-strangler port (DR-059): the bash implementation has been fully
# ported to coordinator_core/ops/verify_schema_registry_sync.py (DoE-claude
# clean-slate migration, 2026-07-16). This file is now a thin DoE-side
# (contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE
# owns contract/generator, claude-klabauter owns engine).
#
# Exit convention: this is a fail-loud gate script (SSOT drift check), NOT a
# never-block auto-push shape — it exits 1 both on engine-root/import
# resolution failure AND on the ported check's own FAIL verdict, mirroring
# the pre-port .sh's own ERROR/FAIL exit-1 conventions (it never silently
# skipped).
#
# Exit codes:
#   0 — all schemas with applies_to: have a recognised --type in query-records.js
#   1 — one or more schemas with applies_to: are NOT recognised by
#       query-records.js, OR claude-klabauter-link resolution/import failed, OR a
#       sanity guard (schemas dir / query-records.js missing) tripped.
#
# Usage:
#   verify-schema-registry-sync.sh
#   bash plugins/coordinator/bin/verify-schema-registry-sync.sh
#
# Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 3 + C4

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from coordinator_data_root import data_root  # noqa: E402


def _resolve_plugin_root() -> str:
    """The coordinator root containing the live schemas/ dir.

    Previously a bare `os.path.dirname(os.path.dirname(__file__))` walk — the
    old co-located-only assumption, broken by the 2026-07-22 executable-surface
    migration that moved this script into claude-klabauter while schemas/ stayed
    DoE-resident (DR-047: contract/data lives with DoE, engine with claude-klabauter; see
    `lib/coordinator_data_root.py`'s module docstring for the full two-rung
    resolution chain this now delegates to). Returns the PARENT of the resolved
    schemas/ dir, matching what `coordinator_core.ops.verify_schema_registry_sync
    .run()` expects as its `plugin_root` argument (`plugin_root / "schemas"`).
    """
    return str(data_root("schemas").parent)


def _resolve_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import — this op declares no writes (pure read/verify/
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
            f"verify-schema-registry-sync: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            f"verify-schema-registry-sync: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        plugin_root = _resolve_plugin_root()
    except RuntimeError as exc:
        print(
            f"verify-schema-registry-sync: schemas dir resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.verify_schema_registry_sync", [plugin_root] + sys.argv[1:])
    except ImportError as exc:
        print(
            f"verify-schema-registry-sync: coordinator_core.ops.verify_schema_registry_sync "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
