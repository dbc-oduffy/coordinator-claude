---
title: "Baton bookkeeping — the engine mechanics pickup does not narrate"
created: 2026-08-14
status: active
spec_backlink: docs/plans/2026-08-14-eager-supersede-archival-and-pickup-slimming.md § C1
---

# Baton Bookkeeping

> **Purpose.** `coordinator/skills/pickup/SKILL.md` narrates only the judgment residue a picking-up
> EM must decide — the archival move, the supersede status flip, claim/drop/repark, and the
> archive-fallback resolution are all engine-computed, and a picking-up EM cannot change their
> outcome. This page is the reference those mechanics were excised to: read it on curiosity, never
> on the auto-fire path. `pickup/SKILL.md` carries a single pointer line to it (AC4).

This is reference prose, not a skill body — worked detail belongs here in a way it does not in
`pickup/SKILL.md`.

---

## The two archivers, and which preconditions belong to which

Two distinct claude-klabauter ops move a handoff's file on disk. Conflating their preconditions is
the specific error this page corrects — the three-condition precondition set below belongs to the
*other* archiver, not `handoff_archive_transition.py`.

**`coordinator_core/ops/handoff_archive_transition.py`** — fires at successor-mint time (`/handoff`,
`mode=supersede`/`stamp_shipped`/`chain`). Its own preconditions, in the order the op evaluates
them:

- **Terminal `deployment_state`** (`claude-klabauter coordinator_core/ops/handoff_archive_transition.py:1676-1677` —
  refuses unless the candidate's `deployment_state` is in `_TERMINAL_DEPLOYMENT_STATES`, a local
  frozenset the op defines and gates on itself — `handoff_archive_transition.py` never imports
  `lifecycle_constants`, and this local set is `{shipped, continued, closed}`, omitting
  `abandoned`, which `HANDOFF_TERMINAL_DEPLOYMENT` below carries).
- **The live-children guard** (`claude-klabauter coordinator_core/ops/handoff_archive_transition.py:1424-1434` —
  unconditional across every mode, tri-state: guard exit 1 = safe, proceed; exit 0 (has live
  children) or exit 2 (indeterminate) = retain, never an error).
- **No claim-holder check at all.** This op does not read who holds the claim — a live
  `claimed_by`/`consumed_by` session does not block either the status flip or the move.

**`claude-klabauter coordinator_core/ops/fleet/archive_terminal_handoffs.py`** (`plan_sweep`/`_scan_terminal`, fronted by `bin/sweep-terminal-handoffs.py` — the general archiver; it subsumed the deleted `sweep-shipped-handoffs.py`, and the session-boot sweep that also fired this class is killed) and **`claude-klabauter coordinator_core/ops/fleet/
archive_shipped_handoffs.py`** (`::216`, the `shipped`-only sweep) are the *stricter* selector the
three-condition set actually describes: terminal `deployment_state`, **childless** (`reverse_membership`
over the DAG index, `archive_handoffs.py:925-937`), and **no live claim holder**
(`cs_claim_holder_live` on the derived claim dir, `archive_handoffs.py:939-969` /
`archive_shipped_handoffs.py:216-239`) — for the `shipped` subclass specifically, also a
git-reachable `shipped_in` SHA (`archive_shipped_handoffs.py:204-214`).

**Name the two-selector distinction explicitly** (`canonical-artifact-shapes.md § Archive-Safe
Predicate`): that page's "childless" gate is the `sweep-terminal-handoffs.py` / `archive_terminal_handoffs.py`
selector above, a *different* selector from the live-children guard on
`handoff_archive_transition.py` this page documents first. The two ops answer different questions —
"is it safe to move at successor-mint" vs. "is it safe for the boot-sweep to reap it later" — and
their precondition sets are not interchangeable. `HANDOFF_TERMINAL_DEPLOYMENT` is defined once, at
`claude-klabauter coordinator_core/lifecycle_constants.py:42` — today `{shipped, abandoned, continued,
closed}`.

---

## Supersession: the unconditional flip, then the gated move

`continued_into` is the forward succession edge (schema
`coordinator/schemas/handoff.schema.json:718-727`), written by `_supersede_continued`
(`claude-klabauter coordinator_core/ops/handoff_archive_transition.py:603`). Two facts about when it
fires are load-bearing and easy to conflate:

- **The status flip is unconditional, ahead of the guard** (`handoff_archive_transition.py:1381-1394`
  calls `_supersede_continued` before the live-children guard is ever evaluated at `:1430-1434`).
  Per the op's own module docstring (`handoff_archive_transition.py:48-61`): as soon as a successor
  baton exists, the predecessor is by definition not in flight — a live claim holder or a live child
  is irrelevant to that fact, and may legitimately still gate the archival *move*, but never the
  status flip.
- **The move stays gated.** `superseded: True, moved: False` is the ordinary outcome pre-spike: the
  flip lands every time, the `git mv` waits on the guard. The eager-supersede spike
  (`docs/research/spike-verdicts/2026-08-14-lift-live-children-guard-on-supersede.md`) proved the
  guard can be lifted on this path without orphaning anything, because the guard's own scan set
  (`handoff_children.py`'s `allowed_roots`, `handoff_children.py:362` and `:696`) already
  spans both `state/handoffs/` and `archive/handoffs/` — a child survives its parent's archival
  move and stays enumerable, claimable, and pickup-resolvable (spike § E2).

**Exception:** a roadmap-baton predecessor (`canonical_kind(...) == "roadmap-baton"`) never reaches
the unconditional flip — refused on `kind` alone, in any state, whether or not a live `blocked_by`
dependent exists today (`handoff_archive_transition.py:1037-1069`, DR-126 § Clarifications C-1). A
`blocked_by`/`stub_id` dependent edge on a roadmap baton is invisible to the archival path, so no
guard on that path can safely auto-supersede it — this is a deliberate, permanent scoping, not a
gap to close.

---

## Claim / drop / repark

- **Claim** happens on pickup — a mutual-exclusion check, not cosmetic staleness; it is what stops
  two concurrent pickups of the same handoff from both proceeding.
- **Drop** (`pickup-assemble drop <path>`) is the clean inverse of claim: the baton returns to open
  and `ready_to_fire`, claim record wiped, as if pickup never happened. It routes to the engine's
  `handoff_transition._unclaim`, defined *only* as the `in_flight`→`ready_to_fire` reset — it
  refuses fail-loud (exit 1, no write) on any other `deployment_state`
  (`shipped`/`continued`/`closed`/`awaiting_gate` are out of scope by design). Claim, ship, then
  reach for `drop`, and the refusal is the contract: the recovery is `/workstream-complete`, never
  "repair what drop half-did."
- **Repark** is the opposite intent from drop: it deliberately leaves the handoff reading as
  claimed, for a later session to continue. Use drop when stepping away for good; repark when
  handing the claim onward.
- **`held_by_self`.** A claim already held by *this* session is not contention — the brief reports
  it via `gates.claim_grant.held_by_self` and `directives[].already_satisfied`. A raw frontmatter
  read (bare `status: claimed` / `claimed_by: <sid>`), taken without a fresh brief, carries no
  self-claim signal — it cannot say whether `<sid>` is you. Take a fresh brief rather than
  hand-comparing `claimed_by`.

---

## The `## Session Ledger` carve-out

Every claimed body is frozen once claimed — no appended session notes, no edited
Progress/Recommended-Next-Steps blocks. One exception: a `## Session Ledger` block takes one
appended row per session. It is an accumulator, not narration — chain LoE sums those rows across the
chain (`session_ledger.aggregate_chain_loe`), so a session that never appends renders the chain as
zero effort. Append at `/workstream-complete` or `/handoff`, in the format the block's own comment
declares, one row, never edited after.

---

## Archive-fallback: a moved baton still resolves from its stale path

A baton absent at its passed live path may already have been swept by a concurrent archival move.
`baton.resolve_swept_in_archive` (`claude-klabauter coordinator_core/ops/resolve_swept_baton.py`,
registered at `_registry_map.py:244`) resolves it by basename `rglob` against the known archive
roots, regardless of which month directory it landed in — a skewed `created:`-vs-filename date
mis-files a record, it never loses it (spike § E1c). The eager-supersede spike exercised this path
directly (§ E2): with a parent force-archived, `pickup-assemble brief` on the parent's stale live
path falls back to the archive path and resolves cleanly; the surviving child remains enumerable,
claimable, and pickup-resolvable with its parent archived.

**Known defect, claude-klabauter surface, not DoE's to patch:** the CLI/JSON-RPC transport for this op fails
on every archived handoff — `_read_frontmatter` returns a raw `yaml.safe_load`, so an unquoted
`created: 2026-08-14` arrives as a `datetime.date` the JSON-RPC serializer rejects
(`{"error":{"code":-32603,"message":"Handler returned non-serializable result: Object of type date
is not JSON serializable"}}`). The in-process handler is fine; only the invoke-CLI transport is
broken. Routed to claude-klabauter by memo (spike § "Break-class defect found en route").

---

## What archiving forecloses

`handoff_transition._resolve_path` is live-only containment, keyed on path alone, never
`deployment_state` — a transition verb aimed at an archived record refuses with `handoff_path
escapes state/handoffs/: 'archive/handoffs/<name>'`. This is accepted as the cost of moving early:
a baton that reached `archive/handoffs/` is terminal by positive proof, so no transition verb
*should* reach it again. `archive_transition` mode=supersede is the one exception that still admits
archive paths and works in place — a replay with the same successor converges as a no-op; a
*different* successor hard-refuses rather than silently overwriting one real succession edge with
another.
