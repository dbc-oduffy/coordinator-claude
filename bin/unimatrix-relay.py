"""Forced command for the unimatrix key on the receiving box: the ONLY thing that key
can run. It moves Claude Code cross-session messages between boxes and nothing else.

authorized_keys line (restrict = no pty, no forwarding of any kind; key body elided):
  restrict,command="python3 ~/.coordinator-claude-settings/unimatrix/unimatrix-relay.py" ssh-ed25519 <key-body> unimatrix

Modes, read from SSH_ORIGINAL_COMMAND:
  roster            print one JSON line per live local session: its registry entry
                    plus key file, so the far box can mirror it and SendMessage it.
  send <pid>        read one message line on stdin and deliver it to that live
                    session's socket.
  inbox <name>      register <name> as a session living on this box (entry + key on
                    stdin, two lines), listen on /tmp/cc-socks/unimatrix-<name>.sock, and
                    write each message delivered there to stdout as one line, so the
                    far box can hand it to the real session. Runs until ssh drops
                    (stdin EOF), then removes only the socket it bound.
  source            print this file, so far boxes can vendor the current relay.
  grant <grantee> <note> <ttl> <repo>
                    read the issuer's signed grant envelope (one JSON line on stdin) and hand
                    it to suite_grant.receive_relayed_grant; prints its JSON reply, exit 0 only
                    when accepted. Argv must restate the envelope or the grant is refused.

Wire facts this relies on (Claude Code 2.1.3xx, peerProtocol 1): a message is one
JSON line per connection, sender writes and closes, receiver sends nothing back.
A receiver only accepts a socket listed in ~/.claude/sessions with a key file.
"""
import hashlib
import json
import os
import re
import select
import shlex
import socket
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SESS = "~/.claude/sessions"
SOCKS = "/tmp/cc-socks"
NAME_RE = re.compile(r"[a-z0-9-]{1,40}")
# Remote-supplied registry fields a mirror entry passes through; pid, socket path and
# procStart are set locally so the far box cannot point a mirror at a local socket.
MIRROR_FIELDS = {"cwd", "entrypoint", "kind", "nameSince", "nameSource", "peerFeatures",
                 "peerProtocol", "sessionId", "startedAt", "status", "statusUpdatedAt",
                 "updatedAt", "version"}


def parse_mode(original_command):
    """Map an SSH_ORIGINAL_COMMAND string to (mode, arg) or None when it is not allowed."""
    cmd = (original_command or "").split()
    if cmd == ["roster"]:
        return "roster", None
    if cmd == ["source"]:
        return "source", None
    if len(cmd) == 2 and cmd[0] == "send" and cmd[1].isdigit():
        return "send", int(cmd[1])
    if len(cmd) == 2 and cmd[0] == "inbox" and NAME_RE.fullmatch(cmd[1]):
        return "inbox", cmd[1]
    if cmd and cmd[0] == "grant":
        return grant_args(original_command)
    return None


def grant_args(original_command):
    """`grant <grantee> <note> <ttl> <repo>` (shell-quoted note; repo `-` = none) -> ("grant", dict) or None."""
    try:
        parts = shlex.split(original_command)
    except ValueError:
        return None
    if len(parts) != 5 or not parts[3].isdigit() or int(parts[3]) <= 0:
        return None
    _, grantee, note, ttl, repo = parts
    if not grantee or not note or not repo:
        return None
    return "grant", {"grantee": grantee, "note": note, "ttl": int(ttl),
                     "repo": None if repo == "-" else repo}


# Prefix-only containment: the registry entry is a local file owned by the harness.
PIPE_PREFIX = "\\\\.\\pipe\\"


def endpoint_kind(platform=None):
    """Local-session endpoint family: named pipe on win32, unix socket on darwin/linux."""
    return "pipe" if (platform or sys.platform) == "win32" else "socket"


def alive(pid):
    if sys.platform == "win32":
        # os.kill(pid, 0) terminates the process on Windows; probe with OpenProcess instead.
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
        return bool(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def entries():
    for f in os.listdir(os.path.expanduser(SESS)):
        m = re.fullmatch(r"(\d+)\.json", f)
        if not m:
            continue
        pid = int(m.group(1))
        try:
            with open(os.path.join(os.path.expanduser(SESS), f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if d.get("pid") != pid or not alive(pid):
            continue
        keys = [k for k in os.listdir(os.path.expanduser(SESS)) if k.startswith(f"{pid}.") and k.endswith(".key")]
        if len(keys) != 1:
            continue
        yield pid, d, keys[0]


def roster():
    for pid, d, key in entries():
        if d.get("unimatrixMirror"):
            continue  # never re-export a far session we are only mirroring
        with open(os.path.join(os.path.expanduser(SESS), key), encoding="utf-8") as fh:
            body = fh.read()
        print(json.dumps({"entry": d, "key_name": key, "key": body}))


def local_reply_address(line):
    """Swap a far sender's `from` for the local mirror socket that reaches it.

    A notify_when_idle frame names its sender's reply address in `from`; the receiver drops
    any address outside its own namespace. A message frame also repeats it as a `from="..."`
    attribute in its content, which is the address the receiving agent replies to.
    """
    try:
        frame = json.loads(line)
    except ValueError:
        return line
    if not isinstance(frame, dict) or not isinstance(frame.get("from"), str):
        return line
    addr = frame["from"]
    scheme = "uds:" if addr.startswith("uds:") else ""
    for _, d, _ in entries():
        if d.get("unimatrixMirror") and d.get("unimatrixRemoteSocket") == addr[len(scheme):]:
            frame["from"] = scheme + d["messagingSocketPath"]
            msg = frame.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                msg["content"] = msg["content"].replace(
                    f'from="{addr}"', f'from="{frame["from"]}"', 1)
            return json.dumps(frame).encode() + b"\n"
    return line


def send(pid):
    target = {p: d for p, d, _ in entries()}.get(pid)
    if not target:
        sys.exit(f"no live session with pid {pid}")
    path = target["messagingSocketPath"]
    if endpoint_kind() == "pipe":
        if not path.lower().startswith(PIPE_PREFIX.lower()):
            sys.exit(f"refusing non-session pipe {path}")
        import win32file
        line = local_reply_address(sys.stdin.buffer.readline())
        h = win32file.CreateFile(path, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                 0, None, win32file.OPEN_EXISTING, 0, None)
        win32file.WriteFile(h, line)
        win32file.CloseHandle(h)
        return
    if os.path.dirname(path) != SOCKS or not stat.S_ISSOCK(os.stat(path).st_mode):
        sys.exit(f"refusing non-session socket {path}")
    line = local_reply_address(sys.stdin.buffer.readline())
    s = socket.socket(socket.AF_UNIX)
    s.connect(path)
    s.sendall(line)
    s.close()


def pid_domain():
    return "darwin" if sys.platform == "darwin" else "linux"


def check_name_free(name):
    """Exit unless `name` is neither a live local session nor held by a live mirror relay."""
    live = list(entries())
    if any(d.get("name") == name and not d.get("unimatrixMirror") for _, d, _ in live):
        sys.exit(f"name {name} belongs to a live local session")
    # A second live mirror would duplicate the name, and its bind would orphan the older
    # relay on an unlinked socket; the caller stops the old one first.
    held = [p for p, d, _ in live if d.get("name") == name and d.get("unimatrixMirror")]
    if held:
        sys.exit(f"name {name} already mirrored by live relay pid {held[0]}")


def mirror_entry(raw, name):
    """Registry entry for a mirror: allowlisted remote fields plus the far socket for the `from` swap."""
    entry = {k: v for k, v in raw.items() if k in MIRROR_FIELDS}
    entry["name"] = name
    if isinstance(raw.get("messagingSocketPath"), str):
        entry["unimatrixRemoteSocket"] = raw["messagingSocketPath"]
    return entry


def key_file_name(pid, socket_path):
    """Claude Code finds a peer's key by sha256 of that peer's own socket path."""
    return f"{pid}.{hashlib.sha256(socket_path.encode()).hexdigest()}.key"


def release(sock_path, our_ino, others):
    """Unlink `others`, and the socket only when it is still the inode this relay bound."""
    try:
        mine = os.stat(sock_path).st_ino == our_ino
    except OSError:
        mine = False
    for p in ([sock_path] if mine else []) + list(others):
        try:
            os.unlink(p)
        except OSError:
            pass


def serve(srv, stdin_fd, out):
    """Forward each message delivered to `srv` to `out`; return when stdin hits EOF."""
    while True:
        ready, _, _ = select.select([srv, stdin_fd], [], [])
        if stdin_fd in ready:
            if not os.read(stdin_fd, 4096):
                return
            continue
        c, _ = srv.accept()
        buf = b""
        while chunk := c.recv(65536):
            buf += chunk
        c.close()
        if buf.strip():
            out.write(buf.rstrip(b"\n") + b"\n")
            out.flush()


def inbox(name):
    if endpoint_kind() == "pipe":
        sys.exit("inbox: mirror sessions are hosted on macOS/Linux boxes only")
    check_name_free(name)
    entry = mirror_entry(json.loads(sys.stdin.readline()), name)
    key_body = sys.stdin.readline().rstrip("\n")
    pid = os.getpid()
    os.makedirs(SOCKS, mode=0o700, exist_ok=True)
    path = f"{SOCKS}/unimatrix-{name}.sock"
    if os.path.exists(path):
        os.unlink(path)
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(path)
    os.chmod(path, 0o600)  # bind honours umask; other local users must not reach the far session
    our_ino = os.stat(path).st_ino
    srv.listen(8)
    # Raw ps output: the harness compares it byte for byte, padded one-digit day included.
    ps = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                        capture_output=True, text=True, check=True).stdout.strip()
    entry.update(pid=pid, procStart=ps, pidDomain=pid_domain(),
                 messagingSocketPath=path, unimatrixMirror=True)
    entry_path = os.path.join(os.path.expanduser(SESS), f"{pid}.json")
    key_path = os.path.join(os.path.expanduser(SESS), key_file_name(pid, path))
    with open(entry_path, "w", encoding="utf-8") as fh:
        json.dump(entry, fh)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as kf:
        kf.write(key_body)
    try:
        serve(srv, sys.stdin.fileno(), sys.stdout.buffer)
    finally:
        release(path, our_ino, [entry_path, key_path])


def receive_grant():
    """The engine's arrival check for a relayed grant; the engine is resolved lazily."""
    try:
        from coordinator_core.group_em import suite_grant
    except ImportError:
        return _receive_via_door
    return suite_grant.receive_relayed_grant


def _receive_via_door(env):
    """Arrival check through the settings-home door; never raises.

    The forced command can run under a system python with no engine and no lib/ beside this copy.
    """
    try:
        home = Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")
        exe = home / "bin" / ("coordinator-invoke.exe" if os.name == "nt" else "coordinator-invoke")
        proc = subprocess.run([str(exe), "groupem.suite_grant_receive", json.dumps({"envelope": env})],
                              capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return {"ok": False, "reason": f"door_unavailable:{type(exc).__name__}"}
    try:
        data = json.loads(proc.stdout or "")
    except Exception:
        return {"ok": False, "reason": "door_bad_reply"}
    result = data.get("result") if isinstance(data, dict) else None
    return result if isinstance(result, dict) else {"ok": False, "reason": "door_bad_reply"}


def grant(args, line, receive=None):
    """Hand the signed envelope on `line` to the arrival check; return its reply dict.

    The argv fields only restate the envelope: any disagreement is refused before the
    engine sees it, so argv can never widen what the issuer signed.
    """
    try:
        env = json.loads(line)
    except ValueError:
        env = None
    if not isinstance(env, dict):
        return {"ok": False, "reason": "bad_envelope"}
    sid = str(env.get("grantee_session_id", ""))
    if args["grantee"] not in (sid, f'{env.get("grantee_box_id")}:{sid}'):
        return {"ok": False, "reason": "argv_mismatch:grantee"}
    if str(env.get("note", "")) != args["note"].strip():
        return {"ok": False, "reason": "argv_mismatch:note"}
    if args["repo"] is not None and env.get("scope_root") != args["repo"]:
        return {"ok": False, "reason": "argv_mismatch:repo"}
    try:
        issued = datetime.fromisoformat(str(env["issued_at"]).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(env["expires_at"]).replace("Z", "+00:00"))
        if round((expires - issued).total_seconds()) != args["ttl"] * 60:
            return {"ok": False, "reason": "argv_mismatch:ttl"}
    except (KeyError, ValueError, TypeError):
        return {"ok": False, "reason": "bad_ttl"}
    return (receive or receive_grant())(env)


def main():
    parsed = parse_mode(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    if parsed is None:
        sys.exit("usage: roster | send <pid> | inbox <name> | source | "
                 "grant <grantee> <note> <ttl> <repo>")
    mode, arg = parsed
    if mode == "grant":
        reply = grant(arg, sys.stdin.readline())
        print(json.dumps(reply))
        sys.exit(0 if reply.get("ok") is True else 1)
    if mode == "roster":
        roster()
    elif mode == "send":
        send(arg)
    elif mode == "source":
        # Far boxes vendor this relay; serving our own text keeps syncs off the full-shell key.
        sys.stdout.buffer.write(Path(__file__).read_bytes())
    else:
        inbox(arg)


if __name__ == "__main__":
    main()
