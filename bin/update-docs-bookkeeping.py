#!/usr/bin/env python3
"""
coordinator/bin/update-docs-bookkeeping.py — operator CLI seam for
"ceremony.update_docs_bookkeeping" (coordinator_core/ops/ceremony/update_docs_bookkeeping.py).

Purpose: one in-process call that runs the /update-docs doc inventory and the doc-index regen
and prints both results. Like doc-index.py it imports the op handler directly — no subprocess,
no second interpreter. Reports by default and writes no index; judgment items stay in
`inventory.agent_worklist` for the agent.

Usage:
    update-docs-bookkeeping.py [--repo <path>] [--write] [--rebaseline] [--ack]

    --repo <path>   Repo to operate on (default: the current directory).
    --write         Rewrite every index whose comparison is ordinary drift.
    --rebaseline    Repair a hand-edited index region from source.
    --ack           Advance the inventory baseline to HEAD.

Output: `json.dumps({inventory, index_regen})`.

Exit codes: 0 success; 1 usage error; 2 the op raised (message on stderr).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_FLAGS = {"--write": "write", "--rebaseline": "rebaseline", "--ack": "ack"}


def _parse_argv(argv: list[str]) -> tuple[dict, Path]:
    params: dict = {}
    repo = Path.cwd()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--repo":
            i += 1
            if i >= len(argv):
                raise ValueError("--repo requires a value")
            repo = Path(argv[i])
        elif arg in _FLAGS:
            params[_FLAGS[arg]] = True
        else:
            raise ValueError(f"unknown argument: {arg!r}")
        i += 1
    return params, repo


def _engine():
    """Put the colocated engine on sys.path; return (op handler, git_common_dir)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core.lifecycle import git_common_dir
    from coordinator_core.ops.ceremony.update_docs_bookkeeping import _ceremony_update_docs_bookkeeping

    return _ceremony_update_docs_bookkeeping, git_common_dir


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print((__doc__ or "").strip())
        return 0
    try:
        params, repo = _parse_argv(argv)
    except ValueError as e:
        print(f"[update-docs-bookkeeping] usage error: {e}", file=sys.stderr)
        return 1

    try:
        op, git_common_dir = _engine()
        result = op(params, repo_root=git_common_dir(repo))
    except Exception as e:  # noqa: BLE001 — a client-facing CLI names any op failure
        print(f"[update-docs-bookkeeping] ceremony.update_docs_bookkeeping failed: {e}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
