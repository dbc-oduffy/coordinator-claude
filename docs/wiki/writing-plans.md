---
title: Writing Plans
description: Long-form doctrine for writing implementation plans — scope modes, definition of ready, file structure, executor hard constraints. Linked from coordinator:plan SKILL.md branches.
created: 2026-05-06
updated: 2026-05-06
authoritative_source: previously skills/writing-plans/SKILL.md (deleted in clean-break migration 2026-05-06)
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
- **No problem-set on a feature/architecture/spike plan?** The coverage check emits an advisory nudge (not a verdict-gate) — confirm problem understanding with the PM before dispatch.

Authoring the problem-set is `/shape`'s job, not the plan's. If you arrived at `coordinator:plan` without one and the work is non-trivial, that is the Branch B doubt-check's cue (see `coordinator/skills/plan/SKILL.md`).

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

**`UNCERTAIN`-as-status is hedging — rectify before any PM gate.** A plan, stub, or AC row that carries `UNCERTAIN` / `TBD` / `unclear` in a status field is an undelegated decision wearing a status label, not a legitimate state. Resolve it (decide, or grep the substrate) before the plan reaches a PM gate or review — a PM gate is not the place to discover the author never made a call.

**A "name your biggest uncertainty" plan-time data-flow question is resolvable NOW — do not make the fix conditional on a trace deferred to execution.** When a plan names its biggest uncertainty as a data-flow question ("do these three lanes serve raw content or covered?") and hedges the fix as conditional on it ("fix C1 *if* found to serve raw"), the call-graph trace that answers the question is almost always tractable at plan-review time — cheaper than deferring it into an execution-time branch the executor has to re-derive. Trace it across the producing / serializing / consuming files during review and make the fix unconditional. A fix gated on a deferred trace is an undelegated decision wearing a conditional; it composes with the `UNCERTAIN`-as-status rule above. (Empirically, a plan-review trace across four files resolved a "biggest uncertainty" the plan had made C1 conditional on.)

**Plan over brainstorm when the PM has set the architectural axiom.** Once the axiom is PM-set, remaining ambiguity is classification-with-rationale work that belongs in plan Decision blocks for PM ratification — not open-ended brainstorm dialogue. Heuristic: if (a) axiom is set, (b) scouts have produced an evidence base, and (c) ambiguous calls are classification-shaped (not architecture-shaped), skip directly to plan. The review pipeline (prior-art-checker → named reviewer → integrator) catches real substrate failures and scope refinements that brainstorming wouldn't surface any faster.

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

**Validation floors derive from emission shape, not author intuition.** Setting `≥N items emitted` as a gate when N is chosen by feel produces false-negatives (gate passes on a near-empty output) and false-positives (gate blocks a legitimately sparse but correct result). Before writing a count gate, trace the emission path: identify the producer loop or query and derive the minimum expected output from the logic, not from a gut estimate.

**Default to EXTEND when an extension point already has detection helpers wired.** When a plan proposes new behavior that an existing hook, validator, or skill could carry — and that surface already has the detection/parsing/dispatch helpers the new behavior needs — extend it; do not fork a sibling. Forking doubles blast radius and creates a drift surface between two near-identical detectors. This is the plan-time twin of the "refactor over patch" engineering default and the location-challenge in § Negative-Search Before Drafting (point 5): the cheapest locus is usually the surface that already detects the class.

**Sibling-team archive memos collapse cross-repo coordination cost.** When sizing cross-repo work, READ sibling-team `archive/*proposal*` / `*coordination*` / `*authority*` memos before estimating bump cost. Tri-repo ratification is often over-cost for unilateral-authority shapes already established in a peer's archive — the authority decision may already be made and the bump is unilateral. Skipping the archive read produces inflated complexity estimates and unnecessary PM escalations.

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
3. `.claude/repomap.md` (or task-scoped variant)

This gives you the structural context to make informed file-mapping decisions without redundant grep discovery. Use Glob/Grep after this to fill specific gaps — exact line numbers, recent additions not yet in the atlas, etc.

**Substrate-verification at plan time.** Verify substrate facts (file paths, framework names, helper APIs, line numbers) via `ls`/`grep` while authoring — not at completion. Two minutes of disk verification prevents the substrate-fact errors reviewers will catch on R1.

**Reviewer pre-resolved substrate values need executor `ls` confirmation.** A reviewer citing a `@import` path as authority for a manifest `functional_probe.path` field is hypothesis based on indirect evidence — the `@import` is the local-install path; the manifest's path field is schema-defined as repo-source path. Reviewer pre-resolution is never authoritative on schema-distinct fields. Pre-resolution of any path-typed field requires an executor `ls` confirmation step in the plan.

**A reviewer-named architectural seam is substrate to verify, not a literal mechanism to execute.** When a reviewer names a seam ("route through the `run_consumers()` gate", "this belongs on the host envelope") the plan author treats it as a *pointer to substrate to grep*, not a verbatim API to wire. The reviewer named the seam from their reading, not from disk; the actual symbol, signature, or registration shape at that seam must be confirmed by grep before the plan body cites it. Transcribing a reviewer's seam-name as if it were the literal callable is the same fabrication class as citing an unverified field.

**Periodic baselines drift — instruct read-current-and-increment, not match-spec.** When a stub names a count, version, or baseline ("bump from 55 to 56"), absolute values rot between enrichment and execution. Phrase as "read current value and increment" so the math survives the gap.

**Plunge vs. plan split by substrate certainty, not appetite.** Verified-on-disk parts of a workstream may plunge directly to execution. Parts that depend on foreign-repo substrate (paths, APIs, schema fields in a sibling repo you haven't grepped) require a plan with an explicit verification step before execution dispatch. Certainty is the gate, not effort estimate.

**Satisfy schema constraints by construction before relaxing.** When a closed-enum schema gate appears to block a new entity type, ask "can the producer satisfy the constraint?" before "should we relax the constraint?" Relaxation carries cross-consumer blast radius; satisfaction by construction is local and reversible. Document the construction path in the plan before entertaining schema changes.

- Scaffolded config files (templates the plan instructs an executor to write) must self-disclose which fields they actually support — silent ignoring of unrecognized fields breeds downstream debugging cost. Plans citing config templates should require the template carry a `# Supported fields:` comment listing the keys.
- Plans extending an existing pipeline (e.g. adding a new wave to /distill, a new phase to /update-docs) MUST grep the pipeline's existing scratch-path conventions before declaring output paths — silent collision with sibling waves' scratch namespaces breaks parallel safety.

**Doctrine constants claiming an empirical basis MUST cite the dated incident — un-cited "observed threshold" numbers are folklore.** When a plan (or a doctrine/wiki rule the plan introduces) states a numeric constant as if measured — a concurrency cap, a timeout, an RSS ceiling, a "we've seen N crash" threshold — it must carry the dated incident that produced the number. An un-cited "observed threshold" reads as empirical to every downstream EM and makes them over-comply with a number nobody actually measured. The 2026-05-30 case: a 6–8 concurrent-executor cap circulated as an observed crash threshold with no recorded crash behind it. Rule: every doctrine constant is either (a) cited to a dated incident/measurement, or (b) flagged explicitly as a heuristic default ("heuristic, not measured") — never bare.

**TEMPLATE blocks with substrate-divergent specifics are worse than no TEMPLATE.** Concrete assertions in TEMPLATE blocks (file paths, version strings, flag names, count thresholds) must be substrate-checked at plan-time, or stripped to truly skeletal pseudocode. A TEMPLATE that carries specific values not verified on disk becomes a fabrication vector — executors treat TEMPLATE content as authoritative. Pre-review audit: walk every concrete value in a TEMPLATE block and confirm it against `ls`/grep, or replace with a `<placeholder>` that forces the executor to resolve it.

**OS-primitive constraints are brief-altitude substrate, not executor-time discovery.** Any executor brief whose action verb depends on an OS primitive (kernel cap, signal, ioctl, syscall, Win32 Job Object limit) must cite the primitive's authoritative behavior — a one-line doc quote + URL or man-page section — *before* the action step. Pushing that confirmation down to executor-time spreads architecture decisions across executor sessions where they don't belong, and the brief-bloat that hides the bad assumption is itself a violation of the small-remit-and-many HARD RULE: if the brief crosses 5–10 minutes or 3 step-changes of altitude, split before dispatch. The 2026-06-09 case: a brief told an executor to enforce a 2.5 GiB RSS cap via Windows `JOB_OBJECT_LIMIT_PROCESS_MEMORY` — but that primitive enforces on commit-VA only by design (`BasicLimitInformation.ProcessMemoryLimit` is checked against `PrivateUsage`; `JOB_OBJECT_LIMIT_WORKINGSET` is a trim hint, not a kill primitive). The executor discovered the constraint empirically and self-rearchitected to a layered design — the right answer, produced by executor-altitude problem-solving instead of brief-altitude design.

**CI-step-shape borrowing requires an asymmetry audit before copying the step.** When a plan borrows a CI step shape from a reference implementation (another repo, a peer plan, an existing workflow), first audit whether the reference's "missing resource" is symmetric in failure-mode load-bearing with your target. A CI step that is *optional infra* in the reference (the build still passes if the resource is missing; the step is a best-effort enrichment) is NOT the same shape as a step that is *load-bearing substrate* in your target (a missing resource means the produced artifact is wrong or absent). Copying the optional-infra step shape into a load-bearing-substrate context ships a CI step that passes green while the substrate is silently broken. Before borrowing a step shape, answer: "if the resource this step depends on is absent, does the reference build pass? Does MY build need to pass in that case?" If the answers diverge, the shapes are not symmetric — write the step to fail-loud on absence rather than borrowing the reference's silent-skip.

**Protocol-tier semantics are contracts, not defaults — look for the recommendation/nag pattern instead.** Before approving a plan that "changes the default" on a stringly-typed dispatch slot, grep the resolver to see whether it has multi-tier resolution (exact-match + umbrella/glob/group). If yes, the proposed "default change" is almost certainly a protocol-tier reshape disguised as a refactor: consumers depend on protocol-tier resolution being stable across versions, and flipping what an umbrella token resolves to is a breaking contract change. The cleaner fix is usually to keep the protocol meaning intact and *recommend* the canonical narrow form at the call site — moving the consumer's call site (their problem, with a clear migration path) rather than the protocol meaning (everyone's problem, silently). Grep the codebase for an existing accept-with-nag analog before approving the default flip. Case: a plan proposed defaulting `source="unreal"` to one band, with explicit opt-in for the umbrella fan-out; the resolver (`_resolve_band_for_source`) was a documented protocol contract resolving `"unreal"` to every band whose `applicable_kinds` contained `"unreal"`, and a sibling resolver (`_resolve_engine_token`) already shipped the accept-with-nag pattern the cleaner fix re-used.

## Negative-Search Before Drafting

Before committing to a prescribed shape, run a negative search to surface prior decisions that argue against what the plan proposes to introduce or restore.

**No-fabrication branch — predicates citing fields must grep the field first.** A plan or predicate that asserts on a frontmatter key, env var, config field, or schema column without grepping for the literal name is fabrication, not verification. Extends the no-duplicate dimension into no-fabrication: *does the named field exist on disk?* Before writing any trigger gate, abstain condition, or rule that references a structured data field (`outcome:`, `status:`, `kind:`), grep the schema definition (e.g., `schemas/handoff.schema.json`, frontmatter validator) and quote a file:line citation. Absence of a grep citation against the schema is a plan smell. Empirically, a pre-flight checker's plan trigger-gate cited a non-existent `outcome: failed` field on a handoff schema (the actual enum was `active | consumed | superseded`); the gate would have fired on EM mood, not signal. See `coordinator/docs/wiki/pre-dispatch-verification.md` § Premise-Pass Discipline (`no-fabrication`).

1. **Identify the central nouns/abstractions** the prescription introduces or restores (e.g., a pattern name, an architectural layer, a specific tool or verb).

2. **Search for those nouns paired with prohibition vocabulary.** Grep `state/lessons/` and `docs/wiki/` for each noun alongside: `do not`, `never`, `tear down`, `deprecated`, `forbidden`, `removed`, `do NOT`. `bin/query-records` is also useful here for frontmatter-indexed records.

3. **If a prohibition exists, the plan must do one of two things:**
   - **(a)** Acknowledge the prior decision in §1 Objective and explicitly justify the reversal — with reasoning that engages the original argument, not merely reasserts the new direction.
   - **(b)** Recuse the prescription and choose a different shape that does not conflict with the prior decision.

4. **Reversal-verb hint:** If §1 Objective uses any of `restore`, `reintroduce`, `reconstitute`, `undo`, `re-add`, or `bring back`, the plan author should *consider suggesting* a staff-session to the PM before approval. This is a suggestion only — the PM owns the call. Frame it as: "This plan reverses prior direction; PM may want a staff-session before approving execution."

5. **External-doctrine proposals — independent location-challenge.** When a peer audit or external review recommends a fix, never adopt the proposed *location* uncritically — proposals frame fixes from where they noticed the problem, which is rarely the cheapest place to apply them. Run an independent location-challenge before drafting: would an upstream surface (producer skill, hook, dispatch template) prevent the class of problem more cheaply than the proposed downstream patch?

**Index/overview doc enumeration is NOT authoritative on a target file's actual headings.** Before dispatching against a named section in a multi-file refactor keyed off an overview or pipeline doc, grep the target file's own headings (`grep -nE '^#+ ' <target-file>`) and confirm the section exists. A PIPELINE overview lists phases; it is not a manifest of any one file's internal section structure. Full treatment: `docs/wiki/pre-dispatch-verification.md` § Index/Overview Docs Are Not Authoritative.

**Versioned-token plans must name the axis, not just the token.** When multiple distinct version concepts share a token spelling (e.g. three `SCHEMA_VERSION` constants — DDL/on-disk, consumer-graph, addon-protocol — coexisting in one tree), a plan that bumps "the SCHEMA_VERSION" without naming *which axis* will edit the wrong one or all three. Grep the literal token, enumerate every definition site, and state in the plan body which axis the change is on. This is the no-fabrication discipline applied to ambiguous-token identity, not just field existence.

**Read the LANDED schema for a cross-artifact id-prefix contract — never guess the prefix in a plan.** A plan that references another artifact's id prefix (goal-id, plan-id, session-id) must read the prefix from the *landed* schema before writing any well-formedness regex or field-shape table against it. Guessing the scheme (`gol-`/`g-` for goal-ids) ships a plan whose C-rules and regexes are wrong from the outset — even when a gating precondition later forces the executor to catch it, the plan should never have carried the wrong prefix. This is the no-fabrication discipline (§ above) applied to identifier *shape*, not just token spelling or field existence: grep the schema (`schemas/<artifact>.schema.json`) and quote the actual scheme. Empirical case: a spinoff-provenance plan speculated `gol-`/`g-` across its field-shape table and C2 rule; the landed `goal.schema.json` scheme was `goal-<slug>` (kebab, no enforced regex).

**Plan-substrate CLI verification via `--help` / argparse grep.** When a plan cites a script's CLI flags, require a `--help` excerpt or `argparse.add_argument` grep in the plan body — source-range inspection misses the actual surface. Reviewing the source file for argument *definitions* is insufficient; flag names surfaced to callers are in the `add_argument` call strings, which may differ from internal variable names. The Staff Engineer-level reviews have missed invalid flags this way (empirically, `--source engine --authority engine` cited in a plan were not valid flags).

**Remediation prose must name a command that BOTH exists AND performs the named action — verify existence *and* behavior.** When a plan's gate, runbook step, or recovery clause tells the executor to do something via a named slash-command, flag, or script ("stop the daemon via `/doctor --fix`", "reset state with `--clean`"), grep that the named primitive exists AND read what it actually does before hard-coding it. Existence is half the check: a primitive can exist and do the *opposite* of the named action. The 2026-05-30 case: a plan gate said "stop the daemon via `/doctor --fix`" — but no daemon-stop `--fix` existed, and the real `--fix` *restarts* the daemon, so the remediation would have done the reverse of what the gate intended. This extends the `--help`/argparse existence check above with a behavior check: confirm the primitive's effect matches the verb the prose assigns it. Prefer naming a dedicated script with a single unambiguous effect over a composite verb (`--fix`, `--repair`, `--reset`) whose behavior is broad and unconfirmed.

**Grep existing test fixtures before prescribing new ones.** Plan-write substrate verification must `ls tests/_*_fixture.py` and `grep -l "<symptom symbol>" tests/conftest.py tests/_*_fixture.py` before prescribing a NEW fixture. Canonical fixtures frequently ship before the plan that needs them — a plan that authors a duplicate fixture wastes executor time and creates a drift surface between two near-identical helpers. Rule: if a match exists, cite it as the canonical fixture; if absent, scaffold a new one. The fixture search is the same no-fabrication / no-duplicate check applied to the test layer.

**Verify prereq-cited banks/baselines with a dry-scorer/dry-validator pass before consuming downstream.** Handoff prereqs naming a specific class of artifact (smoke bank, graded bank, scored baseline) need a dry pass before leg 1 of the consuming workstream runs end-to-end. Without the dry pass, the consumer silently operates on a mismatched input class and produces subtly wrong outputs that pass all structural checks.

**Registrar-bound callables read like globals — grep the registration shape before asserting invocation counts.** Before drafting a plan whose fix slate cites N invocations of a callable like `foo()`, grep the registration shape (`def register_*`, FastMCP `register_*_tools`, FastAPI `Depends`, pytest fixtures) for `foo` as a *parameter* — a global-looking identifier at a call site may be bound at registration time by production wiring (e.g. `register_live_tools(mcp, get_project_root, …)` bound to `lambda: _effective_project_root()`). Grepping the literal name confirms the name *exists*, not what it *resolves to*; read the production call site that constructs the registrar args. plan-coverage-checker misses this — it verifies token presence at cited lines, not the symbol's binding. (Empirically, a plan asserted "10 boot-pinned `get_project_root()` sites" that were already parameter-bound and correct; it would have shipped a duplicate of already-shipped code.)

**Content-migration inbound-link greps must enumerate every citation form.** For any cross-repo / mass-delete content migration, the inbound-link grep pattern MUST enumerate all three markdown ref shapes per target — absolute (`docs/wiki/name.md`), bare-name (`name.md`), and self-relative (`./name.md`) — not just the absolute-prefix form. Markdown ref resolution is per-source-file relative, so the same target appears in 3+ shapes across the tree; a writer-mental-model grep ("how the path appears in MY edits") misses the reader-mental-model shapes. Empirically, an absolute-prefix-only grep let 25 broken links escape to the final gate on one such migration.

**When porting a pattern from a reference impl, verify every flag, path, and command-name against the TARGET repo.** Reference implementations carry environment-specific tokens — flag names, path conventions, command-name aliases — that are correct for the reference but may not exist in the target. Before dispatching an executor based on a reference-impl port, grep the target repo for each flag and path cited in the plan to confirm they exist there. Operator-doc attribution (e.g., which skill or hook owns a phase) must come from the target's live routing table, not from the reference's documentation.

**Deleting a vendored or shared constant requires grepping its re-export (back-compat shim) sites, not just direct importers.** A `from module import CONST` grep finds direct importers; it does not find modules that re-export the same constant for backward compatibility (`from original import CONST; __all__ = ["CONST"]`). A re-export shim hides the deletion's blast radius — downstream consumers of the shim break silently after the delete lands. Before any constant-or-symbol deletion, grep for the literal name in `__all__`, `from X import Y as Z`, and `importlib.import_module` patterns across all modules, not just the primary call sites.

**Durability assertions over a multi-writer file must enumerate ALL writers.** An assertion like "this file is durable across restarts" is quantified over every path that can write or overwrite the file. Single-writer coverage of a multi-writer surface produces a silently-false durability claim: if any writer resets the file, the durability contract is broken regardless of how careful the one covered writer is. Before asserting durability, grep for every writer of the target file (open for write, atomic rename, truncate+write) and enumerate them in the plan body.

**A policy-activation or value-relocation change that looks like a 2-file edit is usually an N-consumer + co-writer sweep — enumerate both directions at plan-write.** Two change shapes hide their real blast radius behind a small surface:
- **Monkey-patch passthrough → active policy.** When a patched API shifts from passthrough to enforcing a policy, every existing caller of that API becomes a new policy consumer. Grep every direct caller of the patched API (e.g. `git grep 'chromadb.PersistentClient'`) and check each against the new policy; add the call-site audit as a substrate-findings bullet. Treat "monkey-patch policy change" as a plan-coverage trigger to enumerate the patched-API call-site set as the oracle.
- **Untracking a machine-specific value from a shared tracked file.** A value in a shared file has N readers AND M writers. Moving it breaks any reader still pointed at the old file, and risks a clobber if a full-rewrite writer drops a co-tenant table. Grep every reader AND every writer, classify each as moved-key vs stays, and check install ORDER between co-writers — a later full-rewrite writer must preserve the earlier writers' tables.

**Vocabulary substitution instructions must be verified against the authoritative project glossary before mass-rename dispatch.** When a brief instructs X → Y vocabulary substitution, grep the project's `CONTEXT.md` (or canonical glossary document) first. The glossary may already reserve Y for a different concept, making the substitution a collision; or it may list X as a deprecated alias that maps to a different canonical term than Y. A mass-rename dispatched against an unverified substitution ships the collision into every occurrence. Require a glossary-diff step in the plan before any rename wave.

**Vacuous-true is not an AC pass.** When an acceptance criterion turns out vacuous at close-out time — the seam it was designed to exercise has moved, or the criterion reduces to a trivially-satisfied structural check — either re-anchor it to the moved seam or surface it as a stub-quality finding. A criterion that passes because nothing is checked is not evidence of correctness; it is evidence of an unverified requirement. The plan-coverage-checker's "vacuous-pass" bucket is the mechanical signal; the resolution is always re-anchor or open-finding, never mark-closed.

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
- `coordinator/docs/wiki/pre-dispatch-verification.md` § Plan-Time Verification Checklist, "Audit symptom is correct; locus may be wrong" — conceptual ancestor, firing at investigation time.
- `coordinator/docs/wiki/pre-dispatch-verification.md` § Plan-Time Verification Checklist, "Reviewer rationale must discriminate chosen shape from alternatives" — analogous discipline at review time.

Fix-locus discrimination fires **between** them: at plan-author time, after substrate verification, before the first task is drafted.

**Protocol-tier semantics aren't a default to flip — multi-tier resolvers make every "default change" a contract break.** When a plan proposes to "change the default" on a stringly-typed dispatch slot (a routing key, a verdict enum value, a kind tag), grep the resolver before approving. If resolution is multi-tier — exact-match plus an umbrella/glob/group fallback, or any layered cascade — the affected token is at protocol altitude: every existing producer encodes assumptions about which tier their token resolves on, and a "default" flip silently re-routes those producers without their authors' knowledge. The right shape is almost never a default change; look for an `accept-with-nag` analog already in the codebase (the dispatch still routes the legacy way, but a one-shot warning surfaces the migration). Surface multi-tier resolution to the reviewer at plan altitude and reframe the chunk as a recommendation/nag rather than a default swap.

**Reference-plan prose is hypothesis; the shipped manifest is truth.** When mirroring an existing artifact's disposition — "do what plan X did for case Y" — grep its *shipped* manifest (probe block, test ID, config file, hookspec entry) plus the runtime behaviour, not the prose of the cited plan. The reference plan's stated disposition can diverge from its own shipped artifact (a late chunk amended the manifest after the body froze; a follow-up DR overrode the original framing; a corollary chunk landed without back-porting the prose). Inheriting the prose-disposition into your own plan inherits the divergence. Discipline: every "mirror existing precedent" plan body cites the *manifest line and the runtime witness* it inherits from — not just the precedent's plan title.

**"Mirror function X exactly" dispatch briefs need a negative-spec naming what NOT to mirror when X has side effects.** Telling an executor to make a new function "an exact structural analog of `X()`" is safe only when `X` is pure. When the reference function publishes a boot-state sentinel, burns a once-only token on a `None`→value transition, or mutates shared state on first call, a verbatim copy corrupts that shared state on the analog's first run. Before writing a "mirror X" brief, read X for side effects; if any exist, add a negative-spec block enumerating the side-effecting lines the analog must NOT reproduce. Empirically, a plan-review caught a `get_engine_structural_index_path()` brief told to exactly mirror `get_engine_collection_path()` — the reference published the engine boot-state sentinel and burned an exactly-once token, so the verbatim copy would have corrupted the freshly-shipped sentinel and written a struct-index at the wrong transition.

**A fork arm that rests on an external binary is only as real as that binary RUNNING on the target platform — verify it RUNS before ranking the fork.** When a plan weighs two or more approaches and the "precise" / "architecturally correct" arm depends on an external CLI or binary (a language-server indexer, a transpiler, a vendored analysis tool), that arm's cost is contingent on the binary actually executing on the target OS — not on its existence in a package registry. Before letting the dependent arm weight the decision, run `--version` (or a minimal invocation) on the target platform and check installed-vs-latest plus any known platform breakage. If the binary crashes or is unavailable, the "correct" arm is DOA, and the cost of vendoring/patching upstream must go in *that arm's cost column* before you choose — otherwise the ranking inverts the moment the executor discovers the binary doesn't run. The 2026-05-30 case: scip-python 0.6.6 (latest) crashes on Windows, so the "architecturally correct" arm that rested on it was dead on arrival; ranking it as the winner without a `--version` check would have inverted the recommendation. **Distinct from the runtime-degrade external-CLI-producer rule** (a producer that degrades at *runtime*): this is verifying a *candidate* binary runs *at plan-time* before its availability weights a fork-ranking decision.

## File Structure

Before defining tasks, map out which files will be created or modified and what each is responsible for:

- Design units with clear boundaries and well-defined interfaces
- Prefer smaller, focused files over large ones doing too much
- Files that change together should live together — split by responsibility, not technical layer
- In existing codebases, follow established patterns; include splits for unwieldy files when reasonable

This structure informs task decomposition — each task should produce self-contained changes.

**Factor shared interfaces into their own chunk.** (A *chunk* here = one executor-sized unit of work — see § Bite-Sized Task Granularity below.) When several chunks will consume a *new* shared surface — a helper, a kwarg, a schema field, an envelope extension — do NOT bundle that surface into one consumer chunk alongside its other work. Welding the shared API to one consumer makes the parallelism invisible: every *other* consumer now appears to depend on the whole fat chunk, when it actually depends only on the interface. Draw the shared surface as its own minimal chunk (`C0`) and pin its interface. The consumers then fan out against it — concurrently by default (the producer runs in the same wave; verification concentrates at merge), or after `C0` lands as a predecessor wave when the interface can't be confidently pinned. See `dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy (Author vs. verify) for the default/fallback call.

This is the **plan-time twin** of the dispatch-time "promote shared-API to a predecessor wave" rule (`dispatching-parallel-agents.md` § Shared-API Gap). That promotion is only *drawable* if the plan didn't already bury the interface inside a consumer — by dispatch time, the fat chunk has already collapsed the fan-out. Catch it here, at chunk-drawing time.

**Test:** if extracting one chunk's shared-surface work would unblock *two or more* other chunks to run concurrently, that surface belongs in its own chunk. Empirically (self): `C1` was drawn as "extract `host_probes` + rewire one consumer + add the kwarg + land the regression net" — the shared interface (`host_probes` + kwarg) welded to one consumer (the rewire). Every other consumer then read as "depends on C1" wholesale; the trivial `C0`-then-fan-out shape was never surfaced.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

**Additive-before-destructive ordering.** When chunks are file-independent and one is purely additive while another removes existing code, land the additive chunk first. The destructive chunk's regression window shrinks because the additive piece is already in the codebase — reviewers and tests can verify behavior before removal, not after.

- Order chunks additive-before-destructive — scaffolding/new-symbol chunks land before delete-old-symbol chunks. A destructive chunk that lands before its replacement is staged risks a broken intermediate state on rollback.

**14-minute single-executor run signals under-decomposition.** When an executor's observed wall-clock time approaches or exceeds 14 minutes, that is a structural signal — the chunk spans multiple distinct surfaces or concerns and should have been split further. The target per-executor budget is ~5–10 minutes on ONE coherent surface (15-minute hard ceiling). If a plan chunk would exceed this in practice: split before dispatch, not after the executor stalls. Empirical: a 14-min run welding indexing + fixture authoring + CLI wiring into one chunk cut down to an 8-minute longest executor once each surface was split out separately. Companion to `coordinator/docs/wiki/dispatching-parallel-agents.md` § Sonnet Chunk-Sizing Is a Correctness Constraint, Not Just an Efficiency One ("small-remit-and-many beats large-remit-and-one, every time" — "~5–10 min on one coherent surface, 15 min ceiling"; "never hand a single agent a multi-change remit that will hit compaction mid-work and grind").

**Sizing from inside an investigation under-counts execution scope 2-3x.** Scope numbers derived from inside a spike systematically under-count the executor's cost. Apply 2× to any spike-derived scope estimate, or dispatch a scope-scout before writing the plan.

**Scaffolded config files must self-disclose their supported subset.** A scaffolded config in a familiar format (`.gitignore`-shaped, JSON-schema-like, INI) must declare which subset of the format is actually honored in a header comment — OR the plan must instruct the executor to implement the full format. Catch at plan-time by walking the proposed default body through the matcher implementation. (Surfaced by `/percolate`'s `.percolate-ignore` shipping `**/scratch/` as dead code — the bash `[[ ]]` matcher didn't handle `**/`.)

## Test Surface

**A chunk's named test surface must be Tier T — path-scoped to the files/dirs that chunk itself authors or touches.** The tier ladder (Tier T / Tier F / Tier U) is canon in `coordinator/skills/validate/SKILL.md` § "Tier classification is by shape, not by config key" — this section cites that ladder, it does not restate it. Naming the repo's fast tier (Tier F) or full suite (Tier U) as a chunk's test surface is malformed **at plan-write time**, for the identical reason `coordinator/skills/execute-plan/SKILL.md` (line ~209) calls a dispatch brief naming either "malformed, full stop": authoring it into the plan body doesn't avoid that deny, it just defers it to dispatch — after the plan has already cleared `coordinator:review` and been PM-ratified on the strength of a test-surface row that was never enforceable as written.

Global or cadence-scoped verification (Tier F/Tier U) still has a legitimate home — it is just never a chunk's test surface and never a plan deliverable. It is **EM-owned, at the wave boundary or the cadence gate**: `execute-plan/SKILL.md` (line ~209) specifies that mechanism (the EM runs the global/registry check itself, once, after a wave's chunks land Tier-T-green, under a live test-invocation grant). A plan should rely on that mechanism existing, not re-author it into a chunk brief.

**Worked example.** One plan's chunk row named, among its deliverables, "run full suite green" — a Tier-U instruction baked into the chunk brief itself. That's the anti-pattern this section exists to catch: it reads fine at plan-review time and only surfaces as malformed once execute-plan tries to dispatch it. A corrected row would instead name the chunk's own scoped test file — the file the chunk itself writes, run at Tier T — as the test surface, with the full-suite run dropped from the chunk entirely; if a global check is warranted it belongs to the EM's wave-boundary verification, not the chunk's write-files or deliverables list. That plan's dispatch-ledger row went uncorrected on disk for a time — a live specimen of the anti-pattern this section exists to catch.

**What is mechanically enforced, and what is not.** `hooks/scripts/nudge-plan-test-surface-tier.py` advises at plan-write time, but only on suite-shaped **commands** in imperative position — it delegates to the shared engine-plane suite-invocation classifier, which reads commands, not English. The worked example above (`run full suite green`) yields zero classifier hits: it is prose, so the hook stays silent on the very row that motivated this section. That is a deliberate coverage boundary, not a defect to route around by bolting prose-matching onto the hook — matching English in a corpus this dense with quoted commands and negated examples buys false positives faster than it buys catches. The prose form is caught by plan review. **The hook's silence is not evidence the rule is satisfied.**

## Substrate-drift mid-execution = Branch D plan amendment, NOT executor-scope expansion

When mid-execution drift blocks an executor (the substrate on disk differs from plan assumptions), the right path is Branch D plan amendment — not telling the executor to work around it. Scope-expanding the executor bypasses the doctrinal lenses (the Staff Engineer review, prior-art-checker, coverage-checker). Apply: when an executor surfaces `BLOCKED: substrate-drift`, stop the executor, invoke Branch D of `coordinator:plan` with the drift description, and re-plan before re-dispatching.

## Heading-Anchor Discipline

**Use ASCII (`:`/single `-`) in headings intended to be linked — Unicode dashes (em-dash `—`, en-dash `–`) in heading text cause silent slug-rot in cross-doc links.** Markdown parsers strip or percent-encode Unicode punctuation when generating fragment IDs; a link authored against the raw heading text silently resolves to nothing after the first renderer normalizes the slug. Apply: before writing a heading you expect to cross-link, check that it contains only ASCII characters in the fragment-forming region. If an em-dash is desirable in prose, rewrite the heading to use a colon or a plain hyphen instead (e.g. `## Schema Bump — Backstop Rule` → `## Schema-Bump Backstop Rule`).

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

<!-- Optional. Plans may carry an AC table as a reviewer's design lens.
     Use simple prose form: ID | Criterion | Status -->

| ID | Criterion | Status |
|----|-----------|--------|
| AC-1 | [Testable criterion] | ☐ |

## Non-Goals

- [Explicitly out of scope — heads off mid-stream scope creep]

---
```

**Why these fields are required:**
- **Scope mode** routes review depth and the evidence bar. Reviewers and `/merge-to-main` read it.
- **Acceptance criteria** are what reviewers check against and what the ship verdict scores. Without them, "done" reduces to "the agent says it implemented it." AC tables are optional; when present they serve as the reviewer's design lens (see § Acceptance Criteria (optional) below).
- **Non-goals** are the most-skipped field and the single highest source of scope drift. Spend 30 seconds on them.

The `Status:` field is **EM-owned** and is part of the write-ahead protocol — it gets updated at every phase transition (review, enrichment, execution) so that crashed sessions leave unambiguous state. This is unchanged.

**A plan is authored `draft` and never hand-advanced past it.** The author writes `status: draft` once, at scaffold, and stops — every later rung (`reviewed`, `approved`, `executing`, `landed`, `implemented`) is produced by a ceremony-fired op, never a plan-writing step. See `docs/wiki/coordinator-tripwires/plan-status-ladder.md` for the full rung table and producers; do not add a status-advancing step to a plan or skill on the strength of this section.

**Per-chunk executor in-flight state** lives in a dedicated sidecar at `tasks/<plan-slug>/flight/<chunk-id>.md`, not in the plan body. The EM creates the sidecar at dispatch time; the executor updates it. The plan body is mechanically immutable to executors — a PreToolUse tripwire fires closed on any subagent Edit/Write to `docs/plans/**/*.md`. Do NOT stamp `**Status:**` into a plan section; write to the sidecar instead.

**Disambiguation:** "Plan-body `**Status:**` is EM-owned phase state. Sidecar frontmatter `status:` is executor-owned lifecycle state. These are distinct fields; do not cross-reference."

**Cross-references:** `agents/executor.md § Flight-Recorder Sidecar`, `ARCHITECTURE.md § The Write-Ahead Status Protocol`.

**Do not author a `## Deviations` audit table.** Forecast-vs-shipped reconciliation happens entirely via `(was: <plan-forecast>)` ALLOWLIST annotations in the Decisions Made / API Contracts sections (the load-bearing surface for `/distill` Phase 1 `[SUPERSEDED]` classification). `/workstream-complete`'s `plan-vs-reality-reconcile` judgment point corrects ALLOWLIST sections in place. A plan carrying a `## Deviations` table is handled by `/distill`, which drops it as `[EPHEMERAL]`.

## Acceptance Criteria (optional)

Plans MAY carry an `## Acceptance Criteria` table as a reviewer's design lens, in prose `ID | Criterion | Status` form. It is not required and is not mechanically gated — the table helps reviewers check that criteria are testable and complete, but no automated gate enforces it.

## Machine-Parseable Task Spine

> Schema: `coordinator/schemas/plan-tasks.schema.json` (per-row shape), wired into `coordinator/schemas/plan.schema.json`'s `tasks` property via `$ref`.

A plan's `## Tasks` section carries **EXACTLY ONE** fenced code block, info-string
` ```yaml plan-tasks `, directly under the `## Tasks` heading. This is the
**parser-locate rule** — a mechanical tool (`plan-coverage-checker`, the deferred-harvest
CLI) locates the block by scanning for that exact heading-then-fence adjacency, not by
scanning the whole document body for any YAML fence. The block body is a YAML list of
task objects, one per plan chunk (shipped or deferred).

**Zero fenced `plan-tasks` blocks, or more than one, is a defined error** — but the two
consumers disagree deliberately on severity:

- **`plan-coverage-checker` FAILS LOUD.** It cannot do its job (verifying the fix slate
  against the spine) without exactly one spine to read.
- **The deferred-harvest CLI WARNS-AND-SKIPS.** A plan mid-authoring may not have a task
  spine yet — the harvest should not hard-fail an in-progress plan that simply hasn't
  reached the point of drafting `## Tasks` yet.

### Authoring the block

Each list item is a task object with the following fields:

| Field | Type | Required? | Semantics |
|---|---|---|---|
| `id` | string | required | Chunk id (`C1`, `D1`, ...). Unique within the plan. Deferred rows conventionally use a `D<n>` prefix — this is a naming convention, not a schema-enforced discriminator; `deferred: true` is the actual signal a tool reads. |
| `title` | string | required | One-line brief. Becomes the queue-entry title on harvest. |
| `change_kind` | enum | required | The **WIDER UNIVERSAL** enum: `doctrine-edit`, `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`, `wiki-new`, `wiki-append`, `skill-edit`, `doc-edit`, `test-edit`, `code-edit`, `config-edit`, `verification`. The value names the **surface changed**, not the flavour of the change — do not coin a work-shape token (a bash-to-Python port of a `bin/` utility is `script-edit`); a non-member routes nowhere on harvest, which is how a ratified deferral gets dropped. `verification` is the one member for a row whose deliverable is evidence, not a diff. |
| `surface` | string | required | The harvest/coverage **PRIMARY-TARGET** field — a single path or subsystem. Maps to the queue entry's `surface` field ONLY. This is deliberately **not** the wave-map's write-files set (which may enumerate many files) — `surface` names the one primary target a triager would look at first. |
| `queue_scope` | enum `project`\|`central` | optional (default `project`) | Which improvement-queue the harvest writes into. `central` is a per-deferral opt-in, mapping to `coordinator-queue-append --queue-scope central`. |
| `deferred` | bool | **LEGACY — read-tolerance only, no live authoring path** | Formerly `true` meant this row is NOT shipped by this plan. Superseded by `disposition: backlogged` (see below). Retained on the schema only because a live consumer's corpus still contains it; do not write it on new rows. |
| `disposition` | enum | optional (default `open`) | **THE authoring surface for row resolution.** `open \| coded \| spun_off \| backlogged \| wont_do`. `open` is live, undecided work. `coded` means the row shipped (evidence: a commit SHA). `spun_off` / `backlogged` / `wont_do` are closed dispositions — the row is not being built by this plan, and each names why. This is a deliberately separate vocabulary from `handoff.carried_items[].disposition` (`carried \| closed \| spun_off \| blocked`, `coordinator/schemas/handoff.schema.json:706-712` <!-- Review: coordinator:code-reviewer — citation off by one, corrected to the disposition field's actual span -->) — the two enums share exactly one member, `spun_off`, and are otherwise disjoint by design: a handoff row answers what TRAVELS to the next session, while a plan-tasks row answers whether the work GOT BUILT. |
| `disposition_ref` | string | **required for `coded`/`spun_off`/`backlogged`; forbidden for `open`/`wont_do`** | The forward-pointer evidence, singular by contract (never a range, comma-list, or branch name). `coded`: a single 7-40 char hex commit SHA, pattern-validated. `spun_off`/`backlogged`: a single repo-relative path (a spinoff doc, a queue-entry filename). |
| `disposition_detail` | string | **required for every non-`open` disposition** | Prose rationale. `wont_do` carries no `disposition_ref`, so this is its sole evidence for why the row was cut. |
| `case_against` | string | **required for `backlogged`/`wont_do`** | The strongest HONEST case for doing the work now, plus the EM's recommendation, confidence, and what would change it. Written at `plan_tasks.mutate set` — no new verb; see § Both-Sides Deferral Argument below. |
| `pm_approved` | bool | **LEGACY — read-tolerance only, no live authoring path on a governed plan** | On a plan with no `grouping_approvals` frontmatter block (a legacy plan), this per-row bool is still the gate: `false` or absent on a closed-disposition row (or a legacy `deferred: true` row) is a `plan-coverage-checker` flag. On a **governed** plan (frontmatter carries `grouping_approvals` — see § Grouping Approvals below), this field is not read as authorization at all; ratification lives in the plan-document-level `grouping_approvals` block, one per grouping, and a bare `pm_approved: true` on a row in that plan records nothing the gate consults. `coded` never needed PM sign-off either way — it is evidence of work done, not a scope decision. |
| `body` | string block | optional | Multi-line detail. Maps to the queue entry's `body` field. |
| `writes` | array of strings | **required on every non-deferred row** (`deferred: true` rows are exempt — harvest candidates, never dispatch candidates) | Repo-relative paths this task writes (plain strings; no glob syntax in this version). This is the surface-vs-write-files-set distinction `surface` points at above: `surface` is the single harvest/coverage primary target, `writes` is the net-new full write set, and write-overlap/wave-map derivation is a pure function of `writes` across the spine's rows. **Three spellings; name the one you wrote and never call any of them "empty".** Key **absent**, or **present with no value** (YAML null — colon, then nothing): equivalent, both *not-yet-knowable*. Such a row is not provably disjoint from any other, so it lands in a solo wave, which then refuses at commit time until the row is filled in. `writes: []` is the opposite — a **positive claim that this row writes nothing**: it may share a wave with declared-writes rows, and is excluded from that wave's commit pathspec. |
| `reads` | array of strings | optional | Repo-relative paths this task reads without writing. Same string-array shape as `writes`. |
| `depends_on` | array of objects | optional; **absence is a positive claim of no non-computable gate on this row** | One entry per predecessor row this task's execution is gated on — object shape `{chunk, gate_kind, note?}`, never a bare chunk-id list. Required wherever the author imposes a gate the write-overlap graph cannot derive on its own (never for write-overlap itself — the wave-builder computes that from `writes`/`reads`). Full field shape, valid `gate_kind` values, and a worked example: § Substrate-Migration Sequencing below. |
| `external_gate` | array of objects | optional | Declared blockers on work owned by ANOTHER repo — one entry per blocking party. Each entry: `owner_repo` (required, bare hyphenated repo shortname; confirm the spelling with `machine-local keys | grep '^repos\.'`; never this repo's own shortname — that's an intra-plan blocker, belongs on `depends_on` — and never a session id), `condition` (required, prose — what must become true before this row executes), `closure_evidence` (optional — memo path, commit SHA, or probe naming HOW closure is or will be verified; clears nothing on its own), `cleared` (optional bool — asserts the gate IS discharged; `cleared: true` clears it outright, `cleared: false` is an explicit negative that overrides a truthy `closure_evidence`), `closure_key` (optional object, `{kind, id}` — the machine-matchable IDENTITY of what discharges the gate, `kind` one of `deliverable`\|`memo-thread`; a reader matches it against a `discharges.closure_key` block on a cross-repo memo from `owner_repo` and may propose the `cleared: true` flip, never perform it), `blocks` (optional, enum `execution`\|`ac-closure`, default `execution` — whether the gate blocks the row's execution or only a named acceptance criterion's closure). A sibling field to `depends_on`, not nested in it: an external blocker has no local predecessor row, so it cannot fill `depends_on[].chunk`. NOT for intra-plan edges (use `depends_on`) and NOT a substitute for the write-overlap gate the wave-builder computes from `writes`/`reads`. |

**Which closure field to write.** Three fields on an `external_gate` entry look related and
answer different questions: `condition` is reader-facing prose, never machine-evaluated —
what a human reads to judge the gate. `closure_evidence` names HOW closure is or will be
verified — a probe, a path, a SHA — and clears nothing by itself. `closure_key` names WHAT
identity discharges the gate, machine-matchable and writable before the discharge happens.
`cleared: true` is the one and only clearing path, on both readers. Reaching for
`closure_evidence` to declare a gate discharged is the common mistake — set `closure_key` for
identity and flip `cleared: true` to actually clear it.

**Closure needs PM ratification — this is not a self-service escape hatch.** A row resolved to
`spun_off`, `backlogged`, or `wont_do` is a plan author cutting scope, and that cut needs the
PM's sign-off before it counts as closed. On a **governed** plan (§ Grouping Approvals below)
that sign-off lives on the plan document itself, as a `grouping_approvals` block per grouping —
`do` / `defer` / `ruled_out` — not on the individual row. `plan-coverage-checker` is a
**report-only** surface: it surfaces an unratified cut to a plan author at review time, but it
does not itself gate anything closed. The hard enforcement — the check that actually refuses to
treat a row as authorized-closed — lives in the claude-klabauter frontmatter layer
(`schema_validate.py`'s `check_plan_tasks_grouping_approval`) together with the write-guard pair
that blocks a plan-body edit from mutating its own approval state. Only a grouping carrying
`status: approved`, a non-empty `pm_utterance`, and a digest that matches a fresh recomputation
over the grouping's current membership authorizes the rows in it; a plan author toggling
`pm_approved: true` on a governed plan's row does not do this work — see the table above.

**An execution authorization is not a scope authorization.** "Handoff for execution when ready,"
an `execution_authorized_at` stamp, or any prior go-ahead on the plan authorizes *building what
the plan says* — it never pre-approves a scope decision the plan makes afterwards. A closed
disposition IS a scope decision, so it is never covered by an earlier "execute when ready."
Neither are changed deliverables. The PM's framing, verbatim:

> "sometimes EMs just think that because I said 'handoff for execution when ready' that that
> constitutes an approval of whatever the plan will become. Instead, I'd rather that deferrals get
> flagged to me, and a 'when ready' doesn't cover 'scope-shaped' items or 'deliverables changing'."

On a governed plan, that utterance is what `pm_utterance` on the grouping's `grouping_approvals`
block carries — verbatim, never synthesized or backfilled from "the PM would have approved."
`pm_approved: true` on the row itself is the pre-grouping shape: still read-tolerated on a legacy
plan, but it is a bare bool with no utterance attached, which is exactly the gap the grouping
block closes. An EM concluding the PM would have approved is the failure this whole mechanism
exists to make visible. Flag the cut and get the answer; do not infer it.

**`deferred` is legacy; `disposition` is the live vocabulary.** New plans author `disposition`
directly — a row that ships is `disposition: coded` with the shipping commit SHA in
`disposition_ref`, not left implicitly-shipped-by-absence. `deferred: true` with no `disposition`
set is treated as legacy-equivalent to `disposition: backlogged` by every live consumer
(`coordinator-harvest-deferrals`, `plan-coverage-checker`) — read-tolerance for the pre-existing
corpus, never a shape to write on a new row.

### Both-Sides Deferral Argument (`case_against`)

A candidate scope-cut row is authored `open`, carrying its argument, and only later flipped to
`backlogged`/`wont_do` once ratified. That argument is **both-sided**, not a one-sided pitch for
the cut: the case FOR (`disposition_detail`), the case AGAINST (`case_against`), and a
recommendation naming the EM's confidence and what would change it.

**This requirement is blanket, not scoped to the EM's own uncertainty.** An EM who is confident
in a cut does not get to skip `case_against` on the theory that a confident cut needs no
counter-argument — the EM proposing the cut has already decided, which makes the EM the *least*
reliable party to judge which cuts deserve the PM's attention. The field exists precisely for the
cuts the EM feels most sure about, not the ones already in doubt.

**Honest-limit clause.** The bar is the strongest HONEST case against the cut, not any case. A
strawman — a case against phrased so weakly it can't win — satisfies the field's mechanical
presence requirement while defeating the rule it exists to serve. `plan-coverage-checker` narrows
this (a specificity sub-check asking whether `case_against` names a concrete consequence tied to
the row's own surface, versus merely negating `disposition_detail`) but cannot fully close it by
grep alone — presence of the field does not settle whether the question was honestly asked. Read
the field, don't just count it.

**PM ruling — the positive clause.** An EM's case FOR deferring often rests on a constraint only
the PM can lift: cross-team alignment the EM cannot get, a resourcing call the EM cannot make.
Because that constraint is visible only to the PM, `case_against` should name specifically WHAT
would have to change and WHO could change it — not just assert that the cut is disputable. This
is exactly why the argument is put to the PM rather than settled by the EM: the PM may bring
authority to the conversation the EM does not have, so a deferral's own reason can EVAPORATE
mid-conversation rather than being cleanly ratified or rejected as recorded. That is also why the
requirement stops at showing the argument and does not extend to sealing `pm_utterance` against
it after the fact — the argument is read live, at the moment of ratification, not audited later
as a static fact.

**The n=4 rule.** At 5+ candidate scope-cut rows, the EM does not enumerate five separate
arguments. It describes the shape the cuts form, groups them into buckets, and proposes a
spinoff per bucket. A long deferral list is itself a **scope-misalignment signal** — scope drift
surfacing during investigation is normal and blameless, and the correct response is re-scoping,
not writing more documentation to justify the drift. This doctrine is descriptive, not punitive:
a plan that grows a long deferral slate found something real about its own scope, and the bucket
response is how that finding gets acted on. The threshold of 4 is **provisional** — inferred from
the PM's "I've never seen more than four," not a value the PM deliberately fixed — and should be
re-derived once `plan-coverage-checker` has counted real plans. A number whose provenance is
invisible cannot be revised by anyone who did not write it, so this paragraph is that provenance.

**The airtime discriminator.** Where the EM is unsure how much depth a given cut deserves, the
test is **load-bearingness**, not EM confidence — how much would break, or how much of the plan's
outcome would change, if the cut turned out to be wrong, not how sure the EM feels about it.

### Grouping Approvals — the live ratification mechanism

A plan's frontmatter may carry a `grouping_approvals` key. Bare presence of that key is the
**whole** discriminator between a **governed** plan and a **legacy** one — there is no
`schema_version` conjunct and no version fallback anywhere in the read path. A plan without the
key is legacy and keeps the per-row `pm_approved` gate described above, unchanged. A plan with
the key is governed, and ratification for its closed rows lives on the block, not on the row.

Three groupings, **derived** from each task-spine row's `disposition` and never stored anywhere
themselves:

- **`do`** — rows with `disposition: open` or `disposition: coded`. Live or shipped work; never
  gated by this mechanism.
- **`defer`** — rows with `disposition: spun_off` or `disposition: backlogged`.
- **`ruled_out`** — rows with `disposition: wont_do`.

Each grouping carries its own approval block: `status` (`pending` | `approved`), `approver`,
`approved_at` (a date), `pm_utterance` (the PM's verbatim reasoning — required non-empty when
`status: approved`), and `digest` (`sha256:<64 hex>`, required when `status: approved`).
Plan-level approval is the **sum** of the three block statuses, computed at read time — there is
no fourth "plan approved" field to keep in sync, because a stored rollup is a second home for a
derivable truth and the two would drift.

**The digest's scope is narrow on purpose.** It covers only the sorted set of `(row id,
disposition)` pairs for the rows currently in that grouping — nothing else. It does **not** cover
plan body prose, row order, row `body`/`disposition_detail` text, or any other frontmatter field.
Widening it to a whole-body hash is the specific regression to avoid: a whole-document digest
looks like it makes approval "more thorough," but it actually reintroduces self-certification —
whoever edits the plan can recompute and re-stamp a whole-body hash themselves, exactly as they
could a bare bool, just with more bytes hashed. The narrow membership-set digest is what forces a
fresh PM utterance whenever the *set of rows in a grouping* changes, without also invalidating
approval every time someone fixes a typo in unrelated prose.

**Presence-only is not taken bare, either.** A governed plan whose `grouping_approvals` block is
malformed, or that is missing the block a closed row's grouping needs, fails loud with a remedy
naming the grouping — it does not silently degrade to the legacy per-row gate. A malformed
governed plan is a defect to fix, not a reason to fall back.

### Harvest routing (informational — the harvest CLI owns the mechanics)

The harvest-eligible slice of `change_kind` is the project-tier subset
(`script-edit`, `skill-edit`, `wiki-append`, `wiki-new`, `hook-edit`, `agent-prompt-edit`,
`doc-edit`, `test-edit`, `code-edit`, `config-edit`, `verification`) — these route to `coordinator-queue-append --schema
improvement-queue --queue-scope <row queue_scope, default project>`. The remaining two
values (`doctrine-edit`, `snippet-sync-update`) route instead to
`coordinator-lesson-promote` (the lessons-outbox path) — the improvement-queue schema
rejects those two kinds at project scope. Harvested rows land with `status: open` (never
the queue's own `status: deferred` value — a harvested row is newly-opened work, not a
pre-deferred queue entry). **`## Anti-scope` items are never harvested**, regardless of
their `deferred`/`pm_approved` values — anti-scope is a warning about what NOT to do, not
a deferred-work candidate.

**A harvested deferral carries both sides.** The queue entry a harvest writes carries
`title`/`body`/`surface`/`change_kind`/`proposed_action` — all of which state the case FOR the
work. Without more, the moment a deferral becomes a backlog item the only surviving record is the
argument that *won* the cut, and the triager who picks it up months later inherits a one-sided
file with no way to see what was argued on the other side. `improvement-queue.schema.json` (1.2.0)
therefore carries an optional `case_against` string mirroring the task-spine field (§ Both-Sides
Deferral Argument above), so the argument survives the cut rather than stopping at the plan.

The field is **optional, and not yet populated**: the harvest CLI is owned by the control-plane
engine, not by this doctrine surface, so the schema half lands here while the population half is
requested of that capability separately. An entry written by today's harvest simply omits the
field and stays valid. Do not read the field's presence in the schema as evidence the harvest is
already filling it.

### Malformed-row disposition

A row missing a required field, or a block that fails `yaml.safe_load` entirely, is:

- **SKIPPED-WITH-WARNING** by the harvest (defensive parse-or-skip — one bad row must not
  abort a harvest run over an otherwise-valid spine).
- **FLAGGED** by `plan-coverage-checker` — report-only, but the surface a plan author
  actually sees at review time.

**Post-scaffold hand edits to the `## Tasks` block are Tier-2 (warn, never block)** — the same
posture the whole coordinator system applies to free-form prose-seam edits. A hand-edited
row that drifts from the schema is warned on, not rejected outright; the mechanical gates
above (coverage-checker FAIL-LOUD, harvest WARN-AND-SKIP) are what actually catch drift at
the points that matter.

## Full-Coverage Scoping — Default Is the Complete Problem Set


**Default plan scope is the complete problem set the PM named — not the slice that fits
one session.** A plan's job is to cover the problem; a session boundary is a scheduling
constraint on execution, not a scoping input on the plan body. Planning MAY legitimately
span multiple sessions — `/handoff-for-execution` mid-plan is **normal continuity**, not a
scoping failure and not evidence the plan was "too big." A plan that spans three
`/handoff-for-execution` cycles because the problem genuinely has that many chunks is a
correctly-scoped plan; a plan that quietly drops chunks 6-9 to fit inside one session is a
mis-scoped one, even though it "finished" faster.

**The anti-pattern this section names: partial-to-fit-one-session.** The tell is a plan
whose task list stops not because the problem is covered but because the session felt
long enough, or the EM wanted a clean single-session close. This produces the exact
failure `plan-coverage-checker` (C3) and the deferred-harvest CLI (C4a) exist to catch
downstream — but catching it at review/harvest time is strictly worse than not
introducing it at plan-authoring time. Scope the plan to the problem first; let session
boundaries fall out of chunk count, not the other way around.

**Deferral is a PM decision, never an EM self-service scope trim.** If a piece of the
complete problem set genuinely should not ship in this plan, it does not silently vanish
from the task list — it becomes a `disposition: spun_off`/`backlogged` row on the spine (see
§ Authoring the block above), and that cut is only legitimate once the PM has ratified it. On a
legacy plan the mechanized surface for spotting an unratified cut is `plan-coverage-checker`'s
deferral-flag check — a closed-disposition row with `pm_approved` false or absent is flagged.
That checker is **report-only**, on both the legacy and governed paths: it surfaces the gap to a
plan author at review time, it does not itself withhold authorization. On a governed plan the
actual gate is the `defer` grouping's `grouping_approvals` block (§ Grouping Approvals above) —
`status: approved` with a matching `pm_utterance` and a fresh membership digest — enforced by the
Claude-klabauter frontmatter layer, not by an EM's own judgment that a cut was reasonable. See
`## Branch C — Compose the plan body` in `coordinator/skills/plan/SKILL.md` (the "soon = now" deferral row
and the YAGNI row) for the authoring-time version of this same discipline, and `## Branch A` in
the same skill for the triage-time scoping check this section extends.

**Adoption note.** The machine-parseable spine (`## Machine-Parseable Task Spine` above)
is built for the executing EM's ease, not as process overhead bolted on top of planning —
one YAML block per plan, fields you'd be tracking in prose anyway, no new ceremony. Give
it a go on the next plan you write; a longer, persuasive case for the format lives in a
separately spun-off roadmap document and is deliberately not re-litigated here.

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

> See `coordinator/docs/wiki/pre-dispatch-verification.md` for the pre-dispatch confidence checklist.

When a plan targets a gated path (MCP verb, hook, build system, auth flow) and the first fix unblocks one gate but reveals a second, **the correct response is to trace the full path before claiming the fix is complete**, not to ship after clearing gate one.

**Principle:** bypass one gate, trace the full path. Fixes that target a single gate often reveal the next gate immediately downstream — stacked-gate diagnosis is empirically common in UE plugin pipelines, MCP auth flows, and coordinator hook chains.

**In plans:** when a task's acceptance criterion is "passes gate X," include an explicit verification step that walks the full downstream path (not just the gate being targeted). If gate X passes but gate Y blocks, the AC is not met.

**Measurement loop (P4):** if repeated fixes keep hitting the next gate, you're in a stacked-gate scenario. Shift the plan to "enumerate all gates in this path before writing any fixes" — one investigation pass at the start is cheaper than N sequential fix-and-reblock cycles.

## Digression Governance

> See `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off for the plan-first doctrine this governs.

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

> See `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off for the round-trip framing.

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

**A spike's verdict is only as strong as its observation window — a window shorter than the failure's timescale yields a confidently-wrong "it persists" / "it's stable."** When a spike answers a temporal question (does this leak? does this drift? does the daemon stay up? does the value persist across N cycles?), a too-short window observes only the pre-failure régime and reports the wrong verdict with full confidence — the property "held" only because the spike stopped watching before it broke. At plan-write time, state the observation window AND its size explicitly, and justify it against the suspected failure timescale: a leak that manifests over hours is not disproven by a 5-minute watch; zero observed variance over a window narrower than the period is a false-null tell, not a clean result. Bind the spike's pass-condition to a window provably longer than the failure mode it's ruling out.

## Close-Out Chunks Cite Specs, Don't Re-Exercise Them

A close-out chunk's job is citation, not re-validation: name the spec, name the code paths, mark the AC verified-shipped-by-citation. Minutes of work.

**Anti-pattern:** riding the close-out on a sibling integration run and asserting the binding path fired. Looks rigorous; fragile by construction — hardware and topology drift make the path unreachable on the validation host even when the contract is correct (RAM cap doesn't bind on a CPU-bound host; `delta == 0` between baseline-at-`--jobs auto` and resume-at-`--jobs 1` fails on shard-count drift, not on a resume bug; a lock-reaper exercise needs an orphan-PID class that's its own engineering problem to stage).

**Rule:** if the contract was the Staff Engineer-reviewed (or equivalent) and shipped with tests at the time it landed, cite that. A separate validation run is justified only when the host *and* topology can reproduce the binding path cleanly. Don't bundle "validation that hardening still works" with "documentation that hardening shipped."

**Plan-time canary:** if a reviewer's earliest finding is "integration coverage by happenstance" or "close-outs ride on Chunk N's run as their only test," reshape, don't slice-size-patch. Field-cite (ws2-narrow-activation): the Staff Engineer flagged the shape; the EM patched. At execution: Target 2 hit hardware-ceiling drift; Targets 3+4 hit shard-topology drift. PM authorized consolidated spec-citation close-outs, recovering ~46 min.

## Shared-State Pre-Flight Gate

Before a plan changes the semantics of a shared symbol — a state enum, gameplay tag, public field, or exported function signature — include a reverse-reference scan in the plan: list every consumer found via grep, IDE rename-preview, or equivalent tool. Plans that mutate shared contracts without enumerating consumers are incomplete and risk silent breakage across subsystems with no obvious compile-time signal.

**Checklist:** For each shared symbol the plan mutates, add a subsection that names every file/component that reads or depends on it. If the scan is non-trivial, make it an explicit plan step, not an assumption.

**Rename-sweep enumeration must be case-insensitive.** A shared-symbol rename plan that greps case-sensitively for the old name misses occurrences that appear only capitalized (sentence-start prose, headings, title-cased identifiers, ALL-CAPS constants). Run the occurrence-enumeration grep case-insensitively (`grep -i` / `rg -i`) so capitalized-only references are in scope before the rename wave dispatches.

**Simultaneously-renamed symbols need an explicit cross-reference reconcile pass.** When a plan renames two or more symbols in the same wave and the symbols reference *each other*, the cross-references fall between the per-symbol chunks — chunk A renames symbol-1 but leaves symbol-1's mention of symbol-2 on the old spelling, and chunk B does the mirror. Add an explicit reconcile pass after the per-symbol chunks that greps each new name's occurrences for any sibling-symbol's OLD name. Per-symbol parallelism does not cover the seam between the symbols.

## Data Before Dispatch

Before writing a plan or dispatching agents on a debugging or fix task, identify and run the smallest diagnostic that exposes ground truth — a test runner, curl probe, `git show`, or single inspect call. Target: < 60 seconds. This is the cheapest step in any plan and prevents hours of hypothesis-driven agent rework.

**Framing rule:** Hypothesis-driven dispatch without diagnostic data is a stuck-detection trigger. If you find yourself writing a plan section that says "the cause is probably X," stop and run the diagnostic first. (example-repo T1.2, paired across writing-plans + systematic-debugging)

**Diagnose-then-design sequence.** Don't author architectural plans for unknown root causes. When the symptom is observed but the mechanism is unverified, the first plan is a diagnostic plan — not a mitigation/refactor plan. Architectural plans built on guessed-at root causes optimize the wrong surface and bury the actual fault under structural churn; the structural work then has to be unwound when the real mechanism surfaces. Sequence is diagnostic spike → mechanism identified → design plan. Skipping the diagnostic step because "we already know it's the X layer" is exactly the heuristic that produces wrong-locus mitigations.

## Substrate-Migration Sequencing

When a plan introduces a layout change (directory shape, file naming, schema location, persistence path) that a downstream producer depends on, the layout-creation work MUST be its own explicit task that lands BEFORE the producer task — not assumed to "exist by the time the producer runs." Plan-documented and reviewer-approved layout invariants do not guarantee runtime existence; the executor for the producer task will hit `ENOENT` / `IsADirectoryError` / `FileNotFoundError` at first run and the recovery shape (create directory inline, fall back to old path, etc.) is exactly the silent-pick footgun this rule prevents.

**Procedure at plan-write time:**

1. Walk every layout assumption the plan makes (new directories, new schemas, new persistence paths, new registry entries, renamed/moved files).
2. For each, ask: *does this exist at the moment the producer task runs?* If "yes, because Task K creates it" — Task K must precede the producer task explicitly, declared on the producer's `## Tasks` row via `depends_on` (`plan-tasks.schema.json`, ≥ 1.5.0). It is an array of objects, one per predecessor — a producer with three predecessors carries three entries — and each entry names its gate kind, because a bare chunk-id list would force the EM to re-derive the kind from prose at execute time:

   ```yaml
   - id: C7
     title: Emit the projection into the new layout
     change_kind: code-edit
     surface: coordinator_core/projection/
     depends_on:
       - chunk: C3
         gate_kind: output-consumption-runtime
         note: C3 creates state/projections/ — C7 opens it at first run.
       - chunk: C4
         gate_kind: output-consumption-runtime
         note: C4 lands the schema C7 validates against at runtime.
   ```

   A layout artifact that must EXIST when the producer *executes* is `output-consumption-runtime`, not write-overlap — the two chunks need not write the same file at all. Use `epistemic-premise` only for a predecessor that decides whether this row should exist. Do **not** hand-declare `file-write-overlap`: it is computed from the write-target graph (`skills/execute-plan/SKILL.md` Phase 1.6), and a hand-written copy is a second source of truth free to desync. `output-consumption-content` and `contract-change` are not writable here either — Phase 1.6 requires both to downgrade to concurrent-with-pinned-interface, so pin the interface in the consumer's body instead of declaring an edge. If the predecessor is owned by ANOTHER repo rather than a row in this plan's spine, `depends_on` cannot express it at all — use `external_gate` instead (`plan-tasks.schema.json` ≥ 1.8.0, § Machine-Parseable Task Spine above).
3. If "yes, because the substrate is naturally present" — grep the substrate to confirm. Don't assume; tests in CI run on clean checkouts.
4. If the answer is genuinely "no, the producer creates it" — that producer task's spec MUST include the creation step explicitly. Not a side-effect, not "it'll mkdir as needed" — an explicit step in the task body.

**Non-discriminating reviewer rationale is the warning sign.** When a reviewer's rationale for accepting a layout decision is true of multiple shapes (e.g., "PersistentClient needs a directory" — true of both old and new shapes), the reviewer didn't actually pick the right shape; they ratified a non-decision. Plan reviewers should be asked: *what about your rationale would change if we picked the OPPOSITE layout?* If the answer is "nothing," the rationale is non-discriminating and the layout decision isn't actually grounded in this review. Re-decide explicitly, or flag the decision as deferred.

**Default-RETIRE is lazy when an axiom assigns production capability to a specialist repo.** When an axiom assigns a domain to a specialist repo, it assigns *production capability*, not just receive-side responsibility for existing artifacts. The correct default disposition for types the specialist doesn't yet produce is PORT (specialist authors the missing producers); RETIRE is the override case requiring explicit per-type justification of why coverage isn't lost. Defaulting 39 specialist-only chunk types to RETIRE because the specialist lacked producers was the documented error; PM corrected it hard.

## Cross-Module TU Move — Enumerate the Donor Module's Full Dep Set, Not the Headline Dep

**A translation unit moved across module boundaries carries its code but NOT its old module's link dependencies — audit the donor module's full dependency arrays before dispatch.** When a plan moves a `.cpp`/`.h` (or any TU) from module A to module B — UE `.Build.cs` `PublicDependencyModuleNames`/`PrivateDependencyModuleNames`, a CMake `target_link_libraries`, a Cargo dep table — the destination module does NOT inherit A's link deps. The headline dependency the TU obviously uses is insufficient: transitive *private* deps that A pulled in (and that the moved code relies on implicitly) don't propagate, and the move compiles-then-fails-to-link on a dep the plan never enumerated. At plan-write time, read the donor module's *entire* dependency array (not just the one dep the moved symbol names) and list every dep the destination must add.

## Precedent-Replication Plans Must Name the Novel Delta and Gate Exactly It

**"Replicates a proven precedent" can conceal the one novel seam — identify NOVEL-vs-precedent and gate exactly that delta.** A plan framed as "this is just like the existing X" lulls review into pattern-matching the precedent and waving the whole plan through — but the value (and the risk) is in the *one seam that differs* from the precedent. At plan-write time, split the plan explicitly into the precedent-replicated portion (cite the proven instance) and the NOVEL delta (the seam, contract, or behavior that has no precedent), and concentrate the acceptance gate on the novel delta — the replicated portion rides the precedent's existing coverage. A generalist diff reviewer earns its keep here *after* domain approval: the domain reviewer ratifies the precedent-match, the generalist catches what the precedent framing hid in the novel seam.

## Roadmap and Cross-Repo Plan Hazards

These apply when a plan is part of a multi-stub roadmap or moves work between repos.

**Single-consumer audit-spike work folds into Phase 0 of the implementation plan, not a separate roadmap stub.** When a roadmap-shaped audit/spike has exactly one downstream consumer (the implementation workstream that uses its findings), the audit is not a peer stub — it's the first phase of that consumer. Separate-stub framing introduces handoff overhead, stale-findings risk between stubs, and review duplication for no integration benefit. Roadmap-shape heuristic: count consumers. ≥2 consumers → standalone audit stub justified; 1 consumer → fold into Phase 0 of that consumer's plan.

**Cross-repo MOVE between repos = audit residual at the source.** When a plan moves a stub/component/feature from repo A to repo B, the destination often only needs *part* of the original scope. The residual in repo A is not auto-deleted by the MOVE — audit what stays behind and decide explicitly: keep / delete / migrate. Silent MOVE without source-residual audit leaves orphaned scaffolding (configs, hooks, references, dead helpers) at the origin that survive every subsequent grep as "still in use somewhere," gating future cleanups.

**Verify a roadmap stub's INPUT contract against the SHIPPED producer at pickup, not the stub's OVERVIEW-era assumption — and don't pre-assert a reviewer's ruling before the review runs.** Two compound rules from the same failure shape:

(1) *Stub input contract vs. shipped producer:* A roadmap stub's stated input contract is OVERVIEW-era hypothesis; the disk is truth. At stub pickup, grep+read the SHIPPED producer's schema/output and reconcile the stub's input assumption against it before planning. A stub that says "C3 receives the raw pin type" when the shipped producer actually hands a pre-resolved (and lossy) `CppTypeRef` makes every AC for that stub unsatisfiable as written. Fix-forward means reading the committed producer first; the disk wins over the stub's framing.

(2) *Never pre-assert a reviewer's ruling:* Do not write "<reviewer> confirms X" in a plan body until that reviewer has actually ruled. Leave it pending: "the Staff Engineer ratification pending — see §Q-N." Pre-asserting a review outcome that hasn't happened inverts the review's purpose and precludes the reviewer from ruling independently.

Sister to "existence ≠ fit" and `§ Verifying Handoff Premises` (broken-today claims need HEAD verification).

**"Copy from upstream" rows mis-classify ~25% of the time — read every such file at its landed SHA before executing.** Plan-stub-vs-landed-disk drift is structural on cross-repo plans: "Copy from X verbatim" is the provisional assumption, not the execution contract. Before the executor runs, read each "Copy from X" file at its actual landed SHA and classify freshly (extend / text-adapt / upstream-specific-replace). The 1-in-4 mis-rate means a provisionally-correct plan will ship wrong code for roughly one file in four without this step.

**Cross-plan amendment discipline: body-edit, not wiki audit-trail.** When a PM-ratified decision in plan A supersedes a decision in plan B on the same branch, grep-and-amend plan B's body in one coordinated commit — a wiki audit-trail entry alone leaves downstream executor briefs on the stale doctrine. Enumerate every surface that carries the superseded claim (sub-decision body, risk row, convergence timeout, wave steps, AC rows) and update them in-place; a single missed surface ships an executor brief that contradicts the ratification.

**Cross-plan amendments need a structural pointer, not just a body breadcrumb — `amendments:` frontmatter list as the durable seam.** When plan A amends a live peer plan B (especially during concurrent EM sessions where plan B is mid-execution), body-prose markers ("**Amended YYYY-MM-DD by <slug>:** …") have real concurrency risk (a peer rebase or mid-chunk recompose can clobber the prose region) AND no programmatic consumer (nothing greps for them). Add an `amendments:` frontmatter list to the parent plan (and its DR if applicable) with one entry per amendment — durable structural pointer, future tooling can enumerate, single well-defined frontmatter region less likely to collide with in-flight body edits. Keep a body-prose marker as a redundant reader-facing breadcrumb. Same shape on DRs: same-day clarification that does NOT change the decision → edit-in-place + `amendments:` frontmatter list (shape A); ≥1-day-later amendment → follow-up DR with `related: [<parent-DR-id>]` (shape B).

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

A reviewer (the Staff Engineer / domain reviewer) will dispatch against the assumption that this scan has happened; surfacing a sibling-plan conflict at executor time is plan-substrate failure, not executor failure.

### (d) Tool resolution in teammate prompts

When a plan step dispatches a teammate agent that needs MCP tools, use graduated ToolSearch in the teammate's prompt — never hardcode a single tool name prefix. MCP tool names vary across teammate spawn contexts (e.g., the current NotebookLM server's `mcp__notebooklm-mcp__*`, vs the bare `mcp__notebooklm__*` form, vs the retired vendored `mcp__plugin_notebooklm_notebooklm__*` prefix — three different prefixes for the same tool suffixes across sessions/installs).

**Graduated resolution order:** `select:exact` → `+prefix` keyword fallback → graceful failure message. Any teammate prompt that names an MCP tool should follow this pattern; hardcoding a single prefix is a silent failure waiting for the next spawn context change.

### (e) No fallback escape hatches in stubs

Python-fallback / "if MCP missing, use Python" / "if X unavailable, fall back to Y" clauses are a structural fault — under firefight pressure executors pick the fallback every time, bypassing the canonical surface precisely when it most needs exercising. Fix is structural, not prose: remove the clause; convert the "missing verb" branch into an explicit Step 0 prerequisite that fails loudly.

**Doc-doctrine corollary:** Don't advertise the escape hatch in the README or stub preamble. When a primary path and a fallback both exist, the entry-point promotes one path only; the fallback file lives on disk but isn't surfaced.

**One spec sentence carrying both a hard requirement and a soft fallback reads two ways — split it at plan-write.** A sentence like "use the MCP verb (or fall back to Python if unavailable)" gives the executor a hard mandate and a soft escape in the same breath; executor and reviewer resolve the ambiguity in opposite directions (executor takes the fallback under pressure, reviewer reads the mandate). Resolve at authoring: state the hard requirement as a flat imperative and demote the fallback to an explicit Step 0 prerequisite that fails loudly (per (e) above) — never weld both into one sentence.

### (f) Concurrency-safe file design

When a plan proposes shared-file appends across N machines or sessions, prefer **per-machine paths** over "atomic per-block append" merge logic — the latter is a euphemism for "PM resolves merges at daily wrap." Per-machine files sidestep the conflict class entirely.

### (g) File-overlap analysis before parallel dispatch

Plans that claim "fully independent files" still need EM-side file-overlap analysis before parallel executor dispatch. Trust-but-verify: a 30-second cross-check against the plan's file lists prevents two executors from racing the same file under independence assumptions.

**Index files are hidden shared substrate.** `docs/README.md`, `docs/wiki/DIRECTORY_GUIDE.md`, and any central index get rewritten by every chunk that touches them. These files never appear in per-chunk file lists yet every chunk that adds a new wiki page, doc, or plan entry implicitly writes to them. In mise/parallel-dispatch file-overlap analysis, the anchor chunk must own all index rows and forward-references. If no anchor is designated, index files must be committed by the EM after all chunks land — never by individual parallel executors.

**Concurrency unit is the file, not the chunk — and file-overlap is necessary but not sufficient for parallel-safety.** Two facts compound here. First, the unit of parallel safety is the *file*: a wave is parallel-safe only when no two concurrent executors write the same path, so the overlap analysis is per-file, not per-narrative-chunk. Second, file-disjointness alone does not license parallelism — cross-wave *contract coupling* (a signature, schema field, or wire shape one chunk produces and another consumes) must be enumerated separately and pinned before declaring parallel-safe. A plan that proves "no file overlap" but skips the signature-dependency pass races two executors against an unpinned interface. Enumerate both axes: (a) file-overlap graph, (b) cross-wave signature/schema/contract dependencies.

**Cross-wave test-substrate drift — earlier-wave tests assert intermediate shapes later waves change.** When a multi-wave plan lands tests in an early wave, those tests can assert on a substrate shape (schema, file layout, envelope field) that a *later* wave deliberately mutates — the early tests then go red not because of a regression but because they encoded a transient intermediate state as a permanent contract. At plan-write time, walk every test an early wave ships and ask: does any later wave change the shape this test asserts on? If yes, either defer the test to after the mutating wave, or write it against the final shape from the start.

### (h) Plan-time dispatch decisions go stale

Dispatch-shape decisions written into a plan (Haiku/Sonnet/Opus, parallel/serial, scout vs general-purpose) are valid at plan-write time only. Phase-2 dispatch must re-check that the chosen shape still fits the substrate; staleness window is ~24h.

### (i) Read-current-and-increment for periodic baselines

Increment math is durable; absolute baseline values rot. Stubs touching a periodically-changing baseline (orphan count, lesson count, queue depth) MUST instruct executor to `read-current-then-increment-by-N` rather than asserting absolute target values.

### (j) PM redirect mid-pipeline invalidates completed reviews

PM redirect mid-pipeline (scope/direction change after dispatch is in flight) counts as structural rework — completed reviews are invalidated against the new surface and MUST be re-run before treating the pipeline as resumable. Don't smuggle pre-redirect review approvals across a surface change.

### (k) No-TBD-thresholds (extends substrate-verification confidence checklist)

Any plan that ships with `TBD` / `???` / `<placeholder>` in a threshold position (cutoff value, retry count, timeout) is unsafe to dispatch — the executor will either fabricate the value or fail at runtime. Resolve thresholds at plan-write time or explicitly defer the chunk.

### (l.1) Executor briefs authoring meta-repo subpaths must pin `${CLAUDE_HOME:-$HOME}/.claude` verbatim

**Any executor brief that writes, reads, or references a path inside the meta-repo's `.claude` directory must pin the resolution `${CLAUDE_HOME:-$HOME}/.claude` verbatim in the brief — never hardcode a bare tilde-path.** The `CLAUDE_HOME` override is the multi-machine portability seam: on machines where the meta-repo's `.claude` directory is symlinked or relocated (e.g., for shared installs or custom home dirs), a bare tilde-path expands to the wrong root. An executor brief that hardcodes a bare tilde-path bakes the primary machine's path into the executor's commands, fails silently on all other machines, and cannot be caught by the path-verification row above (that row checks repo-relative paths, not meta-repo-relative tilde paths). Mechanism: `${CLAUDE_HOME:-$HOME}/.claude` expands to `CLAUDE_HOME` when set, falling back to `$HOME/.claude`.

### (l) Plan frontmatter is EM-only territory

Plan frontmatter (`status:`, `landed_in:`, `reviewed_by:`) is EM-only territory. Executor dispatch briefs MUST include verbatim "DO NOT modify plan frontmatter — that is the EM's bookkeeping surface." Even with this, audit `git diff` on plan files in the post-dispatch verification step.

### (m) Seam Contract for cross-stub symbols

In a multi-stub plan, every cross-stub symbol dependency — a function in Stub-1 that calls a symbol Stub-2 is supposed to produce — is a *seam*. The producer stub MUST ship its symbol in the same wave as the consumer that references it. A `getattr(module, "X", None)` or `try/except AttributeError` graceful-degrade clause against a planned primitive is a permanent fallback, not a temporary bridge: once the consumer ships and the producer hasn't, the degrade clause silently becomes load-bearing infrastructure and the call path permanently no-ops. If the producer is genuinely not in the same wave, the consumer stub MUST include a task that ships the symbol — not a degrade clause. Distinct from (e): (e) governs runtime fallbacks; (m) governs plan-time forward-references.

### (n) Plan-AC "commit required" must carve out the executor commit prohibition explicitly

When a plan's AC genuinely requires a commit to exist (e.g. `cited:<sha>` acceptance, a "land the regression net" task), it collides with the standing executor "DO NOT create commits" scope constraint (per (a)) and the EM-serial-commit discipline. The plan wins — but the dispatch brief MUST carve out the exception explicitly: name *which* task is permitted to commit, *which* pathspec, and that all other files stay out of that commit. A bare "commit required" AC with no carve-out leaves the executor choosing between two contradictory instructions, and it picks wrong under wrap-up pressure. Distinct from (l) (frontmatter immutability) — (n) governs the commit *action*, not the bookkeeping surface.

### (o) Verbatim-parity audit — enumerate ALL branches, or weaken the claim

When a plan declares "VERBATIM parity" with a source mechanism, it MUST copy ALL branches and side-effects of that mechanism — including `--check-only` paths, error branches, fallback clauses, and conditional sub-steps. Partial duplication that lies about being verbatim is worse than honest divergence: it causes the plan's executor to ship an incomplete implementation that silently diverges precisely in the less-common paths.

**Rule:** before writing "verbatim" or "reuses the exact mechanism from X", enumerate every branch in X (if/else trees, conditional flags, mode switches). Mirror each or explicitly name the deviation and weaken the claim: "reuses the headline invocation, omitting the `--check-only` branch." the Staff Engineer's review surface is the backstop — a "VERBATIM" assertion in a plan is a known attention trigger for the reviewer.

## Anti-Literal-Tripwire Chunks Must Grep-and-Mark Scoped Docstrings In-Chunk

**A chunk that adds an anti-literal tripwire (a hook or validator that fires on a literal string appearing in a file) must grep every in-scope path for any docstring, comment, or test fixture that uses the literal as a teaching example — and mark each occurrence with a scoped exemption annotation in the SAME chunk, not at validation time.** Anti-literal tripwires fire on docstrings that say "do not write X" or tests that assert the string X appears for negative coverage; by the time the executor reaches the validation step, those false-positive fire sites are already present on disk and the tripwire blocks the merge. Finding and annotating them is the chunk author's obligation, not a follow-up task. At plan-write time, add an explicit sub-step: `grep -rn "<literal>" <scoped-paths> — mark each non-production hit with the tripwire's exemption comment`.

## Self-Modifying Infrastructure

Plans that modify hooks, validators, or other infra that runs against the plan's own artifacts must include a smoke-test step with synthetic input that exercises the modified code path BEFORE the modified hook fires on real session traffic. The plan body MUST cite the synthetic-input file path.

## Lessons Learned

**Default to subagent dispatch over a new RPC verb when *adding* internal operations.** When a plan proposes a new tool/verb/handler/CLI-job, ask first: can a subagent compose this from existing primitives via `execute_python_code` + `inspect` + extant MCP verbs? If yes, the plan should propose the dispatch path, not the new verb. The new verb earns its place only on (a) C++-only capability, (b) transactional state coupling that primitive composition cannot preserve, or (c) cross-call editor-state invisible in tool signatures. **Never default to dispatch over an existing verb without explicit retire-justification** — prior surface is the proven path.

Tag: `[universal]` — applies to any project_type using the coordinator pipeline.

## Doctrinal Contradiction — Surface as Open Question, Don't Pre-Resolve

When plan-body research surfaces a contradiction between two pieces of existing doctrine — the plan cites source A, prior-art-checker surfaces source B that conflicts — do **not** pre-resolve the contradiction inline. Surface it as an explicit §-numbered open question addressed to the reviewer: *"§Q-N: Source A says X; Source B says Y. Which doctrine prevails here?"* The reviewer reads both citations in context and rules; the plan author's job is to expose the tension, not dissolve it before anyone else can see it.

**Pre-resolving looks like:** asserting one doctrine wins without naming the other, or burying the conflict in a footnote the reviewer may skip. Either leaves the reviewer ratifying a choice they didn't see.

## Architecture-Survey Chunk-K Guard — Doc-Heavy Repos

The architecture-survey's chunk-K guard that detects "uncatalogued architecture" by counting recently-changed files overshoots on doc-heavy repos: `tasks/`, `docs/`, and `archive/` churn (lesson captures, plan edits, handoff updates) is not uncatalogued architecture. Before triggering the guard's escalation path, cut the emergent-drift candidate list against catalogued SOURCE directories only — exclude `tasks/`, `docs/`, `archive/`, and similar doc-tree paths. A guard that fires on lesson-capture churn produces false-positive escalations that crowd out real structural drift.

## Architecture-Audit Rotation — Formula Bias and Feature-Shaped Targets

**Rotation formula over-weights freshly-audited systems.** The open-P1 signal in the rotation formula inflates exactly the systems most recently reviewed — a just-audited system with open P1 findings scores high enough to re-target immediately, starving unreviewed systems of audit cycles. Decay the open-P1 weight for systems audited within N days (suggested: linear decay to 0 over 14 days) so the formula drives breadth rather than anchoring on the freshest finding cluster.

**Rotation targets can be feature-shaped, not just atlas-systems.** "Audit system X" is the natural unit, but a cross-cutting feature (authentication flow, error-handling sweep, multi-tenant isolation) that spans several atlas systems is equally valid as a rotation target. When a fresh atlas is available, the reviewer pre-reads it as pre-digestion before the audit session — this collapses the "what IS this system?" ramp-up and concentrates audit time on the architectural questions.

## Defer B.0 Doubt-Check Recommendations on a Peer-Doctrine Axis

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

<!-- Review: code-reviewer — this section restated the authorization convention, hashing recipe,
     and write-bar nearly verbatim from the doctrine wiki (~70 lines), the exact drift risk
     `plan-execute-session-split.md`'s own § Pinned Conventions warns against for consumer
     surfaces. Trimmed to a cite; the two-option decision list is kept because it's pedagogically
     useful in-context. -->

**Default: a fresh/parallel session executes the plan, not this one.** After the plan is reviewed
(or review is explicitly skipped), the EM writes an execution handoff via `/handoff` and stops —
writing (or a successor picking up) the baton is itself the authorization, so no separate PM
"approve execution" exchange gates it. A fresh session picks it up and runs `/execute-plan`, which
mints the authorization-of-record from its own invocation. See
`coordinator/docs/wiki/plan-execute-session-split.md` for
the full rule, the authorization-stamp fields, the canonical hashing recipe (content-binding via
`execution_authorized_sha`), the write-bar, and the two sanctioned exceptions (`/autonomous`,
token-economics carve-out) — this file does not re-derive that mechanism detail.

**"Plan reviewed and saved to `docs/plans/<filename>.md`. Execution options:**

**1. Parallel Session (default)** - `/handoff` for a fresh session to run `/execute-plan`, which
mints `execution_authorized_*` on the plan from its own invocation — batch execution with
checkpoints, full context budget

**2. Executor-Driven (this session, carve-out)** - I dispatch Executor agents per task following
`docs/wiki/delegate-execution.md`, code review via `/review-code` between tasks, fast iteration — the
token-economics carve-out, permitted ONLY when ALL of the following countable bounds hold: (a) NO
auto-compaction has occurred in this session yet, AND (b) the plan's task-spine is ≤ 3 tasks
(single-phase plans qualify), AND (c) the EM logs the carve-out to the flight recorder with the
measured plan-size + compaction-count. "Feels fine" / unmeasured judgment is explicitly disallowed —
if any of (a)-(c) fails, default to Parallel Session (handoff). This carve-out is ENFORCED (not just
documented) at `/execute-plan`'s session-freshness gate — see `skills/execute-plan/SKILL.md` Phase 1
step 3. See `coordinator/docs/wiki/plan-execute-session-split.md` for the full rule.

**Which approach?"**

**If Parallel Session chosen (default):**
- Write an execution handoff via `/handoff`; stop
- New session picks it up via `/pickup` and uses `/execute-plan`, which mints the plan frontmatter
  `execution_authorized_by`/`execution_authorized_at` from that invocation

**If Executor-Driven chosen (carve-out):**
- Follow `docs/wiki/delegate-execution.md` to dispatch Executor agents
- Stay in this session
- Fresh Executor agent per task + code review via `/review-code`

## Porting Patterns Carries Source Tokens

When a plan ports logic from a reference implementation (another repo, upstream project, earlier version), the executor inherits env-specific tokens: command names, flag names, path shapes, import aliases, and routing-table entries that were valid in the SOURCE environment but may be wrong or absent in the TARGET. Before dispatching: enumerate all env-specific tokens in the ported block and verify each against the target repo's live state (file tree, routing table, `pyproject.toml`, `package.json`, etc.). A porting plan that doesn't name this verification step is incomplete.

## Re-Export Shim Blast Radius Before Deleting a Vendored Constant

Deleting a constant (or any symbol) from a module requires grepping not just direct importers but ALSO any re-export shim sites — lines with `# noqa: F401` or `__all__` entries that back-compat-re-export the symbol from a transitional shim module. These lines do not show up as "uses" in a naive grep for the symbol name; they show up only when you grep the shim file's body for the constant name. Miss a shim, and consuming code that imports via the shim breaks silently at runtime.

**A re-export shim preserves IMPORTS but not `mock.patch` targets when a symbol's consumer moves.** A module-extraction refactor that leaves a back-compat re-export shim keeps `from old.mod import sym` working — but a test that does `mock.patch("old.mod.sym")` (or `patch.object(alias, "sym")`, or a `mod.sym = …` reset) still patches the *old* binding, while the consumer that moved now reads the symbol from its *new* home. The patch silently no-ops: the test goes green against an un-patched code path. Before any module-extraction / symbol-move refactor, enumerate every `patch("…")`, `patch.object(…, "…")`, and `mod.sym =` reset site for the moved symbol — the import grep does not surface them, and the failure is silent-green. Chain-end (combined-surface) review is the net.

## AC gate degraded to static-analysis: document which direction each half covers

**When a runtime verification gate falls back to static-analysis grep, document the asymmetry explicitly — which direction does the runtime dump cover vs. the grep? Don't mark the AC fully passed if only one half is verified.**

A fallback to static analysis is often correct given substrate constraints (commandlet mode skips certain initializers, hardware ceiling doesn't bind in CI), but the asymmetry must be named. The successor stub's scope becomes clear from the gap: what would prove the other half?

## Asymmetric-defaults framing produces sharper decision documents

**Declare per-layer defaults with explicit override conditions ("KEEP X unless evidence demonstrates Y") rather than balanced surveys — specialists then look for evidence to override defaults rather than justify positions.**
**Why:** A LightRAG synthesis reached "PORT-PATTERNS, single track" cleanly because a DISQUALIFYING verdict tripped a pre-declared override condition. A balanced frame would have produced a "both have merit" table.
**How to apply:** before dispatching research or architecture specialists, write the scope document as `KEEP <default> UNLESS <override condition>`. Asymmetry forces evidence to do work; symmetry invites hedge-anchored synthesis.

## Post-review plan edits need a body sweep, not just a patch

**When a reviewer finding renames a section header, resequences chunks, or restructures a scope, grep the rest of the plan for the old framing after applying the finding — don't trust the integrator to surface all residual instances.**
**Why:** A the Staff Engineer sequencing finding was applied to the Sequencing block, but the plan body still said "phase 1 / phase 2" — the enricher inherited the phase split from body text and surfaced it as an open question, requiring the EM to fold a step back in mid-stub.
**How to apply:** after applying any structural reviewer finding (sequencing, scoping, decomposition, rename), grep the plan body for the old terminology and sweep — the integrator's brief is "apply this finding," not "audit the plan for residual implications."

## Durability Assertions Must Cover ALL Writers of a File

A durability assertion like "this file is never overwritten by X" is only meaningful if X is the ONLY writer. If multiple code paths write the file, single-source coverage is a silently-false durability claim — the un-asserted writer can overwrite at any time. Before writing a durability assertion, grep ALL write-direction patterns (open-for-write, rename-to, shutil.move, os.replace) for the target path. If multiple writers exist, the assertion must cover all of them or be scoped narrower.

## Vocabulary Substitution Must Be Cross-Checked Against Authoritative Glossary

A plan brief that instructs mass-rename of vocabulary tokens (e.g. "rename `foo` → `bar` everywhere") must cross-check the NEW tokens against `CONTEXT.md` or the authoritative glossary BEFORE dispatch. A vocabulary substitution that introduces a non-canonical synonym — or conflicts with an existing term — ships the wrong vocabulary into every file it touches. The check takes one grep and prevents a second sweep to undo the damage.

## Vacuous-True Acceptance Criteria Is Not a Pass

An acceptance criterion that turns out vacuously true at close (the condition is always satisfied regardless of the code's behavior — e.g. "the function returns a non-None value" when the type annotation already guarantees that) is not a pass — it's a stub-quality finding. When a close reveals an AC is vacuous, re-anchor it to the moved seam (what is the real behavioral contract?), replace the vacuous criterion with one that would actually fail if the implementation were wrong, or surface it explicitly as a stub-quality gap for the plan author to resolve. Marking it PASS and moving on hides incomplete specification.

**AC that only tests the field-present case gives false consumer-proof — the negative-spec must cover absent-as-no-distortion.** An acceptance criterion that exercises only the populated/literal-field-set path ("consumer reads field X and renders it") proves nothing about the case the consumer hits more often: the field *absent*. A consumer can pass the field-present AC and still distort, crash, or mis-default when the field is missing. For any AC gating consumer behavior on an optional field, the plan's negative-spec block MUST add an explicit absent-case criterion (field missing ⇒ consumer produces the no-distortion default), not just the present-case one. This is the negative-spec twin of the vacuous-true finding above.

## Threshold-Table Reachability — Test the Floor Before Shipping

A tier/threshold table that classifies by an "any-criterion-matches" rule with a `>= 0` floor on any criterion silently collapses tier reachability: a `>= 0` floor is satisfied by every input, so any tier resting on it becomes unreachable or swallows the tier below it. When a plan ships a threshold table (severity tiers, confidence bands, score buckets), every non-floor tier's criteria MUST be strictly `>` the floor on each criterion separately — and the plan must include a floor-reachability test: construct the boundary input for each tier and assert it lands in the intended tier, not a neighbor. Don't ship a threshold table whose tiers were never exercised at their boundaries. (This is the same "detect-then-silently-pick is a footgun" failure shape as an unreachable tier — see `coordinator/snippets/deletion-list-hygiene.md` for a related instance.)

## Preference-Order Over Co-Equal Framing — Name the Asymmetry

Doctrine (or a plan's resolution rule) that frames two sources as "co-equal rules" often masks an asymmetric *preference*. When one source is primary and the other a fallback — registry-primary / sibling-fallback, flag-then-env-then-marker-discovery, lockfile-then-floor — say so as an explicit ordered preference. Co-equal framing leaves the consumer to detect-then-silently-pick, and a silently-wrong pick (CPU vs GPU substrate, stale vs fresh registry) surfaces as a downstream mystery rather than a loud resolution error. The plan must state the order and the tiebreak, not present the sources as interchangeable. (This is the same "detect-then-silently-pick is a footgun" failure shape applied to doctrine sourcing rather than runtime resolution.)

## Closure-Gate Circularity — Gate-Condition Must Not Name Its Own Closure-Action

Before shipping any "blocked on X" / "gated on Y" / "closes when Z" language, check the gate-condition against the closure-action for circularity. A gate whose condition names the very work it gates on is tautological — it can never fire (the condition is the action) or it fires vacuously (the action trivially satisfies its own condition). The check: write the gate-condition and the closure-action side by side; if the action *is* the condition (or trivially produces it), the gate is decorative. Re-anchor the condition to an *independent* observable (a PR URL, a flag flip, a downstream test going green) that is not produced by the gated work itself. (A circular gate is appetite-hedging disguised as a dependency.)

## Retirement Premise-Pass — Identify the Real Consumer

**A module's reason-to-exist may be a third party's need — verify the actual consumer before a "field Y now retires module X" deletion.** "Retire X because Y replaces it" plans conflate X's apparent purpose with its actual consumer. The retirement premise-pass must identify X's REAL consumer (grep what actually depends on its runtime behavior), not assume it serves the consolidation's own call sites. Empirically: a WMI-safe `is_windows` field was meant to retire a `platform_shim.py` module, but the shim actually pre-warmed a cached platform check for a *third-party* library's own import-time system call — not the host's own checks. A field covering the host's checks does nothing for the third-party library's internal call; deleting the shim would re-expose a live hang. Bonus: the shim's own cache-warming entry point had zero production callers — the mitigation wasn't even wired.

## Plan-Doc Drift — Re-walk Enumerations After Inter-Plan Decision Deltas

**Plan-doc framing drifts from shipped execution reality; downstream substrate audits catch what upstream reviews miss.** A plan document's stated move-set, deletion list, or ID enumeration can drift from what the executor actually ships — especially when intermediate decisions (polarity reclassifications, follow-up corrections) happen between plan-write and execution.

**Rule:** when polarity, scope, or ID-set decisions land after plan-write but before execution, re-walk every count and enumeration in the plan against the decision delta. The grep tripwire: a plan that mentions a count more than 2× without an audit-trail note explaining the count's evolution is at risk. Pair plan frontmatter `verification_evidence` blocks with "as-of-shipped" snapshots citing the actual shipped commit, not the plan's pre-decision framing.

2026-05-14 example: `§AC-4.2` listed 9 producers as the move-set; R2 polarity audit had reclassified 4 (kept in host) but missed `engine_cvars.py`; the PR-W1c executor independently converged on the correct 6+2 reality. Addon-EM substrate audit caught the drift via correction memo. Without the cross-repo audit, a future re-read of the plan would have asserted the wrong gate shape.

## Gate on the Discriminating Signal, Not the Coarse Aggregate

When a plan gates downstream behavior on a status, color, or rollup that aggregates multiple underlying conditions, gate on the *discriminating* sub-signal instead — the coarse aggregate fires on cases that need opposite handling. **Worked example:** a fresh-state offer was gated on `AMBER`, but `AMBER` fires both on never-indexed (INFO — the offer is correct) *and* on half-indexed-WARN (a real problem the offer would paper over). The fix gates the offer on the never-indexed INFO branch specifically, not the AMBER color. At plan-write time, for any gate keyed on an aggregate: enumerate every underlying condition the aggregate rolls up, and confirm they all want the same downstream action. If they diverge, gate on the discriminating branch.

## Invokable Skill/Command Names Can Collide With Evolving Platform Vocabulary

Empirically, a `coordinator:fan-out` skill collided within days of shipping when "fan out" became native Claude Code dispatch vocabulary, forcing a skill→methodology demotion. A command verb that is also a platform primitive is a latent collision.

## pre-plan substrate check must include today-dated plans and recent git log

Substrate check before invoking `coordinator:plan` must include `git log --since=today` AND `ls docs/plans/<today's-date>*`. Without this check, two concurrent sessions can independently plan the same work. Apply: this check must fire before Branch B scouts, not after.

**`source_memo:` cross-check — for a plan that actions a cross-repo memo.** Filename + `git log` collision detection misses the case where two sessions route plans from the *same memo* under different slugs — two sessions can realize the same accepted memo because nothing cross-checked `source_memo` at plan-write time. When the plan carries (or will carry) a `source_memo:` frontmatter pointer, additionally grep every plan for a sibling citing the same memo basename — `grep -l "source_memo:.*<memo-basename>" docs/plans/*.md` plus a body-mention fallback — and surface any hit to the PM before drafting. This fires in the same Branch B.0 pre-flight as the filename/`git log` checks, before scout/reviewer dispatch. **Residual:** catches plan-routed collisions only; commit-only / `inline` realizations leave no plan carrying `source_memo:` and are instead guarded by the memo claim-lock at pickup time plus the archived `realized_by` claim-of-record.

**Key the collision grep on the shared `deliverable_id` / predecessor-spinoff path, not `source_memo` alone.** One deliverable can be entered via N batons — a cross-repo memo, a spinoff handoff, a plain predecessor handoff — and `source_memo` is only one of them. A Branch B.0 grep keyed solely on `source_memo:.*<memo-basename>` misses the case where the peer session picked up the *spinoff* (a different `source_memo`, or none) for the same deliverable. Extend the pre-flight to ALSO grep every plan for the shared `deliverable_id` and the shared `predecessor_handoff` / spinoff path — not just the memo basename. Root: the deliverable identity is the invariant across batons; the memo is not. Empirical case: two sessions realized the same `dlv-*` deliverable — one via the spinoff handoff directly, one via a re-sent memo — and the memo-only grep let the collision slip to prior-art-check time, after a full plan + two sidecars were already authored.

## regression-net-before-refactor must plan test-env injection mechanism

A regression-net-before-refactor plan must declare the test-env injection mechanism alongside the test, not leave it for mid-execution discovery. For hardcoded→discovered refactors, the injection mechanism (e.g., env var, monkeypatch, fixture override) must be specified in the plan before the executor brief is written. A mid-execution BLOCKED on "how do I inject the test value?" is a plan-authoring failure. Apply: for any refactor plan, add a "test-env injection: <mechanism>" line to each chunk that writes tests.

## Defense-in-Depth Framing — Deliberate Overlap, Not Necessary-and-Sufficient

Defense-in-depth contracts are "deliberate overlap" — NOT "necessary AND sufficient." The framing "necessary AND sufficient" implies orthogonality that layered defenses rarely have and invites future layer-removal ("we already cover that"). The correct framing is "compose with deliberate overlap." Apply: when documenting layered defenses (multiple validators, schema + runtime check + test), describe them as "deliberately overlapping" rather than "necessary AND sufficient."

## Substrate-drift mid-execution = plan amendment via Branch D, NOT executor-scope expansion

When mid-execution drift blocks an executor (substrate on disk differs from plan assumptions), the correct path is Branch D plan amendment — not telling the executor to figure it out. Scope-expanding the executor bypasses doctrinal lenses (the Staff Engineer review, prior-art-checker, coverage-checker). Apply: when an executor surfaces a `BLOCKED: substrate-drift` issue, stop the executor, invoke Branch D of `coordinator:plan` with the drift description, and re-plan before re-dispatching.

## Sizing from inside an investigation under-counts execution scope 2-3x

Scope numbers derived from inside an investigation or spike systematically under-count execution cost by 2-3×. Investigation-resolved scope reflects the planner's mental model, not the executor's cost. Apply 2× multiplier to any scope estimate that came from a spike, OR dispatch a scope-scout before writing the plan. Apply: never take a spike-derived "it's just N files" estimate at face value; budget for 2× to 3× actual.

## AC criteria drift from what executors write — reconcile at execute-time

Plan-pre-named AC criteria drift from what executors actually write. Reconcile AC criteria at execute-time Phase 1 (before dispatching) by grepping the actual test file or deliverable path for the expected content. Apply: always confirm AC criteria are satisfied on disk before treating them as done.

**Rule (Branch C skill-scaffold checklist item):** when naming a new invokable skill/command, prefer a collision-free verb and re-check against current platform primitives at the time of authoring. Platform vocabulary evolves post-ship — a name collision that didn't exist at creation may appear at any future Claude Code release. The only resilient defense is to avoid platform-verb-shaped names at the outset.

## Load-bearing numeric ceilings must declare a growth model or fixed-ceiling justification

**Rule (Branch C checklist item):** when a plan introduces a numeric ceiling — RSS budget, capacity cap, timeout, retry count, allocation limit — it must declare EITHER (a) the growth model (inputs + function shape + recalibration trigger) OR (b) the architectural reason a fixed ceiling is correct here (physical hardware limit, protocol constant, user-facing UX bound). A bare integer constant in a ceiling position with no declared rationale is a P1 by default.

The Staff Engineer's review lens checks for this at plan-review time. (Empirically, two independent ceilings surfaced the same defect class within weeks of each other — the recurrence is what promoted this from a nitpick to a standing rule.)

## VERBATIM / Spelling-Lock Blocks Must Carve Out Standard Capitalization

When an executor brief locks the spelling of a token or phrase ("write `my-service-name` exactly, do not paraphrase"), the lock over-applies if it forbids the executor from capitalizing the token at sentence-start or in a heading. A spelling-lock is about *token identity*, not *casing*: the brief MUST carve out standard English capitalization (sentence-initial, title-case headings) so the executor isn't forced to write a lowercase token mid-prose where grammar demands a capital. State the lock as "preserve this exact token, applying normal capitalization at sentence boundaries" rather than a flat verbatim mandate.

## Cluster decomposition — group by space-adjacency, not plan-capacity

When breaking a multi-entry corpus (lessons batch, audit findings, retrofit list) into plans, the grouping axis is **space-adjacency** — shared problem-space, solution-space, or codebase region. NOT plan-capacity (how many entries fit). NOT chronology. NOT severity bucket.

Heuristic: the EM holds one mental model per plan. Two entries belong in the same plan when reasoning about one requires loading the same context as reasoning about the other. Empirically calibrated at the 2026-05-27 Pass-2 C-Bucket fresh-run: 34 code-surface entries decomposed cleanly into 7 clusters (+ 2 held condition-gated). One mega-plan failed (EM context overflow); one-plan-per-entry failed (no reuse of substrate reads).

Condition-gated holdouts are a legitimate fourth outcome, distinct from backlog-hedging: an entry is held when its dispatch is gated on an observable not yet present (an in-flight refactor, a pending review, a missing reproduction). Gate criteria must be calendarable.

## Synthesizer / integrator discipline — read-in-full before append

Plan synthesizers and review integrators read the target wiki in full before writing. The 2026-05-27 Pass-2 S1/S4 sprints both surfaced a recurring failure mode: 6/N (S1) and 8/N (S4) of assigned entries were ALREADY-COVERED by a morning sprint. Appending without reading produces guide drift — each cycle subtly rewords existing prose and the wiki bloats without new information.

**Rule.** Before any ADD_SECTION / UPDATE_SECTION op, the synthesizer Reads the target wiki in full and emits a per-nugget disposition: NEW / ALREADY-COVERED / SUPERSEDES-EXISTING. Phase 2 outputs include disposition manifests for exactly this reason — coverage contract is enforced at the seam, not after the fact.

## Pre-Dispatch Substrate Verification — Extended Rules

These rules extend § Codebase Research (before file mapping) and § Negative-Search Before Drafting with patterns that recur across plan failures but were not covered by the earlier rules.

### Writers-of-the-file enumeration (config mutation plans)

**Rule:** when authoring a plan that mutates a config file, grep every writer of that file (`grep -rln '<filename>' bin/ lib/ hooks/`) and read each one. Cite them in the plan's substrate section. Existence ≠ exclusive ownership.

**Why:** empirically, a plan wrote to the meta-repo's `settings.json` without reading `coordinator/templates/bin/platform-localize.py`, which already performed a wholesale-write to `settings.local.json`'s `extraKnownMarketplaces` key from a directory-scan — a two-writer tension on the same key, flagged at review as critical/major. The plan body's "Substrate verification" bullets named what existed but not what *wrote* to it.

Add a "writers-of-the-file" enumeration step between the path-verification row and the symbol-liveness row in every config-mutation plan.

### Inbound-reference grep for path-migration plans

**Rule:** when authoring a path-migration plan, grep the old path across `docs/`, `README.md`, and the project's wiki tree at plan-write time (Branch B), not at close-out. Inbound consumer docs reference the old path convention and ride below the file-overlap radar.

**Why:** the 2026-06-15 deep-research-workdir plan listed 9 pipeline driver files + 2 wiki + .gitignore + memo in scope. C4 closeout grep discovered 3 downstream consumer docs (`docs/architecture/systems/deep-research.md`, `docs/guides/coordinator-infrastructure.md`, `docs/guides/deep-research-infrastructure.md`) also referencing the old path. Caught and fixed inline as scope expansion, but the right move is to surface it at plan-write time.

Extend Branch B substrate verification to include: `grep -rn '<old-path>' docs/ README.md`.

### Parse-contract masquerade detection

**Rule:** when a plan brief contains a "Read X, locate heading Y, enumerate Z" step, ask "what is X's actual format, and is the parse contract codified?" If the producer's output format is free-form, the consumer's parse step IS a format contract — spec the producer-side schema explicitly OR carry the data inline to eliminate the indirection.

**Why:** empirically, a plan phase expansion specified "Read scout file, locate section_anchor heading, enumerate paths under that section (until next H2 or EOF)." Review caught it as a Markdown-parse contract masquerading as mechanical — path-line format unspecified, H2 boundary unverified. Fix: tighten the scout format to fenced YAML-under-anchor; the consumer parses YAML, not Markdown prose.

A "Read file / locate section / enumerate items" step in a plan is a specification-of-a-parse-contract, not a mechanical one-liner. Confirm the producer format before the plan body asserts the consumer can do it.

### Computed-value consumer sweep (extends shared-symbol reverse-reference scan)

The § Shared-State Pre-Flight Gate above covers *mutations* to a shared symbol's signature. This rule extends it to *mutations in how the value is derived or resolved*.

**Rule:** when a fix changes how a widely-consumed value is COMPUTED — a session id, a hash, a normalized path, a default resolution algorithm — grep every consumer that *namespaces/keys/branches* on that value and confirm the new computation doesn't break their assumption. This is the "runtime contract change → grep every assertion" discipline applied to value-derivation, not just call signatures.

**Why:** empirically, a spike switched a handoff-claim function's session-id resolution from a machine-shared sentinel file to a per-session env var (correct locally). But an existing same-machine concurrent-pickup guard relied on the OLD behavior — it namespaced the atomic-`mkdir` claim path on the session id, and same-machine sessions only collided because they shared the sentinel sid. Per-session sids → distinct claim paths → `mkdir` never collides → the guard silently never fired (split-brain dual pickup). The fix's author saw only the local correctness win, not the downstream consumer that assumed the shared value.

At plan-write time, for any proposed change to a computed value's derivation: enumerate every consumer that branches or keys on that value (not just callers of the API surface) and verify the new distribution doesn't break their assumption.

### Prior-art-checker corpus excludes `skills/` — manual skills/ grep required

**Rule:** `prior-art-checker` scans wikis, lessons, central queue, and optional peer repos — it does NOT scan `skills/**/SKILL.md`. A plan that authors a new predicate, classifier, or rubric must also grep `skills/**/SKILL.md` manually for an existing implementation, OR the named Opus reviewer must. A green-or-near-green pre-flight does NOT guarantee no skill collision.

**Why:** the 2026-06-18 /distill reshape plan invented a brand-new plan-ripeness predicate; prior-art-checker returned WARN on 3 completeness gaps but MISSED that `skills/plan-delivery-audit/SKILL.md` already IS the canonical done-vs-in-flight classifier (keyed on the real `status: implemented`). The Staff Engineer (the Opus reviewer pass) caught it and blocked.

Add a "grep skills/ for existing predicates" row to Branch B when a plan authors any new classifier, rubric, or predicate logic.

### Consumer audits must enumerate skill-altitude consumers, not just code

**Rule:** when auditing whether a doctrine surface "has a downstream consumer," the audit must scan SKILLS, agent prompts, and wiki narrative references — not just scripts that grep the artifact. A skill body that reads a plan section IS a consumer; an Opus persona prompt that references an artifact IS a consumer. Consumer audits that check only code will misclassify load-bearing surfaces as ABSENT and recommend retiring them.

**Why:** a workstream-complete ceremony-calibration audit initially recommended dropping the `## Deviations` table on ABSENT-mechanical-consumer grounds. PM corrected: `/distill`'s skill body reads plan bodies as the consumer ("any undocumented plan deviation means crystallizing something incorrect"). Both consumers were real; the audit caught the mechanical one and missed the skill-altitude one.

Consumer audit dispatches must explicitly request HARD (script-parsed), SOFT (skill body / agent prompt / wiki narrative reference), and ABSENT verdicts as three distinct buckets. Before recommending retirement of any doctrine surface, name the skills whose body reads it and confirm retirement doesn't break their reading contract.

### A `pending` gate/decision-table row is a lagging indicator — read the artifact before re-litigating

**Rule:** when a pm-gate or decision table shows a row marked `pending`, read the SHIPPED ARTIFACT (code header marker, decision record, closed type header) before surfacing it to the PM as an open fork. On a fast multi-session roadmap, table-lag is the common case — the table was never updated after the work shipped. Re-opening a ratified decision because the table still says `pending` is the re-litigate-a-ratified-call anti-pattern.

**Detection pattern:** grep the shipped code/headers for ratification markers (e.g., `Gate N ratification: "<decision>" — the Staff Engineer → PM, <date>`) and the git log for the workstream-complete commit. If either exists, fix the stale table row and proceed without re-opening the decision.

**Corollary — unowned "driver" gaps:** when mappers/consumers defer work to "the X walk/driver" without naming an owning chunk, that unowned gap masquerades as someone else's done work. Before closing a workstream, grep that the deferred surface has an owning cluster. A gap that every chunk deferred to but none owned is a planning failure, not an adjacent chunk's residue.

Sister to "broken-today claims need HEAD verification" and "verified-at-plan-write is decaying.".

### "Verified at plan-write" is a decaying claim within a single long session

**Rule:** when a plan's gate-posture or substrate-blocker matrix asserts a dependency is absent / broken / unlanded ("SB-2: tc-7 not landed, verified at plan-write"), re-verify against HEAD at *review-integration* AND at *execute-plan Phase 1* on any session longer than ~1h or with known concurrent branch activity. A concurrent EM can land the blocker mid-session while the plan is in review — the "verified" timestamp is intra-session-stale, not just pickup-to-now stale.

**Distinct from `§ (h) Plan-time dispatch decisions go stale`** (which governs dispatch-shape staleness at ~24h): this rule is specifically about *substrate-absence/blocker-state* claims going stale within a SINGLE session due to concurrent sibling execution on a shared branch. The staleness window is minutes-to-hours when concurrent sessions are active, not days.

**How to apply:** any plan row that reads "X is currently absent/broken/unlanded" is a time-stamped claim — add a note to re-run the verification step at the two pipeline stages above, especially when the plan's authoring session overlaps known concurrent EM activity. (Empirically caught via `git cat-file`/`ls` against HEAD.)

### Spec-table bucket names are not detection-category names — iterate ALL named buckets

**Rule:** when a plan reads a config/allowlist table keyed by named buckets (a TOML allowlist, a routing map, a category-to-action table), iterate over EVERY named bucket the table actually defines — do not look up entries by an assumed detection-category name. The bucket names in the table need not match the detection-category vocabulary the plan author has in mind; a lookup-by-category misses buckets whose names diverge from the categories.

**Why:** the 2026-06-08 case (from the meta-repo): allowlist TOML bucket names were treated as if they equalled detection category names, so an entry was looked up by category and missed — the correct shape iterates all named buckets and matches each.

### Schema field-meaning change invokes the contract's named ratifiers even when "free" (no shipped consumer)

**Rule:** a schema field-*meaning* change (replacing a field's type, semantics, or structural role) invokes the contract's named ratifiers even when it is "free" — i.e., grep confirms zero readers. "No consumer yet" is an extenuating circumstance, not an exemption from a clause that names roles by authority. The correct path is to run the named ceremony (PM ack + named reviewer affirm), not route around it because the change appears low-risk.

**Distinguish field-addition from field-meaning-change:** field-*addition* is often an unconditional additive op (add a new field, leave the old one); field-*meaning-change* (replacing a stringly-typed field with a typed struct, changing what an existing field encodes) is typically gated. When in doubt, add a new field rather than repurposing an existing one — the additive path is always unconditionally available.

**How to apply:** at plan-write time, when a chunk proposes to change an existing field's meaning, locate the versioning/schema contract and look for a `who-must-ratify-meaning-changes` clause before treating the change as free. You cannot substitute "it's low-risk" for the named approval.

### Default-flip in writer code requires same-commit audit of parallel reader code

**Rule:** when a plan flips a default in *writer* code (a config-write, a schema-emit, a manifest-build, an install-time default), the same commit's pre-flight MUST grep the codebase for the affected key/value and audit every *reader* that asserts or branches on that default. Three reader-locus signs: `default=<old>` in comments, initial-value assignments mirroring the old default, and branch conditions like `if missing: <old-default-behavior>`.

**Why:** a C7 chunk flipped `bMcpNativeTransportEnabled` install-time default from FALSE→TRUE in setup scripts, but the parallel doctor probe kept the pre-flip "default=disabled" comment and `setting_state="unknown"` initialization — producing INFO/unknown verdicts on every fresh default-ON install. Caught at C8 verification, not pre-merge. The C7 author commit named only the writer (setup script) as scope and didn't grep for downstream readers asserting the old default.

**Sister rules:** `Detect-then-silently-pick is a footgun`, `Premise-pass before regenerating torn-down structure` — all three are "the symptom isn't the locus" failures. The writers-of-the-file enumeration rule above covers multi-writer tension on config files; this rule covers the mirror: code that *reads* a default that has been flipped in writer code.

### Peer-port Branch-B substrate scan — grep action names, not directory names

**Rule:** when planning a peer-port from a reference implementation, the Branch B substrate scan's first grep is the ACTION-NAME set across `**/*.{cpp,h,ts,py}` — NOT a directory enumeration. A `find -type d -iname "*<Domain>*"` returns "no module named X → greenfield" even when a flat handler file implementing all target verbs already exists inside an existing module under a different naming convention.

**Why:** `find -type d` answers "is there a module *named* X?" — a peer-port needs to answer "does this *functionality* already exist anywhere?" — a content question, not a structure question. In one case, a `find -type d -iname "*Landscape*"` scan concluded greenfield, missing 3,800+ lines of already-shipped landscape handlers in a flat file inside an unrelated module, plus 8 already-shipped peer methods under a different verb. The plan would have re-implemented ~80% of already-shipped code in parallel.

**How to apply:** for any peer-port or "looks greenfield" first impression, before declaring the target scope, grep the full action-name set (from the reference impl's public interface) across the target tree with `-r`. Only after that search returns empty is "greenfield" a safe claim.

### Version-bump and sentinel-allowlist cascades enumerated at plan-write

**Rule:** a plan that bumps a version constant or adds a sentinel/allowlist entry must enumerate the full cascade of co-dependent surfaces at plan-write time — every file that pins the version, every allowlist that must gain the new sentinel, every check that asserts the old value. A bare "bump the version" or "add the sentinel" chunk that doesn't enumerate the cascade ships a half-applied bump that fails a downstream gate the plan never named. Walk the cascade (`grep` the literal version/sentinel token across the tree) and list every site in the chunk's scope before dispatch.

**Parity invariants extend the cascade — not just `assert X == N` literals.** Sentinel-cascade enumeration must include ALL parity invariants: set-equality tripwires, `len()`-asserts, `_VALID_*`/`_ALLOWED_*`/`_REGISTERED_*` frozenset/list definitions whose membership must stay in lockstep with the bumped symbol, count-trail comments, and shim `__all__` unions — not only literal `assert X == <constant>` patterns. Prior-art-checker catches `assert ... == <value>` patterns but misses set-equality tripwires of different shape. Grep both `assert X == <constant>` (literal value) AND frozenset/list definitions the bumped symbol must stay in lockstep with. Pattern for versioned-enum changes: a `_Verdict` Literal change must pair with a `_VALID_ENVELOPE_VERDICTS` membership update + a count-trail comment update — three surfaces, one change.

**Reconcile in the SAME chunk — do not split the bump and its cascade update across chunks.** A `BLOCKED`-then-EM-inline reconcile is silent scope expansion, and a later chunk that "eats" the reconcile leaves the suite red between commits. Empirically, a command-seam plan carried its 10-site version-pin reconcile in-chunk and stayed green; a sibling skill-seam plan omitted it and hit 12 red tests at execution. When the cascade is too large for one chunk, add an explicit substrate-completion chunk listing the full cascade as in-scope — do not leave cascade sites as executor-time discovery.

### A Dispatch Ledger must decompose EVERY path-shape/variant its ACs name, not just the salient one

**Rule:** when an acceptance criterion enumerates N shapes / variants / forms (a fallback-form AND a bare-form path, two casings, three envelope shapes), the Dispatch Ledger must carry rows covering **all N** — not just the version front-of-mind at ledger-build time. Enumerate the full AC oracle when building the ledger; a fan-out decomposed against only the salient variant under-scopes and silently leaves the other variants' sites unmigrated. This is the ledger-to-AC coverage twin of the "enumerate every X" substrate rules above (call-sites, write-paths, cascade surfaces): here the oracle is the AC's own variant enumeration, and the ledger is the thing that must match it row-for-row.

**Empirical:** an install-shape plan's AC7 required migrating BOTH the fallback-form and bare-form flat paths, but the Dispatch Ledger only decomposed the fallback form; the first fan-out under-scoped and left ~150 bare-form sites untouched. `plan-coverage-checker` cross-references the fix slate against an audit oracle, but the AC's own N-variant enumeration is the oracle the *ledger* must satisfy — check it at ledger-build time, not at executor-stall time.

### Cross-repo contract evolution — enumerate the byte-exact fixture surface upfront

**Rule:** when a plan evolves a cross-repo contract whose conformance is checked by byte-exact fixtures (golden files, recorded payloads, snapshot tests in a sibling repo), the fixture surface expands the execution scope — the contract change is incomplete until every byte-exact fixture is refreshed. Plan-authors enumerate the fixture surface (which fixtures encode the old contract shape, in which repo) at plan-write time; reviewers flag a missing fixture-refresh chunk as a substrate gap, not a stylistic miss. A contract-evolution plan that ships without the fixture-refresh chunk red-fails the sibling's conformance gate at merge.

### Write-site specs enumerate ALL execution paths (function:line per site), not just the recently-touched one

**Rule:** when a plan's fix targets a write site (a logging call, a state mutation, an emit), enumerate EVERY execution path that reaches an equivalent site — `function:line` for each — not just the most-recently-touched or narratively-prominent one. Narrative positioning ("the X handler writes Y") names one site and silently omits shape-equivalent sibling paths (a retry branch, an error path, a second caller that does the same write). Grep the write pattern across the tree and list every match in the plan body; a single-site spec ships a fix that the sibling paths route around. (Sibling of § Durability Assertions Must Cover ALL Writers of a File — that rule covers a single file's writers; this covers a single logical write's execution paths.)

### Closed-enum / discriminated-union KIND bump — run a mechanical schema-migration-auditor as backstop

**Rule:** when a plan bumps a closed-enum or discriminated-union `KIND` (adds a new variant, renames a variant, or removes one), run a mechanical schema-migration-auditor before dispatch — enumerate every `switch`/`match`/`if-chain` on the discriminant, including recursive child-block visitors that descend into nested subtrees, and confirm each handles the new variant or will fail-loud on the unknown case. Hand-enumeration of switch sites is reliably incomplete on large trees: reviewers miss recursive visitor branches and mid-tree secondary switches that are not adjacent to the top-level dispatch. The mechanical backstop (a grep for the discriminant token + pattern-match on switch/case/match arms) is the enumeration gate, not the reviewer's memory. Add a "schema-migration-auditor run" sub-step to any chunk proposing a closed-enum KIND change — before the executor writes any code.

### Migration scripts own their own parse logic — no cross-queue parser reuse

**Rule:** when a plan extends a `migrate-X.py` pattern across multiple sibling surfaces (different queues, schemas, or entry shapes), add a Hard Constraint that each migrator owns its own parse logic and bans copying the reference migrator's parse function. Structure (dry-run/apply, stale-guard, unmigrated-bucket) ports cleanly across queue shapes; the parse function does not — it is specific to the entry shape of the reference queue.

**Why:** the Staff Engineer F4 on the structured-queue-medium-rollout caught this pre-execution. `_extract_promote_fields` from `migrate-improvement-queue-universals.py` is pipe-delimited-shape-specific; debt-backlog is a 6-column markdown table, bug-backlog is YAML-frontmatter + markdown-table, improvement-queue is pipe-delimited prose. Copying the parser across queues silently produces wrong title/body splits — and the unmigrated-bucket guard does NOT catch this because parse *succeeds* against the wrong field positions.

## Runtime-Payload Matcher Plans — Chunk 0 Evidence Gate

**Rule:** when a plan's matcher targets runtime data (a jq path, a regex on tool output, a hook-event field), the field path is hypothesis until empirically captured. Add a Chunk 0 EM-owned live-payload capture as a hard gate before C1 dispatches.

**Why:** empirically, a v1 plan authored a PostToolUse-on-Agent hook scanning `tool_response.content`. Review flagged the field path as hypothesis. The EM added Chunk 0 ("EM-owned live-payload capture before executor dispatch"). C0 captured a real payload, revealed `tool_response.content` doesn't exist for async responses, and killed the entire v1 approach before any executor wasted cycles.

**Pattern that works:** temporarily inject capture into an existing hook script (e.g. `agent-completion-log.py`), trigger one Agent dispatch, sanitize the JSON payload, commit as plan sidecar (`*.c0-evidence.json`). Only after the real payload shape is confirmed do C1 executors begin.

This is a mandatory Branch B item for any plan whose implementation requires matching against a runtime tool-output field, event envelope, or jq path that has not been observed from a real invocation. Hypothesis-based field paths produce broken hooks that silently no-op or crash at first use.

## Doctrine-Prose Change AC Pattern

**Rule:** for a plan whose deliverable is a doctrine change (a wiki section, a CLAUDE.md rule, a skill-body amendment) with no executable harness, anchor ACs to the specific text invariants the doctrine ships — the doctrine text IS the deliverable. Do not author behavior-fixture AC criteria for a change that ships no executable surface.

For any real I/O side-effect the doctrine change triggers (e.g., a foldering migration, a renamed script), include an AC criterion that can be verified against the file-system contract. Runtime behavior with no harness belongs in reviewer-judgment criteria, marked as such.

**Why:** the 2026-06-18 /distill reshape plan's ACs initially named behavior fixtures that have no test rig — the distill pipeline isn't fixture-tested. The honest, verifiable criteria were the specific invariant text in the shipped docs plus a real regression script for the 102-file foldering migration.

**Shape:** doctrine-change plan AC table has:
- Criteria for the specific text invariants the doctrine ships (verifiable by grep)
- Criteria for concrete filesystem side-effects the change introduces (verifiable by script)
- Reviewer-judgment criteria for runtime behavior or semantic quality assessments
