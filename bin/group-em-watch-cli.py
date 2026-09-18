"""
group-em-watch-cli.py — thin front on
`coordinator_core.group_em.watch_heartbeat.read_liveness` /
`human_verdict`, callable as an independent probe against ANY repo root.

WHY `--repo-root` IS LOAD-BEARING, NOT A CONVENIENCE. Every other emitter of
this verdict resolves its target repo from a hook payload's `cwd`. This CLI
has no payload, so the only way to exercise it against an absent-heartbeat
world and then a fresh-heartbeat world is a `--repo-root` flag pointed at a
disposable fixture directory — writing the real `state/group-em-watch.json`
in a tree many live sessions share is not an option. `read_liveness` itself
takes the root as an argument rather than calling `os.getcwd()`, for the
same reason.

Holds no logic of its own: parses `--repo-root`, calls `read_liveness` then
`human_verdict`, and prints `GROUP EM WATCH: <verdict>` as the first line —
the same line shape every other emitter of this verdict uses.

Cold path — one process, one call. Direct in-process import
(`lib` bootstrap, `require_dispatch_engine_on_path`), same trampoline shape
`coordinator/bin/group-em-watch.py` uses.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C7.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional


def _resolve_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.group_em import watch_heartbeat

    return watch_heartbeat


def _parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root to read state/group-em-watch.json from (default: cwd).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root if args.repo_root else os.getcwd()
    watch_heartbeat = _resolve_module()
    liveness = watch_heartbeat.read_liveness(repo_root)
    print(f"GROUP EM WATCH: {watch_heartbeat.human_verdict(liveness)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
