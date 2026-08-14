"""spawn-trace-capture.py — one-command spawn-count capture for one op invocation.

Spec backlink: state/handoffs/2026-08-14-windows-spawn-economics.md
(deliverable_id: dlv-spawn-per-call-economics-on-windows-ba9646).

WHAT THIS DOES
    Runs a given command under `coordinator/lib/spawn-trace/sitecustomize.py`
    (injected via PYTHONPATH) and reports how many subprocess.Popen /
    os.exec* / os.posix_spawn / os.system events were raised, transitively,
    by the whole process tree the command's own top-level Python interpreter
    spawns — see that module's docstring for exactly what it can and cannot
    see. Portable, stdlib-only: no shell, no bash, works unmodified on
    Windows (os.name == "nt").

USAGE
    python3 coordinator/bin/spawn-trace-capture.py -- <command> [args...]
    python3 coordinator/bin/spawn-trace-capture.py --json -- <command> [args...]

    The FIRST word of <command> must itself be a Python interpreter (or a
    script with a python shebang the OS execs into one) for the hook to have
    anything to attach to on its first hop -- a bare shell command with no
    Python anywhere in its tree will trace nothing (see sitecustomize.py's
    own "WHAT THIS CANNOT SEE" section for the analogous Windows cmd.exe gap).

OUTPUT
    Human-readable summary (spawn count, wall time, one line per event) to
    stdout, plus the raw JSONL log path. `--json` instead prints one JSON
    object with the same fields, for scripted multi-run capture.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HOOK_DIR = str(Path(__file__).resolve().parents[1] / "lib" / "spawn-trace")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spawn-trace-capture.py",
        description="Trace transitive process spawns for one command invocation.",
    )
    p.add_argument("--json", action="store_true", help="print one JSON summary object")
    p.add_argument("--keep-log", action="store_true", help="do not delete the JSONL log after summarizing")
    p.add_argument("command", nargs=argparse.REMAINDER, help="command to run, after --")
    return p


def run_capture(command: list[str], keep_log: bool = False) -> dict:
    """Run `command` under the spawn tracer; return a summary dict.

    `command` must be a full argv list (no shell). The tracer's log lives in
    a fresh tmp file per call so concurrent captures never collide.
    """
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("no command given (usage: ... -- <command> [args...])")

    log_fd, log_path = tempfile.mkstemp(prefix="spawn-trace-", suffix=".jsonl")
    os.close(log_fd)
    os.unlink(log_path)  # tracer appends; start from a clean, non-existent path

    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _HOOK_DIR + (os.pathsep + existing_pp if existing_pp else "")
    env["SPAWN_TRACE_LOG"] = log_path

    start = time.monotonic()
    proc = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    wall_seconds = time.monotonic() - start

    events: list[dict] = []
    log_file = Path(log_path)
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))

    summary = {
        "command": command,
        "returncode": proc.returncode,
        "wall_seconds": wall_seconds,
        "spawn_count": len(events),
        "events": events,
        "log_path": log_path if keep_log else None,
        "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
    }

    if keep_log:
        pass
    elif log_file.exists():
        log_file.unlink()

    return summary


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = run_capture(args.command, keep_log=args.keep_log)
    except ValueError as exc:
        print(f"spawn-trace-capture.py: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"command: {' '.join(summary['command'])}")
    print(f"returncode: {summary['returncode']}")
    print(f"wall_seconds: {summary['wall_seconds']:.3f}")
    print(f"spawn_count: {summary['spawn_count']}")
    for ev in summary["events"]:
        print(f"  pid={ev['pid']} ppid={ev['ppid']} {ev['event']}: {' '.join(ev['argv'])}")
    if summary["log_path"]:
        print(f"log: {summary['log_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
