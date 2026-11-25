"""gem-save-box — the Group EM's "save the box by killing stuff" button.

A forwarder, not a kill tool: it runs the G-EM's own `tools/gem-save-box/gem_save_box.py`
(`survey | kill --pid --reason [--tree] [--dry-run] [--expect-create-time] [--allow-session] |
trim-memory [--apply]`) under `sys.executable` with argv verbatim and returns its exit code. The
tool keeps its critical-process and caller-ancestor refusals and its audit log. The group-em home
is `settings_home() / "group-em"`.

Refuses (exit 2, one line, nothing run) unless the calling session is the live Group EM, or the
tool script is absent. `--help` with no subcommand prints this forwarder's help and skips the check.

Known limit: a CLI process sees no hook agent_id, so a subagent of the G-EM's session resolves the
G-EM's session_id and passes the standing check; the tool's own refusals and audit log still apply.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOOL_REL = Path("tools") / "gem-save-box" / "gem_save_box.py"
_HELP = (
    "usage: gem-save-box.py {survey | kill --pid PID --reason TEXT [--tree] [--dry-run] "
    "[--expect-create-time T] [--allow-session] | trim-memory [--apply]}\n"
    "Live Group EM only: forwards argv to the group-em tool tools/gem-save-box/gem_save_box.py."
)


def _settings_home() -> Path:
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(override) if override else Path.home() / ".coordinator-claude-settings"


def tool_path() -> Path:
    """The G-EM's tool script under the settings home's group-em directory."""
    return _settings_home() / "group-em" / _TOOL_REL


def _live_gem(cwd: str) -> bool:
    """True iff this process's session is the live Group EM for ``cwd``'s repo; import and session-resolve failures raise."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from coordinator_core.bash_guards._gem_standing_kill import gem_standing
    from coordinator_core.session.core import resolve_session_id

    return gem_standing({"session_id": resolve_session_id(cwd), "cwd": cwd})


def run(
    argv: Sequence[str],
    *,
    standing: Optional[Callable[[str], bool]] = None,
    cwd: Optional[str] = None,
    err=None,
) -> int:
    """Forward ``argv`` to the group-em tool for the live G-EM; collaborators are injectable for tests."""
    err = err or sys.stderr
    cwd = cwd or os.getcwd()
    try:
        live = (standing or _live_gem)(cwd)
        why = "not the live G-EM"
    except Exception as exc:
        live, why = False, f"standing check failed: {type(exc).__name__}: {exc}"
    if not live:
        print(f"gem-save-box: refused, {why}", file=err)
        return 2
    script = tool_path()
    if not script.is_file():
        print(f"gem-save-box: tool script not found: {script}", file=err)
        return 2
    return subprocess.run(
        [sys.executable, str(script), *argv],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).returncode


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    if not args or args == ["--help"] or args == ["-h"]:
        print(_HELP)
        return 0
    return run(args)
