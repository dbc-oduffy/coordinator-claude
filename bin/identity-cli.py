from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "session"
)

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)
    _BOOTSTRAP_DONE = True


_SUBCOMMANDS = (
    "subcommands: resolve-subagent-identity | build-canonical-agent-id | format-ok"
)

_HELP_FLAGS = ("--help", "-h", "help")


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    _bootstrap_engine()
    import identity as mod

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
