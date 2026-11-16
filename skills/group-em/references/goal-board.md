---
segment_id: goal-board
class: protected
order: 11
situation: goal-board
---
### Roll call fills the goal board

The goal board lives in the group-em home, resolved by `_gem_home.resolve_home()`, never by a
`machine-local get` of the optional key. Shape and flags: the schema,
`coordinator/schemas/fleet-goal-board.schema.json`.

1. At each roll call, fill one row per goal: owners, `distance` (`{figure, ref}` or `unmeasured`,
   never `0`), `next`, `blocked_on`, and a fresh `last_updated`.
2. Map every EM open task to a goal id or `EXAMPLE-STATS-REPO` in `task_map`.
3. Write through the refresh op once the engine ships it; until then, write to the schema.
   Never hand-edit a board the op owns.
4. Surface drift to the owner at the roll call, or at a cadence between roll calls: a `stale` row,
   a `no-live-owner` goal, an `unmapped-task`.

Tripwire: `A-GOAL-BOARD-ROW-WITH-NO-MEASURED-DISTANCE-READS-UNMEASURED`.
