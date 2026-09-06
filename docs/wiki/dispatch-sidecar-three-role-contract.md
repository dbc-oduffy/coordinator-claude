---
title: Dispatch sidecar — the flight recorder's three-role contract (R1)
created: 2026-07-09
type: doctrine
related:
  - docs/plans/2026-06-09-executor-sidecar-flight-recorder.md
  - docs/plans/2026-07-09-dispatch-sidecar-executor-confinement.md
  - plugins/coordinator/docs/wiki/workflow-orchestration.md
  - plugins/coordinator/docs/wiki/schema-version-gate.md
  - plugins/coordinator/docs/wiki/coordinator-tripwires.md
  - plugins/coordinator/schemas/run-report.schema.json
  - archive/specs/2026-07/2026-07-13-subagent-run-report-subsume.md
  - coordinator/docs/wiki/computed-engine-model.md
  - coordinator/docs/wiki/invisible-doctrine.md
  - docs/decisions/DR-091-agent-citizenship-identity-typed-sidecar-contract.md
  - docs/plans/2026-07-24-agent-citizenship-identity-adapted-provisioning.md
---

<!--
Purpose: document the flight recorder's extended THREE-role contract (R1 "dispatch sidecar")
introduced by the 2026-07-09 dispatch-sidecar-executor-confinement plan — lifecycle (existing),
dispatch_feed (new, claude-klabauter/pcli-04-filled), divergence (new, executor-authored). Names the
write-owner-per-field split, the versioned-schema-is-ground-truth stance, the drift-gate
obligation, and the writes:/reads: spine cross-plan dependency.
Negative-spec: this page does NOT define the claude-klabauter emitter (pcli-04/C3) or the plan-tasks
`writes:`/`reads:` spine field (authored by `docs/plans/2026-07-19-pcli-phase2-stubs-claude-klabauter-
contracts.md` C2) — both are cited as dependencies, not authored here.
-->

# Dispatch sidecar — the flight recorder's three-role contract (R1)

## What this is

`COORDINATOR-RESOLUTIONS.md § R1` called for killing the plan-body Dispatch Ledger in favor of
one executor-writable sidecar. That retirement is now realized: the
`2026-07-13-retire-plan-body-dispatch-ledger` plan removed the plan-body `## Dispatch Ledger`
table, replacing it with the wave-map (the execution vehicle's own on-disk decomposition input —
default the background Workflow's `phase()`/`agent()` calls, rare hand-orchestrated carve-out the
`fan-out-dispatch.py` TSV). A reader may still encounter this sidecar under its older name, the
per-chunk **flight recorder**, at `tasks/<plan-slug>/flight/<chunk-id>.md`, typed by
`coordinator/schemas/flight-recorder.schema.json`, produced by `fan-out-dispatch.py` via
`coordinator-doc-new --type flight-recorder`, and read back by `workstream-complete`'s `d-fold-execution-observations` directive.
The `dispatch-sidecar-executor-confinement` plan extended that flight recorder in
place (additive schema bump, `x-schema-version` 1.0.0 → 1.1.0) so the same file carried three
distinct roles instead of one.

**Subsumption.** The `2026-07-13-subagent-run-report-subsume` plan subsumed the
flight recorder into a universal **run-report sidecar**, eligible for every scoped subagent
(executors, integrators, enrichers, long scouts — per the `report_sidecar:` policy list), not
just `/execute-plan` chunk executors. The sidecar now lives at
`state/subagent-share/<session-id>/<provision_key>.md`, where `provision_key` is the flat,
pre-flattened `<plan-slug>.<chunk-id>` (joined on `.`), computed and provisioned at spawn time by
Claude-klabauter's engine (`python3 -m coordinator_core.subagent_sandbox.provision_report`). It is typed
by `coordinator/schemas/run-report.schema.json` (the superset schema that replaced
`flight-recorder.schema.json`, which has been deleted) and read back by `workstream-complete`'s
`d-fold-execution-observations` directive via `coordinator-fold-execution-record`. `coordinator-doc-new --type flight-recorder`
is kept only as a backward-compat alias mapping to `--type run-report`. The three-role contract
this page documents — lifecycle / `dispatch_feed` / `divergence` — carries over unchanged onto
the run-report sidecar; only the mechanism, path, and schema name changed. That new file is what
this page calls the **R1 dispatch sidecar** — wider eligibility, same three-role contract.

The three roles:

1. **Lifecycle** (existing, unchanged shape) — `dispatched_at`, `dispatched_by`, `status`,
   `commits`, plus the new `started_at`/`finished_at` timestamps. The executor's own
   dispatched → in_flight → complete/blocked/thrashing state machine.
2. **`dispatch_feed`** (new) — a per-chunk object shaped 1:1 against the live `Workflow`
   `agent()` call contract, filled by the claude-klabauter emitter (C3/pcli-04), not the executor.
3. **`divergence`** (new) — prose defending any divergence from the chunk's spec, written by the
   executor after the chunk finishes.

## Why one file, three roles — not three files

This is a **deliberate coordinator-side inlining choice**, not a claim that the three roles share
a lifecycle. Claude-Klabauter's own reply on this exact question (`ops/dispatch/` as a new module,
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
| Dispatch feed | `dispatch_feed` (`label`, `agent_type`, `model`, `effort`, `schema_ref`, `brief_ref`, `phase`, `gate_kind`, `write_files`, `est_min`) | claude-klabauter emitter (C3/pcli-04) | Pre-dispatch (filled before the chunk is ever handed to an executor) | **No — READ-ONLY to the executor.** The executor does not author or mutate `dispatch_feed`; it is upstream of the executor's own work. |
| Divergence | `divergence` (`diverged`, `summary`, `detail`) | Executor | Post-run (written after the chunk's work is done, before exit) | Yes — this is the executor's own account of what it did versus what the spec said |

If a future change makes the executor believe it should populate or correct `dispatch_feed`,
that is a signal the inlining assumption above has been violated somewhere — stop and check
against this table before writing.

## `dispatch_feed` — Workflow-transferability is the design goal

The field set exists so that going from a chunk's run-report sidecar (originally the flight
recorder) to a ready-to-fire
`workflow.js` `agent()` call requires near-zero transcription. This is the same mapping already
documented in `workflow-orchestration.md § The Workflow Script Is the Wave-Map` (wave-map wave →
`phase()` group; wave-map chunk row → one labelled `agent()` call; serial gate → `await` boundary +
`if (...) return { halted }`; parallel wave → `parallel([...])`; item pipeline → `pipeline(...)`)
— `dispatch_feed` is that mapping made a typed, per-chunk artifact instead of a table a human (or
an EM) has to re-derive by hand each time.

Per-chunk field set (shaped 1:1 against the live `Workflow` `agent()` contract):
`label`, `agent_type`, `model` (`'sonnet'` default), `effort`, `schema_ref`, `brief_ref`
(pointer to the per-chunk brief/prompt), `phase` (the `phase()` group name the chunk belongs to),
`gate_kind` (`none | file-write-overlap | output-consumption-runtime | contract-change` — maps
onto the await-boundary-vs-`parallel()`/`pipeline()` choice), `write_files`, `est_min`.
`additionalProperties: true` on this object lets the claude-klabauter emitter add emitter-specific fields
without a schema round-trip.

**Cardinality: per-chunk, not per-plan.** `dispatch_feed` is one object per run-report sidecar
file (one per chunk) — it matches C3's own independent design (spine task → N≥1 dispatch rows).
The per-plan Workflow *envelope* (`meta` + the `phase()`/`parallel()`/`pipeline()` topology) is
assembled separately, by the claude-klabauter emitter, from the N per-chunk feeds across a plan's
run-report sidecars. This wiki page (and the schema it documents) defines the per-chunk
`agent()`-shape only; per-plan derivation and assembly is C3/pcli-04's concern, not this
schema's.

## The versioned schema is the ground truth, not the live Workflow API

Claude-Klabauter's consult reply on this question (`cross-repo/inbox/2026-07-09-claude-klabauter-em-pcli-claude-klabauter-engines-consult-reply.md`
§ Q3) is explicit: the emitter's codegen ground truth **must be a versioned, DoE-owned contract
schema, not the live harness tool description** — coupling a producer to an un-versioned upstream
API is "the classic brittleness trap." This plan honors that stance directly: the extended
schema (`run-report.schema.json`, renamed from `flight-recorder.schema.json` v1.1.0)
**is** that versioned Workflow-dispatch contract. The live
`Workflow` tool description is read exactly once, at schema-authoring time, to pin the
`dispatch_feed` field set — after that, the claude-klabauter emitter targets the versioned schema, never
the live API, for every subsequent chunk it processes.

**A standalone `workflow-dispatch.schema.json` is a ruled-out proposal, not a live alternative.**
`docs/plans/2026-07-19-pcli-phase2-stubs-claude-klabauter-contracts.md` proposed a separate,
standalone schema for this role; no such file exists on disk
(`coordinator/schemas/workflow-dispatch.schema.json` — not present). That proposal is
superseded by `run-report.schema.json`'s `dispatch_feed` object, which is the sole emitter
output contract — a PM-ratified consolidation, not a call this page is making. A reader who
encounters the phantom filename in the older plan, or who recalls the retired
flight-recorder naming, must not treat either as a live or parallel contract: `dispatch_feed`
inside `run-report.schema.json` is the one and only target.

**Transcription-adequacy, confirmed against schema on disk.** The `dispatch_feed` object's
declared field set (`run-report.schema.json` properties, roughly lines 79-123) —
`label`, `agent_type`, `model`, `effort`, `schema_ref`, `brief_ref`, `phase`, `gate_kind`,
`write_files`, `est_min` — maps 1:1 onto the arguments of one `Workflow` `agent()` call with no
additional lookup required: `brief_ref` already points at the per-chunk brief the emitter
transcribes into the call body, so nothing outside the sidecar itself needs to be consulted to
fire the call. This confirmation repoints the plan's AC8/baton-AC8 transcription-adequacy
requirement from the retired flight-recorder target onto `run-report.schema.json`.

**Pre-condition checked, not assumed: the body-fenced-block `## Tasks` parser.** This schema
pin does not itself depend on pcli-01/C1's `## Tasks` spine parser, but a reader tracing the
emitter's full dependency chain needs its status stated rather than assumed. As checked against
the engine repo (`claude-klabauter/coordinator_core`): `coordinator_core/frontmatter/body_blocks.py`
has landed on disk; `task_spine.py` has not — no file by that name exists anywhere under
`coordinator_core`. Treat the spine parser as partially landed, not landed, until `task_spine.py`
(or its equivalent) appears.

### Drift-gate obligation (downstream dependency for the claude-klabauter emitter)

Because the field set is pinned from a live API snapshot at one point in time, the versioned
schema **will drift** as the `Workflow` tool's actual API surface moves. This plan does not build
the gate — only documents the obligation. A drift gate is needed between this schema version and
the live `Workflow` tool description, with the same discipline as claude-klabauter's own
`plan-tasks.schema.json` vendoring drift-gate: it must fail loud when the live API and the pinned
schema diverge, rather than silently emitting stale or invalid `agent()` calls. This is a **named
dependency of the shipped `dispatch.emit` op** (the claude-klabauter emitter cites this schema as a hard
input) — whether the gate itself shipped alongside the op is unverified here; check claude-klabauter's side
directly rather than assuming either way.

### The `writes:`/`reads:` spine dependency (claude-klabauter contract-ask #2) — live

`dispatch_feed.write_files` and `gate_kind` are **derived outputs**, not authored directly: the
Claude-klabauter emitter (`coordinator_core.ops.dispatch_emit`, op `dispatch.emit`) derives them from the
explicit per-task `writes:` (and `reads:`) declaration on the plan's `## Tasks` spine. That spine
field landed as claude-klabauter's **contract-ask #2**, a `plan-tasks.schema.json` change authored by
`docs/plans/2026-07-19-pcli-phase2-stubs-claude-klabauter-contracts.md` C2 (`x-schema-version: 1.7.0`), and
the emitter itself lives on claude-klabauter's side, deriving a Workflow wave-map from the spine.
`write_files`/`gate_kind` have a live producer wherever a plan's spine declares `writes:`.

The op is preferred, not mandatory — `coordinator/skills/execute-plan/SKILL.md` Phase 1.6 names it
as the preferred wave-map derivation with hand-authoring as the fallback, because the emitted
Workflow script spawns coordinator-typed `agent()` calls and a Workflow `agent()` spawn is not an
`Agent` tool call — injected `contract_blocks` never arrive on that path (claude-klabauter's
`coordinator_core/ops/dispatch_emit/emit.py`; see `SKILL.md` § Vehicle default QUALIFIES), so an
emit-first default would fire a plan wave of coordinator-typed agents without their contract
blocks. A spine row without
`writes:` still leaves `write_files`/`gate_kind` unpopulated for that row — the field set is
schema-optional, and an authoring surface must ask for it before it is filled.

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

## AC13 discharge — the plan-body-immutability guard was already there

`docs/plans/2026-07-24-agent-citizenship-identity-adapted-provisioning.md` C9 went in
expecting to build a guard denying `coordinator:executor` writes to `docs/plans/**/*.md`.
Re-verification against current disk found the guard already live: **AC13's red test is
ALREADY GREEN, not a build target.** This section records the discharge so a future reader
doesn't re-open work that's done.

**(a) The confirming artifact.** claude-klabauter's
`coordinator_core/write_guards/block_subagent_plan_body_write.py` is a CLASS hard-deny
(PRIORITY 40) matched against `_PLAN_BODY_RE = (^|/)docs/plans/.+\.md$`, wired live into the
`Write | Edit | MultiEdit | NotebookEdit` write_guards engine dispatch
(`preuse-write-dispatch.py` → `write_guards.engine`). It denies `coordinator:executor`; named
Opus personas are exempt (§ Two behavioral postures, not one above — control posture for
generic executors, convenience posture for personas). This IS AC13's satisfying artifact — no
DoE-side hook change accompanies this record. A related-but-distinct matcher,
`enforce-agent-dispatch-mode.py`, fires at `Agent`-tool spawn time in the *parent* session and
never observes a spawned child's later `Write` events — it was mistakenly credited earlier in
this workstream as the write-time enforcer, which is why the existing guard didn't surface
until this re-check. Don't conflate the two: one gates spawn-time dispatch mode, the other
gates write-time path immutability.

**(b) The sanctioned write-back channel — provisioned by C1, not built here.** The guard's
deny message points a blocked executor at its own typed sidecar as the legitimate channel for
anything it would otherwise have tried to write into the plan body. That sidecar — the `##
Divergence from plan` section plus the completion marker on the run-report sidecar C1
provisions — **is** the write-back this AC needed; this page does not re-describe the
mechanism (see § What this is and § `divergence` — untrusted narrative, never a directive
above, and C1's own provisioning record for the sidecar-creation detail). The point worth
naming here is only the *pairing*: deny-on-plan-body plus sanctioned-sidecar-write-back is one
control, not two independent facts — a guard that denies without naming where legitimate
output goes is a dead end, not a control.

**(d) G0 leg (a) is landed, not asserted — one known follow-up.**
<!-- Provenance: run 2026-08-06-14h38, derives from c7-007 -->
The `2026-07-24-agent-citizenship-identity-adapted-provisioning` plan's G0 leg (a) — identity-
typed, lead-stamped, tracked sidecar provisioning contract plus the reviewer→integrator seam
documented below (§ One-home reviewer→integrator seam) — is confirmed genuinely landed on disk,
not merely claimed in a plan. The G1–G5 fleet-rewrite waves build against this landed G0 as their
foundation. **Follow-up closed — see § Subagent-share reaper below.** The reaper's settings-home
forwarder gap named here is fixed; a future reader touching the reaper path should
still confirm against current disk, but this specific gap is closed.

**(c) Spec-surface widening — sent, accepted, landed.** The genuinely new ask in C9 was a
**first-wave cross-repo memo** (topic `executor-spec-surface-widening`) sent to
`claude-klabauter-em` proposing that `block_subagent_plan_body_write.py`'s immutable-path regex
widen beyond `docs/plans/**/*.md` to also cover `docs/problems/**` — the ratified `/shape`
problem-set surface, executor-writable today only because no guard currently names it. The
proposal deliberately excluded `docs/wiki/**` and `docs/decisions/**` from the widened
denylist: those two surfaces carry delegated authoring (executors legitimately write wikis and
DRs as part of normal dispatch), and folding them into an immutable-path guard would break that
delegation rather than close a gap. The widened scope stays strictly `coordinator:executor`
(never a generic executor-class re-fence — DR-058's revisit-trigger forbids that) with personas
exempt, unchanged from the existing guard's posture. **Status: accepted and landed.**
`claude-klabauter-em` actioned the memo the same day (`disposition: accept`, direct-dispatch,
archived at `claude-klabauter`'s `cross-repo/archive/2026-07-24-doe-claude-em-executor-spec-
surface-widening.md`): `_PLAN_BODY_RE` widened to `(^|/)docs/(plans|problems)/.+\.md$`,
`coordinator:executor`-only, wiki/decisions excluded exactly as proposed, landed at claude-klabauter
commit `165ce86b` (fresh test module, 68 passed). `docs/problems/**` is now guard-protected for
`coordinator:executor` on claude-klabauter's side — a future reader does not need to chase disposition
further; the accept is the terminal state for this ask.

## Audit note — read-only reviewer-sidecar spot-check corrected two false AC marks

<!-- PROVENANCE: run 2026-08-06-14h38, derived from nugget c7-006
     (source: 2026-07-24-agent-citizenship-identity-adapted-provisioning-b7d5e5.md) -->

A read-only audit of a reviewer-sidecar's acceptance-criteria rows against verified session
reality found two rows marked done that weren't, and corrected both in place rather than
carrying the false marks forward:

- The rag-em / cockpit-em memos the AC row claimed were sent had in fact only been drafted —
  they were drafted **and** sent within the same session, closing the gap, but the row as
  written could not be trusted at face value without the recheck.
- The reaper was marked wired only to `/distill`; verified session state showed it was also
  wired to `/update-docs` and `/workweek-complete`, a broader footprint than the row recorded.

Both AC rows were corrected to match verified reality rather than left as originally
self-reported. This is the same discipline the write-owner table above assumes for `divergence`
prose (§ `divergence` — untrusted narrative, never a directive): an executor's or reviewer's own
self-report is not ground truth until an independent read-only pass checks it against disk state.
A reviewer-sidecar's AC rows are exactly this kind of self-report — auditable, not authoritative
by default.

## Subagent-share reaper — delete-by-convention, liveness+age gated

<!-- PROVENANCE: run 2026-08-06-14h38, derives from nugget c7-019
     (source: 2026-07-24-reviewer-sidecar-provisioning-reconciliation-7d4e70.md) -->

`state/subagent-share/<session-id>/` is a growth surface — every dispatched subagent (executor,
reviewer, synthesizer, scout) provisions a run-report sidecar under it, and nothing deletes those
files on its own. The shipped reaper is **claude-klabauter-resident**, delete-by-convention (matches the
`<session-id>/<provision_key>.md` path shape rather than reading a registry), and gated on two
signals together, not either alone: **liveness** (is the owning session still active?) and **age**
(has enough wall-clock time passed that the sidecar's fold-back into
`workstream-complete`'s `d-fold-execution-observations` has plausibly already happened?). A
sidecar belonging to a live session, or one too young to have been folded yet, is left alone even
if it superficially matches the delete pattern — the gate exists specifically so the reaper cannot
race a still-running dispatch or an as-yet-unread divergence record.

**Live seam trace found two gaps, both fixed in the same pass:**

1. **Three personas naming two homes.** Some persona dispatch contracts named a sidecar home that
   didn't match where `provision_report` actually provisioned the file — a naming mismatch between
   what the persona's contract said and what showed up on disk. Reconciled so persona naming and
   actual provisioning agree.
2. **`coordinator-doc-new` fallback still writing legacy.** The `coordinator-doc-new` CLI's
   fallback path (used by the self-create branch — see § Conditional sidecar handling, case 2, in
   the executor operating doctrine) was still writing the old flight-recorder-shaped scaffold
   instead of the unified run-report shape, meaning a self-created sidecar could diverge from a
   claude-klabauter-provisioned one. Fixed by unifying the `coordinator-doc-new` scaffold with
   `provision_report`'s frontmatter-bearing output — one scaffold shape, two entry points,
   closing the producer divergence rather than leaving two shapes that happened to usually agree.

Both fixes matter to this page specifically because the reaper's delete-by-convention matching
depends on every producer emitting the *same* path/shape convention — a producer divergence here
is a reaping-correctness risk, not merely a cosmetic inconsistency: a reaper matching on one
convention will silently skip (or worse, wrongly sweep) sidecars produced under the other.

## Dispatch-encouragement doctrine binds by placement, not wording
<!-- PROVENANCE: run 2026-08-06-14h38, derives from nugget c9-004
     (source: 2026-07-28-adhoc-215a34.md) -->

A related but distinct binding failure, worth recording here because it shapes how any
sidecar-adjacent contract (this page's three-role table included) should be delivered to an
agent that must act on it under context-switch pressure. An EM asked the PM three times in six
days for dispatch permission, each time with a forbidding rule already loaded in context. The
repeat was diagnosed as an **intervention-shape problem, not a wording problem** — no amount of
rephrasing the permission-seeking language fixed it, because the doctrine was arguing its own
case from deep inside a 39KB boot payload where it had to compete for attention at the exact
moment it needed to win.

The fix moved the binding mechanism, not the words: from the large boot payload into a **small
identity block plus per-turn restatement**, and `/coordinator:review` gained inline
authorization directly at its failure gate instead of relying on the boot-time doctrine to have
survived that far into the session. Two collateral corrections landed in the same pass: a
decision-record numbering collision was resolved by renumbering to DR-110, and an
unmechanizable detection claim in the original doctrine text was corrected rather than left
standing.

**Takeaway for this page's own contract.** The three-role write-owner table above is exactly the
kind of binding rule that degrades if it only lives in a large upstream document an executor read
once at dispatch time — the same failure shape this section documents. Where a rule must survive
context-switch pressure (an executor mid-chunk, an EM mid-session), placement close to the point
of use and per-turn restatement is the working pattern; relitigating the rule's wording is not.

## Dispatch-tier measurement — boot envelope and configuration costs

<!-- PROVENANCE: run 2026-08-06-14h38, derives from nuggets c10-009, c10-010, c10-015
     (source: 2026-07-30-adhoc-7490da.md, 2026-07-30-adhoc-942487.md) -->

These findings are about the **dispatch decision itself** — agent-type, model, effort — not the
sidecar contract above; they're recorded here under `system_tag: dispatch-tier-measurement`
because no dedicated page exists yet for dispatch-cost measurement. A future reader looking for a
richer treatment of boot-envelope economics should check for a more specific page first; if none
exists, this section is the canonical home.

### Agent-type choice is worth ~28k tokens per dispatch

**Explore and Plan are the only subagent types that skip the always-on doctrine corpus**
(~56 KB) injected into every other dispatched agent's boot. Because that corpus is loaded, not
optional, per-dispatch, choosing Explore or Plan over a doctrine-bearing agent type when the task
doesn't need doctrine saves roughly 28k tokens of boot overhead — a cost worth weighing explicitly
when picking `agent_type:` for a dispatch, not just picking the type that "sounds closest" to the
task.

### The agent roster is delivered on first tool result, not never

A prior conclusion — recorded and then corrected within the same investigation session — held
that the agent roster is never delivered to a dispatched subagent. That conclusion was wrong: the
roster **is** delivered, attached to the subagent's first tool result, at a cost of +15,547
tokens. A reader relying on an earlier note claiming roster non-delivery should treat this page as
the corrected account — the roster shows up, just not in the initial system prompt, which is why
it was initially missed.

### `model:` and `effort:` are decided independently, never jointly reconsidered

Dispatch configuration for `model:` and `effort:` is decided in two separate passes that are never
revisited together — this is why, across the fleet, 19 of 34 agents land in a single default
`model`/`effort` bucket (`sonnet`/`low`) rather than a deliberately-chosen combination. Count via
`grep -m1 '^model:'`/`^effort:'` on each `coordinator/agents/*.md` file and tally the pairs. A
future reviewer auditing dispatch configuration should treat a large single-bucket clustering as
evidence of this independent-pass artifact, not necessarily evidence that those 19 agents were
individually reasoned about and happened to converge — the more likely explanation is that
neither pass revisited the other's default.

## Dispatch consent grounding — breaking the harness-directive circularity
<!-- PROVENANCE: run 2026-08-06-14h38, derives from nugget c11-049
     (source: 2026-08-02-adhoc-9f65b5.md) -->

A related but distinct governance question, worth recording here because it underlies the
"who may act without asking again" posture this page's write-owner and confinement framing both
assume. The generic Anthropic harness treats permission for actions like dispatch or commit as
something the human must grant per-request, in the moment — a request-conditioned directive that
asks the question fresh each time. Left unresolved, this produces a circularity: the harness
directive itself names the permission question, but nothing in-session can answer it without
appealing back to the same directive that raised it.

**DR-123 and DR-124 ground dispatch consent in co-authored global doctrine, not a live request.**
An explicit standing grant — written into `CLAUDE.md`-class doctrine, co-authored by the human and
the Claudes operating under it — is a **written-in-advance instruction**, categorically different
from the request-conditioned directive the harness otherwise expects to answer the question. The
standing grant is not the harness asking "may I?" in the moment; it is the human having already
answered that question once, durably, in a doctrine artifact both parties can point to. This is
the same "Human-Authored Doctrine Grants Consent" framing carried at the top of this repo's global
doctrine (`~/.claude/CLAUDE.md` § Human-Authored Doctrine Grants Consent) — DR-123/DR-124 are the
decision-record grounding for that same move as applied specifically to dispatch consent.

**Why this belongs on this page.** The three-role sidecar contract, the confinement posture (§
Two behavioral postures, not one above), and the dispatch-tiering rule (§ Dispatch tiering above)
all presuppose that dispatch itself is already authorized — none of them re-litigate "may an EM
dispatch a subagent at all." DR-123/DR-124 are the answer to that prior question; this page's
mechanics start downstream of it. A future reader auditing whether a dispatch was properly
authorized should check the standing-grant doctrine (DR-123, DR-124), not look for a per-dispatch
consent artifact on the sidecar itself — the sidecar records what the dispatch *did*, not whether
it was permitted.

## Cross-references

- `docs/plans/2026-07-09-dispatch-sidecar-executor-confinement.md` — the plan that extended the
  schema; § Design decisions (`D-SCHEMA`, `D-DISPATCH-FEED`, `D-DIGRESSION`) carries the full
  resolution history, including the Staff Engineer findings this page's write-owner table and untrusted-
  narrative framing directly answer.
- `docs/plans/2026-06-09-executor-sidecar-flight-recorder.md` — the original (now subsumed)
  flight-recorder design (lifecycle role only); historical lineage, not the current mechanism.
- `docs/plans/2026-07-13-subagent-run-report-subsume.md` — the subsuming plan: folds the flight
  recorder into the universal run-report sidecar (`state/subagent-share/<session-id>/
  <provision_key>.md`, typed by `run-report.schema.json`, provisioned by claude-klabauter's
  `provision_report` engine), eligible for every scoped subagent, not just `/execute-plan` chunk
  executors.
- `cross-repo/inbox/2026-07-09-claude-klabauter-em-pcli-claude-klabauter-engines-consult-reply.md` § Q3 —
  claude-klabauter's `ops/dispatch/` module-separation stance and the versioned-schema-as-ground-truth /
  drift-gate / contract-ask #2 positions cited above.
- `docs/wiki/workflow-orchestration.md` § The Workflow Script Is the Wave-Map — the wave-map-to-
  Workflow mapping table that `dispatch_feed`'s field set makes into a typed artifact.
- `docs/wiki/schema-version-gate.md` — the additive-bump discipline this schema's 1.0.0 → 1.1.0
  move follows.
- `coordinator/docs/wiki/coordinator-tripwires/` § `EXECUTOR-PLAN-BODY-IMMUTABLE` — the existing plan-body
  write-deny (Write/Edit/MultiEdit/NotebookEdit) whose carve-out is what keeps this sidecar
  writable, plus its new Bash sibling — honestly scoped to common write idioms, not
  categorical; see the hook's own header comment
  (`hooks/scripts/block-subagent-plan-body-bash-write.sh`, folded into claude-klabauter
  `coordinator_core.bash_guards` via `preuse-bash-dispatch.py`; DoE `.sh` removed). **The original `tasks/<plan-slug>/
  flight/*.md` carve-out path is RETIRED** — the current sidecar location is
  `state/subagent-share/<session-id>/<provision_key>.md`; a reader auditing the hook's allow-list
  should confirm against the live hook source, not this note.
  <!-- Review: code-reviewer — cross-reference didn't repeat the hook's honest-scoping caveat,
       risking a reader who only visits this page believing the Bash escape is fully closed. -->
- `coordinator/schemas/run-report.schema.json` — the schema itself; source of truth for the
  exact JSON Schema shape of all three roles. Supersedes the deleted
  `flight-recorder.schema.json`.
- `coordinator/docs/wiki/computed-engine-model.md` § The subagent-sidecar convention — the
  generalization this page's three-role table is now a specialization of.
- `coordinator/docs/wiki/invisible-doctrine.md` — the discharge-test framing this page's N-role
  extension is scoped against (§ Generalizing the write-owner table below).
- `docs/plans/2026-07-24-agent-citizenship-identity-adapted-provisioning.md` C9 — the chunk
  that produced § AC13 discharge above: confirmed the existing guard, cross-referenced C1's
  sidecar write-back, and sent the spec-surface-widening memo recorded there as sent-pending.

## Generalizing the write-owner table — from three roles to N identity-typed roles

The three-role table above (§ Write-owner-per-field) was written for one dispatch shape:
`/execute-plan` chunk executors, each writing lifecycle + divergence into a run-report sidecar
while claude-klabauter's emitter writes `dispatch_feed`. That shape still holds exactly as documented —
nothing above is retracted. But it is now understood as the **executor specialization** of a
wider pattern that spans every scoped subagent class, not just chunk executors:
`coordinator/docs/wiki/computed-engine-model.md` § The subagent-sidecar convention names the
general form directly — "a dispatched agent is spawned with a prescaffolded, frontmatter-stamped
sidecar it writes its deliverable into" — and generalizes the review-sidecar →
cheap-EM-disposition → review-integrator loop that predates this page.

**The generalization is identity-typing, not role-counting.** Three roles was never the ceiling;
it was the field count for one agent identity (the chunk executor) inside one dispatch shape. Each
agent *class* gets its own typed deliverable document, shaped to what that class actually
produces:

| Agent class | Deliverable doc shape | Write owner |
| --- | --- | --- |
| Chunk executor (`/execute-plan`) | run-report sidecar — lifecycle + `dispatch_feed` + `divergence`, exactly as tabled above | Executor (lifecycle, divergence) / claude-klabauter emitter (`dispatch_feed`) |
| Review persona (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering) | review-findings sidecar — per-finding severity, file:line citation, `Worker Dispatch Recommendations` | Reviewer |
| Staff-engineer / architecture reviewer | staff-eng-review sidecar — architectural tradeoff framing, alternatives-considered | Reviewer |
| Scout / prior-art / docs-checker pre-flight | assessment sidecar — Conflicts / Compatible-but-relevant / Silent verdict, AUTO-FIX log | Pre-flight worker |
| Synthesizer | synthesis sidecar — assess/fill/frame record, never condensed specialist prose | Synthesizer |

Every row is the same shape at the schema level — a prescaffolded, frontmatter-stamped sidecar
under `state/subagent-share/<session-id>/<provision_key>.md` that the agent writes its
deliverable into instead of returning an ephemeral chat dump — and every row differs only in
*what the deliverable document's body schema is typed to*. The three-role split this page
documents is what that generic contract looks like when the identity is "chunk executor" and the
dispatch shape is `/execute-plan`. A future reader adding a new agent class should reach for this
generalized table, name the class's deliverable-doc type, and only then check whether the
class's write-owner-per-field split needs its own version of § Write-owner-per-field above — most
classes need a simpler split (one writer, no upstream-filled field like `dispatch_feed`) because
`dispatch_feed`'s pre-dispatch/claude-klabauter-owned shape is specific to the Workflow-transferability
goal (§ `dispatch_feed` — Workflow-transferability is the design goal above), not a general
feature every identity type needs.

**When the pre-scaffolded file and the injected frontmatter contract disagree, the file on disk
wins.** A `coordinator:staff-eng` dogfood dispatch reported exactly this seam gap:
its injected `sidecar-frontmatter-contract` block described a `kind: staff-eng-review` +
`reviewer:`/`verdict:`/`findings_count:`/`plan:` frontmatter, but the file it was handed at its
provisioned path was already scaffolded as a run-report (`status: open`, `agent_type:`,
`divergence:`, exit-interview headings) — the `report_type_map:` resolution for that dispatch had
picked the wrong template upstream. The agent resolved this correctly on its own judgment (filled
the scaffolded shape rather than overwriting its frontmatter), but the contract gave it no
explicit rule to lean on. The rule, made explicit here so the next agent doesn't have to re-derive
it: **the provisioned scaffold that actually arrives on disk is the deliverable-doc shape you
fill; an injected frontmatter contract names the fields to add within that shape, never a
competing frontmatter to replace it with.** A mismatch between the two is a signal to flag (the
upstream template resolution picked the wrong type for this identity), not license to pick
whichever shape you prefer.

**Two behavioral postures, not one.** `computed-engine-model.md` § The subagent-sidecar
convention draws a second distinction orthogonal to identity-typing: generic (unnamed Sonnet)
executors are confined — read-only on the plan/spec, with the sidecar as their only sanctioned
write-back, "so they don't 'helpfully' self-assign extra tasks or rewrite the plan." Named Opus
personas (the review roster above) are unconfined on the source they're reviewing but still get
sidecars, offered as convenience rather than imposed as a fence. Confinement is "a behavioral
speedbump, not security" — it does not change which agents get typed deliverable docs (all of
them do), only whether the sidecar is the agent's *sole* write surface or one write surface among
several. See `docs/decisions/DR-091-agent-citizenship-identity-typed-sidecar-contract.md` for the
ratified decision record covering identity-typing, lead-stamping, tracked-inversion, and the
two-posture model in full.

### One-home reviewer→integrator seam — DR-091 implemented
<!-- Provenance: run 2026-08-06-14h38, derives from c7-018 -->

DR-091 (§ Cross-references above) is not just a ratified decision record — it is implemented.
`review-integrator`'s intake, plus all 7 reviewer personas and all 5 review skills, now
read/write exclusively `state/subagent-share/<session>/` for review findings. This retires the
prior `review-trail/findings/` home and its sentinel-append convention entirely — a reviewer no
longer appends to a shared sentinel file; it writes its own sidecar under the per-session
subagent-share directory, same as every other identity-typed deliverable doc in the table above.
A single mechanical non-trivial-fill guard sits at the **integrator chokepoint** (not scattered
across the 7 reviewer dispatch sites) to catch a reviewer sidecar that was provisioned but never
actually filled in before `review-integrator` tries to fold it. This is the concrete landed
mechanism behind § Why the reviewer's write carve-out exists below — the sidecar-shaped outlet
described there is, as of this seam, the *only* outlet; `review-trail/findings/` is retired, not
merely deprecated.

### Dispatch tiering — a stated rule, not case-by-case

<!-- PROVENANCE: run 2026-08-06-14h38, derives from nugget c10-001
     (source: 2026-07-30-adhoc-1cd6ec.md) -->

Every row in § Generalizing the write-owner table above implies a prior question: does this agent
class earn a sidecar at all? That question should be answered by a stated rule, not decided
case-by-case per new agent type as it's proposed. A surface earns a sidecar only if BOTH of the
following hold:

1. **It can actually fill one.** A sidecar offered to an agent with nothing durable to put in it
   is dead scaffolding, not a control.
2. **At least one of:**
   - it transports its output **downstream** to another consumer (e.g. `dispatch_feed` to the
     claude-klabauter emitter, review findings to `review-integrator`),
   - it **accumulates across units of work** (e.g. divergence prose feeding a future
     canonization pass), or
   - it returns a **payload too large to hand back inline** (the context-management framing in §
     Why the reviewer's write carve-out exists above — a verbose reviewer's findings flooding the
     dispatching EM's context).

A dispatch surface failing all three of the "or" conditions — nothing to transport, nothing to
accumulate, and a payload small enough to return inline — does not earn a sidecar merely because
every other agent class in the table has one. Applying this rule before adding a new row to §
Generalizing the write-owner table above keeps the sidecar convention from becoming boilerplate
that gets attached to every new agent class by default rather than by actual need.

### Why the reviewer's write carve-out exists — context management, not a safety boundary

The review-persona write carve-out — able to write into its own sidecar and the subagent-share
sandbox, blocked everywhere else — is a **context-management design, not a safety control**, and
this distinction changes the conclusion an auditor should reach, not just the label attached to
it.

The mechanism it exists for: review personas get overeager and produce a lot of material. If a
reviewer cannot write that material anywhere, all of it returns inline and floods the dispatching
EM's context — and the EM then has to re-emit the whole thing back out just so `review-integrator`
has something to act on. The sidecar carve-out exists so a reviewer's output lands on disk where
the EM can *judge* it at a pointer's cost, not a context-dump's cost. Nothing about a security
boundary requires that design; a context-budget problem does.

**The question this reframes.** When auditing a dispatched agent's write restrictions, the
question to ask is **"does this agent have a sidecar-shaped outlet for its findings?"** — never
**"is it prevented from writing?"**. Reading the carve-out as a safety boundary produces the wrong
conclusion in both directions: it makes removing a write-sandbox confinement elsewhere look like a
security regression when it isn't one, and it makes "this agent claims read-only but has no
structural confinement enforcing it" look like a break-class finding when the real question is
whether that agent has an ergonomic way to write its findings to a sidecar at all. An agent that
is sidecar-eligible in its dispatch contract but lacks the write tool needed to use it is the
actual defect shape under this framing — the scaffolding half of the contract shipped and the
grant half didn't, and the agent falls back to an improvised write path (a bash heredoc) instead
of its sanctioned one. This is the same "eager, not adversarial" caller model the confinement
posture above is built on — the reviewer isn't a threat to be fenced off, it's a verbose
collaborator that needs a place to put its output.
