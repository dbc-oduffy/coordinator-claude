---
title: "Goals / OKR system"
created: 2026-07-07
status: active
---

# Goals / OKR System

> **Purpose.** The goals/OKR system turns the PM's strategic intent from an
> unrecorded mental model into first-class per-repo artifacts that the EM,
> ceremony ladder, and a fleet dashboard can all point at. It answers "what
> larger objective does this initiative serve, and are we winning?" at any point
> in the workstream.

---

## Goal Artifact Shape

Goal artifacts live at `state/goals/<slug>.yaml` (per-repo) — **pure `.yaml`
is canonical** (an earlier `.md`+frontmatter shape was retired once retrieval
parity was confirmed — see the "why the format changed" note below). The
`--type goal` scaffolder, `validate-frontmatter-schema.js` binding,
`emit-goal-from-artifact.py`, and the engine-resident `coordinator/bin/reassess-goal-krs`
all glob `state/goals/*.yaml`; no path in the goal pipeline still targets `*.md`. See
the weekly-goal-artifact authoring path below for how a goal gets
authored week-to-week, and the "why the format changed" note at the end of
this section for the rationale history.

### YAML Frontmatter

```yaml
id: goal-<slug>                 # required; stable canonical identity key
                                 # no <repo> segment; the scaffolder emits
                                 # `goal-{slug}` only.
                                 # Uniqueness is directory-scoped (state/goals/ is
                                 # per-repo), not id-string-scoped — see Peer-Repo
                                 # Percolation § below.
title: <human-readable name>
status: active                  # active | achieved | abandoned
objective: >-                   # prose — the aspiration / why
  One-paragraph description of what we are trying to achieve.
key_results:
  - id: kr-1
    text: Ship X metric to Y by Z
    kind: outcome                # output | outcome
    status: not-started          # not-started | in-progress | met | at-risk
    weekly_perceptible: true     # can an agent/PM observe movement week-to-week?
    evidence_source: null        # string path or null
created: YYYY-MM-DD
owner: <session-or-PM-id>
period: week                    # required, non-null — day | week | repo | quarter | year
period_value: 2026-W29          # required alongside period — the concrete instance
                                 # (ISO week, quarter label, etc); pairs with `period`
                                 # for identity + RAG-index structured-record filtering
parent_goal_id: null            # present-as-null-when-absent; links a
                                 # weekly-goal-artifact to its parent initiative
schema: goal
```

**`period` + `period_value` are a required pair, not `period` alone.** `period`
names the cadence (`day | week | repo | quarter | year`); `period_value` pins
the concrete instance (e.g. `2026-W29` for a week, a quarter label for a
quarter). Both are non-null-required by schema — but non-null is not the same
as filter-ready: at scaffold time `period_value` is transiently the literal
sentinel string `"PLACEHOLDER"` until `/workweek-start` Step 7/8 fills the real
value (see § The five collision cells, arbitrated, cell 3). Only a
post-fill `period_value` is a stable filtering key downstream (see § Peer-Repo
Percolation for the RAG-index structured-records use); a consumer that
treats any non-null `period_value` as filter-ready will silently group
not-yet-authored records under the `"PLACEHOLDER"` bucket. Filter/query code
must exclude `period_value == "PLACEHOLDER"` records, matching the enforcement
backstop `coordinator/tests/test_goal_record_governance.py` asserts on
non-scaffold records.

**`id` is the stable canonical identity key.** The RAG index hashes on body content,
so body edits rotate the content hash across reindex. The `id` field gives a
stable, addressable identity that survives KR updates and prose edits.

<!-- Correction: `id` is NOT the same identity chain as the wire `goal_id`. The
     scaffolder's `id: goal-<slug>` facet key and the authored `goal_id:` hint
     field are computed independently from the wire `goal_id` that
     `append-goal-event.py` derives itself at emit time (sha1 of
     repo|root|period|period_value|text — see § Emit Pipe below). The two
     are DISTINCT identifiers by design for weekly-authored goals; do not assert or
     rely on them matching byte-for-byte. See the engine-resident
     `coordinator/bin/coordinator-doc-new`'s `_scaffold_goal` goal_id comment for
     the authoritative distinction. -->

**`objective` is the RAG semantic-retrieval surface.** Write it as prose, not
bullet points. This is the primary field the semantic-search embedding operates
over in indexed peer repos.

**`weekly_perceptible` is the VP-Product Reviewer shaping test.** If a KR cannot show observable
movement in a week, it is either a lagging indicator ("later impact") or not a
real Key Result. The `/goal-setting` ceremony uses this as a shaping question,
not a rejection gate — collaborative posture, not a compliance gate.

**Scaffold via `coordinator-doc-new --type goal`.** Hand-authoring frontmatter
is a producer-obligation violation. The scaffolder emits conformant frontmatter
at the correct per-repo root: sibling repos use `$(python3 <engine-root>/coordinator/lib/coordinator-state-root.py)/goals/`;
the doctrine-authoring repo uses `$(python3 <engine-root>/coordinator/lib/coordinator-state-root.py --central --subject doctrine)/goals/`.

**Weekly-goal-artifact authoring path.** A `period: week` goal is a first-class
`state/goals/*.yaml` artifact like any other — scaffolded the same way, same
schema, same emit pipe — distinguished only by its `period` value and (usually)
a populated `parent_goal_id` pointing at the initiative-level goal it ladders
up to. `/workweek-start` is the natural authoring moment: set the week's goal(s)
alongside priorities, each carrying `parent_goal_id` where a parent initiative
goal exists.

**`/workweek-start` Step 5 authors the week's goal(s); `/workweek-complete`
Step 1c reads them back.** Step 5 invokes the `--type goal` scaffolder to
author each weekly priority as a `period: week` goal artifact, auto-populating
`period`, `period_value`, `weekly_perceptible`, and `goal_id` — the PM/EM do
not hand-fill these. The output filename is session-disambiguated (so two
weekly-start sessions in the same ISO week don't collide on one artifact path).
`HEADER.priorities` becomes the rendered index over these artifacts, not a
separate freeform list. At the other end of the week,
`/workweek-complete` Step 1c reads directly from the `state/goals/*.yaml`
artifacts (not from `HEADER.priorities` prose) to close the loop — the
artifact is the source of truth for both start and completion ceremonies.

**`parent_goal_id` links a goal to its parent initiative goal.** It is
present-as-null-when-absent (never dropped) so the emit pipe and downstream
consumers can distinguish "no parent" from "field not yet populated." A
top-level initiative goal typically carries `parent_goal_id: null`; a
`period: week` goal spawned under it carries the initiative goal's `id`.

**Coverage sweep.** `goal-coverage-scan` (read-only, no write handles, no
`--output`/`--out`) reads active goals plus any `origin_goal_id`-tagged
artifacts and emits a per-goal coverage count, flagging zero-coverage active
goals. `/workweek-start` surfaces the result after priorities are set,
proposing a stub spinoff per zero-coverage goal — propose-only, PM-gated.

**Why the format changed (already-non-constraint, not a pending gap).** Goal
artifacts were originally `.md` with YAML frontmatter because, at authoring
time, the RAG index's `.yaml` chunker gave plain YAML files a single blob
embedding with no prose-section granularity — a real retrieval-quality cost.
That constraint is now historical: the index confirmed YAML retrieval parity
some time later, so the artifact shape no longer needs to work around a
chunker limitation. Goals moved to pure `.yaml` precisely because the
original reason to avoid it no longer holds.

---

## The Ceremony Ladder

The goals/OKR system sits at the top rung of a **horizon-keyed ceremony ladder**.
`/shape` converges on the problem (the PRD half), then routes upward to the
altitude-appropriate ceremony by the work's time horizon:

```
/shape  (converge on the problem; ratify a problem-set)
   ├─→ /goal-setting     (horizon: initiative — weeks-to-quarters)  creates goals, spawns roadmap stubs
   ├─→ /roadmap-planning (horizon: week — roughly a week)           understands target, spawns plan stubs
   └─→ /plan             (horizon: session — a session or two)      spawns executor chunks
```

A PM writing `estimated_horizon` must use the enum value
(`session|week|initiative`), not the prose description above — the values
match the transition routing table in the `/shape` skill body.

**Each rung spawns the artifacts of the rung below.** Goal-setting spawns
`spinoff-roadmap-creator` stubs; roadmap-planning consumes those and spawns
`spinoff-roadmap` plan-seeds; plan/execute authors chunks. The ceremony ladder
is a decomposition ladder, not just a labeling convention.

**`/shape` is the altitude-router.** At problem-set ratification, `/shape` reads
the `estimated_horizon` field (problem-set frontmatter: `session | week | initiative`)
and routes to the right rung with an explicit EM/PM confirm — detect-then-confirm,
never a silent rung pick. A wrong-altitude route is costly rework; the confirm
preserves the `/shape` invariant ("no solutioning inside `/shape` until the
problem-set is ratified").

### Deferred-baton fan-out at weeks–quarters

When horizon = weeks–quarters and the vision decomposes into multiple goal-slices,
`/shape` (and `/goal-setting` itself) can fan out **1→N `spinoff-goal` stubs**
simultaneously rather than chaining into a single ceremony. Each stub is a
captured vision-slice; each is independently actioned (pickup → `/goal-setting`
fleshes that slice into a full `state/goals/*.yaml` artifact).

### The four spinoff kinds

All ladder-rung stubs coexist in `state/handoffs/`, discriminated by `kind:`:

| `kind` | Lifecycle role | Produced by | Consumed by |
|---|---|---|---|
| `spinoff-goal` | Deferred-baton INPUT — raw vision-slice awaiting the goal-setting ceremony | `/shape` or `/goal-setting` (1→N fan-out) | `/goal-setting` (fleshes into `state/goals/*.yaml`) |
| `spinoff-roadmap-creator` | Actioned → runs `/roadmap-planning`, creates a roadmap | `/goal-setting` (one per roadmap-worth-of-work) | `/roadmap-planning` |
| `spinoff-roadmap` | Plan-seed output of roadmap-planning | `/roadmap-planning` | `/plan` / `/execute-plan` |
| `spinoff` | General task-birthed fork (pre-existing) | Various | Various |

**`spinoff-goal` is the baton INPUT; `state/goals/*.yaml` is the ceremony OUTPUT.**
These are distinct lifecycle stages — the baton captures deferred intent and
triggers the ceremony at pickup; the goal artifact is the formed objective+KRs
that emerge from the ceremony. Do not conflate them.

**No per-rung folders.** All four kinds coexist in `state/handoffs/`. The `kind`
key is the discriminator; `query-records --type handoff --where "kind=spinoff-goal"`
filters correctly.

---

## The Goal-Setting Ceremony (`/goal-setting`)

**Entry is vision-shaped, not OKR-shaped.** Users arrive with raw vision —
UI-UX sketches, a feature wishlist, enthusiasm — not a formed Objective+KRs.
The ceremony's front door meets them there; EM + the VP-Product Reviewer help *convert vision →
measurable goals*. OKR shape is the exit, not the entry ticket.

**Posture:** neither obsequious rubber-stamp nor idea-crushing gate. The stance
is *"let's put enough definition on this that we can win at it together"* —
the human-facing analog of the `design-as-offers` / `eager-agent-calibration`
ethos: lead with the better path, not the violation.

### Ceremony flow

1. **PM states objective + candidate KRs** — raw vision, not necessarily
   well-formed.
2. **Dispatch the VP-Product Reviewer** (`Agent subagent_type:"coordinator:vp-product"`, Opus) as
   full OKR critic:
   - Is this a real Objective (aspiration, not a task)?
   - Are these real Key Results (measurable outcomes, not outputs)?
   - Is the *set* reasonable (not 15)?
   - **Weekly-perceptibility test per KR** — "how would we see this move week to
     week?" Not a rejection gate; a shaping question. KRs with no weekly signal
     are reclassified as "later impact."
3. **EM + PM integrate the VP-Product Reviewer's critique in-dialogue** — the goal artifact does not
   yet exist on disk; the converged shape is written into the artifact at scaffold
   time (not via review-integrator machinery, because the artifact doesn't exist
   yet).
4. **Scaffold goal artifact(s)** via `coordinator-doc-new --type goal`.
5. **Spawn `spinoff-roadmap-creator` stubs** pre-tagged to the goal (one per
   roadmap-worth-of-work the goal implies).
6. **Optionally fan out 1→N `spinoff-goal` stubs** for additional goal-slices
   identified during the ceremony but not yet fleshed — captured vision-slices
   for future goal-setting pickup sessions.
7. **Offer** (PM-gated) to chain into `/roadmap-planning`. The skill offers;
   it does NOT auto-run roadmap-planning.
8. **Commit** goal artifacts + stubs.

**HARD CONSTRAINT:** The skill spawns roadmap *stubs* (seeds for
`/roadmap-planning`) and *offers* the PM-gated chain. It does NOT auto-author
roadmap plans or bypass the roadmap-planning PM gate.

### Entry points

- **Direct invocation** — PM arrives with raw vision.
- **Pickup from `spinoff-goal`** — a deferred-baton stub is actioned, triggering
  a goal-setting session that fleshes the captured vision-slice.

---

## Initiative → Goals Ladder

Initiatives carry a `goals` field (a many-to-many list of goal-ids) in
`initiative.schema.json`. A single initiative may serve multiple goals; a single
goal may be served by multiple initiatives.

**Bottom-up offer (non-blocking).** A PostToolUse hook
(`hooks/scripts/nudge-initiative-goals-ladder.py`) fires when an initiative is
written without a `goals` field and ≥1 goal exists in the repo. It emits an
exit-2 advisory (non-blocking) listing candidate goal-ids from the
`goal.match_candidates` engine op (COMPUTE_ONLY):

> *"This initiative isn't laddered — did you mean to tag `g-legibility` or
> `g-runtime-tooling`? `coordinator-initiative attach --goals …`"*

The advisory leads with the better alternative (offer-shape), never with the
violation (friction-as-warning). It does NOT block initiative authoring — the
`design-as-offers` ethos applies throughout.

**Client implementation:** `coordinator/hooks/scripts/nudge-initiative-goals-ladder.py`
calls the `goal.match_candidates` op in-process (import + direct handler
invocation) — no bash veneer script; the historical
`resolve-goal-candidates.sh` shell-out client was retired once the hook itself
was ported to naked Python.

---

## Weekly KR Re-assessment

**Slot:** workweek-complete Step 4.5 (between Step 4 triage and Step 4b).

The engine-resident `coordinator/bin/reassess-goal-krs` reads **existing signal only** — no new
instrumentation. Signal sources:

- `bin/query-completions.py --since <week-start>`
- `bin/query-records.js --type handoff`
- the week-changelog header file

For each `state/goals/*.yaml` artifact, the script:

1. Reads current KR statuses from YAML frontmatter.
2. Scans existing signal for movement evidence.
3. Proposes a per-KR status update + a `perceptible_movement: yes|no` flag.
4. KRs with `weekly_perceptible: true` AND `no` movement are flagged as
   *"maybe-not-a-goal — no perceptible movement this week."*
5. Writes the proposed status back to the artifact for EM/PM confirmation —
   not a silent auto-set.
6. Then invokes the emitter (`emit-goal-from-artifact.py`) to push the updated
   state through the cockpit pipe.

The step is **advisory, non-blocking** — it does not gate the weekly release.

**Ceiling: `reassess-goal-krs` can never propose a terminal status.** Its only transition is
`not-started -> in-progress`; `in-progress` echoes itself and every other status passes through
unchanged (the per-KR routine initializes its proposal to the current status and has exactly one
branch below that). It therefore cannot propose `met`, `at-risk`, or `missed`, and no amount of
movement signal will make it do so. This is by design, not a defect: leaving a KR is a judgement
call, so **every terminal KR transition is authored by the EM/PM directly into
`key_results[].status`, permanently** — the reassessment surface assists the entry half of a KR's
life and has nothing to say about its exit. A repo that infers otherwise from step 3's "proposes a
per-KR status update" wording will build a confirmation flow for a proposal that never arrives.

---

## Emit → Cockpit → Cockpit Pipe

> **Phase-ship note (historical — a later phase has since landed).** `emit-goal-from-artifact.py`
> and `append-goal-event.py` were originally deferred components at authoring time; a follow-up
> plan closed that gap and the cockpit-contract's wire `Goal` entity picked up the fields that
> deferral had left out (see the version-bump note below). The pipe below is current
> architecture, not a forward-looking target.

Goals flow into the fleet dashboard via the existing cockpit pipe:

```
state/goals/*.yaml
    │
    └─→ emit-goal-from-artifact.py
            │  (reads frontmatter, maps artifact→wire params)
            │  (subprocess-invokes the single-writer facade)
            ▼
        append-goal-event.py   ← single-writer facade (do NOT bypass)
            │
            ▼
        $(python3 <engine-root>/coordinator/lib/coordinator-state-root.py --central)/goals-log.<machine>.jsonl
            │  (engine-central; ENGINE — do NOT relocate)
            ▼
        engine artifact.emit (sole production emitter)
            │  — the goals SECTION 6 → goals_current collection logic
            │  — ported from the now-retired bash emitter body
            ▼
        cockpit-emission.json (wire Goal entity)
            │
            ▼
        fleet dashboard
```

**`append-goal-event.py` is the single-writer facade.** The emitter
(`emit-goal-from-artifact.py`) invokes it as a subprocess — it does NOT bypass
it with a parallel direct-append. This preserves the single-writer seam the
engine's write-facade convention establishes.

**Goals-log is engine-central (ENGINE — do NOT relocate).** Per-repo *authoring*
(`state/goals/*.yaml`) is local to each repo; the central *emission* path
(`goals-log.<machine>.jsonl` in the engine's state root) must not be moved. This
is the authoring/emission split that respects the ENGINE ruling.

**Identity chain — later-phase target, NOT current weekly-authoring behavior.** This
diagram describes `emit-goal-from-artifact.py` (a later-phase component, see the
phase-ship note above), which is designed to pass the artifact `id` through
verbatim as the wire `goal_id`. **This is distinct from the CURRENT weekly-goal
authoring path** (`/workweek-start` → `append-goal-event.py`):
`append-goal-event.py` independently re-derives its own `goal_id` by hashing
`repo|root|period|period_value|text` at emit time and does NOT substitute a
passed `--goal-id` for the wire value (accepted for forward-compat only). For
`/workweek-start`-authored goals today, the artifact's `id`/`goal_id:` hint
field and the wire `goal_id` are DISTINCT identifiers — a facet key vs. an
independently-hashed wire id — not one identity chain. Do not assert
byte-identity between them.

**Cockpit-contract is `2.13.0`** (a MINOR version bump), adding `weekly_perceptible`,
`parent_goal_id` (present-as-null when absent), and `key_results_status[]`
to the wire `Goal` entity. `InitiativeSummary.goals[]` folds the
initiative→goals ladder edge in alongside the KR-status fields, as part of
this same bump rather than a separate release.

---

## Negative-Spec Block

> Hard-won corrections for future maintainers and agents.

- **Do NOT conflate the artifact schema with the wire schema.** `coordinator/schemas/goal.schema.json`
  (the authored artifact shape) and `coordinator/cockpit-contract/schema/goal.schema.json`
  (the wire entity the dashboard reads) are different artifacts with different owners.
  The emitter maps artifact → wire; it does not merge them.

- **DO write goal artifacts as `.yaml`.** Pure `.yaml` is canonical, superseding
  the earlier `.md`+frontmatter shape. The original rationale for `.md` (the RAG
  index's YAML chunker gave `.yaml` files a single blob embedding with no
  prose-section granularity) is now historical — YAML retrieval parity was
  confirmed some time later. See § Goal Artifact Shape for the full "why the
  format changed" note.

- **Do NOT relocate the goals-log off engine-central.** The goals-log
  (`$(python3 <engine-root>/coordinator/lib/coordinator-state-root.py --central)/goals-log.<machine>.jsonl`) is an ENGINE
  surface owned by the engine. It must not be moved or duplicated into a
  per-repo path.

- **Historical: residual `.md` glob hits after the `.yaml` schema migration — closed, verify
  before citing as live.** A sweep during the `.md` → `.yaml` migration found a live, functional
  `for _f in ${_goals_dir}/*.md` loop in `nudge-initiative-goals-ladder.sh` that would have
  silently gone dark (permanently disabling the initiative-goals-ladder nudge, a quiet no-op
  rather than a loud failure) once goal artifacts became `.yaml`-only. **This is now closed**,
  not open work: the script has since been ported to
  `coordinator/hooks/scripts/nudge-initiative-goals-ladder.py` (see § Initiative → Goals Ladder
  above), which globs `state/goals/*.yaml` correctly. Kept here only as a standing reminder —
  **when repointing a glob-driven format migration, grep for *every* consumer of the old glob
  pattern across the tree, not just the read/write helpers directly touched by the migrating
  chunk** — a live consumer outside the migration's declared scope can silently go dark.

- **Do NOT edit `append-goal-event.py` to implement emission.** `emit-goal-from-artifact.py`
  is a new sibling script that subprocess-invokes the facade. Editing the facade
  itself collides with a companion effort that adds an ENGINE-classification comment to
  `append-goal-event.py`.

- **Do NOT auto-run `/roadmap-planning` from the goal-setting skill.** The skill
  spawns roadmap-creator stubs and *offers* the chain; the PM-gate on
  `/roadmap-planning` is not bypassed.

- **Do NOT hard-gate initiative authoring on laddering.** The offer hook is
  non-blocking (advisory, exit-2). A missing `goals` field is not an error.

- **Do NOT create per-rung folders in `state/handoffs/`.** All four `kind` values
  coexist in the same directory. The `kind` key is the discriminator.

- **Do NOT place a reader-first sentinel for the `InitiativeSummary.goals[]`
  field-addition.** It is a MINOR additive bump (see § Emit → Cockpit → Cockpit
  Pipe) — the one-way reader-ready announcement memo path is the correct
  coordination mechanism, not a bilateral hold sentinel. Earlier plan text
  tracked this as a separate version bump; that number was superseded when
  the field landed folded into the current one.

---

## Write-Owner-Per-Field (Goal/KR Records)

Goal/KR records (`state/goals/*.yaml`) are a **multi-writer artifact** — the goal-setting
ceremony, `/workweek-start` Step 7, `/workweek-complete` Step 1c, the `--type goal` scaffolder,
and the engine-resident `reassess-goal-krs` / `emit-goal-from-artifact.py` / `append-goal-event.py`
can all touch a record over its lifetime, and none of them is confined to a distinct file the way
sibling fields are on the run-report sidecar (a comparable multi-writer artifact this record's
per-field table generalizes from). This section is the per-field table that role split needs
when it can't be had for free by file separation — a new artifact class gets its own typed
write-owner split rather than inheriting a prior artifact's role shape verbatim.

**Field vs. record identity.** `id` and `key_results[].id` are distinct fields that happen to
share a bare name; both are listed below with their `key_results[].` qualifier where the field is
a key-result-item property rather than a top-level one, so the two are never conflated in the
Field column.

| Field | Write owner | Lifecycle phase | Other actors may write? |
| --- | --- | --- | --- |
| `schema` | `coordinator-doc-new --type goal` scaffolder | Scaffold time | No — fixed discriminator, never rewritten |
| `id` | `coordinator-doc-new --type goal` scaffolder | Scaffold time | No — stable canonical identity key |
| `title` | `coordinator-doc-new --type goal` scaffolder | Scaffold time | Goal-setting ceremony, at authoring time |
| `status` (goal-level) | `coordinator-doc-new --type goal` scaffolder writes `active` | Scaffold time (initial); PM/EM thereafter | `/workweek-complete` **reads only** — never writes `status` |
| `objective` | **Collision cell 1** — goal-setting ceremony OR `/workweek-start` Step 7; see § Collision cell 1 below | Authoring time | See below — two authoring actors, arbitrated, not merged |
| `key_results` (array) | Goal-setting ceremony / scaffolder, at KR-authoring time | Authoring time | No independent writer of the container itself — see the seven `key_results[].*` rows for its items (`reassessment_proposal` is its own row) |
| `created` | `coordinator-doc-new --type goal` scaffolder | Scaffold time | No — stamped once |
| `owner` | **Collision cell 5** — orphan field, oaxis-compatible framing; see § Collision cell 5 below | N/A — no fixed phase | See below |
| `period` | Goal-setting ceremony / scaffolder | Authoring time | No |
| `period_value` | **Collision cell 3** — scaffolder emits `"PLACEHOLDER"`; `/workweek-start` Step 7/8 fills the real value | Scaffold time (placeholder) → `/workweek-start` Step 7/8 (real value) | See below |
| `weekly_perceptible` (goal-level) | Scaffolder leaves the line commented out | N/A — no live writer today | None currently populate it; reserved field |
| `parent_goal_id` | Goal-setting ceremony / `/workweek-start`, when a parent OKR exists; otherwise left `null` | Authoring time | No |
| `initiative` | `coordinator-initiative attach --goals` (reverse-edge CLI) | Post-authoring, on ladder attach | No — single CLI path |
| `goal_id` | **Collision cell 4** — scaffolder leaves commented; `append-goal-event.py` independently re-derives its own at emit time | Scaffold time (hint, optional) → emit time (wire value, independent) | See below — deliberately dual-derived, not a bug |
| `key_results[].id` | Goal-setting ceremony / scaffolder, at KR-authoring time | Authoring time | No — stable across reordering (FK survives) |
| `key_results[].text` | **Collision cell 1** — same two actors as `objective`; see below | Authoring time | See below |
| `key_results[].kind` | Goal-setting ceremony | Authoring time | No |
| `key_results[].status` | **Collision cell 2** — scaffolder sets the initial value; `reassess-goal-krs` **proposes** an update, never auto-sets | Authoring time (initial) → weekly reassessment (proposal → confirmation) | See below — the headline defect this table exists to fix |
| `key_results[].weekly_perceptible` | Goal-setting ceremony | Authoring time | No |
| `key_results[].evidence_source` | Goal-setting ceremony | Authoring time; updated as evidence is located | No fixed second writer — EM may update in place as evidence surfaces |
| `key_results[].reassessment_proposal` | `reassess-goal-krs` — **sole writer** of the proposal object | Weekly reassessment (propose) | No. EM/PM act on it by applying `proposed_status` to `key_results[].status` and clearing the object back to `null` — the confirm half of collision cell 2. A non-null value is an unapplied proposal, never a decided one. |

### The five collision cells, arbitrated

1. **`objective` + `key_results[].text` — two authoring actors, incompatible provenance.** The
   goal-setting ceremony writes PM-ratified, the VP-Product Reviewer-critiqued text; `/workweek-start` Step 7 writes
   raw priority text with no critic pass. Both are legitimate writers of the same field — this is
   not a bug to resolve by picking one. The arbitration is: **the record carries no on-disk
   discriminator distinguishing which provenance a given `objective`/`key_results[].text` value
   came from, and none is added here.** A reader that needs to know which quality contract applied
   must trace provenance externally (which ceremony authored the artifact, per its filename/session
   context) — the field itself does not self-report it. Do not infer "critiqued" from the mere
   presence of text.

2. **`key_results[].status` — proposal indistinguishable from confirmation.** This is the defect
   the plan's Problem section names directly: a proposed status and a confirmed one are
   byte-identical on disk today. The fix is schema-level (`goal.schema.json`'s new
   reassessment-proposal object, landing alongside this table) — `reassess-goal-krs` writes its
   proposal into that separate, nested surface, **not** into the live `key_results[].status`
   field. The live field is only ever written by the scaffolder (initial value) or by an explicit
   EM/PM confirmation step that promotes an accepted proposal into it. See § Propose → confirm →
   emit, generalized below for the full protocol this field is the first instance of.

3. **`period_value` — `"PLACEHOLDER"` validates.** The scaffolder emits the literal string
   `"PLACEHOLDER"` for a goal that hasn't reached `/workweek-start` Step 7/8 yet, and the schema's
   bare-string typing (no pattern) accepts it as a valid required field. This is a **known,
   accepted gap** this table does not close — `coordinator/tests/test_goal_record_governance.py`
   asserts `period_value != "PLACEHOLDER"` on non-scaffold records as the enforcement backstop,
   rather than tightening the schema itself. The write-owner split is unambiguous even though the
   validity gap isn't closed here: scaffolder writes the placeholder, `/workweek-start` Step 7/8 is
   the sole subsequent writer of the real value.

4. **`goal_id` — dual derivation is deliberate, not a bug.** The artifact's `id` field and the wire
   `goal_id` that `append-goal-event.py` derives (content-hash over
   `repo|root|period|period_value|text`) are **intentionally independent identifiers**, not two
   copies of one identity chain. A future reader who "fixes" them to match has broken the emission
   pipe's actual contract. The scaffolder-authored `goal_id:` field is a forward-compat hint only
   — `append-goal-event.py` accepts `--goal-id` but does not substitute it for the value it
   computes itself. Write owner: scaffolder (optional hint, commented by default), then
   `append-goal-event.py` (wire value, independently re-derived at every emit — not a one-time
   write).

5. **`owner` — orphan field, authored in owner-axis-compatible terms.** No actor writes `owner`
   today. Rather than leave the cell as a bare "no named writer" (which a sibling plan flipping
   `owner`'s type to nullable would immediately contradict), this table states the rule in the
   terms that sibling plan encodes directly in the type: **`null` = unclaimed — any actor may
   claim the field by writing a non-null value; a non-null value = a named owner, and that owner
   becomes the sole subsequent writer** (last-writer-wins is not the model — a named owner is not
   silently overwritten by a different actor claiming the same field). This cell does not change
   `owner`'s current TYPE — still a plain, non-nullable string type, not yet the nullable type a
   companion contract publication will introduce; note that `owner` is already absent from
   `goal.schema.json`'s top-level `required` array, so no JSON-Schema `required`-array change is
   at stake here, only the write-owner naming this cell adds. The ownership *rule* stated here is
   written so it survives that type change unmodified.

### Propose → confirm → emit, generalized

`key_results[].status` (collision cell 2, above) is currently the only field in this record with a
propose-then-confirm protocol, and until now the protocol existed only as prose narrowly scoped to
that one field (§ Weekly KR Re-assessment above). Stated generally, for any current or future
field on this record that a non-ceremony actor (an engine-resident script, an automated
reassessment, any process that isn't the PM/EM authoring the record directly) wants to update
based on inferred signal rather than direct instruction:

1. **Propose, don't mutate.** The proposing actor writes its candidate value into a field-scoped
   proposal surface distinct from the live field — never directly into the field a reader would
   treat as current truth. (For `key_results[].status`, this surface is the nested
   reassessment-proposal object the schema now carries; a future second instance of this pattern
   gets its own analogous nested surface, not a reuse of this one.)
2. **Confirm, explicitly.** The live field is updated only by an explicit EM/PM confirmation step
   that reads the proposal and promotes it — never by the proposing actor itself, and never
   silently on a schedule. "Silent auto-set" is the failure mode this step exists to prevent.
3. **Emit, after confirmation, not before.** The emit pipe (`emit-goal-from-artifact.py` →
   `append-goal-event.py`) reads the confirmed live field, never the pending proposal surface — a
   proposal that has not yet been confirmed must not reach the wire.

A future writer adding a second inferred-update field to this record should reach for this
three-step shape rather than re-deriving it, and should give its proposal surface the same
strictness discipline (`additionalProperties: false` + `required`) the KR-status proposal object
uses, for the same reason: a permissive proposal object lets a malformed proposal validate
silently, defeating the whole point of separating proposal from confirmation.

---

## Peer-Repo Percolation

When a sibling repo wants to adopt the goals/OKR system:

1. **Goal doc-type auto-registers via the manifest — for live `--plugin-dir` siblings only.**
   `coordinator/schemas/coordinator-registry.manifest.json` carries
   `{type:"goal", schemaName:"goal", isSidecar:false, offerable:true}`. Fleet siblings that
   resolve `coordinator/` live from this repo via `--plugin-dir` get the schema, the
   `coordinator-doc-new --type goal` scaffolder, and the `validate-frontmatter-schema.js`
   guard automatically — no per-repo doc-type wiring needed. **OSS adopters of the published
   `coordinator-claude` mirror do not** — `coordinator/schemas/` is absent from
   `setup/publish-targets.portable`, so the goal schema never reaches the mirror. This is a
   known gap in the OSS publish surface, not intended design.

2. **`state/goals/` is per-repo.** Each sibling maintains its own
   `state/goals/*.yaml` artifacts under its own state root
   (`$(python3 <engine-root>/coordinator/lib/coordinator-state-root.py)/goals/`). There is no
   central cross-repo goal registry (out of scope, ratified constraint). A goal-id from one
   repo is not automatically visible to another.

3. **The emit pipe is already central.** `append-goal-event.py` + the
   `goals-log.<machine>.jsonl` → engine `artifact.emit` (sole production emitter) → the fleet dashboard
   path is owned by the engine and already handles multi-repo emission. A sibling adopting the
   goals system authors `state/goals/*.yaml` locally and invokes `emit-goal-from-artifact.py`;
   the central pipe picks up from there.

4. **The RAG index indexes `.yaml` goals via its YAML chunker.** For repos it indexes,
   `state/goals/*.yaml` files are picked up by the YAML chunker. The `objective` prose body
   and `key_results[].text` fields become semantic-retrieval surfaces on the same terms as any
   other indexed YAML artifact — YAML retrieval parity with the markdown chunker was
   confirmed some time later, so this is not a degraded path. No index-side configuration is
   needed for the artifact type — `.yaml` is already a first-class indexing target. The
   `state/handoffs/` path is explicitly pruned from the semantic index, so `spinoff-goal` /
   `spinoff-roadmap-creator` stubs stored there remain out of the semantic index (as
   intended); they are queryable via the records-SQL relational tier
   (`query-records --type handoff --where "kind=spinoff-goal"`).

5. **`period`/`period_value` + `goal_id` filtering runs through a `[[structured_records]]`
   config entry — zero index-side code.** A config-only path was chosen over an earlier
   candidate that would have added index-side filtering code: a `[[structured_records]]`
   entry in the consuming repo's RAG config declares `period`/`period_value` as
   structured-record filter fields and `goal_id` as the stable identity field, letting the
   existing structured-records machinery do period-scoped and identity-scoped goal lookups
   without any new indexing-engine code. The `id` scaffolder field and the wire `goal_id`
   remain distinct identifiers (see § Goal Artifact Shape) — the structured-records config
   keys on whichever one the repo's config declares, so pick the field deliberately rather
   than assuming which is stable across body edits.

6. **`goal_id` honoring is gated behind a defect ordering — do not wire ceremonies to
   `goal.append` ahead of it.** Two related defects are tracked: **Defect 3** (make
   `goal.append` honour an explicit `goal_id` when supplied, instead of always recomputing by
   content-hash) and **Defect 1** (wire ceremony code to call `goal.append` directly).
   **Defect 3 gates Defect 1** — until Defect 3 lands, wiring Defect 1 will silently duplicate
   every goal in the fleet on first run: the ceremony path and whatever pre-existing path
   already writes goals will content-hash *different* canonical strings for what is
   conceptually the same goal, minting two distinct `goal_id`s instead of one. Any second
   producer of goal records (a new ceremony, a new import path) must hash the *same* canonical
   string the original producer does, or it collides in meaning but not identity.

---

## Companion Doctrine

- Ceremony-calibration doctrine — when to invoke heavyweight ceremony
- Spinoff-handoffs doctrine — spinoff kinds, predecessor semantics, exemption list
- Canonical-artifact-shapes doctrine — artifact shape doctrine, warn-not-block enforcement
- Cockpit-contract entity-addition protocol — field-addition track
- Eager-agent-calibration doctrine — offer-shape vs friction-as-warning
- State-placement-law doctrine — per-repo vs central-state routing rules
