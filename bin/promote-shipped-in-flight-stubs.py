# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""promote-shipped-in-flight-stubs.py — closes stranded origin fork-point spinoff-roadmap stubs.

Interim /workday-start closer: CLI trampoline over claude-klabauter
coordinator_core.ops.promote_shipped_in_flight_stubs. /workstream-complete only
ships the terminal successor handoff of a forked spinoff-roadmap lineage,
leaving the origin fork-point stub frozen at deployment_state:in_flight even
after its deliverable ships on origin/main — this script finds those stranded
stubs (joined on the deliverable spine, not a predecessor-walk) and promotes
them to terminal shipped.
"""
from __future__ import annotations
# promote-shipped-in-flight-stubs.py — interim /workday-start closer: CLI
# trampoline over claude-klabauter coordinator_core.ops.promote_shipped_in_flight_stubs.
#
# Promotes clean-fork consumed spinoff-roadmap stubs whose deliverable has
# SHIPPED on origin/main from deployment_state:in_flight to terminal shipped.
# /workstream-complete ships only the terminal SUCCESSOR handoff of a forked
# spinoff-roadmap lineage — it never touches the origin fork-point stub, which
# is left frozen at deployment_state:in_flight forever even after the
# deliverable it forked from ships. This closer finds those stranded origin
# stubs and closes them out.
#
# Join key: the DELIVERABLE SPINE (deliverable_id -> rollup-derive.py), NOT a
# predecessor-walk. rollup-derive.py re-derives ship-state on demand from
# `Resolves: <deliverable_id>` commit trailers — it is the sole shipped/
# not-shipped oracle here.
#
# Usage:
#   promote-shipped-in-flight-stubs.py
#
# No CLI arguments. Scans <repo>/state/handoffs/*.md, where <repo> is
# resolved SCRIPT_DIR-relative (this file's own grandparent directory) — NOT
# the invoking shell's cwd — matching the retired bash body's
# `${SCRIPT_DIR}/../../state/handoffs` resolution exactly.
#
# Exit codes: propagated verbatim from coordinator_core.ops.
# promote_shipped_in_flight_stubs.main() — see that module's own docstring
# for the AC14 split. In short: 0 when there is nothing to do or every
# candidate legitimately has no resolving commits yet (quiet), non-zero
# when a shipped candidate's stamp write failed (loud). A claude-klabauter-link/import
# failure at THIS trampoline layer still degrades to exit 0 with a loud
# stderr diagnostic (never-block posture) — that failure class is orthogonal
# to the ported module's own business-outcome exit code.
#
# Negative-spec: does NOT implement a predecessor-walk or multi-signal
# lineage matcher. The only join is deliverable_id -> rollup-derive.py's
# four-token contract.
#
# Spec: docs/plans/2026-07-11-consumed-in-flight-stub-shipped-stamp-propagation.md (C1)
# Port of: coordinator/bin/promote-shipped-in-flight-stubs.py (bash body retired on cutover; see git log)
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md

import os
import sys

# SCRIPT_DIR-relative repo root — this file lives at <repo>/coordinator/bin/,
# so its grandparent is <repo>. Matches the retired bash body's
# `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` +
# `HANDOFFS_DIR="${SCRIPT_DIR}/../../state/handoffs"` derivation exactly —
# invocation-location-independent, NOT cwd-relative.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DOE_REPO_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: NOT routed through `coordinator_core.cli_entry.run_op_main` —
    this call passes a `repo_root=` keyword the ported `main(argv, *,
    repo_root=None)` needs for its SCRIPT_DIR-relative (not cwd-relative)
    resolution, and `run_op_main` only supports `entrypoint(argv)` with no
    room for extra kwargs; forcing this through it would silently drop
    `repo_root` and regress resolution to cwd-relative. Instead this
    trampoline owns its own orchestration and wraps the call in
    `coordinator_core.cli_entry.recording_declared_writes`, the sanctioned
    seam for exactly this case (see that context manager's own docstring).
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import recording_declared_writes
    from coordinator_core.ops.promote_shipped_in_flight_stubs import main as _op_main

    return _op_main, recording_declared_writes


def main(argv: "list[str] | None" = None) -> int:
    # Never-block posture (this is a best-effort /workday-start closer, not a
    # fail-loud gate): a claude-klabauter-link failure degrades to exit 0 with a loud
    # stderr diagnostic, matching the ported module's own always-exit-0
    # contract rather than surfacing a distinct transport-failure code.
    try:
        op_main, recording_declared_writes = _import_main()
    except RuntimeError as exc:
        print(
            f"promote-shipped-in-flight-stubs.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            "promote-shipped-in-flight-stubs.py: "
            f"coordinator_core.ops.promote_shipped_in_flight_stubs not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    with recording_declared_writes(cwd=_DOE_REPO_ROOT):
        code = op_main((sys.argv[1:] if argv is None else argv), repo_root=_DOE_REPO_ROOT)

    return code


if __name__ == "__main__":
    sys.exit(main())
