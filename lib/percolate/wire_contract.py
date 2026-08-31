"""Single source of truth for the small set of literal string/format
contracts shared between `coordinator/bin/percolate-round.py` (writer) and
`coordinator/bin/publish.py` (reader) — no other dependency, so importing
this module carries no risk of a cycle or a heavy transitive import into
either bin script.

Review: code-reviewer nit — `_INHERITED_LOCK_ROOTS_ENV` was previously
defined byte-for-byte in both modules with only a comment keeping them in
sync; a future edit to one literal without the other would silently drop
back to always-locking (the safe direction) with no test catching the
drift, since each module's tests only referenced its own local copy.
"""
from __future__ import annotations

import os

from coordinator_core import publish_lane
from coordinator_core.locked_write import contended_lock_wait_secs

#: D1 fix — inherited-holder handoff env var. `percolate-round.py` writes
#: `"<its own pid>=<realpath>"` (pathsep-joined for multiple roots);
#: `publish.py::main` reads it, verifying the PID against `os.getppid()`
#: before honouring the skip. See each module's own call site for the
#: full mechanism/rationale.
INHERITED_LOCK_ROOTS_ENV = "PERCOLATE_ROUND_INHERITED_LOCK_ROOTS"

#: A second EM reaching a publish DESTINATION already held by a round used to
#: sleep on the lock and then fail — the wait, not the failure, was the
#: defect (a session asleep for minutes on a box where 50-70 peers are
#: queued). Default posture: deny at once. Set truthy to opt back into the
#: wait, which then resolves through `contended_lock_wait_secs()` — same
#: clamp, same 180s ceiling, no second source of truth for that number.
COORDINATOR_ALLOW_PERCOLATE_QUEUE_ENV = "COORDINATOR_ALLOW_PERCOLATE_QUEUE"

def lock_busy_message(dest: str, exc: Exception) -> str:
    """One refusal line for a contended per-destination lock — the single
    text `percolate-round.py`, `percolate-mirror.py` (via `_round.
    _lock_busy_message`), and `publish.py`'s own inline BUSY branch all
    emit, so a reader (human or agent) sees one refusal shape regardless of
    which CLI reached the lock first (staff-eng finding 0).

    Lifted verbatim from `percolate-round.py::_lock_busy_message` (B6,
    pointer-only, already correct — not re-authored here).

    Register (docs/wiki/guard-messaging.md § B6): a percolate refusal's
    audience is not positively resolvable at emission — it may reach a
    dispatched subagent as readily as a human operator's shell — and B6's
    unresolved-audience rule degrades to SILENCE about the bypass mechanism,
    never to emitting it. POINTER-ONLY: states one fact once (the dest is
    held by a live round, naming the holder — `exc` already carries the
    pid/label/acquire-time `held_lock`'s `LockTimeout` reads off the lock
    sidecar), the terse alternative (leave it, the next round against this
    dest carries the commit), then a pointer at the mechanism page.

    Negative-spec: does NOT name the override env var, its value shape, or
    any command to run with it, does NOT say "an override exists" in any
    form, and does NOT carry a re-run/retry imperative of any kind (the
    mechanical proxy for the DR-344 respawn-risk finding — a session that
    read "Re-run" here retried harder against a queue that was never going
    to clear faster for the pressure; 17 refused attempts across two loops
    in one observed session). This text no longer asserts a "waited Ns"
    claim of its own — `exc`'s own "within {timeout}s" already reflects the
    actual timeout this acquisition used (0s on the default deny path,
    the real wait when the caller opted into the queue), so nothing here can
    go stale relative to which path fired.
    """
    return (
        f"dest '{dest}' is held by another round ({exc}). Leave it — the "
        "next round against this dest carries the commit. See "
        "docs/reference/percolate-lock-contention.md."
    )


def publish_contention_wait_secs() -> float:
    """Resolve the wait a percolate/publish DESTINATION acquisition hands to
    `held_lock`.

    Returns ``0.0`` (deny at once) unless `COORDINATOR_ALLOW_PERCOLATE_QUEUE`
    is truthy, in which case it returns `contended_lock_wait_secs()` verbatim
    — so the queueing path resolves through the existing clamp and the
    existing 180s ceiling, with no second source of truth for that number.

    A 0.0 wait still enters `_acquire_flock`, whose first action is a
    `_plat_try_lock` attempt before any deadline arithmetic — so a 0 wait is
    one try, not zero tries, and an uncontended acquire is unaffected
    (LEG 3 of `docs/plans/2026-08-30-a-second-percolate-round-stops-sleeping.falsifier.py`
    measures it; 1.7-2.9ms across runs, against 2.8ms on the pre-change baseline).

    Truthiness is delegated to `coordinator_core.publish_lane.env_declares_lane`
    itself (fed this env var's own raw value under `PUBLISH_LANE_ENV`'s key,
    via a synthetic one-entry `environ` mapping) rather than a second copy of
    its falsy-string tuple — staff-eng-review finding 5: two in-tree copies
    of one truthiness convention drift the first time either one changes.
    An unset key needs no branch of its own: `env_declares_lane` reads an
    empty value as falsy, so absent and explicitly-off resolve identically.
    """
    raw = os.environ.get(COORDINATOR_ALLOW_PERCOLATE_QUEUE_ENV, "")
    if not publish_lane.env_declares_lane({publish_lane.PUBLISH_LANE_ENV: raw}):
        return 0.0
    return contended_lock_wait_secs()
