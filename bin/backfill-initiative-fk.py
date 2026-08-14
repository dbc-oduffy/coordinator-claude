# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""backfill-initiative-fk.py — CLI trampoline over the claude-klabauter initiative-FK backfill op.

One-shot batch-attach tool: reads (artifact-path, initiative-id) TSV pairs from
a file or stdin and attaches the `initiative:` FK to each artifact's YAML
frontmatter via the sibling coordinator-initiative CLI. Idempotent —
re-running over already-attached pairs is a no-op. Resolves CLAUDE_KLABAUTER_ROOT and
delegates to coordinator_core.ops.backfill_initiative_fk for the actual
attach loop.
"""
# backfill-initiative-fk.sh — CLI trampoline over claude-klabauter
# coordinator_core.ops.backfill_initiative_fk.
#
# Direct-import trampoline (port-template variant #1): no `register_op`, no IPC
# — this file resolves CLAUDE_KLABAUTER_ROOT, imports the ported module in-process, and
# calls its main() directly. No live caller invokes this script today (one-shot
# migration tool, per tasks/2026-07-15-sh-inventory/slice-00.md); the filename
# and CLI contract are kept byte-identical regardless, per the port template's
# zero-caller-repoint convention.
#
# Purpose: idempotent batch-attach tool. Reads (artifact-path, initiative-id)
# TSV pairs from a file or stdin and attaches the `initiative:` FK to each
# artifact's YAML frontmatter via the sibling `coordinator-initiative attach`
# CLI (a python3 script, per coordinator_core/ops/backfill_initiative_fk.py).
#
# Usage:
#   backfill-initiative-fk.sh [mapping.tsv]     # read from file
#   cat mapping.tsv | backfill-initiative-fk.sh  # read from stdin
#   backfill-initiative-fk.sh -                  # explicit stdin
#
# Exit codes:
#   0  success — all pairs attached or skipped, zero errors.
#   1  business failure — coordinator-initiative missing/not-executable, python3 not
#      on PATH, mapping file not found, lock held by a live concurrent instance,
#      or errors > 0 after processing all pairs.
#   2  CLAUDE-KLABAUTER transport failure — CLAUDE_KLABAUTER_ROOT resolution or
#      coordinator_core.ops.backfill_initiative_fk import failed BEFORE the
#      ported module's own main() was reached. A DEDICATED code, per porter
#      addendum §3b: this tool is a mutating, fail-loud batch CLI (not a
#      best-effort/never-block hook like coordinator-auto-push), so a claude-klabauter
#      outage must be distinguishable from a legitimate business
#      pass/fail (0/1) rather than degrading silently to exit 0.
#
# Spec backlink: DoE-claude:pln-ceremony-as-pipeline-2-land-th-aa5ace § F4 (AC8)
# Ported to coordinator_core/ops/backfill_initiative_fk.py, co-located pytest
# test_backfill_initiative_fk.py (claude-klabauter-resident).

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_EXIT_TRANSPORT_FAILURE = 2


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the DR-276 runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"backfill-initiative-fk.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(_EXIT_TRANSPORT_FAILURE)
    except ImportError as exc:
        print(
            f"backfill-initiative-fk.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_EXIT_TRANSPORT_FAILURE)

    # script_dir is THIS trampoline's own bin/ directory — the ported module
    # resolves the sibling `coordinator-initiative` executable relative to it,
    # mirroring the bash oracle's SCRIPT_DIR-relative resolution exactly.
    # `run_op_main` only forwards argv, with no channel for a `script_dir=`
    # kwarg, so it is threaded through as an explicit `--script-dir` argv
    # flag instead (see the op's own DR-276 note on `main`).
    script_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        code = run_op_main(
            "coordinator_core.ops.backfill_initiative_fk",
            [*sys.argv[1:], "--script-dir", script_dir],
        )
    except ImportError as exc:
        print(
            f"backfill-initiative-fk.sh: coordinator_core.ops.backfill_initiative_fk "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_EXIT_TRANSPORT_FAILURE)

    sys.exit(code)


if __name__ == "__main__":
    main()
