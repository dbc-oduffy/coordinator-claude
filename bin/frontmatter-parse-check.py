#!/usr/bin/env python3
"""frontmatter-parse-check — does every record's frontmatter actually parse?

WHY THIS EXISTS. Nothing in this fleet checked that a record's frontmatter is
loadable YAML, so a malformed one was invisible until some unrelated tool
tripped over it. Measured when this was written: 43 records across
Claude-klabauter and DoE-claude do not parse — plans, lessons, decisions,
handoffs and review sidecars. Every one was found by accident.

The failure is silent in the only direction anyone checks. A reader that cannot
parse a frontmatter block sees a file with NO frontmatter, not a file with a
broken one, so the record simply drops out of every census, gate and query that
reads it — reporting nothing rather than reporting a defect.

WHAT COUNTS AS A DEFECT, stated because a wrong detector here is worse than no
detector. Only "a frontmatter block was opened and its YAML does not load".
  * A file that does not start with `---` has no frontmatter. NOT a defect —
    plenty of records are plain prose, and demanding one would be a new rule.
  * A MULTI-DOCUMENT record is legal YAML. `yaml.safe_load` raises
    ComposerError on it; this module uses `safe_load_all`. Getting this wrong
    overcounted 595 legal files as broken on the first pass of this very check
    — the detector was the defect, which is the failure class this fleet has
    already filed instances of.

THE BUDGET IS WHY `--changed` IS THE DEFAULT AND NOT A CONVENIENCE.
Pure-python PyYAML parses ~1.5 ms per document, so the full two-repo corpus
(8,632 load-bearing records) costs ~12.8 s in one process — an order over
DR-344's 500 ms, and no amount of tuning inside this file fixes a per-document
constant. So the hot path checks only what a commit touched, which is a handful
of records and lands in single-digit milliseconds. `--corpus` exists for a
deliberate audit and is over the brightline BY CONSTRUCTION; it says so when it
runs rather than pretending otherwise.

WHERE THIS SITS relative to the write guard. `write_guards/
validate_frontmatter_schema_deny.py` sees the write itself and is the earlier,
cheaper catch. This is the commit-time and audit-time net behind it: a guard
only fires where it is registered, and a record can arrive by a route no guard
watched (a percolate sync, a merge, a hand edit on a box with no plugin loaded).

Exit status: 0 every checked record parses, 1 at least one does not, 2 usage.

Budget: zero spawns in the default and explicit-path modes; ONE `git diff`
spawn under `--changed`. No engine import, no network.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import yaml

EXIT_CLEAN = 0
EXIT_BROKEN = 1
EXIT_USAGE = 2

RECORD_SUFFIXES = (".md", ".yaml", ".yml")

#: `--corpus` walks the whole repo and SUBTRACTS, rather than enumerating the
#: directories records live in. An allowlist was tried and was the wrong shape:
#: the first cut listed twelve plausible roots, returned a clean exit over both
#: repos, and had simply not read the directories 30 of the 43 known-broken
#: records were in — `state/audits`, `state/reviews`, `state/memo-outbox`,
#: `docs/reference`, `archive/**`. A green result from a checker that looked at
#: nothing is worse than no checker, because it is evidence.
#:
#: Records turn up in new directories as the fleet grows; skip-dirs do not. A
#: denylist covers a directory nobody has invented yet, which is the property
#: that matters for a check meant to keep a class from recurring.
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    # Deliberately-malformed samples live here. Reporting a fixture as a defect
    # trains readers to ignore this check, which costs more than it catches.
    "fixtures",
    "testdata",
    "test-data",
}

#: The defect classes measured in this corpus, and the idiom that fixes each.
#: Named so the message is actionable at the point of failure rather than
#: sending the reader to a wiki to find out what YAML dislikes.
_HINTS = (
    (
        ": ",
        "a plain scalar cannot contain \": \" — quote the value",
    ),
    (
        "found unexpected end of stream",
        "an unclosed quote or bracket",
    ),
    (
        "expected <block end>",
        "a single-quoted scalar containing an apostrophe — double it ('' ), "
        "or a multi-line plain scalar whose continuation reads as a key — use >- or |-",
    ),
)


def frontmatter_of(path: Path) -> Optional[str]:
    """The YAML document to check, or None when this file has none.

    For `.md` the document is the block between the opening `---` and the next
    `\\n---`. An unterminated block returns None deliberately: that is a
    different defect (a truncated file), and this check refuses to report a
    class it cannot name precisely.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if path.suffix in (".yaml", ".yml"):
        return text
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return None if end == -1 else text[4:end]


def check(path: Path) -> Optional[str]:
    """None when the record parses (or has no frontmatter); else the error."""
    doc = frontmatter_of(path)
    if doc is None:
        return None
    try:
        # safe_load_ALL: a multi-document record is legal and must not be a finding.
        list(yaml.safe_load_all(doc))
    except yaml.YAMLError as exc:
        detail = " ".join(str(exc).split())
        for needle, hint in _HINTS:
            if needle in detail:
                return f"{type(exc).__name__}: {detail}  [likely {hint}]"
        return f"{type(exc).__name__}: {detail}"
    return None


def changed_paths(repo: Path, ref: str) -> List[Path]:
    """Record files changed against `ref`. The one spawn this module makes."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", "--diff-filter=ACMR", ref],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(
            f"frontmatter-parse-check: git diff against {ref!r} failed:\n"
            f"{proc.stderr.strip()}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    out = []
    for line in proc.stdout.splitlines():
        p = repo / line.strip()
        if line.strip().endswith(RECORD_SUFFIXES) and p.is_file():
            out.append(p)
    return out


def corpus_paths(repo: Path) -> Iterable[Path]:
    """Every record in the repo, minus the skip-dirs. Walk-and-subtract, never
    an allowlist of roots — see `_SKIP_DIRS` for the measurement that decided it.
    """
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(RECORD_SUFFIXES):
                yield Path(dirpath) / name


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="frontmatter-parse-check",
        description="Check that every named record's frontmatter is loadable YAML.",
    )
    parser.add_argument("paths", nargs="*", help="record files to check")
    parser.add_argument(
        "--changed",
        metavar="REF",
        nargs="?",
        const="HEAD",
        help="check records changed against REF (default HEAD) instead of named paths",
    )
    parser.add_argument(
        "--corpus",
        action="store_true",
        help="walk every record directory — a deliberate audit, over the DR-344 "
        "brightline by construction (~1.5ms per record)",
    )
    parser.add_argument("--repo", default=".", help="repo root (default: cwd)")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if args.corpus:
        targets: List[Path] = list(corpus_paths(repo))
        print(
            f"frontmatter-parse-check: corpus audit over {len(targets)} record(s) — "
            "a batch mode, deliberately over the 500ms brightline.",
            file=sys.stderr,
        )
    elif args.changed is not None:
        targets = changed_paths(repo, args.changed)
    elif args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        parser.print_usage(sys.stderr)
        print(
            "frontmatter-parse-check: name paths, or pass --changed / --corpus",
            file=sys.stderr,
        )
        return EXIT_USAGE

    broken: List[Tuple[Path, str]] = []
    for path in targets:
        if not path.is_file():
            print(f"frontmatter-parse-check: no such file: {path}", file=sys.stderr)
            return EXIT_USAGE
        error = check(path)
        if error:
            broken.append((path, error))

    for path, error in broken:
        try:
            shown = path.resolve().relative_to(repo)
        except ValueError:
            shown = path
        print(f"frontmatter does not parse: {shown}")
        if not args.quiet:
            print(f"  {error}")

    if broken:
        print(
            f"\nfrontmatter-parse-check: {len(broken)} of {len(targets)} record(s) "
            "do not parse. Every reader sees these as having NO frontmatter, "
            "not as a record with a broken one."
        )
        return EXIT_BROKEN
    if not args.quiet:
        print(f"frontmatter-parse-check: {len(targets)} record(s), all parse.")
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
