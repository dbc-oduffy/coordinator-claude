"""Link the group-em home and ~/.claude into the user's repos folder, per OS.

Windows writes a `.lnk` shortcut, macOS a Finder alias, Linux a symlink. Paths reach the
PowerShell/osascript children as environment values or argv, never as script text. An existing
entry is never overwritten or retargeted. Every failure is returned as a status dict, not raised.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import _gem_home
import _general_work
from _win_portability import no_console_spawn_kwargs

SPAWN_TIMEOUT_S = 30

_WIN_CREATE = (
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:HL_LINK);"
    "$s.TargetPath=$env:HL_TARGET;$s.Save()"
)
_WIN_READ = "(New-Object -ComObject WScript.Shell).CreateShortcut($env:HL_LINK).TargetPath"

_MAC_CREATE = (
    "on run argv",
    "set t to (POSIX file (item 1 of argv)) as alias",
    "set f to (POSIX file (item 2 of argv)) as alias",
    'tell application "Finder"',
    "set a to make new alias file at f to t",
    "set name of a to (item 3 of argv)",
    "end tell",
    "end run",
)
_MAC_READ = (
    "on run argv",
    "set a to (POSIX file (item 1 of argv)) as alias",
    'tell application "Finder"',
    'if kind of a is not "Alias" then error "not an alias"',
    "return POSIX path of ((original item of a) as alias)",
    "end tell",
    "end run",
)


def _platform() -> str:
    """`win32`, `darwin` or the POSIX `sys.platform`; the seam tests monkeypatch."""
    return sys.platform


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(str(p))).rstrip("\\/")


def _same(a, b) -> bool:
    if _norm(a) == _norm(b):
        return True
    try:
        return _norm(os.path.realpath(a)) == _norm(os.path.realpath(b))
    except OSError:
        return False


def _run(argv: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.update(env or {})
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=SPAWN_TIMEOUT_S,
        env=full_env,
        **no_console_spawn_kwargs(),
    )


def _powershell(script: str, env: dict) -> subprocess.CompletedProcess:
    return _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env)


def _osascript(lines: tuple[str, ...], *args: str) -> subprocess.CompletedProcess:
    argv = ["osascript"]
    for line in lines:
        argv += ["-e", line]
    return _run(argv + list(args))


def repos_folder() -> Path:
    """The folder the user keeps their repos in: `_general_work.workspace_dir()`, nothing else."""
    return _general_work.workspace_dir()


def _result(status: str, path: Path, detail: str = "") -> dict:
    return {"status": status, "path": str(path), "detail": detail}


def _existing_target(plat: str, entry: Path) -> str | None:
    """The target an existing link entry points at, or None when it is not a link of this OS."""
    if plat == "win32":
        if entry.suffix.lower() != ".lnk" or not entry.is_file():
            return None
        cp = _powershell(_WIN_READ, {"HL_LINK": str(entry)})
        out = (cp.stdout or "").strip()
        return out if cp.returncode == 0 and out else None
    if entry.is_symlink():
        return os.readlink(entry)
    if plat == "darwin" and entry.is_file():
        cp = _osascript(_MAC_READ, str(entry))
        out = (cp.stdout or "").strip()
        return out if cp.returncode == 0 and out else None
    return None


def ensure_link(target: Path, folder: Path, name: str) -> dict:
    """Make `<folder>/<name>` (`.lnk` on Windows) a link to `target`, idempotently.

    Returns {status, path, detail}; status is one of created, present, refused-not-a-link,
    refused-points-elsewhere, skipped-no-target, unsupported, failed. Never raises, never
    overwrites or retargets an existing entry.
    """
    target, folder = Path(target), Path(folder)
    plat = _platform()
    if plat == "win32":
        entry = folder / f"{name}.lnk"
    elif plat == "darwin" or plat.startswith("linux") or plat in ("freebsd", "cygwin"):
        entry = folder / name
    else:
        return _result("unsupported", folder / name, f"platform {plat}")
    try:
        if not target.exists():
            return _result("skipped-no-target", entry, f"{target} does not exist")
        if not folder.is_dir():
            return _result("failed", entry, f"repos folder {folder} is not a directory")
        if os.path.lexists(entry):
            current = _existing_target(plat, entry)
            if current is None:
                return _result("refused-not-a-link", entry, "an existing entry is not a link")
            if _same(current, target):
                return _result("present", entry)
            return _result("refused-points-elsewhere", entry, f"points at {current}, wanted {target}")
        if plat == "win32":
            cp = _powershell(_WIN_CREATE, {"HL_LINK": str(entry), "HL_TARGET": str(target)})
        elif plat == "darwin":
            cp = _osascript(_MAC_CREATE, str(target), str(folder), name)
        else:
            os.symlink(target, entry, target_is_directory=True)
            return _result("created", entry)
        if cp.returncode != 0:
            return _result("failed", entry, (cp.stderr or cp.stdout or "").strip()[:300])
        if plat == "win32" and not entry.is_file():
            return _result("failed", entry, "shortcut was not written")
        return _result("created", entry)
    except (OSError, subprocess.SubprocessError) as exc:
        return _result("failed", entry, f"{type(exc).__name__}: {exc}")


def ensure_home_links() -> list[dict]:
    """Link `group-em` and `dot-claude` into the repos folder; one result dict per link."""
    folder = repos_folder()
    results = []
    try:
        gem = _gem_home.resolve_home()
    except _gem_home.HomeRefused as exc:
        results.append({**_result("failed", folder / "group-em", f"HomeRefused: {exc}"), "name": "group-em"})
    else:
        results.append({**ensure_link(gem, folder, "group-em"), "name": "group-em"})
    results.append({**ensure_link(Path.home() / ".claude", folder, "dot-claude"), "name": "dot-claude"})
    return results
