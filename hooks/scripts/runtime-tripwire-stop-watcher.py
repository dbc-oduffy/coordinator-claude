#!/usr/bin/env python3
"""Runtime Tripwire -- asyncRewake Stop Watcher (L2 backstop) -- naked-Python port.

STOOD DOWN -- THIS MODULE IS NOT REGISTERED AND DOES NOT RUN. It sits in
hooks.json's `retired` roster ("Stood down 2026-07-31 per PM ruling;
reversible, comment-only mention remains in hooks.json"), and the Stop array
carries only a comment naming it. The file and its tests are kept because the
stand-down is reversible, not because anything invokes them: a bug found here
is latent, not live, and fixing one changes no session's behaviour until the
registration is restored. Restore procedure: stop-dispatch.py. Re-registering
is a PM call, not an engineering one.

Ported from the former bash Stop-hook watcher. Self-contained
(no claude-klabauter op exists for this hook as of this port -- grepped
Claude-klabauter/coordinator_core/hooks + ops, no stop-watcher/asyncRewake match).
The doctrine plane owns the full logic directly; there is no thin-stub/engine split here.

Purpose: Registered on the Stop hook event with asyncRewake: true. Fires at
         end-of-turn, launches a DETACHED background process that sleeps until
         the earliest tracked agent's model-specific threshold, then re-checks
         whether the agent cleared. If not, that detached process exits 2
         (asyncRewake signal) to wake Claude with a stderr nudge naming the
         overrunning dispatch.

Spec backlink: docs/plans/2026-06-15-runtime-tripwire-idle-em-layered-fix.md § C2a
Wiki: docs/wiki/runtime-tripwire.md § L2
Bash original: retired by the repo-wide bash-kill campaign; this module is
  now the sole implementation.

Loop-guard invariant: if HOOK_INPUT.stop_hook_active == true, this Stop was
triggered by the asyncRewake wakeup itself -- do NOT re-arm a new watcher
(infinite re-arming loop prevention per the Staff Engineer #6 / AC16).

Lock invariant: PID lock at
  <git COMMON dir>/coordinator-sessions/$SESSION_ID/stop-watcher.pid
  (resolved via `_resolve_git_common_dir`, not `$GIT_ROOT/.git` directly --
  portability fix, see that helper's docstring)
The parent (this invocation) does NOT register any exit/atexit cleanup for the
lock -- the lock must outlive the parent while the detached child sleeps. The
detached child removes the lock in ALL its exit paths (cleared path, wake-fire
path, and the fail-open exception path added in this port). Stale locks are
swept by session-init.py at session start (mirrors the bash's C2d note).

Detached-launch mechanics (the concurrency-sensitive part of this port):
  The bash original backgrounds a subshell with `( ... ) &` from WITHIN the
  same script process; on POSIX that subshell inherits the parent's stdout/
  stderr file descriptors WITHOUT explicit redirection, and continues running
  after the parent's own `exit 0` -- the classic "the pipe hasn't seen EOF
  yet because a descendant still holds the write end open" trick. Python has
  no portable fork() on Windows, so this port instead RESPAWNS ITSELF as a
  brand-new detached process (`sys.executable <this file> --watch ...`),
  explicitly duplicating the parent's own stdout/stderr handles into that
  child (stdout=sys.stdout, stderr=sys.stderr -- Python dup()s these
  automatically regardless of close_fds) so the fd-inheritance trick is
  reproduced as faithfully as a real OS process boundary allows:
    - POSIX: start_new_session=True (setsid-equivalent -- new session, no
      controlling terminal, survives the parent's exit).
    - Windows: creationflags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
      with a best-effort CREATE_BREAKAWAY_FROM_JOB attempt (falls back to
      without it if the current job object forbids breakaway -- CreateProcess
      raises WinError 5 in that case).

      NOT `DETACHED_PROCESS`, which is what this used to pass. Detachment
      there is from the CONSOLE, never from the parent's lifetime -- Windows
      does not reap children when a parent exits, and survival past parent
      exit measures identically under both flags. What DETACHED_PROCESS does
      buy is a child with NO console at all, so a console-subsystem child
      (this script, and every git.exe and hook interpreter beneath it)
      allocates its own conhost -- WITH A VISIBLE WINDOW -- the moment it
      writes anything. That is a console-window storm fired once per session
      Stop. CREATE_NO_WINDOW gives the child its own WINDOWLESS console
      instead: still untied to the parent's console session, minus the
      windows. Job-object teardown is unaffected either way -- breakaway is
      CREATE_BREAKAWAY_FROM_JOB's job, below, and DETACHED_PROCESS never
      mitigated it.

      Never spell it `DETACHED_PROCESS | CREATE_NO_WINDOW`: Win32 documents
      CREATE_NO_WINDOW as IGNORED alongside DETACHED_PROCESS, and that
      combination measures identically to the bare DETACHED_PROCESS form --
      it reads as fixed while behaving as broken.

  KNOWN, NOT-FULLY-CLOSABLE RISK (flagged per the "STOP and report" clause):
  if the harness spawns hook processes inside a Windows Job Object configured
  with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE and does NOT permit breakaway, the
  detached child WILL be killed the moment the harness tears down the parent
  hook process's job -- no user-mode code in this script can prevent that.
  This is a genuine platform-level gap that cannot be verified from inside a
  single hook invocation. It does not, however, make the *observable* fire
  behavior worse than the bash original's already-unconfirmed status: per
  state/runtime-tripwire-fire-log.tsv (checked at port time, 2026-07-15),
  every recorded fire to date is `fire_type=agent-side` (L1 em-check); there
  is NOT ONE `fire_type=stop-watcher` row, meaning the L2 asyncRewake wake
  path has never been empirically confirmed to fire even in the existing bash
  version. This port carries the identical unconfirmed-in-production status
  forward -- it is a faithful-risk port, not a regression. All the
  synchronous, disk-observable invariants (loop guard, single-instance PID
  lock, dispatch-file scan, threshold computation, wake-condition recheck,
  lock cleanup) are fully verifiable and ARE verified below; only the final
  "does exit 2 from a truly detached process reach the harness's asyncRewake
  monitor on Windows" step is inherently unverifiable from user-mode code and
  is called out explicitly here rather than silently assumed to work.

PID-lock liveness (Windows-safe, NOT raw kill -0): the lock's PID is a real,
long-lived OS PID (the detached watcher's own PID, analogous to bash's `$!`),
NOT a coordinator session_id -- so this is deliberately NOT routed through
cs_live_session_ids / cs_claim_holder_live (those check SESSION recency via
last_activity in meta.json; the floor rule they anchor,
docs/wiki/... RAW-PID-LIVENESS, exists because a session's stored `pid` field
is $$ of a dead-in-seconds hook subshell -- a DIFFERENT quantity than this
lock's PID, which genuinely is the long-lived sleeper). What IS avoided here
is the naive kill -0 / os.kill(pid, 0) footgun: on Windows, os.kill() has no
real "signal 0" semantics -- passing sig=0 still routes through
TerminateProcess() in CPython's implementation, which can KILL the very
process being merely checked. `_pid_alive()` below uses OpenProcess +
GetExitCodeProcess (read-only query, never sends a signal) on Windows, and
os.kill(pid, 0) with proper ProcessLookupError/PermissionError handling on
POSIX (where signal 0 genuinely is a no-op existence probe).

Portability: no bash/coreutils dependency; runs directly as
`python3 runtime-tripwire-stop-watcher.py` under the harness. Fail-open
throughout -- this hook always exits 0 in its default (Stop-event) invocation
mode; only the internal `--watch` detached child may exit 2 (the asyncRewake
wake signal) or 0 (cleared / fail-open).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _message_envelope import resolve_wiki_citation  # noqa: E402
except Exception:
    # A deployment missing its `_message_envelope.py` sibling must not
    # crash this hook's import; it degrades to the un-resolved
    # repo-relative citation instead (C2, `_message_envelope.py` module
    # docstring).
    def resolve_wiki_citation(text: str) -> str:
        return text

try:
    from _session_hub import session_id_is_real  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _session_hub.py must
    # still fail open to the pre-gate behaviour, not crash on import.
    def session_id_is_real(session_id: object) -> bool:
        return bool(session_id)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Windows CreateProcess flags (no-op values on POSIX; only used when os.name == "nt").
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000


# ---------------------------------------------------------------------------
# Shared thresholds (ported inline from the former bash thresholds lib --
# self-contained per the packaging constraint; no cross-language sourcing).
# ---------------------------------------------------------------------------

def runtime_threshold_minutes(model: str) -> int:
    """Per-model runtime ceiling in integer minutes. Mirrors the former bash
    thresholds lib's runtime_threshold_minutes() exactly, including
    the "unknown/empty model -> Opus default" fail-safe direction (a too-large
    threshold only delays a nudge; a too-small one fires spuriously)."""
    m = model or ""
    opus_default = int(os.environ.get("RUNTIME_TRIPWIRE_OPUS_MIN", "25"))
    sonnet_default = int(os.environ.get("RUNTIME_TRIPWIRE_SONNET_MIN", "12"))
    haiku_default = int(os.environ.get("RUNTIME_TRIPWIRE_HAIKU_MIN", "10"))
    # Explicit 1M-context variants matched before bare family arms (mirrors
    # bash's *\[1m\]*|*-1m* case arm ordering -- must precede *sonnet*/*opus*
    # to avoid misclassifying a 1M-context Sonnet as plain Sonnet).
    if "[1m]" in m or "-1m" in m:
        return opus_default
    if "opus" in m:
        return opus_default
    if "sonnet" in m:
        return sonnet_default
    if "haiku" in m:
        return haiku_default
    return opus_default


# ---------------------------------------------------------------------------
# Windows-safe, read-only PID liveness (see module docstring -- NOT kill -0).
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.wintypes.DWORD()
                ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                return bool(ok) and exit_code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, just not owned by us
        except Exception:
            return False
        return True


# ---------------------------------------------------------------------------
# stdin read w/ hang guard (mirrors bash's `timeout 2 cat` Windows Git-Bash guard)
# ---------------------------------------------------------------------------

def _read_stdin(timeout: float = 2.0) -> str:
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


def _git_root() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5.0,
            creationflags=_NO_WINDOW,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return ""


def _resolve_git_common_dir(git_root: str) -> str:
    """Resolve the git COMMON dir for `git_root` without spawning a
    subprocess. Fail-open to "" on any error.

    THIS IS A DUPLICATE of the canonical copy in
    `offer-exploration-tier-dispatch.py` (~line 186) -- hooks are standalone
    scripts and cannot import each other, so the duplication is deliberate.
    Keep every copy in step -- a divergence would mean different hooks
    resolve the same session's bookkeeping directory to different locations
    under a worktree, silently breaking correlation between them.

    In an ordinary clone, `<git_root>/.git` IS the common dir (a directory).
    In a worktree, `<git_root>/.git` is a FILE containing a single
    `gitdir: <path>` line pointing at the worktree's own private git dir
    (`<path>` may be relative to `git_root`); that private git dir in turn
    contains a `commondir` file naming the actual shared common dir (again
    possibly relative -- this time to the private git dir itself). Blindly
    joining `git_root + ".git"` (this file's shape before this fix) silently
    resolves to a location that doesn't exist as a directory under a
    worktree -- the PID lock, dispatch-tracking file, and completion log
    this hook reads/writes there would silently never persist.
    """
    try:
        dot_git = os.path.join(git_root, ".git")
        if os.path.isdir(dot_git):
            return dot_git
        if os.path.isfile(dot_git):
            with open(dot_git, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
            if not text.startswith("gitdir:"):
                return ""
            gitdir_value = text[len("gitdir:"):].strip()
            git_dir = (
                gitdir_value
                if os.path.isabs(gitdir_value)
                else os.path.normpath(os.path.join(git_root, gitdir_value))
            )
            if not os.path.isdir(git_dir):
                return ""
            commondir_file = os.path.join(git_dir, "commondir")
            if os.path.isfile(commondir_file):
                with open(commondir_file, "r", encoding="utf-8", errors="replace") as fh:
                    common_value = fh.read().strip()
                if not common_value:
                    return git_dir
                return (
                    common_value
                    if os.path.isabs(common_value)
                    else os.path.normpath(os.path.join(git_dir, common_value))
                )
            return git_dir
        return ""
    except Exception:
        return ""


def _agent_completed(completion_log: Path, agent_id: str) -> bool:
    """Mirrors bash: grep -q "\"agentId\":[[:space:]]*\"<id>\"" COMPLETION_LOG."""
    if not completion_log.is_file():
        return False
    try:
        text = completion_log.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    pattern = r'"agentId"\s*:\s*"' + re.escape(agent_id) + r'"'
    return re.search(pattern, text) is not None


def _parse_dispatch_row(line: str) -> Optional[tuple]:
    """Returns (agent_id, model, dispatched_at:int) or None if the row is
    unusable -- mirrors the bash while-read loop's skip conditions (empty
    agentId, non-numeric or zero dispatched_at). Tolerates legacy short rows
    (1-col / 3-col) same as the writer's documented tolerance."""
    fields = line.rstrip("\n").split("\t")
    agent_id = fields[0] if len(fields) > 0 else ""
    model = fields[1] if len(fields) > 1 else ""
    dispatched_at_raw = fields[3] if len(fields) > 3 else ""
    if not agent_id:
        return None
    if not re.fullmatch(r"[0-9]+", dispatched_at_raw or ""):
        return None
    dispatched_at = int(dispatched_at_raw)
    if dispatched_at == 0:
        return None
    return (agent_id, model, dispatched_at)


# ---------------------------------------------------------------------------
# Default (Stop-event) mode
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        return _main_impl()
    except Exception:
        # Fail-open: any unexpected error in the synchronous arming path must
        # never block the Stop event or leave Claude Code waiting on us.
        return 0


def _main_impl() -> int:
    hook_input_raw = _read_stdin(2.0)

    # --- Step 1: stop_hook_active loop-guard (MUST be first check) ---
    stop_hook_active = False
    payload: dict = {}
    try:
        parsed = json.loads(hook_input_raw) if hook_input_raw.strip() else {}
        if isinstance(parsed, dict):
            payload = parsed
            stop_hook_active = bool(payload.get("stop_hook_active", False))
    except Exception:
        m = re.search(r'"stop_hook_active"\s*:\s*(true|false)', hook_input_raw)
        stop_hook_active = bool(m and m.group(1) == "true")

    if stop_hook_active:
        return 0

    # --- Step 2: GIT_ROOT discovery ---
    git_root = _git_root()
    if not git_root:
        return 0

    # --- Step 3: SESSION_ID extraction ---
    session_id = ""
    v = payload.get("session_id")
    if isinstance(v, str) and v:
        session_id = v
    if not session_id:
        m = re.search(r'"session_id"\s*:\s*"([^"]*)"', hook_input_raw)
        if m:
            session_id = m.group(1)
    if not session_id:
        session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not session_id:
        return 0
    # The PID lock, the dispatch file, and every sentinel below live under
    # `<hub>/<session_id>/`. A session id the hub gate will not accept has no
    # lock to take and must not mint a directory trying (see `_session_hub`),
    # so the watcher stands down the same way a live lock-holder makes it
    # stand down -- silent, never launched.
    if not session_id_is_real(session_id):
        return 0

    # --- Step 4: Per-session PID lock ---
    # Rooted at the git COMMON dir (see `_resolve_git_common_dir`'s
    # docstring), never `<git_root>/.git` -- that path is a FILE in a
    # worktree, so the pre-fix join silently never persisted the lock/
    # dispatch-tracking/completion-log paths below. Fail-open: an
    # unresolvable common dir is treated the same as an unresolvable
    # git_root above -- silent pass, never build a path from "".
    common_dir = _resolve_git_common_dir(git_root)
    if not common_dir:
        return 0
    sessions_dir = Path(common_dir) / "coordinator-sessions"
    lock_dir = sessions_dir / session_id
    lock = lock_dir / "stop-watcher.pid"

    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    if lock.is_file():
        try:
            existing_pid_text = lock.read_text(encoding="utf-8", errors="replace").strip()
            existing_pid = int(existing_pid_text) if existing_pid_text else 0
        except Exception:
            existing_pid = 0
        if _pid_alive(existing_pid):
            return 0  # live watcher already running; do not stack
        # stale lock -- overwritten below once the new watcher is launched.

    # --- Step 5: dispatch/completion paths ---
    dispatch_file = sessions_dir / session_id / "dispatched-agents.txt"
    completion_log = sessions_dir / "logs" / "agent-audit.jsonl"

    if not dispatch_file.is_file():
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass
        return 0

    max_track_minutes = int(os.environ.get("RUNTIME_TRIPWIRE_MAX_TRACK_MIN", "90"))
    now = int(time.time())

    # --- Step 6: earliest still-tracked agent ---
    earliest_agent_id = ""
    earliest_model = ""
    earliest_dispatched_at = 0

    try:
        lines = dispatch_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        lines = []

    for line in lines:
        row = _parse_dispatch_row(line)
        if row is None:
            continue
        agent_id, model, dispatched_at = row
        elapsed_min = (now - dispatched_at) // 60
        if elapsed_min >= max_track_minutes:
            continue
        if _agent_completed(completion_log, agent_id):
            continue
        if earliest_dispatched_at == 0 or dispatched_at < earliest_dispatched_at:
            earliest_agent_id = agent_id
            earliest_model = model
            earliest_dispatched_at = dispatched_at

    if not earliest_agent_id:
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass
        return 0

    # --- Step 7: compute SLEEP_SEC ---
    threshold_min = runtime_threshold_minutes(earliest_model)
    threshold_sec = threshold_min * 60
    target_epoch = earliest_dispatched_at + threshold_sec
    sleep_sec = max(0, target_epoch - now)

    # --- Step 8: launch detached watcher; write ITS pid to the lock ---
    watch_argv = [
        sys.executable,
        os.path.abspath(__file__),
        "--watch",
        str(lock),
        str(dispatch_file),
        str(completion_log),
        earliest_agent_id,
        earliest_model,
        str(earliest_dispatched_at),
        str(max_track_minutes),
        str(sleep_sec),
    ]

    child_pid = _spawn_detached(watch_argv)
    if child_pid is not None:
        try:
            lock.write_text(str(child_pid), encoding="utf-8")
        except Exception:
            pass
    # else: launch failed -- fail-open, leave any prior (already-checked-stale)
    # lock content in place rather than risk writing a garbage PID; the next
    # Stop event will re-attempt (stale lock still reaps cleanly next time).

    # --- Parent exits 0 immediately ---
    return 0


def _spawn_detached(argv: list) -> Optional[int]:
    """Launch argv as a detached background process that outlives this parent.
    Explicitly inherits this process's own stdout/stderr handles into the
    child (see module docstring -- the fd-inheritance trick the wake path
    depends on). Returns the child PID, or None on failure (fail-open)."""
    common_kwargs = dict(
        stdin=subprocess.DEVNULL,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    try:
        if os.name == "nt":
            flags = _NO_WINDOW | _CREATE_NEW_PROCESS_GROUP
            try:
                proc = subprocess.Popen(
                    argv,
                    creationflags=flags | _CREATE_BREAKAWAY_FROM_JOB,
                    **common_kwargs,
                )
            except OSError:
                # Current job object forbids breakaway -- best-effort retry
                # without it (see module docstring KNOWN RISK paragraph: the
                # detached child may still die with the parent's job in this
                # branch; nothing further can be done from user-mode code).
                proc = subprocess.Popen(argv, creationflags=flags, **common_kwargs)
        else:
            proc = subprocess.Popen(argv, start_new_session=True, **common_kwargs)
        return proc.pid
    except Exception:
        return None


# ---------------------------------------------------------------------------
# --watch mode: the detached child. Sleeps, rechecks, clears or wakes.
# ---------------------------------------------------------------------------

def _watch_main(args: list) -> int:
    try:
        (
            lock_s,
            dispatch_file_s,
            completion_log_s,
            earliest_agent_id,
            earliest_model,
            earliest_dispatched_at_s,
            max_track_minutes_s,
            sleep_sec_s,
        ) = args
    except ValueError:
        return 0  # malformed invocation -- fail-open, nothing to clean up

    lock = Path(lock_s)
    dispatch_file = Path(dispatch_file_s)
    completion_log = Path(completion_log_s)
    earliest_dispatched_at = int(earliest_dispatched_at_s)
    max_track_minutes = int(max_track_minutes_s)
    sleep_sec = int(sleep_sec_s)

    try:
        if sleep_sec > 0:
            time.sleep(sleep_sec)

        recheck_now = int(time.time())
        still_tracked = False

        if dispatch_file.is_file():
            try:
                lines = dispatch_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                lines = []
            for line in lines:
                row = _parse_dispatch_row(line)
                if row is None:
                    continue
                agent_id, _model, dispatched_at = row
                if agent_id != earliest_agent_id:
                    continue
                recheck_elapsed = (recheck_now - dispatched_at) // 60
                if recheck_elapsed >= max_track_minutes:
                    break  # over-age by wake time -- treat as cleared
                if _agent_completed(completion_log, earliest_agent_id):
                    break  # completed -- still_tracked stays False
                still_tracked = True
                break

        if not still_tracked:
            _rm_lock(lock)
            return 0

        wake_now = int(time.time())
        elapsed_min = (wake_now - earliest_dispatched_at) // 60
        sys.stderr.write(
            "RUNTIME TRIPWIRE (L2 asyncRewake watcher) -- agent past threshold:\n"
        )
        sys.stderr.write(f"  {earliest_agent_id} | {earliest_model} | {elapsed_min} min elapsed\n")
        sys.stderr.write(
            "Agent owns the wrap judgment; you (EM) hold authority. Assess: let it "
            "finish, TaskStop, or plan a successor.\n"
        )
        sys.stderr.flush()

        _rm_lock(lock)
        return 2  # asyncRewake signal
    except Exception:
        # Fail-open even in the detached child: never leave an orphaned lock,
        # never risk a spurious wake on an internal error.
        _rm_lock(lock)
        return 0


def _rm_lock(lock: Path) -> None:
    try:
        lock.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        sys.exit(_watch_main(sys.argv[2:]))
    sys.exit(main())
