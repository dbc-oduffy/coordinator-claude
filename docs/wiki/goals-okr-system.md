---
title: "Goals / OKR system"
created: 2026-07-07
status: active
spec_backlink: docs/plans/2026-07-06-goal-setting-okr-legibility-system.md
---

# Goals / OKR System

> **Purpose.** The goals/OKR system turns the PM's strategic intent from an
> unrecorded mental model into first-class per-repo artifacts that the EM,
> ceremony ladder, and cockpit dashboard can all point at. It answers "what
> larger objective does this initiative serve, and are we winning?" at any point
> in the workstream.

**Spec backlink:** `docs/plans/2026-07-06-goal-setting-okr-legibility-system.md`

---

## Goal Artifact Shape

Goal artifacts live at `state/goals/<slug>.md` (per-repo). They are
**Markdown files with YAML frontmatter** — not `.yaml` files. The format is
load-bearing: `.md` with frontmatter uses the markdown chunker's section
splitting and frontmatter-key enrichment, giving project-rag the prose body as
a semantic-retrieval surface. A plain `.yaml` file gets a single blob embedding
with no section granularity.

### YAML Frontmatter

```yaml
id: goal-<repo>-<slug>          # required; stable canonical identity key
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
period: null                    # nullable — day | week | initiative
schema: goal
```

**`id` is the stable canonical identity key.** project-rag hashes on body content,
so body edits rotate the content hash across reindex. The `id` field gives a
stable, addressable identity that survives KR updates and prose edits. It is
also the `goal_id` emitted on the cockpit wire and returned by the
`goal.match_candidates` engine op — one identity chain end-to-end (see
§ Emit Pipe below).

**`objective` is the RAG semantic-retrieval surface.** Write it as prose, not
bullet points. This is the primary field the semantic-search embedding operates
over in indexed peer repos.

**`weekly_perceptible` is the VP-Product Reviewer shaping test.** If a KR cannot show observable
movement in a week, it is either a lagging indicator ("later impact") or not a
real Key Result. The `/goal-setting` ceremony uses this as a shaping question,
not a rejection gate — collaborative posture, not a compliance gate.

**Scaffold via `coordinator-doc-new --type goal`.** Hand-authoring frontmatter
is a producer-obligation violation. The scaffolder emits conformant frontmatter
at the correct per-repo root: sibling repos use `$(coordinator_state_root)/goals/`;
the DoE meta-repo uses `$(coordinator_state_root --central --subject doctrine)/goals/`.

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
<!-- Review: code-reviewer F12 — added frontmatter enum values (session|week|initiative) alongside
     natural-language descriptions; a PM writing estimated_horizon must use the enum value, not the
     prose description. -->
<!-- Review: code-reviewer F12 — values match shape/SKILL.md § Transition routing table -->

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
fleshes that slice into a full `state/goals/*.md` artifact).

### The four spinoff kinds

All ladder-rung stubs coexist in `state/handoffs/`, discriminated by `kind:`:

| `kind` | Lifecycle role | Produced by | Consumed by |
|---|---|---|---|
| `spinoff-goal` | Deferred-baton INPUT — raw vision-slice awaiting the goal-setting ceremony | `/shape` or `/goal-setting` (1→N fan-out) | `/goal-setting` (fleshes into `state/goals/*.md`) |
| `spinoff-roadmap-creator` | Actioned → runs `/roadmap-planning`, creates a roadmap | `/goal-setting` (one per roadmap-worth-of-work) | `/roadmap-planning` |
| `spinoff-roadmap` | Plan-seed output of roadmap-planning | `/roadmap-planning` | `/plan` / `/execute-plan` |
| `spinoff` | General task-birthed fork (pre-existing) | Various | Various |

**`spinoff-goal` is the baton INPUT; `state/goals/*.md` is the ceremony OUTPUT.**
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
(`hooks/scripts/nudge-initiative-goals-ladder.sh`) fires when an initiative is
written without a `goals` field and ≥1 goal exists in the repo. It emits an
exit-2 advisory (non-blocking) listing candidate goal-ids from the
`goal.match_candidates` engine op (example-orchestration-hub-owned, COMPUTE_ONLY):

> *"This initiative isn't laddered — did you mean to tag `g-legibility` or
> `g-runtime-tooling`? `coordinator-initiative attach --goals …`"*

The advisory leads with the better alternative (offer-shape), never with the
violation (friction-as-warning). It does NOT block initiative authoring — the
`design-as-offers` ethos applies throughout.

**DoE-side client:** `coordinator/bin/resolve-goal-candidates.sh` shells the
`goal.match_candidates` op via `coordinator_core/client`, mirroring the
`resolve-initiative.sh` pattern for `initiative.serve_set`.

---

## Weekly KR Re-assessment

**Slot:** workweek-complete Step 4.5 (between Step 4 triage and Step 4b).

`bin/reassess-goal-krs.sh` reads **existing signal only** — no new
instrumentation (OOS #1 from the problem-set). Signal sources:

- `bin/query-completions.sh --since <week-start>`
- `bin/query-records.js --type handoff`
- `state/week-changelog/HEADER.md`

For each `state/goals/*.md` artifact, the script:

1. Reads current KR statuses from YAML frontmatter.
2. Scans existing signal for movement evidence.
3. Proposes a per-KR status update + a `perceptible_movement: yes|no` flag.
4. KRs with `weekly_perceptible: true` AND `no` movement are flagged as
   *"maybe-not-a-goal — no perceptible movement this week."*
5. Writes the proposed status back to the artifact for EM/PM confirmation —
   not a silent auto-set.
6. Then invokes the emitter (`emit-goal-from-artifact.sh`) to push the updated
   state through the cockpit pipe.

The step is **advisory, non-blocking** — it does not gate the weekly release.

---

## Emit → Cockpit → Cockpit Pipe

<!-- Review: code-reviewer F10 — phase-ship annotation added; emit scripts land in Phase 2, not Phase 1 -->
> **Phase-ship note:** `emit-goal-from-artifact.sh` and `append-goal-event.sh` are **Phase 2** components
> (plan `2026-07-06-goal-setting-okr-legibility-system.md` § Phase 2). Phase 1 ships the authoring
> surface (`state/goals/*.md`, goal-setting skill, OKR schema, KR re-assessment). The pipe diagram
> below documents the target architecture — these scripts do not yet exist in Phase 1 installs.

Goals flow into the cockpit dashboard via the existing cockpit pipe:

```
state/goals/*.md
    │
    └─→ emit-goal-from-artifact.sh
            │  (reads frontmatter, maps artifact→wire params)
            │  (subprocess-invokes DR-210 single-writer facade)
            ▼
        append-goal-event.sh   ← DR-210 single-writer facade (do NOT bypass)
            │
            ▼
        $(coordinator_state_root --central)/goals-log.<machine>.jsonl
            │  (example-orchestration-hub-central; ENGINE — do NOT relocate)
            ▼
        example-orchestration-hub artifact.emit (sole production emitter, DR-208/DR-210)
            │  — the goals SECTION 6 → goals_current collection logic
            │  — ported from the now-retired bash emitter body
            ▼
        cockpit-emission.json (wire Goal entity, v2.7.0+)
            │
            ▼
        cockpit dashboard
```

**`append-goal-event.sh` is the DR-210 single-writer facade.** The emitter
(`emit-goal-from-artifact.sh`) invokes it as a subprocess — it does NOT bypass
it with a parallel direct-append. This preserves the single-writer seam that
DR-210 consolidated.

**Goals-log is example-orchestration-hub-central (ENGINE — do NOT relocate).** Per-repo *authoring*
(`state/goals/*.md`) is local to each repo; the central *emission* path
(`goals-log.<machine>.jsonl` in example-orchestration-hub's state root) must not be moved. This
is the authoring/emission split that respects the ENGINE ruling.

**Identity chain:** the artifact `id` field == the wire `goal_id` emitted by
`emit-goal-from-artifact.sh` == the `goal_id` returned by `goal.match_candidates`
== cockpit's `(kind, id)` composite node key. One identity chain. The emitter
passes the artifact `id` as `goal_id` on the wire; it does not generate a new
id at emit time.

**No cockpit-contract version bump for goal-level emission.** The emitter rides
the existing v2.7.0 wire `Goal` entity + SECTION 6 → `goals_current` → cockpit.
The `InitiativeSummary.goals[]` array (Phase 2 of the plan, v2.8.0 MINOR bump)
adds the initiative→goals ladder edge to the dashboard — that is a separate
MINOR field-addition per DR-204/D21.

---

## Negative-Spec Block

> Hard-won corrections for future maintainers and agents.

- **Do NOT conflate the artifact schema with the wire schema.** `coordinator/schemas/goal.schema.json`
  (the authored artifact shape) and `coordinator/cockpit-contract/schema/goal.schema.json`
  (the wire entity cockpit reads) are different artifacts with different owners.
  The emitter maps artifact → wire; it does not merge them.

- **Do NOT write goal artifacts as `.yaml`.** project-rag's YAML chunker gives
  `.yaml` files a single blob embedding with no prose-section granularity. Goals
  require the Markdown chunker's frontmatter-key enrichment + section splitting
  for useful semantic retrieval. Always `.md` with YAML frontmatter.

- **Do NOT relocate the goals-log off example-orchestration-hub-central.** The goals-log
  (`$(coordinator_state_root --central)/goals-log.<machine>.jsonl`) is an ENGINE
  surface owned by example-orchestration-hub (the Director of Engineering F2 / Plan D ruling). It must not be moved or
  duplicated into a per-repo path.

- **Do NOT edit `append-goal-event.sh` to implement emission.** `emit-goal-from-artifact.sh`
  is a new sibling script that subprocess-invokes the facade. Editing the facade
  itself collides with Plan D (which adds an ENGINE-classification comment to
  `append-goal-event.sh`).

- **Do NOT auto-run `/roadmap-planning` from the goal-setting skill.** The skill
  spawns roadmap-creator stubs and *offers* the chain; the PM-gate on
  `/roadmap-planning` is not bypassed.

- **Do NOT hard-gate initiative authoring on laddering.** The offer hook is
  non-blocking (advisory, exit-2). A missing `goals` field is not an error.

- **Do NOT create per-rung folders in `state/handoffs/`.** All four `kind` values
  coexist in the same directory. The `kind` key is the discriminator.

- **Do NOT place a v2.8.0 reader-first sentinel for the `InitiativeSummary.goals[]`
  field-addition.** It is a MINOR additive bump per DR-204/D21 — the one-way
  reader-ready announcement memo path (C12) is the correct coordination mechanism,
  not a bilateral hold sentinel.

---

## Peer-Repo Percolation

When a sibling repo (example-game-repo, project-rag, etc.) wants to adopt the goals/OKR
system:

1. **Goal doc-type auto-registers via the manifest.** `coordinator/schemas/coordinator-registry.manifest.json`
   carries `{type:"goal", schemaName:"goal", isSidecar:false, offerable:true}`.
   Any repo that percolates the coordinator plugin obtains the schema, the
   `coordinator-doc-new --type goal` scaffolder, and the `validate-frontmatter-schema.js`
   guard automatically — no per-repo doc-type wiring needed.

2. **`state/goals/` is per-repo.** Each sibling maintains its own
   `state/goals/*.md` artifacts under its own state root
   (`$(coordinator_state_root)/goals/`). There is no DoE-central cross-repo goal
   registry (OOS, ratified constraint). A goal-id from one repo is not
   automatically visible to another.

3. **The emit pipe is already central.** `append-goal-event.sh` + the
   `goals-log.<machine>.jsonl` → example-orchestration-hub `artifact.emit` (sole production emitter,
   DR-208/DR-210) → cockpit path is owned by coordinator/example-orchestration-hub and already
   handles multi-repo emission.
   A sibling adopting the goals system authors `state/goals/*.md` locally and
   invokes `emit-goal-from-artifact.sh`; the central pipe picks up from there.

4. **project-rag indexes `.md` goals automatically.** For repos indexed by
   project-rag, `state/goals/*.md` files with YAML frontmatter are picked up by
   the markdown chunker. The `objective` prose body and `key_results[].text`
   fields become semantic-retrieval surfaces. No rag-side configuration is needed
   for the new artifact type — `.md` with frontmatter is already a first-class
   indexing target. The `state/handoffs/` path is explicitly pruned from the
   semantic index, so `spinoff-goal` / `spinoff-roadmap-creator` stubs stored
   there remain out of the semantic index (as intended); they are queryable via
   the records-SQL relational tier (`query-records --type handoff --where "kind=spinoff-goal"`).

---

## Companion Doctrine

- `coordinator/docs/wiki/ceremony-calibration.md` — when to invoke heavyweight ceremony
- `coordinator/docs/wiki/spinoff-handoffs.md` — spinoff kinds, predecessor semantics, exemption list
- `coordinator/docs/wiki/canonical-artifact-shapes.md` — artifact shape doctrine, warn-not-block enforcement
- `coordinator/docs/wiki/cockpit-contract-entity-addition-protocol.md` — DR-204/D21 field-addition track
- `coordinator/docs/wiki/eager-agent-calibration.md` — offer-shape vs friction-as-warning
- `coordinator/docs/wiki/state-placement-law.md` — per-repo vs central-state routing rules
- `docs/plans/2026-07-06-goal-setting-okr-legibility-system.md` — plan with substrate map, chunk details, acceptance criteria
