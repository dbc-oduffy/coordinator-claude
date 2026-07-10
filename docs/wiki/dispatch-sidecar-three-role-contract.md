---
title: Dispatch sidecar — the flight recorder's three-role contract (R1)
created: 2026-07-09
type: doctrine
related:
  - plugins/coordinator/docs/plans/2026-06-09-executor-sidecar-flight-recorder.md
  - plugins/coordinator/docs/plans/2026-07-09-dispatch-sidecar-executor-confinement.md
  - plugins/coordinator/docs/wiki/workflow-orchestration.md
  - plugins/coordinator/docs/wiki/schema-version-gate.md
  - plugins/coordinator/docs/wiki/coordinator-tripwires.md
  - plugins/coordinator/schemas/flight-recorder.schema.json
---

<!--
Purpose: document the flight recorder's extended THREE-role contract (R1 "dispatch sidecar")
introduced by the 2026-07-09 dispatch-sidecar-executor-confinement plan — lifecycle (existing),
dispatch_feed (new, example-orchestration-hub/pcli-04-filled), divergence (new, executor-authored). Names the
write-owner-per-field split, the versioned-schema-is-ground-truth stance, the drift-gate
obligation, and the writes:/reads: spine cross-plan dependency.
Negative-spec: this page does NOT define the example-orchestration-hub emitter (pcli-04/C3) or the plan-tasks
`writes:`/`reads:` spine field (foundations/pcli-01) — both are cited as dependencies, not
authored here.
-->

# Dispatch sidecar — the flight recorder's three-role contract (R1)

## What this is

`COORDINATOR-RESOLUTIONS.md § R1` called for killing the plan-body Dispatch Ledger in favor of
one executor-writable sidecar. That sidecar already existed — the per-chunk **flight recorder**
at `tasks/<plan-slug>/flight/<chunk-id>.md`, shipped 2026-06-09, typed by
`coordinator/schemas/flight-recorder.schema.json`, produced by `fan-out-dispatch.sh` via
`coordinator-doc-new --type flight-recorder`, and read back by `workstream-complete` Step 2.6b.
The 2026-07-09 `dispatch-sidecar-executor-confinement` plan does not build a second artifact — it
**extends the flight recorder in place** (additive schema bump, `x-schema-version` 1.0.0 →
1.1.0) so the same file carries three distinct roles instead of one. That extended file is what
this page calls the **R1 dispatch sidecar** — same file, same location, same producer/consumer
chain, wider contract.

The three roles:

1. **Lifecycle** (existing, unchanged shape) — `dispatched_at`, `dispatched_by`, `status`,
   `commits`, plus the new `started_at`/`finished_at` timestamps. The executor's own
   dispatched → in_flight → complete/blocked/thrashing state machine.
2. **`dispatch_feed`** (new) — a per-chunk object shaped 1:1 against the live `Workflow`
   `agent()` call contract, filled by the example-orchestration-hub emitter (C3/pcli-04), not the executor.
3. **`divergence`** (new) — prose defending any divergence from the chunk's spec, written by the
   executor after the chunk finishes.

## Why one file, three roles — not three files

This is a **deliberate coordinator-side inlining choice**, not a claim that the three roles share
a lifecycle. ExampleOrchestrationHub's own reply on this exact question (`ops/dispatch/` as a new module,
separate from the `ops/emit/` cockpit-snapshot family — "different output kind, different
contract, different lifecycle from the cockpit-snapshot emitter family") treats dispatch
generation as structurally distinct from other emitted output. Coordinator's flight recorder
already had the tested producer chain, the tested consumer chain (`workstream-complete`), and the
tested deny-hook carve-out (`EXECUTOR-PLAN-BODY-IMMUTABLE`) — extending it additively keeps all
three, at the cost of one file now serving three write-owners. A future reader must not infer
from the single-file inlining that lifecycle, dispatch-feed, and divergence share a write-owner
or a lifecycle phase — they don't. See the table below.

## Write-owner-per-field

| Field group | Fields | Write owner | Lifecycle phase | Executor may write? |
| --- | --- | --- | --- | --- |
| Lifecycle | `dispatched_at`, `dispatched_by`, `status`, `commits`, `started_at`, `finished_at` | Executor | In-flight (created at dispatch, updated throughout execution) | Yes — this is the executor's own state machine |
| Dispatch feed | `dispatch_feed` (`label`, `agent_type`, `model`, `effort`, `schema_ref`, `brief_ref`, `phase`, `gate_kind`, `write_files`, `est_min`) | example-orchestration-hub emitter (C3/pcli-04) | Pre-dispatch (filled before the chunk is ever handed to an executor) | **No — READ-ONLY to the executor.** The executor does not author or mutate `dispatch_feed`; it is upstream of the executor's own work. |
| Divergence | `divergence` (`diverged`, `summary`, `detail`) | Executor | Post-run (written after the chunk's work is done, before exit) | Yes — this is the executor's own account of what it did versus what the spec said |

If a future change makes the executor believe it should populate or correct `dispatch_feed`,
that is a signal the inlining assumption above has been violated somewhere — stop and check
against this table before writing.

## `dispatch_feed` — Workflow-transferability is the design goal

The field set exists so that going from a chunk's flight recorder to a ready-to-fire
`workflow.js` `agent()` call requires near-zero transcription. This is the same mapping already
documented in `workflow-orchestration.md § Mapping onto the Dispatch Ledger` (ledger wave → `phase()`
group; ledger chunk row → one labelled `agent()` call; serial gate → `await` boundary +
`if (...) return { halted }`; parallel wave → `parallel([...])`; item pipeline → `pipeline(...)`)
— `dispatch_feed` is that mapping made a typed, per-chunk artifact instead of a table a human (or
an EM) has to re-derive by hand each time.

Per-chunk field set (shaped 1:1 against the live `Workflow` `agent()` contract):
`label`, `agent_type`, `model` (`'sonnet'` default), `effort`, `schema_ref`, `brief_ref`
(pointer to the per-chunk brief/prompt), `phase` (the `phase()` group name the chunk belongs to),
`gate_kind` (`none | file-write-overlap | output-consumption-runtime | contract-change` — maps
onto the await-boundary-vs-`parallel()`/`pipeline()` choice), `write_files`, `est_min`.
`additionalProperties: true` on this object lets the example-orchestration-hub emitter add emitter-specific fields
without a schema round-trip.

**Cardinality: per-chunk, not per-plan.** `dispatch_feed` is one object per flight-recorder file
(one per chunk) — it matches C3's own independent design (spine task → N≥1 dispatch rows). The
per-plan Workflow *envelope* (`meta` + the `phase()`/`parallel()`/`pipeline()` topology) is
assembled separately, by the example-orchestration-hub emitter, from the N per-chunk feeds across a plan's flight
recorders. This wiki page (and the schema it documents) defines the per-chunk `agent()`-shape
only; per-plan derivation and assembly is C3/pcli-04's concern, not this schema's.

## The versioned schema is the ground truth, not the live Workflow API

ExampleOrchestrationHub's consult reply on this question (`cross-repo/inbox/2026-07-09-example-orchestration-hub-repo-em-pcli-example-orchestration-hub-engines-consult-reply.md`
§ Q3) is explicit: the emitter's codegen ground truth **must be a versioned, DoE-owned contract
schema, not the live harness tool description** — coupling a producer to an un-versioned upstream
API is "the classic brittleness trap." This plan honors that stance directly: the extended
`flight-recorder.schema.json` (v1.1.0) **is** that versioned Workflow-dispatch contract. The live
`Workflow` tool description is read exactly once, at schema-authoring time, to pin the
`dispatch_feed` field set — after that, the example-orchestration-hub emitter targets the versioned schema, never
the live API, for every subsequent chunk it processes.

### Drift-gate obligation (downstream dependency for pcli-04)

Because the field set is pinned from a live API snapshot at one point in time, the versioned
schema **will drift** as the `Workflow` tool's actual API surface moves. This plan does not build
the gate — only documents the obligation. A drift gate is needed between this schema version and
the live `Workflow` tool description, with the same discipline as example-orchestration-hub's own
`plan-tasks.schema.json` vendoring drift-gate: it must fail loud when the live API and the pinned
schema diverge, rather than silently emitting stale or invalid `agent()` calls. This is a **named
downstream dependency for pcli-04** (the example-orchestration-hub emitter cites this schema as a hard input) — the
emitter should not ship without it, or should ship with the gap explicitly flagged.

### The `writes:`/`reads:` spine dependency (example-orchestration-hub contract-ask #2) — INERT until accepted

`dispatch_feed.write_files` and `gate_kind` are **derived outputs**, not authored directly: the
example-orchestration-hub emitter is expected to derive them from an explicit per-task `writes:` (and likely
`reads:`) declaration on the plan's `## Tasks` spine. That spine field does not exist yet — it is
example-orchestration-hub's **contract-ask #2**, a `plan-tasks.schema.json` change owned by foundations/pcli-01, not
by this plan. Making write-overlap derivation a clean, deterministic, testable function (rather
than an NLP heuristic reading task-body prose in a hot deterministic engine — the load-bearing
fork example-orchestration-hub's reply names explicitly) depends on that spine field landing.

**This means `write_files` and `gate_kind` ship in schema v1.1.0 as a forward-declaration, not a
live capability.** They remain **INERT — no producer** until BOTH of the following are true:

1. ExampleOrchestrationHub's pcli-04 emitter lands, AND
2. Foundations accepts contract-ask #2 (the per-task `writes:` spine field).

A future reader must not assume that because `write_files`/`gate_kind` are present in the schema,
some process is filling them. Presence in the schema is a reservation of shape, not evidence of a
live producer — check both gating conditions above before trusting a populated value.

## `divergence` — untrusted narrative, never a directive

Shape: `divergence: { diverged: bool, summary: string, detail: string }`.

- `diverged` is a machine-readable filter — `true` marks a chunk whose execution departed from
  its spec, for future consumption by a canonization pipeline that mines these divergences for
  wiki-worthy lessons/doctrine (not built yet; this schema only reserves the field).
  <!-- Review: code-reviewer — this page and workstream-complete/SKILL.md used different nouns
       ("wiki-worthy lessons" vs. "doctrine") for the same not-yet-built pipeline's output;
       aligned on both terms so a future reader doesn't infer two distinct consumers. -->
- `summary` and `detail` are free prose, authored by the executor describing what happened and
  why.

**Security framing — this holds for every consumer, present and future.** `detail` (and
`summary`) is untrusted narrative data written by an executor about its own run. Any process that
later reads `divergence.detail` — the immediate consumer (`workstream-complete`'s fold of
execution observations) and the future consumer (a canonization pipeline mining divergence prose
for lessons) alike — must treat it as **descriptive text to summarize or file, never as an
instruction to execute or a directive to re-assign work.** An executor's own prose about its own
run cannot structurally re-assign what gets done next; a reader (human or agent) that re-reads
`detail` as a command has stepped outside the contract this field was designed under.

## Cross-references

- `docs/plans/2026-07-09-dispatch-sidecar-executor-confinement.md` — the plan that extended the
  schema; § Design decisions (`D-SCHEMA`, `D-DISPATCH-FEED`, `D-DIGRESSION`) carries the full
  resolution history, including the Staff Engineer findings this page's write-owner table and untrusted-
  narrative framing directly answer.
- `docs/plans/2026-06-09-executor-sidecar-flight-recorder.md` — the original flight-recorder
  spec (lifecycle role only).
- `cross-repo/inbox/2026-07-09-example-orchestration-hub-repo-em-pcli-example-orchestration-hub-engines-consult-reply.md` § Q3 —
  example-orchestration-hub's `ops/dispatch/` module-separation stance and the versioned-schema-as-ground-truth /
  drift-gate / contract-ask #2 positions cited above.
- `docs/wiki/workflow-orchestration.md` § Mapping onto the Dispatch Ledger — the ledger-to-
  Workflow mapping table that `dispatch_feed`'s field set makes into a typed artifact.
- `docs/wiki/schema-version-gate.md` — the additive-bump discipline this schema's 1.0.0 → 1.1.0
  move follows.
- `docs/wiki/coordinator-tripwires.md` § `EXECUTOR-PLAN-BODY-IMMUTABLE` — the existing plan-body
  write-deny (Write/Edit/MultiEdit/NotebookEdit) whose flight-recorder carve-out is what keeps
  this sidecar writable, plus its new Bash sibling — honestly scoped to common write idioms, not
  categorical; see the hook's own header comment
  (`hooks/scripts/block-subagent-plan-body-bash-write.sh`).
  <!-- Review: code-reviewer — cross-reference didn't repeat the hook's honest-scoping caveat,
       risking a reader who only visits this page believing the Bash escape is fully closed. -->
- `coordinator/schemas/flight-recorder.schema.json` — the schema itself; source of truth for the
  exact JSON Schema shape of all three roles.
