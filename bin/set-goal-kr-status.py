#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""set-goal-kr-status.py — CLI trampoline over claude-klabauter's goal.set_kr_status op
(coordinator_core/ops/goal_kr_status.py).

Purpose: the missing `coordinator/bin/` door for `goal.set_kr_status` — every
sibling goal op (append-goal-event.py, emit-goal-from-artifact.py,
goal-coverage-scan.py, reassess-goal-krs) has one; this op didn't, so callers
had to reach for `python3 -m coordinator_core.invoke goal.set_kr_status ...`
directly. This is a thin door only: it parses CLI flags into the op's params
dict and spawns the op via `coordinator/bin/lib/cc_invoke.py`'s `cc_invoke()`
(same non-bare envelope-unwrap transport `reassess-goal-krs` uses) — it does
NOT reimplement the locked read-modify-write, the line-oriented KR parsing,
or the provenance stamping. Exactly one implementation of the status-rewrite
algorithm exists in the repo: `coordinator_core.ops.goal_kr_status`.

Usage:
    set-goal-kr-status.py --goal-file <path> --kr-id <id> --status <status>
                           [--repo-root <path>] [--timeout <secs>]

Options:
    --goal-file <path>  Absolute path to the target state/goals/*.yaml artifact
                         (required; must already exist — the op raises
                         FileNotFoundError otherwise, never silently creates one).
    --kr-id <id>        The key_results[] entry's `id` value, matched verbatim
                         (required).
    --status <status>   The new status value; non-empty after strip (required).
    --repo-root <path>  Any path inside goal-file's git repository, used to
                         locate the cross-process lock sidecar. Default: the
                         goal file's parent directory (mirrors the op's own
                         default — see goal_kr_status.py's set_kr_status()).
    --timeout <secs>    Max seconds to wait for the cross-process lock
                         (default: 10.0, matching the op's own default).

Exit codes:
    0 — success; the op's bare result ({goal_file, kr_id, status}) printed to
        stdout as JSON.
    1 — client-side argument error (missing --goal-file / --kr-id / --status).
    2 — everything else: unresolvable git repo root for the cc_invoke spawn,
        or any cc_invoke transport/op failure (op-level ValueError such as an
        unknown kr_id or a missing status: field, missing goal file, lock
        timeout, malformed envelope).

Spec backlink: docs/plans/2026-07-25-goal-kr-status-provenance-and-bin-door.md
Source memo: cross-repo/inbox/2026-07-25-example-market-data-repo-em-goal-engine-seams-and-kr-status-provenance.md
"""

from __future__ import annotations

import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import cc_invoke  # noqa: E402


def _find_repo_root(start: str) -> str:
    """Walk upward from `start` looking for a `.git` entry; falls back to
    `start` itself if none is found (mirrors reassess-goal-krs's own
    derivation — this is the repo the cc_invoke spawn resolves CLAUDE_KLABAUTER_ROOT
    relative to, a distinct concern from --repo-root, which is the op's own
    lock-sidecar placement param).
    """
    cur = start
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return start
        cur = parent


def _parse_args(argv: list[str]) -> dict[str, str]:
    goal_file = ""
    kr_id = ""
    status = ""
    repo_root = ""
    timeout = ""

    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if arg == "--goal-file":
            if i + 1 >= n:
                print("ERROR: --goal-file requires an argument", file=sys.stderr)
                sys.exit(1)
            goal_file = argv[i + 1]
            i += 2
        elif arg == "--kr-id":
            if i + 1 >= n:
                print("ERROR: --kr-id requires an argument", file=sys.stderr)
                sys.exit(1)
            kr_id = argv[i + 1]
            i += 2
        elif arg == "--status":
            if i + 1 >= n:
                print("ERROR: --status requires an argument", file=sys.stderr)
                sys.exit(1)
            status = argv[i + 1]
            i += 2
        elif arg == "--repo-root":
            if i + 1 >= n:
                print("ERROR: --repo-root requires an argument", file=sys.stderr)
                sys.exit(1)
            repo_root = argv[i + 1]
            i += 2
        elif arg == "--timeout":
            if i + 1 >= n:
                print("ERROR: --timeout requires an argument", file=sys.stderr)
                sys.exit(1)
            timeout = argv[i + 1]
            i += 2
        elif arg in ("--help", "-h"):
            sys.stdout.write(__doc__ or "")
            sys.exit(0)
        else:
            print(f"ERROR: Unknown argument: {arg}", file=sys.stderr)
            sys.exit(1)

    if not goal_file:
        print("ERROR: --goal-file is required", file=sys.stderr)
        sys.exit(1)
    if not kr_id:
        print("ERROR: --kr-id is required", file=sys.stderr)
        sys.exit(1)
    if not status:
        print("ERROR: --status is required", file=sys.stderr)
        sys.exit(1)

    return {
        "goal_file": goal_file,
        "kr_id": kr_id,
        "status": status,
        "repo_root": repo_root,
        "timeout": timeout,
    }


def main(argv: list[str]) -> int:
    parsed = _parse_args(argv)

    params: dict[str, object] = {
        "goal_file": parsed["goal_file"],
        "kr_id": parsed["kr_id"],
        "status": parsed["status"],
    }
    if parsed["repo_root"]:
        params["repo_root"] = parsed["repo_root"]
    if parsed["timeout"]:
        params["timeout"] = float(parsed["timeout"])

    cwd_repo_root = _find_repo_root(os.getcwd())

    try:
        result = cc_invoke("goal.set_kr_status", params, cwd_repo_root)
    except RuntimeError as exc:
        print(f"set-goal-kr-status: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
