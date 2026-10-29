"""Register (or remove) the on-demand `BoxCacheTrim` Windows scheduled task.

Purpose: freeing the Windows file cache needs an ELEVATED trim. This installs the plugin's
`trim-system-cache.ps1` into `%ProgramData%\\BoxMemory\\` and registers a trigger-less,
highest-run-level task named `BoxCacheTrim` that runs it, so a non-elevated session starts the
elevated trim with `schtasks /Run /TN BoxCacheTrim` -- no prompt, once the operator has opted in.

Security: the task runs its action ELEVATED whenever fired, so whoever can write anything the
action touches can run code elevated. The action is therefore only the absolute machine-wide
PowerShell 7 (`%ProgramFiles%\\PowerShell\\7\\pwsh.exe`, MSI install, admin-only writable; install
refuses on a standard-user write grant) with fixed arguments naming the ProgramData script and log. `%ProgramData%\\BoxMemory`
is ACL'd to SYSTEM and Administrators full control, BUILTIN\\Users read-only, inheritance disabled
(the script inherits that); install reads the ACL back and refuses on mismatch, `--check` flags
any drift.

Negative-spec (RAG-bait):
    No trigger of any kind (no logon, boot, idle or time trigger) -- on-demand only. Never
    `/SC ONCE /SD <date>`: `/SD` is parsed in the host's locale date format. Never
    `sys.executable`, a plugin-root, settings-home or user-profile path, or a bare `powershell.exe`
    resolved via PATH in the task action. Never self-elevates: install/uninstall off an elevated
    shell print the elevated command and exit 3.

Exit codes: 0 installed / done, 1 absent or stale (target vanished), 2 not applicable
(not Windows), 3 elevation needed, 4 schtasks/icacls/copy failed or ACL readback mismatch,
5 installed but insecure (action or ACL drifted from the hardened shape).

Usage:
    python install-box-cache-trim-task.py [--install | --check | --uninstall]
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "BoxCacheTrim"
SCRIPT_NAME = "trim-system-cache.ps1"
LOG_NAME = "trim.log"
_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"

OK, ABSENT, NOT_APPLICABLE, NEEDS_ELEVATION, FAILED, INSECURE = 0, 1, 2, 3, 4, 5

_ADMIN_RIGHTS = frozenset({"OI", "CI", "F"})
_USERS_RIGHTS = frozenset({"OI", "CI", "RX"})
# Well-known SIDs. icacls prints the host-LOCALIZED account name (VORDEFINIERT\Administratoren on a
# German host), so names are resolved from these SIDs at runtime; the English text is the fallback.
_SYSTEM_SID, _ADMINS_SID, _USERS_SID = "S-1-5-18", "S-1-5-32-544", "S-1-5-32-545"
_EVERYONE_SID, _AUTH_USERS_SID = "S-1-1-0", "S-1-5-11"
_ENGLISH = {
    _SYSTEM_SID: "NT AUTHORITY\\SYSTEM",
    _ADMINS_SID: "BUILTIN\\Administrators",
    _USERS_SID: "BUILTIN\\Users",
    _EVERYONE_SID: "Everyone",
    _AUTH_USERS_SID: "NT AUTHORITY\\Authenticated Users",
}
_WRITE_RIGHTS = frozenset(
    {"F", "M", "W", "WD", "AD", "WA", "WEA", "DC", "DE", "GW", "GA", "WO", "WDAC"}
)
_ACE_RE = re.compile(r"([^\s:][^:\r\n]*?):((?:\([^)]*\))+)")


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """The single subprocess seam: every schtasks and icacls call goes through here."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _drive_root() -> Path:
    return Path(Path.home().anchor)


def _powershell_exe() -> Path:
    """Machine-wide PowerShell 7 (MSI): admin-only writable, and Microsoft Update keeps the path.

    Never the Store/MSIX pwsh: its alias lives in the user profile and its real folder name changes
    with every version. Never Windows PowerShell 5.1: it breaks when launched from a PowerShell 7
    shell (inherited PSModulePath).
    """
    root = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles")
    base = Path(root) if root else _drive_root() / "Program Files"
    return base / "PowerShell" / "7" / "pwsh.exe"


def _box_dir() -> Path:
    env = os.environ.get("ProgramData")
    return (Path(env) if env else _drive_root() / "ProgramData") / "BoxMemory"


def _box_script() -> Path:
    return _box_dir() / SCRIPT_NAME


def _box_log() -> Path:
    return _box_dir() / LOG_NAME


def _template_script() -> Path:
    return Path(__file__).resolve().with_name(SCRIPT_NAME)


def _action() -> tuple[str, str]:
    """(command, arguments) for the task: fixed, no user-writable path."""
    arguments = (
        "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "
        "\"& { (Get-Date).ToUniversalTime().ToString('o'); "
        f"& '{_box_script()}' }} *>> '{_box_log()}'\""
    )
    return str(_powershell_exe()), arguments


def _current_user() -> str:
    user = os.environ.get("USERNAME")
    if not user:
        import getpass

        user = getpass.getuser()
    domain = os.environ.get("USERDOMAIN")
    return f"{domain}\\{user}" if domain else user


def _task_xml(command: str, arguments: str, user: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>On-demand elevated file-cache trim (coordinator-claude). Fire with: schtasks /Run /TN {TASK_NAME}</Description>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _query_xml() -> str | None:
    """The registered task's XML, or None when no such task exists."""
    proc = _run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"])
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout


def _norm(p: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(p).strip().strip('"')))


def _under_box_dir(p: str) -> bool:
    box = _norm(_box_dir())
    n = _norm(p)
    return n == box or n.startswith(box + os.sep)


def _parse_action(xml_text: str) -> tuple[str, str] | str:
    """(command, arguments) of the registered Exec action, or an error description."""
    body = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_text.lstrip("﻿"))
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return "<unparseable task XML>"
    exe = root.find(f".//{_NS}Exec")
    if exe is None:
        return "<no Exec action>"
    command = (exe.findtext(f"{_NS}Command") or "").strip().strip('"')
    if not command:
        return "<empty command>"
    return command, exe.findtext(f"{_NS}Arguments") or ""


def _action_problems(command: str, arguments: str) -> list[str]:
    """Ways the registered action departs from the hardened shape (not about existence)."""
    problems = []
    if _norm(command) != _norm(_powershell_exe()):
        problems.append(f"action exe is not the machine-wide PowerShell 7: {command}")
    # The POSIX alternative exists only so the mocked suite can run off Windows; real tasks carry drive paths.
    paths = re.findall(r"(?:[A-Za-z]:\\|/)[^'\"\s]+", arguments)
    outside = [p for p in paths if not _under_box_dir(p)]
    if outside:
        problems.append(f"action argument path(s) outside {_box_dir()}: {', '.join(outside)}")
    if not any(_norm(p) == _norm(_box_script()) for p in paths):
        problems.append(f"action does not run {_box_script()}")
    if arguments != _action()[1]:
        problems.append("action arguments differ from the fixed hardened arguments")
    return problems


def _parse_aces(icacls_out: str, path: Path) -> dict[str, frozenset[str]]:
    """principal(lowercase) -> union of its rights/flags tokens, for non-DENY ACEs."""
    text = icacls_out.replace(str(path), "")
    aces: dict[str, set[str]] = {}
    for m in _ACE_RE.finditer(text):
        tokens = re.findall(r"\(([^)]*)\)", m.group(2))
        flat = {t for tok in tokens for t in tok.split(",")}
        if "DENY" in flat:
            continue
        aces.setdefault(m.group(1).strip().lower(), set()).update(flat)
    return {k: frozenset(v) for k, v in aces.items()}


def _icacls(path: Path) -> str | None:
    proc = _run(["icacls", str(path)])
    return proc.stdout if proc.returncode == 0 else None


def _users_writable(aces: dict[str, frozenset[str]]) -> list[str]:
    # Principals every standard user belongs to, localized and English; none may hold a write right.
    sids = (_USERS_SID, _EVERYONE_SID, _AUTH_USERS_SID)
    low = {n.lower() for sid in sids for n in (_account_name(sid), _ENGLISH[sid])}
    return [p for p, r in aces.items() if p in low and r & _WRITE_RIGHTS]


def _acl_problems(path: Path) -> list[str]:
    """Unreadable ACL or a standard-user write grant on `path`."""
    out = _icacls(path)
    if out is None:
        return [f"cannot read ACL of {path}"]
    writable = _users_writable(_parse_aces(out, path))
    return [f"{p} can write {path}" for p in writable]


def _dir_acl_exact(out: str) -> bool:
    aces = _parse_aces(out, _box_dir())
    return aces == {
        _account_name(_SYSTEM_SID).lower(): _ADMIN_RIGHTS,
        _account_name(_ADMINS_SID).lower(): _ADMIN_RIGHTS,
        _account_name(_USERS_SID).lower(): _USERS_RIGHTS,
    }


_REPARSE_POINT = 0x400


def _is_reparse(path: Path) -> bool:
    """True for a symlink or junction (any reparse point); `is_symlink` alone misses junctions."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & _REPARSE_POINT)


_NAME_CACHE: dict[str, str] = {}


def _account_name(sid_string: str) -> str:
    """The host's (possibly localized) `DOMAIN\\name` for a well-known SID, as icacls prints it."""
    if sid_string not in _NAME_CACHE:
        name = None
        try:
            from ctypes import wintypes

            advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            sid = ctypes.c_void_p()
            if advapi32.ConvertStringSidToSidW(ctypes.c_wchar_p(sid_string), ctypes.byref(sid)):
                try:
                    n, d = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
                    nl, dl, use = wintypes.DWORD(256), wintypes.DWORD(256), wintypes.DWORD()
                    if advapi32.LookupAccountSidW(
                        None, sid, n, ctypes.byref(nl), d, ctypes.byref(dl), ctypes.byref(use)
                    ):
                        name = f"{d.value}\\{n.value}" if d.value else n.value
                finally:
                    kernel32.LocalFree(sid)
        except (AttributeError, OSError):
            name = None
        _NAME_CACHE[sid_string] = name or _ENGLISH[sid_string]
    return _NAME_CACHE[sid_string]


def _owner_sid(path: Path) -> str | None:
    """The owner of `path` as a SID string such as `S-1-5-32-544`, or None when unreadable.

    Read through the Win32 API, never a PowerShell child: Windows PowerShell 5.1 launched from
    PowerShell 7 inherits a PSModulePath it cannot load Get-Acl from, and the owner read back empty.
    A SID, never a name: account names are localized on non-English hosts.
    """
    try:
        advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    except AttributeError:
        return None
    from ctypes import wintypes

    se_file_object, owner_security_information = 1, 1
    sid, sd = ctypes.c_void_p(), ctypes.c_void_p()
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    rc = advapi32.GetNamedSecurityInfoW(
        ctypes.c_wchar_p(str(path)), se_file_object, owner_security_information,
        ctypes.byref(sid), None, None, None, ctypes.byref(sd),
    )
    if rc != 0:
        return None
    try:
        text = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            return None
        try:
            return text.value
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.LocalFree(sd)


def _elevated_hint(flag: str) -> str:
    me = Path(__file__).resolve()
    return f'python "{me}"{flag}'


def check() -> int:
    xml_text = _query_xml()
    if xml_text is None:
        print(f"ABSENT: task {TASK_NAME} is not registered")
        return ABSENT
    parsed = _parse_action(xml_text)
    if isinstance(parsed, str):
        print(f"STALE: task {TASK_NAME} has {parsed}")
        return ABSENT
    command, arguments = parsed
    problems = _action_problems(command, arguments)
    if problems:
        print(f"INSECURE: task {TASK_NAME}: " + "; ".join(problems))
        return INSECURE
    missing = [p for p in (_powershell_exe(), _box_script()) if not p.is_file()]
    if missing:
        print(f"STALE: task {TASK_NAME} targets missing path(s): {', '.join(map(str, missing))}")
        return ABSENT
    acl = _acl_problems(_box_dir()) + _acl_problems(_box_script())
    if acl:
        print(f"INSECURE: task {TASK_NAME}: " + "; ".join(acl))
        return INSECURE
    print(f"installed: task {TASK_NAME}")
    return OK


def _harden_and_copy() -> str | None:
    """Create BoxMemory, lock its ACL, copy the script in; an error message or None."""
    box, script = _box_dir(), _box_script()
    template = _template_script()
    if not template.is_file():
        return f"trim script template missing: {template}"
    pwsh = _powershell_exe()
    if not pwsh.is_file():
        return (
            f"machine-wide PowerShell 7 not found at {pwsh}; install it elevated with: winget install "
            "--id Microsoft.PowerShell --source winget --scope machine --installer-type wix"
        )
    # The elevated action runs this exe; a standard-user write grant on it or its folder is an EoP.
    problems = _acl_problems(pwsh.parent) + _acl_problems(pwsh)
    if problems:
        return "; ".join(problems)
    for p in (box, script):
        if _is_reparse(p):
            return f"{p} is a symlink or junction (reparse point); remove it and re-run"
    box.mkdir(parents=True, exist_ok=True)
    if _is_reparse(box):
        return f"{box} is a symlink or junction (reparse point); remove it and re-run"
    # icacls rejects /setowner combined with any other operation (exit 87), so it is its own call.
    for icacls_args in (
        ["/setowner", "*S-1-5-32-544"],
        [
            "/inheritance:r",
            "/grant:r",
            "*S-1-5-18:(OI)(CI)(F)",
            "*S-1-5-32-544:(OI)(CI)(F)",
            "*S-1-5-32-545:(OI)(CI)(RX)",
        ],
    ):
        proc = _run(["icacls", str(box), *icacls_args])
        if proc.returncode != 0:
            return f"icacls failed: {(proc.stderr or proc.stdout).strip()}"
    owner = _owner_sid(box)
    if owner != _ADMINS_SID:
        return f"owner of {box} reads back as {owner!r}, not Administrators ({_ADMINS_SID})"
    out = _icacls(box)
    if out is None or not _dir_acl_exact(out):
        return f"ACL readback of {box} does not match SYSTEM/Administrators full, Users read-only"
    # A pre-planted script keeps its own ACL and owner; recreate so it inherits the locked dir's.
    script.unlink(missing_ok=True)
    shutil.copyfile(template, script)
    if _is_reparse(script):
        return f"{script} is a symlink or junction (reparse point)"
    problems = _acl_problems(script)
    if problems:
        return "; ".join(problems)
    return None


def _rotate_ps51_log() -> None:
    """Rename a UTF-16LE (BOM) trim.log written by PowerShell 5.1 redirection to trim-ps51.log."""
    log = _box_log()
    try:
        with open(log, "rb") as fh:
            head = fh.read(2)
        if head == b"\xff\xfe":
            os.replace(log, log.with_name("trim-ps51.log"))
    except OSError:
        pass


def install() -> int:
    if not _is_admin():
        print(
            f"Installing {TASK_NAME} needs an ELEVATED shell. Re-run from an Administrator "
            f"terminal:\n  {_elevated_hint(' --install')}",
            file=sys.stderr,
        )
        return NEEDS_ELEVATION
    try:
        error = _harden_and_copy()
    except OSError as exc:
        error = str(exc)
    if error:
        print(f"refusing to register {TASK_NAME}: {error}", file=sys.stderr)
        return FAILED
    _rotate_ps51_log()
    command, arguments = _action()
    xml = _task_xml(command, arguments, _current_user())
    # The XML is staged inside the locked BoxMemory dir, never a user-writable temp dir.
    fd, tmp = tempfile.mkstemp(suffix=".xml", prefix="BoxCacheTrim-", dir=_box_dir())
    try:
        with os.fdopen(fd, "w", encoding="utf-16", newline="") as fh:
            fh.write(xml)
        proc = _run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", tmp, "/F"])
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if proc.returncode != 0:
        print(f"schtasks /Create failed: {(proc.stderr or proc.stdout).strip()}", file=sys.stderr)
        return FAILED
    print(f"installed: task {TASK_NAME} -> {command} {arguments}")
    print(f"Fire it with:  schtasks /Run /TN {TASK_NAME}")
    return OK


def uninstall() -> int:
    task_present = _query_xml() is not None
    box = _box_dir()
    if not task_present and not box.exists():
        print(f"no change needed: task {TASK_NAME} is not registered")
        return OK
    if not _is_admin():
        print(
            f"Removing {TASK_NAME} needs an ELEVATED shell. Re-run from an Administrator "
            f"terminal:\n  {_elevated_hint(' --uninstall')}",
            file=sys.stderr,
        )
        return NEEDS_ELEVATION
    if task_present:
        proc = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        if proc.returncode != 0:
            print(
                f"schtasks /Delete failed: {(proc.stderr or proc.stdout).strip()}", file=sys.stderr
            )
            return FAILED
        print(f"removed: task {TASK_NAME}")
    if box.exists():
        if _is_reparse(box):
            print(f"refusing to remove {box}: it is a link", file=sys.stderr)
            return FAILED
        try:
            shutil.rmtree(box)
        except OSError as exc:
            print(f"could not remove {box}: {exc}", file=sys.stderr)
            return FAILED
        print(f"removed: {box}")
    return OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="report whether the task is installed with the hardened action and ACLs; change "
        "nothing. Exit 0 installed, 1 absent or stale, 2 not Windows, 5 insecure.",
    )
    group.add_argument(
        "--install",
        action="store_true",
        help="install the task (the default when no flag is given)",
    )
    group.add_argument(
        "--uninstall",
        action="store_true",
        help="delete the task and the BoxMemory dir (no-op when absent)",
    )
    args = ap.parse_args(argv)

    if not _is_windows():
        print(f"not applicable: {TASK_NAME} is a Windows scheduled task", file=sys.stderr)
        return NOT_APPLICABLE
    if args.check:
        return check()
    if args.uninstall:
        return uninstall()
    return install()


if __name__ == "__main__":
    sys.exit(main())
