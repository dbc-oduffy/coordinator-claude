"""PreToolUse hook (matcher: Bash|PowerShell): deny a `codex exec` on Windows without the per-run unelevated sandbox override.

Tripwire CODEX-EXEC-ON-WINDOWS-RUNS-UNELEVATED-PER-RUN. With `[windows] sandbox = "elevated"` in
the box's codex config, every `codex exec` starts an elevated `codex.exe sandbox` and raises a UAC
prompt; a batch raises one per exec. `-c windows.sandbox="unelevated"` on the command line
overrides the config for that run only, so no box-wide config edit is needed.

Per statement (`;`, `&&`, `||`, `|`, `&`, newline), with `codex` in command position (an optional
`.exe` and path allowed, `-c`/`--config`/`-m`-style value flags before `exec` skipped): the
statement is denied unless an argument is `-c`/`--config` followed by `windows.sandbox=unelevated`
(quotes and backslash escapes around the value ignored) or `--config=windows.sandbox=unelevated`.
`--help`, `-h` and `--version` calls run; `bash -c`/`pwsh -Command` bodies are parsed too. Active
only when sys.platform is win32; silent on every other host. The `codex-exec-windows` wrapper
(`.exe`, `.cmd` or `python .../codex-exec-windows.py`) forwards its extra args to `codex exec`, so
it is held to the same override. A driver script that spawns codex internally is not visible here.

Override: COORDINATOR_ALLOW_CODEX_EXEC_WITHOUT_UNELEVATED_SANDBOX=1 in the hook environment
(guard-override-keys convention); the deny text never names it.

Contract: stdin is the PreToolUse JSON; a deny is the hookSpecificOutput envelope on stdout,
exit 0. Fails open (silent exit 0) on anything unparseable.
"""

from __future__ import annotations

import json
import os
import re
import sys

TRIPWIRE = "CODEX-EXEC-ON-WINDOWS-RUNS-UNELEVATED-PER-RUN"
OVERRIDE_KEY = "COORDINATOR_ALLOW_CODEX_EXEC_WITHOUT_UNELEVATED_SANDBOX"
_MAX_DEPTH = 2

_PREFILTER = re.compile(r"codex", re.I)
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAP = {"sudo", "env", "nohup", "time", "command", "exec", "timeout", "nice", "call", "start",
         "then", "do", "else", "if", "while", "until", "!", "setsid"}
_XARGS_VALUE_FLAGS = {"-P", "-n", "-I", "-L", "-d", "-s", "-E", "-a"}
_WRAPPER = "codex-exec-windows"
_PYTHONS = {"python", "python3", "py"}
_SHELLS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell", "cmd"}
_BODY_FLAGS = {"-c", "-command", "/c", "/k"}
_HELP = {"--help", "-h", "--version"}
_CODEX_VALUE_FLAGS = {"-c", "--config", "-m", "--model", "-p", "--profile", "-C", "--cd", "-s",
                      "--sandbox", "-i", "--image"}
_OVERRIDE_VALUE = re.compile(r"^windows\.sandbox=unelevated$")
_ESCAPES = re.compile(r"""[\\`"']""")


def _strip_heredocs(text: str) -> str:
    out: list[str] = []
    end: str | None = None
    for line in text.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        m = _HEREDOC.search(line)
        if m and "<<<" not in line:
            end = m.group(1)
    return "\n".join(out)


def _statements(text: str) -> list[list[str]]:
    """Quote-aware split into statements of tokens; an escaped quote inside a quote stays literal."""
    stmts: list[list[str]] = []
    tokens: list[str] = []
    buf: list[str] = []
    have = False
    quote = ""
    i, n = 0, len(text)

    def end_token() -> None:
        nonlocal have
        if have:
            tokens.append("".join(buf))
        buf.clear()
        have = False

    def end_stmt() -> None:
        end_token()
        if tokens:
            stmts.append(list(tokens))
        tokens.clear()

    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and quote == '"' and text[i + 1:i + 2] == '"':
                buf.append('"')
                i += 1
            elif c == quote:
                quote = ""
            else:
                buf.append(c)
        elif c in "'\"":
            quote = c
            have = True
        elif c in " \t":
            end_token()
        elif c in "\r\n;":
            end_stmt()
        elif c == "|":
            end_stmt()
            if text[i + 1:i + 2] == "|":
                i += 1
        elif c == "&":
            prev = text[i - 1:i] if i else ""
            if prev in ("<", ">") or text[i + 1:i + 2] == ">":
                buf.append(c)
                have = True
            else:
                end_stmt()
                if text[i + 1:i + 2] == "&":
                    i += 1
        else:
            buf.append(c)
            have = True
        i += 1
    end_stmt()
    return stmts


def _head(tokens: list[str]) -> tuple[str, list[str]]:
    """(command basename, argv) after env assignments and wrapper words."""
    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        if _ENV.match(t) or t in ("&", "."):
            i += 1
        elif t in _WRAP:
            i += 1
            while i < n and tokens[i].startswith("-") and len(tokens[i]) > 1:
                i += 1
            if t == "timeout" and i < n:
                i += 1
        elif t == "xargs":
            i += 1
            while i < n and tokens[i].startswith("-") and len(tokens[i]) > 1:
                i += 2 if tokens[i] in _XARGS_VALUE_FLAGS else 1
        else:
            break
    if i >= n:
        return "", []
    name = re.split(r"[\\/]", tokens[i])[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name, tokens[i + 1:]


def _codex_is_exec(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-"):
            i += 1 if "=" in a and a.startswith("--") else (2 if a in _CODEX_VALUE_FLAGS else 1)
            continue
        return a in ("exec", "e")
    return False


def _has_override(args: list[str]) -> bool:
    for idx, a in enumerate(args):
        if a in ("-c", "--config") and idx + 1 < len(args):
            value = args[idx + 1]
        elif a.startswith("--config="):
            value = a[len("--config="):]
        else:
            continue
        if _OVERRIDE_VALUE.match(_ESCAPES.sub("", value).replace(" ", "")):
            return True
    return False


def _scan(command: str, depth: int = 0) -> bool:
    """True when a statement spawns `codex exec` without the unelevated override."""
    for tokens in _statements(_strip_heredocs(command)):
        name, args = _head(tokens)
        if name in _SHELLS:
            for idx, a in enumerate(args):
                if a.lower() in _BODY_FLAGS and idx + 1 < len(args) and depth < _MAX_DEPTH:
                    if _scan(args[idx + 1], depth + 1):
                        return True
            continue
        if name in _PYTHONS and args:
            skip = next((k for k, a in enumerate(args) if not a.startswith("-")), len(args))
            name, args = _head(args[skip:])
            name = name[:-3] if name.endswith(".py") else name
        if any(a in _HELP for a in args):
            continue
        if name == _WRAPPER:
            if not _has_override(args):
                return True
        elif name == "codex" and _codex_is_exec(args) and not _has_override(args):
            return True
    return False


def _deny_reason(command: str) -> str:
    snippet = " ".join(command.split())[:140]
    return (
        f"[guard] {TRIPWIRE}: `codex exec` on Windows without the per-run unelevated sandbox override is "
        "denied. With the box's codex config on an elevated Windows sandbox, every exec starts an "
        "elevated `codex.exe sandbox` and raises a UAC prompt; a batch raises one per exec. "
        f"Command: {snippet}\n"
        "Use instead: add `-c windows.sandbox=\"unelevated\"` to the command, e.g. `codex exec -c "
        "windows.sandbox=\"unelevated\" --json --sandbox read-only --ephemeral ...`. Never edit the box-wide "
        "~/.codex/config.toml for it. See the tripwire-registry page "
        f"codex-exec-on-windows-runs-unelevated-per-run. Tripwire: {TRIPWIRE}."
    )


def main() -> int:
    try:
        if sys.platform != "win32":
            return 0
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str) or not _PREFILTER.search(command):
            return 0
        if os.environ.get(OVERRIDE_KEY) == "1":
            return 0
        if not _scan(command):
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
