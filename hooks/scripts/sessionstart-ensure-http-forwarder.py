"""SessionStart ensure for the http hook forwarder -- DoE-hosted lifecycle fallback.

WHY THIS EXISTS. `docs/decisions/DR-http-hook-forwarder-lifecycle.md` assigns the resident
forwarder's (`coordinator/hooks/http_hook_forwarder.py`) start/keep-alive/respawn lifecycle to the
engine plane's warm supervisor, via an `ensure_*` seam that DR names as NOT YET PUBLISHED
(`grep -rn "front.door\\|forwarder" coordinator_core/warm/` returns nothing as of that DR). This
module is the documented fallback the DR authorizes taking when that seam has slipped: a DoE-hosted
`SessionStart` command hook that ensures the forwarder is up using nothing but the forwarder's own
exclusive-bind arbitration, without waiting on a seam that does not exist yet on this machine.

ENSURE, NOT SPAWN-BLINDLY. The forwarder is a machine-wide resident and `SessionStart` fires once
per session, so the Nth session must find an already-running forwarder rather than racing a second
bind. This module uses the SAME exclusive-bind primitive the forwarder itself binds with
(`http_hook_forwarder.make_server`, `_ExclusiveServer.allow_reuse_address = False` plus
`SO_EXCLUSIVEADDRUSE` on Windows) as the arbiter: it attempts a probe bind on `FIXED_PORT`, and
treats a losing bind ("already bound") as SUCCESS, not failure -- something is already listening
there. It never health-checks the winner; the forwarder's own module docstring is what defines "no
live engine backend reachable" behaviour once a request actually lands, not this hook's job to
duplicate.

ONE INSPECTION, AND IT IS NOT A HEALTH CHECK: IS THE WINNER RUNNING THE CODE ON DISK. A bound port
is the only thing the probe can see, and a forwarder serving SUPERSEDED code holds it exactly as a
current one does. The forwarder is a long-lived resident, so an edit to its module is inert until
that process happens to die -- and nothing makes it die. Measured 2026-08-30: `6b136a38d` fixed a
guard-execution timeout and the box went on denying at the old bound for over an hour beneath a
process bound 20 h earlier, 259/18357 dials (1.41%) never forwarded and the rate climbing, with the
fix committed the whole time. So this script compares the fingerprint the running process stamped
into the dial-count file at ITS bind against the module on disk now, and on a mismatch retires the
stale process and spawns a successor. That is a code-identity question with a recorded answer, not
a health question with a probed one -- it stays out of the "does the backend work" business the
paragraph above refuses. This has a narrow race (the probe socket closes before the
winner spawns and rebinds), accepted deliberately: the machine-wide binder election
(`DR-http-hook-forwarder-fixed-port.md` Decision 4) is the portable floor this hardening layer sits
on top of, not a substitute for it -- exactly the same relationship the forwarder's own exclusivity
bears to that same election, per its module docstring's negative-spec.

NEVER WAIT. `warm.client`'s "NO CLIENT EVER WAITS FOR A SERVER TO BOOT" doctrine binds here for the
identical reason the DR states it does: `SessionStart` sits on the session's critical path, and a
spawn that blocks boot is a worse regression than the 271ms this whole plan exists to remove. The
detached spawn below returns as soon as the child process is launched -- it does not poll, does not
wait for the child's own bind to succeed, and does not retry.

DISCLOSE LOUDLY, NEVER SILENTLY, ON FAILURE. Explicitly NOT `supervisor.ensure_listener`'s silent
fail-open posture -- that call has a caller-side cold path to fall back to; this owner does not (DR,
"Cold-start honesty"). Every failure path here writes BOTH a stderr line AND a NESTED
`hookSpecificOutput.additionalContext` string (never a top-level `additionalContext`, which the
harness silently drops) so the operator and the session transcript both see it, every time, not
rate-limited.

EXIT 0 ALWAYS. This hook must never block a session from starting. Every code path -- probe-bind
success, probe-bind loss (already running), spawn failure, or an unexpected exception -- ends in
`sys.exit(0)`.

NOT REGISTERED HERE. `hooks.json` gains no entry from this module; the DR's own "Consequences"
section defers that wiring to a later chunk, landed together with this script, not ahead of it.

NEGATIVE SPEC. This module does not call any engine-plane `ensure_*` seam -- none is published
yet (DR, "What this DR does not settle"). It does not import `coordinator_core` and does not resolve
an engine root: starting the forwarder body needs only the sibling file
`coordinator/hooks/http_hook_forwarder.py` on this same checkout, not the engine. It does not
health-check, poll, or retry the forwarder once spawned or once found already bound: the single
inspection it makes of a running winner is the code-identity comparison above, which reads a file
the forwarder already writes and never dials it. It does not kill a process it has not confirmed to
be a forwarder, and it treats every "cannot tell" -- absent record, absent fingerprint, unreadable
process table -- as DO NOT RESTART, because a wrongly-retired forwarder is a box-wide silent
guard-disarm and a wrongly-kept one is the status quo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _win_portability import no_console_creationflags  # noqa: E402

# Sibling module this script starts -- see module docstring, "not registered here" / negative-spec.
_FORWARDER_MODULE_PATH = Path(__file__).resolve().parents[1] / "http_hook_forwarder.py"

#: Mirrors `http_hook_forwarder.FIXED_PORT` by value, not by import -- this script must not import
#: the forwarder module itself (it only launches it as a detached child process; importing it here
#: would additionally bind/serve inside THIS short-lived hook process, which is not this module's
#: job). Kept as a literal with this comment as the single cross-reference, matching the forwarder
#: module's own "exactly one place in the tree commits the number" framing for its own copy.
_FIXED_PORT = 47623

_ADDR_IN_USE_ERRNOS = frozenset(
    e
    for e in (
        getattr(__import__("errno"), "EADDRINUSE", None),
        10048,  # WSAEADDRINUSE, Windows
    )
    if e is not None
)


def _probe_bind_wins(port: int = _FIXED_PORT) -> Optional[bool]:
    """Attempt an exclusive probe bind on `port`, immediately releasing it on success.

    Returns `True` when this call won the bind (nothing else is listening there right now --
    caller should spawn the forwarder), `False` when the bind lost to an existing listener
    (treated as success per module docstring -- caller should do nothing), or `None` when the
    attempt raised something that is neither of those (caller should disclose a failure).

    Never raises.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        exclusive_flag = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive_flag is not None:
            try:
                sock.setsockopt(socket.SOL_SOCKET, exclusive_flag, 1)
            except OSError:
                pass
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            if getattr(exc, "errno", None) in _ADDR_IN_USE_ERRNOS:
                return False
            return None
        return True
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _dial_count_path() -> Path:
    """Where the running forwarder stamped its bind record.

    Mirrors `http_hook_forwarder.dial_count_path` BY VALUE, for the same reason `_FIXED_PORT`
    does: this script must not import the forwarder module, which would bind and serve inside a
    short-lived hook process. The two ladders must not drift -- a mismatch here reads as "no
    record", which is the do-not-restart case, so drift fails toward leaving a stale forwarder up
    rather than toward killing a healthy one.
    """
    override = os.environ.get("COORDINATOR_FORWARDER_DIAL_COUNT_PATH")
    if override and override.strip():
        return Path(override.strip())
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".claude" / "http-hook-forwarder-dial-count.json"


def _module_fingerprint_on_disk() -> Optional[str]:
    """Fingerprint of the forwarder module as it exists on disk RIGHT NOW.

    Mirrors `http_hook_forwarder.module_fingerprint`'s algorithm by value (sha256 of the file
    bytes, first 16 hex) for the same no-import reason as the two above. Content, never mtime: a
    checkout or a branch switch rewrites mtime without changing a byte, and each spurious mismatch
    costs a real forwarder restart on a box carrying dozens of live sessions.
    """
    try:
        return hashlib.sha256(_FORWARDER_MODULE_PATH.read_bytes()).hexdigest()[:16]
    except Exception:
        return None


def _running_forwarder_record() -> Optional[dict]:
    """The bind record the resident forwarder wrote, or `None` if it cannot be read or parsed."""
    try:
        with _dial_count_path().open("r", encoding="utf-8") as handle:
            record = json.load(handle)
    except Exception:
        return None
    return record if isinstance(record, dict) else None


def _pid_is_a_forwarder(pid: int) -> Optional[bool]:
    """Whether `pid` is actually a forwarder process, asked of the OS process table.

    WHY THIS GATE EXISTS AT ALL. The pid comes off a file that a long-dead process may have
    written, and pids are recycled. Killing on the record alone means that in the one scenario
    where the record is stale -- the forwarder died and something ELSE took the fixed port -- this
    script terminates whatever unrelated program inherited the number. The kill path is rare (only
    a fingerprint mismatch reaches it), so it can afford one subprocess to be sure.

    RESIDUAL, NOT CLOSED BY THIS CHECK. The confirmation and the `os.kill` that follows it are not
    atomic: a pid confirmed here can exit and be recycled before the signal lands. The window is one
    Python call wide and this check shrinks the hazard by orders of magnitude, but it does not
    eliminate it -- so this is a reduction, not a guarantee, and a future edit must not lean on it
    as though the pid were pinned.

    Returns `True`/`False` when the process table answered, and `None` when it could not be read
    -- which the caller treats as do-not-kill, never as `True`.
    """
    if os.name == "nt":
        argv = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            '(Get-CimInstance Win32_Process -Filter "ProcessId={0}").CommandLine'.format(int(pid)),
        ]
    else:
        argv = ["ps", "-p", str(int(pid)), "-o", "args="]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
            # A SessionStart hook runs headless; without this the query flashes a console window
            # on every boot that reaches it. The helper is a no-op mapping on POSIX, so one splat
            # covers both dialects above.
            **no_console_creationflags(),
        )
    except Exception:
        return None
    if completed.returncode != 0 and not (completed.stdout or "").strip():
        # No such process, or the query failed outright. Either way there is nothing to retire,
        # and "nothing to retire" is not the same claim as "this is a forwarder".
        return False
    return bool(_FORWARDER_ARGV_RE.search(completed.stdout or ""))


#: What a command line has to look like for its process to be a forwarder worth SIGTERMing.
#:
#: A BARE SUBSTRING IS NOT THIS TEST, and the difference is a wrongly-killed process. Matching
#: `http_hook_forwarder` anywhere in the command line also matches every process that merely NAMES
#: the module: `pytest coordinator/tests/test_http_hook_forwarder_staleness.py`, an editor holding
#: the file open, a `grep` over the hooks tree. This requires the module's own filename as a whole
#: path component -- so `test_http_hook_forwarder_staleness.py` and `http_hook_forwarder_decoy.py`
#: both correctly fail to match, while `python <repo-root>\hooks\http_hook_forwarder.py` matches.
_FORWARDER_ARGV_RE = re.compile(r"""(?:^|[\s"'/\\])http_hook_forwarder\.py(?:["'\s]|$)""")

#: How long, in total, to wait for a spawned successor to actually take the port before declaring
#: the box forwarderless. Ten polls at 200 ms.
_BIND_CONFIRM_ATTEMPTS = 10
_BIND_CONFIRM_INTERVAL_SECS = 0.2


def _forwarder_is_listening(port: int = _FIXED_PORT) -> bool:
    """Whether ANYTHING is serving the fixed port right now, asked by CONNECTING, never binding.

    WHY NOT `_probe_bind_wins`. That probe answers the same question, and asking it here would be
    a self-inflicted wound: it binds exclusively, so a probe issued while a freshly-spawned
    successor is still racing for the port can WIN it, and the successor -- which treats a bind
    failure as fatal and does not retry -- dies on the spot. The confirmation would cause the
    failure it exists to detect. A connect touches nothing.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _await_successor_bind() -> bool:
    """Block briefly until a successor has actually taken the port. Returns whether one did.

    THE ONE PLACE THIS MODULE IS ALLOWED TO WAIT, and the module docstring's "NEVER WAIT" is not
    weakened by it. That rule is about the ordinary path, where nothing was killed and a spawn that
    has not yet bound costs nobody anything. This path has already terminated a live listener: the
    box is unguarded RIGHT NOW, and returning without confirming trades a bounded ~2 s on a rare
    branch for an unbounded window in which every Bash call on the machine fails open silently.
    Launching is not binding -- `_spawn_forwarder_detached` returns on `Popen`, while the successor
    still has to win `SO_EXCLUSIVEADDRUSE` against the socket the process we just killed has not
    finished tearing down, and it treats losing that race as fatal without retrying.
    """
    for _ in range(_BIND_CONFIRM_ATTEMPTS):
        if _forwarder_is_listening():
            return True
        time.sleep(_BIND_CONFIRM_INTERVAL_SECS)
    return _forwarder_is_listening()


def _retire_stale_forwarder(pid: int) -> bool:
    """Terminate a confirmed stale forwarder so the caller can spawn a current one.

    THE WINDOW THIS OPENS IS THE WHOLE COST, AND IT IS THE PERMISSIVE DIRECTION. Between this kill
    and the successor's bind there is no forwarder, and a dead forwarder is a connection refusal,
    which the harness FAILS OPEN on -- silently, on `PreToolUse`. Every Bash call that fires on the
    box in that window runs unguarded. Measured by hand on 2026-08-30 at sub-second on a box with
    ~41 live sessions, which is what makes it payable against a defect rate of 1.41% and climbing.
    It is NOT payable speculatively: that is why a fingerprint mismatch, and never the bind probe
    alone, is the only thing that reaches here.
    """
    try:
        os.kill(int(pid), signal.SIGTERM)
        return True
    except Exception:
        return False


def _ensure_current_forwarder() -> None:
    """Handle the already-bound case: retire and replace the winner IF it runs superseded code.

    Every early return is a "cannot tell" and leaves the running forwarder alone -- see this
    module's negative spec for why that asymmetry is deliberate.
    """
    on_disk = _module_fingerprint_on_disk()
    if on_disk is None:
        return
    record = _running_forwarder_record()
    if record is None:
        return
    running = record.get("module_fingerprint")
    if not isinstance(running, str) or not running:
        # A forwarder that predates the fingerprint stamp. It is very likely stale, but "likely"
        # does not buy a kill: nothing here can confirm what code it runs, and that generation's
        # record carries no pid to verify either. It self-heals the first time a stamping forwarder
        # binds.
        return
    if running == on_disk:
        return
    pid = record.get("pid")
    # `isinstance(True, int)` is True in Python, so a record carrying `"pid": true` would otherwise
    # reach `os.kill(1, ...)` -- init on POSIX. Bools and non-positives are rejected explicitly.
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return
    if _pid_is_a_forwarder(pid) is not True:
        _disclose_failure(
            "the resident forwarder runs superseded code (running {0}, on disk {1}) but pid {2} "
            "could not be confirmed to be a forwarder -- left running, restart it by hand".format(
                running, on_disk, pid
            )
        )
        return
    if not _retire_stale_forwarder(pid):
        _disclose_failure(
            "the resident forwarder runs superseded code (running {0}, on disk {1}) and pid {2} "
            "could not be terminated -- left running, restart it by hand".format(
                running, on_disk, pid
            )
        )
        return
    if not _spawn_forwarder_detached():
        _disclose_failure(
            "retired the superseded forwarder at pid {0} but failed to spawn its successor -- THE "
            "BOX HAS NO FORWARDER AND BASH GUARDS ARE FAILING OPEN until one binds".format(pid)
        )
        return
    if _await_successor_bind():
        return
    # The successor launched and did not take the port -- almost always the exclusive-bind race
    # against the socket the retired process had not finished tearing down. One retry, because by
    # now that teardown has had the confirmation window to complete.
    if _spawn_forwarder_detached() and _await_successor_bind():
        return
    _disclose_failure(
        "retired the superseded forwarder at pid {0} and its successor did not take port {1} "
        "(launched, then lost the bind or exited) -- THE BOX HAS NO FORWARDER AND BASH GUARDS ARE "
        "FAILING OPEN until one binds".format(pid, _FIXED_PORT)
    )


def _spawn_forwarder_detached() -> bool:
    """Launch `http_hook_forwarder.py` as a detached child process that outlives this session.

    Returns `True` once the child process has been launched (NOT once it has finished binding --
    see module docstring, "never wait"), `False` on any failure to launch. Never raises.
    """
    if not _FORWARDER_MODULE_PATH.is_file():
        return False

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    detached = getattr(subprocess, "DETACHED_PROCESS", 0)
    creationflags = no_window | detached

    kwargs = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    if os.name == "nt":
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(
            [sys.executable, str(_FORWARDER_MODULE_PATH)],
            **kwargs,
        )
        return True
    except Exception:
        return False


def _disclose_failure(reason: str) -> None:
    """Write the loud-disclosure pair this hook's whole contract turns on: stderr, plus a NESTED
    `hookSpecificOutput.additionalContext` on stdout -- never a top-level `additionalContext`,
    which the harness silently drops (DR, "Disclosure"). Never raises."""
    try:
        sys.stderr.write(f"[sessionstart-ensure-http-forwarder] {reason}\n")
    except Exception:
        pass
    try:
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    f"COORDINATOR HTTP HOOK FORWARDER: {reason} -- the http hook forwarder "
                    "could not be ensured for this session; Bash-guard http-transport calls "
                    "may find no live backend for this session until a future SessionStart "
                    "recovers it."
                ),
            }
        }
        print(json.dumps(payload))
    except Exception:
        pass


def main() -> int:
    try:
        result = _probe_bind_wins()
        if result is False:
            # Already bound -- something is listening on FIXED_PORT. Not health-checked; the one
            # question asked of the winner is whether it runs the module on disk. See module
            # docstring, "one inspection, and it is not a health check".
            _ensure_current_forwarder()
            return 0
        if result is True:
            if not _spawn_forwarder_detached():
                _disclose_failure(
                    "won the probe bind but failed to spawn the forwarder process"
                )
            return 0
        # result is None: the probe bind itself raised something unexpected.
        _disclose_failure(
            "could not determine whether the http hook forwarder is already running "
            "(probe bind failed for a reason other than address-in-use)"
        )
        return 0
    except Exception as exc:  # belt-and-braces: this hook must never crash a session boot.
        _disclose_failure(f"unexpected error ensuring the http hook forwarder: {exc!r}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
