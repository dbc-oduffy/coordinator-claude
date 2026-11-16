#!/usr/bin/env python3
"""Control entry on the receiving box: starts or wakes a session and nothing else. The message key's forced
command (unimatrix-relay.py) and the file key's (unimatrix-file-relay.py) refuse both modes, and this one refuses
every other mode.

The control key is full-admin, pinned only by from= (key body elided); `unimatrix-install.py --control-key` prints
the exact line:
  from="<cidr>[,<cidr>...]" ssh-ed25519 <key-body> unimatrix-control
The client runs this script explicitly: `<far interpreter> <this script> launch <repo-key>` (argv form). An older
forced-command key (`command="<interpreter> <this script>"`) keeps working: it gets the bare `launch <repo-key>`
or the explicit `[&] <interpreter> <this script> launch <repo-key>` in SSH_ORIGINAL_COMMAND.

Modes, read from argv or SSH_ORIGINAL_COMMAND (stdin is never read):
  launch <repo-key>   resolve <repo-key> through the machine-local `repos.` registry, mint a session name
                      `<repo-key>-<6 hex>` and run `headless-em-launch.py claude --name <name>` there
                      (`claude --bg -n <name>` on every OS); its one JSON line carries the session id. A path
                      is never accepted; an unknown key is refused.
  wake <session>      resolve the not-live local session of that name to its recorded session id and run
                      `headless-em-launch.py claude --resume <id>` in its recorded cwd; a live, unknown or
                      ambiguous name is refused. Never attaches to or messages a live session.
Reply: one JSON line {"ok": true, "session_name", "session_id", "pid", "family"} (`pid` is null for claude:
`claude --bg` owns the background process) or {"ok": false, "error"}; exit 0 only when ok.
"""
import json
import ntpath
import os
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

SESS = "~/.claude/sessions"
REPO_KEY_RE = re.compile(r"[A-Za-z0-9_]{1,56}")
NAME_RE = re.compile(r"[A-Za-z0-9_-](?:[A-Za-z0-9_.-]{0,62}[A-Za-z0-9_-])?")
SESSION_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")
LAUNCH_FAMILIES = ("claude", "codex", "agy", "grok")
DEFAULT_LAUNCH_FAMILY = "claude"
HERE = Path(__file__).resolve().parent


def settings_home():
    return Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")


def _load_sibling(filename, modname):
    import importlib.util
    spec = importlib.util.spec_from_file_location(modname, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_EXPLICIT_RE = re.compile(r"(.*\S) (\S+) (\S+)")


def _prefix_runs_this_script(prefix):
    """True when `prefix` (`[&] <interpreter> <script>`, either shell's quoting) ends in unimatrix-control.py."""
    try:
        tokens = shlex.split(prefix, posix=False)
    except ValueError:
        return False
    if tokens and tokens[0] == "&":
        tokens = tokens[1:]
    if len(tokens) < 2:
        return False
    script = tokens[-1]
    if len(script) >= 2 and script[0] == script[-1] and script[0] in "\"'":
        script = script[1:-1]
    return ntpath.basename(script) == "unimatrix-control.py"


def parse_mode(original_command):
    """Map a command string to ("launch"|"wake", arg), or None when it is not allowed.

    Accepts the bare `<verb> <arg>` (forced-command key) and the same two tokens behind an explicit
    `[&] <interpreter> <script>` prefix whose script is unimatrix-control.py (a new client over an old forced key)."""
    original_command = original_command or ""
    cmd = original_command.split()
    if len(cmd) != 2 or original_command != f"{cmd[0]} {cmd[1]}":
        m = _EXPLICIT_RE.fullmatch(original_command)
        if not m or not _prefix_runs_this_script(m.group(1)):
            return None
        cmd = [m.group(2), m.group(3)]
    if cmd[0] == "launch" and REPO_KEY_RE.fullmatch(cmd[1]):
        return "launch", cmd[1]
    if cmd[0] == "wake" and NAME_RE.fullmatch(cmd[1]):
        return "wake", cmd[1]
    return None


def resolve_repo_key(key):
    """The directory the machine-local `repos.<key>` registry entry names, or None."""
    reader = settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return None
    try:
        r = subprocess.run([_console_python(), str(reader), "get", f"repos.{key}"], capture_output=True,
                           text=True, timeout=2.0, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    path = os.path.expanduser(r.stdout.strip()) if not r.returncode else ""
    return path if path and os.path.isdir(path) else None


def named_session_entries(name):
    """Registry entries named `name` that carry a session id, as (entry, live) pairs."""
    root = os.path.expanduser(SESS)
    found = []
    try:
        files = os.listdir(root)
    except OSError:
        return found
    liveness = None
    for f in files:
        m = re.fullmatch(r"(\d+)(?:\.([0-9a-f]{16}))?\.json", f)
        if not m:
            continue
        try:
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if (isinstance(d, dict) and d.get("name") == name and isinstance(d.get("sessionId"), str)
                and SESSION_ID_RE.fullmatch(d["sessionId"])):
            liveness = liveness or _load_sibling("unimatrix-liveness.py", "unimatrix_control_liveness")
            found.append((d, bool(d.get("pid") == int(m.group(1)) and liveness.entry_live(d))))
    return found


def _console_python():
    """A real console CPython for a child argv; OSError when none resolves."""
    found = _load_sibling("lib/python_interp.py", "unimatrix_control_python_interp").resolve_console_python()
    if not found:
        raise FileNotFoundError("no console Python interpreter resolvable")
    return found


def spawn_launch(family, repo_dir, session_id, session_name, *, spawner=None, platform=None):
    """Start `headless-em-launch <family> --session-id <id> --name <name>` detached in `repo_dir`; the reply dict."""
    launcher = HERE / "headless-em-launch.py"
    if spawner is None:
        if not (HERE / "lib" / "session_detach.py").is_file():
            return {"ok": False, "error": "session_detach not vendored beside the control command"}
        spawner = _load_sibling("lib/session_detach.py", "unimatrix_control_session_detach").spawn_detached
    log = settings_home() / "unimatrix" / "control-launch.log"
    try:
        interpreter = _console_python()
    except OSError as e:
        return {"ok": False, "error": f"spawn failed: {type(e).__name__}"}
    cmd = [interpreter, str(launcher), family, "--session-id", session_id, "--name", session_name]
    pid = spawner(cmd, log, cwd=repo_dir, strict=True, platform=platform)
    if pid is None:
        return {"ok": False, "error": "spawn failed"}
    return {"ok": True, "session_name": session_name, "session_id": session_id, "pid": pid, "family": family}


def run_claude_launch(args, repo_dir, session_name, *, runner=None, timeout=60):
    """Run `headless-em-launch.py claude <args>` synchronously in `repo_dir`; the reply dict.

    The launcher prints one JSON line `{"name", "id", "session_id"}` on success; `id` is the one `claude --bg`
    printed (what `--resume` takes), `session_id` is only the grant's minted id."""
    try:
        cmd = [_console_python(), str(HERE / "headless-em-launch.py"), "claude", *args]
        r = (runner or subprocess.run)(cmd, cwd=repo_dir, capture_output=True, text=True, timeout=timeout,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": f"launch failed: {type(e).__name__}"}
    if r.returncode:
        return {"ok": False, "error": "launch failed"}
    try:
        sid = json.loads((r.stdout or "").strip().splitlines()[-1])["id"]
    except (IndexError, ValueError, KeyError, TypeError):
        return {"ok": False, "error": "launch reply unparseable"}
    if not isinstance(sid, str) or not SESSION_ID_RE.fullmatch(sid):
        return {"ok": False, "error": "launch reply unparseable"}
    return {"ok": True, "session_name": session_name, "session_id": sid, "pid": None, "family": "claude"}


def launch(key, *, resolve=None, runner=None):
    """`launch <repo-key>`: the repo resolves through the machine-local registry, never a path argument."""
    repo_dir = (resolve or resolve_repo_key)(key)
    if not repo_dir:
        return {"ok": False, "error": f"unknown repo key {key}"}
    name = f"{key}-{uuid.uuid4().hex[:6]}"
    return run_claude_launch(["--name", name], repo_dir, name, runner=runner)


def wake(name, *, sessions=None, spawner=None, platform=None, runner=None):
    """`wake <session>`: relaunch the one not-live local session of that name under its session id."""
    found = (sessions or named_session_entries)(name)
    if not found:
        return {"ok": False, "error": f"unknown session {name}"}
    if any(live for _, live in found):
        return {"ok": False, "error": f"session {name} is already live"}
    if len({d["sessionId"] for d, _ in found}) != 1:
        return {"ok": False, "error": f"session name {name} is ambiguous"}
    d = found[0][0]
    cwd = d.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return {"ok": False, "error": f"session {name} has no usable working directory"}
    family = d.get("vendor") if d.get("vendor") in LAUNCH_FAMILIES else DEFAULT_LAUNCH_FAMILY
    if family == "claude":
        return run_claude_launch(["--resume", d["sessionId"]], cwd, name, runner=runner)
    return spawn_launch(family, cwd, d["sessionId"], name, spawner=spawner, platform=platform)


def main():
    argv = sys.argv[1:]
    parsed = parse_mode(" ".join(argv) if len(argv) == 2 else os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    if parsed is None:
        sys.exit("usage: launch <repo-key> | wake <session>")
    mode, arg = parsed
    reply = (launch if mode == "launch" else wake)(arg)
    print(json.dumps(reply))
    sys.exit(0 if reply.get("ok") is True else 1)


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-control [-h]\nunimatrix control client; see the module docstring for subcommands")
        raise SystemExit(0)
    main()
