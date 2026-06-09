"""
conftest.py — shared fixtures and helpers for cruft-sweep tests.

Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C1/C2

Review: code-reviewer (F9) — run(), bp(), and _make_stale_uuid_dir() were
copy-pasted across 4+ test files; extracted here so updates land in one place.
Individual test files retain their own definitions for backward compatibility
(import from conftest is opt-in); this file provides them as pytest-importable
helpers and as fixtures where appropriate.

Isolation: helpers never touch real ~/.claude/ state; they operate exclusively
on tmp_path fixtures passed by callers.
"""

import os
import subprocess
import time
from pathlib import Path

# Canonical path to the script under test
SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "cruft-sweep.sh"


def run(args, **kw):
    """Run cruft-sweep.sh with the given args; returns CompletedProcess."""
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        **kw,
    )


def bp(p: Path) -> str:
    """Convert a Path to a bash-navigable string on all platforms.

    On Windows, Path.as_posix() gives C:/... which Git-Bash handles correctly.
    On macOS/Linux, it is equivalent to str(p).
    """
    return p.as_posix()


def _make_stale_uuid_dir(parent: Path, uuid: str, age_days: int = 15) -> Path:
    """Create a uuid directory under parent with mtime aged by age_days."""
    d = parent / uuid
    d.mkdir(parents=True, exist_ok=True)
    (d / "dummy.txt").write_text("session data")
    old_mtime = time.time() - age_days * 86400
    os.utime(d, (old_mtime, old_mtime))
    return d
