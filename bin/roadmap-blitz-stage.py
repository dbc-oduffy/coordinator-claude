# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
roadmap-blitz-stage — CLI trampoline over claude-klabauter coordinator_core.roadmap.blitz_stage.

Phase 2 of a roadmap blitz in one call: scaffold and number the roadmap's stubs,
report their size against the M/L band, run audit-roadmap, and freeze the gate
report plan-blitz consumes. The same work the `roadmap.blitz_stage` op does.

Usage:
  roadmap-blitz-stage <roadmap-dir-or-file> [--edges <edges-file>] [--branch <b>] [--repo-root <dir>]

Exit 0 staged and audit passed; 1 audit failed; 2 usage error or refused roadmap;
3 engine-root resolution/import failure.
"""

from __future__ import annotations

import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.roadmap.blitz_stage import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"roadmap-blitz-stage: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(f"roadmap-blitz-stage: coordinator_core.roadmap.blitz_stage not importable: {exc}", file=sys.stderr)
        return 3

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
