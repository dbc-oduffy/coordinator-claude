"""PreToolUse hook (matcher: Bash|PowerShell): deny a recursive grep over a repo root.

Box-poison class: concurrent `grep -rn X .` calls read whole repo trees, .git packs
included, and fill the file cache until the warm engine wedges. Tripwire
DENY-RECURSIVE-GREP-REPO-ROOT; there is no override, the alternatives are cheaper.

Denied, per pipeline segment (`|`, `||`, `&&`, `;`, `&`, newline; `bash -c`/`eval` bodies
are parsed too):
  - grep/egrep/fgrep with a recursive flag (-r, -R, inside a cluster such as -rn, --recursive,
    --dereference-recursive, -d recurse) whose target is `.`/`..`, no target, a drive or
    filesystem root, `~`/$HOME, a `*` glob inside a repo root, or a directory holding `.git`.
    --exclude-dir=.git does not save it; untracked scratch/archive/build trees are the cost.
  - The same recursive grep over 3+ existing directories at once, or over any target named
    like a known-large tree (corpus, node_modules, .venv, Intermediate, Saved, Binaries, ...).
  - `find <root>` with `-exec grep` or piped into `xargs grep`, unless -maxdepth is 0..2.
Allowed: a recursive grep scoped to one or two subdirectories holding no `.git`, non-recursive grep,
`git grep`, `rg`, a grep reading stdin. One stat per target; no walk.

Contract: stdin is the PreToolUse JSON; a deny is the hookSpecificOutput envelope on stdout,
exit 0. Fails open (silent exit 0) on anything unparseable or unresolvable.
"""

from __future__ import annotations

import json
import os
import re
import sys

TRIPWIRE = "DENY-RECURSIVE-GREP-REPO-ROOT"
_GREPS = {"grep", "egrep", "fgrep", "ggrep"}
_WRAPPERS = {"command", "builtin", "exec", "sudo", "nohup", "time", "env", "nice", "setsid",
             "timeout", "{", "!", "then", "do", "else", "if", "while", "until"}
_SHELLS = {"bash", "sh", "zsh", "dash", "pwsh", "powershell"}
_SHORT_ARG = set("efmABCdD")
_LONG_ARG = {"include", "exclude", "exclude-from", "exclude-dir", "file", "regexp", "max-count",
             "after-context", "before-context", "context", "label", "directories", "devices",
             "binary-files", "group-separator"}
_XARGS_ARG = set("IniPLdEsaJ")
_MAX_DIR_TARGETS = 3
_LARGE_TREES = {"corpus", "node_modules", ".venv", "venv", "intermediate", "deriveddatacache",
                "saved", "binaries"}
_ESCAPED = set(" \t\"';&|()<>$`")
_ROOTISH = re.compile(r"^(?:\.{1,2}[\\/]+)*\.{1,2}[\\/]*$")
_DRIVE_ROOT = re.compile(r"^(?:[A-Za-z]:)?[\\/]*$|^/[A-Za-z]/?$")
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


def _segments(text: str) -> list[tuple[str, list[str]]]:
    """[(separator-before, tokens)] with quotes stripped; quoted separators stay in tokens."""
    segs: list[tuple[str, list[str]]] = []
    tokens: list[str] = []
    cur: list[str] = []
    in_tok = False
    quote = ""
    sep = ""
    i, n = 0, len(text)

    def end_tok() -> None:
        nonlocal in_tok, cur
        if in_tok:
            tokens.append("".join(cur))
        cur, in_tok = [], False

    def end_seg(new_sep: str) -> None:
        nonlocal tokens, sep
        end_tok()
        if tokens:
            segs.append((sep, tokens))
        tokens, sep = [], new_sep

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
        elif c == "\n" or c == ";" or c in "()`":
            end_seg("")
        elif c == "|":
            if text[i + 1:i + 2] == "|":
                i += 1
                end_seg("||")
            else:
                end_seg("|")
        elif c == "&":
            if text[i + 1:i + 2] == "&":
                i += 1
                end_seg("&&")
            elif cur and cur[-1] in "<>" or (not in_tok and i + 1 < n and text[i + 1] == ">"):
                cur.append(c)
                in_tok = True
            else:
                end_seg("&")
        else:
            cur.append(c)
            in_tok = True
        i += 1
    end_seg("")
    return segs


def _head(tokens: list[str]) -> tuple[str, list[str]]:
    """Command name (basename) and its argv after env assignments and wrapper words."""
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
        elif _REDIR_ATTACHED.match(t):
            continue
        else:
            out.append(t)
    return out


def _grep_parse(args: list[str]) -> tuple[bool, list[str]]:
    """(recursive?, targets) for grep argv. Targets exclude the pattern and flag values."""
    recursive = False
    pattern_given = False
    positionals: list[str] = []
    i = 0
    only_pos = False
    while i < len(args):
        t = args[i]
        i += 1
        if only_pos or t == "-" or not t.startswith("-"):
            positionals.append(t)
        elif t == "--":
            only_pos = True
        elif t.startswith("--"):
            name, eq, val = t[2:].partition("=")
            if name in ("recursive", "dereference-recursive"):
                recursive = True
            if name in ("regexp", "file"):
                pattern_given = True
            if name in _LONG_ARG and not eq:
                val = args[i] if i < len(args) else ""
                i += 1
            if name == "directories" and val == "recurse":
                recursive = True
        else:
            j = 1
            while j < len(t):
                ch = t[j]
                if ch in "rR":
                    recursive = True
                elif ch in _SHORT_ARG:
                    val = t[j + 1:]
                    if not val:
                        val = args[i] if i < len(args) else ""
                        i += 1
                    if ch in "ef":
                        pattern_given = True
                    if ch == "d" and val == "recurse":
                        recursive = True
                    break
                j += 1
    return recursive, (positionals if pattern_given else positionals[1:])


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(/.*)?$", p)
        if m:
            p = f"{m.group(1).upper()}:{m.group(2) or '/'}"
    return p


def _holds_git(path: str) -> bool:
    return os.path.exists(os.path.join(path, ".git"))


def _root_target(target: str, cwd: str | None) -> bool:
    """True when grepping/finding from `target` is a repo-root / whole-tree walk."""
    if target == "":
        return False
    if _ROOTISH.match(target) or _DRIVE_ROOT.match(target):
        return True
    if target in ("~", "$HOME", "${HOME}", "$PWD", "${PWD}") or "--show-toplevel" in target:
        return True
    if "$" in target or "`" in target:
        return False
    p = _norm(target)
    if p == "~" or p.startswith("~/"):
        p = os.path.expanduser(p)
    base = p.rsplit("/", 1)[-1]
    if base in ("*", ".*"):
        parent = p[: len(p) - len(base)].rstrip("/") or ("/" if p.startswith("/") else ".")
        if parent in (".", ""):
            return _resolve_holds_git(".", cwd)
        return _root_target(parent, cwd)
    return _resolve_holds_git(p, cwd)


def _resolve_holds_git(p: str, cwd: str | None) -> bool:
    try:
        if not os.path.isabs(p):
            if not cwd:
                return False
            p = os.path.join(_norm(cwd), p)
        return _holds_git(p)
    except (OSError, ValueError):
        return False


def _large_name(target: str) -> bool:
    if "$" in target or "`" in target:
        return False
    return _norm(target).rstrip("/").rsplit("/", 1)[-1].lower() in _LARGE_TREES


def _dir_target(target: str, cwd: str | None) -> bool:
    """True when `target` is an existing directory (one stat)."""
    if not target or "$" in target or "`" in target or any(c in target for c in "*?["):
        return False
    try:
        p = _norm(target)
        if p == "~" or p.startswith("~/"):
            p = os.path.expanduser(p)
        if not os.path.isabs(p):
            if not cwd:
                return False
            p = os.path.join(_norm(cwd), p)
        return os.path.isdir(p)
    except (OSError, ValueError):
        return False


def _storm_label(targets: list[str], cwd: str | None) -> str | None:
    """Deny label for a recursive grep whose target set is large without naming a root."""
    if any(_large_name(t) for t in targets):
        return "recursive grep over a known-large tree"
    if sum(1 for t in targets if _dir_target(t, cwd)) >= _MAX_DIR_TARGETS:
        return f"recursive grep over {_MAX_DIR_TARGETS}+ directories at once"
    return None


def _shallow_find(args: list[str]) -> bool:
    for i, t in enumerate(args[:-1]):
        if t == "-maxdepth" and args[i + 1].isdigit():
            return int(args[i + 1]) <= 2
    return False


def _find_roots(args: list[str]) -> list[str]:
    roots: list[str] = []
    for t in args:
        if t in ("-H", "-L", "-P", "-E", "-X", "-x", "-d", "-s"):
            continue
        if t.startswith(("-", "!", ",")):
            break
        roots.append(t)
    return roots or ["."]


def _walks_root(args: list[str], cwd: str | None) -> bool:
    return not _shallow_find(args) and any(_root_target(r, cwd) for r in _find_roots(args))


def _check_argv(name: str, args: list[str], cwd: str | None, prev: tuple[str, str, list[str]],
                depth: int) -> str | None:
    """Deny label for one command, or None. `prev` = (separator, name, args) of the prior segment."""
    if name in _GREPS:
        recursive, targets = _grep_parse(_drop_redirects(args))
        if recursive and (not targets or any(_root_target(t, cwd) for t in targets)):
            return "recursive grep over a repo root"
        if recursive:
            return _storm_label(targets, cwd)
        return None
    if name == "find":
        for k, t in enumerate(args):
            if t in ("-exec", "-execdir", "-ok", "-okdir") and k + 1 < len(args):
                inner = re.split(r"[\\/]", args[k + 1])[-1].lower().removesuffix(".exe")
                if inner in _GREPS and _walks_root(args, cwd):
                    return "find over a repo root running grep on every file"
        return None
    if name == "xargs":
        rest = _xargs_command(args)
        inner_name, inner_args = _head(rest)
        if inner_name in _GREPS:
            if prev[0] == "|" and prev[1] == "find" and _walks_root(prev[2], cwd):
                return "find over a repo root piped into xargs grep"
            return _check_argv(inner_name, inner_args, cwd, ("", "", []), depth)
        return None
    if name in _SHELLS and depth < 3:
        for k, t in enumerate(args[:-1]):
            if re.match(r"^-[A-Za-z]*c$", t) or t.lower() in ("-command", "-c"):
                return _check_text(args[k + 1], cwd, depth + 1)
        return None
    if name == "eval" and depth < 3:
        return _check_text(" ".join(args), cwd, depth + 1)
    return None


def _xargs_command(args: list[str]) -> list[str]:
    i = 0
    while i < len(args) and args[i].startswith("-") and len(args[i]) > 1:
        t = args[i]
        i += 1
        if t[1] in _XARGS_ARG and len(t) == 2:
            i += 1
    return args[i:]


def _check_text(command: str, cwd: str | None, depth: int = 0) -> str | None:
    prev: tuple[str, str, list[str]] = ("", "", [])
    for sep, tokens in _segments(_strip_heredocs(command)):
        name, args = _head(tokens)
        if not name:
            continue
        label = _check_argv(name, args, cwd, (sep, prev[1], prev[2]) if sep == "|" else ("", "", []), depth)
        if label:
            return label
        prev = (sep, name, _drop_redirects(args))
    return None


def _deny_reason(label: str, command: str) -> str:
    snippet = " ".join(command.split())[:140]
    return (
        f"[guard] {TRIPWIRE}: {label} is denied. Grep storms (many `grep -r` reading whole repo "
        f"trees, .git packs included) fill the file cache and wedge the box; this is a standing "
        f"box-poison class, not a style note. Command: {snippet}\n"
        "Use instead: `git grep <pattern> -- <pathspec>` (tracked files only; works in every session "
        "and every dispatched subagent); or `rg <pattern> <subpath>` (honours .gitignore). Sessions "
        "that hold the Grep tool (not all dispatched subagents do) may use it too. A recursive grep "
        "scoped to one or two small subdirectories that hold no .git still runs, e.g. `grep -rn X coordinator/hooks`. "
        f"--exclude-dir=.git does not lift the deny. Tripwire: {TRIPWIRE}."
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str) or "grep" not in command:
            return 0
        cwd = payload.get("cwd")
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        label = _check_text(command, cwd)
        if not label:
            return 0
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _deny_reason(label, command),
        }}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
