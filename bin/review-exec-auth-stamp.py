#       [--utterance <PM's verbatim words>] [--at <YYYY-MM-DD>]
#     always with execution_authorized_by: PM. MUTATING. Convergent —
#   stamp <plan-path> --by <who> --note <verbatim-note> [--at <YYYY-MM-DD>]
#     frontmatter, atomically. MUTATING. Idempotent — re-stamping with
#     sitting at. MUTATING (plan status only). Convergent — a plan already
#   restamp <plan-path> --by <witness> --reason <one line> [--at <YYYY-MM-DD>]
#     from_sha,note} quartet. MUTATING. Fires no rung. Refuses a PM-shaped
from __future__ import annotations
"""review-exec-auth-stamp — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as pickup-assemble/archive-stamp-cli)."""

import os
import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.review_assemble.exec_auth_stamp as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"review-exec-auth-stamp: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"review-exec-auth-stamp: coordinator_core.review_assemble.exec_auth_stamp not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
