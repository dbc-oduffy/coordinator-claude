#!/usr/bin/env python3
"""agy PreToolUse hook: the Klabauter guard first, then keep a live agy leg for this conversation.

Order: unimatrix-host-guard.py (loaded as a sibling; `--engine-root <path>` selects the engine) answers
first. A guard "deny" is returned unchanged with no rewrite. Guard-authored "allow" and "ask"
answers fall through to the leg bootstrap below; any guard reason and the bootstrap rewrite share the
decision. A peer reply (a run_command that is exactly this interpreter and the installed
unimatrix-send.py beside this hook, plain arguments, no shell operator or expansion; mirrors the Codex
unimatrix.rules send rule) answers "allow". A no-verdict answer (guard unrunnable, bad payload, worker
exception, expired wall) is an allow whose reason keeps "guard did not run": an "ask" has no approver in
a subagent conversation and reads as a hook failure (DR-402: irreversible denies stay with the backstop).

Hooks do not receive agy's language-server address or token, but run_command children do. When no
current leg exists, the hook prefixes the command the agent is about to run with a detached start of
unimatrix-agy-hook-launch.py, which inherits the token. That rewrite answers "ask": the user sees and
approves the exact command. agy fails closed on a non-zero exit, invalid JSON, or a reply without
`decision`, so every path emits one JSON object with `decision`.

`--event PreInvocation` runs the same script as the PreInvocation hook: it drains the advisories the
adapter stashed at PreToolUse (agy documents no `injectSteps` on a PreToolUse answer) and injects them as
`systemMessage` steps; stash format is `coordinator_core/host_hooks/agy_adapter.py :: stash_advisory`.

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
from pathlib import Path

HOOK_WALL_SECS = 1.0
_hard_exit = os._exit
HERE = Path(__file__).resolve().parent
LAUNCH = HERE / "unimatrix-agy-hook-launch.py"
FAIL_OPEN_REASON = "coordinator: guard did not run, allowing"
PASS = {"decision": "allow", "reason": FAIL_OPEN_REASON}
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
    """pid -> (parent pid, lowercase name) or None; Windows snapshot, macOS libproc, else /proc. None reader: no process table here."""
    if os.name == "nt":
        table = _nt_process_table()
        return table.get if table else None
    if sys.platform == "darwin":
        import ctypes
        import ctypes.util
        import struct
        try:
            lib = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib", use_errno=True)
        except OSError:
            return None

        def read(pid):
            buf = ctypes.create_string_buffer(136)
            if lib.proc_pidinfo(ctypes.c_int(pid), ctypes.c_int(3), ctypes.c_uint64(0), buf, ctypes.c_int(136)) != 136:
                return None
            ppid = struct.unpack_from("<I", buf.raw, 16)[0]
            nbuf = ctypes.create_string_buffer(256)
            nlen = lib.proc_name(ctypes.c_int(pid), nbuf, ctypes.c_uint32(256))
            name = nbuf.raw[:nlen].decode("utf-8", "replace").lower() if nlen > 0 else ""
            return (ppid, name) if name else None
        return read
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


def _is_agy_name(name) -> bool:
    """True for the agy CLI exe or its daemon (`agy-*`, `agy_*`, `antigravity*`)."""
    n = str(name).lower()
    return n in AGY_EXE_NAMES or n.startswith(("agy-", "agy_", "antigravity"))


def agy_ancestor_pid(read=None, start=None, max_depth=MAX_ANCESTOR_DEPTH) -> int | None:
    """Pid of the nearest ancestor of `start` (default: this process) whose exe is agy, else None.

    The hook's direct parent is an intermediate launcher that exits with the hook, so getppid() is
    never taken. `read(pid)` returns (parent pid, name) or None; it is the injected process table.
    An ancestor whose exe is the agy CLI (AGY_EXE_NAMES) wins over a nearer daemon; a daemon-named
    ancestor (agy-*, agy_*, antigravity*) is the fallback when no CLI ancestor exists within max_depth.
    No agy ancestor within max_depth, or no table: None, silently; stderr stays empty on every path.
    """
    read = read or _proc_reader()
    pid = os.getpid() if start is None else start
    seen = {pid}
    daemon = None
    for _ in range(max_depth):
        row = read(pid) if read else None
        if not row:
            break
        pid = row[0]
        if not isinstance(pid, int) or pid <= 0 or pid in seen:
            break
        seen.add(pid)
        parent = read(pid)
        if parent and _is_agy_name(parent[1]):
            if str(parent[1]).lower() in AGY_EXE_NAMES:
                return pid
            daemon = daemon or pid
    return daemon


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
    except Exception:
        return None


PRINT_FLAG_RE = re.compile(r"\s(?:-p|--print)(?:[=\s]|$)")


def child_pids(pid) -> list:
    """Direct children of `pid` from one process-table read (Windows snapshot, Linux /proc, macOS one `ps`); [] on failure."""
    if os.name == "nt":
        return [p for p, (ppid, _n) in _nt_process_table().items() if ppid == pid]
    out = []
    if sys.platform == "darwin":
        try:
            table = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, timeout=2,
                                   stdin=subprocess.DEVNULL).stdout
        except Exception:
            return []
        for row in (table or "").splitlines():
            cols = row.split()
            if len(cols) == 2 and cols[0].isdigit() and cols[1].isdigit() and int(cols[1]) == pid:
                out.append(int(cols[0]))
        return out
    try:
        for d in Path("/proc").iterdir():
            if d.name.isdigit():
                try:
                    stat = (d / "stat").read_text(encoding="utf-8", errors="replace")
                    if int(stat[stat.rindex(")") + 2:].split()[1]) == pid:
                        out.append(int(d.name))
                except (OSError, ValueError, IndexError):
                    continue
    except OSError:
        pass
    return out


def _is_print_line(line) -> bool:
    return bool(line and PRINT_FLAG_RE.search(" " + line))


def agy_print_mode(agy_pid, read=None) -> bool:
    """True when the agy process runs headless (`-p`/`--print`). Unknown agy pid or unreadable line: False.

    A hook runs under agy's daemon, whose own argv carries no `-p`: when the pid's line is not a print
    line, its child processes are read too, and any print-mode child makes the answer True (a wrong True
    skips one leg bootstrap; a wrong False rewrites a headless run's command and breaks its permissions.allow match).
    """
    if agy_pid is None:
        return False
    read = read or process_cmdline
    if _is_print_line(read(agy_pid)):
        return True
    return any(_is_print_line(read(c)) for c in child_pids(agy_pid))


def _core_module(subname):
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and os.path.isdir(os.path.join(bin_dir, "_unimatrix")):
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
    import importlib
    return importlib.import_module(f"_unimatrix.{subname}")


def pid_alive(pid):
    """True while `pid` runs (delegated to spawn-free _unimatrix.proc.pid_alive)."""
    return _core_module("proc").pid_alive(pid)


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
    ep = rec.get("endpoint")
    if os.name != "nt" and isinstance(ep, str) and os.path.isabs(ep) and not os.path.exists(ep):
        return False
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


def _ps_quote(arg) -> str:
    """One PowerShell single-quoted literal; an arg with whitespace carries inner double quotes because
    Start-Process joins -ArgumentList items with bare spaces."""
    if not arg or any(c.isspace() for c in arg):
        arg = f'"{arg}"'
    return "'" + arg.replace("'", "''") + "'"


def launch_prefix(conv, agy_pid) -> tuple:
    """(start text, separator) that starts the launcher detached and silent. The start runs inside the
    run_command shell, so the launcher inherits that shell's ANTIGRAVITY_CSRF_TOKEN; the hook process
    itself has none. sh on posix, a hidden Start-Process on Windows (agy runs PowerShell there)."""
    argv = launcher_argv(conv, agy_pid)
    if os.name == "nt":
        rest = ",".join(_ps_quote(a) for a in argv[1:])
        exe = argv[0].replace("'", "''")
        return f"Start-Process -WindowStyle Hidden -FilePath '{exe}' -ArgumentList {rest}", "; "
    return f"(nohup {' '.join(shlex.quote(a) for a in argv)} >/dev/null 2>&1 &)", "; "


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


def run_guard(raw, engine_root) -> dict:
    """The host guard's agy answer for the raw payload text; the fail-open allow when it cannot run."""
    try:
        answer, _state = load_sibling("unimatrix-host-guard").guard("agy", raw, engine_root)
    except Exception:
        return dict(PASS)
    return answer if isinstance(answer, dict) and isinstance(answer.get("decision"), str) else dict(PASS)


def bootstrap_rewrite(payload, agy_pid) -> dict | None:
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
    start, sep = launch_prefix(conv, agy_pid)
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
    decision = guard.get("decision")
    if decision == "deny":
        return guard
    if decision == "ask" and is_peer_reply(payload):
        decision = "allow"
        guard = {**guard, "decision": "allow"}
    reason = guard.get("reason") if isinstance(guard.get("reason"), str) else ""
    fail_open = decision == "allow" and "guard did not run" in reason
    if decision in ("allow", "ask") and not fail_open:
        rewrite = bootstrap_rewrite(payload, agy_pid)
        if rewrite is not None:
            reasons = [r for r in (reason, rewrite["reason"]) if r]
            return {**guard, "decision": decision, "reason": " | ".join(reasons), "overwrite": rewrite["overwrite"]}
    return guard


def engine_root_arg(argv):
    if "--engine-root" in argv:
        i = argv.index("--engine-root")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def advisory_dir() -> Path:
    return settings_home() / "unimatrix" / "agy-advisories"


def pre_invocation_reply(payload) -> dict:
    """`injectSteps` carrying each distinct stashed advisory for the payload's conversation, then drained; {} when none."""
    conv = payload.get("conversationId") if isinstance(payload, dict) else None
    if not isinstance(conv, str) or not CONV_RE.match(conv):
        return {}
    folder = advisory_dir() / conv
    texts = []
    try:
        for path in sorted(folder.glob("*.txt")):
            try:
                text = path.read_text(encoding="utf-8").strip()
                path.unlink()
            except OSError:
                continue
            if text and text not in texts:
                texts.append(text)
    except OSError:
        return {}
    return {"injectSteps": [{"systemMessage": {"systemMessage": t}} for t in texts]} if texts else {}


def _lifecycle_reply(event: str, payload, engine_root=None) -> dict:
    """Adapt an agy PostToolUse/Stop payload onto `codex_lifecycle.handle`, stashing advisories for PreInvocation."""
    if not isinstance(payload, dict):
        return {}
    conv = payload.get("conversationId") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID") or ""
    root = None
    if engine_root:
        cand = Path(engine_root)
        if cand.is_absolute():
            root = cand
    if root is None:
        env_root = os.environ.get("COORDINATOR_ENGINE_ROOT")
        if env_root and Path(env_root).is_absolute():
            root = Path(env_root)
    if root is None or not (root / "coordinator_core").is_dir():
        return {}
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from coordinator_core.host_hooks.agy_adapter import AgyAdapter, stash_advisory
        from coordinator_core.host_hooks.codex_lifecycle import handle

        host_event = AgyAdapter().adapt_event(payload, event=event)
        engine_payload = {
            **dict(host_event.metadata),
            "hook_event_name": event,
            "session_id": host_event.session_id or conv or None,
            "cwd": host_event.cwd or None,
            "tool_name": host_event.tool_name,
            "tool_input": dict(host_event.tool_input),
        }
        if event == "Stop":
            for key in ("last_assistant_message", "lastAssistantMessage", "response", "text"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    engine_payload["last_assistant_message"] = val
                    break
            if payload.get("stop_hook_active") or payload.get("stopHookActive"):
                engine_payload["stop_hook_active"] = True
        verdict = handle(engine_payload, dict(os.environ))
        if not isinstance(verdict, dict) or not verdict:
            return {}
        if event == "Stop" and verdict.get("decision") == "block" and verdict.get("reason"):
            return {"decision": "block", "reason": str(verdict["reason"])}
        nested = verdict.get("hookSpecificOutput") if isinstance(verdict.get("hookSpecificOutput"), dict) else {}
        text = nested.get("additionalContext") or verdict.get("additionalContext") or verdict.get("systemMessage") or ""
        if isinstance(text, str) and text.strip() and isinstance(conv, str) and CONV_RE.match(conv):
            stash_advisory(conv, text.strip())
    except Exception:
        return {}
    return {}


def _lifecycle_main(event: str, argv) -> int:
    try:
        out = _lifecycle_reply(event, json.loads(sys.stdin.read()), engine_root_arg(argv))
    except Exception:
        out = {}
    print(json.dumps(out))
    sys.stdout.flush()
    return 0


def _pre_invocation_main() -> int:
    try:
        out = pre_invocation_reply(json.loads(sys.stdin.read()))
    except Exception:
        out = {}
    print(json.dumps(out))
    sys.stdout.flush()
    return 0


def _answer(argv, result) -> None:
    """Worker body: the decision into `result["out"]`; any failure is the fail-open allow."""
    try:
        raw = sys.stdin.read()
        result["out"] = decide(json.loads(raw), agy_ancestor_pid(), engine_root_arg(argv), raw)
    except Exception:
        result["out"] = dict(PASS)


def _wall_expired() -> dict:
    """The fail-open allow for a hook that outran HOOK_WALL_SECS, after one hook_wall degrade row."""
    try:
        load_sibling("unimatrix-host-guard")._record_degrade("agy", "hook_wall", HOOK_WALL_SECS, None)
    except Exception:
        pass
    return {"decision": "allow",
            "reason": "coordinator: guard did not run, allowing (did not finish within the hook wall; engine cold or unreachable)"}


def main(argv=None):
    """One JSON object with `decision` on stdout and exit 0, whatever stdin or the checks do.

    decide() runs on a daemon thread joined at HOOK_WALL_SECS; a slow or stuck engine answers the
    advisory ask and the process exits hard, so no worker can hold it past agy's hook timeout."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:2] == ["--event", "PreInvocation"]:
        return _pre_invocation_main()
    if len(argv) >= 2 and argv[0] == "--event" and argv[1] in ("PostToolUse", "Stop"):
        return _lifecycle_main(argv[1], argv)
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
