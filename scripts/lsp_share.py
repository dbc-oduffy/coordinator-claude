"""Per-repo language-server share daemon and the stdio-to-TCP proxy clients use to reach it.

One daemon per (repo, server name) owns the single server child and multiplexes every client that
connects over 127.0.0.1. Clients (the lsp_launch wrapper) bridge their stdio to the daemon; the
daemon exits, taking the server with it, once no client has been connected for the idle window.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

IDLE_SECONDS = 600
IDLE_ENV = "LSP_SHARE_IDLE_SECONDS"
SPAWN_WAIT_S = 20.0
LOCK_STALE_S = 60.0
_JSONRPC = "2.0"


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def share_key(name: str, repo_root: "str | Path") -> str:
    """Stable id for (server name, repo): sha of the normalised repo path plus the name."""
    try:
        resolved = os.path.realpath(str(repo_root))
    except OSError:
        resolved = str(repo_root)
    norm = os.path.normcase(os.path.normpath(resolved))
    return hashlib.sha256(f"{norm}\0{name}".encode("utf-8")).hexdigest()[:16]


def read_message(stream) -> Optional[dict]:
    """One Content-Length framed JSON-RPC message from a binary stream, None at EOF."""
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        key, _, value = line.partition(b":")
        if key.strip().lower() == b"content-length":
            try:
                length = int(value.strip())
            except ValueError:
                return None
    if length is None:
        return None
    body = stream.read(length)
    if len(body) < length:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def encode_message(obj: dict) -> bytes:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


class _Peer:
    """Serialised writer for one socket."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._lock = threading.Lock()

    def send(self, obj: dict) -> bool:
        try:
            with self._lock:
                self.sock.sendall(encode_message(obj))
            return True
        except OSError:
            return False

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Daemon:
    """Owns one language server and multiplexes any number of TCP clients onto it."""

    def __init__(
        self,
        name: str,
        repo_root: "str | Path",
        argv: Sequence[str],
        runtime: Path,
        idle_seconds: float = IDLE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.repo_root = Path(repo_root)
        self.argv = list(argv)
        self.runtime = Path(runtime)
        self.idle_seconds = idle_seconds
        self.clock = clock
        self.key = share_key(name, repo_root)
        self.port = 0
        self.stopped = threading.Event()
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen] = None
        self._listener: Optional[socket.socket] = None
        self._server_write = threading.Lock()
        self._clients: "dict[int, _Peer]" = {}
        self._next_cid = 0
        self._next_sid = 0
        self._id_map: "dict[int, tuple[int, object]]" = {}
        self._srv_reqs: "dict[str, object]" = {}
        self._init_sid: Optional[int] = None
        self._init_result: Optional[dict] = None
        self._init_waiters: "list[tuple[int, object]]" = []
        self._initialized_sent = False
        self._uris: "dict[str, set[int]]" = {}
        self._idle_since = clock()

    @property
    def registry_path(self) -> Path:
        return self.runtime / f"{self.key}.json"

    def start(self) -> int:
        """Spawn the server, open the listener, publish the registry entry; returns the port."""
        exe = shutil.which(self.argv[0]) or self.argv[0]
        self._proc = subprocess.Popen(
            [exe, *self.argv[1:]],
            cwd=str(self.repo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=_no_console(),
        )
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(16)
        self.port = self._listener.getsockname()[1]
        self.runtime.mkdir(parents=True, exist_ok=True)
        entry = {
            "pid": os.getpid(),
            "port": self.port,
            "name": self.name,
            "repo": str(self.repo_root),
            "server_pid": self._proc.pid,
            "argv": self.argv,
        }
        tmp = self.registry_path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(entry), encoding="utf-8")
        os.replace(tmp, self.registry_path)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._server_loop, daemon=True).start()
        return self.port

    def run_forever(self, poll_s: float = 5.0) -> None:
        self.start()
        while not self.stopped.wait(poll_s):
            self.tick()

    def tick(self) -> bool:
        """Stop when the server died or no client has been connected for the idle window."""
        with self._lock:
            dead = self._proc is not None and self._proc.poll() is not None
            idle = not self._clients and self.clock() - self._idle_since >= self.idle_seconds
        if dead or idle:
            self.shutdown()
        return self.stopped.is_set()

    def shutdown(self) -> None:
        with self._lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            clients = list(self._clients.values())
            self._clients.clear()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            self._to_server({"jsonrpc": _JSONRPC, "id": "lspshare-shutdown", "method": "shutdown"})
            self._to_server({"jsonrpc": _JSONRPC, "method": "exit"})
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        for peer in clients:
            peer.close()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        try:
            current = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if current.get("pid") == os.getpid():
                self.registry_path.unlink()
        except (OSError, ValueError):
            pass

    def _to_server(self, obj: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            with self._server_write:
                proc.stdin.write(encode_message(obj))
                proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def _accept_loop(self) -> None:
        while not self.stopped.is_set():
            try:
                sock, _ = self._listener.accept()
            except OSError:
                return
            with self._lock:
                self._next_cid += 1
                cid = self._next_cid
                peer = _Peer(sock)
                self._clients[cid] = peer
            threading.Thread(target=self._client_loop, args=(cid, peer), daemon=True).start()

    def _client_loop(self, cid: int, peer: _Peer) -> None:
        reader = peer.sock.makefile("rb")
        try:
            while True:
                msg = read_message(reader)
                if msg is None:
                    break
                self.handle_client_message(cid, msg)
        except OSError:
            pass
        finally:
            self._drop_client(cid)

    def _drop_client(self, cid: int) -> None:
        closes = []
        with self._lock:
            peer = self._clients.pop(cid, None)
            for uri in list(self._uris):
                holders = self._uris[uri]
                if cid in holders:
                    holders.discard(cid)
                    if not holders:
                        del self._uris[uri]
                        closes.append(uri)
            if not self._clients:
                self._idle_since = self.clock()
        if peer is not None:
            peer.close()
        for uri in closes:
            self._to_server({
                "jsonrpc": _JSONRPC,
                "method": "textDocument/didClose",
                "params": {"textDocument": {"uri": uri}},
            })

    def handle_client_message(self, cid: int, msg: dict) -> None:
        method = msg.get("method")
        mid = msg.get("id")
        if method is None:
            with self._lock:
                orig = self._srv_reqs.pop(mid, None)
            if orig is not None:
                self._to_server({**msg, "id": orig})
            return
        if mid is None:
            self._client_notification(cid, method, msg)
            return
        peer = self._clients.get(cid)
        if method == "shutdown":
            if peer:
                peer.send({"jsonrpc": _JSONRPC, "id": mid, "result": None})
            return
        if method == "initialize":
            with self._lock:
                cached = self._init_result
                if cached is None and self._init_sid is not None:
                    self._init_waiters.append((cid, mid))
                    return
                if cached is None:
                    sid = self._new_sid()
                    self._init_sid = sid
                    self._id_map[sid] = (cid, mid)
            if cached is not None:
                if peer:
                    peer.send({"jsonrpc": _JSONRPC, "id": mid, "result": cached})
            else:
                self._to_server({**msg, "id": sid})
            return
        with self._lock:
            sid = self._new_sid()
            self._id_map[sid] = (cid, mid)
        self._to_server({**msg, "id": sid})

    def _new_sid(self) -> int:
        self._next_sid += 1
        return self._next_sid

    def _client_notification(self, cid: int, method: str, msg: dict) -> None:
        params = msg.get("params") or {}
        if method == "exit":
            return
        if method == "initialized":
            with self._lock:
                first = not self._initialized_sent
                self._initialized_sent = True
            if first:
                self._to_server(msg)
            return
        if method in ("textDocument/didOpen", "textDocument/didClose"):
            uri = (params.get("textDocument") or {}).get("uri")
            if uri is None:
                self._to_server(msg)
                return
            with self._lock:
                holders = self._uris.setdefault(uri, set())
                if method == "textDocument/didOpen":
                    forward = not holders
                    holders.add(cid)
                else:
                    holders.discard(cid)
                    forward = not holders
                    if forward:
                        del self._uris[uri]
            if forward:
                self._to_server(msg)
            return
        if method == "$/cancelRequest":
            with self._lock:
                for sid, (owner, orig) in self._id_map.items():
                    if owner == cid and orig == params.get("id"):
                        self._to_server({**msg, "params": {**params, "id": sid}})
                        return
            return
        self._to_server(msg)

    def _server_loop(self) -> None:
        proc = self._proc
        try:
            while True:
                msg = read_message(proc.stdout)
                if msg is None:
                    break
                self.handle_server_message(msg)
        except (OSError, ValueError):
            pass
        self.shutdown()

    def handle_server_message(self, msg: dict) -> None:
        method = msg.get("method")
        mid = msg.get("id")
        if method is None:
            self._server_response(mid, msg)
            return
        if mid is not None:
            with self._lock:
                target = self._clients.get(min(self._clients)) if self._clients else None
                if target is not None:
                    rid = f"lspshare-{self._new_sid()}"
                    self._srv_reqs[rid] = mid
            if target is None:
                self._to_server({"jsonrpc": _JSONRPC, "id": mid, "result": None})
            else:
                target.send({**msg, "id": rid})
            return
        if method == "textDocument/publishDiagnostics":
            uri = (msg.get("params") or {}).get("uri")
            with self._lock:
                peers = [self._clients[c] for c in self._uris.get(uri, ()) if c in self._clients]
        else:
            with self._lock:
                peers = list(self._clients.values())
        for peer in peers:
            peer.send(msg)

    def _server_response(self, mid: object, msg: dict) -> None:
        with self._lock:
            owner = self._id_map.pop(mid, None)
            targets = []
            if self._init_sid is not None and mid == self._init_sid:
                if "result" in msg:
                    self._init_result = msg["result"]
                self._init_sid = None
                waiters, self._init_waiters = self._init_waiters, []
                targets = [(c, i) for c, i in waiters]
            if owner is not None:
                targets.insert(0, owner)
            sends = [(self._clients.get(c), i) for c, i in targets]
        for peer, orig in sends:
            if peer is not None:
                peer.send({**msg, "id": orig})


def read_registry(runtime: Path, key: str) -> Optional[dict]:
    try:
        return json.loads((Path(runtime) / f"{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_daemons(runtime: Path) -> "list[dict]":
    """Live daemons recorded under runtime; an entry whose port refuses connections is deleted.

    A daemon killed with its host session never runs shutdown, so its entry outlives it. The
    listener is open before the entry is published, so a refused port means a dead daemon.
    """
    found = []
    try:
        entries = sorted(Path(runtime).glob("*.json"))
    except OSError:
        return found
    for path in entries:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            sock = socket.create_connection(("127.0.0.1", int(entry["port"])), timeout=1)
        except (OSError, ValueError, KeyError):
            try:
                path.unlink()
            except OSError:
                pass
            continue
        sock.close()
        found.append(entry)
    return found


def _try_connect(runtime: Path, key: str) -> Optional[socket.socket]:
    entry = read_registry(runtime, key)
    if not entry:
        return None
    try:
        sock = socket.create_connection(("127.0.0.1", int(entry["port"])), timeout=2)
    except (OSError, ValueError, KeyError):
        return None
    # The 2 s bound is for connecting only. Left on, it makes the bridge's recv raise after any
    # 2 s of server silence (a slow initialize, an idle editor) and the client sees the server die.
    sock.settimeout(None)
    return sock


def _spawn_daemon(name: str, repo_root: Path, argv: "list[str]", runtime: Path) -> None:
    cmd = [
        sys.executable, str(Path(__file__).resolve()), "--daemon", name, str(repo_root),
        "--runtime", str(runtime), "--", *argv,
    ]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | _no_console()
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, cwd=str(repo_root), **kwargs)


def ensure_daemon(
    name: str, repo_root: Path, argv: "list[str]", runtime: Path, wait_s: float = SPAWN_WAIT_S
) -> Optional[socket.socket]:
    """A connected socket to the repo's daemon, spawning it when none is live; None on failure."""
    runtime = Path(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    key = share_key(name, repo_root)
    lock = runtime / f"{key}.lock"
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        sock = _try_connect(runtime, key)
        if sock is not None:
            return sock
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE_S:
                    lock.unlink()
            except OSError:
                pass
            time.sleep(0.1)
            continue
        except OSError:
            return None
        os.close(fd)
        try:
            sock = _try_connect(runtime, key)
            if sock is not None:
                return sock
            try:
                registry = runtime / f"{key}.json"
                registry.unlink()
            except OSError:
                pass
            _spawn_daemon(name, Path(repo_root), argv, runtime)
            while time.monotonic() < deadline:
                sock = _try_connect(runtime, key)
                if sock is not None:
                    return sock
                time.sleep(0.1)
            return None
        finally:
            try:
                lock.unlink()
            except OSError:
                pass
    return None


def bridge(sock: socket.socket, stdin, stdout) -> int:
    """Copy stdin to the socket and the socket to stdout until either side closes."""

    def pump_in() -> None:
        try:
            while True:
                chunk = stdin.read1(65536) if hasattr(stdin, "read1") else stdin.read(65536)
                if not chunk:
                    break
                sock.sendall(chunk)
        except OSError:
            pass
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    threading.Thread(target=pump_in, daemon=True).start()
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            stdout.write(chunk)
            stdout.flush()
    except OSError:
        pass
    finally:
        sock.close()
    return 0


def connect(name: str, repo_root: "str | Path", argv: "list[str]", runtime: Path) -> Optional[int]:
    """Proxy this process's stdio to the repo's shared server; None when no daemon could be reached."""
    sock = ensure_daemon(name, Path(repo_root), argv, runtime)
    if sock is None:
        return None
    rc = bridge(sock, sys.stdin.buffer, sys.stdout.buffer)
    # pump_in is still blocked reading stdin; a normal interpreter shutdown then dies taking the
    # stdin lock (0xC0000005 on Windows), so leave without finalizing.
    sys.stdout.flush()
    os._exit(rc)


def _daemon_main(args: "list[str]") -> int:
    runtime = None
    idle = float(os.environ.get(IDLE_ENV) or IDLE_SECONDS)
    pos = []
    i = 0
    while i < len(args) and args[i] != "--":
        if args[i] == "--runtime":
            runtime = Path(args[i + 1])
            i += 2
        else:
            pos.append(args[i])
            i += 1
    argv = args[i + 1:]
    if runtime is None or len(pos) != 2 or not argv:
        print("usage: lsp_share.py --daemon <name> <repo> --runtime <dir> -- <server argv...>", file=sys.stderr)
        return 2
    Daemon(pos[0], pos[1], argv, runtime, idle_seconds=idle).run_forever()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        sys.exit(_daemon_main(sys.argv[2:]))
    print("lsp_share.py is started by lsp_launch.py", file=sys.stderr)
    sys.exit(2)
