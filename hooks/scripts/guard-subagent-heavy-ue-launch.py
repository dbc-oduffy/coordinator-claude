# guard-not-a-hook-entrypoint: registered by the control-plane engine's guard roster behind the
# single PreToolUse(Bash|PowerShell) dispatcher (preuse-bash-dispatch.py) -- hooks.json names the
# dispatcher, not this file.
"""PreToolUse(Bash|PowerShell) hook: deny a dispatched agent an Unreal build or editor launch.

Unreal build/editor runs are Group EM slot legs (tripwire AN-EXECUTOR-NEVER-FANS-OUT-HEAVY-RUNS):
a UBT compile must never overlap an editor run, and the slot is granted to the EM, not to a
subagent. Prose failed once (an executor compile-verified with build-plugin.ps1 mid-GPU-leg), so
this guard denies the launch itself.

DETECTION IS COMMAND-POSITION, NOT SUBSTRING. A name sitting as the program being run is a launch;
the same name as a grep pattern, a `cat` operand, `echo` text, a `git log --` pathspec or a comment
is a mention and is allowed. The command is split into segments on unquoted `; && || | & ( )` and
newlines, comments dropped, and each segment's head is peeled through launch wrappers (`&`, `.`,
`call`, `start`, `env`, `cmd /c`, `pwsh|powershell -File|-Command`, `bash|sh -c`, `dotnet`) to the
program actually run. This is a local tokenizer, not the engine's: the engine classifier is
shape-oriented and this guard must work with the engine unresolvable.

KNOWN GAPS (fail open): a program reached through a variable (`& $ue`), `Invoke-Expression`,
`eval`, a `xargs`/`-exec` target, a name assembled by string concatenation, and a script that
itself launches UBT. The residual is an unenforced prose rule, the status quo ante.

SCOPED TO SUBAGENTS: a non-empty `agent_id`. The main-loop EM holds the slot and is never guarded.
Fails open on a malformed payload or any exception.

Contract: stdin PreToolUse JSON; exit 0 = allow (silent); exit 2 + stderr = deny.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from _message_envelope import compose, render  # noqa: E402

_SHELL_TOOLS = ("Bash", "PowerShell")

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/an-executor-never-fans-out-heavy-runs.md"
)

#: Lowercased basenames, `.exe` already stripped, that are a heavy UE launch when run.
_HEAVY_NAMES = frozenset({
    "unrealbuildtool", "unrealbuildtool.dll",
    "build.bat",
    "runuat", "runuat.bat", "runuat.sh", "runuat.command",
    "build-plugin.ps1",
    "unrealeditor", "unrealeditor-cmd",
})

#: Words that precede the real program without being it.
_PASS_THROUGH = frozenset({
    "&", ".", "call", "start", "start-process", "env", "sudo", "time", "nohup", "exec", "command",
    "builtin", "nice", "stdbuf", "{", "}", "!", "if", "then", "else", "elif", "do", "while",
    "until", "-and", "-or", "invoke-command",
})

_PLAIN_INTERPRETERS = frozenset({"dotnet", "bash", "sh", "zsh", "cmd", "cmd.exe"})
_PWSH_NAMES = frozenset({"pwsh", "powershell"})
_MAX_DEPTH = 4


def _segments(cmd: str) -> "list[list[str]]":
    """Split `cmd` into segments of unquoted-token lists; quotes are removed, comments dropped."""
    segments: "list[list[str]]" = []
    tokens: "list[str]" = []
    cur: "list[str]" = []
    have_tok = False
    quote = ""
    i, n = 0, len(cmd)

    def end_tok() -> None:
        nonlocal cur, have_tok
        if have_tok:
            tokens.append("".join(cur))
        cur, have_tok = [], False

    def end_seg() -> None:
        nonlocal tokens
        end_tok()
        if tokens:
            segments.append(tokens)
        tokens = []

    while i < n:
        ch = cmd[i]
        if quote:
            if ch == quote:
                quote = ""
            else:
                cur.append(ch)
            i += 1
            continue
        if ch in "\"'":
            quote, have_tok = ch, True
            i += 1
            continue
        if ch == "#" and not have_tok:
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        if ch in " \t\r":
            end_tok()
        elif ch in ";\n|()":
            end_seg()
        elif ch == "&":
            if cmd[i:i + 2] == "&&":
                end_seg()
                i += 1
            elif not have_tok and not tokens:
                tokens.append("&")  # PowerShell call operator in command position
            else:
                end_seg()
        else:
            cur.append(ch)
            have_tok = True
        i += 1
    end_seg()
    return segments


def _base(token: str) -> str:
    name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _is_heavy(token: str) -> bool:
    return _base(token) in _HEAVY_NAMES


def _is_env_assign(token: str) -> bool:
    head, eq, _ = token.partition("=")
    return bool(eq) and head.replace("_", "a").isalnum() and not head[:1].isdigit()


def _first_positional(tokens: "list[str]") -> "str | None":
    for tok in tokens:
        if tok and not tok.startswith("-") and tok.lower() not in ("/c", "/k", "/s", "/q", "exec"):
            return tok
    return None


def _segment_launches_heavy(tokens: "list[str]", depth: int) -> bool:
    i = 0
    while i < len(tokens) and (tokens[i].lower() in _PASS_THROUGH or _is_env_assign(tokens[i])):
        i += 1
    if i >= len(tokens):
        return False
    head, rest = tokens[i], tokens[i + 1:]
    if _is_heavy(head):
        return True
    base = _base(head)
    if depth >= _MAX_DEPTH:
        return False
    if base in _PWSH_NAMES:
        for j, tok in enumerate(rest):
            low = tok.lower()
            if low in ("-file", "-f") and j + 1 < len(rest):
                return _is_heavy(rest[j + 1])
            if low in ("-command", "-c") and j + 1 < len(rest):
                return _launches_heavy(" ".join(rest[j + 1:]), depth + 1)
        return False
    if base in _PLAIN_INTERPRETERS:
        for j, tok in enumerate(rest):
            if tok.lower() in ("-c", "/c", "/k") and j + 1 < len(rest):
                return _launches_heavy(" ".join(rest[j + 1:]), depth + 1)
        target = _first_positional(rest)
        return target is not None and _is_heavy(target)
    return False


def _launches_heavy(cmd: str, depth: int = 0) -> bool:
    for tokens in _segments(cmd):
        if _segment_launches_heavy(tokens, depth):
            return True
        # Start-Process/start take the program as -FilePath or first positional.
        lowered = [t.lower() for t in tokens]
        if lowered and lowered[0] in ("start-process", "start") or (
            len(lowered) > 1 and lowered[0] == "&" and lowered[1] in ("start-process", "start")
        ):
            for j, low in enumerate(lowered):
                if low == "-filepath" and j + 1 < len(tokens) and _is_heavy(tokens[j + 1]):
                    return True
            positional = _first_positional(
                tokens[2 if lowered[0] == "&" else 1:]
            )
            if positional is not None and _is_heavy(positional):
                return True
    return False


_REASON = (
    "BLOCKED: Unreal build/editor launches are Group EM slot legs: return this step to the EM "
    "as a needs_slot leg; never run it from a subagent. A UBT build or editor run needs a "
    "capacity slot the Group EM grants, and a build must never overlap an editor run "
    "(AN-EXECUTOR-NEVER-FANS-OUT-HEAVY-RUNS). Author the change, report the compile as an EM "
    "leg, and stop there."
)


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("tool_name") not in _SHELL_TOOLS:
            return 0
        agent_id = data.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            return 0
        tool_input = data.get("tool_input")
        cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(cmd, str) or not cmd.strip():
            return 0
        if not _launches_heavy(cmd):
            return 0
        message = render(compose(_REASON, anchor=_WIKI_ANCHOR)) + "\n"
    except Exception:
        return 0
    sys.stderr.buffer.write(message.encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
