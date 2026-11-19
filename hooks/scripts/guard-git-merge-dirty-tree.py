"""PreToolUse hook (matcher: Bash|PowerShell): refuse `git merge` and `git merge --abort` on a shared
tree that carries uncommitted changes the merge did not make.

An aborted merge resets every file it touched, so it silently reverts a peer session's uncommitted
edit. Tripwire GUARD-GIT-MERGE-DIRTY-TREE; no override: commit or hand back the named paths first.

Denied, per pipeline segment (`bash -c` / `pwsh -Command` bodies are parsed too):
  - `git [global opts] merge <ref...>` and `git merge --abort` when a tracked path is dirty.
    Before a merge starts every dirty path is foreign. Mid-merge (MERGE_HEAD present) paths with an
    index-side state (unmerged or staged by the merge) are the merge's; a path dirty only in the
    worktree is foreign.
Allowed: every other git command, `git merge --continue|--quit|--help`, untracked files (a merge
never deletes them), a clean tree.

The denial names the dirty paths and the live sessions from the fleet roster
(`bin/unimatrix-roster.py live_sessions()`), or says none could be enumerated.

Contract: stdin is the PreToolUse JSON; a deny is the hookSpecificOutput envelope on stdout, exit 0.
Fails open (silent exit 0) on anything unparseable, any git error, or a cwd outside a git repo.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TRIPWIRE = "GUARD-GIT-MERGE-DIRTY-TREE"
_WRAPPERS = {"command", "builtin", "exec", "sudo", "nohup", "time", "env", "nice", "setsid", "timeout"}
_SHELLS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell"}
_GIT_ARG_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
_MAX_PATHS = 15
_MAX_SESSIONS = 20
_GIT_TIMEOUT = 3
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _segments(text: str) -> list[list[str]]:
    """Tokens per command segment; quotes stripped, `;|&()` and newlines outside quotes split segments."""
    segs: list[list[str]] = []
    toks: list[str] = []
    cur: list[str] = []
    in_tok = False
    quote = ""

    def end_tok() -> None:
        nonlocal cur, in_tok
        if in_tok:
            toks.append("".join(cur))
        cur, in_tok = [], False

    def end_seg() -> None:
        nonlocal toks
        end_tok()
        if toks:
            segs.append(toks)
        toks = []

    for c in text:
        if quote:
            if c == quote:
                quote = ""
            else:
                cur.append(c)
        elif c in "'\"":
            quote, in_tok = c, True
        elif c in " \t\r":
            end_tok()
        elif c in "\n;|&()`":
            end_seg()
        else:
            cur.append(c)
            in_tok = True
    end_seg()
    return segs


def _merge_kind(tokens: list[str]) -> tuple[str, str | None] | None:
    """('start'|'abort', -C dir or None) when the segment is a denied git merge shape, else None."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) or t in _WRAPPERS:
            i += 1
        else:
            break
    if i >= len(tokens) or re.split(r"[\\/]", tokens[i])[-1].lower().removesuffix(".exe") != "git":
        return None
    i += 1
    chdir: str | None = None
    while i < len(tokens) and tokens[i].startswith("-"):
        t = tokens[i]
        if t in _GIT_ARG_OPTS:
            if t == "-C" and i + 1 < len(tokens):
                chdir = tokens[i + 1] if chdir is None else os.path.join(chdir, tokens[i + 1])
            i += 2
        else:
            i += 1
    if i >= len(tokens) or tokens[i] != "merge":
        return None
    rest = tokens[i + 1:]
    if any(a in ("-h", "--help", "--continue", "--quit") for a in rest):
        return None
    return ("abort" if "--abort" in rest else "start"), chdir


def _find_merge(command: str, depth: int = 0) -> tuple[str, str | None] | None:
    for tokens in _segments(command):
        found = _merge_kind(tokens)
        if found:
            return found
        name = re.split(r"[\\/]", tokens[0])[-1].lower().removesuffix(".exe")
        if name in _SHELLS and depth < 3:
            for k, t in enumerate(tokens[:-1]):
                if re.match(r"^-[A-Za-z]*c$", t) or t.lower() in ("-command", "-c"):
                    inner = _find_merge(" ".join(tokens[k + 1:]), depth + 1)
                    if inner:
                        return inner
    return None


def _git(cwd: str, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "--no-optional-locks", *args], cwd=cwd, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _foreign_paths(cwd: str) -> list[str] | None:
    """Tracked dirty paths the merge did not make; None when git cannot answer."""
    probe = _git(cwd, "rev-parse", "--show-toplevel", "--git-path", "MERGE_HEAD")
    if probe is None:
        return None
    lines = probe.splitlines()
    if len(lines) < 2:
        return None
    top, merge_head = lines[0], lines[1]
    if not os.path.isabs(merge_head):
        merge_head = os.path.join(cwd, merge_head)
    mid_merge = os.path.exists(merge_head)
    status = _git(top, "status", "--porcelain=v1", "-z", "--untracked-files=no")
    if status is None:
        return None
    foreign: list[str] = []
    entries = iter(status.split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        x, path = entry[0], entry[3:]
        if x in "RC":
            next(entries, None)
        if mid_merge and x != " ":
            continue
        foreign.append(path)
    return foreign


def _live_session_names() -> list[str] | None:
    """Bare names of the live fleet sessions, or None when the roster cannot be read."""
    try:
        here = Path(__file__).resolve()
        roster = here.parents[2] / "bin" / "unimatrix-roster.py"
        spec = importlib.util.spec_from_file_location("unimatrix_roster_for_merge_guard", roster)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return sorted({name for name, _sock in module.live_sessions()})
    except Exception:
        return None


def _deny_reason(kind: str, paths: list[str], sessions: list[str] | None) -> str:
    shown = paths[:_MAX_PATHS]
    path_lines = "\n".join(f"  {p}" for p in shown)
    if len(paths) > len(shown):
        path_lines += f"\n  ... and {len(paths) - len(shown)} more"
    if sessions is None:
        who = "Live sessions could not be enumerated (the fleet roster was unreadable)."
    elif not sessions:
        who = "No live sessions are listed in the fleet roster."
    else:
        who = "Live sessions that may own these paths: " + ", ".join(sessions[:_MAX_SESSIONS])
        if len(sessions) > _MAX_SESSIONS:
            who += f", ... and {len(sessions) - _MAX_SESSIONS} more"
        who += "."
    verb = "git merge --abort" if kind == "abort" else "git merge"
    effect = (
        "An abort resets every file the merge touched and reverts uncommitted edits there."
        if kind == "abort" else
        "A merge that conflicts is aborted and the abort reverts uncommitted edits in the files it touched."
    )
    return (
        f"[guard] {TRIPWIRE}: `{verb}` is denied: {len(paths)} tracked path(s) carry uncommitted "
        f"changes this merge did not make.\n{path_lines}\n{who}\n{effect} "
        "Do not stash, commit or discard these changes to get past this: they belong to another "
        "session. Stop, report the paths and sessions to your EM, and retry once the owner has "
        f"committed or released them. Tripwire: {TRIPWIRE}."
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str) or "merge" not in command:
            return 0
        found = _find_merge(command)
        if not found:
            return 0
        kind, chdir = found
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        if chdir:
            cwd = chdir if os.path.isabs(chdir) else os.path.join(cwd, chdir)
        if not os.path.isdir(cwd):
            return 0
        paths = _foreign_paths(cwd)
        if not paths:
            return 0
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _deny_reason(kind, paths, _live_session_names()),
        }}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
