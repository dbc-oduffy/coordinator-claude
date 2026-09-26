# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations
# /workstream-complete ships only the terminal SUCCESSOR handoff of a forked
# Join key: the DELIVERABLE SPINE (deliverable_id -> rollup-derive.py), NOT a
# resolved SCRIPT_DIR-relative (this file's own grandparent directory) — NOT
# `${SCRIPT_DIR}/../../state/handoffs` resolution exactly.

import os
import sys

# SCRIPT_DIR-relative repo root — this file lives at <repo>/coordinator/bin/,
# `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` +
# `HANDOFFS_DIR="${SCRIPT_DIR}/../../state/handoffs"` derivation exactly —
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
