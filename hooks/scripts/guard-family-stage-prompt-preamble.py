"""PreToolUse hook (matcher: Bash|PowerShell): deny a codex/agy/grok stage call whose prompt lacks the WORKER ROLE preamble.

Tripwire DENY-FAMILY-STAGE-PROMPT-WITHOUT-PREAMBLE. The vendor CLIs load EM-session role files
(`~/.codex/AGENTS.md`); a prompt that does not lead with the preamble makes the worker act as an EM.
The prompt is built by `scripts/family_stage_prompt.py`, the one source of the preamble text.
Per statement (`;`, `&&`, `||`, `|`, `&`, newline), with the vendor name in command position only:
  - `codex exec ... - < <file>`: the stdin file is read; no resolvable file (argv prompt, pipe,
    heredoc) is denied.
  - `codex-exec-windows --prompt <file>` (the engine bin, any of .exe/.cmd/.py): the file is read.
  - `grok ... --prompt-file <file>`: the file is read.
  - `agy -p=<v>` / `agy -p <v>`: `<v>` is literal text, or `$(cat <file>)` / `$(Get-Content -Raw <file>)`.
A call carrying --help, -h or --version, and a path built from a variable, are allowed. A literal
prompt file that does not exist yet is allowed only when `family_stage_prompt.py --out` builds it
earlier in the same command; otherwise it is denied. `bash -c`/`pwsh -Command` bodies are parsed too.

A headless EM is exempt: a vendor statement whose COORDINATOR_SESSION_ID and
COORDINATOR_ALLOW_HEADLESS_EM_TOKEN (inline `VAR=v`, an earlier `export VAR=v` or `$env:VAR = v`, or
this hook's own env) match the grant headless-em-launch.py wrote for that session and family. An EM
prompt leads with no WORKER preamble by design; the launcher's grant is the EM-vs-worker boundary
(A-HEADLESS-EM-WITHOUT-THE-LAUNCHER-GRANT-IS-A-WORKER). The grant check is the engine's own
`headless_em_grant_matches`; when the engine cannot load, the exemption fails closed.

Cost: an in-process regex prefilter returns at once for a command naming none of the three vendors.
Override: COORDINATOR_ALLOW_FAMILY_STAGE_PROMPT_WITHOUT_PREAMBLE=1 in the hook environment
(guard-override-keys convention); the deny text never names it.

Contract: stdin is the PreToolUse JSON; a deny is the hookSpecificOutput envelope on stdout,
exit 0. Fails open (silent exit 0) on anything unparseable or unresolvable; a missing builder
module fails open with one stderr line.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

TRIPWIRE = "DENY-FAMILY-STAGE-PROMPT-WITHOUT-PREAMBLE"
OVERRIDE_KEY = "COORDINATOR_ALLOW_FAMILY_STAGE_PROMPT_WITHOUT_PREAMBLE"
_READ_BYTES = 8192
_MAX_DEPTH = 2

_PREFILTER = re.compile(r"codex|agy|grok", re.I)
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAP = {"sudo", "env", "nohup", "time", "command", "exec", "timeout", "nice", "call", "start",
         "then", "do", "else", "if", "while", "until", "!", "setsid"}
_INTERPRETERS = {"python", "python3", "py"}
_SHELLS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell", "cmd"}
_BODY_FLAGS = {"-c", "-command", "/c", "/k"}
_HELP = {"--help", "-h", "--version"}
_CODEX_VALUE_FLAGS = {"-c", "--config", "-m", "--model", "-p", "--profile", "-C", "--cd", "-s",
                      "--sandbox", "-i", "--image"}
_WINDOWS_WRAPPER = "codex-exec-windows"
_WRAPPER_SUFFIXES = ("", ".exe", ".cmd", ".py")
_CAT_NAMES = {"cat", "get-content", "gc", "type"}
_CAT_VALUE_FLAGS = {"-encoding", "-readcount", "-totalcount", "-tail", "-first"}
_SUBST = re.compile(r"^\$\(\s*(.*?)\s*\)$", re.S)
SESSION_ENV = "COORDINATOR_SESSION_ID"
GRANT_ENV = "COORDINATOR_ALLOW_HEADLESS_EM_TOKEN"
_PS_ENV = re.compile(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$", re.I)
_GRANT_FAMILIES = {"codex", "agy", "grok"}


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
    """Quote-aware split into statements of dequoted tokens; `$(...)` and quotes stay inside a token."""
    stmts: list[list[str]] = []
    tokens: list[str] = []
    buf: list[str] = []
    have = False
    quote = ""
    depth = 0
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
            if c == quote:
                quote = ""
            else:
                buf.append(c)
                if quote == '"' and c == "$" and text[i + 1:i + 2] == "(":
                    depth += 1
                    buf.append("(")
                    i += 1
                elif depth and c == ")":
                    depth -= 1
            i += 1
            continue
        if c in "'\"":
            quote = c
            have = True
        elif depth:
            buf.append(c)
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
        elif c == "$" and text[i + 1:i + 2] == "(":
            buf.append("$(")
            have = True
            depth = 1
            i += 1
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


def _head(tokens: list[str]) -> tuple[str, str, list[str]]:
    """(command basename, raw command token, argv) after env assignments and wrapper words."""
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
        else:
            break
    if i >= n:
        return "", "", []
    name = re.split(r"[\\/]", tokens[i])[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name, tokens[i], tokens[i + 1:]


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(/.*)?$", p)
        if m:
            p = f"{m.group(1).upper()}:{m.group(2) or '/'}"
    return p


def _resolve(path: str, cwd: str) -> str | None:
    """Absolute form of a literal path; None for a variable, glob or empty path."""
    if not path or "$" in path or "`" in path or any(c in path for c in "*?["):
        return None
    p = _norm(path)
    if p == "~" or p.startswith("~/"):
        p = os.path.expanduser(p)
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(_norm(cwd), p))


# Prompt files the builder writes earlier in the command under check. A literal prompt path that
# does not exist yet is allowed only when it is one of these: a prompt written by hand in the same
# call (printf > file, then codex) would otherwise escape the check because the file is absent at
# hook time.
_BUILT_HERE: set[str] = set()


def _read_head(path: str, cwd: str) -> str | None:
    """First bytes of the file at `path`, or None when it is a variable path or cannot be read."""
    p = _resolve(path, cwd)
    if p is None:
        return None
    try:
        with open(p, "rb") as fh:
            return fh.read(_READ_BYTES).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def _flag_value(args: list[str], names: tuple[str, ...]) -> tuple[bool, str | None]:
    """(flag present, its value) for `-p v`, `-p=v` or `-p:v` style flags, case-insensitive."""
    for idx, a in enumerate(args):
        low = a.lower()
        for name in names:
            if low == name:
                nxt = args[idx + 1] if idx + 1 < len(args) else None
                return True, (nxt if nxt is not None and not nxt.startswith("-") else None)
            if low.startswith(name + "=") or low.startswith(name + ":"):
                return True, a[len(name) + 1:]
    return False, None


def _stdin_file(args: list[str]) -> str | None:
    for idx, a in enumerate(args):
        if a.startswith("<") and not a.startswith("<<"):
            rest = a[1:]
            if rest:
                return rest
            return args[idx + 1] if idx + 1 < len(args) else None
    return None


def _cat_file(inner: str) -> str | None:
    """File named by the body of `$(cat f)` / `$(Get-Content -Raw f)`, or None for anything else."""
    stmts = _statements(inner)
    if len(stmts) != 1:
        return None
    toks = stmts[0]
    if toks[0].lower() not in _CAT_NAMES:
        return None
    rest = toks[1:]
    i = 0
    while i < len(rest):
        low = rest[i].lower()
        if low in ("-path", "-literalpath") and i + 1 < len(rest):
            return rest[i + 1]
        if low in _CAT_VALUE_FLAGS:
            i += 2
            continue
        if rest[i].startswith("-"):
            i += 1
            continue
        return rest[i]
    return None


def _codex_is_exec(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-"):
            i += 2 if a in _CODEX_VALUE_FLAGS else 1
            continue
        return a in ("exec", "e")
    return False


_starts_with_preamble = None


def _verdicts(tokens: list[str], cwd: str) -> tuple[str, str] | None:
    """(kind, detail) when a vendor call in this statement lacks the preamble, else None."""
    name, raw, args = _head(tokens)
    if not name:
        return None
    if _is_wrapper(raw):
        return _check_windows_wrapper(args, cwd)
    if name == "codex" and _codex_is_exec(args):
        return _check_codex(args, cwd)
    if name == "grok":
        return _check_grok(args, cwd)
    if name == "agy":
        return _check_agy(args, cwd)
    return None


def _check_windows_wrapper(args: list[str], cwd: str) -> tuple[str, str] | None:
    present, value = _flag_value(args, ("--prompt",))
    if not present or value is None:
        return None
    return _judge_file("codex-exec-windows --prompt", value, cwd)


def _is_wrapper(token: str) -> bool:
    base = token.replace(chr(92), "/").rsplit("/", 1)[-1].lower()
    return any(base == _WINDOWS_WRAPPER + sfx for sfx in _WRAPPER_SUFFIXES)


def _check_codex(args: list[str], cwd: str) -> tuple[str, str] | None:
    path = _stdin_file(args)
    if path is None:
        return ("codex exec", "no stdin prompt file: the prompt is on argv, a pipe or a heredoc")
    return _judge_file("codex exec", path, cwd)


def _check_grok(args: list[str], cwd: str) -> tuple[str, str] | None:
    present, value = _flag_value(args, ("--prompt-file",))
    if not present or value is None:
        return None
    return _judge_file("grok --prompt-file", value, cwd)


def _check_agy(args: list[str], cwd: str) -> tuple[str, str] | None:
    present, value = _flag_value(args, ("-p", "--prompt"))
    if not present or value is None:
        return None
    sub = _SUBST.match(value)
    if sub:
        path = _cat_file(sub.group(1))
        if path is None:
            return ("agy -p", "the prompt is a command substitution that does not read one file")
        return _judge_file("agy -p", path, cwd)
    if _starts_with_preamble(value):
        return None
    return ("agy -p", "the prompt text does not start with the preamble")


def _judge_file(label: str, path: str, cwd: str) -> tuple[str, str] | None:
    head = _read_head(path, cwd)
    if head is None:
        resolved = _resolve(path, cwd)
        if resolved is None or os.path.exists(resolved) or resolved in _BUILT_HERE:
            return None
        return (label, f"prompt file {path} does not exist when the call is checked and nothing "
                "earlier in the command builds it")
    if _starts_with_preamble(head):
        return None
    return (label, f"prompt file {path} does not start with the preamble")


def _load_builder() -> bool:
    """Bind the C1 builder's starts_with_preamble; False (with one stderr line) when it cannot load."""
    global _starts_with_preamble
    if _starts_with_preamble is not None:
        return True
    try:
        path = Path(__file__).resolve().parents[2] / "scripts" / "family_stage_prompt.py"
        spec = importlib.util.spec_from_file_location("family_stage_prompt_builder", path)
        if spec is None or spec.loader is None:
            raise ImportError(str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _starts_with_preamble = module.starts_with_preamble
        return True
    except Exception:
        sys.stderr.write(
            "guard-family-stage-prompt-preamble: scripts/family_stage_prompt.py missing or "
            "unimportable, guard fails open\n")
        return False


def _scan_shell_args(args: list[str], cwd: str, depth: int, env: dict[str, str]) -> tuple[str, str] | None:
    """A `-c`/`-Command`//c body passed to a shell."""
    for idx, a in enumerate(args):
        if a.lower() in _BODY_FLAGS and idx + 1 < len(args) and depth < _MAX_DEPTH:
            return _scan(args[idx + 1], cwd, depth + 1, env)
    return None


def _assignments(tokens: list[str]) -> dict[str, str]:
    """Env values a statement sets for the rest of the command: `export V=x`, `$env:V = x`, `$env:V=x`."""
    if not tokens:
        return {}
    m = _PS_ENV.match(tokens[0])
    if m:
        if m.group(2) is not None:
            return {m.group(1): m.group(2)}
        if len(tokens) >= 3 and tokens[1] == "=":
            return {m.group(1): tokens[2]}
        return {}
    if tokens[0] in ("export", "set"):
        return dict(a.split("=", 1) for a in tokens[1:] if _ENV.match(a))
    if all(_ENV.match(a) for a in tokens):
        return dict(a.split("=", 1) for a in tokens)
    return {}


def _inline_env(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for a in tokens:
        if _ENV.match(a):
            k, v = a.split("=", 1)
            out[k] = v
        elif a not in _WRAP:
            break
    return out


def _grant_holds(env: dict[str, str], family: str) -> bool:
    """True only when the engine confirms a launcher grant for (session, family); False on any doubt."""
    sid, token = env.get(SESSION_ENV), env.get(GRANT_ENV)
    if family not in _GRANT_FAMILIES or not sid or not token or "$" in sid or "$" in token:
        return False
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _engine_root import resolve_claude_klabauter_root
        root = resolve_claude_klabauter_root()
        if not root:
            return False
        from _engine_root import place_engine_root_on_path
        place_engine_root_on_path(root)
        from coordinator_core.ops.workflow_fire.headless_em_grant import headless_em_grant_matches
        return bool(headless_em_grant_matches({GRANT_ENV: token}, sid, family))
    except Exception:
        return False


def _scan(command: str, cwd: str, depth: int = 0, env: dict[str, str] | None = None) -> tuple[str, str] | None:
    env = dict(env if env is not None else {k: os.environ[k] for k in (SESSION_ENV, GRANT_ENV) if k in os.environ})
    for tokens in _statements(_strip_heredocs(command)):
        set_here = _assignments(tokens)
        if set_here:
            env.update(set_here)
            continue
        name, _raw, args = _head(tokens)
        if name in ("cd", "set-location", "sl") and args and not args[0].startswith("-"):
            base = _norm(args[0])
            cwd = base if os.path.isabs(base) else os.path.join(_norm(cwd), base)
            continue
        if any(t.replace("\\", "/").endswith("family_stage_prompt.py") for t in tokens):
            present, out = _flag_value(tokens, ("--out",))
            built = _resolve(out, cwd) if present and out else None
            if built:
                _BUILT_HERE.add(built)
            continue
        if name in _SHELLS:
            hit = _scan_shell_args(args, cwd, depth, {**env, **_inline_env(tokens)})
            if hit:
                return hit
            continue
        if any(a in _HELP for a in args):
            continue
        family = _family(name, _raw)
        if name in _INTERPRETERS:
            hit = _interpreted_wrapper(args, cwd)
            family = "codex"
        else:
            hit = _verdicts(tokens, cwd)
        if hit and _grant_holds({**env, **_inline_env(tokens)}, family):
            continue
        if hit:
            return hit
    return None


def _interpreted_wrapper(args: list[str], cwd: str) -> tuple[str, str] | None:
    """`python [-flags] codex-exec-windows.py --prompt <file> ...`; any other script is not ours."""
    for idx, a in enumerate(args):
        if a.startswith("-"):
            continue
        return _check_windows_wrapper(args[idx + 1:], cwd) if _is_wrapper(a) else None
    return None


def _family(name: str, raw: str) -> str:
    if name == "codex" or _is_wrapper(raw):
        return "codex"
    return name


def _deny_reason(kind: str, detail: str, command: str) -> str:
    snippet = " ".join(command.split())[:140]
    return (
        f"[guard] {TRIPWIRE}: {kind} is denied: {detail}. A non-Claude worker loads EM-session role "
        "files (~/.codex/AGENTS.md) and acts as an EM unless its prompt leads with the WORKER ROLE "
        f"preamble. Command: {snippet}\n"
        "Use instead: build the prompt with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/family_stage_prompt.py "
        "--family <codex|agy|grok> --brief <brief file> --out <prompt file>`, never write the prompt by "
        "hand, and feed that built file to the CLI (codex: `- < <prompt>`; grok: `--prompt-file <prompt>`; "
        "agy: `-p=\"$(cat <prompt>)\"`). See the tripwire-registry page "
        f"deny-family-stage-prompt-without-preamble. Tripwire: {TRIPWIRE}."
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
        if not _load_builder():
            return 0
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        _BUILT_HERE.clear()
        hit = _scan(command, cwd)
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
