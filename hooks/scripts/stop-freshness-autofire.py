"""stop-freshness-autofire.py -- Stop producer: observe doc-freshness state at the engine thresholds.

A PRODUCER folded into `stop-dispatch.py` (no hooks.json entry of its own), the idle leg of
A-FRESHNESS-THE-OPERATOR-MUST-REMEMBER-IS-NOT-MAINTAINED. It always exits 0 with empty stdout and
never tells the EM to act: it records what the probes found, and the state is reported passively
(boot orientation) from the repo-level record `_freshness_pending` keeps beside the session
directories.

On a Stop in an EM session (`em-role-asserted` present) of a repo that carries
`state/distillation-log.md` or the dev sentinel, with the throttle window elapsed or HEAD moved
since the last check, `main()` stamps the check and spawns this script detached with `--child`. The
child reserves a generation, then runs `update-docs-probes fresh-scaffold-probe` and
`update-docs-probes distill-threshold` (exit 0 = clean, 1 = due, anything else or HEAD-suppressed
drift = unknown; the probe owns the thresholds, never restated here), publishes the per-signal
results through `_freshness_pending.write_pending`, and still writes the legacy
`<hub>/<session_id>/freshness-due.json`. A due result stamps the throttle once per window, and drift
only when HEAD moved since the last stamp. Every decision after the precondition appends one row to
`.coordinator-local/freshness-autofire/fired.jsonl`. The leg never runs a skill or an index
command, and fails open on every path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import _freshness_pending  # noqa: E402
from _win_portability import no_console_spawn_kwargs  # noqa: E402

STATE_SUBDIR = os.path.join(".coordinator-local", "freshness-autofire")
STAMP_NAME = "last-check.json"
EVIDENCE_NAME = "fired.jsonl"
MARKER_NAME = "freshness-due.json"
EM_MARKER_NAME = "em-role-asserted"
THROTTLE_ENV = "COORDINATOR_FRESHNESS_AUTOFIRE_THROTTLE_HOURS"
DEFAULT_THROTTLE_HOURS = 6.0
MIN_RECHECK_S = 300.0
PROBE_BIN = "update-docs-probes"
PROBE_TIMEOUT_S = 120
DRIFT_VERB = "fresh-scaffold-probe"
DISTILL_VERB = "distill-threshold"


def throttle_seconds() -> float:
    try:
        return float(os.environ.get(THROTTLE_ENV) or DEFAULT_THROTTLE_HOURS) * 3600
    except ValueError:
        return DEFAULT_THROTTLE_HOURS * 3600


def head_sha(root: str) -> str:
    """HEAD commit of an ordinary clone, no subprocess; "" when it cannot be read cheaply."""
    git = os.path.join(root, ".git")
    try:
        if not os.path.isdir(git):
            return ""
        head = Path(git, "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head
        ref = head[4:].strip()
        ref_file = Path(git, *ref.split("/"))
        if ref_file.is_file():
            return ref_file.read_text(encoding="utf-8").strip()
        packed = Path(git, "packed-refs")
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    except OSError:
        pass
    return ""


def read_stamp(root: str) -> dict:
    try:
        data = json.loads(Path(root, STATE_SUBDIR, STAMP_NAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def write_stamp(root: str, stamp: dict) -> None:
    _atomic_write(Path(root, STATE_SUBDIR, STAMP_NAME), stamp)


def record(root: str, session_id: str, event: str, reason: str, **extra: object) -> None:
    """Append one fired-evidence row; never raises."""
    try:
        path = Path(root, STATE_SUBDIR, EVIDENCE_NAME)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.time(), "session_id": session_id, "event": event, "reason": reason}
        row.update(extra)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _hub_session_dir(root: str, session_id: str) -> str:
    from _git_common_dir import resolve_git_common_dir
    from _session_hub_path import hub_for_common

    common = resolve_git_common_dir(root)
    if not common:
        return ""
    return str(hub_for_common(Path(common)) / session_id)


def _probe_bin() -> str:
    settings = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME") or str(Path.home()), ".coordinator-claude-settings"
    )
    name = PROBE_BIN + (".exe" if sys.platform == "win32" else "")
    path = os.path.join(settings, "bin", name)
    return path if os.path.isfile(path) else ""


def _spawn_child(root: str, session_id: str, due_dir: str) -> None:
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": root,
    }
    if sys.platform == "win32":
        hidden = no_console_spawn_kwargs()
        # Trap: never DETACHED_PROCESS. It overrides CREATE_NO_WINDOW, leaving the child no console,
        # so each console grandchild (git, python) allocates a visible window.
        hidden["creationflags"] = (hidden.get("creationflags", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        kwargs.update(hidden)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child",
         "--repo", root, "--session-id", session_id, "--due-dir", due_dir],
        **kwargs,
    )


def main() -> int:
    root = ""
    session_id = ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        session_id = payload.get("session_id") or ""
        from _git_root_walk import git_root_walk

        root = git_root_walk() or ""
        if not root or not session_id:
            return 0
        now = time.time()
        head = head_sha(root)
        stamp = read_stamp(root)
        window = throttle_seconds()
        if stamp.get("fired_ts") and now - float(stamp["fired_ts"]) < window:
            write_stamp(root, {**stamp, "ts": now, "head": head})
            record(root, session_id, "skip", "fired-within-window")
            return 0
        if not _probe_bin():
            write_stamp(root, {**stamp, "ts": now, "head": head})
            record(root, session_id, "skip", "probe-bin-unresolvable")
            return 0
        due_dir = _hub_session_dir(root, session_id)
        if not due_dir:
            record(root, session_id, "skip", "session-hub-unresolvable")
            return 0
        write_stamp(root, {**stamp, "ts": now, "head": head})
        _spawn_child(root, session_id, due_dir)
        record(root, session_id, "fire", "probes-spawned", head=head)
    except BaseException:  # noqa: BLE001 -- a producer never blocks a Stop
        if root:
            record(root, session_id, "skip", "leg-raised")
    return 0


def _run_probe(bin_path: str, verb: str, root: str) -> int:
    try:
        done = subprocess.run(
            [bin_path, verb], cwd=root, capture_output=True, timeout=PROBE_TIMEOUT_S,
            **no_console_spawn_kwargs(),
        )
        return done.returncode
    except (OSError, subprocess.SubprocessError):
        return -1


def _probe_result(rc: int) -> str:
    """Exit 0 is clean, exit 1 is due, any other exit or an error is unknown."""
    return {0: "clean", 1: "due"}.get(rc, "unknown")


def child_main(argv: list[str]) -> int:
    """Reserve a generation, run both probes, publish pending state and the legacy due-marker."""
    rest = [a for a in argv[1:] if a != "--child"]
    args = dict(zip(rest[0::2], rest[1::2]))
    root, session_id, due_dir = args.get("--repo", ""), args.get("--session-id", ""), args.get("--due-dir", "")
    try:
        bin_path = _probe_bin()
        if not (root and session_id and due_dir and bin_path):
            record(root, session_id, "skip", "child-args-or-bin-unresolvable")
            return 0
        stamp = read_stamp(root)
        head = head_sha(root)
        reservation = _freshness_pending.reserve_generation(root)
        if not reservation.available:
            record(root, session_id, "skip", "pending-generation-unavailable", detail=reservation.reason)
        drift_rc = _run_probe(bin_path, DRIFT_VERB, root)
        distill_rc = _run_probe(bin_path, DISTILL_VERB, root)
        drift_suppressed = drift_rc == 1 and head == stamp.get("fired_head")
        results = {
            "update-docs": "unknown" if drift_suppressed else _probe_result(drift_rc),
            "distill": _probe_result(distill_rc),
        }
        now = time.time()
        if reservation.available:
            outcome = _freshness_pending.write_pending(
                root, _freshness_pending.make_observation(root, reservation.generation, results, head, now))
            if not outcome.ok:
                record(root, session_id, "skip", "pending-write-failed", detail=outcome.reason)
        due = []
        if results["update-docs"] == "due":
            due.append("update-docs")
        if results["distill"] == "due":
            due.append("distill")
        if not due:
            reason = "probes-clean" if {drift_rc, distill_rc} <= {0, 1} else "probe-error"
            record(root, session_id, "skip", reason, drift_rc=drift_rc, distill_rc=distill_rc)
            return 0
        _atomic_write(Path(due_dir, MARKER_NAME), {"due": due, "ts": now, "head": head})
        write_stamp(root, {**read_stamp(root), "fired_ts": now, "fired_head": head})
        record(root, session_id, "fire", "due-marker-written", due=due)
    except BaseException:  # noqa: BLE001
        record(root, session_id, "skip", "child-raised")
    return 0


if __name__ == "__main__":
    sys.exit(child_main(sys.argv) if "--child" in sys.argv else main())
