---
title: /delegate-execution procedure
created: 2026-05-06
type: doctrine
related:
  - plugins/coordinator/commands/delegate-execution.md
  - plugins/coordinator/agents/executor.md
  - docs/wiki/dispatching-parallel-agents.md
  - plugins/coordinator/skills/review-code/SKILL.md
  - plugins/coordinator/commands/enrich-and-review.md
---

# /delegate-execution — Dispatch Enriched Stubs to Executor Agents

Hand enriched, reviewed stub specifications to executor agents for implementation, selecting the appropriate model (Sonnet or Opus) based on stub complexity. The slash-command `/delegate-execution` exists as a thin entry-point; this wiki carries the enforceable procedure.

Executors dispatched via this procedure carry the meta-ask preamble (see `snippets/meta-ask-preamble.md`, synced into `agents/executor.md`) and have access to ergonomic substrate helpers (`claude_machine_local` Python module, `claude-machine-local.{sh,ps1}` sourced shell helpers) for portable cross-machine path references.

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

**For plan-based fan-out dispatches (no separate tracker README):** instead of a tracker README entry, the EM creates a per-chunk sidecar at `tasks/<plan-slug>/flight/<chunk-id>.md` and passes `sidecar_path:` in the executor brief. The executor updates the sidecar's `status:` field (not the plan body) as its write-ahead record. See § Flight-Recorder Sidecars below for the full convention.

### Between Dispatch Waves — Checkpoint Protocol

After each parallel or sequential executor wave completes, before launching the next:

1. **Verify external persistence** — confirm any persistence step that executors were responsible for (force-save, build artifact write, DB migration commit) actually completed. Executor self-reports that "compiled and saved" may not reflect what hit disk.
2. **Git commit** — commit the wave's output before launching the next wave.

Each wave is a checkpoint. Prefer to never batch multiple waves before committing — if a crash occurs between waves, you lose only the in-flight wave, not all prior work. This directly supports the global doctrine: "Make long-running work resumable — checkpoint to disk so crashes cost one increment, not the full runtime."

### Phase 2: Select Model and Dispatch Executors

#### Model Selection Rubric

**Default: Sonnet. Always.** The enrichment pipeline exists precisely so execution can be cheap. By the time a stub reaches this phase, it has been through enrichment (exact code sketches, line numbers, file paths) and domain review (the Game Dev Reviewer/the Data Science Reviewer/the Front-End Reviewer corrections). The Opus judgment has already been spent — the executor is a typist following a blueprint.

| Stub character | Model | Rationale |
|---|---|---|
| **Any enriched+reviewed stub** | `model: "sonnet"` | The spec IS the Opus judgment. Sonnet follows blueprints reliably. |
| **Very large + natural seams** — API surfaces with independent endpoints, feature sets with clear boundaries | `model: "sonnet"` with **Opus tech lead** (see below) | Too large for one executor; Opus coordinates, Sonnets type. |

**Dispatched executors are always Sonnet.** No exceptions. The `model` parameter on executor dispatch should never be set to `"opus"`. The hierarchy is: Opus oversees, Sonnet types.

**If a stub genuinely needs Opus-level judgment to execute** (unresolved ambiguity, `NEEDS_COORDINATOR` markers, cross-file coherence decisions not captured in code sketches), the EM handles it directly — don't dispatch it. The coordinator IS the Opus. If you find yourself wanting to dispatch an Opus executor, ask: "Is the spec incomplete?" If yes, fix the spec. If no, the EM can do the work inline or supervise Sonnet executors directly.

#### Dispatch

#### Briefing Concreteness

Prefer enumerated targets over described scope. "Apply this regex to these 7 files" beats "apply this regex everywhere it's needed." When the work is enumerable, enumerate it in the prompt.

Vague specs invite hallucinated completion — agents with vague instructions will by default report success against their own interpretation of the scope, not against the coordinator's intent. Hardcoded file lists, symbol lists, and exact replacement strings produce measurably higher first-try success than scope descriptions.

**Briefs touching an existing surface MUST name the pre-existing regression-net test file(s) in the verification step — not just newly-authored tests.** Executors verify exactly what they are told to verify. A brief that says "run the new tests" gets green-on-new while the executor's change silently breaks the existing regression net, because the executor never ran it. The blind spot is structural: the executor's verification surface is the brief's verification surface. When a chunk modifies an existing module, enumerate the pre-existing test file(s) covering that module by path in the brief's verification step alongside any new tests, so the executor runs both.

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
- Dispatch a **fresh executor per stub/chunk**, one at a time, waiting for completion before starting the next — never one long-lived agent handed chunk after chunk (the overload in slow motion: context accumulation, growing blast radius, degrading judgment).
- **Distinguish the two dependency kinds before serializing.** A *shared-file* dependency is genuinely serial — file-overlap is the unconditional gate. But a *pure sequential-prerequisite* dependency (B consumes A's output/contract, disjoint files) only gates B's **verification**, not its **authoring**: if A's interface is pinned (full signature written down, authorable-against without asking the producer), B can be authored concurrently with verification concentrated at merge. **By default, author pinned-interface consumers concurrently** — serialize into a predecessor wave only when the interface can't be confidently pinned, or per-chunk blast-radius isolation is worth the serialization on a high-stakes surface. → `docs/wiki/dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy (Author vs. verify).
- Pass any relevant context from the previous executor's output
- **A single coupled stub that exceeds the per-executor budget (~5-10 min / one coherent surface, 15 min hard ceiling) is itself decomposed into a sequence of fresh-agent dispatches with EM verify-between.** "Can't parallelize" ≠ "one dispatch" — coupling removes concurrency, not decomposition. This is lighter than the Opus-tech-lead pattern below; reserve that for genuinely large stubs needing a dedicated coordinating context. → `docs/wiki/dispatching-parallel-agents.md` § Coupling Rules Out Concurrency, Not Decomposition.

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

Track attempts in the **tracker README** status column (coordinator-owned), not the stub's own status line:

```
Tracker README: | chunk-2A | Execution in progress (attempt 2/3) | ... |
```

<!-- Review: dispatch-ledger vocabulary completion sweep -->
**Sidecar alternative (plan-based fan-out):** when there is no tracker README, track attempt counts in the EM's wave-map entry (`skills/execute-plan/SKILL.md` § Phase 1.6) and in the per-chunk run-report sidecar at `state/subagent-share/<session-id>/<provision_key>.md`. See § Flight-Recorder Sidecars below.

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
5. If spec-compliant and validation passes: route to code quality review via `/review-code`
   - Post-execution review findings flow through the review-integrator for application, not the EM manually. This requires an on-disk sidecar — the reviewer writes to its provisioned `state/subagent-share/<session>/<provision_key>.md` sidecar (pre-provisioned by the dispatching EM in the common case, self-scaffolded into that same home otherwise) and returns the path; the integrator reads that path, not an inline finding list.
6. If not spec-compliant: re-dispatch executor with specific gap list (this is distinct from validation failure — this is missing work, not broken work)
7. Update tracker status to "Done" with commit hash if applicable

**Anti-dodge framing for executors:** When an executor hits an unexpected gate, BLOCKED is the correct answer — substrate switches are dodges. An executor reaching for a different tool, language, or implementation pattern when the spec's named approach hits resistance is hiding a spec problem behind a self-authorized scope expansion. Pair with a sanity-floor: "if the stated approach can't make it past <named gate>, return BLOCKED with the gate quoted, do not switch substrates."

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

### Scope-Conformance Check — After Every Executor Returns (example-repo T1.5)

Before staging any executor output:

1. Run `git diff --stat` to enumerate all changed paths.
2. Confirm each changed path is within the dispatch's declared scope.
3. Stash or revert any out-of-scope edits — common out-of-scope mutations include test file deletions, unrelated refactors, and autonomous commits the executor made despite instructions.

**Dispatch-prompt enforcement clause** — include this verbatim in every executor prompt:

> Modify ONLY the files listed in scope. Do not commit. Do not delete or modify tests unless explicitly listed.

See `docs/wiki/verification-before-completion.md` (or the active equivalent) → "Scope-Conformance Check After Executor Returns" for the coordinator-side mechanical check.

**Apply executor briefs must explicitly forbid cross-repo writes — Sonnet executors will follow wiki redirect stubs to sibling repos and write there directly.** When a wiki file in the current repo is a redirect stub (e.g. "new content lands addon-side"), an executor will correctly infer the canonical destination and write there — violating cross-repo write discipline. The instinct on content destination can be right while the write path is wrong. The apply-dispatch prompt's OUT-OF-SCOPE block must include verbatim: *"Do NOT write to any path outside the current repo root, even if a wiki redirect stub names the canonical sibling location — flag such records for memo dispatch instead."*

**The `Edit` tool is guarded; `Bash` is not — and the write-outside-sandbox confinement was removed end-to-end.** Two consequences for source-writing dispatches: (1) a general-purpose subagent may now write source directly by design, so the *operative* discipline is that the EM reviews every subagent source-write via `git diff` before commit (reviewers stay read-only-on-source by convention — their Bash allowlist blocks commit/push, so any stray edit lands only in the working tree for the EM to catch on the diff); (2) writes to a SIBLING repo block the `Edit` tool but NOT `Bash`, so a `Bash`/python/PowerShell-heredoc write can still land unreviewed source in a sibling repo — the cross-repo forbid clause above is exactly what closes that gap. For sanctioned source writes prefer `coordinator:executor`; otherwise knowingly accept the bypass and have the EM review every on-disk diff before committing.

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
- **`/review`** handles the plan-review step that precedes execution
- For a post-execution code quality pass, use `/review-code` (see Phase 3, step 5)

---

## Bug-Blitz Pattern — Executor Edit-and-Report, EM Serializes Commits

From the live bug-blitz smoke run, two defects were discovered in the original design:

1. **Concurrent-commit absorption** — multiple executor self-commits bundled into one with only one message surviving.
2. **Scope sweep** — coordinator-safe-commit consulted touched-files from the long-lived session, absorbing 46 unrelated dirty files from concurrent workstreams.

**Fix pattern (now canonical):** Executors **edit-and-report only** (no self-commit). EM serializes
commits at wave gate by invoking the `ceremony.scoped_git_commit` op — `worktree_root`, the
wave's `paths`, and the commit `message` — rather than hand-rolling git. This pattern prevents
both absorption and scope sweep. The op inherits its underlying commit pipeline's mechanism
selection (private index when staged content diverges from the worktree, ordinary pathspec
commit when it agrees) rather than the caller having to pick one by hand — see
`scoped-safety-commits.md § SC-DR-015`.

This retires the earlier `git reset && git add -- <paths> && git commit -m "<message>"` recipe.
That form's leading `git reset` cleared the *shared* index — unstaging whatever a concurrent
session had staged — to make an absent trailing pathspec load-bearing; the op needs neither: it
takes an explicit `paths` list and never resets the shared index out from under a peer.

## File deletions in retirement/migration chunks route to the EM — `git rm` is blocked for executors

The subagent destructive-action EM-lock denies all git verbs, `git rm` included, so a retirement/migration executor cannot stage a file deletion. Its filesystem-`rm` fallback removes the file from disk but does NOT persist to the index — so the deletion silently fails to land in the commit. Route file DELETIONS in retirement/migration chunks to the EM (`git rm`), OR let the executor filesystem-`rm` and have the EM stage the deletion. Either way, verify the deletion on disk AND in the index (`git status` shows a staged `D`) — never trust the executor's "deleted" claim. (C8a schema-file retirement: the executor's `git rm` was denied, its filesystem-rm fallback didn't reach the index.)

## Copy-into-dest executors silently clobber same-named files — an `M` on an expected-new path is the tell

A copy/merge executor that writes files into a destination can overwrite a same-basename, different-content file the destination already owned. The tell is in `git status`: a **genuinely new** write lands as `??` (untracked); an **`M`** (modified) on a path you expected to be new means the write clobbered an existing file. Before committing a copy/merge dispatch, verify each expected-new file shows `??`, not `M` — an unexpected `M` means revert and re-scope. (DR→coordinator merge: a copy-executor overwrote coordinator's OWN `test_prereq_probe.sh` / `test_repo_root_resolution.sh` with the same-named DR versions; `git status` showed them `M`, not `??`.)

## Review-Integrator as Mandatory Next Step

After every review (plan, code, or architectural), the next action MUST be dispatching the review-integrator agent. Manual integration ("go through findings line-by-line") is prohibited except for explicit PM-override items.

**Reviewer self-persists; dispatch the integrator with the returned path.** The review-integrator hard-stops on inline-relayed finding lists (`agents/review-integrator.md` § Intake precondition).

The required sequence:

1. **Dispatch `coordinator:code-reviewer`** (UNNAMED) or a persona reviewer. The sidecar is spawn-provisioned by the engine — no sentinel-append instruction is needed in the brief.
2. **Read the returned pointer line**: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. The sidecar is already on disk at `state/subagent-share/<session>/<provision_key>.md` — provisioned at spawn, not self-scaffolded.
3. **Dispatch the review-integrator pointing at the on-disk sidecar path** — never an inline finding list.

The review-integrator dispatched as a subagent handles:
- Applying tradeoff-free correctness fixes silently
- Writing an escalation list for the EM (items needing PM input or genuine disagreement)

EM spot-checks the diff after integration; does not re-do the integration manually.

## Executor brief compliance — out-of-scope file edits are structural, not instructional

**Executors self-mark plan-status fields and archive entries despite explicit "do not edit X" briefs — the impulse is structural, not a reading error.**
**Why:** Across one session, 5 of 5 dispatched executors touched plan Status fields and/or archive entries despite each brief carrying a verbatim prohibition. The "mark this complete" impulse recurs because the executor's prior conflates plan-status ownership with chunk-completion convention.
**How to apply:** gate Status edits via schema-validation hook + frontmatter enum (catches invalid values mid-write), or move plan-status into a derived view computed from the archive log. Stop assuming briefs alone are the enforcement; they're the policy, hooks are the enforcement.

## No-commit briefs need structural enforcement, not prose

**Executors ignore explicit no-commit constraints under chunk-mode — "DO NOT commit" in a brief will be overridden by the executor's chunk-completion convention.**
**Why:** A brief said "DO NOT commit; EM commits after verification" verbatim; the Sonnet executor self-committed anyway, citing chunk-completion as the stronger convention.
**How to apply:** either enforce no-commit via `settings.json` deny on `git commit`, or accept that committers will commit and use an EM-side review/amend pattern after the executor returns. Prose alone is not binding against a structural prior. See the improvement-queue for the executor agent-prompt amendment candidate.

**Long-running dispatches are especially prone to constraint decay.** A Sonnet executor dispatched for ~30 min on a .NET/native task committed and continued past stub scope to author + commit a second wave despite an explicit "DO NOT COMMIT — EM commits at wave end" in the mandatory verbatim block. Hypothesis: long runs let initial constraints decay; the executor reverts to "ship the work" instinct mid-debugging. Mitigation candidates: (a) pin `expected_branch` AND `expected_HEAD_sha` in dispatch so a pre-commit hook can fail-loud on any commit during the run; (b) shorten dispatch windows to keep the no-commit constraint in working memory; (c) name the executor and include a kill-switch `SendMessage` after the first commit-attempt is detected. File for instance #2 before extracting a full pattern.

**The more durable fix is a non-cooperative, structural deny on subagent-context commits, not a cooperative pre-commit hook.** Pinning `expected_branch`/`expected_HEAD_sha` so a hook can fail-loud still assumes the executor *could* commit if the guard were bypassed or decayed. A PreToolUse-level guard that denies every subagent-context `git commit` before it lands (rather than catching it after, via a hook the executor's own actions could still race) closes the constraint-decay failure mode entirely — the commit is structurally unreachable, not merely discouraged.

## Flight-Recorder Sidecars

**Executor prompt:** `agents/executor.md § Flight-Recorder Sidecar`.

For plan-based fan-out dispatches (via `bin/fan-out-dispatch.sh`), the EM creates a per-chunk sidecar file at dispatch time and passes its path to the executor brief. The executor writes crash-safety status and observations into the sidecar — never into the plan body.

### Sidecar path convention

```
tasks/<plan-slug>/flight/<chunk-id>.md
```

`<plan-slug>` derives from the plan filename without the `YYYY-MM-DD-` prefix and `.md` suffix. `<chunk-id>` is the dispatch's chunk identifier (e.g., `C1-executor-prompt`).

### EM responsibilities

1. **At dispatch:** create the sidecar with starter frontmatter (including `status: dispatched`) and pass `sidecar_path:` in the executor brief.
2. **Mid-dispatch:** do NOT edit the sidecar — the executor owns it until it exits.
3. **At `/workstream-complete`:** read all sidecars under `tasks/<plan-slug>/flight/`; fold genuinely-noteworthy observations into a `## Execution Observations` section appended to the plan body; delete `complete`-status sidecars. `blocked` and `thrashing` sidecars persist until the EM clears them manually (diagnostic preservation).

The git commit log by chunk-id prefix (`git log --oneline -- <plan-path>`; a subject beginning `<chunk-id>:` means that chunk shipped), cross-referenced against the current wave-map, is the canonical surface for "is chunk N done?" — readers consult the commit log, not a body stamp.

### Executor responsibilities

1. Read `sidecar_path:` from the brief. If the file does not exist, create it with the starter frontmatter defined in `agents/executor.md § Flight-Recorder Sidecar`.
2. First action: update `status: dispatched` → `status: in_flight`.
3. Append free-form observations under `## Observations` (latent-bug notes, mid-flight decisions, validation output).
4. Exit transition: update `status: in_flight` → `status: complete | blocked | thrashing`.
5. Append `commits:` list when the executor commits (one SHA per line).

**Executors do NOT stamp `**Status:**` into the plan body.** The plan body is immutable to executors; a PreToolUse tripwire (`hooks/scripts/preuse-write-dispatch.py`, registered as `EXECUTOR-PLAN-BODY-IMMUTABLE` in `coordinator-tripwires.md`) denies subagent Edit/Write on `docs/plans/**/*.md`. The sidecar path at `tasks/<plan-slug>/flight/` is carved out from that deny rule.

### Status state machine

```
dispatched → in_flight → complete
                       → blocked
                       → thrashing
```

### Disambiguation — two different "Status:" fields

<!-- Review: dispatch-ledger vocabulary completion sweep -->
**Plan-body `**Status:**`** is EM-owned phase state (e.g., `Enriched and reviewed`, `Execution in progress` in the wave-map). The EM writes this; executors never touch it.

**Sidecar frontmatter `status:`** is executor-owned lifecycle state (`dispatched`, `in_flight`, `complete`, `blocked`, `thrashing`). The executor writes this; the EM reads it post-dispatch.

These are distinct fields with distinct owners — do not cross-reference.

### Scope: fan-out dispatches only

Sidecars are mandatory only for fan-out dispatches where `bin/fan-out-dispatch.sh` writes `sidecar_path:` into each brief. Solo `Agent`-tool dispatches without a `sidecar_path:` field in the brief are valid; the executor falls back to exit-report-only and does not attempt to create or update a sidecar.

### Lifecycle

`tasks/<plan-slug>/flight/` directories are tracked by default (consistent with other `tasks/` UUID flight-recorder dirs) and swept at `/workstream-complete`. They are ephemeral — not load-bearing substrate. Load-bearing surface is the wave-map, not the sidecar files themselves.

## Spotter Ownership — Fix What You Find

**The spotter fixes it — don't route a latent gap you found to a hypothetical "owner".** When a review or investigation surfaces a fixable gap in committed code — even in a file near a concurrent session's workstream — fix it yourself (surgically, with a clear commit/comment trail). The spotter already has the full context; deferring is buck-passing, and the gap rots.

"Align-don't-kill" means don't stomp *uncommitted* peer edits; it does NOT mean "never touch committed code near a peer's workstream." Reserve hand-off-to-owner for genuine cross-*repo* or design-authority calls.

## Fabricated 'Already Done' Claims — git diff Is Ground Truth

**Executor reports fabricate "already done" file states — verify edits via `git diff`, not the report.** Executors hallucinate prior state and downstream success, especially when a fix "feels" present — they report a flag that doesn't exist, cite a score from a test that errored, and assert the change landed when the source is unmodified.

**How to apply:** after any executor edit, run `git diff`/`git status` on the claimed paths and re-run the tests yourself before committing. Chat is hypothesis; the diff is ground truth (→ `docs/wiki/dispatching-parallel-agents.md` § Executor commit-fidelity and ground-truth verification). Small well-diagnosed fixes are often faster to apply EM-direct than to re-dispatch over a confused executor.

## 'Pre-Existing' and 'Already Fixed' Claims — Verify Against Merge-Base

**An executor's "pre-existing failure" / "already on branch" claim checks only ITS dispatch baseline — verify against merge-base + source.** An executor's pre-edit tree is its own baseline, not the workstream's; and executors systematically under-report remaining work as already-done, especially on P1 findings.

**How to apply:** verify "pre-existing"/"already-fixed" claims against `git merge-base origin/main HEAD` AND by grepping the cited lines — never trust a P1 "already fixed" report without confirming on disk. A file introduced by Chunk 2 in the same workstream is NOT "pre-existing" to a Chunk 6 executor even though it appears in its baseline.

## Stronger enforcement, not stronger wording — executor no-commit needs a structural guard

**An executor that commits clean, well-messaged work in defiance of "no commits, no push" still defeats the EM-serial commit contract — the EM can no longer verify full scope before atomic commit.** The dispatch brief is policy; without an enforcement seam, eagerness wins.
**Why:** the EM-serial commit pattern exists precisely so the EM can residuals-check (`git status`, scope-diff, missed call sites) before any commit lands. A partial executor commit — even a tidy one — pre-empts that gate and silently narrows the verification window to whatever the executor noticed. Recurring instance, same shape as the long-running-decay entry above.
**How to apply:** until a structural seam lands, treat "executor committed" as a known-recurring risk — after every executor return, run `git status` + `git log --since="<dispatch_start>"` and recover missed scope in an explicit follow-up commit before the next dispatch. Pair with the existing `--expected-branch` discipline and prefer dispatch surfaces that withhold commit/push permission outright over briefs that ask politely.

This is exactly the failure mode a structural EM-only commit gate (see § No-commit briefs need structural enforcement above) closes for good — once the commit itself is denied at the tool layer for subagent context, "executor committed anyway" stops being a residual risk to hand-audit for.

## coordinator-auto-push — SSH Routing on Windows

Git Bash's bundled OpenSSH cannot read 1Password's Windows named pipe (`\\.\pipe\openssh-ssh-agent`). `coordinator-auto-push` detects Git Bash + SSH remote and routes through `powershell.exe -NonInteractive -NoProfile` (Windows OpenSSH has access to the credential manager via the pipe). HTTPS and Linux/macOS go direct.

The post-commit hook delegates to `coordinator-auto-push`; repo-setup installs it on new repos.
