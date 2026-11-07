"""agy-side leg: run BY agy (its run_command, backgrounded) so it inherits agy's own
ANTIGRAVITY_CSRF_TOKEN / ANTIGRAVITY_LS_ADDRESS / ANTIGRAVITY_CONVERSATION_ID. The token never
leaves this process: it is not logged, written, or forwarded.

Without a token the leg runs pending (a SessionStart hook has none): it binds the endpoint, appends
each inbound {"text"} to <conv>.queue.jsonl beside the log (0600), and answers {"ok": true,
"queued": true}. A live leg (token present) drains that spool in order through send() before it
binds, keeping any line it could not deliver or parse.

Listens on <sock>; each connection carries one JSON line {"text": ...}. The leg POSTs it to the
live language server's SendUserCascadeMessage for agy's own conversation and answers one JSON
line {"ok", "status", "body"}.

The leg exits, unlinking its endpoint, once $AGY_LEG_PARENT_PID (the agy process it serves) is
gone; without that variable it runs until killed.

Usage (agy runs this): nohup python3 unimatrix-agy-leg.py <sock> > unimatrix-agy-leg.out 2>&1 &
The log path is $AGY_LEG_LOG else unimatrix-agy-leg.log beside this script.
"""
try:
    import fcntl
except ImportError:  # Windows: main() refuses before any lock is taken; importing must still work
    fcntl = None
import json
import os
import socket
import sys
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
    with open(path, "rb") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # held through os.replace: no append lands in between
        rest = f.read()[len(data):]
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(b"".join(keep) + rest)
        os.replace(tmp, path)
    log("drain", {"kept": len(keep)})


PARENT_POLL_SECS = 5


def parent_gone():
    """True when $AGY_LEG_PARENT_PID names a process that no longer exists."""
    try:
        pid = int(os.environ.get("AGY_LEG_PARENT_PID", ""))
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False  # EPERM: alive under another user
    return False


def main(sock):
    if sys.platform == "win32":
        sys.exit("unimatrix-agy-leg: POSIX only (AF_UNIX listener); the Windows pipe endpoint is not served")
    pending = not os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    log("start", {"pid": os.getpid(), "ls_address": os.environ.get("ANTIGRAVITY_LS_ADDRESS"),
                  "conversation": os.environ.get("ANTIGRAVITY_CONVERSATION_ID"),
                  "mode": "pending" if pending else "live"})
    if not os.environ.get("ANTIGRAVITY_CONVERSATION_ID"):
        sys.exit("missing env: ['ANTIGRAVITY_CONVERSATION_ID']")
    if not pending:
        drain()
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
            try:
                text = json.loads(buf)["text"]
            except (ValueError, KeyError, TypeError):
                c.sendall(b'{"ok":false,"body":"bad request"}\n')
                continue
            if pending:
                try:
                    enqueue(text)
                except OSError as e:
                    c.sendall((json.dumps({"ok": False, "body": f"spool error: {e}"}) + "\n").encode())
                    continue
                c.sendall(b'{"ok": true, "queued": true}\n')
                continue
            c.sendall((json.dumps(send(text)) + "\n").encode())


if __name__ == "__main__":
    main(sys.argv[1])
