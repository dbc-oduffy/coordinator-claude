---
name: roadmap-planning
description: "PM-GATED. Shape research into ratified, graphed roadmap batons."
version: 2.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "<input-corpus-path|problem-set-path|roadmap-seed-stub-path> [--run-id <slug>]"
---

# Roadmap Planning — From Inputs to Sequenced Spinoff Stubs

**What this skill does:** Take a corpus of inputs (research artifacts, peer-repo deep-dives, brainstorming outputs, or a ratified problem-set) and produce a sequenced backlog of `kind: roadmap-baton` stubs that are queryable, dispatchable, and pickup-able through the standard handoff lifecycle. The roadmap is not a plan doc; it's a graph of stubs.

**When to use:** the PM has 5+ candidate work items emerging from research/deep-dive/peer-repo input, and wants them sequenced into sprint-shaped waves with explicit gate dependencies. Single-feature plans use `coordinator:plan`. Architectural decisions use `coordinator:staff-session`. Tactical bug-batch processing uses `coordinator:bug-blitz`. Roadmap-planning sits above plan-shaping — it produces the graph that individual plans live on.

**When NOT to use:** if you just want a single plan doc → `coordinator:plan`. If you want to brainstorm options before committing to a roadmap → `coordinator:brainstorming` first. If you don't have 5+ candidate items in writing → not yet roadmap-shaped; gather more before invoking. **Exception — goal-seeded (roadmap-seed pickup) path:** when this skill is triggered by actioning a `kind: roadmap-seed` stub (see Entry Point B below), a single stub represents one discrete roadmap-worth-of-work as already scoped by the upstream goal-setting session; the 5+ items precondition does NOT apply to this entry point. The roadmap-seed stub's `authoring_session` contains the upstream context that was used to scope the roadmap's boundaries.

---

## Entry points

### Entry Point A — Direct invocation (research / deep-dive corpus)

The classic path. PM arrives with a corpus of research artifacts, peer-repo deep-dives, or brainstorming outputs and wants them sequenced into a backlog. Begin at Phase 1 (Synthesize).

**Input:** `<input-corpus-path>` — a directory of research files, deep-dive outputs, or brainstorming artifacts.

### Entry Point B — Pickup from `kind: roadmap-seed` stub (goal-seeded)

When a `kind: roadmap-seed` stub is actioned via `/pickup`, the stub's `authoring_session` path contains the goal-setting context that spawned it (the goal artifact, upstream problem-set, and any KRs the goal-setting session produced). The stub represents a pre-scoped slice of work whose roadmap boundaries were already ratified during goal-setting.

**On pickup:**
1. Read the stub's `authoring_session` path to load upstream context (goal artifact, problem-set, initiative).
2. Use the stub body's scope description as the Phase 1 cluster seed — the stub is the single cluster that was already scoped; Phase 1 Synthesize refines it into sub-clusters.
3. Set `run-id` from the stub's `stub_id` (e.g. a stub `roadmap-seed` with `stub_id: rc-04` → `run-id: rc-04`).
4. The 5+ items precondition does NOT apply — a single roadmap-seed stub is a valid entry even if it describes a narrowly scoped roadmap.
5. Proceed to Phase 1 (Synthesize) with the stub's scope as the input corpus anchor, then continue the normal pipeline.

**Stub lifecycle:** set `deployment_state: in_flight` on the roadmap-seed stub when Phase 1 begins; set `deployment_state: shipped` (via the normal `/workstream-complete` path) when Phase 2 completes and the resulting roadmap-baton stubs are committed.

### Entry Point C — Chain from `/shape` (ratified problem-set, `estimated_horizon: week`)

When `/shape` ratifies a problem-set whose `estimated_horizon` field is `week`, it routes here instead of `coordinator:plan`. The ratified problem-set (`docs/problems/<slug>.md`) is the oracle that replaces the research corpus as the cluster seed.

**On chain-from-shape:**
1. The ratified problem-set (`docs/problems/<slug>.md`) arrives as the `<input-corpus-path>` argument (or is cited explicitly in the invocation).
2. Treat each problem listed under `## Problems` in the problem-set as a provisional cluster for Phase 1 Step 1.2. The problem-set's `## Out of scope` block pre-populates DROP verdicts.
3. Phase 1.5 research corpus still applies — each KEEP cluster still needs a research-corpus scout to ground the OVERVIEW in primary sources, not just the problem-set prose.
4. The plan's frontmatter inherits the problem-set reference: `problem_set: docs/problems/<slug>.md`.
5. The 5+ items precondition applies to this path — if the problem-set has fewer than 5 items, the work is likely plan-shaped, not roadmap-shaped; confirm with the PM before proceeding (the `/shape` router routes here because `estimated_horizon: week` was set at ratification — the 5+ items check is this skill's own precondition, not a `/shape` filter; if the problem-set is genuinely week-sized but shallow, it may warrant a single `coordinator:plan` call instead).

**Routing note (from `/shape`):** `/shape` sets `estimated_horizon: week` on the problem-set frontmatter at ratification. The EM confirms the routing at the fork (detect-then-confirm, never silent guess) before invoking this skill. See `coordinator/skills/shape/SKILL.md § Transition` for the router's outbound logic.

### Entry Point D — Conform intake from a sizing-object (roadmap-routed)

The sizing lobby (`coordinator:sizing`) resolves initiative-scale asks to the PM-decision route with an `xl_exit: roadmap` pick, or — on an older sizing-object — directly to `route: roadmap`, and hands roadmap-planning a `state/sizings/<id>.yaml` sizing-object as an optional entry contract either way. This is a conform intake, not a replacement for Entry Points A/B/C above — no sizing-object present means this skill's YAML-DAG/topo-numbering mechanics and Phase 1–3 pipeline run exactly as today; the sizing lobby never gates or refuses a `roadmap-planning` invocation absent one, by explicit anti-scope ruling ("do not build a wall").

Recognize the roadmap signal in either shape: `route: pm-decision` with `xl_exit: roadmap` (the PM chose the roadmap exit at the XL decision point — the current shape), or the legacy `route: roadmap` (sizing-objects already on disk in this shape remain valid — accept both, do not require migrating one to the other).

**On sizing-routed entry:**
1. Read the sizing-object's `intent` (the PM's ask, verbatim), `appetite`, `estimate`, and `scout_evidence`.
2. The sizing-object seeds Phase 1 the same way Entry Point A's `<input-corpus-path>` does — it supplies the routing rationale and any `scout_evidence` pointers as additional Phase 1.1 inventory input, not a pre-built cluster set. Phase 1 Synthesize (Steps 1.1–1.4) still runs unchanged.
3. Cite the sizing-object's path in `OVERVIEW.md`'s framing prose (Step 1.5.2) alongside the other Phase 1 outputs, for audit-trail continuity — no new frontmatter field is added; the schema is unchanged.
4. If Entry Point B or C also applies (a goal-seeded stub or a `/shape` chain), the sizing-object is additional provenance context layered on top, not a competing entry — resolve to whichever of A/B/C matches the actual input shape, then note the sizing-object alongside it.

---

## Ceremony ladder — each rung spawns the next

`/roadmap-planning` is the second rung of the ceremony ladder:

```
/goal-setting  →  spawns  kind: roadmap-seed  stubs (one per roadmap-worth-of-work)
/roadmap-planning  →  spawns  kind: roadmap-baton  plan-seed stubs (one per KEEP cluster)
coordinator:plan  →  authors  plan-doc  (dispatcher for a single roadmap-baton stub)
execute-plan  →  dispatches  executor chunks  (the typed work inside a plan)
```

**The spawn edge at this rung (Phase 2, Step 2.1):** every KEEP cluster in Phase 2 becomes a `kind: roadmap-baton` stub authored by `coordinator-doc-new --type roadmap-baton`. These stubs are the feed for the next rung — a future EM picks one up via `/pickup`, runs `coordinator:plan` against its scope, and the resulting plan-doc becomes the work authorization for executor chunks. The anti-scope section below formalizes the seam: `/roadmap-planning` does NOT invoke `coordinator:plan`; it only authors the stubs that a downstream `coordinator:plan` invocation will consume. The ladder is legible — each rung authors the artifacts that feed the rung below.

---

## Phase 1 — Synthesize: from input corpus to verdict-grid

**Goal:** every cluster gets a verdict; `we'll see` is rejected by construction. **Closure split:** Phase 1 enforces *cluster → verdict* coverage; Phase 2 Step 2.6 enforces the inverse (*verdict → stub* coverage). Both directions are required to close the brief's ESC-4 escape — a stub without a source cluster passes Phase 1 but fails Step 2.6, and a verdict without a stub passes Step 2.6 but fails Phase 1. Treat the two as halves of one bidirectional gate.

### Step 1.1 — Inventory inputs

Read every file in `<input-corpus-path>`. List title + one-line summary. Group by source repo / topic / authoring date. Output: `state/roadmap/<run-id>/inventory.md`.

### Step 1.2 — Topic clustering

Cluster the inputs into 20–60 topics. Cluster boundary rule: a cluster is what one stub could plausibly cover (~one wave of work). Output: `state/roadmap/<run-id>/clusters.md` with shape:

```
## Cluster N: <one-line topic>
- Source 1: <file>
- Source 2: <file>
- Notes: <why these belong together>
```

### Step 1.3 — Reconciliation verdicts (MERGE / DEFER / KEEP / DROP / MOVE)

Every cluster gets exactly one verdict — no exceptions.

- **MERGE** — fold into another cluster (name the target cluster). A MERGE verdict is stub-producing for Step 2.6's Audit 1 count (it counts alongside KEEP); a fold decided at THIS step, before the verdict is recorded, is not — it collapses into one cluster and produces one verdict. Prefer folding at clustering time when two topics would have to agree on one field or one stub's scope anyway; use MERGE only when the source cluster remains independently identifiable in the reconciliation table.
- **DEFER** — out of scope for this roadmap; record reason and target re-evaluation date.
- **KEEP** — becomes a stub in Phase 2.
- **DROP** — discard outright (record one-line reason for the audit trail).
- **MOVE** — belongs to a different system (different repo / different roadmap); name the destination.

Verdict assignment is a forcing function — it kills "we'll see" entries. Output: `state/roadmap/<run-id>/reconciliation.md`.

**Coverage AC:** verdict counts (MERGE+DEFER+KEEP+DROP+MOVE) must equal cluster count.

### Step 1.4 — Coordinator-resolutions document

When clusters conflict (two clusters propose contradictory architecture, or a MERGE creates a stub whose scope is ambiguous), create `state/roadmap/<run-id>/COORDINATOR-RESOLUTIONS.md`. One section per conflict; each has the form:

```
## Resolution N: <one-line>

**Conflict:** <cluster-A> says X, <cluster-B> says Y.
**Resolution:** <decision>. Overrides any conflicting stub language.
**Rationale:** <one paragraph>.
```

This file is authoritative — when a stub conflicts with COORDINATOR-RESOLUTIONS, the resolution wins.

### Phase 1 exit gate

Before Phase 1.5, verify:
- [ ] Inventory written and complete.
- [ ] Every cluster has a verdict.
- [ ] Verdict counts sum to cluster count.
- [ ] COORDINATOR-RESOLUTIONS exists for any cross-cluster conflicts (or is omitted if none).

---

## Phase 1.5 — Substantiate: research corpus + OVERVIEW + peer-team asks (PM-gated, double-approved)

### Precondition — UE-internal-API engine RAG availability (gate-first; check before any other Phase 1.5 work on UE clusters)

For any cluster planning UE-internal-API work (`FNiagaraStackGraphUtilities`, `UWorldPartitionBuilder`, `UGameplayEffect::GEComponents`, `UAnimBlueprintGeneratedClass`, `FAnimNode_StateMachine`, or any 5.x-specific engine class/struct/function), `mcp__project-rag__project_semantic_search` with `source="unreal"` MUST be available as a *precondition*, not a tier-2 nice-to-have. The skill's "solo scout default" assumes web-discoverability; UE is empirically not web-discoverable for internal-API specifics — web search returns UE 4.x forum posts + stale 5.0-era blogs, and LLM training data is similarly stale for 5.7+ specifics. Solo Sonnet scouts dispatched on this surface produce confident-looking research-corpus files grounded in noise — worse than no artifact because the noise encodes into Phase 2 stubs as if substrated.

**If `source="unreal"` is unavailable** (addon down, corpus not registered, daemon not reachable for that source): STOP planning UE-internal-API clusters, do NOT substitute solo web scouts, surface the block to the PM with the specific clusters affected and the cheapest path to restore the RAG (typically: run `/project-rag-ue-addon:doctor`, then `/project-rag-ue-addon:setup` if needed). Other clusters (non-UE-internal, e.g. tooling, build, infrastructure) may proceed.

Verification call shape:
```
mcp__project-rag__project_semantic_search(query="UClass", source="unreal", limit=1)
```
A non-empty response with engine-corpus hits proves liveness. Anything else (404, "no addon registered for source=unreal", empty result) is the block signal.

**Goal:** stubs in Phase 2 cite primary research and a PM-approved architectural overview, not EM hand-waving. The empirical motivator is the project-rag retrospective (ESC-4, ESC-5) — thin Phase 1 → Phase 2 transition let stubs encode contested architecture as fait accompli. Phase 1.5 forces contested decisions into the open *before* they get cast as 20+ stubs. A stub is a load-bearing artifact picked up by a context-less EM; wrong architecture means shipping the wrong thing or burning a session re-deriving the right shape. Phase 1.5 is **mandatory** by construction — never skipped; the judgment call ("do we really need primary research this time?") is the failure mode the retrospective surfaced.

### Step 1.5.0 — Research-depth assessment (EM judgment, PM-authorized)

Before dispatching the default parallel Sonnet scouts in Step 1.5.1, the EM assesses whether the roadmap's ambition exceeds solo-scout depth. **Solo scouts are 5–10 minute web searches per topic — not state-of-the-art surveys.** When the roadmap aims at "best in class", "cutting edge", "novel architecture", or "matches/exceeds <named-frontier-system>", model memory alone is insufficient (knowledge cutoff + non-existence-of-public-state-of-the-art — the techniques may not be in training data at all).

**EM-side escalation criteria — if ANY hit, surface a deep-research recommendation to the PM:**

- Roadmap framing uses "best in class", "state of the art", "cutting edge", "novel", or names a frontier-tier reference system to match.
- ≥3 KEEP clusters touch the same novel domain (a single scout per cluster fragments the survey; one deep-research run cross-pollinates).
- A cluster's topic surface is research-active (LLM agent architectures, novel RAG patterns, frontier ML training infra, etc.) where the half-life of best-practice is <12 months.
- PM-stated ambition exceeds what current `docs/wiki/` + peer-repo wikis cover.

**EM recommendation format (to PM):**

> Phase 1.5 research-depth assessment. Default is parallel Sonnet scouts (5–10 min/topic). For this roadmap I recommend escalating to `/research` (deep-research-web pipeline) on the following topic surface: <one-line per topic + why>. Cost: one deep-research run (~30–60 min, Opus synthesizer). Benefit: cross-topic claim verification, adversarial peer review of findings, structured claims.json that stubs can cite. Authorize, decline, or pick a subset.

`/research` is PM-gated (per the skill description — "PM-GATED: ask first; never from subagent"). EM never auto-invokes it; the recommendation is the gate. PM may authorize (a) full deep-research replacing solo scouts, (b) deep-research on a subset + solo scouts on the rest, or (c) decline and stay with solo scouts.

**When authorized:** dispatch `/research` per its skill contract; output lands under `state/roadmap/<run-id>/research-corpus/deep-research/<topic-slug>/`. OVERVIEW.md citations in Step 1.5.2 point at the deep-research artifacts (claims.json + summary.md + executive-summary.md) instead of (or in addition to) solo-scout files. Update the Phase 1.5 exit gate's "research-corpus exists" check to accept either shape. **When declined or not triggered:** proceed to Step 1.5.1 with solo Sonnet scouts. This step forces the EM to surface the depth call so the PM authorizes it — the doctrinal fix is not "always deep-research" (too expensive for routine roadmaps).

### Step 1.5.1 — Research corpus (parallel Sonnet scouts)

For each KEEP cluster (and each MERGE-target cluster that absorbs a KEEP), dispatch one `general-purpose` Sonnet scout in parallel. Cap at 8 concurrent; chunk if >8 clusters. Each scout's brief uses the verbatim internet-research dispatch language from `coordinator/snippets/internet-research-scout.md`:

> Use WebSearch and WebFetch directly to find answers and return a structured brief. Do NOT invoke any skills. Do NOT use the Deep Research pipeline. Do NOT spawn agents or teams. Your job is a quick solo web search — 5-10 minutes, a handful of queries, a clear brief back to me.

Plus topic-specific framing:
- Cluster topic + scope (one paragraph the EM authors from `clusters.md`).
- Output path: `state/roadmap/<run-id>/research-corpus/<topic-slug>.md`.
- Required sections: `## Primary sources`, `## Key findings`, `## Open questions`, `## How peer projects have done this` (if applicable).
- Disk-first verification preamble per `coordinator/snippets/em-operating-doctrine.md` § How to Dispatch, "Scouts are disk-first".

EM verifies each file exists and is non-trivial (≥2KB) before proceeding. Inline TEXT-ONLY recoveries per the same wiki section.

**Per-project research material counts as a primary source.** If `docs/wiki/`, `docs/research/`, or peer-repo wikis already cover a cluster, the scout cites those alongside web findings — does not duplicate. The scout decides.

**A measurement-derived corpus file may replace the scout outright for a cluster a web search cannot answer** — e.g. a question about this project's own schema, behavior, or prior `/spike` output, where a web scout would produce confident noise. The EM writes `research-corpus/<topic-slug>.md` by hand from first-hand measurement (probe output, a prior spike, direct inspection) instead of dispatching a scout. This is EM-authored ground truth, not scout output, so it carries a stricter bar: open with an explicit provenance paragraph stating it is not a web-research brief and why, cite `file:line` or a named run artifact per claim, and report results honestly even when inconvenient to the EM's preferred design — do not launder EM judgment as measurement. The reviewer at Step 1.5.5 checks this distinction specifically when present.

### Step 1.5.2 — OVERVIEW.md draft

EM authors `state/roadmap/<run-id>/OVERVIEW.md`. One section per KEEP cluster. **Head each section by cluster NAME, not by a provisional stub id or cluster number** (e.g. `## Source-availability registry`, not `## dsrc-01`) — stub numbers aren't assigned until Step 2.1.5, one phase later, by the topo-numbering op, which for any non-trivial DAG returns a *permutation* of the authoring order. A number-headed section silently disagrees with the eventual stub_id, and a `## Reference materials` citation by number in Step 2.2 then points at the wrong sibling section — internally consistent and wrong. Names are stable across renumbering; numbers are not. Each section MUST:

- Cite its `research-corpus/<topic-slug>.md` by path.
- Name the proposed architecture in one paragraph (not pseudocode — shape and seams).
- Name **contested decisions** explicitly under a `### Contested` sub-heading — anything where two reasonable engineers would pick differently. Silence here is the failure mode; if a section has no `### Contested` sub-heading, EM has not done the work.
- Name **certain vs. speculative** — what the research grounds, what is EM judgment.
- Cross-reference dependent clusters (forward references to other OVERVIEW sections).

The PM/EM declares `initiative:` at roadmap-planning time from the taxonomy in `state/initiatives/<id>.yaml`; it is never inferred downstream by cockpit or rag. When this roadmap doesn't attach to a known initiative, carry explicit `null` rather than omitting the key (D9 present-as-null) — a wrong attachment is worse than null, since downstream cockpit panels group on this field.

Frontmatter:

```yaml
---
roadmap_id: <run-id>
initiative: null        # nullable FK to state/initiatives/<id>.yaml; set when this roadmap belongs to a named initiative
status: draft           # draft | shape-approved | final-approved
shape_approved_by:      # filled in Step 1.5.4
shape_approved_at:
final_approved_by:      # filled in Step 1.5.6
final_approved_at:
---
```

### Step 1.5.3 — peer-team-asks.md

`state/roadmap/<run-id>/peer-team-asks.md`. Enumerates everything the roadmap needs from peer teams that we cannot deliver ourselves. Motivating case: example-game-repo engine team — items "behind the wall" (headless extraction at scale/speed, engine-side RAG ingestion hooks, etc.) require their cooperation. Empty file is permitted (must be present) — single bullet `- None identified at authoring time.`

Per-ask shape:

```markdown
## Ask N: <one-line>

- **Unblocks:** tc-X, tc-Y
- **What we need:** <concrete deliverable; "fast headless asset extraction CLI" not "help with extraction">
- **Why we can't do it ourselves:** <one paragraph; engine surface, expertise, code-ownership>
- **Who:** <peer-team-name + named contact if known>
- **Sharp question:** <the one question that, if answered, unblocks scoping on our side>
- **Status:** not-yet-sent | sent-<date> | answered-<date>
```

Stubs gated on a peer-team ask carry `awaiting_gate` plus `blocking_notes: peer-team-ask:<ask-slug> — <what is owed>` in their frontmatter, set in Phase 2. The gate-meaningfulness audit (§ After Phase 2) reads this text — keep the slug stable. (The audit also reads the slug from `gate_dependency:`, which older records carry.)

### Step 1.5.4 — PM round 1: shape approval (CHEAP RE-DIRECT)

Before reviewers run, surface OVERVIEW.md + peer-team-asks.md to the PM with the framing:

> Phase 1.5 round 1 — shape approval. Reviewers haven't run yet. This is the cheap point to re-direct: if the architectural shape or the set of peer-team asks is wrong, redirecting now costs one EM pass instead of two reviewer integrations + a stub-authoring fan-out. Outputs: `state/roadmap/<run-id>/OVERVIEW.md`, `state/roadmap/<run-id>/peer-team-asks.md`, `state/roadmap/<run-id>/research-corpus/`. Approve to proceed to reviewer dispatch, or redirect.

On PM approval, write `shape_approved_by: PM` and `shape_approved_at: <YYYY-MM-DD>` to OVERVIEW frontmatter and set `status: shape-approved`. On redirect, iterate the OVERVIEW (and re-dispatch any research-corpus topics whose scope changed) and re-surface.

### Step 1.5.5 — Primary rigor reviewer + domain reviewer (sequential)

Sequential, not parallel (per `coordinator/snippets/em-operating-doctrine.md` § How to Review What Came Back — plan/stub/doc carve-out applies). **Primary rigor-reviewer selection follows the same altitude rule as Step 2.8** — the Director of Engineering (`coordinator:eng-director`, standalone primary) when the roadmap sets cross-repo/cross-team boundaries (peer-team-asks cross-repo ask / ≥2-repo scope / sibling-consumed contract / cross-repo COORDINATOR-RESOLUTION); else the Staff Engineer (`coordinator:staff-eng`).

**Persist the persona verdict — auto-provisioned sidecar, doc-handoff contract.** Persona reviewers (the Staff Engineer, the Director of Engineering, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer) are auto-provisioned a `staff-eng-review`-typed sidecar at spawn (`report_type_map`, `state/subagent-share/…`). The brief states the contract: write the `ReviewOutput` there and return a pointer, not a dump — `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. Read that path for integrator dispatch. **Multi-reviewer chain:** the domain reviewer (step 3) gets the same contract; each reviewer writes to its own auto-provisioned sidecar.

1. Dispatch the **primary rigor reviewer** (the Director of Engineering or the Staff Engineer per the altitude rule) against `state/roadmap/<run-id>/` (full dir: OVERVIEW + research-corpus + peer-team-asks + Phase 1 artifacts). Brief: architectural soundness of OVERVIEW; contested-decisions completeness; peer-team-asks scope-appropriateness; whether research-corpus citations actually support the OVERVIEW claims (the citation-load-bearing check). When the Director of Engineering is primary, add the cross-repo-boundary lens (is the boundary drawn correctly; does the OVERVIEW assume authority over a sibling repo it shouldn't). Read-only. Brief states the doc-handoff contract above — write findings to the auto-provisioned sidecar and return the pointer as the reviewer's final action.
2. Integrate via `coordinator:review-integrator` (mode: auto) pointing at the on-disk sidecar path the reviewer returned — not an inline finding list.
3. Dispatch domain reviewer — the Game Dev Reviewer if game-dev / UE-flavored, the Data Science Reviewer if data-science / ML-flavored, the Front-End Reviewer if web-front-end flavored. EM picks based on roadmap shape; default the Data Science Reviewer if mixed/unclear (data shapes appear in most roadmaps). Brief: domain coherence, edge cases the OVERVIEW silently elides, premise gaps in research-corpus. Read-only. Brief states the same doc-handoff contract; write findings to the reviewer's own auto-provisioned sidecar and return the pointer as the final action.
4. Integrate via `coordinator:review-integrator` pointing at the on-disk sidecar path the domain reviewer returned.

### Step 1.5.6 — PM round 2: final approval

Surface the post-reviewer OVERVIEW + peer-team-asks to the PM with diff summary against the shape-approved version (`git diff <shape-approved-sha> -- state/roadmap/<run-id>/OVERVIEW.md state/roadmap/<run-id>/peer-team-asks.md`). Framing:

> Phase 1.5 round 2 — final approval. Reviewers integrated (the Staff Engineer + <domain>). This sign-off authorizes Phase 2 stub authoring; stubs will cite this OVERVIEW as ground truth. Diff summary attached. Approve to proceed to stub authoring, or surface remaining concerns.

On PM approval, write `final_approved_by: PM` and `final_approved_at: <YYYY-MM-DD>` to OVERVIEW frontmatter and set `status: final-approved`. **Phase 2 MUST NOT start without `status: final-approved`** — the Phase 2 entry checklist verifies this.

### Phase 1.5 exit gate

Before Phase 2, verify:
- [ ] Research-depth assessment recorded: either solo-scout default (no PM surfacing required) OR deep-research recommendation surfaced with PM disposition logged in OVERVIEW frontmatter (`research_depth: solo-scout | deep-research | mixed` + one-line PM disposition note if escalated).
- [ ] For every KEEP cluster (and MERGE-target cluster absorbing a KEEP): EITHER `research-corpus/<topic-slug>.md` ≥2KB (solo-scout path) OR `research-corpus/deep-research/<topic-slug>/` directory with at least `summary.md` + `claims.json` (deep-research path).
- [ ] `OVERVIEW.md` exists; every KEEP cluster has a section; every section cites its research-corpus file and has a `### Contested` sub-heading (even if "no contested decisions identified").
- [ ] `peer-team-asks.md` exists (may be empty-with-bullet; must be present).
- [ ] the Staff Engineer review integrated.
- [ ] Domain reviewer integrated.
- [ ] OVERVIEW frontmatter shows `status: final-approved`, both `shape_approved_*` and `final_approved_*` populated.

---

## Phase 2 — Plan: stubs + STUB-INDEX + constraint graph + PM-gates + reviews

**Goal:** every KEEP cluster becomes a `kind: roadmap-baton` stub. A roadmap-baton is an intention baton, not a spinoff, but it shares the same handoff lifecycle mechanics (per the lifecycle plan B+H) — it lives in `state/handoffs/`, queryable via `bin/query-records --type handoff`.

### Step 2.1 — Stub frontmatter (scaffold via coordinator-doc-new, then fill)

Per stub, scaffold first, then fill computed graph values via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type roadmap-baton --title "<stub title>" --roadmap-id <run-id> --stub-id <slug>-<N> --out state/handoffs/<date>_<HHMMSS>_roadmap-<slug>-<N>.md`.

**`--type` and `kind` now agree** — both are `roadmap-baton`. The retired doc-type spelling
`--type spinoff-roadmap` is still accepted as a permanent alias for in-flight callers, but
`--type roadmap-baton` is the canonical form going forward.

**Deliverable-spine threading (D1, C3d).** Each `roadmap-baton` stub is the *earliest artifact* for its deliverable and owns the identity (D1 design decision). The `deliverable_id` for a roadmap stub is `dlv-<stub_id>` — derived mechanically from the `stub_id` the scaffolding command already assigns. After scaffolding, set this in frontmatter:

**C3d — deliverable_id for roadmap stubs (D1: reuse stub identity, never mint separately).** Mint via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/mint-deliverable-id" --stub-id "<slug>-<N>"` — captured as `STUB_DLVR_ID`. The call logs "mint-from-stub path — minted: dlv-<slug>-<N>" to stderr; set in stub frontmatter: `deliverable_id: $STUB_DLVR_ID`.

This id is the durable join key for the deliverable: every plan or handoff authored *against* this stub inherits it via the C3d auto-inheritance rules in `skills/handoff` and `skills/spinoff` — no manual carry is required by the picking-up EM. Set `initiative:` in the stub frontmatter when this roadmap belongs to a known initiative (nullable FK; use the initiative id from `state/initiatives/<id>.yaml`).

This emits schema-valid frontmatter (all required fields present, placeholders for
graph values). After scaffolding, fill the computed fields from the `roadmap-number-stubs`
topo output (Step 2.1.5) and write the body (Step 2.2):

- `sprint:` — sprint grouping from topo linearization
- `wave:` — concurrency-gate index within sprint (depth + 1 for single-sprint roadmaps)
- `cost:` — T0|T1|T2|T3 estimation tier
- `blocks:` and `blocked_by:` — graph edges from the DAG
- `blocking_notes:` — advisory prose naming what gates this stub, when `deployment_state: awaiting_gate`. An `awaiting_gate` record must carry **at least one** of non-empty `blocked_by`, non-empty `blocking_notes`, or `gate_dependency`. Author the first two. **`gate_dependency:` is deprecated** (handoff schema C2): it takes free text where `blocked_by` takes a resolvable slug, and the schema rejects a path-shaped value outright (containing `tasks/` or `archive/`, or ending `.md`). A baton dependency goes in `blocked_by` as a slug; the prose goes in `blocking_notes`.
- `scope:` — in-scope pathspecs (git pathspec syntax)
- `workstream:` — roadmap short prefix slug

The scaffolded frontmatter schema (for reference; do not hand-author):

```yaml
---
title: <one-line>
created: <YYYY-MM-DD>
branch: <current-branch>
status: open
predecessor: none                 # load-bearing for spinoffs
kind: roadmap-baton
roadmap_id: <run-id>              # groups all stubs from one roadmap-planning invocation
stub_id: <slug>-<NN>              # globally-unique stub code; <slug> is this roadmap's short prefix, <NN> the zero-padded integer (min two digits, e.g. 04, 12)
deliverable_id: dlv-<slug>-<NN>  # C3d — durable join key; set to dlv-<stub_id> via mint-deliverable-id.py --stub-id (D1 reuse-stub-identity path)
initiative: null                  # nullable FK to state/initiatives/<id>.yaml; set when this roadmap belongs to a named initiative
authoring_session: state/roadmap/<run-id>/   # path-shaped audit trail back to the roadmap run dir; /pickup can Read this deterministically
workstream: <slug>
sprint: <N>                       # sprint grouping (typically 1–4)
wave: <N>                         # serialization-order grouping within a sprint
cost: <T0|T1|T2|T3>               # estimation tier — T0 trivial, T3 multi-day
deployment_state: awaiting_gate | ready_to_fire
blocking_notes: <one-line>        # advisory prose when awaiting_gate. awaiting_gate needs >=1 of
                                  # blocked_by / blocking_notes / gate_dependency; author the
                                  # first two (gate_dependency is deprecated, schema C2).
blocks: [<slug>-X, <slug>-Y]      # stub_ids that this stub unblocks when shipped
blocked_by: [<slug>-Z]            # stub_ids that must ship first
scope:
  - <pathspec 1>
  - <pathspec 2>
category: roadmap
summary: <one-line, ≤120 chars>
---
```

`authoring_session` is path-shaped (`state/roadmap/<run-id>/`) so `/pickup` can deterministically `Read` origin context. The wiki schema describes this field as a one-line description; for roadmap stubs we narrow it to a directory path (roadmap-specific narrowing; wiki amends if the convention broadens).

**Two schema fields NOT in the template** — they're populated by lifecycle events, not by `roadmap-planning`:

- **`pickup_ready: true`** — defaults to absent for roadmap stubs. Absence triggers a non-blocking warning at `/pickup` time (not a block); the EM proceeds to mutation. `awaiting_gate` + `blocked_by`/`blocking_notes` is the correct sequencing mechanism for stubs that must not be picked up yet — do not use `pickup_ready` absence as a gate.
- **`shipped_in: <sha-or-PR-ref>`** — never authored by the roadmap-planning skill. Set by `/handoff` or `/workstream-complete` post-execution when the work transitions to `deployment_state: shipped`. `/distill` requires this field present before deleting an archived stub (Phase 4c safety guard).

**Four schema fields also NOT in the scaffolded template** — `origin_session`, `origin_handoff`, `origin_plan_id`, `origin_goal_id` are NOT emitted by `_scaffold_spinoff_roadmap`; they are hand-filled post-scaffold per "Origin-provenance fields — fill at stub-authoring time" below.

**Origin-provenance fields — fill at stub-authoring time.** Resolve each field from live session context when writing the stub; these are the cheapest to capture correctly and impossible to reconstruct an hour later:

- **`origin_session:`** — `$CLAUDE_CODE_SESSION_ID` if set in the environment; else `cat .git/coordinator-sessions/.current-session-id 2>/dev/null`. A global UUID (no prefix). Emit explicit `null` when neither source is available. Scalar.
- **`origin_handoff:`** — the path of the active pickup baton this session was opened with (e.g. `state/handoffs/<YYYY-MM-DD>_<topic>.md`). Emit explicit `null` if this session has no active baton. Scalar. **Handoff paths only — a memo-origin session emits `null`.** The schema (claude-klabauter Rule C2-1b) requires a `state/handoffs/` path when non-null; a `cross-repo/inbox/…` memo path fails validation and blocks pickup. Carry the memo citation in `authoring_session:` instead. **The value MUST resolve** — confirm the path exists in `state/handoffs/`, `archive/handoffs/`, or git history before writing it; if you cannot confirm the baton path resolves on disk, emit `null` instead of a guessed or stale path. **Warning:** an unresolvable `origin_handoff` is hard-denied at write time by claude-klabauter's `coordinator_core/write_guards/validate_frontmatter_schema_deny.py`, and once committed it locks the stub against ALL future Edits — the guard revalidates whole post-edit frontmatter, so even a body-only edit is denied. Archival does NOT trigger this: `dag.resolve_target` resolves through `archive/handoffs/YYYY-MM/` and then git history, so only a path that never existed fails.
- **`origin_plan_id:`** — the `pln-…` id of the plan under execution at roadmap-authoring time, if any. Emit explicit `null` otherwise. Scalar.
- **`origin_goal_id:`** — an **array** of `goal-…` ids (kebab-case slug, `goal-` prefix) for the goal(s) this roadmap serves. Emit explicit `null` when no goal context is active. **Array even for a single goal** (multi-goal roadmaps are a documented real case — a roadmap serving multiple goals maps many-to-many).

> **Origin-provenance axis — distinct from `predecessor`:** `origin_*` records *where this stub was spawned from* (session, baton, plan, goal). This is a DISTINCT axis from `predecessor` (continuation spine — always `none` for spinoff kinds), `forked_from` (branch-point ancestry, a handoff-path), and `deliverable_id` (the `dlv-` grouping key). Never encode origin provenance in `predecessor:`.
>
> **Producer note:** do NOT build a parallel auto-populator for these fields — this is documentation-level frontmatter-fill guidance, not scaffolding logic.

Stubs are written to `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_roadmap-{stub_id}.md` (i.e. `..._roadmap-<slug>-<NN>.md`) so they appear alongside ad-hoc spinoffs in query-records output but cluster by `roadmap_id` for `/workday-start` reporting (per `commands/workday-start.md` Step 1.1 routing).

**Field semantics — clarifications:**

- **`wave: <N>` is a concurrency-gate primitive, NOT a sprint synonym.** Two distinct shapes:
  - **Wave** = single-dispatch parallel fan-out within a sprint, once verified. `roadmap-number-stubs` assigns a wave floor from DAG depth; it does NOT verify same-wave stubs are file-disjoint — that check is Step 2.4's judgment residue, run before fan-out, not a property the numbering op guarantees "by construction". Two independent (`blocked_by: []`) stubs at the same depth may also be numbered into distinct wave slots rather than sharing one, to satisfy Audit 2's `≤1 ready_to_fire` per `(roadmap_id, sprint, wave)` rule — see Step 2.1.5. Cost profile: one EM-session of dispatch + sync, once disjointness is confirmed. Risk profile: bounded — failure of one wave-N stub does not invalidate sibling stubs.
  - **Sprint** = multi-session sequence; the time-box across which wave-N → wave-N+1 gating fires. Cost profile: multi-day, multi-session, with `/handoff` between sessions. Risk profile: compound — a sprint-2 architectural finding can invalidate sprint-3 stubs authored against a now-wrong assumption.
  Do NOT use `wave:` for time-boxing or for unit-of-effort grouping; use `sprint:` for that. A roadmap with 20 stubs split as 4 sprints × 5 waves of 1 stub each is using `wave:` wrong — those should be 4 sprints × 1 wave × 5 sequential stubs, OR (if truly parallel) 4 sprints × 1 wave × 5 parallel stubs.
- **Hard gates go in `blocked_by:`; advisory prose goes in `blocking_notes:`.** A hard gate is a precondition that must land before this stub can be dispatched at all — typically a sibling stub_id, a merged PR, or a flipped feature flag — and it belongs in `blocked_by` as a resolvable slug, which is what gives the gate an index instead of a free-text one-liner. Soft cross-repo seams (advisory cues like "consider coordinating with peer-repo PR-N" or "watch for X downstream") belong in the stub body's `## Soft seams` section, never in a machine-read gate field. `blocked_by` drives query-records surfacing and `/pickup` gating logic; polluting it with unresolvable text causes false "still gated" reports. (`gate_dependency:` is the deprecated predecessor of this pair — see Step 2.1. It still validates on existing records, so you will meet it in the corpus; do not author new values into it.)
- **Soft seams declared in body, not frontmatter.** Each stub MUST include a `## Soft seams` section in its body (Step 2.2) enumerating workstreams it may overlap with, advisory cross-repo coordination notes, and any "consider coordinating with X" cues. Format: bulleted list, each entry one line, naming the peer workstream/PR/stub and the nature of the overlap (file-region, schema-shape, timing). The frontmatter `scope:` block remains the HARD declaration (machine-readable, drives `/pickup` safety-commit pathspec); `## Soft seams` is the SOFT declaration (human-readable, drives EM judgment when sequencing parallel waves).
- **Audit-spike sizing heuristic.** When an audit/spike has exactly one downstream consumer, fold it as Phase 0 of that consumer's implementation stub rather than authoring a standalone audit stub — the audit's output never reaches a second consumer, so the stub overhead is pure ceremony. Standalone audit stubs earn their own stub_id only when ≥2 downstream consumers will read the audit output to define their own behavior. Cross-EM gate-waiting on a single-consumer audit-spike costs more than the leverage it delivers.
- **Stub-dedup canonical = git commit provenance, not the filename timestamp.** When two stubs of the same stub_id exist (e.g. `11xxxx_…_<slug>-3.md` and `14xxxx_…_<slug>-3.md`), the canonical is whichever was committed FIRST as a deliberate per-stub commit — NOT whichever has the earlier HHMMSS prefix. Filename timestamps can invert the truth when an HHMMSS-earlier draft gets bulk-committed later than the HHMMSS-later canonical. Determine canonical from `git log -- <each-stub-path>` + the STUB-INDEX + any existing archival precedent (e.g. prior `.DUPLICATE-FROM-BULK-COMMIT.md`-suffixed siblings). When the duplicated pairs are **divergent** (drafts sometimes structurally richer than the canonical — extra sections, more thorough acceptance criteria), the safe dedup is `git mv` to `archive/` with a `.DUPLICATE-FROM-BULK-COMMIT.md` suffix, NOT `git rm` — it preserves draft-only content at zero cost for the eventual implementing EM, who may want the richer draft's text.

### Step 2.1.5 — Assign stub numbers in dependency order

Before writing any stub frontmatter, resolve the final `stub_id` integer (`N`), `sprint`, and `wave` for every stub in topological (dependency) order. A lower-numbered stub must never depend on a higher-numbered one.

**Invariant (strict):** stub numbers are a topological linearization of the `blocks`/`blocked_by` DAG — for every edge `A blocked_by B`, `number(B) < number(A)` AND the `(sprint, wave)` execution slot is **strictly dependency-monotone**: `(sprint(B), wave(B)) <_lex (sprint(A), wave(A))`. A dependency and its dependent sharing the same `(sprint, wave)` slot is itself a violation — `blocked_by` is a hard gate and wave members dispatch concurrently.

**Steps:**

1. **Build the provisional dependency graph** from `clusters.md` before any stubs exist. List every KEEP cluster as a provisional label and draw `A blocked_by B` edges from the cluster dependency notes (or COORDINATOR-RESOLUTIONS where applicable).

2. **Invoke the topo-numbering op** — `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/roadmap-number-stubs" <edges-file>`. **Edges-file format:** one edge per line, `A <- B` meaning "A blocked_by B"; `#` comments and blank lines are ignored; a bare label with no `<-` on its line is an isolated node (no dependency), not an error. A JSON array of `{from, to}` objects is also accepted. A file with more than one non-comment line that yields zero parsed edges is almost certainly a format error (e.g. `A blocked_by B` prose instead of `A <- B`) — the op silently linearizes the nodes as independent in that case, so sanity-check the printed wave assignments against the dependency notes in `clusters.md` before transcribing; if every stub lands in its own wave and you expected shared waves, suspect a malformed edges file first. The op applies Kahn's algorithm over the DAG and prints a `label → (stub_id N, sprint, wave)` mapping (topo-layer ties broken deterministically by original cluster index; single-sprint roadmaps get `wave = depth + 1` by construction). Alternatively, apply Kahn's sort and number by hand if the graph is small.

   **The op computes a safe serial linearization, not a parallelism plan.** `wave = depth + 1` gives every stub a wave floor from the DAG, but the op cannot see file overlap — it does not, and structurally cannot, verify that same-wave stubs are file-disjoint. Achieving actual parallel dispatch is the EM's job, done at Step 2.4 by checking `scope:` overlap before fan-out ("the one unconditional serial gate"). Independent (`blocked_by: []`) same-depth stubs may still be assigned to **distinct** wave numbers rather than sharing one — Audit 2 permits at most one `ready_to_fire` per `(roadmap_id, sprint, wave)`, so genuinely parallel starters are spread across separate wave slots as a pickup-staging device, not serialized; A picking-up session still takes them together, because it enumerates `ready_to_fire` across the whole sprint rather than one wave at a time. Do not read "each stub got its own wave" as proof the roadmap is sequential — check `blocked_by` first.

   **Multi-sprint roadmaps:** the op's output is the topological linearization order only; the author still assigns `sprint` values by hand (grouping linearized stubs into sprint boundaries) — judgment residue the op does not resolve. Audit 5 (see Step 2.7) verifies the resulting `(sprint, wave)` strict monotonicity after stubs are on disk.

3. **Consume the op's mapping into stub frontmatter** (Step 2.1 template fields). The op is read-only/print-only — it does not write frontmatter directly — so transcribe its printed `N`/`sprint`/`wave` values verbatim; do not auto-mutate authored markdown from its output. Zero-pad the stub number to at least two digits (width = max(2, digits of the highest N in the set)) — the op already emits padded values; match them exactly in frontmatter and filenames.

   This zero-pad-to-≥2-digits convention applies to any ordered/numbered artifact set we author (not only roadmap stubs), so files sort lexically and read uniformly.

**This guarantee applies exclusively to DECLARED `blocked_by` edges.** The gate cannot discover an undeclared or missing dependency — that remains a human / OVERVIEW-review responsibility.

### Step 2.2 — Body sections (per stub)

- `# <title>`
- One-paragraph "why this exists as its own session"
- `## What this covers` — origin context, scope.
- `## Reference materials (read first)` — file paths. **MUST cite `state/roadmap/<run-id>/OVERVIEW.md § <cluster-section-name>`** as the architectural ground truth, AND **MUST cite the relevant `state/roadmap/<run-id>/research-corpus/<topic-slug>.md` files** that the stub's scope leans on. Cite the OVERVIEW section by its NAME (per Step 1.5.2's naming convention), never by stub number or provisional cluster number — the stub's own `stub_id` did not exist when the section was written, and citing by number risks pointing at a sibling's section if a fan-out agent guesses stub_id == cluster number. Stubs that introduce architecture not present in OVERVIEW.md are caught in Step 2.8 review as drift — the OVERVIEW is doctrine, the stub is implementation of doctrine.
- `## Specification` — concrete enough that a context-less EM can act.
- `## Acceptance criteria` — binary checklist.
- `## Recommended next steps for the picking-up EM` — 3–7 numbered, each verifiable.
- `## Anti-scope` — what NOT to do.
- `## Soft seams` — bulleted enumeration of workstreams/PRs/stubs this stub may overlap with; one line per seam naming peer + overlap nature. MAY be empty (single bullet: `- None identified at authoring time.`); MUST be present. Distinct from frontmatter `scope:` (HARD pathspec) and `blocked_by:` (HARD graph edge).
- Trailing marker: `<!-- roadmap-baton: <run-id> <stub_id> by roadmap-planning -->`

### Step 2.3 — STUB-INDEX as a query callout

Write `state/roadmap/<run-id>/STUB-INDEX.md`:

```markdown
# STUB-INDEX — <run-id>

<!-- BEGIN query: handoff where=roadmap_id=<run-id> sort=sprint -->
(regenerated by /update-docs Phase 11c via bin/refresh-queries.py)
<!-- END query -->
```

NOT a hand-maintained table. Do NOT hand-add a static-snapshot table below the callout — the callout is the single authoritative rendered surface. The query callout regenerates at `/pickup` and `/workstream-complete` (scoped to the baton's roadmap) and on every `/update-docs` run (all roadmaps), so the index always reflects current frontmatter.

**Single-clause `where=` only inside callouts.** `bin/refresh-queries.py` token-splits the BEGIN marker on whitespace, so a multi-clause where like `where=kind=roadmap-baton AND roadmap_id=...` would silently lose every clause after the first space. Single-clause `where=roadmap_id=<run-id>` is sufficient because the cross-field validator (`bin/lib/schema.js` CROSS_FIELD_RULES.handoff) enforces `roadmap_id` ⇒ `kind: roadmap-baton` — the kind clause is redundant. **Multi-condition queries from the CLI work fine** (`--where "X AND Y"` in shell quotes); the limitation is callout-only. Future enhancement candidate: extend `refresh-queries.py` to accept quoted multi-clause where; tracked in the improvement queue.

### Step 2.4 — Constraint graph (machine-readable in frontmatter)

`blocks` and `blocked_by` arrays in each stub's frontmatter ARE the graph. To visualize, pipe `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-records" --type handoff --where "kind=roadmap-baton AND roadmap_id=<run-id>" --format json` into `<graphviz-script>`.

Wave order is assigned in dependency order per **Step 2.1.5** — stub numbers are a topological linearization of the `blocks`/`blocked_by` DAG, and the `(sprint, wave)` execution slot is **strictly dependency-monotone** (`(sprint(B), wave(B)) <_lex (sprint(A), wave(A))` for every edge `A blocked_by B`; same-slot is a violation). For single-sprint roadmaps `bin/roadmap-number-stubs` is constructive (wave = depth + 1); for multi-sprint roadmaps the author assigns sprint boundaries from the topo order and **Audit 5** (`audit-roadmap.py`) verifies the strict monotonicity gate at Phase 2 close. If you find yourself hand-maintaining a wave-order table, stop — you've recreated the brief's failure mode (siblings, not subsets).

**`sort=sprint` reminder:** `query-records` sorts by frontmatter field name; `sprint` is a roadmap-stub frontmatter field, so the callout's `sort=sprint` IS valid syntactically. But no multi-sprint corpus has yet confirmed sprint-sort actually executes. On the next multi-sprint roadmap run, verify sort ordering against expected sprint sequence; if it sorts by `created` instead, file an improvement-queue entry.

**Pre-derive the design graph BEFORE any fan-out (hard gate) — name the checks, don't narrate them.** The wave order is a *derived* artifact — topologically sorted over `blocked_by` — not an assumption the dispatching EM makes by reading sprint numbers. This is verified at Phase 2 close and RECORDED for the sessions that will pick the stubs up — this skill never fans out a wave itself. Run two ops plus one judgment check:

1. Fetch the stub set — `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-records" --type handoff --where "roadmap_id=<run-id>" --format json`.
2. Invoke the dependency-order op — `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/audit-roadmap" <run-id>` (Audit 5): confirms every `blocked_by` edge resolves to a stub_id in this set, the graph is acyclic, and no dependency endpoint is missing `sprint`. Exit 1 names the specific offending edge and blocks dispatch.
3. **Judgment residue (the op does not check this):** confirm every wave-N stub set is file-disjoint per its `scope:` blocks — overlap is the one unconditional serial gate.

A fan-out dispatched against an unverified or cyclic graph is the "siblings, not subsets" failure the skill exists to prevent, now in execution form: executors collide on shared files or block on edges that were never real. The checks are cheap (one query + one op run); skipping them costs an aborted wave.

### Step 2.5 — `pm-gates.md` enumeration (brief recommendation E)

Phase 2 forces explicit enumeration of every product-coupled question. Write `state/roadmap/<run-id>/pm-gates.md`:

```markdown
# PM Gates — <run-id>

| sprint | stub_id | gate question | disposition format | resolved? |
|---|---|---|---|---|
| 2 | dscov-15 | should consumer_runner emit retry telemetry by default? | yes/no/defer | pending |
```

**Detection rule for "product-coupled":** during Phase 2 stub authoring, scan each stub's `gate_dependency:` text for any of: explicit `PM `-prefixed strings, named-stakeholder references, `decision needed` / `approval needed` / `policy` / `scope` / `user-facing` tokens. Each hit becomes a row in `pm-gates.md`. Author can add rows manually for product-coupled questions whose `gate_dependency:` text doesn't trip the detector.

**Manual audit at Phase 2 close (cross-file; `bin/lint-frontmatter` cannot do cross-file validation):** for every stub with `gate_dependency:` starting `PM `, confirm an entry exists in `pm-gates.md` (`stub_id` column). For every row in `pm-gates.md` with `resolved? = pending`, confirm at least one stub references it via `gate_dependency:` text. Mismatch blocks Phase 2 close. Automation candidate post-dogfood: a `audit-roadmap.py <run-id>` script that runs all Phase 2 cross-file checks.

### Step 2.6 — Stub-coverage audit (brief recommendation G)

Invoke the op at Phase 2 close: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/audit-roadmap" <run-id>` (Audit 1) — checks `count(MERGE + KEEP verdicts in reconciliation.md) == count(stubs on disk, live + archived, with this run's roadmap_id)`. (DROP / DEFER / MOVE verdicts do NOT produce stubs by definition; only MERGE + KEEP do.)

Mismatch BLOCKS Phase 2 close (op exits 1). Surface to PM with the diff: which clusters lack stubs, which stubs lack source clusters. This would have caught ESC-4 in the project-rag episode (6 stubs shipped without source clusters).

### Step 2.7 — `kind: roadmap-baton` tripwire (brief recommendation H)

Validator rules (added to `bin/lint-frontmatter` cross-field rules):
- Any handoff with `roadmap_id:` MUST have `kind: roadmap-baton`.
- Any `kind: roadmap-baton` MUST have `roadmap_id:` AND `blocks` AND `blocked_by` AND `wave: <integer>` AND `stub_id:` non-empty.
- `stub_id:` MUST be globally unique. It is `<slug>-<NN>` where `<slug>` is this roadmap's short prefix derived from its roadmap_id, `<NN>` is a zero-padded roadmap-local integer (min two digits, e.g. `pcore-04`, `pcore-12`). The `<slug>` MUST be distinct from every existing roadmap's slug — grep existing `stub_id:` prefixes across state/handoffs/ and archive/handoffs/ before choosing one, so codes are self-qualifying and never collide across roadmaps.
- At most one `ready_to_fire` per `(roadmap_id, sprint, wave)` triple across the active set. Wave is sprint-LOCAL (§ "Wave = single-dispatch parallel fan-out within a sprint"), so wave 1 of sprint 1 and wave 1 of sprint 4 are distinct execution slots and do NOT collide. `audit-roadmap.py` Audit 2 enforces this composite key.
- **`cost` if present MUST be one of T0/T1/T2/T3.** A separate cross-field rule in `bin/lint-frontmatter` enforces this (added alongside the kind:roadmap-baton rules). A stub with `cost: "very large"` is rejected at lint time.
- **Audit 5 — dependency order invariant (`bin/audit-roadmap.py`).** For every declared `A blocked_by B` edge across the stub set: `number(B) < number(A)` AND `(sprint(B), wave(B)) <_lex (sprint(A), wave(A))` (STRICT — same-slot is a violation). Also checks: no cycles in the `blocked_by` graph; no unresolved edges (a `blocked_by` entry pointing at a stub_id absent from the set); no missing `sprint` field on either endpoint of a dependency edge (fail-loud own violation class, not silent coercion). Runs at Phase 2 close; exit 1 names the specific offending edge and blocks the close. (The op's stdout phrases this as "Phase 3 dispatch is blocked" — claude-klabauter-resident wording for the same verdict: these stubs are not fit to hand forward.)

Prevents the brief's "siblings, not subsets" failure mode — stubs cannot exist outside a roadmap parent, and roadmap parents cannot exist without graph primitives.

### Step 2.8 — Primary rigor reviewer then domain reviewer (sequential; primary mandatory, domain conditional)

#### Primary rigor-reviewer selection by altitude (cross-repo boundary → the Director of Engineering, else the Staff Engineer)

The default primary rigor reviewer for the stub set is **the Staff Engineer** (`coordinator:staff-eng`, EM-altitude). BUT when the roadmap **sets cross-repo or cross-team boundaries**, the primary reviewer is **the Director of Engineering** (`coordinator:eng-director`, standalone primary mode). Setting cross-repo/cross-team boundaries is DoE-altitude authority an EM-altitude reviewer structurally lacks — it is exactly why the Staff Engineer reaches for a the Director of Engineering backstop on such seams; at this gate the backstop becomes the primary. Detect "sets cross-repo/cross-team boundaries" by ANY of:

- (a) `peer-team-asks.md` carries a non-trivial cross-repo / cross-team ask;
- (b) the stubs' `scope:` pathspecs resolve into ≥2 repos;
- (c) the roadmap authors or amends a contract / interface / wire-format consumed by a sibling repo;
- (d) `COORDINATOR-RESOLUTIONS.md` sets a cross-repo coordination, ownership, or version-cutover boundary.

When the Director of Engineering is primary, the Staff Engineer MAY still run as the second reviewer or a backstop pass; the domain/data reviewer (below) is unchanged. **The same selection rule governs the Step 1.5.5 OVERVIEW review.**

**Sequential, not parallel** (merge-gate parallel carve-out explicitly excludes plan/stub/doc review — a roadmap stub set is plan/stub/doc-shaped).

**Persist the persona verdict — auto-provisioned sidecar, doc-handoff contract.** Persona reviewers (the Staff Engineer, the Director of Engineering, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer) are auto-provisioned a `staff-eng-review`-typed sidecar at spawn (`report_type_map`, `state/subagent-share/…`) — the single target path for this review pass (no separate `docs/plans/<run-id>-stubs.review.md`; that path named an EM-injected target that predates identity-triggered provisioning and is retired here to avoid two conflicting sidecars per reviewer). The brief states the contract: write the `ReviewOutput` there and return a pointer, not a dump — `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. Read that path for integrator dispatch. **Multi-reviewer chain:** the domain reviewer (step 3) gets the same contract; each reviewer writes to its own auto-provisioned sidecar.

Sequence:
1. Dispatch the **primary rigor reviewer** (the Director of Engineering if the roadmap sets cross-repo/cross-team boundaries per the rule above, else the Staff Engineer) with the full `state/roadmap/<run-id>/` directory + all stubs. Brief: schema/architecture/sequencing review of the stub set; flag P0 conflicts, missing AC surface, scope errors, sequencing bugs in the constraint graph. **When the Director of Engineering is primary, the brief ALSO carries the cross-repo-boundary lens** — is the boundary drawn correctly; does any stub assume direct authority over a sibling repo it shouldn't; is the cross-repo coordination (memo + PM-relay) routed right. Read-only. Brief states the doc-handoff contract above — write findings to the auto-provisioned sidecar and return the pointer as the reviewer's final action.
2. Integrate the primary reviewer's findings via `coordinator:review-integrator` (mode: auto) pointing at the on-disk sidecar path the reviewer returned. EM spot-checks the diff.
3. Dispatch the domain/data reviewer — the Data Science Reviewer for data shapes (default), or the Game Dev Reviewer (game-dev/UE) / the Front-End Reviewer (web) per roadmap flavor — with the same directory. Brief: domain coherence + data shapes; flag clusters whose stubs would compose poorly, premise gaps, edge cases the stub set silently elides. Read-only. Brief states the same doc-handoff contract; write findings to the reviewer's own auto-provisioned sidecar and return the pointer as the final action.
4. Integrate the domain reviewer's findings via `coordinator:review-integrator` pointing at the on-disk sidecar path the domain reviewer returned.

The latency cost is acceptable: fires once per roadmap, the domain reviewer benefits from the primary reviewer's integrated changes, and the sequential rule holds across all plan-shaped review.

#### Domain/data reviewer skip condition (ceremony-calibration)

The **primary rigor review (steps 1–2) is always mandatory.** The **domain/data reviewer (steps 3–4) is SKIPPABLE** when BOTH hold:

- (a) the same domain reviewer already ran at **Step 1.5.5** on the OVERVIEW and their findings were integrated and **pinned into the stub ACs** — i.e. the stubs carry the reviewed data shapes verbatim (via COORDINATOR-RESOLUTIONS), not new ones; AND
- (b) **each stub becomes a downstream `coordinator:plan`** (per § Anti-scope) that gets its own domain review at `coordinator:review` — so the data-shape lens is re-applied at the per-stub PLAN altitude, where it is most load-bearing (concrete DDL / emitter code, not stub prose).

When both hold, the primary rigor reviewer is the sufficient stub-set gate and a second full domain pass on the stubs is **redundant-by-convergence** — skip it and record a one-line skip rationale in the roadmap dir (e.g. a note in `pm-gates.md` or a commit message). The domain pass at 2.8 is **REQUIRED** when: the OVERVIEW domain review (1.5.5) was skipped; OR the stubs introduce data shapes not present in the reviewed OVERVIEW; OR the primary rigor reviewer flags an unresolved data-shape concern. Rationale: do not run a review whose findings are pre-converged and which recurs at a better altitude downstream.

### Phase 2 entry gate

Before Phase 2 begins:
- [ ] `state/roadmap/<run-id>/OVERVIEW.md` frontmatter shows `status: final-approved` with both `shape_approved_by: PM` and `final_approved_by: PM` populated.
- [ ] Phase 1.5 exit gate fully checked.

If either fails: STOP and return to Phase 1.5. Authoring stubs against an unapproved OVERVIEW risks committing execution to architecture the PM has not ratified.

### Phase 2 exit gate

Before the stubs are handed forward (Phase 2 close):
- [ ] Every KEEP cluster has a stub on disk.
- [ ] Every stub's `## Reference materials` cites `OVERVIEW.md § <cluster>` AND at least one `research-corpus/` file.
- [ ] Every stub has the canonical frontmatter (validator clean).
- [ ] STUB-INDEX query callout regenerates correctly.
- [ ] COORDINATOR-RESOLUTIONS exists for every conflict.
- [ ] `pm-gates.md` enumerates every PM-gate; each is cross-referenced in stub frontmatter.
- [ ] Stub-coverage audit passes (MERGE+KEEP count matches stub count).
- [ ] Every stub has a `## Soft seams` section (may be empty with `- None identified`, must be present per Step 2.2).
- [ ] `kind: roadmap-baton` validator clean across all stubs.
- [ ] Primary rigor review integrated (the Director of Engineering at cross-repo/cross-team altitude, else the Staff Engineer — per Step 1.5.5's altitude rule).
- [ ] Domain review integrated, or its skip condition met AND the skip rationale recorded in the run directory.
- [ ] Design graph derived and verified: `blocks`/`blocked_by` edges all resolve, graph is acyclic (acyclicity is now **ENFORCED by Audit 5** — not a manual checkbox; the gate cannot drift back to manual), every wave-N set is file-disjoint by `scope:`. (Pre-fan-out gate per Step 2.4.)
- [ ] Dependency-order invariant: `audit-roadmap.py` Audit 5 green — no lower-number-depends-on-higher, `(sprint, wave)` strictly dependency-monotone (`<_lex`), acyclic, no unresolved edges, no missing `sprint` on dependency endpoints.

---

## After Phase 2 — the stubs go live

**This run ends when the stubs are on disk and audited. Phase 2 close IS the deliverable.**

**A stub is a baton, and handing it forward is the point of authoring it.** A fresh session picks
one up via `/pickup` whenever it is ready; everything that session needs is in the stub. This skill
therefore has no execution phase, runs no sprint loop, and never invokes `coordinator:plan` — the
§ Anti-scope and ceremony-ladder statements of that seam are load-bearing, not aspirational. A
roadmap-planning session that picks its own stubs back up has to outlive the entire roadmap's
execution, which is both unrunnable and a defeat of the artifact it just authored.

Three mechanisms live downstream. They are named here so the author knows the ground is covered,
not so this run performs them:

- **Readiness view.** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/roadmap-number-stubs" --state <run-id>` prints every stub's `deployment_state` and its gate text, sorted by `(sprint, wave, stub_id)`. It is a *view* for whoever is choosing what to pick up — never a loop this skill runs. `/workday-start` already carries roadmap-stub-aware sections (e.g. Step 1.473's shipped-stub promotion, Step 1.55's recent-roadmap orientation) and is the obvious future home for surfacing this view; neither it nor `/workstream-start` wires the resolver in yet.
- **Gate transitions are not this skill's to make.** A stub moves `awaiting_gate → ready_to_fire` when the `/handoff` or `/workstream-complete` of some *other* session clears its gate. Never auto-transition a sibling's stub, and never pre-emptively mark one ready because its gate looks satisfied from here.
- **End-of-roadmap review** belongs to whoever closes the roadmap out — a cross-cutting pass over the shipped output, dispatched from `/workstream-complete` once every stub has shipped. Specified below for that session, not queued for this one.

**Roadmap stubs are never handed to `/mise-en-place` directly.** Mise's Phase 0 readiness gate
rejects them by construction, on three independent counts: `deployment_state: awaiting_gate` is a
hard bypass-disqualifier and is one of the two legal stub states; criterion 1 ("the decisions are
made") fails because a stub is precisely the artifact that carries decisions forward — its
`pm-gates.md` rows and `## Recommended next steps` block are open forks by design; and criterion 3
("a single Sonnet executor can complete it given the spec") fails because a stub's deliverable is
decisions, not typed lines. Mise optimizes for deep planning BEFORE the run; the stub is the
pre-planning artifact. Routing stubs there produces a guaranteed reject-and-`pickup-assemble drop`
round trip.

### Downstream mechanism — gate-meaningfulness audit (brief recommendation F)

**Fires from `/handoff` and `/workstream-complete`, never from this skill.** Specified here because
this skill authors the gates it audits.

Named op: **gate-meaningfulness-audit**, invoked by `/handoff` and `/workstream-complete` whenever either is about to write `deployment_state: ready_to_fire` over an existing `awaiting_gate` value (the *unblock* event). NOT invoked from `/pickup` — pickup transitions to `in_flight`, not `ready_to_fire`.

The op resolves prior frontmatter from git (`git show HEAD:state/handoffs/<file>`) and fires only on a detected `awaiting_gate → ready_to_fire` edge. Idempotent under concurrent-EM operation by construction: it fires only on that literal edge observed against the file's current git state, so a stub a concurrent EM already transitioned reads `ready_to_fire` as the prior state and the op skips silently — no double-prompt, no race window where neither EM fires it. Two concurrent EMs both attempting the unblock: whichever's commit lands first owns the audit.

**Judgment residue (the op surfaces this; it does not resolve it — human/EM call only):** on a detected edge, the op surfaces the prior `blocking_notes` text (falling back to `gate_dependency` for pre-deprecation records that carry the prose there instead) and asks:

```
The gate that blocked this stub was:
  <blocking_notes (or gate_dependency, for older records) text from prior frontmatter>

Does that gate still mean what it meant when authored? (y/n/clarify)
```

- `y` → transition proceeds.
- `n` → stub returns to `awaiting_gate`; author updates `blocking_notes` (or `gate_dependency` on an older record still carrying it there) to reflect what's actually now blocking.
- `clarify` → PM disposition required before transition.

Would have caught ESC-5 (G1 went structurally hollow when synthetic-baseline acceptance changed its meaning).

### Downstream mechanism — end-of-roadmap review

**Owned by the session that closes the roadmap out, not by this run.** Once every stub has shipped,
dispatch ONE Sonnet review across the whole roadmap output — NOT per-wave Opus (empirical finding: end-of-run
Sonnet beat per-wave Opus on cost without meaningful signal loss). Brief: "Cross-cutting review of
<run-id> roadmap execution. Flag any drift from stubs, missing acceptance criteria, deferred items
that should have been fixed in-session." **Dispatch `coordinator:code-reviewer`** (UNNAMED — no `name:` param, auto-provisioned its sidecar at spawn):

1. **Dispatch `coordinator:code-reviewer`** (UNNAMED) on the roadmap output. It is auto-provisioned a `review-findings`-typed sidecar at spawn (`report_type_map`, `state/subagent-share/…`); the brief states the doc-handoff contract: write findings there and return a pointer, not a dump — `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. No pre-scaffold, no claim marker. Read the returned path.
2. **Integrate via `coordinator:review-integrator`** pointing at the on-disk sidecar path from the returned pointer — not an inline finding list (`agents/review-integrator.md` § Intake precondition hard-stops on inline-relayed findings). Surface escalations (ESC-N format) to PM.

---

## Output artifacts (full list)

By the end of a roadmap-planning run:

- `state/roadmap/<run-id>/inventory.md` — Phase 1 input listing
- `state/roadmap/<run-id>/clusters.md` — Phase 1 cluster grid
- `state/roadmap/<run-id>/reconciliation.md` — Phase 1 verdicts
- `state/roadmap/<run-id>/COORDINATOR-RESOLUTIONS.md` — Phase 1 conflict resolutions (if any)
- `state/roadmap/<run-id>/research-corpus/<topic-slug>.md` × N — Phase 1.5 primary-research scout output (one per KEEP cluster)
- `state/roadmap/<run-id>/OVERVIEW.md` — Phase 1.5 architectural overview (PM double-approved: shape + final)
- `state/roadmap/<run-id>/peer-team-asks.md` — Phase 1.5 enumeration of cross-team dependencies
- `state/roadmap/<run-id>/STUB-INDEX.md` — Phase 2 query callout (regenerated by `/update-docs`)
- `state/roadmap/<run-id>/pm-gates.md` — Phase 2 PM-gate enumeration
- `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_roadmap-{stub_id}.md` × N (i.e. `..._roadmap-<slug>-<NN>.md`, per Step 2.1) — Phase 2 stubs (one per KEEP / MERGE-target cluster)

Stubs live alongside ad-hoc spinoffs and continuation handoffs; `roadmap_id:` clusters them. `/workstream-start`, `/workday-start`, `/pickup` light up automatically — no second-class artifact.

---

## Contact-points checklist

- **`/handoff` and `/spinoff` durability rules apply with extra force to roadmap stubs.** Gate text MUST be subsystem-named (e.g., `consumer_runner retry telemetry policy`), never file-pathed (e.g., `state/handoffs/<YYYY-MM-DD>_<topic>.md ships`). The gate-meaningfulness audit (§ After Phase 2) reads this text from git history via `git show HEAD:<file>`; a file-pathed dependency goes stale on archive-to-`archive/handoffs/` and breaks the audit prompt by displaying a dangling reference. That is why the schema **rejects** a path-shaped `gate_dependency` value outright — put the baton dependency in `blocked_by` as a resolvable slug and the prose in `blocking_notes`. The picking-up EM editing a roadmap stub's frontmatter must respect this.

- **`/repo-setup`** — verify roadmap-planning is mentioned in the orientation flow when the project tracker contains roadmap entries.
- **`/workstream-start`** — query callout already covers `kind: roadmap-baton` via the universal `deployment_state=ready_to_fire` filter.
- **`/workstream-complete`** — verifies workstream-complete's plan-doc update step covers roadmap stubs (no special-case logic; they share the handoff lifecycle).
- **`/workday-start`** — Step 1.1 routing groups `kind: roadmap-baton` with spinoffs and clusters by `roadmap_id` when count > 3 per group.
- **Hooks:** the boot-time archival sweep (claude-klabauter `coordinator_core/ops/` `session.boot_sweep`, fronted by `bin/sweep-boot.py`) provides a quiet sweep: consumed handoffs whose authoring session is dead are silently archived to `archive/handoffs/`. Covers orphaned roadmap stubs without roadmap-specific hook logic.
- **Canonical artifact:** roadmap stubs themselves are the artifact agents will encounter. The `kind:` enum and frontmatter schema make them discoverable via `bin/query-records --list-schemas` and `bin/lint-frontmatter --list-schemas`.

---

## Anti-scope (what this skill does NOT do)

- Auto-derive `blocking_notes:`/`gate_dependency:` text from natural language. Author-supplied only.
- Cross-repo roadmap rollup. Single-repo only for v1.
- Auto-trigger gate-meaningfulness on `/pickup` (only on `awaiting_gate → ready_to_fire` transitions, which are `/handoff` and `/workstream-complete` events).
- Render dashboards or HTML. The query callout in markdown is the surface.
- **Replace `coordinator:plan` for single-plan work.** If a roadmap stub itself becomes the basis for a `coordinator:plan` invocation, that's a downstream plan in the same workstream — NOT a continuation of the stub. The picking-up EM running `coordinator:plan` against a stub:
  - keeps the stub's `deployment_state: in_flight` (set by `/pickup` at archival time),
  - writes the resulting plan-doc with `predecessor: none` (the plan is forked, not continued),
  - documents the lineage in the plan-doc body's "Why this plan" section, citing the stub's `roadmap_id/stub_id` (e.g., "originating roadmap stub: `dogfood-2026-05-08/dogfood-3`").

  A future schema extension may add a `roadmap_parent:` field to plan-doc frontmatter for machine-readable lineage; that's deferred until a second instance of plan-from-stub demonstrates the textual citation pattern is insufficient for retrieval. PM disposition required to add the field.

---

## See also

- `commands/distill.md` — extracts knowledge from completed roadmap stubs
- `coordinator:plan` — for single-plan work downstream of a roadmap stub (the rung below in the ceremony ladder)
- `coordinator:brainstorming` — for pre-roadmap option exploration
- `coordinator/skills/shape/SKILL.md` — upstream of Entry Point C; sets `estimated_horizon: week` at ratification to route here
- `coordinator:goal-setting` — upstream of Entry Point B; spawns `kind: roadmap-seed` stubs (the rung above in the ceremony ladder)
