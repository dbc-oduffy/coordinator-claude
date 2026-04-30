---
description: Dispatch enriched stubs to executor agents
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[stub-ids|directory-path|'all']"
---

# Delegate Execution — Dispatch Enriched Stubs to Executor Agents

Hand enriched, reviewed stub specifications to executor agents for implementation, selecting the appropriate model (Sonnet or Opus) based on stub complexity.

<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
**Project-rag is project-scoped.** It indexes ONE specific codebase, configured at install time. Before reaching for `mcp__*project-rag*` tools, confirm they index the codebase you're investigating — not a different project on the same machine. If your target codebase doesn't have a project-rag index (no `Saved/ProjectRag/` marker at its root, no `--project-root` argument pointing at it in the MCP config), skip this preamble entirely and use grep/Explore.

**If MCP tools matching `mcp__*project-rag*` are available AND they index the codebase you're investigating, prefer them over grep/Explore for any code-shaped lookup.** Symbol-shaped questions ("where is X defined", "find the function that does Y") → `project_cpp_symbol` / `project_semantic_search`. Subsystem-shaped questions ("how does X work") → `project_subsystem_profile`. Impact questions ("what breaks if I change X") → `project_referencers` with depth=2. Stale RAG still beats grep on structure. Fall through to grep/Explore only if RAG returns nothing AND staleness is plausible.
<!-- END project-rag-preamble -->

## Instructions

When invoked, dispatch executor agents to implement enriched and reviewed stubs.

If `$ARGUMENTS` is provided:
- Specific stub IDs (e.g., "2A 2B 2C") → execute only those stubs
- A directory path → execute all ready stubs in that directory
- "all" → execute everything with status "Enriched and reviewed"

### Phase 1: Read Tracker and Identify Ready Stubs

1. Read the tracker README in the chunk directory
2. Identify stubs with status "Enriched and reviewed" (or equivalent — ready for execution)
3. Read the dependency graph / execution order section
4. Verify each stub has been through enrichment AND review (do not execute un-reviewed stubs)
5. Report: "Found N stubs ready for execution. Execution order: [list with dependencies noted]"

### Phase 1.5: Write-Ahead Status Update

**Before dispatching any executors**, mark every stub that is about to be executed:

1. Update the tracker README: change each stub's status from "Enriched and reviewed" → **"Execution in progress"**
2. Commit this tracker update immediately (WAL record — must persist before agents launch)

The executor agents will also mark their individual stub documents (per the executor's write-ahead protocol), creating two layers of breadcrumbs. If a session crashes mid-execution, both the tracker and the stub itself show "in progress."

### Between Dispatch Waves — Checkpoint Protocol (DroneSim T1.1)

After each parallel or sequential executor wave completes, before launching the next:

1. **Verify external persistence** — confirm any persistence step that executors were responsible for (force-save, build artifact write, DB migration commit) actually completed. Executor self-reports that "compiled and saved" may not reflect what hit disk.
2. **Git commit** — commit the wave's output before launching the next wave.

Each wave is a checkpoint. Prefer to never batch multiple waves before committing — if a crash occurs between waves, you lose only the in-flight wave, not all prior work. This directly supports the global doctrine: "Make long-running work resumable — checkpoint to disk so crashes cost one increment, not the full runtime."

### Phase 2: Select Model and Dispatch Executors

#### Model Selection Rubric

**Default: Sonnet. Always.** The enrichment pipeline exists precisely so execution can be cheap. By the time a stub reaches this phase, it has been through enrichment (exact code sketches, line numbers, file paths) and domain review (Sid/Camelia/Palí corrections). The Opus judgment has already been spent — the executor is a typist following a blueprint.

| Stub character | Model | Rationale |
|---|---|---|
| **Any enriched+reviewed stub** | `model: "sonnet"` | The spec IS the Opus judgment. Sonnet follows blueprints reliably. |
| **Very large + natural seams** — API surfaces with independent endpoints, feature sets with clear boundaries | `model: "sonnet"` with **Opus tech lead** (see below) | Too large for one executor; Opus coordinates, Sonnets type. |

**Dispatched executors are always Sonnet.** No exceptions. The `model` parameter on executor dispatch should never be set to `"opus"`. The hierarchy is: Opus oversees, Sonnet types.

**If a stub genuinely needs Opus-level judgment to execute** (unresolved ambiguity, `NEEDS_COORDINATOR` markers, cross-file coherence decisions not captured in code sketches), the EM handles it directly — don't dispatch it. The coordinator IS the Opus. If you find yourself wanting to dispatch an Opus executor, ask: "Is the spec incomplete?" If yes, fix the spec. If no, the EM can do the work inline or supervise Sonnet executors directly.

#### Dispatch

#### Briefing Concreteness (DroneSim T1.4)

Prefer enumerated targets over described scope. "Apply this regex to these 7 files" beats "apply this regex everywhere it's needed." When the work is enumerable, enumerate it in the prompt.

Vague specs invite hallucinated completion — agents with vague instructions will by default report success against their own interpretation of the scope, not against the coordinator's intent. Hardcoded file lists, symbol lists, and exact replacement strings produce measurably higher first-try success than scope descriptions.

**For independent stubs** (no shared dependencies):
- Dispatch executor agents in parallel using Task tool with `run_in_background: true`
- Use `subagent_type: "executor"` and the model selected by the rubric above
- Each executor receives:
  - The enriched stub document path
  - The project root path
  - A list of reference files from the stub's "Reference (read only)" section
  - **The tracker file path** (so the executor can update its own status — see executor agent protocol "Tracker Updates" section)
  - **The chunk codename** (e.g., "chunk-2A", "camera-refactor") — the executor uses this to grep canonical trackers and update every reference, not just the dispatch tracker. Extract the codename from the stub's identifier or filename.
  - Instruction: "Follow the executor agent protocol. Read the stub completely before writing code. Your chunk codename is '{codename}' — use it for the canonical tracker sweep."

**For dependent stubs** (shared files or sequential prerequisites):
- Dispatch one at a time, waiting for completion before starting the next
- Pass any relevant context from the previous executor's output

**For very large stubs with natural seams** (Opus tech lead pattern):
- **Dispatch a dedicated Opus agent as tech lead** — do NOT supervise from the coordinator session directly. The coordinator's context is the scarcest resource in the system; filling it with sub-task orchestration for one large stub wastes capacity that should be reserved for cross-stub decisions, PM conversations, and portfolio-level orchestration.
- The Opus tech lead receives the full enriched stub spec and owns the deliverable end-to-end:
  - Decomposes the stub into sequential sub-tasks at seam boundaries
  - Dispatches Sonnet executors one at a time for each sub-task
  - Verifies each executor's output against the master spec before dispatching the next
  - Makes micro-decisions within the spec's intent without escalating to the coordinator
  - Can chip in directly on a complex sub-task if a Sonnet executor would struggle with it
- The tech lead reports back to the coordinator with a single completion report (DONE/DONE_WITH_CONCERNS/BLOCKED), not a stream of per-sub-task updates
- **Escalation from tech lead to coordinator** only when: spec is genuinely ambiguous, architectural decision exceeds the stub's scope, or a blocker requires PM input

### Phase 3: Monitor Results

For each executor that completes:

**Re-dispatch budget:** Each stub gets a maximum of **3 dispatch attempts** (initial + 2 re-dispatches). This budget is shared across all failure modes (BLOCKED spec fixes, THRASHING re-dispatch, validation self-correction) and **supersedes** the previous THRASHING-specific rule ("if second executor also aborts → escalate to PM") — the universal 3-budget is the single source of truth.

Track attempts in the **tracker README** status column (coordinator-owned), not the stub's own status line (which the executor overwrites with its write-ahead format):

```
Tracker README: | chunk-2A | Execution in progress (attempt 2/3) | ... |
```

After the 3rd attempt, regardless of outcome:
- If still failing: escalate to PM with full dispatch history
- Do NOT re-dispatch. The problem is structural, not fixable by another executor run.
- Document all 3 attempts in the stub's `## Execution History` section

**Exception:** The Phase 3 step-4 self-correction loop for deterministic validation failures (type errors, lint) counts as part of one dispatch attempt, not separate attempts. The budget counts coordinator-level re-dispatches, not executor-internal fix iterations.

**Worked example — how budgets nest:**
1. **Dispatch 1 (attempt 1/3):** Executor internally retries fixable errors up to 3-5 times per its own Deterministic Failure Recovery protocol. Reports DONE but validation fails at coordinator level.
2. **Dispatch 2 (attempt 2/3):** Coordinator re-dispatches with validation errors. Executor retries internally, reports DONE. Validation still fails.
3. **Dispatch 3 (attempt 3/3):** Coordinator re-dispatches again. If this attempt also fails → PM escalation. No 4th dispatch regardless of failure mode.

**Phase 3.0: Post-Executor Haiku Verification**

Before the coordinator reads files manually, dispatch a **Haiku agent** to do the mechanical data-gathering. The Haiku agent receives the executor's completion report and the stub's acceptance criteria, then:

1. **Confirms files changed** — `git diff --name-only` against the pre-execution state. Do the modified files match what the stub specified?
2. **Runs project validation** — compile, typecheck, lint, test suite (the command identified in the stub or project config)
3. **Checks acceptance criteria** — reads the stub's `## Acceptance Criteria` section and for each `AC-N:` item:
   - Verifies the criterion against the git diff and current file state
   - Returns a structured checklist: `AC-N | criterion text | ✓ checked / ✗ unchecked | evidence or gap description`
   - **Graceful degradation:** If the stub has no `## Acceptance Criteria` section, the Haiku agent reports this absence in its structured output. The coordinator treats a missing section as a signal to investigate the enrichment — not as a verification failure.
4. **Returns a structured report:** files changed (expected vs actual), validation pass/fail with output, acceptance criteria checklist (checked/unchecked)

The coordinator then performs the semantic spec compliance check (step 2 below) using the Haiku's structured data — not by reading every file from scratch.

**Why Haiku:** `git diff`, `tsc --noEmit`, and reading file:line are mechanical. Delegating this data-gathering saves coordinator context for the judgment calls (spec intent matching, gap identification).

**Dispatch template:**
```
Agent(
  model: "haiku",
  prompt: """
  You are a mechanical verification agent. Check the following:

  EXECUTOR REPORT:
  {paste executor completion report}

  STUB ACCEPTANCE CRITERIA:
  {paste stub's ## Acceptance Criteria section, or "NONE — report absence"}

  TASKS:
  1. Run: git diff --name-only {pre-execution-commit}..HEAD
     Report: files changed (expected vs actual from executor report)
  2. Run project validation: {validation command from stub or project config}
     If no explicit command, use the Validation Matrix: tsconfig.json → npx tsc --noEmit,
     pyproject.toml → poetry run python -m py_compile, package.json with pnpm → pnpm typecheck.
     If no project signal found, report validation as SKIPPED (do not assume passing).
     Report: pass/fail/skipped with output
  3. For each AC-N item, verify against current file state:
     Report: AC-N | criterion | PASS/FAIL | evidence

  OUTPUT FORMAT (write to stdout, not to a file):
  ## Haiku Verification Report
  ### Files Changed
  Expected: [list from executor report]
  Actual: [list from git diff]
  Match: yes/no

  ### Validation
  Command: {command}
  Result: PASS/FAIL/SKIPPED
  Output: {relevant output, truncated to 50 lines}

  ### Acceptance Criteria
  | AC | Criterion | Result | Evidence |
  |----|-----------|--------|----------|
  | AC-1 | ... | PASS/FAIL | ... |

  ### Missing Criteria
  [If stub has no ## Acceptance Criteria section, state:
   "Stub lacks Acceptance Criteria section — flag for coordinator"]
  """
)
```

**If Haiku reports "Stub lacks Acceptance Criteria section":**
1. Check the stub's enrichment status line — was it previously enriched?
   - **If enriched and reviewed:** Spec regression. The enricher should have added ACs. Re-dispatch enricher for this stub only (targeted re-enrichment), then re-queue for execution.
   - **If not enriched:** Hard stop — this stub bypassed the pipeline. Do not execute. Report: "Stub {id} reached execution without enrichment. Pipeline violation."
2. Do NOT proceed with execution without acceptance criteria — they are the verification contract.

**On DONE/DONE_WITH_CONCERNS report:**
1. Read the executor's completion report + **Haiku verification report**
2. **Spec compliance check** — the Coordinator verifies (using Haiku data as input):
   - Did the executor implement everything the stub specifies?
   - Did the executor build anything the stub does NOT specify?
   - Does the implementation match the stub's intent, not just its letter?
   - Read actual key files only where the Haiku report flags discrepancies or unchecked criteria
3. **Post-execution validation** — skip if Haiku already ran it and it passed. Re-run only if Haiku reported failures or couldn't run the validation command.
4. **Self-correction loop** (max 2 iterations):
   - If validation fails with deterministic errors (test failures, type errors, lint violations): re-dispatch the executor with the failure output and instruction to fix. Do NOT escalate to code review with known failures.
   - If validation fails after 2 re-dispatches: escalate to coordinator for diagnosis. The failures may indicate a spec problem, not an execution problem.
   - If validation passes: proceed to step 5.
5. If spec-compliant and validation passes: route to code quality review via `/review-dispatch`
   - Post-execution review findings flow through the review-integrator for application (via Phase 3.7 of `/review-dispatch`), not the EM manually
6. If not spec-compliant: re-dispatch executor with specific gap list (this is distinct from validation failure — this is missing work, not broken work)
7. Update tracker status to "Done" with commit hash if applicable

**On BLOCKED report:**
1. Read the structured escalation report (BLOCKED format)
2. **Persist attempted approach:** Extract the "Attempted" field from the BLOCKED report and add to the task's `metadata.tried_and_abandoned` via TaskUpdate. Format: `"Tried: [attempted approach] — Blocked: [blocker]"`
3. Diagnose the issue:
   - **If fixable by updating the stub:** Update the stub document with the resolution, then re-dispatch the executor
   - **If requires architectural decision:** Make the decision (or escalate to PM), update the stub, then re-dispatch
   - **If fundamental spec problem:** Flag for PM/Coordinator review, do not re-dispatch until resolved
4. When re-dispatching after BLOCKED, include in the executor prompt if `tried_and_abandoned` is non-empty:
   ```
   ANTI-REPETITION: The following approaches were tried on this stub:
   {paste tried_and_abandoned entries}
   The spec has been updated to address the blocker. Use the updated spec, not the old approach.
   ```
5. Document what was changed in the stub and why

**On THRASHING REPORT (self-detected):**
1. Check the executor's return message for post-mortem details (detection type, approaches tried, last error)
2. **Persist failed approaches:** For each item in the post-mortem's "Approaches tried" list, add to the task's `metadata.tried_and_abandoned` via TaskUpdate. Format: `"Tried: [approach] — Failed: [last error/state]"`. This survives compaction and prevents re-dispatched executors from repeating dead approaches.
3. Triage by the diagnosis:
   - **spec problem** → fix the spec based on the post-mortem's "Approaches tried" and "Last error/state", then re-dispatch
   - **environment problem** → investigate the environment issue (missing dependency, permissions, file state) before re-dispatching
   - **architectural gap** → escalate to PM — the stub may need redesign, not just a spec patch
5. When re-dispatching after THRASHING, include in the executor prompt:
   ```
   ANTI-REPETITION: The following approaches were tried and failed on this stub:
   {paste tried_and_abandoned entries}
   Do NOT repeat these approaches. See stub ## Execution Post-Mortem for details.
   ```
6. The re-dispatch budget (3 attempts total) applies — check the tracker README for the current attempt count before re-dispatching.

### Scope-Conformance Check — After Every Executor Returns (geneva T1.5)

Before staging any executor output:

1. Run `git diff --stat` to enumerate all changed paths.
2. Confirm each changed path is within the dispatch's declared scope.
3. Stash or revert any out-of-scope edits — common out-of-scope mutations include test file deletions, unrelated refactors, and autonomous commits the executor made despite instructions.

**Dispatch-prompt enforcement clause** — include this verbatim in every executor prompt:

> Modify ONLY the files listed in scope. Do not commit. Do not delete or modify tests unless explicitly listed.

See `skills/verification-before-completion/SKILL.md` → "Scope-Conformance Check After Executor Returns" for the coordinator-side mechanical check.

### Phase 4: Final Verification

After all stubs are executed:

1. Run project-level validation (full compile, typecheck, lint, or equivalent)
2. Check for integration issues between stubs that were executed in parallel
3. Report any cross-stub conflicts or issues

### Phase 5: Verify Tracker State

Executors own their tracker updates (status, commit hashes). The coordinator's role here is verification, not data entry — but verification must be **thorough**.

**5.1: Dispatch tracker verification**
1. Read the dispatch tracker — confirm each executor updated its own status
2. Fix any gaps (executor crashed before updating, or was dispatched without tracker path)
3. Note any stubs that remain blocked or require PM decision
4. Update the tracker's progress summary

**5.2: Canonical tracker sweep verification**
For each completed stub, grep its codename across canonical trackers to confirm the executor ran its sweep:
```bash
grep -in "<codename>" docs/project-tracker.md tasks/*/todo.md docs/roadmap.md ROADMAP.md 2>/dev/null
```
- If a canonical tracker still shows the item as pending/unchecked despite the executor reporting DONE, fix it now
- If `docs/project-tracker.md` references the work and wasn't updated, that's a gap — update it
- This is the coordinator's backstop for the executor's sweep. If executors did their job, this is a no-op. If they didn't, it catches the drift.

### Completion Report

```
## Execution Summary

**Stubs executed:** N of M
**Stubs blocked:** K (with reasons)
**Validation:** Pass/Fail

### Completed
| Stub | Status | Notes |
|------|--------|-------|
| ... | Done | ... |

### Blocked (if any)
| Stub | Blocker | Stub Needs |
|------|---------|------------|
| ... | ... | ... |

### Next Steps
- [What remains to be done]
```

### Relationship to Other Commands

- **`/enrich-and-review`** must be run before this command — stubs must be enriched and reviewed
- **`/review-dispatch`** handles the review step that precedes execution
- For a post-execution code quality pass, use `/review-dispatch` (see Phase 3, step 5)
