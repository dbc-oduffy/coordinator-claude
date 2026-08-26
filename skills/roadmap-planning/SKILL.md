---
name: roadmap-planning
description: "PM-GATED. Shape research into ratified, graphed roadmap batons."
version: 2.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "<input-corpus-path|problem-set-path|roadmap-seed-stub-path> [--run-id <slug>]"
---

# Roadmap Planning — From Inputs to Sequenced Spinoff Stubs

Turns a corpus of inputs (research, deep-dives, brainstorming, or a ratified problem-set) into a
sequenced backlog of `kind: roadmap-baton` stubs — dispatchable, pickup-able handoffs, not a plan
doc. Use when 5+ candidate items need sequencing into gated waves (one feature → `coordinator:plan`;
architecture call → `coordinator:staff-session`; bug batch → `coordinator:bug-blitz`; option
exploration → `coordinator:brainstorming`). **Exception:** a `kind: roadmap-seed` pickup (Entry
Point B) is exempt from the 5+ floor — goal-setting already scoped it as one roadmap's worth of work.

## Entry points

Detail for B/C/D, read before starting Phase 1 on that path: `residue/entry-points-b-c-d.md`.

- **A** — direct invocation, `<input-corpus-path>` is the corpus dir. Begin at Phase 1.
- **B** — pickup of a `kind: roadmap-seed` stub (goal-seeded) → `§ Entry Point B`.
- **C** — chain from `/shape` (`estimated_horizon: week`) → `§ Entry Point C`.
- **D** — conform intake from a sizing-object (`xl_exit: roadmap`), never a gate → `§ Entry Point D`.

## Ceremony ladder

```
/goal-setting → kind: roadmap-seed stubs → /roadmap-planning → kind: roadmap-baton stubs
  → coordinator:plan → plan-doc → execute-plan → executor chunks
```

This skill authors the stubs a downstream `coordinator:plan` consumes; never invokes it (§ Anti-scope).

---

## Phase 1 — Synthesize: input corpus → verdict-grid

Every cluster gets exactly one verdict — no "we'll see". Inverse coverage (verdict → stub) is
Step 2.6's job (below).

1. Inventory every input file (title + summary) → `state/roadmap/<run-id>/inventory.md`.
2. Cluster into coverage units (typically 20–60/roadmap); a sub-floor cluster folds into a
   sibling here, pre-verdict (wiki: grain-fold vs. MERGE) → `state/roadmap/<run-id>/clusters.md`.
   **A cluster is a unit of coverage accounting, never a unit of dispatch** — how many batons
   these become is Step 2.1.6's call, not this step's.
3. Verdict each cluster — MERGE / DEFER / KEEP / DROP / MOVE — into
   `state/roadmap/<run-id>/reconciliation.md`. Verdict count must equal cluster count.
4. Conflicts → `state/roadmap/<run-id>/COORDINATOR-RESOLUTIONS.md` (template:
   `residue/coordinator-resolutions-format.md`), authoritative over any stub.

**Exit:** inventory + verdicts complete and balanced; resolutions doc present if conflicts; every
sub-floor cluster folded or dispatched — a rationale is not a disposition.

---

## Phase 1.5 — Substantiate: research + OVERVIEW + peer-team asks (PM-gated, double-approved)

Mandatory, never skipped (wiki: why). Stubs cite primary research and a PM-approved overview, not
EM hand-waving.

**UE-cluster precondition:** confirm `mcp__project-rag__project_semantic_search(query="UClass",
source="unreal", limit=1)` returns a hit before any UE-internal-API cluster proceeds; unavailable →
STOP those clusters, never substitute web scouts, surface to PM. Other clusters unaffected.

1.5.0. Assess research depth (EM judgment, PM-authorized) — `residue/research-depth-assessment.md`
   before dispatching scouts; `/research` is PM-gated, never EM-auto-invoked.
1.5.1. Dispatch one scout per KEEP/MERGE-target cluster (cap 8 concurrent), brief =
   `coordinator/snippets/internet-research-scout.md` + cluster scope → `research-corpus/<topic-
   slug>.md`, ≥2KB. Exceptions (per-project material, measurement-derived corpus): wiki.
1.5.2. Author `OVERVIEW.md`, one section per KEEP cluster, headed by NAME never number (wiki:
   why); each section cites its research-corpus file and carries `### Contested` (required, even
   empty). Frontmatter template: wiki.
1.5.3. `peer-team-asks.md` — must be present, empty as `- None identified at authoring time.`
   (template: `residue/peer-team-ask-format.md`).
1.5.4. PM round 1 (shape approval) before reviewers run — framing template: wiki. On approval,
   `status: shape-approved`.
1.5.5. Sequential reviews — the Staff Engineer, or the Director of Engineering on cross-repo/cross-team boundaries; domain reviewer
   by flavor. Sidecar contract + altitude rule (shared with Step 2.8): wiki.
1.5.6. PM round 2 (final approval) with a diff vs. shape-approved — framing template: wiki. On
   approval, `status: final-approved`. **Phase 2 MUST NOT start without it.**

**Exit:** research-depth recorded; every KEEP cluster has a research-corpus file; OVERVIEW cites +
`### Contested` per section; peer-team-asks present; both reviews integrated; `status:
final-approved`.

---

## Phase 2 — Plan: stubs + STUB-INDEX + constraint graph + PM-gates + reviews

**Entry:** OVERVIEW `status: final-approved`, Phase 1.5 exit checked — else STOP, return to Phase 1.5.

2.1. Scaffold each stub (Shape W, `snippets/resolve-coordinator-bin.md`):
   `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.cmd" --type roadmap-baton --title "<title>" --roadmap-id <run-id> --stub-id <slug>-<N> --out state/handoffs/<date>_<HHMMSS>_roadmap-<slug>-<N>.md`,
   mint the id (`bin/mint-deliverable-id --stub-id "<slug>-<N>"` → `deliverable_id:`), fill the rest
   from Step 2.1.5's numbering output. **Read `residue/stub-frontmatter-schema-and-field-notes.md`
   first.**
2.1a. **Carry the size forward — pass `--sizing-object <the object that routed this roadmap>`.** A
   stub minted without it reads as unsized downstream and `plan` trampolines it back to the lobby,
   re-litigating a size this roadmap already made: 2.1.6 assigns every stub its own `loe:`, and the
   roadmap itself arrived through the lobby. Sizing is not re-run on a stub. After scaffolding,
   confirm `sizing_object:` is actually present in the stub's frontmatter — if it is not, stamp it
   by hand rather than trusting the flag silently took effect. Tripwire:
   `A-BATON-IS-NOT-A-SIZING-ARTIFACT`.
2.1.5. Number stubs in dependency order before writing any — run (Shape W,
   `snippets/resolve-coordinator-bin.md`)
   `& "$env:COORDINATOR_SETTINGS_HOME\bin\roadmap-number-stubs.cmd" <edges-file>`
   and transcribe its `N`/`sprint`/`wave` output verbatim (multi-sprint boundary assignment is hand
   judgment it doesn't resolve). Covers only DECLARED edges. Format + the dependency-order
   invariant it enforces: wiki.
2.1.6. **Fold to size — the baton is the parallel wave, not the idea.** Runs on 2.1.5's `wave`
   output; sets how many stubs 2.1 scaffolds. `loe:` is the whole-baton t-shirt read.
   - **Band: mostly M and L.** XS/S never ship alone — group them into one baton. XL only where a
     group cannot cut smaller. An XXL stub means the roadmap is mis-made; go back to Phase 1.
   - **Collapse the wave.** Same wave + pairwise-disjoint `scope:` + no `blocked_by` between
     members → one baton, several specs. Same-file units never split, in any wave.
   - **Split only on a real barrier** — a gate that cannot clear until the first half lands, or a
     decision the first half's output determines.
   - **Re-price on scope change**, or a stale size routes a go-do-it through a full lifecycle.

   Distinct ideas are sections, never batons; each keeps its cluster id in `covers:`.
2.2. Body, per stub, in order: title; why-its-own-session paragraph; `## What this covers`; `##
   Reference materials (read first)` (cite `OVERVIEW.md § <name>` + research-corpus, by name never
   number); `## Specification`; `## Acceptance criteria`; `## Recommended next steps for the
   picking-up EM` (3–7); `## Anti-scope`; `## Soft seams` (may be `- None identified`, must be
   present); trailing `<!-- roadmap-baton: <run-id> <stub_id> by roadmap-planning -->`.
2.3. `STUB-INDEX.md` — a query callout, never a hand table (template + rationale: wiki).
2.4. Before any fan-out: run `audit-roadmap <run-id>`; then **what it cannot check** —
   confirm every wave-N stub set is file-disjoint per `scope:`. Disjointness is now a *merge*
   predicate spent at 2.1.6, so any disjoint pair surviving here is an un-run fold, not a
   licensed parallelism: fold it and re-number.
2.5. `pm-gates.md` — one row per stub whose `blocking_notes`/`gate_dependency` carries a
   product-coupled signal (`PM `-prefix, named stakeholder, decision/approval/policy/scope/
   user-facing language). Template + detection rule: wiki.
2.6–2.7. Phase 2 close (Shape W, `snippets/resolve-coordinator-bin.md`):
   `& "$env:COORDINATOR_SETTINGS_HOME\bin\audit-roadmap.cmd" <run-id>` — one gate, five audits (stub-coverage, `ready_to_fire`
   uniqueness, pm-gates cross-reference, dependency-order). Exit 1 blocks close and names the
   offender. `kind: roadmap-baton` frontmatter is also `bin/lint-frontmatter`-clean.
2.8. Sequential reviews — same altitude rule and sidecar contract as Step 1.5.5. Domain reviewer
   skippable when its Step-1.5.5 findings are already pinned into the stub ACs verbatim AND each
   stub becomes a downstream `coordinator:plan` that re-applies the lens at PLAN altitude — record
   the skip rationale in the roadmap dir.

**Exit:** every KEEP cluster named in exactly one stub's `covers:`; every stub `loe:` M–XL;
frontmatter validator-clean, `## Soft seams` present; STUB-INDEX regenerates; resolutions doc
covers every conflict; `audit-roadmap <run-id>` exits 0; primary review integrated, domain
integrated or its skip recorded; Step 2.4's disjointness check done.

---

## After Phase 2 — the stubs go live

Phase 2 close IS the deliverable. A stub is a baton; a fresh session picks it up via `/pickup`
whenever ready. This skill has no execution phase and never invokes `coordinator:plan` (§
Anti-scope — this session cannot outlive the roadmap's whole execution). Three mechanisms live
downstream, owned by other sessions, not this run: a readiness view, gate transitions, and the
end-of-roadmap review — full spec in `residue/downstream-mechanisms.md`.

---

## Output artifacts

`inventory.md` · `clusters.md` · `reconciliation.md` · `COORDINATOR-RESOLUTIONS.md` (if any) ·
`research-corpus/<topic-slug>.md` × N · `OVERVIEW.md` · `peer-team-asks.md` · `STUB-INDEX.md` ·
`pm-gates.md` (all under `state/roadmap/<run-id>/`) · `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_
roadmap-{stub_id}.md` × N, clustered by `roadmap_id:` alongside ad-hoc spinoffs.

## Contact points

`/handoff`, `/spinoff`, `/repo-setup`, `/workstream-start`, `/workstream-complete`,
`/workday-start`, boot-time archival sweep — read `residue/contact-points-checklist.md` before
touching any on behalf of a roadmap stub.

## Anti-scope

- Auto-derive `blocking_notes:`/`gate_dependency:` from natural language. Author-supplied only.
- Cross-repo roadmap rollup. Single-repo only for v1.
- Auto-trigger gate-meaningfulness on `/pickup` (only on `awaiting_gate → ready_to_fire`).
- Render dashboards or HTML. The query callout in markdown is the surface.
- **Replace `coordinator:plan` for single-plan work.** A picking-up EM keeps `deployment_state:
  in_flight`, writes `predecessor: none`, cites `roadmap_id/stub_id` in the plan-doc's "Why this
  plan" — never a `roadmap_parent:` field until textual citation proves insufficient (PM call).

## See also

`commands/distill.md` · `coordinator:plan` · `coordinator:brainstorming` ·
`coordinator/skills/shape/SKILL.md` · `coordinator:goal-setting`
