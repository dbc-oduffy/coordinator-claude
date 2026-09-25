# Handoff Deployment-State Lifecycle and Transition-Verb Machinery


Purpose: Documents the `deployment_state` lifecycle, transition-verb machinery, and the
reclamation/reaping sweeps that operate on handoff frontmatter. There is no rendered tracker
artifact — query the substrate live (`bin/query-records`) rather than reading a pre-rendered
snapshot.

>
> Back-citations:
>   - coordinator/CLAUDE.md § Live Queries vs. Scaffolded Indices — retired, no confirmed successor located (why no hand-maintained table)
>   - docs/wiki/ceremony-calibration/workday-workweek-cadence.md "Handoffs are the atom; the week-changelog is the index"
>   - docs/wiki/release-and-distribution/completion-log-release-loop.md § Phase 2 (canonical archive glob for archive reads)
>   - docs/wiki/baton-lifecycle/spinoff-handoffs.md (lineage DAG edge-kinds — `predecessor`, `additional_predecessors`,
>     `forked_from`, `origin_*` — is the canonical home for fan-in/fan-out lineage; not duplicated here)

---

## Query-records as spine — query live, don't render a snapshot

There is no hand-written or rendered markdown table of handoff state. That would require agents
to keep a file consistent with the source files it describes — the classic scaffolded-index
maintenance trap documented in coordinator/CLAUDE.md § Live Queries vs. Scaffolded Indices —
retired, no confirmed successor located. Instead, `bin/query-records` reads frontmatter from
`state/handoffs/*.md`, `state/handoffs/spinoffs/*.md`, and `cross-repo/*.md` on demand — the
substrate is the source of truth, queried live, not a pre-rendered artifact that can drift.

---

## Category Taxonomy

The `category` frontmatter field provides coarse routing signal for `query-records` filters.
All values map to the `handoff.yaml` schema enum.

| Value | Meaning |
|-------|---------|
| `roadmap` | Feature work tracked in the roadmap graph (spinoff-roadmap handoffs, sprint items) |
| `infra` | Build system, tooling, plugin, CI, deployment, install-surface work |
| `bug` | Defect investigation and fix workstreams |
| `docs` | Documentation updates, wiki authoring, onboarding content |
| `research` | Deep-research pipelines, experiments, discovery work |
| `refactor` | Code restructuring, cleanup, migration without new behaviour |
| `uncategorized` | Null-object sentinel for legacy handoffs backfilled by the normalizer when no category can be inferred. New handoffs should pick one of the six meaningful values, not this. |

`category` is **optional** in the schema (legacy handoffs without it still pass validation).
`query-records` filters on `category=X` skip unset entries.

**Spinoff-roadmap clarification:** A `kind: spinoff-roadmap` handoff carries roadmap graph
primitives (`stub_id`, `roadmap_id`, `blocked_by`). It queries as a handoff record — with those
fields present — because it IS a handoff (a session-continuity artifact). The roadmap plan
document and sprint alignment reviews stay in the **weekly** ceremony. The daily/weekly split is
by **artifact type** (handoffs/spinoffs/memos vs. plans), not by strategic-ness. A roadmap
spinoff is strategically significant but temporally a handoff.

---

## The Normalizer

`bin/normalize-handoff-frontmatter.js` is a companion tool that backfills `category` and
`summary` on handoffs that predate the schema extension.

Operating rules:
- **Active-only by default** — only processes `state/handoffs/` (not the archive).
  Archived handoffs are immutable records; backfilling them changes the historical record
  without benefit.
- **Dry-run is the default** — invoke with `--write` to apply changes. Without `--write`,
  the tool reports what it would change without touching any file.
- **Non-destructive** — only adds missing fields; never overwrites existing values.

### Running ad-hoc

`normalize-handoff-frontmatter.js` migrated to the engine repo's `coordinator/bin/` — resolve `$REPO_CLAUDE_KLABAUTER` per `percolate-setup.md` § PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT.

```sh
# Dry-run (preview only):
node "$REPO_CLAUDE_KLABAUTER/coordinator/bin/normalize-handoff-frontmatter.js"

# Apply:
node "$REPO_CLAUDE_KLABAUTER/coordinator/bin/normalize-handoff-frontmatter.js" --write

# Against a specific repo root:
node "$REPO_CLAUDE_KLABAUTER/coordinator/bin/normalize-handoff-frontmatter.js" \
  --root /path/to/repo --write
```

---

## The `deployment_state` Lifecycle

<!-- src: plan06-033, plan06-034, plan06-035, plan06-036, plan06-037, plan06-038, plan06-039, plan06-040, plan06-048, plan06-051 -->

`deployment_state` is a handoff's other axis alongside `status` (`active | consumed`). It applies
universally across all handoff kinds (continuation, spinoff, spinoff-roadmap) — one enum, one
queryable field, not a per-kind variant.

| Value | Meaning |
|-------|---------|
| `awaiting_gate` | Blocked on a named dependency (`gate_dependency:` prose or `blocked_by:` structured edge) — not yet pickable. |
| `ready_to_fire` | Unblocked and eligible for pickup. **Only this value surfaces in start ceremonies** (`/workday-start`, `/workstream-start`). |
| `in_flight` | `/pickup` has claimed it; a session is actively working it. |
| `shipped` | Terminal — the deliverable landed. |
| `abandoned` | Terminal — carries the supersession semantic (see `coordinator/skills/handoff/SKILL.md` § Handoff Lineage: expressed as `status: consumed` + `deployment_state: abandoned`, not a separate `superseded` status). |

### `/pickup` Step 2 (Mutate and Commit) — the state-mutating commit

`/pickup` mutates frontmatter only (`status: open → claimed`, `deployment_state → in_flight`,
stamp `claimed_at`/`claimed_by`) and commits that mutation with a single explicit-path commit —
it does NOT move the file. Archival is a separate later event: whichever fires first, the async
sweep (`fleet.archive_completed_handoffs`) or the picking-up session's own terminal event
(`/handoff` chain-archival or `/workstream-complete`'s close). The lifecycle-vocabulary overhaul renamed the fields
(`consumed_by` -> `claimed_by`) at P2, and the write path has already cut over — `/pickup` stamps
only `claimed_at`/`claimed_by` today. The corpus is still mixed during the P1..P4 migration window,
so readers must prefer `claimed_by` and fall back to `consumed_by`.

**Concurrent `/pickup` is fail-loud, not first-wins-silently.** The losing session's claim attempt
fails — `cs_claim_handoff` returns EEXIST, or a post-`git fetch` re-read shows `claimed_by`/
`claimed_at` already populated by the winner (the file itself never moves; both sessions
are racing the same in-place frontmatter mutation, not a file relocation). The loser MUST stop,
surface to the PM, and must NOT retry, mutate, or commit anything further — no automatic fallback
to a different handoff, no silent no-op. This mirrors `cs_claim_handoff` EEXIST semantics
referenced in `coordinator/skills/handoff/SKILL.md` § Handoff Lineage.

### Archival — Option-A cutover mechanics


As of 2026-07-12, archival is an **event-driven** operation owned by the engine, replacing a
prior shell-side mtime-polling veto (Option A, chosen over re-keying the shell veto in place —
PM direction: "lean on the engine," extending its existing boot-time-archival ownership
rather than patching the shell-side mechanism it was meant to replace). The cutover's concrete
migration sequence:

- **C1** — delete the mtime veto outright; do not re-key it to a different field.
<!-- guard-allow: directive-ids-are-engine-current — K-046 removed this directive and its `ceremony.wsc_tail` op; named so a reader tracing the old detached-sweep path learns it is gone -->
- **C2/C3** — wire `handoff.ship_and_archive` at `/workstream-complete`'s `d-run-wsc-tail` directive, and give
  `/handoff` its own chain-archival path via `strangle_route_mutation`.
- **C4** — tests covering both wiring points.
- **C5** — caller audit (find and fix every caller assuming the old mtime-veto behavior).
- **C6** — doc update.
- **C7** — reply-to-claude-klabauter memo closing the cross-repo loop.

Treat C1–C7 as an ordered checklist, not independently schedulable items — C2/C3 depend on C1
being gone first, and C4 validates C2/C3.

**Graceful degrade, not fail-loud, when the engine is absent (AC2, PM-confirmed).** The event-driven
archival op is engine-primary, not hard-required: with the engine present, archival runs through the
engine op; with the engine absent, archival must still self-archive via a veto-less fallback that
skips the (retired) mtime veto logic entirely rather than blocking or erroring out. Do not
confuse "engine-primary" with "engine-required," and do not re-introduce mtime-based archival
vetoes in shell as a "quick fix" — the veto-less fallback, not a veto re-key, is the intended
degrade path.

**Chain-archiving a predecessor must flip `status` in the same move.** When a successor handoff
is created and its predecessor is chain-archived (`git mv` to `archive/handoffs/`), the
predecessor's `status: active` is frequently left un-flipped — landing an archived file that
still reads `status: active` + `deployment_state: ready_to_fire`, i.e. a "live, pickable" handoff
sitting in the archive. The chain-archive step must, in the same commit, set `status: consumed` +
a truthful `deployment_state` (`in_flight` if the successor continues the workstream, `abandoned`
if superseded-and-dropped), optionally with `consumed_by: <successor-basename>`. An archived
handoff with an active status is not a stale record, it is a dangerous one — a reader or sweep can
treat it as still fireable.

**`handoff.ship_and_archive` receipts are not proof the DoE-side mutation ran.** The
Claude-klabauter-driven (pipeline-inverted) `/workstream-complete` `wsc_commit` op records "ship consumed
handoff" and stub-close as receipt nodes but has been observed NOT to execute the corresponding
DoE-side mutation — the consumed handoff stays `consumed`/`in_flight` and the roadmap stub-index
stays stale even though the receipt says the step ran. After a chain-terminal `wsc_commit`,
verify the handoff and any origin stub on disk rather than trusting the receipt; if unshipped,
ship and refresh them manually via the archive-stamp CLI's stamp-only mode. A stub-close call
no-ops silently unless the plan/handoff itself carries `roadmap_id`/`stub_id` — that silent no-op
is expected, not a bug to chase.

### Query surfaces

- **Start-ceremony query:** `bin/query-records --type handoff --where 'deployment_state=ready_to_fire AND status=active'`.
- **Stale-gate query (separate, not folded into the above):** `awaiting_gate` entries older than 14
  days, via `bin/query-records --older-than 14d` — the inverse of `--since Nd`.
- **`--type handoff-archived`** maps `archive/handoffs/*.md`, orthogonal to `--type handoff` (which
  reads `state/handoffs/`). Backed by its own `schemas/handoff-archived.yaml`.
- **`/distill` archive acceptance:** `archive/specs/` is in scope; `archive/handoffs/` is **not a
  distillation cohort** and is never harvested or deleted by `/distill` (pruning is `/update-docs`
  Phase 8b). For specs, deletion requires either `shipped_in:` present + an extraction artifact
  already exists, OR the record is content-free with no cross-refs. `shipped_in:` (commit SHA or PR ref) is what prevents
  orphan deletion — it is set by `/pickup` (rare) or by the picking-up session's `/handoff`/
  session-end.

### `reviewed_at_session_end` and the mtime defense-in-depth check

- `reviewed_at_session_end` (optional handoff field): `'<sha-range> <reviewer> <YYYY-MM-DD>'`,
  mirrored from the session-end review-trail record when a handoff and a review both exist for the
  same session boundary.
- **Defense-in-depth, not the primary archival mechanism:** `/update-docs` runs a lightweight mtime
  check as a backstop. A file with `status: consumed` OR `deployment_state: in_flight` (i.e.
  `/pickup` claimed it in place, but neither deferred archival path — the async sweep or the
  picking-up session's own terminal event — has fired yet) surfaces to the PM rather than being
  silently swept. This preserves `/pickup`'s independence — the backstop catches its failure mode
  without coupling the two mechanisms.

---

## Execution-Handoff Contract — the `handoff_phase` Field

Historically a handoff covered only involuntary/voluntary continuation (context ran out,
session ending) — but a distinct sub-shape emerged organically: the **execution handoff**,
used at the plan-review → `/execute-plan` seam, where a reviewed plan has been authorized and
a fresh execution session is deliberately spun up to run it (the Starfleet Officer Doctrine
carries no "ask, don't assume" sub-rule for execution of a reviewed plan under that name,
and no successor location is confirmed; see `plan-execute-session-split.md`
for the authorization-stamp mechanics themselves).

A 2026-07-17 fleet-wide sweep found **120 de-facto execution handoffs across 8 repos** already
using this shape informally, with **five divergent dialects** across siblings. The 2026-07-17
contract 
formalized this into schema rather than leaving it as convention, and shipped it same-day.

### An orthogonal field, not a new kind

**Decision (PM-ratified):** add `handoff_phase` as a field on the existing
`kind:session-handoff`, with enum values `{continuation, execution}` — do **not** introduce a
parallel `kind` (e.g. `execution-handoff`) for this.

Rationale: the plan→execute seam and an involuntary mid-work save-state are best modeled as
**orthogonal axes** of the same underlying object (a handoff is still a handoff — same
consumers, same query surfaces, same lifecycle), not as a fork in the `kind` enum. Splitting
`kind` would fork every downstream consumer (query surfaces, renderers-turned-queries) that
currently treats `session-handoff` as one thing. Adding a field is additive; forking `kind` is
not.

### Shipped schema surface

Ships in five commits, replacing what would otherwise be a recurring 120-handoff manual scout
sweep:

| Commit | Delivers |
|---|---|
| C1 | Schema: `handoff_phase` enum field on `kind:session-handoff` |
| C2 | Cross-field validation rules (stamp requirement + kind-gate — see below) |
| C3 | query-surface view — splits fireable vs gated |
| C4 | Scaffold (record-creation helper/template updates) |
| C5 | Normalize (backfill/reconciliation pass over existing records) |

Optional fields added alongside `handoff_phase`: `execution_authorized_by`,
`execution_authorized_at`, `execution_authorized_sha`, `execution_authorized_note` — the
**four-field authorization stamp** (see `plan-execute-session-split.md` for the stamp's own
content-binding and write-bar rules). A `query-records` facet was added so the stamp/phase
state is queryable by locator, not just visible on individual records.

### Cross-field validation rules

Two independent validation rules govern the new field, each with a different scope:

1. **Stamp-completeness rule (phase-conditional).** When `handoff_phase == execution`, ALL FOUR
   stamp fields (`execution_authorized_by/at/sha/note`) must be present and non-empty. This is
   gated by a **going-forward cutoff of 2026-07-17** — records created before the cutoff are
   exempt, protecting the 120 historical execution handoffs discovered in the census (most of
   which predate the four-field convention and would otherwise fail validation en masse). The
   cutoff mirrors the pattern used for the `category`/`summary` A3a self-guard. The cutoff is
   **defense-in-depth**; the primary exemption mechanism is field-presence itself — a record
   either has all four fields or it doesn't, checked per-record regardless of date, with the
   cutoff as the backstop that prevents pre-existing records from being retroactively flagged.

2. **Kind-gate rule (phase-presence, no cutoff).** If `handoff_phase` is present at all
   (either `continuation` or `execution`), then `kind` MUST be `session-handoff`. This fails
   loud if `handoff_phase` appears on any other kind — `spinoff`, `spinoff-roadmap`,
   `spinoff-goal`, `spinoff-roadmap-creator`, `recovery`. Unlike the stamp rule, this gate has
   **no cutoff** — it applies unconditionally regardless of when the record was created, because
   the field is declared as belonging to one specific `kind`, not globally available.

**Why two different gating strategies for the same field:** the stamp rule protects against
breaking 120 pre-existing records that predate a convention; the kind-gate rule protects
against a field ending up on the wrong record type at all, which has no legitimate historical
exemption — a `spinoff` record with `handoff_phase` set is a misuse regardless of when it was
written.

### Deployment-state orthogonality — fireable vs gated

**Decision:** do NOT collapse `ready_to_fire` and `awaiting_gate` into a single `authorized`
state. These are two **distinct live sub-states** along an axis orthogonal to
`handoff_phase` itself:

- An execution handoff can be **authorized but not yet fireable** — e.g. blocked on an
  external cross-repo gate (a sibling repo needs to land a dependency first). This is a
  legitimate, common state, not an edge case to be squashed.
- Correct classification of "where is this execution handoff right now" requires **both axes**:
  phase (`continuation` vs `execution`) AND deployment sub-state (`ready_to_fire` vs
  `awaiting_gate`). Collapsing the sub-state loses exactly the information the
  query-surface execution-handoffs view (C3, above) exists to surface.

### Key Patterns

- **Additive-field-over-kind-fork** is the general pattern here: when a new sub-shape of an
  existing record type emerges, prefer an orthogonal field with its own enum over forking
  `kind`. Forking `kind` is a one-way door that fans out to every consumer; adding a field does
  not.
- **Cutoff-as-defense-in-depth, presence-as-primary-gate**: when introducing a new
  cross-field validation rule that would retroactively invalidate a large body of existing
  records, pair a going-forward date cutoff with a presence/completeness check, rather than
  gating solely on date. The date cutoff is the safety net; the field-shape check is the real
  rule.
- **Survey before you formalize.** The schema work here followed, not preceded, a fleet-wide
  empirical sweep (six scouts, 8 repos) that established the dialects already in informal use.
  The formalization target (four-field stamp, `handoff_phase` enum) was chosen to match the
  dominant existing dialect (the engine repo/market-intel "full" dialect) rather than inventing a new
  shape from scratch.

### Gotchas

- **Convention drift across repos predates the schema.** The 2026-07-17 census found five
  dialects: the engine repo/market-intel (full four-field stamp), cockpit/rag (mostly just `_by`),
  this repo (mixed), example-game-repo (no stamp at all). Do not assume any given repo's pre-2026-07-17
  handoff records conform to the four-field stamp — check the phase/cutoff logic before
  treating a record's absence of stamp fields as a validation failure.
- **`handoff_phase` presence outside `kind:session-handoff` is a hard failure, not a warning**,
  and has no historical-cutoff exemption — unlike the stamp-completeness rule. Don't reuse the
  cutoff mental model across both rules; they're gated differently on purpose (see § Cross-field
  validation rules above).
- **Don't conflate `ready_to_fire`/`awaiting_gate` with `handoff_phase` itself** — the former is
  a deployment/execution sub-state; the latter is the phase-of-lifecycle field this section
  primarily describes. They are orthogonal axes that must both be checked to classify an
  execution handoff correctly (see § Deployment-state orthogonality above).

### Reference

- Ships in five commits (C1–C5): schema, validation rules, query-surface view, scaffold,
  normalize.
- Fleet census (six-scout sweep): 120 de-facto execution handoffs across 8 repos, five dialects
  identified.

---

## Transition Verbs and the Auto-Reconcile Engine

<!-- src: memo05-001, memo05-007, plan24-002, plan33-020, plan33-021, plan33-022, plan33-041, plan33-042, memo04-019, memo04-020, memo04-021, memo04-022 -->

`deployment_state` and `status` transitions are increasingly expressed as named **verbs**
(`handoff.transition <verb>`) rather than by-hand frontmatter edits, ported one at a time from
coordinator JS into the engine's Python implementation (the contract-vs-engine split — this repo authors the
verb contract, the engine owns the implementation).

### Verb inventory (as of 2026-07-13)

| Verb | Effect | Status |
|------|--------|--------|
| `consume` | `status: open → claimed`, stamps `claimed_at`/`claimed_by` | Ported to the engine; this repo's side `strangle_route`d |
| `supersede` | marks abandoned with lineage pointer | Ported to the engine |
| `ship` | marks `deployment_state: shipped` | Ported to the engine |
| `unconsume` | reverses `consume`: `status: claimed → open`; `deployment_state {in_flight\|ready_to_fire} → ready_to_fire`; strips `claimed_at`/`claimed_by` (and defensively any stray `consumed_at`/`consumed_by`); optional `note` param writes `park_note` frontmatter | Shipped (engine60 tests green); this repo wired via `cs_unconsume_handoff` |
| `gate-recheck` | re-evaluates a `blocked_by`/`gate_dependency` edge, clears if satisfied | Ported to the engine 2026-07-13 (was local-JS-only, `strangle_route`d after) |
| `repark` | re-blocks a handoff; fail-loud when the handoff is not `in_flight` (guard preserved across the port) | Ported to the engine 2026-07-13 |

**`unconsume` resolves the body-freeze problem:** once a handoff's `status` flips to `consumed`, it
becomes an immutable archival record by convention — `unconsume` is the sanctioned way to reopen
one for edits (flip back to `active` unblocks the file for further changes).

### Fail-loud vs. silent-by-design — the transition-verb asymmetry

`cs_consume_handoff` (and transition-verb wrappers generally) must **exit non-zero on failure**,
unlike advisory helpers such as `stamp_shipped_in` which fail silently. A silent `consume` failure
leaves `status: open` / `claimed_by: <empty>` — a state that breaks downstream idempotency
checks (a second consume attempt can't tell "already consumed" from "never attempted"). The
asymmetry is principled, not inconsistent: `stamp_shipped_in` writes an **advisory** field (missing
it degrades gracefully — see `shipped_in:` orphan-deletion guard above); a transition verb performs
a **state-transition write** whose partial failure corrupts the state machine. State-transition
writes fail loud; advisory stamps fail soft.

### Auto-reconcile engine — retired, do not re-arm

`handoff.reconcile_open` is a dead op — engine-side unclassified, pinned dead by three engine-repo
tests, kill-ledger K-057 (superseding the earlier K-026 entry). No cadence invokes it, no wrapper
consumes it, and no doctrine in this file depends on it being live. Two propagation rules survive
independent of the retired op and remain in force: an `abandoned` handoff's gate is never silently
auto-cleared — it always surfaces to a human/EM for a decision; and a satisfied structured
`blocked_by` edge that contradicts stale `gate_dependency` prose is surfaced as a named finding,
never auto-transitioned — `handoff.transition gate-recheck --cleared` is the human discharge verb
either way. Off-baton auto-ship (whether a handoff worked without `/pickup` or a direct session
claim counts as shipped) remains an open coordinator-doctrine question with no engine mechanism
attached.

---

## Orphan Reclamation and Claim-Lock Reaping

<!-- src: plan33-023, plan33-024, plan33-043, memo04-014, memo04-015, memo04-016, memo08-012 -->

Two independent sweep mechanisms recover handoffs left in inconsistent states by crashed or
abandoned sessions.

### Reaper: dead holders release their claim

`reap-orphaned-in-flight-handoffs.py` reclaims handoffs whose `deployment_state: in_flight` claim
outlived its holder session. Automated resolution to `abandoned` followed by archival is not
performed — only a session's own resolution should ever produce `abandoned`. The reaper
first runs a ship-check: it ships an orphan as `shipped` when four predicates ALL hold — that dead
holder genuinely ran a terminal completion ceremony, which IS resolution by a session:

- **P1** — the orphan handoff itself is not a `kind: spinoff-roadmap` node with a populated
  `deliverable_id` (those belong to `promote-shipped-in-flight-stubs.py`'s separate
  deliverable-spine join and skip this reaper's ship-check entirely).
  <!-- Review: code-reviewer Finding 2 — reworded from "the dead holder session is not
       promoter-owned" (a session-level framing) to the actual per-handoff frontmatter
       gate; a single dead session can hold claims on both a spinoff-roadmap node and an
       ordinary handoff simultaneously, so "session is not promoter-owned" isn't coherent. -->
- **P2** — the dead holder session consumed **exactly one** handoff. If ≥2 handoffs share the same
  `consumed_by`/`claimed_by`, the reaper falls through to release rather than guess which one shipped — this
  guards against a false-positive ship attribution when a session's claim history is ambiguous.
- **P3** — the dead holder session has exactly one completion-log entry.
- **P4** — at least one SHA in that completion entry is git-reachable (resolvable).

If any predicate fails, the reaper falls through to **release**, not abandonment: it dispatches
`archive-stamp-cli`'s `unconsume-handoff` verb, returning the handoff to the pool (`status: active`,
`deployment_state: ready_to_fire`, `consumed_by`/`claimed_by` and `consumed_at`/`claimed_at` stripped, a `park_note:` recording
the release). The handoff stays in `state/handoffs/` and is NOT archived — archival only ever
happens after a handoff reaches `shipped` via the engine repo's `coordinator/bin/sweep-terminal-handoffs.py`, run from `/workday-start` Step 1.47 on demand, or via `/workday-complete`'s `reap-orphaned-in-flight-handoffs` + `handoff-housekeeping` pair, which owns the dead-holder case. Not on any boot-time trigger — that sweep is killed.
**There is no liveness-based auto-abandonment.** `abandoned` is reachable only by
explicit human/session decision, never by this sweep — a fail-closed-to-`abandoned` default
silently destroys handoffs and must not be restored.

The reaper re-reads state at act-time (TOCTOU guard — the holder-liveness and claim state can
change between the sweep's initial read and its write) and `--dry-run` reports the decision without
mutating anything.


### Ship-oracle design — ship, don't abandon

Completion witnessing for handoffs is **local to this repo**, not sourced from the engine's cross-repo
receipt. The canonical oracle is the engine repo's `coordinator/bin/rollup-derive.py`'s deliverable-spine oracle — it derives
completion from the local completion-entry witness. This explicitly replaces cross-repo
receipt coupling to the engine's `wsc` (workstream-complete) receipt — do not reach for the engine's
receipt as the completion signal. The completion-entry's `authored_by` witness is only trusted
when gated behind an unambiguous 1:1-binding predicate (one completion-entry maps unambiguously
to one handoff; ambiguous bindings do not count as a witness) — the architectural sibling of the
auto-abandonment halt above: both push completion/closure authority toward an explicit,
session-authored signal and away from an inferred or cross-repo-coupled one.

### Handoff loss mechanisms — the other two triage classes

Beyond crash-orphan auto-abandonment (above, 30 events since 2026-07-04 — archetype:
`2026-07-19_141129_kill-bash-python-cli-veneers.md`, a kill-bash goal item killed because its
holder crashed mid-session, not because the goal was actually abandoned), two further loss
mechanisms were found, each needing separate triage treatment:

1. **v3 flat-cutover sweep** — a confirmed live instance was `validate-install-contract.sh`
   (surfaced via an cockpit-em report). This class needs an **active diff** against current
   state, not a wait-for-reports posture — passive monitoring will not surface these.
2. **Plans stranded mid-execution** — 7 plans executing >6 days, 4 plans in `draft` >14 days at
   triage time; this batch was already triaged as of the source handoff.

**Operating bias:** bias hard toward DROP when triaging revival candidates — only revive with an
explicit PM decision. Do not default to reviving a stranded/orphaned handoff just because it
still exists on disk.

### Stale claim-lock pruning (open defect, DoE-owned as of 2026-07-13)

Claim locks at `.git/coordinator-sessions/handoff-claims/<handoff>/{pid,session_id,claimed_at}` are
**never pruned by PID liveness** by the reaper described above. A dead-PID lock reads as a "live
claim" to the archival no-live-claim gate, so any consumed/terminal handoff under a stale lock is
retained indefinitely. (Repro observed 2026-07-13: 7 claim locks present, all 7 PIDs dead, one even
already-archived, with the reaper's `.last-reap` sentinel itself 6h stale.) Per
`coordinator/docs/wiki/coordinator-tripwires/`'s `RAW-PID-LIVENESS` tripwire, liveness checks must use
`cs_live_session_ids`/`cs_claim_holder_live`, never a raw `kill -0 <pid>` — a stored PID from a
prior process generation reads as live to `kill -0` even when the actual claiming process is long
gone. This is the same hazard applied specifically to claim-lock pruning.

### Archive-predicate terminality — two-branch fix

`fleet.archive_completed_handoffs` originally gated terminality on `status == 'consumed'` only. A
handoff with `status: active` + `deployment_state: shipped` — schema-valid, but not consumed
(produced by `/workstream-complete`'s close in `--stamp-only` mode and by the auto-reconcile engine
itself) — passed the sweep pre-filter but was silently rejected by the archive op, because the two
mechanisms disagreed on what "terminal" means. Fixed by widening `_is_terminal` to a two-branch
predicate: Branch A (`status == consumed` AND `deployment_state != in_flight`), Branch B (`status`
anything, `deployment_state` in `HANDOFF_TERMINAL_DEPLOYMENT`). That set is four-member —
`{shipped, continued, closed, abandoned}`, `abandoned` carried for legacy records only — and has a
single home in the engine repo's `coordinator_core/lifecycle_constants.py`. Read it from there; a
hand-written copy of the member list is how the two branches silently diverged before.

### `/pickup` archive-fallback directory nesting

`/pickup`'s Step 1 (Classify, Load, and Reconcile Against Reality) archive-fallback resolution originally used flat `[ -f <path> ]` existence
checks, but this repo's actual archive layout sweeps handoffs into month-nested directories
(`archive/handoffs/2026-07/…`), so a swept baton dead-ended to "Ambiguous" instead of resolving as
shipped. Fixed to `find` recursively across `cross-repo/archive`, `archive/handoffs`,
and `archive/completed` — tolerates flat, month-nested, or any other layout. When adding a new
archive-sweep destination directory, check it against this fallback resolution or it will silently
regress to the same "Ambiguous" failure mode.

### Marking gap — terminal transitions must actually be invoked

Some handoffs whose workstream fully shipped were observed left at `deployment_state: active`/
`awaiting_gate` forever — never stamped terminal, so no sweep was ever eligible to archive them
(e.g. a roadmap stub + its execution handoff, still live-labelled while all its child chunks
shipped). The terminal-transition *engine verb* (`handoff_transition.ship`) is the engine's, but the
*callers* are coordinator skills — `/workstream-complete`'s close and `/handoff` chain-archival.
When authoring or auditing a new ship-path, confirm it actually invokes the terminal transition
rather than assuming a downstream sweep will catch it — nothing sweeps a handoff that was never
marked terminal in the first place.

---

## Picking Up — Carried-Forward Items Are Hypotheses, Not a Work Queue

A handoff's Carried-Forward / "pending" list is a snapshot of what the authoring session *believed*
was outstanding — a large fraction of those items are, on inspection, already-done (shipped since
the handoff was written), premise-wrong, or ratified-permanent (a DR-blessed bash residue, or a
strangler State-1 fallback that is NOT collapsible). Treating the list as an executor work-queue
re-does shipped work and, worse, can silently reverse a ratified decision. Empirically, a single
pickup can find most tail chunks (observed: 5 of 6) are no-op or premise-corrected on inspection.

**Verify-first, then execute only the confirmed-live remainder.** Dispatch *verify-first* agents
(read-only scouts, NOT executors) across the carried-forward items, each with an explicit
`report if the premise is unclear, do not guess` stop-condition; only the chunks that come back
confirmed-live get an executor. This is cheap relative to a wrong executor dispatch, and it is the
tracker-side application of coordinator/docs/wiki/em-operating-model/verification-discipline.md § Premises Are Hypothesis — Verify Against Disk, Not Prose ("handoff framing is
hypothesis, not ground truth — read cited code before acting").

**The verdict table is a hypothesis in both directions, not just the OPEN column.** Pickup
doctrine already covers re-verifying items an inherited handoff calls OPEN — concurrent sessions
routinely close a large fraction of such a list. The symmetric error is unguarded: an item the
handoff writes off as dead, changed-shape, or already-closed deserves the same re-verification,
not a free pass. A reconciliation baton once declared an item dead because the tracked successor
record had been "wholly rewritten" — true, and irrelevant, because the item actually targeted two
archived records whose own state was fully intact and unaddressed. Had only the live rows been
re-checked, that write-off would have been carried forward as settled indefinitely. Treat every
row of a verdict table — dead or open — as a claim to spot-check, not a label to trust.

**`/workstream-complete` cannot see a plan the same session authored — it caps unexecuted work as
clean.** A session that *authors* a plan never claims it; claim acquisition is `/pickup`'s alone,
and the handoff path releases rather than acquires. Governing-plan resolution therefore has no
input on a plan-authoring session, and every check keyed on it reports the healthy-looking
absence — "not applicable, no open rows on the governing plan" — while a plan committed by that
same session sits on disk with open, unauthorized rows. Multiple independent tail checks asking
"is anything in flight" can each answer "cannot resolve" and have that read as "nothing in
flight." When a session both authors and closes in the same sitting, check its own just-committed
plans directly rather than trusting governing-plan resolution to surface them.

---

## Schema, Graph-Key, and Review-Trail Integrity Gaps

**A dependency stated in prose but absent from frontmatter does not exist to a scheduler.**
Humans reading a plan see a coherent dependency order; ceremonies like `/mise-en-place` and
handoff-triage read `blocked_by`/`blocks`/`deployment_state` keys, not paragraphs. The two
diverge silently: a plan can name its gate in `gate_dependency` prose while omitting it from
`blocked_by`, or declare `blocks: [X, Y]` that neither X nor Y reciprocates, or assert an edge in
its body with no graph keys at all. Any of these executes out of order with every individual gate
passing. The same rule applies to conventions and mitigations generally: an ordering pinned only
in an audit document is inert, because no executor reads audits. If a constraint must bind a
machine, it has to be encoded in the key the machine actually reads.

**`kind: spinoff-roadmap` handoffs have shipped with schema-invalid `gate_dependency`/`stub_id`.**
A comment-only `gate_dependency` (parses to `null`) fails validation because the schema wants a
string or omission, and `ready_to_fire`'s cross-field rule requires the key to be empty or
*omitted*, not merely falsy — two validators in tension over the same field. Separately, a
`spinoff-roadmap` handoff has shipped carrying `tc_id` where `stub_id` was expected, failing
`cs_consume_handoff` on pickup. The fix belongs at the authoring skill (emit `stub_id`; omit,
don't null-comment, a cleared `gate_dependency`); the pickup-time workaround is to delete the
stray `gate_dependency` line and add `stub_id` before consuming.

**A tool accepting your artifact without complaint is not schema validation.** The brief/read
path (e.g. `pickup-assemble brief`) parses frontmatter; it does not validate against the schema.
A hand-authored handoff has shipped clean through that path while carrying real schema
violations — a status value from a retired enum, a typed-string field set to `null`, a key
present alongside a deployment state whose cross-field rule forbids the key's presence at all
(not just a truthy value). Only the write-time PreToolUse hook validates against schema; when
hand-authoring a schema-backed handoff instead of taking a scaffolder the hook offers, validate
explicitly against `coordinator/schemas/<kind>.schema.json` rather than inferring health from any
tool that merely consumed the record without erroring. Note when validating by hand: an unquoted
`YYYY-MM-DD` parses to a date object under PyYAML, so a naive harness will false-positive a
"not of type string" finding on every record in the corpus — stringify before comparing, and
don't "fix" the corpus to satisfy your own harness.

**A review sidecar and an integration sidecar both existing does not mean the review landed
before the integration.** A plan can carry a review-integration commit and a reviewer's sidecar
(e.g. `REQUIRES_CHANGES` with several findings) that both read as "done" at a glance, while the
integration pass actually ran *before* the reviewer's findings landed — so the integration
ledger covers only the sidecars that existed at integration time, and the later findings,
including a real correctness defect, sit un-applied with nothing on disk flagging the gap. At
pickup or reconcile, do not treat the existence of a review-integration sidecar as proof its
sibling reviews are integrated: compare each review sidecar's commit against the integration
commit, and read the integration ledger's own finding list for which oracles it actually
consumed. This matters most where reviewer dispatch and integration dispatch are separate waves
that can interleave.

**Per-stub review during a sprint does not satisfy the close-time coverage gate — the trail
record is the coverage, not the review having happened.** A ten-stub sprint can have every stub
genuinely reviewed — multiple reviewers, every finding integrated and verified — and still have
`/workstream-complete`'s chain coverage gate return uncovered, because `state/review-trail/` is
what the gate reads, and no trail record was written at review time. A review that happened but
left no trail record is, to every downstream gate and successor session, indistinguishable from a
review that never happened. Write the trail record at the moment of the review, not deferred to a
closing ceremony that may be handed to a different session — deferring bookkeeping bets the same
session runs the close, and on a shared branch `sha_range` usually cannot be a contiguous span of
just your own commits, so the record gets harder to write the longer it's deferred. Separately,
the close-time partitioned review this gate enforces is not a duplicate of the per-stub reviews:
per-stub review checks a stub against its own acceptance criteria, while the close-time pass sees
the integrated whole and is the only pass positioned to catch a defect whose fix was verified
against the stub's framing rather than against the system it lands in. Budget for a chain-terminal
close to require this re-review rather than treating "uncovered" as a bookkeeping nuisance to
waive — and note that running the gate can itself mint an auto-ancestry waiver that reports
"covered" with no review having occurred, so a waiver is an accounting artifact, never evidence
the work was reviewed.

**Every coordinator ceremony validates the artifact it owns; defects live in the disagreements
*between* surfaces.** Plan frontmatter, completion entries, ceremony records, and git are each
individually well-formed and each pass their own gate, so defects accumulate specifically where
two surfaces disagree and nothing reads across them — a plan stamped `implemented` at a fraction
of its acceptance criteria, an unfinished plan with no owner, a daily summary truncated by a
ceremony that ran early, a stale plan stamp, a docstring claiming a sibling module "has not
landed" work that a later commit already exported. None of this is hidden; every fact is usually
already written down correctly in its own artifact. What's missing is a reader comparing two
artifacts and noticing they disagree. Cheap cross-surface checks worth doing on reconcile: a
plan's `status:` against its completion entry; a baton's `blocks:` against whether the named stub
has a live owner; a daily summary's `covered_tip_sha` against that day's actual last commit; a
plan's correction blocks against its own stamp; a module docstring's claim about a sibling against
that sibling's landed code. Corollary for authors: a negative-spec or "not yet landed" claim is a
dated assertion, not a permanent fact — it goes stale the moment the thing lands, and nothing will
tell you.
