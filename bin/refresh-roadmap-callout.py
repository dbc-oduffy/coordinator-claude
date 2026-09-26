# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""refresh-roadmap-callout.py — refreshes a roadmap-callout sentinel block in place.

CLI trampoline over claude-klabauter coordinator_core.ops.refresh_roadmap_callout, per
DR-047 (DoE owns contract/generator, claude-klabauter owns engine). Validates a
roadmap_id against the STUB-INDEX allowlist, checks the invoking coordinator
root is trusted, and delegates the actual markdown rewrite to
refresh-queries.py's --files mode. Invoked at /pickup and
/workstream-complete to keep roadmap callouts current.
"""
from __future__ import annotations
# validation, STUB-INDEX resolution, trust-guard, and the
#                docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md (R1 DOE-PORT)
import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.refresh_roadmap_callout import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"refresh-roadmap-callout.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"refresh-roadmap-callout.sh: coordinator_core.ops.refresh_roadmap_callout not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    # rather than routing through run_op_main — the STUB-INDEX.md path the op
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        code = op_main((sys.argv[1:] if argv is None else argv), self_commit=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
