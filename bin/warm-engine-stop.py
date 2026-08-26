"""warm-engine-stop.py — the operator hatch for a wedged-but-listening warm
engine server.

Spec backlink: docs/plans/2026-08-16-one-engine-for-the-whole-box.md § C18,
AC9a of the warm-engine plan (`docs/plans/2026-08-15-warm-engine-retires-
the-per-invocation-cold-start.md`) -- a server that answers the pipe but
will not shut down needs an operator-runnable stop path independent of any
agentic session.

COLD-PATH RULE: this script is RUNNABLE, never a slash command. It must
work with no Claude Code session, no coordinator plane, nothing but a
plain interpreter -- exactly the guard `coordinator/tests/
test_cold_path_remediation_is_runnable.py` exists to enforce for this
class of script (that guard's own `COLD_PATH_MODULES` list is out of this
row's `writes:`, so this script is not enrolled in it here; the shape --
naked argparse, no imported session/agent surface, every diagnostic a
plain string -- is followed regardless, since AC9a's whole point is this
running before/without a session).

INVOCATION BINDS TO THE CLONE THIS FILE LIVES IN. There is no `--engine-
root` flag: `Path(__file__).resolve().parents[2]` is this script's own
containing clone's root, the same computation every other `warm/*` module
keeps as a local copy (`election._default_engine_clone`, `client.
_engine_clone_root`, `skew._default_engine_clone`, `breadcrumb.
_default_engine_clone`). Running the copy of this script SHIPPED INSIDE
the klabauter clone therefore resolves and stops THAT clone's server, with
no argument to get wrong:

    python3 <klabauter-clone-root>/coordinator/bin/warm-engine-stop.py

-- substitute the box's actual `repos.claude_klabauter` resolution (`
machine-local get repos.claude_klabauter`) for `<klabauter-clone-root>`.
This script does not resolve that registry key itself, to keep "which
clone does this stop" a property of "which copy did you run," not of
another config lookup that could disagree with it.

IDENTIFICATION, conservative by construction (this box runs 50-70
concurrent LLM sessions -- module docstring of every other `warm/*`
module names this load). This script NEVER sends a kill signal to a pid
it has not positively identified as this engine's server:

  1. Read `<svc dir>/warm.json` (`coordinator_core.warm.breadcrumb.
     read_breadcrumb`). Absent or corrupt -> nothing to stop, exit
     `_EXIT_NO_BREADCRUMB`, no process touched.
  2. Verify the recorded `pid` is STILL the SAME process via
     `coordinator_core.session.core.stable_pid_alive(pid,
     stored_start_epoch=...)` -- pid PLUS the psutil birth instant, so a
     pid the OS has since recycled for an unrelated process reads dead
     rather than falsely alive. A dead/recycled pid -> nothing to stop,
     exit `_EXIT_STALE_BREADCRUMB`, no process touched.

MECHANISM, preferred order:

  1. ASK. Connects to the breadcrumb's own `pipe` (the same transport
     shape `warm.client._open_pipe` uses: plain `open(pipe, "r+b")`, no
     ctypes) and sends one JSON-RPC frame carrying a deliberately-wrong
     `_engine_token`. This is a considered reuse of ALREADY-WIRED
     machinery, not a new server-side "stop" op: `warm.server._serve_line`
     pops `_engine_token` off every incoming frame and, on a mismatch,
     calls `warm.skew.evict_on_skew` -- which runs respond -> close the
     listener -> `warm.lifecycle.drain_and_exit` (steps 2-4 of C17's own
     ordered shutdown sequence) BEFORE it ever looks at the request's
     `method`. No dedicated `engine.stop` RPC exists yet at C18 (would
     require editing `warm/server.py`, outside this row's `writes:`), so
     this is the only currently-wired path that reaches the graceful
     drain-and-exit sequence remotely. Flagged here, deliberately, as a
     borrowed mechanism a future chunk should replace with a purpose-built
     op -- not hidden as if it were one.
  2. FALL BACK to a direct signal (`psutil.Process(pid).terminate()`,
     escalating to `.kill()` after a bounded wait) ONLY if step 1's
     connection itself fails (no pipe, busy, or no response within the
     wait) -- i.e. the server is not answering its own transport, so
     asking nicely cannot work. The pid signalled is the SAME pid
     `stable_pid_alive` already verified in the identification step above;
     this script does not re-resolve it a second way.

Negative-spec:
  - Does NOT wait for anything at connect time beyond one bounded read
    (mirrors `warm.client.READ_DEADLINE_SECS`'s discipline, not this
    module's own invention) -- an operator running this by hand wants a
    bounded command, not one that can itself wedge.
  - Does NOT touch any pid the breadcrumb did not name and
    `stable_pid_alive` did not verify. No "kill anything listening near
    this pipe name" fallback exists.
  - Does NOT delete the breadcrumb before confirming the target process
    is gone (or the ask succeeded) -- `unlink_breadcrumb` is the last
    step, best-effort, on a success path only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coordinator_core.warm import breadcrumb  # noqa: E402
from coordinator_core.session.core import stable_pid_alive  # noqa: E402

_EXIT_OK = 0
_EXIT_NO_BREADCRUMB = 2
_EXIT_STALE_BREADCRUMB = 3
_EXIT_COULD_NOT_STOP = 4

# Matches `warm.client.READ_DEADLINE_SECS`'s own bound for a single
# request/response round trip -- an operator command should never itself
# hang past a plausible server response window.
_ASK_READ_DEADLINE_SECS = 2.0

# Matches `warm.client.ERROR_PIPE_BUSY` -- kept as a local literal rather
# than importing the private constant from a sibling module for a single
# comparison.
_ERROR_PIPE_BUSY = 231

# Bound on waiting for a `terminate()`'d process to actually exit before
# escalating to `kill()`.
_TERMINATE_GRACE_SECS = 5.0
_TERMINATE_POLL_INTERVAL_SECS = 0.1

# A fixed, obviously-invalid engine-generation token. The real token
# (`warm.skew.compute_client_token`) is a 16-hex-character sha1 prefix;
# this literal cannot collide with one and is never meant to -- it exists
# only to guarantee `warm.skew.ServerVersionState.is_skewed` sees a
# mismatch, per this script's own docstring ("MECHANISM", step 1).
_STOP_REQUEST_TOKEN = "warm-engine-stop-requested-0000"


def _read_line_with_deadline(fh, deadline_secs: float) -> "bytes | None":
    """One bounded `readline()`, run on a daemon thread so a wedged server
    never blocks this process past `deadline_secs` -- the same shape
    `warm.client._PendingRead` uses, kept local rather than imported since
    that class is private to its module."""
    import threading

    result: dict = {}

    def _read() -> None:
        try:
            result["line"] = fh.readline()
        except OSError as exc:
            result["exc"] = exc

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    reader.join(deadline_secs)
    if reader.is_alive():
        return None
    if "exc" in result:
        return None
    return result.get("line")


def _open_pipe(pipe: str):
    """Open the client end of the warm pipe -- isolated as its own
    function (mirroring `warm.client._open_pipe`'s own shape) so tests can
    monkeypatch the transport without a real named pipe."""
    return open(pipe, "r+b")


def _ask_server_to_stop(pipe: str) -> bool:
    """Attempt the graceful ask (docstring "MECHANISM" step 1). Returns
    True iff a connection was made and a response (well-formed or not) was
    received or the write itself succeeded before the connection dropped
    -- i.e. the server was there and reachable, so a direct signal is
    unnecessary. Returns False on any transport failure (no pipe, busy,
    someone else's pipe, or a read-deadline expiry), which is this
    script's signal to fall back to a direct process signal.
    """
    request = {
        "jsonrpc": "2.0",
        "id": "warm-engine-stop",
        "method": "engine.stop_probe",
        "params": {},
        "_engine_token": _STOP_REQUEST_TOKEN,
    }
    payload = json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"

    try:
        fh = _open_pipe(pipe)
    except OSError:
        return False

    try:
        try:
            fh.write(payload)
            fh.flush()
        except OSError:
            return False
        _read_line_with_deadline(fh, _ASK_READ_DEADLINE_SECS)
        # Whether or not a response line arrived, the write succeeding
        # means the server accepted the frame and (per `warm.server.
        # _serve_line`'s fixed order) already ran respond -> close_listener
        # -> drain before this function could observe anything further --
        # a dropped read here is an EXPECTED shape of a server that is now
        # exiting, not a failure to report.
        return True
    finally:
        try:
            fh.close()
        except OSError:
            pass


def _terminate_pid(pid: int, *, psutil_module=None) -> bool:
    """Direct-signal fallback (docstring "MECHANISM" step 2): `terminate()`
    then, if still alive past `_TERMINATE_GRACE_SECS`, `kill()`. Returns
    True iff the process was confirmed gone. Never signals a pid this
    module has not itself resolved via `psutil` here -- the caller already
    verified this exact pid with `stable_pid_alive` before calling this
    function.

    `psutil_module` is an injectable seam for tests -- this function never
    signals a real OS process in this repo's own test suite (per this
    row's own dispatch instructions); production callers leave it `None`
    and get the real `psutil` import.
    """
    psutil = psutil_module
    if psutil is None:
        import psutil

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True

    try:
        proc.terminate()
    except psutil.NoSuchProcess:
        return True
    except psutil.AccessDenied:
        return False

    deadline = time.monotonic() + _TERMINATE_GRACE_SECS
    while time.monotonic() < deadline:
        if not proc.is_running():
            return True
        time.sleep(_TERMINATE_POLL_INTERVAL_SECS)

    try:
        proc.kill()
    except psutil.NoSuchProcess:
        return True
    except psutil.AccessDenied:
        return False

    deadline = time.monotonic() + _TERMINATE_GRACE_SECS
    while time.monotonic() < deadline:
        if not proc.is_running():
            return True
        time.sleep(_TERMINATE_POLL_INTERVAL_SECS)
    return not proc.is_running()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stop the warm engine server for the clone this script lives in. "
            "No arguments: identification comes entirely from this clone's "
            "own <svc dir>/warm.json breadcrumb."
        )
    )
    parser.parse_args(argv)

    record = breadcrumb.read_breadcrumb()
    if record is None:
        print(
            f"No breadcrumb at {breadcrumb.breadcrumb_path()} -- nothing to stop.",
            file=sys.stderr,
        )
        return _EXIT_NO_BREADCRUMB

    pid = record.get("pid")
    pipe = record.get("pipe")
    stored_epoch = record.get("stable_pid_start_epoch")
    if not isinstance(pid, int) or not isinstance(pipe, str):
        print(
            f"Breadcrumb at {breadcrumb.breadcrumb_path()} is malformed -- nothing to stop.",
            file=sys.stderr,
        )
        return _EXIT_NO_BREADCRUMB

    stored_epoch_str = str(stored_epoch) if stored_epoch is not None else ""
    if not stable_pid_alive(pid, stored_start_epoch=stored_epoch_str):
        print(
            f"Breadcrumb pid {pid} is dead or recycled -- nothing to stop. "
            f"Remove the stale breadcrumb at {breadcrumb.breadcrumb_path()} if it persists.",
            file=sys.stderr,
        )
        return _EXIT_STALE_BREADCRUMB

    print(f"Identified warm engine server: pid={pid} pipe={pipe}", file=sys.stderr)

    asked = _ask_server_to_stop(pipe)
    if asked:
        print("Sent graceful-stop request over the warm pipe.", file=sys.stderr)
        breadcrumb.unlink_breadcrumb()
        return _EXIT_OK

    print(
        "Warm pipe did not accept a connection -- falling back to a direct process signal.",
        file=sys.stderr,
    )
    stopped = _terminate_pid(pid)
    if not stopped:
        print(f"Could not confirm pid {pid} stopped.", file=sys.stderr)
        return _EXIT_COULD_NOT_STOP

    print(f"pid {pid} stopped.", file=sys.stderr)
    breadcrumb.unlink_breadcrumb()
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
