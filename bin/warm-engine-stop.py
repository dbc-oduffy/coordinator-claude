"""warm-engine-stop.py — the operator hatch that takes down the warm pair
(supervisor, front door, then server) of the clone this file lives in.

Spec backlink: docs/plans/2026-10-25-publish-stops-warm-pair-and-blocks-respawn.md (C3);
originally AC9a of the warm-engine plan
(`docs/plans/2026-08-15-warm-engine-retires-the-per-invocation-cold-start.md`).

COLD-PATH RULE: this script is RUNNABLE, never a slash command. It must
work with no Claude Code session, no coordinator plane, nothing but a plain
interpreter (guard: `coordinator/tests/test_cold_path_remediation_is_runnable.py`):
naked argparse, no imported session/agent surface, every diagnostic a plain string.

INVOCATION BINDS TO THE CLONE THIS FILE LIVES IN. There is no `--engine-root`
flag: `_REPO_ROOT` is this script's own containing clone, so the copy shipped
inside the klabauter clone stops THAT clone's pair:

    python3 <klabauter-clone-root>/coordinator/bin/warm-engine-stop.py

IDENTIFICATION AND MECHANISM live in `coordinator_core.warm.pair_stop.
stop_warm_pair`: the supervisor is stopped first, then the front door, then the server (graceful
ask, then a direct signal), and a final exact-argv command-line sweep under
the engine root decides success.

EXIT CODES: 0 when neither process survives ("stopped", or "nothing to stop"
when no process was found); `_EXIT_COULD_NOT_STOP` (4) otherwise, with every
survivor's pid and role on stderr.

Negative-spec:
  - Never signals a pid that a verified record or the exact command-line match
    did not identify; there is no "kill anything python-ish" fallback.
  - Never claims success while a survivor remains.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent


_BOOTSTRAP_DONE = False


_BOOTSTRAPPED_NAMES = ("pair_stop",)


def _bootstrap_engine() -> None:
    """Put `_REPO_ROOT` on `sys.path` and bind `pair_stop` -- idempotent.

    Trap: runs on first use, never at import, so importing this file does not
    mutate the `sys.path` of a warm server ~50 sessions share.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    from coordinator_core.warm import pair_stop

    _resolved = locals()
    for _name in _BOOTSTRAPPED_NAMES:
        if _name not in globals() and _name in _resolved:
            globals()[_name] = _resolved[_name]

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_EXIT_OK = 0
_EXIT_COULD_NOT_STOP = 4


def main(argv=None) -> int:
    _bootstrap_engine()
    parser = argparse.ArgumentParser(
        description=(
            "Stop the warm supervisor, front door and server for the clone this script "
            "lives in. No arguments: the engine root is this clone."
        )
    )
    parser.parse_args(argv)

    result = pair_stop.stop_warm_pair(_REPO_ROOT)
    if result.ok():
        print("stopped" if result.stopped else "nothing to stop", file=sys.stderr)
        return _EXIT_OK

    print(result.render_survivors(), file=sys.stderr)
    return _EXIT_COULD_NOT_STOP


if __name__ == "__main__":
    sys.exit(main())
