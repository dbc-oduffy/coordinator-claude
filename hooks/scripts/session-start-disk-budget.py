"""session-start-disk-budget.py -- throttled size-and-age sweep of ~/.claude/projects and ~/.cache.

Runs only inside a live coordinator session: the async SessionStart leg (folded into
`sessionstart-async-dispatch.py`; sources startup|resume|compact) and the Stop producer
`stop-disk-budget-sweep.py` both reach it. At most one sweep per `Policy.throttle_hours`, gated by
`~/.claude/disk-budget/last-sweep.json`. The hook itself runs only the fast `~/.claude/projects`
pass under `Policy.deadline_s`, then spawns this same script as a detached `--child --max-wall-s N`
that runs the full sweep (uv clean included) under `sweep_lock`; the child's monotonic deadline is
its hard cap, and it never spawns, re-arms or persists anything beyond the stamp, `sweeps.jsonl`
and the over-budget notice. A child sweep that ends still over budget writes `over-budget.json`
(read by the sync dispatcher, which tells the session to SendMessage the live Group EM) and a
record to the repo's `state/housekeeping-failures.log`; one that ends under budget clears it.

`run_sweep` is shared with `coordinator/bin/disk-budget-sweep.py`. Fail-open: any exception is
swallowed, boot is never blocked, and `main` returns 0.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _engine_root import resolve_claude_klabauter_root  # noqa: E402

_ENGINE = resolve_claude_klabauter_root()
if _ENGINE:
    _LIB_DIR = Path(_ENGINE) / "coordinator" / "lib"
    if str(_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_LIB_DIR))
    try:
        from disk_budget import CHILD_MAX_WALL_S, Policy, resolve_roots, spawn_detached, sweep_due, sweep_lock  # noqa: E402
    except ImportError:  # an engine copy without disk_budget must not wedge boot at import time
        _ENGINE = None
if not _ENGINE:
    CHILD_MAX_WALL_S = 0.0

#: Model whose newest huggingface snapshot the cache pruner always keeps.
EMBEDDER_MODEL_ENV = "COORDINATOR_DISK_BUDGET_EMBEDDER_MODEL"

#: Env override for the volume free-space floor (bytes) below which an over-budget record alerts.
FREE_FLOOR_ENV = "COORDINATOR_DISK_BUDGET_FREE_FLOOR_BYTES"
DEFAULT_FREE_FLOOR = 20 * 1024**3

SWEEPS_LOG = "sweeps.jsonl"
STAMP = "last-sweep.json"
NOTICE = "over-budget.json"

#: Sentinel for `run_sweep(deadline_s=...)`: keep `Policy.deadline_s` (None already means unbounded).
_POLICY_DEADLINE = object()


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj), encoding="utf-8")
    os.replace(tmp, path)


def _repo_root(start: str) -> Optional[Path]:
    p = Path(start or os.getcwd()).resolve()
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d
    return None


def _record_over_budget(cwd: str, detail: str) -> None:
    """Append a record to the repo's housekeeping-failures log; best-effort."""
    try:
        root = _repo_root(cwd)
        if root is None:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log = root / "state" / "housekeeping-failures.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] CHILD FAILED script={os.path.abspath(__file__)} :: {detail}\n")
    except Exception:
        pass


def run_sweep(
    *,
    apply: bool = True,
    ignore_throttle: bool = False,
    home: Optional[Path] = None,
    environ=None,
    now: Optional[float] = None,
    cwd: str = "",
    runner=None,
    deadline_s=_POLICY_DEADLINE,
    fast: bool = False,
) -> Optional[dict]:
    """One throttled sweep. Returns the sweep record, or None when throttled.

    `apply=False` deletes nothing and writes no stamp, log or notice. `deadline_s` overrides
    `Policy.deadline_s` (None = unbounded). `fast` prunes ~/.claude/projects only and writes no
    log or notice; the full sweep belongs to the detached child. An applied sweep holds
    `sweep_lock`; when another run holds it the record has `skipped: True` and nothing is touched.
    """
    env = os.environ if environ is None else environ
    policy = Policy.from_env(env)
    if deadline_s is not _POLICY_DEADLINE:
        policy = dataclasses.replace(policy, deadline_s=deadline_s)
    wall = time.time() if now is None else now
    roots = resolve_roots(home=home, environ=env, repos=(_repo_root(cwd),) if cwd and _repo_root(cwd) else ())
    if apply and not ignore_throttle and not sweep_due(roots.state_dir, policy, wall):
        return None
    if not apply:
        return _sweep(policy, roots, env, wall, cwd, runner, False, fast)
    with sweep_lock(roots.state_dir, now=wall) as held:
        if not held:
            return {
                "ts": wall, "freed_bytes": 0, "per_root": {}, "still_over": False,
                "unfinished": False, "skipped": True,
                "log": ["sweep lock held by another run; skipped"],
            }
        return _sweep(policy, roots, env, wall, cwd, runner, True, fast)


def _sweep(policy, roots, env, wall, cwd, runner, apply, fast) -> dict:
    from disk_budget_cache import prune_cache
    from disk_budget_projects import prune_projects

    state = roots.state_dir
    stamp = state / STAMP
    if apply:
        _write_json(stamp, {"ts": wall})
    deadline = policy.deadline_at()
    projects = prune_projects(policy, deadline, roots=roots, now=wall, apply=apply)
    if fast:
        return {
            "ts": wall, "freed_bytes": projects.freed_bytes, "per_root": dict(projects.per_root),
            "still_over": projects.still_over, "unfinished": False, "log": list(projects.log),
        }
    cache = prune_cache(
        policy, deadline, roots=roots, runner=runner, apply=apply,
        embedder_model=env.get(EMBEDDER_MODEL_ENV, ""),
    )
    return _finish(projects, cache, wall, cwd, stamp, state, apply, policy, roots, env, deadline)


def _pressure(policy, deadline, roots, env, wall) -> dict:
    """Volume free bytes vs its floor, and bytes a dry-run projects pass could still delete (non-live)."""
    import shutil

    from disk_budget_projects import prune_projects

    try:
        floor = int(env.get(FREE_FLOOR_ENV, DEFAULT_FREE_FLOOR))
    except (TypeError, ValueError):
        floor = DEFAULT_FREE_FLOOR
    try:
        free = shutil.disk_usage(str(roots.state_dir.parent if roots.state_dir.parent.exists() else Path.home())).free
    except OSError:
        free = None
    try:
        deletable = prune_projects(policy, deadline, roots=roots, now=wall, apply=False).freed_bytes
    except Exception:
        deletable = None
    return {"free_bytes": free, "floor_bytes": floor, "deletable_bytes": deletable}


def _finish(projects, cache, wall, cwd, stamp, state, apply, policy, roots, env, deadline) -> dict:
    """Merge the two pass reports; an applied sweep logs the record and sets or clears the notice."""
    unfinished = any("deadline" in line for line in projects.log + cache.log)
    per_root = dict(projects.per_root)
    for k, v in cache.per_root.items():
        per_root[k] = per_root.get(k, 0) + v
    still_over = projects.still_over or cache.still_over
    record = {
        "ts": wall,
        "freed_bytes": projects.freed_bytes + cache.freed_bytes,
        "per_root": per_root,
        "still_over": still_over,
        "unfinished": unfinished,
        "log": projects.log + cache.log,
    }
    if not apply:
        return record

    if unfinished:
        stamp.unlink(missing_ok=True)
    with open(state / SWEEPS_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    notice = state / NOTICE
    if still_over:
        _write_json(notice, {
            "ts": wall, "per_root": per_root, "log": record["log"],
            **_pressure(policy, deadline, roots, env, wall),
        })
        _record_over_budget(cwd, "disk budget still over after sweep: " + json.dumps(per_root))
    else:
        notice.unlink(missing_ok=True)
    return record


def child_argv(max_wall_s: float = CHILD_MAX_WALL_S) -> list:
    """argv of the detached full-sweep child: this script by absolute path, capped at `max_wall_s`."""
    return [sys.executable, os.path.abspath(__file__), "--child", "--max-wall-s", str(max_wall_s)]


def _run_child(max_wall_s: float) -> None:
    run_sweep(cwd=os.getcwd(), ignore_throttle=True, deadline_s=max_wall_s)


def _run_hook(cwd: str) -> None:
    policy = Policy.from_env()
    state = resolve_roots().state_dir
    if not sweep_due(state, policy, time.time()):
        return
    run_sweep(cwd=cwd, ignore_throttle=True, fast=True)
    spawn_detached(child_argv())


def main(argv=None) -> int:
    if not _ENGINE:
        return 0
    try:
        ap = argparse.ArgumentParser(allow_abbrev=False, add_help=False)
        ap.add_argument("--child", action="store_true")
        ap.add_argument("--max-wall-s", type=float, default=CHILD_MAX_WALL_S)
        args, _unknown = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
        if args.child:
            _run_child(args.max_wall_s)
            return 0
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {}
        cwd = payload.get("cwd") if isinstance(payload, dict) else ""
        _run_hook(cwd if isinstance(cwd, str) else "")
    except BaseException as exc:  # noqa: BLE001 -- fail-open: boot must never wedge
        try:
            sys.__stderr__.write(f"[session-start-disk-budget] sweep failed (fail-open): {exc!r}\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
