"""Grok host adapter for Unimatrix: registry discovery, spawn-free ancestor match, and headless resume.

Uses _unimatrix.proc.parent_pid (macOS libproc / Linux /proc / Windows Toolhelp) — zero `ps` spawns.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import uuid
from pathlib import Path

from _unimatrix import paths as _paths
from _unimatrix import proc as _proc

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import termios
except ImportError:
    termios = None

TURN_TIMEOUT = 600
NO_REPLY = "[unimatrix-peer-grok] no reply before timeout"


def grok_home() -> Path:
    """Grok state dir: $GROK_HOME, else ~/.grok."""
    return Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")


def grok_binary(home=None) -> str:
    """The GROK_BIN environment variable, else grok on PATH, else <grok home>/bin/grok(.exe)."""
    configured = os.environ.get("GROK_BIN")
    if configured:
        return shutil.which(configured) or configured
    found = shutil.which("grok")
    if found:
        return found
    name = "grok.exe" if os.name == "nt" else "grok"
    return str(Path(home) if home else grok_home()) + os.sep + "bin" + os.sep + name


def _clean(value) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-")


def peer_name(session_id, cwd, box_fn=None) -> str:
    """grok-<repo>-<first 8 of session id>-on-<box>; repo is the enclosing git root's name, else the cwd's."""
    base = str(cwd).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    path = Path(cwd)
    if path.is_absolute():
        try:
            root = next((p for p in (path, *path.parents) if (p / ".git").exists()), None)
        except OSError:
            root = None
        if root is not None and root.name:
            base = root.name
    box = (box_fn or _paths.local_box)()
    return f"grok-{_clean(base) or 'session'}-{session_id[:8]}-on-{_clean(box)}"


def discover_peers(home=None, pid_alive=None, taken_names=(), taken_targets=(), box_fn=None):
    """Peers for every live row of active_sessions.json: vendor grok, target the session id, cwd the row's."""
    try:
        rows = json.loads((Path(home) if home else grok_home()).joinpath("active_sessions.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    alive = pid_alive or _proc.pid_alive
    peers, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid, cwd, pid = row.get("session_id"), row.get("cwd"), row.get("pid")
        if (not isinstance(sid, str) or not sid or not isinstance(cwd, str) or not cwd
                or type(pid) is not int or sid in taken_targets or sid in seen or not alive(pid)):
            continue
        name = peer_name(sid, cwd, box_fn=box_fn)
        if name in taken_names:
            continue
        seen.add(sid)
        peers.append({"name": name, "vendor": "grok", "target": sid, "cwd": cwd})
    return peers


def own_session(home=None, pid_alive=None, parent_of=None, start=None, max_depth: int = 16, box_fn=None):
    """Which Grok session is this shell? Live registry peer whose pid is an ancestor of `start`, else None."""
    try:
        rows = json.loads((Path(home) if home else grok_home()).joinpath("active_sessions.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    by_pid = {}
    live = {p["target"]: p for p in discover_peers(home, pid_alive, box_fn=box_fn)}
    for row in rows:
        if isinstance(row, dict) and type(row.get("pid")) is int and row.get("session_id") in live:
            by_pid[row["pid"]] = live[row["session_id"]]
    if not by_pid:
        return None
    step = parent_of or _proc.parent_pid
    pid, seen = os.getpid() if start is None else start, set()
    for _ in range(max_depth):
        if pid in by_pid:
            return by_pid[pid]
        if pid is None or pid in seen:
            return None
        seen.add(pid)
        pid = step(pid)
    return None


def resume_argv(binary, session_id, text, cwd):
    """Headless resume pinned to the session cwd, never --add-dir or --fork-session.

    `--permission-mode dontAsk` and `--dangerously-skip-permissions` cancel tool calls in headless
    `-p` mode (including `unimatrix-send.py` replies); `--always-approve` auto-approves them.
    """
    return [binary, "--always-approve", "-p", text, "-r", session_id,
            "--cwd", cwd, "--output-format", "json"]


def _rows_from(registry):
    """Registry rows. A dict is one row, a session-id map, or {"sessions": [...]}."""
    if isinstance(registry, list):
        return registry
    if not isinstance(registry, dict):
        return []
    if isinstance(registry.get("sessions"), list):
        return registry["sessions"]
    if isinstance(registry.get("session_id"), str):
        return [registry]
    rows = []
    for sid, row in registry.items():
        if isinstance(sid, str) and isinstance(row, dict):
            rows.append({"session_id": sid, **row})
    return rows


def _read_rows(home=None):
    try:
        rows = json.loads((Path(home) if home else grok_home()).joinpath("active_sessions.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def _registry_map(registry, session_id=None, tty_of=None):
    """session id -> {pid, tty}. `tty_of(pid)` fills a missing tty for `session_id` only."""
    out = {}
    for row in _rows_from(registry):
        if not isinstance(row, dict):
            continue
        sid, pid = row.get("session_id"), row.get("pid")
        if not isinstance(sid, str) or not sid or type(pid) is not int:
            continue
        tty = row.get("tty") if isinstance(row.get("tty"), str) and row.get("tty") else None
        if tty is None and tty_of is not None and sid == session_id:
            found = tty_of(pid)
            tty = found if isinstance(found, str) and found else None
        out[sid] = {"pid": pid, "tty": tty}
    return out


def live_holder(session_id, registry, is_live_grok):
    """{"pid", "tty"} when `registry` has a live grok for `session_id`, else None.

    `is_live_grok(pid)` is the only liveness check. This function does no I/O.
    """
    if not isinstance(session_id, str) or not session_id or not isinstance(registry, dict):
        return None
    for row in _rows_from(registry):
        if not isinstance(row, dict) or row.get("session_id") != session_id:
            continue
        pid, tty = row.get("pid"), row.get("tty")
        if type(pid) is not int or not isinstance(tty, str) or not tty:
            return None
        if not is_live_grok(pid):
            return None
        return {"pid": pid, "tty": tty}
    return None


def _process_name(pid):
    if os.name == "nt":
        argv = ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"]
    else:
        argv = ["ps", "-o", "comm=", "-p", str(int(pid))]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    if os.name == "nt":
        return out.split('"', 2)[1] if out.startswith('"') else ""
    return out.replace("\\", "/").rsplit("/", 1)[-1]


def _default_is_live_grok(pid):
    """True when `pid` is alive and its process name is grok."""
    if not _proc.pid_alive(pid):
        return False
    return _process_name(pid).lower() in {"grok", "grok.exe"}


def _default_tty_of(pid):
    """Controlling tty of `pid` (`/dev/...`), else None. Linux reads /proc; other POSIX uses `ps`."""
    if os.name == "nt":
        return None
    if sys.platform.startswith("linux"):
        try:
            target = os.readlink(f"/proc/{int(pid)}/fd/0")
        except (OSError, ValueError):
            return None
        return target if target.startswith("/dev/") else None
    try:
        out = subprocess.run(["ps", "-o", "tty=", "-p", str(int(pid))], capture_output=True, text=True,
                             timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if not out or out in {"?", "??"}:
        return None
    return out if out.startswith("/") else "/dev/" + out


def _tiocsti():
    value = getattr(termios, "TIOCSTI", None) if termios is not None else None
    if value is not None:
        return value
    return 0x80017472 if sys.platform == "darwin" else 0x5412


def _submit_tiocsti(tty, text):
    """Push `text` and a newline onto the tty input queue. False when the kernel refuses."""
    if fcntl is None or not isinstance(tty, str) or not tty.startswith("/dev/"):
        return False
    payload = text if text.endswith("\n") else text + "\n"
    fd = -1
    try:
        fd = os.open(tty, os.O_RDWR | getattr(os, "O_NOCTTY", 0))
        request = _tiocsti()
        for ch in payload:
            fcntl.ioctl(fd, request, ch.encode())
    except OSError:
        return False
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
    return True


_SUBMIT_OSA = (
    "on run argv\n"
    "set want to item 1 of argv\n"
    "set payload to item 2 of argv\n"
    "set needle to paragraph 1 of payload\n"
    "tell application \"Terminal\"\n"
    "set hits to 0\n"
    "repeat with w in windows\n"
    "try\n"
    "repeat with t in tabs of w\n"
    "if (tty of t) is equal to want then\n"
    "set hits to hits + 1\n"
    "set selected of t to true\n"
    "set index of w to 1\n"
    "end if\n"
    "end repeat\n"
    "end try\n"
    "end repeat\n"
    "if hits is not 1 then error \"tty hits \" & hits\n"
    "activate\n"
    "end tell\n"
    "delay 0.2\n"
    "tell application \"System Events\"\n"
    "set frontApp to name of first application process whose frontmost is true\n"
    "end tell\n"
    "if frontApp is not \"Terminal\" then error \"front \" & frontApp\n"
    "tell application \"Terminal\"\n"
    "set frontTty to tty of selected tab of front window\n"
    "set blob to contents of selected tab of front window\n"
    "end tell\n"
    "if frontTty is not equal to want then error \"front tty \" & frontTty\n"
    "if my draftOf(blob) is not \"\" then error \"composer busy\"\n"
    "tell application \"System Events\" to keystroke payload\n"
    "delay 0.4\n"
    "tell application \"Terminal\"\n"
    "set blob to contents of selected tab of front window\n"
    "end tell\n"
    "if blob does not contain needle then error \"not on screen\"\n"
    "tell application \"System Events\" to key code 36\n"
    "delay 0.4\n"
    "tell application \"Terminal\"\n"
    "set blob to contents of selected tab of front window\n"
    "end tell\n"
    "if my draftOf(blob) contains needle then error \"still in composer\"\n"
    "if blob does not contain needle then error \"not queued\"\n"
    "end run\n"
    "on draftOf(blob)\n"
    "set found to \"\"\n"
    "repeat with ln in paragraphs of blob\n"
    "if ln contains \"❯\" then\n"
    "set AppleScript's text item delimiters to \"❯\"\n"
    "set tail to last text item of ln\n"
    "set AppleScript's text item delimiters to \"\"\n"
    "set keep to \"\"\n"
    "repeat with ch in characters of tail\n"
    "set c to ch as text\n"
    "if c is not \" \" and c is not \"│\" and c is not \"|\" then set keep to keep & c\n"
    "end repeat\n"
    "set found to keep\n"
    "end if\n"
    "end repeat\n"
    "return found\n"
    "end draftOf\n"
)


def submit_tty(tty, text, runner=subprocess.run):
    """Deliver `text` to the interactive grok on `tty`.

    The tty input queue is first choice. On macOS a refusal focuses the one Terminal tab
    on that tty, keystrokes the text, and presses Enter so the line queues. It raises when
    that composer already holds a draft, or when the line does not leave the composer.
    """
    if _submit_tiocsti(tty, text):
        return
    if sys.platform != "darwin":
        raise OSError(f"cannot submit to {tty}")
    proc = runner(["osascript", "-e", _SUBMIT_OSA, tty, text], capture_output=True, text=True,
                  timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if getattr(proc, "returncode", 0) != 0:
        raise subprocess.CalledProcessError(proc.returncode, "osascript", getattr(proc, "stdout", ""),
                                             getattr(proc, "stderr", ""))


def _resumable_path(home, session_id):
    """Marker path for one session, or None when `session_id` is not a single path segment."""
    if not isinstance(session_id, str) or not session_id or session_id in {".", ".."}:
        return None
    if any(sep in session_id for sep in ("/", "\\", "\x00")):
        return None
    return Path(home) / "unimatrix-resumable" / f"{session_id}.json"


def is_resumable(home, session_id):
    """True when this adapter launched `session_id` for a later headless resume."""
    path = _resumable_path(home, session_id)
    return bool(path and path.is_file())


def mark_resumable(home, session_id, cwd):
    """Record that `session_id` was launched with `--dangerously-skip-permissions` and no TUI."""
    path = _resumable_path(home, session_id)
    if path is None:
        raise ValueError(f"session id is not a marker name: {session_id!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"session_id": session_id, "cwd": cwd,
                                 "launch": "grok --dangerously-skip-permissions"}), encoding="utf-8")


def launch_argv(binary, cwd, text):
    """Headless launch. No `-r`, no TUI: the json stdout names the session a later resume targets."""
    return [binary, "--dangerously-skip-permissions", "-p", text, "--cwd", cwd, "--output-format", "json"]


def session_id_from_launch(stdout):
    """Session id printed by a headless launch, else None."""
    try:
        obj = json.loads(stdout)
    except (TypeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    for key in ("sessionId", "session_id"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def record_launch(home, stdout, cwd):
    """Mark the session a launch stdout names. None when the stdout has no session id."""
    session_id = session_id_from_launch(stdout)
    if session_id is None:
        return None
    mark_resumable(home, session_id, cwd)
    return session_id


def session_updates_path(home, cwd, session_id):
    """updates.jsonl for one grok session. The directory name is the cwd, quoted."""
    quoted = urllib.parse.quote(str(cwd), safe="")
    return Path(home) / "sessions" / quoted / session_id / "updates.jsonl"


def chunk_recorded(home, cwd, session_id, text):
    """True when that session's updates.jsonl has a user_message_chunk containing `text`."""
    if not isinstance(text, str) or not text:
        return False
    try:
        lines = session_updates_path(home, cwd, session_id).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        update = (obj.get("params") or {}).get("update") if isinstance(obj.get("params"), dict) else None
        if not isinstance(update, dict) or update.get("sessionUpdate") != "user_message_chunk":
            continue
        content = update.get("content")
        body = content.get("text") if isinstance(content, dict) else None
        if isinstance(body, str) and text in body:
            return True
    return False


def receipt(session_id):
    """The only success value: a user_message_chunk was read back for this session."""
    return {"user_message_chunk": True, "session_id": session_id, "msg_id": str(uuid.uuid4())}


async def deliver(session_id, cwd, text, timeout=TURN_TIMEOUT, binary=None, runner=subprocess.run,
                  home=None, registry=None, is_live_grok=None, submit=None, tty_of=None):
    """Resume a marked session even if its grok is still live. Otherwise submit to a TUI.

    grok-coordinator writes the resumable marker. That session is headless-resumed,
    including while the child grok holds it. An unmarked live TUI is a tty submit.
    A session with no holder and no marker is not resumed.
    """
    root = Path(home) if home is not None else grok_home()
    if is_resumable(root, session_id):
        await grok_turn(session_id, cwd, text, timeout=timeout, binary=binary, runner=runner)
        if not chunk_recorded(root, cwd, session_id, text):
            return "delivery failed: no user_message_chunk"
        return receipt(session_id)
    rows = registry if registry is not None else _read_rows(home)
    mapped = _registry_map(rows, session_id, None if registry is not None else (tty_of or _default_tty_of))
    pred = is_live_grok or _default_is_live_grok
    holder = live_holder(session_id, mapped, pred)
    if holder is not None:
        (submit or submit_tty)(holder["tty"], text)
        return {"ok": True, "written": True, "msg_id": str(uuid.uuid4())}
    row = mapped.get(session_id)
    pid = row.get("pid") if isinstance(row, dict) else None
    if type(pid) is int and not row.get("tty") and pred(pid):
        return "delivery failed: held grok session has no tty"
    return "delivery failed: grok session was not launched for headless resume"


def parse_reply(stdout):
    """The reply text of a `--output-format json` run, else None."""
    try:
        obj = json.loads(stdout)
    except (TypeError, ValueError):
        return None
    text = obj.get("text") if isinstance(obj, dict) else None
    return text if isinstance(text, str) else None


async def grok_turn(session_id, cwd, text, timeout=TURN_TIMEOUT, binary=None, runner=subprocess.run):
    """One user turn into the grok session via headless resume; returns the reply or NO_REPLY.

    A timeout, non-zero exit, launch failure or unparsable stdout returns NO_REPLY.
    """
    argv = resume_argv(binary or grok_binary(), session_id, text, cwd)
    env = {**os.environ, "UNIMATRIX_GROK_SESSION_ID": session_id}
    try:
        proc = await asyncio.to_thread(
            runner, argv, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError):
        return NO_REPLY
    if proc.returncode != 0:
        return NO_REPLY
    reply = parse_reply(proc.stdout)
    return reply if reply else NO_REPLY



class GrokAdapter:
    vendor = "grok"

    def own_session(self, env=None) -> str | None:
        peer = own_session()
        return peer["target"] if peer else None

    def discover_peers(self, home=None, pid_alive=None, taken_names=(), taken_targets=()):
        return discover_peers(home=home, pid_alive=pid_alive, taken_names=taken_names, taken_targets=taken_targets)

    async def deliver(self, peer: dict, text: str, timeout=TURN_TIMEOUT, binary=None, runner=subprocess.run,
                      home=None):
        cwd = peer.get("cwd")
        if not cwd:
            return "delivery failed: grok peer has no cwd to pin the resume to"
        return await deliver(peer["target"], cwd, text, timeout=timeout, binary=binary, runner=runner,
                             home=home if home is not None else peer.get("grok_home"))

    def owned_endpoints(self, state_root=None) -> set[str]:
        return set()
