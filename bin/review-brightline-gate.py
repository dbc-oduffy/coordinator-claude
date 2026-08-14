# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""review-brightline-gate.py — mechanical partition-vs-single-reviewer gate.

CLI trampoline over claude-klabauter coordinator_core.ops.review_brightline_gate, used
at /workstream-complete Step 2.9 to decide whether a diff must be reviewed
as a partitioned multi-chunk slice or a single reviewer suffices. Computes
loc/commits/surfaces over a git range and prints a
VERDICT={PARTITION-MANDATORY|single-reviewer-ok} line; any one threshold
(loc>=500, commits>=5, surfaces>=4) trips PARTITION-MANDATORY.
"""
from __future__ import annotations
# review-brightline-gate.py — CLI trampoline over claude-klabauter coordinator_core.ops.review_brightline_gate.
#
# Mechanical partition-vs-single gate for /workstream-complete Step 2.9. Prints
# `range=… loc=… commits=… surfaces=… files=… [filtered_to=…] VERDICT={PARTITION-MANDATORY|single-reviewer-ok}`.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Usage:
#   review-brightline-gate.py [--session-id <id>] [<git-range>]
#     (range default: `git merge-base origin/main HEAD`..HEAD)
#
# Thresholds (any one trips PARTITION-MANDATORY): loc>=500 (gross insertions+
# deletions), commits>=5, surfaces>=4.
#
# Exit codes: 0 — verdict printed (incl. vacuous --session-id zero-match).
# 1 — usage error OR die-silent gate (see claude-klabauter module's negative-spec
# docstring for the pre-existing bash-oracle quirk this reproduces).
#
# Spec backlink: docs/plans/2026-06-15-brightline-session-scope-fix.md § C3
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.review_brightline_gate import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"review-brightline-gate.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"review-brightline-gate.py: coordinator_core.ops.review_brightline_gate not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
