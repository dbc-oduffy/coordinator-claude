"""
emit-artifact-shape-contract — CLI trampoline over claude-klabauter
coordinator_core.ops.emit_artifact_shape_contract.

Emits `artifact-shape-contract/artifact-shape-contract.schema.json` — a stable,
versioned JSON Schema contract (draft-2020-12) carrying one JSON Schema per
registered coordinator schema type (schemas/*.yaml + *.schema.json) plus the
cross-type liveness mapping as first-class contract data.

Finish-strangler port: the JS implementation (schema-registry -> JSON Schema
translation, LIVENESS_MAPPING + ProvenanceEnvelope sub-shape contract data, emit/CLI
wiring) has been fully ported to coordinator_core/ops/emit_artifact_shape_contract.py
(claude-klabauter), with independent parity coverage in the co-located pytest
(coordinator_core/ops/test_emit_artifact_shape_contract.py — including a live
structural-parity run against this trampoline's own JS predecessor). This file is now
a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module, per DR-047
(DoE owns contract/generator, claude-klabauter owns engine).

Unlike coordinator-auto-push (whose ported module is a HOT per-commit path that reads
only claude-klabauter-resident state), this op reads DoE-side input (coordinator/schemas/) and
writes a DoE-side output (coordinator/artifact-shape-contract/ by default) — the ported
module has no way to locate those on its own, since schemas/ lives in THIS repo, not
Claude-klabauter. This trampoline resolves its own coordinator root and hands it to the claude-klabauter
module via the EMIT_ARTIFACT_SHAPE_CONTRACT_COORDINATOR_ROOT env var (module docstring
has the full contract). ARTIFACT_CONTRACT_OUT_DIR (output-dir override) is passed through
unchanged — same literal env var name the JS oracle already used, so existing test
tooling that redirects output to a tmp dir keeps working unchanged.

Coordinator-root resolution does NOT derive from this script's own __file__ location
(dirname(dirname(__file__))). That mirrored the JS oracle's `COORDINATOR =
path.join(__dirname, '..')` correctly while this executable lived in DoE-claude
(coordinator/bin/.. IS the coordinator root there) — but this file has since migrated to
Claude-klabauter (see BACKGROUND above) while coordinator/schemas/ and
coordinator/artifact-shape-contract/ stayed in DoE-claude. Self-location now resolves to
<claude-klabauter>/coordinator, which has neither directory, so the op module would fail with a
misleading "schemas/ not found" instead of a clear root-resolution error. Resolution now
goes through CLAUDE_PLUGIN_ROOT (env override, wins verbatim if set) else
coordinator_registry.doe_root() + "/coordinator" (fail loud via sys.exit(2) if
unresolvable) — see _resolve_coordinator_root() below. A future reader must not restore
__file__-based resolution to regain oracle parity; that is precisely what caused this
break (same class of fix as commit 1a31400d, verify-templates-bin-sync.py).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here).

Usage:
  emit-artifact-shape-contract

Exit codes (parity-critical — matches coordinator_core.ops.emit_artifact_shape_contract.main
exactly; see that module's docstring for the full contract):
  0 — contract emitted successfully.
  1 — business failure: the schema registry is empty, or an injected sub-shape name
      (e.g. ProvenanceEnvelope) collides with a registered schema name.
  2 — DEDICATED transport/config-failure code, distinct from both business codes above:
      engine-root resolution failed, coordinator_core.ops.emit_artifact_shape_contract
      not importable, or (raised inside the claude-klabauter module) the coordinator root's
      schemas/ directory could not be found.

Spec backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md, BIG_PORT
               Wave B item emit-artifact-shape-contract
               archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk B1
Prior JS implementation: see git log (coordinator/bin/emit-artifact-shape-contract.js,
                          642 lines, retired on this cutover)
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402


def _resolve_coordinator_root() -> str:
    """Resolve the DoE-side coordinator/ root that owns schemas/ (input) and
    artifact-shape-contract/ (default output).

    CLAUDE_PLUGIN_ROOT wins verbatim if set. Otherwise resolves via
    coordinator_registry.doe_root() (env DOE_ROOT / REPO_DOE_CLAUDE -> machine-local
    repos.doe_claude -> raise) and returns <doe_root()>/coordinator.

    Does NOT derive from this script's own __file__ location — see this module's
    docstring § coordinator root resolution for why self-location broke when this
    executable migrated to claude-klabauter while schemas/ and artifact-shape-contract/
    stayed in DoE-claude.

    Fails loud (sys.exit(2), the same DEDICATED transport/config-failure code used for
    engine-root resolution failures below) if doe_root() cannot resolve.
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return env_root
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            f"emit-artifact-shape-contract: cannot resolve the coordinator doctrine repo root ({exc}). "
            "Set repos.doe_claude in the machine-local registry, or set the DOE_ROOT "
            "(or REPO_DOE_CLAUDE) env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(2)
    return os.path.join(root, "coordinator")


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 op runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is deliberately
    NOT used here (variant-#1 direct-import trampoline — see
    tasks/2026-07-16-clean-slate-recon/r1-doe-port-template.md § 1).

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"emit-artifact-shape-contract: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"emit-artifact-shape-contract: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    # This is DoE-side data (schemas/ input, artifact-shape-contract/ output) that
    # the claude-klabauter module has no way to locate on its own; hand it over via env var
    # (see module docstring, and _resolve_coordinator_root()'s own docstring, for
    # why this is NOT derived from this script's own __file__ location).
    coordinator_root = _resolve_coordinator_root()
    os.environ["EMIT_ARTIFACT_SHAPE_CONTRACT_COORDINATOR_ROOT"] = coordinator_root

    try:
        code = run_op_main(
            "coordinator_core.ops.emit_artifact_shape_contract", sys.argv[1:]
        )
    except ImportError as exc:
        print(
            f"emit-artifact-shape-contract: coordinator_core.ops.emit_artifact_shape_contract "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
