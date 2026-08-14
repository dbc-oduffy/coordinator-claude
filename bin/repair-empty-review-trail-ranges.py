"""repair-empty-review-trail-ranges.py — re-derive the lost left endpoint of a
review-trail record whose `sha_range` names zero commits.

Purpose: the install-surface `.cmd` forwarder strips the `^` out of
`--sha-range SHA^..SHA` (the `%CMDCMDLINE%` capture block C1 adds is the fix
for future writes) — the caret loss is a pure single-character deletion on
the LEFT endpoint, so an intended `SHA^..SHA` (the commit against its own
first parent) persisted as `SHA..SHA`, a range that resolves to zero commits.
A peer repo reported records with this identical-endpoint shape (source
memo: docs/plans/2026-08-10-caret-fix-on-the-wrong-launcher.md § Problem).
Everything else in each record — timestamp, reviewer, verdict, scope —
survived; only the left endpoint is wrong, and it is mechanically
re-derivable: the commit's own first parent.

This tool re-derives it. It runs against an ARBITRARY repo root (a flag) —
this repo writes it, the affected peer runs it on their own corpus; this
tool must not be run against a sibling repo's tree (docs/plans/2026-08-10-
caret-fix-on-the-wrong-launcher.md, Anti-scope).

Two cases are reported, never silently handled (AC8) — a silent choice here
would be the same class of defect as the bug this tool repairs:
  - A root commit has no first parent. Not repairable; listed, left untouched.
  - A merge commit's first parent is the branch-side parent — the right
    intent for a per-commit review record, but the tool states, per record,
    that it made that choice rather than assuming it silently.
An identical-endpoint record whose SHA does not resolve in the target repo is
also reported, never repaired — that is a different defect, and guessing
would manufacture coverage the record never earned.

Rewrites ONLY the `sha_range` field's value, via a targeted substring
replacement of the exact `"sha_range":"OLD"` span — never json.load/dump —
so every other byte of the record (key order, absence of whitespace, the
hand-built serialization `_build_json_record`
(coordinator_core/ops/review_trail_write.py) emits) survives untouched.

Naked Python 3.11+, shebang-resolved, no bash — this repo's runtime
conventions (CLAUDE.md).

Usage:
  repair-empty-review-trail-ranges.py --repo-root PATH [--apply]
                                       [--review-trail-dir PATH]

Dry-run by default (no writes); pass --apply to rewrite in place.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT_GUESS = _BIN_DIR.parent.parent
if str(_REPO_ROOT_GUESS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_GUESS))

from coordinator_core.win_portability import no_console_creationflags  # noqa: E402

GENERATES = []  # operates against `--repo-root`, an explicit arbitrary flag (never a fixed claude-klabauter path — see module docstring "must not be run against a sibling repo's tree")


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    # Windows-safe: suppresses the console window a bare subprocess.run would
    # otherwise flash, paired with stdin=DEVNULL (CREATE_NO_WINDOW alone hangs
    # on Windows when stdin is inherited/invalid) — matches this repo's other
    # git subprocess call sites (coordinator_core/ops/review_trail_write.py).
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=30,
        stdin=subprocess.DEVNULL,
        **no_console_creationflags(),
    )


def _resolves(repo_root: Path, sha: str) -> bool:
    try:
        result = _git(repo_root, "cat-file", "-e", f"{sha}^{{commit}}")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _parents(repo_root: Path, sha: str) -> list[str]:
    """Return *sha*'s parent SHAs in order (empty list for a root commit)."""
    try:
        result = _git(repo_root, "rev-list", "--parents", "-n1", sha)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    tokens = result.stdout.strip().split()
    # tokens[0] is sha itself; the rest are parents, in order.
    return tokens[1:]


def _split_identical_endpoint_range(sha_range: str) -> Optional[str]:
    """Return the shared endpoint if *sha_range* is diff-shaped with
    identical left/right endpoints (the caret-strip signature), else None.

    Mirrors `_resolve_symbolic_range`'s own separator detection
    (coordinator_core/ops/review_trail_write.py) — "..." takes precedence
    over ".." when both could match, so a `sha_range` legitimately using
    the three-dot form is never misread as a two-dot split.
    """
    sep = "..." if "..." in sha_range else (".." if ".." in sha_range else None)
    if sep is None:
        return None
    left, right = sha_range.split(sep, 1)
    if not left or not right or left != right:
        return None
    return right


class _RecordOutcome:
    def __init__(self, path: Path, status: str, detail: str) -> None:
        self.path = path
        self.status = status
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.status}: {self.path.name} — {self.detail}"


def _process_record(path: Path, repo_root: Path, apply: bool) -> Optional[_RecordOutcome]:
    """Inspect one review-trail record file. Returns None for records with no
    identical-endpoint sha_range (nothing to report — they are not affected).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return _RecordOutcome(path, "SKIP_UNREADABLE", str(exc))

    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        return _RecordOutcome(path, "SKIP_UNPARSEABLE", str(exc))

    sha_range = record.get("sha_range")
    if not isinstance(sha_range, str):
        return None

    sha = _split_identical_endpoint_range(sha_range)
    if sha is None:
        return None

    sep = "..." if "..." in sha_range else ".."

    if not _resolves(repo_root, sha):
        return _RecordOutcome(
            path, "SKIP_UNRESOLVED_SHA",
            f"sha_range={sha_range!r} — {sha!r} does not resolve in {repo_root}; "
            "not repaired (a different defect — guessing would manufacture coverage)",
        )

    parents = _parents(repo_root, sha)
    if not parents:
        return _RecordOutcome(
            path, "SKIP_ROOT_COMMIT",
            f"sha_range={sha_range!r} — {sha!r} is a root commit, no first parent; "
            "not repairable, left untouched",
        )

    first_parent = parents[0]
    is_merge = len(parents) > 1
    # Review: coordinator:code-reviewer — preserve the detected separator so a
    # three-dot (symmetric-difference) record isn't silently rewritten into a
    # two-dot ancestry range.
    new_sha_range = f"{first_parent}{sep}{sha}"

    old_field = f'"sha_range":"{sha_range}"'
    new_field = f'"sha_range":"{new_sha_range}"'
    if old_field not in text:
        return _RecordOutcome(
            path, "SKIP_FIELD_NOT_FOUND",
            f"sha_range={sha_range!r} — literal field span not found verbatim in "
            f"{path}; refusing to guess at a rewrite",
        )

    merge_note = " (MERGE COMMIT — first parent is the branch-side parent; " \
        "chosen deliberately, not silently)" if is_merge else ""
    status = "REPAIRED_MERGE" if is_merge else "REPAIRED"
    detail = f"{sha_range!r} -> {new_sha_range!r}{merge_note}"

    if apply:
        new_text = text.replace(old_field, new_field, 1)
        path.write_text(new_text, encoding="utf-8")
    else:
        status = f"WOULD_{status}"

    return _RecordOutcome(path, status, detail)


def _iter_record_files(review_trail_dir: Path) -> list[Path]:
    if not review_trail_dir.is_dir():
        return []
    return sorted(p for p in review_trail_dir.glob("*.json") if p.is_file())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", required=True,
        help="Repo root to run against (an arbitrary tree — the review-trail "
        "corpus and the git history commits are resolved against, both live "
        "here).",
    )
    parser.add_argument(
        "--review-trail-dir", default=None,
        help="Override the review-trail record directory (default: "
        "<repo-root>/state/review-trail).",
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Rewrite repairable records in place. Default is dry-run: report only.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    review_trail_dir = (
        Path(args.review_trail_dir).resolve()
        if args.review_trail_dir
        else repo_root / "state" / "review-trail"
    )

    files = _iter_record_files(review_trail_dir)
    if not files:
        print(f"No review-trail records found under {review_trail_dir}")
        return 0

    outcomes = [_process_record(path, repo_root, args.apply) for path in files]
    outcomes = [o for o in outcomes if o is not None]

    if not outcomes:
        print(f"{len(files)} record(s) scanned under {review_trail_dir}; "
              "none had an identical-endpoint sha_range.")
        return 0

    for outcome in outcomes:
        print(outcome)

    repaired = sum(1 for o in outcomes if "REPAIRED" in o.status)
    root_commits = sum(1 for o in outcomes if o.status == "SKIP_ROOT_COMMIT")
    unresolved = sum(1 for o in outcomes if o.status == "SKIP_UNRESOLVED_SHA")
    other_skips = len(outcomes) - repaired - root_commits - unresolved

    mode = "applied" if args.apply else "dry-run — pass --apply to write"
    print(
        f"\n{len(outcomes)} identical-endpoint record(s) found "
        f"({len(files)} scanned): {repaired} repaired, {root_commits} root-commit "
        f"(unrepairable), {unresolved} unresolved-SHA, {other_skips} other skip(s). "
        f"[{mode}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
