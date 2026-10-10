"""Deterministic scaffold-marker gate for a plan file.

A plan scaffolded by `coordinator-doc-new --type plan` carries template markers until its author
fills them. A plan that still carries one is not a plan: no stage or execute step may consume it.

Verdict contract: `scan(text)` returns each marker found with its first line number; the CLI
exits 0 clean, 3 with a one-line `PLAN-SCAFFOLD-UNFILLED` verdict naming each marker.
Frontmatter comment lines (`# ...`) are template documentation and never count.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MARKERS = (
    ("PLACEHOLDER", re.compile(r"\bPLACEHOLDER\b")),
    ("<REPLACE:", re.compile(r"<REPLACE:")),
    ("path/to/file", re.compile(r"path/to/file")),
)


def _is_yaml_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("#") and not s.startswith("##")


def scan(text: str) -> dict[str, int]:
    """Marker -> first 1-based line it appears on, skipping `#` comment lines."""
    found: dict[str, int] = {}
    for n, line in enumerate(text.splitlines(), 1):
        if _is_yaml_comment(line):
            continue
        for name, rx in MARKERS:
            if name not in found and rx.search(line):
                found[name] = n
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: plan_scaffold_markers.py <plan.md>", file=sys.stderr)
        return 2
    found = scan(Path(argv[1]).read_text(encoding="utf-8"))
    if not found:
        return 0
    detail = ", ".join(f"{k} (line {v})" for k, v in sorted(found.items()))
    print(f"PLAN-SCAFFOLD-UNFILLED: {argv[1]} still carries {detail}; fill the spine before stage or execute.")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
