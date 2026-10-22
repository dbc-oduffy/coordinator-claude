"""Win32 adapter for the file-cache trim tool: implements file_cache_contract.FileCacheHost.

Importable on every OS: nothing here touches the Windows DLLs until a Win32FileCacheHost is
constructed. snapshot_from_values is pure and tested everywhere; memory counters are read
in-process through pdh.dll, with no child process.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
from collections.abc import Iterator

from file_cache_contract import (
    CacheLimits,
    CounterError,
    MemorySnapshot,
    PrivilegeError,
    TrimError,
)

ERROR_NOT_ALL_ASSIGNED = 1300
TOKEN_QUERY = 0x0008
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_ELEVATION_CLASS = 20
SE_PRIVILEGE_ENABLED = 0x2
QUOTA_PRIVILEGE_NAME = "SeIncreaseQuotaPrivilege"

PDH_FMT_LARGE = 0x00000400
PERF_FIELDS = (
    "CacheBytes",
    "AvailableBytes",
    "StandbyCacheCoreBytes",
    "StandbyCacheNormalPriorityBytes",
    "StandbyCacheReserveBytes",
    "ModifiedPageListBytes",
)
# PERF_FIELDS name -> English "\Memory\<counter>" path.
PDH_COUNTER_PATHS = {
    "CacheBytes": r"\Memory\Cache Bytes",
    "AvailableBytes": r"\Memory\Available Bytes",
    "StandbyCacheCoreBytes": r"\Memory\Standby Cache Core Bytes",
    "StandbyCacheNormalPriorityBytes": r"\Memory\Standby Cache Normal Priority Bytes",
    "StandbyCacheReserveBytes": r"\Memory\Standby Cache Reserve Bytes",
    "ModifiedPageListBytes": r"\Memory\Modified Page List Bytes",
}

_SIZE_T_MAX = (1 << (ctypes.sizeof(ctypes.c_size_t) * 8)) - 1


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", ctypes.c_uint32)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    """One-entry TOKEN_PRIVILEGES; the only shape this adapter ever sends or receives."""

    _fields_ = [("PrivilegeCount", ctypes.c_uint32), ("Privileges", LUID_AND_ATTRIBUTES * 1)]


class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", ctypes.c_uint32)]


class PDH_FMT_COUNTERVALUE_LARGE(ctypes.Structure):
    """PDH_FMT_COUNTERVALUE read as the PDH_FMT_LARGE member of its union."""

    _fields_ = [("CStatus", ctypes.c_uint32), ("largeValue", ctypes.c_int64)]


def _check_pdh(status: int, what: str) -> None:
    if status != 0:
        raise CounterError(f"{what} failed with PDH_STATUS 0x{status & 0xFFFFFFFF:08X}")


def read_pdh_counters(pdh: object) -> dict[str, int]:
    """Read every PERF_FIELDS counter in one PDH query; any nonzero PDH_STATUS raises
    CounterError. The query is closed on every path."""
    query = ctypes.c_void_p()
    _check_pdh(pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)), "PdhOpenQueryW")
    try:
        handles: dict[str, ctypes.c_void_p] = {}
        for name in PERF_FIELDS:
            handle = ctypes.c_void_p()
            _check_pdh(
                pdh.PdhAddEnglishCounterW(query, PDH_COUNTER_PATHS[name], 0, ctypes.byref(handle)),
                f"PdhAddEnglishCounterW {PDH_COUNTER_PATHS[name]}",
            )
            handles[name] = handle
        _check_pdh(pdh.PdhCollectQueryData(query), "PdhCollectQueryData")
        values: dict[str, int] = {}
        for name, handle in handles.items():
            out = PDH_FMT_COUNTERVALUE_LARGE()
            _check_pdh(
                pdh.PdhGetFormattedCounterValue(
                    handle, PDH_FMT_LARGE, None, ctypes.byref(out)
                ),
                f"PdhGetFormattedCounterValue {PDH_COUNTER_PATHS[name]}",
            )
            _check_pdh(out.CStatus, f"counter {PDH_COUNTER_PATHS[name]}")
            values[name] = out.largeValue
        return values
    finally:
        pdh.PdhCloseQuery(query)


def snapshot_from_values(values: dict[str, int]) -> MemorySnapshot:
    """What memory snapshot does this {PERF_FIELDS name: bytes} dict hold? Missing or negative
    fields raise CounterError."""
    for name in PERF_FIELDS:
        if name not in values or values[name] is None:
            raise CounterError(f"counter field {name} is missing")
        if values[name] < 0:
            raise CounterError(f"counter field {name} is negative: {values[name]}")
    return MemorySnapshot(
        cache_bytes=values["CacheBytes"],
        available_bytes=values["AvailableBytes"],
        standby_bytes=(
            values["StandbyCacheCoreBytes"]
            + values["StandbyCacheNormalPriorityBytes"]
            + values["StandbyCacheReserveBytes"]
        ),
        modified_bytes=values["ModifiedPageListBytes"],
    )


class Win32FileCacheHost:
    """FileCacheHost backed by advapi32/kernel32 and one in-process pdh.dll counter read."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Win32FileCacheHost requires Windows")
        self._advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._pdh = ctypes.WinDLL("pdh")
        self._declare_signatures()

    def _declare_signatures(self) -> None:
        handle, pvoid, dword = ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32
        adv, k32 = self._advapi32, self._kernel32
        k32.GetCurrentProcess.argtypes = []
        k32.GetCurrentProcess.restype = handle
        k32.CloseHandle.argtypes = [handle]
        k32.CloseHandle.restype = ctypes.c_int
        k32.GetSystemFileCacheSize.argtypes = [
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(dword),
        ]
        k32.GetSystemFileCacheSize.restype = ctypes.c_int
        k32.SetSystemFileCacheSize.argtypes = [ctypes.c_size_t, ctypes.c_size_t, dword]
        k32.SetSystemFileCacheSize.restype = ctypes.c_int
        adv.OpenProcessToken.argtypes = [handle, dword, ctypes.POINTER(handle)]
        adv.OpenProcessToken.restype = ctypes.c_int
        adv.GetTokenInformation.argtypes = [handle, ctypes.c_int, pvoid, dword, ctypes.POINTER(dword)]
        adv.GetTokenInformation.restype = ctypes.c_int
        adv.LookupPrivilegeValueW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.POINTER(LUID)]
        adv.LookupPrivilegeValueW.restype = ctypes.c_int
        adv.AdjustTokenPrivileges.argtypes = [
            handle,
            ctypes.c_int,
            ctypes.POINTER(TOKEN_PRIVILEGES),
            dword,
            ctypes.POINTER(TOKEN_PRIVILEGES),
            ctypes.POINTER(dword),
        ]
        adv.AdjustTokenPrivileges.restype = ctypes.c_int
        pdh, status = self._pdh, ctypes.c_uint32
        pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(handle)]
        pdh.PdhOpenQueryW.restype = status
        pdh.PdhAddEnglishCounterW.argtypes = [
            handle, ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(handle),
        ]
        pdh.PdhAddEnglishCounterW.restype = status
        pdh.PdhCollectQueryData.argtypes = [handle]
        pdh.PdhCollectQueryData.restype = status
        pdh.PdhGetFormattedCounterValue.argtypes = [
            handle, dword, ctypes.POINTER(dword), ctypes.POINTER(PDH_FMT_COUNTERVALUE_LARGE),
        ]
        pdh.PdhGetFormattedCounterValue.restype = status
        pdh.PdhCloseQuery.argtypes = [handle]
        pdh.PdhCloseQuery.restype = status

    def _open_token(self, access: int) -> ctypes.c_void_p:
        token = ctypes.c_void_p()
        ok = self._advapi32.OpenProcessToken(
            self._kernel32.GetCurrentProcess(), access, ctypes.byref(token)
        )
        if not ok:
            raise OSError(ctypes.get_last_error(), "OpenProcessToken failed")
        return token

    def is_elevated(self) -> bool:
        """Fails closed: any API failure reads as not elevated."""
        try:
            token = self._open_token(TOKEN_QUERY)
        except OSError:
            return False
        try:
            info = TOKEN_ELEVATION()
            returned = ctypes.c_uint32()
            ok = self._advapi32.GetTokenInformation(
                token, TOKEN_ELEVATION_CLASS, ctypes.byref(info), ctypes.sizeof(info),
                ctypes.byref(returned),
            )
            return bool(ok) and bool(info.TokenIsElevated)
        finally:
            self._kernel32.CloseHandle(token)

    @contextlib.contextmanager
    def quota_privilege(self) -> Iterator[None]:
        try:
            token = self._open_token(TOKEN_QUERY | TOKEN_ADJUST_PRIVILEGES)
        except OSError as exc:
            raise PrivilegeError(f"cannot open process token: {exc}") from exc
        try:
            luid = LUID()
            if not self._advapi32.LookupPrivilegeValueW(None, QUOTA_PRIVILEGE_NAME, ctypes.byref(luid)):
                raise PrivilegeError(
                    f"LookupPrivilegeValue failed with Win32 error {ctypes.get_last_error()}"
                )
            wanted = TOKEN_PRIVILEGES()
            wanted.PrivilegeCount = 1
            wanted.Privileges[0].Luid = luid
            wanted.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
            previous = TOKEN_PRIVILEGES()
            returned = ctypes.c_uint32()
            ctypes.set_last_error(0)
            ok = self._advapi32.AdjustTokenPrivileges(
                token, 0, ctypes.byref(wanted), ctypes.sizeof(previous), ctypes.byref(previous),
                ctypes.byref(returned),
            )
            error = ctypes.get_last_error()
            if not ok:
                raise PrivilegeError(f"AdjustTokenPrivileges failed with Win32 error {error}")
            if error == ERROR_NOT_ALL_ASSIGNED:
                raise PrivilegeError(
                    "SeIncreaseQuotaPrivilege is not held by this token (ERROR_NOT_ALL_ASSIGNED)"
                )
            try:
                yield
            finally:
                self._restore_privilege(token, previous)
        finally:
            self._kernel32.CloseHandle(token)

    def _restore_privilege(self, token: ctypes.c_void_p, previous: TOKEN_PRIVILEGES) -> None:
        """Put back the prior state; PrivilegeCount 0 means it was already enabled, so no change
        was made. Failure goes to stderr and never raises, so it cannot mask the chosen exit."""
        if previous.PrivilegeCount == 0:
            return
        returned = ctypes.c_uint32()
        ctypes.set_last_error(0)
        ok = self._advapi32.AdjustTokenPrivileges(
            token, 0, ctypes.byref(previous), 0, None, ctypes.byref(returned)
        )
        if not ok or ctypes.get_last_error() != 0:
            print(
                f"warning: could not restore SeIncreaseQuotaPrivilege "
                f"(Win32 error {ctypes.get_last_error()})",
                file=sys.stderr,
            )

    def read_memory(self) -> MemorySnapshot:
        return snapshot_from_values(read_pdh_counters(self._pdh))

    def read_limits(self) -> CacheLimits:
        minimum, maximum = ctypes.c_size_t(), ctypes.c_size_t()
        flags = ctypes.c_uint32()
        ctypes.set_last_error(0)
        ok = self._kernel32.GetSystemFileCacheSize(
            ctypes.byref(minimum), ctypes.byref(maximum), ctypes.byref(flags)
        )
        if not ok:
            raise CounterError(
                f"GetSystemFileCacheSize failed with Win32 error {ctypes.get_last_error()}"
            )
        return CacheLimits(minimum=minimum.value, maximum=maximum.value, flags=flags.value)

    def trim_working_set(self) -> None:
        ctypes.set_last_error(0)
        if not self._kernel32.SetSystemFileCacheSize(_SIZE_T_MAX, _SIZE_T_MAX, 0):
            raise TrimError(ctypes.get_last_error())
