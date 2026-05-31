---
title: Writing Plans
description: Long-form doctrine for writing implementation plans — scope modes, definition of ready, file structure, executor hard constraints. Linked from coordinator:plan SKILL.md branches.
created: 2026-05-06
updated: 2026-05-06
authoritative_source: previously skills/writing-plans/SKILL.md (deleted in clean-break migration 2026-05-06)
related:
  - docs/plans/2026-05-06-plan-super-skill.md  # design plan that scaffolded this wiki
  - docs/plans/2026-05-06-decision-tree-skill-pattern.md  # super-skill pattern requiring this extraction
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## Sub-plan delegation under a master plan

**Master + N sub-plans: EM holds the problem space.** When a plan's scope crosses ≥3 logical workstreams that would normally each spinoff to their own session but the architectural integration is tight enough that a spinoff would lose context, an alternative shape is one master plan with N sub-plans dispatched in sequence by the same EM. The master plan owns the problem space (cross-workstream invariants, sequencing, integration checks); each sub-plan owns one workstream's body.

**Distinct from spinoffs and monolithic plans.** Spinoffs fork to new sessions and are appropriate when workstreams are genuinely independent. Monolithic plans walk every workstream linearly in one document and become unwieldy at ≥3 workstreams. The master+sub-plan shape sits between them: shared EM context without a single unwieldy document.

**Use when all three hold:**
- (a) Sub-workstreams share invariants that no single sub-plan should re-derive independently.
- (b) The same EM has corpus and tool access to execute them in-session without context loss.
- (c) Spinoff overhead (session boundary, handoff, pickup ceremony) would exceed the per-sub-plan size.

**Shape:** The master plan body is a ≤40-line orchestration brief (cross-workstream invariants, integration checks, sequencing rationale) plus links to the N sub-plans. Each sub-plan is a normal plan body following all the standard plan conventions in this wiki. Order of dispatch is declared in the master plan — it is not a freestyle EM decision made at execution time.

**Source:** `tasks/lessons.md` 2026-05-17 (project-rag).

## Scope Mode (required header field)

Every plan declares one scope mode. The mode shapes review depth, acceptable tradeoffs, and what counts as "done." Don't skip — pick one before drafting tasks.

| Mode | Use when | Rules | Evidence bar |
|------|----------|-------|--------------|
| **prototype** | Learning, demo, throwaway | Mark shortcuts; prefer reversible changes; no broad refactors unless forced | Demo path + known-limitations list |
| **production-patch** | Small safe fix, bug | Minimal diff; no opportunistic refactors; preserve existing behavior unless explicitly changed | Targeted tests + reviewer + low blast radius |
| **feature** | User-visible work | Acceptance criteria required; demo path required; product-risk review required | Acceptance criteria satisfied or explicitly waived |
| **architecture** | Structural/cross-cutting change | Alternatives considered; migration + rollback plan; blast-radius analysis; staff-session likely | Tests + architectural review + risk ledger |
| **spike** | Discovery, "is this feasible?" | Throwaway code allowed; answer the learning question; do not polish unless asked | Findings + recommendation + next step |

If you can't pick confidently, the scope is under-specified — push back to the PM (see "Definition of Ready" below) before drafting tasks.

## the VP-Product Reviewer Pre-Flight (anticipate the stress test)

The VP-Product Reviewer reviews shape, not just correctness — *"why this many threads?", "why single-threaded when parallel is 30 lines?", "is this YAGNI legitimate or laziness in a costume?", "have you considered a different shape?"* The PM (Head of Product) applies the VP-of-Product lens at merge directly — the VP-Product Reviewer does NOT auto-dispatch on plans, on per-merge gates, or on multi-patch areas. The VP-Product Reviewer joins as a teammate in `/staff-session` planning when the PM includes the `vp-product` slug. See `agents/vp-product.md` for the full lens.

**The plan is where the wrong shape gets baked in.** A plan that picks single-threaded execution, naive polling loops, synchronous calls where async would be more natural, or ad-hoc state where a state machine wants to live — that plan will produce code that walks into a the VP-Product Reviewer finding. Fix it at the plan stage, not at merge.

While drafting, walk the VP-Product Reviewer questions against your own plan **before** you save it:

- Is the *shape* of the solution right? (data flow, concurrency model, sync/async, declarative vs. imperative, abstraction altitude)
- For any choice that defaults to single-threaded / single-process / serial / synchronous: is that defensible, or is it the path of least drafting effort?
- For any "we'll add X later" — is that legitimate YAGNI, or is the system silently degrading without X (slow, lossy, fragile)?
- For any patch in an area with prior patches: would a refactor be cheaper in the long run? With AI execution this is hours, not weeks.
- What 1–3 alternative shapes did you consider before picking this one? Name them in a `## Alternatives Considered` section.

**The point is not to write a the VP-Product Reviewer simulation in every plan.** The point is to internalize the questions so the *spectre* of the review keeps the planner honest — exactly the way the spectre of the Staff Engineer's review keeps engineers writing better code in the first pass. The PM applies the VP-of-Product lens at merge time directly; the planner's job is to make the choices defensible before they reach the PM.

If a the VP-Product Reviewer question doesn't have a confident answer at plan time, that's a signal — name the open question in the plan rather than ship the unexamined choice.

## Problem-set as external oracle

A plan documents a PM-owned PRD half (the problem, what "solved" means) and an EM-owned SDD half (architecture, fix-locus, sequencing). When the problem was converged via the `/shape` ceremony (`coordinator:shape`), the PRD half lives in its own ratified file at `docs/problems/YYYY-MM-DD-<slug>.md`, and the plan links it via the `problem_set:` frontmatter key.

That file is the plan's **external coverage oracle.** Because it is authored *before* and *outside* the plan, `plan-coverage-checker` can verify the fix slate covers every ratified problem without the plan grading its own homework — the self-referential trap that an in-plan audit table cannot escape. For feature/PRD-shaped plans (which carry no internal audit table and otherwise get a silent `SCOPE-MISMATCH` skip), a ratified problem-set is the *only* thing that gives the coverage check a target.

- **Integrity marker:** `status: ratified` + a `> Ratified by PM <name> <date>` blockquote. Unratified = `status: draft` = not an oracle.
- **Linkage values:** `problem_set: <path>` (external file), `problem_set: inline (§ ...)` (a ratified block inside the plan — validated by the same blockquote marker), or `problem_set: none`.
- **No problem-set on a feature/architecture/spike plan?** The coverage check emits an advisory nudge (not a verdict-gate) — confirm problem understanding with the PM before dispatch. See `docs/wiki/plan-coverage-checker.md`.

Authoring the problem-set is `/shape`'s job, not the plan's. If you arrived at `coordinator:plan` without one and the work is non-trivial, that is the Branch B doubt-check's cue (see `skills/plan/SKILL.md`).

## Definition of Ready (pre-drafting gate)

Before writing tasks, confirm each item or explicitly waive it. If multiple are missing, recommend brainstorming or a spike instead of a plan.

- [ ] **Product objective** is one clear sentence.
- [ ] **User/stakeholder** is identified (who benefits, who's affected).
- [ ] **Acceptance criteria** are testable.
- [ ] **Non-goals** are explicit (what this *won't* do, to head off scope creep).
- [ ] **Scope mode** is selected (see table above).
- [ ] **Open product decisions** are resolved or intentionally deferred — not hidden inside an implementation request.
- [ ] **Verification method** is known (tests? manual demo? both?).

If two or more checkboxes can't be filled honestly, the plan isn't ready. Surface to the PM with a specific ask, not a draft full of TBDs.

**Plans default to decisions, not questions.** Reviewer-facing questions in the plan body indicate undelegated decisions the author had context to make. Decide; surface only the genuine tradeoffs.

**`UNCERTAIN`-as-status is hedging — rectify before any PM gate.** A plan, stub, or AC row that carries `UNCERTAIN` / `TBD` / `unclear` in a status field is an undelegated decision wearing a status label, not a legitimate state. Resolve it (decide, or grep the substrate) before the plan reaches a PM gate or review — a PM gate is not the place to discover the author never made a call. Source: 2026-05-18 project-rag.

**Plan over brainstorm when the PM has set the architectural axiom.** Once the axiom is PM-set, remaining ambiguity is classification-with-rationale work that belongs in plan Decision blocks for PM ratification — not open-ended brainstorm dialogue. Heuristic: if (a) axiom is set, (b) scouts have produced an evidence base, and (c) ambiguous calls are classification-shaped (not architecture-shaped), skip directly to plan. The review pipeline (prior-art-checker → named reviewer → integrator) catches real substrate failures and scope refinements that brainstorming wouldn't surface any faster. Source: 2026-05-27 project-rag-ue-addon.

## Pre-dispatch confidence checklist

Before dispatching a build-task agent or entering plan mode for a non-trivial feature, walk through these seven gates. Any "no" demands more investigation, not bigger agent dispatch. NOT a numeric score — the checklist is the gate.

1. **No duplicate.** Have I greped for an existing implementation under nearby paths? **(See `Negative-Search Before Drafting` below for the formal greppable procedure.)**
2. **Architecture-compatible.** Does the proposed approach use existing project conventions (tech stack from CLAUDE.md, patterns from atlas)? If introducing a new dependency, is the rationale in the plan? **(See `Codebase Research (before file mapping)` above for the survey discipline.)**
3. **Official docs read.** For any external API the plan calls into, have I read the actual signature — not relied on training memory?
4. **Reference impl seen.** For any nontrivial pattern, can I point to a working implementation (OSS or in our codebase) that demonstrates it? **(See `Codebase Research (before file mapping)` above.)**
5. **Root cause known (bugs only).** For bug fixes, do I have evidence the diagnosis is correct, not just plausible?
6. **No-fabrication.** For any plan asserting on a frontmatter key, env var, config field, or schema column, have I greped for the literal field name? (See § Negative-Search Before Drafting.)
7. **Fix-locus discrimination.** For each proposed patch, have I identified the upper-layer registry/dispatch/extension site by `file:line` and named a concrete reason patching the upper layer is wrong? (See § Fix-locus discrimination.)

All seven green → dispatch. Any red → loop back to investigation tier 1-3 or escalate to PM.

**Validation floors derive from emission shape, not author intuition.** Setting `≥N items emitted` as a gate when N is chosen by feel produces false-negatives (gate passes on a near-empty output) and false-positives (gate blocks a legitimately sparse but correct result). Before writing a count gate, trace the emission path: identify the producer loop or query and derive the minimum expected output from the logic, not from a gut estimate. Source: 2026-05-14 project-rag-ue-addon.

**Default to EXTEND when an extension point already has detection helpers wired.** When a plan proposes new behavior that an existing hook, validator, or skill could carry — and that surface already has the detection/parsing/dispatch helpers the new behavior needs — extend it; do not fork a sibling. Forking doubles blast radius and creates a drift surface between two near-identical detectors. This is the plan-time twin of `coordinator/CLAUDE.md` § Implementation Standards "Refactor over patch" and the location-challenge in § Negative-Search Before Drafting (point 5): the cheapest locus is usually the surface that already detects the class. Source: 2026-05-23 self.

**Sibling-team archive memos collapse cross-repo coordination cost.** When sizing cross-repo work, READ sibling-team `archive/*proposal*` / `*coordination*` / `*authority*` memos before estimating bump cost. Tri-repo ratification is often over-cost for unilateral-authority shapes already established in a peer's archive — the authority decision may already be made and the bump is unilateral. Skipping the archive read produces inflated complexity estimates and unnecessary PM escalations. Source: 2026-05-15 claude-unreal-holodeck.

## Domain Language

Read `CONTEXT.md` if present at the project root; if absent, proceed silently — do not flag, suggest, or scaffold. Use canonical terms throughout the plan — and for any term on the `_Avoid_:` lists, substitute the canonical term silently. If the plan introduces a new domain term that will recur across sessions, append it to `CONTEXT.md` as part of the plan-writing pass.

## Codebase Research (before file mapping)

<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
**Project-rag is project-scoped.** It indexes ONE specific codebase, configured at install time. Before reaching for `mcp__*project-rag*` tools, confirm they index the codebase you're investigating — not a different project on the same machine. If your target codebase doesn't have a project-rag index (no `Saved/ProjectRag/` marker at its root, no `--project-root` argument pointing at it in the MCP config), skip this preamble entirely and use grep/Explore.

**If MCP tools matching `mcp__*project-rag*` are available AND they index the codebase you're investigating, prefer them over grep/Explore for any code-shaped lookup.** Symbol-shaped questions ("where is X defined", "find the function that does Y") → `project_cpp_symbol` / `project_semantic_search`. Subsystem-shaped questions ("how does X work") → `project_subsystem_profile`. Impact questions ("what breaks if I change X") → `project_referencers` with depth=2. Stale RAG still beats grep on structure. Fall through to grep/Explore only if RAG returns nothing AND staleness is plausible.
<!-- END project-rag-preamble -->

Before defining the file structure, check what's already been documented about the relevant systems. Read these if they exist (skip silently if they don't):

1. `docs/architecture/systems-index.md` → relevant system pages in `docs/architecture/systems/`
2. `docs/wiki/DIRECTORY_GUIDE.md` → relevant wiki guides in `docs/wiki/`
3. `tasks/repomap.md` (or task-scoped variant)

This gives you the structural context to make informed file-mapping decisions without redundant grep discovery. Use Glob/Grep after this to fill specific gaps — exact line numbers, recent additions not yet in the atlas, etc.

**Substrate-verification at plan time.** Verify substrate facts (file paths, framework names, helper APIs, line numbers) via `ls`/`grep` while authoring — not at completion. Two minutes of disk verification prevents the substrate-fact errors reviewers will catch on R1.

**Reviewer pre-resolved substrate values need executor `ls` confirmation.** A reviewer citing a `@import` path as authority for a manifest `functional_probe.path` field is hypothesis based on indirect evidence — the `@import` is the local-install path; the manifest's path field is schema-defined as repo-source path. Reviewer pre-resolution is never authoritative on schema-distinct fields. Pre-resolution of any path-typed field requires an executor `ls` confirmation step in the plan. Source: 2026-05-08 project-rag.

**A reviewer-named architectural seam is substrate to verify, not a literal mechanism to execute.** When a reviewer names a seam ("route through the `run_consumers()` gate", "this belongs on the host envelope") the plan author treats it as a *pointer to substrate to grep*, not a verbatim API to wire. The reviewer named the seam from their reading, not from disk; the actual symbol, signature, or registration shape at that seam must be confirmed by grep before the plan body cites it. Transcribing a reviewer's seam-name as if it were the literal callable is the same fabrication class as citing an unverified field. Source: 2026-05-19 project-rag.

**Periodic baselines drift — instruct read-current-and-increment, not match-spec.** When a stub names a count, version, or baseline ("bump from 55 to 56"), absolute values rot between enrichment and execution. Phrase as "read current value and increment" so the math survives the gap.

**Plunge vs. plan split by substrate certainty, not appetite.** Verified-on-disk parts of a workstream may plunge directly to execution. Parts that depend on foreign-repo substrate (paths, APIs, schema fields in a sibling repo you haven't grepped) require a plan with an explicit verification step before execution dispatch. Certainty is the gate, not effort estimate. Source: 2026-05-18 project-rag.

**Satisfy schema constraints by construction before relaxing.** When a closed-enum schema gate appears to block a new entity type, ask "can the producer satisfy the constraint?" before "should we relax the constraint?" Relaxation carries cross-consumer blast radius; satisfaction by construction is local and reversible. Document the construction path in the plan before entertaining schema changes. Source: 2026-05-15 claude-unreal-holodeck.

- Scaffolded config files (templates the plan instructs an executor to write) must self-disclose which fields they actually support — silent ignoring of unrecognized fields breeds downstream debugging cost. Plans citing config templates should require the template carry a `# Supported fields:` comment listing the keys.
- Plans extending an existing pipeline (e.g. adding a new wave to /distill, a new phase to /update-docs) MUST grep the pipeline's existing scratch-path conventions before declaring output paths — silent collision with sibling waves' scratch namespaces breaks parallel safety.

**Doctrine constants claiming an empirical basis MUST cite the dated incident — un-cited "observed threshold" numbers are folklore.** When a plan (or a doctrine/wiki rule the plan introduces) states a numeric constant as if measured — a concurrency cap, a timeout, an RSS ceiling, a "we've seen N crash" threshold — it must carry the dated incident that produced the number. An un-cited "observed threshold" reads as empirical to every downstream EM and makes them over-comply with a number nobody actually measured. The 2026-05-30 case: a 6–8 concurrent-executor cap circulated as an observed crash threshold with no recorded crash behind it. Rule: every doctrine constant is either (a) cited to a dated incident/measurement, or (b) flagged explicitly as a heuristic default ("heuristic, not measured") — never bare. Source: 2026-05-30 self.

**TEMPLATE blocks with substrate-divergent specifics are worse than no TEMPLATE.** Concrete assertions in TEMPLATE blocks (file paths, version strings, flag names, count thresholds) must be substrate-checked at plan-time, or stripped to truly skeletal pseudocode. A TEMPLATE that carries specific values not verified on disk becomes a fabrication vector — executors treat TEMPLATE content as authoritative. Pre-review audit: walk every concrete value in a TEMPLATE block and confirm it against `ls`/grep, or replace with a `<placeholder>` that forces the executor to resolve it. Source: 2026-05-16 project-rag.

## Negative-Search Before Drafting

Before committing to a prescribed shape, run a negative search to surface prior decisions that argue against what the plan proposes to introduce or restore.

**No-fabrication branch — predicates citing fields must grep the field first.** A plan or predicate that asserts on a frontmatter key, env var, config field, or schema column without grepping for the literal name is fabrication, not verification. Extends the no-duplicate dimension into no-fabrication: *does the named field exist on disk?* Before writing any trigger gate, abstain condition, or rule that references a structured data field (`outcome:`, `status:`, `kind:`), grep the schema definition (e.g., `schemas/handoff.yaml`, frontmatter validator) and quote a file:line citation. Absence of a grep citation against the schema is a plan smell. Source: 2026-05-07 external-pattern-checker plan trigger-gate cited a non-existent `outcome: failed` field on handoff schema (enum is `active | consumed | superseded`); the gate would have fired on EM mood, not signal. Greppable from `coordinator/CLAUDE.md` § Pre-Dispatch Verification (`no-fabrication`).

1. **Identify the central nouns/abstractions** the prescription introduces or restores (e.g., a pattern name, an architectural layer, a specific tool or verb).

2. **Search for those nouns paired with prohibition vocabulary.** Grep `tasks/lessons.md` and `docs/wiki/` for each noun alongside: `do not`, `never`, `tear down`, `deprecated`, `forbidden`, `removed`, `do NOT`. `bin/query-records` is also useful here for frontmatter-indexed records.

3. **If a prohibition exists, the plan must do one of two things:**
   - **(a)** Acknowledge the prior decision in §1 Objective and explicitly justify the reversal — with reasoning that engages the original argument, not merely reasserts the new direction.
   - **(b)** Recuse the prescription and choose a different shape that does not conflict with the prior decision.

4. **Reversal-verb hint:** If §1 Objective uses any of `restore`, `reintroduce`, `reconstitute`, `undo`, `re-add`, or `bring back`, the plan author should *consider suggesting* a staff-session to the PM before approval. This is a suggestion only — the PM owns the call. Frame it as: "This plan reverses prior direction; PM may want a staff-session before approving execution."

5. **External-doctrine proposals — independent location-challenge.** When a peer audit or external review recommends a fix, never adopt the proposed *location* uncritically — proposals frame fixes from where they noticed the problem, which is rarely the cheapest place to apply them. Run an independent location-challenge before drafting: would an upstream surface (producer skill, hook, dispatch template) prevent the class of problem more cheaply than the proposed downstream patch?

**Index/overview doc enumeration is NOT authoritative on a target file's actual headings.** Before dispatching against a named section in a multi-file refactor keyed off an overview or pipeline doc, grep the target file's own headings (`grep -nE '^#+ ' <target-file>`) and confirm the section exists. A PIPELINE overview lists phases; it is not a manifest of any one file's internal section structure. Full treatment: `docs/wiki/pre-dispatch-verification.md` § Index/Overview Docs Are Not Authoritative.

*Source: 2026-05-28 claude-central (distill-manifests fan-out; plan modelled sections from PIPELINE.md phase-overview table).*

**Versioned-token plans must name the axis, not just the token.** When multiple distinct version concepts share a token spelling (e.g. three `SCHEMA_VERSION` constants — DDL/on-disk, consumer-graph, addon-protocol — coexisting in one tree), a plan that bumps "the SCHEMA_VERSION" without naming *which axis* will edit the wrong one or all three. Grep the literal token, enumerate every definition site, and state in the plan body which axis the change is on. This is the no-fabrication discipline applied to ambiguous-token identity, not just field existence. Source: 2026-05-19 project-rag-ue-addon.

**Plan-substrate CLI verification via `--help` / argparse grep.** When a plan cites a script's CLI flags, require a `--help` excerpt or `argparse.add_argument` grep in the plan body — source-range inspection misses the actual surface. Reviewing the source file for argument *definitions* is insufficient; flag names surfaced to callers are in the `add_argument` call strings, which may differ from internal variable names. The Staff Engineer-level reviews have missed invalid flags this way. Source: 2026-05-14 project-rag (`--source engine --authority engine` cited in plan were not valid flags).

**Remediation prose must name a command that BOTH exists AND performs the named action — verify existence *and* behavior.** When a plan's gate, runbook step, or recovery clause tells the executor to do something via a named slash-command, flag, or script ("stop the daemon via `/doctor --fix`", "reset state with `--clean`"), grep that the named primitive exists AND read what it actually does before hard-coding it. Existence is half the check: a primitive can exist and do the *opposite* of the named action. The 2026-05-30 case: a plan gate said "stop the daemon via `/doctor --fix`" — but no daemon-stop `--fix` existed, and the real `--fix` *restarts* the daemon, so the remediation would have done the reverse of what the gate intended. This extends the `--help`/argparse existence check above with a behavior check: confirm the primitive's effect matches the verb the prose assigns it. Prefer naming a dedicated script with a single unambiguous effect over a composite verb (`--fix`, `--repair`, `--reset`) whose behavior is broad and unconfirmed. Source: 2026-05-30 project-rag.

**Grep existing test fixtures before prescribing new ones.** Plan-write substrate verification must `ls tests/_*_fixture.py` and `grep -l "<symptom symbol>" tests/conftest.py tests/_*_fixture.py` before prescribing a NEW fixture. Canonical fixtures frequently ship before the plan that needs them — a plan that authors a duplicate fixture wastes executor time and creates a drift surface between two near-identical helpers. Rule: if a match exists, cite it as the canonical fixture; if absent, scaffold a new one. The fixture search is the same no-fabrication / no-duplicate check applied to the test layer.

*Source: 2026-05-28 project-rag (tasks/lessons.md:5).*

**Verify prereq-cited banks/baselines with a dry-scorer/dry-validator pass before consuming downstream.** Handoff prereqs naming a specific class of artifact (smoke bank, graded bank, scored baseline) need a dry pass before leg 1 of the consuming workstream runs end-to-end. Without the dry pass, the consumer silently operates on a mismatched input class and produces subtly wrong outputs that pass all structural checks. Source: 2026-05-17 project-rag.

**Registrar-bound callables read like globals — grep the registration shape before asserting invocation counts.** Before drafting a plan whose fix slate cites N invocations of a callable like `foo()`, grep the registration shape (`def register_*`, FastMCP `register_*_tools`, FastAPI `Depends`, pytest fixtures) for `foo` as a *parameter* — a global-looking identifier at a call site may be bound at registration time by production wiring (e.g. `register_live_tools(mcp, get_project_root, …)` bound to `lambda: _effective_project_root()`). Grepping the literal name confirms the name *exists*, not what it *resolves to*; read the production call site that constructs the registrar args. plan-coverage-checker misses this — it verifies token presence at cited lines, not the symbol's binding. Source: 2026-05-21 project-rag (a plan asserted "10 boot-pinned `get_project_root()` sites" that were already parameter-bound and correct; would have shipped a duplicate of already-shipped code).

**Content-migration inbound-link greps must enumerate every citation form.** For any cross-repo / mass-delete content migration, the inbound-link grep pattern MUST enumerate all three markdown ref shapes per target — absolute (`docs/wiki/name.md`), bare-name (`name.md`), and self-relative (`./name.md`) — not just the absolute-prefix form. Markdown ref resolution is per-source-file relative, so the same target appears in 3+ shapes across the tree; a writer-mental-model grep ("how the path appears in MY edits") misses the reader-mental-model shapes. Source: 2026-05-23 holodeck W6b PRUNE — an absolute-prefix-only grep let 25 broken links escape to the final gate.

**When porting a pattern from a reference impl, verify every flag, path, and command-name against the TARGET repo.** Reference implementations carry environment-specific tokens — flag names, path conventions, command-name aliases — that are correct for the reference but may not exist in the target. Before dispatching an executor based on a reference-impl port, grep the target repo for each flag and path cited in the plan to confirm they exist there. Operator-doc attribution (e.g., which skill or hook owns a phase) must come from the target's live routing table, not from the reference's documentation. (Source: 2026-05-24 project-rag)

**Deleting a vendored or shared constant requires grepping its re-export (back-compat shim) sites, not just direct importers.** A `from module import CONST` grep finds direct importers; it does not find modules that re-export the same constant for backward compatibility (`from original import CONST; __all__ = ["CONST"]`). A re-export shim hides the deletion's blast radius — downstream consumers of the shim break silently after the delete lands. Before any constant-or-symbol deletion, grep for the literal name in `__all__`, `from X import Y as Z`, and `importlib.import_module` patterns across all modules, not just the primary call sites. (Source: 2026-05-24 project-rag)

**Durability assertions over a multi-writer file must enumerate ALL writers.** An assertion like "this file is durable across restarts" is quantified over every path that can write or overwrite the file. Single-writer coverage of a multi-writer surface produces a silently-false durability claim: if any writer resets the file, the durability contract is broken regardless of how careful the one covered writer is. Before asserting durability, grep for every writer of the target file (open for write, atomic rename, truncate+write) and enumerate them in the plan body. (Source: 2026-05-24 project-rag)

**Vocabulary substitution instructions must be verified against the authoritative project glossary before mass-rename dispatch.** When a brief instructs X → Y vocabulary substitution, grep the project's `CONTEXT.md` (or canonical glossary document) first. The glossary may already reserve Y for a different concept, making the substitution a collision; or it may list X as a deprecated alias that maps to a different canonical term than Y. A mass-rename dispatched against an unverified substitution ships the collision into every occurrence. Require a glossary-diff step in the plan before any rename wave. (Source: 2026-05-24 project-rag-ue-addon)

**Vacuous-true is not an AC pass.** When an acceptance criterion turns out vacuous at close-out time — the seam it was designed to exercise has moved, or the criterion reduces to a trivially-satisfied structural check — either re-anchor it to the moved seam or surface it as a stub-quality finding. A criterion that passes because nothing is checked is not evidence of correctness; it is evidence of an unverified requirement. The plan-coverage-checker's "vacuous-pass" bucket is the mechanical signal; the resolution is always re-anchor or open-finding, never mark-closed. (Source: 2026-05-24 project-rag-ue-addon)

## Fix-locus discrimination

<!-- Review: code-reviewer — structural displacement fix (F2): moved Fix-locus discrimination to after the full Negative-Search procedure so the numbered 1-5 list correctly reads under its own heading. Dimension question label dropped and folded into Green clause (F3). Tier 2 narrowing broadened to Tier 1–3 (F4). -->

**Green — this is the right layer to patch.** Planner has identified the upper-layer registry/dispatch/extension site by `file:line` (one level above each proposed edit site) AND can name a concrete reason patching the upper layer is wrong (registry already gates this case; upper layer is closed contract; upper layer is hot-path with unrelated callers).

**Red:** planner cannot articulate why the upper layer is the wrong locus, OR the upper layer already has the gate type the patch would re-implement at the call site.

**Action on red:** loop back to Tier 1–3 investigation on the upper-layer mechanism before drafting the plan body.

**Worked example** — 2026-05-19 python-first-class-corpus-closure plan, the Director of Engineering standalone review F1/F2/SI-1:

- **(a) Patch-shaped fix as proposed:** threshold patch inside `consumer_runner.py:547` (`_run_embed_cpp_chunks`) — skip chunks below threshold inside the embedder.
- **(b) Upper-layer surface that should have been amended:** the `run_consumers()` substrate-applicability gate one level up — refuses to dispatch the embedder when no applicable substrate exists, making (a) redundant and fragile.
- **What would have flipped green→red:** identifying (b) by `file:line` during Branch B would have returned Red — forcing Tier 1–3 investigation before the plan body was drafted. Instead, the prior checklist returned all-green on a patch-shaped plan where an upper-layer refactor was correct.

**Failure mode prevented:** the prior checklist returning green while the plan is patch-shaped at a call site where an upper-layer gate exists or should exist.

**Cross-references:**
- `coordinator/CLAUDE.md` § Pre-Dispatch Verification, "Audit symptom is correct; locus may be wrong" — conceptual ancestor, firing at investigation time.
- `coordinator/CLAUDE.md` § Pre-Dispatch Verification, "Reviewer rationale must discriminate between the chosen shape and its alternatives" — analogous discipline at review time.

Fix-locus discrimination fires **between** them: at plan-author time, after substrate verification, before the first task is drafted.

**A fork arm that rests on an external binary is only as real as that binary RUNNING on the target platform — verify it RUNS before ranking the fork.** When a plan weighs two or more approaches and the "precise" / "architecturally correct" arm depends on an external CLI or binary (a language-server indexer, a transpiler, a vendored analysis tool), that arm's cost is contingent on the binary actually executing on the target OS — not on its existence in a package registry. Before letting the dependent arm weight the decision, run `--version` (or a minimal invocation) on the target platform and check installed-vs-latest plus any known platform breakage. If the binary crashes or is unavailable, the "correct" arm is DOA, and the cost of vendoring/patching upstream must go in *that arm's cost column* before you choose — otherwise the ranking inverts the moment the executor discovers the binary doesn't run. The 2026-05-30 case: scip-python 0.6.6 (latest) crashes on Windows, so the "architecturally correct" arm that rested on it was dead on arrival; ranking it as the winner without a `--version` check would have inverted the recommendation. **Distinct from the runtime-degrade external-CLI-producer rule** in `implementation-standards-by-domain.md` (a producer that degrades at *runtime*): this is verifying a *candidate* binary runs *at plan-time* before its availability weights a fork-ranking decision. Source: 2026-05-30 project-rag.

## File Structure

Before defining tasks, map out which files will be created or modified and what each is responsible for:

- Design units with clear boundaries and well-defined interfaces
- Prefer smaller, focused files over large ones doing too much
- Files that change together should live together — split by responsibility, not technical layer
- In existing codebases, follow established patterns; include splits for unwieldy files when reasonable

This structure informs task decomposition — each task should produce self-contained changes.

**Factor shared interfaces into their own chunk.** (A *chunk* here = one executor-sized unit of work — see § Bite-Sized Task Granularity below.) When several chunks will consume a *new* shared surface — a helper, a kwarg, a schema field, an envelope extension — do NOT bundle that surface into one consumer chunk alongside its other work. Welding the shared API to one consumer makes the parallelism invisible: every *other* consumer now appears to depend on the whole fat chunk, when it actually depends only on the interface. Draw the shared surface as its own minimal chunk (`C0`) and pin its interface. The consumers then fan out against it — concurrently by default (the producer runs in the same wave; verification concentrates at merge), or after `C0` lands as a predecessor wave when the interface can't be confidently pinned. See `dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy (Author vs. verify) for the default/fallback call.

This is the **plan-time twin** of the dispatch-time "promote shared-API to a predecessor wave" rule (`dispatching-parallel-agents.md` § Shared-API Gap). That promotion is only *drawable* if the plan didn't already bury the interface inside a consumer — by dispatch time, the fat chunk has already collapsed the fan-out. Catch it here, at chunk-drawing time.

**Test:** if extracting one chunk's shared-surface work would unblock *two or more* other chunks to run concurrently, that surface belongs in its own chunk. Empirically (2026-05-27, self): `C1` was drawn as "extract `host_probes` + rewire one consumer + add the kwarg + land the regression net" — the shared interface (`host_probes` + kwarg) welded to one consumer (the rewire). Every other consumer then read as "depends on C1" wholesale; the trivial `C0`-then-fan-out shape was never surfaced.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

**Additive-before-destructive ordering.** When chunks are file-independent and one is purely additive while another removes existing code, land the additive chunk first. The destructive chunk's regression window shrinks because the additive piece is already in the codebase — reviewers and tests can verify behavior before removal, not after.

- Order chunks additive-before-destructive — scaffolding/new-symbol chunks land before delete-old-symbol chunks. A destructive chunk that lands before its replacement is staged risks a broken intermediate state on rollback.

**14-minute single-executor run signals under-decomposition.** When an executor's observed wall-clock time approaches or exceeds 14 minutes, that is a structural signal — the chunk spans multiple distinct surfaces or concerns and should have been split further. The target per-executor budget is ~5–10 minutes on ONE coherent surface (15-minute hard ceiling). If a plan chunk would exceed this in practice: split before dispatch, not after the executor stalls. Empirical: a 14-min run on project-rag indexing + fixture authoring + CLI wiring = three surfaces welded into one chunk; splitting each surface separately cut the longest executor to 8 minutes. Companion to `coordinator/CLAUDE.md` § Subagent Dispatch HARD RULE ("small-remit-and-many beats large-remit-and-one, every time").

*Source: 2026-05-28 project-rag (tasks/lessons.md:1395).*

**Scaffolded config files must self-disclose their supported subset.** A scaffolded config in a familiar format (`.gitignore`-shaped, JSON-schema-like, INI) must declare which subset of the format is actually honored in a header comment — OR the plan must instruct the executor to implement the full format. Catch at plan-time by walking the proposed default body through the matcher implementation. (Surfaced by `/percolate`'s `.percolate-ignore` shipping `**/scratch/` as dead code — the bash `[[ ]]` matcher didn't handle `**/`.)

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Status:** Pending review

**Scope mode:** [prototype | production-patch | feature | architecture | spike]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

## Acceptance Criteria

<!-- For plans going through coordinator:review, use the bindable table form below.
     Trivial/unreviewed plans may keep simple prose checkboxes.
     Full doctrine: § Acceptance Oracle (outer-loop) below. -->

| ID | Criterion (prose — pre-review) | Test (typed-prefix) | Binding-Class | Status |
|----|--------------------------------|---------------------|---------------|--------|
| AC-1 | [Pre-review prose, testable-shaped] | `pending realization` | gate-bound | ☐ |
| AC-2 | [Tone/shape criterion the reviewer judges] | `reviewer-judgment` | reviewer-judgment | ☐ |

## Non-Goals

- [Explicitly out of scope — heads off mid-stream scope creep]

---
```

**Why these fields are required:**
- **Scope mode** routes review depth and the evidence bar. Reviewers and `/merge-to-main` read it.
- **Acceptance criteria** are what reviewers check against and what the ship verdict scores. Without them, "done" reduces to "the agent says it implemented it." For plans going through `coordinator:review`, the prose checkboxes upgrade to a bindable table with binding-class and typed-prefix Test cells — see § Acceptance Oracle (outer-loop) below.
- **Non-goals** are the most-skipped field and the single highest source of scope drift. Spend 30 seconds on them.

The `Status:` field is part of the write-ahead protocol — it gets updated at every phase transition (review, enrichment, execution) so that crashed sessions leave unambiguous state. See ARCHITECTURE.md § "The Write-Ahead Status Protocol" for the full state machine.

**`## Deviations` is auto-appended at session completion — do not hand-author it.** When the session's work was governed by this plan and the implementation deviated from the plan's forecast, `/session-end` Step 2.4 appends a `## Deviations` audit table and corrects the affected ALLOWLIST sections in place. This section is provenance-only and intentionally non-crystallized — `/distill` drops it as `[EPHEMERAL]`. Writing your own `## Deviations` section before session-end will conflict with the auto-append. → `docs/wiki/plan-deviation-reconciliation.md` for the full format and contact-point contract.

## Acceptance Oracle (outer-loop)

> Spec: `archive/specs/2026-05-24-acceptance-oracle-with-teeth.md`. Sibling doctrine: `docs/wiki/test-driven-development.md` § Two loops.

When a plan goes through `coordinator:review`, its `## Acceptance Criteria` section is bindable: each row links to a named executable test that the *green-gate* runs at the merge boundary. This is the **outer loop** of test-driven development (acceptance-test-driven at the plan boundary), distinct from — and complementary to — the inner red-green cycle the executor runs per function.

**Gate predicate (no new predicate; rides the existing review trigger):** a plan that warranted a review warrants verifiable exit criteria. Trivial/unreviewed plans keep prose checkboxes or nothing.

### Two-altitude flow

`plan draft (prose criteria) → coordinator:review (reviewer reads criteria as a design lens — unphraseable criterion ⇒ underspecified spec) → realize each as a named FAILING test → implementation → tests green → done-gate`.

**"Post-review" means after the *plan* review, not the *code* review.** The acceptance test is still authored before its implementation — test-first at the acceptance altitude, compatible with the inner-loop discipline. State this explicitly so "post-review" is never read as licensing tests-after-code.

### AC binding-class

Every AC row carries one of two binding classes:

- **`gate-bound`** — the Test cell is a typed-prefix expression the gate dispatcher can execute. The acceptance gate enforces this row: a red or missing test blocks the done-verdict at the merge boundary.
- **`reviewer-judgment`** — the criterion is about tone, shape, or semantic quality that no mechanical test can confirm. The gate does NOT bind this row; it is the persona reviewer's lens at plan review. Presence-grepping a subjective criterion would produce a proxy that passes trivially — that is the prose-checkbox failure the acceptance oracle exists to kill.

The gate binds the bindable; the reviewer owns the unbindable; neither pretends.

### Typed-prefix test-cell scheme

The gate dispatches on a prefix tag in the Test cell:

| Prefix | Runner | Example |
|--------|--------|---------|
| `pytest:path::nodeid` | pytest | `pytest:tests/test_oracle.py::test_gate_fires` |
| `node:path -t name` | node:test or Jest | `node:tests/oracle.test.js -t "gate fires"` |
| `cargo:module::test` | cargo test | `cargo:oracle_tests::gate_fires` |
| `grep:pattern@path` | bash grep | `grep:acceptance oracle@docs/wiki/writing-plans.md` |
| `cited:ref` | citation validator | `cited:abc1234` or `cited:logs/run-2026-05-24.txt` |

Adding a new language runner requires only a new prefix branch in the gate dispatcher.

**`grep:` multi-path semantics.** A `grep:pattern@path1,path2` cell requires the pattern to match in **every** listed path (all-must-match). A criterion asserting a fact across N files binds to a test that fails if any one file is missing it — closing the single-file-grep-passes-while-half-the-criterion-unmet hole.

**Path convention.** Test-cell paths resolve from the gate's invocation cwd, which is the **project root** for the normal `coordinator:merging-to-main` Step 0a invocation. Use repo-root-relative paths in Test cells (e.g. `plugins/foo/docs/wiki/X.md`, not `docs/wiki/X.md`, when the file lives inside a plugin). Surfaced empirically by the 2026-05-24 dogfood — 9 of 9 gate-bound ACs went red on the first run because the plan used plugin-relative paths; updated Test cells to repo-root and the gate flipped to all-green in one iteration.

**`cited:` validation.** A `cited:` cell is NOT a free-text bypass. The gate validates that the cited ref resolves: a commit SHA must exist in the local git history, or a run-log path must exist on disk. If the ref does not resolve, the gate treats the row as red. Successful citation is logged loudly in the verdict ("AC-N satisfied by citation `<ref>` — NOT re-run on this host"), enabling human inspection. Prefer the citation be present at plan-review time so the reviewer saw it.

### Executor-split-by-test-altitude

Dispatch-graph doctrine: at `coordinator:execute-plan` Phase 1.5, the EM decides which executor authors which test class.

- **Acceptance/regression tests** (contract-derived; the contract is fixed by the reviewed plan) → separable into a dedicated executor or front-loaded as a predecessor wave. No design loop to split because the contract is already settled.
- **Inner unit tests** (implementation-coupled to the code) → stay with the code executor. Splitting reintroduces the two-agents-guessing-one-interface hazard; the inner-loop discipline already governs these (see `test-driven-development.md`).

### Green-gate seam topology

The acceptance-oracle gate runs as **authoritative** at `coordinator:merging-to-main` Step 0 — the merge choke point: oracle-bearing plans with red/missing gate-bound tests hard-block the merge via non-zero exit. It runs as **early, non-authoritative feedback** at `coordinator:execute-plan` Phase 4 and `coordinator:finishing-a-development-branch` (advisory only — agents see red tests early and iterate before the merge boundary). `/session-end` and `/workday-complete` emit offer-shaped notices, never hard blocks (they are not merges). Direct `git push` / `git merge` outside the skill, and CI pipelines, are intentionally not gated here — the merge-boundary skill is the choke; CI is a separate infrastructure concern.

Gate mechanism: `check-acceptance-oracle.sh <plan-path>`. Override: `COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1` skips the gate (exceptional use; `cited:` is the routine accommodation). Registered in `docs/wiki/coordinator-tripwires.md`.

**Pool-exhausted floor doctrine.** When a density-floor plan ("N rules per class; accept N-1 if visible-corpus density is constrained") survives review with rule drops, the floor may need to ratchet to N-2 if the visible-entry pool is exhausted — no replacement candidates exist after the drop. Distinct from the initial density-constraint case: pool-exhausted means "entries are used up AND a drop just landed AND no swap exists." Amend AC language explicitly with "accept N when pool exhausted" rather than letting the floor drift silently; a silent floor drift fails the AC gate on a compliant submission. Source: 2026-05-27 project-rag-ue-addon.

**LIKE-pattern AC tables mask separator/normalization bugs.** Any AC table for an artifact that carries paths must include at least one full-path-equality assertion AND one read-time-consumer-output assertion (live-source, live-signature, drift-detection populated) — not only LIKE-shaped queries. LIKE predicates don't care about separator characters in the prefix; three live consumers were silently broken on path comparison while the customer-sim AC table passed clean. Source: 2026-05-28 claude-unreal-holodeck. (Companion: `verification-discipline.md` § Acceptance-criteria authoring.)

### Tier acceptance by layer to ship the verifiable part independently

When a plan spans a layered routing system (request → router → handler → backend, or addon-protocol → host-envelope → consumer), the acceptance criteria should be tiered by layer rather than bundled into one all-or-nothing end-to-end gate. Bind the layers you can verify on the available substrate as `gate-bound` and ship them independently; mark the layer that needs hardware/topology you don't have as `reviewer-judgment` or `cited:` with the gate named. This lets the verifiable slice land and merge while the unverifiable layer is honestly flagged, instead of one coarse e2e AC blocking the whole plan on the least-reachable layer. Source: 2026-05-19 project-rag-ue-addon. (See § Close-Out Chunks Cite Specs for the citation discipline on the unreachable layer.)

### Design philosophy — teeth at the verdict, offers everywhere else

The acceptance oracle forks the *carrot* of TDD (executable definition of done) without the Superpowers *stick* (see global `~/.claude/CLAUDE.md` § design-as-offers and `docs/wiki/eager-agent-calibration.md`). **Teeth are correct at exactly one place — the non-zero exit code at the done-verdict** — because a false "done" is the failure we exist to prevent. Authoring, realization, messaging, and every upstream surface are offer-shaped. The exit code is teeth; the message is carrot; the two are strictly orthogonal (never soften the exit code to match the friendly tone).

**Teeth at the backstop license carrots upstream.** Because the merge-boundary gate is hard, every upstream surface (oracle authoring, test realization, executor reports) can lead with the better alternative rather than imperatives — any discipline lost upstream is recovered at the authoritative gate before "done" can be declared. This is the general principle the acceptance oracle instances.

**A calibration layer is necessary but not sufficient — plan the enforcement layer alongside it.** When a plan introduces a *calibration* mechanism (a preamble, a doctrine note, a substrate convention that asks agents to do the right thing), first-instance dogfood reliably shows calibration alone leaks: some fraction of runs ignore the soft guidance. Ship the *enforcement* layer (the hard gate, the hook that fails loud, the validator) in the same plan, not as a deferred follow-up. The acceptance oracle is the canonical instance of this duality — calibration upstream, teeth at the verdict — but the rule generalizes to any calibration-shaped mechanism a plan proposes. Source: 2026-05-20 claude-central.

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## Bypass-and-Trace Discipline

> See coordinator/CLAUDE.md § Pre-Dispatch Verification for the pre-dispatch confidence checklist.

When a plan targets a gated path (MCP verb, hook, build system, auth flow) and the first fix unblocks one gate but reveals a second, **the correct response is to trace the full path before claiming the fix is complete**, not to ship after clearing gate one.

**Principle:** bypass one gate, trace the full path. Fixes that target a single gate often reveal the next gate immediately downstream — stacked-gate diagnosis is empirically common in UE plugin pipelines, MCP auth flows, and coordinator hook chains.

**In plans:** when a task's acceptance criterion is "passes gate X," include an explicit verification step that walks the full downstream path (not just the gate being targeted). If gate X passes but gate Y blocks, the AC is not met.

**Measurement loop (P4):** if repeated fixes keep hitting the next gate, you're in a stacked-gate scenario. Shift the plan to "enumerate all gates in this path before writing any fixes" — one investigation pass at the start is cheaper than N sequential fix-and-reblock cycles.

## Digression Governance

> See coordinator/CLAUDE.md § Plan-First Workflow for the plan-first doctrine this governs.

Digression from a proven path requires EM approval before the executor proceeds.

**Proven path:** a file:line cite or a verb with known input/output contract that the plan specifies as the canonical approach.

**Digression:** an executor chooses a different primitive sequence because the proven path hit an unexpected obstacle, or because the alternative "looks simpler."

**Protocol when a digression arises:**
1. **Name the proven path** — cite it by file:line or by verb + expected input/output signature.
2. **Describe the specific mismatch** — what exact input/output gap makes the proven path inapplicable here?
3. **Name the alternative** — describe the proposed alternative sequence explicitly (not just "a different approach").
4. **Get EM sign-off** before proceeding.

Silent digression — choosing the alternative without surfacing steps 1–3 — is a doctrine violation. The proven path is proven because it was tested; the alternative is unproven even if it looks equivalent.

**In plans:** for any step that relies on a canonical MCP verb or established pattern, include a "No fallback" clause (see § Hard Constraints (e)) so executors cannot silently digress under pressure.

## Spike Pass-Conditions Must Match the Wire Path

> See coordinator/CLAUDE.md § Plan-First Workflow and `docs/wiki/round-trip-contract-tests.md` for the round-trip framing.

Spike acceptance criteria must target the actual wire path being verified — not a structural proxy that appears to prove the same thing.

**Failure shape:** spike AC is "registration succeeds." The executor verifies that the module is registered (a static lookup passes). But registration ≠ functional initialization — the registered module may still fail to initialize at runtime (missing deps, incorrect boot order, missing env bindings). The spike returns green on registration; the runtime surface returns broken.

**Rule:** for any spike whose goal is "does X work end-to-end," the pass-condition must exercise the runtime wire path, not just the structural registration. Ask: "could this AC pass even if the runtime path is completely broken?" If yes, the AC is measuring the wrong thing.

**Examples of weak ACs replaced with strong ones:**

| Weak (structural proxy) | Strong (wire path) |
|-------------------------|-------------------|
| "Module is registered in the plugin registry" | "Module successfully initializes: boot log shows INIT_OK line for this module" |
| "Build succeeds with the new include" | "Integration test exercises the new include path end-to-end: at least one functional call reaches the new code" |
| "Config key is present in settings.json" | "App reads the config key and applies it: observed behavior change matches the config value" |

## Spike Verdicts on Temporal Properties Must State the Observation Window Against the Failure Timescale

**A spike's verdict is only as strong as its observation window — a window shorter than the failure's timescale yields a confidently-wrong "it persists" / "it's stable."** When a spike answers a temporal question (does this leak? does this drift? does the daemon stay up? does the value persist across N cycles?), a too-short window observes only the pre-failure régime and reports the wrong verdict with full confidence — the property "held" only because the spike stopped watching before it broke. At plan-write time, state the observation window AND its size explicitly, and justify it against the suspected failure timescale: a leak that manifests over hours is not disproven by a 5-minute watch; zero observed variance over a window narrower than the period is a false-null tell, not a clean result. Bind the spike's pass-condition to a window provably longer than the failure mode it's ruling out. Source: 2026-05-29 project-rag.

## Close-Out Chunks Cite Specs, Don't Re-Exercise Them

A close-out chunk's job is citation, not re-validation: name the spec, name the code paths, mark the AC verified-shipped-by-citation. Minutes of work.

**Anti-pattern:** riding the close-out on a sibling integration run and asserting the binding path fired. Looks rigorous; fragile by construction — hardware and topology drift make the path unreachable on the validation host even when the contract is correct (RAM cap doesn't bind on a CPU-bound host; `delta == 0` between baseline-at-`--jobs auto` and resume-at-`--jobs 1` fails on shard-count drift, not on a resume bug; a lock-reaper exercise needs an orphan-PID class that's its own engineering problem to stage).

**Rule:** if the contract was the Staff Engineer-reviewed (or equivalent) and shipped with tests at the time it landed, cite that. A separate validation run is justified only when the host *and* topology can reproduce the binding path cleanly. Don't bundle "validation that hardening still works" with "documentation that hardening shipped."

**Plan-time canary:** if a reviewer's earliest finding is "integration coverage by happenstance" or "close-outs ride on Chunk N's run as their only test," reshape, don't slice-size-patch. Field-cite 2026-05-17 (ws2-narrow-activation): the Staff Engineer flagged the shape; the EM patched. At execution: Target 2 hit hardware-ceiling drift; Targets 3+4 hit shard-topology drift. PM authorized consolidated spec-citation close-outs, recovering ~46 min.

## Shared-State Pre-Flight Gate

Before a plan changes the semantics of a shared symbol — a state enum, gameplay tag, public field, or exported function signature — include a reverse-reference scan in the plan: list every consumer found via grep, IDE rename-preview, or equivalent tool. Plans that mutate shared contracts without enumerating consumers are incomplete and risk silent breakage across subsystems with no obvious compile-time signal.

**Checklist:** For each shared symbol the plan mutates, add a subsection that names every file/component that reads or depends on it. If the scan is non-trivial, make it an explicit plan step, not an assumption.

## Data Before Dispatch

Before writing a plan or dispatching agents on a debugging or fix task, identify and run the smallest diagnostic that exposes ground truth — a test runner, curl probe, `git show`, or single inspect call. Target: < 60 seconds. This is the cheapest step in any plan and prevents hours of hypothesis-driven agent rework.

**Framing rule:** Hypothesis-driven dispatch without diagnostic data is a stuck-detection trigger. If you find yourself writing a plan section that says "the cause is probably X," stop and run the diagnostic first. (geneva T1.2, paired across writing-plans + systematic-debugging)

**Diagnose-then-design sequence.** Don't author architectural plans for unknown root causes. When the symptom is observed but the mechanism is unverified, the first plan is a diagnostic plan — not a mitigation/refactor plan. Architectural plans built on guessed-at root causes optimize the wrong surface and bury the actual fault under structural churn; the structural work then has to be unwound when the real mechanism surfaces. Sequence is diagnostic spike → mechanism identified → design plan. Skipping the diagnostic step because "we already know it's the X layer" is exactly the heuristic that produces wrong-locus mitigations.

## Substrate-Migration Sequencing

*Lesson 2026-05-18, project-rag-ue-addon.* When a plan introduces a layout change (directory shape, file naming, schema location, persistence path) that a downstream producer depends on, the layout-creation work MUST be its own explicit task that lands BEFORE the producer task — not assumed to "exist by the time the producer runs." Plan-documented and reviewer-approved layout invariants do not guarantee runtime existence; the executor for the producer task will hit `ENOENT` / `IsADirectoryError` / `FileNotFoundError` at first run and the recovery shape (create directory inline, fall back to old path, etc.) is exactly the silent-pick footgun this rule prevents.

**Procedure at plan-write time:**

1. Walk every layout assumption the plan makes (new directories, new schemas, new persistence paths, new registry entries, renamed/moved files).
2. For each, ask: *does this exist at the moment the producer task runs?* If "yes, because Task K creates it" — Task K must precede the producer task explicitly, with `depends_on: <Task K>` in the producer's task header.
3. If "yes, because the substrate is naturally present" — grep the substrate to confirm. Don't assume; tests in CI run on clean checkouts.
4. If the answer is genuinely "no, the producer creates it" — that producer task's spec MUST include the creation step explicitly. Not a side-effect, not "it'll mkdir as needed" — an explicit step in the task body.

**Non-discriminating reviewer rationale is the warning sign.** When a reviewer's rationale for accepting a layout decision is true of multiple shapes (e.g., "PersistentClient needs a directory" — true of both old and new shapes), the reviewer didn't actually pick the right shape; they ratified a non-decision. Plan reviewers should be asked: *what about your rationale would change if we picked the OPPOSITE layout?* If the answer is "nothing," the rationale is non-discriminating and the layout decision isn't actually grounded in this review. Re-decide explicitly, or flag the decision as deferred.

**Default-RETIRE is lazy when an axiom assigns production capability to a specialist repo.** When an axiom assigns a domain to a specialist repo, it assigns *production capability*, not just receive-side responsibility for existing artifacts. The correct default disposition for types the specialist doesn't yet produce is PORT (specialist authors the missing producers); RETIRE is the override case requiring explicit per-type justification of why coverage isn't lost. Defaulting 39 specialist-only chunk types to RETIRE because the specialist lacked producers was the documented error; PM corrected it hard. Source: 2026-05-27 project-rag-ue-addon.

## Cross-Module TU Move — Enumerate the Donor Module's Full Dep Set, Not the Headline Dep

**A translation unit moved across module boundaries carries its code but NOT its old module's link dependencies — audit the donor module's full dependency arrays before dispatch.** When a plan moves a `.cpp`/`.h` (or any TU) from module A to module B — UE `.Build.cs` `PublicDependencyModuleNames`/`PrivateDependencyModuleNames`, a CMake `target_link_libraries`, a Cargo dep table — the destination module does NOT inherit A's link deps. The headline dependency the TU obviously uses is insufficient: transitive *private* deps that A pulled in (and that the moved code relies on implicitly) don't propagate, and the move compiles-then-fails-to-link on a dep the plan never enumerated. At plan-write time, read the donor module's *entire* dependency array (not just the one dep the moved symbol names) and list every dep the destination must add. Source: 2026-05-30 claude-unreal-holodeck.

## Precedent-Replication Plans Must Name the Novel Delta and Gate Exactly It

**"Replicates a proven precedent" can conceal the one novel seam — identify NOVEL-vs-precedent and gate exactly that delta.** A plan framed as "this is just like the existing X" lulls review into pattern-matching the precedent and waving the whole plan through — but the value (and the risk) is in the *one seam that differs* from the precedent. At plan-write time, split the plan explicitly into the precedent-replicated portion (cite the proven instance) and the NOVEL delta (the seam, contract, or behavior that has no precedent), and concentrate the acceptance gate on the novel delta — the replicated portion rides the precedent's existing coverage. A generalist diff reviewer earns its keep here *after* domain approval: the domain reviewer ratifies the precedent-match, the generalist catches what the precedent framing hid in the novel seam. Source: 2026-05-30 claude-unreal-holodeck.

## Roadmap and Cross-Repo Plan Hazards

These apply when a plan is part of a multi-stub roadmap or moves work between repos.

**Single-consumer audit-spike work folds into Phase 0 of the implementation plan, not a separate roadmap stub.** When a roadmap-shaped audit/spike has exactly one downstream consumer (the implementation workstream that uses its findings), the audit is not a peer stub — it's the first phase of that consumer. Separate-stub framing introduces handoff overhead, stale-findings risk between stubs, and review duplication for no integration benefit. Roadmap-shape heuristic: count consumers. ≥2 consumers → standalone audit stub justified; 1 consumer → fold into Phase 0 of that consumer's plan.

**Cross-repo MOVE between repos = audit residual at the source.** When a plan moves a stub/component/feature from repo A to repo B, the destination often only needs *part* of the original scope. The residual in repo A is not auto-deleted by the MOVE — audit what stays behind and decide explicitly: keep / delete / migrate. Silent MOVE without source-residual audit leaves orphaned scaffolding (configs, hooks, references, dead helpers) at the origin that survive every subsequent grep as "still in use somewhere," gating future cleanups.

**"Copy from upstream" rows mis-classify ~25% of the time — read every such file at its landed SHA before executing.** Plan-stub-vs-landed-disk drift is structural on cross-repo plans: "Copy from X verbatim" is the provisional assumption, not the execution contract. Before the executor runs, read each "Copy from X" file at its actual landed SHA and classify freshly (extend / text-adapt / upstream-specific-replace). The 1-in-4 mis-rate means a provisionally-correct plan will ship wrong code for roughly one file in four without this step. Source: 2026-05-27 project-rag-ue-addon.

**Cross-plan amendment discipline: body-edit, not wiki audit-trail.** When a PM-ratified decision in plan A supersedes a decision in plan B on the same branch, grep-and-amend plan B's body in one coordinated commit — a wiki audit-trail entry alone leaves downstream executor briefs on the stale doctrine. Enumerate every surface that carries the superseded claim (sub-decision body, risk row, convergence timeout, wave steps, AC rows) and update them in-place; a single missed surface ships an executor brief that contradicts the ratification. Source: 2026-05-27 project-rag-ue-addon.

## Hard Constraints for Executor-Bound Plans

These apply to any plan that will be handed to an executor agent. Violations here are the most common source of scope bleed and unauthorized work.

### (a) Executor specs must include explicit file-scope constraints

"Restructure the cheatsheets" or "fix the auth module" is insufficient — an executor without a scope constraint will modify adjacent files, run scripts, and create unauthorized commits. Every executor-bound stub MUST include a constraint block:

```markdown
**Scope constraint:** Only edit files matching `<pattern>`. Do NOT modify files outside that scope. Do NOT run scripts beyond `<allowed list>`. Do NOT create commits.
```

Name the allowed paths explicitly. If the stub says "update the config files," list them by path — don't rely on the executor to infer scope.

### (b) Orchestrator agents in plans must be read-only planners

The Agent tool is single-level nesting — subagents cannot spawn further subagents. When a plan calls for an agent that decomposes work and "dispatches sub-tasks," that agent MUST be configured as a read-only planner:

- No `Agent` tool in its `allowed-tools`
- No `execute-*` tools either (omni-tool gravity: if the tool is present, the agent will use it)
- Sub-task dispatch happens back at the EM level, not nested inside the orchestrator

If a plan step says "an orchestrator agent will analyze and dispatch," rewrite it: "orchestrator agent analyzes and returns a briefing; EM dispatches sub-tasks based on briefing."

### (c) Cross-plan reconciliation is a separate pass

When plan A depends on plan B — shared paths, asset names, API contracts — a reviewer of A in isolation cannot see contradictions with B. Plans that interlock require an explicit cross-plan reconciliation step:

- Read both plans' cross-references side by side
- Verify mount paths, asset names, and assumed APIs align
- Document any conflicts before execution begins

**In the plan document itself:** If interlocking plans exist, add a `**Depends on:**` line in the header and a reconciliation checklist as the final pre-execution step. Do not leave this implicit.

**Cross-plan conflict scan before executor dispatch (procedure).** A `**Depends on:**` header is insufficient when sibling plans were authored concurrently and neither knew about the other. Before dispatching any executor on a freshly-written plan, run a mechanical scan over `docs/plans/*.md` that have been touched since the plan-author last reconciled (or are still in `## Active` state):

1. **File-overlap grep.** For each chunk-scope file in the new plan, grep sibling plans for the same path. Any sibling that names an overlapping file is a candidate conflict — read the sibling's relevant section.
2. **Architectural-seam grep.** For each new abstraction, registry entry, hookspec, schema field, or contract the new plan introduces, grep sibling plans for the seam's central noun. A sibling that mentions the same seam (even with a different name) is a candidate conflict.
3. **Fold into `## Cross-plan coordination` section.** Add a section to the new plan body enumerating: (a) each sibling plan touched on the same file or seam, (b) what assumption each carries, (c) whether the new plan amends, defers to, or supersedes the sibling. No conflicts found → write the section with this body:

   > **Cross-plan coordination:** scanned `docs/plans/*.md` — no overlapping file scope or seam citations.

   Empty-but-present section is fine; missing section is the failure mode.

A reviewer (the Staff Engineer / domain reviewer) will dispatch against the assumption that this scan has happened; surfacing a sibling-plan conflict at executor time is plan-substrate failure, not executor failure. Source: 2026-05-18, project-rag.

### (d) Tool resolution in teammate prompts

When a plan step dispatches a teammate agent that needs MCP tools, use graduated ToolSearch in the teammate's prompt — never hardcode a single tool name prefix. MCP tool names vary across teammate spawn contexts (e.g., `mcp__notebooklm__*` vs `mcp__plugin_notebooklm_notebooklm__*`).

**Graduated resolution order:** `select:exact` → `+prefix` keyword fallback → graceful failure message. Any teammate prompt that names an MCP tool should follow this pattern; hardcoding a single prefix is a silent failure waiting for the next spawn context change.

### (e) No fallback escape hatches in stubs

Python-fallback / "if MCP missing, use Python" / "if X unavailable, fall back to Y" clauses are a structural fault — under firefight pressure executors pick the fallback every time, bypassing the canonical surface precisely when it most needs exercising. Fix is structural, not prose: remove the clause; convert the "missing verb" branch into an explicit Step 0 prerequisite that fails loudly.

**Doc-doctrine corollary:** Don't advertise the escape hatch in the README or stub preamble. When a primary path and a fallback both exist, the entry-point promotes one path only; the fallback file lives on disk but isn't surfaced.

**One spec sentence carrying both a hard requirement and a soft fallback reads two ways — split it at plan-write.** A sentence like "use the MCP verb (or fall back to Python if unavailable)" gives the executor a hard mandate and a soft escape in the same breath; executor and reviewer resolve the ambiguity in opposite directions (executor takes the fallback under pressure, reviewer reads the mandate). Resolve at authoring: state the hard requirement as a flat imperative and demote the fallback to an explicit Step 0 prerequisite that fails loudly (per (e) above) — never weld both into one sentence. Source: 2026-05-18 coordinator.

### (f) Concurrency-safe file design

When a plan proposes shared-file appends across N machines or sessions, prefer **per-machine paths** over "atomic per-block append" merge logic — the latter is a euphemism for "PM resolves merges at daily wrap." Per-machine files sidestep the conflict class entirely.

### (g) File-overlap analysis before parallel dispatch

Plans that claim "fully independent files" still need EM-side file-overlap analysis before parallel executor dispatch. Trust-but-verify: a 30-second cross-check against the plan's file lists prevents two executors from racing the same file under independence assumptions.

**Index files are hidden shared substrate.** `docs/README.md`, `docs/wiki/DIRECTORY_GUIDE.md`, and any central index get rewritten by every chunk that touches them. These files never appear in per-chunk file lists yet every chunk that adds a new wiki page, doc, or plan entry implicitly writes to them. In mise/parallel-dispatch file-overlap analysis, the anchor chunk must own all index rows and forward-references. If no anchor is designated, index files must be committed by the EM after all chunks land — never by individual parallel executors. Source: 2026-05-15 project-rag.

**Concurrency unit is the file, not the chunk — and file-overlap is necessary but not sufficient for parallel-safety.** Two facts compound here. First, the unit of parallel safety is the *file*: a wave is parallel-safe only when no two concurrent executors write the same path, so the overlap analysis is per-file, not per-narrative-chunk. Second, file-disjointness alone does not license parallelism — cross-wave *contract coupling* (a signature, schema field, or wire shape one chunk produces and another consumes) must be enumerated separately and pinned before declaring parallel-safe. A plan that proves "no file overlap" but skips the signature-dependency pass races two executors against an unpinned interface. Enumerate both axes: (a) file-overlap graph, (b) cross-wave signature/schema/contract dependencies. Source: 2026-05-19 project-rag.

**Cross-wave test-substrate drift — earlier-wave tests assert intermediate shapes later waves change.** When a multi-wave plan lands tests in an early wave, those tests can assert on a substrate shape (schema, file layout, envelope field) that a *later* wave deliberately mutates — the early tests then go red not because of a regression but because they encoded a transient intermediate state as a permanent contract. At plan-write time, walk every test an early wave ships and ask: does any later wave change the shape this test asserts on? If yes, either defer the test to after the mutating wave, or write it against the final shape from the start. Source: 2026-05-19 project-rag.

### (h) Plan-time dispatch decisions go stale

Dispatch-shape decisions written into a plan (Haiku/Sonnet/Opus, parallel/serial, scout vs general-purpose) are valid at plan-write time only. Phase-2 dispatch must re-check that the chosen shape still fits the substrate; staleness window is ~24h.

### (i) Read-current-and-increment for periodic baselines

Increment math is durable; absolute baseline values rot. Stubs touching a periodically-changing baseline (orphan count, lesson count, queue depth) MUST instruct executor to `read-current-then-increment-by-N` rather than asserting absolute target values.

### (j) PM redirect mid-pipeline invalidates completed reviews

PM redirect mid-pipeline (scope/direction change after dispatch is in flight) counts as structural rework — completed reviews are invalidated against the new surface and MUST be re-run before treating the pipeline as resumable. Don't smuggle pre-redirect review approvals across a surface change.

### (k) No-TBD-thresholds (extends substrate-verification confidence checklist)

Any plan that ships with `TBD` / `???` / `<placeholder>` in a threshold position (cutoff value, retry count, timeout) is unsafe to dispatch — the executor will either fabricate the value or fail at runtime. Resolve thresholds at plan-write time or explicitly defer the chunk.

### (l) Plan frontmatter is EM-only territory

Plan frontmatter (`status:`, `landed_in:`, `reviewed_by:`) is EM-only territory. Executor dispatch briefs MUST include verbatim "DO NOT modify plan frontmatter — that is the EM's bookkeeping surface." Even with this, audit `git diff` on plan files in the post-dispatch verification step.

### (m) Seam Contract for cross-stub symbols

In a multi-stub plan, every cross-stub symbol dependency — a function in Stub-1 that calls a symbol Stub-2 is supposed to produce — is a *seam*. The producer stub MUST ship its symbol in the same wave as the consumer that references it. A `getattr(module, "X", None)` or `try/except AttributeError` graceful-degrade clause against a planned primitive is a permanent fallback, not a temporary bridge: once the consumer ships and the producer hasn't, the degrade clause silently becomes load-bearing infrastructure and the call path permanently no-ops. If the producer is genuinely not in the same wave, the consumer stub MUST include a task that ships the symbol — not a degrade clause. Distinct from (e): (e) governs runtime fallbacks; (m) governs plan-time forward-references.

### (n) Plan-AC "commit required" must carve out the executor commit prohibition explicitly

When a plan's AC genuinely requires a commit to exist (e.g. `cited:<sha>` acceptance, a "land the regression net" task), it collides with the standing executor "DO NOT create commits" scope constraint (per (a)) and the EM-serial-commit discipline. The plan wins — but the dispatch brief MUST carve out the exception explicitly: name *which* task is permitted to commit, *which* pathspec, and that all other files stay out of that commit. A bare "commit required" AC with no carve-out leaves the executor choosing between two contradictory instructions, and it picks wrong under wrap-up pressure. Distinct from (l) (frontmatter immutability) — (n) governs the commit *action*, not the bookkeeping surface. Source: 2026-05-18 project-rag.

## Self-Modifying Infrastructure

Plans that modify hooks, validators, or other infra that runs against the plan's own artifacts must include a smoke-test step with synthetic input that exercises the modified code path BEFORE the modified hook fires on real session traffic. The plan body MUST cite the synthetic-input file path.

## Lessons Learned

**Default to subagent dispatch over a new RPC verb when *adding* internal operations.** When a plan proposes a new tool/verb/handler/CLI-job, ask first: can a subagent compose this from existing primitives via `execute_python_code` + `inspect` + extant MCP verbs? If yes, the plan should propose the dispatch path, not the new verb. The new verb earns its place only on (a) C++-only capability, (b) transactional state coupling that primitive composition cannot preserve, or (c) cross-call editor-state invisible in tool signatures. **Never default to dispatch over an existing verb without explicit retire-justification** — prior surface is the proven path.

Tag: `[universal]` — applies to any project_type using the coordinator pipeline.

## Doctrinal Contradiction — Surface as Open Question, Don't Pre-Resolve

*Source: project-rag tasks/lessons.md:30, 2026-05-29. [universal]*

When plan-body research surfaces a contradiction between two pieces of existing doctrine — the plan cites source A, prior-art-checker surfaces source B that conflicts — do **not** pre-resolve the contradiction inline. Surface it as an explicit §-numbered open question addressed to the reviewer: *"§Q-N: Source A says X; Source B says Y. Which doctrine prevails here?"* The reviewer reads both citations in context and rules; the plan author's job is to expose the tension, not dissolve it before anyone else can see it.

**Pre-resolving looks like:** asserting one doctrine wins without naming the other, or burying the conflict in a footnote the reviewer may skip. Either leaves the reviewer ratifying a choice they didn't see.

## Architecture-Survey Chunk-K Guard — Doc-Heavy Repos

*Source: project-rag tasks/lessons.md:91, 2026-05-29. [universal]*

The architecture-survey's chunk-K guard that detects "uncatalogued architecture" by counting recently-changed files overshoots on doc-heavy repos: `tasks/`, `docs/`, and `archive/` churn (lesson captures, plan edits, handoff updates) is not uncatalogued architecture. Before triggering the guard's escalation path, cut the emergent-drift candidate list against catalogued SOURCE directories only — exclude `tasks/`, `docs/`, `archive/`, and similar doc-tree paths. A guard that fires on lesson-capture churn produces false-positive escalations that crowd out real structural drift.

## Architecture-Audit Rotation — Formula Bias and Feature-Shaped Targets

*Source: project-rag tasks/lessons.md:107 and rag-ue-addon tasks/lessons.md:23, 2026-05-29. [universal]*

**Rotation formula over-weights freshly-audited systems.** The open-P1 signal in the rotation formula inflates exactly the systems most recently reviewed — a just-audited system with open P1 findings scores high enough to re-target immediately, starving unreviewed systems of audit cycles. Decay the open-P1 weight for systems audited within N days (suggested: linear decay to 0 over 14 days) so the formula drives breadth rather than anchoring on the freshest finding cluster.

**Rotation targets can be feature-shaped, not just atlas-systems.** "Audit system X" is the natural unit, but a cross-cutting feature (authentication flow, error-handling sweep, multi-tenant isolation) that spans several atlas systems is equally valid as a rotation target. When a fresh atlas is available, the reviewer pre-reads it as pre-digestion before the audit session — this collapses the "what IS this system?" ramp-up and concentrates audit time on the architectural questions.

## Defer B.0 Doubt-Check Recommendations on a Peer-Doctrine Axis

*Source: rag-ue-addon tasks/lessons.md:19, 2026-05-29. [universal]*

The Branch B doubt-check in `coordinator:plan` can surface recommendations that depend on peer-doctrine substrate — a pattern or convention that lives in another repo's CLAUDE.md or wiki, not yet on disk in the current repo. When a B.0 doubt-check recommendation references peer-doctrine that hasn't been mirrored locally yet, **defer it** rather than pre-resolving against the peer's in-flight doctrine. Acting on peer-doctrine recommendations before the substrate is confirmed on disk risks implementing against a stale or mis-remembered version. Flag it explicitly: *"B.0 rec deferred — peer-doctrine substrate not yet confirmed on disk."*

## Plan Review Gate (Mandatory)

After saving the plan, it MUST go through one review cycle before execution. This catches structural problems while they're cheap to fix — before enrichment and execution invest real work.

1. Route the plan through `/review` — the plan document is the artifact
2. **Dispatch the review-integrator agent** to apply findings to the plan. Do not integrate findings manually — the review-integrator handles this. Your job after dispatch:
   - Review the integrator's escalation list (usually 0 items)
   - Spot-check the diff to verify findings were applied correctly
   - If you disagree with how a finding was applied, change that specific part — don't re-integrate the whole review yourself
   - Only skip integration of an item if: (a) requires PM input, or (b) you genuinely disagree (flag to PM with reasoning)
3. Add a review status marker to the plan document header:

```markdown
**Review:** Reviewed by [reviewer name] on [date]. Ready for execution.
```

4. Only after review is complete, proceed to the execution handoff below.

**PM Override:** If the PM explicitly says to skip review (e.g., "ship it", "straight to execution"), skip this gate and note in the header:

```markdown
**Review:** Skipped per PM direction. Proceed to execution.
```

## Execution Handoff

After the plan is reviewed (or review is explicitly skipped), offer execution choice:

**"Plan reviewed and saved to `docs/plans/<filename>.md`. Two execution options:**

**1. Executor-Driven (this session)** - I dispatch Executor agents per task following `docs/wiki/delegate-execution.md`, code review via `/review-code` between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session and run /execute-plan, batch execution with checkpoints

**Which approach?"**

**If Executor-Driven chosen:**
- Follow `docs/wiki/delegate-execution.md` to dispatch Executor agents
- Stay in this session
- Fresh Executor agent per task + code review via `/review-code`

**If Parallel Session chosen:**
- Guide them to open new session in worktree
- New session uses `/execute-plan`

## Porting Patterns Carries Source Tokens

*2026-05-24, project-rag.* When a plan ports logic from a reference implementation (another repo, upstream project, earlier version), the executor inherits env-specific tokens: command names, flag names, path shapes, import aliases, and routing-table entries that were valid in the SOURCE environment but may be wrong or absent in the TARGET. Before dispatching: enumerate all env-specific tokens in the ported block and verify each against the target repo's live state (file tree, routing table, `pyproject.toml`, `package.json`, etc.). A porting plan that doesn't name this verification step is incomplete. (Source: 2026-05-24 project-rag)

## Re-Export Shim Blast Radius Before Deleting a Vendored Constant

*2026-05-24, project-rag.* Deleting a constant (or any symbol) from a module requires grepping not just direct importers but ALSO any re-export shim sites — lines with `# noqa: F401` or `__all__` entries that back-compat-re-export the symbol from a transitional shim module. These lines do not show up as "uses" in a naive grep for the symbol name; they show up only when you grep the shim file's body for the constant name. Miss a shim, and consuming code that imports via the shim breaks silently at runtime. (Source: 2026-05-24 project-rag)

**A re-export shim preserves IMPORTS but not `mock.patch` targets when a symbol's consumer moves.** A module-extraction refactor that leaves a back-compat re-export shim keeps `from old.mod import sym` working — but a test that does `mock.patch("old.mod.sym")` (or `patch.object(alias, "sym")`, or a `mod.sym = …` reset) still patches the *old* binding, while the consumer that moved now reads the symbol from its *new* home. The patch silently no-ops: the test goes green against an un-patched code path. Before any module-extraction / symbol-move refactor, enumerate every `patch("…")`, `patch.object(…, "…")`, and `mod.sym =` reset site for the moved symbol — the import grep does not surface them, and the failure is silent-green. Chain-end (combined-surface) review is the net. (Source: 2026-05-29/30 project-rag)

## AC gate degraded to static-analysis: document which direction each half covers

**When a runtime verification gate falls back to static-analysis grep, document the asymmetry explicitly — which direction does the runtime dump cover vs. the grep? Don't mark the AC fully passed if only one half is verified.**

A fallback to static analysis is often correct given substrate constraints (commandlet mode skips certain initializers, hardware ceiling doesn't bind in CI), but the asymmetry must be named. The successor stub's scope becomes clear from the gap: what would prove the other half?

*Source: holodeck `tasks/lessons.md` (holodeck-L33, central-promoted 2026-05-28).*

## Asymmetric-defaults framing produces sharper decision documents

**Declare per-layer defaults with explicit override conditions ("KEEP X unless evidence demonstrates Y") rather than balanced surveys — specialists then look for evidence to override defaults rather than justify positions.**
**Why:** A LightRAG synthesis reached "PORT-PATTERNS, single track" cleanly because a DISQUALIFYING verdict tripped a pre-declared override condition. A balanced frame would have produced a "both have merit" table.
**How to apply:** before dispatching research or architecture specialists, write the scope document as `KEEP <default> UNLESS <override condition>`. Asymmetry forces evidence to do work; symmetry invites hedge-anchored synthesis.

*Source: holodeck `tasks/lessons.md` (holodeck-L115, central-promoted 2026-05-28).*

## Post-review plan edits need a body sweep, not just a patch

**When a reviewer finding renames a section header, resequences chunks, or restructures a scope, grep the rest of the plan for the old framing after applying the finding — don't trust the integrator to surface all residual instances.**
**Why:** A the Staff Engineer sequencing finding was applied to the Sequencing block, but the plan body still said "phase 1 / phase 2" — the enricher inherited the phase split from body text and surfaced it as an open question, requiring the EM to fold a step back in mid-stub.
**How to apply:** after applying any structural reviewer finding (sequencing, scoping, decomposition, rename), grep the plan body for the old terminology and sweep — the integrator's brief is "apply this finding," not "audit the plan for residual implications."

*Source: holodeck `tasks/lessons.md` (holodeck-L155, central-promoted 2026-05-28).*

## Durability Assertions Must Cover ALL Writers of a File

*2026-05-24, project-rag.* A durability assertion like "this file is never overwritten by X" is only meaningful if X is the ONLY writer. If multiple code paths write the file, single-source coverage is a silently-false durability claim — the un-asserted writer can overwrite at any time. Before writing a durability assertion, grep ALL write-direction patterns (open-for-write, rename-to, shutil.move, os.replace) for the target path. If multiple writers exist, the assertion must cover all of them or be scoped narrower. (Source: 2026-05-24 project-rag)

## Vocabulary Substitution Must Be Cross-Checked Against Authoritative Glossary

*2026-05-24, project-rag-ue-addon.* A plan brief that instructs mass-rename of vocabulary tokens (e.g. "rename `foo` → `bar` everywhere") must cross-check the NEW tokens against `CONTEXT.md` or the authoritative glossary BEFORE dispatch. A vocabulary substitution that introduces a non-canonical synonym — or conflicts with an existing term — ships the wrong vocabulary into every file it touches. The check takes one grep and prevents a second sweep to undo the damage. (Source: 2026-05-24 project-rag-ue-addon)

## Vacuous-True Acceptance Criteria Is Not a Pass

*2026-05-24, project-rag-ue-addon.* An acceptance criterion that turns out vacuously true at close (the condition is always satisfied regardless of the code's behavior — e.g. "the function returns a non-None value" when the type annotation already guarantees that) is not a pass — it's a stub-quality finding. When a close reveals an AC is vacuous, re-anchor it to the moved seam (what is the real behavioral contract?), replace the vacuous criterion with one that would actually fail if the implementation were wrong, or surface it explicitly as a stub-quality gap for the plan author to resolve. Marking it PASS and moving on hides incomplete specification. (Source: 2026-05-24 project-rag-ue-addon)

**AC that only tests the field-present case gives false consumer-proof — the negative-spec must cover absent-as-no-distortion.** An acceptance criterion that exercises only the populated/literal-field-set path ("consumer reads field X and renders it") proves nothing about the case the consumer hits more often: the field *absent*. A consumer can pass the field-present AC and still distort, crash, or mis-default when the field is missing. For any AC gating consumer behavior on an optional field, the plan's negative-spec block MUST add an explicit absent-case criterion (field missing ⇒ consumer produces the no-distortion default), not just the present-case one. This is the negative-spec twin of the vacuous-true finding above. Source: 2026-05-19 project-rag.

## Threshold-Table Reachability — Test the Floor Before Shipping

A tier/threshold table that classifies by an "any-criterion-matches" rule with a `>= 0` floor on any criterion silently collapses tier reachability: a `>= 0` floor is satisfied by every input, so any tier resting on it becomes unreachable or swallows the tier below it. When a plan ships a threshold table (severity tiers, confidence bands, score buckets), every non-floor tier's criteria MUST be strictly `>` the floor on each criterion separately — and the plan must include a floor-reachability test: construct the boundary input for each tier and assert it lands in the intended tier, not a neighbor. Don't ship a threshold table whose tiers were never exercised at their boundaries. Source: 2026-05-19 claude-central. (Sibling of `coordinator/CLAUDE.md` § Implementation Standards "detect-then-silently-pick is a footgun" — an unreachable tier is a silent mis-pick.)

## Preference-Order Over Co-Equal Framing — Name the Asymmetry

Doctrine (or a plan's resolution rule) that frames two sources as "co-equal rules" often masks an asymmetric *preference*. When one source is primary and the other a fallback — registry-primary / sibling-fallback, flag-then-env-then-marker-discovery, lockfile-then-floor — say so as an explicit ordered preference. Co-equal framing leaves the consumer to detect-then-silently-pick, and a silently-wrong pick (CPU vs GPU substrate, stale vs fresh registry) surfaces as a downstream mystery rather than a loud resolution error. The plan must state the order and the tiebreak, not present the sources as interchangeable. Source: 2026-05-19 claude-central. (Sibling of `coordinator/CLAUDE.md` § Implementation Standards "detect-then-silently-pick is a footgun"; see also `document-bloat-trim.md` § two-co-equal-rules framing for the doctrine-authoring side.)

## Closure-Gate Circularity — Gate-Condition Must Not Name Its Own Closure-Action

Before shipping any "blocked on X" / "gated on Y" / "closes when Z" language, check the gate-condition against the closure-action for circularity. A gate whose condition names the very work it gates on is tautological — it can never fire (the condition is the action) or it fires vacuously (the action trivially satisfies its own condition). The check: write the gate-condition and the closure-action side by side; if the action *is* the condition (or trivially produces it), the gate is decorative. Re-anchor the condition to an *independent* observable (a PR URL, a flag flip, a downstream test going green) that is not produced by the gated work itself. Source: 2026-05-20 project-rag. (Extends `coordinator/CLAUDE.md` § Implementation Standards "OOS framing must be architectural" — a circular gate is appetite-hedging disguised as a dependency.)

## Retirement Premise-Pass — Identify the Real Consumer

**A module's reason-to-exist may be a third party's need — verify the actual consumer before a "field Y now retires module X" deletion.** "Retire X because Y replaces it" plans conflate X's apparent purpose with its actual consumer. The retirement premise-pass must identify X's REAL consumer (grep what actually depends on its runtime behavior), not assume it serves the consolidation's own call sites. 2026-05-27 example: a WMI-safe `is_windows` field was meant to retire `platform_shim.py`, but the shim pre-warmed `platform.uname()` for ChromaDB's import-time `platform.system()` call — not project-rag's own checks. A field for our checks does nothing for ChromaDB's internal call; deleting the shim would re-expose a live hang. Bonus: `ensure_platform_cached()` had zero production callers — the mitigation wasn't even wired. Source: 2026-05-27 project-rag.

## Plan-Doc Drift — Re-walk Enumerations After Inter-Plan Decision Deltas

**Plan-doc framing drifts from shipped execution reality; downstream substrate audits catch what upstream reviews miss.** A plan document's stated move-set, deletion list, or ID enumeration can drift from what the executor actually ships — especially when intermediate decisions (polarity reclassifications, follow-up corrections) happen between plan-write and execution.

**Rule:** when polarity, scope, or ID-set decisions land after plan-write but before execution, re-walk every count and enumeration in the plan against the decision delta. The grep tripwire: a plan that mentions a count more than 2× without an audit-trail note explaining the count's evolution is at risk. Pair plan frontmatter `verification_evidence` blocks with "as-of-shipped" snapshots citing the actual shipped commit, not the plan's pre-decision framing.

2026-05-14 example: `§AC-4.2` listed 9 producers as the move-set; R2 polarity audit had reclassified 4 (kept in host) but missed `engine_cvars.py`; the PR-W1c executor independently converged on the correct 6+2 reality. Addon-EM substrate audit caught the drift via correction memo. Without the cross-repo audit, a future re-read of the plan would have asserted the wrong gate shape. Source: 2026-05-14 project-rag.

## Gate on the Discriminating Signal, Not the Coarse Aggregate

When a plan gates downstream behavior on a status, color, or rollup that aggregates multiple underlying conditions, gate on the *discriminating* sub-signal instead — the coarse aggregate fires on cases that need opposite handling. **Worked example (doctor F-2, 2026-05-23 project-rag):** a fresh-state offer was gated on `AMBER`, but `AMBER` fires both on never-indexed (INFO — the offer is correct) *and* on half-indexed-WARN (a real problem the offer would paper over). The fix gates the offer on the never-indexed INFO branch specifically, not the AMBER color. At plan-write time, for any gate keyed on an aggregate: enumerate every underlying condition the aggregate rolls up, and confirm they all want the same downstream action. If they diverge, gate on the discriminating branch. Source: 2026-05-23 project-rag.

## VERBATIM / Spelling-Lock Blocks Must Carve Out Standard Capitalization

When an executor brief locks the spelling of a token or phrase ("write `project-rag` exactly, do not paraphrase"), the lock over-applies if it forbids the executor from capitalizing the token at sentence-start or in a heading. A spelling-lock is about *token identity*, not *casing*: the brief MUST carve out standard English capitalization (sentence-initial, title-case headings) so the executor isn't forced to write a lowercase token mid-prose where grammar demands a capital. State the lock as "preserve this exact token, applying normal capitalization at sentence boundaries" rather than a flat verbatim mandate. Source: 2026-05-19 project-rag.
