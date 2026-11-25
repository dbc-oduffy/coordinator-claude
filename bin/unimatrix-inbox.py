#!/usr/bin/env python3
"""Register a local session on the far box through the unimatrix relay's `inbox` mode,
and carry every message the far box delivers to it back into the local session.

Usage:
  unimatrix-inbox.py <local-session-pid> <name> <log> [<deliver-endpoint>]
                     --remote <lan-ssh-alias> [--tunnel-remote <ssh-alias>] [--key <path>]

--remote is tried first; --tunnel-remote (or $UNIMATRIX_TUNNEL_REMOTE) is used only while
--remote does not answer. A dropped ssh ends this client; its supervisor restarts it and the
choice is made again.

  unimatrix-inbox.py mux <log> --names-file <json> --remote <alias> [--tunnel-remote <alias>] [--key <path>]

holds every name in the names file (name -> {pid, endpoint}) on one far `inbox-mux` relay,
adding and dropping names as the file changes. Exits 4 when the far relay lacks `inbox-mux`.

Ordinary inbox registrations stay local to the receiving box. Explicit --reply-inbox
uses the relay's reply-inbox mode to advertise a temporary transport return endpoint
to its directly connected boxes. It lasts only while this client's SSH stays open;
downstream mirrors are never re-exported. Raw remote socket paths are not portable
reply addresses; use an advertised endpoint or an already reachable owner session.

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
import time
import traceback
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


def _roster():
    """LAN alias when it answers, else the tunnel alias; see unimatrix-roster.py (vendored beside this script)."""
    path = Path(__file__).resolve().parent / "unimatrix-roster.py"
    spec = importlib.util.spec_from_file_location("unimatrix_roster", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod



def _box_mux():
    path = Path(__file__).resolve().parent / "lib" / "unimatrix_box_mux.py"
    mod = sys.modules.get("unimatrix_box_mux")
    if mod is None:
        spec = importlib.util.spec_from_file_location("unimatrix_box_mux", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_box_mux"] = mod
        spec.loader.exec_module(mod)
    return mod


def pick_remote(lan, tunnel):
    return _roster().pick_remote(lan, tunnel)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="unimatrix-inbox.py")
    p.add_argument("pid", type=int)
    p.add_argument("name")
    p.add_argument("log")
    p.add_argument("deliver_endpoint", nargs="?")
    p.add_argument("--remote", required=True, help="ssh alias of the far box on the LAN, tried first")
    p.add_argument("--tunnel-remote", default=None, help="ssh alias over the tunnel, used only when --remote does not answer")
    p.add_argument("--key", default=None)
    p.add_argument("--reply-inbox", action="store_true",
                   help="explicitly advertise this temporary return endpoint on the receiving box")
    a = p.parse_args(argv)
    a.key = a.key or default_key()
    a.tunnel_remote = a.tunnel_remote or os.environ.get("UNIMATRIX_TUNNEL_REMOTE") or None
    return a


def write_local(endpoint, data):
    data = _roster().authenticated_data(endpoint, data, os.path.expanduser(SESSIONS))
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


def inject_port(frame, box=None):
    src = str(frame.get("from", "")).removeprefix("uds:")
    candidates = [d for d in _roster().remote_mirrors(_mirrors(), box)
                  if d.get(FAR_SOCKET_FIELD) == src and d.get("injectPort")]
    return candidates[0]["injectPort"] if len(candidates) == 1 else DEFAULT_PORT


def _readdress(frame, src, new, content_from=None):
    """Point `frame` and its cross-session-message `from=` attribute at `new` (a full address string).

    With `new` None only the attribute moves, to `content_from`: the frame-level `from` stays, since
    the receiving inbox checks it, and the attribute is what a reply copies."""
    if new is not None:
        frame["from"] = new
    if isinstance(frame.get("message"), dict):
        c = frame["message"]["content"]
        frame["message"]["content"] = c.replace(f'from="uds:{src}"', f'from="{content_from or new}"', 1)
    return json.dumps(frame).encode() + b"\n"


def _from_name(frame):
    m = frame.get("message")
    found = re.search(r'from-name="([^"]+)"', m.get("content", "")) if isinstance(m, dict) else None
    return found.group(1) if found else None


def localize(frame, line, box=None):
    """Rewrite a far `from` to an address the local receiver can reply to.

    A mirror holding the sender's far socket wins. Failing that, the mirror of the same
    session found by `from-name` (the far socket can be a cc-msg path no mirror lists).
    Failing that, the sending box's single reply-inbox mirror endpoint (the one address that routes back
    to that box). With none or several the attribute a reply copies becomes the sender's `from-name`
    (a name SendMessage resolves on this box; no endpoint, so the frame-level `from` is untouched)
    and the miss is logged. Without a `from-name` the frame is left as is.
    """
    src = str(frame.get("from", "")).removeprefix("uds:")
    all_mirrors = list(_mirrors())
    mirrors = _roster().remote_mirrors(all_mirrors, box)
    candidates = [d for d in mirrors if d.get(FAR_SOCKET_FIELD) == src]
    if len(candidates) == 1:
        return _readdress(frame, src, "uds:" + candidates[0]["messagingSocketPath"])
    name = _from_name(frame)
    if not name:
        return line
    want = f"{name}.{box}" if box else name
    candidates = [d for d in mirrors if d.get(FAR_SOCKET_FIELD) and d.get("messagingSocketPath")
                  and (d.get("name") == want or d.get("unimatrixFarName") == name)]
    if len(candidates) == 1:
        return _readdress(frame, src, "uds:" + candidates[0]["messagingSocketPath"])
    if box:
        label = _roster().box_label(box)
        replies = [d for d in all_mirrors
                   if d.get("unimatrixMirror") and d.get("unimatrixReplyInbox") is True
                   and d.get("messagingSocketPath")
                   and d.get("unimatrixClient") == label]
        if len(replies) == 1:
            return _readdress(frame, src, "uds:" + replies[0]["messagingSocketPath"])
    if log:
        log.write(f"localize: no routable reply endpoint for {src!r} from box {box!r}; reply address is the name {name!r}\n")
    return _readdress(frame, src, None, content_from=name)


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


def entry_refusal(entry, a):
    """Why this leg must not carry `entry`'s frames under `a.name`/`a.deliver_endpoint`, else None."""
    if not isinstance(entry, dict):
        return "entry is not a JSON object"
    if entry.get("name") not in (None, a.name):
        return f"entry names {entry.get('name')!r} not {a.name!r}"
    if a.deliver_endpoint and entry.get("messagingSocketPath") != a.deliver_endpoint:
        return f"entry endpoint {entry.get('messagingSocketPath')!r} is not deliver endpoint {a.deliver_endpoint!r}"
    return None


def main(argv=None):
    global log
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["mux"]:
        return mux_main(argv[1:])
    a = parse_args(argv)
    log = open(a.log, "a", encoding="utf-8", buffering=1)
    try:
        _run(a)
    except Exception:
        log.write(f"inbox failed:\n{traceback.format_exc()}")
        raise


def _run(a):
    with open(os.path.join(os.path.expanduser(SESSIONS), f"{a.pid}.json"), encoding="utf-8") as fh:
        entry = fh.read().strip()
    refusal = entry_refusal(json.loads(entry), a)
    if refusal:
        log.write(f"refused: {refusal}\n")
        sys.exit(f"inbox: refused: {refusal}")
    (key_path,) = glob.glob(os.path.join(os.path.expanduser(SESSIONS), f"{a.pid}.*.key"))
    with open(key_path, encoding="utf-8") as fh:
        key = fh.read().strip()
    remote = pick_remote(a.remote, a.tunnel_remote)
    # The key goes over ssh stdin only, never argv or the log.
    p = _box_mux().for_remote(remote, key=a.key).subscribe(
        f"{'reply-inbox' if a.reply_inbox else 'inbox'} {a.name}", registration_payload(entry, key))
    far_err = threading.Thread(target=log_far_stderr, args=(p.stderr,), daemon=True)
    far_err.start()
    log.write(f"inbox {a.name} up, ssh pid {p.pid}\n")

    def beat():
        while p.poll() is None:
            time.sleep(HEARTBEAT_SECONDS)
            try:
                p.stdin.write(PING_LINE)
                p.stdin.flush()
            except (OSError, ValueError):
                return
    threading.Thread(target=beat, daemon=True).start()

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
        auth = deliver_frame(frame, line, auth, a.deliver_endpoint, str(a.remote).rpartition("@")[2],
                             on_fail=lambda _e: p.kill(), pid=a.pid)
    rc = p.wait()
    far_err.join(timeout=2)
    log.write(f"inbox ended rc={rc}\n")
    if rc:
        sys.exit(rc)


def _relay() -> object:
    path = Path(__file__).resolve().parent / "unimatrix-relay.py"
    mod = sys.modules.get("unimatrix_relay_for_inbox")
    if mod is None:
        spec = importlib.util.spec_from_file_location("unimatrix_relay_for_inbox", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_relay_for_inbox"] = mod
        spec.loader.exec_module(mod)
    return mod


def record_receipt(pid, line, box) -> None:
    """Receipt a frame just delivered into local session `pid` (sender `box`), so the receipts oracle sees
    every transport. Never raises: a missing receipt must not undo a delivery."""
    try:
        with open(os.path.join(os.path.expanduser(SESSIONS), f"{pid}.json"), encoding="utf-8") as fh:
            entry = json.load(fh)
        _relay().record_inbound_receipt(entry, line, box)
    except Exception as e:
        if log:
            log.write(f"receipt not recorded: {type(e).__name__}: {e}\n")


def deliver_frame(frame, line, auth, deliver_endpoint, box, on_fail=None, pid=None) -> bytes:
    """Hand one far frame (with its preceding `auth` line) to the local session; return the next `auth`.

    `on_fail` is called with the exception when the session cannot be reached, so the caller can stop
    advertising a mirror nobody reads. With `pid` (the local session) a delivered frame is receipted."""
    if deliver_endpoint:
        line = localize(frame, line, box)
        log.write(f"<< {deliver_endpoint} {line!r}\n")
        try:
            write_local(deliver_endpoint, auth + line)
        except Exception as e:
            log.write(f"deliver failed: {e}\n")
            if on_fail:
                on_fail(e)
        else:
            if pid is not None:
                record_receipt(pid, line, box)
        return b""
    port = inject_port(frame, box)
    log.write(f"<< :{port} {line!r}\n")
    try:
        with socket.create_connection((LOOPBACK, port)) as s:
            s.sendall(auth + line)
    except OSError as e:
        log.write(f"handoff failed: {e}\n")
        if on_fail:
            on_fail(e)
    else:
        if pid is not None:
            record_receipt(pid, line, box)
    return b""


MUX_UNSUPPORTED_RC = 4  # unimatrix-mirror-all.py matches this exit code: the far relay lacks inbox-mux
MUX_POLL_SECONDS = 2
HEARTBEAT_SECONDS = 20  # the far relay leases a mirror out after 90s without stdin traffic
PING_LINE = b'{"op":"ping"}\n'
MUX_PARK_SECONDS = 600  # a name the far box refused is retried this much later
MUX_UNREADABLE_RETRY_SECONDS = 30  # a name whose entry or key cannot be read or carried is retried this much later


def parse_mux_args(argv):
    p = argparse.ArgumentParser(prog="unimatrix-inbox.py mux")
    p.add_argument("log")
    p.add_argument("--names-file", required=True,
                   help="JSON name -> {pid, endpoint}: the mirrors to hold, rewritten by the supervisor")
    p.add_argument("--remote", required=True)
    p.add_argument("--tunnel-remote", default=None)
    p.add_argument("--key", default=None)
    a = p.parse_args(argv)
    a.key = a.key or default_key()
    a.tunnel_remote = a.tunnel_remote or os.environ.get("UNIMATRIX_TUNNEL_REMOTE") or None
    return a


def mux_add_frame(name, pid, endpoint):
    """The `add` frame for one session, or None (logged) when its entry cannot be carried under `name`."""
    base = os.path.expanduser(SESSIONS)
    try:
        with open(os.path.join(base, f"{pid}.json"), encoding="utf-8") as fh:
            entry = fh.read().strip()
        (key_path,) = glob.glob(os.path.join(base, f"{pid}.*.key"))
        with open(key_path, encoding="utf-8") as fh:
            key = fh.read().strip()
        refusal = entry_refusal(json.loads(entry), argparse.Namespace(name=name, deliver_endpoint=endpoint))
    except (OSError, ValueError, TypeError):
        log.write(f"mux: {name} pid {pid} unreadable; skipped\n")
        return None
    if refusal:
        log.write(f"mux: {name} refused: {refusal}\n")
        return None
    return {"op": "add", "name": name, "entry": json.loads(entry), "key": key}


def session_alive(pid, proc_start):
    """True while `pid` is the process that registered with `proc_start`; a recycled pid is not it."""
    try:
        roster = _roster()
        if not roster.pid_alive(pid):
            return False
        return proc_start is None or roster.proc_start(pid) == proc_start
    except (OSError, subprocess.SubprocessError):
        return True  # an unreadable stamp never drops a live mirror


class MuxFeed:
    """The mux stream's stdin side: reconciles the names file into add/drop frames, one at a time."""

    def __init__(self, stdin, names_file, clock=None, alive=None):
        self.stdin, self.names_file = stdin, names_file
        self.clock = clock or time.monotonic
        self.alive = alive or session_alive
        self.stamps = {}  # name -> procStart the session registered with
        self.sent = {}    # name -> (pid, endpoint) last added
        self.parked = {}  # name -> clock time the far refusal ends
        self.lock = threading.Lock()

    def _send(self, frame):
        self.stdin.write(json.dumps(frame).encode() + b"\n")
        self.stdin.flush()

    def heartbeat(self):
        """Keep the far relay's lease; False when the pipe is gone."""
        try:
            with self.lock:
                self.stdin.write(PING_LINE)
                self.stdin.flush()
        except (OSError, ValueError):
            return False
        return True

    def fail(self, name):
        """The local session behind `name` is unreachable: drop its far mirror so a sender gets a refusal,
        and hold off re-adding it until the park lapses."""
        try:
            with self.lock:
                if name in self.sent:
                    self._send({"op": "drop", "name": name})
                    del self.sent[name]
                self.parked[name] = self.clock() + MUX_UNREADABLE_RETRY_SECONDS
        except (OSError, ValueError):
            pass

    def refuse(self, name, error):
        """The far box refused `name`: forget it and retry after MUX_PARK_SECONDS."""
        with self.lock:
            self.sent.pop(name, None)
            self.parked[name] = self.clock() + MUX_PARK_SECONDS

    def reconcile(self):
        """Send the add/drop frames that bring the far relay to the names file; False when the pipe is gone."""
        try:
            with open(self.names_file, encoding="utf-8") as fh:
                want = json.load(fh)
        except (OSError, ValueError):
            return True
        if not isinstance(want, dict):
            return True
        now = self.clock()
        try:
            with self.lock:
                for name in [n for n in self.sent if n not in want]:
                    self._send({"op": "drop", "name": name})
                    del self.sent[name]
                # A session whose process exited is dropped now, within one poll, not when the supervisor's
                # slower roster refresh notices: the far socket must be gone before the next send reaches it.
                for name, (pid, _ep) in list(self.sent.items()):
                    if not self.alive(pid, self.stamps.get(name)):
                        self._send({"op": "drop", "name": name})
                        del self.sent[name]
                        self.parked[name] = now + MUX_UNREADABLE_RETRY_SECONDS
                for name, v in want.items():
                    if not isinstance(v, dict) or self.parked.get(name, 0) > now:
                        continue
                    ident = (v.get("pid"), v.get("endpoint"))
                    if self.sent.get(name) == ident:
                        continue
                    frame = mux_add_frame(name, *ident)
                    if frame:
                        self._send(frame)
                        self.sent[name] = ident
                        self.stamps[name] = frame["entry"].get("procStart")
                    else:
                        self.parked[name] = now + MUX_UNREADABLE_RETRY_SECONDS
        except (OSError, ValueError):
            return False
        return True


def mux_main(argv):
    global log
    a = parse_mux_args(argv)
    log = open(a.log, "a", encoding="utf-8", buffering=1)
    try:
        _mux_run(a)
    except Exception:
        log.write(f"inbox mux failed:\n{traceback.format_exc()}")
        raise


def _mux_run(a):
    remote = pick_remote(a.remote, a.tunnel_remote)
    p = _box_mux().for_remote(remote, key=a.key).subscribe("inbox-mux", b"")
    usage = []

    def watch_stderr():
        for raw in p.stderr:
            text = raw.decode("utf-8", "replace").rstrip()
            if text:
                log.write(f"far: {text}\n")
                if text.startswith("usage:"):
                    usage.append(text)

    far_err = threading.Thread(target=watch_stderr, daemon=True)
    far_err.start()
    log.write(f"inbox mux up, ssh pid {p.pid}\n")
    feed, stop = MuxFeed(p.stdin, a.names_file), threading.Event()

    def pump():
        beat = 0.0
        while not stop.is_set() and feed.reconcile():
            beat += MUX_POLL_SECONDS
            if beat >= HEARTBEAT_SECONDS:
                beat = 0.0
                if not feed.heartbeat():
                    return
            stop.wait(MUX_POLL_SECONDS)

    threading.Thread(target=pump, daemon=True).start()
    box, auths, frames = str(a.remote).rpartition("@")[2], {}, 0
    for line in p.stdout:
        if not line.strip():
            continue
        try:
            wrapped = json.loads(line)
            name = wrapped["name"]
        except (ValueError, KeyError, TypeError):
            log.write(f"unparsed {line!r}\n")
            continue
        frames += 1
        if "error" in wrapped:
            log.write(f"far refused {name}: {wrapped['error']}\n")
            feed.refuse(name, wrapped["error"])
            continue
        frame = wrapped.get("frame")
        if not isinstance(frame, dict):
            log.write(f"unparsed {frame!r}\n")
            continue
        text = json.dumps(frame).encode() + b"\n"
        if frame.get("type") == "auth":
            auths[name] = text
            continue
        local_pid, endpoint = feed.sent.get(name) or (None, None)
        if endpoint is None:
            continue  # dropped while the frame was in flight
        auths[name] = deliver_frame(frame, text, auths.get(name, b""), endpoint, box,
                                    on_fail=lambda _e, n=name: feed.fail(n), pid=local_pid)
    rc = p.wait()
    stop.set()
    far_err.join(timeout=2)
    log.write(f"inbox mux ended rc={rc}\n")
    if rc and usage and not frames:
        sys.exit(MUX_UNSUPPORTED_RC)
    if rc:
        sys.exit(rc)


if __name__ == "__main__":
    main()
