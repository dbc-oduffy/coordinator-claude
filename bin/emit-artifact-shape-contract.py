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
import pathlib
import re
import sys

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
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_registry import _DoeUnresolvable, doe_root

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
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def _source_contract_version() -> "str | None":
    """Read CONTRACT_VERSION out of this repo's own engine source, as text.

    Deliberately a text read, not an import: importing
    coordinator_core.ops.emit_artifact_shape_contract would just hand back
    whichever module sys.path already resolved to (possibly the stale,
    published klabauter mirror) — that is exactly the thing being checked
    against, so it cannot also be the check.

    Returns None if the source file cannot be found or does not declare a
    matching CONTRACT_VERSION assignment (caller treats None as "cannot
    check, do not block").
    """
    source_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "coordinator_core"
        / "ops"
        / "emit_artifact_shape_contract.py"
    )
    if not source_path.exists():
        return None
    text = source_path.read_text(encoding="utf-8")
    match = re.search(r'^CONTRACT_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        return None
    return match.group(1)


def _assert_resolved_engine_is_this_source() -> "str | None":
    """Refuse to emit from a resolved engine that is not this repo's source tree.

    Incident, 2026-09-12: this repo's engine module bumped CONTRACT_VERSION to
    9.1.0 (new p4_server/p4_workspace schema content). A run of this
    trampoline resolved the engine via require_dispatch_engine_on_path(),
    which returns the published klabauter mirror, not this source tree. The
    mirror was still on the stale 9.0.0 bundle, carrying no Perforce kinds,
    and — because the mirror is also the OSS-sanitized variant — rewrote
    internal spec references into placeholders in the emitted output. The run
    exited 0, printed a plausible "emitted 68 schemas" line, and modified the
    output file, with nothing to indicate that none of the edit had actually
    been applied.

    regen-cockpit-schema.py avoids this class of failure entirely by
    trampolining into claude-klabauter's source tree via CLAUDE_KLABAUTER_ROOT/PYTHONPATH rather
    than the published mirror; this trampoline instead resolves via
    require_dispatch_engine_on_path() (see _import_runner()) and so needs
    this explicit post-resolution check.

    Returns None if the check passes or cannot be performed (no local source
    to compare against). Otherwise returns a multi-line error string
    describing the mismatch; never raises, never prints.
    """
    import coordinator_core.ops.emit_artifact_shape_contract as resolved

    source_version = _source_contract_version()
    if source_version is None:
        return None
    resolved_version = getattr(resolved, "CONTRACT_VERSION", None)
    if source_version == resolved_version:
        return None

    source_root = pathlib.Path(__file__).resolve().parents[2]
    return (
        "refusing to emit: the resolved engine is not this repo's source tree.\n"
        f"source root: {source_root} (CONTRACT_VERSION={source_version!r})\n"
        f"resolved module: {getattr(resolved, '__file__', '<unknown>')} "
        f"(CONTRACT_VERSION={resolved_version!r})\n"
        "emitting from the resolved tree would publish its stale content and "
        "OSS-sanitized spec references with a zero exit.\n"
        "re-run with CLAUDE_KLABAUTER_ROOT / COORDINATOR_ENGINE_ROOT / REPO_CLAUDE_KLABAUTER "
        "pointed at this repo, or publish the engine first."
    )


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"emit-artifact-shape-contract: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"emit-artifact-shape-contract: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    # This is DoE-side data (schemas/ input, artifact-shape-contract/ output) that
    # the claude-klabauter module has no way to locate on its own; hand it over via env var
    # (see module docstring, and _resolve_coordinator_root()'s own docstring, for
    # why this is NOT derived from this script's own __file__ location).
    mismatch = _assert_resolved_engine_is_this_source()
    if mismatch is not None:
        print(f"emit-artifact-shape-contract: {mismatch}", file=sys.stderr)
        return 2

    coordinator_root = _resolve_coordinator_root()
    os.environ["EMIT_ARTIFACT_SHAPE_CONTRACT_COORDINATOR_ROOT"] = coordinator_root

    try:
        code = run_op_main(
            "coordinator_core.ops.emit_artifact_shape_contract", (sys.argv[1:] if argv is None else argv)
        )
    except ImportError as exc:
        print(
            f"emit-artifact-shape-contract: coordinator_core.ops.emit_artifact_shape_contract "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
