#!/usr/bin/env python3
"""detect-existing-claude-home.py — three-state classifier for Claude home directories.

Thin, argv-passthrough veneer over claude-klabauter's
coordinator_core.ops.detect_existing_claude_home. Classifies a target
Claude home directory as pristine / used-vanilla / configured, driving the
install flow's track A/B fork. Read-only, idempotent; degrades to
"pristine" on an empty/nonexistent target rather than failing.
"""
# lib/detect-existing-claude-home.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.detect_existing_claude_home (three-state classifier
# for Claude home directories: pristine / used-vanilla / configured).
#
# Full behavioral spec, decision-tier ordering, and the three-state rationale
# now live in the claude-klabauter module's own docstring (this file is a thin,
# argv-passthrough veneer) — see coordinator_core/ops/detect_existing_claude_home.py
# in claude-klabauter. Read-only, idempotent contract carries over unchanged.
#
# Usage:
#   detect-existing-claude-home.py [<target-dir>]
#   CLAUDE_CONFIG_DIR=<dir> detect-existing-claude-home.py
#
# Output (stdout): one line of the form:
#   state=<pristine|used-vanilla|configured> track=<A|B> reason: <human explanation>
#
# Exit codes:
#   0 — always. Business classification never fails (it degrades to
#       "pristine" on an empty/nonexistent target). A claude-klabauter-link (transport)
#       failure ALSO exits 0, loud on stderr — this is a best-effort,
#       never-block advisory classifier (both callers already treat a
#       non-zero exit as "continue anyway": install-maximalist.py warns and
#       proceeds; install.md's structural fork is agent-read, not
#       gate-blocking) — so there is no dedicated transport-failure code to
#       collide with a business code (rule per porter-brief addendum § 3b).
#
# Spec backlink: docs/plans/2026-07-16-bash-to-naked-python-engine-migration.md
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here: the classifier is a handful of filesystem
    stat/listdir calls, and routing it through a JSON-RPC envelope would add a
    subprocess hop for a call this cheap.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.detect_existing_claude_home import main as _op_main

    return _op_main


def main() -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # CLAUDE_KLABAUTER_ROOT resolution failed. This is a best-effort advisory
        # classifier — never block the caller's install flow.
        print(
            f"detect-existing-claude-home.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            "detect-existing-claude-home.py: "
            f"coordinator_core.ops.detect_existing_claude_home not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return op_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
