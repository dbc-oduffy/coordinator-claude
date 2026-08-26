#!/usr/bin/env python3
"""Generate AC15's allowlist: every live file still carrying the literal ``CLAUDE_KLABAUTER_ROOT``,
classified by WHY it survives the rename.

AC15 (``docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md``) asks that
``grep -rl CLAUDE_KLABAUTER_ROOT`` over live paths return zero *outside a checked-in allowlist,
each entry carrying its reason*. That allowlist cannot be hand-written: the residue is
several hundred files, and a hand-written list is stale the moment the next slice lands.
So it is generated, and the reason is derived from the line rather than asserted.

The classes, in precedence order:

``dual-read-site``
    The file names both spellings. C11's dual-read window is open by design, so a site
    that reads the new name with the old one as fallback is CORRECT, not residue.
``env-read-or-write``
    An actual environment read or write, or a test monkeypatching one. C11 owns this
    axis; C12's prose sweep is explicitly forbidden from touching it.
``error-string-marker``
    The ``CLAUDE_KLABAUTER_ROOT resolution failed`` transport marker, asserted verbatim by test
    suites across the repo. Rewriting it turns a green suite into a false one.
``retained-prose``
    Prose a C12 slice examined and deliberately kept -- typically because it names a
    probe id, a module path, or an identifier that is genuinely still spelled that way.
    The per-file reasons live in the slices' sidecars.
``UNEXAMINED``
    No C12 slice's ``writes:`` list ever named this file. This is NOT an allowlist
    entry. It is a coverage gap, and it is reported separately and loudly, because a
    gap that renders as an allowlist row is the exact stealth-skip shape AC15 exists to
    forbid.

Negative spec: this script never edits anything and never decides that a site is fine.
It reports what is there and which population it falls in; a non-empty UNEXAMINED
section means AC15 is not dischargeable yet, whatever the other counts say.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

TOKEN = "CLAUDE_KLABAUTER_ROOT"
NEW_TOKEN = "COORDINATOR_ENGINE_ROOT"

#: Prefixes that record what was true when they were written. Rewriting one falsifies
#: the evidence trail the plan argues from (AC16), so they are out of AC15's scope --
#: this mirrors C13's body, where the principle is the filter, not the prefix list.
RECORD_PREFIXES = (
    "state/",
    "archive/",
    "cross-repo/",
    "tasks/",
    "docs/decisions/",
    "docs/research/",
    "docs/plans/",
)

#: Generated or published trees: not authored surface.
DERIVED_PREFIXES = ("dist/", ".structural-index/")

#: A dated artifact directly under docs/ is a record of what was true on that date, not
#: a description of what is. C13's body ratifies this after an earlier run swept exactly
#: this class -- a dated census among them -- and had to be reverted by token.
DATED_DOC = re.compile(r"^docs/\d{4}-\d{2}-\d{2}-")

ENV_SITE = re.compile(
    r"""environ|getenv|setenv|env\[|monkeypatch\.setenv|["']CLAUDE_KLABAUTER_ROOT["']"""
)
ERROR_MARKER = "resolution failed"

#: Suffixes that identify a path inside the partition JSON, which also carries prose.
PATH_SUFFIXES = (".py", ".md", ".json", ".toml", ".ps1", ".yaml", ".sh", ".cmd")

PARTITION = (
    "state/dispatch-briefs/2026-08-20-an-engine-root-is-not-named-for-the-repo/"
    "C12-slices.json"
)


def live_files(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    return [
        f
        for f in out.split("\n")
        if f
        and not f.startswith(RECORD_PREFIXES + DERIVED_PREFIXES)
        and not DATED_DOC.match(f)
    ]


def _looks_like_path(value: str) -> bool:
    """Both tests are load-bearing, and each alone files a real file in the wrong bucket.

    A repo-root path (``INSTALL.md``) has no separator; an extensionless CLI
    (``coordinator/bin/scoped-git-commit``) has no suffix. Requiring either one alone
    drops examined files into the coverage gap, which is the one bucket that must stay
    honest.
    """
    return (
        value.endswith(PATH_SUFFIXES) or ("/" in value and not value.endswith("/"))
    ) and " " not in value


def examined_paths(repo: Path) -> set[str]:
    """Every path a C12 slice's own ``writes:`` list declared -- not any path-shaped
    string anywhere in the partition. A path merely mentioned in a chunk's ``title``,
    ``body``, or ``disposition`` prose was never reviewed under the guarantee AC15
    checks for -- only an explicit ``writes:`` entry means a slice examined it.

    # Review: code-reviewer P2 -- whole-object-tree harvest let prose mentions launder
    # a never-reviewed file into the examined set; narrowed to declared writes.
    """
    found: set[str] = set()
    path = repo / PARTITION
    if not path.exists():
        return found
    chunks = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(chunks, list):
        return found
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        for value in chunk.get("writes") or []:
            if isinstance(value, str) and _looks_like_path(value):
                found.add(value.replace("\\", "/"))
    return found


def classify(text: str, hits: list[str], path: str, examined: set[str]) -> str:
    # Review: code-reviewer P1 -- whole-file `NEW_TOKEN in text` laundered every
    # CLAUDE_KLABAUTER_ROOT hit in a file into dual-read-site merely because the file mentioned
    # COORDINATOR_ENGINE_ROOT anywhere (an unrelated docstring, a changelog line).
    # Decided at hit-line granularity instead, so an unrelated co-occurrence can no
    # longer mask a hit that was never examined.
    if any(NEW_TOKEN in line for line in hits):
        return "dual-read-site"
    if any(ENV_SITE.search(line) for line in hits):
        return "env-read-or-write"
    if any(ERROR_MARKER in line for line in hits):
        return "error-string-marker"
    return "retained-prose" if path in examined else "UNEXAMINED"


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    examined = examined_paths(repo)

    buckets: dict[str, list[tuple[str, int]]] = {}
    for rel in live_files(repo):
        path = repo / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if TOKEN not in text:
            continue
        hits = [line for line in text.split("\n") if TOKEN in line]
        buckets.setdefault(classify(text, hits, rel, examined), []).append(
            (rel, len(hits))
        )

    total_files = sum(len(v) for v in buckets.values())
    total_hits = sum(n for v in buckets.values() for _, n in v)
    gap = buckets.get("UNEXAMINED", [])

    print("<!-- Generated by coordinator/bin/classify-engine-root-residue.py — do not")
    print("     hand-edit; regenerate. A file list is a snapshot, not a frozen roster. -->")
    print()
    print("# AC15 allowlist: live files still naming `CLAUDE_KLABAUTER_ROOT`, and why")
    print()
    print(
        f"AC15's predicate measured over live paths: **{total_files}** files, "
        f"**{total_hits}** occurrences."
    )
    print()
    if gap:
        print(
            f"> **AC15 is NOT dischargeable as measured.** {len(gap)} file(s) below are "
            "in the UNEXAMINED bucket: no C12 slice's `writes:` list ever named them, so "
            "nobody has decided whether their mentions should survive. An unexamined "
            "file is a coverage gap, not an allowlist entry."
        )
    else:
        print(
            "> Every surviving mention falls in a bucket someone examined and kept on "
            "purpose. The UNEXAMINED bucket is empty."
        )
    print()

    order = [
        "UNEXAMINED",
        "retained-prose",
        "error-string-marker",
        "env-read-or-write",
        "dual-read-site",
    ]
    for name in order:
        rows = buckets.get(name)
        if not rows:
            continue
        rows.sort(key=lambda kv: (-kv[1], kv[0]))
        print(f"## `{name}` — {len(rows)} file(s), {sum(n for _, n in rows)} occurrence(s)")
        print()
        print(REASONS[name])
        print()
        print("| occurrences | file |")
        print("|---|---|")
        for rel, count in rows:
            print(f"| {count} | `{rel}` |")
        print()
    return 0


REASONS = {
    "UNEXAMINED": (
        "**Not an allowlist.** No C12 slice declared these paths, so their mentions "
        "were never read by anyone. Assign them to a slice and re-run this generator."
    ),
    "retained-prose": (
        "A C12 slice examined the file and kept the mention deliberately — it names a "
        "probe id, module path, or identifier still spelled that way. Per-file reasons "
        "are in that slice's sidecar under `state/subagent-share/`."
    ),
    "error-string-marker": (
        "Carries the `CLAUDE_KLABAUTER_ROOT resolution failed` transport marker, asserted "
        "verbatim by suites across the repo. Rewriting it makes a green suite lie."
    ),
    "env-read-or-write": (
        "A real environment read or write, or a test pinning one. C11 owns this axis; "
        "the prose sweep is forbidden from touching it."
    ),
    "dual-read-site": (
        "Names both spellings: reads the new variable with the old one as fallback. "
        "This is C11's dual-read window working as designed, not residue."
    ),
}


if __name__ == "__main__":
    raise SystemExit(main())
