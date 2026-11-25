#!/usr/bin/env python3
"""Parent for a Grok session that receives Unimatrix agent mail.

Bare `grok` is unchanged. `coordinator-grok` and `grok-coordinator` stay the
parent, start `grok --dangerously-skip-permissions`, and drop a leading
`--coordinator` so a wrapper can pass that flag through. When the child
appears in active_sessions.json, this process writes the resumable marker
and holds that session's agent inbox until the child exits. Mail that
already says `From agent <name>, not the PM.` is submitted with `grok -p`
(an argv, not the TUI, and no Enter). A failed submit stays on the spool
for the Stop hook, which feeds it as a block reason. Unannounced text is
never submitted as a turn.

`grok-coordinator -p TEXT` runs one headless turn, marks the session named
in the json stdout, and prints that stdout. That path does not listen.
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


def load_grok_adapter():
    """The adapter beside this script, else the installed peer facade."""
    import importlib
    bin_dir = Path(__file__).resolve().parent
    if (bin_dir / "_unimatrix" / "adapters" / "grok.py").is_file():
        if str(bin_dir) not in sys.path:
            sys.path.insert(0, str(bin_dir))
        return importlib.import_module("_unimatrix.adapters.grok")
    path = Path(os.environ.get("COORDINATOR_SETTINGS_HOME", Path.home() / ".coordinator-claude-settings"))
    path = path / "unimatrix" / "unimatrix-peer-grok.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("unimatrix_peer_grok_coordinator", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"grok-coordinator: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def strip_coordinator(argv: list[str]) -> list[str]:
    """Drop `--coordinator`. The real grok binary does not know that flag."""
    return [arg for arg in argv if arg != "--coordinator"]


def ensure_stop_hook(home, command: str | None = None) -> Path:
    """Write the Stop hook grok loads from `<grok home>/hooks`. Same bytes stay put."""
    command = command or str(Path(__file__).resolve().parent / "unimatrix-grok-stop.py")
    body = json.dumps({
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": command, "timeout": 5}]}]},
    }, indent=2) + "\n"
    path = Path(home) / "hooks" / "unimatrix-agent-mail.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_text(encoding="utf-8") != body:
        path.write_text(body, encoding="utf-8")
    return path


def register_host_binding(session_id: str) -> bool:
    """Write the engine's host-sessions/grok row for the interactive child; False when the engine or evidence is absent.

    A copy launched outside the repo has no engine, so the fire gate's own adopt leg stays the fallback."""
    root = Path(__file__).resolve().parents[2]
    if (root / "coordinator_core").is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from coordinator_core.session import core, external_registry
        sid = core.canonical_session_env_value("GROK_SESSION_ID", session_id)
        return external_registry.adopt_grok_session(sid, {"GROK_SESSION_ID": session_id}) is not None
    except Exception:
        return False


def _hold_inbox(mod, child_pid: int, stop: threading.Event) -> None:
    """Mark the child, then listen until it exits. Mail waits on the shown spool."""
    home = mod.grok_home()
    registry = home / "active_sessions.json"
    while not stop.is_set():
        try:
            rows = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = []
        row = session_for_pid(rows, child_pid)
        if row is not None:
            session_id = row["session_id"]
            cwd = row.get("cwd") or os.getcwd()
            mod.mark_resumable(home, session_id, cwd)
            register_host_binding(session_id)

            def _on_text(text, sid=session_id, work=cwd):
                if mod.submit_peer_turn(sid, work, text) is None:
                    return
                mod.append_shown(home, sid, "UNIMATRIX-AGENT-MAIL " + text.replace("\r", " ").replace("\n", "\\n"))

            inbox = mod.AgentInbox(home, session_id, on_line=None)
            inbox.on_text = _on_text
            inbox.start()
            stop.wait()
            inbox.stop()
            return
        stop.wait(0.4)


def run_interactive(extra: list[str]) -> int:
    mod = load_grok_adapter()
    ensure_stop_hook(mod.grok_home())
    child = subprocess.Popen(interactive_argv(grok_binary(), extra))
    stop = threading.Event()
    watcher = threading.Thread(target=_hold_inbox, args=(mod, child.pid, stop), daemon=True)
    watcher.start()
    try:
        return child.wait()
    finally:
        stop.set()
        watcher.join(timeout=2)


def run_headless(text: str) -> int:
    mod = load_grok_adapter()
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
    argv = strip_coordinator(list(sys.argv[1:] if argv is None else argv))
    if "-p" in argv:
        i = argv.index("-p")
        if i + 1 >= len(argv):
            raise SystemExit("grok-coordinator: -p needs the prompt text")
        return run_headless(argv[i + 1])
    return run_interactive(argv)


if __name__ == "__main__":
    raise SystemExit(main())
