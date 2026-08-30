"""Select and throttle the Group EM's nudge population (roadmap `gem-01`,
baton `gem-14`).

PURPOSE. This is the Group EM send half: given `read_pass.build_candidate_roster`'s
read-only candidate list, it narrows to the peers a nudge may be *offered*
for, throttles the offer so no per-peer-per-tick pattern is reachable, and
emits a single digest. It selects and throttles. **It does not send.** The
send itself is an explicit per-send act performed by the Group EM under
`SKILL.md` § "Send pass (gem-14)", with GATE 1 and GATE 2 declared in prose
for each entry. That split is the design, not an omission -- GATE 2 has no
instrument (see below), so no code can clear it, and a module that sent
anyway would be clearing a gate it cannot evaluate.

PM RULING (`state/roadmap/gem-01/pm-gates.md`, gem-14 row). The auto-messaging
crossing is **ruled IN, with a bar**: an interrupt is justified by its cost to
the *receiver*, not by the sender's convenience or the topic's importance --
"is this worth tapping the busy engineer on the shoulder and saying 'stop what
you're doing and listen to me'". The bar is **per send**. The ruling licenses
the send half to be built; it does not pre-answer the design questions this
module settles.

WHY THIS IS NOT THE STOOD-DOWN WATCHER. `runtime-tripwire-stop-watcher.py`
inferred a STATE ("is this session stalled?") from timing and transcript
shape, fired 681 times in 26 days at ~99.4% wrong, and was stood down by PM
ruling (`coordinator/docs/wiki/runtime-tripwire.md:11-24`); its restore recipe
is three lines (`:20-22`). This module **infers NOTHING**. It reads two
concrete observed records and intersects them:

  1. a `read_pass` verdict, itself sourced from `receiver-state.json` (written
     at the peer's own Stop seam) or a bounded transcript-tail marker; and
  2. an **undischarged obligation** in that peer's own next-move ledger
     (`state/subagent-share/<session-id>/next-move-ledger.jsonl`), opened only
     by a PostToolUse observation of a seam-opening call and discharged only
     by a PostToolUse observation of the matching terminal call
     (`coordinator/hooks/scripts/_next_move_ledger.py`).

No elapsed-time, idle-duration, session-age, or transcript-shape predicate
exists anywhere in this module's trigger path -- the only clock reading here
is the send-log cooldown, which throttles *this session's own past sends* and
never classifies a peer. Grep-asserted by the test suite.

THE NARROWING PREDICATE, AND WHY IT IS THE OBLIGATION LEDGER.
`DR-group-em-roster-excludes-mid-work-peers.md` § "What this ruling does NOT
fix" left this stub one direction-class choice: carry an obligation signal
alongside the carrier, narrow on another predicate, or accept that a human
adjudicates the full list. The roster is not a bounded candidate list --
`receiver-state.json` is written at the Stop seam, so nearly every classifiable
peer reads `PAUSED` (8 of 10 measured). What bounded the population under the
losing Arm B was an obligation predicate that died with Arm B's reader.

This module carries the obligation signal back, from a *different and still-live*
carrier -- the doctrine-plane next-move ledger the surviving watchdog already
writes. Measured on this repo, 2026-08-30: 41 live agents machine-wide, 9 repo
peers, 6 roster candidates, of which **1** carried an undischarged obligation.
124 ledgers exist machine-wide; 3 carry an undischarged record.

The predicate bounds hard, and ledger COVERAGE is what binds -- a second tick
minutes later returned 7 candidates and 0 eligible, 6 of the 7 having no
ledger file at all. `_next_move_ledger` writes one only after a seam in its
static table has fired for that session, and most sessions never trip one.
**An empty digest is the expected steady state, not a failure to report.**
Widening the population is a change to that seam table, never a softening of
`is_send_eligible`.

ABSENCE OF A LEDGER IS NOT ABSENCE OF OBLIGATION. A peer with no ledger file
at all returns `None`, never `0`, and is **not eligible** -- absence of
evidence never becomes a trigger. This is the same rule `read_pass` applies to
an unrecognised transcript tail (AC6): never guessed into a nudgeable state.

NEGATIVE SPEC -- what this module deliberately does NOT do:

- **No send.** Nothing here writes to, messages, or otherwise touches a peer
  session. The only write is this session's own send log (below).
- **No `PAUSED:away` nudge, ever.** `away` is excluded by name, and any reason
  string this module does not recognise is ineligible rather than assumed
  benign. Note the empirical caveat carried from `gem-11`: `away` was not
  observed in the 2026-08-30 measurement window, so the exclusion is
  structural and has not been exercised against live `away` traffic.
- **No shouldn't-be adjudication.** Nothing here judges whether a paused peer
  "should" have kept moving -- that population is unmeasurable by PM ruling.
  An undischarged obligation says the peer resolved a next move and has not
  invoked it; it does not say the peer is stuck, and this module never says so.
- **No GATE 2 instrument.** `peer_roster`'s `status` is never read (it is
  negative-spec'd; measured 1465 s stale, unbounded to 6.9 h), and the
  obligation ledger is deliberately **not** repurposed as a receiver-state
  proxy -- it answers "does this peer owe a move", not "is this message
  cheaper to them now than later". Every digest entry therefore carries
  `gate1`/`gate2` as `None`, and the send procedure requires the Group EM to
  fill both in prose per send.
- **No CPU-delta leg.** The CPU-band separation finding is RETRACTED (adjacent
  bands, 0.01 cpu-s apart); the signal remains an open work item on the
  engine-plane side and is not read here, gated or otherwise.
- **No `Stop` hook registration and no re-derivation of the stood-down
  watcher's restore recipe** (AC6). This module is invoked from a PM-gated
  skill body, never from an unattended hook.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

#: Reader/fallback `reason` strings a nudge may be offered for. Both spell the
#: same condition -- the peer's turn closed -- on the two `read_pass` legs
#: (`turn-ended` from the receiver-state ladder, `tail-turn-duration` from the
#: bounded transcript-tail marker). Enumerated, never pattern-matched.
SEND_ELIGIBLE_REASONS = frozenset({"turn-ended", "tail-turn-duration"})

#: Excluded by name so the exclusion is greppable rather than implied by the
#: allow-list. 17 of 23 paused sessions in the durable 30-row dataset are
#: `away`, and no Director prods an `away` session (roadmap §5.2).
NEVER_SEND_REASONS = frozenset({"away"})

#: Per-peer cooldown: a peer offered in one digest is suppressed from later
#: digests in this session until it elapses. Throttle, not a classifier.
DEFAULT_COOLDOWN_SECONDS = 3600

#: Rate ceiling: the most entries one digest may carry, whatever the roster
#: size. A digest at the ceiling is reported truncated rather than silently
#: cut, so the Group EM knows the population exceeded it.
DEFAULT_MAX_ENTRIES = 5

_SEND_LOG_FILENAME = "group-em-send-log.jsonl"
_LEDGER_FILENAME = "next-move-ledger.jsonl"


def _session_share_dir(repo_root: str, session_id: str) -> str:
    return os.path.join(repo_root, "state", "subagent-share", session_id)


def undischarged_obligations(repo_root: str, session_id: str) -> Optional[int]:
    """Count this peer's open obligations, or `None` when it has no ledger.

    `None` and `0` are deliberately distinct: `None` is "this peer has no
    ledger file at all" (the hook never ran for it, or the session predates
    the ledger), which is absence of evidence and never a trigger. `0` is a
    ledger that exists and says the peer owes nothing.

    Unparseable lines are skipped, not raised -- a malformed ledger degrades
    to a lower count, never to a crash or to an inferred obligation.
    """
    path = os.path.join(_session_share_dir(repo_root, session_id), _LEDGER_FILENAME)
    if not os.path.exists(path):
        return None
    count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get("discharged_at") is None:
                    count += 1
    except OSError:
        return None
    return count


def is_send_eligible(verdict: dict[str, Any], obligations: Optional[int]) -> bool:
    """Both concrete signals must be positive; neither alone is enough.

    Fails closed on every unrecognised shape: a reason string outside
    `SEND_ELIGIBLE_REASONS`, an `away` reason, a non-candidate verdict, a
    missing ledger (`None`), or a ledger with nothing open.
    """
    if not verdict.get("candidate"):
        return False
    reason = verdict.get("reason")
    if reason in NEVER_SEND_REASONS:
        return False
    if reason not in SEND_ELIGIBLE_REASONS:
        return False
    if obligations is None or obligations <= 0:
        return False
    return True


def send_log_path(repo_root: str, caller_session_id: str) -> str:
    """This session's own record of which peers it has already offered.

    Per-session bookkeeping of *this session's actions*, following the
    existing `state/subagent-share/<session-id>/advisory-fire-counts.jsonl`
    convention -- not a peer roster, address, or reachability fact, which
    `SKILL.md` § "No registration ceremony, no persistence" forbids
    persisting. Session-scoped by construction: a new Group EM session starts
    with an empty cooldown, matching the DACI-is-a-frame ruling that the
    Driver role ends with the session.
    """
    return os.path.join(
        _session_share_dir(repo_root, caller_session_id), _SEND_LOG_FILENAME
    )


def read_send_log(repo_root: str, caller_session_id: str) -> list[dict[str, Any]]:
    """Every offer this session has recorded. `[]` when there is no log yet."""
    path = send_log_path(repo_root, caller_session_id)
    if not os.path.exists(path):
        return []
    records: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
    except OSError:
        return []
    return records


def record_offer(
    repo_root: str,
    caller_session_id: str,
    peer_session_id: str,
    now: Optional[float] = None,
) -> None:
    """Append one offer to this session's send log, starting its cooldown."""
    now = time.time() if now is None else now
    path = send_log_path(repo_root, caller_session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(
        {"peer_session_id": peer_session_id, "offered_at": now}, sort_keys=True
    )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _cooldown_remaining(
    records: list[dict[str, Any]],
    peer_session_id: str,
    now: float,
    cooldown_seconds: int,
) -> float:
    """Seconds left on this peer's cooldown; `0.0` when it may be offered.

    A record with a non-numeric or absent `offered_at` is ignored rather than
    treated as "just offered" -- a corrupt log must not silently suppress a
    peer forever.
    """
    remaining = 0.0
    for record in records:
        if record.get("peer_session_id") != peer_session_id:
            continue
        offered_at = record.get("offered_at")
        if not isinstance(offered_at, (int, float)):
            continue
        left = cooldown_seconds - (now - offered_at)
        if left > remaining:
            remaining = left
    return remaining


def build_send_digest(
    repo_root: str,
    roster: list[dict[str, Any]],
    caller_session_id: str,
    now: Optional[float] = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> dict[str, Any]:
    """One digest per invocation -- the batching discipline itself (AC5).

    A digest is the only shape this module emits. There is no per-peer entry
    point and no loop a caller can drive one peer at a time, so the
    per-peer-per-tick firehose §5.3 forbids is unreachable from this API
    rather than merely discouraged by it.

    Every entry carries `gate1`/`gate2` as `None`: the two gates are checked
    per send, in prose, by the Group EM. A digest is a list of peers a nudge
    may be *offered* for, never a list of peers to message.

    `suppressed` records every roster peer that did not make the digest and
    why, so a shrinking population is legible rather than silent.
    """
    now = time.time() if now is None else now
    log = read_send_log(repo_root, caller_session_id)

    entries: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    eligible_count = 0

    for verdict in roster:
        peer_session_id = verdict.get("session_id")
        if not isinstance(peer_session_id, str) or not peer_session_id:
            suppressed.append({"session_id": peer_session_id, "why": "no-session-id"})
            continue

        obligations = undischarged_obligations(repo_root, peer_session_id)
        if not is_send_eligible(verdict, obligations):
            suppressed.append(
                {
                    "session_id": peer_session_id,
                    "why": (
                        "no-ledger"
                        if obligations is None
                        else "no-open-obligation"
                        if obligations <= 0
                        else "reason-not-eligible"
                    ),
                    "reason": verdict.get("reason"),
                    "undischarged_obligations": obligations,
                }
            )
            continue

        eligible_count += 1
        remaining = _cooldown_remaining(log, peer_session_id, now, cooldown_seconds)
        if remaining > 0:
            suppressed.append(
                {
                    "session_id": peer_session_id,
                    "why": "cooldown",
                    "cooldown_remaining_seconds": remaining,
                }
            )
            continue

        entries.append(
            {
                "session_id": peer_session_id,
                "state": verdict.get("state"),
                "reason": verdict.get("reason"),
                "source": verdict.get("source"),
                "undischarged_obligations": obligations,
                "trigger": "paused-turn-ended+undischarged-obligation",
                "gate1": None,
                "gate2": None,
            }
        )

    truncated = len(entries) > max_entries
    if truncated:
        for entry in entries[max_entries:]:
            suppressed.append({"session_id": entry["session_id"], "why": "rate-ceiling"})
        entries = entries[:max_entries]

    return {
        "entries": entries,
        "suppressed": suppressed,
        "truncated": truncated,
        "roster_size": len(roster),
        "eligible_before_throttle": eligible_count,
        "gate_declaration_required": True,
    }
