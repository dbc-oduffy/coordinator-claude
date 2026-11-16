#!/usr/bin/env python3
"""agy PreToolUse hook: the Klabauter guard first, then keep a live agy leg for this conversation.

Order: unimatrix-host-guard.py (loaded as a sibling; `--engine-root <path>` selects the engine) answers
first. A guard answer other than "ask" (a deny) is returned unchanged with no rewrite. An "ask" answer,
including the guard's own degraded neutral "ask", falls through to the leg bootstrap below; a guard
reason and the bootstrap rewrite then share one "ask". The one "allow" is a peer reply: a run_command that
is exactly this interpreter and the installed unimatrix-send.py beside this hook, plain arguments, no shell
operator or expansion (mirrors the Codex unimatrix.rules send rule); it is never a fallback.

Hooks do not receive agy's language-server address or token, but run_command children do. When no
current leg exists, the hook prefixes the command the agent is about to run with a detached start of
unimatrix-agy-hook-launch.py, which inherits the token. That rewrite answers "ask": the user sees and
approves the exact command. Every other path also answers "ask": agy fails closed on a non-zero exit,
invalid JSON, or a reply without `decision`, and "ask" keeps agy's own approval behaviour where
"allow" would silently widen it.

A headless agy (`-p`/`--print` on the agy ancestor's command line) gets no rewrite and no launcher
spawn: the guard's answer passes through so agy's own permissions.allow decides.

A leg is current only if it is alive, was started under this same agy process (the nearest agy ancestor of the hook; none found is never current),
and its language server still accepts connections. An agy restart changes the token and port, so a
leg that survives one is stale even though its pid is alive. A `pending` leg (started by SessionStart
without a token) is never current: the rewrite relaunches it live.

Leg record (STATE/<conversationId>.json, written by the launcher, read here and by the router):
  {"pid": <leg pid>, "conversation": <id>, "endpoint": <leg socket>, "ls_address": "host:port",
   "agy_pid": <agy pid>, "mode": "pending" | "live"}   (mode absent reads as live)
"""
import importlib.util
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

SPAWN_DEBOUNCE_S = 30.0
HOOK_WALL_SECS = 1.0
_hard_exit = os._exit
HERE = Path(__file__).resolve().parent
LAUNCH = HERE / "unimatrix-agy-hook-launch.py"
PASS = {"decision": "ask"}
CONV_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def settings_home():
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def state_dir():
    return settings_home() / "unimatrix" / "agy-legs"


AGY_EXE_NAMES = ("agy.exe", "agy")
MAX_ANCESTOR_DEPTH = 8


def _nt_process_table():
    """{pid: (parent pid, lowercase exe name)} from one CreateToolhelp32Snapshot walk; {} on failure. No subprocess."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    table = {}
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if snap in (None, ctypes.c_void_p(-1).value):
            return {}
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(ProcessEntry)
            ok = k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile.lower())
                ok = k32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snap)
    except (OSError, AttributeError, ValueError):
        return {}
    return table


def _proc_reader():
    """pid -> (parent pid, lowercase name) or None; Windows snapshot, else /proc. None reader: no process table here."""
    if os.name == "nt":
        table = _nt_process_table()
        return table.get if table else None
    if not Path("/proc/self/stat").exists():
        return None

    def read(pid):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
            name = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip().lower()
            return int(stat[stat.rindex(")") + 2:].split()[1]), name
        except (OSError, ValueError, IndexError):
            return None
    return read


def agy_ancestor_pid(read=None, start=None, max_depth=MAX_ANCESTOR_DEPTH):
    """Pid of the nearest ancestor of `start` (default: this process) whose exe is agy, else None.

    The hook's direct parent is an intermediate launcher that exits with the hook, so getppid() is
    never taken. `read(pid)` returns (parent pid, name) or None; it is the injected process table.
    No agy ancestor within max_depth, or no table: None, noted on stderr.
    """
    read = read or _proc_reader()
    pid = os.getpid() if start is None else start
    seen = {pid}
    for _ in range(max_depth):
        row = read(pid) if read else None
        if not row:
            break
        pid = row[0]
        if not isinstance(pid, int) or pid <= 0 or pid in seen:
            break
        seen.add(pid)
        parent = read(pid)
        if parent and str(parent[1]).lower() in AGY_EXE_NAMES:
            return pid
    print(f"unimatrix-agy-hook: no agy ancestor within {max_depth} levels; agy_pid not recorded", file=sys.stderr)
    return None


def _nt_cmdline(pid):
    """Command line of a 64-bit Windows process read from its PEB (no subprocess); None on any failure."""
    import ctypes
    from ctypes import wintypes
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return None
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        nt = ctypes.WinDLL("ntdll")
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                          ctypes.POINTER(ctypes.c_size_t)]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        nt.NtQueryInformationProcess.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                                 ctypes.POINTER(ctypes.c_ulong)]
        handle = k32.OpenProcess(0x1010, False, pid)  # QUERY_INFORMATION | VM_READ
        if not handle:
            return None
        try:
            def read(addr, size):
                buf = ctypes.create_string_buffer(size)
                got = ctypes.c_size_t(0)
                if not k32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
                    return None
                return buf.raw[:got.value]

            pbi = (ctypes.c_void_p * 6)()
            if nt.NtQueryInformationProcess(handle, 0, pbi, ctypes.sizeof(pbi), None) != 0 or not pbi[1]:
                return None
            params = read(pbi[1] + 0x20, 8)  # PEB.ProcessParameters
            if not params:
                return None
            ustr = read(int.from_bytes(params, "little") + 0x70, 16)  # RTL_USER_PROCESS_PARAMETERS.CommandLine
            if not ustr:
                return None
            length, buf_addr = int.from_bytes(ustr[:2], "little"), int.from_bytes(ustr[8:16], "little")
            text = read(buf_addr, length) if length and buf_addr else None
            return text.decode("utf-16-le", "replace") if text else None
        finally:
            k32.CloseHandle(handle)
    except (OSError, AttributeError, ValueError):
        return None


def process_cmdline(pid):
    """Space-joined command line of `pid`, or None when it cannot be read."""
    if os.name == "nt":
        return _nt_cmdline(pid)
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip() or None
    except OSError:
        pass
    try:
        out = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True, timeout=2)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


PRINT_FLAG_RE = re.compile(r"\s(?:-p|--print)(?:[=\s]|$)")


def agy_print_mode(agy_pid, read=None):
    """True when the agy process runs headless (`-p`/`--print`). Unknown agy pid or unreadable line: False."""
    if agy_pid is None:
        return False
    line = (read or process_cmdline)(agy_pid)
    return bool(line and PRINT_FLAG_RE.search(" " + line))


def pid_alive(pid):
    """True while `pid` runs. os.kill(pid, 0) means CTRL_C_EVENT on Windows, so ask the roster helper there."""
    if os.name == "nt":
        return bool(load_sibling("unimatrix-roster").pid_alive(pid))
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def ls_reachable(addr):
    host, _, port = (addr or "").rpartition(":")
    try:
        with socket.create_connection((host or "localhost", int(port)), timeout=0.2):
            return True
    except (OSError, ValueError):
        return False


def leg_current(conv, agy_pid, state=None):
    try:
        with open((state or state_dir()) / f"{conv}.json", encoding="utf-8") as f:
            rec = json.load(f)
        if not pid_alive(int(rec["pid"])):
            return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if rec.get("mode", "live") != "live":
        return False  # a pending leg only queues; the first run_command relaunches it live
    return agy_pid is not None and rec.get("agy_pid") == agy_pid and ls_reachable(rec.get("ls_address"))


def _console_python():
    """A real console CPython; the running image only when no resolver is beside this script (the hook never raises)."""
    try:
        spec = importlib.util.spec_from_file_location("unimatrix_pretool_python_interp", HERE / "lib" / "python_interp.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        found = mod.resolve_console_python()
    except (OSError, ImportError, AttributeError):
        found = None
    return found or sys.executable


def launcher_argv(conv, agy_pid):
    """Launcher command line; --agy-pid is omitted when no agy ancestor was found."""
    argv = [_console_python(), str(LAUNCH), "--conversation", conv]
    return argv + ["--agy-pid", str(agy_pid)] if agy_pid is not None else argv


def launch_prefix(conv, agy_pid):
    """Shell text that starts the launcher detached and silent, for sh. None on Windows: agy runs
    PowerShell there, which rejects cmd syntax, so bootstrap_rewrite spawns the launcher itself."""
    if os.name == "nt":
        return None
    argv = launcher_argv(conv, agy_pid)
    return f"(nohup {' '.join(shlex.quote(a) for a in argv)} >/dev/null 2>&1 &)", "; "


def spawn_launcher(conv, agy_pid):
    """Windows: start the launcher detached from this hook, since the command line cannot carry the
    start (agy's PowerShell rejects cmd syntax). The hook's own environment lacks the language-server
    token; the launcher is idempotent, so a failed or tokenless start only leaves the leg pending.
    A start stamp (STATE/<conv>.spawned) debounces it: each hook is a fresh process, so a start within
    SPAWN_DEBOUNCE_S of the stamp is skipped. An unwritable stamp never blocks the start."""
    stamp = state_dir() / f"{conv}.spawned"
    try:
        if time.time() - stamp.stat().st_mtime < SPAWN_DEBOUNCE_S:
            return
    except OSError:
        pass
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:
        pass
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(launcher_argv(conv, agy_pid),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, creationflags=flags)
    except OSError:
        pass


_SIBLINGS = {}


def load_sibling(name):
    """The sibling script as a module, executed once per process and cached."""
    mod = _SIBLINGS.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SIBLINGS[name] = mod
    return mod


def run_guard(raw, engine_root):
    """The host guard's agy answer for the raw payload text; the neutral "ask" when it cannot run."""
    try:
        answer, _state = load_sibling("unimatrix-host-guard").guard("agy", raw, engine_root)
    except Exception:
        return dict(PASS)
    return answer if isinstance(answer, dict) and isinstance(answer.get("decision"), str) else dict(PASS)


def bootstrap_rewrite(payload, agy_pid):
    """{"reason", "overwrite"} when a run_command needs the leg started, else None."""
    conv = payload.get("conversationId")
    call = payload.get("toolCall")
    call = call if isinstance(call, dict) else {}
    args = call.get("args")
    cmd = args.get("CommandLine") if isinstance(args, dict) else None
    if (not isinstance(conv, str) or not CONV_RE.match(conv) or call.get("name") != "run_command"
            or not isinstance(cmd, str) or not cmd or leg_current(conv, agy_pid)):
        return None
    if agy_print_mode(agy_pid):
        return None  # a headless run keeps no leg; a rewrite would break the user's permissions.allow match
    prefix = launch_prefix(conv, agy_pid)
    if prefix is None:
        spawn_launcher(conv, agy_pid)
        return None
    start, sep = prefix
    return {"reason": "PM-installed unimatrix hook: also (re)starts the agy leg for Claude/Codex peer messaging in the background.",
            "overwrite": {"CommandLine": f"{start}{sep}{cmd}"}}


SEND_SCRIPT = HERE / "unimatrix-send.py"
UNSAFE_SHELL_TEXT = ("$", "`", "\n", "\r", "%", "^")


SHELL_SYNTAX_OUTSIDE_QUOTES = set("();<>|&{}@#,")


def quote_aware_tokens(cmd):
    """Split a Windows command line on unquoted whitespace, keeping backslashes literal and dropping the
    quote marks. None on an unterminated quote or on shell syntax outside quotes."""
    tokens, cur, quote, has = [], [], None, False
    for c in cmd:
        if quote:
            if c == quote:
                quote = None
            else:
                cur.append(c)
        elif c in "'\"":
            quote, has = c, True
        elif c.isspace():
            if has or cur:
                tokens.append("".join(cur))
            cur, has = [], False
        elif c in SHELL_SYNTAX_OUTSIDE_QUOTES:
            return None
        else:
            cur.append(c)
    if quote:
        return None
    if has or cur:
        tokens.append("".join(cur))
    return tokens


def is_peer_reply(payload):
    """True only for a run_command that is the interpreter, then the installed send script, then plain
    arguments: the shape of the Codex exec rule's argv. Any shell operator, expansion, other interpreter
    or other script path is False."""
    call = payload.get("toolCall")
    call = call if isinstance(call, dict) else {}
    args = call.get("args")
    cmd = args.get("CommandLine") if isinstance(args, dict) else None
    if call.get("name") != "run_command" or not isinstance(cmd, str) or any(c in cmd for c in UNSAFE_SHELL_TEXT):
        return False
    if os.name == "nt":
        tokens = quote_aware_tokens(cmd)
        if tokens is None:
            return False
    else:
        try:
            lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            return False
    if len(tokens) < 2 or tokens[0] not in (sys.executable, _console_python()) or tokens[1] != str(SEND_SCRIPT):
        return False
    return os.name == "nt" or not any(t and set(t) <= set("();<>|&") for t in tokens)


def decide(payload, agy_pid, engine_root=None, raw=None):
    if not isinstance(payload, dict):
        return dict(PASS)
    guard = run_guard(json.dumps(payload) if raw is None else raw, engine_root)
    if guard.get("decision") != "ask":
        return guard
    if is_peer_reply(payload):
        return {**guard, "decision": "allow"}
    rewrite = bootstrap_rewrite(payload, agy_pid)
    if rewrite is None:
        return guard
    reasons = [r for r in (guard.get("reason"), rewrite["reason"]) if isinstance(r, str) and r]
    return {**guard, "decision": "ask", "reason": " | ".join(reasons), "overwrite": rewrite["overwrite"]}


def engine_root_arg(argv):
    if "--engine-root" in argv:
        i = argv.index("--engine-root")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _answer(argv, result):
    """Worker body: the decision into `result["out"]`; any failure is the neutral "ask"."""
    try:
        raw = sys.stdin.read()
        result["out"] = decide(json.loads(raw), agy_ancestor_pid(), engine_root_arg(argv), raw)
    except Exception:
        result["out"] = dict(PASS)


def _wall_expired():
    """The advisory ask for a hook that outran HOOK_WALL_SECS, after one hook_wall degrade row."""
    try:
        load_sibling("unimatrix-host-guard")._record_degrade("agy", "hook_wall", HOOK_WALL_SECS, None)
    except Exception:
        pass
    return {"decision": "ask", "reason": "coordinator: guard did not finish within the hook wall; engine cold or unreachable"}


def main(argv=None):
    """One JSON object with `decision` on stdout and exit 0, whatever stdin or the checks do.

    decide() runs on a daemon thread joined at HOOK_WALL_SECS; a slow or stuck engine answers the
    advisory ask and the process exits hard, so no worker can hold it past agy's hook timeout."""
    argv = list(sys.argv[1:] if argv is None else argv)
    result = {}
    worker = threading.Thread(target=_answer, args=(argv, result), daemon=True)
    worker.start()
    worker.join(HOOK_WALL_SECS)
    expired = worker.is_alive()
    out = _wall_expired() if expired else result.get("out", dict(PASS))
    print(json.dumps(out))
    sys.stdout.flush()
    sys.stderr.flush()
    if expired:
        _hard_exit(0)
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-agy-hook-pretool [-h]\nAntigravity PreToolUse hook body; reads hook JSON on stdin, emits a JSON decision")
        raise SystemExit(0)
    sys.exit(main())
