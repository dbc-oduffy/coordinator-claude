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

## Pre-dispatch confidence checklist

Before dispatching a build-task agent or entering plan mode for a non-trivial feature, walk through these five gates. Any "no" demands more investigation, not bigger agent dispatch. NOT a numeric score — the checklist is the gate.

1. **No duplicate.** Have I greped for an existing implementation under nearby paths? **(See `Negative-Search Before Drafting` below for the formal greppable procedure.)**
2. **Architecture-compatible.** Does the proposed approach use existing project conventions (tech stack from CLAUDE.md, patterns from atlas)? If introducing a new dependency, is the rationale in the plan? **(See `Codebase Research (before file mapping)` above for the survey discipline.)**
3. **Official docs read.** For any external API the plan calls into, have I read the actual signature — not relied on training memory?
4. **Reference impl seen.** For any nontrivial pattern, can I point to a working implementation (OSS or in our codebase) that demonstrates it? **(See `Codebase Research (before file mapping)` above.)**
5. **Root cause known (bugs only).** For bug fixes, do I have evidence the diagnosis is correct, not just plausible?

Five greens → dispatch. Any red → loop back to investigation tier 1-3 or escalate to PM.

**Validation floors derive from emission shape, not author intuition.** Setting `≥N items emitted` as a gate when N is chosen by feel produces false-negatives (gate passes on a near-empty output) and false-positives (gate blocks a legitimately sparse but correct result). Before writing a count gate, trace the emission path: identify the producer loop or query and derive the minimum expected output from the logic, not from a gut estimate. Source: 2026-05-14 project-rag-ue-addon.

**Sibling-team archive memos collapse cross-repo coordination cost.** When sizing cross-repo work, READ sibling-team `archive/*proposal*` / `*coordination*` / `*authority*` memos before estimating bump cost. Tri-repo ratification is often over-cost for unilateral-authority shapes already established in a peer's archive — the authority decision may already be made and the bump is unilateral. Skipping the archive read produces inflated complexity estimates and unnecessary PM escalations. Source: 2026-05-15 claude-unreal-holodeck.

## Domain Language

Read `CONTEXT.md` if present at the project root; if absent, proceed silently — do not flag, suggest, or scaffold. Use canonical terms throughout the plan — and for any term on the `_Avoid_:` lists, substitute the canonical term silently. If the plan introduces a new domain term that will recur across sessions, append it to `CONTEXT.md` as part of the plan-writing pass.

## Codebase Research (before file mapping)

<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
**Project-rag is project-scoped.** It indexes ONE specific codebase, configured at install time. Before reaching for `mcp__*project-rag*` tools, confirm they index the codebase you're investigating — not a different project on the same machine. If your target codebase doesn't have a project-rag index (no `Saved/ProjectRag/` marker at its root, no `--project-root` argument pointing at it in the MCP config), skip this preamble entirely and use grep/Explore.

**If MCP tools matching `mcp__*project-rag*` are available AND they index the codebase you're investigating, prefer them over grep/Explore for any code-shaped lookup.** Symbol-shaped questions ("where is X defined", "find the function that does Y") → `project_cpp_symbol` / `project_semantic_search`. Subsystem-shaped questions ("how does X work") → `project_subsystem_profile`. Impact questions ("what breaks if I change X") → `project_referencers` with depth=2. Stale RAG still beats grep on structure. Fall through to grep/Explore only if RAG returns nothing AND staleness is plausible.
<!-- END project-rag-preamble -->

Before defining the file structure, check what's already been documented about the relevant systems. Read these if they exist (skip silently if they don't):

1. `tasks/architecture-atlas/systems-index.md` → relevant system pages in `tasks/architecture-atlas/systems/`
2. `docs/wiki/DIRECTORY_GUIDE.md` → relevant wiki guides in `docs/wiki/`
3. `tasks/repomap.md` (or task-scoped variant)

This gives you the structural context to make informed file-mapping decisions without redundant grep discovery. Use Glob/Grep after this to fill specific gaps — exact line numbers, recent additions not yet in the atlas, etc.

**Substrate-verification at plan time.** Verify substrate facts (file paths, framework names, helper APIs, line numbers) via `ls`/`grep` while authoring — not at completion. Two minutes of disk verification prevents the substrate-fact errors reviewers will catch on R1.

**Reviewer pre-resolved substrate values need executor `ls` confirmation.** A reviewer citing a `@import` path as authority for a manifest `functional_probe.path` field is hypothesis based on indirect evidence — the `@import` is the local-install path; the manifest's path field is schema-defined as repo-source path. Reviewer pre-resolution is never authoritative on schema-distinct fields. Pre-resolution of any path-typed field requires an executor `ls` confirmation step in the plan. Source: 2026-05-08 project-rag.

**Periodic baselines drift — instruct read-current-and-increment, not match-spec.** When a stub names a count, version, or baseline ("bump from 55 to 56"), absolute values rot between enrichment and execution. Phrase as "read current value and increment" so the math survives the gap.

**Plunge vs. plan split by substrate certainty, not appetite.** Verified-on-disk parts of a workstream may plunge directly to execution. Parts that depend on foreign-repo substrate (paths, APIs, schema fields in a sibling repo you haven't grepped) require a plan with an explicit verification step before execution dispatch. Certainty is the gate, not effort estimate. Source: 2026-05-18 project-rag.

**Satisfy schema constraints by construction before relaxing.** When a closed-enum schema gate appears to block a new entity type, ask "can the producer satisfy the constraint?" before "should we relax the constraint?" Relaxation carries cross-consumer blast radius; satisfaction by construction is local and reversible. Document the construction path in the plan before entertaining schema changes. Source: 2026-05-15 claude-unreal-holodeck.

- Scaffolded config files (templates the plan instructs an executor to write) must self-disclose which fields they actually support — silent ignoring of unrecognized fields breeds downstream debugging cost. Plans citing config templates should require the template carry a `# Supported fields:` comment listing the keys.
- Plans extending an existing pipeline (e.g. adding a new wave to /distill, a new phase to /update-docs) MUST grep the pipeline's existing scratch-path conventions before declaring output paths — silent collision with sibling waves' scratch namespaces breaks parallel safety.

**TEMPLATE blocks with substrate-divergent specifics are worse than no TEMPLATE.** Concrete assertions in TEMPLATE blocks (file paths, version strings, flag names, count thresholds) must be substrate-checked at plan-time, or stripped to truly skeletal pseudocode. A TEMPLATE that carries specific values not verified on disk becomes a fabrication vector — executors treat TEMPLATE content as authoritative. Pre-review audit: walk every concrete value in a TEMPLATE block and confirm it against `ls`/grep, or replace with a `<placeholder>` that forces the executor to resolve it. Source: 2026-05-16 project-rag.

## Negative-Search Before Drafting

Before committing to a prescribed shape, run a negative search to surface prior decisions that argue against what the plan proposes to introduce or restore.

**No-fabrication branch — predicates citing fields must grep the field first.** A plan or predicate that asserts on a frontmatter key, env var, config field, or schema column without grepping for the literal name is fabrication, not verification. Extends the 5-dim no-duplicate branch into no-fabrication: *does the named field exist on disk?* Before writing any trigger gate, abstain condition, or rule that references a structured data field (`outcome:`, `status:`, `kind:`), grep the schema definition (e.g., `schemas/handoff.yaml`, frontmatter validator) and quote a file:line citation. Absence of a grep citation against the schema is a plan smell. Source: 2026-05-07 external-pattern-checker plan trigger-gate cited a non-existent `outcome: failed` field on handoff schema (enum is `active | consumed | superseded`); the gate would have fired on EM mood, not signal. Greppable from `coordinator/CLAUDE.md` § Pre-Dispatch Verification (`no-fabrication`).

1. **Identify the central nouns/abstractions** the prescription introduces or restores (e.g., a pattern name, an architectural layer, a specific tool or verb).

2. **Search for those nouns paired with prohibition vocabulary.** Grep `tasks/lessons.md` and `docs/wiki/` for each noun alongside: `do not`, `never`, `tear down`, `deprecated`, `forbidden`, `removed`, `do NOT`. `bin/query-records` is also useful here for frontmatter-indexed records.

3. **If a prohibition exists, the plan must do one of two things:**
   - **(a)** Acknowledge the prior decision in §1 Objective and explicitly justify the reversal — with reasoning that engages the original argument, not merely reasserts the new direction.
   - **(b)** Recuse the prescription and choose a different shape that does not conflict with the prior decision.

4. **Reversal-verb hint:** If §1 Objective uses any of `restore`, `reintroduce`, `reconstitute`, `undo`, `re-add`, or `bring back`, the plan author should *consider suggesting* a staff-session to the PM before approval. This is a suggestion only — the PM owns the call. Frame it as: "This plan reverses prior direction; PM may want a staff-session before approving execution."

5. **External-doctrine proposals — independent location-challenge.** When a peer audit or external review recommends a fix, never adopt the proposed *location* uncritically — proposals frame fixes from where they noticed the problem, which is rarely the cheapest place to apply them. Run an independent location-challenge before drafting: would an upstream surface (producer skill, hook, dispatch template) prevent the class of problem more cheaply than the proposed downstream patch?

**Plan-substrate CLI verification via `--help` / argparse grep.** When a plan cites a script's CLI flags, require a `--help` excerpt or `argparse.add_argument` grep in the plan body — source-range inspection misses the actual surface. Reviewing the source file for argument *definitions* is insufficient; flag names surfaced to callers are in the `add_argument` call strings, which may differ from internal variable names. The Staff Engineer-level reviews have missed invalid flags this way. Source: 2026-05-14 project-rag (`--source engine --authority engine` cited in plan were not valid flags).

**Verify prereq-cited banks/baselines with a dry-scorer/dry-validator pass before consuming downstream.** Handoff prereqs naming a specific class of artifact (smoke bank, graded bank, scored baseline) need a dry pass before leg 1 of the consuming workstream runs end-to-end. Without the dry pass, the consumer silently operates on a mismatched input class and produces subtly wrong outputs that pass all structural checks. Source: 2026-05-17 project-rag.

## File Structure

Before defining tasks, map out which files will be created or modified and what each is responsible for:

- Design units with clear boundaries and well-defined interfaces
- Prefer smaller, focused files over large ones doing too much
- Files that change together should live together — split by responsibility, not technical layer
- In existing codebases, follow established patterns; include splits for unwieldy files when reasonable

This structure informs task decomposition — each task should produce self-contained changes.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

**Additive-before-destructive ordering.** When chunks are file-independent and one is purely additive while another removes existing code, land the additive chunk first. The destructive chunk's regression window shrinks because the additive piece is already in the codebase — reviewers and tests can verify behavior before removal, not after.

- Order chunks additive-before-destructive — scaffolding/new-symbol chunks land before delete-old-symbol chunks. A destructive chunk that lands before its replacement is staged risks a broken intermediate state on rollback.

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

- [ ] [Testable criterion 1]
- [ ] [Testable criterion 2]
- [ ] [Testable criterion 3]

## Non-Goals

- [Explicitly out of scope — heads off mid-stream scope creep]

---
```

**Why these fields are required:**
- **Scope mode** routes review depth and the evidence bar. Reviewers and `/merge-to-main` read it.
- **Acceptance criteria** are what reviewers check against and what the ship verdict scores. Without them, "done" reduces to "the agent says it implemented it."
- **Non-goals** are the most-skipped field and the single highest source of scope drift. Spend 30 seconds on them.

The `Status:` field is part of the write-ahead protocol — it gets updated at every phase transition (review, enrichment, execution) so that crashed sessions leave unambiguous state. See ARCHITECTURE.md § "The Write-Ahead Status Protocol" for the full state machine.

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

## Roadmap and Cross-Repo Plan Hazards

These apply when a plan is part of a multi-stub roadmap or moves work between repos.

**Single-consumer audit-spike work folds into Phase 0 of the implementation plan, not a separate roadmap stub.** When a roadmap-shaped audit/spike has exactly one downstream consumer (the implementation workstream that uses its findings), the audit is not a peer stub — it's the first phase of that consumer. Separate-stub framing introduces handoff overhead, stale-findings risk between stubs, and review duplication for no integration benefit. Roadmap-shape heuristic: count consumers. ≥2 consumers → standalone audit stub justified; 1 consumer → fold into Phase 0 of that consumer's plan.

**Cross-repo MOVE between repos = audit residual at the source.** When a plan moves a stub/component/feature from repo A to repo B, the destination often only needs *part* of the original scope. The residual in repo A is not auto-deleted by the MOVE — audit what stays behind and decide explicitly: keep / delete / migrate. Silent MOVE without source-residual audit leaves orphaned scaffolding (configs, hooks, references, dead helpers) at the origin that survive every subsequent grep as "still in use somewhere," gating future cleanups.

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

### (f) Concurrency-safe file design

When a plan proposes shared-file appends across N machines or sessions, prefer **per-machine paths** over "atomic per-block append" merge logic — the latter is a euphemism for "PM resolves merges at daily wrap." Per-machine files sidestep the conflict class entirely.

### (g) File-overlap analysis before parallel dispatch

Plans that claim "fully independent files" still need EM-side file-overlap analysis before parallel executor dispatch. Trust-but-verify: a 30-second cross-check against the plan's file lists prevents two executors from racing the same file under independence assumptions.

**Index files are hidden shared substrate.** `docs/README.md`, `docs/wiki/DIRECTORY_GUIDE.md`, and any central index get rewritten by every chunk that touches them. These files never appear in per-chunk file lists yet every chunk that adds a new wiki page, doc, or plan entry implicitly writes to them. In mise/parallel-dispatch file-overlap analysis, the anchor chunk must own all index rows and forward-references. If no anchor is designated, index files must be committed by the EM after all chunks land — never by individual parallel executors. Source: 2026-05-15 project-rag.

### (h) Plan-time dispatch decisions go stale

Dispatch-shape decisions written into a plan (Haiku/Sonnet/Opus, parallel/serial, scout vs general-purpose) are valid at plan-write time only. Phase-2 dispatch must re-check that the chosen shape still fits the substrate; staleness window is ~24h.

### (i) Read-current-and-increment for periodic baselines

Increment math is durable; absolute baseline values rot. Stubs touching a periodically-changing baseline (orphan count, lesson count, queue depth) MUST instruct executor to `read-current-then-increment-by-N` rather than asserting absolute target values.

### (j) PM redirect mid-pipeline invalidates completed reviews

PM redirect mid-pipeline (scope/direction change after dispatch is in flight) counts as structural rework — completed reviews are invalidated against the new surface and MUST be re-run before treating the pipeline as resumable. Don't smuggle pre-redirect review approvals across a surface change.

### (k) No-TBD-thresholds (extends 5-dim confidence checklist)

Any plan that ships with `TBD` / `???` / `<placeholder>` in a threshold position (cutoff value, retry count, timeout) is unsafe to dispatch — the executor will either fabricate the value or fail at runtime. Resolve thresholds at plan-write time or explicitly defer the chunk.

### (l) Plan frontmatter is EM-only territory

Plan frontmatter (`status:`, `landed_in:`, `reviewed_by:`) is EM-only territory. Executor dispatch briefs MUST include verbatim "DO NOT modify plan frontmatter — that is the EM's bookkeeping surface." Even with this, audit `git diff` on plan files in the post-dispatch verification step.

### (m) Seam Contract for cross-stub symbols

In a multi-stub plan, every cross-stub symbol dependency — a function in Stub-1 that calls a symbol Stub-2 is supposed to produce — is a *seam*. The producer stub MUST ship its symbol in the same wave as the consumer that references it. A `getattr(module, "X", None)` or `try/except AttributeError` graceful-degrade clause against a planned primitive is a permanent fallback, not a temporary bridge: once the consumer ships and the producer hasn't, the degrade clause silently becomes load-bearing infrastructure and the call path permanently no-ops. If the producer is genuinely not in the same wave, the consumer stub MUST include a task that ships the symbol — not a degrade clause. Distinct from (e): (e) governs runtime fallbacks; (m) governs plan-time forward-references.

## Self-Modifying Infrastructure

Plans that modify hooks, validators, or other infra that runs against the plan's own artifacts must include a smoke-test step with synthetic input that exercises the modified code path BEFORE the modified hook fires on real session traffic. The plan body MUST cite the synthetic-input file path.

## Lessons Learned

**Default to subagent dispatch over a new RPC verb when *adding* internal operations.** When a plan proposes a new tool/verb/handler/CLI-job, ask first: can a subagent compose this from existing primitives via `execute_python_code` + `inspect` + extant MCP verbs? If yes, the plan should propose the dispatch path, not the new verb. The new verb earns its place only on (a) C++-only capability, (b) transactional state coupling that primitive composition cannot preserve, or (c) cross-call editor-state invisible in tool signatures. **Never default to dispatch over an existing verb without explicit retire-justification** — prior surface is the proven path.

Tag: `[universal]` — applies to any project_type using the coordinator pipeline.

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
