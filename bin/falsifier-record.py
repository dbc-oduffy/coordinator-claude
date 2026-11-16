#!/usr/bin/env python3
"""falsifier-record -- a plan's `prime_exit_criterion` block, alone, as the falsifier-integrity
reviewer's whole input. Reads one plan; writes only `--out`.

BLINDING BY CONSTRUCTION. The reviewer judges whether the falsifier can report red against the
criterion as written. Handed the plan, it also reads the body that argues the criterion is met,
and "do not open the plan" is an instruction, not a mechanism. Handed this file, there is nothing
else to open.

VERBATIM, NOT RE-SERIALISED. The block is sliced out of the frontmatter as written -- comments,
quoting and key order kept -- then loaded once to prove the slice is the whole mapping. A
`yaml.dump` round trip would reorder keys and drop comments the author left for the reviewer.

Exit status:
  0  written (or printed)
  1  the plan declares no `prime_exit_criterion` mapping
  3  usage, or a plan that cannot be read
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

EXIT_OK = 0
EXIT_ABSENT = 1
EXIT_USAGE = 3

_KEY = "prime_exit_criterion"
_DELIMITER = re.compile(r"^---[ \t]*$")
_TOP_LEVEL_KEY = re.compile(r"^[^\s#-][^:]*:")


def _frontmatter_lines(text: str) -> Optional[list[str]]:
    lines = text.splitlines(keepends=True)
    if not lines or not _DELIMITER.match(lines[0].rstrip("\r\n")):
        return None
    for i, line in enumerate(lines[1:], start=1):
        if _DELIMITER.match(line.rstrip("\r\n")):
            return lines[1:i]
    return None


def extract(text: str) -> Optional[str]:
    """The `prime_exit_criterion:` block as written, or None when the plan declares none."""
    fm = _frontmatter_lines(text)
    if fm is None:
        return None
    start = next((i for i, ln in enumerate(fm) if ln.startswith(f"{_KEY}:")), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(fm)) if _TOP_LEVEL_KEY.match(fm[i])), len(fm))
    block = "".join(fm[start:end]).replace("\r\n", "\n").rstrip() + "\n"

    import yaml

    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if not (isinstance(loaded, dict) and list(loaded) == [_KEY] and isinstance(loaded[_KEY], dict)):
        return None
    return block


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="falsifier-record")
    ap.add_argument("plan", help="plan path")
    ap.add_argument("--out", help="file to write; stdout when omitted")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    try:
        text = Path(args.plan).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"falsifier-record: cannot read {args.plan}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    block = extract(text)
    if block is None:
        print(f"falsifier-record: {args.plan} declares no {_KEY} mapping", file=sys.stderr)
        return EXIT_ABSENT
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(block, encoding="utf-8", newline="\n")
        print(out)
    else:
        sys.stdout.write(block)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
