#!/usr/bin/env python3
"""agy PreToolUse hook: the Klabauter guard's answer, never a command rewrite.

Order: unimatrix-host-guard.py (loaded as a sibling; `--engine-root <path>` selects the engine) answers
first and its answer is returned as is: the hook never rewrites a command. A peer reply (a run_command that is exactly this interpreter and the installed
unimatrix-send.py beside this hook, plain arguments, no shell operator or expansion; mirrors the Codex
unimatrix.rules send rule) answers "allow". A no-verdict answer (guard unrunnable, bad payload, worker
exception, expired wall) is an allow whose reason keeps "guard did not run": an "ask" has no approver in
a subagent conversation and reads as a hook failure (DR-402: irreversible denies stay with the backstop).

A pending CLI leg is served by the PreInvocation spool below. agy fails closed on a non-zero exit,
invalid JSON, or a reply without `decision`, so every path emits one JSON object with `decision`.

`--event PreInvocation` runs the same script as the PreInvocation hook: it drains the advisories the
adapter stashed at PreToolUse (agy documents no `injectSteps` on a PreToolUse answer) and injects them as
`systemMessage` steps; stash format is `coordinator_core/host_hooks/agy_adapter.py :: stash_advisory`.

PreInvocation also drains a pending leg's `<conv>.queue.jsonl` (the leg's spool, claimed by atomic rename
before emit and deleted after) into the same `injectSteps`, each message with its sender's reply command;
a live leg's spool is left to the leg. Every hook invocation appends one `hook <event>` line to `<conv>.log`.

Leg record (STATE/<conversationId>.json, written by the launcher, read here and by the router):
  {"pid": <leg pid>, "conversation": <id>, "endpoint": <leg socket>, "ls_address": "host:port",
   "agy_pid": <agy pid>, "mode": "pending" | "live"}   (mode absent reads as live)
"""
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

HOOK_WALL_SECS = 1.0
_hard_exit = os._exit
HERE = Path(__file__).resolve().parent
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


def decide(payload, agy_pid, engine_root=None, raw=None) -> dict:
    """The guard's answer for `payload`, never a rewrite: deny as is, a peer reply's ask turned allow, no verdict an allow."""
    if not isinstance(payload, dict):
        return dict(PASS)
    guard = run_guard(json.dumps(payload) if raw is None else raw, engine_root)
    decision = guard.get("decision")
    if decision == "deny":
        return guard
    if decision == "ask" and is_peer_reply(payload):
        return {**guard, "decision": "allow"}
    return guard


def engine_root_arg(argv):
    if "--engine-root" in argv:
        i = argv.index("--engine-root")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def advisory_dir() -> Path:
    return settings_home() / "unimatrix" / "agy-advisories"


CLAIM_STALE_SECS = 30
SENDER_RE = re.compile(r"\[from ([A-Za-z0-9_.@-]+) on ")
_CLAIM_SEQ = 0
_CLAIMS = []  # claimed spool files already emitted by this process, unlinked by release_claims() after the reply is written


def log_hook(conv, event, state=None) -> None:
    """One `HH:MM:SS hook <event>` line in the conversation's leg log; never raises."""
    try:
        if isinstance(conv, str) and CONV_RE.match(conv):
            folder = state or state_dir()
            folder.mkdir(parents=True, exist_ok=True)
            with open(folder / f"{conv}.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + f"hook {event}\n")
    except Exception:
        pass


def _leg_pending(conv, state) -> bool:
    try:
        return json.loads((state / f"{conv}.json").read_text(encoding="utf-8")).get("mode") == "pending"
    except (OSError, ValueError, AttributeError):
        return False


def _claim_path(state, conv) -> Path:
    """A claim name no earlier claim in this process shares: time_ns alone repeats within one clock tick on Windows, and a repeat would overwrite a live claim."""
    global _CLAIM_SEQ
    _CLAIM_SEQ += 1
    return state / f"{conv}.queue.claimed.{time.time_ns()}-{os.getpid()}-{_CLAIM_SEQ}.jsonl"


def claim_spool(conv, state=None) -> list:
    """Claimed spool files for `conv`: stale claims left by a crash, plus the spool itself when the leg record reads pending.

    The spool (`<conv>.queue.jsonl`, the leg's own rule and line format) is renamed to a unique
    `<conv>.queue.claimed.<ns>-<pid>.jsonl` before anything is emitted, so a second hook finds nothing to take.
    A live leg owns its spool: it is never claimed here. A claim younger than CLAIM_STALE_SECS belongs to a
    hook still emitting it."""
    state = state or state_dir()
    claimed = []
    try:
        for old in state.glob(f"{conv}.queue.claimed.*.jsonl"):
            try:
                if time.time() - old.stat().st_mtime < CLAIM_STALE_SECS:
                    continue
                mine = _claim_path(state, conv)
                os.replace(old, mine)
                claimed.append(mine)
            except OSError:
                continue
    except OSError:
        pass
    spool = state / f"{conv}.queue.jsonl"
    if not _leg_pending(conv, state) or not spool.exists():
        return claimed
    mine = _claim_path(state, conv)
    try:
        if os.name == "nt":
            with load_sibling("unimatrix-agy-leg").nt_spool_lock(str(spool)):
                os.replace(spool, mine)
                os.close(os.open(spool, os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600))
        else:
            import fcntl
            fd = os.open(spool, os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)  # an enqueue waiting on this lock reopens onto the fresh spool below
                os.replace(spool, mine)
                os.close(os.open(spool, os.O_WRONLY | os.O_CREAT, 0o600))
            finally:
                os.close(fd)
        claimed.append(mine)
    except (OSError, TimeoutError):
        pass
    return claimed


def reply_hint(sender) -> str:
    """The run_command that answers `sender` (the installed unimatrix-send.py, plain arguments)."""
    prefix = [_console_python(), str(SEND_SCRIPT), "--to", sender]
    quoted = subprocess.list2cmdline(prefix) if os.name == "nt" else " ".join(shlex.quote(a) for a in prefix)
    return f"Reply to {sender}: run `{quoted} <your reply words>`"


def spool_steps(conv, state=None) -> list:
    """`injectSteps` entries for a pending leg's queued messages, each naming the sender's reply command; claims are released after the reply is written."""
    steps = []
    for path in claim_spool(conv, state):
        try:
            lines = path.read_bytes().splitlines()
        except OSError:
            continue
        _CLAIMS.append(path)
        for line in lines:
            try:
                text = json.loads(line)["text"]
            except (ValueError, KeyError, TypeError):
                continue
            if not isinstance(text, str) or not text.strip():
                continue
            m = SENDER_RE.search(text)
            if m:
                text = f"{text}\n{reply_hint(m.group(1))}"
            steps.append({"systemMessage": {"systemMessage": text}})
    return steps


def release_claims() -> None:
    """Delete the claimed spool files this process emitted; a crash before this leaves them for the next hook."""
    while _CLAIMS:
        try:
            _CLAIMS.pop().unlink()
        except OSError:
            pass


def pre_invocation_reply(payload) -> dict:
    """`injectSteps` for a pending leg's queued messages, then each distinct stashed advisory for the payload's conversation, all drained; {} when none."""
    conv = payload.get("conversationId") if isinstance(payload, dict) else None
    if not isinstance(conv, str) or not CONV_RE.match(conv):
        return {}
    log_hook(conv, "PreInvocation")
    try:
        queued = spool_steps(conv)
    except Exception:
        queued = []
    reply = _advisory_reply(conv)
    if queued:
        reply = {"injectSteps": queued + reply.get("injectSteps", [])}
    return reply


def _advisory_reply(conv) -> dict:
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
        payload = json.loads(sys.stdin.read())
        if isinstance(payload, dict):
            log_hook(payload.get("conversationId") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID"), event)
        out = _lifecycle_reply(event, payload, engine_root_arg(argv))
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
    release_claims()
    return 0


def _answer(argv, result) -> None:
    """Worker body: the decision into `result["out"]`; any failure is the fail-open allow."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if isinstance(payload, dict):
            log_hook(payload.get("conversationId"), "PreToolUse")
        result["out"] = decide(payload, agy_ancestor_pid(), engine_root_arg(argv), raw)
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
