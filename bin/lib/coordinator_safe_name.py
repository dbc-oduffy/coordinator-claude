from __future__ import annotations

import datetime
import os
import re
import sys

CSN_ILLEGAL_CHARS = ':?*<>|"\\/'


def csn_timestamp(mode: str = "--now", file: str | None = None) -> str:
    """Emit a UTC timestamp in the colon-free form YYYY-MM-DDTHH-MM-SSZ.

    mode="--now" (default): current time.
    mode="--mtime": derive from `file`'s mtime (os.stat — platform-portable,
      replaces the bash oracle's BSD-stat/GNU-stat/date-r 3-way probe chain
      since Python's os.stat().st_mtime is already cross-platform).
    Raises ValueError on a genuine failure (unknown mode, missing/unreadable
    file for --mtime) — callers map this to a non-zero exit, matching the
    bash oracle's `return 1`.
    """
    if mode not in ("--now", "--mtime"):
        raise ValueError(f'csn_timestamp: unknown option "{mode}"')

    if mode == "--now":
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    if not file:
        raise ValueError("csn_timestamp: --mtime requires a file argument")
    try:
        epoch = os.stat(file).st_mtime
    except OSError as exc:
        raise ValueError(f'csn_timestamp: cannot read mtime of "{file}"') from exc

    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H-%M-%SZ"
    )


def csn_slug(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = slug[:40]
    slug = slug.rstrip("-")
    return slug


def csn_check(component: str) -> tuple[bool, str]:
    if component.endswith("."):
        return False, f'trailing dot in "{component}"'
    if component.endswith(" "):
        return False, f'trailing space in "{component}"'

    for ch in CSN_ILLEGAL_CHARS:
        if ch in component:
            display = '\\"' if ch == '"' else ch
            return False, f'illegal char "{display}" in "{component}"'

    for ch in component:
        cp = ord(ch)
        if cp <= 0x1F or cp == 0x7F:
            return False, f'control character in "{component}"'

    return True, ""


_USAGE = """Usage: coordinator-safe-name <timestamp|slug|check> [args...]
"""


def main(argv: list[str]) -> int:
    subcommand = argv[1] if len(argv) > 1 else ""
    rest = argv[2:]

    if subcommand in ("--help", "-h"):
        print(_USAGE, end="")
        return 0

    if subcommand == "timestamp":
        mode = "--now"
        file = None
        if rest:
            if rest[0] == "--now":
                mode = "--now"
            elif rest[0] == "--mtime":
                mode = "--mtime"
                file = rest[1] if len(rest) > 1 else None
            else:
                print(f'csn_timestamp: unknown option "{rest[0]}"', file=sys.stderr)
                print("Usage: csn_timestamp [--now | --mtime <file>]", file=sys.stderr)
                return 1
        try:
            print(csn_timestamp(mode, file))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if subcommand == "slug":
        text = rest[0] if rest else ""
        print(csn_slug(text))
        return 0

    if subcommand == "check":
        component = rest[0] if rest else ""
        ok, reason = csn_check(component)
        if not ok:
            print(f"csn_check: {reason}", file=sys.stderr)
            return 1
        return 0

    if subcommand == "check-paths":
        found = False
        for raw_path in sys.stdin:
            path = raw_path.rstrip("\n")
            if not path:
                continue
            for component in path.split("/"):
                if not component:
                    continue
                ok, _reason = csn_check(component)
                if not ok:
                    print(
                        f'ILLEGAL PATH: {path}  (component "{component}" '
                        "contains an NTFS-illegal char)",
                        file=sys.stderr,
                    )
                    found = True
        return 1 if found else 0

    print(_USAGE, end="", file=sys.stderr)
    if subcommand:
        print(f'coordinator-safe-name: unknown subcommand "{subcommand}"', file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
