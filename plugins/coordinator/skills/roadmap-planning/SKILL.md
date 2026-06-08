---
name: roadmap-planning
description-budget: 400
description: PM-GATED. Roadmap shaping from research/deep-dive/peer-repo inputs via Synthesize → Substantiate → Plan → Dispatch pipeline producing kind:spinoff-roadmap stubs with deployment_state, blocks/blocked_by graph, machine-readable STUB-INDEX. Stubs cite PM-approved OVERVIEW + research corpus, not EM hand-waving. Triggers — "shape a roadmap", "plan a sprint sequence from this research".
version: 1.1.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "<input-corpus-path> [--run-id <slug>]"
---

# Roadmap Planning — From Inputs to Sequenced Spinoff Stubs

> **Spec backlink:** `docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` § Phase 5. Empirical motivator: `archive/specs/2026-05-08-roadmap-planning-skill-brief.md` (project-rag cross-deep-dive-synthesis episode, 2026-05-03 → 2026-05-06).

**What this skill does:** Take a corpus of inputs (research artifacts, peer-repo deep-dives, brainstorming outputs) and produce a sequenced backlog of `kind: spinoff-roadmap` stubs that are queryable, dispatchable, and pickup-able through the standard handoff lifecycle. The roadmap is not a plan doc; it's a graph of stubs.

**When to use:** the PM has 5+ candidate work items emerging from research/deep-dive/peer-repo input, and wants them sequenced into sprint-shaped waves with explicit gate dependencies. Single-feature plans use `coordinator:plan`. Architectural decisions use `coordinator:staff-session`. Tactical bug-batch processing uses `coordinator:bug-blitz`. Roadmap-planning sits above plan-shaping — it produces the graph that individual plans live on.

**When NOT to use:** if you just want a single plan doc → `coordinator:plan`. If you want to brainstorm options before committing to a roadmap → `coordinator:brainstorming` first. If you don't have 5+ candidate items in writing → not yet roadmap-shaped; gather more before invoking.

---

## Phase 1 — Synthesize: from input corpus to verdict-grid

**Goal:** every cluster gets a verdict; `we'll see` is rejected by construction. **Closure split:** Phase 1 enforces *cluster → verdict* coverage; Phase 2 Step 2.6 enforces the inverse (*verdict → stub* coverage). Both directions are required to close the brief's ESC-4 escape — a stub without a source cluster passes Phase 1 but fails Step 2.6, and a verdict without a stub passes Step 2.6 but fails Phase 1. Treat the two as halves of one bidirectional gate.

<!-- Review: the Staff Engineer — Phase 1 alone closes ESC-4 from only one direction; the wording made it easy to miss that Step 2.6 enforces the inverse direction (P2-8) -->

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

- **MERGE** — fold into another cluster (name the target cluster).
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

For each KEEP cluster (and each MERGE-target cluster that absorbs a KEEP), dispatch one `general-purpose` Sonnet scout in parallel. Cap at 8 concurrent; chunk if >8 clusters. Each scout's brief uses the verbatim internet-research dispatch language from coordinator CLAUDE.md § Internet Research:

> Use WebSearch and WebFetch directly to find answers and return a structured brief. Do NOT invoke any skills. Do NOT use the Deep Research pipeline. Do NOT spawn agents or teams. Your job is a quick solo web search — 5-10 minutes, a handful of queries, a clear brief back to me.

Plus topic-specific framing:
- Cluster topic + scope (one paragraph the EM authors from `clusters.md`).
- Output path: `state/roadmap/<run-id>/research-corpus/<topic-slug>.md`.
- Required sections: `## Primary sources`, `## Key findings`, `## Open questions`, `## How peer projects have done this` (if applicable).
- Disk-first verification preamble per coordinator CLAUDE.md § Scouts and Disk-First Verification.

EM verifies each file exists and is non-trivial (≥2KB) before proceeding. Inline TEXT-ONLY recoveries per the same wiki section.

**Per-project research material counts as a primary source.** If `docs/wiki/`, `docs/research/`, or peer-repo wikis already cover a cluster, the scout cites those alongside web findings — does not duplicate. The scout decides.

### Step 1.5.2 — OVERVIEW.md draft

EM authors `state/roadmap/<run-id>/OVERVIEW.md`. One section per KEEP cluster. Each section MUST:

- Cite its `research-corpus/<topic-slug>.md` by path.
- Name the proposed architecture in one paragraph (not pseudocode — shape and seams).
- Name **contested decisions** explicitly under a `### Contested` sub-heading — anything where two reasonable engineers would pick differently. Silence here is the failure mode; if a section has no `### Contested` sub-heading, EM has not done the work.
- Name **certain vs. speculative** — what the research grounds, what is EM judgment.
- Cross-reference dependent clusters (forward references to other OVERVIEW sections).

Frontmatter:

```yaml
---
roadmap_id: <run-id>
status: draft           # draft | shape-approved | final-approved
shape_approved_by:      # filled in Step 1.5.4
shape_approved_at:
final_approved_by:      # filled in Step 1.5.6
final_approved_at:
---
```

### Step 1.5.3 — peer-team-asks.md

`state/roadmap/<run-id>/peer-team-asks.md`. Enumerates everything the roadmap needs from peer teams that we cannot deliver ourselves. Motivating case: holodeck engine team — items "behind the wall" (headless extraction at scale/speed, engine-side RAG ingestion hooks, etc.) require their cooperation. Empty file is permitted (must be present) — single bullet `- None identified at authoring time.`

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

Stubs whose `blocked_by` includes a peer-team ask carry `awaiting_gate` + `gate_dependency: peer-team-ask:<ask-slug>` in their frontmatter, set in Phase 2. The gate-meaningfulness audit (Step 3.2) reads this text — keep the slug stable.

### Step 1.5.4 — PM round 1: shape approval (CHEAP RE-DIRECT)

Before reviewers run, surface OVERVIEW.md + peer-team-asks.md to the PM with the framing:

> Phase 1.5 round 1 — shape approval. Reviewers haven't run yet. This is the cheap point to re-direct: if the architectural shape or the set of peer-team asks is wrong, redirecting now costs one EM pass instead of two reviewer integrations + a stub-authoring fan-out. Outputs: `state/roadmap/<run-id>/OVERVIEW.md`, `state/roadmap/<run-id>/peer-team-asks.md`, `state/roadmap/<run-id>/research-corpus/`. Approve to proceed to reviewer dispatch, or redirect.

On PM approval, write `shape_approved_by: PM` and `shape_approved_at: <YYYY-MM-DD>` to OVERVIEW frontmatter and set `status: shape-approved`. On redirect, iterate the OVERVIEW (and re-dispatch any research-corpus topics whose scope changed) and re-surface.

### Step 1.5.5 — the Staff Engineer + domain reviewer (sequential)

Sequential, not parallel (per § Review Sequencing — plan/stub/doc carve-out applies).

1. Dispatch the Staff Engineer against `state/roadmap/<run-id>/` (full dir: OVERVIEW + research-corpus + peer-team-asks + Phase 1 artifacts). Brief: architectural soundness of OVERVIEW; contested-decisions completeness; peer-team-asks scope-appropriateness; whether research-corpus citations actually support the OVERVIEW claims (the citation-load-bearing check). Read-only.
2. Integrate via `coordinator:review-integrator` (mode: acceptEdits).
3. Dispatch domain reviewer — the Game Dev Reviewer if game-dev / UE-flavored, the Data Science Reviewer if data-science / ML-flavored, the Front-End Reviewer if web-front-end flavored. EM picks based on roadmap shape; default the Data Science Reviewer if mixed/unclear (data shapes appear in most roadmaps). Brief: domain coherence, edge cases the OVERVIEW silently elides, premise gaps in research-corpus.
4. Integrate via `coordinator:review-integrator`.

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

**Goal:** every KEEP cluster becomes a `kind: spinoff-roadmap` stub. Stubs are spinoffs by construction (per the lifecycle plan B+H) — they live in `state/handoffs/`, queryable via `bin/query-records --type handoff`.

### Step 2.1 — Stub frontmatter (canonical template)

Per stub:

```yaml
---
title: <one-line>
created: <YYYY-MM-DD>
branch: <current-branch>
status: active
kind: spinoff-roadmap
predecessor: none                 # load-bearing for spinoffs (per docs/wiki/spinoff-handoffs.md)
authoring_session: state/roadmap/<run-id>/   # path-shaped audit trail back to the roadmap run dir; /pickup can Read this deterministically
workstream: <slug>
roadmap_id: <run-id>              # groups all stubs from one roadmap-planning invocation
tc_id: tc-<N>                     # roadmap-local identifier; unique within roadmap_id
sprint: <N>                       # sprint grouping (typically 1–4)
wave: <N>                         # serialization-order grouping within a sprint
cost: <T0|T1|T2|T3>               # estimation tier — T0 trivial, T3 multi-day
deployment_state: awaiting_gate | ready_to_fire
gate_dependency: <one-line>       # iff awaiting_gate (subsystem-named, not file-pathed)
blocks: [tc-X, tc-Y]              # tc-IDs that this stub unblocks when shipped
blocked_by: [tc-Z]                # tc-IDs that must ship first
scope:
  - <pathspec 1>
  - <pathspec 2>
---
```

`authoring_session` is path-shaped (`state/roadmap/<run-id>/`) so `/pickup` can deterministically `Read` origin context. The wiki schema describes this field as a one-line description; for roadmap stubs we narrow it to a directory path (roadmap-specific narrowing; wiki amends if the convention broadens).

**Two schema fields NOT in the template** — they're populated by lifecycle events, not by `roadmap-planning`:

- **`pickup_ready: true`** — defaults to absent for roadmap stubs. Absence triggers a non-blocking warning at `/pickup` time (not a block); the EM proceeds to mutation. `awaiting_gate` + `gate_dependency` is the correct sequencing mechanism for stubs that must not be picked up yet — do not use `pickup_ready` absence as a gate.
- **`shipped_in: <sha-or-PR-ref>`** — never authored by the roadmap-planning skill. Set by `/handoff` or `/workstream-complete` post-execution when the work transitions to `deployment_state: shipped`. `/distill` requires this field present before deleting an archived stub (Phase 4c safety guard).

<!-- Review: the Staff Engineer — authoring_session must be path-shaped so /pickup can Read the origin context deterministically (P1-2); pickup_ready and shipped_in are lifecycle fields not authored here (P2-5) -->

Stubs are written to `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_roadmap-{run-id}-tc-{N}.md` so they appear alongside ad-hoc spinoffs in query-records output but cluster by `roadmap_id` for `/workday-start` reporting (per `commands/workday-start.md` Step 1.1 routing).

**Field semantics — clarifications:**

- **`wave: <N>` is a concurrency-gate primitive, NOT a sprint synonym.** Two distinct shapes:
  - **Wave** = single-dispatch parallel fan-out within a sprint. All wave-N stubs are file-disjoint by construction and dispatch concurrently. Cost profile: one EM-session of dispatch + sync. Risk profile: bounded — failure of one wave-N stub does not invalidate sibling stubs.
  - **Sprint** = multi-session sequence; the time-box across which wave-N → wave-N+1 gating fires. Cost profile: multi-day, multi-session, with `/handoff` between sessions. Risk profile: compound — a sprint-2 architectural finding can invalidate sprint-3 stubs authored against a now-wrong assumption.
  Do NOT use `wave:` for time-boxing or for unit-of-effort grouping; use `sprint:` for that. A roadmap with 20 stubs split as 4 sprints × 5 waves of 1 stub each is using `wave:` wrong — those should be 4 sprints × 1 wave × 5 sequential stubs, OR (if truly parallel) 4 sprints × 1 wave × 5 parallel stubs. See `docs/wiki/spinoff-handoffs.md` § "Wave vs sprint" for the cost/risk breakdown.
- **`gate_dependency:` frontmatter is for HARD gates only.** A hard gate is a precondition that must land before this stub can be dispatched at all — typically a sibling tc-id, a merged PR, or a flipped feature flag. Soft cross-repo seams (advisory coordination cues like "consider coordinating with peer-repo PR-N" or "watch for X downstream") belong in the stub body's `## Notes` section, NOT in machine-read `gate_dependency:` frontmatter. The frontmatter field drives query-records surfacing and `/pickup` gating logic; polluting it with advisory text causes false "still gated" reports.
- **Soft seams declared in body, not frontmatter.** Each stub MUST include a `## Soft seams` section in its body (Step 2.2) enumerating workstreams it may overlap with, advisory cross-repo coordination notes, and any "consider coordinating with X" cues. Format: bulleted list, each entry one line, naming the peer workstream/PR/stub and the nature of the overlap (file-region, schema-shape, timing). The frontmatter `scope:` block remains the HARD declaration (machine-readable, drives `/pickup` safety-commit pathspec); `## Soft seams` is the SOFT declaration (human-readable, drives EM judgment when sequencing parallel waves). See `docs/wiki/spinoff-handoffs.md` § "Soft-seams discipline" for the full rule and rationale.
- **Audit-spike sizing heuristic.** When an audit/spike has exactly one downstream consumer, fold it as Phase 0 of that consumer's implementation stub rather than authoring a standalone audit stub — the audit's output never reaches a second consumer, so the stub overhead is pure ceremony. Standalone audit stubs earn their own tc-id only when ≥2 downstream consumers will read the audit output to define their own behavior. Cross-EM gate-waiting on a single-consumer audit-spike costs more than the leverage it delivers.
- **Stub-dedup canonical = git commit provenance, not the filename timestamp.** When two stubs of the same tc-id exist (e.g. `11xxxx_…_tc-3.md` and `14xxxx_…_tc-3.md`), the canonical is whichever was committed FIRST as a deliberate per-stub commit — NOT whichever has the earlier HHMMSS prefix. Filename timestamps can invert the truth when an HHMMSS-earlier draft gets bulk-committed later than the HHMMSS-later canonical. Determine canonical from `git log -- <each-stub-path>` + the STUB-INDEX + any existing archival precedent (e.g. prior `.DUPLICATE-FROM-BULK-COMMIT.md`-suffixed siblings). When the duplicated pairs are **divergent** (drafts sometimes structurally richer than the canonical — extra sections, more thorough acceptance criteria), the safe dedup is `git mv` to `archive/` with a `.DUPLICATE-FROM-BULK-COMMIT.md` suffix, NOT `git rm` — it preserves draft-only content at zero cost for the eventual implementing EM, who may want the richer draft's text. The 2026-05-23 DroneSim roadmap (each tc-N authored twice via overlapping bulk-commit + per-stub-commit passes) is the empirical case.

### Step 2.2 — Body sections (per stub)

- `# <title>`
- One-paragraph "why this exists as its own session"
- `## What this covers` — origin context, scope.
- `## Reference materials (read first)` — file paths. **MUST cite `state/roadmap/<run-id>/OVERVIEW.md § <cluster-section>`** as the architectural ground truth, AND **MUST cite the relevant `state/roadmap/<run-id>/research-corpus/<topic-slug>.md` files** that the stub's scope leans on. Stubs that introduce architecture not present in OVERVIEW.md are caught in Step 2.8 review as drift — the OVERVIEW is doctrine, the stub is implementation of doctrine.
- `## Specification` — concrete enough that a context-less EM can act.
- `## Acceptance criteria` — binary checklist.
- `## Recommended next steps for the picking-up EM` — 3–7 numbered, each verifiable.
- `## Anti-scope` — what NOT to do.
- `## Soft seams` — bulleted enumeration of workstreams/PRs/stubs this stub may overlap with; one line per seam naming peer + overlap nature. MAY be empty (single bullet: `- None identified at authoring time.`); MUST be present. Distinct from frontmatter `scope:` (HARD pathspec) and `blocked_by:` (HARD graph edge). See `docs/wiki/spinoff-handoffs.md` § "Soft-seams discipline".
- Trailing marker: `<!-- spinoff-roadmap: <run-id> tc-<N> by roadmap-planning -->`

### Step 2.3 — STUB-INDEX as a query callout

Write `state/roadmap/<run-id>/STUB-INDEX.md`:

```markdown
# STUB-INDEX — <run-id>

<!-- BEGIN query: handoff where=roadmap_id=<run-id> sort=sprint -->
(regenerated by /update-docs Phase 11c via bin/refresh-queries.js)
<!-- END query -->
```

NOT a hand-maintained table. The query callout regenerates on every `/update-docs` run, so the index always reflects current frontmatter.

**Single-clause `where=` only inside callouts (dogfood-2026-05-08 finding).** `bin/refresh-queries.js` token-splits the BEGIN marker on whitespace, so a multi-clause where like `where=kind=spinoff-roadmap AND roadmap_id=...` would silently lose every clause after the first space. Single-clause `where=roadmap_id=<run-id>` is sufficient because the cross-field validator (`bin/lib/schema.js` CROSS_FIELD_RULES.handoff) enforces `roadmap_id` ⇒ `kind: spinoff-roadmap` — the kind clause is redundant. **Multi-condition queries from the CLI work fine** (`--where "X AND Y"` in shell quotes); the limitation is callout-only. Future enhancement candidate: extend `refresh-queries.js` to accept quoted multi-clause where; tracked in the improvement queue.

### Step 2.4 — Constraint graph (machine-readable in frontmatter)

`blocks` and `blocked_by` arrays in each stub's frontmatter ARE the graph. To visualize:

```bash
"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type handoff --where "kind=spinoff-roadmap AND roadmap_id=<run-id>" --format json | <graphviz-script>
```

Wave order auto-derives from topological sort over `blocked_by`. If you find yourself hand-maintaining a wave-order table, stop — you've recreated the brief's failure mode (siblings, not subsets).

**`sort=sprint` reminder:** `query-records.js` sorts by frontmatter field name; `sprint` is a roadmap-stub frontmatter field, so the callout's `sort=sprint` IS valid syntactically. But the dogfood-2026-05-08 run could not confirm sprint-sort actually executed (the test corpus had no multi-sprint variation). On the next multi-sprint roadmap run, verify sort ordering against expected sprint sequence; if it sorts by `created` instead, file an improvement-queue entry.

**Pre-derive the design graph BEFORE any fan-out (hard gate).** The wave order is a *derived* artifact — topologically sorted over `blocked_by` — not an assumption the dispatching EM makes by reading sprint numbers. Before Phase 3 dispatch fans out any wave, run the derivation and verify it:

```bash
"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type handoff --where "roadmap_id=<run-id>" --format json
```

Confirm: (1) every stub's `blocks`/`blocked_by` edges reference tc-ids that exist in this `roadmap_id`; (2) the graph is acyclic (a cycle means the topology cannot produce a wave order — fix the edges before dispatch); (3) every wave-N stub set is file-disjoint per its `scope:` blocks (the file-overlap gate per coordinator CLAUDE.md § Pre-Dispatch Verification — overlap is the one unconditional serial gate). A fan-out dispatched against an unverified or cyclic graph is the "siblings, not subsets" failure the skill exists to prevent, now in execution form: executors collide on shared files or block on edges that were never real. The derivation is cheap (one query + a cycle check); skipping it costs an aborted wave.

### Step 2.5 — `pm-gates.md` enumeration (brief recommendation E)

Phase 2 forces explicit enumeration of every product-coupled question. Write `state/roadmap/<run-id>/pm-gates.md`:

```markdown
# PM Gates — <run-id>

| sprint | tc_id | gate question | disposition format | resolved? |
|---|---|---|---|---|
| 2 | tc-15 | should consumer_runner emit retry telemetry by default? | yes/no/defer | pending |
```

**Detection rule for "product-coupled":** during Phase 2 stub authoring, scan each stub's `gate_dependency:` text for any of: explicit `PM `-prefixed strings, named-stakeholder references, `decision needed` / `approval needed` / `policy` / `scope` / `user-facing` tokens. Each hit becomes a row in `pm-gates.md`. Author can add rows manually for product-coupled questions whose `gate_dependency:` text doesn't trip the detector.

**Manual audit at Phase 2 close (cross-file; `bin/lint-frontmatter.js` cannot do cross-file validation):** for every stub with `gate_dependency:` starting `PM `, confirm an entry exists in `pm-gates.md` (`tc_id` column). For every row in `pm-gates.md` with `resolved? = pending`, confirm at least one stub references it via `gate_dependency:` text. Mismatch blocks Phase 3 entry. Automation candidate post-dogfood: a `audit-roadmap.sh <run-id>` script that runs all Phase 2 cross-file checks.

### Step 2.6 — Stub-coverage audit (brief recommendation G)

Cross-check at Phase 2 close:

```
count(MERGE + KEEP verdicts in reconciliation.md)  ==  count(stubs on disk in state/handoffs/ with this run's roadmap_id)
```

(DROP / DEFER / MOVE verdicts do NOT produce stubs by definition; only MERGE + KEEP do.)

Mismatch BLOCKS Phase 3 entry. Surface to PM with the diff: which clusters lack stubs, which stubs lack source clusters. This would have caught ESC-4 in the project-rag episode (6 stubs shipped without source clusters).

### Step 2.7 — `kind: spinoff-roadmap` tripwire (brief recommendation H)

Validator rules (added to `bin/lint-frontmatter.js` cross-field rules):
- Any handoff with `roadmap_id:` MUST have `kind: spinoff-roadmap`.
- Any `kind: spinoff-roadmap` MUST have `roadmap_id:` AND `blocks` AND `blocked_by` AND `wave: <integer>` AND `tc_id:` non-empty.
- `tc_id:` MUST be unique within a `roadmap_id:`.
- At most one `ready_to_fire` per `(roadmap_id, wave)` pair across the active set.
- **`cost` if present MUST be one of T0/T1/T2/T3.** A separate cross-field rule in `bin/lint-frontmatter.js` enforces this (added alongside the kind:spinoff-roadmap rules). A stub with `cost: "very large"` is rejected at lint time.

<!-- Review: the Staff Engineer — cost is a documented enum but was missing from validator surface; a stub with free-text cost would pass lint silently (P2-4) -->

Prevents the brief's "siblings, not subsets" failure mode — stubs cannot exist outside a roadmap parent, and roadmap parents cannot exist without graph primitives.

### Step 2.8 — the Staff Engineer then the Data Science Reviewer review (sequential, mandatory)

<!-- Review: the Staff Engineer — parallel review stretches the merge-gate carve-out which explicitly excludes plan/stub/doc review; sequential is the correct doctrine-compliant shape here (P1-3) -->

**Sequential, not parallel** (merge-gate parallel carve-out explicitly excludes plan/stub/doc review — a roadmap stub set is plan/stub/doc-shaped).

Sequence:
1. Dispatch the Staff Engineer with the full `state/roadmap/<run-id>/` directory + all stubs. Brief: schema/architecture/sequencing review of the stub set; flag P0 conflicts, missing AC surface, scope errors, sequencing bugs in the constraint graph. Read-only.
2. Integrate the Staff Engineer's findings via `coordinator:review-integrator` (mode: acceptEdits). EM spot-checks the diff.
3. Dispatch the Data Science Reviewer with the same directory. Brief: domain coherence + data shapes; flag clusters whose stubs would compose poorly, premise gaps, edge cases the stub set silently elides. Read-only.
4. Integrate the Data Science Reviewer's findings via `coordinator:review-integrator`.

The latency cost is acceptable: fires once per roadmap, the Data Science Reviewer benefits from the Staff Engineer's integrated changes, and the sequential rule holds across all plan-shaped review.

### Phase 2 entry gate (NEW — gates on Phase 1.5)

Before Phase 2 begins:
- [ ] `state/roadmap/<run-id>/OVERVIEW.md` frontmatter shows `status: final-approved` with both `shape_approved_by: PM` and `final_approved_by: PM` populated.
- [ ] Phase 1.5 exit gate fully checked.

If either fails: STOP and return to Phase 1.5. Authoring stubs against an unapproved OVERVIEW is exactly the failure mode this skill version (1.1.0) was introduced to close.

### Phase 2 exit gate

Before Phase 3:
- [ ] Every KEEP cluster has a stub on disk.
- [ ] Every stub's `## Reference materials` cites `OVERVIEW.md § <cluster>` AND at least one `research-corpus/` file.
- [ ] Every stub has the canonical frontmatter (validator clean).
- [ ] STUB-INDEX query callout regenerates correctly.
- [ ] COORDINATOR-RESOLUTIONS exists for every conflict.
- [ ] `pm-gates.md` enumerates every PM-gate; each is cross-referenced in stub frontmatter.
- [ ] Stub-coverage audit passes (MERGE+KEEP count matches stub count).
- [ ] Every stub has a `## Soft seams` section (may be empty with `- None identified`, must be present per Step 2.2).
- [ ] `kind: spinoff-roadmap` validator clean across all stubs.
- [ ] the Staff Engineer+the Data Science Reviewer review integrated.
- [ ] Design graph derived and verified: `blocks`/`blocked_by` edges all resolve, graph is acyclic, every wave-N set is file-disjoint by `scope:`. (Pre-fan-out gate per Step 2.4.)

---

## Phase 3 — Dispatch: mise-en-place run + end-of-run review

**Goal:** sprint-by-sprint execution; gates clear between sprints; one Sonnet batch review at the end (not per-wave Opus, per the brief's empirical finding).

### Step 3.1 — Sprint loop

For each sprint in `sprint` order:

1. Run `/mise-en-place` on the sprint's stubs (filtered by `query-records --type handoff --where "roadmap_id=<run-id> AND sprint=<N> AND deployment_state=ready_to_fire"`).
2. After mise completes, the `awaiting_gate` stubs in the next sprint may be ready to transition to `ready_to_fire`. **Do NOT auto-transition.** The `/handoff` or `/workstream-complete` of the sprint's executor sessions transitions individual stubs as their gate clears — and at each transition, the gate-meaningfulness audit (Step 3.2) fires.

### Step 3.2 — Gate-meaningfulness audit (brief recommendation F)

Implementation surface: `/handoff` and `/workstream-complete` fire the audit when they would write `deployment_state: ready_to_fire` over an existing `awaiting_gate` value. NOT from `/pickup` — pickup transitions to `in_flight`, not `ready_to_fire`. The audit hooks the *unblock* event.

**Detection:** read prior frontmatter from git (`git show HEAD:state/handoffs/<file>`); if the prior `deployment_state` was `awaiting_gate` and the new value is `ready_to_fire`, emit:

```
The gate that blocked this stub was:
  <gate_dependency text from prior frontmatter>

Does that gate still mean what it meant when authored? (y/n/clarify)
```

- `y` → transition proceeds.
- `n` → stub returns to `awaiting_gate`; author updates `gate_dependency` to reflect what's actually now blocking.
- `clarify` → PM disposition required before transition.

Would have caught ESC-5 (G1 went structurally hollow when synthetic-baseline acceptance changed its meaning).

**Idempotency under concurrent-EM operation:** the audit triggers only on the `awaiting_gate → ready_to_fire` edge, observed via `git show HEAD:<file>` against the file's current state. If a concurrent EM already transitioned the stub, the second EM's check reads `ready_to_fire` as the prior state and the audit skips silently — no double-prompt, no race window where neither EM fires the audit. Two concurrent EMs both attempting the unblock: whichever's commit lands first owns the audit; the second EM's `git show` sees the post-first-EM state and treats the transition as already-done.

<!-- Review: the Staff Engineer — concurrent-EM race on gate-meaningfulness audit was undocumented; idempotency via git show HEAD: closes the ordering hazard (P2-9) -->

### Step 3.3 — End-of-run review

After all sprints complete, dispatch ONE Sonnet review across the whole roadmap output. NOT per-wave Opus (empirical finding: end-of-run Sonnet beat per-wave Opus on cost without meaningful signal loss). Brief: "Cross-cutting review of <run-id> roadmap execution. Flag any drift from stubs, missing acceptance criteria, deferred items that should have been fixed in-session." Integrate via `coordinator:review-integrator`. Surface escalations (ESC-N format) to PM.

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
- `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_roadmap-{run-id}-tc-{N}.md` × N — Phase 2 stubs (one per KEEP / MERGE-target cluster)

Stubs live alongside ad-hoc spinoffs and continuation handoffs; `roadmap_id:` clusters them. `/workstream-start`, `/workday-start`, `/pickup` light up automatically — no second-class artifact.

---

## Contact-points checklist

- **`/handoff` and `/spinoff` durability rules apply with extra force to roadmap stubs.** `gate_dependency:` MUST be subsystem-named (e.g., `consumer_runner retry telemetry policy`), never file-pathed (e.g., `state/handoffs/2026-05-08_foo.md ships`). Step 3.2's gate-meaningfulness audit reads this text from git history via `git show HEAD:<file>`; a file-pathed dependency goes stale on archive-to-`archive/handoffs/` and breaks the audit prompt by displaying a dangling reference. The picking-up EM editing a roadmap stub's frontmatter must respect this; a v1 lint extension catches `gate_dependency:` text containing path-fragments (e.g., `tasks/`, `archive/`, `*.md`) and warns.

<!-- Review: the Staff Engineer — gate_dependency text durability is more load-bearing for roadmap stubs because Step 3.2 reads it from git history; file-pathed values go stale on archive-move (P2-7) -->

- **`/repo-setup`** — verify roadmap-planning is mentioned in the orientation flow when the project tracker contains roadmap entries.
- **`/workstream-start`** — query callout already covers `kind: spinoff-roadmap` via the universal `deployment_state=ready_to_fire` filter.
- **`/workstream-complete`** — verifies workstream-complete's plan-doc update step covers roadmap stubs (no special-case logic; they're spinoffs).
- **`/workday-start`** — Step 1.1 routing groups `kind: spinoff-roadmap` with spinoffs and clusters by `roadmap_id` when count > 3 per group.
- **Hooks:** `hooks/scripts/session-init.sh` provides a boot-time quiet sweep: consumed handoffs whose authoring session is dead are silently archived to `archive/handoffs/`. Covers orphaned roadmap stubs without roadmap-specific hook logic.
- **Canonical artifact:** roadmap stubs themselves are the artifact agents will encounter. The `kind:` enum and frontmatter schema make them discoverable via `bin/query-records --list-schemas` and `bin/lint-frontmatter --list-schemas`.

---

## Anti-scope (what this skill does NOT do)

- Auto-derive `gate_dependency:` text from natural language. Author-supplied only.
- Cross-repo roadmap rollup. Single-repo only for v1.
- Auto-trigger gate-meaningfulness on `/pickup` (only on `awaiting_gate → ready_to_fire` transitions, which are `/handoff` and `/workstream-complete` events).
- Render dashboards or HTML. The query callout in markdown is the surface.
- **Replace `coordinator:plan` for single-plan work.** If a roadmap stub itself becomes the basis for a `coordinator:plan` invocation, that's a downstream plan in the same workstream — NOT a continuation of the stub. The picking-up EM running `coordinator:plan` against a stub:
  - keeps the stub's `deployment_state: in_flight` (set by `/pickup` at archival time),
  - writes the resulting plan-doc with `predecessor: none` (the plan is forked, not continued),
  - documents the lineage in the plan-doc body's "Why this plan" section, citing the stub's `roadmap_id/tc_id` (e.g., "originating roadmap stub: `dogfood-2026-05-08/tc-3`").

  A future schema extension may add a `roadmap_parent:` field to plan-doc frontmatter for machine-readable lineage; that's deferred until a second instance of plan-from-stub demonstrates the textual citation pattern is insufficient for retrieval. PM disposition required to add the field.

<!-- Review: the Staff Engineer — anti-scope was silent on lineage when a stub becomes the basis for a coordinator:plan invocation; without this, /distill loses provenance trail (P2-6) -->

---

## See also

- `docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` — spec
- `archive/specs/2026-05-08-roadmap-planning-skill-brief.md` — empirical motivator (project-rag retrospective)
- `docs/wiki/spinoff-handoffs.md` — cohort wiki: frontmatter conventions (predecessor: none), deployment_state lifecycle for spinoffs, soft-seams discipline, awaiting_gate aging, pickup-side premise check.
- `commands/distill.md` — extracts knowledge from completed roadmap stubs
- `coordinator:plan` — for single-plan work downstream of a roadmap stub
- `coordinator:brainstorming` — for pre-roadmap option exploration
