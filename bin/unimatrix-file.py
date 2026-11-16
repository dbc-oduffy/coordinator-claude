#!/usr/bin/env python3
"""Move a file or folder to or from a fleet peer's per-peer drop dir over this box's own file key.

Usage:
  unimatrix-file.py put <peer> <path> [--name <name>] [--key <path>]
  unimatrix-file.py get <peer> <name> [--dest <dir>] [--key <path>]

The file key is <settings home>/.secrets/ssh/unimatrix-file (or --key); the relay key is never used. A
missing file key exits 2 naming the path; messaging is unaffected.

<peer> is a box of the held membership snapshot. put lands <path> at <name> (default: its basename)
in the peer's drop dir for this box; get returns what this box put there. Both sides verify the
sha256 manifest; any mismatch exits 1. An unknown peer exits 2 and names the known boxes.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _sibling(filename, modname):
    spec = importlib.util.spec_from_file_location(modname, HERE / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


FILE_KEY_NAME = "unimatrix-file"


def file_key_path(roster):
    """This box's file-transfer private key path; never the relay key."""
    return roster.settings_home() / ".secrets" / "ssh" / FILE_KEY_NAME


def resolve_peer(peer, members):
    """`user@host` of the member whose box is `peer`; None when no member matches."""
    for m in members:
        if m["box"] == peer:
            return f"{m['user']}@{m['host']}"
    return None


def ssh_argv(key, target, command):
    return ["ssh", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
            target, command]


def default_popen(argv):
    return subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_no_window())


def _reply(raw):
    """The last JSON object line in `raw` (bytes or str), else None; ssh may print warnings around it."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
    return None


def _fail(err, reply, raw_err=b""):
    reason = (reply or {}).get("reason") or "no_reply"
    print(f"unimatrix-file: {reason}", file=err)
    tail = (raw_err.decode("utf-8", "replace") if isinstance(raw_err, bytes) else raw_err).strip()
    if tail and not reply:
        print(tail.splitlines()[-1][:200], file=err)
    return 1


def over_cap(relay, src):
    """The relay's refusal reason ("too_large" / "too_many_files") when `src` would exceed a put cap, else None.
    Walks what pack would send (same skip rules); members count files and dirs."""
    total = count = 0
    for kind, _rel, path in relay.iter_tree(src):
        count += 1
        if kind == "file":
            total += path.stat().st_size
        if count > relay.MAX_DROP_FILES:
            return "too_many_files"
        if total > relay.MAX_DROP_BYTES:
            return "too_large"
    return None


def put(relay, popen, argv_ssh, src, out, err):
    """Pack `src` into one ssh child's stdin and read the relay's JSON reply; returns the exit code."""
    proc = popen(argv_ssh)
    manifest = None
    try:
        manifest = relay.pack(src, proc.stdin)
        proc.stdin.close()
    except (OSError, ValueError):
        pass  # the relay refused early or ssh died: its reply or exit code says why
    raw_out = proc.stdout.read()
    raw_err = proc.stderr.read() if proc.stderr else b""
    proc.wait()
    reply = _reply(raw_out)
    if not reply or reply.get("ok") is not True or manifest is None:
        return _fail(err, reply, raw_err)
    want = hashlib.sha256(relay.manifest_bytes(manifest)).hexdigest()
    if reply.get("manifest_sha256") != want or reply.get("files") != len(manifest):
        print("unimatrix-file: manifest_mismatch", file=err)
        return 1
    print(json.dumps(reply), file=out)
    return 0


def get(relay, popen, argv_ssh, dest, out, err):
    """Stream the relay's tar into a temp dir beside `dest`, verify it, then rename it to `dest`."""
    dest = Path(dest)
    if dest.exists():
        print(f"unimatrix-file: destination exists: {dest}", file=err)
        return 1
    tmp = dest.parent / f".{dest.name}.part-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    proc = popen(argv_ssh)
    try:
        proc.stdin.close()
    except OSError:
        pass
    manifest = problem = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        manifest = relay.unpack(proc.stdout, tmp)
    except relay.DropError as ex:
        problem = ex.args[0]
    except OSError as ex:
        problem = f"io_error:{type(ex).__name__}"
    try:
        while proc.stdout.read(1 << 16):  # a relay blocked on a full stdout pipe never reaches stderr
            pass
    except OSError:
        pass
    raw_err = proc.stderr.read() if proc.stderr else b""
    proc.wait()
    reply = _reply(raw_err)
    if problem is None and (not reply or reply.get("ok") is not True):
        problem = (reply or {}).get("reason") or "no_reply"
    if problem is None:
        want = hashlib.sha256(relay.manifest_bytes(manifest)).hexdigest()
        if reply.get("manifest_sha256") != want or reply.get("files") != len(manifest):
            problem = "manifest_mismatch"
    if problem is not None:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"unimatrix-file: {problem}", file=err)
        return 1
    (tmp / relay.MANIFEST).unlink(missing_ok=True)
    os.replace(tmp, dest)
    print(json.dumps({**reply, "dest": str(dest)}), file=out)
    return 0


def main(argv=None, popen=None, members=None, key=None, out=None, err=None):
    out, err = out or sys.stdout, err or sys.stderr
    p = argparse.ArgumentParser(prog="unimatrix-file.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="verb", required=True)
    pp = sub.add_parser("put")
    pp.add_argument("peer")
    pp.add_argument("path")
    pp.add_argument("--name")
    pg = sub.add_parser("get")
    pg.add_argument("peer")
    pg.add_argument("name")
    pg.add_argument("--dest")
    for sp in (pp, pg):
        sp.add_argument("--key")
    a = p.parse_args(argv)
    relay = _sibling("unimatrix-relay.py", "unimatrix_relay_file")
    roster = _sibling("unimatrix-roster.py", "unimatrix_roster_file")
    if members is None:
        mem = _sibling("unimatrix-membership.py", "unimatrix_membership_file")
        try:
            members = mem.verified_members(roster.settings_home())
        except mem.MembershipError as ex:
            print(f"unimatrix-file: membership unusable: {ex}", file=err)
            return 2
    target = resolve_peer(a.peer, members)
    if target is None:
        known = ", ".join(sorted(m["box"] for m in members)) or "none"
        print(f"unimatrix-file: unknown peer {a.peer!r}; known boxes: {known}", file=err)
        return 2
    name = a.name if a.verb == "get" else (a.name or Path(a.path).resolve().name)
    if not relay.valid_inbox_name(name):
        print(f"unimatrix-file: invalid drop name {name!r}", file=err)
        return 2
    key = Path(a.key or key or file_key_path(roster))
    if not key.is_file():
        print(f"unimatrix-file: file_key_missing: file key missing: {key}; mint it with `unimatrix-install.py --file-key` "
              f"(the relay key is not used for file transfer)", file=err)
        return 2
    try:
        verdict = _sibling("unimatrix-passphrase.py", "unimatrix_passphrase_file").ensure_agent(key)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        verdict = "loaded"
    if verdict == "locked":
        print(f"unimatrix-file: waiting: 1Password locked; unlock it and retry ({key} is passphrase-encrypted)",
              file=err)
        return 3
    if verdict == "missing":
        print(f"unimatrix-file: passphrase_source_missing: op CLI or unimatrix.passphrase_vault unavailable; "
              f"{key} is passphrase-encrypted", file=err)
        return 2
    argv_ssh = ssh_argv(key, target, f"{a.verb} {name}")
    popen = popen or default_popen
    if a.verb == "put":
        src = Path(a.path)
        if not src.exists():
            print(f"unimatrix-file: no such path: {src}", file=err)
            return 2
        reason = over_cap(relay, src)
        if reason:
            print(f"unimatrix-file: {reason}", file=err)
            return 1
        return put(relay, popen, argv_ssh, src, out, err)
    return get(relay, popen, argv_ssh, a.dest or Path.cwd() / name, out, err)


if __name__ == "__main__":
    sys.exit(main())
