#!/usr/bin/env python3
"""push-hold -- freeze or release the cadence push for a repo or one branch.

Usage:
  push-hold set   [--branch X] [--reason TEXT] [--allow-sha SHA] [--repo PATH]
  push-hold clear [--branch X] [--repo PATH]
  push-hold list  [--repo PATH]
  push-hold set   --compile [--reason TEXT] [--repo PATH]
  push-hold clear --compile [--repo PATH]
  push-hold stamp-green --tree SHA [--repo PATH]

--compile is the compile hold (the ladder refuses control/plugin merges while
set); it excludes --branch and --allow-sha. stamp-green records a compile-green
tree that lifts the compile hold for that tree.

Without --branch the hold covers the whole repo. The hold lives in the repo's
git config (`coordinator.pushHold`, `branch.<X>.coordinatorPushHold`);
`push.outstanding` reports a held branch as skipped `push:hold`; a manual
`git push` of a held branch is refused. --allow-sha names the one commit a
manual `git push <remote> <sha>:refs/heads/<branch>` may release.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)
    from coordinator_core import push_hold

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["set", "clear", "list", "stamp-green"])
    ap.add_argument("--branch", default=None)
    ap.add_argument("--reason", default=None)
    ap.add_argument("--allow-sha", default=None)
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--tree", default=None)
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    args = ap.parse_args(argv)

    if args.compile and (args.branch or args.allow_sha):
        ap.error("--compile excludes --branch and --allow-sha")
    if args.compile and args.action not in ("set", "clear"):
        ap.error("--compile applies to set and clear only")
    if args.action == "stamp-green" and not args.tree:
        ap.error("stamp-green requires --tree SHA")
    if args.reason and args.action in ("list", "clear", "stamp-green"):
        ap.error("--reason applies to set only")
    if args.tree and args.action != "stamp-green":
        ap.error("--tree applies to stamp-green only")

    from coordinator_core.argv_fidelity import ArgvFidelityError, refuse_newline_argv

    try:
        refuse_newline_argv(args.reason, flag_name="--reason", remedy="a hold reason is a single line.")
    except ArgvFidelityError as exc:
        ap.error(str(exc))

    if args.action == "list":
        holds = push_hold.list_holds(args.repo)
        allow = f" (allow {holds['repo_allow']})" if holds["repo_allow"] else ""
        print(f"repo: {holds['repo'] or '-'}{allow}")
        for name, note in holds["branches"].items():
            a = holds["branch_allow"].get(name)
            print(f"branch {name}: {note}" + (f" (allow {a})" if a else ""))
        green = push_hold.read_compile_green_tree(args.repo)
        print(f"compile: {push_hold.read_compile_hold(args.repo) or '-'}" + (f" (green {green})" if green else ""))
        return 0
    if args.action == "stamp-green":
        ok = push_hold.stamp_green_tree(args.repo, args.tree)
    elif args.compile:
        ok = (
            push_hold.set_compile_hold(args.repo, args.reason)
            if args.action == "set"
            else push_hold.clear_compile_hold(args.repo)
        )
    elif args.action == "set":
        ok = push_hold.set_hold(args.repo, args.branch, args.reason, args.allow_sha)
    else:
        ok = push_hold.clear_hold(args.repo, args.branch)
    if not ok:
        print(f"push-hold {args.action} failed in {args.repo}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
