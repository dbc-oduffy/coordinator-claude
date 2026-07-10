#!/usr/bin/env python3
"""Idempotently seed bundled-skill skillOverrides into a Claude Code settings.json.

Purpose: merge the coordinator's bundled-skill override entries into the user's
settings.json without clobbering any existing user values. Reused by
install-health drop-in checks.

Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md (seed-skill-overrides chunk).

Negative-spec: CLAUDE_HOME is the home-substitute, not the .claude-substitute.
  CLAUDE_HOME=/tmp/x  →  /tmp/x/.claude/settings.json   (CORRECT)
  CLAUDE_HOME=/tmp/x  →  /tmp/x/settings.json            (WRONG — recurring footgun)
"""

# Review: code-reviewer F4 — PEP 563 lazy annotations (PEP 585 list[str] fails at
# def-time on Python 3.8; __future__ annotation makes all annotations strings, valid 3.7+)
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile


# Core override set — always seeded.
_CORE_OVERRIDES = ["review", "security-review", "simplify", "init"]

# Optional override added when --with-deep-research is passed.
_DEEP_RESEARCH_OVERRIDE = "deep-research"


def _resolve_settings_path() -> pathlib.Path:
    """Resolve settings.json using the home-substitute convention.

    Priority: CLAUDE_HOME env var (home substitute) → pathlib.Path.home().
    Appends .claude/settings.json in both cases.
    """
    base = (
        pathlib.Path(os.environ["CLAUDE_HOME"])
        if os.environ.get("CLAUDE_HOME")
        else pathlib.Path.home()
    )
    return base / ".claude" / "settings.json"


def _load_settings(settings_path: pathlib.Path) -> dict:
    """Read and parse settings.json, returning {} when the file is absent.

    Raises SystemExit(1) on malformed JSON or unreadable file.
    """
    if not settings_path.exists():
        return {}
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"FATAL: settings.json malformed ({e}) — skipping skillOverrides seed."
            " Repair and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)


def _build_names(with_deep_research: bool) -> list[str]:
    names = list(_CORE_OVERRIDES)
    if with_deep_research:
        names.append(_DEEP_RESEARCH_OVERRIDE)
    return names


def _atomic_write(settings_path: pathlib.Path, data: dict) -> None:
    """Write data to settings_path atomically via a sibling temp file.

    Creates parent directory first — required so mkstemp(dir=parent) doesn't
    fail on a fresh CLAUDE_HOME temp directory that has no .claude/ subdirectory yet.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=settings_path.parent, prefix=".settings.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", newline="\n") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, settings_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Idempotently seed bundled-skill skillOverrides into settings.json."
    )
    parser.add_argument(
        "--with-deep-research",
        action="store_true",
        help="Seed the deep-research bundled-skill override (suppresses the Claude Code built-in /deep-research in favour of /coordinator:research).",
        # Review: code-reviewer — F13: stale help text post-C4 merge; deep-research is always bundled, this suppresses the CC built-in
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Print the would-seed delta to stdout and exit 0; write nothing.",
    )
    args = parser.parse_args()

    settings_path = _resolve_settings_path()
    s = _load_settings(settings_path)
    names = _build_names(args.with_deep_research)

    # Validate or initialise the skillOverrides key.
    overrides = s.setdefault("skillOverrides", {})
    if not isinstance(overrides, dict):
        print(
            f"FATAL: skillOverrides is present but not an object"
            f" (got {type(overrides).__name__}) — refusing to seed."
            " Repair settings.json.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.check_only:
        would_seed = [n for n in names if n not in overrides]
        # Review: code-reviewer F5 — consistent status-line family: (check-only) suffix
        # distinguishes check-only from real writes; no "/ ready" ambiguity.
        if would_seed:
            print(f"skill_overrides: would seed {', '.join(would_seed)} (check-only)")
        else:
            print("skill_overrides: would seed (none) (check-only)")
        sys.exit(0)

    # Merge — direct assignment inside `not in` guard; setdefault is redundant here
    # (Review: code-reviewer F7 — setdefault after confirming absence is misleading).
    newly_added = []
    for name in names:
        if name not in overrides:
            overrides[name] = "off"
            newly_added.append(name)

    # Review: code-reviewer F2 — skip write on fully-idempotent re-run (avoids mtime
    # churn, watcher noise, and needless reformatting of a hand-edited settings.json).
    if newly_added:
        _atomic_write(settings_path, s)

    # Review: code-reviewer F5 — consistent status-line family (no "/ already-present"
    # suffix on the seeded branch, which was semantically confusing).
    if newly_added:
        print(f"skill_overrides: seeded {', '.join(newly_added)}")
    else:
        print("skill_overrides: already-present")


if __name__ == "__main__":
    main()
