# directives/judgment_points/decisions/narration/next_move). READ-ONLY —
from __future__ import annotations
"""learn-lessons-reconcile-candidates — see the # comment block above for
the RAG-bait purpose text (the polyglot shebang line above makes THIS
triple-quoted string a silently-discarded expression statement, not the
module __doc__ — same convention as baton-assemble/pickup-assemble)."""

import os
import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.learn_lessons_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"learn-lessons-reconcile-candidates: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"learn-lessons-reconcile-candidates: coordinator_core.learn_lessons_assemble not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
