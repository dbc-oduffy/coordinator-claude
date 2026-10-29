# claude-md-grant-cli — CLI trampoline over the engine
# coordinator_core.session.claude_md_grant (the session-scoped PM grant that
# lets a dispatched agent write a CLAUDE.md-class surface). Direct-import
# variant, mirroring coordinator/bin/tier-u-grant-cli's resolve/import/
# dispatch/exit shape; the argv grammar lives in claude_md_grant.main and is
# forwarded verbatim, never re-implemented here.
#
# An EM runs this once the PM approves a CLAUDE.md-class write, from the repo
# whose CLAUDE.md the write targets (the grant lands in that repo's
# .git/coordinator-sessions/<sid>/):
#   claude-md-grant-cli grant pm "<the PM's words>"
#
# Subcommands (argv[1] selects):
#   grant pm <note>   -> write the calling session's grant; note stored verbatim
#   read              -> print the calling session's raw grant record as JSON, if any
#   check             -> exit 0 iff the calling session holds a live grant
#
# Exit codes: 0/1 for the mapped bool-returning function, 2 on a usage or
# validation error, 3 (_TRANSPORT_FAIL) when the engine could not be
# reached — never silently degraded to 0/1.
from __future__ import annotations
"""claude-md-grant-cli — see the # comment block above for the purpose text
(the polyglot shebang line makes this triple-quoted string a discarded
expression statement, not the module __doc__ — same convention as
tier-u-grant-cli)."""

import sys

_TRANSPORT_FAIL = 3

_NAME = "claude-md-grant-cli"

_SUBCOMMANDS = "subcommands: grant pm <note> | read | check"

_REPO_HINT = "run from the repo whose CLAUDE.md the write targets"

_HELP_FLAGS = ("--help", "-h", "help")


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    import coordinator_core.session.claude_md_grant as _mod

    return _mod


def _usage_text() -> str:
    return f"usage: {_NAME} <subcommand> <args...>\n{_SUBCOMMANDS}\n{_REPO_HINT}"


def main(argv: list[str]) -> int:
    if not argv:
        print(_usage_text(), file=sys.stderr)
        return 2
    if argv[0] in _HELP_FLAGS:
        print(_usage_text())
        return 0

    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"{_NAME}: engine-root resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"{_NAME}: coordinator_core.session.claude_md_grant not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
