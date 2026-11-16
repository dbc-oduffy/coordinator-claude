#!/usr/bin/env python3
"""Forced command for the unimatrix FILE key on the receiving box: the ONLY thing that key can run.
It lands and returns drop dirs and nothing else; the message key's forced command (unimatrix-relay.py)
refuses put/get, and this one refuses every message mode.

authorized_keys line (restrict = no pty, no forwarding; key body elided; absolute interpreter and script
paths, `--peer` pinning the calling member's box). `unimatrix-install.py --install` prints the exact form:
  restrict,command="/usr/bin/python3 /home/me/.coordinator-claude-settings/unimatrix/unimatrix-file-relay.py --peer <box>" ssh-ed25519 <key-body> unimatrix

Modes, read from SSH_ORIGINAL_COMMAND:
  put <name>   read one uncompressed tar on stdin (first member MANIFEST.sha256, one "<sha256>  <relpath>"
               line per regular file) and land it, verified, at <settings_home>/unimatrix/drop/<peer>/<name>/;
               an existing name is refused. Prints one JSON line {ok, files, bytes, manifest_sha256}.
  get <name>   stream that drop dir back as the same tar on stdout; the JSON reply goes to stderr.
A peer reads only what it put; put/get without `--peer` are refused. Caps: MAX_DROP_BYTES / MAX_DROP_FILES
of unimatrix-relay.py.
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_RELAY = []


def relay():
    """The message relay beside this script (pack/unpack/caps), loaded by path on first use."""
    if not _RELAY:
        import importlib.util
        spec = importlib.util.spec_from_file_location("unimatrix_relay_for_file_relay", HERE / "unimatrix-relay.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _RELAY.append(mod)
    return _RELAY[0]


def parse_mode(original_command):
    """Map an SSH_ORIGINAL_COMMAND string to ("put"|"get", name), or None when it is not allowed."""
    cmd = (original_command or "").split()
    if (len(cmd) == 2 and cmd[0] in ("put", "get") and relay().valid_inbox_name(cmd[1])
            and original_command == f"{cmd[0]} {cmd[1]}"):
        return cmd[0], cmd[1]
    return None


def peer_arg(argv):
    """The box named by a `--peer <box>` argv pair, or None."""
    return argv[1] if len(argv) >= 2 and argv[0] == "--peer" else None


def file_line(key_body, box):
    """The restrict line for a member's file key with this copy's interpreter and path, quoted as the
    installer does; `--peer <box>` pins the calling member's drop dir into the forced command."""
    parts = [f'\\"{p}\\"' if " " in p else p for p in (sys.executable, str(Path(__file__).resolve()))]
    parts += ["--peer", box]
    return f'restrict,command="{" ".join(parts)}" ssh-ed25519 {key_body} unimatrix'


MAX_PEER_DROP_BYTES = 32 << 30  # bytes already held under one peer's drop dir; a put at or over it is refused peer_quota_full


def _tree_bytes(path):
    """Sum of regular-file sizes under `path`; 0 when it does not exist."""
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def file_leg(mode, name, peer, home, stdin=None, stdout=None, stderr=None):
    """`put <name>` / `get <name>` confined to <home>/unimatrix/drop/<peer>/<name>/; returns the exit code.

    put reads the tar from stdin and prints the JSON reply to stdout. get streams the tar to stdout and
    prints the JSON reply to stderr. A failed put leaves no partial drop."""
    r = relay()
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    stderr = stderr or sys.stderr
    root = tmp = None
    try:
        if peer is None or not r.valid_inbox_name(peer):
            raise r.DropError("no_peer")
        root = Path(home) / "unimatrix" / "drop" / peer / name
        if mode == "put":
            if _tree_bytes(root.parent) >= MAX_PEER_DROP_BYTES:
                raise r.DropError("peer_quota_full")
            claim = root.parent / f".tmp-{name}"
            claim.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.mkdir(claim)
            except FileExistsError:
                raise r.DropError("exists")
            tmp = claim
            if root.exists():
                raise r.DropError("exists")
            manifest = r.unpack(stdin, tmp)
            os.rename(tmp, root)
            tmp = None
            reply = r._drop_reply(root, manifest)
        else:
            r._need_filter()
            if not root.is_dir():
                raise r.DropError("not_found")
            reply = r._drop_reply(root, r.pack(root, stdout))
            stdout.flush()
    except r.DropError as ex:
        reply = {"ok": False, "reason": ex.args[0]}
    except OSError as ex:
        reply = {"ok": False, "reason": f"io_error:{type(ex).__name__}"}
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
    line = json.dumps(reply) + "\n"
    if mode == "put":
        stdout.write(line.encode("ascii"))
        stdout.flush()
    else:
        stderr.write(line)
        stderr.flush()
    return 0 if reply.get("ok") is True else 1


def main():
    parsed = parse_mode(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    if parsed is None:
        sys.exit("usage: put <name> | get <name>")
    mode, name = parsed
    sys.exit(file_leg(mode, name, peer_arg(sys.argv[1:]), relay().settings_home()))


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-file-relay [-h]\nfile-based unimatrix relay")
        raise SystemExit(0)
    main()
