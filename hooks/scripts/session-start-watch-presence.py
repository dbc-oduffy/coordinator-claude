"""SessionStart hook: state Group EM presence as a fact, and report the watch.

PURPOSE. `docs/plans/2026-08-31-the-watch-leaves-a-trace.md` § C3. Two
things land in one line of `additionalContext`, both facts, neither a
solicitation:

1. A presence FACT, never a report request -- "a Group EM holds this repo's
   crown and can be reached by name" if the roster names one, phrased so a
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

OWN TOP-LEVEL REGISTRATION, NEVER FOLDED into `sessionstart-dispatch.py`.
That fan-in shares one shared stdout stream, and the measured consequence
(this hook's own sibling `assert-em-role.py`'s unfold rationale, chunk C1 of
`docs/plans/2026-08-29-restore-em-boot-payload-delivery.md`) is a payload
reaching actual session context in 4 of 279 archived sessions -- captured,
then truncated away before becoming context. A presence line nobody reads
is this plan's own failure mode (P1: a healthy watcher and no watcher
produce byte-identical trees) wearing a different hat.

Contract: SessionStart hooks exit 0 unconditionally. Every failure mode
(unreadable stdin, unresolvable `watch_heartbeat` module, an unreachable
live-session registry) degrades to silence on that leg -- never a crash, and
the other leg (if computable) still emits.

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


# Review: overengineering-reviewer -- module resolution hoisted to the
# shared _watch_module.py beside this directory's other _-prefixed modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _watch_module  # noqa: E402

_resolve_watch_module = _watch_module.resolve_watch_module


def render_presence_line(watch_result: dict | None) -> str | None:
    """Render the presence FACT line, never a solicitation.

    Only fires when a holder is actually named on the record -- an
    `absent` heartbeat (nobody has ever entered) has nothing to state a
    fact about, and stating "no Group EM" here would itself be a nudge
    toward nominating one, which this hook never does.

    A holder the registry cannot name gets the session id and NOT the
    promise of a name: "reachable by name" over a bare uuid is a sentence
    that is false exactly when the reader tries to act on it.
    """
    if not watch_result:
        return None
    holder_name = watch_result.get("holder_name")
    holder_session_id = watch_result.get("holder_session_id")
    if not holder_name and not holder_session_id:
        return None
    if holder_name:
        return f"This repo's Group EM crown is held by {holder_name}, reachable by that name."
    return (
        f"This repo's Group EM crown is held by session {holder_session_id}, which the live "
        "registry does not name -- `ListAgents` resolves it if you need to reach them."
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

    watch_line = f"GROUP EM WATCH: {watch_result['verdict']}" if watch_result else None
    # Review: overengineering-reviewer -- format kept inline (watch_result is
    # already read above to feed render_presence_line); _watch_module.render_watch_line
    # is the shared shape used by the CLI and autofire, which re-read via read_watch.
    presence_line = render_presence_line(watch_result)

    lines = [line for line in (presence_line, watch_line) if line]
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
