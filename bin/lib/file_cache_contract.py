"""Contract for the on-demand Windows file-cache trim tool.

Pure Python, importable on every OS: exit codes, Win32 flag constants, counter snapshots, errors,
and the FileCacheHost Protocol the Win32 adapter implements and the orchestration consumes.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

FILE_CACHE_MAX_HARD_ENABLE = 0x1
FILE_CACHE_MAX_HARD_DISABLE = 0x2
FILE_CACHE_MIN_HARD_ENABLE = 0x4
FILE_CACHE_MIN_HARD_DISABLE = 0x8


class ExitCode(IntEnum):
    """Process exit codes of trim-file-cache.py; each names one distinct outcome."""

    OK = 0
    USAGE = 2
    NOT_ELEVATED = 3
    PRIVILEGE_UNAVAILABLE = 4
    TRIM_FAILED = 5
    NOT_WINDOWS = 6
    COUNTERS_UNAVAILABLE = 7
    CAP_CHANGED = 8


@dataclass(frozen=True)
class MemorySnapshot:
    """Win32_PerfRawData_PerfOS_Memory readings, all in bytes.

    standby_bytes is StandbyCacheCoreBytes + StandbyCacheNormalPriorityBytes +
    StandbyCacheReserveBytes; modified_bytes is ModifiedPageListBytes.
    """

    cache_bytes: int
    available_bytes: int
    standby_bytes: int
    modified_bytes: int


@dataclass(frozen=True)
class CacheLimits:
    """GetSystemFileCacheSize result: minimum/maximum working-set bytes and the flags word."""

    minimum: int
    maximum: int
    flags: int

    @property
    def hard_max_enabled(self) -> bool:
        return bool(self.flags & FILE_CACHE_MAX_HARD_ENABLE)

    @property
    def hard_min_enabled(self) -> bool:
        return bool(self.flags & FILE_CACHE_MIN_HARD_ENABLE)


class PrivilegeError(Exception):
    """SeIncreaseQuotaPrivilege could not be enabled (including ERROR_NOT_ALL_ASSIGNED, 1300)."""


class CounterError(Exception):
    """The memory counters could not be read or parsed."""


class TrimError(Exception):
    """SetSystemFileCacheSize failed; winerror carries the Win32 error code."""

    def __init__(self, winerror: int) -> None:
        super().__init__(f"SetSystemFileCacheSize failed with Win32 error {winerror}")
        self.winerror = winerror


class FileCacheHost(Protocol):
    """The system surface the trim orchestration drives; fakeable in tests."""

    def is_elevated(self) -> bool:
        """May this process mutate the system cache? True only for an elevated token."""
        ...

    def quota_privilege(self) -> AbstractContextManager[None]:
        """Enable SeIncreaseQuotaPrivilege for the block, restoring the prior state on exit.

        Raises PrivilegeError on failure, including GetLastError() == 1300.
        """
        ...

    def read_memory(self) -> MemorySnapshot:
        """Read the memory counters; raises CounterError."""
        ...

    def read_limits(self) -> CacheLimits:
        """GetSystemFileCacheSize."""
        ...

    def trim_working_set(self) -> None:
        """SetSystemFileCacheSize((SIZE_T)-1, (SIZE_T)-1, 0); raises TrimError."""
        ...
