"""Bridge a local endpoint to a remote Claude session so SendMessage("uds:<endpoint>")
lands on another box.

The local endpoint is a Windows named pipe on Windows and a unix socket path on
macOS/Linux. Every byte both ways is logged to <log> so the wire shape is visible.

Usage:
  unimatrix-bridge.py <endpoint> <tcp-port|relay> <log> [<return-port> <local-inbox>]
                      [--remote <lan-ssh-alias>] [--tunnel-remote <ssh-alias>] [--key <path>]

<tcp-port> "relay" sends each message through the unimatrix key's forced-command
relay (`send <remote-pid>`) over `ssh <lan-ssh-alias>`; --remote is required then.
--tunnel-remote (or $UNIMATRIX_TUNNEL_REMOTE) is used only while --remote does not answer.
--key defaults to <settings home>/.secrets/ssh/unimatrix-zero.

A failed relay send writes a delivery-failure notice into the sender's inbox and is recorded;
`unimatrix-bridge.py status` prints the recent sends as delivered or FAILED.

On Windows the endpoint must be a pipe named cc-msg-<32 hex> (see mirror_pipe).

The optional return leg runs in this same process on purpose: the local inbox
only accepts writes from a process registered in ~/.claude/sessions, and this
process is the one the mirrored entry vouches for.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
LOOPBACK = "localhost"
SESSIONS = "~/.claude/sessions"
# Registry field the mirror entries carry for the far session's real socket.
FAR_SOCKET_FIELD = "macSocketPath"

log = None
cfg = None


def settings_home():
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def default_key():
    """The Unimatrix-Zero key: the settings home's, else the group-em home's; first candidate when neither exists."""
    home = settings_home()
    cands = [home / ".secrets" / "ssh" / "unimatrix-zero", home / "group-em" / ".secrets" / "ssh" / "unimatrix-zero"]
    return str(next((c for c in cands if c.is_file()), cands[0]))


def pick_remote(lan, tunnel):
    """LAN alias when it answers, else the tunnel alias; see unimatrix-roster.py (vendored beside this script)."""
    mod = sys.modules.get("unimatrix_roster")
    if mod is None:
        path = Path(__file__).resolve().parent / "unimatrix-roster.py"
        spec = importlib.util.spec_from_file_location("unimatrix_roster", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_roster"] = mod
        spec.loader.exec_module(mod)
    return mod.pick_remote(lan, tunnel)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="unimatrix-bridge.py")
    p.add_argument("endpoint")
    p.add_argument("port", help="local TCP port forwarded to the far socket, or 'relay'")
    p.add_argument("log")
    p.add_argument("return_port", nargs="?", type=int)
    p.add_argument("inbox", nargs="?")
    p.add_argument("--remote", help="ssh alias of the far box on the LAN, tried first (required for relay)")
    p.add_argument("--tunnel-remote", default=None, help="ssh alias over the tunnel, used only when --remote does not answer")
    p.add_argument("--key", default=None, help="private key for the relay (default: settings-home .secrets)")
    a = p.parse_args(argv)
    a.tunnel_remote = a.tunnel_remote or os.environ.get("UNIMATRIX_TUNNEL_REMOTE") or None
    a.port = None if a.port == "relay" else int(a.port)
    if a.port is None and not a.remote:
        p.error("relay mode needs --remote <ssh-alias>")
    a.key = a.key or default_key()
    return a


PIPE_NAME_RE = re.compile(r"cc-msg-[0-9a-f]{32}")


def mirror_pipe(far_socket):
    """Windows pipe path for a mirror of `far_socket`, shaped cc-msg-<32 hex>.

    The Windows idle-notice sender replies only to a pipe of this shape; any other name
    passes the reachability probe and the real send is then refused silently.
    """
    digest = hashlib.md5(f"unimatrix-{far_socket}".encode()).hexdigest()
    return "\\\\.\\pipe\\LOCAL\\cc-msg-" + digest


def check_endpoint(endpoint, platform=None):
    """Exit when a Windows bridge endpoint is not a cc-msg-<32 hex> pipe."""
    if (platform or sys.platform) != "win32":
        return
    leaf = endpoint.replace("/", "\\").rsplit("\\", 1)[-1]
    if not PIPE_NAME_RE.fullmatch(leaf):
        sys.exit(f"bridge endpoint {endpoint!r} must be a pipe named cc-msg-<32 hex>")


def _win():
    import pywintypes
    import win32file
    import win32pipe
    return pywintypes, win32file, win32pipe


class WinConn:
    def __init__(self, h):
        self.h = h
        self.pywintypes, self.win32file, self.win32pipe = _win()

    def read(self):
        try:
            return self.win32file.ReadFile(self.h, 65536)[1]
        except self.pywintypes.error:
            return b""

    def write(self, data):
        self.win32file.WriteFile(self.h, data)

    def close(self):
        try:
            self.win32pipe.DisconnectNamedPipe(self.h)
        except self.pywintypes.error:
            pass
        self.win32file.CloseHandle(self.h)


class SockConn:
    def __init__(self, s):
        self.s = s

    def read(self):
        try:
            return self.s.recv(65536)
        except OSError:
            return b""

    def write(self, data):
        self.s.sendall(data)

    def close(self):
        self.s.close()


def accept_loop(endpoint):
    """Yield one connection per local client on `endpoint`."""
    if IS_WIN:
        _, _, win32pipe = _win()
        while True:
            h = win32pipe.CreateNamedPipe(
                endpoint, win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                win32pipe.PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, None)
            win32pipe.ConnectNamedPipe(h, None)
            yield WinConn(h)
    else:
        if os.path.exists(endpoint):
            os.unlink(endpoint)
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(endpoint)
        os.chmod(endpoint, 0o600)
        srv.listen(8)
        while True:
            c, _ = srv.accept()
            yield SockConn(c)


def write_local(endpoint, data):
    """Deliver `data` to a local endpoint (named pipe on Windows, unix socket elsewhere)."""
    if IS_WIN:
        _, win32file, _ = _win()
        h = win32file.CreateFile(endpoint, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                 0, None, win32file.OPEN_EXISTING, 0, None)
        win32file.WriteFile(h, data)
        win32file.CloseHandle(h)
    else:
        s = socket.socket(socket.AF_UNIX)
        s.connect(endpoint)
        s.sendall(data)
        s.close()


def _load(f):
    if not f.endswith(".json"):
        return None
    try:
        with open(os.path.join(os.path.expanduser(SESSIONS), f), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def frames_to_send(buf):
    """Message lines in `buf` with the sender's auth line dropped (the relay forwards one line)."""
    return [l for l in buf.splitlines() if l.strip() and b'"type":"auth"' not in l.replace(b" ", b"")]


DELIVERY_KEEP = 100
_delivery_lock = None


def _lock():
    """Not created at import (not inert); main() calls this before any thread starts."""
    global _delivery_lock
    if _delivery_lock is None:
        _delivery_lock = threading.Lock()
    return _delivery_lock


def deliveries_path():
    return settings_home() / "unimatrix" / "deliveries.jsonl"


def record_delivery(entry):
    """Append one relay outcome to the shared delivery record, trimmed to the last DELIVERY_KEEP.

    Trap: _delivery_lock is per process; bridges for several mirrors share this file, so a
    concurrent read-trim-write across processes can drop a row (the record is advisory).
    """
    path = deliveries_path()
    try:
        with _lock():
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            rows = (rows + [json.dumps(entry)])[-DELIVERY_KEEP:]
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    except OSError as e:
        log.write(f"delivery record failed: {e}\n")


def notify_sender(line, target, error):
    """Tell the sender of `line` its cross-box message did not land, through the return leg's write_local.

    The notice is stamped from this bridge's own endpoint: the inbox accepts it because
    this process is the one the mirror entry vouches for.
    """
    try:
        sender = json.loads(line).get("from", "").removeprefix("uds:")
    except (ValueError, AttributeError):
        sender = ""
    if not sender:
        log.write("delivery-failure notice: sender unknown\n")
        return
    text = f"Delivery failed: your message to {target} did not reach the far box ({error}). It was not delivered."
    frame = json.dumps({"from": "uds:" + cfg.endpoint, "message": text}).encode() + b"\n"
    try:
        write_local(sender, frame)
    except Exception as e:  # pywintypes.error is not an OSError subclass
        log.write(f"delivery-failure notice not delivered: {e}\n")


def delivery_status(limit=10):
    """Lines describing the most recent relay sends, newest last."""
    try:
        rows = [json.loads(l) for l in deliveries_path().read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        rows = []
    if not rows:
        return ["no cross-box sends recorded"]
    return [f"{'delivered' if r['ok'] else 'FAILED   '} {r['ts']} {r['target']}" + ("" if r["ok"] else f": {r['error']}")
            for r in rows[-limit:]]


def ssh_mux_options():
    """ssh options that reuse one warm connection per remote, shortening the send leg the sender waits on.

    Win32 OpenSSH has no ControlMaster; the ControlPath is kept short (unix socket path limit).
    """
    if IS_WIN:
        return []
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return ["-o", "ControlMaster=auto", "-o", "ControlPersist=120", "-o", f"ControlPath=/tmp/unimatrix-cm-{uid}-%C",
            "-o", "ConnectTimeout=10"]


def relay_send(conn):
    # The relay forwards ONE stdin line, and the far receiver accepts tokenless
    # frames, so the sender's auth line is dropped rather than forwarded.
    buf = b""
    while chunk := conn.read():
        buf += chunk
    # Close before the ssh leg: a cold leg takes 5-10s and the sender reports a held-open
    # connection as "Failed to send" though the relay delivers. A failed relay still
    # reaches the sender, as notify_sender's delivery-failure notice in its inbox.
    conn.close()
    lines = frames_to_send(buf)
    mine = next((d for d in map(_load, os.listdir(os.path.expanduser(SESSIONS))) if d and d.get("messagingSocketPath") == cfg.endpoint), None)
    if not mine or not lines:
        log.write(f"relay: nothing to send (mirror={bool(mine)}) raw={buf!r}\n")
        return
    # A win32 peer's socket is a named pipe with no pid in its name; the roster records `farPid`.
    far_pid = str(mine.get("farPid") or os.path.basename(mine[FAR_SOCKET_FIELD]).removesuffix(".sock"))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
    for line in lines:
        log.write(f"relay >> {line!r}\n")
        target = f"{mine.get('name') or far_pid} (pid {far_pid})"
        started = time.monotonic()
        try:
            remote = pick_remote(cfg.remote, getattr(cfg, "tunnel_remote", None))
            r = subprocess.run(["ssh", "-i", cfg.key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", *ssh_mux_options(), remote, f"send {far_pid}"],
                               input=line + b"\n", capture_output=True, timeout=30, creationflags=flags)
        except Exception as e:  # any send-leg fault is a failed delivery, never a silent one
            r = subprocess.CompletedProcess([], 255, b"", f"{type(e).__name__}: {e}".encode())
        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        ms = round((time.monotonic() - started) * 1000)
        if r.returncode:
            log.write(f"relay send failed {r.returncode}: {r.stderr!r}\n")
            error = f"ssh exit {r.returncode}: " + r.stderr.decode(errors="replace").strip()[-300:]
            record_delivery({"ts": ts, "target": target, "ok": False, "error": error, "ms": ms})
            notify_sender(line, target, error)
        else:
            record_delivery({"ts": ts, "target": target, "ok": True, "ms": ms})


def pump_local_to_sock(conn, s):
    while data := conn.read():
        log.write(f">> {data!r}\n")
        s.sendall(data)
    log.write("local->sock end\n")
    try:
        s.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def pump_sock_to_local(conn, s):
    try:
        while True:
            data = s.recv(65536)
            if not data:
                break
            log.write(f"<< {data!r}\n")
            conn.write(data)
    except OSError as e:
        log.write(f"sock->local end: {e}\n")


def serve_one(conn):
    if cfg.port is None:
        relay_send(conn)  # closes conn itself, before the ssh leg
        return
    s = socket.create_connection((LOOPBACK, cfg.port))
    t = threading.Thread(target=pump_sock_to_local, args=(conn, s), daemon=True)
    t.start()
    try:
        pump_local_to_sock(conn, s)
    except OSError as e:
        log.write(f"local->sock end: {e}\n")
    t.join(timeout=10)
    s.close()
    conn.close()


def mirror_for(src):
    for f in os.listdir(os.path.expanduser(SESSIONS)):
        d = _load(f)
        if d and d.get(FAR_SOCKET_FIELD) == src:
            return d
    return None


def localize_from(data):
    # The local inbox drops a message whose `from` is not an address registered on
    # this box, so a far socket path is swapped for its mirror's local endpoint.
    # Returns (bytes, inject port of the mirror's bridge or None).
    # A frame may arrive as an auth line followed by the message line.
    lines = data.splitlines()
    try:
        msg = json.loads(lines[-1])
    except (ValueError, IndexError):
        return data, None
    head = b"".join(l + b"\n" for l in lines[:-1])
    frm = msg.get("from", "")
    if frm.startswith("uds:\\\\"):
        return data, None  # already localized by a sibling bridge
    src = frm.removeprefix("uds:")
    m = mirror_for(src)
    if not m:
        log.write(f"no mirror for sender {src}\n")
        return data, None
    local = m["messagingSocketPath"]
    msg["from"] = "uds:" + local
    if isinstance(msg.get("message"), dict):
        content = msg["message"]["content"]
        msg["message"]["content"] = content.replace(f'from="uds:{src}"', f'from="uds:{local}"', 1)
    return head + json.dumps(msg).encode() + b"\n", m.get("injectPort")


def serve_return(c):
    # One message per connection. The local inbox only accepts a message whose
    # client is the process registered for its `from` sender, so a message
    # from another mirrored session is handed to that session's own bridge.
    buf = b""
    while chunk := c.recv(65536):
        buf += chunk
    c.close()
    if not buf.strip():
        return
    data, port = localize_from(buf)
    try:
        if port and port != cfg.return_port:
            log.write(f"handoff to bridge :{port}\n")
            with socket.create_connection((LOOPBACK, port)) as s:
                s.sendall(data)
        else:
            log.write(f">> {data!r}\n")
            write_local(cfg.inbox, data)
    except OSError as e:
        log.write(f"deliver failed: {e}\n")
    except Exception as e:  # pywintypes.error is not an OSError subclass
        log.write(f"deliver failed: {e}\n")


def return_leg():
    srv = socket.create_server((LOOPBACK, cfg.return_port))
    while True:
        c, _ = srv.accept()
        log.write("return client connected\n")
        threading.Thread(target=serve_return, args=(c,), daemon=True).start()


def main(argv=None):
    global cfg, log
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["status"]:
        print("\n".join(delivery_status()))
        return
    cfg = parse_args(argv)
    check_endpoint(cfg.endpoint)
    log = open(cfg.log, "a", encoding="utf-8", buffering=1)
    _lock()  # create before serving threads exist: _lock()'s check-then-set is unguarded
    if cfg.return_port:
        threading.Thread(target=return_leg, daemon=True).start()
    for conn in accept_loop(cfg.endpoint):
        log.write("client connected\n")
        threading.Thread(target=serve_one, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
