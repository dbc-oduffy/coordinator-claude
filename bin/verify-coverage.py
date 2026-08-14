#
# verify-coverage — CLI trampoline over claude-klabauter coordinator_core.ops.verify_coverage.
#
# Cross-reference integrity sweep for the coordinator-claude plugin tree: every
# `<plugin>:<name>` skill/agent/command reference, `subagent_type:` assignment,
# and worker bullet under a "## Worker Dispatch Recommendations" header must
# resolve to a real artifact on disk. Invoked from /update-docs Phase 11h2.
#
# Usage:
#   verify-coverage [--root <path>] [--sweep-root <path>] [--json] [--report-only]
#
# Options:
#   --root <path>        Plugin tree root (artifact discovery). Defaults to
#                         ~/.claude/.doe-root sentinel target, else the OSS
#                         mirror ~/.claude/plugins/coordinator-claude/.
#   --sweep-root <path>  Doc-sweep root (which .md files get scanned). Defaults
#                         to the invoking repo's cwd — deliberately NOT the
#                         plugin root, so a consumer repo's coverage pass never
#                         HALTs on DoE-claude's own archival drift.
#   --json                Emit machine-readable JSON instead of a markdown report.
#   --report-only         Always exit 0 even when violations exist.
#
# Exit codes (HARDENED per the 2026-07-17 porter-brief addendum A3/A3b — mirrors
# the sibling refresh-queries.py trampoline's dedicated-code precedent):
#   0 — clean (or --report-only)
#   1 — orphan reference(s) found (business fail, from the ported module)
#   2 — usage/configuration error (unknown flag, root/sweep-root not found —
#       also from the ported module's own main())
#   3 — TRANSPORT failure: CLAUDE_KLABAUTER_ROOT resolution or
#       coordinator_core.ops.verify_coverage import failure AT THIS trampoline
#       layer. Deliberately distinct from both CLI-usage (2) and business (1)
#       failure — a caller branching on exit code alone (e.g. /update-docs
#       Phase 11h2) must be able to tell "the claude-klabauter engine couldn't be
#       located" apart from "your flag/root was wrong" without parsing
#       stderr text. Phase 11h2 itself only checks nonzero (no per-code
#       branching found), so this change is exit-code-additive, not
#       contract-breaking for known callers.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
# for this shape. On Windows, this file's co-located `.cmd` twin wins via
# `PATHEXT` when invoked as a bareword, so the shebang is never read there; on
# macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
# via the extensionless name or a resolved-interpreter prefix, never a bareword
# `.py` through git-bash — git-bash DOES honor the shebang and would exec-127
# with no `python3` present. See the carve-out in DoE-claude's
# coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
# this wiki lives in the DoE-claude repo, not here).
#
# Port of: coordinator/bin/verify-coverage.js (retired on cutover; see git log)
# Spec backlink: tasks/2026-07-16-clean-slate-recon (BIG_PORT Wave B, item verify-coverage)

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the DR-276 runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here (this is not a hot per-commit path, but the
    logic is a plain module with no async/registry footprint, so direct
    import is both correct-shaped and strictly cheaper).

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than calling the op's `main` directly, so any paths it declares become a
    session scope-touch claim (verify_coverage is read-only today, but the
    seam is uniform across every trampoline over this route).
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
        print(f"verify-coverage: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(3)
    except ImportError as exc:
        print(
            f"verify-coverage: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    try:
        code = run_op_main("coordinator_core.ops.verify_coverage", sys.argv[1:])
    except ImportError as exc:
        print(
            f"verify-coverage: coordinator_core.ops.verify_coverage not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    sys.exit(code)


if __name__ == "__main__":
    main()
