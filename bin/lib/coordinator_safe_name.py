"""lib/coordinator_safe_name.py — cross-platform safe filename component primitives.

Port of: coordinator-safe-name.sh (DoE 721a71f4, 2026-07-21). Defines the canonical NTFS-illegal charset and
three pure functions (csn_timestamp, csn_slug, csn_check) plus a `main()` CLI
dispatcher, importable by any consumer so the NTFS-illegal-charset logic
lives in exactly one place. Known importers: the `coordinator-safe-name` CLI
(this directory's sibling bin/ entrypoint) and
check-no-illegal-paths.py (sibling chunk E3-b), which imports `csn_check`
directly in-process rather than shelling out.

Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § seam 1
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E3-c)

PURPOSE: canonical single source of truth for the NTFS-illegal charset a
filename component must avoid to survive a `git checkout` on Windows (NTFS /
VFAT). `U+F03A` (private-use full-width colon) exists precisely because the
real colon `:` (U+003A) is the Windows ADS separator. Trailing dot and
trailing space are also NTFS-illegal even though they are not characters per
se — NTFS silently strips them, breaking the path.

Negative-spec: does NOT resolve its own file location for path-derivation
purposes (no path-resolution side effects beyond `__file__` module import
machinery) — pure functions + constants only, mirroring the bash oracle's
no-self-location contract.
"""
from __future__ import annotations

import datetime
import os
import re
import sys

# ---------------------------------------------------------------------------
# Canonical NTFS-illegal charset (the SoT for every consumer)
# ---------------------------------------------------------------------------
# Illegal chars: : ? * < > | " \ /
# Also illegal: ASCII control chars (0x00-0x1F, 0x7F DEL)
# Also illegal: trailing dot or trailing space (not chars, but structural rules)
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
    """Emit a [a-z0-9-]-only slug, <=40 chars, no leading/trailing hyphen.

    Mirrors coordinator-doc-new._slug_from_title and
    coordinator-lesson-promote._slug_from_title (independent, pre-existing
    Python impls — not refactored by this port). This function is the
    canonical SoT for shell/subprocess-style slug generation.
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = slug[:40]
    slug = slug.rstrip("-")
    return slug


def csn_check(component: str) -> tuple[bool, str]:
    """Returns (ok, reason). ok=True when `component` is safe for NTFS,
    macOS HFS+, Linux ext4, and Git-Bash checkout. ok=False + a reason string
    naming the offending char/rule otherwise. This is the canonical predicate
    reused by the illegal-filename guard and the check-no-illegal-paths
    commit/merge backstop.
    """
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
        # Batch mode: one process for an entire path list (stdin, newline-
        # delimited), not one subprocess per component. Not currently wired
        # to any caller — check-no-illegal-paths.py (chunk E3-b, the commit/
        # merge backstop that scans every tracked+staged path in the repo)
        # imports csn_check directly in-process instead, which is even
        # cheaper than this CLI batch mode. Kept as a general-purpose primitive
        # for any future bash/non-Python caller that needs to check many
        # components without a per-component subprocess spawn (a per-
        # component spawn was measured as a multi-minute regression on a
        # multi-thousand-file tree during this port, chunk E3-c).
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
