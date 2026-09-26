from __future__ import annotations

import sys
from typing import FrozenSet


def parse_repo_root_argv(
    argv: list[str],
    *,
    prog: str,
    usage: str,
    known_flags: FrozenSet[str] = frozenset(),
    max_positional: int = 1,
) -> tuple[list[str], set[str], "int | None"]:
    positional: list[str] = []
    flags_seen: set[str] = set()
    for arg in argv:
        if arg in ("-h", "--help"):
            print(usage)
            return [], flags_seen, 0
        if arg.startswith("-"):
            if arg in known_flags:
                flags_seen.add(arg)
                continue
            print(f"{prog}: unrecognized argument: {arg!r}", file=sys.stderr)
            print(usage, file=sys.stderr)
            return [], flags_seen, 2
        positional.append(arg)
    if len(positional) > max_positional:
        print(
            f"{prog}: too many positional arguments (expected at most "
            f"{max_positional}, got {len(positional)}: {positional!r})",
            file=sys.stderr,
        )
        print(usage, file=sys.stderr)
        return [], flags_seen, 2
    return positional, flags_seen, None
