"""Windows ConPTY relay for claude-author --control-socket (implements protocol.Relay/Spawn).

Pure ctypes against kernel32, bound lazily so the module imports on every OS. The child gets
its own pseudoconsole; the supervisor is the only reader of the invoking console.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from typing import Optional

# Win32 constants.
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
ENABLE_PROCESSED_OUTPUT = 0x0001
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT = 0x102
INVALID_HANDLE_VALUE = -1
DEFAULT_COLS, DEFAULT_ROWS = 120, 30
RESIZE_POLL_SECONDS = 0.25

# CreateProcessW contract: no console-placement flag (the pseudoconsole is the console) and no
# handle inheritance. STARTF_USESTDHANDLES is set with all three std handles left NULL: without
# it, current Windows builds copy the parent's std handles into the child (a redirected parent
# gets its pipes inherited and the child writes there, bypassing the pseudoconsole; a real
# console handle would bind the child to the invoking console). NULL handles make the child
# fall back to the console it is attached to, the pseudoconsole.
CREATION_FLAGS = EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
INHERIT_HANDLES = False
STARTF_USESTDHANDLES = 0x00000100
STARTF_FLAGS = STARTF_USESTDHANDLES


def build_env_block(env: dict[str, str]) -> str:
    """Sorted (case-insensitive, as Windows requires), double-NUL-terminated block text."""
    items = sorted(env.items(), key=lambda kv: (kv[0].upper(), kv[0]))
    return "".join(f"{k}={v}\0" for k, v in items) + "\0"


def build_cmdline(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv)


class _Api:
    """kernel32 bindings and structures, built on first use (win32 only)."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes as w

        self.ctypes, self.w = ctypes, w
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k = k
        H = w.HANDLE

        class COORD(ctypes.Structure):
            _fields_ = [("X", w.SHORT), ("Y", w.SHORT)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", w.SHORT), ("Top", w.SHORT), ("Right", w.SHORT), ("Bottom", w.SHORT)]

        class CSBI(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD), ("wAttributes", w.WORD),
                        ("srWindow", SMALL_RECT), ("dwMaximumWindowSize", COORD)]

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR),
                        ("lpTitle", w.LPWSTR), ("dwX", w.DWORD), ("dwY", w.DWORD),
                        ("dwXSize", w.DWORD), ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD),
                        ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                        ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
                        ("lpReserved2", ctypes.c_void_p), ("hStdInput", H), ("hStdOutput", H),
                        ("hStdError", H)]

        class STARTUPINFOEXW(ctypes.Structure):
            _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [("hProcess", H), ("hThread", H), ("dwProcessId", w.DWORD),
                        ("dwThreadId", w.DWORD)]

        self.COORD, self.CSBI = COORD, CSBI
        self.STARTUPINFOEXW, self.PROCESS_INFORMATION = STARTUPINFOEXW, PROCESS_INFORMATION

        vp = ctypes.c_void_p
        k.CreatePipe.argtypes = [ctypes.POINTER(H), ctypes.POINTER(H), vp, w.DWORD]
        k.CreatePipe.restype = w.BOOL
        k.CreatePseudoConsole.argtypes = [COORD, H, H, w.DWORD, ctypes.POINTER(vp)]
        k.CreatePseudoConsole.restype = ctypes.c_long
        k.ResizePseudoConsole.argtypes = [vp, COORD]
        k.ResizePseudoConsole.restype = ctypes.c_long
        k.ClosePseudoConsole.argtypes = [vp]
        k.ClosePseudoConsole.restype = None
        k.InitializeProcThreadAttributeList.argtypes = [vp, w.DWORD, w.DWORD,
                                                        ctypes.POINTER(ctypes.c_size_t)]
        k.InitializeProcThreadAttributeList.restype = w.BOOL
        k.UpdateProcThreadAttribute.argtypes = [vp, w.DWORD, ctypes.c_size_t, vp,
                                                ctypes.c_size_t, vp, vp]
        k.UpdateProcThreadAttribute.restype = w.BOOL
        k.DeleteProcThreadAttributeList.argtypes = [vp]
        k.DeleteProcThreadAttributeList.restype = None
        k.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, vp, vp, w.BOOL, w.DWORD, vp,
                                     w.LPCWSTR, ctypes.POINTER(STARTUPINFOEXW),
                                     ctypes.POINTER(PROCESS_INFORMATION)]
        k.CreateProcessW.restype = w.BOOL
        k.ReadFile.argtypes = [H, vp, w.DWORD, ctypes.POINTER(w.DWORD), vp]
        k.ReadFile.restype = w.BOOL
        k.WriteFile.argtypes = [H, vp, w.DWORD, ctypes.POINTER(w.DWORD), vp]
        k.WriteFile.restype = w.BOOL
        k.CloseHandle.argtypes = [H]
        k.CloseHandle.restype = w.BOOL
        k.GetStdHandle.argtypes = [w.DWORD]
        k.GetStdHandle.restype = H
        k.GetConsoleMode.argtypes = [H, ctypes.POINTER(w.DWORD)]
        k.GetConsoleMode.restype = w.BOOL
        k.SetConsoleMode.argtypes = [H, w.DWORD]
        k.SetConsoleMode.restype = w.BOOL
        k.GetConsoleScreenBufferInfo.argtypes = [H, ctypes.POINTER(CSBI)]
        k.GetConsoleScreenBufferInfo.restype = w.BOOL
        k.WaitForSingleObject.argtypes = [H, w.DWORD]
        k.WaitForSingleObject.restype = w.DWORD
        k.GetExitCodeProcess.argtypes = [H, ctypes.POINTER(w.DWORD)]
        k.GetExitCodeProcess.restype = w.BOOL

    def error(self, what: str) -> OSError:
        return OSError(self.ctypes.get_last_error(), f"{what} failed")


_api: Optional[_Api] = None


def _get_api() -> _Api:
    global _api
    if _api is None:
        if sys.platform != "win32":
            raise OSError("ConPTY relay is Windows-only")
        _api = _Api()
    return _api


def _std_handle(api: _Api, which: int):
    h = api.k.GetStdHandle(which)
    if h is None or h == INVALID_HANDLE_VALUE or h == 0:
        return None
    return h


def _console_size(api: _Api, hout) -> tuple[int, int]:
    if hout is None:
        return DEFAULT_COLS, DEFAULT_ROWS
    info = api.CSBI()
    if not api.k.GetConsoleScreenBufferInfo(hout, api.ctypes.byref(info)):
        return DEFAULT_COLS, DEFAULT_ROWS
    cols = info.srWindow.Right - info.srWindow.Left + 1
    rows = info.srWindow.Bottom - info.srWindow.Top + 1
    return (cols, rows) if cols > 0 and rows > 0 else (DEFAULT_COLS, DEFAULT_ROWS)


def _read(api: _Api, handle, n: int = 4096) -> bytes:
    """Blocking read; b'' on EOF/broken pipe/error."""
    buf = api.ctypes.create_string_buffer(n)
    got = api.w.DWORD(0)
    if not api.k.ReadFile(handle, buf, n, api.ctypes.byref(got), None) or got.value == 0:
        return b""
    return buf.raw[:got.value]


def _write_all(api: _Api, handle, data: bytes) -> None:
    view = memoryview(data)
    while view:
        chunk = bytes(view[:65536])
        got = api.w.DWORD(0)
        if not api.k.WriteFile(handle, chunk, len(chunk), api.ctypes.byref(got), None):
            raise api.error("WriteFile")
        if got.value == 0:
            raise OSError("WriteFile wrote 0 bytes")
        view = view[got.value:]


class ConPtyRelay:
    """protocol.Relay over a Windows pseudoconsole."""

    def __init__(self, api: _Api, argv: list[str], env: dict[str, str], observers,
                 *, attach_console: bool = True) -> None:
        self._api = api
        self._obs = observers
        self._write_lock = threading.Lock()
        self._closed = False
        self._exit_code: Optional[int] = None
        self._wait_lock = threading.Lock()
        self._stop = threading.Event()
        self._h_in_write = self._h_out_read = None
        self._hpc = None
        self._h_proc = None
        self._saved_modes: list = []
        self._hin = _std_handle(api, STD_INPUT_HANDLE) if attach_console else None
        self._hout = _std_handle(api, STD_OUTPUT_HANDLE) if attach_console else None
        self._threads: list[threading.Thread] = []
        try:
            self._start(argv, env)
        except BaseException:
            self._restore_modes()
            self._close_handles()
            raise

    # -- setup -------------------------------------------------------------------------
    def _start(self, argv: list[str], env: dict[str, str]) -> None:
        a = self._api
        ct, w, k = a.ctypes, a.w, a.k
        in_read, in_write = w.HANDLE(), w.HANDLE()
        out_read, out_write = w.HANDLE(), w.HANDLE()
        if not k.CreatePipe(ct.byref(in_read), ct.byref(in_write), None, 0):
            raise a.error("CreatePipe")
        if not k.CreatePipe(ct.byref(out_read), ct.byref(out_write), None, 0):
            k.CloseHandle(in_read)
            k.CloseHandle(in_write)
            raise a.error("CreatePipe")
        self._h_in_write, self._h_out_read = in_write, out_read
        cols, rows = _console_size(a, self._hout)
        self._cols, self._rows = cols, rows
        hpc = ct.c_void_p()
        hr = k.CreatePseudoConsole(a.COORD(cols, rows), in_read, out_write, 0, ct.byref(hpc))
        if hr != 0:
            k.CloseHandle(in_read)
            k.CloseHandle(out_write)
            raise OSError(hr, "CreatePseudoConsole failed")
        self._hpc = hpc

        size = ct.c_size_t(0)
        k.InitializeProcThreadAttributeList(None, 1, 0, ct.byref(size))
        attr_buf = ct.create_string_buffer(size.value)
        if not k.InitializeProcThreadAttributeList(attr_buf, 1, 0, ct.byref(size)):
            k.CloseHandle(in_read)
            k.CloseHandle(out_write)
            raise a.error("InitializeProcThreadAttributeList")
        try:
            if not k.UpdateProcThreadAttribute(attr_buf, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                                               hpc, ct.sizeof(ct.c_void_p), None, None):
                raise a.error("UpdateProcThreadAttribute")
            si = a.STARTUPINFOEXW()
            si.StartupInfo.cb = ct.sizeof(a.STARTUPINFOEXW)
            si.StartupInfo.dwFlags = STARTF_FLAGS
            si.lpAttributeList = ct.cast(attr_buf, ct.c_void_p)
            pi = a.PROCESS_INFORMATION()
            cmd = ct.create_unicode_buffer(build_cmdline(argv))
            text = build_env_block(env)
            block = (ct.c_wchar * len(text))(*text)
            ok = k.CreateProcessW(None, cmd, None, None, INHERIT_HANDLES, CREATION_FLAGS,
                                  ct.cast(block, ct.c_void_p), None, ct.byref(si), ct.byref(pi))
            if not ok:
                raise a.error("CreateProcessW")
        finally:
            k.DeleteProcThreadAttributeList(attr_buf)
            k.CloseHandle(in_read)
            k.CloseHandle(out_write)
        k.CloseHandle(pi.hThread)
        self._h_proc = pi.hProcess

        self._set_modes()
        self._spawn_thread(self._pump_output, "conpty-out")
        if self._hin is not None and self._console_mode(self._hin) is not None:
            self._spawn_thread(self._pump_input, "conpty-in")
        if self._hout is not None:
            self._spawn_thread(self._poll_resize, "conpty-resize")

    def _spawn_thread(self, target, name: str) -> None:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        self._threads.append(t)

    def _console_mode(self, handle) -> Optional[int]:
        mode = self._api.w.DWORD(0)
        if self._api.k.GetConsoleMode(handle, self._api.ctypes.byref(mode)):
            return mode.value
        return None

    def _set_modes(self) -> None:
        k = self._api.k
        if self._hin is not None:
            old = self._console_mode(self._hin)
            if old is not None:
                self._saved_modes.append((self._hin, old))
                k.SetConsoleMode(self._hin, ENABLE_VIRTUAL_TERMINAL_INPUT)
        if self._hout is not None:
            old = self._console_mode(self._hout)
            if old is not None:
                self._saved_modes.append((self._hout, old))
                k.SetConsoleMode(self._hout,
                                 ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING)

    def _restore_modes(self) -> None:
        for handle, mode in reversed(self._saved_modes):
            self._api.k.SetConsoleMode(handle, mode)
        self._saved_modes = []

    # -- channel threads ---------------------------------------------------------------
    def _pump_input(self) -> None:
        a = self._api
        while not self._stop.is_set():
            data = _read(a, self._hin)
            if not data:
                return
            try:
                self._obs.on_input(data)
            except Exception:
                pass
            try:
                self.write(data)
            except OSError:
                return

    def _pump_output(self) -> None:
        a = self._api
        while True:
            data = _read(a, self._h_out_read)
            if not data:
                return
            try:
                self._obs.on_output(data)
            except Exception:
                pass
            if self._hout is not None:
                try:
                    _write_all(a, self._hout, data)
                except OSError:
                    pass

    def _poll_resize(self) -> None:
        a = self._api
        while not self._stop.wait(RESIZE_POLL_SECONDS):
            cols, rows = _console_size(a, self._hout)
            if (cols, rows) != (self._cols, self._rows):
                try:
                    self.resize(cols, rows)
                except OSError:
                    pass

    # -- protocol.Relay ----------------------------------------------------------------
    def write(self, data: bytes) -> None:
        with self._write_lock:
            if self._closed:
                raise OSError("relay closed")
            _write_all(self._api, self._h_in_write, data)

    def resize(self, cols: int, rows: int) -> None:
        if self._closed or self._hpc is None:
            return
        hr = self._api.k.ResizePseudoConsole(self._hpc, self._api.COORD(cols, rows))
        if hr != 0:
            raise OSError(hr, "ResizePseudoConsole failed")
        self._cols, self._rows = cols, rows

    def alive(self) -> bool:
        if self._h_proc is None or self._exit_code is not None:
            return False
        return self._api.k.WaitForSingleObject(self._h_proc, 0) == WAIT_TIMEOUT

    def wait(self) -> int:
        with self._wait_lock:
            if self._exit_code is not None:
                return self._exit_code
            a = self._api
            a.k.WaitForSingleObject(self._h_proc, INFINITE)
            code = a.w.DWORD(0)
            a.k.GetExitCodeProcess(self._h_proc, a.ctypes.byref(code))
            self._shutdown()
            self._exit_code = int(code.value)
            return self._exit_code

    def _shutdown(self) -> None:
        """Close the pseudoconsole while the output thread keeps draining, then join it."""
        self._stop.set()
        with self._write_lock:
            self._closed = True
        if self._hpc is not None:
            self._api.k.ClosePseudoConsole(self._hpc)
            self._hpc = None
        for t in self._threads:
            if t.name == "conpty-out":
                t.join(timeout=5.0)
        self._restore_modes()
        self._close_handles()

    def _close_handles(self) -> None:
        k = self._api.k
        for name in ("_h_in_write", "_h_out_read", "_h_proc"):
            h = getattr(self, name)
            if h is not None:
                k.CloseHandle(h)
                setattr(self, name, None)
        if self._hpc is not None:
            k.ClosePseudoConsole(self._hpc)
            self._hpc = None


def spawn(argv: list[str], env: dict[str, str], observers) -> ConPtyRelay:
    """protocol.Spawn: run argv under a pseudoconsole with exactly `env` as its environment."""
    return ConPtyRelay(_get_api(), argv, env, observers)
