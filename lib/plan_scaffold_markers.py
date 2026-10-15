"""Deterministic scaffold-marker gate for a plan file.

A plan scaffolded by `coordinator-doc-new --type plan` carries template markers until its author
fills them. A plan that still carries one is not a plan. Enforcement is the plan-author's
self-check before it returns a path; `/execute-plan` Phase 1 re-runs it. The stage consumer
lives in the engine, which wires this gate itself.

Verdict contract: `scan(text)` returns each marker found with its first line number; the CLI
exits 0 clean, 2 on bad usage or an unreadable file, 3 with a one-line `PLAN-SCAFFOLD-UNFILLED`
verdict naming each marker. Comment lines (`# ...`) inside the frontmatter are template
documentation and never count; a `#` line in the body is content.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKERS = (
    # A template PLACEHOLDER is a whole value: a line, a field, a list item, a cell or a heading
    # starts with it. The word in prose ("keeps the PLACEHOLDER comment") is a mention.
    ("PLACEHOLDER", re.compile(r"(?:^|[:|]|^\s*-|^\s*#+)\s*[\"']?PLACEHOLDER\b")),
    ("<REPLACE:", re.compile(r"<REPLACE:")),
    ("path/to/file", re.compile(r"path/to/file")),
)


# TRAP: path/to/file and <REPLACE: are template-only strings and stay flagged inside a code span;
# only PLACEHOLDER is an ordinary word a plan quotes.
_CODE_SPAN = re.compile(r"`[^`]*`")


def scan(text: str) -> dict[str, int]:
    """Marker -> first 1-based line it appears on, skipping `#` lines inside the frontmatter."""
    found: dict[str, int] = {}
    lines = text.splitlines()
    in_front = bool(lines) and lines[0].strip() == "---"
    for n, line in enumerate(lines, 1):
        if in_front:
            if n > 1 and line.strip() == "---":
                in_front = False
                continue
            if line.lstrip().startswith("#"):
                continue
        for name, rx in MARKERS:
            probe = _CODE_SPAN.sub("", line) if name == "PLACEHOLDER" else line
            if name not in found and rx.search(probe):
                found[name] = n
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: plan_scaffold_markers.py <plan.md>", file=sys.stderr)
        return 2
    try:
        text = Path(argv[1]).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"plan_scaffold_markers: cannot read {argv[1]}: {exc}", file=sys.stderr)
        return 2
    found = scan(text)
    if not found:
        return 0
    detail = ", ".join(f"{k} (line {v})" for k, v in sorted(found.items()))
    print(f"PLAN-SCAFFOLD-UNFILLED: {argv[1]} still carries {detail}; fill the spine before stage or execute.")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
