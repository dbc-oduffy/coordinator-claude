---
segment_id: watch
class: protected
order: 1
situation: watch-run
---
   The run's completion is the wake. It prints only `PARKED|WAITING|GONE|POLL-ERROR` lines (drop
   nothing: A-TURN-ENDED-IS-THE-WAKE-NOT-NOISE), one per peer entering a parked state (per
   `read_pass.classify_peer`), silent while that peer's cooldown is armed; then exits 0; any
   failure exit also completes it. After acting, read the fleet (`--status`), then relaunch the
   same command. Never wrap it in a `Monitor`; the `--until-event` run never refuses; never
   hand-edit the record.
   **`--group-em-session-id` is passed explicitly, never defaulted** — distinct from
   `--caller-session-id`. `--status`: 0 alive, 1 not running, 2 unknown (never green); `--once`: a single poll.

- Confirm the subprocess started rather than trusting its silence.
- **Arm within the entry lease:** an entry that never arms is a crown with no watch.
- **Verify with a nameable background task id plus `--status`** fresh, `tick_source: cron`,
  `subscribed_peers` above zero (ALIVE alone is not).
- Use `$COORDINATOR_SETTINGS_HOME/bin/group-em-watch` (`.exe` on Windows), never an engine import.

Mechanics: remit § Arming the watch. `notify_when_idle` is main-conversation only, once per peer. The park spool is
`group-em-assistant`'s surface: ask it first; it never nudges (wiki `group-em-entry-teammates.md`).

**Sanctioned, exhaustively: the oracle's verdict, and `last_tick_at` age in
`state/group-em-watch.json`** against the record's `next_expected_by`. Process-table checks and
resource-usage proxies (CPU, memory, I/O) are banned (remit § Liveness). A PM-reported dead
watcher is confirmed by `last_tick_at` age, never the session list.

**You arm nothing for the wake's producer:** `state/group-em-watch-spool.jsonl` gets one record
per park, appended by every session's own `Stop`
(`coordinator/hooks/scripts/group-em-park-spool.py`), retained at least 30 minutes.

**The watch is FOR:** sessions asking permission for EM-autonomous acts they already recommended;
break-class defects handed up as "worth your eye"; a session idling on a peer repo while holding a
repo-agnostic fallback. **Not** finding sessions something to do.
