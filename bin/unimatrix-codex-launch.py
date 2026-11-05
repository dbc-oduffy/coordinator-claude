"""Optional: start Codex attached to the app-server daemon with --remote.

Using this launcher is NOT required for peer delivery. A plain `codex` TUI started without
--remote and without a peers.json entry is reached by the router through the queue route; this
launcher only adds live injection through the daemon's control socket (unimatrix-peer-codex.py),
which an attached TUI renders. If the daemon cannot start, codex is launched plain.
Usage: unimatrix-codex-launch.py [codex args...]   (--help prints this text)

Socket: $CODEX_APP_SERVER_SOCK, else the Codex default. A default socket is brought up with
`codex app-server daemon start`; an overridden one with a detached `codex app-server --listen
unix://<sock>`. Registration happens in the SessionStart hook, not here.
"""
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
READY_SECONDS = 20


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def daemon_live(sock):
    """True when something accepts connections on the unix socket."""
    if not hasattr(socket, "AF_UNIX") or not os.path.exists(sock):
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(sock)
        return True
    except OSError:
        return False
    finally:
        s.close()


def daemon_argv(codex, sock, default_sock):
    """argv that brings the daemon up on `sock`, and whether it must be detached."""
    if sock == default_sock:
        return [codex, "app-server", "daemon", "start"], False
    return [codex, "app-server", "--listen", f"unix://{sock}"], True


def ensure_daemon(codex, sock, default_sock, run=subprocess.run, popen=subprocess.Popen,
                  live=daemon_live, sleep=time.sleep, ready_seconds=READY_SECONDS):
    """Start the daemon when none is live; raise RuntimeError if it is not accepting in time."""
    if live(sock):
        return False
    argv, detach = daemon_argv(codex, sock, default_sock)
    if detach:
        popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True)
    else:
        done = run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"{' '.join(argv)} failed: {(done.stderr or done.stdout or '').strip()}")
    deadline = time.monotonic() + ready_seconds
    while time.monotonic() < deadline:
        if live(sock):
            return True
        sleep(0.25)
    raise RuntimeError(f"app-server not accepting on {sock} after {ready_seconds}s")


def tui_argv(codex, sock, args):
    """The attached-TUI command line: --remote unix://<sock> then the caller's args."""
    return [codex, "--remote", f"unix://{sock}", *args]


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):
        print(__doc__)
        return 0
    codex = shutil.which("codex")
    if not codex:
        print("unimatrix-codex-launch: codex is not on PATH", file=sys.stderr)
        return 127
    if os.name == "nt":
        print("unimatrix-codex-launch: unix-socket attach is unavailable on Windows; "
              "starting codex without --remote", file=sys.stderr)
        return subprocess.call([codex, *args])
    pc = load_sibling("unimatrix-peer-codex")
    sock = pc.socket_path()
    default_sock = os.path.expanduser(pc.DEFAULT_SOCK)
    try:
        ensure_daemon(codex, sock, default_sock)
    except (RuntimeError, OSError) as exc:
        print(f"unimatrix-codex-launch: {exc}; starting codex without --remote "
              "(peer messages still arrive through the queue)", file=sys.stderr)
        cmd = [codex, *args]
    else:
        cmd = tui_argv(codex, sock, args)
    os.execv(cmd[0], cmd)


if __name__ == "__main__":
    sys.exit(main())
