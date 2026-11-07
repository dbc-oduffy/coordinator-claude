"""Forced command for the unimatrix key on the receiving box: the ONLY thing that key
can run. It moves Claude Code cross-session messages between boxes and nothing else.

authorized_keys line (restrict = no pty, no forwarding of any kind; key body elided). The exact
line for a box, with absolute interpreter and relay paths, is printed by `unimatrix-install.py --install`:
  restrict,command="/opt/homebrew/bin/python3 /Users/me/.coordinator-claude-settings/unimatrix/unimatrix-relay.py" ssh-ed25519 <key-body> unimatrix

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
  membership get    print the held signed membership snapshot (canonical JSON line, then its
                    base64 signature line); exit 1 when none is held.
  membership put    read the snapshot line and base64 signature line on stdin, verify against
                    the pinned signer key and the held epoch, adopt, and reconcile the
                    relay-managed authorized_keys lines (from= pins generated); prints a JSON
                    reply, exit 0 only when adopted. The relay never signs.

Wire facts this relies on (Claude Code 2.1.3xx, peerProtocol 1): a message is one
JSON line per connection, sender writes and closes, receiver sends nothing back.
A receiver only accepts a socket listed in ~/.claude/sessions with a key file.
"""
import base64
import hashlib
import json
import os
import re
import select
import shlex
import signal
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
    if cmd == ["membership", "get"] or cmd == ["membership", "put"]:
        return "membership", cmd[1]
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


def _engine_roots():
    """Candidate engine roots: env locators first, then the checkout this copy sits in."""
    for var in ("COORDINATOR_ENGINE_SOURCE_ROOT", "COORDINATOR_ENGINE_ROOT", "CLAUDE_KLABAUTER_ROOT"):
        if os.environ.get(var):
            yield Path(os.environ[var])
    yield Path(__file__).resolve().parents[2]


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None


def _head_sha(root):
    """Checkout HEAD sha read from .git files (no git spawn); None when unresolvable."""
    git = Path(root) / ".git"
    if git.is_file():
        ptr = _read_text(git) or ""
        if not ptr.startswith("gitdir:"):
            return None
        git = (Path(root) / ptr[7:].strip()).resolve()
    head = _read_text(git / "HEAD")
    if not head:
        return None
    if not head.startswith("ref:"):
        return head
    ref = head[4:].strip()
    sha = _read_text(git / ref)
    if sha:
        return sha
    packed = _read_text(git / "packed-refs") or ""
    for ln in packed.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return None


def engine_fields():
    """engine_sha (published `_engine_stamp`), engine_checkout_sha and, when a surfaced record
    exists, engine_freshness. Standalone: reads files only, no coordinator_core import."""
    sha = checkout = None
    for root in _engine_roots():
        if sha is None:
            sha = _read_text(root / "coordinator_core" / "_engine_stamp")
        if checkout is None:
            checkout = _head_sha(root)
    out = {"engine_sha": sha, "engine_checkout_sha": checkout}
    home = Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")
    try:
        rec = json.loads((home / "coordinator" / "klabauter-freshness.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = None
    if isinstance(rec, dict) and rec:
        out["engine_freshness"] = rec
    return out


def roster():
    fields = engine_fields()
    for pid, d, key in entries():
        if d.get("unimatrixMirror") or d.get("macSocketPath"):
            continue  # never re-export a far session we are only mirroring, whichever OS made the entry
        with open(os.path.join(os.path.expanduser(SESS), key), encoding="utf-8") as fh:
            body = fh.read()
        print(json.dumps({"entry": d, "key_name": key, "key": body, **fields}))


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


def proc_start(pid):
    """Raw `ps` start stamp of `pid` ('' when no such process); None when ps cannot answer."""
    try:
        return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                              capture_output=True, text=True).stdout.strip()
    except OSError:
        return None


def stale_holder(pid, d):
    """Is this mirror entry a corpse: its pid is live only because the OS recycled it?

    A hard reset leaves mirror entries behind; a recycled pid passes `alive` and would
    hold the name forever. A mirror records the start stamp it was born with, so a
    different stamp on that pid means another process. No recorded stamp, or ps unable
    to answer, is never proof of staleness.
    """
    recorded = d.get("procStart")
    if not isinstance(recorded, str) or not recorded:
        return False
    actual = proc_start(pid)
    return actual is not None and actual != recorded


def client_address():
    """Source address of the ssh client driving this relay ('' when not under sshd)."""
    parts = os.environ.get("SSH_CONNECTION", "").split()
    return parts[0] if parts else ""


def superseded_holder(d, client):
    """Is this live mirror relay held open by a dead connection of the same near box?

    A near box that hard-resets leaves its old `inbox` relay alive on a half-open ssh; the
    restarted client (one per name per near box) asks for the same name from the same
    address, so the old relay can only be that client's own ghost. No recorded or current
    address, or a different one, never proves it.
    """
    recorded = d.get("unimatrixClient")
    return bool(client) and isinstance(recorded, str) and recorded == client


def check_name_free(name, client=""):
    """Exit unless `name` is neither a live local session nor held by a live mirror relay.

    Returns (pid, key file, kill) for each mirror holder of `name` that does not count as a
    holder: a recycled-pid corpse (kill False) or a live relay superseded by `client`'s own
    reconnect (kill True).
    """
    live = list(entries())
    if any(d.get("name") == name and not d.get("unimatrixMirror") for _, d, _ in live):
        sys.exit(f"name {name} belongs to a live local session")
    # A second live mirror would duplicate the name, and its bind would orphan the older
    # relay on an unlinked socket; the caller stops the old one first.
    mirrors = [(p, d, k) for p, d, k in live if d.get("name") == name and d.get("unimatrixMirror")]
    freed = [(p, k, False) for p, d, k in mirrors if stale_holder(p, d)]
    freed += [(p, k, True) for p, d, k in mirrors
              if p not in {f[0] for f in freed} and superseded_holder(d, client)]
    held = [p for p, _, _ in mirrors if p not in {f[0] for f in freed}]
    if held:
        sys.exit(f"name {name} already mirrored by live relay pid {held[0]}")
    return freed


def drop_stale(freed):
    """Stop each superseded relay, then remove the registry entry and key of every freed holder."""
    base = os.path.expanduser(SESS)
    for pid, key, kill in freed:
        if kill:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        for f in (f"{pid}.json", key):
            try:
                os.unlink(os.path.join(base, f))
            except OSError:
                pass


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
    client = client_address()
    drop_stale(check_name_free(name, client))
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
                 messagingSocketPath=path, unimatrixMirror=True, unimatrixClient=client)
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


def settings_home():
    return Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")


def load_membership():
    """The membership library beside this relay, loaded by path; None when it is not vendored here."""
    import importlib.util
    path = Path(__file__).with_name("unimatrix-membership.py")
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("unimatrix_membership", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_KEY_TYPES = r"(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-\S+|sk-\S+)"
_COMMAND_RE = re.compile(r'command="((?:[^"\\]|\\.)*)"')
_KEY_RE = re.compile(rf"\s{_KEY_TYPES}\s+(\S+)")


def managed_key_body(line):
    """Key body of an authorized_keys line whose forced command names this relay; None for any other line."""
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    cmd = _COMMAND_RE.search(text)
    if not cmd or "unimatrix-relay.py" not in cmd.group(1):
        return None
    key = _KEY_RE.search(text, cmd.end())
    return key.group(1) if key else None


def relay_line(key_body):
    """The restrict line for `key_body` with this copy's interpreter and path, quoted as the installer does."""
    parts = [f'\\"{p}\\"' if " " in p else p for p in (sys.executable, str(Path(__file__).resolve()))]
    return f'restrict,command="{" ".join(parts)}" ssh-ed25519 {key_body} unimatrix'


def windows_admin():
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def reconcile_authorized_keys(members, path, membership, is_admin=windows_admin):
    """Make the relay-managed lines of `path` equal the generated lines for `members`.

    Only lines whose forced command names unimatrix-relay.py are touched; every other line keeps its
    exact bytes. A managed line already equal to its generated line stays in place; any other managed
    line (a revoked or never-signed key, a stale pin) is dropped. Returns admin | unchanged | updated.
    """
    if is_admin():
        return "admin"
    want = {}
    for m, line in zip(members, membership.authorized_keys_lines(members, relay_line)):
        want[m["relay_pub"].split()[1]] = line
    path = Path(path)
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    out, kept = [], set()
    for raw in old.splitlines(keepends=True):
        body = managed_key_body(raw)
        if body is None:
            out.append(raw)
        elif body in want and body not in kept and raw.rstrip("\r\n") == want[body]:
            kept.add(body)
            out.append(raw)
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    out += [line + "\n" for body, line in want.items() if body not in kept]
    new = "".join(out)
    if new == old:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(new, encoding="utf-8")
        if os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return "updated"


def membership_get(home, membership):
    """(snapshot line, base64 sig line) of the held snapshot, or None when none is held. Never verifies or signs."""
    snap, sig = membership.load_snapshot(home)
    if snap is None:
        return None
    return membership.canonical_bytes(snap).decode("ascii"), base64.b64encode(sig).decode("ascii")


def membership_put(home, snapshot_line, sig_line, membership, authorized_keys, notifier=None,
                   is_admin=windows_admin, run=subprocess.run):
    """Verify and adopt a pushed snapshot, then reconcile authorized_keys; return the reply dict.

    The pin and the epoch gate inside `membership.adopt` are the only defence: a refusal (bad
    signature, replayed epoch, fork, no pin, malformed input) appends one `refused` event and changes
    nothing. The relay never signs."""
    notifier = notifier or membership.notify
    try:
        snap = json.loads(snapshot_line)
        sig = base64.b64decode(sig_line.strip(), validate=True)
        if not isinstance(snap, dict) or not sig:
            raise ValueError("snapshot or signature empty")
    except ValueError as ex:
        notifier(home, {"kind": "refused", "detail": f"malformed push: {type(ex).__name__}"})
        return {"ok": False, "reason": "malformed"}
    try:
        members = membership.adopt(home, snap, sig, notifier=notifier, run=run)
    except membership.MembershipError as ex:
        return {"ok": False, "reason": f"refused: {ex}"[:200]}
    return {"ok": True, "epoch": snap["epoch"],
            "authorized_keys": reconcile_authorized_keys(members, authorized_keys, membership, is_admin)}


def main():
    parsed = parse_mode(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    if parsed is None:
        sys.exit("usage: roster | send <pid> | inbox <name> | source | "
                 "grant <grantee> <note> <ttl> <repo> | membership get | membership put")
    mode, arg = parsed
    if mode == "membership":
        membership = load_membership()
        if membership is None:
            sys.exit("membership library not vendored beside the relay")
        home = settings_home()
        if arg == "get":
            held = membership_get(home, membership)
            if held is None:
                sys.exit("no membership snapshot held")
            print(held[0])
            print(held[1])
            return
        reply = membership_put(home, sys.stdin.readline(), sys.stdin.readline(), membership,
                               Path.home() / ".ssh" / "authorized_keys")
        print(json.dumps(reply))
        sys.exit(0 if reply.get("ok") is True else 1)
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
