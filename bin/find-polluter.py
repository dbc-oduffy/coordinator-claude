# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
find-polluter.py — CLI trampoline over claude-klabauter coordinator_core.ops.find_polluter.

Bisection-based test-pollution finder: given a filesystem path that should NOT
exist and a glob test-pattern, runs `npm test <file>` once per matched test
file (in sorted order) until the path springs into existence, then reports the
polluter.

Usage: find-polluter.py <file_or_dir_to_check> <test_pattern>
Example: find-polluter.py '.git' 'src/**/*.test.ts'

Port source: coordinator/bin/find-polluter.py (this file; original bash body
retired on cutover — see git log). Full reimplementation:
../claude-klabauter/coordinator_core/ops/find_polluter.py
Test: ../claude-klabauter/coordinator_core/ops/test_find_polluter.py (pytest,
Claude-klabauter-resident).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_run_op_main():
    """Resolve the engine root and import `run_op_main` (DR-276: routes the op
    in-process through `coordinator_core.cli_entry` rather than a plain
    `_import_main()` + `sys.exit(op_main(argv))` tail, so any path the op
    declares via `declare_write` becomes a session scope-touch claim instead
    of an unclaimed orphan at the `scoped_git_commit` sink)."""
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"find-polluter.py: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"find-polluter.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        code = run_op_main("coordinator_core.ops.find_polluter", sys.argv[1:])
    except ImportError as exc:
        print(f"find-polluter.py: coordinator_core.ops.find_polluter not importable: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
