"""backup-global-claude-md: keep the first pre-coordinator copy of the global CLAUDE.md.

Copies `<claude-home>/.claude/CLAUDE.md` to `CLAUDE.md.pre-coordinator.bak` when the file is
non-empty, lacks the seed sentinel, and no `.bak` exists yet. Exit 0 always on a clean decision;
stdout names the outcome (`backed-up`, `skip-no-file`, `skip-empty`, `skip-seeded`, `skip-exists`).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SENTINEL = "coordinator:claude-md-seed:v1"
BACKUP_NAME = "CLAUDE.md.pre-coordinator.bak"


def backup(claude_home: Path) -> str:
    """Back up `<claude_home>/.claude/CLAUDE.md` no-clobber; return the outcome token."""
    src = claude_home / ".claude" / "CLAUDE.md"
    dst = src.with_name(BACKUP_NAME)
    if not src.is_file():
        return "skip-no-file"
    if src.stat().st_size == 0:
        return "skip-empty"
    if SENTINEL in src.read_text(encoding="utf-8", errors="replace"):
        return "skip-seeded"
    if dst.exists():
        return "skip-exists"
    shutil.copyfile(src, dst)
    return "backed-up"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--claude-home", required=True, type=Path,
                        help="resolved ${CLAUDE_HOME:-$HOME}; the script appends .claude itself")
    args = parser.parse_args(argv)
    print(backup(args.claude_home))
    return 0


if __name__ == "__main__":
    sys.exit(main())
