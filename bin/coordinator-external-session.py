#!/usr/bin/env python3
"""Codex lifecycle bridge: one stdlib round trip to the warm engine's external_session.handle op.

Imports no coordinator_core module and spawns no server. Any miss prints a typed
`{"systemMessage": "<hook>: degraded: <ExcType>: <detail>"}` advisory and a stderr line and exits 0, so a Codex turn is never blocked. The endpoint derivation below mirrors
`coordinator_core.warm.election` / `skew` (pipe on Windows, unix socket elsewhere) and must
change with them.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import BinaryIO

EVENTS = ('SessionStart', 'SessionEnd', 'SubagentStart', 'UserPromptSubmit', 'PostToolUse',
          'Stop', 'SubagentStop', 'PreCompact', 'PostCompact')
OP = 'external_session.handle'
HOOK = 'coordinator-external-session'
DEADLINE_SECS = 1.5
_BUSY_RETRY_SECS = 0.4


def _user_sid() -> str:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    htoken = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(htoken)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(htoken, 1, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(htoken, 1, buf, size.value, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(text)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return text.value or ''
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.CloseHandle(htoken)


def _owner_sid(root: Path) -> str:
    try:
        text = (root / 'coordinator_core' / 'warm' / 'door' / 'door.owner-sid.txt').read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError):
        text = ''
    if text.startswith('S-1-') and not text.strip('0123456789-S'):
        return text
    return _user_sid()


def _endpoint(root: Path, token: str) -> str:
    clone_hash = hashlib.sha1(str(root.resolve()).encode('utf-8')).hexdigest()[:16]
    if sys.platform == 'win32':
        return f'\\\\.\\pipe\\coordinator-core.{_owner_sid(root)}.{clone_hash}.{token}'
    base = os.environ.get('COORDINATOR_WARM_RUNTIME_BASE', '').strip() or os.environ.get('LOCALAPPDATA') or str(Path.home() / '.cache')
    return str(Path(base) / 'coordinator' / 'warm' / clone_hash / f'{token}.sock')


def _open(endpoint: str) -> BinaryIO:
    if sys.platform == 'win32':
        deadline = time.monotonic() + _BUSY_RETRY_SECS
        while True:
            try:
                return open(endpoint, 'r+b')
            except FileNotFoundError:
                raise
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
    import socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.25)
        sock.connect(endpoint)
        sock.settimeout(None)
        stream = sock.makefile('rwb')
    except BaseException:
        sock.close()
        raise
    sock.close()
    return stream


def _round_trip(root: Path, request: dict) -> dict:
    token = hashlib.sha1(b'engine-stamp:' + (root / 'coordinator_core' / '_engine_stamp').read_bytes()).hexdigest()[:16]
    request['_engine_token'] = token
    fh = _open(_endpoint(root, token))
    try:
        fh.write(json.dumps(request, ensure_ascii=False).encode('utf-8') + b'\n')
        fh.flush()
        line = fh.readline()
    finally:
        try:
            fh.close()
        except OSError:
            pass
    if not line.strip():
        raise ValueError('warm engine closed without a response')
    return json.loads(line)


def _dial(root: Path, request: dict) -> 'dict | Exception':
    """The op's response, or an Exception describing the miss; bounded by DEADLINE_SECS."""
    box: dict = {}

    def run() -> None:
        try:
            box['value'] = _round_trip(root, request)
        except Exception as exc:  # noqa: BLE001 -- every dial failure is a miss
            box['value'] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(DEADLINE_SECS)
    return box.get('value', TimeoutError(f'no warm response within {DEADLINE_SECS}s'))


def main(argv: 'list[str] | None' = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        event = args[args.index('--event') + 1]
        root = Path(args[args.index('--engine-root') + 1])
        if event not in EVENTS or not root.is_absolute():
            raise ValueError('published engine root and lifecycle event are required')
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError('hook payload must be an object')
        request = {'jsonrpc': '2.0', 'id': 1, 'method': OP,
                   'params': {'event': event, 'payload': payload, 'env': dict(os.environ), 'caller_pid': os.getpid()},
                   '_caller': {'cwd': os.getcwd(), 'pid': os.getpid()},
                   '_dispatch_key': f'{os.getpid()}-1-{time.monotonic_ns()}'}
        response = _dial(root, request)
        if isinstance(response, Exception):
            raise response
        result = response.get('result')
        if 'error' in response or not isinstance(result, dict) or not isinstance(result.get('output'), dict):
            raise RuntimeError(f'warm engine refused {OP}: {str(response.get("error", response))[:200]}')
        for notice in result.get('notices') or ():
            sys.stderr.write(f'{notice}\n')
        sys.stdout.write(json.dumps(result['output']) + '\n')
        return 0
    except BaseException as exc:  # noqa: BLE001 -- a hook must never break the session
        sys.stderr.write(f'external session context unavailable: {type(exc).__name__}: {exc}\n')
        sys.stdout.write(json.dumps({'systemMessage': f'{HOOK}: degraded: {type(exc).__name__}: {exc}'}) + '\n')
        return 0


if __name__ == '__main__':
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: coordinator-external-session [-h]\nprint the external session context (hook-driven bridge; takes no arguments)")
        raise SystemExit(0)
    try:
        _rc = main()
        sys.stdout.flush()
        sys.stderr.flush()
    except BaseException:  # noqa: BLE001 -- a broken pipe must not turn a degrade into exit 1
        _rc = 0
    os._exit(_rc)
