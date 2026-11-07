"""Unimatrix installer: Claude Code version-range gate plus copy of the vendored scripts.

Default mode checks `claude --version` against VERIFIED_RANGE; `--install` copies
VENDORED_SCRIPTS into <settings home>/unimatrix. Outside the range the gate refuses;
`--force` downgrades the refusal to a warning. Stdlib only, portable across
macOS, Windows and Linux.
"""
import argparse
import importlib.util
import json
import ntpath
import os
import posixpath
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
    "unimatrix-autolink.py",
    "unimatrix-liveness.py",
    "unimatrix-mirror-all.py",
    "unimatrix-reshape.py",
    "unimatrix-membership.py",
    "unimatrix-doctor.py",
    "unimatrix-pair.py",
)

AUTOLINK_SCRIPT = "unimatrix-autolink.py"
_SCRIPT_REF = re.compile(r"unimatrix-[a-z0-9-]+\.py")

AGY_HOOK_KEY = "unimatrix-agy-leg"
AGY_HOOK_SCRIPT = "unimatrix-agy-hook-pretool.py"
AGY_SESSIONSTART_SCRIPT = "unimatrix-agy-hook-sessionstart.py"
CODEX_SESSIONSTART_SCRIPT = "unimatrix-codex-hook-sessionstart.py"
GUARD_SCRIPT = "unimatrix-host-guard.py"
DOCTRINE_SEED_SCRIPT = "unimatrix-doctrine-seed.py"
PLUGIN_GEN_SCRIPT = "unimatrix-plugin-gen.py"
AGY_PLUGIN_TREE_DIR = "agy-plugin"
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


def script_closure(src_dir, root=AUTOLINK_SCRIPT):
    """Every unimatrix-*.py script named, transitively, from `root` in src_dir (root included)."""
    seen, todo = set(), [root]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        path = Path(src_dir) / name
        if path.is_file():
            todo.extend(_SCRIPT_REF.findall(path.read_text(encoding="utf-8")))
    return seen


def install_scripts(src_dir, dest_dir):
    """Copy VENDORED_SCRIPTS plus the autolink closure from src_dir into dest_dir; return the copied names."""
    wanted = list(VENDORED_SCRIPTS) + sorted(script_closure(src_dir) - set(VENDORED_SCRIPTS))
    missing = [n for n in wanted if not (Path(src_dir) / n).is_file()]
    if missing:
        raise FileNotFoundError(f"vendored scripts missing in {src_dir}: {', '.join(missing)}")
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    for name in wanted:
        shutil.copy2(Path(src_dir) / name, dest / name)
    extra = [n for n in OPTIONAL_SCRIPTS if n not in wanted and (Path(src_dir) / n).is_file()]
    for name in extra:
        shutil.copy2(Path(src_dir) / name, dest / name)
    return wanted + extra


HOMEBREW_PYTHONS = ("/opt/homebrew/bin/python3", "/usr/local/bin/python3")


def forced_command_interpreter():
    """Absolute interpreter for the forced command. On macOS sshd's PATH python3 is the CLT stub, so a
    Homebrew python3 wins over sys.executable when one exists."""
    if sys.platform == "darwin":
        for cand in HOMEBREW_PYTHONS:
            if os.path.isfile(cand) and os.name == "posix" and os.access(cand, os.X_OK):
                return cand
    return sys.executable


def authorized_keys_line(dest_dir, interpreter=None, key_body="<key-body>"):
    """Paste-ready `restrict,command=...` authorized_keys line; `key_body` defaults to the <key-body> placeholder.
    A path with a space is quoted inside the command and each inner quote escaped for sshd."""
    interp = interpreter or forced_command_interpreter()
    relay = str(Path(dest_dir) / "unimatrix-relay.py")
    parts = [f'\\"{p}\\"' if " " in p else p for p in (interp, relay)]
    return f'restrict,command="{" ".join(parts)}" ssh-ed25519 {key_body} unimatrix'


FAR_DEST_DIR = "~/.coordinator-claude-settings/unimatrix"
FAR_INTERPRETER = "python3"
_ALIAS_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_SIBLINGS = {}


def _sibling(script):
    """A sibling unimatrix script loaded once from beside this file."""
    if script not in _SIBLINGS:
        spec = importlib.util.spec_from_file_location("unimatrix_" + script[9:-3].replace("-", "_"), _BIN_DIR / script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SIBLINGS[script] = mod
    return _SIBLINGS[script]


def _pub_body(pub_path):
    """The base64 body of an ssh public key file; ValueError when it is not an ssh-ed25519 line."""
    fields = Path(pub_path).read_text(encoding="utf-8").split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise ValueError(f"{pub_path} is not an ssh-ed25519 public key")
    return fields[1]


def pair_key(alias, run=subprocess.run):
    """Return (private key path, public key body) for this box's pair with `alias`. Reads the key autolink's
    resolve_key finds when it is alias-specific and present; otherwise mints (or adopts an unrecorded file at)
    <settings home>/.secrets/ssh/unimatrix-<alias> and records unimatrix.keys.<alias>. Never overwrites a key.
    RuntimeError when the alias reduces to nothing, ssh-keygen fails, or the machine-local record cannot be made."""
    autolink, roster = _sibling(AUTOLINK_SCRIPT), _sibling("unimatrix-roster.py")
    found = autolink.resolve_key(
        roster, alias,
        local_fn=lambda r, a: autolink.machine_local_key(r, a, run=run),
        ssh_fn=lambda r, a: autolink.ssh_identity_file(r, a, run=run))
    if found != roster.default_key() and Path(found).is_file():
        priv = Path(found)
    else:
        safe = _ALIAS_UNSAFE.sub("-", alias)
        if not safe.strip("-"):
            raise RuntimeError(f"alias {alias!r} has no usable characters for a key file name")
        priv = roster.settings_home() / ".secrets" / "ssh" / f"unimatrix-{safe}"
        reader = roster.settings_home() / "bin" / "_machine_local.py"
        if not reader.is_file():
            raise RuntimeError(f"{reader} is missing; an unrecorded pair key would not be found next run")
        if not priv.is_file():
            priv.parent.mkdir(parents=True, exist_ok=True)
            kg = run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "unimatrix", "-f", str(priv)],
                     capture_output=True, text=True, timeout=30, creationflags=roster.no_window())
            if kg.returncode or not priv.is_file():
                raise RuntimeError(f"ssh-keygen failed: {(kg.stderr or kg.stdout or '').strip()[:200]}")
        rec = run([sys.executable, str(reader), "set", f"{autolink.KEYS_PREFIX}{alias}", str(priv)],
                  capture_output=True, text=True, timeout=30, creationflags=roster.no_window())
        if rec.returncode:
            raise RuntimeError(f"recording {autolink.KEYS_PREFIX}{alias} failed: "
                               f"{(rec.stderr or rec.stdout or '').strip()[:200]}")
    pub = Path(str(priv) + ".pub")
    if not pub.is_file():
        raise RuntimeError(f"{pub} is missing; cannot read the public key of {priv}")
    return priv, _pub_body(pub)


def render_ssh_config_block(alias, key_path):
    """The near-side `~/.ssh/config` block for the pair; printed, never written."""
    return (f"Host {alias}\n"
            f"    # HostName <address of {alias}>\n"
            f"    IdentityFile {Path(key_path).as_posix()}\n"
            f"    IdentitiesOnly yes\n")


_PROBE_PROGRAM = (
    "import os, sys\n"
    "h = os.environ.get('COORDINATOR_SETTINGS_HOME') or "
    "os.path.join(os.path.expanduser('~'), '.coordinator-claude-settings')\n"
    "print(sys.platform, sys.executable, h, sep='\\t')\n")

_APPEND_PROGRAM = '''import os, sys
body, line = {body!r}, {line!r}
if sys.platform == "win32":
    import ctypes
    if ctypes.windll.shell32.IsUserAnAdmin():
        print("admin")
        raise SystemExit(0)
ssh = os.path.join(os.path.expanduser("~"), ".ssh")
path = os.path.join(ssh, "authorized_keys")
if not os.path.isdir(ssh):
    os.makedirs(ssh)
    if os.name == "posix":
        os.chmod(ssh, 0o700)
text = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
if any(body in l.split() for l in text.splitlines()):
    print("present")
else:
    with open(path, "a", encoding="utf-8") as f:
        f.write(("" if not text or text.endswith("\\n") else "\\n") + line + "\\n")
    if os.name == "posix":
        os.chmod(path, 0o600)
    print("added")
'''


def _ssh_batch(alias, interp, program, run):
    """Run `interp -` on the far box with `program` on stdin, over the user's own credentials only."""
    return run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "--", alias, interp, "-"],
               input=program, capture_output=True, text=True, timeout=30,
               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def probe_far(alias, run=subprocess.run):
    """(interpreter name that answered, platform, absolute interpreter, far settings home), or None when no
    authorized link answers with that triple (a relay key's forced command answers with something else)."""
    for py in ("python3", "python"):
        try:
            r = _ssh_batch(alias, py, _PROBE_PROGRAM, run)
        except (OSError, subprocess.SubprocessError):
            continue
        lines = (r.stdout or "").strip().splitlines()
        fields = lines[-1].split("\t") if r.returncode == 0 and lines else []
        if len(fields) == 3 and all(f.strip() for f in fields) and " " not in fields[0]:
            return py, fields[0], fields[1], fields[2]
    return None


def install_over_link(alias, body, run=subprocess.run):
    """Append the pair's authorized_keys line on the far box over an already-authorized BatchMode link.
    Returns (status, line): status is added | present | admin | no-link | failed; `line` is the line with the far
    box's own interpreter and relay directory (None for no-link). Never prompts, never sudo, never the relay key."""
    far = probe_far(alias, run)
    if far is None:
        return "no-link", None
    py, plat, interp, home = far
    join = ntpath.join if plat == "win32" else posixpath.join
    line = authorized_keys_line(join(home, "unimatrix"), interp, body)
    try:
        r = _ssh_batch(alias, py, _APPEND_PROGRAM.format(body=body, line=line), run)
    except (OSError, subprocess.SubprocessError):
        return "failed", line
    out = (r.stdout or "").strip().splitlines()
    status = out[-1] if r.returncode == 0 and out else ""
    return (status if status in ("added", "present", "admin") else "failed"), line


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


LOGIN_AGENT_LABEL = "com.unimatrix.autolink"
LOGIN_TASK_NAME = "UnimatrixAutolink"
LOGIN_UNIT = "unimatrix-autolink.service"


def run_schtasks(*args):
    """Run schtasks.exe; None when it cannot launch."""
    try:
        return subprocess.run(["schtasks.exe", *args], capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None


def login_agent_dir():
    """Where this OS reads user login agents; None on a platform with none."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents"
    if sys.platform.startswith("linux"):
        return Path.home() / ".config" / "systemd" / "user"
    return None


def _autolink_argv(dest_dir):
    return [sys.executable, str(Path(dest_dir) / AUTOLINK_SCRIPT)]


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _winreg():
    import winreg
    return winreg


def _windows_run_command(dest_dir):
    """Autolink command line for the HKCU Run value; pythonw.exe beside the interpreter keeps it windowless."""
    argv = _autolink_argv(dest_dir)
    pythonw = Path(argv[0]).with_name("pythonw.exe")
    if pythonw.is_file():
        argv[0] = str(pythonw)
    return subprocess.list2cmdline(argv)


def _delete_run_value():
    """Delete the HKCU Run value; True when one was there."""
    wr = _winreg()
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as key:
            wr.DeleteValue(key, LOGIN_TASK_NAME)
    except FileNotFoundError:
        return False
    return True


def _delete_login_task(schtasks=None, strict=False):
    """Delete a legacy scheduled task of the old registration; True when one was removed.

    Best effort unless strict, where a found task that will not delete raises OSError.
    """
    run = schtasks or run_schtasks
    found = run("/Query", "/TN", LOGIN_TASK_NAME)
    if found is None or found.returncode != 0:
        return False
    proc = run("/Delete", "/TN", LOGIN_TASK_NAME, "/F")
    if proc is None or proc.returncode != 0:
        if strict:
            raise OSError(f"schtasks /Delete {LOGIN_TASK_NAME} failed")
        return False
    return True


def _login_agent_text(dest_dir):
    """Bytes of the login-agent file for this OS: a RunAtLoad plist or a oneshot systemd unit. No restart, no interval."""
    argv = _autolink_argv(dest_dir)
    if sys.platform == "darwin":
        import plistlib
        return plistlib.dumps({"Label": LOGIN_AGENT_LABEL, "ProgramArguments": argv, "RunAtLoad": True,
                               "ProcessType": "Background", "LowPriorityIO": True})
    return ("[Unit]\nDescription=Unimatrix autolink at login\n\n[Service]\nType=oneshot\n"
            f"ExecStart={' '.join(shlex.quote(a) for a in argv)}\n\n[Install]\nWantedBy=default.target\n"
            ).encode("utf-8")


def _login_agent_paths(agent_dir):
    name = f"{LOGIN_AGENT_LABEL}.plist" if sys.platform == "darwin" else LOGIN_UNIT
    return Path(agent_dir) / name, Path(agent_dir) / "default.target.wants" / LOGIN_UNIT


def register_login_agent(dest_dir, agent_dir=None, schtasks=None):
    """Register one run-once-at-login agent for the installed autolink; return (state, where).

    state is "created", "updated" or "present" (plist / systemd unit), "registered" (Windows HKCU Run value,
    needs no elevation; overwritten in place and any legacy scheduled task removed), or "skipped"
    (no login-agent mechanism here, or the registry write failed).
    Plain file writes on macOS and Linux: picked up at next login, no process spawned.
    """
    if sys.platform == "win32":
        try:
            wr = _winreg()
            with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as key:
                wr.SetValueEx(key, LOGIN_TASK_NAME, 0, wr.REG_SZ, _windows_run_command(dest_dir))
        except OSError as exc:
            return "skipped", f"HKCU Run value write failed: {exc}"
        _delete_login_task(schtasks)
        return "registered", f"HKCU Run value {LOGIN_TASK_NAME}"
    root = Path(agent_dir) if agent_dir else login_agent_dir()
    if root is None:
        return "skipped", f"no login agent for platform {sys.platform!r}"
    target, link = _login_agent_paths(root)
    data = _login_agent_text(dest_dir)
    state = "created"
    if target.exists():
        state = "present" if target.read_bytes() == data else "updated"
    if state != "present":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if sys.platform != "darwin" and not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(f"../{LOGIN_UNIT}")
    return state, str(target)


def unregister_login_agent(agent_dir=None, schtasks=None):
    """Remove the login agent; return "removed" or "absent" (absence is not an error)."""
    if sys.platform == "win32":
        value = _delete_run_value()
        task = _delete_login_task(schtasks, strict=True)
        return "removed" if value or task else "absent"
    root = Path(agent_dir) if agent_dir else login_agent_dir()
    if root is None:
        return "absent"
    removed = False
    for path in _login_agent_paths(root):
        if path.is_symlink() or path.exists():
            path.unlink()
            removed = True
    return "removed" if removed else "absent"


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


def _plugin_gen():
    """The plugin-tree generator module, loaded from beside this file."""
    spec = importlib.util.spec_from_file_location("unimatrix_plugin_gen", _BIN_DIR / PLUGIN_GEN_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_agy_plugin_tree(args, out, dest=None):
    """Generate the agy plugin tree from --plugin-root (or PLUGIN_ROOT) into --out (or <dest>/agy-plugin).

    `dest` defaults to <settings home>/unimatrix. True when written; a generator OSError/ValueError
    prints WARN and returns False, never raises.
    """
    plugin_root = Path(args.plugin_root) if args.plugin_root else PLUGIN_ROOT
    tree = Path(args.out) if args.out else (dest or settings_home() / "unimatrix") / AGY_PLUGIN_TREE_DIR
    if not args.out and not plugin_root.is_dir():
        print(f"NOTE: agy plugin tree skipped: plugin root {plugin_root} not found (name one with --plugin-root)", file=out)
        return True
    try:
        report = _plugin_gen().generate(plugin_root, tree, "agy")
    except (OSError, ValueError) as exc:
        print(f"WARN: agy plugin tree not written: {exc}", file=out)
        return False
    print(f"agy plugin tree written {len(report['written'])} files in {tree}; "
          f"unmapped {len(report['unmapped'])} (see {tree / 'UNMAPPED.json'})", file=out)
    return True


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


def doctrine_root(plugin_root=None):
    """The directory holding global-doctrine/, or None when this install does not carry it.

    A named `plugin_root` replaces this script's own location as the search base. A flat published
    checkout keeps the tree under `templates/`, beside or inside the base.
    """
    base = Path(plugin_root) if plugin_root else PLUGIN_ROOT
    for root in (base.parent, base, base.parent / "templates", base / "templates"):
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
         agy_skills_json=None, codex_skills=None, agent_dir=None, schtasks=None, pair_run=None):
    """`hooks_path` overrides agy's file. Codex's file defaults to codex_hooks_path(), or to a sibling
    `codex-hooks.json` when only `hooks_path` is overridden; trust runs against the real Codex only for
    the default path, unless `codex_trust` (a callable taking the hooks path) is injected. The peer
    doctrine files follow the same rule: real home files by default, siblings `codex-AGENTS.md` and
    `agy-GEMINI.md` of `hooks_path` when it is overridden, or the explicit `codex_rules`/`agy_rules`.
    The login agent lives in the OS agent directory by default, a `login-agent` sibling of `hooks_path`
    when that is overridden, or `agent_dir`; `schtasks` (argv tail -> CompletedProcess) replaces the real
    Task Scheduler, which an overridden `hooks_path` otherwise skips."""
    out = out or sys.stdout
    if agent_dir is None and hooks_path is not None:
        agent_dir = Path(hooks_path).with_name("login-agent")
    if schtasks is None and hooks_path is not None:
        schtasks = lambda *a: None
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
    ap.add_argument("--pair", metavar="ALIAS", help="mint or read the pair key for a far box and print its "
                    "authorized_keys line and ssh config block")
    ap.add_argument("--plugin-root", metavar="DIR", help="seed Codex and agy doctrine and skills from this plugin "
                    "root (doctrine in DIR.parent or DIR, skills in DIR/skills) instead of this script's own location")
    ap.add_argument("--out", metavar="DIR", help="write the agy plugin tree (translated plugin source) into DIR; "
                    f"default under --install: <settings home>/unimatrix/{AGY_PLUGIN_TREE_DIR}")
    args = ap.parse_args(argv)
    skills_root = Path(args.plugin_root) / "skills" if args.plugin_root else SKILLS_ROOT
    if args.pair is not None:
        try:
            priv, body = pair_key(args.pair, run=pair_run or subprocess.run)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"REFUSE: {exc}", file=out)
            return 6
        print(f"pair key for {args.pair}: {priv}", file=out)
        if _sibling("unimatrix-membership.py").load_pin(_sibling("unimatrix-roster.py").settings_home()) is not None:
            print(f"signer pin present: no ssh config or authorized_keys edit. On this box run "
                  f"`python {_sibling('unimatrix-roster.py').settings_home() / 'unimatrix' / 'unimatrix-pair.py'} "
                  f"request --box {args.pair}` and give the JSON to the operator, who runs `unimatrix-pair.py "
                  f"approve <request-file>` (the approval is the only 1Password prompt).", file=out)
            return 0
        print("no signer pin (pre-membership): ssh config block for this box (add to ~/.ssh/config):", file=out)
        print(render_ssh_config_block(args.pair, priv), file=out)
        print(f"authorized_keys line for the far box (interpreter and path are placeholders: {FAR_INTERPRETER} "
              f"and {FAR_DEST_DIR}; replace with the far box's absolute ones):", file=out)
        print(authorized_keys_line(FAR_DEST_DIR, FAR_INTERPRETER, body), file=out)
        status, line = install_over_link(args.pair, body, run=pair_run or subprocess.run)
        if status == "no-link":
            print(f"no authorized link to {args.pair}: paste the line above on the far box", file=out)
        elif status == "failed":
            print(f"install over the link to {args.pair} failed: paste this line on the far box:\n{line}", file=out)
        elif status == "admin":
            print(f"{args.pair} is a Windows administrator account: nothing written. Append this line to "
                  f"%ProgramData%\\ssh\\administrators_authorized_keys on the far box:\n{line}", file=out)
        else:
            print(f"authorized_keys line {'already present' if status == 'present' else 'added'} on {args.pair}; "
                  f"line:\n{line}", file=out)
        return 0
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
            steps.append(("agy skills", agy_sj, lambda: _seed().unseed_agy_skills(agy_sj, skills_root)))
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
        steps.append(("login agent", agent_dir or login_agent_dir() or LOGIN_TASK_NAME,
                      lambda: unregister_login_agent(agent_dir, schtasks)))
        for label, where, fn in steps:
            try:
                res = fn()
            except (ValueError, OSError) as exc:
                print(f"REFUSE: {exc}", file=out)
                return 4
            print(f"{label} {res} in {where}", file=out)
        return 0

    if version_text is None:
        gate_skipped = hosts is not None and "claude" not in hosts
        if gate_skipped:
            print("NOTE: --hosts names no claude; Claude version-range gate skipped", file=out)
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
    if want_agy and args.out and not args.install:
        if _write_agy_plugin_tree(args, out):
            return 0
        print("PARTIAL INSTALL: not installed: agy plugin tree", file=out)
        return 7
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
    print(f"authorized_keys line for the far side (paste verbatim, fill <key-body>): "
          f"{authorized_keys_line(dest)}", file=out)
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
    missing = []
    if want_agy:
        _seed_agy_config(hp.with_name("config.json"), out)
        if not _write_agy_plugin_tree(args, out, dest):
            missing.append("agy plugin tree")
    try:
        block = render_peer_doctrine(dest)
    except (OSError, ValueError) as exc:
        block = None
        print(f"WARN: peer doctrine not installed: {exc}", file=out)
    for label, rp, wanted in (("codex", codex_rp, want_codex), ("agy", agy_rp, want_agy)):
        if not wanted:
            continue
        try:
            if block is None:
                raise OSError("peer doctrine template unreadable")
            print(f"{label} peer doctrine {seed_peer_doctrine(rp, block)} in {rp}", file=out)
        except (OSError, ValueError) as exc:
            missing.append(f"{label} peer doctrine")
            if block is not None:
                print(f"WARN: {label} peer doctrine not installed: {exc}", file=out)
    if want_codex:
        try:
            print(f"codex send rule {seed_file(codex_xp, render_codex_exec_rule(dest))} in {codex_xp}", file=out)
        except (OSError, ValueError) as exc:
            missing.append("codex send rule")
            print(f"WARN: codex send rule not installed: {exc}", file=out)
    missing += _seed_standing_doctrine(out, want_codex, want_agy, codex_rp, agy_rp, codex_sd, agy_sj,
                                       args.plugin_root, skills_root)
    if missing:
        print(f"PARTIAL INSTALL: not installed: {', '.join(missing)}", file=out)
        rc = rc or 7
    try:
        state, where = register_login_agent(dest, agent_dir, schtasks)
        print(f"login agent {state}: {where}" if state != "skipped" else f"WARN: login agent not registered: {where}", file=out)
    except OSError as exc:
        print(f"WARN: login agent not registered: {exc}", file=out)
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


def _seed_standing_doctrine(out, want_codex, want_agy, codex_rp, agy_rp, codex_sd, agy_sj,
                            plugin_root=None, skills_root=None):
    """Seed the coordinator-doctrine block and skills for the wanted hosts; every miss is a WARN, never a refusal.

    Returns the "<host> coordinator doctrine" surfaces left uninstalled.
    """
    seed = _seed()
    missing = []
    skills_root = skills_root or SKILLS_ROOT
    root = doctrine_root(plugin_root) if plugin_root else doctrine_root()
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
            missing.append(f"{label} coordinator doctrine")
            print(f"WARN: {label} coordinator doctrine not installed: {exc}", file=out)
    try:
        if want_agy:
            print(f"agy skills {seed.seed_agy_skills(agy_sj, skills_root)} in {agy_sj}", file=out)
        if want_codex:
            names = seed.seed_codex_skills(codex_sd, skills_root)
            print(f"codex skills seeded {len(names)} in {codex_sd}", file=out)
    except (OSError, ValueError) as exc:
        print(f"WARN: skills not installed: {exc}", file=out)
    return missing


def _seed_agy_config(path, out):
    """Create agy's config.json as `{}` at mode 0600 only when absent; an existing file is never touched."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"agy config present in {path}", file=out)
        return
    except OSError as exc:
        print(f"WARN: agy config not seeded: {exc}", file=out)
        return
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    print(f"agy config created in {path}", file=out)


if __name__ == "__main__":
    sys.exit(main())
