"""structural-index-refresh -- never-blocking ceremony hook for project-rag's `ensure`.

Keeps `<repo>/.structural-index/` current by running project-rag's
`project_rag_scripts/structural_index_refresh.py ensure` at ceremony gates. Contract:
`<project-rag>/project_rag_scripts/structural_index_templates/README.md`.

Always exits 0. Prints one line only when it did something notable. Silent exit 0 when
project-rag is not on this box (registry key `repos.project_rag`) or when the kill-switch
`COORDINATOR_STRUCTURAL_INDEX_REFRESH_OFF` is set to a non-empty value.

A missing `status.json` or `full_rebuild_required` means a cold build (~3 min): started
detached, not waited on. Otherwise `ensure` runs with a short wait (~4 s when nothing
drifted); on timeout it is left running detached. `ensure` runs under THIS interpreter, which
must carry the pinned tree-sitter grammars -- ensure refuses rather than emit a partial index.

Every run's outcome (started_at, finished_at, exit_code, stderr_tail) lands in
`<repo>/.structural-index/refresh-last.json`, written by the detached `--run-and-record` wrapper.
A launch refused for memory (`post_close_admission.admit`) instead writes a record with
`exit_code` null and a `deferred` reason, and spawns nothing.

Usage: structural-index-refresh.py [--root DIR] [--timeout SECONDS]
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# The published transform runs this source with no `__file__`; there the
# engine is already importable.
if "__file__" in globals():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from cc_invoke import ensure_engine_on_path

    ensure_engine_on_path(__file__)


def _python() -> str:
    """A console interpreter for a spawned child; `sys.executable` when the resolver is not importable."""
    try:
        from python_interp import resolve_console_python
    except ImportError:
        return sys.executable
    return resolve_console_python() or sys.executable


# Writes a refresh-status record under the gitignored .structural-index/.
GENERATES = []

KILL_SWITCH = "COORDINATOR_STRUCTURAL_INDEX_REFRESH_OFF"
# Fragmented: the publish transform rewrites the contiguous codename, and a rewritten key never resolves.
_INDEX_REPO = "project" "_rag"
REGISTRY_KEY = f"repos.{_INDEX_REPO}"
ENSURE_SCRIPT = Path(f"{_INDEX_REPO}_scripts") / "structural_index_refresh.py"
DEFAULT_TIMEOUT = 30.0
RECORD_NAME = "refresh-last.json"
STDERR_TAIL_LINES = 5


def resolve_index_repo() -> Optional[Path]:
    """project-rag checkout from the machine-local registry; None when absent for any reason."""
    try:
        from coordinator_core.machine_resolver import registry_get
        value = registry_get(REGISTRY_KEY) or ""
    except Exception:  # an unresolvable registry means no index repo, never a crash
        return None
    if not value:
        return None
    path = Path(value)
    return path if (path / ENSURE_SCRIPT).is_file() else None


def read_status(root: Path) -> Optional[dict]:
    try:
        data = json.loads((root / ".structural-index" / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def record_path(root: Path) -> Path:
    return root / ".structural-index" / RECORD_NAME


def run_and_record(rag: Path, root: Path) -> int:
    """Run `ensure` to completion, capture stderr, and write refresh-last.json.

    The detached child's body: nothing else observes a detached run's outcome. Never raises;
    a record that cannot be written is dropped.
    """
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    started = time.strftime(stamp, time.gmtime())
    cmd = [_python(), str(rag / ENSURE_SCRIPT), "ensure", "--root", str(root)]
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, errors="replace", cwd=str(root),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rc, err = proc.returncode, proc.stderr or ""
    except Exception as exc:
        rc, err = -1, f"{type(exc).__name__}: {exc}"
    lines = [ln for ln in err.splitlines() if ln.strip()]
    record = {
        "started_at": started,
        "finished_at": time.strftime(stamp, time.gmtime()),
        "exit_code": rc,
        "stderr_tail": lines[-STDERR_TAIL_LINES:],
    }
    _write_record(root, record)
    return rc


# project-rag's per-repo lock: a concurrent `ensure` exits 3. Benign -- the other run records its own outcome.
ALREADY_RUNNING = 3


ADMISSION_LABEL = "structural-index"
POSIX_NICE = 10


def _write_record(root: Path, record: dict) -> None:
    try:
        path = record_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")
    except OSError:
        pass


def admit_launch(root: Path) -> tuple[Optional[object], str]:
    """Gate a launch on `post_close_admission.admit`; posts nothing.

    Returns ``(verdict, reason)`` with ``verdict`` None when deferred. Fail-closed: an
    unimportable or raising admission module defers. The START notice is `post_start`'s, after Popen.
    """
    try:
        from coordinator_core.ops.ceremony import post_close_admission as admission

        avail, trusted = admission.read_available()
        verdict = admission.admit(ADMISSION_LABEL, avail, trusted)
        return (verdict if verdict.admitted else None), verdict.reason
    except Exception as exc:
        return None, f"admission unavailable ({type(exc).__name__})"


def post_start(verdict: object, pid: int) -> None:
    """Post the one START notice for a spawned child, naming its PID; never raises."""
    try:
        from coordinator_core.ops.ceremony import post_close_admission as admission

        admission.notice(verdict, f"{ADMISSION_LABEL}:{int(time.time())}", pids=[pid])
    except Exception:
        pass


def _platform() -> str:
    return sys.platform


def _libc():
    return ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)


# Linux ioprio_set(2): syscall numbers by machine; IOPRIO_WHO_PROCESS=1, IOPRIO_CLASS_IDLE=3.
_IOPRIO_SYSCALL = {"x86_64": 251, "aarch64": 30, "arm64": 30, "i386": 289, "i686": 289}
_IOPRIO_WHO_PROCESS = 1
_IOPRIO_CLASS_IDLE = 3
_IOPRIO_CLASS_SHIFT = 13
# macOS setiopolicy_np(IOPOL_TYPE_DISK, IOPOL_SCOPE_PROCESS, IOPOL_THROTTLE).
_IOPOL_TYPE_DISK = 1
_IOPOL_SCOPE_PROCESS = 0
_IOPOL_THROTTLE = 3


def lower_io_priority_self() -> None:
    """Best-effort low disk I/O priority for the calling process (Linux idle class, macOS throttle).

    Runs in the forked child before exec. Any failure or missing API is skipped silently.
    """
    try:
        plat = _platform()
        if plat.startswith("linux"):
            number = _IOPRIO_SYSCALL.get(platform.machine().lower())
            if number is not None:
                _libc().syscall(number, _IOPRIO_WHO_PROCESS, 0, _IOPRIO_CLASS_IDLE << _IOPRIO_CLASS_SHIFT)
        elif plat == "darwin":
            _libc().setiopolicy_np(_IOPOL_TYPE_DISK, _IOPOL_SCOPE_PROCESS, _IOPOL_THROTTLE)
    except Exception:
        pass


def lower_io_priority_pid(pid: int) -> None:
    """Best-effort very-low I/O priority for a spawned Windows child via psutil; skipped without psutil."""
    try:
        import psutil

        psutil.Process(pid).ionice(psutil.IOPRIO_VERYLOW)
    except Exception:
        pass


def _child_preexec() -> None:
    os.nice(POSIX_NICE)
    lower_io_priority_self()


def spawn_ensure(rag: Path, root: Path) -> "Optional[subprocess.Popen]":
    """Start this CLI's `--run-and-record` wrapper in its own session/process group so it
    outlives us; the wrapper runs `ensure` and records the outcome.

    Returns None, spawning nothing, when admission defers; the deferral lands in refresh-last.json.
    The wrapper starts at below-normal CPU priority and low I/O priority; `ensure` inherits both.
    The START notice posts only after a successful Popen, carrying the child's PID; a failed
    Popen propagates and posts nothing.
    stdout/stderr go to DEVNULL: an inherited pipe would tie the child's life to ours.
    """
    verdict, reason = admit_launch(root)
    if verdict is None:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_record(root, {"started_at": stamp, "finished_at": stamp, "exit_code": None,
                             "deferred": reason, "stderr_tail": []})
        return None
    cmd = [_python(), str(Path(__file__).resolve()), "--run-and-record",
           "--root", str(root), "--rag", str(rag)]
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(root),
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        )
    else:
        kwargs["start_new_session"] = True
        kwargs["preexec_fn"] = _child_preexec
    proc = subprocess.Popen(cmd, **kwargs)
    if os.name == "nt":
        lower_io_priority_pid(proc.pid)
    post_start(verdict, proc.pid)
    return proc


def refresh(root: Path, timeout: float, env: Optional[dict] = None) -> Optional[str]:
    """Return the one notable line, or None when there is nothing to say."""
    environ = os.environ if env is None else env
    if environ.get(KILL_SWITCH):
        return None
    rag = resolve_index_repo()
    if rag is None:
        return None
    status = read_status(root)
    cold = status is None or status.get("full_rebuild_required")
    proc = spawn_ensure(rag, root)
    if proc is None:
        return "structural-index: refresh deferred (insufficient memory); index may be stale"
    if cold:
        return "structural-index: cold build started in background (~3 min)"
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"structural-index: refresh still running in background (>{timeout:g}s)"
    if rc == ALREADY_RUNNING:
        return None
    if rc != 0:
        return f"structural-index: ensure exited {rc}; index may be stale"
    mode = ((read_status(root) or {}).get("refresh") or {}).get("mode")
    return None if mode in (None, "noop") else f"structural-index: refreshed ({mode})"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--run-and-record", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--rag", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        from coordinator_core.cli_entry import recording_declared_writes
    except Exception:  # the published transform may carry no engine
        return _run(args)
    with recording_declared_writes():
        return _run(args)


def _run(args: argparse.Namespace) -> int:
    if args.run_and_record:
        run_and_record(Path(args.rag), Path(args.root).resolve())
        return 0
    try:
        line = refresh(Path(args.root).resolve(), args.timeout)
    except Exception as exc:  # never block a ceremony
        line = f"structural-index: skipped ({type(exc).__name__}: {exc})"
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
