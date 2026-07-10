---
title: "Canonical artifact shapes — Baton blob doctrine"
created: 2026-06-25
status: active
spec_backlink: docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md
roadmap_id: example-initiative-2026-06-25
stub_id: example-initiative-0
---

# Canonical Artifact Shapes — Baton Blob Doctrine

> **Purpose (spec backlink: `docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § C1`).**
> This wiki is the canonical doctrine that roadmap nodes tc-1 (records: plans + decisions),
> tc-2 (queues: lessons + improvement/bug/debt), tc-3 (expressive + audit shapes), and
> tc-4 (fleet machinery + versioned contract emit) cite as their inheritance. It defines the
> designed canonical shape for the **Baton blob**, the cross-type liveness predicate over
> all inventoried artifact kinds, the addressable-section convention, the warn-not-block
> enforcement posture, and the schema-registry-as-published-contract framing. The
> resolution is **order, not uniformity** — a small set of canonical document kinds, each
> *designed*; standardized within a type (predictable, addressable sections), consolidated
> across types where the job is identical, never at the cost of expressiveness or
> capture-speed.

---

## The Baton Blob — Scope and Purpose

The **Baton blob** is the family of artifacts whose job is *persist or pass a unit of
work-state across a boundary*: **handoffs**, **spinoffs** (already `kind`-discriminated
handoffs sharing the same schema and file location), and **cross-repo memos**. They share
one purpose but carry different bodies and slightly different frontmatter because their
boundary-types differ (session boundary vs. workstream fork vs. cross-repo delivery). The
canonical shape defined in this wiki is their designed common form — not a forced
uniformity, but a principled consolidation of the index layer (frontmatter grammar +
liveness predicate + section vocabulary) that leaves the expressive body dialects
intact where they genuinely differ.

**Inventory ground truth:** `state/scratch/query-friendly-fleet-substrate/inventory-records.md`
(handoff/spinoff/memo shapes), `inventory-fleet-machinery.md` (registry + warn-hook +
query-records). The inventory reveals that the baton family accreted rather than was
designed: the same concept (author, lineage/predecessor, liveness) carries multiple
spellings across types, and there is no cross-type "is this live?" predicate despite all
three types having mature per-type enums. This wiki corrects that.

**Scope of this session (tc-0):** the canonical grammar and liveness predicate for batons
are *implemented* in this session (schemas, scaffolder, skill rewire, and `query-records`
liveness resolver). The full mapping table is *designed-complete* across all fleet artifact
kinds (proving the predicate generalizes) even though only batons are implemented — per
The Director of Engineering P1-1, this prevents the keystone from freezing myopic before inheriting nodes author
against it.

---

## Canonical Frontmatter Grammar — Batons

> Spec backlink: `schemas/handoff.schema.json` (10.9 KB; the canonical reference with
> cross-field rules in `bin/lib/schema.js`) and `schemas/cross-repo-memo.schema.json` (the
> live implementation; the originating spec `docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md`
> has been distilled/archived — the live CLI `bin/cross-repo-memo` `_compose_frontmatter`
> l.615 + `_compose_memo` l.655 is the operative reference).
<!-- Review: code-reviewer S1-F4 — _compose_document l.723 fabricated; actual function is _compose_memo (l.655); _compose_frontmatter line corrected l.619→l.615 -->

The batons share a set of core frontmatter keys with common semantics. The table below
enumerates every shared and type-specific key in the canonical grammar.

### Shared Core Keys

| Key | Handoff | Memo | Semantics |
|-----|---------|------|-----------|
| `title` | required | required | Human-readable artifact name; consistent quoting not enforced but `title: string` is schema `required` on both |
| `created` | required (iso-date) | required (iso-date) | Canonical timestamp key; consolidates any historical `date:` redundancy — the only fleet-wide temporal key recognized by `query-records --since` / `--older-than` |
| `status` | required | required | Lifecycle record axis — **TYPE-SCOPED enum** (see §§ below; the same key name carries different value-spaces per type, NOT a cross-type predicate) |
| `summary` | optional (≤120 chars, post-cutoff cross-field enforced) | optional (≤120 chars, cross-field enforced) | One-line description; length enforced in `bin/lib/schema.js` cross-field rules |

**Critical negative-spec: `kind` and `status` are TYPE-SCOPED enums, not cross-type predicates.** A handoff `status: active` and a memo `status: open` are NOT the same thing and share only the key name. A fleet query on `status` cannot treat the values as cross-type comparable without the liveness predicate layer (§ "The Cross-Type Liveness Predicate" below).

### Author and Lineage Concepts

The author and lineage/predecessor concepts exist in both types but are spelled differently — some spellings are accidental, some are load-bearing. The canonical grammar consolidates the accidental divergences and explicitly records the load-bearing ones.

**Handoff author/lineage (canonical):**

| Key | Kind | Semantics |
|-----|------|-----------|
| `machine` | optional | Machine name (not session id); identifies which host authored the handoff |
| `authoring_session` | required-by-convention on spinoffs | Free-form one-liner back to origin; replaces `predecessor` link on spinoffs as audit trail |
| `predecessor` | required | Lineage link — the handoff this one continues (`none` on spinoffs; SHA or filename for session-handoffs); expressed three ways in the wild (`none`, `null`, filename) — canonical form is `none` or a filename |
| `consumed_by` | conditional | Session-id of the consuming `/pickup` invocation; set on lifecycle transition |

**Memo author/lineage (canonical):**

| Key | Kind | Semantics |
|-----|------|-----------|
| `from` | required (load-bearing) | Sender repo/identity — **receiver-routing-critical**; the CLI uses `from` to determine delivery target; do NOT consolidate or rename |
| `to` | required (load-bearing) | Receiver repo/identity — **receiver-routing-critical**; same constraint as `from` |
| `supersedes` | optional | Set on the new memo when re-issuing a pre-lifecycle memo |
| `superseded_by` | optional | Set by receiver when a newer memo supersedes this one |

**Load-bearing divergences — deliberately kept:**
- Memo `from`/`to` encode receiver-routing semantics that handoff `machine`/`authoring_session` do not. These fields are the delivery address; consolidating them with handoff author fields would break the single-surface delivery mechanism in `bin/cross-repo-memo`. They are explicitly marked as `deliberate-keep-with-architectural-reason` in `schemas/cross-repo-memo.schema.json`.
- Handoff `predecessor` (ancestry) vs memo `supersedes`/`superseded_by` (supersession chain): same concept, but memos express the chain bidirectionally because the receiver may re-issue under a different memo ID. The handoff does not need bidirectional pointers because it uses `consumed_by` + `shipped_in` to record the lifecycle transition in place.

### Type-Specific Keys

**Handoff-specific (not shared with memos):**

| Key | Semantics |
|-----|-----------|
| `branch` | Git branch at authoring time; required |
| `deployment_state` | Readiness axis (see liveness predicate below); drives `/pickup` and start-ceremony surfacing |
| `gate_dependency` | Required-by-cross-field-rule iff `deployment_state: awaiting_gate` |
| `kind` | Discriminator: `session-handoff`, `spinoff`, `spinoff-roadmap`, `recovery` |
| `category` | Work category: `roadmap`, `infra`, `bug`, `docs`, `research`, `refactor`, `uncategorized` |
| `pickup_ready` | Positive pickup-authorized signal; absence triggers non-blocking warn at `/pickup` |
| `scope` | List-of-string git pathspecs; optional but used for fleet-scope filtering |
| `roadmap_id`, `stub_id`, `sprint`, `wave`, `cost`, `blocks`, `blocked_by` | Roadmap graph primitives; `spinoff-roadmap` kind only (validator REJECTS on other kinds) |
| `completeness_checklist` | List-of-string; install-leg batons; parsed at `/pickup` |

**Memo-specific (not shared with handoffs):**

| Key | Semantics |
|-----|-----------|
| `delivery_mode` | Enum: `receiver-repo` (current), `central-only` (grandfathered); CLI only ever issues `receiver-repo` |
| `kind` | Sender-declared shape: `ask`, `consult`, `fyi`, `proposal`; absent → reader applies `ask` default; validated via cross-field rule (not YAML enum) to enforce the grandfather cutoff |
| `picked_up_by`, `picked_up_at` | Claim attribution; set when `status: in_progress`; cleared on release |
| `decision`, `decision_note`, `actioned_note` | Receiver-side outcome fields; `decision` required when `status: action_taken` (cross-field rule) |

---

## The Cross-Type Liveness Predicate (KEYSTONE)

> Spec backlink: `docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § The cross-type liveness predicate`
> Implementation: `bin/query-records.js` `liveness(fm, type)` resolver (tc-0 C3).

The sharpest finding from the fleet inventory is that **`status` is a false friend** — one
key name carrying three incompatible enums across batons, plus more across the queue and
record families, with **no cross-type "is this live?" predicate**. A fleet dashboard
and project-rag store live or die on that predicate. This section defines it.

### Why DERIVED, Not Stored (D2)

The liveness predicate is a **derived** synthetic state — computed on read from the enums
already on disk — NOT a new frontmatter key added to every artifact. Rationale (D2):

1. **No capture-speed cost.** Forcing a `lifecycle:` or `live:` boolean onto every artifact
   adds a field every author must set correctly. Authors already set `status` (and `deployment_state`
   for handoffs). A derived predicate adds zero author overhead.
2. **No drift source.** A stored `live: true` field would duplicate the enum it was derived
   from. When `status` changes, the stored `live:` field must also change — a second source
   of truth guaranteed to diverge. The derived predicate is always correct because it is
   computed at query time.
3. **Expressiveness preserved.** No artifact gains a required field; no capture path slows.
   The guardrail ("a canonical shape that cannot hold its artifact's ASCII diagram has failed")
   is honored.

**Negative-spec: no `lifecycle:`, `live:`, or `liveness:` key appears in any baton schema.**
The mapping table below is doctrine; `query-records.js` is the implementation; no frontmatter
field carries this derived state.

### Three Canonical Derived States

- **LIVE** — actionable now or actively in flight; the artifact is in the operator's working
  attention space.
- **BLOCKED** — the artifact exists and is not terminal, but is gated on an external
  condition before it can be acted on (e.g., `awaiting_gate` on a handoff, `deferred` on a
  backlog item).
- **DONE** — terminal; the artifact's lifecycle is complete (shipped, consumed, actioned,
  abandoned, wontfix). No further action expected. For handoffs specifically: DONE when
  `status == consumed` OR `deployment_state ∈ {shipped, abandoned}` (the retired `superseded`
  status is no longer written on new handoffs).
  <!-- Review: code-reviewer Slice-B — (F4) dropped "see § Handoff Two-Axis Combination Rule"; that section does not mention superseded retirement; parenthetical is self-contained -->

### Handoff Two-Axis Combination Rule

Handoffs carry two independent lifecycle axes (`status` = record axis; `deployment_state` =
readiness axis). The liveness derivation for handoffs combines them:

> **DONE** if `status == consumed` OR `deployment_state ∈ {shipped, abandoned}`;
> else **BLOCKED** if `deployment_state == awaiting_gate`;
> else **LIVE**.

`deployment_state` is authoritative for readiness when present; `status` is the record axis.
A handoff with `status: active` and `deployment_state: awaiting_gate` is BLOCKED, not LIVE.
A handoff with `status: active` and `deployment_state: shipped` is DONE, even though the
record axis says `active` — the readiness axis takes precedence for terminal detection.

### Design-Complete Mapping Table

The table below enumerates every inventoried fleet artifact kind and every status/lifecycle
enum value. Rows marked `implemented this session` are backed by `liveness(fm, type)` in
`bin/query-records.js` (tc-0 C3). Rows marked `design-only` prove the predicate generalizes
before tc-1/tc-2 inherit the doctrine.

| Type | Enum key | Value | Canonical liveness | Implemented this session? |
|------|----------|-------|--------------------|--------------------------|
| handoff | status | active | (record axis; combine w/ deployment_state per combination rule above) | yes |
| handoff | status | consumed | DONE | yes |
| handoff | deployment_state | awaiting_gate | BLOCKED | yes |
| handoff | deployment_state | ready_to_fire | LIVE | yes |
| handoff | deployment_state | in_flight | LIVE | yes |
| handoff | deployment_state | shipped | DONE | yes |
| handoff | deployment_state | abandoned | DONE | yes |
| memo | status | open | LIVE | yes |
| memo | status | in_progress | LIVE | yes |
| memo | status | actioned | DONE | yes |
| memo | status | reviewed *(back-compat)* | DONE | yes |
| memo | status | action_taken *(back-compat)* | DONE | yes |
| memo | status | closed *(back-compat)* | DONE | yes |
| memo | status | superseded *(back-compat)* | DONE | yes |
| plan | status | draft | LIVE | implemented (tc-1) |
| plan | status | reviewed | LIVE | implemented (tc-1) |
| plan | status | approved | LIVE | implemented (tc-1) |
| plan | status | executing | LIVE | implemented (tc-1) |
| plan | status | implemented | DONE | implemented (tc-1) |
| plan | status | deferred | BLOCKED | implemented (tc-1) |
| plan | status | abandoned | DONE | implemented (tc-1) |
| plan | status | superseded | DONE | implemented (tc-1) |
| decision | status | proposed | LIVE | implemented (tc-1) |
| decision | status | accepted | DONE (a decision record is terminal once in force) | implemented (tc-1) |
| decision | status | deprecated | DONE | implemented (tc-1) |
| decision | status | superseded | DONE | implemented (tc-1) |
<!-- Review: code-reviewer S1-F1/F2/F3 — queue-family enums were transposed: improvement-queue had debt-backlog's values (open for-weekly-arch-review, resolved) and debt-backlog had improvement-queue's terminal (closed). Corrected to SCHEMAS source-of-truth (coordinator-queue-append, debt-backlog l.122-126, bug-backlog l.154, improvement-queue l.187). This corrects the earlier the Director of Engineering F1 attribution which transposed the two queues; source-of-truth is coordinator-queue-append SCHEMAS. -->
| improvement-queue | status | open | LIVE | implemented this session |
| improvement-queue | status | closed | DONE | implemented this session |
| improvement-queue | status | deferred | BLOCKED | implemented this session |
| bug-backlog | status | open | LIVE | implemented this session |
| bug-backlog | status | closed | DONE | implemented this session |
| bug-backlog | status | wontfix | DONE (terminal — no action taken; a conscious rejection, not deferred work) | implemented this session |
| bug-backlog | status | deferred | BLOCKED | implemented this session |
| debt-backlog | status | open | LIVE | implemented this session |
| debt-backlog | status | closed | DONE | implemented this session |
| debt-backlog | status | deferred | BLOCKED | implemented this session |
| lesson | status | unprocessed / open *(derived at query time — D3: `parseLessonsFile` extracts from prose conventions)* | LIVE | implemented this session |
| lesson | status | processed / promoted / Resolved / SUPERSEDES *(derived at query time — D3)* | DONE | implemented this session |
| roadmap | status | planning | LIVE | implemented (example-initiative example-workstream example-repo Ask 1) |
| roadmap | status | active | LIVE | implemented (example-initiative example-workstream example-repo Ask 1) |
| roadmap | status | blocked | LIVE (in-flight, NOT done — gated but actively tracked) | implemented (example-initiative example-workstream example-repo Ask 1) |
| roadmap | status | shipped | DONE | implemented (example-initiative example-workstream example-repo Ask 1) |
| roadmap | status | archived | DONE | implemented (example-initiative example-workstream example-repo Ask 1) |
| tracker | status | active | LIVE | implemented (example-initiative example-workstream example-repo Ask 5 promote) |
| tracker | status | archived | DONE | implemented (example-initiative example-workstream example-repo Ask 5 promote) |
| health-status | status | active | LIVE (lifecycle axis; health posture HEALTHY/WATCH/ACTION/CRITICAL is a SEPARATE field) | implemented (example-initiative example-workstream example-repo Ask 5 promote) |
| health-status | status | archived | DONE | implemented (example-initiative example-workstream example-repo Ask 5 promote) |
| decision-guide | status | active | LIVE (document-currency axis; liveness keys on the container's lifecycle, NOT per-decision enum) | implemented (2026-06-27) |
| decision-guide | status | archived | DONE | implemented (2026-06-27) |
| week-changelog | — | (daily blocks, no status field) | N/A — generated digest, not an authored lifecycle artifact | n/a |
| workstream | — | (definition-only, no status/lifecycle field — completion is a field-scoped event, never a definition mutation) | N/A — no status/lifecycle enum | n/a |
| workstream-event | — | (field-scoped mutation record, no status/lifecycle field) | N/A — no status/lifecycle enum | n/a |
<!-- Review: code-reviewer — Finding 3 (P2). workstream/workstream-event registered per
     the week-changelog N/A precedent — both are structurally lifecycle-free (the
     definition never carries a status field; completion state lives exclusively in
     field-scoped events per workstream.schema.json's own design). -->

**Hard-case rationale for reviewers:**
- `wontfix` → DONE: a wontfix entry is a conscious terminal decision ("we will not fix this"). It is not deferred — there is no future action. It resolves the artifact's lifecycle cleanly, the same as `closed`. Treating it as LIVE or BLOCKED would pollute "open work" fleet views with permanently-rejected items.
- `deferred` (bug-backlog, debt-backlog) → BLOCKED: a deferred item is gated on a future condition (time, priority, prerequisite). It is not actionable now, but is not terminal. BLOCKED correctly models "exists, not ready, not done."
- `open for-weekly-arch-review` (debt-backlog) → **consolidated by tc-2**: this enum value was eliminated in the tc-2 queue-schema unification (C6 port). Entries carrying it are ported to `status: open` + `tags: [weekly-arch-review]`. The LIVE semantics are preserved on the tag axis — items tagged `weekly-arch-review` remain surfaceable at the next ceremony and are treated as LIVE by the liveness predicate (their status value is `open`). The original rationale (not gated on an external dependency; actionable at the next weekly) remains correct, now expressed via the tag rather than a space-bearing enum value.<!-- Review: code-reviewer S1-F1/F2/F3 — attribution corrected from (improvement-queue) to (debt-backlog); open for-weekly-arch-review is a debt-backlog enum value per SCHEMAS source; tc-2 C6 consolidated to open+tags:[weekly-arch-review] -->
- `awaiting_gate` (handoff deployment_state) → BLOCKED: the handoff has a named `gate_dependency` (enforced by cross-field rule). It is not ready for pickup until the gate clears.
- `decision: accepted` → DONE: an accepted decision record is terminal — no further lifecycle transitions are expected. The operational effect is governed by the policy the decision describes, not by the record's status field. The record remains queryable for audit but never re-enters LIVE or BLOCKED.<!-- Review: code-reviewer S1-F6 — accepted decision is terminal; added to hard-case rationale to document the rationale alongside other terminal-class values -->

---

## Liveness Mapping as First-Class Contract Data (Forward Seam)

> Spec backlink: `docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § Ratified design decisions D2 sub-point`
> Forward seam target: tc-4 (fleet aggregator + versioned emit), tc-5 (project-rag store, tc-5 memo + PM-relay, out-of-scope for this session).

The liveness mapping table defined above is **first-class contract data**, not a local
implementation detail of `bin/query-records.js`. It travels with the tc-4 versioned emit
artifact — the same Zod-source → emitted-versioned-JSON artifact pattern proven in-tree
by the cockpit-contract owner-enum seam (`docs/plans/2026-06-25-cockpit-contract-owner-enum-seam.md`,
cited here as the in-tree proof; this wiki does NOT extend that plan's scope).

**Implication for tc-5 (project-rag store):** project-rag derives its LIVE/BLOCKED/DONE
derivation FROM the published mapping in the tc-4 emit artifact, not by re-reading or
re-implementing `bin/query-records.js` in another language. project-rag MAY materialize
liveness as a computed column at ingest, but the derivation logic is the published mapping,
not an independent implementation. This prevents the predicate from diverging between the
query layer (`query-records`) and the store layer (project-rag) — a silent divergence that
would produce inconsistent fleet views.

**D2 holds throughout the tc-4→tc-5 chain:** no artifact gains a `liveness:` frontmatter
field; the mapping is published as versioned contract metadata, separate from the artifacts
themselves.

---

## Addressable-Section Convention

Every canonical artifact type defines a set of **addressable named sections** — H2 or H3
headers whose names are predictable enough that an extractor, dashboard, or linked
reference can jump to them without full-text parsing. This is what distinguishes a
*designed* artifact shape from an accreted one.

### Convention Rules

1. **Section names are drawn from a shared vocabulary.** Per D1, the index (frontmatter
   grammar + addressable-section *vocabulary*) is shared across batons; which sections
   appear in a given artifact is `kind`-branched. An extractor that knows the vocabulary
   can reliably locate e.g. `## Acceptance Criteria` in any baton that carries it.

2. **Case and spelling are normalized.** `## Acceptance Criteria` (title case) is the
   canonical form; tc-1 normalized the spelling when consolidating the plan sidecar family
   (C8 port, 2026-06-25).

3. **Section presence is `kind`-specific, not universally required.** A session-handoff
   carries `## What Was Accomplished`, `## Current State`, etc. A spinoff carries
   `## What this covers`, `## Acceptance criteria`, etc. A memo body is largely free-form
   with optional structured sections. The *vocabulary* is shared; the *presence* is
   type-branched. Dashboards must branch on `kind:` to parse body sections.

4. **Body-resident machine blocks stay in the body.** The `## Session Ledger`
   (append-only LoE table in session-handoffs) is deliberately body-resident because it
   grows per-session; it is parsed by the synthetic `--type handoff-ledger` in
   `query-records`, not by schema frontmatter. The addressable-section convention does not
   flatten body-resident machine blocks into frontmatter.

   **The plan `## Tasks` task-spine is the same pattern, applied to a single fenced
   ```yaml plan-tasks``` block instead of a growing table.** A plan's `## Tasks` section
   carries EXACTLY ONE such block directly under the heading (parser-locate rule); its
   YAML-list body is the task spine consumed by `plan-coverage-checker` (FAIL-LOUD on
   zero/multiple blocks) and the deferred-harvest CLI (WARN-AND-SKIP on the same
   condition — a plan mid-authoring may not have a spine yet). The per-row shape is
   registered as `schemas/plan-tasks.schema.json` and `$ref`'d from `schemas/plan.schema.json`'s
   `tasks` property, mirroring how `handoff-ledger` is a synthetic query-time type rather
   than a frontmatter field. Per the same Tier-2 posture as every other body-resident
   machine block (§ Warn-Not-Block Enforcement Posture below), post-scaffold hand edits to
   the block are warned-on, never blocked. Full authoring contract:
   `docs/wiki/writing-plans.md § Machine-Parseable Task Spine`. Spec backlink:
   `docs/plans/2026-07-09-plan-full-coverage-and-deferred-harvest.md § C1`.

### Canonical AC Table Shape

> **Spec backlink: acceptance-oracle retirement (2026-06-30).** The prior 5-column oracle
> table shape (with test-reference and binding-class columns) and its mechanical gate script
> are retired. The canonical AC shape is the 3-column prose form described below.

An `## Acceptance Criteria` section is an **optional** plan artifact and reviewer design
lens. When present, it uses a 3-column prose table:

| ID | Criterion | Status |
|----|-----------|--------|
| AC-1 | Human-readable acceptance condition | PASS / FAIL / n/a |
| AC-2 | … | … |

**Canonical constraints:**

- **Optional.** Plans are not required to carry `## Acceptance Criteria`. Absence is not a
  schema violation; the warn-not-block hook does not gripe on missing AC sections.
- **Not mechanically gated.** There is no CI gate, no oracle grammar, and no binding-class
  column. The table is authored prose — readable by reviewers and extractors, not consumed
  by a validation harness.
- **ID | Criterion | Status only.** The retired test-reference and binding-class columns do
  not appear in the canonical form. Existing plans that carry 5-column tables are not
  retroactively ported; the 3-column form is the target for new plans.
- **Status values are prose, not enums.** `PASS`, `FAIL`, `n/a`, `TBD`, or a one-line
  evidence note are all valid status values. The table is a communication device for the
  reviewer and the EM, not a machine-parsed artifact.

**Negative-spec:** the retired 5-column oracle table (with `Test` and binding-class
columns), the old test-prefix grammar (`pytest:`, `node:`, `cargo:`, `grep:`, `cited:`),
and the oracle gate script are all retired and must not appear in new plans or
agent-authored plan stubs. `## Acceptance Criteria` is a prose section, not a
machine-executable oracle.

---

### Diagram (ASCII) Rule

> Reserved for diagram-bearing artifact types. Defined here for tc-3 (expressive + audit
> shapes) to inherit.

When an artifact carries an architecture or flow diagram, it MUST appear under a
`### Diagram (ASCII)` section. This is the addressable hook for extractors and dashboards
that want to surface visual structure.

- **Batons rarely carry diagrams.** Session-handoffs and spinoffs are narrative/spec
  artifacts; their expressiveness load is prose and tables, not ASCII art. The Diagram
  rule is defined here so inheriting types (tc-3: expressive plans, architecture docs, etc.)
  can cite this wiki as the source of the convention.
- **Diagrams are ALWAYS ASCII.** No image links, no embedded SVG. This ensures diagrams are
  readable in raw-markdown context (terminal, `cat`, `grep`), survive git diffs, and can
  be extracted as plaintext.
- **One `### Diagram (ASCII)` section per artifact** (or per major sub-section for complex
  artifacts). Multiple diagrams within a section are permitted; multiple `### Diagram (ASCII)`
  sections in one artifact require a numbered variant (`### Diagram (ASCII) 1`, etc.).
- **Diagrams are body content, not frontmatter.** The addressable `### Diagram (ASCII)` header
  is a body-section hook; no frontmatter field encodes diagram presence (that would be a
  maintenance burden — a stored `has_diagram: true` that drifts from the body).

---

## Warn-Not-Block Enforcement Posture

> Spec backlink: `state/scratch/query-friendly-fleet-substrate/inventory-fleet-machinery.md § Frontmatter enforcement hook`
> Negative-spec: **do NOT add a hard-deny path to the write-time hook** for enum validation outside `COORDINATOR_SCHEMA_STRICT=1`.

The coordinator system uses a **two-tier enforcement model** for artifact shape: strict at
the typed seam, lenient at the prose seam. This is the established, PM-praised behavior
and is codified here as doctrine, not introduced by this plan.

### Tier 1 — Typed Seam (Fail-Loud)

Structured-append writers are fail-loud. `coordinator-queue-append` (`bin/coordinator-queue-append`)
and the new general scaffolder `coordinator-doc-new` (`bin/coordinator-doc-new`) are single-
entry-point typed writers that:

- Reject unknown `--type` / `--schema` values with a list of known types (`sys.exit(1)`)
- Reject missing required fields (`_validate()`)
- Reject invalid enum values (prints the valid set)
- Fail on invalid `--queue-scope`

The typed seam is where shape correctness is *enforced* because the writer owns the complete
shape of the output — no human or agent edit fills in the body after the typed write.

**Instance — `## Tasks` plan-spine block.** The `## Tasks` machine-parseable spine (single
` ```yaml plan-tasks ``` block, schema `coordinator/schemas/plan-tasks.schema.json`) is today
governed as a Tier 2 prose seam — see below — mutated by free-form hand-edit, warn-only. It
additionally acquires a Tier 1 typed writer: the `plan_tasks.mutate` CLI (verbs `stamp` /
`set` / `defer` / `undefer` / `add-task`) for programmatic mutation. Full contract — verb
surface, invocation shape, error envelope, idempotency semantics — lives at
`docs/wiki/plan-tasks-mutate-cli.md`. This is coexistence, not replacement: the Tier-1 CLI is
**additive**; the Tier-2 hand-edit path documented below stays valid and warn-only — it is
neither blocked nor deprecated by the CLI's existence. The two tiers apply to the same
artifact simultaneously, per the two-tier model this section documents.

### Tier 2 — Prose Seam (Warn, Never Block)

The PreToolUse hook `hooks/scripts/validate-frontmatter-schema.js` governs free-form
`Write`/`Edit`/`MultiEdit` calls on schema-matching paths. Its behavior:

- **Default: WARN (offer-shape).** Schema violations are emitted as `additionalContext`
  (never `permissionDecision: deny`) so the write proceeds and the agent sees the gripe.
  The warning text: *"The write will proceed. Fix the frontmatter on the next edit…
  Periodic drift is swept by /update-docs."* This is the design-as-offers pattern
  (`docs/wiki/eager-agent-calibration.md`): the hook leads with the better alternative,
  never the wall.
- **Scaffold offer for GENERATE-able new-file writes.** On a `Write` call where the target
  path does not yet exist AND the path matches a GENERATE-able schema type, the hook appends
  a `coordinator-doc-new --type <type> …` command offer to `additionalContext` alongside any
  schema gripe. This extends the design-as-offers generator redirect that previously applied
  only to cross-repo memos (`buildMemoOfferPayload`) to all GENERATE-able schema types —
  the preferred path is to invoke the scaffolder and fill the body, not author frontmatter
  from scratch. The write still proceeds (warn-only); the offer fires on new-file creation
  only (`toolName === 'Write'` AND path does not yet exist), never on edits to existing
  schema'd files, so scaffold-then-fill workflows are not self-triggering. Wired in:
  `cli-scaffold-deterministic-docs` C0a (`buildScaffoldOfferPayload` in
  `hooks/scripts/validate-frontmatter-schema.js`).
- **Strict mode exception:** `COORDINATOR_SCHEMA_STRICT=1` upgrades to deny. Test-only.
  Never set in production.
- **Own-inbox deny (structural, not enum):** the own-inbox cross-repo-memo misplacement
  guard (`buildOwnInboxDenyPayload`) IS a hard deny even in warn-mode. This is a routing
  correctness guard, not an enum correctness guard — a fundamentally different concern.
- **Infra failures are silent.** The hook NEVER exits non-zero on its own infra failures;
  logging to stderr and allowing the write prevents infra noise from blocking legitimate
  work.
- **Lenient on unknown keys.** Extra optional keys are tolerated, not rejected. This is
  the mechanism that allows per-repo dialect keys (`scope_mode`, `spec_backlink`, etc.) to
  accrete without tripping the hook.

**The asymmetry is intentional and load-bearing.** Structured-append is fail-loud because it
has a clean typed write at a single entry point with no human/agent latitude needed
afterwards. Free-form Write/Edit is warn-only because that is where humans and agents need
the latitude to add local keys, annotate with novel fields, and author expressive body
content — amputating the **prose body** to enforce a deterministic skeleton would violate the
hard guardrail. The exemption is **body-scoped, not artifact-scoped**: a structured index
layer (registry-conformant frontmatter + promoted structured sub-artifacts) OVER an
expressive prose body is permitted and is the RAG-bait-at-structural-boundaries pattern the
coordinator already applies everywhere (see § The Baton Blob — Scope and Purpose above,
which already frames this for batons: "the index layer … that leaves the expressive body
dialects intact"). What the guardrail forbids is imposing a template on the prose body, not
adding queryable structure around it.

**Negative-spec — body-scoped, not artifact-scoped.** An expressive artifact (a
deep-research synthesis, a design narrative) is NOT exempt from carrying a queryable index
layer. Adding registry-conformant frontmatter and promoting already-structured sub-artifacts
(e.g. a claims sidecar) over an expressive body is permitted and is the
RAG-bait-at-structural-boundaries pattern. What the exemption forbids is imposing a
deterministic skeleton on the PROSE BODY — the high-variance prose stays agent-authored.
The expressive/queryable distinction lives at different LAYERS of the same artifact, not at
the artifact boundary (→ § The Baton Blob — Scope and Purpose above).

---

## Cross-Type Consolidation Principle and Schema-Registry Contract

### The Consolidation Principle

The fleet already has a strongly-percolated backbone (21 schemas → read + guard altitudes;
project-rag, cockpit, and example-game-repo carry byte-compatible core frontmatter). The ambition of
the example-initiative roadmap is to turn this implicit registry into an **explicit, versioned, published
artifact-shape contract** — the same shape the cockpit-contract owner-enum seam
(`docs/plans/2026-06-25-cockpit-contract-owner-enum-seam.md`) already proves in-tree as the
in-tree existence proof that the move is achievable. **That plan is cited as proof; this
wiki does NOT extend its scope or couple to its implementation.**

Consolidation is guided by two tests:
1. **Same concept, N spellings → consolidate.** Author (4 spellings: plan `author`,
   handoff `machine`+`authoring_session`, decision `deciders`+`authors`), predecessor/lineage
   (4 spellings), liveness/status (1 key name, multiple incompatible enums). These are the
   cleanest consolidation wins.
2. **Load-bearing divergence → record as deliberate.** Memo `from`/`to` (receiver-routing),
   handoff `deployment_state` (readiness axis separate from `status` record axis),
   decision 4-section ADR body (the most machine-extractable body in the family) — these
   diverge for architectural reasons. The canonical shape records them as deliberate-keep
   with a named rationale, not as consolidation targets.

### Schema Registry as Published Contract

The schema registry (`schemas/*.yaml`, 21 schemas)
currently drives two altitudes:
- **VALIDATE** — the warn-not-block hook (offer-shape at the prose seam)
- **QUERY** — `query-records.js` derives its `--type` set from the registry at startup;
  adding a schema automatically makes a new `--type` available

The `cli-scaffold-deterministic-docs` workstream ratifies a third altitude as a **producer obligation**:
- **GENERATE (producer obligation)** — `coordinator-doc-new --type handoff|spinoff|memo …`
  is the **required entry point** for creating a schema-registered document; hand-authoring
  the frontmatter is a producer obligation violation (tripwire: `SCHEMAED-DOC-GENERATE-OBLIGATION`
  in `docs/wiki/coordinator-tripwires.md`). The scaffolder emits conformant frontmatter + the
  canonical section skeleton from the registry; the EM fills the body via Edit. For list-shaped
  artifacts it writes the whole file; for expressive batons it scaffolds and the body is filled.
  This eliminates drift at the source by making the schema the production entry point, not
  merely the validation rule. The Tier-2 warn hook enforces this obligation at the prose seam
  — a new-file Write on a GENERATE-able path emits a scaffold offer alongside any schema gripe
  (see § Warn-Not-Block Enforcement Posture below).

The tc-4 node extends this to **EMIT** — a versioned artifact-shape contract that downstream
consumers (project-rag store, cockpit dashboard) derive from without re-reading the source
registry. The cockpit-contract plan's Zod-source → emitted-versioned-JSON-Schema pattern is
the proven in-tree model; tc-4 applies the same pattern to the coordinator artifact shapes.

**The schema registry is the single source of truth.** Adding a `schemas/*.yaml` makes a
new `--type` queryable, validateable, scaffoldable, and (after tc-4) emittable in the versioned
contract. No type is registered twice; no per-type tooling re-implements shape logic the
registry already encodes.

#### Registered Schemas (selected — tc-2 and tc-3 additions)

| Schema | Schema file | `applies_to` glob |
|---|---|---|
| `improvement-queue` | `schemas/improvement-queue.schema.json` | `state/improvement-queue/*.yaml` |
| `bug-backlog` | `schemas/bug-backlog.schema.json` | `state/bug-backlog/*.yaml` |
| `debt-backlog` | `schemas/debt-backlog.schema.json` | `state/debt-backlog/*.yaml` |
| `lessons-outbox` | `schemas/lessons-outbox.schema.json` | `state/lessons-outbox/*.yaml` |
| `lessons` (schema `lesson-entry`) | `schemas/lesson-entry.yaml` | `state/lessons/*.yaml` |
| `audit-record` | `schemas/audit-record.schema.json` | `docs/architecture/audit-records/*.md` |
| `review-integration-record` | `schemas/review-integration-record.schema.json` | `state/review-trail/*-integration.json` |
| `roadmap` | `schemas/roadmap.schema.json` | `state/roadmap/*/OVERVIEW.md` |
| `tracker` | `schemas/tracker.schema.json` | `docs/project-tracker.md` |
| `health-status` | `schemas/health-status.schema.json` | `state/health/*.md` |
| `decision-guide` | `schemas/decision-guide.schema.json` | `docs/guides/*-decisions.md` |
| `skill` | `schemas/skill.schema.json` | `plugins/coordinator/skills/*/SKILL.md` |
| `research-synthesis` | `schemas/research-synthesis.schema.json` | `docs/research/*.md` |
| `research-claim` | `schemas/research-claim.schema.json` | `docs/research/*.claims.json` |
| `coverage-audit` | `schemas/coverage-audit.schema.json` | `docs/research/*-coverage-audit.md` |
| `gap-report` | `schemas/gap-report.schema.json` | `docs/research/*-gap-report.md` |
| `workstream` | `schemas/workstream.schema.json` | `state/workstreams/*.yaml` |
| `workstream-event` | `schemas/workstream-event.schema.json` | `state/workstreams/events/*.yaml` |
| `plan-tasks` | `schemas/plan-tasks.schema.json` | none (`$ref`'d sub-schema of `plan.schema.json`'s `tasks` property — not a directly-authored artifact glob; validates the per-row shape of the body-resident `## Tasks` fenced-YAML task spine) |

<!-- 2026-07-09 added plan-tasks (v1.13.0, schema_count=48) — per-row schema for the ## Tasks
     machine-parseable task-spine (plan-full-coverage-and-deferred-harvest C1). Registers as its
     own top-level $def (the dual-format loader in bin/lib/schema.js counts every schemas/*.schema.json
     file regardless of applies_to presence) but deliberately carries no applies_to — it is a $ref'd
     sub-schema of plan.schema.json's new `tasks` property, not a directly-authored artifact glob.
     change_kind enum is the WIDER UNIVERSAL 10-value set; SSOT is docs/wiki/lessons-outbox-schema.md
     § Change-kind enum (this schema cites that doc, not the reverse). Enum-parity test:
     bin/tests/test-plan-tasks-schema-enum-parity.sh. -->

<!-- 2026-06-30 deep-research-queryable-index-layer added research-synthesis (run record), research-claim
     (per-claim record, N-per-file synthetic enumeration), coverage-audit, gap-report — the queryable index
     layer over the PROTECTED expressive deep-research prose body. Emitted into the artifact-shape contract at
     v1.7.0. Producers across all 4 DR pipelines (web/repo/structured/notebooklm) emit these to docs/research/
     with deterministic frontmatter; the prose body stays agent-authored (never templated). -->

<!-- tc-2 (example-initiative-2026-06-25) added improvement-queue, bug-backlog, debt-backlog, lessons-outbox as first-class
     $defs in the published artifact-shape contract (v1.1.0, schema_count=21). Each carries an
     x-coordinator-applies_to annotation in the emitted JSON Schema — the same glob value shown in the
     applies_to column above. Validatable via the warn-not-block hook (Tier 2 — prose seam).
     Full registry: ls schemas/*.yaml -->
<!-- tc-3 (example-initiative-2026-06-25) added audit-record (v1.1.0, schema_count=17). -->
<!-- Review: code-reviewer F6 — version/count annotation added to match tc-2 comment style;
     confirmed from git show e54a09df on artifact-shape-contract.schema.json. -->
<!-- 2026-06-26 added review-integration-record (v1.2.0, schema_count=22) — PERMISSIVE container
     (no required fields, additionalProperties allowed) for EM-hand-authored review-integration
     audit blobs written at /workstream-complete. These blobs co-locate with strict review-trail
     records at state/review-trail/ but have no stable shape across instances; the permissive
     container claims the more-specific glob *-integration.json, distinguishing them from the
     strict review-trail $def which claims *.json. -->
<!-- 2026-06-26 added roadmap, tracker, health-status (v1.4.0, schema_count=25) — three new
     portfolio/operational artifact types promoted from the example-initiative example-workstream example-repo ask list.
     roadmap: forward-horizon planning record per repo (state/roadmap/*/OVERVIEW.md — nested OVERVIEW only, not sidecars).
     tracker: current status board / action register; single file (docs/project-tracker.md).
     health-status: periodic health summary/ledger; liveness keys on lifecycle status (LIVE/DONE),
       NOT on health posture (HEALTHY/WATCH/ACTION/CRITICAL) (state/health/*.md). -->
<!-- 2026-06-27 added decision-guide (v1.6.0, schema_count=26) — consolidated/distilled terminal
     shape of a DR corpus. Container document; liveness keys on document currency (active/archived),
     NOT per-decision lifecycle. Sibling of per-file `decision`; per-file decision remains the
     escape hatch for individually-tracked/contested decisions.
     Spec backlink: cross-repo/inbox/2026-06-27-example-stats-repo-decision-records-fleet-share.md § Q2 -->
<!-- 2026-06-27 added skill (v1.7.0, schema_count=27) — validates YAML frontmatter of coordinator
     skill files (skills/*/SKILL.md). Required set: name + description only. additionalProperties:false
     (closed key set — a new frontmatter key requires a one-line schema edit; the ccos-1 dual-context
     validator bin/lint-frontmatter.js surfaces the violation with an error hint). Scope is
     coordinator-only: the glob targets plugins/coordinator/skills/*/SKILL.md,
     explicitly excluding vendored trees (plugins/cache/, plugins/marketplaces/) and first-party
     siblings (deep-research, example-game-repo-control) — those are a deferred widening, not in-scope for
     the initial registration. Enforced by bin/lint-frontmatter.js (ccos-1 validator, dual-context:
     PreToolUse warn-not-block + CLI exit-on-error for CI).
     Spec backlink: docs/plans/2026-06-27-ccos-10-skill-manifest-schema.md
     Schema is JSON-backed (skill.schema.json), routes via the `_isJsonSchema` path in
     `validateFrontmatterDispatch`. YAML-dialect keyword forms (required-as-list, bare-string
     type) do NOT apply — use JSON Schema keywords only.
     Review: code-reviewer Slice B — (F4) note JSON-backed schema path so maintainers don't apply YAML-dialect forms -->
<!-- 2026-06-30 added research-synthesis, research-claim, coverage-audit, gap-report — deep-research queryable record families; docs/research/ glob.
     CONTRACT_VERSION bumped 1.6.0 → 1.7.0 (emitted 2026-06-30): re-emit picked up these 4 + all prior
     unemitted additions (skill, session-event, session-events-summary [both removed 2026-06-30 — ccos-4 writer torn down, cockpit consumer never shipped], session-hierarchy, completion-entry, etc.),
     fixed the JSON-Schema pass-through (plan.source_memo anyOf, review-integration-record relaxations) and the
     bare-nested-object `system` descriptor (bug/debt/improvement queues, lesson-entry). 36 schemas on disk; emit
     test 12/12. Verified ADDITIVE-ONLY vs prior emit (0 defs removed, 0 narrowings) → minor bump; the
     major-only version gate does not fire, so no consumer (project-rag/cockpit) is forced to re-vendor. -->
<!-- 2026-07-02 removed file-attribution row schema + session-event/session-events-summary drift (v1.9.0, schema_count=42) — ccos-6 re-homed to on-demand transcript derivation (bin/derive-file-attribution.py); no persisted ledger. -->
<!-- 2026-07-08 added workstream, workstream-event (project-tracker render-from-queue store,
     chunk C2) — two new schemas, CONTRACT_VERSION bump warranted per the bump rule below
     (schema_count delta). Both are lifecycle-free (no status/lifecycle enum; see the
     Design-Complete Mapping Table's N/A rows, week-changelog precedent). GENERATE altitude
     only (coordinator-queue-append --schema workstream|workstream-event), per AC8a.
     Review: code-reviewer — Finding 3 (P2): schemas landed in C2 without this registry
     bookkeeping; corrected here. Emission into artifact-shape-contract.schema.json (tc-4
     EMIT altitude) is a separate re-emit step, not performed as part of this fix — the
     emitted contract's own version/schema_count trail is authoritative for the EMIT
     altitude and is bumped at re-emit time, not by this wiki edit alone. -->

#### CONTRACT_VERSION bump rule

A `CONTRACT_VERSION` bump is warranted when a change alters the **schema** (adds/removes/renames a field or type), **enum values** (widening or narrowing a value set), or **`schema_count`** (schemas added or removed from the registry). An emitted-annotation-only correction — fixing the _values_ emitted into existing fields with no schema, enum, field, or count delta — does NOT warrant a bump; notify consumers and let them re-vendor at leisure instead.

---

## Negative-Spec Block — Hard-Won Corrections

> This section records explicit design rejections so future maintainers and agents do not
> re-propose them. Each entry cites the plan decision where the rejection was ratified.

- **No `lifecycle:` / `live:` / `liveness:` frontmatter key.** A stored liveness field
  duplicates the enums it is derived from and will drift. The predicate is computed at
  query time from the existing enums. (D2, ratified in `docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § Ratified design decisions`)

- **No cross-type consolidation of `status` values.** `status: open` on a memo and
  `status: active` on a handoff are NOT comparable enum values even though they are both
  expressed under the key `status`. The liveness predicate abstracts over them; the raw
  enum values must not be treated as cross-type comparable without the predicate layer.

- **No single body grammar.** Handoffs carry two incompatible body dialects (session-handoff
  vs spinoff), memos a third. Forcing one body grammar would flatten genuine differences — a
  guardrail violation (expressiveness is a hard constraint). Consolidation targets the
  index (frontmatter + section vocabulary), not the body dialects. (D1, ratified in the same plan)

- **No schema-convergence tightening of required-set.** Adding a field to `required:` that
  legacy artifacts lack re-creates fight-the-hook from the other side. New canonical keys
  land in `optional:`; consolidation renames/aliases but never tightens required-set against
  existing on-disk artifacts. (C2 additive-only hard constraint)

- **`coordinator-doc-new` does NOT reroute the memo SEND path.** The memo send/delivery
  surface (`bin/cross-repo-memo`) owns receiver-routing, realpath containment, single-surface
  delivery, self-receipt, and the pickup claim-lock. `coordinator-doc-new --type memo` emits
  a local skeleton only; the send path stays in `bin/cross-repo-memo`. (D3 + F3 from the Director of Engineering review)

- **No diagram images or embedded SVG.** Diagrams are always ASCII under `### Diagram (ASCII)`.
  This preserves raw-markdown readability and git-diffability.

- **Do not treat `plan_tasks.mutate`'s existence as grounds to deprecate or gate Tier-2
  hand-edits to the `## Tasks` spine.** The Tier-1 CLI is additive coexistence, not a
  replacement gate — the Tier-2 warn-only hand-edit path stays valid. See
  `docs/wiki/plan-tasks-mutate-cli.md § Tier posture`.
  <!-- Review: code-reviewer — the coexistence-not-replacement guarantee is made inline at Tier 1 (§ Tier 1 above) but this file's durable-prohibition home is this block; mirrored here per the existing bullets' shape. -->

---

## tc-1 — Record-family doctrine

> Spec backlink: `docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md`
> Implemented: tc-1 C3 (schemas + doctrine), C1 (plan.yaml), C2 (decision.yaml), C4–C9 (machinery + ports).

This section records the ratified design decisions for the **record family** — plans,
decisions, and the co-located sidecar companions — as binding doctrine inherited by tc-2
(queues: lessons + improvement/bug/debt), tc-3 (expressive + audit shapes), and tc-4
(fleet machinery + versioned emit). The decisions below were EM/reviewer ratifications
(refactor mechanics + schema shape), reviewed by the Staff Engineer. They extend tc-0's keystone
without altering the baton-blob doctrine, the liveness predicate, or the warn-not-block
enforcement posture established above.

### D1 — Promoted plan keys

The following de-facto plan keys are promoted to `plan.yaml` `optional:` (additive-only,
per the C2 hard constraint inherited from tc-0):

| Key | Semantics |
|-----|-----------|
| `scope_mode` | Plan altitude/mode (e.g. `architecture`, `implementation`, `spike`) |
| `problem_set` | Problem framing — `inline` (body carries it) or a path reference |
| `predecessor_handoff` | The handoff that spawned this plan — links to `state/handoffs/` |
| `prerequisite_of` | Roadmap-graph edge: the downstream node that gates on this plan |
| `source_memo` | The cross-repo memo(s) this plan acts on, if any; type is `string-or-list-of-string` — a plain string for the common single-memo case, a list when the plan is initiated by multiple memos (multi-source provenance). Expressed as an `anyOf` union in the published v1.2.0 contract. |
| `scope` | List-of-path pathspecs scoping the work; borrowed from the handoff schema |

**Lineage distinction — `predecessor_handoff` vs `parent_plan`.** These are not spelling
variants of the same concept. `predecessor_handoff` names the **handoff that spawned the
plan** (session-boundary lineage); `parent_plan` names a **parent plan** (plan-hierarchy
lineage). Both are kept and documented; they must NOT be collapsed into one key.

**Recognize-but-do-not-promote (tolerated legacy keys):** `parent_plan`, `research_input`,
`borrow_disposition`. These are documented in `plan.yaml` schema comments as legacy keys
tolerated by the warn-not-block hook but not elevated to the canonical key set — they do
not recur across ≥3 recent plans and are not queried in practice.

### D2 — `## Anti-scope` and `## Out of scope` are DISTINCT canonical sections

These two headers cover **different jobs** and must NOT be merged or aliased:

- **`## Anti-scope`** — **failure modes / pitfalls** a context-less picking-up EM might
  hit. Its job is negative scope: *"do not do X, it breaks Y."* This is the section where
  the plan author warns against approaches that look tempting but are wrong for this artifact.
  See `skills/spinoff/SKILL.md` lines 79–80 as the load-bearing source of this distinction.

- **`## Out of scope`** — **adjacent work explicitly not included** in this artifact.
  Its job is boundary scope: *"X is real work but belongs to another node/owner."* It names
  things the reader might expect to find here but won't, and says where they live instead.

The tc-1 C8 port normalizes **spelling and case only** (folds `## Anti-Scope`,
`## anti-scope`, `## Out-of-scope`, `## Out Of Scope` onto the two title-case canonical
headers). It does NOT rewrite a body that uses one header into the other — the two sections
cover distinct concepts and are preserved as-is when a plan carries both.

### D3 — Decision canonical identity key is `id`

The canonical identity key for decision records is **`id`** (the form used by 150 of the
203 on-disk decisions; the dominant DR-NNN form). The minority spelling `decision_id` (51
files, newer DR-195/200/201 vintage) is ported to `id` by the tc-1 C7 pass.

`id` is declared in `decision.yaml` `optional:` (additive-only — cannot be `required:`
because the ~3 date-prefixed non-DR decisions legitimately lack a DR number).

**Why `id` over `decision_id`:** dominance (150 vs 51, minimizing churn) and
informality (shorter key). `decision_id` is more self-documenting, but the port reverses
recent practice on the strength of dominance and churn-minimization. The `DR-NNN` handle
value is preserved regardless of key name, so cross-references in prose and
`supersedes: DR-NNN` fields are unaffected.

### D4 — Canonical temporal key is `created`

`created` is the **fleet-canonical temporal key** for all record-family artifacts, consistent
with the tc-0 baton doctrine (§ "Shared Core Keys" above). The redundant `date` field
(199 decisions carrying both keys with identical values) is dropped in the C7 port. No new
key is introduced; `created` is the single recognized temporal axis for `--since` /
`--older-than` filtering in `query-records`.

### D5 — Sidecar suffix grammar: strict, co-located, full normalization

The canonical sidecar suffix set is:

| Sidecar type | Canonical suffix | Schema file |
|---|---|---|
| Reviewer / verdict | `.review.md` | `schemas/review-sidecar.schema.json` |
| Reviewer iteration (distinct reviewer, N ≥ 2) | `.review-N.md` | `schemas/review-sidecar.schema.json` |
| Prior-art check | `.prior-art-check.md` | `schemas/prior-art-check.schema.json` |
| Plan-coverage check | `.plan-coverage-check.md` | `schemas/plan-coverage-check.schema.json` |
| Docs check | `.docs-check.md` | `schemas/docs-check-sidecar.schema.json` |

**Canonical stem form** is `<plan-stem>.<suffix>.md` — a single `.md` extension. The legacy
double-`.md` form (`<plan-stem>.md.<suffix>.md`) is ported to the single-`.md` form by the
tc-1 C9 broadsword pass.

**Sidecars stay co-located** in `docs/plans/`. A `<plan>.sidecars/` subdir was evaluated and
rejected: it would break every inbound link for no query gain, since `query-records` already
excludes co-located sidecars by suffix pattern.

**Irregular suffix distinctions** previously encoded in filename suffixes (`.the Staff Engineer-r1`,
`.reviewA`, `.reviewB`, `.the Staff Engineer-skill-review`, `.the Staff Engineer-substrate-adjudication`,
`.the Staff Engineer-review-f0-followup`, timestamped `.plan-coverage-check.<ISO>`, `.coverage-check`)
are captured in **frontmatter** after the C9 port — fields such as `reviewer:`,
`predecessor_review:`, `mode:`, `created:`. The filename carries only the canonical type
suffix.

**EXCEPTION — distinct-reviewer iteration sidecars.** When a plan receives sidecars from
two or more distinct reviewers, each gets its own file: `<stem>.review.md` (first reviewer)
and `<stem>.review-2.md`, `<stem>.review-3.md` … (N ≥ 2 for subsequent reviewers). This is
the **canonical iteration form** — see `schemas/review-sidecar.schema.json` C9b comment and tc-1
Execution Notes § C9b. Folding two reviewers into one file loses per-review verdict and
`reviewer:` fields — do NOT merge distinct-reviewer sidecars into a single file.
`query-records` excludes `*.review-N.md` alongside `*.review.md` via the
`REVIEW_ITERATION_RE` check (C9b).
<!-- Review: F2 — D5 paragraph contradicted canonical C9b decision; distinct-reviewer sidecars stay as separate .review-N.md files, not folded to frontmatter -->

**Sidecar-family section grammar (shared core).** Every sidecar, regardless of type, carries
this minimal shared structure:

- **`## Summary`** (or a top-level verdict line as the first non-frontmatter prose) — a
  single-paragraph or single-line verdict: what the sidecar concluded, pass/fail/conflict
  count, or other top-level outcome.
- **`## Findings`** — the enumerated findings, one per subsection or list item. Type-specific
  sections (e.g. `## Conflicts`, `## Compatible`, `## Auto-Fixed Items` for specific sidecar
  types) appear under or alongside `## Findings` per the individual sidecar schema.

This shared grammar is documented in each sidecar schema's comment block (tc-1 C3).

**Broadsword rationale.** Full normalization of all ~81 sidecars in one pass (C9) rather than
incremental porting is the correct approach here: a half-ported family leaves the double-`.md`
form alive, which means the exclusion rule in `query-records` must tolerate two stem shapes
indefinitely. Full normalization makes the disk uniformly conformant in one wave, lets the
exclusion rule assume exactly one stem shape, and gives the sidecar scaffolder (`coordinator-doc-new
--type review|prior-art-check|plan-coverage-check|docs-check`) a single output form to emit.
After C9, the `query-records` Layer-2 kind-fallback denylist (dead code post-port) is retired
and replaced by a positive anomaly detector (C4).

### D6 — `completion-entry` nullable fields: omit-on-emit, tolerate-null-on-ingest

> Spec backlink: `schemas/completion-entry.schema.json` (optional fields `chain` and `chain_span_days`).
> Pattern: same dual-altitude contract as `loe` sub-fields (number-or-null since 2026-05-28).

The `chain` and `chain_span_days` fields in `completion-entry` carry a deliberate two-altitude
contract that can appear contradictory at first read but is not:

- **Schema type:** `chain: string-or-null`, `chain_span_days: number-or-null`. The `null`
  variant is a valid schema value — the validator (Tier 2 warn-not-block hook) accepts it.
- **Producer side — omit when unset:** generators (`/workstream-complete`, `bin/aggregate-chain-loe.sh`)
  emit `chain` and `chain_span_days` only when the value is known. Standalone single-session
  work with no upstream chain context omits the key entirely. **Do not write `chain: null`.**
- **Ingest side — tolerate null:** consumers and validators accept `null` as a valid value,
  enabling downstream code to distinguish "field absent" from "field present with null value"
  when ingesting entries authored by older or partial chain-walkers.

**Canonical guidance: omit on emit; tolerate null on ingest.** A reader seeing `chain: null` and
a reader seeing no `chain` key should treat them identically — both mean "no chain context
recorded." This is NOT a contradiction between the schema (`null` permitted) and the producer
guidance (omit when unset) — they are complementary contracts at different altitudes. The
schema permitting `null` prevents ingest-side explosions on entries where a chain-walker
emitted a null before the omit-guidance was codified; the producer guidance prevents new
entries from polluting the field unnecessarily.

`chain_span_days: null` specifically signals "chain has only one session, or no datable
predecessor" — the chain walk succeeded but the span was not computable. Absent key means
the walk was not attempted or the entry predates chain tracking.

---

## lvv-01 — Durable cross-artifact stable IDs + `Resolves:` commit trailer

> Spec backlink: `docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md`
> Implemented: C1 (mint seam + `hnd-`/`cmp-` IDs), C2 (ID-companion ancestry fields),
> C3 (soft-warn existence-validation), C4 (`Resolves:` trailer convention + parser),
> C5 (`rollup-derive.sh` roll-up primitive).

This cluster adds a **stable-ID layer** on top of the baton-blob doctrine above, closing
the gap named in § The Baton Blob: cross-artifact ancestry was path-based and rotted on
archival/rename, and two artifact types (handoffs, completion-entries) had no stable ID
at all. The additions here are **path-independent join keys** and a **git-native
completion link** — neither introduces a stored liveness/roll-up field (D2 above still
holds).

### Stable-ID table

| Prefix | Artifact type | Pattern | Minted by | Field |
|---|---|---|---|---|
| `pln-` | Plan | `pln-<slug[:30]>-<6hex>` | `coordinator-doc-new` `_mint_plan_id` (shim over `_mint_artifact_id(prefix="pln", …)`) | `plan_id` |
| `dlv-` | Deliverable | `dlv-<slug[:30]>-<6hex>` | `mint-deliverable-id.sh` | `deliverable_id` |
| `hnd-` | Handoff / spinoff | `hnd-<slug>-<6hex>` | `coordinator-doc-new` `_mint_artifact_id(prefix="hnd", …)` | `handoff_id` (optional; `schemas/handoff.schema.json`) |
| `cmp-` | Completion entry | `cmp-<slug>-<6hex>` | `coordinator-doc-new` `_mint_artifact_id(prefix="cmp", …)` | `completion_id` (optional; `schemas/completion-entry.schema.json`) |

All four prefixes share one canonical uniqueness basis —
`sha1(slug|epoch-seconds|pid|random[0,65535))[:6]` — reconciled during this cluster's C1.
Before the reconciliation, two DIFFERENT bases had already diverged on disk:
`_mint_plan_id` used epoch-MICROSECONDS with no random component, while
`mint-deliverable-id.sh` (the cross-language seam mirrored independently in
`bin/normalize-handoff-frontmatter.js`'s `mintDeliverableIdFromSlug`) used
epoch-seconds+pid+`$RANDOM`. The shell/JS basis was chosen as canonical because it has the
real cross-language callers (`skills/handoff`, `skills/spinoff`, `skills/roadmap-planning`,
plus the JS mirror); `coordinator-doc-new`'s new `_mint_artifact_id(prefix, slug)` replicates
that formula in-process (Python `hashlib.sha1`/`random.randint`) rather than shelling out —
`_mint_plan_id` is now a thin shim over `_mint_artifact_id(prefix="pln", …)`.
`mint-deliverable-id.sh` and the JS mirror are unchanged call shapes; only
`coordinator-doc-new`'s formula moved onto their basis, closing the divergence without
adding a third algorithm. `hnd-`/`cmp-` are **optional, additive** fields with **no
backfill** — pre-existing handoffs and completion entries carry no stable ID and are not
retroactively migrated (consistent with the existing handoff schema no-migration policy for
`origin_*` fields).

**ID-companion ancestry fields (add-not-swap).** The handoff schema family gained
`predecessor_id` and `origin_handoff_id` — ID-typed companions to the existing
`predecessor`/`origin_handoff` path fields. The path fields remain the human-legible
display string; the ID companion is the path-independent mechanism a machine walks.
Existence-validation and the never-silently-disagree check (path and ID companion must
resolve to the same artifact when both are non-null) live in `bin/lib/schema.js`
`checkReferentialIntegrity(record, resolver, options)` — a **separate exported function**,
deliberately NOT a `CROSS_FIELD_RULES` addition, since `CROSS_FIELD_RULES` closures run
unconditionally inside `validateFrontmatter`/`validateRecord` while this check needs an
injected resolver only cadence gates can supply. `CROSS_FIELD_RULES` and its two existing
entry points (`applyCrossFieldRules`, `applyCrossFieldRulesFor`) stay untouched — no
refactor, per the "DO NOT rewrite or simplify `CROSS_FIELD_RULES`" constraint. Scope is
LOCAL handoff-DAG refs only (`predecessor_id`, `origin_handoff_id`); `deliverable_id` and
`initiative` are deferred pending their central-vs-local resolution-plane determination.
`checkReferentialIntegrity` is **soft-warn** by default — dangling refs are the normal
state of in-flight work, matching the Tier 2 warn-not-block posture documented above
(§ Warn-Not-Block Enforcement Posture); hard-block is opt-in and fires only at a named
cadence gate (`/workweek-complete`). This does NOT introduce a third enforcement tier, it
is the same posture applied to a new FK class.

### `Resolves:` commit trailer

Stable IDs alone don't answer "has the commit that finishes this artifact actually
shipped?" — that is the job of the new `Resolves: <artifact-id>` commit trailer, documented
in full at `coordinator/docs/wiki/resolves-commit-trailer.md`. In one line: a commit that
completes work on a durable artifact carries a `Resolves: <artifact-id>` git trailer
(one line per resolved artifact); `coordinator/bin/parse-resolves-trailer.sh` extracts the
IDs from a commit's trailers, and `coordinator/bin/rollup-derive.sh <artifact-id>`
re-derives (never caches) one of four tokens — `shipped`, `not-shipped`, `unknown-error`,
`no-resolving-commits` — by combining the trailer search with `check-shipped-on-main.sh`.

**This is git-native, not a schema field.** No artifact schema gained a `resolved_by:` or
similar field — the roll-up-derivation primitive re-derives from commit history on every
call, consistent with the negative-spec above (§ Why DERIVED, Not Stored (D2)):
"no `lifecycle:`/`live:`/`liveness:` key appears in any baton schema" generalizes here to
"no roll-up/shipped-state key is stored either — it is derived from `Resolves:` trailers
on read."

**Negative-spec:** do not hard-enforce FK existence outside `/workweek-complete`; do not
store a stable-ID-resolution result on the referencing record; do not treat a `shipped`
roll-up derivation as frozen (a resolving commit can leave `origin/main` on history
rewrite — re-derive, don't cache).

---

## tc-2 — Queue + lessons doctrine

> Spec backlink: `docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md`
> Implemented: tc-2 C3 (doctrine + liveness table), C1 (unified writer schema), C2 (queue schema wikis), C4 (liveness + lesson-parse machinery), C5 (lesson-entry.yaml), C6–C7 (port + sweep).

This section records the ratified design decisions for the **queue family** — improvement-queue,
bug-backlog, and debt-backlog — and the **lessons machine layer** — as binding doctrine inherited
by tc-4 (fleet machinery + versioned emit). The decisions below were EM/reviewer ratifications
reviewed by the Staff Engineer. They extend tc-0's keystone without altering the baton-blob doctrine, the
liveness predicate, or the warn-not-block enforcement posture established above.

### D1 — One base queue schema + optional domain extensions (canonical field names)

The three structured backlogs share one base field-set with optional domain extensions. The
base `required:` set is the small intersection every queue already satisfies on disk:
`created`, `title`, `body`, `status`. Every other canonical field is **base-optional**, and
**required-in-the-domain-extension** that already carries it (additive-only, tc-0 negative-spec).

**Canonical field-name mapping** (killing same-concept-N-spellings):

| Canonical | Replaces | Base Req? | Notes |
|---|---|---|---|
| `created` | `created` (all) | **required** | ISO date; fleet-canonical temporal key (tc-0 § Shared Core Keys) |
| `title` | `title` (all) | **required** | one-line summary |
| `body` | `body` (all) | **required** | block-scalar prose — **expressive, never flattened** (guardrail) |
| `status` | `status` (all) | **required** | base enum `{open, closed, deferred}`; see D-status below |
| `from_repo` | `from_repo` (all) | optional (required in improvement domain) | registry shortname |
| `surface` | `surface` (impr) / `system` (bug) | optional (required in improvement+bug domains) | file/subsystem/script concerned; debt never had it → base-optional |
| `proposed_action` | `proposed_target` (impr) / `suggested_action` (debt) / `recommended_fix` (bug off-schema) | optional (required in improvement+debt domains) | what to do about it |
| `closed_at` | `closed_at` (impr,bug) / `resolved_at` (debt) | optional | closure date |
| `closed_by` | `closed_by` (impr,bug) / `resolution_note` (debt) | optional | closure attribution (SHA preferred; prose tolerated for ported debt) |
| `tags` | `scope_tags` (impr) / `tags` (debt off-schema) | optional | filter tags (list) |
| `evidence` | `evidence` (impr) / `cross_ref` (bug,debt) | optional | provenance: SHA / plan path / related IDs |

**Domain extensions** (additive on base; "required-in-domain" means the typed-seam writer
requires it for that `--schema`, NOT a base-required field):

| Queue | Extension fields |
|---|---|
| improvement | `surface` (required-in-domain), `proposed_action` (required-in-domain), `from_repo` (required-in-domain), `change_kind` (required-in-domain, enum8: script-edit/skill-edit/wiki-append/wiki-new/hook-edit/agent-prompt-edit/doc-edit/test-edit), `queue_scope` (optional, enum `central\|project`) |
| bug | `surface` (required-in-domain — was `system`), `severity` (required-in-domain, enum P0–P3), `repro_steps` (opt), `environment` (opt), `why_blocked` (opt) |
| debt | `proposed_action` (required-in-domain — was `suggested_action`), `risk` (required-in-domain), `source` (required-in-domain — originating-review audit trail; kept as distinct REQUIRED debt field, NOT folded into generic optional `evidence`, per prior-art-checker Claim #12), `severity` (opt, default P2) |

**Status base enum (D-status).** Base = `{open, closed, deferred}` → maps cleanly onto tc-0
liveness LIVE/DONE/BLOCKED. The only retained domain-extension status value is **bug `wontfix`**
(a genuinely distinct lifecycle outcome — conscious rejection, DONE-mapped). The C6 port
reconciles the rest: debt `resolved`→`closed`; debt `open for-weekly-arch-review`→`open` +
`tags: [weekly-arch-review]` (kills the space-bearing enum value while preserving its LIVE
semantics via the tag).

**Negative-spec (additive-only inherited from tc-0):** `surface`, `proposed_action`, and
`from_repo` are NOT base-required. The base required-set is exactly `{created, title, body,
status}`. Adding any of these three to `required:` would break on-disk entries that legitimately
lack them (0 of 36 debt entries carry `surface`; only 1 of 11 bug entries carried the
off-schema `recommended_fix`).

### D2 — Drop the `id` field; `<date>-<slug>.yaml` filename is the canonical handle

The `id` field is dropped from all three queues. Three competing ID schemes existed (uuid4 /
`BS-YYYY-MM-DD-N` / `DSR-`/`CDX-YYYY-MM-DD-N`) for one "unique handle" concept that the
filename already provides. Dropping `id`:

- removes `id` from the base required-set and from `coordinator-queue-append` generation/validation
  (the uuid4/id-prefix-pattern logic);
- makes the filename the identity key in `query-records` (the `path` field is already emitted
  per record);
- the closure `git mv` already keys on filename, not `id`, so archive naming is unaffected;
- cross-references in entry bodies that cite a `BS-`/`DSR-` handle survive as prose `evidence`
  text (the value survives as a string; only the dedicated `id:` field is dropped).

**Note on DSR-prefixed filenames:** 5 debt files are named `DSR-2026-06-23-N-...yaml` (the DSR
id is embedded in the filename). These are NOT renamed — the filename remains a unique handle
and the `id`-field drop is safe for them. The C6 port reconciles their field content only.

Zero cross-references to `id` field values were found in consumer code (query-records, skills,
hooks) — verified against disk at plan-write time.

### D3 — Lessons machine layer is STORED per-entry YAML — captured via `coordinator-lesson-add`

> **Superseded 2026-06-30 by lessons-md-to-queryable-yaml-queue:** lessons machine layer moves from DERIVED-at-query to stored per-entry YAML (PM-ratified capture-friction reversal).

> Previously: DERIVED-not-stored, ratified by the Staff Engineer (tc-2 original). Reversed 2026-06-30 — back-catalog sparsity on `created`/`evidence` (2/97 and 6/97) confirmed DERIVED-at-query could not serve fleet temporal queries; stored entries solve it prospectively.

The lessons machine layer now uses **stored per-entry YAML** at `state/lessons/<date>-<slug>.yaml`, captured via `coordinator-lesson-add` (thin wrapper: `coordinator-queue-append --schema lessons`). Status: STORED, not derived.

- **Capture path:** `coordinator-lesson-add` / `coordinator-queue-append --schema lessons` → writes `state/lessons/<YYYY-MM-DD>-<slug>.yaml`. The `lessons` schema follows the D1 base queue field-set (`created`, `title`, `body`, `status`) with lesson-specific extension fields (`scope`, `target_wiki`, `evidence`).
- **Status ADD (lessons domain):** lessons entries ADD `applied` and `triaged` on top of the D1 base enum `{open, closed, deferred}` — base values are tolerated; `applied`/`triaged` are the lesson-lifecycle values. **D1 base schema is UNCHANGED** — lessons extend, not replace.
- **lessons-outbox** remains the *stored* structured shape at the promote altitude (`/learn-lessons` → `coordinator-lesson-promote`). Capture and promote are distinct altitudes; this change is at capture only.

---

## tc-3 — Expressive-family doctrine

> Spec backlink: `docs/plans/2026-06-25-example-initiative-tc-3-expressive-audit-canonical-shape.md`
> Implemented: tc-3 C4 (atlas top-level frontmatter convention), C5 (week-changelog label-set doctrine), C6 (audit-record schema registry cross-link).
<!-- Review: code-reviewer slice-B F5 — added C4 and C6 to Implemented tag; C4 atlas-frontmatter convention is now doctrine here (see subsection below); C6 is the audit-record schema registry entry already present in the Registered Schemas table. -->

This section records the ratified design decisions for the **expressive artifact family** —
week-changelog dailies, architecture audit records, and atlas files — as binding doctrine
inherited by tc-4 (fleet machinery + versioned emit). The decisions extend tc-0's
addressable-section convention and tc-1's record-family doctrine without altering the
warn-not-block enforcement posture or the baton-blob doctrine established above.

### week-changelog daily — canonical label set

> Spec backlink: `docs/plans/2026-06-25-example-initiative-tc-3-expressive-audit-canonical-shape.md § C5`

Week-changelog daily files (`state/week-changelog/<machine>/<YYYY-MM-DD>-<machine>.md`) carry
a bold-label key/value block whose label **set** is the machine-addressable contract; the
label values range from machine-filled one-liners to rich expressive prose. The producing
command is `commands/workday-complete.md § Step 9` (→ `bin/workday-complete-step9-append-changelog.sh`).

**The canonical bold-label set:**

| Label | Definition |
|-------|------------|
| `Branch:` | Active workstream branch at wrap time. |
| `Commits:` | Commit count (and optionally SHA range) for the session window. |
| `Scope:` | **Expressive free-prose home** — the day's narrative summary; no schema flattens this field. This label is the guardrail: the daily story stays fully expressive while the surrounding label set is the machine-addressable contract. |
| `Plans touched:` | Plans opened, authored, or advanced today. |
| `Handoffs:` | Handoff files written or consumed today. |
| `Decisions:` | Decision records authored or promoted today; extracted from handoff bodies by the producer. |
| `Blockers:` | Open blockers carried forward; extracted from handoff bodies by the producer. |
| `Validation:` | Machine-filled exit-code field — see `docs/wiki/workday-workweek-cadence.md § Week-changelog Validation: schema` for the full enum. Do NOT re-summarize inline here; that wiki section is the authoritative definition (prevents drift between two definitions). |
| `Reviewed:` | Review-trail entries generated today; auto-filled by the producer from `bin/list-review-trail-records.sh`. |
| `Release:` | Release or merge-to-main events, if any. |
| `Links:` | Supplementary links (daily summary path, notable artifacts). |

**Design guardrail — declare the set, preserve the prose.** The label set is the contract;
the values are NOT flattened to enums. `Scope:` in particular is a free-prose paragraph
that carries the session narrative — the expressiveness guardrail from tc-3 applies in full.
A mechanical enforcement gate (`verify-week-changelog-labels.sh`) is deferred by explicit
architectural decision (tc-3 Out of scope): declaration precedes enforcement, and the producer
already machine-enforces the two auto-filled labels (`Validation:` and `Reviewed:`), bounding
the mechanical risk. See `docs/plans/2026-06-25-example-initiative-tc-3-expressive-audit-canonical-shape.md
§ Out of scope` for the full deferral rationale.

### Atlas top-level files — frontmatter format

> Spec backlink: `docs/plans/2026-06-25-example-initiative-tc-3-expressive-audit-canonical-shape.md § C4`
> Clock doctrine: `docs/wiki/atlas-watch-script-convention.md § Within-atlas clock split`
<!-- Review: code-reviewer slice-B F4 — atlas-frontmatter convention was only in inline file comments; adding explicit doctrine here so tc-4 and agents can cite this wiki as the SSOT. -->

The four top-level atlas files (`systems-index.md`, `cross-system-map.md`, `connectivity-matrix.md`, `file-index.md`) carry YAML frontmatter at the top of the file. The canonical frontmatter format for these files is:

| Field | Present? | Semantics |
|-------|----------|-----------|
| `last_mapped:` | **required** | ISO date of the most recent full survey or refresh that produced or last updated this file. Written by `/architecture-survey` (full and refresh runs). |
| `mode:` | required for index/map/matrix; omitted for file-index | The survey mode string (e.g. `"full"`, `"refresh"`). `file-index.md` omits it because the original header had no Mode field. |
| `last_attested:` | **intentionally omitted** | Top-level atlas files do NOT carry `last_attested:`. See below. |

**Why `last_attested:` is intentionally omitted from top-level atlas files.** The two-clock split (`last_mapped:` / `last_attested:`) exists on **per-system atlas pages** (`docs/architecture/systems/{name}.md`) — those are the surfaces the targeted `/architecture-audit` attests. The four top-level files are survey-exclusive artifacts: only `/architecture-survey` (full or refresh) regenerates them; `/architecture-audit` does not touch them. Carrying `last_attested:` on them would create a clock with no writer — `check-atlas-watch-drift.sh` would emit MISSING for every top-level file between surveys. The two-clock split is therefore confined to per-system pages, which are the actual attestation targets. (→ `atlas-watch-script-convention.md § Within-atlas clock split`)

**Negative-spec:** do NOT add `last_attested:` to top-level atlas files. A survey agent that emits it is out of spec; the `check-atlas-watch-drift.sh` probe treats its presence as unexpected on top-level files.

---

## `decision-guide` — Consolidated DR Corpus Container

> Spec backlink: `cross-repo/inbox/2026-06-27-example-stats-repo-decision-records-fleet-share.md § Q2`
> Schema: `schemas/decision-guide.schema.json` | `applies_to: docs/guides/*-decisions.md`

A `decision-guide` is the **consolidated, distilled terminal shape of a mature DR corpus** — a
single narrative document produced when many per-file decision records (`docs/decisions/DR-*.md`)
are folded into one architecture-decision guide by `/distill`. It is a CONTAINER document, not a
single-decision lifecycle record.

**Relationship to `decision`:** Both types coexist. `decision` is the per-file escape hatch for
individually-tracked or contested decisions (proposed/accepted/deprecated/superseded lifecycle).
`decision-guide` is the post-distillation container covering the corpus as a whole. Per-file
`decision` records remain the source of truth until distillation; the guide is the terminal form
thereafter.

| Field | Required? | Type | Semantics |
|-------|-----------|------|-----------|
| `title` | **required** | string | Human-readable guide name |
| `created` | **required** | iso-date | Authoring / last-distillation date |
| `status` | **required** | enum: `active`, `archived` | Document-currency axis — see liveness below |
| `id_range` | optional | string | DR range covered (e.g. `"DR-001–042"`) |
| `decision_count` | optional | number | Total DRs folded into this guide |
| `summary` | optional | string | One-line description of the guide's scope |
| `owner` | optional | string | Owning team or person |

**Liveness mapping (single-axis on `status`):**

| status | Liveness | Rationale |
|--------|----------|-----------|
| `active` | **LIVE** | The guide is current; it is the active reference for the corpus |
| `archived` | **DONE** | The guide has been retired (corpus superseded, repo archived, etc.) |
| unknown | **LIVE** | Open posture — missing status resolves LIVE |

**No BLOCKED bucket.** A decision-guide is either current (LIVE) or retired (DONE); there is no
"gated on an external condition" state for a distilled container document.

**Glob:** `docs/guides/*-decisions.md` — matches `docs/guides/architecture-decisions.md` and the
general `*-decisions.md` convention used across repos in the fleet.
