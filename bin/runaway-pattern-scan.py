#!/usr/bin/env python3
"""runaway-pattern-scan.py [--pattern RE]... [--pattern-file F]... [--json] [FILE ...] -- scan text for caller-supplied runaway patterns.

Scans each FILE (or stdin when no FILE is given, or for FILE `-`) line by line against regular
expressions the caller supplies; the script ships no patterns. `--pattern RE` may repeat;
`--pattern-file F` reads one regex per line (blank lines and lines starting `#` are skipped) and
may repeat. At least one pattern is required.

Output: one `PATH:LINE: [PATTERN] TEXT` line per hit (TEXT trimmed to 200 chars) and a final
`N hit(s) in M source(s)` or `clean: M source(s)` summary. `--json` prints one object:
`{"hits": [{"source", "line", "pattern", "text"}], "sources": M, "hit_count": N}`.

Exit codes: clean 0, one or more hits 1, usage / bad regex / unreadable input 2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Optional, TextIO

PROG = "runaway-pattern-scan"
EXIT_CLEAN = 0
EXIT_HIT = 1
EXIT_USAGE = 2
_TEXT_CAP = 200


class ScanError(Exception):
    """A bad pattern or unreadable input; maps to exit 2."""


def load_patterns(inline: Iterable[str], files: Iterable[str]) -> list[tuple[str, "re.Pattern[str]"]]:
    """Return (source_text, compiled) pairs from inline patterns then pattern files; raise ScanError."""
    raw = list(inline)
    for name in files:
        try:
            text = Path(name).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ScanError(f"cannot read pattern file {name}: {exc.strerror or exc}") from exc
        raw.extend(ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#"))
    compiled = []
    for src in raw:
        try:
            compiled.append((src, re.compile(src)))
        except re.error as exc:
            raise ScanError(f"bad pattern {src!r}: {exc}") from exc
    if not compiled:
        raise ScanError("no pattern supplied: pass --pattern or --pattern-file")
    return compiled


def scan_stream(name: str, stream: Iterable[str], patterns: list[tuple[str, "re.Pattern[str]"]]) -> list[dict]:
    """Return one hit dict per (line, pattern) match in `stream`."""
    hits = []
    for lineno, line in enumerate(stream, 1):
        line = line.rstrip("\r\n")
        for src, rx in patterns:
            if rx.search(line):
                hits.append({"source": name, "line": lineno, "pattern": src, "text": line[:_TEXT_CAP]})
    return hits


def scan(
    paths: list[str], patterns: list[tuple[str, "re.Pattern[str]"]], stdin: Optional[TextIO] = None
) -> tuple[list[dict], int]:
    """Scan `paths` (stdin when empty or `-`); return (hits, source_count). Raise ScanError on unreadable input."""
    hits: list[dict] = []
    sources = paths or ["-"]
    for p in sources:
        if p == "-":
            hits.extend(scan_stream("<stdin>", stdin if stdin is not None else sys.stdin, patterns))
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                hits.extend(scan_stream(p, fh, patterns))
        except OSError as exc:
            raise ScanError(f"cannot read {p}: {exc.strerror or exc}") from exc
    return hits, len(sources)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=PROG,
        description="Scan files or stdin for caller-supplied runaway-spawn regex patterns. "
        "Exit 0 clean, 1 on any hit, 2 on usage, bad regex or unreadable input.",
        allow_abbrev=False,
    )
    ap.add_argument("files", nargs="*", metavar="FILE", help="files to scan; none or `-` reads stdin")
    ap.add_argument("--pattern", action="append", default=[], metavar="RE", help="regex to match; repeatable")
    ap.add_argument(
        "--pattern-file", action="append", default=[], metavar="F",
        help="file of one regex per line (# comments, blanks skipped); repeatable",
    )
    ap.add_argument("--json", action="store_true", help="emit one JSON object instead of text lines")
    return ap


def main(argv: Optional[list[str]] = None, stdin: Optional[TextIO] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        patterns = load_patterns(args.pattern, args.pattern_file)
        hits, count = scan(args.files, patterns, stdin)
    except ScanError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        print(json.dumps({"hits": hits, "sources": count, "hit_count": len(hits)}))
    else:
        for h in hits:
            print(f"{h['source']}:{h['line']}: [{h['pattern']}] {h['text']}")
        print(f"{len(hits)} hit(s) in {count} source(s)" if hits else f"clean: {count} source(s)")
    return EXIT_HIT if hits else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
