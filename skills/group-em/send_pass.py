"""Select and throttle the Group EM's nudge population (roadmap `gem-01`,
baton `gem-14`).

Rationale, measurements, the superseded first shape, and the PM ruling that
licensed this: `docs/decisions/DR-group-em-send-narrows-on-the-obligation-ledger.md`.
Tripwire: `A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`. The rules alone are below.

**It selects and throttles. It does not send.** GATE 1/GATE 2 are declared
per entry, in prose, by the Group EM. GATE 2 has no instrument, so no code can
clear it; a module that sent anyway would clear a gate it cannot evaluate.

**The roster is the population** -- `read_pass` bounds it, a human adjudicates
it. This module adds throttling and the gate, never another filter.

**The obligation ledger ranks; it does not admit.** An undischarged, unfired
record orders the digest most-owed-first. `None` means no ledger exists at all
-- a producer coverage gap, never evidence the peer owes nothing, and never
grounds to exclude. Gating on it was built first and measured inert.

**The `fired` latch is honoured, not just `discharged_at`** -- the ledger
hook's own predicate (`discharged_at is None and not fired`), implemented here
rather than called, held equivalent against the real producer by a wire-path
test. A fired record already reached that peer once; re-presenting it is the
repeat-fire class AC6 forbids.

**Infers NOTHING.** Every input is a record something else concretely
observed. No elapsed-time, idle-duration, session-age, or transcript-shape
predicate exists in the eligibility path -- `send_suppression_reason`, the
admission rule the emission path calls, takes no clock; pinned. The one clock
is the cooldown, throttling this session's own offers, never a peer.

NEGATIVE SPEC -- deliberately absent:

- **No send, no write to any peer's state.** Only this session's own log.
- **No `PAUSED:away` nudge, ever** -- excluded by name and by allow-list, and
  reported as `never-send-reason` ahead of any bookkeeping cause. `away` was
  unobserved in the 2026-08-30 window, so the exclusion is structural and
  untested against live traffic.
- **No shouldn't-be adjudication.** An open obligation says the peer resolved
  a next move and has not invoked it -- not that it is stuck.
- **No GATE 2 instrument.** `peer_roster.status` is never read (negative-
  spec'd; 1465 s stale measured, unbounded to 6.9 h), and the obligation
  ledger is not repurposed as a receiver-state proxy -- it answers a different
  question. Every entry carries `gate1`/`gate2` as `None`.
- **No CPU-delta leg** -- the band-separation finding is RETRACTED.
- **No `Stop` registration**, no re-derivation of the stood-down watcher's
  restore recipe (AC6). Invoked from a PM-gated skill body, never a hook.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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

#: A session id arrives from `claude agents --json` (peers) and the
#: environment (the caller), and is joined straight into a path
#: `_record_offer` will `makedirs`. The sibling reader
#: (`receiver_state_reader.receiver_state_path`) rejects an unsafe component,
#: a bare `.`/`..` the character class alone would pass included; the same
#: guard applies here rather than trusting the producer.
_SAFE_SID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_session_id(session_id: Any) -> bool:
    return (
        isinstance(session_id, str)
        and bool(session_id)
        and session_id not in (".", "..")
        and bool(_SAFE_SID_RE.match(session_id))
    )


def _session_share_dir(repo_root: str, session_id: str) -> str:
    return os.path.join(repo_root, "state", "subagent-share", session_id)


def undischarged_obligations(repo_root: str, session_id: str) -> Optional[int]:
    """Count this peer's open, unfired obligations; `None` if it has no ledger.

    `None` (no ledger file at all) and `0` (a ledger saying nothing is owed)
    are deliberately distinct -- the first is a producer coverage gap.
    Unparseable lines are skipped: a malformed ledger degrades to a lower
    count, never to a crash or an inferred obligation.
    """
    if not _safe_session_id(session_id):
        return None
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
                if not isinstance(record, dict):
                    continue
                if record.get("discharged_at") is None and not record.get("fired"):
                    count += 1
    except OSError:
        return None
    return count


def send_suppression_reason(verdict: dict[str, Any]) -> Optional[str]:
    """Why the send path must not offer this verdict, or `None` to admit it.

    The single admission rule, the one `build_send_digest` itself calls, so the
    pins bind what entries actually have. Doubles as the `suppressed[].why`
    label. Takes no clock and no obligation count -- the ledger ranks, never
    admits. Fails closed on every unrecognised shape.
    """
    if not verdict.get("candidate"):
        return "not-a-candidate"
    reason = verdict.get("reason")
    if reason in NEVER_SEND_REASONS:
        return "never-send-reason"
    if reason not in SEND_ELIGIBLE_REASONS:
        return "reason-not-eligible"
    return None


def send_log_path(repo_root: str, caller_session_id: str) -> str:
    """This session's own record of which peers it has already offered.

    Per-session bookkeeping beside `advisory-fire-counts.jsonl`. Session-
    scoped: a new Group EM starts with an empty cooldown, matching the DACI
    ruling that the Driver role ends with the session.
    """
    return os.path.join(
        _session_share_dir(repo_root, caller_session_id), _SEND_LOG_FILENAME
    )


def offer_key(caller_session_id: str, peer_session_id: str) -> str:
    """The cooldown's key: a salted digest, never the peer's session id.

    A peer session id IS an address here -- its receiver-state path, share
    directory, and transcript path are all built from that string -- so
    storing one would breach `SKILL.md`'s no-persisted-address rule. The
    caller's own id salts it; the log answers only "did I offer this, when".
    """
    return hashlib.sha256(
        (caller_session_id + "|" + peer_session_id).encode("utf-8")
    ).hexdigest()


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


def _record_offer(
    repo_root: str,
    caller_session_id: str,
    peer_session_id: str,
    now: Optional[float] = None,
) -> bool:
    """Append one offer, starting its cooldown. `False` if the write failed.

    Internal: `build_send_digest` calls this per emitted entry, so the cooldown
    arms itself rather than depending on the caller. Failure is reported, never
    raised -- the caller must be able to say so.
    """
    now = time.time() if now is None else now
    if not _safe_session_id(caller_session_id) or not _safe_session_id(peer_session_id):
        return False
    path = send_log_path(repo_root, caller_session_id)
    line = json.dumps(
        {"offer_key": offer_key(caller_session_id, peer_session_id), "offered_at": now},
        sort_keys=True,
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        return False
    return True


def _cooldown_remaining(
    records: list[dict[str, Any]],
    key: str,
    now: float,
    cooldown_seconds: int,
) -> float:
    """Seconds left on this peer's cooldown; `0.0` when it may be offered.

    Degenerate timestamps are neutralised, not trusted: non-numeric ignored,
    future (skew, ms-epoch) ignored, result clamped to the window. A corrupt
    log must not silently suppress a peer forever -- nothing would surface it.
    """
    remaining = 0.0
    for record in records:
        if record.get("offer_key") != key:
            continue
        offered_at = record.get("offered_at")
        if not isinstance(offered_at, (int, float)) or isinstance(offered_at, bool):
            continue
        if offered_at > now:
            continue
        left = min(cooldown_seconds - (now - offered_at), float(cooldown_seconds))
        if left > remaining:
            remaining = left
    return remaining


def _suppressed(session_id, why, reason=None, obligations=None, remaining=None):
    """One `suppressed` row. Every row carries the same keys -- `None` where
    inapplicable -- so a consumer never has to key-check by variant."""
    return {
        "session_id": session_id,
        "why": why,
        "reason": reason,
        "undischarged_obligations": obligations,
        "cooldown_remaining_seconds": remaining,
    }


def build_send_digest(
    repo_root: str,
    roster: list[dict[str, Any]],
    caller_session_id: str,
    now: Optional[float] = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> dict[str, Any]:
    """One digest per invocation -- the batching discipline itself (AC5).

    The only shape this module emits, and the only route to an entry: no
    per-peer entry point exists, so the firehose is unreachable from this API
    rather than discouraged by it. **Emitting an entry IS the offer and arms
    its cooldown here** -- a throttle left to the actor it throttles is not
    one. A cooldown that could not be written is named in `unrecorded` and its
    entry still stands, so the caller learns the throttle is unarmed.

    Entries carry `gate1`/`gate2` as `None`; both are checked per send, in
    prose. `suppressed` says why each held peer was held, verdict reasons
    ahead of bookkeeping ones -- `away` is never filed under a ledger detail.

    Known limitation -- no lock spans the log read and the per-entry appends,
    so this assumes one caller at a time per `caller_session_id`. Violate it
    and two calls both read the pre-write log, both see zero cooldown for the
    same peer, and both offer it. Bounded: the log path is caller-scoped, so
    it cannot cross sessions.
    """
    if max_entries < 1:
        raise ValueError("max_entries must be >= 1; got %r" % (max_entries,))
    now = time.time() if now is None else now
    log = read_send_log(repo_root, caller_session_id)

    eligible: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for verdict in roster:
        raw_session_id = verdict.get("session_id")
        if not isinstance(raw_session_id, str) or not _safe_session_id(raw_session_id):
            suppressed.append(_suppressed(raw_session_id, "unusable-session-id"))
            continue
        peer_session_id: str = raw_session_id

        reason = verdict.get("reason")
        why = send_suppression_reason(verdict)
        if why is not None:
            suppressed.append(_suppressed(peer_session_id, why, reason))
            continue

        # Corroboration, not a gate. `None` is a producer coverage gap, never
        # evidence the peer owes nothing; gating on it emptied the digest on
        # absence (5 of 5 measured) and shipped the feature inert.
        obligations = undischarged_obligations(repo_root, peer_session_id)

        remaining = _cooldown_remaining(
            log, offer_key(caller_session_id, peer_session_id), now, cooldown_seconds
        )
        if remaining > 0:
            suppressed.append(
                _suppressed(
                    peer_session_id, "cooldown", reason, obligations, remaining
                )
            )
            continue

        eligible.append(
            {
                "session_id": peer_session_id,
                "state": verdict.get("state"),
                "reason": reason,
                "source": verdict.get("source"),
                "undischarged_obligations": obligations,
                "trigger": "paused-turn-ended-uncontradicted-by-live-status",
                "gate1": None,
                "gate2": None,
            }
        )

    # Deterministic before the ceiling cuts: most-owed first, then session id.
    # `claude agents --json` order is arbitrary and unstable between ticks, so
    # an unsorted cut makes ceiling survival random between digests.
    eligible.sort(
        key=lambda e: (-(e["undischarged_obligations"] or 0), e["session_id"])
    )

    entries = eligible[:max_entries]
    for entry in eligible[max_entries:]:
        suppressed.append(
            _suppressed(
                entry["session_id"],
                "rate-ceiling",
                entry["reason"],
                entry["undischarged_obligations"],
            )
        )

    unrecorded = [
        entry["session_id"]
        for entry in entries
        if not _record_offer(repo_root, caller_session_id, entry["session_id"], now=now)
    ]

    return {
        "entries": entries,
        "suppressed": suppressed,
        "truncated": len(eligible) > max_entries,
        "roster_size": len(roster),
        "eligible_before_ceiling": len(eligible),
        "unrecorded": unrecorded,
        "gate_declaration_required": True,
    }
