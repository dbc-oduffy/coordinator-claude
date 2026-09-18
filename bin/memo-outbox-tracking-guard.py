#!/usr/bin/env python3
"""memo-outbox-tracking-guard — detect delivered cross-repo memos losing their sender-side record.

WHY THIS EXISTS. Nine delivered memos, sent by six different sessions, sat on disk and absent from
HEAD for days. Each had a `sent-ledger.jsonl` row and a receiver-side copy, so delivery was never
at risk — only our own record of it. Nothing detected them; they were found by hand, and only once
a tenth sweep was already in progress. The mechanism that produces them is claude-klabauter's (a
private-index landing leaves the shared index with no entry for a brand-new file while HEAD still
has the path, which git renders as a staged deletion). This is the DETECTOR, ours, and it earns its
place whether or not that fix lands: it catches the class regardless of which mechanism produced
it, and it fires on the first orphan rather than the ninth.

THREE LEGS, AND THE OBVIOUS ONE IS THE WEAKEST. The leg ORDER is load-bearing. An implementer
reaching for the state check first — as the original proposal did — ships the one leg that is
worse than no guard at all.

  LEG 1, LOG (primary). Commits that DELETED a path under `state/memo-outbox/sent/` under a subject
  that is not a memo lifecycle operation. Survives repair, because history does, and it is the only
  leg with a demonstrated catch behind it: it is what identified `69dab57b4` (7 memos), `9144d03d9`
  (1) and `fad86f91e` (1) on this tree. Acknowledged sweeps live in a baseline file so a repaired
  sweep stays *counted* without re-reporting forever — a leg that prints the same five commits every
  morning is a leg nobody reads by the second week, and the failure this guard exists to prevent is
  a signal going unread.

  LEG 2, ARMED (preventive). The only leg that stops the loss rather than reporting it.
  `git status --porcelain` reports an affected path TWICE — as staged deletion (`D `) AND as
  untracked (`??`). A genuine staged deletion never does: the file is actually gone, so there is
  nothing to report untracked. The pair is a contradiction git will happily print, a positive
  fingerprint rather than an inference from absence, and it fires while the landmine is still armed.
  Repo-wide, not scoped to memo-outbox — the fingerprint generalises to any path in the tree.

  LEG 3, STATE (backstop, DEMOTED — do not re-promote). A path git has EVER tracked under `sent/`
  is tracked at HEAD now, unless it was relocated rather than lost. Shipping this leg ALONE would
  be worse than no guard at all: it can only fire inside the window between a sweep and its repair,
  so a tree carrying the exact events this guard exists to catch reads GREEN the moment the files
  are restored. A green check retires the question. It stays as a backstop because it still works
  if the phantom mechanism is someday fixed and some other cause orphans a path — never because it
  is the cheap one. If leg 1 ever looks expensive, that is not a reason to fall back here: a cheap
  check over the wrong window is the failure, not the saving.

  WHY LEG 3 IS HISTORY-DERIVED AND NOT A LEDGER JOIN. The obvious form — one assertion per
  `sent-ledger.jsonl` row that its sender-side copy is tracked — is NOT CONSTRUCTIBLE, and the
  measurement is worth recording because it is the shape an implementer will reach for first. The
  ledger records no sender-side path field at all; the only sound join key is frontmatter
  `delivered_to`. Joined that way against this tree on 2026-08-28: 314 rows carry
  `delivery_commit_sha` (the modern memo.send), and 120 of those have NO sender-side copy — not in
  HEAD, and not on disk either. A sender-side copy is written on some send paths and not others, so
  "every ledger row has a file" is false by design, not by loss, and a leg asserting it reports
  ~120 phantom orphans while the nine real ones sit indistinguishable among them. Deriving the set
  from git history instead asks the one question that is always sound: a file git once had under
  `sent/` and does not have now is either relocated or lost, and nothing else.

NOT EXPECTED TO CATCH: an empty-tree commit (`git write-tree` against a missing GIT_INDEX_FILE
returns git's canonical empty-tree sha with exit 0). That is a private index that VANISHED, a
different defect from a shared index left without an ENTRY, and only the latter produces the
`D `+`??` pair. Discharged claude-klabauter's side; a reader who expects leg 2 to have caught it will
wrongly conclude leg 2 is broken.

METHOD TRAP: `delivery_commit_sha` in the ledger names a commit in the RECEIVER's repo, not this
one. Testing a `sent/` file against it returns "not present" for every row and reads as a clean
refutation of a true hypothesis. Every leg here queries this repo's own history instead.

Exits 1 when any leg fires — a lost sender-side record is a defect to repair, not a note to skim.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C5.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SENT_DIR = "state/memo-outbox/sent"
BASELINE = "state/memo-outbox/acknowledged-sweeps.json"

# Deletions under sent/ that are the memo lifecycle doing its job, not a sweep. Kept deliberately
# short: a subject pattern added here is a class of deletion this guard stops seeing forever, so it
# earns its place by naming an operation that legitimately removes a delivered memo, never by
# silencing a sweep whose subject happened to be inconvenient.
_LEGITIMATE_SUBJECT = re.compile(
    r"^(memo\.send:|memo-outbox:|fleet: archive \d+ actioned memo)",
)


def _git(repo_root: Path, *args: str) -> str | None:
    """stdout of a git call, or None when git is unavailable or the call fails."""
    try:
        done = subprocess.run(
            ("git", "--no-optional-locks", *args),
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError):
        return None
    return done.stdout if done.returncode == 0 else None


def _deletions(repo_root: Path) -> list[tuple[str, str, list[str]]]:
    """(sha, subject, deleted paths) for every commit that removed a path under sent/.

    One `git log` serves all three legs. Both leg 1 and leg 3 need the same history and leg 1's
    acknowledgement check needs the per-sha path list, so splitting this into a call per leg would
    spawn three git processes for one question on a machine already carrying a dozen live sessions.
    """
    out = _git(
        repo_root,
        "log",
        "--all",
        "--diff-filter=D",
        "--format=\x1e%H\x1f%s",
        "--name-only",
        "--",
        SENT_DIR,
    )
    if out is None:
        return []
    commits: list[tuple[str, str, list[str]]] = []
    for block in out.split("\x1e"):
        head, _, body = block.partition("\n")
        sha, _, subject = head.partition("\x1f")
        if not sha:
            continue
        paths = [line.strip() for line in body.splitlines() if line.strip().endswith(".md")]
        commits.append((sha, subject, paths))
    return commits


def _acknowledged(repo_root: Path) -> set[str]:
    path = repo_root / BASELINE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(sha) for sha in payload.get("acknowledged_sweeps", {})}


def _tracked(repo_root: Path) -> set[str]:
    out = _git(repo_root, "ls-files", "--", SENT_DIR)
    return {line.strip() for line in out.splitlines() if line.strip()} if out else set()


_MIN_ACK_KEY_LEN = 7


def _acknowledged_by_prefix(sha: str, known: set[str]) -> bool:
    """Whether `sha` (full, from `_deletions()`'s `%H`) is covered by a baseline key.

    Baseline keys recorded before this guard switched to full shas are short (git's `%h`,
    `core.abbrev=auto`), so an exact-match comparison against a full sha would silently stop
    matching every pre-existing entry. A key under `_MIN_ACK_KEY_LEN` is rejected rather than
    matched by prefix: short enough to plausibly collide with more than one commit, which would
    make the acknowledgement mean less than it claims.
    """
    return any(len(key) >= _MIN_ACK_KEY_LEN and sha.startswith(key) for key in known)


def leg_log(repo_root: Path) -> tuple[list[tuple[str, str]], int]:
    """(unacknowledged sweeping commits, acknowledged count).

    An acknowledgement is only honoured while the sha's paths are actually back at HEAD AND the
    sha actually has paths to check. Without the paths-back re-check the baseline is a silencing
    surface with nothing behind it: a session could record a sha with a plausible note over an
    unrepaired sweep and leg 1 would go quiet for it forever, because leg 3 fires only in the
    pre-repair window and that window has already closed. Without the non-empty check, a sha whose
    deletion set `_deletions()` couldn't see (a non-`.md` deletion under `sent/`) satisfies
    `all(...)` over an empty list vacuously — an acknowledgement of nothing.
    """
    known = _acknowledged(repo_root)
    tracked = _tracked(repo_root)
    fresh: list[tuple[str, str]] = []
    seen_known = 0
    for sha, subject, paths in _deletions(repo_root):
        if _LEGITIMATE_SUBJECT.match(subject):
            continue
        if (
            _acknowledged_by_prefix(sha, known)
            and paths
            and all(path in tracked for path in paths)
        ):
            seen_known += 1
            continue
        fresh.append((sha, subject))
    return fresh, seen_known


def _unquote(path: str) -> str:
    """Decode git's C-style quoting on a porcelain path.

    Leg 2 is repo-wide by design, so it cannot assume memo-outbox's safe topic slugs. git quotes a
    path containing whitespace, a quote, a backslash, or (under the default `core.quotepath`) any
    non-ASCII byte; comparing a quoted line against an unquoted one silently fails to pair, which
    for this leg means a real armed phantom reads clean.

    git's octal escapes (`\\NNN`) encode raw UTF-8 bytes, not Latin-1 code points, so the
    `unicode_escape` step alone yields mojibake for any non-ASCII filename: the extra
    `encode("latin-1").decode("utf-8", ...)` pass re-interprets those bytes as the UTF-8 they
    actually are. A malformed byte sequence is decoded with `backslashreplace` rather than raised
    — this runs inside a daily probe, and one odd filename taking out the whole check is worse
    than that one path reporting mangled.
    """
    if not (path.startswith('"') and path.endswith('"') and len(path) > 1):
        return path
    escaped = path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape")
    return escaped.encode("latin-1", "backslashreplace").decode("utf-8", "backslashreplace")


def leg_armed(repo_root: Path) -> list[str]:
    """Paths git reports as BOTH a staged deletion and untracked — the phantom's fingerprint."""
    # `--untracked-files=all` is load-bearing, not thoroughness. git's default collapses untracked
    # entries to the shallowest untracked DIRECTORY — a swept memo under an otherwise-untracked
    # tree renders as `?? state/`, which never pairs with the `D state/memo-outbox/sent/<memo>.md`
    # on the other line, and the fingerprint silently fails to match.
    out = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
    if out is None:
        return []
    staged_deleted: set[str] = set()
    untracked: set[str] = set()
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], _unquote(line[3:].strip())
        if code == "D ":
            staged_deleted.add(path)
        elif code == "??":
            untracked.add(path)
    return sorted(staged_deleted & untracked)


def _relocated_names(repo_root: Path) -> set[str]:
    """Basenames of memos that left sent/ by being archived rather than lost.

    Scoped to paths whose own directory chain names the memo corpus. A bare basename match across
    all of `archive/` and `state/memo-outbox/` would let any unrelated file sharing a topic slug --
    two memos months apart reusing one, or an archived artifact of another kind -- suppress a
    genuinely missing sender-side copy.
    """
    out = _git(repo_root, "ls-files", "--", "archive", "state/memo-outbox")
    if not out:
        return set()
    names = set()
    for line in out.splitlines():
        path = line.strip()
        if not path:
            continue
        parents = path.split("/")[:-1]
        if any(segment in {"memos", "memo-outbox"} for segment in parents):
            names.add(path.rsplit("/", 1)[-1])
    return names


def leg_state(repo_root: Path) -> list[str]:
    """Paths git has ever tracked under sent/ that HEAD no longer has, minus relocations."""
    tracked = _tracked(repo_root)
    relocated = _relocated_names(repo_root)
    gone: list[str] = []
    for _sha, _subject, paths in _deletions(repo_root):
        for path in paths:
            if path in tracked or path in gone:
                continue
            if path.rsplit("/", 1)[-1] in relocated:
                continue
            gone.append(path)
    return sorted(gone)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="memo-outbox-tracking-guard")
    parser.add_argument("repo_root", nargs="?", default=".")
    args = parser.parse_args(argv[1:])
    repo_root = Path(args.repo_root).resolve()

    if _git(repo_root, "rev-parse", "--git-dir") is None:
        print("memo-outbox-tracking-guard: git unavailable or not a work tree", file=sys.stderr)
        return 0

    sweeps, acknowledged = leg_log(repo_root)
    armed = leg_armed(repo_root)
    orphans = leg_state(repo_root)

    if sweeps:
        print(f"LEG 1 (log) — {len(sweeps)} unacknowledged commit(s) deleted delivered memos:")
        for sha, subject in sweeps:
            print(f"  {sha[:9]}  {subject[:110]}")
        print(
            f"  Restore the paths, then record each sha in {BASELINE} with what it swept — "
            "an acknowledged sweep stays counted without re-reporting."
        )
    if armed:
        print(f"\nLEG 2 (armed) — {len(armed)} path(s) staged-deleted AND untracked:")
        for path in armed:
            print(f"  {path}")
        print(
            "  A phantom staged deletion. The next bare commit by ANY session on this tree takes "
            "these files. A scoped `git add` disarms nothing; re-add the path to the index to "
            "disarm, and carry a pathspec on every commit until it is."
        )
    if orphans:
        print(f"\nLEG 3 (state) — {len(orphans)} ledger row(s) with no tracked file at HEAD:")
        for path in orphans:
            print(f"  {path}")

    if sweeps or armed or orphans:
        return 1

    print(
        f"memo-outbox tracking: clean (leg 1 acknowledged {acknowledged} historical sweep(s); "
        "a green leg 3 alone is not coverage)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
