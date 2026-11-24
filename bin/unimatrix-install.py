#!/usr/bin/env python3
"""Unimatrix installer: Claude Code version-range gate plus copy of the vendored scripts.

Default mode checks `claude --version` against VERIFIED_RANGE; `--install` copies
VENDORED_SCRIPTS into <settings home>/unimatrix. Outside the range the gate refuses;
`--force` downgrades the refusal to a warning. Stdlib only, portable across
macOS, Windows and Linux.
"""
import argparse
import getpass
import hashlib
import importlib.util
import ipaddress
import json
import ntpath
import os
import posixpath
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

MIN_PYTHON = (3, 11)
HOMEBREW_PYTHONS = ("/opt/homebrew/bin/python3", "/usr/local/bin/python3")  # literal: the installer must import without lib/ beside it
_REEXEC_ENV = "UNIMATRIX_INSTALL_REEXEC"


def _gate_pin():
    """The `unimatrix.python` pin when it names a file, else None; best-effort, any failure reads as unset.
    Loads the sibling scripts by path: lib/ need not be importable and this interpreter is the old one."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))

        def load(script):
            spec = importlib.util.spec_from_file_location("unimatrix_gate_" + script[9:-3].replace("-", "_"),
                                                          os.path.join(here, script))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        val = load("unimatrix-autolink.py").pin_key_value(load("unimatrix-roster.py"))
        return val if val and os.path.isfile(val) else None
    except Exception:
        return None


def _runs_modern(exe):
    """True when *exe* starts and reports a version of at least MIN_PYTHON."""
    code = "import sys;sys.exit(0 if sys.version_info>=%r else 1)" % (MIN_PYTHON,)
    try:
        return subprocess.call([exe, "-c", code], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _reexec(exe, argv):
    """Replace this process with *exe* running *argv*; Windows has no true exec, so it relays the exit code."""
    if sys.platform == "win32":
        raise SystemExit(subprocess.call([exe, *argv], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
    os.execv(exe, [exe, *argv])


def ensure_modern_python(version_info=None, platform=None, env=None, pin=None, probe=None, reexec=None, argv=None):
    """Before tomllib is imported: on an interpreter older than MIN_PYTHON, re-exec the same argv under the
    `unimatrix.python` pin, else (darwin) the first HOMEBREW_PYTHONS candidate, that runs MIN_PYTHON or newer;
    none qualifies (or this is already the re-exec) is a SystemExit naming the required version. A no-op otherwise."""
    if tuple(version_info or sys.version_info)[:2] >= MIN_PYTHON:
        return
    env = os.environ if env is None else env
    need = "%d.%d" % MIN_PYTHON
    ran = "%s (%s)" % (sys.executable, ".".join(str(p) for p in tuple(version_info or sys.version_info)[:3]))
    if env.get(_REEXEC_ENV):
        raise SystemExit("unimatrix-install requires Python %s or newer; the re-exec under %s is still older" % (need, ran))
    probe = probe or _runs_modern
    candidates = []
    pinned = (pin or _gate_pin)()
    if pinned:
        candidates.append(pinned)
    if (platform or sys.platform) == "darwin":
        candidates.extend(c for c in HOMEBREW_PYTHONS if os.path.isfile(c) and os.access(c, os.X_OK))
    for exe in candidates:
        if probe(exe):
            env[_REEXEC_ENV] = "1"
            (reexec or _reexec)(exe, list(sys.argv if argv is None else argv))
            return
    raise SystemExit("unimatrix-install requires Python %s or newer; running under %s and no pinned or Homebrew "
                     "Python %s was found (set machine-local unimatrix.python to one)" % (need, ran, need))


ensure_modern_python()

import tomllib
import tempfile
import types
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
    "unimatrix-local-transport.py",
    "unimatrix-peer-codex.py",
    "unimatrix-codex-launch.py",
    "unimatrix-peer-agy.py",
    "unimatrix-peer-grok.py",
    "unimatrix-agy-leg.py",
    "unimatrix-peer-router.py",
    "unimatrix-agy-hook-pretool.py",
    "unimatrix-agy-hook-launch.py",
    "unimatrix-agy-hook-sessionstart.py",
    "unimatrix-codex-hook-sessionstart.py",
    "unimatrix-host-guard.py",
    "coordinator-external-session.py",
    "unimatrix-doctrine-seed.py",
    "unimatrix-autolink.py",
    "unimatrix-liveness.py",
    "unimatrix-mirror-all.py",
    "unimatrix-reshape.py",
    "unimatrix-membership.py",
    "unimatrix-doctor.py",
    "unimatrix-pair.py",
    "unimatrix-install.py",
    "unimatrix-file.py",
    "unimatrix-file-relay.py",
    "unimatrix-passphrase.py",
    "unimatrix-control.py",
    "unimatrix-tui-status-launch.py",
    "headless-em-launch.py",
)

AUTOLINK_SCRIPT = "unimatrix-autolink.py"
PASSPHRASE_SCRIPT = "unimatrix-passphrase.py"
STAGING_SUFFIX = ".new"
_SCRIPT_REF = re.compile(r"unimatrix-[a-z0-9-]+\.py")

AGY_HOOK_KEY = "unimatrix-agy-leg"
AGY_HOOK_SCRIPT = "unimatrix-agy-hook-pretool.py"
AGY_SESSIONSTART_SCRIPT = "unimatrix-agy-hook-sessionstart.py"
CODEX_SESSIONSTART_SCRIPT = "unimatrix-codex-hook-sessionstart.py"
GUARD_SCRIPT = "unimatrix-host-guard.py"
EXTERNAL_SESSION_SCRIPT = "coordinator-external-session.py"
DOCTRINE_SEED_SCRIPT = "unimatrix-doctrine-seed.py"
PLUGIN_GEN_SCRIPT = "unimatrix-plugin-gen.py"
AGY_PLUGIN_TREE_DIR = "agy-plugin"
CODEX_SHELL_MATCHER = ".*"
GROK_TOOL_MATCHER = ("Bash|bash|shell|run_command|run_shell_command|"
                     "Edit|Write|MultiEdit|NotebookEdit|edit_file|write_file|"
                     "run_terminal_command|run_terminal_cmd|Shell|search_replace|hashline_edit|"
                     "StrReplace|EditNotebook|Delete|write|"
                     "read_file|spawn_subagent")
GROK_HOOKS_FILE = "coordinator.json"
# agy shell plus every edit tool the engine agy adapter maps to a write guard
# (coordinator_core/host_hooks/agy_adapter.py `_EDIT_TOOLS`); a tool missing here never reaches the guard.
AGY_TOOL_MATCHER = ("run_command|write_file|write_to_file|edit_file|replace_file_content|"
                    "multi_replace_file_content|sed_file|notebook_edit")
HOST_NAMES = ("claude", "codex", "agy", "grok")

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


def resolve_claude():
    """PATH first, then the default install dirs a non-login ssh PATH lacks; None if absent."""
    exe = shutil.which("claude")
    if exe:
        return exe
    home = Path.home()
    names = ("claude.exe", "claude.cmd") if sys.platform == "win32" else ("claude",)
    dirs = [home / ".local" / "bin", home / ".claude" / "local", home / ".npm-global" / "bin",
            home / ".bun" / "bin", home / ".volta" / "bin"]
    if sys.platform == "win32":
        dirs.append(Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "npm")
    else:
        dirs += [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    for d in dirs:
        for n in names:
            cand = d / n
            if cand.is_file() and _is_executable(cand):
                return str(cand)
    return None


def _is_executable(path):
    """Windows has no exec bit: any file counts; POSIX asks the mode."""
    return sys.platform == "win32" or os.access(path, os.X_OK)


def probe_claude_version():
    """Run `claude --version`; shutil.which resolves claude.cmd on Windows."""
    exe = resolve_claude()
    if not exe:
        raise RuntimeError("claude not found on PATH or in default install dirs; cannot read the harness version")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, **kwargs)
    return out.stdout or ""


_UM_PATHS = None


def _um_paths():
    global _UM_PATHS
    if _UM_PATHS is None:
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        has_pkg = "_unimatrix" in sys.modules or os.path.isdir(os.path.join(bin_dir, "_unimatrix"))
        if "_unimatrix" not in sys.modules and os.path.isdir(os.path.join(bin_dir, "_unimatrix")):
            if bin_dir not in sys.path:
                sys.path.insert(0, bin_dir)
        if has_pkg:
            import _unimatrix.paths as mod  # noqa: E402
            _UM_PATHS = mod
        else:
            _UM_PATHS = False
    return _UM_PATHS or None


def settings_home():
    mod = _um_paths()
    if mod is not None:
        return mod.settings_home()
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def script_closure(src_dir, root=AUTOLINK_SCRIPT):
    """Every unimatrix-*.py script named, transitively, from `root` in src_dir (root included)."""
    # Trap: the scan is textual, so any vendored script whose prose names this installer would drag the
    # installer and everything it names (plugin-gen) into the runtime closure; the installer is never one.
    seen, todo = set(), [root]
    while todo:
        name = todo.pop()
        if name in seen or name == Path(__file__).name:
            continue
        seen.add(name)
        path = Path(src_dir) / name
        if path.is_file():
            todo.extend(_SCRIPT_REF.findall(path.read_text(encoding="utf-8")))
    return seen


ROUTER_SCRIPT = "unimatrix-peer-router.py"
PIPE_MARKER = "PipeServer"
ROUTER_RESTART_REFUSED_RC = 8


def router_closure_digest(src_dir):
    """sha256 over the sorted (name, bytes) of the router's script closure and lib/*.py in src_dir; None without the router script."""
    root = Path(src_dir)
    if not (root / ROUTER_SCRIPT).is_file():
        return None
    names = sorted(script_closure(root, ROUTER_SCRIPT)) + [f"lib/{p.name}" for p in sorted((root / "lib").glob("*.py"))]
    h = hashlib.sha256()
    for name in sorted(names):
        try:
            data = (root / name).read_bytes()
        except OSError:
            continue
        h.update(name.encode("utf-8") + b"\0" + data + b"\0")
    return h.hexdigest()


def _installed_autolink(dest):
    """The INSTALLED unimatrix-autolink module, so a restart spawns the installed router; None when absent."""
    path = Path(dest) / AUTOLINK_SCRIPT
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("unimatrix_autolink_installed", path)
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


def router_is_live(dest):
    """True while a router holds the lease under `dest` (the installed autolink's own check)."""
    try:
        mod = _installed_autolink(dest)
        check = getattr(mod, "router_lock_held", None)
        return bool(check and check(Path(dest)))
    except Exception:
        return False


def restart_installed_router(dest, say):
    """Hand the box over to the installed router through the installed autolink's `restart_router`."""
    mod = _installed_autolink(dest)
    restart = getattr(mod, "restart_router", None)
    if restart is None:
        raise RuntimeError(f"installed {AUTOLINK_SCRIPT} has no restart_router")
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        return restart(mod._roster(), Path(dest), say)
    finally:
        sys.dont_write_bytecode = keep


class PipeCapabilityRefused(Exception):
    """A win32 install that would ship or keep a router without the Win32 named-pipe transport."""


def _has_pipe_marker(path):
    try:
        return PIPE_MARKER in Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def check_win32_pipe_capability(src_dir, dest_dir):
    """On win32, refuse a source router lacking the pipe transport (which also covers downgrading an
    installed pipe-capable router). No-op elsewhere."""
    if sys.platform != "win32":
        return
    if _has_pipe_marker(Path(src_dir) / ROUTER_SCRIPT):
        return
    installed = _has_pipe_marker(Path(dest_dir) / ROUTER_SCRIPT)
    what = "would downgrade the installed pipe-capable router" if installed else "carries no pipe transport"
    raise PipeCapabilityRefused(
        f"source {ROUTER_SCRIPT} {what}: missing Win32 named-pipe capability ({PIPE_MARKER}); "
        f"install from the klabauter published mirror tree")


def install_scripts(src_dir, dest_dir, on_copy=None):
    """Copy VENDORED_SCRIPTS plus the autolink closure from src_dir into dest_dir; return the copied names.
    Raises PipeCapabilityRefused on win32 before any copy when the source router lacks the pipe transport."""
    _um_paths()
    wanted = list(VENDORED_SCRIPTS) + sorted(script_closure(src_dir) - set(VENDORED_SCRIPTS))
    missing = [n for n in wanted if not (Path(src_dir) / n).is_file()]
    if missing:
        raise FileNotFoundError(f"vendored scripts missing in {src_dir}: {', '.join(missing)}")
    check_win32_pipe_capability(src_dir, dest_dir)
    dest = Path(dest_dir)
    _mkdir_0755(dest)
    for name in wanted:
        _copy_if_changed(Path(src_dir) / name, dest / name, on_copy)
    for name in VENDORED_LIB:
        if (Path(src_dir) / "lib" / name).is_file():
            _mkdir_0755(dest / "lib")
            _copy_if_changed(Path(src_dir) / "lib" / name, dest / "lib" / name, on_copy)
    core_pkg = Path(src_dir) / "_unimatrix"
    if core_pkg.is_dir():
        for src_py in sorted(core_pkg.rglob("*.py")):
            if "__pycache__" in src_py.parts:
                continue
            rel = src_py.relative_to(src_dir)
            _mkdir_0755((dest / rel).parent)
            _copy_if_changed(src_py, dest / rel, on_copy)
    extra = [n for n in OPTIONAL_SCRIPTS if n not in wanted and (Path(src_dir) / n).is_file()]
    for name in extra:
        _copy_if_changed(Path(src_dir) / name, dest / name, on_copy)
    return wanted + extra


def _mkdir_0755(path):
    """Create `path` and each missing ancestor, forcing 0755 on every directory this call creates so a
    restrictive umask cannot leave a directory the session user cannot traverse. Existing directories keep their mode."""
    missing = []
    for p in (path, *path.parents):
        if p.exists():
            break
        missing.append(p)
    for p in reversed(missing):
        try:
            p.mkdir()
        except FileExistsError:
            continue
        if os.name != "nt":
            os.chmod(p, 0o755)


def untraversable_path_dirs(path_env=None):
    """PATH entries that exist as directories but the current user cannot list or traverse (POSIX only; [] on Windows)."""
    if os.name == "nt":
        return []
    bad = []
    for d in (os.environ.get("PATH", "") if path_env is None else path_env).split(os.pathsep):
        if d and d not in bad and os.path.isdir(d) and not os.access(d, os.R_OK | os.X_OK):
            bad.append(d)
    return bad


def _copy_if_changed(src, dst, on_copy=None):
    """copy2 unless dst already holds the same bytes: an unchanged script keeps its st_ctime, which the
    relay reap reads as the moment the code last changed."""
    try:
        if dst.read_bytes() == src.read_bytes():
            return
    except OSError:
        pass
    shutil.copy2(src, dst)
    if on_copy is not None:
        on_copy(dst)


VENDORED_LIB = ("python_interp.py", "unimatrix_box_mux.py", "unimatrix_relay_sessions.py", "session_detach.py",
                "unimatrix_pair_contract.py", "cc_invoke.py", "engine_bootstrap.py",
                "machine_local_impl_resolve.py", "unimatrix_far_addresses.py", "unimatrix_capabilities.py", "__init__.py")  # sibling lib/ modules the installed scripts load by path or import; __init__ makes `import lib` put lib/ on sys.path
UNSHIPPED_LIB = ("unimatrix_test_home.py",)  # loaded by path only under UNIMATRIX_TEST_HOME; absent from installs by design


def _lib(name):
    """A sibling lib/ module loaded once by path (the installed layout has no package)."""
    if name not in _LIBS:
        spec = importlib.util.spec_from_file_location(f"unimatrix_lib_{name}", _BIN_DIR / "lib" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LIBS[name] = mod
    return _LIBS[name]


_LIBS = {}


def _console_python():
    """A real console CPython for a child argv or a rendered command; OSError when none resolves."""
    found = _lib("python_interp").resolve_console_python()
    if not found:
        raise FileNotFoundError("no console Python interpreter resolvable")
    return found


def _machine_local_spawn():
    """`coordinator_core.machine_local_spawn` with the engine on sys.path, or None when no engine resolves."""
    try:
        from coordinator_core import machine_local_spawn
        return machine_local_spawn
    except ImportError:
        pass
    try:
        sys.path.insert(0, str(_BIN_DIR))
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import ensure_engine_on_path

        ensure_engine_on_path(str(_BIN_DIR / "unimatrix-install.py"))
        from coordinator_core import machine_local_spawn
        return machine_local_spawn
    except Exception:
        return None


def _machine_local_run(run, argv):
    """Run a machine-local reader argv: the injected `run` when a caller supplied one, else the bounded helper.

    A helper that is absent, fails to start or outlives its ceiling reads as exit 2 with a stderr line."""
    if run is not subprocess.run:
        return run(argv, capture_output=True, text=True, timeout=30, creationflags=_sibling("unimatrix-roster.py").no_window())
    helper = _machine_local_spawn()
    done = helper.run_bounded(argv) if helper else None
    return done or subprocess.CompletedProcess(argv, 2, "", "machine-local spawn unavailable, failed or timed out")


_PIN_UNREAD = object()
PYTHON_PIN_KEY = "unimatrix.python"
_PIN_CACHE = {}


def _pin_value():
    """The machine-local `unimatrix.python` value autolink reads, when it names a file; else None. One read per settings home."""
    # Trap: a non-login ssh session carries no env, and the roster's settings_home() is strict.
    os.environ.setdefault("COORDINATOR_SETTINGS_HOME", str(settings_home()))
    roster = _sibling("unimatrix-roster.py")
    home = str(roster.settings_home())
    if home not in _PIN_CACHE:
        try:
            val = _sibling(AUTOLINK_SCRIPT).pin_key_value(roster)
        except (OSError, subprocess.SubprocessError):
            val = None
        _PIN_CACHE[home] = val if val and os.path.isfile(val) else None
    return _PIN_CACHE[home]


def forced_command_interpreter(pin_value=_PIN_UNREAD):
    """Absolute interpreter for the forced command: the one autolink's mirror-all runs (`unimatrix.python`
    pin, else a Homebrew python3 on macOS where sshd's PATH python3 is the CLT stub, else the console python)."""
    if pin_value is _PIN_UNREAD:
        pin_value = _pin_value()
    return _lib("python_interp").unimatrix_python(pin_value, homebrew=HOMEBREW_PYTHONS) or sys.executable


def authorized_keys_line(dest_dir, interpreter=None, key_body="<key-body>", file_peer=None):
    """Paste-ready `restrict,command=...` authorized_keys line; `key_body` defaults to the <key-body> placeholder.
    A path with a space is quoted inside the command and each inner quote escaped for sshd.
    `file_peer` (the calling box) makes it the file key's line: the separate unimatrix-file-relay.py
    forced command with a fixed `--peer <box>`."""
    interp = interpreter or forced_command_interpreter()
    script = "unimatrix-file-relay.py" if file_peer is not None else "unimatrix-relay.py"
    parts = [f'\\"{p}\\"' if " " in p else p for p in (interp, str(Path(dest_dir) / script))]
    if file_peer is not None:
        parts += ["--peer", file_peer]
    return f'restrict,command="{" ".join(parts)}" ssh-ed25519 {key_body} unimatrix'


def control_authorized_keys_line(key_body, from_cidrs):
    """The control key's full-admin line: pinned only by `from=`, no `command=`, no `restrict`."""
    return f'from="{",".join(from_cidrs)}" ssh-ed25519 {key_body} unimatrix-control'


FAR_DEST_DIR = "~/.coordinator-claude-settings/unimatrix"
FAR_INTERPRETER = "python3"
FROM_CIDRS_PLACEHOLDER = "<from-cidrs>"
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


def _item_alias(priv):
    """The 1Password item alias of a key file: its name less `unimatrix-` (the rule ensure_agent applies)."""
    name = Path(priv).name
    return name[len("unimatrix-"):] if name.startswith("unimatrix-") else name


def _mint(priv, comment, run, unencrypted, remint, on_mint=None):
    """Mint the key at `priv`: passphrase-encrypted with the 1Password item's passphrase unless `unencrypted`
    (then the plain `-N ""` ssh-keygen mint). A `remint` writes the new key (sibling path) and its item (staging
    title) first, replaces the superseded files, then deletes the superseded item and retitles the new one; a failure
    before the replace leaves the superseded key and item untouched. PassphraseSourceMissing / OnePasswordLocked
    propagate."""
    roster = _sibling("unimatrix-roster.py")
    alias = _item_alias(priv)
    mod = _sibling(PASSPHRASE_SCRIPT)
    stage = alias + STAGING_SUFFIX if remint and not unencrypted else alias
    target = Path(str(priv) + ".new") if remint else priv
    side = [target, Path(str(target) + ".pub")]
    if remint:
        for stale in side:
            stale.unlink(missing_ok=True)
    priv.parent.mkdir(parents=True, exist_ok=True)
    passphrase = None
    try:
        if not unencrypted:
            passphrase = mod.read_passphrase(mod.ensure_item(stage, run), run)
            try:
                mod.mint_key(target, comment, passphrase)
            except Exception as exc:
                # cryptography raises UnsupportedAlgorithm, not ImportError, when bcrypt (its OpenSSH
                # key-encryption backend) is absent.
                if not isinstance(exc, ImportError) and type(exc).__name__ != "UnsupportedAlgorithm":
                    raise
                raise RuntimeError(f"minting an encrypted key needs the `cryptography` and `bcrypt` packages ({exc}); "
                                   f"run `{sys.executable} -m pip install cryptography bcrypt`, or pass "
                                   f"--unencrypted-key") from exc
        else:
            kg = run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(target)],
                     capture_output=True, text=True, timeout=30, creationflags=roster.no_window())
            if kg.returncode or not target.is_file():
                raise RuntimeError(f"ssh-keygen failed: {(kg.stderr or kg.stdout or '').strip()[:200]}")
    except BaseException:
        if remint:
            for stale in side:
                stale.unlink(missing_ok=True)
            if not unencrypted:
                try:
                    mod.delete_item(stage, run)
                except RuntimeError:
                    pass
        raise
    if remint:
        for part in reversed(side):
            os.replace(part, priv if part == side[0] else Path(str(priv) + ".pub"))
        try:
            mod.delete_item(alias, run)
        except mod.PassphraseSourceMissing:
            if not unencrypted:
                raise
        except RuntimeError as exc:
            if not unencrypted:
                raise RuntimeError(f"the new key is in place but its passphrase item {mod.item_name(stage)} is not "
                                   f"yet titled {mod.item_name(alias)} (the superseded item could not be deleted: "
                                   f"{exc}); re-run --remint") from exc
        if not unencrypted:
            _retitle_item(mod, stage, alias, run)
    if not unencrypted and on_mint:
        on_mint(mod.op_ref(alias, run))


def _retitle_item(mod, stage, alias, run):
    """Rename the staging passphrase item to the alias's title; the new key is already in place, so a failure
    names the item that holds its passphrase."""
    r = mod._op(["item", "edit", mod.item_name(stage), f"--vault={mod._vault(run)}",
                 f"--title={mod.item_name(alias)}"], run)
    if r.returncode:
        raise RuntimeError(f"the new key is in place but its passphrase item {mod.item_name(stage)} could not be "
                           f"renamed to {mod.item_name(alias)}: {mod._tail(r)}")


def pair_key(alias, run=subprocess.run, unencrypted=False, remint=False, on_mint=None, adopt_only=False):
    """Return (private key path, public key body) for this box's pair with `alias`. Reads the key autolink's
    resolve_key finds when it is alias-specific and present; otherwise mints (or adopts an unrecorded file at)
    <settings home>/.secrets/ssh/unimatrix-<alias> and records unimatrix.keys.<alias>. Never overwrites a key
    except under `remint`, which deletes the old pair and its 1Password item first. The mint is passphrase-encrypted
    with the item's passphrase (`on_mint(ref)` receives the op reference) unless `unencrypted`.
    `adopt_only` returns the found key and otherwise raises RuntimeError naming the alias: it never mints, never
    writes the machine-local record, and refuses `remint` (ValueError).
    RuntimeError when the alias reduces to nothing, the mint fails, or the machine-local record cannot be made;
    PassphraseSourceMissing / OnePasswordLocked (RuntimeError) when the passphrase source cannot be reached."""
    if adopt_only and remint:
        raise ValueError("adopt_only and remint are mutually exclusive")
    autolink, roster = _sibling(AUTOLINK_SCRIPT), _sibling("unimatrix-roster.py")
    found = autolink.resolve_key(
        roster, alias,
        local_fn=lambda r, a: autolink.machine_local_key(r, a, run=run),
        ssh_fn=lambda r, a: autolink.ssh_identity_file(r, a, run=run))
    alias_key = found != roster.default_key() and Path(found).is_file()
    if adopt_only and not alias_key:
        raise RuntimeError(f"no recorded pair key for {alias}: {autolink.KEYS_PREFIX}{alias} is unset or its file is missing")
    if alias_key and not remint:
        priv = Path(found)
    else:
        safe = _ALIAS_UNSAFE.sub("-", alias)
        if not safe.strip("-"):
            raise RuntimeError(f"alias {alias!r} has no usable characters for a key file name")
        priv = Path(found) if alias_key else roster.settings_home() / ".secrets" / "ssh" / f"unimatrix-{safe}"
        reader = roster.settings_home() / "bin" / "_machine_local.py"
        if not reader.is_file():
            raise RuntimeError(f"{reader} is missing; an unrecorded pair key would not be found next run")
        if remint or not priv.is_file():
            _mint(priv, "unimatrix", run, unencrypted, remint, on_mint)
        rec = _machine_local_run(run, [_console_python(), str(reader), "set", f"{autolink.KEYS_PREFIX}{alias}", str(priv)])
        if rec.returncode:
            raise RuntimeError(f"recording {autolink.KEYS_PREFIX}{alias} failed: "
                               f"{(rec.stderr or rec.stdout or '').strip()[:200]}")
    pub = Path(str(priv) + ".pub")
    if not pub.is_file():
        raise RuntimeError(f"{pub} is missing; cannot read the public key of {priv}")
    return priv, _pub_body(pub)


def recorded_pair_keys(run=subprocess.run, peers=None):
    """{peer alias: (private key path, public key body)} for each peer in the machine-local `unimatrix.far_boxes`
    registry plus `peers` (member box names the caller asks about), keyed as the box's links key them: the
    `unimatrix.keys.<alias>` record, else the ssh-config IdentityFile `ssh -G <alias>` gives, whose private and
    public key files exist. A record for an alias in neither set (a stray) is never listed. Never mints or
    writes a record. RuntimeError when the reader is missing or the registry read fails, or when a requested
    peer's key file has no `.pub` beside it (a registry-only peer in that state is skipped)."""
    autolink, roster = _sibling(AUTOLINK_SCRIPT), _sibling("unimatrix-roster.py")
    reader = roster.settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        raise RuntimeError(f"{reader} is missing; recorded pair keys cannot be listed")
    r = _machine_local_run(run, [_console_python(), str(reader), "get", autolink.REGISTRY_KEY])
    if r.returncode not in (0, 1):
        raise RuntimeError(f"reading {autolink.REGISTRY_KEY} failed: {(r.stderr or r.stdout or '').strip()[:200]}")
    asked = {t for t in (peers or ()) if autolink.ALIAS_RE.fullmatch(t)}
    aliases = sorted({t for t in re.split(r"[,\s]+", (r.stdout or "") if not r.returncode else "")
                      if t and autolink.ALIAS_RE.fullmatch(t)} | asked)
    out = {}
    for alias in aliases:
        found = autolink.resolve_key(
            roster, alias,
            local_fn=lambda ro, a: autolink.machine_local_key(ro, a, run=run),
            ssh_fn=lambda ro, a: autolink.ssh_identity_file(ro, a, run=run))
        priv = Path(found)
        pub = Path(str(priv) + ".pub")
        if found == roster.default_key() or not priv.is_file():
            continue
        if not pub.is_file():
            if alias in asked:
                raise RuntimeError(f"pair key for {alias}: {priv} has no public key {pub}; nothing is minted")
            continue
        out[alias] = (priv, _pub_body(pub))
    return out


FILE_KEY_NAME = "unimatrix-file"


def file_key(run=subprocess.run, unencrypted=False, remint=False, on_mint=None):
    """(private key path, public key line, fingerprint) of this box's file-transfer key, minted at
    <settings home>/.secrets/ssh/unimatrix-file when absent; never overwrites (bar `remint`, which deletes the old
    pair and its 1Password item first) and never touches the relay key. The mint is passphrase-encrypted unless
    `unencrypted` (`on_mint(ref)` receives the op reference).
    RuntimeError when the mint fails or the minted key does not read back as ssh-ed25519;
    PassphraseSourceMissing / OnePasswordLocked (RuntimeError) when the passphrase source cannot be reached."""
    roster = _sibling("unimatrix-roster.py")
    priv = roster.settings_home() / ".secrets" / "ssh" / FILE_KEY_NAME
    pub = Path(str(priv) + ".pub")
    if remint or not priv.is_file():
        _mint(priv, "unimatrix-file", run, unencrypted, remint, on_mint)
    if not pub.is_file():
        raise RuntimeError(f"{pub} is missing; cannot read the public key of {priv}")
    body = _pub_body(pub)
    fp = run(["ssh-keygen", "-lf", str(pub)], capture_output=True, text=True, timeout=30,
             creationflags=roster.no_window())
    if fp.returncode or not (fp.stdout or "").strip():
        raise RuntimeError(f"ssh-keygen -lf failed: {(fp.stderr or fp.stdout or '').strip()[:200]}")
    return priv, f"ssh-ed25519 {body}", fp.stdout.split()[1]


CONTROL_ALIAS_PREFIX = "unimatrix-control-"


def control_key(box, run=subprocess.run, remint=False):
    """(private key path, public key body) of this box's control key for far box `box`, minted at
    ~/.ssh/unimatrix_control_<box> when absent; never overwrites (bar `remint`) and never touches the relay or file key.
    The mint is always unencrypted: the launch path is `ssh -i` under BatchMode with no agent, so it cannot answer a
    passphrase. RuntimeError when `box` has no usable characters, the mint fails, or the public key is unreadable."""
    safe = _ALIAS_UNSAFE.sub("-", box)
    if not safe.strip("-"):
        raise RuntimeError(f"box {box!r} has no usable characters for a key file name")
    priv = Path.home() / ".ssh" / f"unimatrix_control_{safe}"
    if remint or not priv.is_file():
        _mint(priv, "unimatrix-control", run, True, remint)
    pub = Path(str(priv) + ".pub")
    if not pub.is_file():
        raise RuntimeError(f"{pub} is missing; cannot read the public key of {priv}")
    return priv, _pub_body(pub)


def peer_ssh_options(box, run=subprocess.run):
    """{"hostkeyalias": ..., "user": ...} that `ssh -G` resolves for the existing `Host` entry of `box`; a value
    ssh did not take from config (no hostkeyalias line, or the default local user) is omitted, never invented."""
    try:
        r = run(["ssh", "-G", "--", box], capture_output=True, text=True, timeout=10,
                creationflags=_sibling("unimatrix-roster.py").no_window())
    except (OSError, subprocess.SubprocessError):
        return {}
    if r.returncode or not isinstance(r.stdout, str):
        return {}
    fields = {}
    for line in r.stdout.splitlines():
        k, _, v = line.partition(" ")
        fields.setdefault(k.lower(), v.strip())
    out = {k: fields[k] for k in ("hostkeyalias", "user") if fields.get(k)}
    try:
        if out.get("user") == getpass.getuser():
            del out["user"]
    except (OSError, KeyError, ImportError):
        pass
    return out


def render_ssh_config_block(alias, key_path, host_alias=None, peer_options=None):
    """The near-side `~/.ssh/config` block for the pair; printed, never written. The peer is named by
    hostname (`<name>.local` unless the name is already dotted), never an IP literal. `host_alias` names the
    `Host` entry when it differs from the peer (the control key's `unimatrix-control-<box>`). `peer_options`
    (`peer_ssh_options`) adds the peer's HostKeyAlias and User lines when present."""
    name = alias.rsplit("@", 1)[-1]
    host = name if "." in name else f"{name}.local"
    return (f"Host {host_alias or alias}\n"
            f"    HostName {host}\n"
            f"    AddressFamily inet\n"
            + "".join(f"    {n} {peer_options[k]}\n" for k, n in (("hostkeyalias", "HostKeyAlias"), ("user", "User"))
                      if peer_options and peer_options.get(k))
            + f"    IdentityFile {Path(key_path).as_posix()}\n"
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


_SHELL_PROGRAM = (
    "import winreg\n"
    "try:\n"
    "    print(winreg.QueryValueEx(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\\OpenSSH'), 'DefaultShell')[0])\n"
    "except OSError:\n"
    "    print('')\n")


def far_shell(py, plat, alias, run):
    """The far sshd's command shell: `posix` off win32; on win32 `powershell` when the OpenSSH DefaultShell
    names powershell or pwsh, else `cmd` (also when the registry read fails)."""
    if plat != "win32":
        return "posix"
    try:
        r = _ssh_batch(alias, py, _SHELL_PROGRAM, run)
    except (OSError, subprocess.SubprocessError):
        return "cmd"
    lines = (r.stdout or "").strip().splitlines() if r.returncode == 0 else []
    base = ntpath.basename(lines[-1].strip()).lower() if lines else ""
    return "powershell" if "powershell" in base or "pwsh" in base else "cmd"


def control_far_record_path(box):
    """Where the far invocation record for `box` lives: <settings home>/unimatrix/control-far/<box>.json."""
    return settings_home() / "unimatrix" / "control-far" / f"{_ALIAS_UNSAFE.sub('-', box)}.json"


def write_control_far_record(box, py, plat, interp, home, run=subprocess.run):
    """Atomically write the far invocation record the control client reads: the far platform, absolute interpreter,
    absolute unimatrix-control.py and command shell, all from a successful probe. Returns the record's path."""
    join = ntpath.join if plat == "win32" else posixpath.join
    record = {"platform": plat, "interpreter": interp, "script": join(home, "unimatrix", "unimatrix-control.py"),
              "shell": far_shell(py, plat, box, run)}
    path = control_far_record_path(box)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(record), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def control_from_cidrs(explicit):
    """The `from=` pin for a control key: the `--from-cidr` values, else this box's verified membership
    `from_cidrs`. ValueError naming `--from-cidr` when neither yields a non-empty list or a value is not a CIDR."""
    cidrs = list(explicit or [])
    if not cidrs:
        membership = _sibling("unimatrix-membership.py")
        try:
            members = membership.verified_members(_sibling("unimatrix-roster.py").settings_home())
        except (membership.MembershipError, OSError, ValueError, subprocess.SubprocessError):
            members = []
        me = _sibling("unimatrix-peer-contract.py").local_box()
        cidrs = next((list(m["from_cidrs"]) for m in members if m.get("box") == me and m.get("from_cidrs")), [])
    if not cidrs:
        raise ValueError("no from= pin: pass --from-cidr CIDR (this box's verified membership has no from_cidrs)")
    for c in cidrs:
        try:
            ipaddress.ip_network(c, strict=False)
        except (ValueError, TypeError):
            raise ValueError(f"--from-cidr {c!r} is not a CIDR") from None
    return cidrs


def install_over_link(alias, body, run=subprocess.run, control=False, from_cidrs=None):
    """Append the pair's authorized_keys line on the far box over an already-authorized BatchMode link.
    Returns (status, line): status is added | present | admin | no-link | failed; `line` is the line with the far
    box's own interpreter and relay directory (None for no-link); `control` makes it the control key's full-admin
    `from_cidrs`-pinned line and records the probed far invocation for the control client.
    Never prompts, never sudo, never the relay key."""
    far = probe_far(alias, run)
    if far is None:
        return "no-link", None
    py, plat, interp, home = far
    if control:
        write_control_far_record(alias, py, plat, interp, home, run)
        line = control_authorized_keys_line(body, from_cidrs)
    else:
        join = ntpath.join if plat == "win32" else posixpath.join
        line = authorized_keys_line(join(home, "unimatrix"), interp, body)
    try:
        r = _ssh_batch(alias, py, _APPEND_PROGRAM.format(body=body, line=line), run)
    except (OSError, subprocess.SubprocessError):
        return "failed", line
    out = (r.stdout or "").strip().splitlines()
    status = out[-1] if r.returncode == 0 and out else ""
    return (status if status in ("added", "present", "admin") else "failed"), line


_RELAY_FORCED_SCRIPT = "unimatrix-relay.py"
_FORCED_COMMAND = re.compile(r'command="((?:\\"|[^"])*)"')
_FORCED_INTERP = re.compile(r'^(\s*)(\\"(.*?)\\"|\S+)')


def _same_interpreter(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def rewrite_forced_interpreters(path, interpreter):
    """Rewrite, in the local authorized_keys at `path`, the absolute interpreter of every uncommented line forcing
    unimatrix-relay.py that names a different interpreter than `interpreter` (compared by realpath + normcase).
    Key body, options, other lines, line endings and file mode are untouched; a bare interpreter is never judged.
    Returns the number of lines rewritten (0 when the file is absent or unreadable)."""
    path = Path(path).resolve()
    try:
        text = path.read_text(encoding="utf-8", newline="")
    except OSError:
        return 0
    token = f'\\"{interpreter}\\"' if " " in interpreter else interpreter
    changed = 0
    lines = []
    for line in text.splitlines(keepends=True):
        m = _FORCED_COMMAND.search(line)
        if m and not line.lstrip().startswith("#") and _RELAY_FORCED_SCRIPT in line:
            im = _FORCED_INTERP.match(m.group(1))
            old = im and (im.group(3) if im.group(3) is not None else im.group(2))
            if old and (os.path.isabs(old) or old.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", old)) \
                    and not _same_interpreter(old, interpreter):
                inner = m.group(1)[:im.start(2)] + token + m.group(1)[im.end(2):]
                line = line[:m.start(1)] + inner + line[m.end(1):]
                changed += 1
        lines.append(line)
    if changed:
        tmp = path.with_name(path.name + ".unimatrix-tmp")
        tmp.write_text("".join(lines), encoding="utf-8", newline="")
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    return changed


_FORCED_RELAY_PATH = re.compile(r'\\"([^"]*?)unimatrix-relay\.py\\"|(\S*?)unimatrix-relay\.py')


def rewrite_forced_relay_paths(path, dest_dir) -> int:
    """Point every uncommented forced command that runs unimatrix-relay.py out of a klabauter checkout
    (`.../coordinator/bin/`) at the installed copy in `dest_dir`, which --install refreshes; the checkout is never
    updated by an install, so the far relay otherwise drifts. Lines naming any other directory are left alone.
    Returns the number of lines rewritten (0 when the file is absent or unreadable)."""
    path = Path(path).resolve()
    try:
        text = path.read_text(encoding="utf-8", newline="")
    except OSError:
        return 0
    target = str(Path(dest_dir) / _RELAY_FORCED_SCRIPT)
    token = f'\\"{target}\\"' if " " in target else target
    changed = 0
    lines = []
    for line in text.splitlines(keepends=True):
        m = _FORCED_COMMAND.search(line)
        if m and not line.lstrip().startswith("#"):
            inner = m.group(1)
            rm = _FORCED_RELAY_PATH.search(inner)
            folder = rm and (rm.group(1) if rm.group(1) is not None else rm.group(2))
            if folder and folder.replace("\\", "/").rstrip("/").lower().endswith("/coordinator/bin"):
                line = line[:m.start(1)] + inner[:rm.start()] + token + inner[rm.end():] + line[m.end(1):]
                changed += 1
        lines.append(line)
    if changed:
        tmp = path.with_name(path.name + ".unimatrix-tmp")
        tmp.write_text("".join(lines), encoding="utf-8", newline="")
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    return changed


def agy_hooks_path():
    """agy's global hook discovery file."""
    return Path.home() / ".gemini" / "config" / "hooks.json"


def agy_plugins_path():
    """agy's global plugin registration file (sibling of hooks.json)."""
    return agy_hooks_path().with_name("plugins.json")


def _plugin_entry_matches(entry, tree):
    if not isinstance(entry, dict) or entry.get("include_only") != [tree.name]:
        return False
    return os.path.normcase(os.path.normpath(str(entry.get("path", "")))) == os.path.normcase(os.path.normpath(str(tree.parent)))


def seed_agy_plugin(path, tree) -> str:
    """Register the generated agy plugin tree in agy's plugins.json; return "created", "added", "pruned" or "present".

    agy scans each `entries` path one level deep, so the entry names the tree's parent and
    `include_only` narrows it to the tree. Entries whose path is absent or under another user profile
    are dropped; other entries and keys are preserved; a re-run changes nothing.
    """
    path, tree = Path(path), Path(tree)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError as exc:
            raise ValueError(f"{path} is not valid JSON ({exc}); fix or remove it") from exc
        if not isinstance(data, dict) or not isinstance(data.get("entries", []), list):
            raise ValueError(f"{path} has an unexpected shape (want an object with an `entries` list)")
    entries = data.setdefault("entries", [])
    live = _seed().prune_dead_entries(entries)
    pruned = len(live) != len(entries)
    has = any(_plugin_entry_matches(e, tree) for e in live)
    if has and not pruned:
        return "present"
    if not has:
        live.append({"path": str(tree.parent), "include_only": [tree.name]})
    data["entries"] = live
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "pruned" if has else ("added" if existed else "created")


def unseed_agy_plugin(path, tree):
    """Remove only our registration from plugins.json; return "removed" or "absent"."""
    path, tree = Path(path), Path(tree)
    if not path.exists():
        return "absent"
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON ({exc}); fix or remove it") from exc
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return "absent"
    kept = [e for e in entries if not _plugin_entry_matches(e, tree)]
    if len(kept) == len(entries):
        return "absent"
    data["entries"] = kept
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "removed"


def codex_hooks_path():
    """Codex's user hook discovery file: $CODEX_HOME/hooks.json, default ~/.codex."""
    env = os.environ.get("CODEX_HOME")
    return (Path(env) if env else Path.home() / ".codex") / "hooks.json"


def _quote_argv(argv):
    return subprocess.list2cmdline(argv) if os.name == "nt" else " ".join(shlex.quote(a) for a in argv)


_NEUTRAL_BARE = re.compile(r"[A-Za-z0-9_@%+=:,./~-]+")


def _neutral_arg(arg) -> str:
    """One argument as a word bash and pwsh parse identically: forward slashes, single-quoted."""
    arg = str(arg).replace("\\", "/")
    if "'" not in arg:
        return f"'{arg}'"
    if not any(c in arg for c in '"$`'):
        return f'"{arg}"'
    raise ValueError(f"cannot quote {arg!r} for both bash and pwsh")


def _short_path(exe) -> str:
    """The Windows 8.3 form of an existing path (no spaces), else the path unchanged."""
    if os.name != "nt":
        return exe
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(exe, buf, 32768)
    return buf.value if 0 < n < 32768 else exe


def _neutral_exe(exe) -> str:
    """The interpreter word as _neutral_command emits it: 8.3 short form when the path needs quoting."""
    exe = str(exe).replace("\\", "/")
    if not _NEUTRAL_BARE.fullmatch(exe):
        exe = _short_path(exe).replace("\\", "/")
    if not _NEUTRAL_BARE.fullmatch(exe) and any(c in exe for c in '"$`'):
        raise ValueError(f"cannot quote interpreter {exe!r} for bash")
    return exe


def _neutral_command(argv) -> str:
    """argv as a command line bash and pwsh both run: a quoted first word is an expression in pwsh,
    so the interpreter stays bare when it can: a path with a space takes its 8.3 short form, and
    only when none exists is it double-quoted (bash-only)."""
    exe, *rest = (str(a).replace("\\", "/") for a in argv)
    exe = _neutral_exe(exe)
    head = exe if _NEUTRAL_BARE.fullmatch(exe) else f'"{exe}"'
    return " ".join([head, *(_neutral_arg(a) for a in rest)])


def _hook_command(dest_dir, script_name, *args) -> str:
    return _neutral_command([_console_python(), Path(dest_dir) / script_name, *args])


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
    """Our hooks.json value: PreToolUse, PostToolUse, SessionStart, PreInvocation, and Stop hooks running installed scripts.

    agy groups only tool events (PreToolUse, PostToolUse) under matcher/hooks; non-tool events
    (SessionStart, PreInvocation, Stop) take bare handlers, and agy rejects the whole file
    ("command hook must specify 'command'") when a non-tool event is grouped.
    """
    eng = _engine_args(engine_root)
    return {
        "PreToolUse": [_hook_group(dest_dir, AGY_HOOK_SCRIPT, AGY_TOOL_MATCHER, eng)],
        "PostToolUse": [_hook_group(dest_dir, AGY_HOOK_SCRIPT, AGY_TOOL_MATCHER, ("--event", "PostToolUse", *eng))],
        "SessionStart": [_hook_handler(dest_dir, AGY_SESSIONSTART_SCRIPT, *eng)],
        "PreInvocation": [_hook_handler(dest_dir, AGY_HOOK_SCRIPT, "--event", "PreInvocation")],
        "Stop": [_hook_handler(dest_dir, AGY_HOOK_SCRIPT, "--event", "Stop", *eng)],
    }


def external_session_capability(engine_root):
    """Check the published lifecycle surface without importing ambient engine code."""
    if not engine_root:
        return False, "published engine root unresolved"
    root = Path(engine_root)
    try:
        if not (root / "coordinator_core" / "_engine_stamp").read_bytes():
            return False, "published engine stamp is empty"
        module = root / "coordinator_core" / "session" / "external_registry.py"
        if not module.is_file():
            return False, "published engine lacks session.external_registry; update the engine"
    except OSError as exc:
        return False, f"published engine unavailable: {exc}"
    if not (root / "coordinator_core" / "host_hooks" / "session_context.py").is_file():
        return False, "published engine lacks Codex session context; update the engine"
    if not (root / "coordinator_core" / "host_hooks" / "codex_lifecycle.py").is_file():
        return False, "published engine lacks Codex advisory lifecycle; update the engine"
    if not (root / "coordinator_core" / "codex_status" / "hook.py").is_file():
        return False, "published engine lacks Codex usage lifecycle; update the engine"
    return True, "published registration, context, advisory and usage lifecycle present"


def codex_hook_events(dest_dir, engine_root=None) -> dict:
    """Transport discovery plus engine lifecycle registration and shell guard."""
    start = _hook_group(dest_dir, CODEX_SESSIONSTART_SCRIPT, args=_engine_args(engine_root))
    start["hooks"].append({**_hook_handler(
        dest_dir, EXTERNAL_SESSION_SCRIPT, "--event", "SessionStart", *_engine_args(engine_root)), "timeout": 3})
    end = _hook_group(dest_dir, EXTERNAL_SESSION_SCRIPT,
                      args=("--event", "SessionEnd", *_engine_args(engine_root)))
    end["hooks"][0]["timeout"] = 3
    events = {
        "SessionStart": start,
        "SessionEnd": end,
        "SubagentStart": {"hooks": [{**_hook_handler(
            dest_dir, EXTERNAL_SESSION_SCRIPT, "--event", "SubagentStart", *_engine_args(engine_root)), "timeout": 3}]},
        "PreToolUse": _hook_group(
            dest_dir, GUARD_SCRIPT, CODEX_SHELL_MATCHER, ("--host", "codex", *_engine_args(engine_root))),
    }
    for event in ("UserPromptSubmit", "PostToolUse", "Stop", "SubagentStop", "PreCompact", "PostCompact"):
        events[event] = {"hooks":[{**_hook_handler(dest_dir, EXTERNAL_SESSION_SCRIPT,
            "--event", event, *_engine_args(engine_root)), "timeout":3}]}
    return events



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


_CODEX_OWNED_SCRIPTS = (CODEX_SESSIONSTART_SCRIPT, GUARD_SCRIPT, EXTERNAL_SESSION_SCRIPT)


def _codex_ours(group, dest_dir=None):
    """True for a group holding a handler that runs the SessionStart script or the guard."""
    return isinstance(group, dict) and any(
        _codex_owned_handler(h, dest_dir)
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


def _codex_owned_handler(handler, dest_dir=None):
    return _codex_handler_script(handler, dest_dir) is not None


def _codex_handler_script(handler, dest_dir=None):
    if not isinstance(handler, dict) or not isinstance(handler.get("command"), str):
        return None
    command = handler["command"]
    try:
        argv = [arg.strip("\"'") for arg in shlex.split(command, posix="\\" not in command)]
    except ValueError:
        return None
    if not argv:
        return None
    executable = Path(argv[0].replace("\\", "/")).name
    if re.fullmatch(r"(?:python(?:w|\d+(?:\.\d+)*)?|py)(?:\.exe)?", executable, re.IGNORECASE):
        argv = argv[1:]
        while argv and argv[0] in ("-u", "-B", "-E", "-I", "-s", "-S"):
            argv = argv[1:]
    if not argv:
        return None
    script_path = argv[0].replace("\\", "/")
    script = Path(script_path).name
    if script not in _CODEX_OWNED_SCRIPTS:
        return None
    target = dest_dir if dest_dir is not None else settings_home() / "unimatrix"
    wanted = str(Path(str(target).replace("\\", "/")) / script).replace("\\", "/")
    # Windows legacy commands used backslashes and case-insensitive drive paths.
    if re.match(r"^[a-zA-Z]:/", wanted):
        return script if script_path.casefold() == wanted.casefold() else None
    return script if script_path == wanted else None


def _write_codex_hooks(path, data, baseline):
    if (path.read_bytes() if path.exists() else None) != baseline:
        raise ValueError(f"{path}: retryable drift during hook merge; rerun enrollment")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _without_codex_handlers(group, dest_dir=None):
    if not _codex_ours(group, dest_dir):
        return group
    foreign = [handler for handler in group.get("hooks") or [] if not _codex_owned_handler(handler, dest_dir)]
    return {**group, "hooks": foreign} if foreign else None


def seed_codex_hook(hooks_path, dest_dir, engine_root=None):
    """Install owned handlers idempotently, retaining every foreign handler/group."""
    path = Path(hooks_path)
    existed = path.exists()
    baseline = path.read_bytes() if existed else None
    data = _load_hooks(path)
    changed = False
    added = False
    for event, want in codex_hook_events(dest_dir, engine_root).items():
        events = _codex_events(data, path, event)
        found = False
        had_owned = any(_codex_ours(group, dest_dir) for group in events)
        updated = []
        for group in events:
            if group == want and not found:
                updated.append(group)
                found = True
            else:
                cleaned = _without_codex_handlers(group, dest_dir)
                if cleaned is not None:
                    updated.append(cleaned)
        if not found:
            updated.append(want)
            added = added or not had_owned
        if events != updated:
            events[:] = updated
            changed = True
    if not changed:
        return "present"
    _write_codex_hooks(path, data, baseline)
    return "created" if not existed else "added" if added else "updated"


def unseed_codex_hook(hooks_path, dest_dir=None):
    """Remove owned handlers individually; mixed foreign groups retain their data."""
    path = Path(hooks_path)
    baseline = path.read_bytes() if path.exists() else None
    data = _load_hooks(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return "absent"
    removed = False
    for event in tuple(hooks):
        events = hooks[event]
        if not isinstance(events, list) or not any(_codex_ours(group, dest_dir) for group in events):
            continue
        removed = True
        events[:] = [cleaned for group in events if (cleaned := _without_codex_handlers(group, dest_dir)) is not None]
        if not events:
            del hooks[event]
    if not removed:
        return "absent"
    if not hooks:
        del data["hooks"]
    _write_codex_hooks(path, data, baseline)
    return "removed"


def _event_id(name):
    """Event name normalised so `preToolUse`, `PreToolUse` and `pre_tool_use` compare equal."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _codex_expected_handlers(hooks_path, dest_dir=None):
    """Exact (event, command) identities; multiple owned handlers may share an event."""
    hooks = _load_hooks(hooks_path).get("hooks")
    expected = {}
    required = {
        ("SessionStart", CODEX_SESSIONSTART_SCRIPT): 1,
        ("SessionStart", EXTERNAL_SESSION_SCRIPT): 1,
        ("SessionEnd", EXTERNAL_SESSION_SCRIPT): 1,
        ("SubagentStart", EXTERNAL_SESSION_SCRIPT): 1,
        ("PreToolUse", GUARD_SCRIPT): 1,
    }
    required.update({(event, EXTERNAL_SESSION_SCRIPT):1 for event in ("UserPromptSubmit", "PostToolUse", "Stop", "SubagentStop", "PreCompact", "PostCompact")})
    found = dict.fromkeys(required, 0)
    for event, groups in (hooks.items() if isinstance(hooks, dict) else ()):
        for group in groups if isinstance(groups, list) else ():
            for handler in (group.get("hooks") or []) if isinstance(group, dict) else ():
                if not _codex_owned_handler(handler, dest_dir):
                    continue
                command = str(handler.get("command", ""))
                script = _codex_handler_script(handler, dest_dir)
                identity = (event, script)
                if identity not in required:
                    raise ValueError(f"{script} is on the wrong event {event}")
                found[identity] += 1
                expected[(_event_id(event), command)] = command
    if found != required:
        raise ValueError("hooks.json must hold exactly one owned transport, guard, SessionStart registration and SessionEnd unregister handler")
    return expected


# A spec-loaded import (tests, the installer run from another cwd) has no script dir on sys.path.
if "_unimatrix" not in sys.modules and str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))
from _unimatrix.install_toml import (  # noqa: E402, F401
    _STATUS_DEFAULT,
    _STATUS_PATHS,
    _footer_state,
    _footer_write,
    _status_edit,
    _status_profile,
    _toml_chunks,
    _toml_inline,
    seed_codex_status_line,
)


def agy_settings_path():
    """agy's user settings file, where the `statusLine` command lives."""
    return Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


def grok_config_path():
    """Grok's user config: $GROK_HOME/config.toml, default ~/.grok."""
    env = os.environ.get("GROK_HOME")
    return (Path(env) if env else Path.home() / ".grok") / "config.toml"


def grok_rules_path():
    """Grok's managed peer-doctrine file: $GROK_HOME/rules/unimatrix-peer-doctrine.md (grok loads every *.md there)."""
    return grok_config_path().parent / "rules" / "unimatrix-peer-doctrine.md"


def grok_present():
    """True when grok is on PATH; a leftover $GROK_HOME (default ~/.grok) alone is not presence."""
    # Trap: Path.is_file() swallows only not-found errors; an unreadable PATH entry (EACCES on /usr/local/bin/grok
    # on the Mini) raises and aborted the install, so every probe reads an OSError as absent.
    def _is(probe):
        try:
            return probe()
        except OSError:
            return False

    return any(_is((Path(d) / n).is_file) for d in os.environ.get("PATH", "").split(os.pathsep) if d
               for n in ("grok", "grok.exe", "grok.cmd"))


GROK_SYSTEM_BIN = Path("/usr/local/bin")
GROK_BIN_HINTS = (Path("/opt/homebrew/bin"), Path("~/.grok/bin"), Path("~/.npm-global/bin"), Path("~/.bun/bin"))  # literal: user prefixes grok installs land in, none needing root


def _grok_source(home, path_env, system_bin):
    """An installed grok executable the user can read: PATH first, then the user-prefix hints; never the link target itself."""
    local = home / ".local" / "bin"
    dirs = [Path(d) for d in path_env.split(os.pathsep) if d]
    dirs += [Path(str(h).replace("~", str(home), 1)) if str(h).startswith("~") else h for h in GROK_BIN_HINTS]
    for d in dirs:
        if d in (local, system_bin):
            continue
        cand = d / "grok"
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def link_grok_local_bin(home=None, path_env=None, system_bin=None):
    """Symlink an installed grok into ~/.local/bin (0755, created if absent) when `system_bin` (/usr/local/bin) is not
    writable. Returns 'linked', 'present', 'skipped' (system_bin writable or non-POSIX) or 'absent' (no grok found).
    Never invokes sudo; never replaces a non-symlink ~/.local/bin/grok."""
    if os.name == "nt":
        return "skipped"
    home = Path.home() if home is None else Path(home)
    system_bin = GROK_SYSTEM_BIN if system_bin is None else Path(system_bin)
    if os.access(system_bin, os.W_OK | os.X_OK):
        return "skipped"
    link = home / ".local" / "bin" / "grok"
    src = _grok_source(home, os.environ.get("PATH", "") if path_env is None else path_env, system_bin)
    if link.exists():
        return "present"
    if src is None:
        return "absent"
    _mkdir_0755(link.parent)
    if link.is_symlink():
        link.unlink()
    link.symlink_to(src)
    return "linked"


def _on_path(names):
    return any((Path(d) / n).is_file() for d in os.environ.get("PATH", "").split(os.pathsep) if d for n in names)


def host_present(host):
    """True when `host` is present: codex and grok only when on PATH (a leftover home directory is not presence), agy
    on PATH or its home directory; the one predicate gating every hook, status line, doctrine and rules write."""
    if host == "grok":
        return grok_present()
    if host == "codex":
        return _on_path(("codex", "codex.exe", "codex.cmd"))
    if host == "agy":
        return _on_path(("agy", "agy.exe", "agy.cmd")) or agy_hooks_path().parent.parent.is_dir()
    return True


def _is_windowsapps(path):
    return "windowsapps" in str(path).replace("/", "\\").lower().split("\\")


def pwsh_alias_remedy(environ=None, platform=None):
    """On win32, the install-time warning when the first `pwsh` on PATH is the Store/MSIX alias (it cannot run DISM
    cmdlets and a codex sandbox cannot launch it); None otherwise."""
    environ = os.environ if environ is None else environ
    if (platform or sys.platform) != "win32":
        return None
    for entry in (environ.get("PATH") or environ.get("Path") or "").split(os.pathsep):
        if entry and (Path(entry) / "pwsh.exe").is_file():
            if not _is_windowsapps(entry):
                return None
            return (f"pwsh resolves first to the Store/MSIX alias {Path(entry) / 'pwsh.exe'}; remedy: "
                    "winget install Microsoft.PowerShell --scope machine --installer-type wix (elevated), "
                    "which installs %ProgramFiles%\\PowerShell\\7, and put that directory ahead of WindowsApps in PATH")
    return None


def powershell_host(environ=None, platform=None):
    """The PowerShell host to drive Windows setup scripts: MSI pwsh, else a non-WindowsApps pwsh on PATH, else
    Windows PowerShell 5.1; never the MSIX alias. None off Windows or when none exists."""
    environ = os.environ if environ is None else environ
    if (platform or sys.platform) != "win32":
        return None
    base = environ.get("ProgramFiles")
    if base and (Path(base) / "PowerShell" / "7" / "pwsh.exe").is_file():
        return str(Path(base) / "PowerShell" / "7" / "pwsh.exe")
    path = environ.get("PATH") or environ.get("Path") or ""
    for entry in path.split(os.pathsep):
        if entry and not _is_windowsapps(entry) and (Path(entry) / "pwsh.exe").is_file():
            return str(Path(entry) / "pwsh.exe")
    root = environ.get("SystemRoot")
    if root and (Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe").is_file():
        return str(Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    return None


OPENSSH_NEEDS_ADMIN_RC = 3
OPENSSH_FIREWALL_RULE = "OpenSSH-Server-In-TCP"
OPENSSH_STATE_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$svc = Get-Service sshd
$exe = Join-Path $env:SystemRoot 'System32\OpenSSH\sshd.exe'
$fw = @(Get-NetFirewallRule -Direction Inbound -Action Allow -Enabled True | Get-NetFirewallPortFilter |
        Where-Object { $_.Protocol -eq 'TCP' -and ($_.LocalPort -contains '22') }).Count -gt 0
$f = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
$exists = Test-Path $f
$acl = $null
if ($exists) { $acl = Get-Acl $f }
$sids = @()
if ($acl) { $sids = @($acl.Access | ForEach-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } | Sort-Object -Unique) }
[pscustomobject]@{
  installed = [bool]($svc -or (Test-Path $exe))
  running = [bool]($svc -and $svc.Status -eq 'Running')
  automatic = [bool]($svc -and $svc.StartType -eq 'Automatic')
  firewall22 = $fw
  keys_exists = $exists
  keys_protected = [bool]($acl -and $acl.AreAccessRulesProtected)
  keys_sids = $sids
} | ConvertTo-Json -Compress
"""
OPENSSH_APPLY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { Write-Output 'NEEDS_ADMIN'; exit 3 }
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) { Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' | Out-Null }
Set-Service -Name sshd -StartupType Automatic
if ((Get-Service sshd).Status -ne 'Running') { Start-Service sshd }
if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}
$f = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
if (-not (Test-Path $f)) { New-Item -ItemType File -Path $f -Force | Out-Null }
& icacls.exe $f /inheritance:r /grant '*S-1-5-32-544:F' '*S-1-5-18:F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls exited $LASTEXITCODE" }
Write-Output 'OK'
"""
_ADMIN_SIDS = ["S-1-5-18", "S-1-5-32-544"]


def _run_powershell(script, run=subprocess.run, host=None, timeout=120):
    exe = host or powershell_host()
    if exe is None:
        raise OSError("no PowerShell host: neither MSI pwsh nor Windows PowerShell 5.1 found (the Store/MSIX pwsh alias is never used)")
    return run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
               capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def openssh_state(run=subprocess.run, host=None):
    """The OpenSSH Server receive-side state as a dict (installed, running, automatic, firewall22, keys_*)."""
    done = _run_powershell(OPENSSH_STATE_SCRIPT, run, host, timeout=60)
    if done.returncode != 0:
        raise OSError(f"OpenSSH state query exited {done.returncode}: {(done.stderr or done.stdout or '').strip()[:200]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def openssh_problems(state):
    """(finding name, text) for each receive-side requirement `state` does not meet; empty when complete."""
    out = []
    if not state.get("installed"):
        out.append(("openssh-server-installed", "OpenSSH Server (sshd) is not installed"))
    if not state.get("running"):
        out.append(("openssh-sshd-running", "the sshd service is not running"))
    if not state.get("automatic"):
        out.append(("openssh-sshd-automatic", "the sshd service start type is not Automatic"))
    if not state.get("firewall22"):
        out.append(("openssh-firewall-22", "no enabled inbound allow rule for TCP 22"))
    sids = sorted(state.get("keys_sids") or [])
    if not state.get("keys_exists"):
        out.append(("openssh-admin-keys-acl", "administrators_authorized_keys does not exist"))
    elif sids != _ADMIN_SIDS or not state.get("keys_protected"):
        out.append(("openssh-admin-keys-acl", "administrators_authorized_keys ACL is not Administrators+SYSTEM with inheritance removed"))
    return out


def apply_openssh_receive(run=subprocess.run, host=None):
    """Install, start and wire OpenSSH Server for receiving (service automatic, firewall 22, admin keys file ACL).

    Returns (rc, output); rc OPENSSH_NEEDS_ADMIN_RC means the shell was not elevated and nothing changed."""
    done = _run_powershell(OPENSSH_APPLY_SCRIPT, run, host, timeout=600)
    return done.returncode, ((done.stdout or "") + (done.stderr or "")).strip()


def openssh_receive_report(out, run=subprocess.run, apply=False, host=None):
    """Print the receive-side status (and, with `apply`, the repair); returns 0 when complete, else 1."""
    try:
        problems = openssh_problems(openssh_state(run, host))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"WARN: openssh receive side not checked: {exc}", file=out)
        return 1
    if problems and apply:
        try:
            rc, text = apply_openssh_receive(run, host)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"WARN: openssh receive side not repaired: {exc}", file=out)
            return 1
        if rc == OPENSSH_NEEDS_ADMIN_RC:
            print("openssh receive side needs an elevated shell: re-run `unimatrix-install.py --openssh-receive` as Administrator", file=out)
            return 1
        if rc != 0:
            print(f"WARN: openssh receive side repair exited {rc}: {text[:300]}", file=out)
            return 1
        try:
            problems = openssh_problems(openssh_state(run, host))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f"WARN: openssh receive side not re-checked: {exc}", file=out)
            return 1
    if problems:
        print("openssh receive side incomplete: " + "; ".join(f"{n}: {t}" for n, t in problems)
              + "; remedy: run `unimatrix-install.py --openssh-receive` in an elevated shell", file=out)
        return 1
    print("openssh receive side complete: sshd installed, running, automatic; firewall 22; administrators_authorized_keys ACL", file=out)
    return 0


def grok_hooks_path():
    """Grok's hook registration file: $GROK_HOME/hooks/coordinator.json; grok loads hooks/*.json, never a bare hooks.json."""
    return grok_config_path().parent / "hooks" / GROK_HOOKS_FILE


def grok_hook_entry(dest_dir, engine_root=None):
    """Our grok PreToolUse group: the host guard with `--host grok` over the shell and edit tools."""
    return _hook_group(dest_dir, GUARD_SCRIPT, GROK_TOOL_MATCHER, ("--host", "grok", *_engine_args(engine_root)))


def _grok_owned_handler(handler):
    command = str(handler.get("command", "")) if isinstance(handler, dict) else ""
    return GUARD_SCRIPT in command and "--host grok" in command.replace("'", "").replace('"', "")


def _grok_group_ours(group):
    return isinstance(group, dict) and any(_grok_owned_handler(h) for h in group.get("hooks") or [])


def _grok_pretool(data, path):
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{path} has a non-object `hooks` value")
    events = hooks.setdefault("PreToolUse", [])
    if not isinstance(events, list):
        raise ValueError(f"{path} has a non-list `hooks.PreToolUse` value")
    return events


def _without_grok_handlers(group):
    if not _grok_group_ours(group):
        return group
    foreign = [h for h in group.get("hooks") or [] if not _grok_owned_handler(h)]
    return {**group, "hooks": foreign} if foreign else None


def seed_grok_hook(hooks_path, dest_dir, engine_root=None):
    """Install our PreToolUse group idempotently; return "created", "added", "updated" or "present".

    Foreign groups and every other key stay byte-identical."""
    path = Path(hooks_path)
    existed = path.exists()
    data = _load_hooks(path)
    events = _grok_pretool(data, path)
    want = grok_hook_entry(dest_dir, engine_root)
    had_owned = any(_grok_group_ours(g) for g in events)
    updated, found = [], False
    for group in events:
        if group == want and not found:
            updated.append(group)
            found = True
        elif (cleaned := _without_grok_handlers(group)) is not None:
            updated.append(cleaned)
    if not found:
        updated.append(want)
    if events == updated:
        return "present"
    events[:] = updated
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "created" if not existed else "updated" if had_owned else "added"


def refresh_grok_hook(hooks_path, dest_dir, engine_root=None) -> str:
    """Bring an installed Grok group to current emitter output; return "absent", "present" or "updated".

    One small JSON read and no spawn. Creates nothing: a file with no owned group is "absent" and stays
    untouched, and a current file is not rewritten. An unresolved engine root is "absent" too, so a
    working `--engine-root` is never rendered away."""
    path = Path(hooks_path)
    if engine_root is None or not path.is_file():
        return "absent"
    hooks = _load_hooks(path).get("hooks")
    events = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    if not isinstance(events, list) or not any(_grok_group_ours(g) for g in events):
        return "absent"
    return seed_grok_hook(path, dest_dir, engine_root)


def unseed_grok_hook(hooks_path):
    """Remove only our handler from PreToolUse; return "removed" or "absent"."""
    path = Path(hooks_path)
    data = _load_hooks(path)
    hooks = data.get("hooks")
    events = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    if not isinstance(events, list) or not any(_grok_group_ours(g) for g in events):
        return "absent"
    events[:] = [c for g in events if (c := _without_grok_handlers(g)) is not None]
    if not events:
        del hooks["PreToolUse"]
    if not hooks:
        del data["hooks"]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "removed"


TUI_STATUS_MODULE = "coordinator_core.tui_status"
TUI_STATUS_LAUNCHER = "unimatrix-tui-status-launch.py"
# Trap: agy and Grok run the status line from a cwd with no coordinator_core on sys.path, so a bare
# `-m` fails on every render; the launcher puts the engine root on sys.path. agy on Windows splits a
# `-c` one-liner at its spaces and quotes, so no argument may hold either. The -c form below is kept
# only to recognise (and replace) entries an earlier install wrote.
_TUI_STATUS_BOOT = ("import runpy,sys;sys.path.insert(0,sys.argv.pop(1));"
                    f"runpy.run_module('{TUI_STATUS_MODULE}',run_name='__main__')")


GROK_STATUS_SCRIPT = "coordinator-statusline.ps1"


def _grok_ps1_form(host) -> bool:
    """True when this host's status line is a path-only `.ps1`: Grok on Windows starts `command` as one process image."""
    return host == "grok" and os.name == "nt"


def _grok_status_script_text(engine_root, dest_dir=None) -> str:
    """The `.ps1` body: stdin piped through the console python to the launcher, every path single-quoted."""
    launcher = (Path(dest_dir) if dest_dir else settings_home() / "unimatrix") / TUI_STATUS_LAUNCHER
    q = lambda v: "'" + str(v).replace("'", "''") + "'"
    return (f"$py = {q(_console_python())}\r\n$launcher = {q(launcher)}\r\n$root = {q(engine_root)}\r\n"
            "$input | & $py $launcher $root 'grok'\r\n")


def _tui_status_command(host, engine_root=None, dest_dir=None, config_dir=None) -> str:
    """The status-line command: the installed launcher script run by the console python, one bare word per argument.

    Grok on Windows (with a `config_dir`) gets only the path of the `.ps1` that runs it.
    """
    if engine_root and config_dir and _grok_ps1_form(host):
        script = Path(config_dir) / GROK_STATUS_SCRIPT
        return (_short_path(str(script)) if " " in str(script) and script.exists() else str(script)).replace("\\", "/")
    if engine_root:
        launcher = (Path(dest_dir) if dest_dir else settings_home() / "unimatrix") / TUI_STATUS_LAUNCHER
        argv = [_console_python(), launcher, str(engine_root), host]
    else:
        argv = [_console_python(), "-m", TUI_STATUS_MODULE, host]
    return _quote_argv([(_short_path(str(a)) if " " in str(a) else str(a)).replace("\\", "/") for a in argv])


def _status_command_ours(value, host) -> bool:
    """True when a host's status-line value is one this installer wrote, in any engine root or form."""
    cmd = value.get("command") if isinstance(value, dict) else None
    if not isinstance(cmd, str):
        return False
    try:
        argv = shlex.split(cmd, posix=os.name != "nt")
    except ValueError:
        return False
    argv = [a.strip('"') for a in argv]
    if len(argv) == 1 and host == "grok" and Path(argv[0].replace("\\", "/")).name == GROK_STATUS_SCRIPT:
        return True
    if argv[-3:] == ["-m", TUI_STATUS_MODULE, host]:
        return True
    if len(argv) == 4 and Path(argv[1].replace("\\", "/")).name == TUI_STATUS_LAUNCHER and argv[3] == host:
        return True
    return len(argv) == 5 and argv[1] == "-c" and argv[2] == _TUI_STATUS_BOOT and argv[4] == host


def _agy_status_norm(value):
    """agy's statusLine with the empty `type` key agy writes into it on its own settings rewrite dropped.

    Trap: agy turns our `{"command": ...}` into `{"type": "", "command": ...}`; compared raw, our own
    value never reads as present and the post-edit check refuses every re-install.
    """
    if isinstance(value, dict) and value.get("type") == "":
        return {k: v for k, v in value.items() if k != "type"}
    return value


def _host_status_value(host, text, command):
    """(current status-line value or None, the value we install) for one host's config text."""
    if host == "agy":
        data = json.loads(text or "{}")
        if not isinstance(data, dict):
            raise ValueError("agy settings must be a JSON object")
        return _agy_status_norm(data.get("statusLine")), {"command": command}
    ui_table = tomllib.loads(text or "").get("ui", {})
    if not isinstance(ui_table, dict):
        raise ValueError("ui must be a table")
    return ui_table.get("status_line"), {"type": "command", "command": command}


def _host_status_apply(host, base, command):
    if host == "agy":
        data = json.loads(base or "{}")
        data["statusLine"] = {"command": command}
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    head = base if not base or base.endswith("\n") else base + "\n"
    sep = "\n" if head and not head.endswith("\n\n") else ""
    return head + sep + "[ui.status_line]\ntype = \"command\"\ncommand = " + json.dumps(command, ensure_ascii=False) + "\n"


def _host_status_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(state, dict) or state.get("version") != 1 or type(state.get("existed")) is not bool or
            not isinstance(state.get("before"), str) or not isinstance(state.get("after"), str) or
            not isinstance(state.get("managed"), dict)):
        raise ValueError("invalid status-line ownership record")
    return state


def seed_host_status_line(config_path, host, *, uninstall=False, engine_root=None, dest_dir=None) -> str:
    """Own only the agy `statusLine` / Grok `[ui.status_line]` value; restore only while it remains our exact value.

    The ownership record keeps the pre-install text, so an untouched file returns byte for byte; a file
    edited since is repaired structurally. A status line the user set is never overwritten.
    """
    path = Path(config_path)
    state_path = path.with_name(f".coordinator-status-line-{host}.json")
    text = path.read_bytes().decode("utf-8") if path.exists() else None
    command = _tui_status_command(host, engine_root, dest_dir, path.parent)
    script = path.with_name(GROK_STATUS_SCRIPT)
    if uninstall:
        if not state_path.exists():
            return "absent"
        state = _host_status_state(state_path)
        if text is None:
            state_path.unlink()
            return "absent"
        if text == state["after"]:
            if state["existed"]:
                _footer_write(path, state["before"])
            else:
                path.unlink()
        elif host == "agy":
            data = json.loads(text)
            if not isinstance(data, dict) or _agy_status_norm(data.get("statusLine")) != state["managed"]:
                return "retained-customized"
            original = json.loads(state["before"] or "{}").get("statusLine")
            if original is None:
                data.pop("statusLine")
            else:
                data["statusLine"] = original
            _footer_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        else:
            appended = state["after"][len(state["before"]):] if state["after"].startswith(state["before"]) else ""
            if not appended or appended not in text:
                return "retained-customized"
            replacement = text.replace(appended, "", 1)
            tomllib.loads(replacement)
            _footer_write(path, replacement)
        state_path.unlink()
        script.unlink(missing_ok=True)
        return "restored"
    current, wanted = _host_status_value(host, text, command)
    if current == wanted:
        return "present"
    state = _host_status_state(state_path) if state_path.exists() else None
    if current is not None and _status_command_ours(current, host) and (state is None or text != state["after"]):
        # Our own older value (another engine root, or the bare `-m` form) in an edited file: swap
        # only the command literal so the user's other edits survive.
        old_cmd = current["command"]
        old_literal = next((lit for lit in (json.dumps(old_cmd, ensure_ascii=False), f"'''{old_cmd}'''", f"'{old_cmd}'")
                            if lit in text), None)
        if old_literal is None:
            return "retained-customized"
        base = state["before"] if state else text
        existed = state["existed"] if state else True
        replacement = text.replace(old_literal, json.dumps(command, ensure_ascii=False), 1)
    elif current is not None:
        if state is None or text != state["after"]:
            return "retained-customized"
        base, existed = state["before"], state["existed"]
        replacement = _host_status_apply(host, base, command)
    else:
        base, existed = text or "", text is not None
        replacement = _host_status_apply(host, base, command)
    if _host_status_value(host, replacement, command)[0] != wanted:
        raise ValueError("status-line edit did not address the host's status line")
    path.parent.mkdir(parents=True, exist_ok=True)
    if engine_root and _grok_ps1_form(host):
        _footer_write(script, _grok_status_script_text(engine_root, dest_dir))
    record = {"version": 1, "host": host, "existed": existed, "before": base, "after": replacement, "managed": wanted}
    _footer_write(state_path, json.dumps(record, ensure_ascii=False) + "\n")
    _footer_write(path, replacement)
    return "updated" if text is not None else "created"


AGY_ALLOW_RULE = "command(coordinator-invoke engine_ask.submit)"
AGY_LEGACY_ALLOW_RULE = "command(coordinator-invoke *)"
AGY_PRIOR_ALLOW_RULE = "command(coordinator-invoke engine_ask.submit --params-file .coordinator-local/em-submit.json)"
AGY_ENGINE_OPS = (
    "engine_ask.submit",
    "workflow.fire",
    "workflow.fire_status",
    "workflow.fire_wait",
    "workflow.revise",
)


def invoke_launcher_path():
    """The box's absolute settings-home coordinator-invoke launcher; hosts that refuse a PATH-resolved executable need it spelled out."""
    return str(settings_home() / "bin" / ("coordinator-invoke.exe" if sys.platform == "win32" else "coordinator-invoke"))


def safe_commit_launcher_path():
    """The box's absolute settings-home coordinator-safe-commit launcher."""
    return str(settings_home() / "bin" / ("coordinator-safe-commit.exe" if sys.platform == "win32" else "coordinator-safe-commit"))


def agy_absolute_allow_rule():
    """The submit grant naming coordinator-invoke by its settings-home path, for hosts where the bare name does not resolve."""
    exe = invoke_launcher_path()
    return AGY_ALLOW_RULE.replace("command(coordinator-invoke ", f"command({exe} ", 1)


def agy_absolute_allow_rules(dest_dir=None) -> list[str]:
    """Full coordinator allowlist for agy `permissions.allow`: engine ops, safe-commit, and unimatrix-send."""
    exe = invoke_launcher_path()
    send_script = (Path(dest_dir) if dest_dir else settings_home() / "unimatrix") / SEND_SCRIPT
    rules = [f"command({exe} {op})" for op in AGY_ENGINE_OPS]
    rules.append(f"command({safe_commit_launcher_path()})")
    rules.append(f"command({_console_python()} {send_script})")
    return rules


def launcher_sac_blocked() -> bool:
    """True when Windows Smart App Control is enforcing, so the unsigned `.exe` launcher an allow rule names cannot run.

    Reads one registry value; no process is spawned. Any other platform, an unreadable value or an evaluation-mode state is False.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as key:
            return winreg.QueryValueEx(key, "VerifiedAndReputablePolicyState")[0] == 1
    except (OSError, ImportError):
        return False


AGY_TOOL_PERMISSION_KEY = "toolPermission"
AGY_BYPASS_VALUE = "always-proceed"


def seed_agy_allow_rule(config_path, *, uninstall=False, rule=None, rules=None) -> str:
    """Own coordinator entries in agy's `permissions.allow`, so a headless `agy --print` can run coordinator doors.

    When `rules` is given, own that list; else when `rule` is given, own `[rule]`; else default to
    `agy_absolute_allow_rules()`. Every legacy single-rule form this installer has written is also
    recognized as owned and migrated or removed; operator entries are never touched. A
    `toolPermission: always-proceed` value is removed and its prior value kept in the ownership record
    for uninstall to restore.
    """
    if rules is not None:
        target_rules = list(dict.fromkeys(rules))
    elif rule is not None:
        target_rules = [rule]
    else:
        target_rules = agy_absolute_allow_rules()
    path = Path(config_path)
    state_path = path.with_name(".coordinator-allow-rule-agy.json")
    prior_state = _host_status_state(state_path) if state_path.exists() else None
    prior_managed = []
    if isinstance(prior_state, dict):
        prev_allow = (prior_state.get("managed") or {}).get("allow")
        if isinstance(prev_allow, list):
            prior_managed = [r for r in prev_allow if isinstance(r, str)]
        elif isinstance(prev_allow, str):
            prior_managed = [prev_allow]
    owned = list(dict.fromkeys([
        AGY_ALLOW_RULE,
        agy_absolute_allow_rule(),
        AGY_LEGACY_ALLOW_RULE,
        AGY_PRIOR_ALLOW_RULE,
        AGY_PRIOR_ALLOW_RULE.replace("command(coordinator-invoke ", f"command({invoke_launcher_path()} ", 1),
        *prior_managed,
        *target_rules,
    ]))
    owned_set = set(owned)
    target_set = set(target_rules)
    text = path.read_bytes().decode("utf-8") if path.exists() else None
    if uninstall:
        if not state_path.exists():
            return "absent"
        state = prior_state or _host_status_state(state_path)
        if text is None:
            state_path.unlink()
            return "absent"
        if text == state["after"]:
            if state["existed"]:
                _footer_write(path, state["before"])
            else:
                path.unlink()
        else:
            data = json.loads(text)
            perms = data.get("permissions") if isinstance(data, dict) else None
            allow = perms.get("allow") if isinstance(perms, dict) else None
            if not isinstance(allow, list) or not any(r in allow for r in owned_set):
                state_path.unlink()
                return "absent"
            allow[:] = [r for r in allow if r not in owned_set]
            if not allow:
                del perms["allow"]
            if not perms:
                del data["permissions"]
            prior = state["managed"].get(AGY_TOOL_PERMISSION_KEY)
            if prior is not None and AGY_TOOL_PERMISSION_KEY not in data:
                data[AGY_TOOL_PERMISSION_KEY] = prior
            _footer_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        state_path.unlink()
        return "restored"
    data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ValueError("agy settings must be a JSON object")
    perms = data.setdefault("permissions", {})
    if not isinstance(perms, dict):
        raise ValueError("agy settings permissions must be an object")
    allow = perms.setdefault("allow", [])
    if not isinstance(allow, list):
        raise ValueError("agy settings permissions.allow must be a list")
    stale = state_path.exists() and any(r in allow for r in owned_set if r not in target_set)
    missing_rules = any(r not in allow for r in target_rules)
    bypass = data.get(AGY_TOOL_PERMISSION_KEY) == AGY_BYPASS_VALUE
    if not missing_rules and not stale and not bypass:
        return "present"
    if stale:
        allow[:] = [r for r in allow if r not in owned_set or r in target_set]
    for r in target_rules:
        if r not in allow:
            allow.append(r)
    if bypass:
        del data[AGY_TOOL_PERMISSION_KEY]
    replacement = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"version": 1, "host": "agy", "existed": text is not None, "before": text or "",
              "after": replacement, "managed": {"allow": target_rules}}
    if bypass:
        record["managed"][AGY_TOOL_PERMISSION_KEY] = AGY_BYPASS_VALUE
    if state_path.exists() and (stale or bypass or missing_rules):
        prior = prior_state or _host_status_state(state_path)
        record["existed"], record["before"] = prior["existed"], prior["before"]
        carried = prior["managed"].get(AGY_TOOL_PERMISSION_KEY)
        if carried is not None:
            record["managed"][AGY_TOOL_PERMISSION_KEY] = carried
    _footer_write(state_path, json.dumps(record, ensure_ascii=False) + "\n")
    _footer_write(path, replacement)
    return "updated" if text is not None else "created"


def codex_rules_path():
    """Codex's global instructions file: $CODEX_HOME/AGENTS.md, default ~/.codex."""
    return codex_hooks_path().with_name("AGENTS.md")


def agy_rules_path():
    """agy's global rules file (agy 1.4.12 loads ~/.gemini/GEMINI.md and ~/.gemini/AGENTS.md)."""
    return Path.home() / ".gemini" / "GEMINI.md"


def codex_exec_rule_path():
    """Our Codex execpolicy file: $CODEX_HOME/rules/unimatrix.rules."""
    return codex_hooks_path().parent / "rules" / "unimatrix.rules"


def render_codex_exec_rule(dest_dir) -> str:
    """An allow rule for the send command alone, so a Codex reply to a peer needs no approval prompt."""
    argv = [_neutral_exe(_console_python()), str(Path(dest_dir) / SEND_SCRIPT).replace("\\", "/")]
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
LOGIN_AGENT_INTERVAL_S = 60
LOGIN_TASK_NAME = "UnimatrixAutolink"
LOGIN_UNIT = "unimatrix-autolink.service"
LOGIN_TIMER = "unimatrix-autolink.timer"


def run_schtasks(*args):
    """Run schtasks.exe; None when it cannot launch."""
    try:
        return subprocess.run(["schtasks.exe", *args], capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None


def _agent_python(agent_dir=None):
    """The interpreter the installed macOS login agent runs, when that file exists; else None."""
    if sys.platform != "darwin":
        return None
    root = Path(agent_dir) if agent_dir else login_agent_dir()
    try:
        import plistlib
        exe = plistlib.loads(_login_agent_paths(root)[0].read_bytes())["ProgramArguments"][0]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    return exe if isinstance(exe, str) and os.path.isfile(exe) else None


def _pin_raw():
    """The `unimatrix.python` value as stored, existing file or not; None when unset."""
    return _sibling(AUTOLINK_SCRIPT).pin_key_value(_sibling("unimatrix-roster.py"))


def _write_pin(interp):
    """Record `unimatrix.python` = *interp* in machine-local; True when recorded."""
    roster = _sibling("unimatrix-roster.py")
    reader = roster.settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return False
    try:
        rec = _machine_local_run(subprocess.run, [_console_python(), str(reader), "set", PYTHON_PIN_KEY, interp])
    except OSError:
        return False
    return rec.returncode == 0


def record_python_pin(agent_dir=None) -> str | None:
    """Pin `unimatrix.python` when unset or when the pinned file is absent; return the recorded interpreter,
    else None (a pin naming an existing file is never overwritten). The pin is the interpreter the login agent
    already runs (it holds the macOS Local Network grant), else this installer's: later reinstalls from
    another python keep that binary."""
    try:
        raw = _pin_raw()
        if raw and os.path.isfile(raw):
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    interp = _agent_python(agent_dir) or sys.executable
    if not _write_pin(interp):
        return None
    _PIN_CACHE.clear()
    return interp


def login_agent_dir():
    """Where this OS reads user login agents; None on a platform with none."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents"
    if sys.platform.startswith("linux"):
        return Path.home() / ".config" / "systemd" / "user"
    return None


def _autolink_argv(dest_dir):
    # The `unimatrix.python` pin before the installing interpreter: a reinstall from another python must not
    # repoint the login agent at a binary without the Local Network grant (a silent link loss on macOS).
    return [_pin_value() or sys.executable, str(Path(dest_dir) / AUTOLINK_SCRIPT)]


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
    _refuse_real_run_key(wr)
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
    """Bytes of the login-agent file for this OS: a RunAtLoad plist that launchd re-runs every
    LOGIN_AGENT_INTERVAL_S (autolink's healthy path reads records and spawns nothing; a dead supervisor is
    relinked), or a oneshot systemd unit that a sibling timer (``_login_timer_text``) re-runs on the same
    interval. AbandonProcessGroup keeps launchd's job-exit cleanup from reaping the supervisors autolink
    spawned; KillMode=process is systemd's analogue -- the default control-group mode reaps every process
    left in the oneshot's cgroup when ExecStart exits, killing the link at every login."""
    argv = _autolink_argv(dest_dir)
    if sys.platform == "darwin":
        import plistlib
        return plistlib.dumps({"Label": LOGIN_AGENT_LABEL, "ProgramArguments": argv, "RunAtLoad": True,
                               "StartInterval": LOGIN_AGENT_INTERVAL_S, "AbandonProcessGroup": True,
                               "ProcessType": "Standard", "Nice": 0})
    return ("[Unit]\nDescription=Unimatrix autolink at login\nWants=network-online.target\n"
            "After=network-online.target\n\n[Service]\nType=oneshot\nKillMode=process\n"
            f"ExecStart={' '.join(shlex.quote(a) for a in argv)}\n\n[Install]\nWantedBy=default.target\n"
            ).encode("utf-8")


def _login_timer_text() -> bytes:
    """The Linux relink timer: launchd's StartInterval for the oneshot unit, so a dead supervisor is
    relinked within LOGIN_AGENT_INTERVAL_S of dying, not at the next login."""
    return ("[Unit]\nDescription=Unimatrix autolink relink\n\n[Timer]\nOnBootSec=30\n"
            f"OnUnitInactiveSec={LOGIN_AGENT_INTERVAL_S}\nUnit={LOGIN_UNIT}\n\n"
            "[Install]\nWantedBy=timers.target\n").encode("utf-8")


def _login_timer_paths(agent_dir) -> tuple:
    return Path(agent_dir) / LOGIN_TIMER, Path(agent_dir) / "timers.target.wants" / LOGIN_TIMER


def _login_agent_paths(agent_dir):
    name = f"{LOGIN_AGENT_LABEL}.plist" if sys.platform == "darwin" else LOGIN_UNIT
    return Path(agent_dir) / name, Path(agent_dir) / "default.target.wants" / LOGIN_UNIT


_TEST_HOME = []
try:
    _REAL_HOME = Path.home()
except RuntimeError:
    _REAL_HOME = None


def _test_home():
    """The test-home guard module (lib/unimatrix_test_home.py), loaded once; None when it is not shipped."""
    if not _TEST_HOME:
        path = _BIN_DIR / "lib" / "unimatrix_test_home.py"
        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("unimatrix_test_home", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TEST_HOME.append(mod)
    return _TEST_HOME[0]


def _refuse_real_run_key(wr):
    """Under a test settings home, refuse a registry module that is the real `winreg`; a stand-in object passes."""
    guard = _test_home() if os.environ.get("UNIMATRIX_TEST_HOME") else None
    if guard is not None and isinstance(wr, types.ModuleType):
        guard.refuse_real("run_key", f"HKCU\\{RUN_KEY}\\{LOGIN_TASK_NAME}")


def _refuse_real_agent_dir(root):
    """Under a test settings home, refuse the default plist/systemd dir of the account home captured at
    import (a test that redirects HOME afterwards resolves elsewhere) unless it is inside the settings home."""
    guard = _test_home() if os.environ.get("UNIMATRIX_TEST_HOME") else None
    if guard is None or _REAL_HOME is None:
        return
    here = os.path.normcase(os.path.abspath(os.fspath(root)))
    real_dirs = (_REAL_HOME / "Library" / "LaunchAgents", _REAL_HOME / ".config" / "systemd" / "user")
    if here not in {os.path.normcase(os.path.abspath(os.fspath(d))) for d in real_dirs}:
        return
    try:
        guard.refuse_real("key_path", root)
    except guard.TestHomeRefusal:
        raise guard.TestHomeRefusal("login_agent_dir", root) from None


def register_login_agent(dest_dir, agent_dir=None, schtasks=None, launchctl=None, uid=None):
    """Register one run-once-at-login agent for the installed autolink; return (state, where).

    state is "created", "updated" or "present" (plist / systemd unit), "registered" (Windows HKCU Run value,
    needs no elevation; overwritten in place and any legacy scheduled task removed), or "skipped"
    (no login-agent mechanism here, or the registry write failed).
    Plain file writes on macOS and Linux, picked up at next login. On macOS an "updated" plist whose label is
    loaded is booted out and bootstrapped again: launchd keeps running the old ProgramArguments until logout,
    and an interpreter swap there leaves the job on a binary without the Local Network grant ("No route to
    host" from the agent while every ssh-session context links).
    """
    if sys.platform == "win32":
        wr = _winreg()
        _refuse_real_run_key(wr)
        try:
            with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as key:
                wr.SetValueEx(key, LOGIN_TASK_NAME, 0, wr.REG_SZ, _windows_run_command(dest_dir))
        except OSError as exc:
            return "skipped", f"HKCU Run value write failed: {exc}"
        _delete_login_task(schtasks)
        return "registered", f"HKCU Run value {LOGIN_TASK_NAME}"
    root = Path(agent_dir) if agent_dir else login_agent_dir()
    if root is None:
        return "skipped", f"no login agent for platform {sys.platform!r}"
    if not agent_dir:
        _refuse_real_agent_dir(root)
    target, link = _login_agent_paths(root)
    data = _login_agent_text(dest_dir)
    state = "created"
    if target.exists():
        state = "present" if target.read_bytes() == data else "updated"
    if state != "present":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if sys.platform != "darwin":
        if not link.is_symlink():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(f"../{LOGIN_UNIT}")
        timer, timer_link = _login_timer_paths(root)
        timer_data = _login_timer_text()
        if not timer.exists() or timer.read_bytes() != timer_data:
            timer.write_bytes(timer_data)
            if state == "present":
                state = "updated"
        if not timer_link.is_symlink():
            timer_link.parent.mkdir(parents=True, exist_ok=True)
            timer_link.symlink_to(f"../{LOGIN_TIMER}")
    # A caller-chosen agent_dir with the real launchctl would boot out this box's live agent: reload only
    # the OS agent dir, or under an injected launchctl.
    if sys.platform == "darwin" and state == "updated" and (launchctl or not agent_dir):
        state = _reload_login_agent(target, launchctl, uid)
    return state, str(target)


def _reload_login_agent(target, launchctl=None, uid=None):
    """Reload a loaded agent so launchd runs the plist now on disk; "updated" when nothing was loaded."""
    run = launchctl or run_launchctl
    domain = f"gui/{uid if uid is not None else os.getuid()}"
    loaded = run("print", f"{domain}/{LOGIN_AGENT_LABEL}")
    if loaded is None or loaded.returncode != 0:
        return "updated"
    run("bootout", f"{domain}/{LOGIN_AGENT_LABEL}")
    boot = run("bootstrap", domain, str(target))
    return "updated and reloaded" if boot is not None and boot.returncode == 0 else "updated, reload FAILED"


PS_NICE_ARGV = ["ps", "-axo", "pid,ppid,nice,command"]
BOUNCE_DRAIN_SECONDS = 20


class BounceRefusal(RuntimeError):
    """The bounce cannot run: names the missing key or platform."""


def _tenant_priority():
    """`coordinator_core.tenant_priority` with the engine on sys.path, or None when no engine resolves."""
    try:
        from coordinator_core import tenant_priority
        return tenant_priority
    except ImportError:
        pass
    try:
        sys.path.insert(0, str(_BIN_DIR))
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import ensure_engine_on_path

        ensure_engine_on_path(str(_BIN_DIR / "unimatrix-install.py"))
        from coordinator_core import tenant_priority
        return tenant_priority
    except Exception:
        return None


def ps_nice_snapshot(run=subprocess.run):
    """One `ps` argv exec (no shell); empty text on failure."""
    try:
        res = run(PS_NICE_ARGV, capture_output=True, text=True, timeout=10,
                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout if res.returncode == 0 else ""


def parse_ps_nice(text):
    """[(pid, ppid, nice, command)] from `ps -axo pid,ppid,nice,command` text; header and unparseable rows are skipped."""
    rows = []
    for line in str(text).splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3]))
        except ValueError:
            continue
    return rows


def select_bounce_targets(rows, prefix, is_serve, keep_pids=()):
    """Pids whose command carries the settings-home `prefix` and whose nice is not 0, one `ps` table in.

    A serve-lineage process (`is_serve(command)`) and every descendant of one is never a target, nor is a
    pid in `keep_pids` (this process and its parent)."""
    serve = {pid for pid, _, _, cmd in rows if is_serve(cmd)}
    grew = True
    while grew:
        grew = False
        for pid, ppid, _, _ in rows:
            if ppid in serve and pid not in serve:
                serve.add(pid)
                grew = True
    return [pid for pid, _, nice, cmd in rows
            if nice != 0 and prefix in cmd.replace("\\", "/") and pid not in serve and pid not in keep_pids]


def _bounce_agent(target, launchctl, uid):
    """Boot the login agent out and back in whether or not it is loaded; the state string names the outcome."""
    run = launchctl or run_launchctl
    domain = f"gui/{uid if uid is not None else os.getuid()}"
    run("bootout", f"{domain}/{LOGIN_AGENT_LABEL}")
    boot = run("bootstrap", domain, str(target))
    return "bounced" if boot is not None and boot.returncode == 0 else "bounce FAILED"


def bounce_messaging(roster, ps=None, term=None, kill=None, alive=None, launchctl=None, uid=None,
                     agent_dir=None, sleep=time.sleep, drain_seconds=BOUNCE_DRAIN_SECONDS):
    """Relaunch the messaging set at nice 0 under launchd, draining first; no sudo.

    `roster` is the live roster (session names) taken as input and echoed in the result. Targets are every
    settings-home-prefix process with nice != 0 from one `ps` read, minus the project-rag serve lineage. Drain
    is the supervisors' own SIGTERM stop (`stopped` / `release_on_sigterm`, which log and release the bound
    sockets); the pids are polled for `drain_seconds` and only a straggler past that is SIGKILLed. Then the
    autolink agent is booted out and bootstrapped, so autolink relinks each box with nice-0 children.
    Returns {"roster", "targets", "drained", "killed", "agent"}; raises BounceRefusal when the settings-home
    key or launchd is unavailable."""
    if sys.platform != "darwin":
        raise BounceRefusal(f"bounce relaunches through launchd; platform {sys.platform!r} has none")
    tp = _tenant_priority()
    if tp is None:
        raise BounceRefusal("COORDINATOR_SETTINGS_HOME unresolvable: coordinator_core.tenant_priority not importable")
    try:
        prefix = tp.settings_home_prefix()
    except tp.SettingsHomeKeyMissing as exc:
        raise BounceRefusal(str(exc)) from None
    rows = parse_ps_nice((ps or ps_nice_snapshot)())
    targets = select_bounce_targets(rows, prefix, tp.is_serve_lineage, keep_pids=(os.getpid(), os.getppid()))
    term = term or (lambda pid: os.kill(pid, signal.SIGTERM))
    kill = kill or (lambda pid: os.kill(pid, signal.SIGKILL))
    alive = alive or _pid_alive
    for pid in targets:
        try:
            term(pid)
        except OSError:
            pass
    waited = 0.0
    while waited < drain_seconds and any(alive(p) for p in targets):
        sleep(0.5)
        waited += 0.5
    stragglers = [p for p in targets if alive(p)]
    for pid in stragglers:
        try:
            kill(pid)
        except OSError:
            pass
    root = Path(agent_dir) if agent_dir else login_agent_dir()
    target_plist, _ = _login_agent_paths(root)
    agent = _bounce_agent(target_plist, launchctl, uid)
    return {"roster": list(roster), "targets": targets,
            "drained": [p for p in targets if p not in stragglers], "killed": stragglers, "agent": agent}


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
    paths = (*_login_agent_paths(root), *(() if sys.platform == "darwin" else _login_timer_paths(root)))
    for path in paths:
        if path.is_symlink() or path.exists():
            path.unlink()
            removed = True
    return "removed" if removed else "absent"


LEGACY_LOGIN_AGENT_LABELS = ("com.coordinator.unimatrix-autolink",)


def run_launchctl(*args):
    """Run launchctl; None when it cannot launch."""
    try:
        return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None


def remove_legacy_login_agents(agent_dir=None, launchctl=None, uid=None):
    """Boot out and delete the prior-era autolink labels so one supervisor remains; macOS only.

    Returns the labels removed: a loaded label is booted out of `gui/<uid>`, its plist unlinked.
    A label neither loaded nor on disk is a no-op, so a rerun returns [].
    """
    if sys.platform != "darwin":
        return []
    run = launchctl or run_launchctl
    root = Path(agent_dir) if agent_dir else login_agent_dir()
    if not agent_dir:
        _refuse_real_agent_dir(root)
    domain = f"gui/{uid if uid is not None else os.getuid()}"
    removed = []
    for label in LEGACY_LOGIN_AGENT_LABELS:
        plist = root / f"{label}.plist"
        loaded = run("print", f"{domain}/{label}")
        did = False
        if loaded is not None and loaded.returncode == 0:
            booted = run("bootout", f"{domain}/{label}")
            did = booted is not None and booted.returncode == 0
        if plist.is_symlink() or plist.exists():
            plist.unlink()
            did = True
        if did:
            removed.append(label)
    return removed


def _pid_alive(pid):
    """True when `pid` exists (a pid we may not signal still exists)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def reap_stale_relays(dest_dir, ps=None, kill=None):
    """SIGTERM relay sessions that are orphaned (sshd parent gone) or older than the installed relay
    script's st_ctime; a live current session is kept. POSIX only. Returns (stale, mismatched, failed) pid lists."""
    if sys.platform == "win32":
        return [], [], []
    rs = _lib("unimatrix_relay_sessions")
    sessions = rs.list_relay_sessions((ps or rs.ps_snapshot)())
    stamps = {}
    for name in rs.RELAY_SCRIPTS:
        try:
            stamps[name] = (Path(dest_dir) / name).stat().st_ctime
        except OSError:
            continue
    groups = rs.classify_relay_sessions(sessions, stamps, _pid_alive)
    victims = groups[rs.STALE] + groups[rs.MISMATCHED]
    _, failed = rs.reap(victims, kill)
    return [s.pid for s in groups[rs.STALE]], [s.pid for s in groups[rs.MISMATCHED]], failed


def render_peer_doctrine(dest_dir, template=None, skills_root=None):
    """Return the managed block: the doctrine template with {SEND}, {INVOKE} and {SKILLS_ROOT} bound.

    {SKILLS_ROOT} is the installed plugin skills tree (the module SKILLS_ROOT when `skills_root` is None)."""
    body = Path(template or PEER_DOCTRINE_TEMPLATE).read_text(encoding="utf-8").strip("\n")
    body = body.replace("{SEND}", _hook_command(dest_dir, SEND_SCRIPT)).replace("{INVOKE}", _quote_argv([invoke_launcher_path()])).replace("{SKILLS_ROOT}", str(Path(skills_root or SKILLS_ROOT)))
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


def _resolve_agy_plugin_root(explicit_plugin_root=None):
    """Resolve the Claude plugin source root for agy-plugin generation:
    explicit --plugin-root -> PLUGIN_ROOT (if it already carries .claude-plugin/plugin.json or is absent) ->
    CLAUDE_PLUGIN_ROOT -> content-root pointer (coordinator-content-repo/coordinator or flat published coordinator-claude) ->
    PLUGIN_ROOT fallback."""
    if explicit_plugin_root:
        return Path(explicit_plugin_root)
    if not PLUGIN_ROOT.is_dir() or (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").is_file():
        return PLUGIN_ROOT
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        cand = Path(env_root)
        if cand.is_dir() and (cand / ".claude-plugin" / "plugin.json").is_file():
            return cand
    pointer, _ = _content_root_pointer()
    if pointer:
        ptr = Path(pointer)
        for cand in (ptr / "coordinator", ptr):
            if (cand / ".claude-plugin" / "plugin.json").is_file():
                return cand
    return PLUGIN_ROOT


def _write_agy_plugin_tree(args, out, dest=None):
    """Generate the agy plugin tree from --plugin-root (or resolved content root) into --out (or <dest>/agy-plugin).

    `dest` defaults to <settings home>/unimatrix. True when written; a generator OSError/ValueError
    prints WARN and returns False, never raises.
    """
    plugin_root = _resolve_agy_plugin_root(getattr(args, "plugin_root", None))
    tree = Path(args.out) if getattr(args, "out", None) else (dest or settings_home() / "unimatrix") / AGY_PLUGIN_TREE_DIR
    if not getattr(args, "out", None) and not plugin_root.is_dir():
        print(f"NOTE: agy plugin tree skipped: plugin root {plugin_root} not found (name one with --plugin-root)", file=out)
        return True
    if not (plugin_root / ".claude-plugin" / "plugin.json").is_file():
        print(f"NOTE: agy plugin source {plugin_root} has no .claude-plugin/plugin.json; "
              f"pass --plugin-root <DoE/coordinator> for a strict-valid plugin", file=out)
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


def _content_root_pointer():
    """(pointer value or "", the pointer files consulted), read by the shared spawn-free resolver."""
    try:
        mod = _lib("machine_local_impl_resolve")
        value = mod.read_content_root_pointer()
        names = (mod._CONTENT_ROOT_POINTER, mod._LEGACY_ROOT_POINTER)
        dirs = (os.path.join(mod.settings_home(), "machine-local"), mod.claude_home())
    except (OSError, AttributeError):
        return "", ["<content-root pointer unreadable: lib/machine_local_impl_resolve.py missing>"]
    return value, [os.path.join(d, n) for n in names for d in dirs]


def resolve_doctrine(plugin_root=None):
    """Return (root or None, rung, detail): where global-doctrine/ resolved, which rung, what was read.

    Rungs in order: the DoE content-root pointer, then the base beside this install, where a flat
    published checkout keeps the tree under `templates/`. A named `plugin_root` is an explicit override:
    it replaces both the pointer and this script's location. On a miss `rung` is None and `detail`
    names the pointer files read and the beside-install candidates.
    """
    pointer, pointer_files = ("", []) if plugin_root else _content_root_pointer()
    if pointer and (Path(pointer) / "global-doctrine" / "CLAUDE.md").is_file():
        return Path(pointer), "DoE root pointer", pointer
    base = Path(plugin_root) if plugin_root else PLUGIN_ROOT
    for root in (base.parent, base, base.parent / "templates", base / "templates"):
        if (root / "global-doctrine" / "CLAUDE.md").is_file():
            return root, "beside install" if not plugin_root else "--plugin-root", str(root)
    if plugin_root:
        return None, None, f"--plugin-root named, pointer not consulted; searched beside {base}"
    state = f"pointer value '{pointer}' has no global-doctrine/CLAUDE.md" if pointer else "no pointer value"
    return None, None, (f"{state}; pointer files read: {', '.join(pointer_files)}; "
                        f"also searched beside {base}")


def doctrine_root(plugin_root=None):
    """The directory holding global-doctrine/, or None when neither the DoE root pointer nor this install carries it."""
    return resolve_doctrine(plugin_root)[0]


def resolve_engine_root():
    """Return (engine_root or None, provenance); never raises.

    COORDINATOR_ENGINE_ROOT (an existing directory) is the explicit operator override; otherwise the
    published klabauter root named by the settings-home registry key repos.claude_klabauter, stamped.
    Never self-locates and never reads the authoring-checkout registry key. A miss returns None with a
    provenance naming the key, or the resolver's first failure line.
    """
    override = os.environ.get("COORDINATOR_ENGINE_ROOT") or ""
    if override and Path(override).is_dir():
        return override, "COORDINATOR_ENGINE_ROOT override"
    try:
        shim_path = next((p for p in (PLUGIN_ROOT / "lib" / "resolve-claude-klabauter" / "_resolve_claude_klabauter.py",
                                      _BIN_DIR.parent / "lib" / "resolve-claude-klabauter" / "_resolve_claude_klabauter.py") if p.is_file()), None)
        if shim_path is None:
            raise RuntimeError("lib/resolve-claude-klabauter/_resolve_claude_klabauter.py not found")
        spec = importlib.util.spec_from_file_location("_resolve_claude_klabauter_for_install", shim_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        root = mod._resolve_published_engine(mod._ml_dir())
    except Exception as exc:
        lines = str(exc).strip().splitlines()
        return None, f"resolver failed: {lines[0] if lines else type(exc).__name__}"
    if root and Path(root).is_dir():
        return str(Path(root)), "published klabauter (repos.claude_klabauter)"
    return None, ("repos.claude_klabauter unset or not a stamped engine build; "
                  "run: machine-local set repos.claude_klabauter <published klabauter root>")


def trust_codex_hook(hooks_path, timeout=30, *, dest_dir=None):
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
        expected = _codex_expected_handlers(hooks_file, dest_dir)
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
                ident = (_event_id(h.get("eventName", "")), str(h.get("command", "")))
                if expected.get(ident) != h.get("command") or ident in found:
                    raise ValueError(f"{h.get('eventName', 'hook')} handler is duplicated or on the wrong event")
                found[ident] = h
            missing = sorted(set(expected) - set(found))
            if missing:
                raise ValueError(f"codex did not discover the {', '.join(event for event, _command in missing)} handler (features.hooks disabled?)")
            if len({h.get("key") for h in found.values()}) != len(found):
                raise ValueError("discovered handlers share a trust key")
            return found

        before = discover(2)
        for hook in before.values():
            if not (isinstance(hook.get("key"), str) and hook["key"]
                    and isinstance(hook.get("currentHash"), str) and hook["currentHash"]):
                raise ValueError(f"{hook.get('eventName', 'hook')} reports no key or content hash")
            if hook.get("trustedHash") == hook["currentHash"] or (hook.get("trustedHash") is None and hook.get("trustStatus") == "trusted"):
                continue
            rpc(3, "config/value/write", {
                "keyPath": f'hooks.state.{json.dumps(hook["key"], ensure_ascii=False)}.trusted_hash',
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


def enroll_codex_runtime(engine_root, *, consent=False, check=False, dest_dir=None, out=None):
    """Shared strict enrollment/update: return zero only for a ready, trusted runtime.

    Check mode is read-only; consent must be the literal boolean True for writes.
    """
    out = out or sys.stdout
    if not check and consent is not True:
        print("Codex runtime: consent.codex_runtime must be true", file=out)
        return 2
    root = Path(engine_root)
    dest = Path(dest_dir) if dest_dir else settings_home() / "unimatrix"
    hp = codex_hooks_path()
    from coordinator_core.install import host_install_codex
    if not host_present("codex"):
        print("Codex runtime: codex CLI absent; install Codex then rerun coordinator-install", file=out)
        return 7
    ready, note = external_session_capability(str(root))
    if not ready:
        print(f"Codex runtime: lifecycle unavailable: {note}", file=out)
        return 7
    try:
        # Validate operator configuration before changing any owned surface.
        config = hp.with_name("config.toml")
        if config.exists():
            tomllib.loads(config.read_text(encoding="utf-8"))
        data = _load_hooks(hp)
        drift = any([g for g in _codex_events(data, hp, event) if _codex_ours(g, dest)] != [want]
                    for event, want in codex_hook_events(dest, str(root)).items())
        mcp = host_install_codex.apply(check=True)
        print(f"Codex runtime: hooks={'drift' if drift else 'current'} mcp={mcp.mcp}", file=out)
        if mcp.mcp not in ("current", "present", "would-write"):
            return 7
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        template = Path(plugin_root) / "templates" / "unimatrix" / "peer-doctrine.md" if plugin_root else None
        peer_block = render_peer_doctrine(dest, template, Path(plugin_root) / "skills" if plugin_root else None)
        if check:
            print("Codex runtime: native trust not probed (read-only)", file=out)
            return 0
        copied = []
        try:
            install_scripts(root / "coordinator" / "bin", dest, copied.append)
        finally:
            if copied:
                print(f"Codex runtime: copied {len(copied)} runtime files into {dest}", file=out)
        if not copied:
            print(f"Codex runtime: runtime files current in {dest}", file=out)
        state = seed_codex_hook(hp, dest, str(root))
        ok, note = trust_codex_hook(hp, dest_dir=dest)
        print(f"Codex runtime: hooks={state}; {note}", file=out)
        if not ok:
            return 5
        footer = seed_codex_status_line(config)
        print(f"Codex runtime: status line {footer}", file=out)
        doctrine = seed_peer_doctrine(codex_rules_path(), peer_block)
        print(f"Codex runtime: peer doctrine {doctrine}", file=out)
        rule = seed_file(codex_exec_rule_path(), render_codex_exec_rule(dest))
        print(f"Codex runtime: exec rule {rule}", file=out)
        missing = _seed_standing_doctrine(
            out, True, False, codex_rules_path(), None,
            Path.home() / ".agents" / "skills", None,
            plugin_root, Path(plugin_root) / "skills" if plugin_root else SKILLS_ROOT)
        if missing:
            print(f"Codex runtime: incomplete: {', '.join(missing)}", file=out)
            return 7
        mcp = host_install_codex.apply()
        print(f"Codex runtime: project-rag MCP {mcp.mcp}", file=out)
        if mcp.mcp not in ("written", "current", "present"):
            return 7
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Codex runtime: {exc}", file=out)
        return 7
    print("Codex runtime ready", file=out)
    return 0


def enroll_agy_runtime(engine_root, *, consent=False, check=False, dest_dir=None, out=None, plugin_root=None):
    """Shared strict Agy runtime enrollment/update: return zero only for a ready runtime.

    Check mode is read-only; consent must be the literal boolean True for writes.
    """
    out = out or sys.stdout
    if not check and consent is not True:
        print("Agy runtime: consent.agy_runtime must be true", file=out)
        return 2
    root = Path(engine_root)
    dest = Path(dest_dir) if dest_dir else settings_home() / "unimatrix"
    hp = agy_hooks_path()
    pj = agy_plugins_path()
    settings = agy_settings_path()
    from coordinator_core.install import host_install_agy
    if not host_present("agy"):
        print("Agy runtime: agy CLI absent; install Antigravity then rerun coordinator-install", file=out)
        return 7
    ready, note = external_session_capability(str(root))
    if not ready:
        print(f"Agy runtime: lifecycle unavailable: {note}", file=out)
        return 7
    try:
        data = _load_hooks(hp)
        want = agy_hook_entry(dest, str(root))
        hooks_drift = data.get(AGY_HOOK_KEY) != want
        tree = dest / AGY_PLUGIN_TREE_DIR
        pjson = tree / "plugin.json"
        plugin_ok = False
        if pjson.is_file():
            try:
                loaded = json.loads(pjson.read_text(encoding="utf-8"))
                plugin_ok = isinstance(loaded, dict) and bool(loaded.get("version"))
            except (OSError, ValueError):
                plugin_ok = False
        mcp = host_install_agy.apply(check=True)
        print(f"Agy runtime: hooks={'drift' if hooks_drift else 'current'} plugin={'current' if plugin_ok else 'drift'} mcp={mcp.mcp}", file=out)
        if mcp.mcp not in ("current", "present", "would-write"):
            return 7
        if check:
            return 0
        install_scripts(root / "coordinator" / "bin", dest)
        state = seed_agy_hook(hp, dest, str(root))
        print(f"Agy runtime: hooks={state}", file=out)
        seed_host_status_line(settings, "agy", engine_root=str(root), dest_dir=dest)
        if not launcher_sac_blocked():
            seed_agy_allow_rule(settings, rules=agy_absolute_allow_rules(dest))
        _seed_agy_config(hp.with_name("config.json"), out)
        resolved_plugin = _resolve_agy_plugin_root(plugin_root)
        ns = types.SimpleNamespace(plugin_root=str(resolved_plugin), out=str(tree))
        if not _write_agy_plugin_tree(ns, out, dest):
            print("Agy runtime: plugin tree generation failed", file=out)
            return 7
        seed_agy_plugin(pj, tree)
        seed_peer_doctrine(agy_rules_path(), render_peer_doctrine(dest))
        missing = _seed_standing_doctrine(
            out, False, True, None, agy_rules_path(),
            None, hp.with_name("skills.json"),
            str(resolved_plugin), resolved_plugin / "skills",
        )
        if missing:
            print(f"Agy runtime: incomplete: {', '.join(missing)}", file=out)
            return 7
        mcp = host_install_agy.apply()
        if mcp.mcp not in ("written", "current", "present"):
            return 7
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Agy runtime: {exc}", file=out)
        return 7
    print("Agy runtime ready", file=out)
    return 0


def main(argv=None, version_text=None, dest_dir=None, out=None, hooks_path=None,
         codex_hooks=None, codex_trust=None, codex_rules=None, agy_rules=None, codex_exec_rule=None,
         agy_skills_json=None, codex_skills=None, agent_dir=None, schtasks=None, pair_run=None,
         router_live=None, restart_router=None, launchctl=None, relay_ps=None, relay_kill=None, authorized_keys=None,
         openssh_run=None, sac_blocked=None):
    """`sac_blocked` (() -> bool) replaces the Smart App Control probe that gates the agy allow rule.
    `openssh_run` (argv -> CompletedProcess) replaces the PowerShell run behind the Windows OpenSSH receive-side
    check, which an overridden `hooks_path` otherwise skips. `authorized_keys` overrides the local file whose stale forced-command interpreters --install rewrites;
    an overridden `hooks_path` otherwise skips it. `launchctl` (argv tail -> CompletedProcess), `relay_ps` (() -> ps text) and `relay_kill` (pid -> None)
    replace the real launchctl, `ps` and SIGTERM, which an overridden `hooks_path` otherwise skips.
    `router_live(dest) -> bool` and `restart_router(dest, say) -> dict` replace the installed autolink's
    router check and restart. `hooks_path` overrides agy's file. Codex's file defaults to codex_hooks_path(), or to a sibling
    `codex-hooks.json` when only `hooks_path` is overridden; trust runs against the real Codex only for
    the default path, unless `codex_trust` (a callable taking the hooks path) is injected. The peer
    doctrine files follow the same rule: real home files by default, siblings `codex-AGENTS.md` and
    `agy-GEMINI.md` of `hooks_path` when it is overridden, or the explicit `codex_rules`/`agy_rules`.
    The login agent lives in the OS agent directory by default, a `login-agent` sibling of `hooks_path`
    when that is overridden, or `agent_dir`; `schtasks` (argv tail -> CompletedProcess) replaces the real
    Task Scheduler, which an overridden `hooks_path` otherwise skips."""
    out = out or sys.stdout
    os.environ.setdefault("COORDINATOR_SETTINGS_HOME", str(settings_home()))
    if agent_dir is None and hooks_path is not None:
        agent_dir = Path(hooks_path).with_name("login-agent")
    if schtasks is None and hooks_path is not None:
        schtasks = lambda *a: None
    if hooks_path is not None:
        launchctl = launchctl or (lambda *a: None)
        relay_ps = relay_ps or (lambda: "")
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
    agy_status = agy_settings_path() if hooks_path is None else Path(hooks_path).with_name("agy-settings.json")
    grok_status = grok_config_path() if hooks_path is None else Path(hooks_path).with_name("grok-config.toml")
    grok_rp = grok_rules_path() if hooks_path is None else Path(hooks_path).with_name("grok-peer-doctrine.md")
    grok_hp = grok_hooks_path() if hooks_path is None else Path(hooks_path).with_name("grok-hooks.json")
    if codex_trust is None and codex_default:
        codex_trust = lambda hp: trust_codex_hook(hp, dest_dir=dest_dir)
    agy_sj = Path(agy_skills_json) if agy_skills_json else (
        agy_hooks_path().with_name("skills.json") if hooks_path is None else Path(hooks_path).with_name("agy-skills.json")
    )
    agy_pj = agy_plugins_path() if hooks_path is None else Path(hooks_path).with_name("agy-plugins.json")
    codex_sd = Path(codex_skills) if codex_skills else (
        Path.home() / ".agents" / "skills" if hooks_path is None else Path(hooks_path).with_name("codex-agents-skills")
    )
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--install", action="store_true", help="copy the vendored scripts into the settings home")
    ap.add_argument("--enroll-runtime", action="store_true", help="explicitly consent to strict Codex enrollment/update")
    ap.add_argument("--check", action="store_true", help="read-only runtime drift report with --enroll-runtime")
    ap.add_argument("--uninstall", action="store_true", help="remove everything --install seeded for Codex and agy")
    ap.add_argument("--refresh-hooks", action="store_true", help="re-render an already-installed Grok hook to the current emitter output "
                    "(session-start and adoption trigger; creates nothing, no script copy, no Claude gate)")
    ap.add_argument("--force", action="store_true", help="warn instead of refusing outside the verified range")
    ap.add_argument("--hosts", help="comma list of claude,codex,agy,grok (grok installs a status line, the peer doctrine rules file and a PreToolUse host-guard hook); "
                    "--install seeds only the relay and no host unless named here (--uninstall and --refresh-hooks default to all hosts). "
                    "Naming no claude skips the Claude range gate when `claude` is not on PATH")
    ap.add_argument("--autolink", action="store_true", help="with --install: register the login autolink (Windows Run key, "
                    "macOS launch agent); default off")
    ap.add_argument("--openssh-receive", action="store_true", help="Windows: install and start OpenSSH Server, set it "
                    "Automatic, open firewall TCP 22 and ACL administrators_authorized_keys to Administrators+SYSTEM "
                    "(needs an elevated shell; driven through MSI pwsh or Windows PowerShell 5.1, never the MSIX alias)")
    ap.add_argument("--pair", metavar="ALIAS", help="mint or read the pair key for a far box and print its "
                    "authorized_keys line and ssh config block")
    ap.add_argument("--file-key", action="store_true", help="mint (or read) this box's file-transfer key, "
                    "separate from the relay key, and print its public line and fingerprint for the membership signer")
    ap.add_argument("--control-key", metavar="BOX", help="mint or read the control key for a far box "
                    "(~/.ssh/unimatrix_control_<BOX>) and print its authorized_keys line and the "
                    f"{CONTROL_ALIAS_PREFIX}<BOX> ssh config block; the line is a full-admin key pinned by from=")
    ap.add_argument("--from-cidr", metavar="CIDR", action="append", help="with --control-key: a from= address range "
                    "for the far box to admit (repeatable); default this box's verified membership from_cidrs")
    ap.add_argument("--unencrypted-key", action="store_true", help="with --pair, --file-key or --control-key: mint the private key "
                    "without a passphrase (for boxes with no 1Password); the default mint is passphrase-encrypted, except "
                    "--control-key, which is always unencrypted (the launch path has no agent)")
    ap.add_argument("--remint", action="store_true", help="with --pair, --file-key or --control-key: delete the existing private "
                    "key, its .pub and its 1Password passphrase item, then mint anew")
    ap.add_argument("--plugin-root", metavar="DIR", help="seed Codex and agy doctrine and skills from this plugin "
                    "root (doctrine in DIR.parent or DIR, skills in DIR/skills) instead of this script's own location")
    ap.add_argument("--out", metavar="DIR", help="write the agy plugin tree (translated plugin source) into DIR; "
                    f"default under --install: <settings home>/unimatrix/{AGY_PLUGIN_TREE_DIR}")
    ap.add_argument("--bounce", action="store_true", help="macOS: drain the live roster, SIGTERM every settings-home "
                    "process at nice != 0 (project-rag serve lineage excluded), then boot the autolink launchd agent out "
                    "and in so the messaging set relaunches at nice 0; no sudo")
    args = ap.parse_args(argv)
    if args.enroll_runtime:
        root, provenance = resolve_engine_root()
        target_hosts = [h.strip() for h in (args.hosts or "codex").split(",") if h.strip()]
        if not root:
            print(f"Runtime enrollment: engine unresolved ({provenance})", file=out)
            return 7
        rc = 0
        for host in target_hosts:
            if host == "codex":
                rc = rc or enroll_codex_runtime(root, consent=True, check=args.check, dest_dir=dest_dir, out=out)
            elif host == "agy":
                rc = rc or enroll_agy_runtime(root, consent=True, check=args.check, dest_dir=dest_dir, out=out,
                                              plugin_root=args.plugin_root)
            else:
                print(f"Runtime enrollment: unsupported host {host!r} (expected codex or agy)", file=out)
                return 2
        return rc
    skills_root = Path(args.plugin_root) / "skills" if args.plugin_root else SKILLS_ROOT
    if args.openssh_receive:
        if sys.platform != "win32":
            print("openssh receive side: Windows only; nothing to do", file=out)
            return 0
        return openssh_receive_report(out, openssh_run or subprocess.run, apply=True)
    if args.bounce:
        try:
            names = [n for n, _ in _sibling("unimatrix-roster.py").live_sessions()]
        except Exception as exc:  # the bounce still runs; the report must not read as an empty roster
            names = []
            print(f"WARN: live roster unreadable ({type(exc).__name__}); bounce proceeds with an empty roster", file=out)
        try:
            report = bounce_messaging(names, ps=relay_ps, kill=relay_kill, term=relay_kill,
                                      launchctl=launchctl, agent_dir=agent_dir)
        except BounceRefusal as exc:
            print(f"REFUSE: {exc}", file=out)
            return 6
        print(f"bounce {report['agent']}: roster {len(report['roster'])} session(s), drained "
              f"{len(report['drained'])}, killed {len(report['killed'])}, targets {report['targets']}", file=out)
        return 0 if report["agent"] == "bounced" else 6
    if args.file_key:
        try:
            priv, pub_line, fp = file_key(run=pair_run or subprocess.run, unencrypted=args.unencrypted_key,
                                          remint=args.remint, on_mint=lambda ref: print(
                                              f"minted a passphrase-encrypted private key\npassphrase: {ref}", file=out))
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"REFUSE: {exc}", file=out)
            return 6
        print(f"file key: {priv}\nfingerprint: {fp}\n"
              f"file_pub (give to the membership signer; verify the fingerprint there): {pub_line}", file=out)
        return 0
    if args.control_key is not None:
        try:
            cidrs = control_from_cidrs(args.from_cidr)
            priv, body = control_key(args.control_key, run=pair_run or subprocess.run, remint=args.remint)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"REFUSE: {exc}", file=out)
            return 6
        print(f"control key for {args.control_key}: {priv}", file=out)
        print("ssh config block for this box (add to ~/.ssh/config):", file=out)
        print(render_ssh_config_block(args.control_key, priv, host_alias=f"{CONTROL_ALIAS_PREFIX}{args.control_key}",
                                      peer_options=peer_ssh_options(args.control_key, run=pair_run or subprocess.run)),
              file=out)
        status, line = install_over_link(args.control_key, body, run=pair_run or subprocess.run, control=True,
                                         from_cidrs=cidrs)
        if status == "no-link":
            print(f"no authorized link to {args.control_key}: paste this line on the far box. The far invocation "
                  f"record is absent, so launch sends the bare form until `unimatrix-install.py --control-key "
                  f"{args.control_key}` is re-run over a link:\n{control_authorized_keys_line(body, cidrs)}", file=out)
        elif status == "failed":
            print(f"install over the link to {args.control_key} failed: paste this line on the far box:\n{line}", file=out)
        elif status == "admin":
            print(f"{args.control_key} is a Windows administrator account: nothing written. Append this line to "
                  f"%ProgramData%\\ssh\\administrators_authorized_keys on the far box:\n{line}", file=out)
        else:
            print(f"authorized_keys line {'already present' if status == 'present' else 'added'} on {args.control_key}; "
                  f"line:\n{line}", file=out)
        return 0
    if args.pair is not None:
        try:
            priv, body = pair_key(args.pair, run=pair_run or subprocess.run, unencrypted=args.unencrypted_key,
                                  remint=args.remint, on_mint=lambda ref: print(
                                      f"minted a passphrase-encrypted private key\npassphrase: {ref}", file=out))
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
    want_grok = hosts is None or "grok" in hosts

    if args.refresh_hooks:
        if not want_grok:
            return 0
        try:
            res = refresh_grok_hook(grok_hp, Path(dest_dir) if dest_dir else settings_home() / "unimatrix",
                                    resolve_engine_root()[0])
        except (ValueError, OSError) as exc:
            print(f"REFUSE: {exc}; grok hook not refreshed", file=out)
            return 4
        print(f"grok hook {res} in {grok_hp}", file=out)
        return 0

    if args.uninstall:
        hp = Path(hooks_path) if hooks_path else agy_hooks_path()
        steps = []
        if want_grok:
            steps.append(("grok status line", grok_status, lambda: seed_host_status_line(grok_status, "grok", uninstall=True)))
            steps.append(("grok peer doctrine", grok_rp, lambda: unseed_peer_doctrine(grok_rp)))
            steps.append(("grok hook", grok_hp, lambda: unseed_grok_hook(grok_hp)))
        if want_agy:
            steps.append(("agy allow rule", agy_status, lambda: seed_agy_allow_rule(agy_status, uninstall=True)))
            steps.append(("agy status line", agy_status, lambda: seed_host_status_line(agy_status, "agy", uninstall=True)))
            steps.append(("agy hook", hp, lambda: unseed_agy_hook(hp)))
            steps.append(("agy plugin", agy_pj, lambda: unseed_agy_plugin(
                agy_pj, (Path(dest_dir) if dest_dir else settings_home() / "unimatrix") / AGY_PLUGIN_TREE_DIR)))
            steps.append(("agy skills", agy_sj, lambda: _seed().unseed_agy_skills(agy_sj, skills_root)))
            steps.append(("agy coordinator doctrine", agy_rp, lambda: _seed().unseed_block(
                agy_rp, _seed().DOCTRINE_BEGIN, _seed().DOCTRINE_END)))
            steps.append(("agy peer doctrine", agy_rp, lambda: unseed_peer_doctrine(agy_rp)))
        if want_codex:
            steps.append(("codex status footer", codex_hp.with_name("config.toml"), lambda: seed_codex_status_line(codex_hp.with_name("config.toml"), uninstall=True)))
            steps.append(("codex hook", codex_hp, lambda: unseed_codex_hook(codex_hp, dest_dir)))
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

    for d in untraversable_path_dirs():
        print(f"WARN: PATH entry {d} is not traversable by this user, so tools in it (grok) read as absent; "
              f"remedy: sudo chmod 755 {d}", file=out)
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

    want_codex, want_agy, want_grok = (hosts is not None and h in hosts for h in ("codex", "agy", "grok"))
    absent = [h for h, wanted in (("codex", want_codex), ("agy", want_agy), ("grok", want_grok))
              if wanted and not host_present(h)]
    for h in absent:
        why = f"no {h} home" if h == "agy" else "a leftover home does not count"
        print(f"{h} hook skipped: {h} not on PATH and {why}; no {h} status line, doctrine or rules written", file=out)
    want_codex, want_agy, want_grok = (want_codex and "codex" not in absent, want_agy and "agy" not in absent,
                                       want_grok and "grok" not in absent)
    print(NATIVE_RC_NOTICE, file=out)
    alias_warning = pwsh_alias_remedy()
    if alias_warning:
        print(f"WARN: {alias_warning}", file=out)
    if sys.platform == "win32" and (hooks_path is None or openssh_run is not None):
        openssh_receive_report(out, openssh_run or subprocess.run)
    dest = Path(dest_dir) if dest_dir else settings_home() / "unimatrix"
    digest_before = router_closure_digest(dest)
    try:
        copied = install_scripts(Path(__file__).resolve().parent, dest)
    except FileNotFoundError as exc:
        print(f"REFUSE: {exc}", file=out)
        return 3
    except PipeCapabilityRefused as exc:
        print(f"REFUSE: {exc}", file=out)
        return 5
    print(f"installed {len(copied)} scripts into {dest}", file=out)
    stale, mismatched, failed = reap_stale_relays(dest, relay_ps, relay_kill)
    if stale or mismatched or failed:
        print(f"relay sessions reaped: {len(stale)} orphaned, {len(mismatched)} on replaced code"
              + (f"; could not signal pid {', '.join(map(str, failed))}" if failed else ""), file=out)
    restart_failed = False
    if authorized_keys is None and hooks_path is None:
        authorized_keys = Path.home() / ".ssh" / "authorized_keys"
    if authorized_keys is not None:
        try:
            rewrote = rewrite_forced_interpreters(authorized_keys, forced_command_interpreter())
        except OSError as exc:
            rewrote = 0
            print(f"WARN: authorized_keys forced-command interpreters not rewritten: {exc}", file=out)
        if rewrote:
            print(f"authorized_keys: {rewrote} forced-command interpreter(s) rewritten to {forced_command_interpreter()}", file=out)
        try:
            repointed = rewrite_forced_relay_paths(authorized_keys, dest)
        except OSError as exc:
            repointed = 0
            print(f"WARN: authorized_keys forced-command relay paths not rewritten: {exc}", file=out)
        if repointed:
            print(f"authorized_keys: {repointed} forced-command relay path(s) rewritten to the installed copy in {dest}", file=out)
    router_live = router_live or router_is_live
    if router_live(dest) and (digest_before != router_closure_digest(dest)
                              or not (dest / "router" / "router.pid.json").is_file()):
        try:
            res = (restart_router or restart_installed_router)(dest, lambda s: print(s, file=out)) or {}
            print(f"router restarted: {res.get('stopped')} old pid {res.get('old_pid')} new pid {res.get('new_pid')}", file=out)
        except Exception as exc:
            restart_failed = True
            print(f"REFUSE: router restart failed: {exc}; scripts are installed, run `unimatrix-autolink.py restart`", file=out)
    print(f"authorized_keys line for the far side (paste verbatim, fill <key-body>): "
          f"{authorized_keys_line(dest)}", file=out)
    print(f"authorized_keys line for the far side's file key (fill <key-body> and <box>, this box's name): "
          f"{authorized_keys_line(dest, file_peer='<box>')}", file=out)
    print(f"authorized_keys line for the far side's control key (full admin; fill <key-body> and {FROM_CIDRS_PLACEHOLDER}): "
          f"{control_authorized_keys_line('<key-body>', [FROM_CIDRS_PLACEHOLDER])}", file=out)
    engine_root, provenance = resolve_engine_root()
    hp = Path(hooks_path) if hooks_path else agy_hooks_path()
    if want_agy:
        try:
            res = seed_agy_hook(hp, dest, engine_root)
        except ValueError as exc:
            print(f"REFUSE: {exc}; agy hook not installed", file=out)
            return 4
        print(f"agy hook {res} in {hp}", file=out)
    if want_grok:
        try:
            linked = link_grok_local_bin()
        except OSError as exc:
            linked = f"not linked ({exc})"
        if linked in ("linked", "absent") or linked.startswith("not linked"):
            print(f"grok ~/.local/bin link {linked}", file=out)
    if want_grok:
        try:
            res = seed_grok_hook(grok_hp, dest, engine_root)
        except ValueError as exc:
            print(f"REFUSE: {exc}; grok hook not installed", file=out)
            return 4
        print(f"grok hook {res} in {grok_hp}", file=out)
    if want_codex:
        try:
            res = seed_codex_hook(codex_hp, dest, engine_root)
        except ValueError as exc:
            print(f"REFUSE: {exc}; codex hook not installed", file=out)
            return 4
        print(f"codex hook {res} in {codex_hp}", file=out)
    rc = 0
    lifecycle_ready, lifecycle_note = external_session_capability(engine_root)
    if want_codex and not lifecycle_ready:
        print(f"session lifecycle DEGRADED: {lifecycle_note}; transport hooks remain installed", file=out)
        rc = 7
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
    if want_codex:
        try:
            config = codex_hp.with_name("config.toml")
            print(f"codex status footer {seed_codex_status_line(config)} in {config}", file=out)
        except (OSError, ValueError) as exc:
            missing.append("codex status footer")
            print(f"WARN: codex status footer not installed: {exc}", file=out)
    for label, host, config, wanted in (("agy", "agy", agy_status, want_agy), ("grok", "grok", grok_status, want_grok)):
        if not wanted:
            continue
        try:
            res = seed_host_status_line(config, host, engine_root=engine_root, dest_dir=dest)
            print(f"{label} status line {res} in {config}", file=out)
        except (OSError, ValueError) as exc:
            missing.append(f"{label} status line")
            print(f"WARN: {label} status line not installed: {exc}", file=out)
    if want_agy:
        try:
            if (sac_blocked or launcher_sac_blocked)():
                print("agy allow rule skipped: Smart App Control blocks the coordinator-invoke forwarder", file=out)
            else:
                agy_rules = agy_absolute_allow_rules(dest)
                print(f"agy allow rule {seed_agy_allow_rule(agy_status, rules=agy_rules)} in {agy_status}", file=out)
                print(f"agy allow rule granted: {agy_rules[0]}", file=out)
        except (OSError, ValueError) as exc:
            missing.append("agy allow rule")
            print(f"WARN: agy allow rule not installed: {exc}", file=out)
        _seed_agy_config(hp.with_name("config.json"), out)
        if not _write_agy_plugin_tree(args, out, dest):
            missing.append("agy plugin tree")
        else:
            tree = Path(args.out) if args.out else dest / AGY_PLUGIN_TREE_DIR
            if tree.is_dir():
                try:
                    print(f"agy plugin {seed_agy_plugin(agy_pj, tree)} in {agy_pj}", file=out)
                except (OSError, ValueError) as exc:
                    missing.append("agy plugin registration")
                    print(f"WARN: agy plugin not registered: {exc}", file=out)
    try:
        block = render_peer_doctrine(dest, skills_root=skills_root)
    except (OSError, ValueError) as exc:
        block = None
        print(f"WARN: peer doctrine not installed: {exc}", file=out)
    for label, rp, wanted in (("codex", codex_rp, want_codex), ("agy", agy_rp, want_agy),
                             ("grok", grok_rp, want_grok)):
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
    pinned = record_python_pin(agent_dir)
    if pinned:
        print(f"unimatrix.python pinned: {pinned}", file=out)
    if args.autolink:
        try:
            state, where = register_login_agent(dest, agent_dir, schtasks, launchctl)
            print(f"login agent {state}: {where}" if state != "skipped" else f"WARN: login agent not registered: {where}", file=out)
        except OSError as exc:
            print(f"WARN: login agent not registered: {exc}", file=out)
    try:
        for label in remove_legacy_login_agents(agent_dir, launchctl):
            print(f"legacy login agent removed: {label}", file=out)
    except Exception as exc:
        print(f"WARN: legacy login agent not removed: {exc}", file=out)
    if engine_root:
        print(f"governance engine root: {engine_root} ({provenance})", file=out)
        if verified and lifecycle_ready:
            print("hook wiring/trust verified: Codex SessionStart, SubagentStart, SessionEnd and PreToolUse handlers discovered, "
                  "enabled and trusted", file=out)
        elif verified and want_codex:
            print("transport hook wiring/trust verified; session lifecycle capability UNVERIFIED", file=out)
        elif want_codex:
            print("hook wiring/trust UNVERIFIED: Codex handler trust was not confirmed", file=out)
        print("governance enforcement UNVERIFIED until the C6 live matrix", file=out)
    else:
        print(f"governance DEGRADED: engine root unresolved ({provenance}); guards answer the neutral "
              "fallback (ask on agy, {} on Codex), never allow", file=out)
    print("governance scope: Codex local-tool PreToolUse (shell, projected edits, MCP, spawn briefs; native coverage limits apply); agy run_command and edit tools", file=out)
    return ROUTER_RESTART_REFUSED_RC if restart_failed else rc


def _seed_standing_doctrine(out, want_codex, want_agy, codex_rp, agy_rp, codex_sd, agy_sj,
                            plugin_root=None, skills_root=None):
    """Seed wanted doctrine and skills, returning every incomplete required surface.

    Returns required doctrine or skill surfaces left incomplete.
    """
    seed = _seed()
    missing = []
    skills_root = skills_root or SKILLS_ROOT
    root, rung, detail = resolve_doctrine(plugin_root)
    for label, rp, wanted, cap in (("codex", codex_rp, want_codex, seed.CODEX_CAP_BYTES),
                                   ("agy", agy_rp, want_agy, seed.AGY_CAP_BYTES)):
        if not wanted:
            continue
        try:
            if root is None:
                raise OSError(f"global-doctrine/ not found: {detail}")
            res = seed.seed_block(rp, seed.render_coordinator_doctrine(root, cap), seed.DOCTRINE_BEGIN, seed.DOCTRINE_END)
            print(f"{label} coordinator doctrine {res} in {rp} (doctrine from {rung}: {detail})", file=out)
            lines, size = seed.unmanaged_extent(rp, (seed.DOCTRINE_BEGIN, seed.DOCTRINE_END), (DOCTRINE_BEGIN, DOCTRINE_END))
            if lines:
                print(f"WARN: {label} rules file {rp} holds {lines} non-blank line(s) ({size} bytes) outside the "
                      f"coordinator-doctrine block, left untouched; project rules belong in that repo's AGENTS.md", file=out)
        except (OSError, ValueError) as exc:
            missing.append(f"{label} coordinator doctrine")
            print(f"WARN: {label} coordinator doctrine not installed: {exc}", file=out)
    try:
        if want_agy:
            print(f"agy skills {seed.seed_agy_skills(agy_sj, skills_root)} in {agy_sj}", file=out)
        if want_codex:
            names = seed.seed_codex_skills(codex_sd, skills_root)
            print(f"codex skills available {len(names)} in {codex_sd}", file=out)
    except (OSError, ValueError) as exc:
        print(f"WARN: skills not installed: {exc}", file=out)
        missing.append("host skills")
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
