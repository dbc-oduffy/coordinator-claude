"""PreToolUse hook (matcher: Bash|PowerShell): advise on `git merge` and `git merge --abort` when the
merge set overlaps tracked paths that carry uncommitted changes the merge did not make.

A conflicted merge that is aborted resets every file it touched, so it silently reverts a peer
session's uncommitted edit. Tripwire GUARD-GIT-MERGE-DIRTY-TREE; advisory only, never a block.

Advised, per pipeline segment (`bash -c` / `pwsh -Command` bodies are parsed too):
  - `git [global opts] merge <ref...>` and bare `git merge` (every configured `branch.<cur>.merge`
    head) when a dirty tracked path is also changed by the merge set since its merge base.
  - `git merge --abort` mid-merge when a worktree-only dirty path is changed by a recorded head
    (every MERGE_HEAD line) since ORIG_HEAD.
Silent: every other git command, `git merge --continue|--quit|--help`, untracked files, a clean
tree, and a merge set disjoint from the dirty paths. A merge set the hook cannot fully resolve
(too many heads, a failed diff) advises on every foreign dirty path.

The advice names the overlapping paths and the live sessions from the fleet roster
(`bin/unimatrix-roster.py live_sessions()`), or says none could be enumerated.

Contract: stdin is the PreToolUse JSON; advice is `hookSpecificOutput.additionalContext` on stdout,
exit 0, never a `permissionDecision`. Fails open (silent exit 0) on anything unparseable, any git
error, or a cwd outside a git repo.
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
_WRAPPERS = {"command", "builtin", "exec", "sudo", "nohup", "time", "env", "nice", "setsid", "timeout", "{", "!"}
_SHELLS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell"}
_CD_NAMES = {"cd", "chdir", "pushd", "set-location", "sl"}
_GIT_ARG_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
_VALUE_SHORT = "mFsX"
_VALUE_LONG = {"--message", "--file", "--strategy", "--strategy-option", "--into-name", "--cleanup"}
_MODE_SILENT = {"--continue", "--quit", "--help"}
_FOLD_SEPS = {"", "&&", ";", "\n"}
# Bounds hook latency: git calls are probe + status + config + one diff per head. A merge set larger
# than this is not diffed; the advice then covers every foreign dirty path.
_MAX_HEADS = 4
_MAX_PATHS = 15
_MAX_SESSIONS = 20
_GIT_TIMEOUT = 3
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _win_portability import no_console_spawn_kwargs  # noqa: E402


def _segments(text: str) -> list[tuple[list[str], int, str]]:
    """(tokens, subshell depth, separator before) per command segment.

    Quotes are stripped; `;|&()`, backticks and newlines outside quotes split segments. The separator
    is the operator run (`&&`, `||`, `|`, `;`, `&`) or `\\n` that preceded the segment, `""` for the
    first segment or one directly after a closing paren; `(` and a backtick pair raise the depth.
    """
    segs: list[tuple[list[str], int, str]] = []
    toks: list[str] = []
    cur: list[str] = []
    in_tok = False
    quote = ""
    depth = 0
    in_tick = False
    pending = ""
    seg_sep = ""
    last_op = False

    def end_tok() -> None:
        nonlocal cur, in_tok, pending, seg_sep
        if in_tok:
            if not toks:
                seg_sep, pending = pending, ""
            toks.append("".join(cur))
        cur, in_tok = [], False

    def end_seg() -> None:
        nonlocal toks
        end_tok()
        if toks:
            segs.append((toks, depth, seg_sep))
        toks = []

    for c in text:
        if quote:
            if c == quote:
                quote = ""
            else:
                cur.append(c)
            continue
        if c in "|&;":
            end_seg()
            pending = pending + c if last_op else c
            last_op = True
            continue
        last_op = False
        if c in "'\"":
            quote, in_tok = c, True
        elif c in " \t\r":
            end_tok()
        elif c == "\n":
            end_seg()
            pending = pending or "\n"
        elif c == "(" or (c == "`" and not in_tick):
            end_seg()
            depth += 1
            in_tick = in_tick or c == "`"
        elif c == ")" or c == "`":
            end_seg()
            depth = max(0, depth - 1)
            if c == "`":
                in_tick = False
        else:
            cur.append(c)
            in_tok = True
    end_seg()
    return segs


def _base_name(token: str) -> str:
    return re.split(r"[\\/]", token)[-1].lower().removesuffix(".exe")


def _parse_merge_args(rest: list[str]) -> tuple[str, list[str]]:
    """(mode, explicit heads) from the arguments after `merge`; mode is start|abort|silent.

    Only parsed options select a mode: an option's value (`-m "--abort"`) is never a flag.
    """
    mode = "start"
    silent = False
    heads: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        i += 1
        if a == "--":
            heads.extend(rest[i:])
            break
        if a == "-" or not a.startswith("-"):
            heads.append("@{-1}" if a == "-" else a)
        elif a.startswith("--"):
            name = a.split("=", 1)[0]
            if name == "--abort":
                mode = "abort"
            elif name in _MODE_SILENT:
                silent = True
            elif name in _VALUE_LONG and "=" not in a:
                i += 1
        else:
            for pos, ch in enumerate(a[1:], start=1):
                if ch == "h":
                    silent = True
                elif ch == "S":
                    break
                elif ch in _VALUE_SHORT:
                    if pos == len(a) - 1:
                        i += 1
                    break
    return ("silent" if silent else mode), heads


def _merge_kind(tokens: list[str]) -> tuple[str, list[str], str | None] | None:
    """(mode, explicit heads, -C dir or None) when the segment is an advisable git merge, else None."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) or t in _WRAPPERS:
            i += 1
        else:
            break
    if i >= len(tokens) or _base_name(tokens[i]) != "git":
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
    mode, heads = _parse_merge_args(tokens[i + 1:])
    if mode == "silent":
        return None
    return mode, heads, chdir


def _cd_target(tokens: list[str], cwd: str | None) -> str | None:
    """The directory a `cd`-family segment moves to, or None when it cannot be resolved."""
    i = 0
    while i < len(tokens) and tokens[i] in _WRAPPERS:
        i += 1
    if i >= len(tokens) or tokens[i].lower() not in _CD_NAMES:
        return ""
    args = [t for t in tokens[i + 1:] if t != "--"]
    args = [t for t in args if not t.startswith("-")]
    if cwd is None or not args or "$" in args[0] or "%" in args[0]:
        return None
    return os.path.join(cwd, _native_path(os.path.expanduser(args[0])))


_MSYS_DRIVE = re.compile(r"^/([A-Za-z])(?=/|$)")


def _native_path(path: str, windows: bool = os.name == "nt") -> str:
    """Git Bash spells `C:/x` as `/c/x`; joined as-is it names a missing dir and the hook goes silent."""
    return _MSYS_DRIVE.sub(lambda m: m.group(1).upper() + ":", path) if windows else path


def _find_merge(command: str, cwd: str, depth: int = 0) -> tuple[str, list[str], str] | None:
    """First advisable merge as (mode, heads, cwd it runs in); `cd` folds follow shell scope."""
    scopes: list[str | None] = [cwd]
    undo: tuple[int, str | None] | None = None
    for tokens, seg_depth, sep in _segments(command):
        if undo is not None and sep not in _FOLD_SEPS and undo[0] < len(scopes):
            scopes[undo[0]] = undo[1]
        undo = None
        while len(scopes) <= seg_depth:
            scopes.append(scopes[-1])
        del scopes[seg_depth + 1:]
        here = scopes[seg_depth]
        target = _cd_target(tokens, here)
        if target != "":
            if sep not in ("|", "|&"):
                undo = (seg_depth, here)
                scopes[seg_depth] = target
            continue
        found = _merge_kind(tokens)
        if found and here is not None:
            mode, heads, chdir = found
            run_in = os.path.join(here, os.path.expanduser(chdir)) if chdir else here
            return mode, heads, run_in
        lead = 0
        while lead < len(tokens) and tokens[lead] in _WRAPPERS:
            lead += 1
        if lead < len(tokens) and _base_name(tokens[lead]) in _SHELLS and depth < 3 and here is not None:
            for k, t in enumerate(tokens[:-1]):
                if re.match(r"^-[A-Za-z]*c$", t) or t.lower() in ("-command", "-c"):
                    powershell = _base_name(tokens[lead]) in ("pwsh", "powershell")
                    body = " ".join(tokens[k + 1:]) if powershell else tokens[k + 1]
                    inner = _find_merge(body, here, depth + 1)
                    if inner:
                        return inner
    return None


def _git(cwd: str, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "--no-optional-locks", *args], cwd=cwd, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT, **no_console_spawn_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _configured_heads(top: str, branch: str) -> list[str]:
    """Tracking refs of every `branch.<branch>.merge` value, in config order."""
    out = _git(top, "config", "--get-regexp", rf"^branch\.{re.escape(branch)}\.(merge|remote)$")
    if not out:
        return []
    prefix = f"branch.{branch}."
    merges: list[str] = []
    remote = "origin"
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        if not key.startswith(prefix):
            continue
        if key[len(prefix):].lower() == "merge" and value:
            merges.append(value)
        elif key[len(prefix):].lower() == "remote" and value:
            remote = value
    if remote == ".":
        return merges
    return [f"refs/remotes/{remote}/{m.removeprefix('refs/heads/')}" for m in merges]


def _read_merge_heads(merge_head: str) -> list[str]:
    try:
        return [ln.strip() for ln in Path(merge_head).read_text().splitlines() if ln.strip()]
    except OSError:
        return []


def _overlap(cwd: str, kind: str, explicit: list[str]) -> tuple[list[str], bool] | None:
    """(dirty paths the merge set also changes, exact) or None when nothing is advisable.

    `exact` is False when the changed set is unknown and every foreign dirty path is returned.
    """
    probe = _git(cwd, "rev-parse", "--show-toplevel", "--git-path", "MERGE_HEAD", "--abbrev-ref", "HEAD")
    if probe is None:
        return None
    lines = probe.splitlines()
    if len(lines) < 3:
        return None
    top, merge_head, branch = lines[0], lines[1], lines[2]
    # `--abbrev-ref` disambiguates as `heads/<name>` when a tag shares the branch's name.
    branch = branch.removeprefix("heads/")
    if not os.path.isabs(merge_head):
        merge_head = os.path.join(cwd, merge_head)
    mid_merge = os.path.exists(merge_head)
    if kind == "abort" and not mid_merge:
        return None
    status = _git(top, "status", "--porcelain=v1", "-z", "--untracked-files=no")
    if status is None:
        return None
    foreign: list[str] = []
    entries = iter(status.split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        x, path = entry[0], entry[3:]
        names = [path]
        if x in "RC":
            orig = next(entries, None)
            if orig:
                names.append(orig)
        if mid_merge and x != " ":
            continue
        foreign.extend(names)
    if not foreign:
        return None
    if kind == "abort":
        heads, base = _read_merge_heads(merge_head), "ORIG_HEAD"
    else:
        heads = explicit or (_configured_heads(top, branch) if branch != "HEAD" else [])
        base = "HEAD"
        if not heads:
            return None
    if not heads or len(heads) > _MAX_HEADS:
        return foreign, False
    changed: set[str] = set()
    for head in heads:
        diff = _git(top, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", "--")
        if diff is None:
            return foreign, False
        changed.update(p for p in diff.split("\0") if p)
    hit = [p for p in dict.fromkeys(foreign) if p in changed]
    return (hit, True) if hit else None


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


def _advice(kind: str, paths: list[str], sessions: list[str] | None, exact: bool) -> str:
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
    scope = (
        "the merge set changes these paths too"
        if exact else "the merge set could not be fully resolved, so every dirty path is listed"
    )
    effect = (
        "An abort resets every file the merge touched and reverts uncommitted edits there."
        if kind == "abort" else
        "A merge that conflicts is aborted and the abort reverts uncommitted edits in the files it touched."
    )
    return (
        f"[guard] {TRIPWIRE}: `{verb}` runs on a tree with {len(paths)} tracked path(s) carrying "
        f"uncommitted changes this merge did not make; {scope}.\n{path_lines}\n{who}\n{effect} "
        "Do not stash, commit or discard these changes to get past this: they belong to another "
        "session. Report the paths and sessions to your EM, and proceed once the owner has "
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
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        found = _find_merge(command, cwd)
        if not found:
            return 0
        kind, heads, run_in = found
        if not os.path.isdir(run_in):
            return 0
        overlap = _overlap(run_in, kind, heads)
        if not overlap or not overlap[0]:
            return 0
        paths, exact = overlap
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": _advice(kind, paths, _live_session_names(), exact),
        }}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
