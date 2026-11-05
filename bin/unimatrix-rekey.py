"""Make each local unimatrix mirror look exactly like a session the harness wrote itself.

- Key file: <pid>.<sha256(socket path)>.key. On Windows the harness hashes the pipe
  path LOWERCASED; a mismatched name sends tokenless, which only works while the
  pid+procStart vouch also holds.
- procStart: the harness writes it as a string and compares it as one, so a number
  fails the live-owner check that idle notices require.
"""
import hashlib
import json
import os
import sys

SESS = "~/.claude/sessions"
# Registry field the mirror entries carry for the far session's real socket.
FAR_SOCKET_FIELD = "macSocketPath"


def rekey_name(pid, socket_path, platform=None):
    """Key file name the harness expects for a session with this socket path."""
    if (platform or sys.platform) == "win32":
        socket_path = socket_path.lower()
    return f"{pid}.{hashlib.sha256(socket_path.encode()).hexdigest()}.key"


def main():
    for f in os.listdir(os.path.expanduser(SESS)):
        if not f.endswith(".json"):
            continue
        path = os.path.join(os.path.expanduser(SESS), f)
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        if not d.get(FAR_SOCKET_FIELD):
            continue
        pid = d["pid"]
        if not isinstance(d.get("procStart"), str):
            d["procStart"] = str(d["procStart"])
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(d, fh, separators=(",", ":"))
            os.replace(tmp, path)
            print(d["name"], "procStart -> str")
        want = rekey_name(pid, d["messagingSocketPath"])
        for k in os.listdir(os.path.expanduser(SESS)):
            if k.startswith(f"{pid}.") and k.endswith(".key") and k != want:
                os.replace(os.path.join(os.path.expanduser(SESS), k), os.path.join(os.path.expanduser(SESS), want))
                print(d["name"], "->", want)


if __name__ == "__main__":
    main()
