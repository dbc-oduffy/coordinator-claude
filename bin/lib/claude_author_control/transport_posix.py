"""POSIX control-socket transport: AF_UNIX listener, same-uid peer attestation, NDJSON.

Implements ``protocol.Transport``. All sockets are non-blocking and registered on one
selector, the relay's when the supervisor passes it, otherwise a private one driven by
``poll``. Selector entries carry a ``callable(mask)`` as ``key.data``; the owner's loop calls
``key.data(mask)`` for each ready key.
"""
from __future__ import annotations

import os
import selectors
import socket
import struct
import sys
import threading
from typing import Callable, Optional

try:
    from . import protocol
except ImportError:  # loaded by path, not as a package member
    import protocol  # type: ignore[no-redef]

SO_PEERCRED = getattr(socket, "SO_PEERCRED", 17)
SOL_LOCAL = 0
LOCAL_PEERCRED = 1
_UCRED = struct.Struct("3i")  # pid, uid, gid
_XUCRED_SIZE = 76  # cr_version u32, cr_uid u32, cr_ngroups i16, cr_groups[16] u32
_XUCRED_HEAD = struct.Struct("II")
_RECV_CHUNK = 65536


def read_peer_credentials(sock: socket.socket) -> Optional[tuple[int, Optional[int]]]:
    """(uid, pid-or-None) of the connected peer, or None when the OS cannot say."""
    try:
        if sys.platform.startswith("linux"):
            raw = sock.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, _UCRED.size)
            pid, uid, _gid = _UCRED.unpack(raw[:_UCRED.size])
            return uid, pid
        raw = sock.getsockopt(SOL_LOCAL, LOCAL_PEERCRED, _XUCRED_SIZE)
        _version, uid = _XUCRED_HEAD.unpack(raw[:_XUCRED_HEAD.size])
        return uid, None
    except (OSError, struct.error, AttributeError):
        return None


class _Conn:
    def __init__(self, sock: socket.socket, peer: Optional[protocol.Peer]) -> None:
        self.sock = sock
        self.peer = peer
        self.splitter = protocol.LineSplitter()
        self.out = bytearray()
        self.closing = False


class PosixTransport:
    """AF_UNIX server at ``<instance_dir>/sock``. ``serve`` binds; the selector drives I/O."""

    def __init__(self, instance_dir: str, selector: Optional[selectors.BaseSelector] = None):
        self.instance_dir = str(instance_dir)
        self.address = os.path.join(self.instance_dir, protocol.SOCK_NAME)
        self._own_selector = selector is None
        self.selector = selector if selector is not None else selectors.DefaultSelector()
        self._handler: Optional[protocol.Handler] = None
        self._listener: Optional[socket.socket] = None
        self._conns: dict[int, _Conn] = {}
        self._bound = False

    # ------------------------------------------------------------ lifecycle

    def serve(self, handler: protocol.Handler) -> None:
        if len(os.fsencode(self.address)) > protocol.MAX_SOCK_PATH_BYTES:
            raise ValueError(
                f"socket path exceeds {protocol.MAX_SOCK_PATH_BYTES} bytes: {self.address}")
        os.makedirs(self.instance_dir, mode=protocol.DIR_MODE, exist_ok=True)
        os.chmod(self.instance_dir, protocol.DIR_MODE)
        self._handler = handler
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(self.address)
            self._bound = True
            os.chmod(self.address, protocol.FILE_MODE)
            listener.listen(16)
            listener.setblocking(False)
        except BaseException:
            listener.close()
            self._unlink()
            raise
        self._listener = listener
        self.selector.register(listener, selectors.EVENT_READ, self._on_accept)

    def poll(self, timeout: float = 0) -> None:
        """Service ready sockets once; only for a transport that owns its selector."""
        for key, mask in self.selector.select(timeout):
            key.data(mask)

    def close(self) -> None:
        for conn in list(self._conns.values()):
            self._drop(conn)
        if self._listener is not None:
            try:
                self.selector.unregister(self._listener)
            except (KeyError, ValueError):
                pass
            self._listener.close()
            self._listener = None
        self._unlink()
        if self._own_selector:
            self.selector.close()

    def _unlink(self) -> None:
        if self._bound:
            self._bound = False
            try:
                os.unlink(self.address)
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------ I/O

    def _on_accept(self, _mask: int) -> None:
        assert self._listener is not None
        while True:
            try:
                sock, _ = self._listener.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            sock.setblocking(False)
            creds = read_peer_credentials(sock)
            peer: Optional[protocol.Peer] = None
            if creds is not None and creds[0] == os.geteuid():
                peer = protocol.Peer(transport="unix", uid=creds[0], pid=creds[1])
            conn = _Conn(sock, peer)
            self._conns[sock.fileno()] = conn
            self.selector.register(sock, selectors.EVENT_READ,
                                   lambda mask, c=conn: self._on_conn(c, mask))

    def _on_conn(self, conn: _Conn, mask: int) -> None:
        if mask & selectors.EVENT_READ and not conn.closing:
            self._read(conn)
        if conn.sock.fileno() in self._conns and mask & selectors.EVENT_WRITE:
            self._flush(conn)

    def _read(self, conn: _Conn) -> None:
        try:
            data = conn.sock.recv(_RECV_CHUNK)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._drop(conn)
            return
        if not data:
            self._drop(conn)
            return
        try:
            lines = conn.splitter.feed(data)
        except protocol.ProtocolError as e:
            self._send(conn, protocol.encode_response(
                protocol.ErrorResponse(None, e.code, e.msg, close=True)))
            conn.closing = True
            self._flush(conn)
            return
        for line in lines:
            try:
                resp, close = protocol.handle_line(line, conn.peer, self._handler)
            except Exception:
                self._drop(conn)
                return
            self._send(conn, resp)
            if close:
                conn.closing = True
                break
        self._flush(conn)

    def _send(self, conn: _Conn, data: bytes) -> None:
        conn.out += data

    def _flush(self, conn: _Conn) -> None:
        fd = conn.sock.fileno()
        if fd not in self._conns:
            return
        while conn.out:
            try:
                n = conn.sock.send(conn.out)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                self._drop(conn)
                return
            del conn.out[:n]
        if conn.out:
            self.selector.modify(
                conn.sock, selectors.EVENT_READ | selectors.EVENT_WRITE,
                lambda mask, c=conn: self._on_conn(c, mask))
        elif conn.closing:
            self._drop(conn)
        else:
            self.selector.modify(
                conn.sock, selectors.EVENT_READ,
                lambda mask, c=conn: self._on_conn(c, mask))

    def _drop(self, conn: _Conn) -> None:
        fd = conn.sock.fileno()
        self._conns.pop(fd, None)
        try:
            self.selector.unregister(conn.sock)
        except (KeyError, ValueError):
            pass
        conn.sock.close()


class BlockingPosixTransport(PosixTransport):
    """``serve`` binds, then drives I/O on the calling thread until ``close``."""

    def __init__(self, instance_dir: str) -> None:
        super().__init__(instance_dir)
        self._stop = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        # Set once the socket is bound: the supervisor advertises the address only after it.
        self.ready = threading.Event()

    def serve(self, handler: protocol.Handler) -> None:
        self._idle.clear()
        try:
            super().serve(handler)
            self.ready.set()
            while not self._stop.is_set():
                self.poll(0.2)
        finally:
            self._idle.set()

    def close(self) -> None:
        self._stop.set()
        self._idle.wait(2.0)
        super().close()


def make_transport(instance: str, instance_dir: str) -> BlockingPosixTransport:
    """protocol.Transport factory the supervisor loads; ``instance`` is unused on POSIX."""
    return BlockingPosixTransport(instance_dir)
