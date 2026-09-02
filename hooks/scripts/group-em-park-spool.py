"""Stop-event producer for the Group-EM wake spool -- one append, nothing else.

PURPOSE. The Group-EM fleet watch has a stateless wake (`group-em-watch
--once`) that drains a spool. This file is the producer that puts anything in
it. Without it the wake is a drainer nothing fires.

The split is deliberate and cross-plane: the spool's path, record shape, drain
predicate, debounce and compaction belong to the engine plane; the hook event,
this producer, and its registration are the doctrine plane's. Contract agreed
by cross-repo memo -- see
`state/improvement-queue/2026-09-02-the-group-em-park-producer-is-ours-and-waits-on-claude_klabauters-spool.yaml`
for the thread and the sizing it unblocks.

WHY `Stop`, AND WHY IT RIDES `stop-dispatch.py`'s FAN-IN. A peer's park is
observable exactly when the engine's receiver-state ladder writes `PAUSED:*`
for that session -- and the doctrine-side trigger for that write is
`receiver-state-sensor.py`, registered in `stop-dispatch.py`'s `REGISTRY`. So
`Stop` IS the transition instant, and this guard belongs in the same
interpreter, ordered immediately AFTER `receiver_state_sensor` so the verdict
it reports is guaranteed to exist. `SessionEnd` fires once at genuine session
close and would miss every park a still-live session enters; `SubagentStop`
peers are not registry peers at all.

NEGATIVE SPEC -- the whole contract, and every line of it is load-bearing:

- **This file never classifies.** `state` is carried verbatim from the
  ladder's own `verdict` and `reason`. It is not normalized, the `:<reason>`
  tail is not collapsed, and no branch here decides what counts as parked.
  That predicate belongs to the drain, and one copy of it is the point.
- **It never advances the parked map.** The map is
  `state/group-em-watch-parked.json` and belongs to the drain. A producer that
  advanced it would CONSUME the transition -- the crown's next wake would see
  steady state, stay silent, and the finding would die in a process whose
  stdout nobody reads. That failure is silent and makes coverage worse than
  having no wake at all; it is the reason this is a producer/consumer split
  and not a line of config.
- **It only ever appends.** Never reads the spool, never truncates it, never
  rotates it, never `os.replace`s it. Compaction belongs to the drain and is
  the only thing that shortens the file. A torn interleaved append costs one
  skipped record, never the spool, so there is deliberately no locking.
- **Absence of the spool means "nothing spooled yet", never "don't spool".**
  Hence create-on-append rather than a spool-absent no-op branch: compaction
  can legitimately leave the file absent, and reading absence as "not armed"
  would silently drop the next park.
- **No debounce here.** The drain compares `at` against `last_tick_at`; a
  second freshness gate on this side would be a second definition of the same
  thing.

MISS-PATH COST is the standing constraint -- this runs on every turn end of
every session in the repo. The precondition in `stop-dispatch.py` is payload
fields plus two `stat`s; on a fire it is one small read and one line written.
No registry read, no transcript read, no heartbeat read, no spool read.

CONTRACT: stdin Stop JSON; stdout ALWAYS empty; exit 0 on EVERY path. A Stop
is never blocked by this file, and every failure mode -- unresolvable root,
missing reader, unreadable carrier, unwritable spool -- degrades to silence.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

#: The drain owns this filename; it sits beside `state/group-em-watch.json`
#: (`watch_heartbeat.watch_path`) and `state/group-em-watch-parked.json`
#: (`watch.parked_state_path`), which is why `state/` is the anchor and why a
#: repo without that directory has no watch line and is skipped rather than
#: scaffolded.
SPOOL_RELPATH = ("state", "group-em-watch-spool.jsonl")

#: The ladder's bare tag for a parked session. Only this verdict spools.
_PARKED_VERDICT = "PAUSED"

#: Diagnostic only -- names the producing guard so a spool line can be traced
#: back here. The drain never branches on it.
_WRITER = "receiver-state-sensor"


def _git_root() -> str:
    """Overwritten by `stop-dispatch.py`'s shared-context injection.

    The dispatcher rebinds this name to a closure over the root it already
    resolved with its own zero-spawn parent walk, so the standalone body below
    runs only when this file is invoked directly (tests, manual probe). It
    never spawns `git`.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return str(parent)
    return ""


def _load_receiver_state_reader() -> Optional[Any]:
    """Import `lib/receiver_state_reader.py` BY PATH, not by package.

    `read_pass.py` reaches it as a package import, which needs the repo root
    on `sys.path` -- true in a skill process, not guaranteed in a hook one.
    Resolving from `__file__` works under both plugin-root layouts without
    depending on cwd or on any package being importable.
    """
    lib_path = Path(__file__).resolve().parents[2] / "lib" / "receiver_state_reader.py"
    if not lib_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(
        "_group_em_park_spool_rsr", str(lib_path)
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_payload() -> dict:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def spool_path(repo_root: str) -> str:
    return os.path.join(repo_root, *SPOOL_RELPATH)


def build_record(session_id: str, verdict: dict) -> Optional[dict]:
    """The ladder's verdict in, one spool record out -- or None to not spool.

    `state` is the ladder's own two fields joined and otherwise untouched.
    `at` is the record's OWN `stamped_at`, never `now()`: the drain compares
    it against `last_tick_at`, so it must be the instant the ladder decided,
    and it already carries the naive-UTC `%Y-%m-%dT%H:%M:%SZ` shape both
    planes parse.
    """
    if verdict.get("verdict") != _PARKED_VERDICT:
        return None
    stamped_at = verdict.get("stamped_at")
    if not isinstance(stamped_at, str) or not stamped_at:
        return None
    reason = verdict.get("reason")
    state = f"{_PARKED_VERDICT}:{reason}" if reason else _PARKED_VERDICT
    return {
        "session_id": session_id,
        "state": state,
        "at": stamped_at,
        "writer": _WRITER,
    }


def append_record(path: str, record: dict) -> None:
    """One `open(..., "a")`, one `write()` of one line. Create-on-append.

    Mode `"a"` creates the file when absent; there is deliberately no lock, no
    read-modify-write, and no `os.replace`.
    """
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)


def main() -> int:
    payload = _read_payload()

    # A subagent's own stop is not a peer session-state transition.
    if payload.get("agent_id") or payload.get("hook_event_name") == "SubagentStop":
        return 0

    session_id = payload.get("session_id") or ""
    if not session_id:
        return 0

    root = _git_root()
    if not root:
        return 0

    # `state/` must already exist -- a repo without it has no watch line, and
    # this producer scaffolds nothing.
    if not os.path.isdir(os.path.join(root, SPOOL_RELPATH[0])):
        return 0

    try:
        rsr = _load_receiver_state_reader()
        if rsr is None:
            return 0
        record = build_record(session_id, rsr.read_receiver_state(root, session_id))
        if record is None:
            return 0
        append_record(spool_path(root), record)
    except Exception:
        return 0  # every failure degrades to silence; never block a Stop

    return 0


if __name__ == "__main__":
    sys.exit(main())
