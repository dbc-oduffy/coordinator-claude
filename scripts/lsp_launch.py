"""Wrapper for the coordinator plugin language servers (coordinator/.lsp.json).

`lsp_launch.py <name> -- <server argv...>` routes the session by machine-local keys (box scope,
never a git-tracked file): by default it bridges to the box's uni-server front (`lsp_front.py`,
ty and tsgo); `lsp.front_backend pooled` is the rollback, running the argv after `--` through
lsp_share's per-repo daemon; `lsp.front off` serves the resident stub.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import lsp_front_backends as fb  # noqa: E402
import lsp_share  # noqa: E402

LANE_KEY = "rag.lsp_lane"
ROUTE_OFF = "off"
ROUTE_POOLED = "pooled"
ROUTE_FRONT = "front"
MACHINE_LOCAL_TIMEOUT_S = 5

# (argv) -> (returncode, stdout); injectable so tests never read the real box settings.
Runner = Callable[[Sequence[str]], "tuple[int, str]"]


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _settings_home() -> Path:
    explicit = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"


def machine_local_path() -> Optional[Path]:
    """Absolute path of the settings-home machine-local launcher, or None when not installed."""
    bin_dir = _settings_home() / "bin"
    for name in ("machine-local.exe", "machine-local"):
        candidate = bin_dir / name
        if candidate.is_file():
            return candidate
    return None


def _default_runner(argv: Sequence[str]) -> "tuple[int, str]":
    exe = machine_local_path()
    if exe is None:
        return 127, ""
    try:
        # The extensionless launcher is a python script: Windows cannot exec it, so run it
        # under this interpreter everywhere rather than relying on its shebang.
        cmd = [str(exe)] if exe.suffix.lower() == ".exe" else [sys.executable, str(exe)]
        proc = subprocess.run(
            [*cmd, *argv],
            capture_output=True,
            text=True,
            timeout=MACHINE_LOCAL_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            creationflags=_no_console(),
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, proc.stdout


def resolve_route(runner: Optional[Runner] = None) -> str:
    """Where a session's language-server traffic goes: `off`, `pooled` or `front`.

    The front unless `lsp.front` reads `off` (the stub); `lsp.front_backend pooled` is the rollback to the
    pooled path. A failed key read is the documented default (front on, backend native).
    """
    run = runner or _default_runner
    if not fb.front_enabled(run):
        return ROUTE_OFF
    return ROUTE_POOLED if fb.front_backend(run) == "pooled" else ROUTE_FRONT


def repo_root_of(cwd: Optional[Path] = None) -> Path:
    """`git rev-parse --show-toplevel` from cwd, else cwd itself."""
    cwd = cwd or Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=MACHINE_LOCAL_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
            creationflags=_no_console(),
        )
    except (OSError, subprocess.SubprocessError):
        return cwd
    top = proc.stdout.strip()
    return Path(top) if proc.returncode == 0 and top else cwd


def share_runtime() -> Path:
    return _settings_home() / "runtime" / "lsp-share"


def front_runtime() -> Path:
    return _settings_home() / "runtime" / "lsp-front"


def _serve_front(name: str) -> int:
    """Proxy this client to the box's front; the resident stub when no front can be reached."""
    import lsp_front  # lazy: the stub and status paths never load the front

    try:
        code = lsp_front.connect(front_runtime())
    except OSError:
        code = None
    if code is not None:
        return code
    print(f"lsp_launch: front unavailable for {name}; serving the stub", file=sys.stderr)
    return serve_disabled(name, sys.stdin.buffer, sys.stdout.buffer)


def _serve(name: str, repo_root: Path, argv: "list[str]") -> int:
    """Proxy this client to the repo's shared server; run the server directly only if sharing fails."""
    try:
        shared = lsp_share.connect(name, repo_root, argv, share_runtime())
    except OSError:
        shared = None
    if shared is not None:
        return shared
    print(f"lsp_launch: share daemon unavailable for {name}; running unshared", file=sys.stderr)
    exe = shutil.which(argv[0]) or argv[0]
    if os.name == "posix":
        # Replace the wrapper so the host's kill reaches the server instead of orphaning it.
        try:
            os.chdir(repo_root)
            # guard-allow: no-bare-python-spawn posix-only exec replaces this process; no console window exists to suppress
            os.execv(exe, [exe, *argv[1:]])
        except OSError as exc:
            print(f"lsp_launch: cannot start {name}: {exc}", file=sys.stderr)
            return 1
    try:
        return subprocess.run(
            [exe, *argv[1:]], cwd=str(repo_root), creationflags=_no_console()
        ).returncode
    except OSError as exc:
        print(f"lsp_launch: cannot start {name}: {exc}", file=sys.stderr)
        return 1


def status(runner: Optional[Runner] = None) -> dict:
    """The front switch, the backend switch and the project-rag lane switch, each read on its own.

    Never starts a server. The lane value is project-rag's own box key; it is not derived from
    the front keys.
    """
    run = runner or _default_runner
    master = "on" if fb.front_enabled(run) else "off"
    backend = fb.front_backend(run)
    rc, out = run(["get", LANE_KEY])
    if rc == 0 and out.strip():
        lane = out.strip()
    else:
        lane = {"value": "unread", "reason": "key absent" if rc == 1 else f"machine-local exit {rc}"}
    return {
        "front": master,
        "front_backend": backend,
        "rag_lsp_lane": lane,
        "share_daemons": lsp_share.list_daemons(share_runtime()),
    }


def main(args: Optional[Sequence[str]] = None, runner: Optional[Runner] = None) -> int:
    args = list(sys.argv[1:] if args is None else args)
    if args and args[0] == "--status":
        report = status(runner)
        if "--json" in args[1:]:
            print(json.dumps(report))
        else:
            for key, value in report.items():
                print(f"{key}: {value}")
        return 0
    if "--" not in args or args.index("--") != 1 or len(args) < 3:
        print("usage: lsp_launch.py <name> -- <server argv...>", file=sys.stderr)
        return 2
    name, argv = args[0], args[2:]
    route = resolve_route(runner)
    if route == ROUTE_OFF:
        return serve_disabled(name, sys.stdin.buffer, sys.stdout.buffer)
    if route == ROUTE_POOLED:
        return _serve(name, repo_root_of(), argv)
    return _serve_front(name)


DISABLED_MESSAGE = (
    "language servers are off (machine-local lsp.front is off); "
    "use the project-rag symbol, SCIP and structural tools"
)


def _read_message(stream) -> Optional[dict]:
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1])
    if length is None:
        return None
    body = stream.read(length)
    return json.loads(body.decode("utf-8")) if len(body) == length else None


def _write_message(stream, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    stream.flush()


def serve_disabled(name: str, stdin, stdout) -> int:
    """Answer the host as a server with no capabilities until it says exit.

    Exiting at once leaves the host's pending LSP request hanging forever (measured on the host,
    see the plan's C2 host probe), so the off state is a resident stub that reads no files and
    starts nothing: initialize gets empty capabilities, every other request a clear error.
    """
    while True:
        msg = _read_message(stdin)
        if msg is None or msg.get("method") == "exit":
            return 0
        if "id" not in msg or "method" not in msg:
            continue
        if msg["method"] == "initialize":
            result: object = {"capabilities": {}, "serverInfo": {"name": f"{name} (off)"}}
            _write_message(stdout, {"jsonrpc": "2.0", "id": msg["id"], "result": result})
        elif msg["method"] == "shutdown":
            _write_message(stdout, {"jsonrpc": "2.0", "id": msg["id"], "result": None})
        else:
            _write_message(stdout, {"jsonrpc": "2.0", "id": msg["id"],
                                    "error": {"code": -32601, "message": DISABLED_MESSAGE}})


if __name__ == "__main__":
    sys.exit(main())
