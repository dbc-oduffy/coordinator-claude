# Handoff Deployment-State Lifecycle and Transition-Verb Machinery

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-05/2026-05-08-roadmap-skill-and-handoff-lifecycle.md, archive/specs/2026-05/2026-05-08-session-end-review-and-marker-trail.md, cross-repo/archive/2026-07-13-claude-klabauter-em-claude-klabauter-auto-reconcile-wire-surfaces.md, cross-repo/archive/2026-07-13-claude-klabauter-em-unconsume-verb-veneer-wiring.md, 2026-06-24-handoff-lifecycle-transition-helper.md.the Staff Engineer-review.md, 2026-07-13-reaper-ship-not-abandon-shipped-orphans.md, 2026-07-17-project-rag-em-pickup-archive-fallback-nested-dir.md, claude-klabauter-em → claude-central-em, claude-klabauter-em → claude-central-em, 2026-07-13-doe-auto-reconcile-adopt.md -->

> Purpose: Documents the `deployment_state` lifecycle, transition-verb machinery, and the
> reclamation/reaping sweeps that operate on handoff frontmatter. There is no rendered tracker
> artifact — query the substrate live (`bin/query-records`) rather than reading a pre-rendered
> snapshot.
>
> Spec backlink: docs/plans/2026-05-29-handoff-tracker-system.md
>
> Back-citations:
>   - coordinator/CLAUDE.md § Live Queries vs. Scaffolded Indices — retired, no confirmed successor located (why no hand-maintained table)
>   - docs/wiki/workday-workweek-cadence.md "Handoffs are the atom; the week-changelog is the index"
>   - docs/wiki/completion-log-release-loop.md § Phase 2 (canonical archive glob for archive reads)
>   - docs/wiki/spinoff-handoffs.md (lineage DAG edge-kinds — `predecessor`, `additional_predecessors`,
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

`normalize-handoff-frontmatter.js` migrated to claude-klabauter's `coordinator/bin/` (commit
b644d5a9) — resolve `$REPO_CLAUDE_KLABAUTER` per `percolate-setup.md` § PERCOLATE_ROOT and CLAUDE_KLABAUTER_ROOT.

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
(`/handoff` chain-archival or `/workstream-complete`'s close). DR-084 renamed the fields
(`consumed_by` -> `claimed_by`) at P2, and the write path has already cut over — `/pickup` stamps
only `claimed_at`/`claimed_by` today. The corpus is still mixed during the P1..P4 migration window,
so readers must prefer `claimed_by` and fall back to `consumed_by`.

**Concurrent `/pickup` is fail-loud, not first-wins-silently.** The losing session's claim attempt
fails — `cs_claim_handoff` returns EEXIST, or a post-`git fetch` re-read shows `claimed_by`/
`claimed_at` (DR-084) already populated by the winner (the file itself never moves; both sessions
are racing the same in-place frontmatter mutation, not a file relocation). The loser MUST stop,
surface to the PM, and must NOT retry, mutate, or commit anything further — no automatic fallback
to a different handoff, no silent no-op. This mirrors `cs_claim_handoff` EEXIST semantics
referenced in `coordinator/skills/handoff/SKILL.md` § Handoff Lineage.

### Archival — Option-A cutover mechanics

<!-- folded 2026-07-22-23h55-residue guide-review-2 integration: merged from docs/wiki/handoff.md
(round-2 residue guide, itself merged from docs/wiki/archival.md), nuggets r2-001, r2-002,
r2-003; source archive/handoffs/2026-07/2026-07-12_184145_9377a287-1399-4a71-8255-268555d14f61.md.
Net-new detail behind the `fleet.archive_completed_handoffs` / Step 2.7 wiring named above. -->

As of 2026-07-12, archival is an **event-driven** operation owned by claude-klabauter's engine, replacing a
prior shell-side mtime-polling veto (Option A, chosen over re-keying the shell veto in place —
PM direction: "lean on claude-klabauter," extending the engine's existing boot-time-archival ownership
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

**Graceful degrade, not fail-loud, when claude-klabauter is absent (AC2, PM-confirmed).** The event-driven
archival op is claude-klabauter-primary, not hard-required: with claude-klabauter present, archival runs through the
engine op; with claude-klabauter absent, archival must still self-archive via a veto-less fallback that
skips the (retired) mtime veto logic entirely rather than blocking or erroring out. Do not
confuse "claude-klabauter-primary" with "claude-klabauter-required," and do not re-introduce mtime-based archival
vetoes in shell as a "quick fix" — the veto-less fallback, not a veto re-key, is the intended
degrade path.

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

<!-- folded 2026-07-22-23h55 guide-review integration: relocated from docs/wiki/handoff.md
     (plugin-doctrine misplaced in the DoE-only docs/wiki/ tree — the session-handoff record
     kind's schema belongs here, alongside the rest of the handoff-lifecycle doctrine).
     spec-backlink: run 2026-07-22-23h55, derived from b1-018, b1-020, b1-021, b1-022, b1-023,
     b1-024; source archive/specs/2026-07/2026-07-17-execution-handoff-phase-doe-contract.md -->
## Execution-Handoff Contract — the `handoff_phase` Field

Historically a handoff covered only involuntary/voluntary continuation (context ran out,
session ending) — but a distinct sub-shape emerged organically: the **execution handoff**,
used at the plan-review → `/execute-plan` seam, where a reviewed plan has been authorized and
a fresh execution session is deliberately spun up to run it (per First Officer Doctrine's
"ask, don't assume" rule for execution of a reviewed plan — see `plan-execute-session-split.md`
for the authorization-stamp mechanics themselves).

A 2026-07-17 fleet-wide sweep found **120 de-facto execution handoffs across 8 repos** already
using this shape informally, with **five divergent dialects** across siblings. The 2026-07-17
DoE contract (`archive/specs/2026-07/2026-07-17-execution-handoff-phase-doe-contract.md`)
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
  dominant existing dialect (claude-klabauter/market-intel "full" dialect) rather than inventing a new
  shape from scratch.

### Gotchas

- **Convention drift across repos predates the schema.** The 2026-07-17 census found five
  dialects: claude-klabauter/market-intel (full four-field stamp), cockpit/rag (mostly just `_by`),
  DoE (mixed), example-game-repo (no stamp at all). Do not assume any given repo's pre-2026-07-17
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

- Source spec: `archive/specs/2026-07/2026-07-17-execution-handoff-phase-doe-contract.md`
- Ships in five commits (C1–C5): schema, validation rules, query-surface view, scaffold,
  normalize.
- Fleet census (six-scout sweep): 120 de-facto execution handoffs across 8 repos, five dialects
  identified.

---

## Transition Verbs and the Auto-Reconcile Engine

<!-- src: memo05-001, memo05-007, plan24-002, plan33-020, plan33-021, plan33-022, plan33-041, plan33-042, memo04-019, memo04-020, memo04-021, memo04-022 -->

`deployment_state` and `status` transitions are increasingly expressed as named **verbs**
(`handoff.transition <verb>`) rather than by-hand frontmatter edits, ported one at a time from
coordinator JS into claude-klabauter's Python engine (the DR-047 contract-vs-engine split — DoE authors the
verb contract, claude-klabauter owns the implementation).

### Verb inventory (as of 2026-07-13)

| Verb | Effect | Status |
|------|--------|--------|
| `consume` | `status: open → claimed`, stamps `claimed_at`/`claimed_by` | Ported to claude-klabauter; DoE side `strangle_route`d |
| `supersede` | marks abandoned with lineage pointer | Ported to claude-klabauter |
| `ship` | marks `deployment_state: shipped` | Ported to claude-klabauter |
| `unconsume` | reverses `consume`: `status: claimed → open`; `deployment_state {in_flight\|ready_to_fire} → ready_to_fire`; strips `claimed_at`/`claimed_by` (and defensively any stray `consumed_at`/`consumed_by`); optional `note` param writes `park_note` frontmatter | Shipped (claude-klabauter 6c52aa16, 60 tests green); DoE wired via `cs_unconsume_handoff` |
| `gate-recheck` | re-evaluates a `blocked_by`/`gate_dependency` edge, clears if satisfied | Ported to claude-klabauter 2026-07-13 (was DoE-JS-only, `strangle_route`d after) |
| `repark` | re-blocks a handoff; fail-loud when the handoff is not `in_flight` (guard preserved across the port) | Ported to claude-klabauter 2026-07-13 |

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

`handoff.reconcile_open` is a dead op — engine-side unclassified, pinned dead by three claude-klabauter
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
happens after a handoff reaches `shipped` via claude-klabauter `coordinator/bin/sweep-terminal-handoffs.py`, run from `/workday-start` Step 1.47 on demand, or via `/workday-complete`'s `reap-orphaned-in-flight-handoffs` + `handoff-housekeeping` pair, which owns the dead-holder case. Not on any boot-time trigger — that sweep is killed.
**There is no liveness-based auto-abandonment.** `abandoned` is reachable only by
explicit human/session decision, never by this sweep — a fail-closed-to-`abandoned` default
silently destroys handoffs and must not be restored.

The reaper re-reads state at act-time (TOCTOU guard — the holder-liveness and claim state can
change between the sweep's initial read and its write) and `--dry-run` reports the decision without
mutating anything.

<!-- folded 2026-07-22-23h55-residue guide-review-2 integration: merged from
docs/wiki/handoff.md (round-2 residue guide), nuggets r2-016, r4-032; source handoffs
archive/handoffs/2026-07/2026-07-13_220730_9e520e01-838b-41ce-bcbe-d218f4db25fb.md and
archive/handoffs/2026-07/2026-07-20_114653_revive-lost-capabilities-triage.md. Net-new
material only — the auto-abandonment halt itself and the 30-event count are already covered
above; this adds the ship-oracle framing and the other two loss-mechanism classes. -->

### Ship-oracle design — ship, don't abandon

Completion witnessing for handoffs is **DoE-local**, not sourced from claude-klabauter's cross-repo
receipt. The canonical oracle is claude-klabauter `coordinator/bin/rollup-derive.py`'s deliverable-spine oracle — it derives
completion from the DoE-local completion-entry witness. This explicitly replaces cross-repo
receipt coupling to claude-klabauter's `wsc` (workstream-complete) receipt — do not reach for the claude-klabauter
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
single home in `claude-klabauter coordinator_core/lifecycle_constants.py`. Read it from there; a
hand-written copy of the member list is how the two branches silently diverged before.

### `/pickup` archive-fallback directory nesting

`/pickup`'s Step 1 (Classify, Load, and Reconcile Against Reality) archive-fallback resolution originally used flat `[ -f <path> ]` existence
checks, but DoE's actual archive layout sweeps handoffs into month-nested directories
(`archive/handoffs/2026-07/…`), so a swept baton dead-ended to "Ambiguous" instead of resolving as
shipped. Fixed (1c613e84) to `find` recursively across `cross-repo/archive`, `archive/handoffs`,
and `archive/completed` — tolerates flat, month-nested, or any other layout. When adding a new
archive-sweep destination directory, check it against this fallback resolution or it will silently
regress to the same "Ambiguous" failure mode.

### Marking gap — terminal transitions must actually be invoked

Some handoffs whose workstream fully shipped were observed left at `deployment_state: active`/
`awaiting_gate` forever — never stamped terminal, so no sweep was ever eligible to archive them
(e.g. a roadmap stub + its execution handoff, still live-labelled while all its child chunks
shipped). The terminal-transition *engine verb* (`handoff_transition.ship`) is claude-klabauter's, but the
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
tracker-side application of coordinator/docs/wiki/verification-discipline.md § Premises Are Hypothesis — Verify Against Disk, Not Prose ("handoff framing is
hypothesis, not ground truth — read cited code before acting").
