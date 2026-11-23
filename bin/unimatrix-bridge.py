#!/usr/bin/env python3
"""Bridge a local endpoint to a remote Claude session so SendMessage("uds:<endpoint>")
lands on another box.

The local endpoint is a Windows named pipe on Windows and a unix socket path on
macOS/Linux. Every byte both ways is logged to <log> so the wire shape is visible.

Usage:
  unimatrix-bridge.py <endpoint> <tcp-port|relay> <log> [<return-port> <local-inbox>]
                      [--remote <lan-ssh-alias>] [--tunnel-remote <ssh-alias>] [--key <path>]

<tcp-port> "relay" sends each message through the unimatrix key's forced-command
relay (`send-session <remote-pid> <digest> <name-digest> <session-id>`; an older relay fails the delivery) over `ssh <lan-ssh-alias>`; --remote is required then.
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
BOX_FIELD = "unimatrixBox"  # the peer contract's mirror-row box stamp

log = None
cfg = None
bound_ino = None  # inode of the endpoint socket this bridge bound (unix only)


def settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env and env.strip() else Path.home() / ".coordinator-claude-settings"


def default_key():
    """The Unimatrix-Zero key: the settings home's, else the group-em home's; first candidate when neither exists."""
    home = settings_home()
    cands = [home / ".secrets" / "ssh" / "unimatrix-zero", home / "group-em" / ".secrets" / "ssh" / "unimatrix-zero"]
    return str(next((c for c in cands if c.is_file()), cands[0]))


def _roster():
    """LAN alias when it answers, else the tunnel alias; see unimatrix-roster.py (vendored beside this script)."""
    mod = sys.modules.get("unimatrix_roster")
    if mod is None:
        path = Path(__file__).resolve().parent / "unimatrix-roster.py"
        spec = importlib.util.spec_from_file_location("unimatrix_roster", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_roster"] = mod
        spec.loader.exec_module(mod)
    return mod



def pick_remote(lan, tunnel):
    return _roster().pick_remote(lan, tunnel)


#: `unimatrix_far_addresses.Route.verification` values that may carry a frame: a host-key-verified LAN
#: address, or the recorded fallback that ssh verifies strictly when it dials. Trap: keep in step with
#: VERIFIED / SSH_STRICT_AT_DIAL there; any other value (unavailable, not-this-box, ...) is refused.
DIALABLE = ("verified", "ssh-strict-at-dial")


class RouteRefused(Exception):
    """The roster named no authenticated route; nothing was dialled."""


def route_target(picked) -> "tuple[str, str | None]":
    """(ssh remote, transport label or None) for what the roster's `pick_remote` returned.

    A string is the legacy alias answer (label None: the caller derives ssh/tunnel). A Route-shaped
    result (`endpoint`, `transport`, `verification`) is dialled only when `verification` is in DIALABLE;
    anything else raises RouteRefused with its reason, so a TCP-only or wrong-peer route never carries a frame."""
    if isinstance(picked, str) or not hasattr(picked, "verification"):
        return picked, None
    if picked.verification not in DIALABLE or not picked.endpoint:
        why = getattr(picked, "fallback_reason", None) or picked.verification
        raise RouteRefused(f"no authenticated route to {getattr(picked, 'peer', None) or getattr(picked, 'alias', '?')}: {why}")
    return picked.endpoint, picked.transport


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
    p.add_argument("--supervisor", type=int, default=None,
                   help="roster pid this bridge exits with; its start stamp is read from this bridge's mirror entry")
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
        global bound_ino
        bound_ino = os.stat(endpoint).st_ino
        srv.listen(8)
        while True:
            c, _ = srv.accept()
            yield SockConn(c)


def write_local(endpoint, data):
    """Deliver `data` to a local endpoint (named pipe on Windows, unix socket elsewhere)."""
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


def notify_sender(line, target, error) -> None:
    """Tell the sender of `line` its cross-box message did not land, through the return leg's write_local.

    The notice is stamped from this bridge's own endpoint: the inbox accepts it because
    this process is the one the mirror entry vouches for.
    """
    if "unconfirmed" in error:
        _tell_sender(line, f"Delivery unconfirmed: your message to {target} may have reached the far box ({error}). Do not resend blindly.")
        return
    _tell_sender(line, f"Delivery failed: your message to {target} did not reach the far box ({error}). It was not delivered.")


def _tell_sender(line, text):
    """Write `text` into the inbox of `line`'s sender, stamped from this bridge's endpoint; a failed write is logged."""
    try:
        sender = json.loads(line).get("from", "").removeprefix("uds:")
    except (ValueError, AttributeError):
        sender = ""
    if not sender:
        log.write("sender notice: sender unknown\n")
        return
    frame = json.dumps({"from": "uds:" + cfg.endpoint, "message": text}).encode() + b"\n"
    try:
        write_local(sender, frame)
    except Exception as e:  # pywintypes.error is not an OSError subclass
        log.write(f"sender notice not delivered: {e}\n")


def ack_sender(line, target, reached, reached_box, queued=False) -> None:
    """Tell the sender which far session its message was written to; `reached` is None for a far relay that does not name it.

    `queued`: the far reader was slow and the line is parked for delivery."""
    if queued:
        text = f"Queued for {reached or target} on {reached_box or 'the far box'}; delivered when its reader drains."
    elif reached:
        text = f"Delivered to {reached} on {reached_box or 'the far box'}."
    else:
        text = f"Delivered to {target}; receiver unconfirmed (far relay does not name it)."
    _tell_sender(line, text)


def notify_misdelivered(line, target, reached, reached_box):
    """Tell the sender its message was written to a far session other than the addressed one."""
    _tell_sender(line, f"Misdelivered: your message to {target} was written to {reached} on {reached_box or 'the far box'}, not the addressed session.")


def delivery_status(limit=10):
    """Lines describing the most recent relay sends, newest last."""
    try:
        rows = [json.loads(l) for l in deliveries_path().read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        rows = []
    if not rows:
        return ["no cross-box sends recorded"]
    return [f"{'delivered' if r['ok'] else 'FAILED   '} {r['ts']} {r.get('ref') or r['target']}" + ("" if r["ok"] else f": {r['error']}")
            for r in rows[-limit:]]


def _roster_wrote_name(addressed, far_name, remote, entry_box=None):
    """True when `addressed` is a mirror name unimatrix-roster could have written for `far_name` on `remote`.

    Trap: mirrors unimatrix-roster.py labelled(), box_label(), mirror_name() (a dotted far name not
    already carrying this box is hyphenated first) and mirror_entry_name() (the legacy
    codex/agy `<vendor>-<repo>-<hash10>-on-<box>` alias); the bridge does not import the roster at
    load, so change those and this together. Any other name is a misroute."""
    if not isinstance(addressed, str):
        return False
    box = str(remote).rpartition("@")[2]
    base = far_name
    if "." in base and not base.endswith("." + box):
        base = base.replace(".", "-")
    bare = base.partition(".")[0]
    if addressed in {far_name, base, bare, f"{bare}.{box}"}:
        return True
    legacy = re.fullmatch(r"(codex|agy)-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", far_name, re.I)
    if not legacy:
        return False
    vendor, target = legacy.groups()
    alias_box = re.sub(r"[^A-Za-z0-9_-]+", "-", str(entry_box or box)).strip("-").lower() or "unknown"
    short = hashlib.sha256(target.lower().encode()).hexdigest()[:10]
    alias = rf"{re.escape(vendor.lower())}-[A-Za-z0-9_-]+-{short}-on-{re.escape(alias_box)}"
    return re.fullmatch(alias + rf"(\.{re.escape(box)})?", addressed) is not None


#: The prefix unimatrix-relay.py puts on every wrong-target refusal; a match unmirrors the mirror.
TARGET_MISMATCH = "target mismatch"
#: Marks a send whose far write may have happened with no receipt readable: the bridge never resends it.
UNCONFIRMED_NOTE = "far write unconfirmed; check the far inbox before resending"
#: ssh failures that occur before any byte reaches the far relay: the write cannot have happened, so no UNCONFIRMED_NOTE.
PRE_WRITE_FAILURE = re.compile(
    r"Connection (refused|timed out)|Permission denied|Too many authentication|No route to host|"
    r"Could not resolve|Host key verification failed|Network is unreachable|TimeoutExpired", re.I)


def _target_of(mine) -> tuple:
    """(far pid, far session id, delivery-row target) for a mirror entry; the target leads with the mirror's name."""
    far_pid = str(mine.get("farPid") or os.path.basename(mine[FAR_SOCKET_FIELD]).removesuffix(".sock"))
    far_sid = mine.get("sessionId")
    return far_pid, far_sid, f"{mine.get('name') or far_pid} (pid {far_pid}, session {far_sid})"


_verdict = threading.local()

#: Win32 pipe errors for a client that left before the verdict: broken pipe, no process on the other end, pipe closing.
_PIPE_GONE_WINERRORS = (109, 232, 233)


def _client_gone(e) -> bool:
    """True when `e` is the client having hung up (a liveness probe connects and leaves), not a bridge fault."""
    if isinstance(e, (BrokenPipeError, ConnectionResetError)):
        return True
    return type(e).__name__ == "error" and bool(e.args) and e.args[0] in _PIPE_GONE_WINERRORS


def relay_send(conn) -> None:
    """Relay one client's message lines; answer the client when the bridge takes custody, not after the far leg.

    Custody is the point just before the far ssh run: frames parsed, mirror validated, nothing refused.
    There the connection closes having written nothing: silence is acceptance, as on the router faces
    (`unimatrix-peer-router.py` on_conn), because the client reads any written line as a refusal. A refusal
    or local fault before custody writes one `{"ok": false, "error": ...}` line. A far failure after custody
    is never an answer: it lands as a deliveries row and the sender's failure notice (`_record_outcome`),
    and the bridge never resends."""
    buf = b""
    while chunk := conn.read():
        buf += chunk
    _verdict.errors = []
    _verdict.answered = False

    def accept() -> None:
        _verdict.answered = True
        conn.close()

    def answer(reply) -> None:
        _verdict.answered = True
        try:
            conn.write(json.dumps(reply).encode() + b"\n")
        except Exception as e:  # pywintypes.error is not an OSError subclass
            if not _client_gone(e):
                log.write(f"client verdict not delivered: {e}\n")
        conn.close()

    try:
        _relay_deliver(buf, on_custody=accept)
        if not _verdict.answered:
            errors = [e for e in _verdict.errors if e]
            answer({"ok": False, "error": (errors[0] if errors else "nothing to send")[-300:]})
    except Exception as e:  # a local fault before custody is still a failed send to the client
        if _verdict.answered:
            log.write(f"relay: far leg fault after custody: {type(e).__name__}: {e}\n")
        else:
            answer({"ok": False, "error": f"{LOCAL_FAULT}: {type(e).__name__}: {e}"[-300:]})
    finally:
        _verdict.errors = None


def _relay_deliver(buf, on_custody=None) -> None:
    # The relay forwards one message line and authenticates for its local recipient;
    # the near recipient's auth header must not cross the box boundary.
    lines = frames_to_send(buf)
    mine = _load(f"{os.getpid()}.json")
    if mine and (mine.get("pid") != os.getpid() or mine.get("messagingSocketPath") != cfg.endpoint
                 or mine.get("unimatrixRemote", cfg.remote) != cfg.remote):
        mine = None
    if not mine or not lines:
        log.write(f"relay: nothing to send (mirror={bool(mine)}, bytes={len(buf)})\n")
        return
    # A win32 peer's socket is a named pipe with no pid in its name; the roster records `farPid`.
    far_pid, far_sid, target = _target_of(mine)
    for line in lines:
        log.write(f"relay >> {line!r}\n")
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    box = mine.get(BOX_FIELD) or "unknown"
    transport = "none"
    far_name = mine.get("unimatrixFarName")
    ref = f"{far_name.partition('.')[0]}.{box}" if isinstance(far_name, str) and far_name and box != "unknown" else None
    if not isinstance(far_name, str) or not far_name:
        log.write("relay: mirror lacks far name; re-mirror\n")
        for line in lines:
            _record_outcome(line, target, ts, 0, "mirror lacks far name; re-mirror", box, transport, ref)
        return
    if not isinstance(far_sid, str) or not far_sid:
        log.write("relay: mirror lacks far session id; re-mirror\n")
        for line in lines:
            _record_outcome(line, target, ts, 0, "mirror lacks far session id; re-mirror", box, transport, ref)
        return
    addressed = mine.get("name")
    if not _roster_wrote_name(addressed, far_name, cfg.remote, mine.get("box")):
        error = f"addressed {addressed}, endpoint is {far_name} (session {far_sid}); re-mirror"
        log.write(f"relay refused: {error}\n")
        for line in lines:
            _record_outcome(line, target, ts, 0, error, box, transport, ref)
        _mark_misroute()
        return
    if on_custody:
        on_custody()
    started = time.monotonic()
    started_wall = time.time()
    far_digest = hashlib.sha256(mine[FAR_SOCKET_FIELD].encode("utf-8")).hexdigest()[:16]
    name_digest = hashlib.sha256(far_name.encode("utf-8")).hexdigest()[:16]
    r = _ssh_relay(f"send-session {far_pid} {far_digest} {name_digest} {far_sid}", b"".join(l + b"\n" for l in lines))
    ms = round((time.monotonic() - started) * 1000)
    transport = getattr(r, "transport", "ssh")
    stderr = r.stderr.decode(errors="replace").strip()
    if r.returncode and stderr.startswith((TARGET_MISMATCH, "ambiguous")):
        log.write(f"relay refused: {stderr}\n")
        for line in lines:
            _record_outcome(line, target, ts, ms, stderr[-300:], box, transport, ref)
        if stderr.startswith(TARGET_MISMATCH):
            _mark_misroute()
        return
    if r.returncode == LOCAL_FAULT_EXIT and stderr.startswith(LOCAL_FAULT):
        log.write(f"relay: {stderr}\n")
        for line in lines:
            _record_outcome(line, target, ts, ms, stderr[-300:], box, transport, ref)
        return
    replies = _batch_replies(r.stdout)
    if r.returncode and not replies and r.returncode != 255:
        skew = _skew_of_send_session(far_pid)
        if skew:
            log.write(f"relay: {skew}\n")
            for line in lines:
                _record_outcome(line, target, ts, ms, skew, box, transport, ref)
            return
    acks = _caps().ingest_acked(lines, replies)
    # A pre-ack far relay delivers and replies bare {"ok": true} (or nothing); its `receipts` rows still
    # prove the write. A line the far side explicitly refused is never reconciled.
    if any(not ok and not (i < len(replies) and replies[i].get("ok") is False) for i, (ok, _) in enumerate(acks)):
        acks = _reconcile_acks(lines, acks, far_sid, started_wall)
    marked = False
    for i, (line, (ok, unacked)) in enumerate(zip(lines, acks)):
        error = None
        reached = reached_box = None
        queued = bool(ok and i < len(replies) and replies[i].get("queued") is True)
        if ok and i < len(replies):
            reached = replies[i].get("reached") if isinstance(replies[i].get("reached"), str) else None
            reached_box = replies[i].get("reached_box") if isinstance(replies[i].get("reached_box"), str) else None
        if reached and not _roster_wrote_name(reached, far_name, cfg.remote, mine.get("box")):
            error = f"{TARGET_MISMATCH}: delivered to {reached} on {reached_box or 'the far box'}, addressed {far_name}"
        if not ok:
            if i < len(replies):
                error = f"relay: {replies[i].get('error', 'delivery refused')}" if replies[i].get("ok") is False else unacked
            elif r.returncode:
                log.write(f"relay send failed {r.returncode}: {r.stderr!r}\n")
                error = f"ssh exit {r.returncode}: " + stderr[-300:]
                if transport != "none" and not PRE_WRITE_FAILURE.search(stderr):
                    error += f"; {UNCONFIRMED_NOTE}"
            else:
                error = f"relay: no delivery reply for this message; {UNCONFIRMED_NOTE}"
        if error and TARGET_MISMATCH in error and not marked:
            _mark_misroute()
            marked = True
        _record_outcome(line, target, ts, ms, error, box, transport, ref, reached=reached, reached_box=reached_box,
                        acked=ok, misdelivered=bool(error and reached), queued=queued)


def _caps():
    path = Path(__file__).resolve().parent / "lib" / "unimatrix_capabilities.py"
    mod = sys.modules.get("unimatrix_capabilities")
    if mod is None:
        spec = importlib.util.spec_from_file_location("unimatrix_capabilities", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_capabilities"] = mod
        spec.loader.exec_module(mod)
    return mod


def _skew_of_send_session(far_pid):
    """The named skew when the far relay cannot serve `send-session`, else "".

    Asks `capabilities` once, only after a failed send-session; a relay that rejects the verb with
    `usage:` predates it and send-session together. Any other fault (ssh down) is not a skew."""
    r = _ssh_relay("capabilities", b"")
    if r.returncode == 0:
        reply = next(iter(_batch_replies(r.stdout)), {})
        caps = reply.get("capabilities") if isinstance(reply.get("capabilities"), list) else None
        return _caps().skew_reason(caps, "send-session") if caps is not None else ""
    if r.stderr.lstrip().startswith(b"usage:"):
        return _caps().skew_reason((), "send-session")
    return ""


def _reconcile_acks(lines, acks, far_sid, started_wall):
    """Re-ack unacked lines from the far `receipts` verb when a reply was lost after the write.

    `since` is the near send time minus 60s, not a cross-box clock comparison; a missed read leaves `acks` as is."""
    r = _ssh_relay(f"receipts {far_sid} {started_wall - 60:.3f}", b"")
    rows = next((x.get("rows") for x in _batch_replies(r.stdout) if isinstance(x.get("rows"), list)), None) if r.returncode == 0 else None
    if not rows:
        return acks
    pending = [i for i, (ok, _) in enumerate(acks) if not ok]
    again = _caps().ingest_acked([lines[i] for i in pending], rows)
    out = list(acks)
    for i, res in zip(pending, again):
        out[i] = res
    return out


def _mark_misroute():
    """Atomically create this bridge's empty `<pid>.misroute` in the sessions dir; the roster sync unmirrors the marked mirror."""
    path = os.path.join(os.path.expanduser(SESSIONS), f"{os.getpid()}.misroute")
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        pass
    except OSError as e:
        log.write(f"relay: misroute marker failed: {e}\n")


def _box_mux():
    path = Path(__file__).resolve().parent / "lib" / "unimatrix_box_mux.py"
    mod = sys.modules.get("unimatrix_box_mux")
    if mod is None:
        spec = importlib.util.spec_from_file_location("unimatrix_box_mux", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_box_mux"] = mod
        spec.loader.exec_module(mod)
    return mod


LOCAL_FAULT = "local send-leg fault"
LOCAL_FAULT_EXIT = 70  # never 255: that is ssh's own failure code, and a fault raised here never reached ssh


def _ssh_relay(command, data) -> "subprocess.CompletedProcess":
    """The far relay running `command` with `data` on stdin, through the far box's one channel.

    A route refusal is a 255 result; any other fault raised in this process is a LOCAL_FAULT_EXIT result naming LOCAL_FAULT."""
    label = "ssh"
    try:
        remote, route_label = route_target(pick_remote(cfg.remote, getattr(cfg, "tunnel_remote", None)))
        label = route_label or ("ssh" if remote == cfg.remote else "tunnel")
        r = _box_mux().for_remote(remote, key=cfg.key, extra=["-o", "ConnectTimeout=10"]).run(command, data, timeout=30)
        r.transport = label
        return r
    except RouteRefused as e:
        r = subprocess.CompletedProcess([], 255, b"", str(e).encode())
        r.transport = "none"
        return r
    except Exception as e:  # any send-leg fault is a failed delivery, never a silent one
        r = subprocess.CompletedProcess([], LOCAL_FAULT_EXIT, b"", f"{LOCAL_FAULT}: {type(e).__name__}: {e}".encode())
        r.transport = "none"  # raised in this process: nothing reached ssh
        return r


def _batch_replies(stdout):
    """The send-batch per-line JSON replies, in line order; unparseable output yields none."""
    replies = []
    for raw in (stdout or b"").splitlines():
        try:
            reply = json.loads(raw)
        except ValueError:
            continue
        if isinstance(reply, dict):
            replies.append(reply)
    return replies


def _record_outcome(line, target, ts, ms, error, box="unknown", transport="none", ref=None,
                    reached=None, reached_box=None, acked=False, misdelivered=False, queued=False) -> None:
    """Record one line's outcome; `digest` is the sha256 the far relay's receipt row carries for the same line.

    `box` is the mirror row's BOX_FIELD; `transport` is the leg label: `ssh`, `tunnel`, or `none` when refused before any ssh.
    `ref` is the `<bare>.<box>` address the far box resolves; the failure notice leads with it.
    `reached`/`reached_box` name the far session the relay wrote to. `acked` is a far-confirmed write: with no
    error the sender gets a delivery ack; with `misdelivered` it gets the wrong-session notice, not the not-delivered one.
    `queued` is a far-accepted line parked for a slow reader: an ok row marked `queued`, acked as `queued`, never a failure."""
    if getattr(_verdict, "errors", None) is not None:
        _verdict.errors.append(error)
    row = {"ts": ts, "at": time.time(), "target": target, "ok": not error, "ms": ms, "box": box, "transport": transport,
           "digest": hashlib.sha256(line.rstrip(b"\n")).hexdigest()}
    if ref:
        row["ref"] = ref
    if reached:
        row["reached"] = reached
    if queued and not error:
        row["queued"] = True
    if error:
        row["error"] = error
        if "unconfirmed" in error:
            row["unconfirmed"] = True
    record_delivery(row)
    shown = f"{ref} ({target})" if ref else target
    shown = shown if box in (None, "", "unknown") else f"{shown} on box {box}"
    if misdelivered:
        notify_misdelivered(line, shown, reached, reached_box)
    elif error:
        notify_sender(line, shown, error)
    elif acked:
        ack_sender(line, shown, reached, reached_box, queued)


def _record_socket_send(data, started, error=None) -> None:
    """Record each message line of a mirror-socket send through _record_outcome (the only delivery writer).

    A socket write has no far ack, so a clean write records ok with transport `socket`; an unreadable mirror entry records nothing."""
    mine = _load(f"{os.getpid()}.json")
    lines = frames_to_send(data)
    if not mine or not lines or FAR_SOCKET_FIELD not in mine:
        return
    _, _, target = _target_of(mine)
    box = mine.get(BOX_FIELD) or "unknown"
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    ms = round((time.monotonic() - started) * 1000)
    for line in lines:
        _record_outcome(line, target, ts, ms, error, box, "socket")


def pump_local_to_sock(conn, s) -> None:
    while data := conn.read():
        log.write(f">> {data!r}\n")
        started = time.monotonic()
        try:
            s.sendall(data)
        except OSError as e:
            _record_socket_send(data, started, f"socket write failed: {e}")
            raise
        _record_socket_send(data, started)
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


def serve_one(conn) -> None:
    if cfg.port is None:
        relay_send(conn)  # closes conn at custody (silent) or after a refusal line
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


def _entries():
    return [d for d in map(_load, os.listdir(os.path.expanduser(SESSIONS))) if d]


def mirror_for(src, entries=None):
    entries = _entries() if entries is None else entries
    candidates = [d for d in _roster().remote_mirrors(entries, getattr(cfg, "remote", None))
                  if d.get(FAR_SOCKET_FIELD) == src]
    return candidates[0] if len(candidates) == 1 else None


def _name_routed(msg, src):
    """`msg` with its content `from="uds:<src>"` replaced by the sender's `from-name`, else None.

    The frame-level `from` stays: the local inbox checks it. A session name resolves on any box."""
    body = msg.get("message")
    if not isinstance(body, dict) or not isinstance(body.get("content"), str):
        return None
    found = re.search(r'from-name="([^"]+)"', body["content"])
    if not found:
        return None
    body["content"] = body["content"].replace(f'from="uds:{src}"', f'from="{found.group(1)}"', 1)
    return msg


def localize_from(data) -> tuple:
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
    src = frm.removeprefix("uds:")
    entries = _entries()
    if any(d.get("messagingSocketPath") == src for d in entries):
        return data, None  # already localized: a mirror of this box owns the address
    m = mirror_for(src, entries)
    if not m:
        m = _reply_mirror(msg, entries)
        if m:
            m = {**m, "injectPort": None}  # served by the box's reply inbox, not a session bridge
    if not m:
        log.write(f"no mirror for sender {src}\n")
        named = _name_routed(msg, src)
        return (head + json.dumps(named).encode() + b"\n" if named else data), None
    local = m["messagingSocketPath"]
    msg["from"] = "uds:" + local
    if isinstance(msg.get("message"), dict):
        content = msg["message"]["content"]
        msg["message"]["content"] = content.replace(f'from="uds:{src}"', f'from="uds:{local}"', 1)
    return head + json.dumps(msg).encode() + b"\n", m.get("injectPort")


def _reply_mirror(msg, entries) -> "dict | None":
    """The local mirror a reply to an unmatched far sender can use, else None.

    The mirror of the same session by `from-name` (the far socket can be a cc-msg path no mirror
    lists); failing that, the sending box's single reply-inbox mirror, the one address that routes
    back to that box. Several candidates are ambiguous and give None."""
    body = msg.get("message")
    found = re.search(r'from-name="([^"]+)"', body["content"]) if (
        isinstance(body, dict) and isinstance(body.get("content"), str)) else None
    remote = getattr(cfg, "remote", None)
    mirrors = _roster().remote_mirrors(entries, remote)
    if found:
        name, label = found.group(1), _roster().box_label(remote) if remote else None
        want = f"{name}.{label}" if label else name
        named = [d for d in mirrors if d.get(FAR_SOCKET_FIELD) and d.get("messagingSocketPath")
                 and (d.get("name") == want or d.get("unimatrixFarName") == name)]
        if len(named) == 1:
            return named[0]
    if remote:
        label = _roster().box_label(remote)
        replies = [d for d in entries if d.get("unimatrixMirror") and d.get("unimatrixReplyInbox") is True
                   and d.get("messagingSocketPath") and d.get("unimatrixClient") == label]
        if len(replies) == 1:
            return replies[0]
    return None


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


SUPERVISOR_POLL_SECONDS = 15


def supervisor_gone():
    """True when the roster that spawned this bridge is no longer the process it was.

    The start stamp comes from this bridge's own mirror entry, which the roster writes just after
    spawning; until it exists only the pid is checked."""
    mine = _load(f"{os.getpid()}.json") or {}
    return not _roster()._liveness().entry_live(
        {"pid": cfg.supervisor, "procStart": mine.get("unimatrixRosterProcStart")})


def drop_own_files(endpoint=True):
    """Remove this bridge's registry entry, peer key and (unix) endpoint unless `endpoint` is False."""
    base = os.path.expanduser(SESSIONS)
    try:
        names = [f for f in os.listdir(base) if f.startswith(f"{os.getpid()}.")]
    except OSError:
        names = []
    paths = [os.path.join(base, f) for f in names]
    if not IS_WIN and endpoint:
        paths.append(cfg.endpoint)
    for path in paths:
        try:
            os.unlink(path)
        except OSError:
            pass


def watch_supervisor():
    """Exit with the roster: blocking accept loops cannot poll, so this daemon thread does."""
    while True:
        time.sleep(SUPERVISOR_POLL_SECONDS)
        if supervisor_gone():
            log.write(f"supervisor {cfg.supervisor} gone; exiting\n")
            drop_own_files()
            os._exit(0)


def socket_lost(endpoint, ino):
    """True when `endpoint` no longer holds the socket inode this bridge bound; False before any bind."""
    if ino is None:
        return False
    try:
        return os.stat(endpoint).st_ino != ino
    except OSError:
        return True


def watch_socket():
    """Tick: exit when the bound socket path is gone or swapped, leaving the successor's file alone."""
    while True:
        time.sleep(SUPERVISOR_POLL_SECONDS)
        if socket_lost(cfg.endpoint, bound_ino):
            log.write(f"endpoint {cfg.endpoint} no longer the bound socket; exiting\n")
            drop_own_files(endpoint=False)
            os._exit(0)


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
    if not IS_WIN:
        threading.Thread(target=watch_socket, daemon=True).start()
    if cfg.supervisor is not None:
        threading.Thread(target=watch_supervisor, daemon=True).start()
    for conn in accept_loop(cfg.endpoint):
        log.write("client connected\n")
        threading.Thread(target=serve_one, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
