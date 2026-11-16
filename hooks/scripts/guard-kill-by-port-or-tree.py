"""PreToolUse hook (matcher: Bash|PowerShell): deny kills chosen by port, name or process tree.

Tripwire DENY-KILL-BY-PORT-OR-TREE. A kill selected by listening port, by process name, or by
`taskkill /T` (which walks ParentProcessId; stale or reused parent pids reach foreign trees) can
end a job the session never spawned. Denied, per statement (`;`, `&&`, `||`, `|`, `&`, newline,
`$(...)`, and `-c`/`-Command`/`eval`/`cmd /c` bodies are parsed too):
  - `taskkill` with /T.
  - `taskkill /IM|/FI`, `pkill`, `killall`, `fuser -k`, `Stop-Process -Name`: selection by name.
  - `kill`, `taskkill /PID` or `Stop-Process -Id` in a command or script that also runs a port or
    name lookup (netstat, Get-NetTCPConnection, lsof, pgrep, pidof, tasklist, Get-Process other than
    `-Id`, Win32_Process queries, psutil.process_iter): the pid is not one the session recorded.
Allowed: `kill $!`, `Stop-Process -Id $proc.Id` from Start-Process, `taskkill /PID <pid>` without /T.

Script coverage: when a statement runs a .sh/.ps1/.py file (`bash x.sh`, `pwsh -File x.ps1`,
`& ./x.ps1`, `python x.py`) that was written recently (the in-session proxy: mtime within
_SCRIPT_WINDOW_S), that one file is read and held to the same patterns. Heredoc bodies are
scanned only when fed to a shell, interpreter or a script file.

Cost: an in-process regex prefilter returns at once for a command that mentions no kill verb and
runs no script. No subprocess. Override: COORDINATOR_ALLOW_KILL_BY_PORT_OR_TREE=1 in the hook
environment (guard-override-keys convention); the deny text never names it.

Contract: stdin is the PreToolUse JSON; a deny is the hookSpecificOutput envelope on stdout,
exit 0. Fails open (silent exit 0) on anything unparseable or unresolvable.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

TRIPWIRE = "DENY-KILL-BY-PORT-OR-TREE"
OVERRIDE_KEY = "COORDINATOR_ALLOW_KILL_BY_PORT_OR_TREE"
_SCRIPT_WINDOW_S = 12 * 3600
_SCRIPT_MAX_BYTES = 262144

_PREFILTER = re.compile(r"kill|stop-process|spps|fuser|\.(?:sh|bash|ps1|py)\b", re.I)
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_BODY_RUNS = re.compile(
    r">>?\s*\S*\.(?:sh|bash|ps1|py)\b|\b(?:bash|sh|zsh|pwsh|powershell|python3?|py|tee)\b", re.I)
_EXEC_BODY = re.compile(
    r"(?:\s-(?:c|command)|\beval|\bcmd(?:\.exe)?\s+/[ck])\s+[\"']?", re.I)
_SPLIT = re.compile(r"\r?\n|;|&&|\|\||\||&|\$\(|[(){}`]")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAP = {"sudo", "env", "nohup", "time", "command", "exec", "xargs", "timeout", "nice", "call",
         "start", "then", "do", "else", "if", "while", "until", "!", "setsid"}
_XARGS_VAL = {"-n", "-I", "-P", "-L", "-d", "-E", "-s", "-a"}
_TREE_ARGS = {"/t", "//t", "-t"}
_NAME_ARGS = {"/im", "//im", "-im", "/fi", "//fi", "-fi"}
_PS_NAME = re.compile(r"^-n(?:a(?:m(?:e)?)?)?$", re.I)
_SCRIPT_EXT = {"bash": (".sh", ".bash"), "sh": (".sh", ".bash"), "zsh": (".sh", ".bash"),
               "dash": (".sh", ".bash"), "source": (".sh", ".bash"), ".": (".sh", ".bash", ".ps1"),
               "pwsh": (".ps1",), "powershell": (".ps1",), "python": (".py",), "python3": (".py",),
               "py": (".py",)}
_SOURCE = re.compile(
    r"\bnetstat\b|\bGet-Net(?:TCP|UDP)Connection\b|\bOwningProcess\b|\blsof\b|\bpgrep\b|\bpidof\b"
    r"|\btasklist\b|\bGet-Process\b(?!\s+-(?:Id|InputObject)\b)|\bgps\b|\bWin32_Process\b|\bwmic\b"
    r"|\bprocess_iter\b|\bnet_connections\b|\.connections\s*\(", re.I)
_PY_SINK = re.compile(r"\bos\.kill(?:pg)?\s*\(|\.(?:kill|terminate)\s*\(\s*\)|\btaskkill\b|Stop-Process", re.I)
_PY_NAMED = re.compile(r"\b(?:pkill|killall)\b|Stop-Process\s+(?:\S+\s+)*?-n(?:ame)?\b", re.I)
_PY_ARG_BOUND = r"(?:^|[\s\"',\[(])"
_PY_TREE = re.compile(_PY_ARG_BOUND + r"[/-]{1,2}t(?=$|[\s\"',\])])", re.I)
_PY_NAME = re.compile(_PY_ARG_BOUND + r"[/-]{1,2}(?:im|fi)(?=$|[\s\"',\])])", re.I)

_TREE_LABEL = "taskkill /T (kills a process tree through ParentProcessId)"
_NAME_LABEL = "a kill that selects processes by name"


def _strip_heredocs(text: str) -> str:
    out: list[str] = []
    end: str | None = None
    keep = False
    for line in text.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            elif keep:
                out.append(line)
            continue
        out.append(line)
        m = _HEREDOC.search(line)
        if m and "<<<" not in line:
            end, keep = m.group(1), bool(_BODY_RUNS.search(line))
    return "\n".join(out)


def _head(tokens: list[str]) -> tuple[str, str, list[str]]:
    """(command basename, raw command token, argv) after env assignments and wrapper words."""
    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        if _ENV.match(t):
            i += 1
        elif t in _WRAP:
            i += 1
            if t == "xargs":
                while i < n and tokens[i].startswith("-"):
                    i += 2 if tokens[i] in _XARGS_VAL else 1
            else:
                while i < n and tokens[i].startswith("-") and len(tokens[i]) > 1:
                    i += 1
                if t == "timeout" and i < n:
                    i += 1
        else:
            break
    if i >= n:
        return "", "", []
    name = re.split(r"[\\/]", tokens[i])[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name, tokens[i], tokens[i + 1:]


def _classify(name: str, args: list[str]) -> str | None:
    """A deny label, "plain" for a kill that needs a pid-provenance check, or None."""
    low = [a.lower() for a in args]
    if name == "taskkill":
        if any(a in _TREE_ARGS for a in low):
            return _TREE_LABEL
        if any(a in _NAME_ARGS for a in low):
            return "taskkill selecting by image name or filter"
        return "plain"
    if name in ("pkill", "killall"):
        return f"{name}, which selects processes by name"
    if name == "fuser" and any(re.match(r"^-[a-z]*k", a) for a in low):
        return "fuser -k, which kills whatever holds a port or file"
    if name in ("stop-process", "spps"):
        if any(_PS_NAME.match(a) for a in args):
            return "Stop-Process -Name, which kills every process of that name"
        return "plain"
    if name == "kill":
        return "plain"
    return None


def _script_arg(name: str, raw: str, args: list[str]) -> str | None:
    exts = (".sh", ".bash", ".ps1", ".py")
    if name not in _SCRIPT_EXT:
        return raw if raw.lower().endswith(exts) and not raw.startswith("-") else None
    if name in ("python", "python3", "py") and any(a in ("-m", "-c") for a in args):
        return None
    for a in args:
        if not a.startswith("-") and a.lower().endswith(_SCRIPT_EXT[name]):
            return a
    return None


def _scan_shell(text: str) -> tuple[str | None, list[str]]:
    """(deny label, script paths the statements run) for shell or PowerShell text."""
    text = _EXEC_BODY.sub(" ; ", _strip_heredocs(text))
    plain = False
    scripts: list[str] = []
    for stmt in _SPLIT.split(text):
        tokens = [t.strip("\"'") for t in stmt.split()]
        tokens = [t for t in tokens if t]
        if not tokens or tokens[0].startswith("#"):
            continue
        name, raw, args = _head(tokens)
        if not name:
            continue
        verdict = _classify(name, args)
        if verdict == "plain":
            plain = True
        elif verdict:
            return verdict, scripts
        script = _script_arg(name, raw, args)
        if script:
            scripts.append(script)
    if plain:
        m = _SOURCE.search(text)
        if m:
            return f"a kill whose pid comes from a port or name lookup ({m.group(0).strip()})", scripts
    return None, scripts


def _scan_python(text: str) -> str | None:
    for m in re.finditer(r"taskkill", text, re.I):
        rest = text[m.end():m.end() + 300].split("\n", 1)[0]
        if _PY_TREE.search(rest):
            return _TREE_LABEL
        if _PY_NAME.search(rest):
            return "taskkill selecting by image name or filter"
    m = _PY_NAMED.search(text)
    if m:
        return _NAME_LABEL
    if _PY_SINK.search(text):
        src = _SOURCE.search(text)
        if src:
            return f"a kill whose pid comes from a port or name lookup ({src.group(0).strip()})"
    return None


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(/.*)?$", p)
        if m:
            p = f"{m.group(1).upper()}:{m.group(2) or '/'}"
    return p


def _read_recent(path: str, cwd: str) -> str | None:
    """File text when `path` is a small regular file written within the session window."""
    if "$" in path or "`" in path or any(c in path for c in "*?["):
        return None
    try:
        p = _norm(path)
        if p == "~" or p.startswith("~/"):
            p = os.path.expanduser(p)
        if not os.path.isabs(p):
            p = os.path.join(_norm(cwd), p)
        st = os.stat(p)
        if st.st_size > _SCRIPT_MAX_BYTES or time.time() - st.st_mtime > _SCRIPT_WINDOW_S:
            return None
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def _check(command: str, cwd: str) -> tuple[str, str] | None:
    """(label, where) for a denied command, or None. `where` names the script when the hit is in one."""
    label, scripts = _scan_shell(command)
    if label:
        return label, ""
    for path in scripts[:4]:
        body = _read_recent(path, cwd)
        if body is None:
            continue
        hit = _scan_python(body) if path.lower().endswith(".py") else _scan_shell(body)[0]
        if hit:
            return hit, re.split(r"[\\/]", path)[-1]
    return None


def _deny_reason(label: str, where: str, command: str) -> str:
    snippet = " ".join(command.split())[:140]
    place = f" in script {where}" if where else ""
    return (
        f"[guard] {TRIPWIRE}: {label}{place} is denied. A kill chosen by port, name or process "
        "tree reaches jobs this session never spawned through stale or reused pids (a bisect "
        "reap taskkilled a port owner with /T and ended a foreign 4-hour run). "
        f"Command: {snippet}\n"
        "Use instead: kill only a pid you recorded when you spawned the process (`$!`, "
        "`Start-Process -PassThru` then `.Id`, Popen `.pid`), re-check its CommandLine still "
        "matches what you spawned immediately before the kill, log the pid and CommandLine, and "
        "kill that pid alone without /T. See the tripwire-registry page deny-kill-by-port-or-tree. "
        f"Tripwire: {TRIPWIRE}."
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str) or not _PREFILTER.search(command):
            return 0
        if os.environ.get(OVERRIDE_KEY) == "1":
            return 0
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        hit = _check(command, cwd)
        if not hit:
            return 0
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _deny_reason(hit[0], hit[1], command),
        }}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
