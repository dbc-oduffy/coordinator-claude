"""PreToolUse hook (matcher: Bash|PowerShell): deny a ps/pgrep/pidof wait loop in Git Bash on win32.

Under Git Bash on Windows, MSYS `ps`/`pgrep`/`pidof` see only MSYS processes; a windowless native
Windows runner is invisible to them, so `until ! ps -ef | grep -q runner; do sleep 5; done`
exits at once. Tripwire DENY-PS-WAIT-ON-WIN32 (doctrine A-PS-WAIT-IN-GIT-BASH-FIRES-EARLY).

Denied, on win32 and for tool_name "Bash" only (in PowerShell `ps` is Get-Process, which sees
native processes): an `until`/`while` loop whose condition or body runs ps, pgrep or pidof, in the
command text, in a `bash -c`/`eval` body, or in a `bash|sh <file>.sh` target read from disk
(resolved against the payload cwd, at most 256 KiB).
Allowed: everything off win32; a one-shot ps/pgrep outside a loop; tasklist and
Get-CimInstance Win32_Process loops.

Contract: stdin is the PreToolUse JSON; a deny is the hookSpecificOutput envelope on stdout,
exit 0. Fails open (silent exit 0) on anything unparseable or unreadable.
"""

from __future__ import annotations

import json
import os
import re
import sys

TRIPWIRE = "DENY-PS-WAIT-ON-WIN32"
DOCTRINE = "A-PS-WAIT-IN-GIT-BASH-FIRES-EARLY"
_PROCTAB = {"ps", "pgrep", "pidof"}
_LOOP_OPEN = {"while", "until"}
_BLOCK_OPEN = _LOOP_OPEN | {"for", "select"}
_LEAD = {"do", "then", "else", "{", "!", "if", "elif"}
_WRAPPERS = {"command", "builtin", "exec", "sudo", "nohup", "time", "env", "nice", "setsid",
             "timeout", "!"} | _LEAD | _LOOP_OPEN
_SHELLS = {"bash", "sh", "zsh", "dash"}
_MAX_SCRIPT_BYTES = 256 * 1024
_MAX_DEPTH = 3
_ESCAPED = set(" \t\"';&|()<>$`")
_INTEREST = re.compile(r"(?<![\w-])(?:ps|pgrep|pidof|sh|bash|zsh|dash)(?![\w-])")
_SUBST = re.compile(r"(?:\$\(|`)\s*(?:\S*[\\/])?(?:ps|pgrep|pidof)(?:\.exe)?(?![\w-])")
_REDIR = re.compile(r"^(?:\d*>>?&?|&>>?|\d*<<?<?-?)$")
_REDIR_ATTACHED = re.compile(r"^(?:\d*[<>]|&>)")


def _strip_heredocs(text: str) -> str:
    out: list[str] = []
    end: str | None = None
    for line in text.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if m and "<<<" not in line:
            end = m.group(1)
    return "\n".join(out)


def _segments(text: str) -> list[list[str]]:
    """Token lists per pipeline segment (`|`, `||`, `&&`, `;`, `&`, newline, parens, backticks)."""
    segs: list[list[str]] = []
    tokens: list[str] = []
    cur: list[str] = []
    in_tok = False
    quote = ""
    i, n = 0, len(text)

    def end_tok() -> None:
        nonlocal in_tok, cur
        if in_tok:
            tokens.append("".join(cur))
        cur, in_tok = [], False

    def end_seg() -> None:
        nonlocal tokens
        end_tok()
        if tokens:
            segs.append(tokens)
        tokens = []

    while i < n:
        c = text[i]
        if quote:
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"' and i + 1 < n and text[i + 1] in '"\\$`':
                i += 1
                cur.append(text[i])
            else:
                cur.append(c)
        elif c in "'\"":
            quote, in_tok = c, True
        elif c == "\\" and i + 1 < n and text[i + 1] in _ESCAPED:
            i += 1
            cur.append(text[i])
            in_tok = True
        elif c in " \t\r":
            end_tok()
        elif c in "\n;()`":
            end_seg()
        elif c == "|":
            if text[i + 1:i + 2] == "|":
                i += 1
            end_seg()
        elif c == "&":
            if text[i + 1:i + 2] == "&":
                i += 1
                end_seg()
            elif cur and cur[-1] in "<>" or (not in_tok and i + 1 < n and text[i + 1] == ">"):
                cur.append(c)
                in_tok = True
            else:
                end_seg()
        else:
            cur.append(c)
            in_tok = True
        i += 1
    end_seg()
    return segs


def _head(tokens: list[str]) -> tuple[str, list[str]]:
    """Command name (basename, no .exe) and its argv after env assignments and wrapper words."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
        elif t in _WRAPPERS:
            i += 1
            while i < len(tokens) and tokens[i].startswith("-") and len(tokens[i]) > 1:
                i += 1
            if t == "timeout" and i < len(tokens):
                i += 1
        else:
            break
    if i >= len(tokens):
        return "", []
    name = re.split(r"[\\/]", tokens[i])[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name, tokens[i + 1:]


def _drop_redirects(args: list[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for t in args:
        if skip:
            skip = False
        elif _REDIR.match(t):
            skip = True
        elif not _REDIR_ATTACHED.match(t):
            out.append(t)
    return out


def _leading_keyword(tokens: list[str]) -> str:
    for t in tokens:
        if t not in _LEAD:
            return t
    return ""


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(/.*)?$", p)
        if m:
            p = f"{m.group(1).upper()}:{m.group(2) or '/'}"
    return p


def _read_script(path: str, cwd: str | None) -> str | None:
    try:
        p = _norm(path)
        if not os.path.isabs(p):
            if not cwd:
                return None
            p = os.path.join(_norm(cwd), p)
        with open(p, "rb") as fh:
            return fh.read(_MAX_SCRIPT_BYTES).decode("utf-8", "replace")
    except (OSError, ValueError):
        return None


def _script_arg(args: list[str]) -> str | None:
    for t in args:
        if t.startswith("-"):
            continue
        return t if t.lower().endswith(".sh") else None
    return None


def _check_argv(name: str, args: list[str], cwd: str | None, in_loop: bool, depth: int) -> bool:
    if in_loop and name in _PROCTAB:
        return True
    if depth >= _MAX_DEPTH:
        return False
    if name in _SHELLS:
        for k, t in enumerate(args[:-1]):
            if re.match(r"^-[A-Za-z]*c$", t):
                return _check_text(args[k + 1], cwd, depth + 1, in_loop)
        script = _script_arg(args)
        if script:
            body = _read_script(script, cwd)
            return body is not None and _check_text(body, cwd, depth + 1, in_loop)
        return False
    if name == "eval":
        return _check_text(" ".join(args), cwd, depth + 1, in_loop)
    return False


def _check_text(command: str, cwd: str | None, depth: int = 0, in_loop: bool = False) -> bool:
    """True when the text runs ps/pgrep/pidof inside an until/while loop (or `in_loop` already)."""
    if not _INTEREST.search(command):
        return False
    stack: list[bool] = []
    for tokens in _segments(_strip_heredocs(command)):
        lead = _leading_keyword(tokens)
        if lead == "done":
            if stack:
                stack.pop()
            continue
        if lead in _BLOCK_OPEN:
            stack.append(lead in _LOOP_OPEN)
        looping = in_loop or any(stack)
        if looping and any(_SUBST.search(t) for t in tokens):
            return True
        name, args = _head(tokens)
        if name and _check_argv(name, _drop_redirects(args), cwd, looping, depth):
            return True
    return False


def _deny_reason(command: str) -> str:
    snippet = " ".join(command.split())[:140]
    return (
        f"[guard] {TRIPWIRE}: an until/while wait gated on ps/pgrep/pidof is denied under Git Bash "
        "on Windows. MSYS ps/pgrep see only MSYS processes; a windowless native Windows runner is "
        f"invisible to them, so the wait passes at once and the next stage runs early. Command: {snippet}\n"
        "Use instead: one runner with ordered stages (no wait needed); a `mkdir` lock "
        "(`mkdir \"$LOCK\"` is atomic: retry until it succeeds, `rmdir` when done); or a pid file "
        "checked through the Windows process table: `tasklist //FI \"PID eq <pid>\" //NH` or "
        "`powershell -NoProfile -Command \"Get-CimInstance Win32_Process -Filter 'ProcessId=<pid>'\"`. "
        "A one-shot ps/pgrep outside a loop still runs. "
        f"Doctrine: {DOCTRINE}. Tripwire: {TRIPWIRE}."
    )


def main() -> int:
    try:
        if sys.platform != "win32":
            return 0
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            return 0
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        if not _check_text(command, cwd):
            return 0
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _deny_reason(command),
        }}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
