"""Grok host adapter for Unimatrix: registry discovery and an agent-mail inbox.

Peer text is not a user prompt. `deliver` writes it for a listener this session
started, and never resumes `grok -p` or types into the TUI.

Uses _unimatrix.proc.parent_pid (macOS libproc / Linux /proc / Windows Toolhelp) — zero `ps` spawns.
"""
import asyncio
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import urllib.parse
import uuid
from pathlib import Path

from _unimatrix import paths as _paths
from _unimatrix import proc as _proc

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


def peer_announced(text) -> bool:
    """True when this text already carries the router's peer trailer.

    A turn that lacks it would be indistinguishable from the person at the keyboard.
    """
    return isinstance(text, str) and "From agent " in text and "not the PM." in text


def submit_peer_turn(session_id, cwd, text, binary=None, runner=subprocess.run, timeout=TURN_TIMEOUT):
    """One `grok -p` resume. The prompt is an argv, not keystrokes, and only if it names the peer.

    Returns None when the process exits 0, else a delivery-failed string. No tty and no Enter.
    """
    if not peer_announced(text):
        return "delivery failed: peer turn is missing the agent announcement"
    argv = resume_argv(binary or grok_binary(), session_id, text, cwd)
    try:
        proc = runner(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                      timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError):
        return "delivery failed: peer turn did not start"
    if getattr(proc, "returncode", 1) != 0:
        return "delivery failed: peer turn exited nonzero"
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


REFUSE_USER_SUBMIT = "delivery failed: refusing to submit a peer message as the user"
NOT_LISTENING = "delivery failed: grok session is not listening for agent mail"
_MSG_ID = re.compile(r"[0-9a-f]{32}")


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


def inbox_root(home, session_id):
    """Directory for one session's agent mail, or None when `session_id` is not a single path segment."""
    if not isinstance(session_id, str) or not session_id or session_id in {".", ".."}:
        return None
    if any(sep in session_id for sep in ("/", "\\", "\x00")):
        return None
    return Path(home) / "unimatrix-inbox" / session_id


def _listener_info(root):
    """`{"port", "token"}` from a live listener file, else None."""
    try:
        info = json.loads((root / "listener.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    port, token = info.get("port") if isinstance(info, dict) else None, info.get("token") if isinstance(info, dict) else None
    if type(port) is not int or port <= 0 or port > 65535 or not isinstance(token, str) or not token:
        return None
    return {"port": port, "token": token}


def post_agent_mail(home, session_id, text):
    """Hand `text` to the session's listener. A missing listener is not delivery.

    The file is the message. The socket line is only the listener token and the id,
    so a peer payload is never a user prompt and never a keystroke.
    """
    root = inbox_root(home, session_id)
    if root is None:
        return "delivery failed: session id is not an inbox name"
    if not isinstance(text, str) or not text:
        return "delivery failed: empty peer message"
    info = _listener_info(root)
    if info is None:
        return NOT_LISTENING
    msg_id = uuid.uuid4().hex
    pending = root / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    path = pending / f"{msg_id}.json"
    path.write_text(json.dumps({"msg_id": msg_id, "role": "agent", "text": text}, ensure_ascii=False),
                    encoding="utf-8")
    try:
        with socket.create_connection(("127.0.0.1", info["port"]), timeout=2) as conn:
            conn.sendall(f"{info['token']} {msg_id}\n".encode())
            conn.shutdown(socket.SHUT_WR)
            ack = b""
            while b"\n" not in ack and len(ack) < 16:
                chunk = conn.recv(16)
                if not chunk:
                    break
                ack += chunk
    except OSError:
        path.unlink(missing_ok=True)
        return NOT_LISTENING
    if ack.startswith(b"ok"):
        return {"written": True, "msg_id": msg_id, "channel": "agent-inbox"}
    path.unlink(missing_ok=True)
    return "delivery failed: grok session refused the agent message"


class AgentInbox:
    """Local listener. `on_line` receives one display line per accepted message."""

    def __init__(self, home, session_id, on_line=None):
        self.root = inbox_root(home, session_id)
        if self.root is None:
            raise ValueError(f"session id is not an inbox name: {session_id!r}")
        self.on_line = on_line
        self.on_text = None
        self.token = secrets.token_hex(16)
        self.lines = []
        self._stop = threading.Event()
        self._sock = None
        self._thread = None

    def start(self):
        pending = self.root / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(16)
        sock.settimeout(0.2)
        self._sock = sock
        info = {"port": sock.getsockname()[1], "token": self.token}
        target = self.root / "listener.json"
        tmp = self.root / "listener.json.tmp"
        tmp.write_text(json.dumps(info), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
        self._thread = threading.Thread(target=self._serve, name="unimatrix-grok-inbox", daemon=True)
        self._thread.start()
        return self

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._accept(conn)

    def _accept(self, conn):
        with conn:
            conn.settimeout(2)
            try:
                data = b""
                while b"\n" not in data and len(data) < 256:
                    chunk = conn.recv(256)
                    if not chunk:
                        break
                    data += chunk
                token, _, msg_id = data.split(b"\n", 1)[0].decode().partition(" ")
                if not secrets.compare_digest(token, self.token) or _MSG_ID.fullmatch(msg_id) is None:
                    conn.sendall(b"no\n")
                    return
                path = self.root / "pending" / f"{msg_id}.json"
                record = json.loads(path.read_text(encoding="utf-8"))
                text = record.get("text") if isinstance(record, dict) else None
                if not isinstance(text, str) or record.get("role") != "agent":
                    conn.sendall(b"no\n")
                    return
                shown = "UNIMATRIX-AGENT-MAIL " + text.replace("\r", " ").replace("\n", "\\n")
                self.lines.append(shown)
                if self.on_text is not None:
                    self.on_text(text)
                if self.on_line is not None:
                    self.on_line(shown)
                path.unlink(missing_ok=True)
                conn.sendall(b"ok\n")
            except (OSError, UnicodeError, ValueError):
                try:
                    conn.sendall(b"no\n")
                except OSError:
                    pass

    def stop(self):
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            sock.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        try:
            (self.root / "listener.json").unlink()
        except OSError:
            pass


def _shown_path(home, session_id):
    root = inbox_root(home, session_id)
    return None if root is None else root / "shown.jsonl"


def _lock_shown(root):
    """Exclusive lock around the shown spool. One inode, so a rename cannot drop a line."""
    root.mkdir(parents=True, exist_ok=True)
    fh = open(root / "shown.lock", "a+b")
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        if fh.read(1) == b"":
            fh.write(b" ")
            fh.flush()
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    return fh


def _unlock_shown(fh):
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    fh.close()


def append_shown(home, session_id, line):
    """Record one display line for the Stop hook. The listener has already acked."""
    path = _shown_path(home, session_id)
    if path is None:
        return
    fh = _lock_shown(path.parent)
    try:
        with path.open("a", encoding="utf-8") as out:
            out.write(line.replace("\n", "\\n") + "\n")
    finally:
        _unlock_shown(fh)


def take_shown(home, session_id):
    """Return the pending display lines and clear them, or None when there are none."""
    path = _shown_path(home, session_id)
    if path is None or not path.is_file():
        return None
    fh = _lock_shown(path.parent)
    try:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not text:
            return None
        path.write_text("", encoding="utf-8")
        return text
    finally:
        _unlock_shown(fh)


def serve_inbox(session_id, home=None):
    """Print one line per agent message. Blocks until the process is killed."""
    inbox = AgentInbox(home or grok_home(), session_id, on_line=lambda line: print(line, flush=True))
    inbox.start()
    try:
        inbox._thread.join()
    finally:
        inbox.stop()


async def deliver(session_id, cwd, text, timeout=TURN_TIMEOUT, binary=None, runner=subprocess.run,
                  home=None, registry=None, is_live_grok=None, submit=None, tty_of=None):
    """Deliver peer text to the session's agent inbox.

    `grok -p` writes a user_message_chunk. TIOCSTI and osascript type into the
    user's composer and press Enter. Neither runs here. A session with no
    listener is a failed delivery, not a queued user turn.
    The unused parameters stay so existing callers keep a stable signature.
    """
    del cwd, timeout, binary, runner, registry, is_live_grok, submit, tty_of
    return await asyncio.to_thread(post_agent_mail, home if home is not None else grok_home(), session_id, text)


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
