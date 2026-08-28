# tier-u-grant-cli — CLI trampoline over claude-klabauter
# coordinator_core.session.grant (the Tier-U full-suite authorization-grant
# writer/reader — DR-088 layer 5: "Authorization grant — Tier U requires a
# live token; qualifying ceremonies write an implicit one."). Direct-import
# variant, mirroring coordinator/bin/session-liveness-cli's resolve/import/
# dispatch/exit shape (this CLI's reader leg calls straight through to
# coordinator_core.session.liveness the same way that CLI does, so the two
# stay structurally identical).
#
# DoE's ceremonies (/workday-complete, /workweek-complete, /merging-to-main)
# and skills invoke this BY NAME as an entrypoint — per the 2026-07-22 ruling
# that a skill links to an entrypoint rather than carrying a command payload
# (see the memo this CLI is specced from). The DR-088 layer-5 PreToolUse(Bash)
# guard (coordinator_core/bash_guards/check_test_suite_invocation.py's
# `_tier_u_grant` grant leg) is wired via DIRECT IN-PROCESS IMPORT of
# `coordinator_core.session.grant.check_tier_u_grant` — it does not shell out
# to this CLI's `check` subcommand. This CLI's `check` subcommand remains the
# entrypoint for shell callers (e.g. a skill or a human at a terminal) that
# need the same predicate outside a Python process — see
# coordinator_core/session/grant.py's module docstring for the ownership
# split.
#
# Subcommands (argv[1] selects; remaining argv forwarded to the mapped
# coordinator_core.session.grant function):
#   grant <granted_by> <note> [--ceremony <name>]
#                                              -> grant.write_tier_u_grant(...) bool->exit
#   read                                       -> grant.read_tier_u_grant(): prints the
#                                                  raw grant record as one line of JSON if
#                                                  present, prints nothing if absent/
#                                                  unreadable/malformed; always exit 0
#                                                  (informational — this is NOT the
#                                                  authorization predicate, see `check`)
#   check                                      -> grant.check_tier_u_grant(): the
#                                                  liveness-gated authorization boolean —
#                                                  the one a guard calls. bool->exit
#   revoke [--only-ceremony <name>]            -> grant.revoke_tier_u_grant(): hands the
#                                                  calling session's own grant back
#                                                  (unlink, never a glob). Idempotent —
#                                                  revoking an absent grant is success.
#                                                  --only-ceremony is the GUARDED handback
#                                                  every ceremony must use: unlinks only a
#                                                  grant whose granted_by == "ceremony" and
#                                                  whose ceremony names <name>, leaving a PM
#                                                  grant (or another ceremony's, under
#                                                  workweek->merge nesting) alone and still
#                                                  exiting 0. bool->exit
#
# Exit codes: the mapped bool-returning function maps True->0, False->1
# (matches session-liveness-cli's / session-claim-cli's convention). A
# a missing/unresolvable engine root or an ImportError (this trampoline's own
# transport failure) exits 3 (_TRANSPORT_FAIL — "the claude-klabauter engine could not
# be reached," never silently degraded to 0/1). A usage error (missing/
# unknown subcommand, wrong arity, an invalid `grant` enum/cross-field value
# caught as ValueError) exits 2.
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
        # Cold shell call: coordinator_core is not on the path yet. The
        # in-process callers (workweek_complete.apply loads this file as a
        # module and calls main()) already have it imported, so they never
        # pay the engine-root resolution below.
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
