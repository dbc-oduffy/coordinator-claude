#!/usr/bin/env python3
"""Parent for a Grok session Unimatrix can resume.

Bare `grok` is unchanged. This process stays the parent and starts
`grok --dangerously-skip-permissions`. When the child appears in
active_sessions.json, it writes the unimatrix-resumable marker. A later
send resumes that session instead of typing into the TUI.

`grok-coordinator -p TEXT` runs one headless turn, marks the session named
in the json stdout, and prints that stdout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path


def grok_binary() -> str:
    found = shutil.which("grok")
    if not found:
        raise SystemExit("grok-coordinator: grok is not on PATH")
    return found


def _plan_flags(extra: list[str]) -> list[str]:
    """Plan-role model and effort, unless the caller already set them.

    The catalogue lives in coordinator_core. A copy of this file launched outside the
    repo keeps the CLI default rather than inventing an id.
    """
    root = Path(__file__).resolve().parents[2]
    catalogue = root / "coordinator_core" / "agent_pipe" / "model_tiers.py"
    if catalogue.is_file() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from coordinator_core.agent_pipe.model_tiers import GROK_EM_EFFORT, model_for_role
    except Exception:
        return []
    flags: list[str] = []
    if not any(a in ("--model", "-m") or a.startswith("--model=") for a in extra):
        flags += ["--model", model_for_role("grok", "em")]
    if not any(a in ("--reasoning-effort", "--effort") or a.startswith("--reasoning-effort=")
               or a.startswith("--effort=") for a in extra):
        flags += ["--reasoning-effort", GROK_EM_EFFORT]
    return flags


def interactive_argv(binary: str, extra: list[str]) -> list[str]:
    """TUI launch. No -p and no -r. Extra args are the caller's."""
    return [binary, "--dangerously-skip-permissions", *_plan_flags(extra), *extra]


def headless_argv(binary: str, cwd: str, text: str) -> list[str]:
    """One headless turn. The json stdout names the session to mark."""
    return [binary, "--dangerously-skip-permissions", *_plan_flags([]), "-p", text, "--cwd", cwd,
            "--output-format", "json"]


def session_for_pid(rows, pid: int):
    """The registry row whose pid is the child, else None."""
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("pid") == pid and isinstance(row.get("session_id"), str):
            return row
    return None


def _adapter():
    path = Path(os.environ.get("COORDINATOR_SETTINGS_HOME", Path.home() / ".coordinator-claude-settings"))
    path = path / "unimatrix" / "unimatrix-peer-grok.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("unimatrix_peer_grok_coordinator", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"grok-coordinator: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mark_child(mod, child_pid: int, stop: threading.Event) -> None:
    home = mod.grok_home()
    registry = home / "active_sessions.json"
    while not stop.is_set():
        try:
            rows = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = []
        row = session_for_pid(rows, child_pid)
        if row is not None:
            mod.mark_resumable(home, row["session_id"], row.get("cwd") or os.getcwd())
            return
        stop.wait(0.4)


def run_interactive(extra: list[str]) -> int:
    mod = _adapter()
    child = subprocess.Popen(interactive_argv(grok_binary(), extra))
    stop = threading.Event()
    watcher = threading.Thread(target=_mark_child, args=(mod, child.pid, stop), daemon=True)
    watcher.start()
    try:
        return child.wait()
    finally:
        stop.set()
        watcher.join(timeout=2)


def run_headless(text: str) -> int:
    mod = _adapter()
    cwd = os.getcwd()
    proc = subprocess.run(headless_argv(grok_binary(), cwd, text), cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    if proc.returncode == 0:
        mod.record_launch(mod.grok_home(), proc.stdout, cwd)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-p" in argv:
        i = argv.index("-p")
        if i + 1 >= len(argv):
            raise SystemExit("grok-coordinator: -p needs the prompt text")
        return run_headless(argv[i + 1])
    return run_interactive(argv)


if __name__ == "__main__":
    raise SystemExit(main())
