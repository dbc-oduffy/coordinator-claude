"""PowerShell resolution for coordinator code that spawns PowerShell.

`resolve_pwsh()` prefers the MSI PowerShell 7 at %ProgramFiles%\\PowerShell\\7 over every other
shell: the Store/MSIX build (a WindowsApps alias) cannot run DISM cmdlets and codex sandboxes cannot
launch it. Stdlib only, so a cold or broken install can still import it.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

MSI_SUBDIR = ("PowerShell", "7")


def msi_pwsh_dir(env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """The MSI install directory under %ProgramFiles%, or None when ProgramFiles is unset."""
    env = os.environ if env is None else env
    base = env.get("ProgramFiles")
    return Path(base, *MSI_SUBDIR) if base else None


def msi_pwsh_path(env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """Path of the MSI pwsh.exe (it may not exist), or None when ProgramFiles is unset."""
    directory = msi_pwsh_dir(env)
    return directory / "pwsh.exe" if directory else None


def is_windowsapps_path(path: str) -> bool:
    """True for a Store/MSIX App Execution Alias location (any path segment named WindowsApps)."""
    return "windowsapps" in str(path).replace("/", "\\").lower().split("\\")


def split_path(value: str) -> list[str]:
    """PATH-style string to its non-empty entries."""
    return [entry for entry in value.split(os.pathsep) if entry.strip()]


def msi_ahead_of_windowsapps(entries: list[str], msi_dir: str, expand: Callable[[str], str] = os.path.expandvars) -> bool:
    """True when `msi_dir` is present in `entries` and no WindowsApps entry precedes it."""
    target = os.path.normcase(os.path.normpath(expand(msi_dir)))
    for entry in entries:
        expanded = expand(entry)
        if os.path.normcase(os.path.normpath(expanded)) == target:
            return True
        if is_windowsapps_path(expanded):
            return False
    return False


def prepend_entry(value: str, entry: str, expand: Callable[[str], str] = os.path.expandvars) -> str:
    """`value` with `entry` first; any existing equivalent entry is removed so a re-run is a no-op."""
    target = os.path.normcase(os.path.normpath(expand(entry)))
    kept = [e for e in split_path(value) if os.path.normcase(os.path.normpath(expand(e))) != target]
    return os.pathsep.join([entry, *kept])


def resolve_pwsh(
    env: Optional[Mapping[str, str]] = None,
    which: Callable[..., Optional[str]] = shutil.which,
    is_file: Callable[[str], bool] = os.path.isfile,
    platform: Optional[str] = None,
) -> Optional[str]:
    """MSI pwsh, else a non-WindowsApps pwsh on PATH, else powershell.exe; None when none exists.

    Off Windows only `pwsh` on PATH counts.
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        return which("pwsh")
    msi = msi_pwsh_path(env)
    if msi is not None and is_file(str(msi)):
        return str(msi)
    for entry in split_path(env.get("PATH", env.get("Path", ""))):
        candidate = os.path.join(entry, "pwsh.exe")
        if not is_windowsapps_path(entry) and is_file(candidate):
            return candidate
    return which("powershell.exe") or which("powershell")
