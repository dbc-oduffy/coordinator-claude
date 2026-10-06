#!/usr/bin/env python3
"""Advisory fleet lint: project CLAUDE.md files that teach hand-authored handoffs.

Flags any fleet repo's CLAUDE.md naming the retired `.claude/handoffs` path, or telling the agent
to write a handoff file manually. Repos come from `machine-local keys` (`repos.*`). One line per
offending repo and line number, plus the remedy. Always exits 0; unreadable repos are skipped.

Contract: coordinator/docs/wiki/coordinator-tripwires/a-handoff-written-by-hand-is-not-a-handoff.md.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

CLAUDE_MD_RELPATHS = ("CLAUDE.md", ".claude/CLAUDE.md")
REMEDY = "replace with: run /handoff; handoffs live in state/handoffs/"
RETIRED_PATH = re.compile(r"\.claude(?:/|\\)handoffs")
MANUAL_WRITE = re.compile(
    r"\b(write|writes|author|create|save|hand-?author)\w*\s+(?:a|the|your|an)?\s*(?:session\s+)?handoff"
    r"(?:\s+(?:file|doc\w*|baton))?\s+(?:to|in|at|under|manually|by hand)\b"
    r"|\bhandoff\s+file\s+(?:manually|by hand)\b",
    re.I,
)
NEGATED = re.compile(r"\b(never|do not|don't|retired|instead of)\b", re.I)


def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"


def _machine_local(*args: str) -> str:
    exe = _settings_home() / "bin" / ("machine-local.cmd" if os.name == "nt" else "machine-local")
    r = subprocess.run([str(exe), *args], capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def fleet_repos() -> Dict[str, Path]:
    """`repos.*` registry entries that are existing directories, de-duplicated by resolved path."""
    out: Dict[str, Path] = {}
    seen: set[Path] = set()
    for key in _machine_local("keys").splitlines():
        key = key.strip()
        if not key.startswith("repos."):
            continue
        try:
            val = _machine_local("get", key)
        except RuntimeError:
            continue
        if val and Path(val).is_dir() and Path(val).resolve() not in seen:
            seen.add(Path(val).resolve())
            out[key[len("repos."):]] = Path(val)
    return out


def scan_repo(root: Path) -> Iterator[Tuple[str, int, str]]:
    """Yield (relpath, line number, stripped line) for each offending CLAUDE.md line."""
    for rel in CLAUDE_MD_RELPATHS:
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if (RETIRED_PATH.search(line) or MANUAL_WRITE.search(line)) and not NEGATED.search(line):
                yield rel, n, line.strip()[:120]


def report(repos: Dict[str, Path]) -> List[str]:
    return [
        f"{name}: {rel}:{n}: hand-authored handoff convention ({snippet!r}) -- {REMEDY}"
        for name, root in repos.items()
        for rel, n, snippet in scan_repo(root)
    ]


def main() -> int:
    try:
        repos = fleet_repos()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return 0
    for line in report(repos):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
