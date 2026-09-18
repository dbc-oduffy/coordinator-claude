#!/usr/bin/env python3
"""coordinator/bin/pre_commit_corpus_artifact_guard.py — refuse a commit that stages a
project-rag corpus artifact, or any oversized real blob.

Purpose: the belt-and-braces half of the fleet ruling that a corpus artifact is never
committed (DoE-claude's ``docs/wiki/coordinator-tripwires/corpus-artifact-is-never-committed.md``).
The ignore stanza is the primary defence; this catches the cases the stanza cannot,
because a `.gitignore` rule is silent once a path is staged with ``git add -f`` or was
already tracked before the rule existed.

TWO INDEPENDENT LEGS, and the path leg is the load-bearing one.

  1. PATH leg — any staged path under ``.project-rag-corpus-artifacts/`` or
     ``.project-rag-corpus-store/`` is refused REGARDLESS OF SIZE. A size-only guard
     (the shape the prior art in project-rag-ue-addon implements) passes a small or
     partially-written corpus directory, which is still a corpus artifact in a commit
     and still the thing the ruling forbids. Size is a proxy for the real predicate;
     this leg is the real predicate.
  2. SIZE leg — any staged real blob over the threshold, wherever it lives. This is the
     generic push-limit catch: GitHub hard-rejects a non-LFS blob over 100 MB, so a
     commit that passes locally fails at push after the network round-trip. Defaulting
     to 95 MB leaves margin.

Ported from project-rag-ue-addon's ``bin/pre-commit-oversized-blob-guard.sh`` per the
fleet's standing ruling that structural bash is a defect (claude-klabauter CLAUDE.md §
Runtime conventions). Not a translation — the path leg is new, and the LFS-pointer
reasoning is dropped because git-LFS is ruled out for this artifact class on the merits,
so an over-threshold staged blob here has no legitimate pointer form to be confused with.

Windows-first: no shell, no bash, no ``find``. Every git call goes through
``subprocess.run`` with a list argv, so a path containing a space or a drive letter
survives; paths are compared with forward slashes because that is what git emits on
every platform, including Windows.

Exit codes:
  0 — nothing staged violates either leg (including the no-staged-files case).
  1 — at least one violation; the commit is refused and the reason printed to stderr.

Bypass (both legs): ``CORPUS_ARTIFACT_OK=1 git commit ...``
Threshold override, MiB, size leg only: ``OVERSIZE_BLOB_MAX_MB=<N> git commit ...``

Negative-spec:
  - Does NOT stage, unstage, or modify anything. A guard that repairs the index behind
    the author is a guard that surprises them mid-commit; this one refuses and explains.
  - Does NOT read or write ``.gitignore``. The stanza is scaffolded by repo-setup Phase
    3f; this script never edits it and never infers policy from its contents.
  - Does NOT consult the network, project-rag, or any registry. It must run offline in a
    pre-commit hook on a laptop.
  - Does NOT substitute 0 for an unmeasurable blob. A path that vanished from the index
    mid-run (a concurrent ``git add`` on this shared tree) is skipped, never silently
    passed as zero-sized.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C5.
"""

from __future__ import annotations

import os
import subprocess
import sys

# A console-subsystem child with no console of its own allocates a fresh
# conhost on Windows -- with a visible window. Every git spawn below is
# short-lived and output-captured, so without this each one flashes.
# 0 on POSIX, where the flag does not exist.
_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

_CORPUS_PREFIXES = (
    ".project-rag-corpus-artifacts/",
    ".project-rag-corpus-store/",
)

_DEFAULT_MAX_MB = 95
_BYPASS_ENV = "CORPUS_ARTIFACT_OK"
_MAX_MB_ENV = "OVERSIZE_BLOB_MAX_MB"


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        shell=False,
        **_NO_CONSOLE,
    )


def _staged_paths() -> list[str]:
    """Paths introducing new content: added, modified, renamed. Deletes introduce no blob.

    A rename counts — `git mv` then `git add -f` records as R, and the destination is a
    real blob that would be pushed.
    """
    proc = _git(["diff", "--cached", "--name-only", "--diff-filter=AMR"])
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _staged_size(path: str) -> int | None:
    """Size of the staged blob, or None when it cannot be measured.

    None is deliberately distinct from 0: an unmeasurable path is skipped rather than
    passed, so a concurrent index write on this shared tree never converts an oversized
    blob into a silent pass.
    """
    proc = _git(["cat-file", "-s", f":{path}"])
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def _max_bytes() -> int:
    raw = os.environ.get(_MAX_MB_ENV, "")
    try:
        mb = int(raw) if raw else _DEFAULT_MAX_MB
    except ValueError:
        mb = _DEFAULT_MAX_MB
    if mb <= 0:
        mb = _DEFAULT_MAX_MB
    return mb * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    if os.environ.get(_BYPASS_ENV) == "1":
        print(f"[corpus-artifact-guard] bypassed via {_BYPASS_ENV}=1", file=sys.stderr)
        return 0

    staged = _staged_paths()
    if not staged:
        return 0

    max_bytes = _max_bytes()
    max_mb = max_bytes // (1024 * 1024)

    corpus_hits: list[str] = []
    oversized: list[str] = []

    for path in staged:
        normalized = path.replace("\\", "/")
        if any(normalized.startswith(p) for p in _CORPUS_PREFIXES):
            corpus_hits.append(path)
            continue
        size = _staged_size(path)
        if size is None or size <= max_bytes:
            continue
        size_mb = -(-size // (1024 * 1024))
        oversized.append(f"{path}: {size_mb} MB (limit {max_mb} MB)")

    if not corpus_hits and not oversized:
        return 0

    out = sys.stderr
    print("[corpus-artifact-guard] commit REFUSED.\n", file=out)

    if corpus_hits:
        print(
            "A project-rag corpus artifact is staged. Fleet ruling: a corpus artifact is\n"
            "NEVER committed, in any repo, in any form, git-LFS included. It is regenerable,\n"
            "so history on one is cost with no consumer.\n",
            file=out,
        )
        for hit in corpus_hits:
            print(f"  {hit}", file=out)
        print(
            "\nThese paths are gitignored, so they reached the index via `git add -f` or were\n"
            "tracked before the stanza existed. Unstage them:\n"
            "    git restore --staged -- <path>\n"
            "If they were already tracked, untrack them so the ignore rule takes effect:\n"
            "    git rm -r --cached <path>\n"
            "Ruling: DoE-claude coordinator/docs/wiki/coordinator-tripwires/"
            "corpus-artifact-is-never-committed.md\n",
            file=out,
        )

    if oversized:
        print(
            "Staged blob(s) exceed the push limit. GitHub rejects any pushed blob over\n"
            "100 MB, so this commit would succeed locally and fail at push.\n",
            file=out,
        )
        for hit in oversized:
            print(f"  {hit}", file=out)
        print(
            f"\nRaise the threshold for a known-legitimate large file:\n"
            f"    {_MAX_MB_ENV}=<N> git commit ...\n",
            file=out,
        )

    print(f"To override both legs deliberately:\n    {_BYPASS_ENV}=1 git commit ...", file=out)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
