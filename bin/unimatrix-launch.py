#!/usr/bin/env python3
"""Start or wake a claude-family session on a far box over its pinned control key.

Usage:
  unimatrix-launch.py <box> <repo-key>
  unimatrix-launch.py <box> --wake <session-name>

Runs `ssh -i ~/.ssh/unimatrix_control_<box> -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5
unimatrix-control-<box> <remote command>`; the far unimatrix-control.py replies one JSON line. With a far
invocation record (<settings_home>/unimatrix/control-far/<box>.json, written by unimatrix-install.py
--control-key) the remote command runs the far interpreter on the far script with the verb, which a
full-admin key needs; with no usable record it is the bare `launch <repo-key>` / `wake <name>` that a
forced-command key expects. On ok:true this prints the far session name and exits 0; on ok:false, an
unparseable reply, a timeout or an ssh failure it prints the error to stderr and exits 1.
"""
import argparse
import json
import ntpath
import os
import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path

TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SSH_TIMEOUT_SECONDS = 60
_SHELLS = ("cmd", "powershell", "posix")


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def run_ssh(argv):
    """Run argv; return (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=SSH_TIMEOUT_SECONDS,
                           creationflags=_no_window())
    except subprocess.TimeoutExpired:
        return 255, "", f"ssh timed out after {SSH_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return 255, "", f"ssh could not run: {exc}"
    return p.returncode, p.stdout, p.stderr


def parse_reply(stdout):
    """Return the last JSON-object line of stdout, or None."""
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _far_record(box):
    """Return the far invocation record for box, or None when absent, unreadable or malformed."""
    home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(Path.home() / ".coordinator-claude-settings")
    try:
        rec = json.loads((Path(home) / "unimatrix" / "control-far" / f"{box}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict):
        return None
    shell, platform = rec.get("shell"), rec.get("platform")
    interp, script = rec.get("interpreter"), rec.get("script")
    if shell not in _SHELLS or not all(isinstance(v, str) and v for v in (platform, interp, script)):
        return None
    isabs = ntpath.isabs if platform == "win32" else posixpath.isabs
    if not (isabs(interp) and isabs(script)):
        return None
    return rec


def _remote_command(rec, verb, arg):
    """Build the far command line: explicit interpreter+script when a record exists, else the bare verb."""
    if rec is None:
        return f"{verb} {arg}"
    interp, script, shell = rec["interpreter"], rec["script"], rec["shell"]
    if shell == "posix":
        return shlex.join([interp, script, verb, arg])
    cmd = f'"{interp}" "{script}" {verb} {arg}'
    return f"& {cmd}" if shell == "powershell" else cmd


def control(box, verb, arg, runner=run_ssh):
    """Send the verb over the box's control alias; return (ok, session_name_or_error)."""
    key = Path.home() / ".ssh" / f"unimatrix_control_{box}"
    rec = _far_record(box)
    argv = ["ssh", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5", f"unimatrix-control-{box}", _remote_command(rec, verb, arg)]
    hint = "" if rec else f"; run unimatrix-install.py --control-key {box} to record the far invocation"
    rc, out, err = runner(argv)
    reply = parse_reply(out)
    if reply is None:
        detail = (err or out or "").strip() or f"ssh exited {rc}"
        return False, f"no control reply: {detail}{hint}"
    if reply.get("ok") is True and reply.get("session_name"):
        return True, str(reply["session_name"])
    if reply.get("ok") is True:
        return False, "control reply carried no session_name"
    return False, f"{reply.get('error') or 'control refused'}{hint}"


def main(argv=None, runner=run_ssh):
    ap = argparse.ArgumentParser(prog="unimatrix-launch.py")
    ap.add_argument("box")
    ap.add_argument("repo_key", nargs="?")
    ap.add_argument("--wake", metavar="NAME")
    args = ap.parse_args(argv)
    if bool(args.wake) == bool(args.repo_key):
        ap.error("give exactly one of <repo-key> or --wake <session-name>")
    verb, arg = ("wake", args.wake) if args.wake else ("launch", args.repo_key)
    if not TOKEN_RE.match(args.box) or not TOKEN_RE.match(arg):
        print(f"unimatrix-launch: invalid box or {verb} argument", file=sys.stderr)
        return 2
    ok, value = control(args.box, verb, arg, runner)
    if ok:
        print(value)
        return 0
    print(value, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
