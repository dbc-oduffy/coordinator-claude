"""session-start-scratch-retention.py -- throttled age sweep of the repo's `scratch/` directory.

The async SessionStart leg (folded into `sessionstart-async-dispatch.py`; sources
startup|resume|compact). A call site of the engine op `fleet.scratch_hygiene` through
`_scratch_retention.run_sweep`; this file removes nothing itself. The scratch root is the git
toplevel of the payload cwd plus `/scratch`; no such directory means no-op. At most one sweep per
24 h per repo, gated by `<repo>/.coordinator-local/scratch-retention/last-sweep.json`; each entry the
op reports `deleted` is appended to `removals.jsonl` beside it. Fail-open: any exception is
swallowed, boot is never blocked, and `main` returns 0.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import _scratch_retention as _sr  # noqa: E402

THROTTLE_S = 24 * 3600
STATE_DIRNAME = Path(".coordinator-local") / "scratch-retention"
STAMP = "last-sweep.json"
REMOVALS_LOG = "removals.jsonl"
#: Per-call cap; two calls (dry run, apply) must leave room inside the dispatcher's 45 s timeout.
INVOKE_TIMEOUT_S = 15.0


def _repo_root(start: str) -> Optional[Path]:
    p = Path(start or os.getcwd()).resolve()
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d
    return None


def _stamp_due(stamp: Path, now: float) -> bool:
    try:
        ts = float(json.loads(stamp.read_text(encoding="utf-8")).get("ts", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return True
    return now - ts >= THROTTLE_S


def _write_stamp(stamp: Path, now: float) -> None:
    stamp.parent.mkdir(parents=True, exist_ok=True)
    tmp = stamp.with_name(stamp.name + ".tmp")
    tmp.write_text(json.dumps({"ts": now}), encoding="utf-8")
    os.replace(tmp, stamp)


def _log_removals(log: Path, wall: float, deleted: list) -> None:
    """Append removals; entries are already deleted, so a log failure falls back to stderr."""
    try:
        with open(log, "a", encoding="utf-8") as fh:
            for rec in deleted:
                fh.write(json.dumps({"ts": wall, **rec}) + "\n")
    except OSError as exc:
        try:
            sys.__stderr__.write(
                f"[session-start-scratch-retention] removals log failed ({exc!r}); removed: "
                + json.dumps(deleted) + "\n")
        except Exception:
            pass


def run_hook(cwd: str, now: Optional[float] = None) -> list:
    """One throttled sweep for the repo containing `cwd`; returns the logged `deleted` records."""
    repo = _repo_root(cwd)
    if repo is None or not (repo / "scratch").is_dir():
        return []
    wall = time.time() if now is None else now
    state = repo / STATE_DIRNAME
    stamp = state / STAMP
    if not _stamp_due(stamp, wall):
        return []
    inner = _sr.default_invoke(INVOKE_TIMEOUT_S)
    replied = False

    def invoke(params: dict):
        nonlocal replied
        reply = inner(params)
        if isinstance(reply, dict) and isinstance(reply.get("summary"), dict):
            replied = True
        return reply

    deleted = _sr.run_sweep(repo, _sr.Policy.from_env(), invoke)
    # Invariant: the stamp is written only after the op returned a parseable reply, so an invoke
    # failure or timeout leaves it unwritten and the next session retries.
    if replied:
        _write_stamp(stamp, wall)
    if deleted:
        _log_removals(state / REMOVALS_LOG, wall, deleted)
    return deleted


def main(argv=None) -> int:
    try:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {}
        cwd = payload.get("cwd") if isinstance(payload, dict) else ""
        run_hook(cwd if isinstance(cwd, str) else "")
    except BaseException as exc:  # noqa: BLE001 -- fail-open: boot must never wedge
        try:
            sys.__stderr__.write(f"[session-start-scratch-retention] sweep failed (fail-open): {exc!r}\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
