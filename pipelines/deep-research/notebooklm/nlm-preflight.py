"""NotebookLM preflight: a real `nlm notebook list` call plus the user-scope MCP registration.

Prints one JSON object {ok, remedy, checks} and always exits 0; the calling stage reads `ok`.
Never use `nlm login --check`: it passes on expired auth.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

INSTALL_REMEDY = "! uv tool install notebooklm-mcp-cli"
LOGIN_REMEDY = "! nlm login --force"
ADD_REMEDY = "! claude mcp add -s user notebooklm-mcp -- notebooklm-mcp"
REMOVE_REMEDY = "! claude mcp remove gemini-notebook-mcp -s user"
RESTART_REMEDY = "restart Claude Code"
GOOD_KEY = "notebooklm-mcp"
STALE_KEY = "gemini-notebook-mcp"
AUTH_PATTERN = re.compile(r"auth|expired|log\s*in|login|unauthori[sz]ed|credential", re.I)
TIMEOUT_S = 45

# runner(argv) -> (returncode, combined_output); raises TimeoutError on timeout.
Runner = Callable[[list[str]], tuple[int, str]]


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


def classify(runner: Runner, which: Callable[[str], str | None], mcp_keys: set[str] | None) -> dict:
    remedy: list[str] = []
    checks: dict = {}

    nlm = which("nlm")
    checks["nlm_installed"] = nlm is not None
    if nlm is None:
        remedy.append(INSTALL_REMEDY)
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
            remedy.append(LOGIN_REMEDY)

    if mcp_keys is None:
        checks["mcp_registration"] = "unreadable"
        remedy.append(ADD_REMEDY)
        remedy.append(RESTART_REMEDY)
    elif GOOD_KEY in mcp_keys:
        checks["mcp_registration"] = GOOD_KEY
    else:
        checks["mcp_registration"] = STALE_KEY if STALE_KEY in mcp_keys else "absent"
        remedy.append(ADD_REMEDY)
        if STALE_KEY in mcp_keys:
            remedy.append(REMOVE_REMEDY)
        remedy.append(RESTART_REMEDY)

    return {"ok": not remedy, "remedy": remedy, "checks": checks}


def main() -> int:
    keys = read_user_mcp_keys(Path.home() / ".claude.json")
    print(json.dumps(classify(subprocess_runner, shutil.which, keys)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
