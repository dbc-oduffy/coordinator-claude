"""Register a local session on the far box through the unimatrix relay's `inbox` mode,
and carry every message the far box delivers to it back into the local session.

Usage:
  unimatrix-inbox.py <local-session-pid> <name> <log> [<deliver-endpoint>]
                     --remote <lan-ssh-alias> [--tunnel-remote <ssh-alias>] [--key <path>]

--remote is tried first; --tunnel-remote (or $UNIMATRIX_TUNNEL_REMOTE) is used only while
--remote does not answer. A dropped ssh ends this client; its supervisor restarts it and the
choice is made again.

With <deliver-endpoint> (a named pipe on Windows, a unix socket elsewhere; a session
other than the bridges' own inbox), this process rewrites `from` itself and writes
each frame straight into that endpoint. Otherwise each delivered frame is handed to
the return leg of the bridge that mirrors its far sender (registry `injectPort`),
which rewrites `from` into the local namespace and writes it into the local inbox;
that bridge's pid is the one the mirror vouches for.

The session key goes to the far box over ssh stdin only, never argv or the log.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path

IS_WIN = sys.platform == "win32"
LOOPBACK = "localhost"
SESSIONS = "~/.claude/sessions"
DEFAULT_PORT = 18991
# Registry field the mirror entries carry for the far session's real socket.
FAR_SOCKET_FIELD = "macSocketPath"

log = None


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
    path = Path(__file__).resolve().parent / "unimatrix-roster.py"
    spec = importlib.util.spec_from_file_location("unimatrix_roster", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.pick_remote(lan, tunnel)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="unimatrix-inbox.py")
    p.add_argument("pid", type=int)
    p.add_argument("name")
    p.add_argument("log")
    p.add_argument("deliver_endpoint", nargs="?")
    p.add_argument("--remote", required=True, help="ssh alias of the far box on the LAN, tried first")
    p.add_argument("--tunnel-remote", default=None, help="ssh alias over the tunnel, used only when --remote does not answer")
    p.add_argument("--key", default=None)
    a = p.parse_args(argv)
    a.key = a.key or default_key()
    a.tunnel_remote = a.tunnel_remote or os.environ.get("UNIMATRIX_TUNNEL_REMOTE") or None
    return a


def write_local(endpoint, data):
    if IS_WIN:
        import win32file
        h = win32file.CreateFile(endpoint, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                 0, None, win32file.OPEN_EXISTING, 0, None)
        win32file.WriteFile(h, data)
        win32file.CloseHandle(h)
    else:
        s = socket.socket(socket.AF_UNIX)
        s.connect(endpoint)
        s.sendall(data)
        s.close()


def _mirrors():
    for f in glob.glob(os.path.join(os.path.expanduser(SESSIONS), "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                yield json.load(fh)
        except (OSError, ValueError):
            continue


def inject_port(frame):
    src = str(frame.get("from", "")).removeprefix("uds:")
    for d in _mirrors():
        if d.get(FAR_SOCKET_FIELD) == src and d.get("injectPort"):
            return d["injectPort"]
    return DEFAULT_PORT


def _readdress(frame, src, new):
    """Point `frame` and its cross-session-message `from=` attribute at `new` (a full address string)."""
    frame["from"] = new
    if isinstance(frame.get("message"), dict):
        c = frame["message"]["content"]
        frame["message"]["content"] = c.replace(f'from="uds:{src}"', f'from="{new}"', 1)
    return json.dumps(frame).encode() + b"\n"


def _from_name(frame):
    m = frame.get("message")
    found = re.search(r'from-name="([^"]+)"', m.get("content", "")) if isinstance(m, dict) else None
    return found.group(1) if found else None


def localize(frame, line, box=None):
    """Rewrite a far `from` to an address the local receiver can reply to.

    A mirror holding the sender's far socket wins. Failing that, the mirror of the same
    session found by `from-name` (the far socket can be a cc-msg path no mirror lists).
    Failing that, the name-and-box label replaces the far /tmp/cc-socks path: a label, not an endpoint,
    and not proven replyable by the receiver. A frame with no from-name or no box is left as is.
    """
    src = str(frame.get("from", "")).removeprefix("uds:")
    mirrors = list(_mirrors())
    for d in mirrors:
        if d.get(FAR_SOCKET_FIELD) == src:
            return _readdress(frame, src, "uds:" + d["messagingSocketPath"])
    name = _from_name(frame)
    if not name:
        return line
    want = f"{name}.{box}" if box else name
    for d in mirrors:
        if d.get(FAR_SOCKET_FIELD) and d.get("name") == want and d.get("messagingSocketPath"):
            return _readdress(frame, src, "uds:" + d["messagingSocketPath"])
    return _readdress(frame, src, want) if box else line


def registration_payload(entry, key):
    """Two stdin lines for the relay's `inbox` mode: the registry entry, then the key.

    The relay names the key file itself, so nothing but the entry and the key is sent.
    """
    return json.dumps(json.loads(entry)).encode() + b"\n" + key.encode() + b"\n"


def log_far_stderr(stream):
    """Why did the far `inbox` refuse or die: copy its stderr (the refusal reason) into the log."""
    for raw in stream:
        text = raw.decode("utf-8", "replace").rstrip()
        if text:
            log.write(f"far: {text}\n")


def main(argv=None):
    global log
    a = parse_args(sys.argv[1:] if argv is None else argv)
    log = open(a.log, "a", encoding="utf-8", buffering=1)
    with open(os.path.join(os.path.expanduser(SESSIONS), f"{a.pid}.json"), encoding="utf-8") as fh:
        entry = fh.read().strip()
    (key_path,) = glob.glob(os.path.join(os.path.expanduser(SESSIONS), f"{a.pid}.*.key"))
    with open(key_path, encoding="utf-8") as fh:
        key = fh.read().strip()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
    remote = pick_remote(a.remote, a.tunnel_remote)
    p = subprocess.Popen(["ssh", "-i", a.key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
                          remote, f"inbox {a.name}"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, creationflags=flags)
    far_err = threading.Thread(target=log_far_stderr, args=(p.stderr,), daemon=True)
    far_err.start()
    # The key goes over ssh stdin only, never argv or the log.
    p.stdin.write(registration_payload(entry, key))
    p.stdin.flush()
    log.write(f"inbox {a.name} up, ssh pid {p.pid}\n")

    auth = b""
    for line in p.stdout:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            log.write(f"unparsed {line!r}\n")
            continue
        if frame.get("type") == "auth":
            auth = line  # belongs to the frame on the next line
            continue
        if a.deliver_endpoint:
            line = localize(frame, line, str(a.remote).rpartition("@")[2])
            log.write(f"<< {a.deliver_endpoint} {line!r}\n")
            try:
                write_local(a.deliver_endpoint, auth + line)
            except Exception as e:
                log.write(f"deliver failed: {e}\n")
            auth = b""
            continue
        port = inject_port(frame)
        log.write(f"<< :{port} {line!r}\n")
        try:
            with socket.create_connection((LOOPBACK, port)) as s:
                s.sendall(auth + line)
        except OSError as e:
            log.write(f"handoff failed: {e}\n")
        auth = b""
    rc = p.wait()
    far_err.join(timeout=2)
    log.write(f"inbox ended rc={rc}\n")


if __name__ == "__main__":
    main()
