# `_tier_u_grant` grant leg) is wired via DIRECT IN-PROCESS IMPORT of
# transport failure) exits 3 (_TRANSPORT_FAIL — "the claude-klabauter engine could not
from __future__ import annotations
"""tier-u-grant-cli — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as session-liveness-cli / session-claim-cli)."""

import json
import os
import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.session.grant as _mod

    return _mod


_SUBCOMMANDS = "subcommands: grant | read | check | revoke [--only-ceremony <name>]"

_HELP_FLAGS = ("--help", "-h", "help")


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def _bool_to_exit(result: bool) -> int:
    return 0 if result else 1


def _grant_directive_module():
    """`coordinator_core.session.grant_directive` — the one owner of the
    `grant`/`revoke` argv grammar, shared with the ceremony assemblers that
    dispatch these same directives in-process. Resolved through the same
    engine-root trampoline as `_import_module`, so a missing engine still
    exits `_TRANSPORT_FAIL` rather than ImportError-ing here."""
    try:
        import coordinator_core.session.grant_directive as _mod
    except ImportError:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        claude_klabauter_root = require_dispatch_engine_on_path()
        import coordinator_core.session.grant_directive as _mod

    return _mod


def main(argv: list[str]) -> int:
    if not argv:
        return _usage("tier-u-grant-cli")
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(f"usage: tier-u-grant-cli <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"tier-u-grant-cli: engine-root resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"tier-u-grant-cli: coordinator_core.session.grant not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    if subcmd in ("grant", "revoke"):
        try:
            directive = _grant_directive_module()
        except (RuntimeError, ImportError) as exc:
            print(
                f"tier-u-grant-cli: coordinator_core.session.grant_directive not "
                f"importable: {exc}",
                file=sys.stderr,
            )
            return _TRANSPORT_FAIL
        code, message = directive.run_grant_directive([subcmd, *rest])
        if message:
            print(f"tier-u-grant-cli: {message}", file=sys.stderr)
        return code

    if subcmd == "read":
        if rest:
            return _usage("tier-u-grant-cli read")
        record = mod.read_tier_u_grant()
        if record is not None:
            print(json.dumps(record))
        return 0

    if subcmd == "check":
        if rest:
            return _usage("tier-u-grant-cli check")
        granted, _record = mod.check_tier_u_grant()
        return _bool_to_exit(granted)

    print(f"tier-u-grant-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("tier-u-grant-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
