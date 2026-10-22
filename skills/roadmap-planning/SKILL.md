---
name: roadmap-planning
description: "PM-GATED. Shape research into ratified roadmap batons."
version: 2.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "<input-corpus-path|problem-set-path|roadmap-seed-stub-path> [--run-id <slug>]"
---

# Roadmap Planning — From Inputs to Sequenced Spinoff Stubs

Turns a corpus of inputs (research, deep-dives, brainstorming, or a ratified problem-set) into a
sequenced backlog of `kind: roadmap-baton` stubs: pickup-able handoffs, not a plan doc. Use when 5+
candidate items need sequencing into gated waves (one feature → `coordinator:plan`; architecture
call → `coordinator:staff-session`; bug batch → `coordinator:bug-blitz`; options → `coordinator:brainstorming`). **Exception:** a `kind: roadmap-seed` pickup (Entry
Point B) is exempt from the 5+ floor — goal-setting already scoped it as one roadmap's worth of work.

## Entry points

Read before Phase 1 on B/C/D: `residue/entry-points-b-c-d.md`.

- **A** — direct invocation, `<input-corpus-path>` is the corpus dir. Begin at Phase 1.
- **B** — pickup of a `kind: roadmap-seed` stub (goal-seeded) → `§ Entry Point B`: pickup runs `baton.awaiting_gate_recheck`, reads `goal_go` acks, splits a mixed seed via `baton.seed_split` (`A-GATED-SEED-PARKS-ITS-UNBLOCKED-HALF`).
- **C** — chain from `/shape` (`estimated_horizon: week`) → `§ Entry Point C`.
- **D** — conform intake from a sizing-object (`xl_exit: roadmap`) → `§ Entry Point D`. Receive-and-use-if-present: absent a sizing-object this skill runs exactly as today; the sizing lobby never gates or refuses a `roadmap-planning` invocation.

## Ceremony ladder

```
/goal-setting → kind: roadmap-seed stubs → /roadmap-planning → kind: roadmap-baton stubs
  → coordinator:plan → plan-doc → execute-plan → executor chunks
```

`/mise-prep` drives that stage; `plan.stamp_prepped` is the only attest writer. Batched: `plan-blitz → mise-prep → the run`; **each exit is the next entry, read off
disk, never retyped** (`A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`).

---

## Phase 1 — Synthesize: input corpus → verdict-grid

Every cluster gets exactly one verdict — no "we'll see". Inverse coverage is Step 2.6's job.

1. Inventory every input file (title + summary) → `state/roadmap/<run-id>/inventory.md`. Also read
   `docs/architecture/systems-index.md` and the system pages the corpus touches, noting each
   `last_attested`; every pass, sizing-object or not. The inventory row also MARKS each input that
   is a live plan under `docs/plans/` — the only step that walks the corpus (`residue/source-plan-supersession.md`).
2. Cluster into coverage units (typically 20–60/roadmap); a sub-floor cluster folds into a
   sibling here, pre-verdict → `state/roadmap/<run-id>/clusters.md`.
   Every cluster carries `loe:`; `roadmap.blitz_stage` refuses a clusters.md missing one.
   **A cluster is a unit of coverage accounting, never of dispatch** (Step 2.1.6 sets the baton count).
3. Verdict each cluster — MERGE / DEFER / KEEP / DROP / MOVE — into
   `state/roadmap/<run-id>/reconciliation.md`. Verdict count must equal cluster count.
4. Conflicts → `state/roadmap/<run-id>/COORDINATOR-RESOLUTIONS.md` (template:
   `residue/coordinator-resolutions-format.md`), authoritative over any stub.

**Exit:** inventory + verdicts complete and balanced; resolutions doc if conflicts; every
sub-floor cluster folded or dispatched.

---

## Phase 1.5 — Substantiate: research + OVERVIEW + peer-team asks (PM-gated, double-approved)

Mandatory (wiki).

**UE-cluster precondition:** confirm `mcp__project-rag__project_semantic_search(query="UClass",
source="unreal", limit=1)` returns a hit before any UE-internal-API cluster proceeds; unavailable →
STOP those clusters, never substitute web scouts, surface to PM; other clusters proceed.

1.5.0. Assess research depth (EM sizing call) — `residue/research-depth-assessment.md`
   before dispatching scouts; size by value class.
1.5.1. Dispatch one scout per KEEP/MERGE-target cluster (cap 8 concurrent), brief =
   `${CLAUDE_PLUGIN_ROOT}/snippets/internet-research-scout.md` + cluster scope → `research-corpus/<topic-
   slug>.md`, ≥2KB. **Do not ask whether to dispatch** — invoking this skill IS the request.
1.5.2. Author `OVERVIEW.md`, one section per KEEP cluster, headed by NAME never number (wiki:
   why); each section cites its research-corpus file and carries `### Contested` (required, even
   empty). Frontmatter template: wiki. It carries a `### Atlas consult` section (pages read,
   `last_attested`, changes).
1.5.3. `peer-team-asks.md` — must be present, empty as `- None identified at authoring time.`
   (template: `residue/peer-team-ask-format.md`); answer the consumer-render probe for any cross-repo contract here (wiki: writing-plans.md § Consumer-Surface Enumeration).
1.5.4. PM round 1 (shape approval) before reviewers run. On approval, `status: shape-approved`.
1.5.5. Sequential reviews — the Staff Engineer, or the Director of Engineering cross-repo; domain reviewer by flavor. Sidecar contract + altitude rule (shared with 2.8): wiki.
1.5.6. PM round 2 (final approval) with a diff vs. shape-approved. On approval,
   `status: final-approved`. **Phase 2 MUST NOT start without it** — unless the PM
   pre-waived round 2 at round 1 with a recorded verbatim "execute and adjust" ruling, which stands in for round 2.
   **In `pm` or `ceo` mode, `coordinator:apm` rules rounds 1 and 2**: record the PM's standing
   hands-off words verbatim and the APM's ruling path beside each round's status. Only an APM `escalate` reaches the PM.

**Exit:** research-depth recorded; every KEEP cluster has a research-corpus file; OVERVIEW cites +
`### Contested` per section; peer-team-asks present; reviews integrated; `final-approved`.

---

## Phase 2 — Plan: stubs + STUB-INDEX + constraint graph + PM-gates + reviews

**Entry:** OVERVIEW `status: final-approved`, Phase 1.5 exit checked — else STOP, return to Phase 1.5.
Step 1.1's live-plan marks are CHECKED here, never re-discovered; each marked plan with a KEEP or
MERGE-target cluster owes retirement at Phase 2 close
(`residue/source-plan-supersession.md`).

2.1. Scaffold each stub (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
   `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.exe" --type roadmap-baton --title "<title>" --roadmap-id <run-id> --stub-id <slug>-<N> --out state/handoffs/<date>_<HHMMSS>_roadmap-<slug>-<N>.md`,
   mint the id (`bin/mint-deliverable-id --stub-id "<slug>-<N>"` → `deliverable_id:`), fill the rest
   from 2.1.5's output. **Read `residue/stub-frontmatter-schema-and-field-notes.md` first.**

<!-- engine-gap: field=roadmap_planning.stub_body_section_completeness producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->
2.1a. **Every stub carries its own sizing, never the roadmap's.** `roadmap.blitz_stage` mints
   a per-baton sizing and stamps `sizing_object:`. Never pass the roadmap's sizing to a stub
   (batons sharing one all link to its plan). Tripwire:
   `A-BATON-IS-NOT-A-SIZING-ARTIFACT`.
2.1.5. Number stubs in dependency order before writing any — run (Shape W,
   `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`)
   `& "$env:COORDINATOR_SETTINGS_HOME\bin\roadmap-number-stubs.exe" <edges-file>`
   and transcribe its `N`/`sprint`/`wave` output verbatim (multi-sprint boundaries are hand
   judgment). Covers only DECLARED edges. Format: wiki.

   **`<edges-file>`** — one `A <- B` per line (A blocked_by B); no `<-` = isolated node; `@N` tags
   sprint N; `#` comments; unparseable line exits 2. E.g. `C1 <- C3`, `C4@2`.
2.1.6. **Fold to size — the baton is the parallel wave, not the idea.** Runs on 2.1.5's `wave`
   output; sets how many stubs 2.1 scaffolds. `loe:` is the whole-baton t-shirt read.
   - **Band: mostly M and L.** `roadmap.blitz_stage` folds XS/S only along a declared edge,
     dependent first, stopping at M. An edge-free XS/S is flagged `unfoldable-small` and stages
     as-is; XL is flagged, never auto-split. An XXL stub means the roadmap is mis-made; go back to Phase 1.
   - **Same-wave stubs run in parallel**; collapsing is an EM call; same-file units never split.
   - **Split only on a real barrier** — a gate that cannot clear until the first half lands, or a
     decision its output determines.
   - **Re-price on scope change.**

   Distinct ideas are sections, never batons; each keeps its cluster id in `covers:`.
2.2. Body, per stub, in order: title; why-its-own-session paragraph; `## What this covers`; `##
   Reference materials (read first)` (cite `OVERVIEW.md § <name>` + research-corpus, by name never
   number); `## Specification`; `## Acceptance criteria`; `## Recommended next steps for the
   picking-up EM` (3–7); `## Anti-scope`; `## Soft seams` (may be `- None identified`, must be
   present); `## Session Ledger` (empty; omitted, `handoff.append_session_ledger` cannot write); trailing `<!-- roadmap-baton: <run-id> <stub_id> by
   roadmap-planning -->`.
2.3. `STUB-INDEX.md` — a query callout, never a hand table.
2.4. Before any fan-out: run `audit-roadmap <run-id>`; then **what it cannot check** —
   every wave-N stub set is file-disjoint per `scope:`; a non-disjoint pair is a fold and re-number.

   **`scope:` names a SUBJECT, not a blast radius** — grep each item's symbols for its real touched
   set before splitting. Mark EM-fenced items (`archive/`, permission settings); never send a subagent at the fast/full tier.
   `A-SCOPE-FIELD-NAMES-A-SUBJECT-NOT-A-BLAST-RADIUS`.
2.5. `pm-gates.md` — one row per stub whose `gate_notes`/`gate_dependency` carries a
   product-coupled signal (`PM `-prefix, named stakeholder, decision/policy/scope/
   user-facing language).
2.6–2.7. Phase 2 close (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
   `& "$env:COORDINATOR_SETTINGS_HOME\bin\audit-roadmap.exe" <run-id>` — one gate, five audits. Exit 1 blocks close. `kind: roadmap-baton` frontmatter must be validator-clean; `roadmap_id` must name an on-disk cluster. **No applicable cluster → scaffold the stub `kind: spinoff`** (never a null `roadmap_id` or placeholder cluster).
2.8. Sequential reviews — same altitude rule and sidecar contract as Step 1.5.5. Domain reviewer
   skippable when its Step-1.5.5 findings are pinned into the stub ACs verbatim AND each stub's
   `coordinator:plan` re-applies the lens at PLAN altitude; record the skip in the roadmap dir.
2.9. Retire each marked source plan, in order: migrate its load-bearing prose into the
   inheriting stubs, THEN stamp `status: superseded` + `superseded_by:
   state/roadmap/<run-id>/STUB-INDEX.md`, THEN stand down the owed review. **MUST NOT stamp before
   migrating.** Mechanics: `residue/source-plan-supersession.md`.

**The stub:cluster relation is MANY-TO-ONE.** One stub may name many KEEP clusters in `covers:`;
every cluster is named exactly once across all stubs. A `stub_count == keep_count` check fails a
compliant roadmap; any gate must read `covers:`.

**Exit:** every KEEP cluster in exactly one stub's `covers:`; every stub `loe:` M–XL (XS/S flagged `unfoldable-small`, never refused);
frontmatter validator-clean, `## Soft seams` present; STUB-INDEX regenerates; resolutions doc
covers every conflict; `audit-roadmap <run-id>` exits 0; reviews integrated; 2.4 disjointness done; owed source plans retired (2.9).

---

## After Phase 2 — the stubs go live

Phase 2 close IS the deliverable; a fresh session picks each stub up via `/pickup`. This skill never invokes `coordinator:plan`.

**Owned downstream, never run here:** the readiness view (`roadmap-number-stubs --state <run-id>`);
`awaiting_gate → ready_to_fire` by *another* session's `/handoff` or
`/workstream-complete` — **never pre-mark a sibling's stub ready**; the end-of-roadmap review.
**Roadmap stubs are NEVER handed to `/mise-en-place` directly.** Spec: wiki § Downstream mechanisms.

---

## Contact points

`/handoff`, `/spinoff`, `/repo-setup`, `/workstream-start`, `/workstream-complete`,
`/workday-start`, boot-time archival sweep — read `residue/contact-points-checklist.md` first.

## Anti-scope

- Auto-derive `gate_notes:`/`gate_dependency:` from natural language; author-supplied only.
- Cross-repo roadmap rollup, `/pickup` gate-meaningfulness triggers, dashboards.
- **Replace `coordinator:plan` for single-plan work.** A picking-up EM keeps `deployment_state:
  in_flight`, writes `predecessor: none`, cites `roadmap_id/stub_id` in the plan's "Why this plan", no `roadmap_parent:` field.
- **Leave a re-sliced live plan standing** — retire it at Phase 2 close (Step 2.9).

## See also
`commands/distill.md` · `coordinator:plan` · `coordinator:brainstorming` ·
`coordinator/skills/shape/SKILL.md` · `coordinator:goal-setting`
