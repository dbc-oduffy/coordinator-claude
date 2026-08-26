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
there, whether or not it is healthy. It never health-checks the winner; the forwarder's own module
docstring is what defines "no live engine backend reachable" behaviour once a request actually
lands, not this hook's job to duplicate. This has a narrow race (the probe socket closes before the
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
health-check, poll, or retry the forwarder once spawned or once found already bound -- see "ensure,
not spawn-blindly" above for why a losing bind is trusted as success without inspection.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional

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
            # Already bound -- something is listening on FIXED_PORT. Trusted as success without
            # inspection; see module docstring, "ensure, not spawn-blindly".
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
