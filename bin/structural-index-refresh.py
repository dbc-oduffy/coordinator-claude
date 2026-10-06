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

Usage: structural-index-refresh.py [--root DIR] [--timeout SECONDS]
"""
from __future__ import annotations

import argparse
import json
import os
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
    try:
        path = record_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")
    except OSError:
        pass
    return rc


# project-rag's per-repo lock: a concurrent `ensure` exits 3. Benign -- the other run records its own outcome.
ALREADY_RUNNING = 3


def spawn_ensure(rag: Path, root: Path) -> "subprocess.Popen":
    """Start this CLI's `--run-and-record` wrapper in its own session/process group so it
    outlives us; the wrapper runs `ensure` and records the outcome.

    stdout/stderr go to DEVNULL: an inherited pipe would tie the child's life to ours.
    """
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
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def refresh(root: Path, timeout: float, env: Optional[dict] = None) -> Optional[str]:
    """Return the one notable line, or None when there is nothing to say."""
    environ = os.environ if env is None else env
    if environ.get(KILL_SWITCH):
        return None
    rag = resolve_index_repo()
    if rag is None:
        return None
    status = read_status(root)
    if status is None or status.get("full_rebuild_required"):
        spawn_ensure(rag, root)
        return "structural-index: cold build started in background (~3 min)"
    proc = spawn_ensure(rag, root)
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
