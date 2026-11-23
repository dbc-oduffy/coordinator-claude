#!/usr/bin/env python3
"""sync-shared-index: after a hand-land through a private GIT_INDEX_FILE, bring the shared
`.git/index` to the landed commit for exactly the landed paths.

Without this a plumbing commit leaves the shared index at its pre-commit blobs and the next bare
`git commit` by any peer reverts the land. Zero git spawns; entries of other paths (a peer's own
staging) are left byte-identical; the worktree is never touched.

Exit: 0 synced, 1 refused (index untouched; typed reason on stderr), 2 usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from coordinator_core.git.git_state import diff_commit_trees, head_sha, read_commit  # noqa: E402
from coordinator_core.git.index_sync import IndexSyncRefused, sync_shared_index  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="sync-shared-index",
        description="Sync the shared git index to a landed commit for exactly the named paths.",
    )
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--commit", default="HEAD", help="landed commit sha (default: HEAD)")
    ap.add_argument("--paths-from-commit", action="store_true",
                    help="use every path the commit changed against its first parent")
    ap.add_argument("paths", nargs="*", help="repo-relative landed paths")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    commit = args.commit
    paths = list(args.paths)
    try:
        if commit == "HEAD":
            commit = head_sha(repo) or ""
        if len(commit) != 40 or not all(c in "0123456789abcdef" for c in commit):
            print("sync-shared-index: --commit takes a full 40-hex sha or HEAD", file=sys.stderr)
            return 2
        if args.paths_from_commit:
            info = read_commit(repo, commit)
            changes = diff_commit_trees(repo, info.parents[0], commit) if info and info.parents else None
            if changes is None:
                print("sync-shared-index: commit unreadable or parentless", file=sys.stderr)
                return 1
            paths += [c.path for c in changes]
        if not paths:
            print("sync-shared-index: no paths given", file=sys.stderr)
            return 2
        applied = sync_shared_index(repo, commit, paths)
    except IndexSyncRefused as exc:
        print(json.dumps({"ok": False, "reason": exc.reason, "detail": exc.detail}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "commit": commit, "synced": sorted(applied)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
