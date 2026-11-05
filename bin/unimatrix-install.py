"""Unimatrix installer: Claude Code version-range gate plus copy of the vendored scripts.

Default mode checks `claude --version` against VERIFIED_RANGE; `--install` copies
VENDORED_SCRIPTS into <settings home>/unimatrix. Outside the range the gate refuses;
`--force` downgrades the refusal to a warning. Stdlib only, portable across
macOS, Windows and Linux.
"""
import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path

INSTALL_CLASS = True  # copies vendored scripts into the settings home; see door_install.declared_install_class

# Half-open: lower bound inclusive, upper bound exclusive.
VERIFIED_RANGE = ((2, 1, 300), (2, 2, 0))

VENDORED_SCRIPTS = (
    "unimatrix-bridge.py",
    "unimatrix-relay.py",
    "unimatrix-rekey.py",
    "unimatrix-inbox.py",
    "unimatrix-roster.py",
    "unimatrix-peer-contract.py",
    "unimatrix-peer-codex.py",
    "unimatrix-peer-agy.py",
    "unimatrix-agy-leg.py",
    "unimatrix-peer-router.py",
    "unimatrix-agy-hook-pretool.py",
    "unimatrix-agy-hook-launch.py",
    "unimatrix-agy-hook-sessionstart.py",
    "unimatrix-codex-hook-sessionstart.py",
    "unimatrix-host-guard.py",
    "unimatrix-doctrine-seed.py",
)

AGY_HOOK_KEY = "unimatrix-agy-leg"
AGY_HOOK_SCRIPT = "unimatrix-agy-hook-pretool.py"
AGY_SESSIONSTART_SCRIPT = "unimatrix-agy-hook-sessionstart.py"
CODEX_SESSIONSTART_SCRIPT = "unimatrix-codex-hook-sessionstart.py"
GUARD_SCRIPT = "unimatrix-host-guard.py"
DOCTRINE_SEED_SCRIPT = "unimatrix-doctrine-seed.py"
CODEX_SHELL_MATCHER = "Bash"
HOST_NAMES = ("claude", "codex", "agy")

_BIN_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = _BIN_DIR.parent
SKILLS_ROOT = PLUGIN_ROOT / "skills"

# Copied when present beside this installer; the peer doctrine names its installed path.
OPTIONAL_SCRIPTS = ("unimatrix-send.py",)
SEND_SCRIPT = "unimatrix-send.py"

PEER_DOCTRINE_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "unimatrix" / "peer-doctrine.md"
DOCTRINE_BEGIN = "<!-- BEGIN unimatrix-peer-doctrine (managed by unimatrix-install; edits inside are overwritten) -->"
DOCTRINE_END = "<!-- END unimatrix-peer-doctrine -->"

SEMVER = re.compile(r"\b(\d+)\.(\d+)\.(\d+)\b")

NATIVE_RC_NOTICE = (
    "NOTE: the native same-account /rc route is the first choice for cross-box SendMessage; "
    "Unimatrix is the option for cross-account boxes."
)


def parse_version(text):
    """Return (major, minor, patch) from `claude --version` output; RuntimeError if none."""
    m = SEMVER.search(text or "")
    if not m:
        raise RuntimeError(f"no semver in `claude --version` output: {text!r}")
    return tuple(int(g) for g in m.groups())


def _fmt(v):
    return ".".join(str(p) for p in v)


def check_version(text, force=False):
    """Return ("ok"|"warn"|"refuse", message). `force` turns a refusal into a warning."""
    version = parse_version(text)
    lo, hi = VERIFIED_RANGE
    rng = f">={_fmt(lo)},<{_fmt(hi)}"
    if lo <= version < hi:
        return "ok", f"claude {_fmt(version)} in verified range ({rng})"
    msg = f"claude {_fmt(version)} outside verified range ({rng})"
    if force:
        return "warn", f"WARN: {msg}; continuing because --force"
    return "refuse", f"REFUSE: {msg}; pass --force to override"


def probe_claude_version():
    """Run `claude --version`; shutil.which resolves claude.cmd on Windows."""
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude not found on PATH; cannot read the harness version")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, **kwargs)
    return out.stdout or ""


def settings_home():
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def install_scripts(src_dir, dest_dir):
    """Copy VENDORED_SCRIPTS from src_dir into dest_dir; return the copied names."""
    missing = [n for n in VENDORED_SCRIPTS if not (Path(src_dir) / n).is_file()]
    if missing:
        raise FileNotFoundError(f"vendored scripts missing in {src_dir}: {', '.join(missing)}")
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    for name in VENDORED_SCRIPTS:
        shutil.copy2(Path(src_dir) / name, dest / name)
    extra = [n for n in OPTIONAL_SCRIPTS if (Path(src_dir) / n).is_file()]
    for name in extra:
        shutil.copy2(Path(src_dir) / name, dest / name)
    return list(VENDORED_SCRIPTS) + extra


def agy_hooks_path():
    """agy's global hook discovery file."""
    return Path.home() / ".gemini" / "config" / "hooks.json"


def codex_hooks_path():
    """Codex's user hook discovery file: $CODEX_HOME/hooks.json, default ~/.codex."""
    env = os.environ.get("CODEX_HOME")
    return (Path(env) if env else Path.home() / ".codex") / "hooks.json"


def _hook_command(dest_dir, script_name, *args):
    argv = [sys.executable, str(Path(dest_dir) / script_name), *args]
    return subprocess.list2cmdline(argv) if os.name == "nt" else " ".join(shlex.quote(a) for a in argv)


def _engine_args(engine_root):
    return ("--engine-root", str(engine_root)) if engine_root else ()


def _hook_handler(dest_dir, script_name, *args):
    return {"type": "command", "command": _hook_command(dest_dir, script_name, *args), "timeout": 10}


def _hook_group(dest_dir, script_name, matcher=None, args=()):
    group = {"hooks": [_hook_handler(dest_dir, script_name, *args)]}
    if matcher:
        group = {"matcher": matcher, **group}
    return group


def agy_hook_entry(dest_dir, engine_root=None):
    """Our hooks.json value: a run_command PreToolUse hook and a SessionStart hook running installed scripts.

    agy groups only tool events under matcher/hooks; SessionStart takes bare handlers, and agy
    rejects the whole file ("command hook must specify 'command'") when it is grouped. The
    PreToolUse group is the single merged hook; `--engine-root` is how it finds the Klabauter guard.
    """
    return {
        "PreToolUse": [_hook_group(dest_dir, AGY_HOOK_SCRIPT, "run_command", _engine_args(engine_root))],
        "SessionStart": [_hook_handler(dest_dir, AGY_SESSIONSTART_SCRIPT)],
    }


def codex_hook_events(dest_dir, engine_root=None):
    """The Codex groups we own, by event: SessionStart, and a shell-only PreToolUse guard."""
    return {
        "SessionStart": _hook_group(dest_dir, CODEX_SESSIONSTART_SCRIPT),
        "PreToolUse": _hook_group(
            dest_dir, GUARD_SCRIPT, CODEX_SHELL_MATCHER, ("--host", "codex", *_engine_args(engine_root))),
    }


def _load_hooks(path):
    """Return the parsed hooks.json object ({} when absent); ValueError when unreadable or not an object."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path} is not parseable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def seed_agy_hook(hooks_path, dest_dir, engine_root=None):
    """Point our key at this install; return "created", "added", "updated" or "present".

    A value we wrote earlier (it carries PreToolUse or SessionStart) is replaced when it differs,
    which heals a missing event, a script path or the engine root from an older install. A
    hand-customised value and every other key in the file are left byte-identical.
    """
    path = Path(hooks_path)
    existed = path.exists()
    data = _load_hooks(path)
    want = agy_hook_entry(dest_dir, engine_root)
    if AGY_HOOK_KEY in data:
        entry = data[AGY_HOOK_KEY]
        ours = isinstance(entry, dict) and ("PreToolUse" in entry or "SessionStart" in entry)
        if entry == want or not ours:
            return "present"
        data[AGY_HOOK_KEY] = want
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return "updated"
    data[AGY_HOOK_KEY] = want
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "added" if existed else "created"


def unseed_agy_hook(hooks_path):
    """Remove only our key; return "removed" or "absent"."""
    path = Path(hooks_path)
    data = _load_hooks(path)
    if AGY_HOOK_KEY not in data:
        return "absent"
    del data[AGY_HOOK_KEY]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "removed"


_CODEX_OWNED_SCRIPTS = (CODEX_SESSIONSTART_SCRIPT, GUARD_SCRIPT)


def _codex_ours(group):
    """True for a group holding a handler that runs the SessionStart script or the guard."""
    return isinstance(group, dict) and any(
        isinstance(h, dict) and any(s in str(h.get("command", "")) for s in _CODEX_OWNED_SCRIPTS)
        for h in group.get("hooks") or []
    )


def _codex_events(data, path, event="SessionStart"):
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{path} has a non-object `hooks` value")
    events = hooks.setdefault(event, [])
    if not isinstance(events, list):
        raise ValueError(f"{path} has a non-list `hooks.{event}` value")
    return events


def seed_codex_hook(hooks_path, dest_dir, engine_root=None):
    """Add our SessionStart and PreToolUse guard handlers to Codex's hooks.json.

    Returns "created", "added", "updated" (a stale group of ours was rewritten) or "present".
    Foreign groups are never touched.
    """
    path = Path(hooks_path)
    existed = path.exists()
    data = _load_hooks(path)
    states = []
    for event, want in codex_hook_events(dest_dir, engine_root).items():
        events = _codex_events(data, path, event)
        idx = next((i for i, g in enumerate(events) if _codex_ours(g)), None)
        if idx is None:
            events.append(want)
            states.append("added")
        elif events[idx] != want:
            events[idx] = want
            states.append("updated")
    if not states:
        return "present"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if not existed:
        return "created"
    return "added" if "added" in states else "updated"


def unseed_codex_hook(hooks_path):
    """Remove only our SessionStart and guard handlers (pruning emptied containers); return "removed" or "absent"."""
    path = Path(hooks_path)
    data = _load_hooks(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return "absent"
    removed = False
    for event in ("SessionStart", "PreToolUse"):
        events = hooks.get(event)
        if not isinstance(events, list) or not any(_codex_ours(g) for g in events):
            continue
        removed = True
        events[:] = [g for g in events if not _codex_ours(g)]
        if not events:
            del hooks[event]
    if not removed:
        return "absent"
    if not hooks:
        del data["hooks"]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "removed"


def _event_id(name):
    """Event name normalised so `preToolUse`, `PreToolUse` and `pre_tool_use` compare equal."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _codex_expected_handlers(hooks_path):
    """The exact {event id: command} pair of our handlers in Codex's hooks.json.

    Raises ValueError unless exactly one SessionStart handler (the SessionStart script) and exactly
    one PreToolUse handler (the guard) of ours are present: trust is verified against this set,
    never against whatever rows discovery happens to return.
    """
    hooks = _load_hooks(hooks_path).get("hooks")
    expected = {}
    for event, script in (("SessionStart", CODEX_SESSIONSTART_SCRIPT), ("PreToolUse", GUARD_SCRIPT)):
        cmds = []
        for group in (hooks.get(event) if isinstance(hooks, dict) else None) or []:
            if _codex_ours(group):
                cmds.extend(str(h.get("command", "")) for h in group.get("hooks") or [] if isinstance(h, dict))
        if len(cmds) != 1 or script not in cmds[0]:
            raise ValueError(f"hooks.json must hold exactly one {event} handler of ours running {script}; found {len(cmds)}")
        expected[_event_id(event)] = cmds[0]
    return expected


def codex_rules_path():
    """Codex's global instructions file: $CODEX_HOME/AGENTS.md, default ~/.codex."""
    return codex_hooks_path().with_name("AGENTS.md")


def agy_rules_path():
    """agy's global rules file (agy 1.4.12 loads ~/.gemini/GEMINI.md and ~/.gemini/AGENTS.md)."""
    return Path.home() / ".gemini" / "GEMINI.md"


def codex_exec_rule_path():
    """Our Codex execpolicy file: $CODEX_HOME/rules/unimatrix.rules."""
    return codex_hooks_path().parent / "rules" / "unimatrix.rules"


def render_codex_exec_rule(dest_dir):
    """An allow rule for the send command alone, so a Codex reply to a peer needs no approval prompt."""
    argv = [sys.executable, str(Path(dest_dir) / SEND_SCRIPT)]
    return ("# unimatrix: lets Codex answer a peer agent with the send command, without an approval prompt.\n"
            "# Only this one script. Written by unimatrix-install.py --install, removed by --uninstall.\n"
            f"prefix_rule(pattern={json.dumps(argv)}, decision=\"allow\")\n")


def seed_file(path, text):
    """Write a whole file we own; return "created", "updated" or "present"."""
    path = Path(path)
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return "present"
        path.write_text(text, encoding="utf-8")
        return "updated"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "created"


def unseed_file(path):
    path = Path(path)
    if not path.exists():
        return "absent"
    path.unlink()
    return "removed"


def render_peer_doctrine(dest_dir, template=None):
    """Return the managed block: the doctrine template with {SEND} bound to the installed send command."""
    body = Path(template or PEER_DOCTRINE_TEMPLATE).read_text(encoding="utf-8").strip("\n")
    body = body.replace("{SEND}", _hook_command(dest_dir, SEND_SCRIPT))
    return f"{DOCTRINE_BEGIN}\n{body}\n{DOCTRINE_END}\n"


_SEED_MODULE = None


def _seed():
    """The doctrine-seed module (marker-parameterised block helpers, skills seeders), loaded once from beside this file."""
    global _SEED_MODULE
    if _SEED_MODULE is None:
        spec = importlib.util.spec_from_file_location("unimatrix_doctrine_seed", _BIN_DIR / DOCTRINE_SEED_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SEED_MODULE = mod
    return _SEED_MODULE


def _split_block(text):
    """Return (before, after) around our peer-doctrine block, or None when absent."""
    return _seed().split_block(text, DOCTRINE_BEGIN, DOCTRINE_END)


def seed_peer_doctrine(path, block):
    """Write our managed block into a rules file; return "created", "added", "updated" or "present".

    Text outside the markers is never touched. A re-install with identical text changes nothing.
    """
    return _seed().seed_block(path, block, DOCTRINE_BEGIN, DOCTRINE_END)


def unseed_peer_doctrine(path):
    """Remove only our managed block (deleting a file left empty); return "removed" or "absent"."""
    return _seed().unseed_block(path, DOCTRINE_BEGIN, DOCTRINE_END)


def doctrine_root():
    """The directory holding global-doctrine/, or None when this install does not carry it."""
    for root in (PLUGIN_ROOT.parent, PLUGIN_ROOT):
        if (root / "global-doctrine" / "CLAUDE.md").is_file():
            return root
    return None


def resolve_engine_root():
    """Return (engine_root or None, provenance); never raises.

    Uses the hook-side resolver when this install carries it, else the in-tree settings-home ladder
    (cc_invoke.resolve_engine_root). A miss returns None with the resolver's first failure line.
    """
    hook_side = PLUGIN_ROOT / "hooks" / "scripts" / "_engine_root.py"
    try:
        if hook_side.is_file():
            spec = importlib.util.spec_from_file_location("_engine_root_for_install", hook_side)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            root, _cls, prov = mod.resolve_claude_klabauter_root_with_provenance()
        else:
            spec = importlib.util.spec_from_file_location("_cc_invoke_for_install", _BIN_DIR / "lib" / "cc_invoke.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            root, prov = mod.resolve_engine_root(str(Path(__file__).resolve())), "settings-home ladder"
    except Exception as exc:
        lines = str(exc).strip().splitlines()
        return None, f"resolver failed: {lines[0] if lines else type(exc).__name__}"
    return (str(root), prov) if root and Path(root).is_dir() else (None, prov if root is None else "root missing")


def trust_codex_hook(hooks_path, timeout=30):
    """Mark our Codex SessionStart hook trusted in config.toml via `codex app-server`.

    Codex runs a user hook only after its content hash is recorded under hooks.state; the app-server
    reports the hash (hooks/list) and writes it (config/value/write). Returns (ok, message); never raises.
    """
    exe = shutil.which("codex")
    if not exe:
        return False, "codex not on PATH; hook stays untrusted until reviewed in /hooks"
    hooks_file = Path(hooks_path)
    env = dict(os.environ, CODEX_HOME=str(hooks_file.parent))
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [exe, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, env=env, **kwargs,
        )
    except OSError as exc:
        return False, f"codex app-server did not start: {exc}"
    timer = threading.Timer(timeout, proc.kill)
    timer.start()

    def rpc(rid, method, params):
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("codex app-server closed before answering")
            msg = json.loads(line)
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg["result"]

    try:
        rpc(1, "initialize", {"clientInfo": {"name": "unimatrix-install", "version": "1"}})
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n")
        proc.stdin.flush()
        expected = _codex_expected_handlers(hooks_file)
        here = hooks_file.resolve()

        def discover(rid):
            """One row per expected handler, keyed by event id; ValueError when any is missing, doubled or misplaced."""
            listed = rpc(rid, "hooks/list", {"cwds": []})
            mine = [
                h for entry in listed.get("data", []) for h in entry.get("hooks", [])
                if str(h.get("command", "")) in expected.values()
                and Path(h.get("sourcePath", "")).resolve() == here
            ]
            found = {}
            for h in mine:
                ident = _event_id(h.get("eventName", ""))
                if expected.get(ident) != h.get("command") or ident in found:
                    raise ValueError(f"{h.get('eventName', 'hook')} handler is duplicated or on the wrong event")
                found[ident] = h
            missing = sorted(set(expected) - set(found))
            if missing:
                raise ValueError(f"codex did not discover the {', '.join(missing)} handler (features.hooks disabled?)")
            if len({h.get("key") for h in found.values()}) != len(found):
                raise ValueError("discovered handlers share a trust key")
            return found

        before = discover(2)
        for hook in before.values():
            if not (isinstance(hook.get("key"), str) and hook["key"]
                    and isinstance(hook.get("currentHash"), str) and hook["currentHash"]):
                raise ValueError(f"{hook.get('eventName', 'hook')} reports no key or content hash")
            rpc(3, "config/value/write", {
                "keyPath": f'hooks.state."{hook["key"]}".trusted_hash',
                "value": hook["currentHash"],
                "mergeStrategy": "upsert",
            })
        after = discover(4)
        for ident, hook in after.items():
            name = hook.get("eventName", ident)
            current, trusted = hook.get("currentHash"), hook.get("trustedHash")
            if hook.get("key") != before[ident]["key"] or current != before[ident]["currentHash"]:
                raise ValueError(f"{name} changed while trust was being written")
            if hook.get("enabled") is not True:
                raise ValueError(f"{name} is disabled")
            if not (isinstance(current, str) and current):
                raise ValueError(f"{name} reports no content hash after trust was written")
            # Real Codex reports trustStatus without trustedHash; a trustedHash it does report must still match.
            if trusted is not None and not (isinstance(trusted, str) and trusted == current):
                raise ValueError(f"{name} is untrusted (trustedHash does not equal currentHash)")
            if trusted is None and hook.get("trustStatus") != "trusted":
                raise ValueError(f"{name} is untrusted (no trustedHash and trustStatus is not trusted)")
        return True, f"trusted {len(after)} hook(s)"
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        return False, f"codex hook trust failed: {exc}"
    finally:
        timer.cancel()
        proc.kill()
        proc.wait()


def main(argv=None, version_text=None, dest_dir=None, out=None, hooks_path=None,
         codex_hooks=None, codex_trust=None, codex_rules=None, agy_rules=None, codex_exec_rule=None,
         agy_skills_json=None, codex_skills=None):
    """`hooks_path` overrides agy's file. Codex's file defaults to codex_hooks_path(), or to a sibling
    `codex-hooks.json` when only `hooks_path` is overridden; trust runs against the real Codex only for
    the default path, unless `codex_trust` (a callable taking the hooks path) is injected. The peer
    doctrine files follow the same rule: real home files by default, siblings `codex-AGENTS.md` and
    `agy-GEMINI.md` of `hooks_path` when it is overridden, or the explicit `codex_rules`/`agy_rules`."""
    out = out or sys.stdout
    codex_default = codex_hooks is None and hooks_path is None
    codex_hp = Path(codex_hooks) if codex_hooks else (
        codex_hooks_path() if hooks_path is None else Path(hooks_path).with_name("codex-hooks.json")
    )
    if codex_rules:
        codex_rp = Path(codex_rules)
    else:
        codex_rp = codex_rules_path() if hooks_path is None else Path(hooks_path).with_name("codex-AGENTS.md")
    if codex_exec_rule:
        codex_xp = Path(codex_exec_rule)
    else:
        codex_xp = codex_exec_rule_path() if hooks_path is None else Path(hooks_path).with_name("codex-unimatrix.rules")
    if agy_rules:
        agy_rp = Path(agy_rules)
    else:
        agy_rp = agy_rules_path() if hooks_path is None else Path(hooks_path).with_name("agy-GEMINI.md")
    if codex_trust is None and codex_default:
        codex_trust = trust_codex_hook
    agy_sj = Path(agy_skills_json) if agy_skills_json else (
        agy_hooks_path().with_name("skills.json") if hooks_path is None else Path(hooks_path).with_name("agy-skills.json")
    )
    codex_sd = Path(codex_skills) if codex_skills else (
        Path.home() / ".agents" / "skills" if hooks_path is None else Path(hooks_path).with_name("codex-agents-skills")
    )
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--install", action="store_true", help="copy the vendored scripts into the settings home")
    ap.add_argument("--uninstall", action="store_true", help="remove everything --install seeded for Codex and agy")
    ap.add_argument("--force", action="store_true", help="warn instead of refusing outside the verified range")
    ap.add_argument("--hosts", help="comma list of claude,codex,agy; default codex,agy with the Claude range gate. "
                    "Naming no claude skips the gate when `claude` is not on PATH")
    args = ap.parse_args(argv)
    hosts = None
    if args.hosts is not None:
        hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
        bad = [h for h in hosts if h not in HOST_NAMES]
        if bad or not hosts:
            print(f"REFUSE: --hosts takes {','.join(HOST_NAMES)}; got {args.hosts!r}", file=out)
            return 2
    want_codex = hosts is None or "codex" in hosts
    want_agy = hosts is None or "agy" in hosts

    if args.uninstall:
        hp = Path(hooks_path) if hooks_path else agy_hooks_path()
        steps = []
        if want_agy:
            steps.append(("agy hook", hp, lambda: unseed_agy_hook(hp)))
            steps.append(("agy skills", agy_sj, lambda: _seed().unseed_agy_skills(agy_sj, SKILLS_ROOT)))
            steps.append(("agy coordinator doctrine", agy_rp, lambda: _seed().unseed_block(
                agy_rp, _seed().DOCTRINE_BEGIN, _seed().DOCTRINE_END)))
            steps.append(("agy peer doctrine", agy_rp, lambda: unseed_peer_doctrine(agy_rp)))
        if want_codex:
            steps.append(("codex hook", codex_hp, lambda: unseed_codex_hook(codex_hp)))
            steps.append(("codex skills", codex_sd, lambda: ",".join(_seed().unseed_codex_skills(codex_sd)) or "absent"))
            steps.append(("codex coordinator doctrine", codex_rp, lambda: _seed().unseed_block(
                codex_rp, _seed().DOCTRINE_BEGIN, _seed().DOCTRINE_END)))
            steps.append(("codex peer doctrine", codex_rp, lambda: unseed_peer_doctrine(codex_rp)))
            steps.append(("codex send rule", codex_xp, lambda: unseed_file(codex_xp)))
        for label, where, fn in steps:
            try:
                res = fn()
            except (ValueError, OSError) as exc:
                print(f"REFUSE: {exc}", file=out)
                return 4
            print(f"{label} {res} in {where}", file=out)
        return 0

    if version_text is None:
        gate_skipped = hosts is not None and "claude" not in hosts and shutil.which("claude") is None
        if gate_skipped:
            print("NOTE: claude not on PATH and --hosts names no claude; Claude version-range gate skipped", file=out)
        else:
            try:
                version_text = probe_claude_version()
            except RuntimeError as exc:
                print(f"REFUSE: {exc}", file=out)
                return 2
    if version_text is not None:
        try:
            status, msg = check_version(version_text, args.force)
        except RuntimeError as exc:
            print(f"REFUSE: {exc}", file=out)
            return 2
        print(msg, file=out)
        if status == "refuse":
            return 1
    if not args.install:
        return 0

    print(NATIVE_RC_NOTICE, file=out)
    dest = Path(dest_dir) if dest_dir else settings_home() / "unimatrix"
    try:
        copied = install_scripts(Path(__file__).resolve().parent, dest)
    except FileNotFoundError as exc:
        print(f"REFUSE: {exc}", file=out)
        return 3
    print(f"installed {len(copied)} scripts into {dest}", file=out)
    engine_root, provenance = resolve_engine_root()
    hp = Path(hooks_path) if hooks_path else agy_hooks_path()
    if want_agy:
        try:
            res = seed_agy_hook(hp, dest, engine_root)
        except ValueError as exc:
            print(f"REFUSE: {exc}; agy hook not installed", file=out)
            return 4
        print(f"agy hook {res} in {hp}", file=out)
    if want_codex:
        try:
            res = seed_codex_hook(codex_hp, dest, engine_root)
        except ValueError as exc:
            print(f"REFUSE: {exc}; codex hook not installed", file=out)
            return 4
        print(f"codex hook {res} in {codex_hp}", file=out)
    rc = 0
    verified = None
    if want_codex and codex_trust is not None:
        ok, note = codex_trust(codex_hp)
        if ok:
            print(f"codex hook trust: {note}", file=out)
            verified = True
        else:
            print(f"governance verification FAILED: {note}", file=out)
            verified, rc = False, 5
    try:
        block = render_peer_doctrine(dest)
        for label, rp, wanted in (("codex", codex_rp, want_codex), ("agy", agy_rp, want_agy)):
            if wanted:
                print(f"{label} peer doctrine {seed_peer_doctrine(rp, block)} in {rp}", file=out)
        if want_codex:
            print(f"codex send rule {seed_file(codex_xp, render_codex_exec_rule(dest))} in {codex_xp}", file=out)
    except OSError as exc:
        print(f"WARN: peer doctrine not installed: {exc}", file=out)
    _seed_standing_doctrine(out, want_codex, want_agy, codex_rp, agy_rp, codex_sd, agy_sj)
    if engine_root:
        print(f"governance engine root: {engine_root} ({provenance})", file=out)
        if verified:
            print("hook wiring/trust verified: Codex SessionStart and PreToolUse handlers discovered, "
                  "enabled and trusted", file=out)
        elif want_codex:
            print("hook wiring/trust UNVERIFIED: Codex handler trust was not confirmed", file=out)
        print("governance enforcement UNVERIFIED until the C6 live matrix", file=out)
    else:
        print(f"governance DEGRADED: engine root unresolved ({provenance}); guards answer the neutral "
              "fallback (ask on agy, {} on Codex), never allow", file=out)
    print("governance scope: shell-command PreToolUse only (Codex Bash, agy run_command)", file=out)
    return rc


def _seed_standing_doctrine(out, want_codex, want_agy, codex_rp, agy_rp, codex_sd, agy_sj):
    """Seed the coordinator-doctrine block and skills for the wanted hosts; every miss is a WARN, never a refusal."""
    seed = _seed()
    root = doctrine_root()
    for label, rp, wanted, cap in (("codex", codex_rp, want_codex, seed.CODEX_CAP_BYTES),
                                   ("agy", agy_rp, want_agy, seed.AGY_CAP_BYTES)):
        if not wanted:
            continue
        try:
            if root is None:
                raise OSError("global-doctrine/ not found beside this install")
            res = seed.seed_block(rp, seed.render_coordinator_doctrine(root, cap), seed.DOCTRINE_BEGIN, seed.DOCTRINE_END)
            print(f"{label} coordinator doctrine {res} in {rp}", file=out)
        except (OSError, ValueError) as exc:
            print(f"WARN: {label} coordinator doctrine not installed: {exc}", file=out)
    try:
        if want_agy:
            print(f"agy skills {seed.seed_agy_skills(agy_sj, SKILLS_ROOT)} in {agy_sj}", file=out)
        if want_codex:
            names = seed.seed_codex_skills(codex_sd, SKILLS_ROOT)
            print(f"codex skills seeded {len(names)} in {codex_sd}", file=out)
    except (OSError, ValueError) as exc:
        print(f"WARN: skills not installed: {exc}", file=out)


if __name__ == "__main__":
    sys.exit(main())
