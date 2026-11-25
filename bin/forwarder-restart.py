#!/usr/bin/env python3
"""forwarder-restart.py -- retire the resident http hook forwarder and respawn it.

The runnable the SessionStart forwarder hook names when it finds a superseded
forwarder it cannot confirm by argv. Resolves the forwarder file and the
running-forwarder record through the hook's own functions, so both agree on
which forwarder is meant.

Usage:
  forwarder-restart.py [--check]

  --check   report the recorded pid, the port owner and the verdict; change nothing.

Only a pid positively identified as the forwarder is retired (argv, or port
owner that answers /health as the forwarder holder).

Exit codes: 0 restarted (or --check), 1 retire/spawn/bind failed, 2 refused
(identity unconfirmed; stop the process holding the port by hand).
"""

from __future__ import annotations

INSTALL_CLASS = False

import argparse
import sys
import time
import types
from pathlib import Path
from typing import Optional

_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

_RELEASE_WAIT_SECS = 3.0
_RELEASE_POLL_SECS = 0.1


def _hook() -> "types.ModuleType":
    from coordinator_core.hooks import sessionstart_ensure_http_forwarder as hook

    return hook


def _recorded_pid(hook) -> Optional[int]:
    record = hook._running_forwarder_record() or {}
    pid = record.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        return pid
    return None


def _wait_port_released(hook) -> bool:
    deadline = time.monotonic() + _RELEASE_WAIT_SECS
    while time.monotonic() < deadline:
        if not hook._forwarder_is_listening():
            return True
        time.sleep(_RELEASE_POLL_SECS)
    return not hook._forwarder_is_listening()


def main(argv: "Optional[list[str]]" = None) -> int:
    parser = argparse.ArgumentParser(prog="forwarder-restart.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report identity, change nothing")
    args = parser.parse_args(argv)

    hook = _hook()
    forwarder_path = hook._forwarder_module_path()
    if not forwarder_path.is_file():
        print("forwarder-restart: no forwarder file resolves at {0}".format(forwarder_path), file=sys.stderr)
        return 1

    recorded = _recorded_pid(hook)
    owner = hook._port_owner_pid()
    confirmed = recorded is not None and hook._pid_is_a_forwarder(recorded) is True
    print(
        "forwarder-restart: recorded pid {0}, port {1} owner {2}, recorded pid confirmed {3}".format(
            recorded, hook._FIXED_PORT, owner, confirmed
        )
    )
    if args.check:
        return 0

    if confirmed:
        target: Optional[int] = recorded
    elif recorded is None and owner is None:
        target = None
    else:
        print(
            "forwarder-restart: refused -- the recorded pid is not confirmed as the forwarder "
            "(port owner {0}); stop the process holding port {1} by hand".format(owner, hook._FIXED_PORT),
            file=sys.stderr,
        )
        return 2

    if target is not None:
        if not hook._retire_stale_forwarder(target):
            print("forwarder-restart: pid {0} could not be terminated".format(target), file=sys.stderr)
            return 1
        if not _wait_port_released(hook):
            print("forwarder-restart: port {0} still bound after retiring pid {1}".format(hook._FIXED_PORT, target), file=sys.stderr)
            return 1

    if not hook._spawn_forwarder_detached(forwarder_path):
        print("forwarder-restart: spawning the forwarder failed -- NO FORWARDER", file=sys.stderr)
        return 1
    if not hook._await_successor_bind():
        print("forwarder-restart: successor did not take port {0} -- NO FORWARDER".format(hook._FIXED_PORT), file=sys.stderr)
        return 1
    print("forwarder-restart: forwarder restarted on port {0}".format(hook._FIXED_PORT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
