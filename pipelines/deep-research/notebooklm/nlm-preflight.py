"""NotebookLM preflight: a real `nlm notebook list` call plus the user-scope MCP registration.

Prints one JSON object {ok, remedy, checks} and always exits 0; the calling stage reads `ok`.
Never use `nlm login --check`: it passes on expired auth.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

UPSTREAM_REMEDY = (
    "install and register per https://github.com/jacob-bd/gemini-notebook-mcp-cli "
    "(its README: uv, uvx, pipx or pip, no venv required)"
)
LOGIN_REMEDY = "! nlm login --force"
RENAME_REMEDY = "! nlm setup add claude-code"
RESTART_REMEDY = "restart Claude Code"
GOOD_KEY = "gemini-notebook-mcp"
STALE_KEY = "notebooklm-mcp"
AUTH_PATTERN = re.compile(
    r"\b(?:(?:session|token|credentials?|cookies?)\s+(?:has\s+|have\s+)?expired"
    r"|authentication\s+(?:required|failed|error)"
    r"|not\s+(?:logged\s+in|authenticated)"
    r"|please\s+log\s*in"
    r"|unauthori[sz]ed"
    r"|invalid\s+credentials?)\b",
    re.I,
)
TIMEOUT_S = 45
PROBE_TIMEOUT_S = 10
START_REMEDY = (
    "the registered gemini-notebook-mcp command fails to start (its interpreter lost a dependency): "
    "reinstall notebooklm-mcp-cli into an isolated interpreter no other install shares, "
    "per coordinator install step 1d (no venv; never a pyenv or project interpreter), "
    "then re-register it with `! nlm setup add claude-code`"
)

# runner(argv) -> (returncode, combined_output); raises TimeoutError on timeout.
Runner = Callable[[list[str]], tuple[int, str]]
# probe(argv, env_overrides) -> (returncode, combined_output); raises TimeoutError when still running.
Probe = Callable[[list[str], dict[str, str]], tuple[int, str]]


def subprocess_runner(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(str(exc)) from exc
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def read_user_mcp_keys(config_path: Path) -> set[str] | None:
    """Keys of top-level mcpServers in the user-scope config; None when unreadable."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return set(servers) if isinstance(servers, dict) else set()


def read_user_mcp_servers(config_path: Path) -> dict:
    """Top-level mcpServers entries of the user-scope config; {} when unreadable."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else {}


def subprocess_probe(argv: list[str], env: dict[str, str]) -> tuple[int, str]:
    """Start the registered server with stdin at EOF; a healthy stdio server idles until the
    timeout (TimeoutError) or exits 0, a broken one dies at import with a traceback."""
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            env={**os.environ, **env},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(str(exc)) from exc
    except OSError as exc:
        return 127, f"cannot execute {argv[0]}: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def probe_registered_server(
    entry: dict, which: Callable[[str], str | None], probe: Probe
) -> tuple[bool, str]:
    """(started, detail) for the registered gemini-notebook-mcp command; never reads project-rag."""
    command = entry.get("command") if isinstance(entry, dict) else None
    if not isinstance(command, str) or not command:
        return False, "registration has no command"
    resolved = command if Path(command).is_absolute() else which(command)
    if not resolved:
        return False, f"command not found: {command}"
    args = [str(a) for a in entry.get("args") or []]
    env = {str(k): str(v) for k, v in (entry.get("env") or {}).items()}
    try:
        code, out = probe([resolved, *args], env)
    except TimeoutError:
        return True, "running"
    if code == 0:
        return True, "exited cleanly"
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    return False, f"exit {code}: {lines[-1] if lines else 'no output'}"[:300]


def registered_nlm(entry: dict | None) -> str | None:
    """The nlm installed beside the registered server's absolute command, if any."""
    command = entry.get("command") if isinstance(entry, dict) else None
    if not isinstance(command, str) or not Path(command).is_absolute():
        return None
    for name in ("nlm", "nlm.exe"):
        sibling = Path(command).parent / name
        if sibling.is_file():
            return str(sibling)
    return None


def classify(
    runner: Runner,
    which: Callable[[str], str | None],
    mcp_keys: set[str] | None,
    servers: dict | None = None,
    probe: Probe | None = None,
) -> dict:
    remedy: list[str] = []
    checks: dict = {}

    # The registered server's own nlm, not PATH's: a stale nlm earlier on PATH (an old
    # pyenv install) can be broken while the registered one is healthy.
    own_nlm = registered_nlm((servers or {}).get(GOOD_KEY))
    nlm = own_nlm or which("nlm")
    login_remedy = f"! {own_nlm} login --force" if own_nlm else LOGIN_REMEDY
    checks["nlm_installed"] = nlm is not None
    if nlm is None:
        remedy.append(UPSTREAM_REMEDY)
    else:
        try:
            code, out = runner([nlm, "notebook", "list"])
            checks["notebook_list_exit"] = code
            authed = code == 0 and not AUTH_PATTERN.search(out)
        except TimeoutError:
            checks["notebook_list_exit"] = "timeout"
            authed = False
        checks["nlm_authed"] = authed
        if not authed:
            remedy.append(login_remedy)

    if mcp_keys is None:
        checks["mcp_registration"] = "unreadable"
        if UPSTREAM_REMEDY not in remedy:
            remedy.append(UPSTREAM_REMEDY)
        remedy.append(RESTART_REMEDY)
    elif GOOD_KEY in mcp_keys:
        checks["mcp_registration"] = GOOD_KEY
        entry = (servers or {}).get(GOOD_KEY)
        if probe is not None and entry is not None:
            started, detail = probe_registered_server(entry, which, probe)
            checks["mcp_server_start"] = "ok" if started else f"failed: {detail}"
            if not started:
                remedy.append(START_REMEDY)
                remedy.append(RESTART_REMEDY)
    else:
        checks["mcp_registration"] = STALE_KEY if STALE_KEY in mcp_keys else "absent"
        if STALE_KEY in mcp_keys:
            remedy.append(RENAME_REMEDY)
        elif UPSTREAM_REMEDY not in remedy:
            remedy.append(UPSTREAM_REMEDY)
        remedy.append(RESTART_REMEDY)

    return {"ok": not remedy, "remedy": remedy, "checks": checks}


def main() -> int:
    config = Path.home() / ".claude.json"
    keys = read_user_mcp_keys(config)
    servers = read_user_mcp_servers(config)
    print(json.dumps(classify(subprocess_runner, shutil.which, keys, servers, subprocess_probe)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
