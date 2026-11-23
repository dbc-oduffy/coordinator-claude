#!/usr/bin/env python3
"""Open ssh to a fleet box with the Unimatrix 01 key held in the UNIMATRIX_01_KEY user environment variable.

Usage:
  unimatrix-emergency.py <box> [remote command...]

The key is written to a user-only file in a fresh private temp directory, ssh runs with only that identity
(`-i <file> -o IdentitiesOnly=yes -o IdentityAgent=none`) against the box's `unimatrix-control-<box>` ssh alias, and
the file and directory are removed on every normal, error and KeyboardInterrupt exit (a SIGKILL or power loss leaves them in the user-only temp directory). The key never reaches argv, stdout, stderr or a log; ssh
inherits this process's stdio, so a call with no remote command opens an interactive shell. Exit: ssh's own status; 2 for a
refusal (unset variable, bad box, key not a private key, key file not restrictable) with no file left behind.
"""
import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENV_VAR = "UNIMATRIX_01_KEY"
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
ALIAS_PREFIX = "unimatrix-control-"
IS_WIN = sys.platform == "win32"


class Refusal(Exception):
    """A typed refusal; the message never carries key material."""


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0


def run_ssh(argv: list) -> int:
    """Run argv on this process's stdio; return its exit status (255 when it could not start)."""
    try:
        return subprocess.run(argv).returncode
    except OSError as exc:
        print(f"unimatrix-emergency: ssh could not run: {exc}", file=sys.stderr)
        return 255


def restrict_to_current_user(path) -> None:
    """Leave `path` readable by the current user alone; POSIX is mode 0600, Windows an ACL with inheritance removed."""
    if not IS_WIN:
        os.chmod(path, 0o600)
        return
    who = getpass.getuser()
    done = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{who}:(F)"],
                          capture_output=True, text=True, creationflags=_no_window())
    if done.returncode:
        raise Refusal("the key file could not be restricted to the current user")


def normalize_key(raw: str) -> str:
    """The key as ssh reads it: LF line ends, a trailing newline, and a literal `\\n` expanded when the value is one line.

    Raises Refusal when the value is not an OpenSSH/PEM private key block."""
    key = raw.strip().replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in key:
        key = key.replace("\\n", "\n")
    if "PRIVATE KEY" not in key.splitlines()[0]:
        raise Refusal(f"{ENV_VAR} does not hold a private key block")
    return key + "\n"


def write_key_file(key: str, restrict=restrict_to_current_user) -> tuple:
    """Write `key` to a new file inside a fresh private directory; return (directory, file).

    The file is restricted before the key is written. On any failure the directory is removed and the error propagates."""
    directory = Path(tempfile.mkdtemp(prefix="unimatrix-01-"))
    try:
        path = directory / "key"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        restrict(path)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(key)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return directory, path


def ssh_argv(box: str, key_file, command) -> list:
    """The ssh argv reaching `box` with only `key_file` as identity; `command` is the remote command words."""
    return ["ssh", "-i", str(key_file), "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
            "-o", "ConnectTimeout=10", f"{ALIAS_PREFIX}{box}", *command]


def emergency(box: str, command, env=None, runner=run_ssh, restrict=restrict_to_current_user) -> int:
    """Run ssh to `box` under the key in env[UNIMATRIX_01_KEY]; return ssh's exit status.

    Raises Refusal before any file exists when the box or variable is unusable."""
    if not TOKEN_RE.match(box):
        raise Refusal("invalid box")
    raw = (os.environ if env is None else env).get(ENV_VAR, "")
    if not raw.strip():
        raise Refusal(f"{ENV_VAR} is not set; set it as a user environment variable (see docs/reference/unimatrix-emergency-key.md)")
    key = normalize_key(raw)
    directory, path = write_key_file(key, restrict)
    try:
        return runner(ssh_argv(box, path, command))
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def main(argv=None, env=None, runner=run_ssh, restrict=restrict_to_current_user) -> int:
    ap = argparse.ArgumentParser(prog="unimatrix-emergency.py", description=f"ssh to a fleet box with the key in {ENV_VAR}.")
    ap.add_argument("box")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="remote command; none opens an interactive shell")
    args = ap.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return emergency(args.box, command, env, runner, restrict)
    except Refusal as exc:
        print(f"unimatrix-emergency: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"unimatrix-emergency: could not prepare the key file: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
