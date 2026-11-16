#!/usr/bin/env python3
"""agy-side leg: run BY agy (its run_command, backgrounded) so it inherits agy's own
ANTIGRAVITY_CSRF_TOKEN / ANTIGRAVITY_LS_ADDRESS / ANTIGRAVITY_CONVERSATION_ID. The token never
leaves this process: it is not logged, written, or forwarded.

Without a token the leg runs pending (a SessionStart hook has none): it binds the endpoint, appends
each inbound {"text"} to <conv>.queue.jsonl beside the log (0600), and answers {"ok": true,
"queued": true}. A live leg (token present) drains that spool in order through send() before it
binds, keeping any line it could not deliver or parse.

Listens on <sock> (an AF_UNIX socket; on Windows a named pipe, owner-only, served from a thread);
each connection carries one JSON line {"text": ...}. The leg POSTs it to the
live language server's SendUserCascadeMessage for agy's own conversation and answers one JSON
line {"ok", "status", "body"}.

The leg exits, unlinking its endpoint, once $AGY_LEG_PARENT_PID (the agy process it serves) is
gone; without that variable it runs until killed.

Usage (agy runs this): nohup python3 unimatrix-agy-leg.py <sock> > unimatrix-agy-leg.out 2>&1 &
The log path is $AGY_LEG_LOG else unimatrix-agy-leg.log beside this script.
"""
try:
    import fcntl
except ImportError:  # Windows: the spool is locked through msvcrt on a sidecar file
    fcntl = None
import contextlib
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

LOG = None  # explicit override; None resolves through log_path() at call time
METHOD = "/exa.language_server_pb.LanguageServerService/SendUserCascadeMessage"


def log_path():
    """The leg log: the LOG override, else $AGY_LEG_LOG, else unimatrix-agy-leg.log beside this script."""
    return LOG or os.environ.get("AGY_LEG_LOG") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "unimatrix-agy-leg.log")


def log(*a):
    """Append one line to the leg log; callers pass no token (it is never a log argument)."""
    with open(log_path(), "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")


def base_urls():
    """Candidate HTTP bases: the exported LS address first, then the HTTP port override."""
    out = []
    addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS", "")
    if addr:
        out.append(addr if "://" in addr else f"http://{addr}")
    if os.environ.get("AGY_LS_HTTP"):
        out.append(f"http://{os.environ['AGY_LS_HTTP']}")
    return out


def send(text):
    """POST `text` into agy's own conversation; the CSRF token is read here and used only as a header."""
    token = os.environ["ANTIGRAVITY_CSRF_TOKEN"]
    conv = os.environ["ANTIGRAVITY_CONVERSATION_ID"]
    body = json.dumps({"cascadeId": conv, "items": [{"text": text}]}).encode()
    last = None
    for base in base_urls():
        req = urllib.request.Request(base.rstrip("/") + METHOD, data=body, method="POST", headers={
            "Content-Type": "application/json", "x-codeium-csrf-token": token})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = {"ok": True, "status": r.status, "base": base, "body": r.read(2000).decode("utf-8", "replace")}
        except urllib.error.HTTPError as e:
            resp = {"ok": False, "status": e.code, "base": base, "body": e.read(2000).decode("utf-8", "replace")}
        except OSError as e:
            resp = {"ok": False, "status": None, "base": base, "body": str(e)}
        log("send", {k: v for k, v in resp.items()})
        if resp["ok"]:
            return resp
        last = resp
    return last or {"ok": False, "status": None, "body": "no LS address in env"}


def spool_path():
    """The pending-message spool: the AGY_LEG_SPOOL env var, else the conversation's queue.jsonl beside the leg log."""
    return os.environ.get("AGY_LEG_SPOOL") or os.path.join(
        os.path.dirname(os.path.abspath(log_path())), f"{os.environ['ANTIGRAVITY_CONVERSATION_ID']}.queue.jsonl")


SPOOL_MAX_BYTES = 1 << 20
NT_LOCK_TIMEOUT_SECS = 15


@contextlib.contextmanager
def nt_spool_lock(path):
    """Hold an msvcrt byte lock on `<path>.lock`, a sidecar that is never replaced.

    The spool itself cannot carry the lock: drain() os.replace()s it, which Windows refuses while any
    handle is open. Raises TimeoutError when another holder keeps the lock past NT_LOCK_TIMEOUT_SECS.
    """
    import errno
    import msvcrt
    with open(f"{path}.lock", "a+b") as lock:
        deadline = time.monotonic() + NT_LOCK_TIMEOUT_SECS
        while True:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"spool lock timed out: {path}") from exc
                time.sleep(0.02)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def enqueue(text):
    """Append one message to the spool as a single O_APPEND write of one newline-terminated line.

    Raises OSError when the spool already holds SPOOL_MAX_BYTES, so the sender sees ok:false.
    """
    line = (json.dumps({"text": text}) + "\n").encode()
    try:
        full = os.path.getsize(spool_path()) + len(line) > SPOOL_MAX_BYTES
    except OSError:
        full = False
    if full:
        raise OSError("spool full")
    if fcntl is None:
        with nt_spool_lock(spool_path()):
            fd = os.open(spool_path(), os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)
        return
    while True:
        fd = os.open(spool_path(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)  # serialises with drain()'s rewrite, which would drop this line
            # A drain that won the lock replaced the file: this fd is the unlinked old inode, so reopen.
            if os.fstat(fd).st_ino == os.stat(spool_path()).st_ino:
                os.write(fd, line)
                return
        finally:
            os.close(fd)


def drain():
    """Deliver the spool in order through send(); a line that fails to parse or deliver stays.

    Delivery stops at the first failed send so order holds. Bytes appended while draining survive.
    """
    path = spool_path()
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return
    keep, failed = [], False
    for line in data.splitlines(keepends=True):
        if failed or not line.strip():
            if line.strip():
                keep.append(line)
            continue
        try:
            text = json.loads(line)["text"]
        except (ValueError, KeyError, TypeError):
            keep.append(line)
            continue
        if not send(text).get("ok"):
            failed = True
            keep.append(line)
    if fcntl is None:
        with nt_spool_lock(path):  # held through os.replace: no append lands in between
            _rewrite_spool(path, data, keep)
    else:
        with open(path, "rb") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # held through os.replace: no append lands in between
            _rewrite_spool(path, data, keep)
    log("drain", {"kept": len(keep)})


def _rewrite_spool(path, data, keep):
    """Replace the spool with the kept lines plus whatever was appended after `data` was read."""
    with open(path, "rb") as g:
        rest = g.read()[len(data):]
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(b"".join(keep) + rest)
    os.replace(tmp, path)


PARENT_POLL_SECS = 5


def _roster():
    """The unimatrix-roster module, loaded on first use."""
    roster = sys.modules.get("unimatrix_roster")
    if roster is None:
        spec = importlib.util.spec_from_file_location(
            "unimatrix_roster", os.path.join(os.path.dirname(os.path.abspath(__file__)), "unimatrix-roster.py"))
        roster = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_roster"] = roster
        spec.loader.exec_module(roster)
    return roster


def parent_gone():
    """True when $AGY_LEG_PARENT_PID names a process that no longer exists."""
    try:
        pid = int(os.environ.get("AGY_LEG_PARENT_PID", ""))
    except ValueError:
        return False
    if sys.platform == "win32":  # os.kill(pid, 0) terminates the process on Windows
        return not _roster().pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False  # EPERM: alive under another user
    return False


def stamp_proc_start():
    """Record this leg's process start in its leg record (`<AGY_LEG_LOG stem>.json`) once the hook has written it.

    The router shows a leg live only when pid and procStart both match. Best effort and idempotent:
    a record not yet written, or rewritten by the hook without the stamp, is retried by the poll loop.
    """
    log_file = os.environ.get("AGY_LEG_LOG")
    if not log_file:
        return
    path = os.path.splitext(log_file)[0] + ".json"
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        if rec.get("pid") != os.getpid() or rec.get("procStart") is not None:
            return
        roster = _roster()
        rec["procStart"] = roster.proc_start(os.getpid())
        roster.write_json_atomic(path, rec)
    except (OSError, ValueError, TypeError, AttributeError):
        pass


def respond(buf, pending):
    """The one-line JSON answer to one request line: queue it while pending, else deliver it live."""
    try:
        text = json.loads(buf)["text"]
    except (ValueError, KeyError, TypeError):
        return b'{"ok":false,"body":"bad request"}\n'
    if pending:
        try:
            enqueue(text)
        except OSError as e:
            return (json.dumps({"ok": False, "body": f"spool error: {e}"}) + "\n").encode()
        return b'{"ok": true, "queued": true}\n'
    return (json.dumps(send(text)) + "\n").encode()


def _pipe_security():
    """SECURITY_ATTRIBUTES granting the pipe to the current user only."""
    import pywintypes
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    acl = win32security.ACL()
    acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, sid)
    sd = win32security.SECURITY_DESCRIPTOR()
    sd.SetSecurityDescriptorDacl(1, acl, 0)
    sd.SetSecurityDescriptorControl(win32security.SE_DACL_PROTECTED, win32security.SE_DACL_PROTECTED)
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    return sa


def serve_pipe(endpoint, pending):
    """Bind the named pipe `endpoint` and serve it from a daemon thread; the thread is returned.

    The first instance exists when this returns, and the next instance is created before a
    connection is served, so a client never meets an endpoint-less gap.
    """
    import pywintypes
    import win32file
    import win32pipe
    security = _pipe_security()

    def new_instance():
        return win32pipe.CreateNamedPipe(
            endpoint, win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT
            | getattr(win32pipe, "PIPE_REJECT_REMOTE_CLIENTS", 8),
            win32pipe.PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, security)

    def serve(h):
        try:
            buf = b""
            try:
                while not buf.endswith(b"\n"):
                    chunk = win32file.ReadFile(h, 65536)[1]
                    if not chunk:
                        break
                    buf += chunk
                win32file.WriteFile(h, respond(buf, pending))
                win32file.FlushFileBuffers(h)  # disconnecting first would drop the unread answer
            except pywintypes.error:
                pass
        finally:
            try:
                win32pipe.DisconnectNamedPipe(h)
            except pywintypes.error:
                pass
            win32file.CloseHandle(h)

    def accept(h):
        while True:
            try:
                try:
                    win32pipe.ConnectNamedPipe(h, None)
                except pywintypes.error as exc:
                    if exc.winerror != 535:  # ERROR_PIPE_CONNECTED: the client beat ConnectNamedPipe
                        raise
                nxt = new_instance()
            except pywintypes.error as exc:
                log("exit", {"reason": f"pipe accept failed: {exc}"})
                return
            threading.Thread(target=serve, args=(h,), daemon=True).start()
            h = nxt

    t = threading.Thread(target=accept, args=(new_instance(),), daemon=True)
    t.start()
    return t


def main(sock):
    pending = not os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    log("start", {"pid": os.getpid(), "ls_address": os.environ.get("ANTIGRAVITY_LS_ADDRESS"),
                  "conversation": os.environ.get("ANTIGRAVITY_CONVERSATION_ID"),
                  "mode": "pending" if pending else "live"})
    if not os.environ.get("ANTIGRAVITY_CONVERSATION_ID"):
        sys.exit("missing env: ['ANTIGRAVITY_CONVERSATION_ID']")
    if not pending:
        drain()
    if sys.platform == "win32":
        t = serve_pipe(sock, pending)
        if not pending:
            drain()  # second pass: lines a client queued while the pipe was still binding
        while t.is_alive():
            stamp_proc_start()
            time.sleep(PARENT_POLL_SECS)
            if parent_gone():
                log("exit", {"reason": "agy parent gone"})
                return
        return
    os.makedirs(os.path.dirname(os.path.abspath(sock)), exist_ok=True)
    if os.path.exists(sock):
        os.unlink(sock)
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(sock)
    os.chmod(sock, 0o600)
    srv.listen(4)
    if not pending:
        drain()  # a pending leg SIGTERMed mid-append can land a line after the first drain
    srv.settimeout(PARENT_POLL_SECS)
    while True:
        try:
            c, _ = srv.accept()
        except socket.timeout:
            stamp_proc_start()
            if parent_gone():
                log("exit", {"reason": "agy parent gone"})
                srv.close()
                os.unlink(sock)
                return
            continue
        c.setblocking(True)
        with c:
            c.settimeout(30)
            buf = b""
            try:
                while not buf.endswith(b"\n"):
                    chunk = c.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
            except OSError:
                continue
            c.sendall(respond(buf, pending))


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-agy-leg [-h]\nAntigravity leg; usage: unimatrix-agy-leg <session-id> (needs ANTIGRAVITY_CONVERSATION_ID)")
        raise SystemExit(0)
    main(sys.argv[1])
