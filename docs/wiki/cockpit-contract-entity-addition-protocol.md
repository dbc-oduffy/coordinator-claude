---
title: "Cockpit-contract entity-addition protocol"
created: 2026-06-30
updated: 2026-07-19
status: active
spec_backlink: docs/decisions/DR-167-cockpit-contract-standing-owner.md
---

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-06/2026-06-27-emit-new-record-types-producer-wiring.md, archive/specs/2026-06/cockpit-contract-ext-research-corpus/consumer-render-needs.md, archive/specs/2026-06/cockpit-contract-ext-research-corpus/contract-amendment-mechanics.md, 2026-06-22-cockpit-tc-3-coordinator-emission.md, 2026-06-24-cockpit-cockpit-contract-reshape.md, archive/specs/2026-06/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md, 2026-07-17-example-cockpit-repo-em-dr047-execution-handoffs-accept.md -->


# Cockpit-Contract Entity-Addition Protocol

> **Purpose.** Adding an emission entity type (or new fields to existing entities) in
> `cockpit-emission.json` is governed because cockpit's ingest gates the snapshot's
> `schema_version` against its vendored `CONTRACT_VERSION`. **Read the actual gate before
> reasoning about blast radius** — `checkSchemaVersion` in
> `example-cockpit-repo/src/lib/store/ingest.ts:164-199` (NOT the older `assertSchemaVersion`/`:76-98`
> name some docs still cite). It **throws only on** (a) a missing/malformed `schema_version`,
> or (b) a **MAJOR** mismatch in *either* direction. **Same-major, higher-minor/patch is
> ACCEPTED** — it warns, records a skip, and ignores unknown top-level entity arrays
> (`ingest.ts:185-199`). So the outage-class case is a **MAJOR** bump (e.g. 2.x → 3.0): a
> production emit that races ahead of a consumer re-vendor crashes cockpit's ingest for all
> reads. A **minor/patch additive bump** (new entities, new nullable fields, widened enum) does
> **NOT** crash cockpit — it accepts the snapshot and ignores the not-yet-vendored arrays, the
> same graceful-degradation rag provides. This protocol governs every entity addition and
> field-set extension: who does what, in what order, and why concurrent bumps are banned. The
> reader-first hold below is *unconditional for major bumps*; for minor/patch additive bumps
> there is **no hold at all** — the owner emits immediately and fires a one-way reader-ready
> announcement memo (§ Step g), never a wait-for-confirm gate. This is coordination, not an
> outage-prevention necessity — outage risk is the reason the major path holds; its absence is
> why the minor path doesn't.
> The crash-safety rationale for minor bumps is retired by consumer choice — reversible if a
> future consumer re-strictens (hence the consumer-capability census in Step g). Spec backlink
> for the field-addition pattern, provenance `ref` ref-conditional convention, and v2.4.0
> example row: `docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md`.
>
> **Producer-identity note (claude-klabauter DR-208/DR-210):** claude-klabauter's Python `artifact.emit`
> is the **sole production cockpit emitter**. `coordinator/bin/emit-cockpit-snapshot.sh`
> is a fail-loud facade stub — its body lives in claude-klabauter now and is not
> present at the line numbers this doc cites below (SECTION templates, sentinel-guard
> lines, `FINAL_JSON` wiring, etc.). Those citations describe the **pre-port bash
> procedure** and are retained for historical/structural reference only — treat any
> `emit-cockpit-snapshot.sh:NNN` line citation below as **stale** pending a follow-up
> rewrite of Step (e) against the Python port (`coordinator_core/ops/emit/`, per
> `cross-repo/archive/` claude-klabauter DR-208/DR-210 ratification). Out of scope for this repoint pass
> (`docs/plans/2026-07-08-retire-js-cockpit-emitter-lockstep.md` § C7) — flagged, not
> rewritten, here.

---

## D9 Nullability Discipline (Canonical Rule)

**D9 is the governing rule for ALL nullable fields in the emission class.** Every
nullable field uses Zod `.nullable()` with the key present-as-null (listed in `required[]`
with `anyOf:[T,null]` in JSON Schema) — never key-absent.

```typescript
// CORRECT (D9): key present, carrying null when uncomputed.
deliverable_id: z.string().nullable(),
// JSON Schema required[] includes "deliverable_id"; anyOf:[{type:string},{type:null}]
```

**The `.nullable().optional()` exception (D13) is for exactly two fields** —
`additional_predecessors` and `forked_from` on `HandoffSummary`
(`cockpit-contract/src/entities/summaries.ts:138,147`) — and is **NOT generalizable**.
Those two fields are absent from `required[]` and may be key-absent on the wire.
Every other nullable field uses D9.

**Why this distinction matters.** The rag ingest store (`tc-5`) inserts a value for
every column on every row — absent-vs-null ambiguity breaks the column model. D9
present-as-null eliminates that ambiguity. D13 exists only for fields that must
express the `"not set at all"` state distinctly from `null`; the two `HandoffSummary`
lineage fields have that semantic. New fields do NOT inherit the D13 exception by
proximity — always use D9 unless the field's contract explicitly requires key-absence.

**Derived fields (emit-computed)** follow D9 naturally: `last_meaningful_activity`,
`deliverable_status`, `shipped_sha`, `workstream_type` are computed-or-null at emit time;
the key is always present, carrying `null` when the derivation cannot produce a value.

---

## Provenance `ref` Ref-Conditional Convention (Source A / D1)

`ProvenanceEnvelope.ref` (`cockpit-contract/src/provenance.ts`) is a structured
`{ branch, sha }` object (not a flat string) subject to a **bidirectional conditional**
enforced by `.superRefine()` in Zod and hand-injected `allOf if/then` at every
JSON-Schema inline site in both emitters:

| `source_kind` | `ref` requirement |
|---|---|
| `github_graphql` / `github_rest` | `ref` MUST be non-null (git-backed, branch + SHA available) |
| `local_fs` / `coordinator_artifact` | `ref` MUST be null (no git ref at observation time) |

`.nullable()` is used on `ref` because it is present-as-null for non-git sources
(D9 discipline: key always present) — it is **not optional**. The `.superRefine()`
enforces the closed mapping as a runtime Zod refinement; the JSON-Schema side uses
`allOf if/then` blocks injected by the emitter because JSON Schema 2020-12 `if/then`
is the portable conditional equivalent of Zod `.superRefine()`.

**Emitter convention when injecting the ref-conditional at JSON Schema sites.** The
emitter appends an `allOf` clause alongside the `$ref` that resolves the
`ProvenanceEnvelope` inline type. Do not replicate this in individual entity schemas —
the Zod `.superRefine()` at the `ProvenanceEnvelope` definition level is the canonical
enforcement; the JSON-Schema injection is a documentation mirror for downstream
consumers (cockpit, rag) that validate against the bundle.

**Do NOT touch `provenance.ts` or the `.superRefine()` block** when adding new
entities or fields. The ref-conditional is a settled Source A contract. Future
`source_kind` values that are git-backed must be added to the `isGitBacked` guard in
the `.superRefine()` and in the JSON-Schema `if/then` — that is a governed change, not
a silent addition.

**`observed_at` lives on `provenance`, not the top-level envelope.** The emission
envelope's own timestamp field is `emitted_at` (when the snapshot was assembled). Each
individual *record's* observation time is `provenance.observed_at` — a per-record field,
not a sibling of `emitted_at`. Do not add a new top-level `observed_at` when a field's
intent is "when was this record's data actually observed" — that's `provenance.observed_at`
on the entity itself. <!-- src: plan24-019 -->

**When choosing a join key for a new relational field, reuse an existing identity field
before minting a synthetic one.** E.g. `ReviewTrail`'s join to handoffs uses `workstream`
(already present on `HandoffSummary`) rather than a synthetic `handoff_fk` — cheaper for
the producer to compute and matches how downstream consumers already key their own
views. Prefer the field a peer entity already carries over inventing a new relational
identifier. <!-- src: plan24-008 -->

---

## Owner vs. Contributor Split

The **cockpit-contract surface** is a standing single owner of record (codified in
`docs/decisions/DR-167-cockpit-contract-standing-owner.md`). The surface comprises:

- claude-klabauter's Python `artifact.emit` — the records-spine → `cockpit-emission.json`
  projection step (sole production emitter as of claude-klabauter DR-208/DR-210).
  `plugins/coordinator/bin/emit-cockpit-snapshot.sh` remains on disk
  as a fail-loud facade stub (zero caller repoints, claude-klabauter DR-210 AC8) but is not an independent
  producer — see producer-identity note above.
- `plugins/coordinator/cockpit-contract/` — the entity definitions,
  schema bundle, and TypeScript contract package.

**What the owner does:** lands entity additions, runs version bumps, wires the entity
into the emitter (Step (e), pending Python-port rewrite — see producer-identity note
above), operates the reader-first handshake.

**What contributors do:** define the entity shape (Zod schema + TypeScript type) in a
branch and hand over to the owner. Contributors do **not** independently edit
`CONTRACT_VERSION`, regenerate the schema bundle, or run the production emit. This
split exists because cockpit's ingest is version-gated: two independent bumps landing
out of sequence would crash the reader during the gap (the double-bump/outage hazard).

The `CONTRACT_VERSION` bump is enforced by convention and the reader-first sentinel at
emit time, NOT by a mechanical guard on the edit itself. The owner verifies that no
contributor branch carries a stray bump before merge.

*Contributor workstreams that have handed over:* ccos tc-8 (records-spine entities);
the decision-guide inbound ask. Future contributors follow the same pattern.

---

## Two-Contract Decomposition (Surface A vs. Surface B)

<!-- src: plan27-010, plan27-023 -->

**"The cockpit contract" is one of TWO independently-versioned contracts** — do not
conflate them when scoping a change or deciding which `CONTRACT_VERSION` to bump:

- **Surface A — the records contract** (`artifact-shape-contract`, historically called
  the "records-contract"). Governs `query-records.js`-indexed frontmatter records
  (handoffs, plans, decisions, roadmaps, etc.) independent of any cockpit consumer.
  Additive changes here (new record kind, glob-pattern fix, new optional field) are
  backward-compatible for record-shape consumers (project-rag, example-repo) — no
  `assertSchemaVersion`-class gate exists on this surface, so a version bump is
  **advisory, not a gate**.
- **Surface B — the cockpit contract** (this document's subject —
  `cockpit-contract/`, versioned by `CONTRACT_VERSION`). Governs the emitted
  `cockpit-emission.json` envelope entities. This is the surface cockpit's
  `checkSchemaVersion` gates against (see Purpose note above).

**Why this matters for entity addition:** a change that only widens Surface A (e.g. a
new queryable record kind, or a glob-pattern correction on an existing kind) does
**not** require a Surface B version bump or reader-first handshake — it is invisible to
Cockpit's ingest gate. Only changes to the emitted envelope entities (new entity array,
new/changed field on an existing envelope entity) touch Surface B and trigger this
protocol. Confirm which surface a change actually touches before invoking the
reader-first ceremony (§ Step g) — routing a Surface-A-only change through the Surface B
handshake wastes a sentinel/memo round-trip on a change no consumer gate cares about.

### Value-domain changes — no bump, but not nothing

The version-bump gate is **byte-scoped on `schema/*.json`**. A change that alters only
*what values an existing field carries* — no field added, removed, or retyped — emits no
schema bytes and owes no bump. That reading is correct; do not manufacture a bump for it.

**It does still owe a memo and a declaration** when the field is a cross-entity join
anchor (`repo`, `session_id`, `entity_anchor.value`, any declared natural-key member).
A consumer's correctness on those fields depends on the value domain, not on the JSON
type, and a JSON Schema `{"type": "string"}` cannot tell a consumer that the population
it is joining against just acquired a second kind of token. The observable failure is not
a validation error — it is a silently unresolvable join, indistinguishable from a
legitimate coverage gap.

So: bump gate → no. Producer memo before shipping at scale → yes. Declared domain
(`description`, and `x-natural-key` where the field is part of a key) → yes, and that
declaration is itself the bump event, owned by the contract, not the producer.

Precedent and the worked example: `cockpit-contract/DECISIONS.md` D41 §§2-6
(`file_attributions.session_id` acquiring `agent-<uuid>` subagent-transcript stems
alongside harness session UUIDs).

---

## When NOT to Add a New Entity

<!-- src: plan21-021, plan20-009, plan31-022 -->

Before authoring a new entity file (Step a), check whether the shape actually needs a
**new** entity type:

- **A new discriminator on an existing entity is not a new entity.** E.g. central vs.
  project-scoped improvement-queue rows are both `BacklogItemSummary` (`type:
  improvement`) distinguished by a `queue_scope: central|project` field — not two
  parallel entity types. Reuse the existing entity + add a discriminator field (Step-a
  field-addition path) whenever the new population is structurally identical to an
  existing entity and differs only by provenance/scope.
- **A local emission-composition wrapper is not a contract entity.** The top-level
  envelope shape assembled by the emitter (`schema_version`, `emitted_at`,
  `coordinator_root`, plus the per-entity arrays) is the emitter's own composition
  surface, not a registered `ENTITY_SCHEMAS` member — it does not go through Steps
  (a)–(c). Only the individual entity arrays it wraps are contract-governed.
- **A stored entity does not have to be rendered immediately.** Registering and
  emitting an entity (landing it in `cockpit-emission.json`) is decoupled from any
  consumer building a UI panel for it — `BacklogItemSummary` and `ReviewTrail` shipped
  and were emitted well before cockpit built render surfaces for them. Do not hold an
  entity addition waiting for a consumer's render roadmap; the emit and the render are
  separate concerns on separate timelines.

---

## The Procedure

### Field-Addition to Existing Entities

Adding fields to an **already-registered entity** is a narrower operation than adding a
new entity type. It rides the same version-bump discipline, but note the actual blast radius
(see Purpose): cockpit's `checkSchemaVersion` only hard-throws on a **major** mismatch, so a
minor field-addition bump does not crash cockpit — new nullable fields on an already-consumed
entity are read as absent/null by cockpit's dict-extraction ingest, not a parse failure. The
version bump + reader-first coordination still applies (a consumer re-vendors to *use* the new
fields), but for a minor bump it is coordination, not outage-prevention.

**The same 11-step procedure applies.** The differences are contained to Step (a):

- **No new entity file.** Add the fields directly to the existing entity file
  (e.g. `cockpit-contract/src/entities/handoff-summary.ts`).
- **D9 is mandatory.** Every new nullable field uses `.nullable()` present-as-null
  (key in `required[]`). Never use `.nullable().optional()` (D13 exception — see
  § D9 Nullability Discipline above).
- **Shared enums belong in a standalone module.** If the new fields introduce enum
  types shared across multiple entity files, define them in a separate file (e.g.
  `cockpit-contract/src/entities/deliverable-spine.ts`) and import from there. This
  avoids circular imports when one entity imports from the `summaries.ts` barrel.
- **Step (b) is a no-op for field additions** — the entity's array key in
  `snapshot-envelope.ts` is already wired. Steps (c)–(h) run as normal.

**v2.4.0 example (deliverable-spine fields):** `deliverable_id`, `plan_id`,
`initiative`, `caption`, `status_reason`, `owner`, `last_meaningful_activity`,
`workstream_type`, `shipped_sha`, and `deliverable_status` were added as D9 nullable
fields to `HandoffSummary`, `PlanSummary`, and `RoadmapSummary`. Shared enums
(`WorkstreamType`, `DeliverableStatus`) live in
`cockpit-contract/src/entities/deliverable-spine.ts` to prevent circular imports.

**Narrowing an existing enum is a governed change, not a plain field-addition.**
Retiring a value from an entity's enum (e.g. `HandoffStatus` narrowed from
`[active, consumed, superseded]` to `[active, consumed]`) is data-migration-bearing —
every on-disk record carrying the retired value must be ported to its replacement
representation **before** the schema is narrowed and re-emitted, not after. The
sequence is: (1) land the doctrine + code path that expresses the retired value's
semantic a different way (e.g. `status: consumed` + `deployment_state: abandoned` in
place of `status: superseded`), (2) migrate all existing records, (3) narrow the
enum and bump the version. Treat narrowing with the same seriousness as a MAJOR bump
regardless of the numeric bump size, because unmigrated on-disk data becomes invalid
against the new schema. <!-- src: plan24-009 -->

**Vendoring is a manual copy, not a package dependency.** Consumers do not depend on a
published `@coordinator/cockpit-contract` package — each consumer **vendors** the
emitted schema JSON directly into its own tree (e.g. Cockpit copies
`cockpit-contract/schema/*.json` into `example-cockpit-repo/contract/schema/`, then runs its
own `contract:gen` to regenerate its local Zod/TS bindings). A "re-vendor" in the
reader-first handshake (§ Step g) means this two-step manual chain: producer-side
author + emit + commit, then consumer-side copy-in + regenerate + commit. There is
today no automated puller that performs the copy step — it is a manual file copy on
both sides of the handshake, and is the single most fragile link in the process
(nothing currently detects a stale/forgotten copy other than the consumer's own ingest
gate at production-emit time). <!-- src: plan31-020, plan31-025 -->

---

### Step (a) — Define the entity

Author the entity in `cockpit-contract/src/entities/<entity-name>.ts` following the
existing shapes (e.g. `health-status-summary.ts`, `decision-guide-summary.ts`):

- One Zod schema (`.shape()` exportable).
- D9 nullability: every optional field is `nullable()` + present-as-null, never absent
  (see § D9 Nullability Discipline above — the `.nullable().optional()` D13 exception
  does NOT apply to new entities).
- A TypeScript type alias (`z.infer<typeof …>`).
- Export from `cockpit-contract/src/entities/summaries.ts` (or the appropriate barrel).

Register the entity in `ENTITY_SCHEMAS` in `cockpit-contract/src/index.ts` and add an
`export *` re-export in the appropriate barrel. Codegen iterates `ENTITY_SCHEMAS` — an
unregistered entity produces no per-entity schema and no `$defs` entry in the bundle
(silent omission discovered only at emit/validate time).

**v2.1.0 example:** `roadmap-summary.ts`, `tracker-summary.ts`,
`health-status-summary.ts` were defined together in one contribution wave.

**v2.2.0 example (commit `38636099`):** `DecisionGuideSummary` entity authored in C1,
mirroring the `health-status-summary` shape (single lifecycle axis, D9 nullables).

**v2.4.0 example (`InitiativeSummary`):** New entity for the lightweight work-identity
parent.  Defined in `cockpit-contract/src/entities/initiative-summary.ts` with three
D9 nullable fields (`owner`, `status`, `description`) and two required string fields
(`id`, `label`).  The `status` field uses a two-value enum (`active` / `archived`)
rather than the richer per-artifact status enums.  On-disk records live at
`state/initiatives/<id>.yaml` (per-repo; central-seam-routed in the meta-repo).

### Step (b) — Wire the envelope [OWNER]

Extend the envelope schema in `cockpit-contract/src/entities/snapshot-envelope.ts`
with the new entity's array key, e.g.:

```typescript
decision_guides: z.array(DecisionGuideSummarySchema)
```

This change modifies the contract surface and belongs to the owner. Wire the envelope
before running codegen so the bundle reflects the updated envelope shape.

**v2.2.0 example (commit `72863b3b`):** `decision_guides` added to `snapshot-envelope.ts`
before codegen ran.

**v2.4.0 example (`initiatives`):** `initiatives: z.array(InitiativeSummary)` added to
`snapshot-envelope.ts`, plus a corresponding `initiatives` bucket in `MalformedRecords`.
Both additions happen before codegen to keep the bundle consistent with the wired
envelope.

### Step (c) — Codegen

Regenerate all derived artifacts:

```bash
cd plugins/coordinator/cockpit-contract
pnpm run build          # rebuilds dist/
pnpm run emit           # emits per-entity *.schema.json files
```

This produces:
- `cockpit-contract/schema/<entity-name>.schema.json` (per-entity JSON Schema).
- Updated `cockpit-contract/schema/cockpit-contract.schema.json` (the bundled envelope).
- Updated `cockpit-contract/dist/index.js` (the runtime validator).

**v2.2.0 example (commit `72863b3b`):** C4 ran codegen — emitted
`decision-guide-summary.schema.json`, rebuilt at version 2.2.0. The desync guard
(Step d) verified the match.

### Step (d) — Bump CONTRACT_VERSION

Bump `CONTRACT_VERSION` in `cockpit-contract/src/index.ts` following semver. New entity
type = minor bump (x.**Y**.0).

**The version is dynamic, not hardcoded in the emitter.** `emit-cockpit-snapshot.sh`
reads `schema_version` at runtime from the compiled schema bundle
(`cockpit-contract/schema/cockpit-contract.schema.json`, `.version` field) — the
emitter has no hardcoded version string. After bumping `CONTRACT_VERSION` in `src/index.ts`,
re-run codegen (Step c) so the bundle's `.version` matches. The emitter enforces this
with a **desync guard**: if `src/index.ts`'s `CONTRACT_VERSION` disagrees with the
bundle's `.version`, the emit aborts (DSR-2026-06-23-4, `emit-cockpit-snapshot.sh`
lines ~1841–1863).

**v2.1.0 example:** `CONTRACT_VERSION` bumped from `2.0.0` → `2.1.0` when the first
three entity types landed.

**v2.2.0 example (commit `5772e865`):** `CONTRACT_VERSION` bumped `2.1.0` → `2.2.0` in
C2/Cn/C3, alongside the envelope wiring for `decision_guides`.

### Step (e) — Wire the entity into `emit-cockpit-snapshot.sh` [OWNER]

**Prerequisite:** the record type must be queryable via `query-records.js --type <entity>`
(records-spine registration) before the emitter SECTION can collect it. Confirm this
before authoring the SECTION.

Add a new collection SECTION to `emit-cockpit-snapshot.sh` following the template at
**SECTION 8.11 — DecisionGuideSummary** (lines 1646–1722). The SECTION has four parts:

1. **Collect** — `query-records.js --type <entity>` call with fallback to `[]`
   (see line 1658 for the decision_guides example).
2. **Project** — jq transformation to the entity shape with all required fields and a
   provenance block (lines 1660–1693).
3. **Quarantine** — jq filter for records with missing required fields or out-of-enum
   status; written to a `MALFORMED_<ENTITY>` variable (lines 1696–1712).
4. **Validate** — `validate_main_record` loop over each projected row (lines 1714–1722).

Then wire into the final jq envelope assembly (the `FINAL_JSON` block, ~line 1869):

- `--argjson <key> "$<ENTITY>_ARRAY" \` (see line 1900 for the decision_guides pattern)
- `--argjson malformed_<key> "$MALFORMED_<ENTITY>" \` (line 1901)
- `<key>: $<key>,` in the JSON body (line 1927)
- `<key>: $malformed_<key>` in the `malformed_records` block (line 1940)
- `echo "<key>: $(echo "$FINAL_JSON" | jq '.<key> | length')" >&2` in the summary
  (line 1977)

**v2.2.0 example (decision_guides):** SECTION 8.11 (`emit-cockpit-snapshot.sh`
lines 1646–1722) is the worked template; its wiring in the final jq is at lines 1900,
1901, 1927, 1940, and 1977.

### Step (e) Addendum — Direct-File-Read Collection Branch

> **Purpose.** Step (e) above assumes the record type is queryable via `query-records.js
> --type <entity>` (frontmatter-indexed markdown). JSONL and JSON spine record types stored
> in `state/` directories are NOT supported by `query-records.js`. Those types use a
> **direct file-read per source directory** instead. This addendum closes that gap so future
> spine-type adds have a complete recipe regardless of collection mechanism.
> — Spec backlink: `docs/plans/2026-06-30-ccos-8-cockpit-read-contract-spine-entities.md § C8`

**When this branch applies.** Determine the upstream writer of the record type:

- Writer appends **frontmatter-keyed markdown** (handoffs, decisions, plans, trackers) →
  use the `query-records.js` path in Step (e) above.
- Writer produces **JSONL lines or JSON objects** in a `state/` directory (rollup files,
  ledger shards, hierarchy snapshots) → use the direct-file-read branch described here.

**Graceful-absent contract.** An absent source directory (or a directory with no matching
files) MUST emit `[]`, never fail. The emitter guards this with `[[ -d "$DIR" ]]` before
entering the collection block; when the guard is false the output variable defaults to `[]`.
This contract prevents missing optional state from aborting an otherwise-complete emit.

**Reference pattern — SECTION 6 (goals JSONL).** `state/goals-log.*.jsonl` is the earliest
direct-file-read emitter SECTION. It established the canonical shape: cat all per-machine
shards into a temp file, process with an inline Python heredoc (latest-wins dedup), inject
provenance at emit time. New JSONL spine types mirror this shape.

**Canonical spine examples — SECTIONs 8.13–8.14 (`emit-cockpit-snapshot.sh`).**

The ccos tc-8 spine entities introduced the pattern for JSON objects and JSONL ledgers:

| SECTION | Entity type | Source glob | Collection shape |
|---|---|---|---|
| 8.13 | `session-hierarchy` | `state/session-hierarchy.*.json` | One JSON object or array per file; entries flattened |
| 8.14 | `file-attribution` | on-demand Python derivation over `~/.claude/projects/<project>/*.jsonl` | Derived at query time via claude-klabauter `coordinator/bin/derive-file-attribution.py`; aggregated per (session, file) |

**Per-type transforms worth flagging for future spine adds.**

- **`is_final` liveness join (denoted `D-ISFINAL`).** Session-aware spine types source
  `cs_live_session_ids` (native `coordinator_core.session.liveness`; formerly
  `lib/coordinator-session.sh`, now gone, session-family-repoint C4a) for a second
  read. A `session_id`
  present in the live set forces `is_final=false` regardless of what the rollup says;
  absent-from-live AND `end_at` present ⇒ `is_final=true`; else `null`. Authors of future
  session-aware spine types should replicate this join — the live-set read is a second I/O
  pass beyond the source file and must be guarded for absence (`source … || true`).

- **Per-(session, file) aggregation for ledger types (SECTION 8.14).** Multiple JSONL rows
  keyed to the same `(session_id, file_path)` are merged into a single output row. Honesty
  markers (`completeness`, `capture_source`, `provenance_completeness`) resolve to the
  worst-case value across all merged rows — never stripped or averaged. Rows with
  `link_type: unknown` AND `null file_path` are skipped (forward-compat placeholder rows).
  Authors of future ledger spine types must apply worst-case aggregation on any honesty
  dimension present in the source schema.

**Wiring the envelope, bump, and reader-first handshake.** Steps (b)–(d) and (f)–(h) are
identical regardless of collection branch. The collection mechanism difference is contained
entirely within the emitter SECTION. Once the direct-file-read SECTION is wired into
`FINAL_JSON`, proceed through Steps (f)–(h) as normal.

**v2.3.0 example (session_events_summaries, session_hierarchies, file_attributions):**
SECTIONs 8.12–8.14 are the worked templates for the direct-file-read branch. SECTION 6
(goals) is the reference for the JSONL-shard concat variant. The two branches are parallel,
not sequential — choose based on the upstream writer's output format.

### Step (f) — Run the test gate

Before proceeding to the reader-first handshake, run:

```bash
cd plugins/coordinator/cockpit-contract
pnpm test
```

`pnpm test` runs vitest then `test:sh`. `test:sh` executes the emit round-trip
(`bin/emit-cockpit-snapshot.test.sh`). All green required before filing the
Cockpit re-vendor memo.

### Step (g) — Reader-first handshake: reader-class-tiered

**The reader-first ceremony is tiered by bump class.** The sentinel handshake historically
bundled two roles: (1) a crash-SAFETY gate (prevent an emit that hard-throws a consumer's
`checkSchemaVersion`, causing total cockpit outage — all entity reads abort) and (2) a
COORDINATION signal (tell the consumer to re-vendor the new shapes). These roles
**decouple for MINOR/PATCH bumps**: both current readers are same-major-forward-tolerant,
so the crash-safety gate is empty for a minor/patch bump. Coordination does not need an
emit-block; it needs a notification.

See `DECISIONS.md § D21` and
`state/review-trail/findings/2026-07-06-the Director of Engineering-dr203-sentinel-handshake-doctrine-ruling.md`
(`coordinator/cockpit-contract/DECISIONS.md` § D21) for the ruling behind the reader-class tiering.

**Consumer-capability census (run before every MINOR/PATCH bump).** The minor-bump
relaxation is conditional on every registered cockpit consumer meeting the
quarantine-tolerant bar:

- **(a) Replayable quarantine** — unknown/newer top-level entity arrays routed to replayable
  quarantine; raw payload retained. Never silent-drop (`extra='ignore'`); never
  whole-envelope hard-throw (`extra='forbid'`).
- **(b) Observable-skip signal** — non-empty `malformed_ingest` broken down by entity-kind
  on a query/health/doctor surface; quarantined arrays are visible without depending on the
  producer to notify.

If ANY registered consumer does NOT pass both (a) and (b) — strict-equality or silent-drop —
run the **MAJOR bump path** (full bilateral hold) scoped to that consumer, regardless of
whether the version bump itself is MAJOR or MINOR.

The census is **identity-free**: encode it as a predicate you re-run per bump, not a
hardcoded list of today's consumers. A new fleet consumer that joins with a strict ingest gate
automatically re-arms the full hold. A consumer that quarantines **silently** (satisfies (a)
but not (b)) is **not exempt** — silent quarantine removes the forcing function without a
replacement integrity alarm.

**Current census:** cockpit (a ✓ b ✓ — `checkSchemaVersion` at
`example-cockpit-repo/src/lib/store/ingest.ts:164-199`; major-only throw; same-major minor-newer
ACCEPTED with observable skip); rag (a ✓ b ✓ — `_check_schema_version` at
`project-rag/core/workstate_store/ingest.py:456-485`; major mismatch → `SchemaVersionError`;
same-major higher-minor → `SchemaSkip` + replayable quarantine; floor
`INGEST_SCHEMA_FLOOR = "2.3.0"` at `schema.py:71`). Example-repo is not a cockpit consumer (D13).
**Census passes — all current consumers meet the quarantine-tolerant bar.**

---

#### MAJOR bump path — full bilateral sentinel hold (unchanged)

**Applies when:** the bump is MAJOR (`X.0.0`) OR any registered consumer does not pass
the census. The crash-safety gate is live: a major-newer emit hard-throws both readers →
total cockpit outage.

1. Drop a sentinel: `state/cockpit-revendor-pending-<version>` (e.g.
   `state/cockpit-revendor-pending-v220`). The emitter's sentinel guard
   (`emit-cockpit-snapshot.sh` lines ~81–99) aborts any bare production run while this
   file is present — it cannot be bypassed by accident.
2. Send an outbox memo to each consumer (`state/memo-outbox/`) requesting re-vendor of the
   bumped contract. Relay to PM for cross-repo delivery. Include the bumped version string and
   the updated entity shapes for the consumer to vendor verbatim.
3. **Wait** for each consumer to re-vendor the new `CONTRACT_VERSION`, regenerate their Zod
   bindings, confirm their suite is green, and send a return confirmation memo.
4. Only after all consumers confirm: remove the sentinel, merge the owner branch, run emit.

**v2.1.0 example (commit confirmed by `cross-repo/archive/2026-06-27-cockpit-contract-v210-revendor-confirmed.md`):**
Cockpit vendored `cockpit-contract` v2.1.0 verbatim (roadmap/tracker/health arrays),
updated their `src/lib/contract/version.ts` to `CONTRACT_VERSION = "2.1.0"`, ran full
suite (744 passed), and sent the confirmation. The emit was held until that reply arrived.

**v2.2.0 example (commit `73de1a4b`):** C6 dropped sentinel
`state/cockpit-revendor-pending-v220` and filed the outbox memo
`cockpit-decision-guide-v220-reader-first.md` to cockpit requesting v2.2.0 re-vendor.
Production emit was held until cockpit replied.

---

#### MINOR/PATCH bump path — one-way reader-ready announcement

**Applies when:** all registered consumers pass the census AND the bump is MINOR (`x.Y.0`)
or PATCH (`x.y.Z`). No sentinel. No emit-hold. No wait-for-confirm gate.

1. Owner bumps + runs codegen (Steps d–e) + **emits immediately** — no sentinel placed.
2. Owner fires **one reader-ready announcement memo per consumer** (via `cross-repo-memo`
   CLI + PM-relay): new version, new shapes, and this note: *"New-entity arrays quarantine
   observably until re-vendor; replay automatically on re-vendor. No coordinator action
   required before we emit."*
3. Consumers re-vendor on their own timeline. Quarantined arrays replay automatically.
   No confirm round-trip gates the emit.

**Accepted consequence — emitted-but-quarantined window.** Between emit and consumer
re-vendor, newly populated entity arrays go to replayable quarantine (not live consumption).
This is the only invariant the minor-bump relaxation accepts losing — it is benign:
- **Integrity:** no loss — raw payload retained; replays on re-vendor.
- **Observability:** the quarantine is observable (`malformed_ingest` by entity-kind).
- **Availability latency:** a window where new typed data is emitted-but-not-yet-rendered
  (e.g. Cockpit's panel shows empty for new entity types) until re-vendor. Self-healing on
  re-vendor.
This is NOT the silent-quarantine-is-worse-than-hard-throw hazard — both current consumers
meet observable-skip condition (b).

**Emitter guard — no code change required.** `emit-cockpit-snapshot.sh` fires its sentinel
guard only when a sentinel FILE is present. For a minor bump the owner simply does not place
a sentinel — the guard never fires. The guard is unchanged and remains the hard backstop for
MAJOR bumps.

*Authorities: `docs/plans/2026-07-03-ccos-8-consumer-model-rework-rag-ingest.md` (coordinator
plan ratifying the consumer-model split); `DR-cockpit-store-inheritance` (project-rag decision
record governing quarantine semantics); `coordinator/cockpit-contract/DECISIONS.md` § D21 (sentinel-handshake
relaxation to reader-class-tiered, 2026-07-06).*

### Step (h) — Merge and run the bumped emit

**MAJOR bump path only** (sentinel was placed in Step g). For MINOR/PATCH bumps, the owner
merged and emitted in Step (g) without a confirmation gate.

Only after all consumers confirm:

1. Remove the sentinel file (`state/cockpit-revendor-pending-<version>`).
2. Merge the owner branch to main.
3. Run the production emit (claude-klabauter `artifact.emit` — default path) — this is the first
   live snapshot with the new schema version; all consumers' ingest now accepts it.

**v2.1.0 example:** The confirmation memo (`2026-06-27-cockpit-contract-v210-revendor-confirmed.md`)
stated: *"You are clear to merge B4→main and run the bumped production emit."* The
sentinel was removed and the branch merged.

---

## Serialization Rule (Hard)

**Multiple pending entity additions must batch or sequence under ONE owner-run bump
cadence. Never independent concurrent bumps.**

If two contributor workstreams both hand over entity shapes in the same window (e.g.
decision-guide ask + ccos spine entities), the owner either:

- **Batches** them into a single bump (one `CONTRACT_VERSION` increment, one codegen
  run, one reader-first handshake with cockpit), or
- **Sequences** them (one workstream lands first, completes the full handshake, then the
  second is opened under the next bump).

Batch when both shapes are ready in the same window and a single cockpit re-vendor is
preferable; sequence when one entity is urgent or ready now and the other is materially
later, higher-risk, or not yet fully defined.

**Serialize behind hot-surface quiescence, not just around each other.** When one
in-flight workstream touches Surface B (this contract) alongside other disjoint
changes in the same window, land the disjoint changes first (they're safe anytime) and
hold the Surface B entity/field additions until the contract surface is quiescent —
i.e. no other contributor branch has an uncommitted or unmerged shape change pending
against `cockpit-contract/`. This is the same batch-or-sequence discipline applied at
finer grain: don't serialize the whole workstream, just the part that actually touches
the version-gated surface. <!-- src: plan27-014 -->

Independent concurrent bumps churn the version-tracking for every consumer. For a **major**
bump, a bump whose emit races the re-vendor window hard-throws cockpit's ingest — the
double-bump/**outage** hazard. **Serialization for MAJOR bumps is an outage-prevention hard
gate.** For **minor/patch** bumps, the outage hazard is absent (consumers are
forward-tolerant), but batch-or-sequence remains the right hygiene — concurrent minor bumps
produce version-tracking churn and two in-flight reader-ready memos, not an outage. The
hard serialization gate applies to MAJOR bumps only; for minor bumps it is recommended
coordination practice (`coordinator/cockpit-contract/DECISIONS.md` § D21). The owner decides the batch vs.
sequence call; contributors notify the owner when their entity shape is ready.

---

## File Locations (quick reference)

| Artifact | Path |
|---|---|
| Entity definition | `cockpit-contract/src/entities/<name>.ts` |
| Barrel export | `cockpit-contract/src/entities/summaries.ts` |
| Schema registry | `cockpit-contract/src/index.ts` (`ENTITY_SCHEMAS`) |
| Envelope wiring | `cockpit-contract/src/entities/snapshot-envelope.ts` |
| `CONTRACT_VERSION` source | `cockpit-contract/src/index.ts` |
| Schema bundle (computed) | `cockpit-contract/schema/cockpit-contract.schema.json` |
| Emitter | claude-klabauter Python `artifact.emit` (sole producer; `bin/emit-cockpit-snapshot.sh` is a fail-loud facade stub, claude-klabauter DR-208/DR-210) |
| Sentinel pattern | `state/cockpit-revendor-pending-<version>` |
| Outbox memo landing zone | `state/memo-outbox/` |
| Provenance envelope + ref-conditional | `cockpit-contract/src/provenance.ts` |
| Deliverable-spine shared enums | `cockpit-contract/src/entities/deliverable-spine.ts` |
| Initiative on-disk records | `state/initiatives/<id>.yaml` (per-repo; central-seam-routed) |

---

## Worked Examples

| Version | What changed | Key commits / artifacts | Episode note |
|---|---|---|---|
| 2.1.0 | New entities: roadmap-summary, tracker-summary, health-status-summary | Batch entity + codegen + reader-first (held on AC10) | `cross-repo/archive/2026-06-27-cockpit-contract-v210-revendor-confirmed.md` |
| 2.2.0 | New entity: decision-guide-summary | C1 entity → C4 envelope+codegen → C2/Cn/C3 bump → C5 emitter-wire → C6 sentinel + memo | commits `38636099`…`73de1a4b` |
| 2.3.0 (ccos-8) | New entities: session-hierarchy, file-attribution + session-events-summary spine types; new `required[]` entity arrays on envelope | Widen-reader-first + sentinel handshake; baseline for 2.4.0 | No outstanding sentinel — clean baseline |
| 2.4.0 (spine) | New entity: initiative-summary; deliverable-spine fields (D9 `.nullable()`) on HandoffSummary/PlanSummary/RoadmapSummary; shared enum module `deliverable-spine.ts`; emit projections for identity + facets + `workstream_type` + `shipped_sha` + derived `deliverable_status` | C1 entities + C3 authoring threading + C4 emit projection; reader-first gated behind `cockpit-revendor-pending-v2.4.0` sentinel (C0) | Cockpit re-vendor confirmation required before C6 flips `CONTRACT_VERSION` |
| (in-flight) | `handoff_phase` field on execution-scoped handoff entities, feeding cockpit's `executionHandoffs` fleet-state category (`{fireable, gated, other}`) | `query_fleet_state` reader (cockpit 4260a9c3) already lands and degrades gracefully empty/sparse until the field is populated | Two-part closure explicitly named: DoE-side cockpit-contract widening (cockpit's vendored v2.1.0 does not yet carry `handoff_phase`) + claude-klabauter's emit-side stamping leg — a worked example of a reader shipping ahead of the producer under the graceful-degradation contract |

---

## See Also

- `docs/decisions/DR-167-cockpit-contract-standing-owner.md` — governance decision
  record; names the owner, codifies the contributor contract, and points to the
  originating PM gate.
- `state/roadmap/2026-06-27-ccos/pm-gates.md` — originating PM decisions (owner
  ratification + contributor re-scope).
- `cross-repo/archive/2026-06-27-cockpit-readcontract-analysis.md` — cockpit ingest
  architecture. **Note:** for the authoritative gate behavior read the source directly —
  `checkSchemaVersion` at `example-cockpit-repo/src/lib/store/ingest.ts:164-199` (major-only throw;
  same-major minor-newer accepted). Any doc citing `assertSchemaVersion`/`:76-98` or
  "throws on any newer version" is stale.
- `docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md` — the plan
  that introduced deliverable-spine fields, `InitiativeSummary`, and the v2.4.0
  reader-first handshake shape; source of D1–D6 design decisions.
- `cockpit-contract/src/provenance.ts` — `ProvenanceEnvelope` definition including the
  bidirectional `ref` ref-conditional (`.superRefine()`); the Source A settled contract
  not modified by field/entity additions.
