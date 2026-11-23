#!/usr/bin/env python3
"""Launch codex, agy, grok or claude as a headless EM carrying a launcher-written fire grant.

Usage: headless-em-launch.py <codex|agy|grok|claude> [--session-id ID] [--prepare-only] [--native-executable PATH]
       [--name NAME] [--resume ID] [--cwd DIR] [-- cli args...]
       headless-em-launch.py --exit-check --session-id ID [--cwd DIR]
       (--help prints this text)

Without --native-executable the CLI is resolved from PATH (on Windows a .exe as-is, or codex's npm shim
mapped to its native exe). For Darwin codex exec --json, a profile installed by
scripts/build_darwin_diagnostic_codex.py selects its diagnostic binary. PTY commands receive no
diagnostic registration. An explicit --native-executable selects that executable.

Resolves the child session id (--session-id, else COORDINATOR_SESSION_ID, else a fresh uuid4), writes
the grant for (session id, family), and hands the child COORDINATOR_SESSION_ID plus the grant token
(COORDINATOR_ALLOW_HEADLESS_EM_TOKEN). Exit 2 on a refusal, 127 when the CLI is not on PATH.

codex, agy and grok run as a supervised child (POSIX): when it exits 0 while a run its session fired is
neither landed nor halted, one stderr line per run names its fire_wait command and the launcher exits 3;
a non-zero child code is returned as is (a signal death as 128+signum). Codex exec --json also
propagates a failed engine_ask.submit command reported by the native child. A check that itself fails exits 3.
--exit-check runs only that check (0 clean, 3 open runs or an unchecked exit): the Windows path, whose
--prepare-only JSON names its argv as "exit_check".

This is the only caller of write_headless_em_grant. It refuses when the calling env carries a worker
marker, so a worker cannot mint itself an EM grant; agent-worker-launch.py never writes one.
claude (both OSes) runs `claude --bg -n NAME` (or `claude --bg --resume ID`) captured in --cwd and prints
{"name", "id", "session_id"} JSON, id being the one claude printed; it is never exec'd.
--prepare-only prints {argv, session_id, environment, exit_check} as JSON (the environment holds the token, and for
codex on Windows a shaped PATH: real pwsh dir first, Store alias dirs dropped) and execs nothing;
Windows non-prepare launches are refused because exec must not sit under python.exe.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
_REPO_ROOT = HERE.parents[1]

REFUSED = 2
EXIT_OPEN_RUNS = 3
SESSION_ENV = "COORDINATOR_SESSION_ID"
PROVIDER_ENV = "COORDINATOR_AGENT_PROVIDER"
FAMILIES = ("codex", "agy", "grok", "claude")
BG_TIMEOUT_S = 60
_BG_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_BG_ID = re.compile(r"\b(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{6,12})\b")


def _worker_marker(environ) -> str:
    """Why this env is a worker's, or '' when it is not."""
    if str(environ.get("COORDINATOR_AGENT_WORKER", "")).lower() in ("1", "true", "yes"):
        return "COORDINATOR_AGENT_WORKER is set"
    role = environ.get("COORDINATOR_AGENT_ROLE")
    if role and role != "em":
        return f"COORDINATOR_AGENT_ROLE={role}"
    return ""


def _printed_id(text):
    """The session id `claude --bg` prints: a uuid, else a short hex id; '' when none is present."""
    found = _BG_UUID.findall(text or "") or _BG_ID.findall(text or "")
    return found[-1] if found else ""


def _run_bg(argv, *, cwd, env, runner, name):
    """Run `claude --bg` captured; print {name, id, session_id} JSON and return 0, else a refusal code."""
    kw = {"cwd": cwd, "env": env, "capture_output": True, "text": True, "timeout": BG_TIMEOUT_S,
          "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        done = runner(argv, **kw)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"headless-em-launch: claude --bg failed: {exc}", file=sys.stderr)
        return REFUSED
    if done.returncode != 0:
        print(f"headless-em-launch: claude --bg exited {done.returncode}: {(done.stderr or '').strip()}",
              file=sys.stderr)
        return REFUSED
    bg_id = _printed_id(done.stdout)
    if not bg_id:
        print(f"headless-em-launch: claude --bg printed no session id: {(done.stdout or '').strip()!r}",
              file=sys.stderr)
        return REFUSED
    print(json.dumps({"name": name, "id": bg_id, "session_id": env.get(SESSION_ENV)}))
    return 0


GROK_ENGINE_OPS = ("engine_ask.submit", "workflow.fire", "workflow.fire_status", "workflow.fire_wait",
                   "workflow.revise")

GROK_WORKER_EXES = ("sizing-assemble", "coordinator-doc-new")


def _settings_bin_dir(environ) -> str:
    home = environ.get("COORDINATOR_SETTINGS_HOME") or str(Path.home() / ".coordinator-claude-settings")
    return str(Path(home) / "bin")


def _grok_launch_args(extra, environ, platform) -> list[str]:
    """`extra` led by `--permission-mode auto` and one `--allow Bash(<abs coordinator-invoke> <op>:*)` per engine op, plus one `Bash(<abs exe>:*)` per
    worker executable in `GROK_WORKER_EXES` (the settings-home bin only, never a blanket Execute).

    grok does not expand `$HOME` when matching, so each rule names the resolved absolute path. A caller's
    own `--permission-mode` and any allow rule it already passed are kept, never doubled.
    """
    exe = str(Path(_settings_bin_dir(environ)) / ("coordinator-invoke.exe" if platform == "win32"
                                                  else "coordinator-invoke"))
    head = [] if any(a == "--permission-mode" or a.startswith("--permission-mode=") for a in extra) \
        else ["--permission-mode", "auto"]
    suffix = ".exe" if platform == "win32" else ""
    rules = [f"Bash({exe} {op}:*)" for op in GROK_ENGINE_OPS]
    rules += [f"Bash({Path(_settings_bin_dir(environ)) / (name + suffix)}:*)" for name in GROK_WORKER_EXES]
    for rule in rules:
        if rule not in extra:
            head += ["--allow", rule]
    return [*head, *extra]


def _agy_launch_args(extra, cwd, environ=None) -> list[str]:
    """`extra` led by one `--add-dir` per workspace root and `--mode accept-edits`.

    agy's workspace is its add-dirs, not `--cwd`, and a `read_file` outside it is auto-denied headless.
    Roots: the launch cwd, `~/.coordinator`, and `agy_grant_guard.grant_dirs` (the generated plugin skills,
    the only outside subtree a stage was measured reading). Never the settings home or engine root whole.
    `--dangerously-skip-permissions` is dropped; a caller's own `--mode` and any dir it already granted are
    kept, never doubled.

    Trap: agy has no read-only grant, so each add-dir is writable; `launch` hashes the granted dirs around
    the stage (`agy_grant_tamper`). When agy ships read-only grants, switch to them and drop the hash guard.
    """
    from coordinator_core import agy_grant_guard

    rest = [a for a in extra if a != "--dangerously-skip-permissions"]
    head = []
    granted = {rest[i + 1] for i, a in enumerate(rest[:-1]) if a == "--add-dir"}
    roots = [cwd or os.getcwd(), str(Path.home() / ".coordinator"),
             *map(str, agy_grant_guard.grant_dirs(environ))]
    for d in roots:
        if d not in granted:
            granted.add(d)
            head += ["--add-dir", d]
    if not any(a == "--mode" or a.startswith("--mode=") for a in rest):
        head += ["--mode", "accept-edits"]
    return [*head, *rest]


def _with_settings_bin(environ) -> str:
    """The caller's PATH with `<settings home>/bin` appended once, so agy's sandbox resolves coordinator-invoke.

    Reads the injected `environ`, not `os.environ`, so it mirrors `_settings_home.settings_home()`'s
    COORDINATOR_SETTINGS_HOME / `~/.coordinator-claude-settings` precedence rather than calling it.
    """
    bin_dir = _settings_bin_dir(environ)
    path_key = next((k for k in environ if k.upper() == "PATH"), None)
    entries = [e for e in (environ[path_key].split(os.pathsep) if path_key else []) if e]
    if bin_dir not in entries:
        entries.append(bin_dir)
    return os.pathsep.join(entries)


def _submit_exit(line: bytes) -> int:
    """Read the tool's completion status, ignoring model text and unrelated failed commands."""
    try:
        event = json.loads(line)
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            return 0
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            return 0
        code = item.get("exit_code")
        if type(code) is not int or code == 0:
            return 0
        command = item.get("command")
        if not isinstance(command, str):
            return 0
        argv = shlex.split(command)
        if len(argv) == 3 and Path(argv[0]).name in ("sh", "bash", "zsh", "dash", "ksh") and argv[1] in ("-c", "-lc"):
            command = argv[2]
            argv = shlex.split(command)
        if len(argv) < 2 or argv[1] != "engine_ask.submit" or Path(argv[0]).name != "coordinator-invoke":
            return 0
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        if not any(token in (";", "&&", "||", "|", "&") for token in lexer):
            return code
    except ValueError:
        pass
    return 0


def _diagnostic_install(environ):
    """Resolve one atomically installed native binary and its compiled endpoint."""
    generation = Path(_settings_bin_dir(environ)).parent / "native-diagnostics/current"
    if not generation.is_symlink():
        return None
    root = generation.parent
    info = root.lstat()
    generation = generation.resolve(strict=True)
    if (root.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077
            or generation.parent != root.resolve() or not generation.name.startswith("build-")):
        raise PermissionError("invalid host diagnostic installation")
    for member, expected_type in ((generation, stat.S_ISDIR), (generation / "codex", stat.S_ISREG),
                                  (generation / "socket-directory", stat.S_ISREG)):
        info = member.lstat()
        if info.st_uid != os.getuid() or info.st_mode & 0o022 or not expected_type(info.st_mode):
            raise PermissionError("unsafe native diagnostic installation member")
    directory = Path((generation / "socket-directory").read_text())
    if not directory.is_absolute():
        raise ValueError("diagnostic socket directory must be absolute")
    return generation / "codex", directory


def _spawn_codex_events(cmd, env):
    """Forward the native JSON event stream immediately and retain the first failed submit."""
    install = _diagnostic_install(env) if sys.platform == "darwin" else None
    if install and Path(cmd[0]).resolve() == install[0]:
        from coordinator_core.warm.restricted_endpoint import diagnostic_spawn
        child_context = diagnostic_spawn(install[1], cmd, env)
    else:
        child_context = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE)
    with child_context as child:
        failure = 0
        for line in child.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            failure = failure or _submit_exit(line)
        code = child.wait()
    return code or failure


def _spawn(cmd, env, *, codex_events=False):
    """Run the CLI with inherited stdio and return its exit code (a signal death as 128+signum).

    SIGINT gets a no-op handler, not SIG_IGN: an ignored signal stays ignored across exec, a handler
    resets, so Ctrl-C reaches the CLI while the launcher survives to run the exit check.
    """
    prior = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        if codex_events:
            code = _spawn_codex_events(cmd, env)
        else:
            code = subprocess.run(cmd, env=env).returncode
    finally:
        signal.signal(signal.SIGINT, prior)
    return 128 - code if code < 0 else code


def _spawn_captured(cmd, env):
    """Run the CLI with captured output: (exit code, stdout bytes, stderr bytes)."""
    done = subprocess.run(cmd, env=env, capture_output=True)
    return done.returncode, done.stdout, done.stderr


def _run_agy_guarded(cmd, env, spawn_captured):
    """Run an agy stage over hash-watched grant dirs; (code, refusal paths).

    The stage's output is held and released only when no granted file changed; a changed file discards
    it and returns the paths for the typed `agy_grant_tamper` refusal.
    """
    from coordinator_core import agy_grant_guard

    dirs = [cmd[i + 1] for i, a in enumerate(cmd[:-1]) if a == "--add-dir"]
    watched = [Path(d) for d in dirs if Path(d) in set(agy_grant_guard.grant_dirs(env))]
    before = agy_grant_guard.snapshot(watched)
    code, out, err = spawn_captured(cmd, env)
    changed = agy_grant_guard.changed_paths(before, agy_grant_guard.snapshot(watched))
    if changed:
        agy_grant_guard.write_marker(changed)
        return code, changed
    sys.stdout.buffer.write(out)
    sys.stdout.flush()
    sys.stderr.buffer.write(err)
    sys.stderr.flush()
    return code, []


def exit_check(session_id, cwd=None, *, open_runs=None):
    """0 when every run this session fired is landed or halted, else EXIT_OPEN_RUNS.

    Prints one stderr line per open run. A check that cannot run is not a clean exit: it prints one
    line naming the failure and returns EXIT_OPEN_RUNS.
    """
    try:
        if open_runs is None:
            from coordinator_core.ops.workflow_fire.session_runs import open_runs_for_session as open_runs
        from coordinator_core.git.repo_root import show_toplevel
        start = cwd or os.getcwd()
        runs = open_runs(Path(show_toplevel(start) or start), session_id)
    except (RuntimeError, OSError, ImportError) as exc:
        print(f"headless-em-launch: exit check failed for session {session_id}: {exc}", file=sys.stderr)
        return EXIT_OPEN_RUNS
    for run in runs:
        print(f"headless-em-launch: run {run['run_id']} is {run['stage']}; wait: coordinator-invoke "
              f"workflow.fire_wait '{json.dumps({'fire_id': run['fire_id']})}'", file=sys.stderr)
    return EXIT_OPEN_RUNS if runs else 0


_CODEX_SUBCOMMANDS = ("exec", "e")


def _codex_writable_dirs(extra: list[str], cwd: str | None = None) -> list[str]:
    """`extra` with `--add-dir <machine lock root>` added: codex's workspace-write sandbox otherwise denies
    the engine's per-user lock sidecar, and engine_ask.submit refuses. With `cwd`, `-C <cwd>` too: the
    supervised spawn takes no cwd, so codex otherwise works in the caller's tree. Placed after an `exec`
    subcommand, whose own flags are the ones it reads."""
    from coordinator_core.locked_write import _machine_lock_dir

    root = str(_machine_lock_dir().parent)
    flag = [] if root in extra else ["--add-dir", root]
    if cwd and not {"-C", "--cd"} & set(extra):
        flag += ["-C", cwd]
    if not flag:
        return list(extra)
    if extra and extra[0] in _CODEX_SUBCOMMANDS:
        return [extra[0], *flag, *extra[1:]]
    return [*flag, *extra]


def _codex_workdir(extra: list[str], cwd: str | None) -> str:
    """The directory the codex child works in: the caller's `-C`/`--cd`, else `cwd`, else this process's."""
    for i, arg in enumerate(extra):
        if arg in ("-C", "--cd") and i + 1 < len(extra):
            return extra[i + 1]
        if arg.startswith("--cd="):
            return arg[len("--cd="):]
    return cwd or os.getcwd()


def launch(family, extra, *, session_id=None, which=shutil.which, spawn=_spawn, environ=None,
           prepare_only=False, platform=None, native_executable=None, mint=uuid.uuid4,
           name=None, resume=None, cwd=None, runner=subprocess.run, open_runs=None,
           spawn_captured=_spawn_captured) -> int:
    """Write the grant and run the CLI with the token env; returns an exit code.

    claude is not supervised: `claude --bg [-n NAME | --resume ID]` runs captured in `cwd` on both OSes and
    the printed id is returned with the name. Any other family runs under `spawn(cmd, env)`; its code is
    returned, except 0 becomes EXIT_OPEN_RUNS while a run the session fired is non-terminal.
    """
    from coordinator_core.ops.workflow_fire.headless_em_grant import (
        HEADLESS_EM_TOKEN_ENV, HeadlessEmGrantError, write_headless_em_grant)

    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    if family not in FAMILIES:
        print(f"headless-em-launch: refused: family must be one of {', '.join(FAMILIES)}", file=sys.stderr)
        return REFUSED
    marker = _worker_marker(environ)
    if marker:
        print(f"headless-em-launch: refused: a worker env cannot mint an EM grant ({marker})", file=sys.stderr)
        return REFUSED
    if (name or resume) and family != "claude":
        print("headless-em-launch: --name and --resume apply to claude only", file=sys.stderr)
        return REFUSED
    if platform == "win32" and not prepare_only and family != "claude":
        print("headless-em-launch: Windows launch must run in the current PowerShell process; "
              "use --prepare-only and start the CLI from it", file=sys.stderr)
        return REFUSED
    cli = native_executable
    if not cli and family == "codex" and platform == "darwin" and extra[:1] == ["exec"] and "--json" in extra:
        install = _diagnostic_install(environ)
        if install:
            cli = str(install[0])
    if not cli and family == "claude":
        cli = (which("claude.exe") if platform == "win32" else None) or which("claude")
    elif not cli:
        from coordinator_core.codex_runner.resolve import CodexUnavailable, resolve_native_cli
        try:
            cli = resolve_native_cli(family, platform, which=which)
        except CodexUnavailable as exc:
            print(f"headless-em-launch: {exc}; pass --native-executable with its installed path", file=sys.stderr)
            return REFUSED
    if not cli:
        print(f"headless-em-launch: {family} is not on PATH", file=sys.stderr)
        return 127
    if platform == "win32" and not cli.lower().endswith(".exe"):
        print("headless-em-launch: Windows requires the native CLI .exe, not a .cmd/.bat shim; "
              "pass --native-executable with its installed path", file=sys.stderr)
        return REFUSED
    if family == "codex":
        from coordinator_core.codex_runner.sandbox_scratch import ScratchGrantRefused, ensure_sandbox_scratch
        try:
            ensure_sandbox_scratch(Path(_codex_workdir(extra, cwd)))
        except ScratchGrantRefused as exc:
            print(f"headless-em-launch: refused: {exc}", file=sys.stderr)
            return REFUSED
    sid = (session_id or environ.get(SESSION_ENV) or "").strip() or str(mint())
    try:
        token = write_headless_em_grant(sid, family)
    except HeadlessEmGrantError as exc:
        print(f"headless-em-launch: refused: {exc}", file=sys.stderr)
        return REFUSED
    if family == "codex":
        cmd = [cli, *_codex_writable_dirs(extra, cwd)]
    elif family == "grok":
        cmd = [cli, *_grok_launch_args(extra, environ, platform)]
    elif family == "agy":
        cmd = [cli, *_agy_launch_args(extra, cwd, environ)]
    elif family == "claude":
        cmd = [cli, "--bg", *(["--resume", resume] if resume else ["-n", name] if name else []), *extra]
    else:
        cmd = [cli, *extra]
    child = {SESSION_ENV: sid, HEADLESS_EM_TOKEN_ENV: token, PROVIDER_ENV: family}
    if family == "codex" and platform == "win32":
        from coordinator_core.codex_runner.codex_spawn_env import place_installed_pwsh
        path_key = next((k for k in environ if k.upper() == "PATH"), None)
        if path_key is not None:
            inherited = environ[path_key]
            shaped = place_installed_pwsh({"PATH": inherited}, environ, windows=True)["PATH"]
            if shaped != inherited:
                child["PATH"] = shaped
    if family == "agy":
        child["PATH"] = _with_settings_bin(environ)
    if prepare_only:
        check = [sys.executable, str(Path(__file__).resolve()), "--exit-check", "--session-id", sid]
        print(json.dumps({"argv": cmd, "session_id": sid, "environment": child, "exit_check": check}))
        return 0
    if family == "claude":
        return _run_bg(cmd, cwd=cwd, env={**environ, **child}, runner=runner, name=name)
    if family == "agy" and any(a == "-p" or a.startswith("--print") for a in cmd):
        code, tampered = _run_agy_guarded(cmd, {**environ, **child}, spawn_captured)
        if tampered:
            print(json.dumps({"refused": "agy_grant_tamper", "paths": tampered}), file=sys.stderr)
            return REFUSED
    elif family == "codex" and extra and extra[0] in _CODEX_SUBCOMMANDS and "--json" in extra and spawn is _spawn:
        code = _spawn(cmd, {**environ, **child}, codex_events=True)
    else:
        code = spawn(cmd, {**environ, **child})
    gate = exit_check(sid, cwd, open_runs=open_runs)
    return gate if code == 0 else code


def main(argv=None, **kw):
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import ensure_engine_on_path, place_engine_root_on_path

    if ensure_engine_on_path(__file__) is None:
        place_engine_root_on_path(str(_REPO_ROOT))
    args = list(sys.argv[1:] if argv is None else argv)
    if args in ([], ["--help"], ["-h"]):
        print(__doc__)
        return 0 if args else REFUSED
    if "--" in args:
        i = args.index("--")
        args, extra = args[:i], args[i + 1:]
    else:
        extra = []
    if "--exit-check" in args:
        ck = argparse.ArgumentParser(prog="headless-em-launch", add_help=False)
        ck.add_argument("--exit-check", action="store_true")
        ck.add_argument("--session-id")
        ck.add_argument("--cwd")
        cn = ck.parse_args(args)
        if not cn.session_id:
            print("headless-em-launch: --exit-check requires --session-id", file=sys.stderr)
            return REFUSED
        return exit_check(cn.session_id, cn.cwd, open_runs=kw.get("open_runs"))
    ap = argparse.ArgumentParser(prog="headless-em-launch", add_help=False)
    ap.add_argument("family", choices=FAMILIES)
    ap.add_argument("--session-id")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--native-executable")
    ap.add_argument("--name")
    ap.add_argument("--resume")
    ap.add_argument("--cwd")
    ns = ap.parse_args(args)
    return launch(ns.family, extra, session_id=ns.session_id, prepare_only=ns.prepare_only,
                  native_executable=ns.native_executable, name=ns.name, resume=ns.resume,
                  cwd=ns.cwd, **kw)


if __name__ == "__main__":
    sys.exit(main())
