"""Windows named-pipe transport for claude-author --control-socket (ctypes, stdlib-only).

Implements ``protocol.Transport``. The pipe is created with a current-user-only DACL,
FILE_FLAG_FIRST_PIPE_INSTANCE (a squatter's pre-created pipe makes creation fail) and
PIPE_REJECT_REMOTE_CLIENTS. Each client gets a server thread that stamps a ``protocol.Peer``
with the client PID and SID; a SID other than the supervisor's own yields peer None, which
``protocol.handle_line`` answers with not_attested.

Importing is safe on every OS: all ctypes.windll access happens inside functions that run only
on win32.
"""
from __future__ import annotations

import sys
import threading
from typing import Optional

from . import protocol

IS_WINDOWS = sys.platform == "win32"

PIPE_ACCESS_DUPLEX = 0x00000003
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
PIPE_UNLIMITED_INSTANCES = 255
ERROR_PIPE_CONNECTED = 535
ERROR_NO_DATA = 232
TOKEN_QUERY = 0x0008
TOKEN_USER = 1
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
SDDL_REVISION_1 = 1
BUFSZ = 65536


def sddl_for_sid(sid: str) -> str:
    """Protected DACL granting all access to exactly one SID."""
    return f"D:P(A;;GA;;;{sid})"


def pipe_name(instance: str) -> str:
    if not protocol.is_instance_id(instance):
        raise ValueError(f"bad instance id {instance!r}")
    return protocol.pipe_address(instance)


class _Api:
    """Typed ctypes bindings, built once on win32."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ct = ctypes
        self.wt = wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        self.k32, self.adv = k32, adv
        H, D, B, V = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.c_void_p

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("nLength", D), ("lpSecurityDescriptor", V), ("bInheritHandle", B)]

        self.SECURITY_ATTRIBUTES = SECURITY_ATTRIBUTES
        P = ctypes.POINTER

        def sig(fn, res, args):
            fn.restype = res
            fn.argtypes = args

        sig(k32.CreateNamedPipeW, H, [wintypes.LPCWSTR, D, D, D, D, D, D, P(SECURITY_ATTRIBUTES)])
        sig(k32.ConnectNamedPipe, B, [H, V])
        sig(k32.DisconnectNamedPipe, B, [H])
        sig(k32.CloseHandle, B, [H])
        sig(k32.ReadFile, B, [H, V, D, P(D), V])
        sig(k32.WriteFile, B, [H, V, D, P(D), V])
        sig(k32.GetNamedPipeClientProcessId, B, [H, P(D)])
        sig(k32.GetCurrentProcess, H, [])
        sig(k32.GetCurrentThread, H, [])
        sig(k32.LocalFree, V, [V])
        sig(k32.CreateFileW, H, [wintypes.LPCWSTR, D, D, V, D, D, H])
        sig(adv.OpenProcessToken, B, [H, D, P(H)])
        sig(adv.OpenThreadToken, B, [H, D, B, P(H)])
        sig(adv.GetTokenInformation, B, [H, ctypes.c_int, V, D, P(D)])
        sig(adv.ConvertSidToStringSidW, B, [V, P(wintypes.LPWSTR)])
        sig(adv.ConvertStringSecurityDescriptorToSecurityDescriptorW,
            B, [wintypes.LPCWSTR, D, P(V), V])
        sig(adv.ImpersonateNamedPipeClient, B, [H])
        sig(adv.RevertToSelf, B, [])
        self.INVALID = H(-1).value

    def last_error(self) -> int:
        return self.ct.get_last_error()

    def token_sid(self, token) -> str:
        ct = self.ct
        need = self.wt.DWORD(0)
        self.adv.GetTokenInformation(token, TOKEN_USER, None, 0, ct.byref(need))
        buf = ct.create_string_buffer(need.value)
        if not self.adv.GetTokenInformation(token, TOKEN_USER, buf, need.value, ct.byref(need)):
            raise OSError(self.last_error(), "GetTokenInformation failed")
        sid_ptr = ct.c_void_p.from_buffer(buf).value  # TOKEN_USER.User.the Game Dev Reviewer is the first field
        out = self.wt.LPWSTR()
        if not self.adv.ConvertSidToStringSidW(sid_ptr, ct.byref(out)):
            raise OSError(self.last_error(), "ConvertSidToStringSidW failed")
        try:
            return out.value
        finally:
            self.k32.LocalFree(ct.cast(out, ct.c_void_p))

    def own_sid(self) -> str:
        tok = self.wt.HANDLE()
        if not self.adv.OpenProcessToken(self.k32.GetCurrentProcess(), TOKEN_QUERY,
                                         self.ct.byref(tok)):
            raise OSError(self.last_error(), "OpenProcessToken failed")
        try:
            return self.token_sid(tok)
        finally:
            self.k32.CloseHandle(tok)

    def client_sid(self, pipe) -> str:
        """SID of the pipe client, by impersonation. Needs a prior read on the instance."""
        if not self.adv.ImpersonateNamedPipeClient(pipe):
            raise OSError(self.last_error(), "ImpersonateNamedPipeClient failed")
        try:
            tok = self.wt.HANDLE()
            if not self.adv.OpenThreadToken(self.k32.GetCurrentThread(), TOKEN_QUERY, True,
                                            self.ct.byref(tok)):
                raise OSError(self.last_error(), "OpenThreadToken failed")
            try:
                return self.token_sid(tok)
            finally:
                self.k32.CloseHandle(tok)
        finally:
            self.adv.RevertToSelf()


class PipeTransport:
    """Named-pipe server. Construction creates the first pipe instance, so a squatted name
    raises OSError before the supervisor advertises anything."""

    def __init__(self, instance: str) -> None:
        if not IS_WINDOWS:
            raise OSError("named pipes require win32")
        self.address = pipe_name(instance)
        self._api = _Api()
        self._own_sid = self._api.own_sid()
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._handles: set = set()
        self._threads: list[threading.Thread] = []
        self._pending = self._create_instance(first=True)

    def _create_instance(self, first: bool):
        api, ct = self._api, self._api.ct
        sd = ct.c_void_p()
        if not api.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl_for_sid(self._own_sid), SDDL_REVISION_1, ct.byref(sd), None):
            raise OSError(api.last_error(), "ConvertStringSecurityDescriptor failed")
        try:
            sa = api.SECURITY_ATTRIBUTES(ct.sizeof(api.SECURITY_ATTRIBUTES), sd, False)
            mode = PIPE_ACCESS_DUPLEX | (FILE_FLAG_FIRST_PIPE_INSTANCE if first else 0)
            h = api.k32.CreateNamedPipeW(
                self.address, mode,
                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                PIPE_UNLIMITED_INSTANCES, BUFSZ, BUFSZ, 0, ct.byref(sa))
            if h is None or h == api.INVALID:
                raise OSError(api.last_error(), f"CreateNamedPipeW failed for {self.address}")
        finally:
            api.k32.LocalFree(sd)
        with self._lock:
            self._handles.add(h)
        return h

    def _drop(self, h) -> None:
        with self._lock:
            had = h in self._handles
            self._handles.discard(h)
        if had:
            self._api.k32.CloseHandle(h)

    def serve(self, handler: protocol.Handler) -> None:
        api = self._api
        while not self._closed.is_set():
            h = self._pending
            ok = api.k32.ConnectNamedPipe(h, None)
            if not ok:
                err = api.last_error()
                if err == ERROR_NO_DATA and not self._closed.is_set():
                    # A client connected and closed before this call (a probe, a crashed
                    # peer). The instance is still ours: reset it and listen again.
                    api.k32.DisconnectNamedPipe(h)
                    continue
                if err != ERROR_PIPE_CONNECTED:
                    self._drop(h)
                    if self._closed.is_set():
                        return
                    raise OSError(err, "ConnectNamedPipe failed")
            if self._closed.is_set():
                self._drop(h)
                return
            self._pending = self._create_instance(first=False)
            t = threading.Thread(target=self._client, args=(h, handler), daemon=True)
            t.start()  # started before it is listed: close() joins every listed thread
            self._threads.append(t)

    def _read(self, h) -> Optional[bytes]:
        api, ct = self._api, self._api.ct
        buf = ct.create_string_buffer(BUFSZ)
        n = api.wt.DWORD(0)
        if not api.k32.ReadFile(h, buf, BUFSZ, ct.byref(n), None) or n.value == 0:
            return None
        return buf.raw[:n.value]

    def _write(self, h, data: bytes) -> bool:
        api, ct = self._api, self._api.ct
        view = memoryview(data)
        while view:
            n = api.wt.DWORD(0)
            chunk = bytes(view[:BUFSZ])
            if not api.k32.WriteFile(h, chunk, len(chunk), ct.byref(n), None) or n.value == 0:
                return False
            view = view[n.value:]
        return True

    def _attest(self, h) -> Optional[protocol.Peer]:
        api, ct = self._api, self._api.ct
        try:
            pid = api.wt.DWORD(0)
            if not api.k32.GetNamedPipeClientProcessId(h, ct.byref(pid)):
                return None
            sid = api.client_sid(h)
        except OSError:
            return None
        if sid != self._own_sid:
            return None
        return protocol.Peer(transport="pipe", pid=pid.value, sid=sid)

    def _client(self, h, handler: protocol.Handler) -> None:
        splitter = protocol.LineSplitter()
        peer: Optional[protocol.Peer] = None
        attested = False
        try:
            while not self._closed.is_set():
                data = self._read(h)
                if data is None:
                    break
                if not attested:
                    # Impersonation is only valid once a message has been read.
                    peer, attested = self._attest(h), True
                try:
                    lines = splitter.feed(data)
                except protocol.ProtocolError as e:
                    self._write(h, protocol.encode_response(
                        protocol.ErrorResponse(None, e.code, e.msg, close=True)))
                    break
                for line in lines:
                    resp, close = protocol.handle_line(line, peer, handler)
                    if not self._write(h, resp) or close:
                        return
        finally:
            self._api.k32.DisconnectNamedPipe(h)
            self._drop(h)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        api = self._api
        # Unblock a ConnectNamedPipe waiting on the pending instance.
        wake = api.k32.CreateFileW(self.address, GENERIC_READ | GENERIC_WRITE, 0, None,
                                   OPEN_EXISTING, 0, None)
        if wake is not None and wake != api.INVALID:
            api.k32.CloseHandle(wake)
        for t in list(self._threads):
            t.join(timeout=0.2)
        with self._lock:
            leftover = list(self._handles)
        for h in leftover:
            self._drop(h)


def make_transport(instance: str, instance_dir: str) -> PipeTransport:
    """protocol.Transport factory the supervisor loads; the pipe is named by ``instance``."""
    return PipeTransport(instance)
