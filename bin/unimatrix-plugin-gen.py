#!/usr/bin/env python3
"""Deterministic coordinator-plugin to host-plugin tree translator, driven by unimatrix-host-map.json.

`generate(plugin_root, out_dir, host)` reads a Claude plugin source tree and writes the host's
plugin tree: same inputs give the same bytes on every OS (pathlib only, sorted traversal, LF text,
no symlinks). Anything the host table cannot translate is listed in UNMAPPED.json at the tree root.
Stdlib only; no subprocess, no LLM step.

agy hooks.json is a top-level object keyed by hook name, each value {"<Event>": [...]} (shape from
the agy 1.4.12 strict-validate relay; no agy doc on the build box). `agy plugin validate` proves the
file loads, not that a hook fires: ${PLUGIN_ROOT} expansion and a guard running need a live agy
session, which nothing here covers.
"""
import json
import os
import posixpath
import re
import shlex
import shutil
from pathlib import Path

TABLE_NAME = "unimatrix-host-map.json"
UNMAPPED_NAME = "UNMAPPED.json"
TOKEN_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}|\$CLAUDE_PLUGIN_ROOT\b")
TOOL_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SKIP_NAMES = frozenset({"__pycache__", ".DS_Store", ".git"})
DOCTRINE_SOURCES = ("global-doctrine/CLAUDE.md", "global-doctrine/rules/rules.md")
NO_MAP = "host has no mapping table entry"


def load_table():
    """The per-host mapping table, read from beside this file."""
    return json.loads((Path(__file__).resolve().with_name(TABLE_NAME)).read_text(encoding="utf-8"))


def _is_text(data) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _lf(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text if not text or text.endswith("\n") else text + "\n"


def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _walk(root):
    """Files under root as (posix rel path, Path), sorted by rel path; symlinks and junk are skipped."""
    found = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if SKIP_NAMES & set(rel.parts) or p.suffix == ".pyc" or p.is_symlink() or not p.is_file():
            continue
        found.append((rel.as_posix(), p))
    return sorted(found, key=lambda t: t[0])


def _split_frontmatter(text):
    """(frontmatter lines, body) for a leading `---` block, else (None, text)."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], "\n".join(lines[i + 1:])
    return None, text


def _join_frontmatter(head, body):
    return "---\n" + "\n".join(head) + "\n---\n" + body.lstrip("\n") if head else body


def _field(head, key):
    for i, line in enumerate(head):
        if re.match(rf"{re.escape(key)}\s*:", line):
            return i, line.split(":", 1)[1].strip().strip("\"'")
    return None, None


def _ensure_description(head, body, fallback) -> None:
    """Add a one-line `description:` (first prose line of body, else fallback) when absent or empty; agy skips an item without one."""
    i, val = _field(head, "description")
    if val:
        return
    if i is not None:
        del head[i]
    first = next((ln.strip().lstrip("#>-* ").strip() for ln in body.split("\n")
                  if ln.strip().lstrip("#>-* ").strip()), "") or fallback
    head.append(f"description: {json.dumps(first[:200], ensure_ascii=False)}")


class _Plan:
    """Collects translated files and the unmapped report; writes nothing until finished."""

    def __init__(self, cfg, token_suffixes) -> None:
        self.cfg = cfg
        self.files = {}
        self.unmapped = set()
        self.suffixes = tuple(token_suffixes)

    def miss(self, kind, source, reason) -> None:
        self.unmapped.add((kind, source, reason))

    def put(self, rel, data, kind, source) -> bool:
        if rel in self.files:
            self.miss(kind, source, f"output path {rel} already produced by another source")
            return False
        self.files[rel] = data
        return True

    def rewrite(self, text) -> str:
        return TOKEN_RE.sub(lambda _m: self.cfg["plugin_root_token"], text)

    def put_file(self, rel, src_path, kind, source) -> bool:
        """Copy one source file; text is LF-normalised and gets the plugin-root token rewritten."""
        data = src_path.read_bytes()
        if _is_text(data):
            text = _lf(data.decode("utf-8"))
            if rel.endswith(self.suffixes):
                text = self.rewrite(text)
            data = text.encode("utf-8")
        return self.put(rel, data, kind, source)


def _doctrine_text(plugin_root):
    base = plugin_root
    for root in (base.parent, base, base.parent / "templates", base / "templates"):
        if (root / DOCTRINE_SOURCES[0]).is_file():
            parts = [_lf((root / s).read_text(encoding="utf-8")) for s in DOCTRINE_SOURCES if (root / s).is_file()]
            return "\n".join(parts)
    return None


def _inventory(plugin_root):
    """(kind, rel source) of every translatable item, for a host whose table is empty."""
    items = []
    for kind, sub in (("agent", "agents"), ("command", "commands")):
        d = plugin_root / sub
        if d.is_dir():
            items += [(kind, f"{sub}/{rel}") for rel, _ in _walk(d) if rel.endswith(".md")]
    skills = plugin_root / "skills"
    if skills.is_dir():
        items += [("skill", f"skills/{c.name}") for c in sorted(skills.iterdir(), key=lambda c: c.name)
                  if not c.is_symlink()]
    if (plugin_root / "hooks" / "hooks.json").is_file():
        items.append(("hooks", "hooks/hooks.json"))
    if _doctrine_text(plugin_root) is not None:
        items.append(("rules", DOCTRINE_SOURCES[0]))
    return items


def _map_model(value, cfg):
    """(agy tier, None) or (None, reason)."""
    tiers = cfg["tiers"]
    if value in tiers:
        if tiers[value] is None:
            return None, f"tier {value!r} has no agy value"
        return tiers[value], None
    if value in cfg["valid_tiers"]:
        return value, None
    return None, f"model {value!r} is not a known tier"


def _map_agent_tools(head, src, plan) -> None:
    """Rewrite `tools:` (inline list, comma string or block list) to agy native names; an unmapped name is dropped and reported, an emptied list drops the key."""
    i, _ = _field(head, "tools")
    if i is None:
        return
    end = i + 1
    while end < len(head) and re.match(r"\s+\S|\s*-\s", head[end]):
        end += 1
    raw = " ".join([head[i].split(":", 1)[1]] + [ln.strip().lstrip("-") for ln in head[i + 1:end]])
    names = [t.strip().strip("\"'") for t in raw.strip().strip("[]").replace(",", " ").split()]
    mapped = []
    for t in names:
        native = plan.cfg["tools"].get(t)
        if native is None:
            plan.miss("agent-tool", src, f"tool {t!r} has no agy name; dropped")
        elif native not in mapped:
            mapped.append(native)
    head[i:end] = [f"tools: [{', '.join(mapped)}]"] if mapped else []


def _agents(plan, plugin_root) -> None:
    d = plugin_root / "agents"
    if not d.is_dir():
        return
    for rel, p in _walk(d):
        src = f"agents/{rel}"
        if not rel.endswith(".md"):
            plan.miss("agent", src, "not a markdown agent file")
            continue
        text = plan.rewrite(_lf(p.read_text(encoding="utf-8")))
        head, body = _split_frontmatter(text)
        head = list(head or [])
        i, val = _field(head, "model")
        if i is not None:
            new, reason = _map_model(val, plan.cfg)
            if new is None:
                del head[i]
                plan.miss("agent-model", src, reason)
            else:
                head[i] = f"model: {new}"
        _map_agent_tools(head, src, plan)
        _ensure_description(head, body, _field(head, "name")[1] or Path(rel).stem)
        text = _join_frontmatter(head, body)
        plan.put(src, text.encode("utf-8"), "agent", src)


def _command_skills(plan, plugin_root) -> None:
    d = plugin_root / "commands"
    if not d.is_dir():
        return
    for rel, p in _walk(d):
        src = f"commands/{rel}"
        if not rel.endswith(".md"):
            plan.miss("command", src, "not a markdown command file")
            continue
        if not plan.cfg["commands_to_skills"]:
            plan.miss("command", src, "host has no command surface")
            continue
        name = "-".join(Path(rel[:-3]).parts)
        out = f"skills/{name}/SKILL.md"
        head, body = _split_frontmatter(plan.rewrite(_lf(p.read_text(encoding="utf-8"))))
        head = list(head or [])
        i, _ = _field(head, "name")
        if i is None:
            head.insert(0, f"name: {name}")
        else:
            head[i] = f"name: {name}"
        _ensure_description(head, body, name)
        _put_skill_md(plan, out, _join_frontmatter(head, body), src)


def _put_skill_md(plan, out, text, src) -> None:
    data = text.encode("utf-8")
    cap = plan.cfg["max_text_bytes"]
    if len(data) > cap:
        plan.miss("oversize", src, f"{len(data)} bytes exceeds the {cap}-byte cap")
        return
    plan.put(out, data, "skill", src)


def _skills(plan, plugin_root) -> None:
    d = plugin_root / "skills"
    if not d.is_dir():
        return
    for child in sorted(d.iterdir(), key=lambda c: c.name):
        src = f"skills/{child.name}"
        if child.is_symlink() or SKIP_NAMES & {child.name}:
            continue
        if not child.is_dir() or not (child / "SKILL.md").is_file():
            plan.miss("skill", src, "not a directory holding SKILL.md")
            continue
        text = plan.rewrite(_lf((child / "SKILL.md").read_text(encoding="utf-8")))
        head, body = _split_frontmatter(text)
        head = list(head or [])
        i, name = _field(head, "name")
        name = name or child.name
        if i is None:
            head.insert(0, f"name: {name}")
        out_dir = f"skills/{name}"
        _put_skill_md(plan, f"{out_dir}/SKILL.md", _join_frontmatter(head, body), f"{src}/SKILL.md")
        for rel, p in _walk(child):
            if rel != "SKILL.md":
                plan.put_file(f"{out_dir}/{rel}", p, "skill-file", f"{src}/{rel}")


def _hook_matcher(matcher, event, plan):
    mapped = []
    for tok in matcher.split("|"):
        t = tok.strip()
        if t in plan.cfg["tools"]:
            mapped.append(plan.cfg["tools"][t])
            continue
        if TOOL_NAME_RE.fullmatch(t):
            plan.miss("matcher", "hooks/hooks.json", f"{event}: tool {t!r} has no agy name")
        mapped.append(t)
    return "|".join(mapped)


def _flatten_groups(groups, event, plan):
    """agy takes bare command handlers for a non-tool event; a matcher/hooks group is rejected whole."""
    flat = []
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("hooks"), list):
            if "matcher" in group:
                plan.miss("matcher", "hooks/hooks.json", f"{event}: matcher {group['matcher']!r} dropped; agy {event} takes none")
            flat += group["hooks"]
        else:
            flat.append(group)
    return flat


def _hook_name(event) -> str:
    """agy hook name for one event's handlers: the event in kebab case (PreToolUse -> pre-tool-use)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", event).lower()


SHIM_REL = "hooks/agy-hook-run.py"
GUARD_REL = "unimatrix-host-guard.py"
SHIM_SOURCE = '''"""agy hook launcher: runs the settings-home hook-run door with stdin mode `hook`, shell-neutral.

argv: [--quiet] [--pass-2] [--host-guard <guard.py> --host agy] <hook-run args...>. --quiet drops the door's
stderr; --pass-2 maps its exit 2 to 0; --host-guard first asks the host guard (shim, agy adapter, DIY nag)
and answers with its deny or reasoned ask, else falls through to the door.
An agy tool event (payload carries `toolCall`) is translated to the Claude shape for the door and the
door's verdict back to an explicit agy decision (agy fails closed on `{}`); any other payload passes whole.
"""
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path


RESULT_KEYS = ("toolResult", "toolOutput", "toolResponse", "result", "output")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def settings_home():
    return Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")


def _read_registry_text(path):
    """Registry text without blocking a concurrent replace; plain read only while no engine is importable."""
    try:
        from coordinator_core.shared_read import read_bytes_shared
    except ImportError:
        return path.read_text(encoding="utf-8")
    return read_bytes_shared(path).decode("utf-8")


def engine_root():
    """Published engine root: COORDINATOR_ENGINE_ROOT, else registry key repos.claude_klabauter; None on a miss."""
    env = os.environ.get("COORDINATOR_ENGINE_ROOT")
    if env and Path(env).is_dir():
        return env
    ml = Path(os.environ.get("MACHINE_LOCAL_REGISTRY_DIR") or settings_home() / "machine-local")
    root = None
    for name in ("registry.toml", "registry.local.toml"):
        try:
            data = tomllib.loads(_read_registry_text(ml / name))
        except (OSError, ValueError):
            continue
        repos = data.get("repos")
        root = (repos.get("claude_klabauter") if isinstance(repos, dict) else None) or data.get("repos.claude_klabauter") or root
    return root if root and (Path(root) / "coordinator_core").is_dir() else None


def guard_answer(payload, guard, host):
    """The host guard's answer when it is a deny or an ask carrying a reason, else None (fall through to the door)."""
    guard = Path(guard)
    if not guard.is_file():
        guard = settings_home() / "unimatrix" / guard.name
    root = engine_root()
    if not (root and guard.is_file()):
        return None
    try:
        res = subprocess.run([sys.executable, str(guard), "--host", host, "--engine-root", root], input=payload,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        answer = json.loads(res.stdout)
    except (OSError, ValueError):
        return None
    if not isinstance(answer, dict) or res.returncode != 0:
        return None
    if answer.get("decision") == "deny" or (answer.get("decision") == "ask" and answer.get("reason")):
        return answer
    return None


def agy_event(p):
    """The hook event of an agy tool payload: its own name, else PostToolUse when it carries a tool result."""
    name = p.get("hookEventName") or p.get("hook_event_name")
    if name:
        return str(name)
    return "PostToolUse" if any(k in p for k in RESULT_KEYS) else "PreToolUse"


def to_claude(raw):
    """(payload bytes for the door, True) for an agy `toolCall` event, else (raw, False)."""
    try:
        p = json.loads(raw)
    except ValueError:
        return raw, False
    call = p.get("toolCall") if isinstance(p, dict) else None
    if not isinstance(call, dict):
        return raw, False
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    name = str(call.get("name") or "")
    if name == "run_command":
        name, args = "Bash", {"command": str(args.get("CommandLine") or "")}
    ws = p.get("workspacePaths")
    cwd = str(ws[0]) if isinstance(ws, list) and ws else p.get("cwd") if isinstance(p.get("cwd"), str) else ""
    out = {"hook_event_name": agy_event(p),
           "session_id": str(p.get("conversationId") or "") or None, "cwd": cwd or None,
           "tool_name": name, "tool_input": args}
    return json.dumps(out).encode("utf-8"), True


def to_agy(rc, out, err):
    """The agy decision object for a door answer: deny and ask carry a reason, anything else is an explicit allow."""
    try:
        v = json.loads(out) if out.strip() else {}
    except ValueError:
        v = {}
    v = dict(v) if isinstance(v, dict) else {}
    nested = v.get("hookSpecificOutput")
    if isinstance(nested, dict):
        v.update(nested)
    decision = str(v.get("permissionDecision") or v.get("decision") or "")
    reason = str(v.get("permissionDecisionReason") or v.get("reason") or "").strip()
    if decision in ("deny", "block") or (rc == 2 and not decision):
        return {"decision": "deny", "reason": reason or err.strip() or "denied by coordinator guard"}
    if decision in ("ask", "force_ask"):
        return {"decision": decision, "reason": reason or "coordinator: confirm"}
    return {"decision": "allow"}


def main(argv):
    quiet = "--quiet" in argv
    pass_2 = "--pass-2" in argv
    guard = argv[argv.index("--host-guard") + 1] if "--host-guard" in argv[:-1] else None
    host = argv[argv.index("--host") + 1] if "--host" in argv[:-1] else "agy"
    skip = {"--quiet", "--pass-2"}
    if guard:
        skip |= {"--host-guard", guard, "--host", host}
    rest = [a for a in argv if a not in skip]
    door = settings_home() / "bin" / ("hook-run.exe" if os.name == "nt" else "hook-run")
    env = dict(os.environ, COORDINATOR_DOOR_STDIN_MODE="hook")
    try:
        payload = sys.stdin.buffer.read()
    except (OSError, ValueError):
        payload = b""
    if guard:
        answer = guard_answer(payload, guard, host)
        if answer is not None:
            sys.stdout.write(json.dumps(answer))
            return 0
    payload, agy = to_claude(payload)
    extra = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE} if agy else {}
    if not agy:
        extra["stderr"] = subprocess.DEVNULL if quiet else None
    try:
        res = subprocess.run(
            [str(door), *rest], env=env, input=payload, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **extra,
        )
        rc = res.returncode
    except OSError as exc:
        sys.stderr.write("agy-hook-run: cannot run %s: %s\\n" % (door, exc))
        return 127
    if not agy:
        return 0 if pass_2 and rc == 2 else rc
    out = res.stdout.decode("utf-8", "replace")
    err = res.stderr.decode("utf-8", "replace")
    if err and not quiet:
        sys.stderr.write(err)
    if rc not in (0, 2):
        sys.stdout.write(out)
        return rc
    if pass_2 and rc == 2:
        rc = 0
    sys.stdout.write("{}" if json.loads(payload)["hook_event_name"] == "PostToolUse" else json.dumps(to_agy(rc, out, err)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''
DOOR_CMD_RE = re.compile(
    r'COORDINATOR_DOOR_STDIN_MODE=hook "\$\{COORDINATOR_SETTINGS_HOME:-[^}]*\}/bin/hook-run"'
    r"(?P<rest>(?: --advisory)? hooks\.\w+)(?P<quiet> 2>/dev/null)?"
    r"(?P<pass2>; rc=\$\?; \[ \$rc -eq 2 \] && rc=0; exit \$rc)?"
)
BASH_ONLY_RE = re.compile(r"^\s*[A-Za-z_]\w*=|rc=\$\?|/dev/null|\$\{\w+:-")


def _agy_python():
    """Interpreter name agy resolves on PATH: Windows has `python`, never a working `python3`."""
    return "python" if os.name == "nt" else "python3"


def _agy_hook_command(command, out_dir):
    """The shell-neutral launcher command for one Claude door hook command, else None.

    The shim path is baked absolute: agy on Windows hands `${PLUGIN_ROOT}` to python unexpanded and
    keeps literal quotes, so the path is quoted only when it holds a space.
    """
    m = DOOR_CMD_RE.fullmatch(command)
    if not m:
        return None
    flags = (" --quiet" if m["quiet"] else "") + (" --pass-2" if m["pass2"] else "")
    root = str(out_dir).replace(chr(92), "/").rstrip("/")
    if m["rest"].strip() == "hooks.preuse_bash_dispatch":
        flags += f" --host-guard {_quote_if_space(posixpath.dirname(root) + '/' + GUARD_REL)} --host agy"
    return f"{_agy_python()} {_quote_if_space(f'{root}/{SHIM_REL}')}{flags}{m['rest']}"


def _quote_if_space(path):
    return f'"{path}"' if " " in path else path


def _fold_args(command, args):
    """One command line for a single-token `command` with an `args` list, else None.

    agy runs only `command`; a bare `python3` would read the stdin payload as its program.
    """
    if not (isinstance(args, list) and args and all(isinstance(a, str) for a in args)):
        return None
    if not command or re.search(r"\s", command):
        return None
    exe = _agy_python() if command in ("python", "python3") else command
    return _win_cmdline([exe, *args]) if os.name == "nt" else shlex.join([exe, *args])


def _win_cmdline(argv):
    """argv joined by the MS C runtime quoting rules (the inverse of CommandLineToArgvW)."""
    def quote(a):
        if a and not re.search(r'[\s"]', a):
            return a
        a = re.sub(r'(\\*)"', lambda m: m[1] * 2 + '\\"', a)
        a = re.sub(r"(\\+)$", lambda m: m[1] * 2, a)
        return f'"{a}"'
    return " ".join(quote(a) for a in argv)


GATED_EVENT = "PreToolUse"


def _adapter_only(groups, adapted, plan) -> list:
    """PreToolUse groups cut to the handlers whose command is a shim launcher; agy fails closed on any other handler's reply, so the rest are reported and dropped."""
    kept = []
    for group in groups:
        handlers = group.get("hooks") if isinstance(group, dict) and isinstance(group.get("hooks"), list) else []
        live = [h for h in handlers if isinstance(h, dict) and h.get("command") in adapted]
        for h in handlers:
            if not (isinstance(h, dict) and h.get("command") in adapted):
                plan.miss("hook-command", "hooks/hooks.json",
                          f"{GATED_EVENT}: command ...{str(h.get('command') if isinstance(h, dict) else h)[-60:]!r} "
                          "dropped; it bypasses the agy adapter and agy fails closed on its reply")
        if live:
            kept.append({**group, "hooks": live})
    return kept


def _hooks(plan, plugin_root) -> None:
    src = plugin_root / "hooks" / "hooks.json"
    if not src.is_file():
        return
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except ValueError as exc:
        plan.miss("hooks", "hooks/hooks.json", f"unparseable JSON: {exc}")
        return
    drop = set(plan.cfg["hook_drop_fields"])

    shim = []
    adapted = set()

    def clean(o) -> object:
        if isinstance(o, dict):
            out = {k: clean(v) for k, v in o.items() if k not in drop}
            command = out.get("command")
            if isinstance(command, str):
                folded = _fold_args(command, out.get("args"))
                if folded:
                    out["command"] = folded
                    out.pop("args")
                    return out
                neutral = _agy_hook_command(command, plan.out_dir)
                if neutral:
                    out["command"] = neutral
                    out.pop("shell", None)
                    shim.append(True)
                    adapted.add(neutral)
                elif BASH_ONLY_RE.search(command):
                    plan.miss("hook-command", "hooks/hooks.json", f"bash-only syntax in command {command[:60]!r}")
            return out
        if isinstance(o, list):
            return [clean(v) for v in o]
        # agy expands no ${PLUGIN_ROOT} in a hook arg on Windows: bake the dest dir into every string.
        return plan.rewrite(o).replace(plan.cfg["plugin_root_token"], plan.out_dir) if isinstance(o, str) else o

    data = clean(data)
    events = data.get("hooks") if isinstance(data, dict) else None
    if isinstance(events, dict):
        for event in sorted(events):
            if event not in plan.cfg["hook_events"]:
                plan.miss("hook-event", "hooks/hooks.json", f"event {event!r} has no agy equivalent")
                del events[event]
                continue
            groups = events[event] if isinstance(events[event], list) else []
            if event not in plan.cfg["tool_hook_events"]:
                events[event] = _flatten_groups(groups, event, plan)
                continue
            if event == GATED_EVENT:
                groups = events[event] = _adapter_only(groups, adapted, plan)
                if not groups:
                    del events[event]
                    continue
            for group in groups:
                if isinstance(group, dict) and isinstance(group.get("matcher"), str):
                    group["matcher"] = _hook_matcher(group["matcher"], event, plan)
    named = {_hook_name(event): {event: events[event]} for event in sorted(events)} if isinstance(events, dict) else {}
    plan.put(plan.cfg["hooks_path"], _json_bytes(named), "hooks", "hooks/hooks.json")
    if shim:
        plan.put(SHIM_REL, SHIM_SOURCE.encode("utf-8"), "hooks", "hooks/hooks.json")


AGY_TOOL_SURFACE_MAPPING = """## Agy Tool & Surface Mapping

Coordinator skills and agents are authored against Claude Code tool names; use the corresponding Agy native tools and routes:

- `Read` -> `read_file`
- `Write` -> `write_file`
- `Edit` / `MultiEdit` -> `edit_file`
- `Bash` -> `run_command`
- `Glob` / `Grep` -> `project-rag` MCP tools first, else `run_command` with `rg` / `git grep`
- `Agent` -> `invoke_subagent`
- `AskUserQuestion` -> `ask_question`
- `SendMessage` -> `unimatrix-send.py` (`--to <peer> "<msg>"`)
- `Workflow` -> write `.coordinator-local/em-submit.json` and run `coordinator-invoke engine_ask.submit` + `workflow.fire_wait`
"""


def _rules(plan, plugin_root) -> None:
    text = _doctrine_text(plugin_root)
    if text is None:
        plan.miss("rules", DOCTRINE_SOURCES[0], "no global-doctrine/CLAUDE.md beside the plugin root")
        return
    head, body = _split_frontmatter(plan.rewrite(text))
    head = list(head or [])
    i, _ = _field(head, "trigger")
    line = f"trigger: {plan.cfg['rules_trigger']}"
    if i is None:
        head.insert(0, line)
    else:
        head[i] = line
    if getattr(plan, "host", None) == "agy":
        body = body.rstrip() + "\n\n" + AGY_TOOL_SURFACE_MAPPING
    data = _join_frontmatter(head, body).encode("utf-8")
    cap = plan.cfg["max_text_bytes"]
    if len(data) > cap:
        plan.miss("oversize", DOCTRINE_SOURCES[0], f"{len(data)} bytes exceeds the {cap}-byte cap")
        return
    plan.put(plan.cfg["rules_path"], data, "rules", DOCTRINE_SOURCES[0])


def _manifest(plan, plugin_root) -> None:
    """plugin.json at the output root: name, version, description, logo from the source manifest."""
    src = plugin_root / plan.cfg["source_manifest_path"]
    source = {}
    if src.is_file():
        try:
            loaded = json.loads(src.read_text(encoding="utf-8"))
            source = loaded if isinstance(loaded, dict) else {}
        except ValueError as exc:
            plan.miss("manifest", plan.cfg["source_manifest_path"], f"unparseable JSON: {exc}")
    else:
        plan.miss("manifest", plan.cfg["source_manifest_path"], "no source plugin manifest; name taken from the directory")
    manifest = {"name": source.get("name") or plugin_root.resolve().name}
    for key in ("version", "description"):
        if isinstance(source.get(key), str):
            manifest[key] = source[key]
    logo = source.get("logo")
    if isinstance(logo, str) and logo:
        manifest["logo"] = logo
        logo_path = plugin_root / logo
        if not Path(logo).is_absolute() and ".." not in Path(logo).parts and logo_path.is_file():
            plan.put_file(Path(logo).as_posix(), logo_path, "file", logo)
    plan.put(plan.cfg["manifest_path"], _json_bytes(manifest), "manifest", plan.cfg["source_manifest_path"])


def _copied_dirs(plan, plugin_root) -> None:
    for name in plan.cfg["copy_dirs"]:
        d = plugin_root / name
        if not d.is_dir():
            continue
        for rel, p in _walk(d):
            if name == "hooks" and rel == "hooks.json":
                continue
            plan.put_file(f"{name}/{rel}", p, "file", f"{name}/{rel}")


def _unhandled_top_level(plan, plugin_root) -> None:
    handled = {"agents", "commands", "skills", "hooks", *plan.cfg["copy_dirs"], *plan.cfg["ignore_top_level"]}
    for child in sorted(plugin_root.iterdir(), key=lambda c: c.name):
        if child.name not in handled and child.name not in SKIP_NAMES:
            plan.miss("surface", child.name, "no mapping for this plugin surface")


def _prepare_out(out_dir, plugin_root):
    out, src = out_dir.resolve(), plugin_root.resolve()
    if out == src or src.is_relative_to(out) or out.is_relative_to(src):
        raise ValueError(f"out dir {out_dir} overlaps the plugin source {plugin_root}")
    if out.exists():
        if not out.is_dir():
            raise ValueError(f"out path {out_dir} is not a directory")
        entries = sorted(out.iterdir(), key=lambda c: c.name)
        if entries and not (out / UNMAPPED_NAME).is_file():
            raise ValueError(f"out dir {out_dir} is not empty and holds no prior {UNMAPPED_NAME}; refusing to clear it")
        for e in entries:
            if e.is_dir() and not e.is_symlink():
                shutil.rmtree(e)
            else:
                e.unlink()
    out.mkdir(parents=True, exist_ok=True)
    return out


def generate(plugin_root, out_dir, host: str = "agy"):
    """Write `host`'s plugin tree for `plugin_root` into `out_dir`.

    Returns {"written": [sorted posix rel paths, UNMAPPED.json included],
    "unmapped": [{"kind", "source", "reason"}, ...] sorted}. ValueError for an unknown host or an
    out_dir that is non-empty without a prior UNMAPPED.json (or overlaps the source); the tree is
    built in memory first, so a failed run clears nothing.
    """
    plugin_root, out_dir = Path(plugin_root), Path(out_dir)
    table = load_table()
    if host not in table:
        raise ValueError(f"unknown host {host!r}; table has {', '.join(sorted(table))}")
    cfg = table[host]
    if not plugin_root.is_dir():
        raise ValueError(f"plugin root {plugin_root} is not a directory")
    plan = _Plan(cfg, cfg.get("token_suffixes", ()))
    plan.host = host
    plan.out_dir = out_dir.resolve().as_posix()
    if not cfg:
        for kind, source in _inventory(plugin_root):
            plan.miss(kind, source, NO_MAP)
    else:
        _manifest(plan, plugin_root)
        _agents(plan, plugin_root)
        _command_skills(plan, plugin_root)
        _skills(plan, plugin_root)
        _hooks(plan, plugin_root)
        _rules(plan, plugin_root)
        _copied_dirs(plan, plugin_root)
        _unhandled_top_level(plan, plugin_root)
    unmapped = [{"kind": k, "source": s, "reason": r} for k, s, r in sorted(plan.unmapped)]
    plan.files[UNMAPPED_NAME] = _json_bytes({"host": host, "unmapped": unmapped})
    out = _prepare_out(out_dir, plugin_root)
    written = sorted(plan.files)
    for rel in written:
        target = out.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(plan.files[rel])
    return {"written": written, "unmapped": unmapped}


def main(argv: list[str]) -> int:
    """Library module: only `--help` is answered; anything else exits 2 with nothing to run."""
    if any(a in ("-h", "--help") for a in argv):
        print("usage: unimatrix-plugin-gen [-h]\ntranslate a coordinator plugin tree into a host-plugin tree (library module)")
        return 0
    print("unimatrix-plugin-gen: library module; nothing to run", file=__import__("sys").stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
