---
name: roadmap-planning
description-budget: 400
description: PM-GATED. Roadmap shaping from research/deep-dive/peer-repo inputs via Synthesize → Substantiate → Plan → Dispatch pipeline producing kind:spinoff-roadmap stubs with deployment_state, blocks/blocked_by graph, machine-readable STUB-INDEX. Stubs cite PM-approved OVERVIEW + research corpus, not EM hand-waving. Triggers — "shape a roadmap", "plan a sprint sequence from this research".
version: 1.3.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "<input-corpus-path|problem-set-path|spinoff-roadmap-creator-stub-path> [--run-id <slug>]"
---

# Roadmap Planning — From Inputs to Sequenced Spinoff Stubs

> **Spec backlink:** `archive/specs/2026-05/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` § Phase 5. Empirical motivator: `archive/specs/2026-05-08-roadmap-planning-skill-brief.md` (project-rag cross-deep-dive-synthesis episode, 2026-05-03 → 2026-05-06).

**What this skill does:** Take a corpus of inputs (research artifacts, peer-repo deep-dives, brainstorming outputs, or a ratified problem-set) and produce a sequenced backlog of `kind: spinoff-roadmap` stubs that are queryable, dispatchable, and pickup-able through the standard handoff lifecycle. The roadmap is not a plan doc; it's a graph of stubs.

**When to use:** the PM has 5+ candidate work items emerging from research/deep-dive/peer-repo input, and wants them sequenced into sprint-shaped waves with explicit gate dependencies. Single-feature plans use `coordinator:plan`. Architectural decisions use `coordinator:staff-session`. Tactical bug-batch processing uses `coordinator:bug-blitz`. Roadmap-planning sits above plan-shaping — it produces the graph that individual plans live on.

**When NOT to use:** if you just want a single plan doc → `coordinator:plan`. If you want to brainstorm options before committing to a roadmap → `coordinator:brainstorming` first. If you don't have 5+ candidate items in writing → not yet roadmap-shaped; gather more before invoking. **Exception — goal-seeded (spinoff-roadmap-creator pickup) path:** when this skill is triggered by actioning a `kind: spinoff-roadmap-creator` stub (see Entry Point B below), a single stub represents one discrete roadmap-worth-of-work as already scoped by the upstream goal-setting session; the 5+ items precondition does NOT apply to this entry point. The roadmap-creator stub's `authoring_session` contains the upstream context that was used to scope the roadmap's boundaries.

---

## Entry points

### Entry Point A — Direct invocation (research / deep-dive corpus)

The classic path. PM arrives with a corpus of research artifacts, peer-repo deep-dives, or brainstorming outputs and wants them sequenced into a backlog. Begin at Phase 1 (Synthesize).

**Input:** `<input-corpus-path>` — a directory of research files, deep-dive outputs, or brainstorming artifacts.

### Entry Point B — Pickup from `kind: spinoff-roadmap-creator` stub (goal-seeded)

When a `kind: spinoff-roadmap-creator` stub is actioned via `/pickup`, the stub's `authoring_session` path contains the goal-setting context that spawned it (the goal artifact, upstream problem-set, and any KRs the goal-setting session produced). The stub represents a pre-scoped slice of work whose roadmap boundaries were already ratified during goal-setting.

**On pickup:**
1. Read the stub's `authoring_session` path to load upstream context (goal artifact, problem-set, initiative).
2. Use the stub body's scope description as the Phase 1 cluster seed — the stub is the single cluster that was already scoped; Phase 1 Synthesize refines it into sub-clusters.
3. Set `run-id` from the stub's `stub_id` (e.g. a stub `spinoff-roadmap-creator` with `stub_id: rc-04` → `run-id: rc-04`).
4. The 5+ items precondition does NOT apply — a single roadmap-creator stub is a valid entry even if it describes a narrowly scoped roadmap.
5. Proceed to Phase 1 (Synthesize) with the stub's scope as the input corpus anchor, then continue the normal pipeline.

**Stub lifecycle:** set `deployment_state: in_flight` on the spinoff-roadmap-creator stub when Phase 1 begins; set `deployment_state: shipped` (via the normal `/workstream-complete` path) when Phase 2 completes and the resulting spinoff-roadmap stubs are committed.

### Entry Point C — Chain from `/shape` (ratified problem-set, `estimated_horizon: week`)

When `/shape` ratifies a problem-set whose `estimated_horizon` field is `week`, it routes here instead of `coordinator:plan`. The ratified problem-set (`docs/problems/<slug>.md`) is the oracle that replaces the research corpus as the cluster seed.

**On chain-from-shape:**
1. The ratified problem-set (`docs/problems/<slug>.md`) arrives as the `<input-corpus-path>` argument (or is cited explicitly in the invocation).
2. Treat each problem listed under `## Problems` in the problem-set as a provisional cluster for Phase 1 Step 1.2. The problem-set's `## Out of scope` block pre-populates DROP verdicts.
3. Phase 1.5 research corpus still applies — each KEEP cluster still needs a research-corpus scout to ground the OVERVIEW in primary sources, not just the problem-set prose.
4. The plan's frontmatter inherits the problem-set reference: `problem_set: docs/problems/<slug>.md`.
5. The 5+ items precondition applies to this path — if the problem-set has fewer than 5 items, the work is likely plan-shaped, not roadmap-shaped; confirm with the PM before proceeding (the `/shape` router routes here because `estimated_horizon: week` was set at ratification — the 5+ items check is this skill's own precondition, not a `/shape` filter; if the problem-set is genuinely week-sized but shallow, it may warrant a single `coordinator:plan` call instead). <!-- Review: code-reviewer F11 — clarified ownership boundary: /shape routes on horizon field, 5-item check belongs to roadmap-planning -->

**Routing note (from `/shape`):** `/shape` sets `estimated_horizon: week` on the problem-set frontmatter at ratification. The EM confirms the routing at the fork (detect-then-confirm, never silent guess) before invoking this skill. See `coordinator/skills/shape/SKILL.md § Transition` for the router's outbound logic.

---

## Ceremony ladder — each rung spawns the next

`/roadmap-planning` is the second rung of the ceremony ladder:

```
/goal-setting  →  spawns  kind: spinoff-roadmap-creator  stubs (one per roadmap-worth-of-work)
/roadmap-planning  →  spawns  kind: spinoff-roadmap  plan-seed stubs (one per KEEP cluster)
coordinator:plan  →  authors  plan-doc  (dispatcher for a single spinoff-roadmap stub)
execute-plan  →  dispatches  executor chunks  (the typed work inside a plan)
```

**The spawn edge at this rung (Phase 2, Step 2.1):** every KEEP cluster in Phase 2 becomes a `kind: spinoff-roadmap` stub authored by `coordinator-doc-new --type spinoff-roadmap`. These stubs are the feed for the next rung — a future EM picks one up via `/pickup`, runs `coordinator:plan` against its scope, and the resulting plan-doc becomes the work authorization for executor chunks. The anti-scope section below formalizes the seam: `/roadmap-planning` does NOT invoke `coordinator:plan`; it only authors the stubs that a downstream `coordinator:plan` invocation will consume. The ladder is legible — each rung authors the artifacts that feed the rung below.

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

Stubs whose `blocked_by` includes a peer-team ask carry `awaiting_gate` + `gate_dependency: peer-team-ask:<ask-slug>` in their frontmatter, set in Phase 2. The gate-meaningfulness audit (Step 3.2) reads this text — keep the slug stable.

### Step 1.5.4 — PM round 1: shape approval (CHEAP RE-DIRECT)

Before reviewers run, surface OVERVIEW.md + peer-team-asks.md to the PM with the framing:

> Phase 1.5 round 1 — shape approval. Reviewers haven't run yet. This is the cheap point to re-direct: if the architectural shape or the set of peer-team asks is wrong, redirecting now costs one EM pass instead of two reviewer integrations + a stub-authoring fan-out. Outputs: `state/roadmap/<run-id>/OVERVIEW.md`, `state/roadmap/<run-id>/peer-team-asks.md`, `state/roadmap/<run-id>/research-corpus/`. Approve to proceed to reviewer dispatch, or redirect.

On PM approval, write `shape_approved_by: PM` and `shape_approved_at: <YYYY-MM-DD>` to OVERVIEW frontmatter and set `status: shape-approved`. On redirect, iterate the OVERVIEW (and re-dispatch any research-corpus topics whose scope changed) and re-surface.

### Step 1.5.5 — Primary rigor reviewer + domain reviewer (sequential)

Sequential, not parallel (per § Review Sequencing — plan/stub/doc carve-out applies). **Primary rigor-reviewer selection follows the same altitude rule as Step 2.8** — the Director of Engineering (`coordinator:eng-director`, standalone primary) when the roadmap sets cross-repo/cross-team boundaries (peer-team-asks cross-repo ask / ≥2-repo scope / sibling-consumed contract / cross-repo COORDINATOR-RESOLUTION); else the Staff Engineer (`coordinator:staff-eng`).

**Persist the persona verdict — reviewer self-persists; EM reads the returned path.** Persona reviewers (the Staff Engineer, the Director of Engineering, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer) self-persist their findings to `state/review-trail/findings/` when the skill appends the `snippets/findings-self-persist-sentinel.md` protocol to the brief. No EM pre-scaffold. The reviewer scaffolds its own sidecar via `coordinator-doc-new --type review-findings`, writes its `ReviewOutput` there, and returns: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. Read that path for integrator dispatch. **Multi-reviewer chain:** the domain reviewer (step 3) is dispatched with the same snippet appended; each reviewer scaffolds its own sidecar path. Spec backlink: `cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md`.

1. Dispatch the **primary rigor reviewer** (the Director of Engineering or the Staff Engineer per the altitude rule) against `state/roadmap/<run-id>/` (full dir: OVERVIEW + research-corpus + peer-team-asks + Phase 1 artifacts). Brief: architectural soundness of OVERVIEW; contested-decisions completeness; peer-team-asks scope-appropriateness; whether research-corpus citations actually support the OVERVIEW claims (the citation-load-bearing check). When the Director of Engineering is primary, add the cross-repo-boundary lens (is the boundary drawn correctly; does the OVERVIEW assume authority over a sibling repo it shouldn't). Read-only. **Inject** the `docs/plans/<run-id>.review.md` sidecar path; instruct the reviewer to self-persist as their final action.
2. Integrate via `coordinator:review-integrator` (mode: auto) pointing at the on-disk sidecar (`docs/plans/<run-id>.review.md`) — not an inline finding list.
3. Dispatch domain reviewer — the Game Dev Reviewer if game-dev / UE-flavored, the Data Science Reviewer if data-science / ML-flavored, the Front-End Reviewer if web-front-end flavored. EM picks based on roadmap shape; default the Data Science Reviewer if mixed/unclear (data shapes appear in most roadmaps). Brief: domain coherence, edge cases the OVERVIEW silently elides, premise gaps in research-corpus. **Inject** the existing `docs/plans/<run-id>.review.md` sidecar path; instruct the reviewer to append their section as their final action.
4. Integrate via `coordinator:review-integrator` pointing at the on-disk sidecar (`docs/plans/<run-id>.review.md`).

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

### Step 2.1 — Stub frontmatter (scaffold via coordinator-doc-new, then fill)

Per stub, scaffold first, then fill computed graph values:

```bash
coordinator-doc-new --type spinoff-roadmap \
    --title "<stub title>" \
    --roadmap-id <run-id> \
    --stub-id <slug>-<N> \
    --out state/handoffs/<date>_<HHMMSS>_roadmap-<slug>-<N>.md
```

**Deliverable-spine threading (D1, C3d).** Each `spinoff-roadmap` stub is the *earliest artifact* for its deliverable and owns the identity (D1 design decision). The `deliverable_id` for a roadmap stub is `dlv-<stub_id>` — derived mechanically from the `stub_id` the scaffolding command already assigns. After scaffolding, set this in frontmatter:

```bash
# C3d — deliverable_id for roadmap stubs (D1: reuse stub identity, never mint separately)
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
STUB_DLVR_ID=$(bash "${_cc_root}/bin/mint-deliverable-id.sh" --stub-id "<slug>-<N>")
# logs "mint-from-stub path — minted: dlv-<slug>-<N>" to stderr
# Set in stub frontmatter: deliverable_id: $STUB_DLVR_ID
```

This id is the durable join key for the deliverable: every plan or handoff authored *against* this stub inherits it via the C3d auto-inheritance rules in `skills/handoff` and `skills/spinoff` — no manual carry is required by the picking-up EM. Set `initiative:` in the stub frontmatter when this roadmap belongs to a known initiative (nullable FK; use the initiative id from `state/initiatives/<id>.yaml`).

This emits schema-valid frontmatter (all required fields present, placeholders for
graph values). After scaffolding, fill the computed fields from the `roadmap-number-stubs.js`
topo output (Step 2.1.5) and write the body (Step 2.2):

- `sprint:` — sprint grouping from topo linearization
- `wave:` — concurrency-gate index within sprint (depth + 1 for single-sprint roadmaps)
- `cost:` — T0|T1|T2|T3 estimation tier
- `blocks:` and `blocked_by:` — graph edges from the DAG
- `gate_dependency:` — subsystem-named hard gate (required when `deployment_state: awaiting_gate`)
- `scope:` — in-scope pathspecs (git pathspec syntax)
- `workstream:` — roadmap short prefix slug

The scaffolded frontmatter schema (for reference; do not hand-author):

```yaml
---
title: <one-line>
created: <YYYY-MM-DD>
branch: <current-branch>
status: active
predecessor: none                 # load-bearing for spinoffs (per docs/wiki/spinoff-handoffs.md)
kind: spinoff-roadmap
roadmap_id: <run-id>              # groups all stubs from one roadmap-planning invocation
stub_id: <slug>-<NN>              # globally-unique stub code; <slug> is this roadmap's short prefix, <NN> the zero-padded integer (min two digits, e.g. 04, 12)
deliverable_id: dlv-<slug>-<NN>  # C3d — durable join key; set to dlv-<stub_id> via mint-deliverable-id.sh --stub-id (D1 reuse-stub-identity path)
initiative: null                  # nullable FK to state/initiatives/<id>.yaml; set when this roadmap belongs to a named initiative
origin_session: <UUID | null>     # originating session UUID ($CLAUDE_CODE_SESSION_ID → .git/coordinator-sessions/.current-session-id); null if unavailable
origin_handoff: <path | null>     # active pickup baton path at stub-authoring time (state/handoffs/…); null if no active baton
origin_plan_id: <pln-… | null>   # pln-… id of the plan under execution at authoring time; null if not executing under a plan
origin_goal_id: <["goal-…"] | null>  # array of goal-… ids this roadmap stub serves; null if no goal context; array even for a single goal
authoring_session: state/roadmap/<run-id>/   # path-shaped audit trail back to the roadmap run dir; /pickup can Read this deterministically
workstream: <slug>
sprint: <N>                       # sprint grouping (typically 1–4)
wave: <N>                         # serialization-order grouping within a sprint
cost: <T0|T1|T2|T3>               # estimation tier — T0 trivial, T3 multi-day
deployment_state: awaiting_gate | ready_to_fire
gate_dependency: <one-line>       # iff awaiting_gate (subsystem-named, not file-pathed)
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

- **`pickup_ready: true`** — defaults to absent for roadmap stubs. Absence triggers a non-blocking warning at `/pickup` time (not a block); the EM proceeds to mutation. `awaiting_gate` + `gate_dependency` is the correct sequencing mechanism for stubs that must not be picked up yet — do not use `pickup_ready` absence as a gate.
- **`shipped_in: <sha-or-PR-ref>`** — never authored by the roadmap-planning skill. Set by `/handoff` or `/workstream-complete` post-execution when the work transitions to `deployment_state: shipped`. `/distill` requires this field present before deleting an archived stub (Phase 4c safety guard).

<!-- Review: the Staff Engineer — authoring_session must be path-shaped so /pickup can Read the origin context deterministically (P1-2); pickup_ready and shipped_in are lifecycle fields not authored here (P2-5) -->

**Origin-provenance fields — fill at stub-authoring time.** Resolve each field from live session context when writing the stub; these are the cheapest to capture correctly and impossible to reconstruct an hour later:

- **`origin_session:`** — `$CLAUDE_CODE_SESSION_ID` if set in the environment; else `cat .git/coordinator-sessions/.current-session-id 2>/dev/null`. A global UUID (no prefix). Emit explicit `null` when neither source is available. Scalar.
- **`origin_handoff:`** — the path of the active pickup baton this session was opened with (e.g. `state/handoffs/2026-07-04_…_topic.md`). Emit explicit `null` if this session has no active baton. Scalar.
- **`origin_plan_id:`** — the `pln-…` id of the plan under execution at roadmap-authoring time, if any. Emit explicit `null` otherwise. Scalar.
- **`origin_goal_id:`** — an **array** of `goal-…` ids (kebab-case slug, `goal-` prefix) for the goal(s) this roadmap serves. Emit explicit `null` when no goal context is active. **Array even for a single goal** (multi-goal roadmaps are a documented real case — a roadmap serving multiple goals maps many-to-many).

> **Origin-provenance axis — distinct from `predecessor`:** `origin_*` records *where this stub was spawned from* (session, baton, plan, goal). This is a DISTINCT axis from `predecessor` (continuation spine — always `none` for spinoff kinds), `forked_from` (branch-point ancestry, a handoff-path), and `deliverable_id` (the `dlv-` grouping key). Never encode origin provenance in `predecessor:`.
>
> **Interim producer note:** this SKILL-side capture is the **interim producer**. example-orchestration-hub's `handoff.author_fork` op will absorb it: when that op ships, the skill calls the op rather than hand-writing the four `origin_*` fields. Do NOT build a parallel auto-populator here — this is documentation-level frontmatter-fill guidance. Once `handoff.author_fork` ships, the manual field-fill guidance at this step will be superseded by the op call.

Stubs are written to `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_roadmap-{stub_id}.md` (i.e. `..._roadmap-<slug>-<NN>.md`) so they appear alongside ad-hoc spinoffs in query-records output but cluster by `roadmap_id` for `/workday-start` reporting (per `commands/workday-start.md` Step 1.1 routing).

**Field semantics — clarifications:**

- **`wave: <N>` is a concurrency-gate primitive, NOT a sprint synonym.** Two distinct shapes:
  - **Wave** = single-dispatch parallel fan-out within a sprint. All wave-N stubs are file-disjoint by construction and dispatch concurrently. Cost profile: one EM-session of dispatch + sync. Risk profile: bounded — failure of one wave-N stub does not invalidate sibling stubs.
  - **Sprint** = multi-session sequence; the time-box across which wave-N → wave-N+1 gating fires. Cost profile: multi-day, multi-session, with `/handoff` between sessions. Risk profile: compound — a sprint-2 architectural finding can invalidate sprint-3 stubs authored against a now-wrong assumption.
  Do NOT use `wave:` for time-boxing or for unit-of-effort grouping; use `sprint:` for that. A roadmap with 20 stubs split as 4 sprints × 5 waves of 1 stub each is using `wave:` wrong — those should be 4 sprints × 1 wave × 5 sequential stubs, OR (if truly parallel) 4 sprints × 1 wave × 5 parallel stubs. See `docs/wiki/spinoff-handoffs.md` § "Wave vs sprint" for the cost/risk breakdown.
- **`gate_dependency:` frontmatter is for HARD gates only.** A hard gate is a precondition that must land before this stub can be dispatched at all — typically a sibling stub_id, a merged PR, or a flipped feature flag. Soft cross-repo seams (advisory coordination cues like "consider coordinating with peer-repo PR-N" or "watch for X downstream") belong in the stub body's `## Notes` section, NOT in machine-read `gate_dependency:` frontmatter. The frontmatter field drives query-records surfacing and `/pickup` gating logic; polluting it with advisory text causes false "still gated" reports.
- **Soft seams declared in body, not frontmatter.** Each stub MUST include a `## Soft seams` section in its body (Step 2.2) enumerating workstreams it may overlap with, advisory cross-repo coordination notes, and any "consider coordinating with X" cues. Format: bulleted list, each entry one line, naming the peer workstream/PR/stub and the nature of the overlap (file-region, schema-shape, timing). The frontmatter `scope:` block remains the HARD declaration (machine-readable, drives `/pickup` safety-commit pathspec); `## Soft seams` is the SOFT declaration (human-readable, drives EM judgment when sequencing parallel waves). See `docs/wiki/spinoff-handoffs.md` § "Soft-seams discipline" for the full rule and rationale.
- **Audit-spike sizing heuristic.** When an audit/spike has exactly one downstream consumer, fold it as Phase 0 of that consumer's implementation stub rather than authoring a standalone audit stub — the audit's output never reaches a second consumer, so the stub overhead is pure ceremony. Standalone audit stubs earn their own stub_id only when ≥2 downstream consumers will read the audit output to define their own behavior. Cross-EM gate-waiting on a single-consumer audit-spike costs more than the leverage it delivers.
- **Stub-dedup canonical = git commit provenance, not the filename timestamp.** When two stubs of the same stub_id exist (e.g. `11xxxx_…_<slug>-3.md` and `14xxxx_…_<slug>-3.md`), the canonical is whichever was committed FIRST as a deliberate per-stub commit — NOT whichever has the earlier HHMMSS prefix. Filename timestamps can invert the truth when an HHMMSS-earlier draft gets bulk-committed later than the HHMMSS-later canonical. Determine canonical from `git log -- <each-stub-path>` + the STUB-INDEX + any existing archival precedent (e.g. prior `.DUPLICATE-FROM-BULK-COMMIT.md`-suffixed siblings). When the duplicated pairs are **divergent** (drafts sometimes structurally richer than the canonical — extra sections, more thorough acceptance criteria), the safe dedup is `git mv` to `archive/` with a `.DUPLICATE-FROM-BULK-COMMIT.md` suffix, NOT `git rm` — it preserves draft-only content at zero cost for the eventual implementing EM, who may want the richer draft's text. The 2026-05-23 example-sim-repo roadmap (each stub_id authored twice via overlapping bulk-commit + per-stub-commit passes) is the empirical case.

### Step 2.1.5 — Assign stub numbers in dependency order

<!-- spec-backlink: docs/plans/2026-06-28-roadmap-stub-numbering-dependency-order.md (C4) -->

Before writing any stub frontmatter, resolve the final `stub_id` integer (`N`), `sprint`, and `wave` for every stub in topological (dependency) order. A lower-numbered stub must never depend on a higher-numbered one.

**Invariant (strict):** stub numbers are a topological linearization of the `blocks`/`blocked_by` DAG — for every edge `A blocked_by B`, `number(B) < number(A)` AND the `(sprint, wave)` execution slot is **strictly dependency-monotone**: `(sprint(B), wave(B)) <_lex (sprint(A), wave(A))`. A dependency and its dependent sharing the same `(sprint, wave)` slot is itself a violation — `blocked_by` is a hard gate and wave members dispatch concurrently.

**Steps:**

1. **Build the provisional dependency graph** from `clusters.md` before any stubs exist. List every KEEP cluster as a provisional label and draw `A blocked_by B` edges from the cluster dependency notes (or COORDINATOR-RESOLUTIONS where applicable).

2. **Run the numbering helper** (single-sprint constructive):

   ```bash
   _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
   _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
   _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
   _cc_trusted=0
   case "$_cc_root" in
     "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
   esac
   [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
   case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
   [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
   [ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
   [ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
   node "${_cc_root}/bin/roadmap-number-stubs.js" <edges-file>
   ```

   The helper applies Kahn's algorithm over the DAG and emits a `label → (stub_id N, sprint, wave)` mapping. Within a topo layer, it tie-breaks deterministically by original cluster index. For single-sprint roadmaps `wave = depth + 1` by construction. Alternatively, apply Kahn's sort and number by hand if the graph is small.

   **Multi-sprint roadmaps:** `roadmap-number-stubs.js` provides the topological linearization order; the author then assigns `sprint` values manually (grouping linearized stubs into sprint boundaries). Audit 5 (see Step 2.7) verifies the resulting `(sprint, wave)` strict monotonicity after stubs are on disk.

3. **Transcribe the resulting `N` / `sprint` / `wave` into stub frontmatter** (Step 2.1 template fields). Do not auto-mutate authored markdown — the helper emits a mapping; the author transcribes. When transcribing, zero-pad the stub number to at least two digits (width = max(2, digits of the highest N in the set)) — the helper already emits padded values; match them exactly in frontmatter and filenames.

   This zero-pad-to-≥2-digits convention applies to any ordered/numbered artifact set we author (not only roadmap stubs), so files sort lexically and read uniformly.

**This guarantee applies exclusively to DECLARED `blocked_by` edges.** The gate cannot discover an undeclared or missing dependency — that remains a human / OVERVIEW-review responsibility.

See `../../docs/wiki/roadmap-numbering.md` for the invariant stated as greppable doctrine and worked examples.

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
- Trailing marker: `<!-- spinoff-roadmap: <run-id> <stub_id> by roadmap-planning -->`

### Step 2.3 — STUB-INDEX as a query callout

Write `state/roadmap/<run-id>/STUB-INDEX.md`:

```markdown
# STUB-INDEX — <run-id>

<!-- BEGIN query: handoff where=roadmap_id=<run-id> sort=sprint -->
(regenerated by /update-docs Phase 11c via bin/refresh-queries.js)
<!-- END query -->
```

NOT a hand-maintained table. Do NOT hand-add a static-snapshot table below the callout — the callout is the single authoritative rendered surface. The query callout regenerates at `/pickup` and `/workstream-complete` (scoped to the baton's roadmap) and on every `/update-docs` run (all roadmaps), so the index always reflects current frontmatter.

**Single-clause `where=` only inside callouts (dogfood-2026-05-08 finding).** `bin/refresh-queries.js` token-splits the BEGIN marker on whitespace, so a multi-clause where like `where=kind=spinoff-roadmap AND roadmap_id=...` would silently lose every clause after the first space. Single-clause `where=roadmap_id=<run-id>` is sufficient because the cross-field validator (`bin/lib/schema.js` CROSS_FIELD_RULES.handoff) enforces `roadmap_id` ⇒ `kind: spinoff-roadmap` — the kind clause is redundant. **Multi-condition queries from the CLI work fine** (`--where "X AND Y"` in shell quotes); the limitation is callout-only. Future enhancement candidate: extend `refresh-queries.js` to accept quoted multi-clause where; tracked in the improvement queue.

### Step 2.4 — Constraint graph (machine-readable in frontmatter)

`blocks` and `blocked_by` arrays in each stub's frontmatter ARE the graph. To visualize:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
"$_cc_root/bin/query-records.sh" --type handoff --where "kind=spinoff-roadmap AND roadmap_id=<run-id>" --format json | <graphviz-script>
```

Wave order is assigned in dependency order per **Step 2.1.5** — stub numbers are a topological linearization of the `blocks`/`blocked_by` DAG, and the `(sprint, wave)` execution slot is **strictly dependency-monotone** (`(sprint(B), wave(B)) <_lex (sprint(A), wave(A))` for every edge `A blocked_by B`; same-slot is a violation). For single-sprint roadmaps `bin/roadmap-number-stubs.js` is constructive (wave = depth + 1); for multi-sprint roadmaps the author assigns sprint boundaries from the topo order and **Audit 5** (`audit-roadmap.sh`) verifies the strict monotonicity gate at Phase 2 close. If you find yourself hand-maintaining a wave-order table, stop — you've recreated the brief's failure mode (siblings, not subsets).

**`sort=sprint` reminder:** `query-records.js` sorts by frontmatter field name; `sprint` is a roadmap-stub frontmatter field, so the callout's `sort=sprint` IS valid syntactically. But the dogfood-2026-05-08 run could not confirm sprint-sort actually executed (the test corpus had no multi-sprint variation). On the next multi-sprint roadmap run, verify sort ordering against expected sprint sequence; if it sorts by `created` instead, file an improvement-queue entry.

**Pre-derive the design graph BEFORE any fan-out (hard gate).** The wave order is a *derived* artifact — topologically sorted over `blocked_by` — not an assumption the dispatching EM makes by reading sprint numbers. Before Phase 3 dispatch fans out any wave, run the derivation and verify it:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
"$_cc_root/bin/query-records.sh" --type handoff --where "roadmap_id=<run-id>" --format json
```

Confirm: (1) every stub's `blocks`/`blocked_by` edges reference tc-ids that exist in this `roadmap_id`; (2) the graph is acyclic (a cycle means the topology cannot produce a wave order — fix the edges before dispatch); (3) every wave-N stub set is file-disjoint per its `scope:` blocks (the file-overlap gate per coordinator CLAUDE.md § Pre-Dispatch Verification — overlap is the one unconditional serial gate). A fan-out dispatched against an unverified or cyclic graph is the "siblings, not subsets" failure the skill exists to prevent, now in execution form: executors collide on shared files or block on edges that were never real. The derivation is cheap (one query + a cycle check); skipping it costs an aborted wave.

### Step 2.5 — `pm-gates.md` enumeration (brief recommendation E)

Phase 2 forces explicit enumeration of every product-coupled question. Write `state/roadmap/<run-id>/pm-gates.md`:

```markdown
# PM Gates — <run-id>

| sprint | stub_id | gate question | disposition format | resolved? |
|---|---|---|---|---|
| 2 | dscov-15 | should consumer_runner emit retry telemetry by default? | yes/no/defer | pending |
```

**Detection rule for "product-coupled":** during Phase 2 stub authoring, scan each stub's `gate_dependency:` text for any of: explicit `PM `-prefixed strings, named-stakeholder references, `decision needed` / `approval needed` / `policy` / `scope` / `user-facing` tokens. Each hit becomes a row in `pm-gates.md`. Author can add rows manually for product-coupled questions whose `gate_dependency:` text doesn't trip the detector.

**Manual audit at Phase 2 close (cross-file; `bin/lint-frontmatter.js` cannot do cross-file validation):** for every stub with `gate_dependency:` starting `PM `, confirm an entry exists in `pm-gates.md` (`stub_id` column). For every row in `pm-gates.md` with `resolved? = pending`, confirm at least one stub references it via `gate_dependency:` text. Mismatch blocks Phase 3 entry. Automation candidate post-dogfood: a `audit-roadmap.sh <run-id>` script that runs all Phase 2 cross-file checks.

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
- Any `kind: spinoff-roadmap` MUST have `roadmap_id:` AND `blocks` AND `blocked_by` AND `wave: <integer>` AND `stub_id:` non-empty.
- `stub_id:` MUST be globally unique. It is `<slug>-<NN>` where `<slug>` is this roadmap's short prefix derived from its roadmap_id, `<NN>` is a zero-padded roadmap-local integer (min two digits, e.g. `pcore-04`, `pcore-12`). The `<slug>` MUST be distinct from every existing roadmap's slug — grep existing `stub_id:` prefixes across state/handoffs/ and archive/handoffs/ before choosing one, so codes are self-qualifying and never collide across roadmaps.
- At most one `ready_to_fire` per `(roadmap_id, sprint, wave)` triple across the active set. Wave is sprint-LOCAL (§ "Wave = single-dispatch parallel fan-out within a sprint"), so wave 1 of sprint 1 and wave 1 of sprint 4 are distinct execution slots and do NOT collide. `audit-roadmap.sh` Audit 2 enforces this composite key.
- **`cost` if present MUST be one of T0/T1/T2/T3.** A separate cross-field rule in `bin/lint-frontmatter.js` enforces this (added alongside the kind:spinoff-roadmap rules). A stub with `cost: "very large"` is rejected at lint time.
- **Audit 5 — dependency order invariant (`bin/audit-roadmap.sh`).** For every declared `A blocked_by B` edge across the stub set: `number(B) < number(A)` AND `(sprint(B), wave(B)) <_lex (sprint(A), wave(A))` (STRICT — same-slot is a violation). Also checks: no cycles in the `blocked_by` graph; no unresolved edges (a `blocked_by` entry pointing at a stub_id absent from the set); no missing `sprint` field on either endpoint of a dependency edge (fail-loud own violation class, not silent coercion). Runs at Phase 2 close; exit 1 names the specific offending edge and blocks Phase 3 dispatch.

<!-- Review: the Staff Engineer — cost is a documented enum but was missing from validator surface; a stub with free-text cost would pass lint silently (P2-4) -->

Prevents the brief's "siblings, not subsets" failure mode — stubs cannot exist outside a roadmap parent, and roadmap parents cannot exist without graph primitives.

### Step 2.8 — Primary rigor reviewer then domain reviewer (sequential; primary mandatory, domain conditional)

<!-- Review: the Staff Engineer — parallel review stretches the merge-gate carve-out which explicitly excludes plan/stub/doc review; sequential is the correct doctrine-compliant shape here (P1-3) -->

#### Primary rigor-reviewer selection by altitude (cross-repo boundary → the Director of Engineering, else the Staff Engineer)

The default primary rigor reviewer for the stub set is **the Staff Engineer** (`coordinator:staff-eng`, EM-altitude). BUT when the roadmap **sets cross-repo or cross-team boundaries**, the primary reviewer is **the Director of Engineering** (`coordinator:eng-director`, standalone primary mode). Setting cross-repo/cross-team boundaries is DoE-altitude authority an EM-altitude reviewer structurally lacks — it is exactly why the Staff Engineer reaches for a the Director of Engineering backstop on such seams; at this gate the backstop becomes the primary. Detect "sets cross-repo/cross-team boundaries" by ANY of:

- (a) `peer-team-asks.md` carries a non-trivial cross-repo / cross-team ask;
- (b) the stubs' `scope:` pathspecs resolve into ≥2 repos;
- (c) the roadmap authors or amends a contract / interface / wire-format consumed by a sibling repo;
- (d) `COORDINATOR-RESOLUTIONS.md` sets a cross-repo coordination, ownership, or version-cutover boundary.

When the Director of Engineering is primary, the Staff Engineer MAY still run as the second reviewer or a backstop pass; the domain/data reviewer (below) is unchanged. **The same selection rule governs the Step 1.5.5 OVERVIEW review.** Rationale and altitude boundaries: `docs/wiki/doe-altitude-and-shared-infra.md`.

**Sequential, not parallel** (merge-gate parallel carve-out explicitly excludes plan/stub/doc review — a roadmap stub set is plan/stub/doc-shaped).

**Persist the persona verdict — reviewer self-persists; EM reads the returned path.** Persona reviewers (the Staff Engineer, the Director of Engineering, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer) self-persist their findings to `state/review-trail/findings/` when the skill appends the `snippets/findings-self-persist-sentinel.md` protocol to the brief. No EM pre-scaffold. The reviewer scaffolds its own sidecar via `coordinator-doc-new --type review-findings`, writes its `ReviewOutput` there, and returns: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. Read that path for integrator dispatch. **Multi-reviewer chain:** the domain reviewer (step 3) is dispatched with the same snippet appended; each reviewer scaffolds its own sidecar path. Spec backlink: `cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md`.

Sequence:
1. Dispatch the **primary rigor reviewer** (the Director of Engineering if the roadmap sets cross-repo/cross-team boundaries per the rule above, else the Staff Engineer) with the full `state/roadmap/<run-id>/` directory + all stubs. Brief: schema/architecture/sequencing review of the stub set; flag P0 conflicts, missing AC surface, scope errors, sequencing bugs in the constraint graph. **When the Director of Engineering is primary, the brief ALSO carries the cross-repo-boundary lens** — is the boundary drawn correctly; does any stub assume direct authority over a sibling repo it shouldn't; is the cross-repo coordination (memo + PM-relay) routed right. Read-only. **Inject** the `docs/plans/<run-id>-stubs.review.md` sidecar path; instruct the reviewer to self-persist as their final action.
2. Integrate the primary reviewer's findings via `coordinator:review-integrator` (mode: auto) pointing at the on-disk sidecar (`docs/plans/<run-id>-stubs.review.md`). EM spot-checks the diff.
3. Dispatch the domain/data reviewer — the Data Science Reviewer for data shapes (default), or the Game Dev Reviewer (game-dev/UE) / the Front-End Reviewer (web) per roadmap flavor — with the same directory. Brief: domain coherence + data shapes; flag clusters whose stubs would compose poorly, premise gaps, edge cases the stub set silently elides. Read-only. **Inject** the existing `docs/plans/<run-id>-stubs.review.md` sidecar path; instruct the reviewer to append their section as their final action.
4. Integrate the domain reviewer's findings via `coordinator:review-integrator` pointing at the on-disk sidecar (`docs/plans/<run-id>-stubs.review.md`).

The latency cost is acceptable: fires once per roadmap, the domain reviewer benefits from the primary reviewer's integrated changes, and the sequential rule holds across all plan-shaped review.

#### Domain/data reviewer skip condition (ceremony-calibration)

The **primary rigor review (steps 1–2) is always mandatory.** The **domain/data reviewer (steps 3–4) is SKIPPABLE** when BOTH hold:

- (a) the same domain reviewer already ran at **Step 1.5.5** on the OVERVIEW and their findings were integrated and **pinned into the stub ACs** — i.e. the stubs carry the reviewed data shapes verbatim (via COORDINATOR-RESOLUTIONS), not new ones; AND
- (b) **each stub becomes a downstream `coordinator:plan`** (per § Anti-scope) that gets its own domain review at `coordinator:review` — so the data-shape lens is re-applied at the per-stub PLAN altitude, where it is most load-bearing (concrete DDL / emitter code, not stub prose).

When both hold, the primary rigor reviewer is the sufficient stub-set gate and a second full domain pass on the stubs is **redundant-by-convergence** — skip it and record a one-line skip rationale in the roadmap dir (e.g. a note in `pm-gates.md` or a commit message). The domain pass at 2.8 is **REQUIRED** when: the OVERVIEW domain review (1.5.5) was skipped; OR the stubs introduce data shapes not present in the reviewed OVERVIEW; OR the primary rigor reviewer flags an unresolved data-shape concern. Rationale: do not run a review whose findings are pre-converged and which recurs at a better altitude downstream (§ ceremony-calibration; `docs/wiki/ceremony-calibration.md`).

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
- [ ] Design graph derived and verified: `blocks`/`blocked_by` edges all resolve, graph is acyclic (acyclicity is now **ENFORCED by Audit 5** — not a manual checkbox; the gate cannot drift back to manual), every wave-N set is file-disjoint by `scope:`. (Pre-fan-out gate per Step 2.4.)
- [ ] Dependency-order invariant: `audit-roadmap.sh` Audit 5 green — no lower-number-depends-on-higher, `(sprint, wave)` strictly dependency-monotone (`<_lex`), acyclic, no unresolved edges, no missing `sprint` on dependency endpoints.

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

After all sprints complete, dispatch ONE Sonnet review across the whole roadmap output. NOT per-wave Opus (empirical finding: end-of-run Sonnet beat per-wave Opus on cost without meaningful signal loss). Brief: "Cross-cutting review of <run-id> roadmap execution. Flag any drift from stubs, missing acceptance criteria, deferred items that should have been fixed in-session." **Dispatch `coordinator:code-reviewer`** (UNNAMED — no `name:` param, self-persists by default):

1. **Dispatch `coordinator:code-reviewer`** (UNNAMED) on the roadmap output. The reviewer scaffolds its own sidecar in `state/review-trail/findings/` via `coordinator-doc-new --type review-findings`, writes its findings there, and returns: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. No pre-scaffold, no claim marker. Read the returned path. Spec backlink: `cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md`.
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
  - documents the lineage in the plan-doc body's "Why this plan" section, citing the stub's `roadmap_id/stub_id` (e.g., "originating roadmap stub: `dogfood-2026-05-08/dogfood-3`").

  A future schema extension may add a `roadmap_parent:` field to plan-doc frontmatter for machine-readable lineage; that's deferred until a second instance of plan-from-stub demonstrates the textual citation pattern is insufficient for retrieval. PM disposition required to add the field.

<!-- Review: the Staff Engineer — anti-scope was silent on lineage when a stub becomes the basis for a coordinator:plan invocation; without this, /distill loses provenance trail (P2-6) -->

---

## See also

- `docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` — spec
- `archive/specs/2026-05-08-roadmap-planning-skill-brief.md` — empirical motivator (project-rag retrospective)
- `docs/wiki/spinoff-handoffs.md` — cohort wiki: frontmatter conventions (predecessor: none), deployment_state lifecycle for spinoffs, soft-seams discipline, awaiting_gate aging, pickup-side premise check.
- `commands/distill.md` — extracts knowledge from completed roadmap stubs
- `coordinator:plan` — for single-plan work downstream of a roadmap stub (the rung below in the ceremony ladder)
- `coordinator:brainstorming` — for pre-roadmap option exploration
- `coordinator/skills/shape/SKILL.md` — upstream of Entry Point C; sets `estimated_horizon: week` at ratification to route here
- `coordinator:goal-setting` — upstream of Entry Point B; spawns `kind: spinoff-roadmap-creator` stubs (the rung above in the ceremony ladder)
