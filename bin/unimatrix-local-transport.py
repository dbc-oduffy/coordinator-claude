"""Local JSON-line transport: private Unix sockets and native Windows named pipes.

Windows serves through `PipeServer` (protected current-user-only DACL, remote clients rejected)
and connects through asyncio's Proactor pipe transports, preserving the harness's raw byte
protocol. No TCP listener, shell, authentication framing or extra proxy process is introduced.
"""
import asyncio
import errno
import json
import os
import signal
import socket
import stat
import sys
import threading


def is_pipe(endpoint):
    return str(endpoint).lower().startswith("\\\\.\\pipe\\")


def endpoint_exists(endpoint):
    """Probe a pipe without opening it or sending a liveness frame; filesystem stat off Windows."""
    if not is_pipe(endpoint):
        return os.path.exists(endpoint)
    try:
        import _winapi
        _winapi.WaitNamedPipe(str(endpoint), 1)
        return True
    except OSError as exc:
        return getattr(exc, "winerror", None) in (121, 231)  # an existing busy pipe
    except ImportError:
        return False


def _pipe_call(fn, *args, **kwargs):
    """Give callers the same OSError contract as Unix socket operations."""
    import pywintypes
    try:
        return fn(*args, **kwargs)
    except pywintypes.error as exc:
        raise OSError(exc.winerror, str(exc)) from exc


class PipeServer:
    """Byte-mode named pipes with a protected DACL granting only the current user access.

    Remote clients are rejected. Blocking Win32 I/O stays on daemon threads; `handler(reader,
    writer)` runs on the owning asyncio loop. Leading `{"type":"auth"}` frames are consumed.
    """

    def __init__(self, endpoint, handler, limit=1 << 22):
        import pywintypes
        import win32api
        import win32con
        import win32security
        self.endpoint, self.handler, self.limit = endpoint, handler, limit
        self.loop = asyncio.get_running_loop()
        self.closed = False
        self.pending = None
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
        self.security = pywintypes.SECURITY_ATTRIBUTES()
        self.security.SECURITY_DESCRIPTOR = sd
        # Bind synchronously so a successful constructor means the endpoint exists.
        self.pending = self._new_pipe()
        threading.Thread(target=self._accept, daemon=True).start()

    def _new_pipe(self):
        import win32pipe
        return win32pipe.CreateNamedPipe(
            self.endpoint, win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT
            | getattr(win32pipe, "PIPE_REJECT_REMOTE_CLIENTS", 8),
            win32pipe.PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, self.security)

    def _accept(self):
        import pywintypes
        import win32pipe
        while True:
            handle = self.pending
            try:
                try:
                    win32pipe.ConnectNamedPipe(handle, None)
                except pywintypes.error as exc:
                    if exc.winerror != 535:  # client connected before ConnectNamedPipe
                        raise
                if self.closed:
                    handle.Close()
                    return
                self.pending = self._new_pipe()
                threading.Thread(target=self._read, args=(handle,), daemon=True).start()
            except (OSError, pywintypes.error):
                if not self.closed:
                    self.loop.call_exception_handler({"message": "named pipe accept failed"})
                return

    def _read(self, handle):
        import win32file
        import pywintypes
        try:
            raw = bytearray()
            while True:
                raw.extend(win32file.ReadFile(handle, 65536)[1])
                if len(raw) > self.limit:
                    return
                while b"\n" in raw:
                    first, rest = raw.split(b"\n", 1)
                    # Auth headers can be separate writes or share a write with the user frame.
                    parsed = json.loads(first)
                    if isinstance(parsed, dict) and parsed.get("type") == "auth":
                        raw = bytearray(rest)
                        continue
                    break
                else:
                    continue
                break
            reader = asyncio.StreamReader(limit=self.limit, loop=self.loop)
            reader.feed_data(bytes(raw))
            reader.feed_eof()

            class Writer:
                def __init__(self):
                    self.pending = bytearray()

                def write(self, data):
                    self.pending.extend(data)

                async def drain(self):
                    data, self.pending = bytes(self.pending), bytearray()
                    if data:
                        await asyncio.to_thread(_pipe_call, win32file.WriteFile, handle, data)

                def close(self):
                    pass

            asyncio.run_coroutine_threadsafe(self.handler(reader, Writer()), self.loop).result()
        except (OSError, ValueError, pywintypes.error):
            pass
        finally:
            handle.Close()

    def close(self):
        self.closed = True
        # Wake the synchronous accept; its thread owns and closes the pending handle.
        import win32file
        import pywintypes
        try:
            handle = win32file.CreateFile(self.endpoint,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None)
            handle.Close()
        except (OSError, pywintypes.error):
            pass


def _remove_stale_socket(endpoint):
    """Refuse regular files/live listeners; unlink only an unchanged, refused Unix socket."""
    try:
        before = os.lstat(endpoint)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(before.st_mode):
        raise FileExistsError(f"local endpoint is not a socket: {endpoint}")
    with socket.socket(socket.AF_UNIX) as probe:
        probe.settimeout(0.1)
        try:
            probe.connect(endpoint)
        except ConnectionRefusedError:
            pass
        except FileNotFoundError:
            return
        else:
            raise FileExistsError(f"local endpoint already has a listener: {endpoint}")
    try:
        after = os.lstat(endpoint)
    except FileNotFoundError:
        return
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise FileExistsError(f"local endpoint changed during stale check: {endpoint}")
    os.unlink(endpoint)


async def start_server(callback, endpoint, limit):
    """Bind a harness-compatible endpoint; socket mode is private from creation."""
    if is_pipe(endpoint):
        return PipeServer(endpoint, callback, limit)
    os.makedirs(os.path.dirname(endpoint) or ".", mode=0o700, exist_ok=True)
    _remove_stale_socket(endpoint)
    old = os.umask(0o177)
    try:
        server = await asyncio.start_unix_server(callback, path=endpoint, limit=limit)
    finally:
        os.umask(old)
    os.chmod(endpoint, 0o600)
    return server


async def _pipe_exchange(endpoint, data, timeout, reply_timeout):
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=1 << 22)
    protocol = asyncio.StreamReaderProtocol(reader)
    async with asyncio.timeout(timeout):
        transport, _ = await loop.create_pipe_connection(lambda: protocol, endpoint)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        try:
            writer.write(data)
            await writer.drain()
            if reply_timeout is None:
                return await reader.readline()
            try:
                return await asyncio.wait_for(reader.readline(), reply_timeout)
            except asyncio.TimeoutError:
                return b""  # harness sessions may accept without a response line
        finally:
            writer.close()


def pipe_exchange(endpoint, data, timeout, reply_timeout=None):
    """One raw newline request/reply, called off the router's event-loop thread."""
    return asyncio.run(_pipe_exchange(endpoint, data, timeout, reply_timeout))


def install_stop_handlers(stop):
    """Proactor loops lack add_signal_handler; the main thread's signal API remains usable."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))


def lock_file(file, *, windows=None):
    """Take one nonblocking process lock; False means another holder owns it.

    Only contention errnos (EACCES, EAGAIN, EDEADLK) read as held; any other OSError propagates.
    """
    file.seek(0)
    use_windows = sys.platform == "win32" if windows is None else windows
    try:
        if use_windows:
            import msvcrt
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return False
        raise
    return True


def unlock_file(file, *, windows=None):
    file.seek(0)
    use_windows = sys.platform == "win32" if windows is None else windows
    if use_windows:
        import msvcrt
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
