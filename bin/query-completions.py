# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""query-completions.py — CLI trampoline for querying the completion-log.

Thin wrapper over claude-klabauter coordinator_core.ops.query_completions, giving callers
a --type-free entry point onto the completion-log record store. All arguments
are forwarded verbatim to that op via coordinator_core.cli_entry.run_op_main
(DR-276).

Negative-spec: does NOT shell out to a Node oracle. Earlier revisions of this
docstring described forwarding to `query-records.js --type completion`; that
path was retired with the rest of the JS read layer and no claude-klabauter CLI may
reintroduce a Node runtime dependency on this seam.
"""
from __future__ import annotations
# query-completions.py — CLI trampoline over claude-klabauter coordinator_core.ops.query_completions.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 2
#
# Thin wrapper for querying completion-log entries. All arguments are forwarded
# verbatim to coordinator_core.ops.query_completions (see the claude-klabauter module's
# docstring for the full contract). Run this CLI with --help for option
# documentation.
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than calling the op's `main` directly, so any paths it declares become a
    session scope-touch claim (query_completions is read-only today, but the
    seam is uniform across every trampoline over this route)."""
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"query-completions.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"query-completions.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.query_completions", sys.argv[1:])
    except ImportError as exc:
        print(f"query-completions.py: coordinator_core.ops.query_completions not importable: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
