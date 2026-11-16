"""Installer helper: seed the top-level `crossSessionInbound` setting to `accept` when unset.

`--apply <settings.json>` writes the default only when the key is absent (a present key, `null`
included, is never rewritten) and prints `applied` or `unchanged`. `--check <settings.json>`
prints `present=<value>` or `absent` and never writes. Unparseable or non-dict JSON is left
untouched with exit 2.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

KEY = "crossSessionInbound"
DEFAULT = "accept"


def apply_default(settings: dict) -> bool:
    """Set KEY to DEFAULT in `settings` when the key is absent. True when changed."""
    if KEY in settings:
        return False
    settings[KEY] = DEFAULT
    return True


def apply_default_to_file(path: Path) -> bool:
    """Seed `path` atomically; a missing file is created. Raises ValueError on unparseable or non-dict JSON."""
    path = Path(path)
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError("settings JSON is not an object")
    if not apply_default(settings):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-%d" % os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(settings, indent=2) + "\n")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return True


def check_file(path: Path) -> str:
    """`present=<value>` or `absent`; never writes. Raises ValueError on unparseable or non-dict JSON."""
    path = Path(path)
    if not path.exists():
        return "absent"
    settings = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError("settings JSON is not an object")
    if KEY not in settings:
        return "absent"
    value = settings[KEY]
    return "present=%s" % (value if isinstance(value, str) else json.dumps(value))


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("--apply", "--check"):
        print("usage: %s --apply|--check <settings.json>" % argv[0], file=sys.stderr)
        return 2
    path = Path(argv[2])
    try:
        if argv[1] == "--apply":
            print("applied" if apply_default_to_file(path) else "unchanged")
        else:
            print(check_file(path))
    except (OSError, ValueError) as exc:
        print("%s: left untouched: %s" % (path, exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
