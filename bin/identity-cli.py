# identity-cli — CLI trampoline over coordinator/lib/session/identity.py's pure
# teammate-identity-resolution functions (resolve_subagent_identity,
# cs_build_canonical_agent_id, cs_canonical_agent_id_format_ok).
# Port of: coordinator/lib/session/identity.sh (6fb5fb37, 2026-07-22)
#
# No engine-root / coordinator_core dependency: identity.py is pure logic
# (no filesystem I/O, no engine-side state), so this trampoline imports it
# directly from the co-located coordinator/lib/session/ tree -- unlike
# session-liveness-cli / session-claim-cli, there is no claude-klabauter seam here.
#
# Subcommands (argv[1] selects; remaining argv forwarded to the mapped
# coordinator/lib/session/identity.py function):
#   resolve-subagent-identity <agent_id> <session_id>
#       -> identity.resolve_subagent_identity(...); prints result (may be
#          empty string), always exits 0 (mirrors the bash echo "" fail-closed
#          convention -- callers gate on the printed value, not exit code).
#   build-canonical-agent-id <name> <short_session>
#       -> identity.cs_build_canonical_agent_id(...); prints result, exit 0.
#          Exits 2 with a stderr message on empty name/short_session (mirrors
#          bash's ${1:?...} parameter-expansion hard-fail).
#   format-ok <agent_id>
#       -> identity.cs_canonical_agent_id_format_ok(...): bool->exit
#          (0 = matches, 1 = does not match).
#
# Exit codes: resolve-subagent-identity and build-canonical-agent-id (success
# path) always exit 0 -- their contract is "print the answer, empty string on
# no-match", not "boolean via exit code". format-ok is the one bool->exit
# subcommand. A usage error (missing/unknown subcommand, wrong arity) exits 2.
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "session"
)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import identity as mod  # noqa: E402

_SUBCOMMANDS = (
    "subcommands: resolve-subagent-identity | build-canonical-agent-id | format-ok"
)

_HELP_FLAGS = ("--help", "-h", "help")


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    if not argv:
        return _usage("identity-cli")
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(f"usage: identity-cli <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    if subcmd == "resolve-subagent-identity":
        if len(rest) != 2:
            return _usage(
                "identity-cli resolve-subagent-identity <agent_id> <session_id>"
            )
        print(mod.resolve_subagent_identity(rest[0], rest[1]))
        return 0

    if subcmd == "build-canonical-agent-id":
        if len(rest) != 2:
            return _usage(
                "identity-cli build-canonical-agent-id <name> <short_session>"
            )
        try:
            print(mod.cs_build_canonical_agent_id(rest[0], rest[1]))
        except ValueError as exc:
            print(f"identity-cli: build-canonical-agent-id: {exc}", file=sys.stderr)
            return 2
        return 0

    if subcmd == "format-ok":
        if len(rest) != 1:
            return _usage("identity-cli format-ok <agent_id>")
        return 0 if mod.cs_canonical_agent_id_format_ok(rest[0]) else 1

    print(f"identity-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("identity-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
