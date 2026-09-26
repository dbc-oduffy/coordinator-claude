#     closed `_CLI_DISPATCH` table, per-directive gated on the judgment
#   1 — a directive raised (APPLY_EXIT_PARTIAL_MUTATION) or the dispatch was
#       (APPLY_EXIT_HALTED_AT_JUDGMENT).
from __future__ import annotations
"""execute-plan-assemble — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ --
same convention as close-out-and-stamp/pickup-assemble/archive-stamp-cli)."""

import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()  # noqa: F841
    import coordinator_core.execute_plan_assemble.apply as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"execute-plan-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"execute-plan-assemble: coordinator_core.execute_plan_assemble.apply "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
