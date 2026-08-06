#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""query-completions.py — CLI trampoline for querying the completion-log.

Thin wrapper over claude-klabauter coordinator_core.ops.query_completions. Forwards all
arguments verbatim to query-records.js with --type completion pre-set, giving
callers a --type-free entry point onto the completion-log record store.
"""
from __future__ import annotations
# query-completions.py — CLI trampoline over claude-klabauter coordinator_core.ops.query_completions.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 2
#
# Thin wrapper for querying completion-log entries. All arguments are forwarded
# verbatim to query-records.js with --type completion pre-set (see the claude-klabauter
# module's docstring for the full contract). See query-records.js --help for
# option documentation.
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than calling the op's `main` directly, so any paths it declares become a
    session scope-touch claim (query_completions is read-only today, but the
    seam is uniform across every trampoline over this route)."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
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
