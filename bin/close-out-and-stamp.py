#     path plus the plan doc itself. MUTATING BY DEFAULT.
#     UNCHANGED and still mutates, so no existing caller (`/execute-plan`
# EXIT_OK/EXIT_BUSINESS_FAIL/EXIT_USAGE constants -- see the module for the
from __future__ import annotations
"""close-out-and-stamp — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as pickup-assemble/archive-stamp-cli/review-exec-auth-stamp)."""

import os
import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.execute_plan_assemble.close_out_and_stamp as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"close-out-and-stamp: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"close-out-and-stamp: coordinator_core.execute_plan_assemble.close_out_and_stamp "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
