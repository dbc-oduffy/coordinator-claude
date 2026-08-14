"""coordinator/lib/percolate/ignore.py — .percolate-ignore matcher.

Native-Python port of `setup/publish.sh`'s `load_percolate_ignore` (~:872-898)
and `is_ignored` (~:911-937). This module is the single source of truth for
`.percolate-ignore` matching semantics — `setup/publish_sync.py`'s
`IgnoreMatcher` delegates to `is_ignored` (see that module's docstring) rather
than re-implementing the four branches, so the two copies of this
leak-gate cannot drift.

SECURITY-LOAD-BEARING: `.percolate-ignore` is what keeps operator-identity
files (e.g. `bin/depersonalize-identity.sh`) out of the public OSS publish. A
false negative here (a pattern that should match but doesn't) leaks. Fail
closed on anything ambiguous — do not add fuzzy/best-effort matching.

Pattern forms (NOT full gitignore — order matters, first-match-wins):
  1. `/dir/`  (leading AND trailing slash) — root-anchored directory match:
     rel_path must begin with `dir/` at the root only (never any-depth).
  2. `dir/`   (trailing slash, no leading slash) — any-depth directory match:
     rel_path begins with `dir/`, OR contains `/dir/` anywhere.
  3. `*...`   (leading `*`) — basename glob: fnmatch against the final path
     segment only. A mid-pattern `*` inside a basename glob is a normal glob
     wildcard (fnmatch handles it); the "mid-pattern `*` is literal" rule
     below applies to branch 4, not this branch.
  4. anything else — EXACT full rel_path match. A `*` that appears mid-string
     in a branch-4 pattern (i.e. the pattern does NOT start with `*`) is
     matched LITERALLY, never as a wildcard — branch 4 never globs.

Reader semantics: strip a trailing `\r` (Windows line endings), skip blank
lines and `#`-comment lines, trim TRAILING whitespace only — leading
whitespace in a pattern is significant and preserved.

Spec backlink: DoE-claude:pln-port-the-percolate-engine-to-p-94f40f § C-W1b.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path


def load_percolate_ignore(ignore_file: Path) -> list[str]:
    """Read `.percolate-ignore` at `ignore_file` and return its patterns, in
    file order (order matters — matching is first-match-wins).

    Returns an empty list if `ignore_file` does not exist (bash's
    no-file-found branch: "defaulting to publish-everything").
    """
    if not ignore_file.is_file():
        return []

    patterns: list[str] = []
    raw = ignore_file.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        # Strip a trailing \r defensively — splitlines() already treats a
        # bare \r as a line terminator, but a stray \r before a \n survives
        # splitlines() as a trailing char on the segment; strip it explicitly
        # to match the bash `line="${line%$'\r'}"` behaviour exactly.
        if line.endswith("\r"):
            line = line[:-1]
        stripped_leading = line.lstrip()
        if not stripped_leading or stripped_leading.startswith("#"):
            continue
        # Trim TRAILING whitespace only — leading whitespace is significant.
        line = line.rstrip()
        if not line:
            continue
        patterns.append(line)
    return patterns


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    """Return True iff `rel_path` matches any pattern in `patterns`, applying
    the four ordered branches documented in the module docstring.
    First-match-wins across the pattern list, in list order."""
    for pattern in patterns:
        if len(pattern) >= 2 and pattern[0] == "/" and pattern[-1] == "/":
            # Branch 1: root-anchored directory match. Strip both slashes,
            # then require a prefix match at the root only (never any-depth,
            # never a bare equality — mirrors bash `[[ "$rel_path" == "$dir"/* ]]`,
            # which requires content after the slash).
            dir_ = pattern[1:-1]
            if rel_path.startswith(dir_ + "/"):
                return True
        elif pattern.endswith("/"):
            # Branch 2: any-depth directory match. Mirrors bash's two glob
            # tests exactly — prefix OR any-depth occurrence; no bare
            # equality branch (a pattern "dir/" does not match rel_path=="dir").
            dir_ = pattern[:-1]
            if rel_path.startswith(dir_ + "/"):
                return True
            if ("/" + dir_ + "/") in rel_path:
                return True
        elif pattern.startswith("*"):
            # Branch 3: basename glob.
            base = rel_path.rsplit("/", 1)[-1]
            if fnmatch.fnmatchcase(base, pattern):
                return True
        else:
            # Branch 4: EXACT full rel_path match — a mid-pattern `*` is
            # literal, never a wildcard. Do NOT use fnmatch here.
            if rel_path == pattern:
                return True
    return False


class PercolateIgnoreMatcher:
    """Convenience wrapper bundling a loaded pattern list with `is_ignored`,
    for callers (e.g. `setup/publish_sync.py`) that want an object rather
    than a bare (rel_path, patterns) call pair."""

    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns

    @classmethod
    def from_file(cls, ignore_file: Path) -> "PercolateIgnoreMatcher":
        return cls(load_percolate_ignore(ignore_file))

    def matches(self, rel_path: str) -> bool:
        return is_ignored(rel_path, self.patterns)


def main(argv: list[str] | None = None) -> int:
    """Thin CLI: `ignore.py <ignore_file> <rel_path> [<rel_path> ...]` —
    prints `IGNORED <rel_path>` or `KEPT <rel_path>` per argument, for
    ad-hoc diagnosis. Exit 0 always (diagnostic tool, not a gate)."""
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2:
        print("usage: ignore.py <ignore_file> <rel_path> [<rel_path> ...]", file=sys.stderr)
        return 2
    ignore_file = Path(args[0])
    patterns = load_percolate_ignore(ignore_file)
    for rel_path in args[1:]:
        verdict = "IGNORED" if is_ignored(rel_path, patterns) else "KEPT"
        print(f"{verdict} {rel_path}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
