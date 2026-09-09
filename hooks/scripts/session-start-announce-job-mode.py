#!/usr/bin/env python3
"""SessionStart(startup) naked-Python plumbing stub -- announces the resolved
``job_mode`` (``blitz`` / ``cron`` / ``interactive``).

This doctrine-plane repo owns only this thin PLUMBING shim (DR-047
transport-seam carve-out, same shape as `preuse-write-dispatch.py` and
`guard-settings-integrity.py`): resolve the claude-klabauter engine, call its
resolver IN-PROCESS, relay the result. Claude-klabauter owns the resolution LOGIC
(`coordinator_core.session.mode_resolution.resolve_mode`, keyed on
`COORDINATOR_JOB_MODE`, forwarded across the warm door) -- this stub adds no
content logic of its own beyond formatting the two lines below. No bash, no
`python3 -m` subprocess re-spawn -- folded into `sessionstart-dispatch.py`'s
existing fan-in interpreter, so this announcement costs zero NEW `python3`
cold starts fleet-wide (see that dispatcher's own `REGISTRY` for why a new
top-level `hooks.json` registration was rejected -- DR-344's brightline
forbids a permanent extra interpreter start on every session for this).

`sources` = `frozenset({"startup"})` ONLY (see this script's `StartGuard`
registration in `sessionstart-dispatch.py`). `job_mode` is a property of the
environment a human chose to launch the session in -- it cannot change
mid-session, so announcing again on `resume`/`clear`/`compact`/`fork` would
just repeat a fact that has not changed since `startup`.

TWO OUTPUT CHANNELS, AND THE SECOND IS THE POINT.

  1. stdout -- one line naming the resolved mode, readable by the agent
     itself out of its own session context, and stating whether the value
     was explicitly ASSERTED via `COORDINATOR_JOB_MODE` or fell through to
     the conservative anchor.
  2. A durable append to
     `<coordinator-settings-home>/state/job-mode-announce.log` -- one line
     per boot, timestamped, never truncated.

WHY BOTH: in a cloud container, stdout is not persisted. A stdout-only
announcement satisfies "a human reading a log can act on it" only while the
session is alive -- the instant the container exits, that line is gone with
it. The durable line is what a human reads AFTERWARDS, once the session has
ended. But do not overclaim what the durable leg buys: on a genuinely
ephemeral box, `<settings-home>/state/` dies with the container too, exactly
like stdout does -- the durable log only outlives the SESSION, never the
CONTAINER. Anything that must cross the terminal survives only by landing in
a commit; this log is not that, and is not a substitute for it.

Contract:
  stdin   -- SessionStart JSON (session_id, source, ...) -- drained; only
             `session_id` is read, for the durable line only, best-effort.
  stdout  -- exactly one line naming the resolved mode, or NOTHING on any
             failure to resolve/import/call the engine.
  exit 0  -- ALWAYS.

Graceful degradation -- REQUIRED, unconditional: any failure to resolve the
Claude-klabauter engine, import it, or call `resolve_mode` falls through to silent
fail-open (exit 0, no stdout, nothing raised) -- identical philosophy to
`preuse-write-dispatch.py`. A missing sibling engine must never brick
session start. Once a mode value IS in hand, the two output legs are
independent: a failure writing the durable log (unwritable path, missing
permissions, ...) must never cost the stdout leg its already-composed line
-- see the per-leg try/except split in `main()` below.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
        place_engine_root_on_path as _place_engine_root_on_path,
    )
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> "str | None":
        return None

    def _place_engine_root_on_path(root):
        if root and root not in sys.path[:2]:
            sys.path.insert(1 if sys.path else 0, root)
        return root

    def _arm_lazy_ops() -> None:
        return None


#: The durable log's filename, under this settings-home's `state/` subtree
#: (see the state-placement-law wiki's install-baton-rendezvous row for the
#: precedent of machine-shared install substrate living at
#: `<settings-home>/state/...`). Picked to name the artifact class plainly:
#: one line per SessionStart boot that resolved a job mode.
_LOG_FILENAME = "job-mode-announce.log"


def resolve_settings_home() -> Path:
    """Resolve the coordinator-claude settings-home root.

    Precedence: an explicit `COORDINATOR_SETTINGS_HOME` override is used
    AS-IS; otherwise `CLAUDE_HOME` (or `HOME`) joined with the fixed
    `.coordinator-claude-settings` suffix -- bit-for-bit the same precedence
    every sibling hook script in this directory carries its own copy of
    (see `handoff-segment-inject.py` / `pickup-autofire.py` / `mise-
    autofire.py`'s own `resolve_settings_home`) -- each hook script here is
    a self-contained single-file module loaded by path, not a shared
    import, matching this directory's own stated convention.
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


def _append_durable_line(line: str) -> None:
    """Best-effort append -- raises on any failure; `main()` catches it so a
    durable-write failure never costs the stdout leg its own line."""
    log_path = resolve_settings_home() / "state" / _LOG_FILENAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _extract_session_id(raw: str) -> str:
    try:
        payload = json.loads(raw) if raw else {}
        if isinstance(payload, dict):
            sid = payload.get("session_id")
            if isinstance(sid, str) and sid:
                return sid
    except Exception:
        pass
    return "unknown"


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    _place_engine_root_on_path(root)

    # Must precede the first coordinator_core.* import -- see
    # _engine_root.arm_lazy_ops for the eager package-init cost this avoids.
    _arm_lazy_ops()

    try:
        from coordinator_core.session.mode_resolution import (
            COORDINATOR_JOB_MODE,
            JOB_MODE_VALUES,
            resolve_mode,
        )
    except Exception:
        return 0  # engine unimportable -> fail-open

    env = dict(os.environ)
    session_id = _extract_session_id(raw)

    try:
        # session_id is unused by the `job_mode` key today (its
        # `session_pair` is None -- see mode_resolution.py's own
        # `MODE_KEYS["job_mode"]`), but `resolve_mode`'s signature requires
        # one; passing the session's own id (falling back to "") keeps this
        # call honest against a future key that does read it.
        mode = resolve_mode("job_mode", session_id if session_id != "unknown" else "", env=env)
    except Exception:
        return 0  # any engine failure -> fail-open

    # Whether the value was explicitly ASSERTED via COORDINATOR_JOB_MODE, or
    # fell through to the conservative anchor -- read the same public wire
    # name and enum claude-klabauter exports (never re-spelled here; see this
    # module's own docstring and mode_resolution.py's "ONE place the wire
    # name is spelled fleet-wide"). `job_mode` is `environment-wins`, so a
    # raw value inside the declared enum always IS the resolved value;
    # anything else (absent, empty, mis-cased, or otherwise unrecognised)
    # fell through past the environment rung.
    raw_env_value = env.get(COORDINATOR_JOB_MODE)
    if isinstance(raw_env_value, str) and raw_env_value in JOB_MODE_VALUES:
        provenance = f"asserted via {COORDINATOR_JOB_MODE}"
    else:
        provenance = f"{COORDINATOR_JOB_MODE} absent/unrecognised -- conservative anchor"

    stdout_line = f"[job-mode] {mode} ({provenance})"

    try:
        sys.stdout.write(stdout_line + "\n")
    except Exception:
        pass

    # Durable leg is independent of the stdout leg above -- a failure here
    # (unwritable path, permissions, ...) must never retract or suppress
    # the stdout line already written.
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        _append_durable_line(f"{timestamp} session={session_id} job_mode={mode} ({provenance})")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
