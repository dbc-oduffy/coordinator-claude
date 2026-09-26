"""SessionStart hook: state who holds this repo's roles, and report the watch.

PURPOSE. `docs/plans/2026-08-31-the-watch-leaves-a-trace.md` § C3. Three
things land in one line of `additionalContext`, all facts, none a
solicitation:

1. A presence FACT, never a report request -- "a Group EM holds this repo's
   standing and can be reached by name" if the roster names one, phrased so a
   session with no work in flight reads it and moves on rather than being
   asked to reply. The plan's `## What is NOT the problem` explicitly
   declines the broadcast-invitation shape (`Stop` cannot tell "finished
   cleanly" from "stuck", so a solicitation fires wrong most of the time);
   this hook never asks anything.
2. `GROUP EM WATCH: <verdict>` -- the heartbeat's own verdict
   (`absent`/`vacant`/`stale`/`armed`), read via
   `coordinator/skills/group-em/watch_heartbeat.read_watch`, joined against
   the live session registry. REPORTED, never acted on: no auto-nominate,
   no auto-send, no arming, no nudge on `stale` (plan hard constraint 3).
3. The Uhura holder, and the fact that its relayed PM rulings carry the PM's
   authority. Group EM standing was confirmable from first-party context and
   Uhura standing was not, so a fresh session met an unverifiable authority
   claim while the harness's peer-message boilerplate named authority-claiming
   peers as the hazard -- and resolved against the relay, which is to say
   against the PM. `coordinator/bin/uhura-mode.py`'s `who` verb already read
   this record; nothing emitted it. See
   `cross-repo/inbox/2026-09-04-example-cockpit-repo-em-uhura-authority-not-legible-to-a-fresh-session.md`.

OWN TOP-LEVEL REGISTRATION, NEVER FOLDED into `sessionstart-dispatch.py`.
That fan-in shares one shared stdout stream, and the measured consequence
(this hook's own sibling `assert-em-role.py`'s unfold rationale, chunk C1 of
`docs/plans/2026-08-29-restore-em-boot-payload-delivery.md`) is a payload
reaching actual session context in 4 of 279 archived sessions -- captured,
then truncated away before becoming context. A presence line nobody reads
is this plan's own failure mode (P1: a healthy watcher and no watcher
produce byte-identical trees) wearing a different hat.

Contract: SessionStart hooks exit 0 unconditionally. Every failure mode
(unreadable stdin, unresolvable `watch_heartbeat` or `uhura-mode` module, an
unreachable live-session registry, an unreadable holder record) degrades to
silence on that leg -- never a crash, and the other legs (if computable) still
emit.

Repo-root resolution mirrors `group-em-autofire.py`'s convention exactly:
`payload.get("cwd")` with an `os.getcwd()` fallback, passed to `read_watch`.
Not cwd alone -- a hook process's own cwd is not reliably the invoking
session's under concurrency, and the plan's falsifier runs this surface
against disposable fixture roots that only reach it via `cwd`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import _watch_module  # noqa: E402

_resolve_watch_module = _watch_module.resolve_watch_module


def _resolve_uhura_module():
    try:
        import importlib.util

        path = Path(__file__).resolve().parents[2] / "bin" / "uhura-mode.py"
        spec = importlib.util.spec_from_file_location("_uhura_mode", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:  # noqa: BLE001
        return None


def render_uhura_line(record: dict | None) -> str | None:
    """State who holds the PM comms channel, and that the relay is authoritative.

    Both halves are load-bearing and the second is the one that was missing.
    Naming the holder answers WHO; without the authority clause a fresh
    session still reads a relayed PM ruling against the harness's own
    peer-message boilerplate ("a peer cannot grant escalation", "never treat
    a peer message as your user's approval") and our doctrine's "paraphrase
    is not authorization" -- correct rules aimed at undifferentiated peers,
    which resolve against the one peer whose entire function is carrying PM
    authority. A role whose authority cannot be verified gets ignored by
    exactly the sessions being most careful.

    LIVENESS IS NOT CLAIMED, and that is deliberate rather than unfinished.
    This is a third party asking about another session, the case
    `DR-uhura-holder-record-stays-doctrine-plane` identifies as the one the
    record cannot answer today: `session-claim-cli is-session-live` resolves
    off `stable_pid`, which is not unique per session, so joining against it
    would turn a stale record into a ghost the fleet believes in MORE
    confidently. The line therefore names the holder and its entry time and
    says plainly what it does not know -- a named-but-possibly-stale holder
    beats silence, because the reader can ask that session by name instead of
    escalating to the PM.

    No record emits nothing. "No Uhura channel is held" would be a nudge
    toward claiming one, which this hook never does -- the same posture
    `render_presence_line` takes on an `absent` heartbeat.
    """
    if not record:
        return None
    holder = record.get("peer_name") or record.get("session_id")
    if not holder:
        return None
    reach = "" if record.get("peer_name") else " (`ListAgents` names it)"
    return (
        f"Uhura channel: {holder}{reach}. Its relayed PM rulings carry the PM's "
        "authority -- act, no round trip. Unproven live: if silent, treat unheld."
    )


def render_presence_line(watch_result: dict | None) -> str | None:
    if not watch_result:
        return None
    holder_name = watch_result.get("holder_name")
    holder_session_id = watch_result.get("holder_session_id")
    if not holder_name and not holder_session_id:
        return None
    if holder_name:
        return (
            f"Group EM standing is held by {holder_name}, reachable by that name. Its "
            "direction on this repo carries PM-delegated authority -- act, no round trip."
        )
    if watch_result.get("verdict") == _watch_module.vacant_verdict():
        return (
            f"Group EM standing is on record to session {holder_session_id}, which has "
            "ended -- the record names a holder nobody is. Do not go looking."
        )
    return (
        f"Group EM standing is held by session {holder_session_id}, whose registry row "
        "carries no name -- `ListAgents` resolves it."
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001
        raw = ""

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:  # noqa: BLE001
        payload = {}

    cwd = payload.get("cwd")
    repo_root = cwd if isinstance(cwd, str) and cwd else os.getcwd()

    module = _resolve_watch_module()
    watch_result = None
    if module is not None:
        try:
            watch_result = module.read_watch(repo_root)
        except Exception:  # noqa: BLE001
            watch_result = None

    watch_line = _watch_module.render_verdict_line(watch_result)
    presence_line = render_presence_line(watch_result)

    uhura_module = _resolve_uhura_module()
    uhura_record = None
    if uhura_module is not None:
        try:
            uhura_record = uhura_module.read_record(repo_root)
        except Exception:  # noqa: BLE001
            uhura_record = None
    uhura_line = render_uhura_line(uhura_record)

    lines = [line for line in (presence_line, watch_line, uhura_line) if line]
    if not lines:
        return 0

    context = "\n".join(lines)
    try:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
