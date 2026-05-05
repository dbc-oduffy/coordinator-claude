---
description: Systematic codebase bug hunt — find and fix all AI-fixable bugs in-session, defer blocked ones to backlog
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[path] [--codex-verify]"
---

# Bug Sweep — Systematic Codebase Bug Hunt

Sweep the codebase for bug patterns, fix everything AI-fixable in-session, defer human-dependent bugs to the backlog. Not a daily check — use when code churn warrants it.

**This command occupies your context for ~20-40 min. It is not background work.**

**Not for:** Recent-commit review (use daily-code-health), architectural debt (use weekly-architecture-audit), or single known bugs (just fix them).

## Arguments

`$ARGUMENTS` is an optional path to scope the sweep. If omitted, the full codebase is scanned.

`--codex-verify` — after fixes are committed, run a Codex review on the diff as a second-opinion check from a different model family. **Opt-in add-on, off by default.** Requires the bundled `codex-review-gate` skill (added via `setup/install.sh --enable-codex`) AND the external Codex CLI installed and authenticated (`/codex:setup`). If `--codex-verify` is passed but the skill is not installed, report _"--codex-verify ignored: codex-review-gate skill not installed (re-run setup with --enable-codex)"_ and proceed without the verification step.

Announce: "I'm running `/bug-sweep` — systematic bug hunt [scoped to X / across the full codebase][, with Codex verification]."

## Phase 0: Scope and Pattern Selection (~5 min, YOU do this)

1. **Detect project stack:**
   ```bash
   # Language detection
   find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.cpp" -o -name "*.h" | head -20
   # Test framework detection
   ls -d tests/ __tests__/ spec/ test/ 2>/dev/null
   # Config files
   ls pytest.ini pyproject.toml jest.config.* tsconfig.json CMakeLists.txt 2>/dev/null
   ```

   **Docs verification flag:** Set `DOCS_VERIFY = true` when the stack is a compiled language or large opinionated framework where Claude's API knowledge is imperfect and "compiles" does not imply "as documented". Canonical examples: Unreal Engine, C++, C#, Unity, Godot, Java/Spring, Rust. Canonical non-examples: TypeScript, JavaScript, Python — training data is dense and hallucinations rare for common APIs. When in doubt, lean toward enabling it: the cost is a few extra agents, the cost of a missed hallucinated API is a confusing compile failure or silent wrong behavior. This flag enables Track C in Phase 1 and makes Phase 3.5 mandatory.

2. **Select patterns** from the Pattern Library (end of this document) based on detected stack. Universal patterns always apply. Language-specific patterns apply per detected language.

3. **Define search chunks** — split codebase into 3-6 chunks by directory/system. If architecture atlas exists (`tasks/architecture-atlas/systems-index.md`), use its system boundaries. Otherwise, derive from `DIRECTORY.md` or directory structure.

4. **Check test suite** — identify the test runner and prepare to run it in Phase 1.

5. **Read `tasks/lessons.md`** (if exists) for project-specific gotchas to add as patterns.

6. **Generate run ID** — format: `YYYY-MM-DD-HHhMM` (current timestamp). Create scratch directory: `tasks/scratch/bug-sweep/{run-id}/`

7. **Output:** Chunk table with pattern assignments + test runner command.

## Pre-Dispatch: Verify Backlog Against Current Code (geneva T1.1, single landing across 3 files)

**Before dispatching any Phase 1 agents, verify that known backlog items are still applicable.**

If this sweep is re-running against a prior bug backlog (`tasks/bug-backlog.md`), dispatch one Haiku agent per system to check each open item before Phase 1 begins:

1. Read each cited file:line — does the bug pattern still exist in HEAD?
2. Check recent history — `git log --oneline -5 {file}` to see if recent commits addressed it
3. Return a `still-open` / `already-fixed` verdict per item

Drop `already-fixed` items from the dispatch queue before any Phase 1 agents are launched.

**Why verify first:** In one measured run, 11 of 20 backlog items were already fixed before dispatch — fixes landed through other workstreams without updating the tracker. Dispatching agents on ghost debt wastes time and produces false findings.

**P0/P1 verification gate** (fifa T1.5, paired with E1.6): Before fixing any item that is or will be classified P0 or P1, the EM (or a verifier subagent) must read the cited code and confirm the claim against current source — not the agent's paraphrase. Bug-sweep Sonnet agents have a 100% false positive rate on P0 claims in their 2026-03-19 sweep. P2 and lower-confidence findings had a much better hit rate (~60%).

## Phase 1: Search + Test (dispatch leaf agents, parallel)

**Three parallel tracks:**

### Track A1 — Mechanical Pattern Grep (YOU do this, fast)

Run deterministic grep searches across all chunks via Bash. These are pattern-library entries found with regex — no LLM needed:
- `TODO`, `FIXME`, `HACK`, `XXX`, `BUG` comments
- Empty catch/except blocks
- Language-specific mechanical patterns (bare `except:`, `== null`, etc.)

This is fast (<30 seconds) and produces a grep findings list that feeds into Track A2 as context.

### Track A2 — Semantic Analysis (dispatch one Sonnet per chunk)

Dispatch one agent per chunk with `model: "sonnet"`. Each agent receives its chunk's file list, assigned patterns, AND the Track A1 grep results for its chunk. For each file:
- Review grep findings for false positives (intentional catch-and-ignore, etc.)
- Run deeper semantic analysis (error handling gaps, potential null access, resource leaks, logic errors, dead code paths, race conditions)
- For each finding: severity (P0/P1/P2), confidence (HIGH/MEDIUM/LOW), file:line, description, and whether it's AI-fixable or needs human verification
- **Include code smells alongside bugs.** Confusing names, structural issues, dead code, mutation footguns — these are all findings worth reporting. Do NOT invent a P3 or "info" tier to downgrade them.

**Agent prompt must instruct:** "Cast a wide net. Report bugs AND code smells — both are worth fixing. Err on the side of reporting — false positives are cheap, missed issues are expensive. Use P0/P1/P2 severity ONLY — do not invent P3, 'info', or 'defer' tiers. A code smell that can be fixed in under 5 minutes is P2, not 'informational'. Write your complete findings to `{scratch-path}` using the Write tool. Return only a brief summary (finding count, any blockers) — the coordinator reads full output from disk."

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1-sonnet.md`

### Track B — Test Suite (dispatch one Haiku agent)

Dispatch one agent with `model: "haiku"`. Run the test suite (`pytest`, `jest`, `npm test`, `cargo test`, etc.). Capture pass/fail/error counts. For each failure: extract the error, test file:line, and likely source.

If no test suite exists, report that fact and skip.

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/tests-phase1-haiku.md`

### Track C — API Documentation Verification (`DOCS_VERIFY = true` stacks only)

Dispatch one `coordinator:docs-checker` agent per chunk with `model: "sonnet"`. Each agent receives the source files for its chunk. The agent:
- Scans all external API references (class names, function signatures, header includes, Blueprint nodes, UPROPERTY/UFUNCTION specifiers, enum values, SDK calls)
- Verifies each against holodeck-docs (UE APIs) or Context7 (non-UE libraries)
- Returns a structured Docs Verification Report

**Rationale:** For compiled languages and large opinionated frameworks (UE, Unity, C#, C++, etc.), Claude's API knowledge is imperfect — wrong header paths, nonexistent methods, and incorrect signatures can exist silently in codebases because they may still compile or because the error is deferred to link time. Unlike TypeScript/Python where training data is dense, these stacks are precisely where "looks right" and "is right per the docs" diverge. Track C surfaces API bugs at the same triage priority as functional bugs.

**Feeding into triage:**
- `INCORRECT` findings (docs contradict the code) → P1 bug finding: "API incorrect per holodeck-docs: [detail]"
- `UNVERIFIED` findings where the symbol follows UE naming conventions but has zero RAG hits → P2 finding: "Possible hallucinated API — zero docs hits"
- `UNVERIFIED` due to server unavailability → drop (not actionable)

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1-docschecker.md`

### Scratch Verification

Before proceeding to Phase 2, verify all expected scratch files exist (`ls tasks/scratch/bug-sweep/{run-id}/`). If any chunk agent failed to write, re-dispatch once. If it fails again, proceed with available findings.

## Phase 2: Triage (~5 min, YOU do this)

Read all Phase 1 findings from `tasks/scratch/bug-sweep/{run-id}/`. When `DOCS_VERIFY = true`, this includes Track C docs-checker reports — merge their INCORRECT and suspicious-UNVERIFIED findings into the main finding list before categorizing.

### Step 2.1: Categorize

1. **Fix now** — the default. If the bug OR smell is clear and the fix is clear, fix it:
   - Missing error handling, dead code, swallowed exceptions, failed tests with obvious cause, straightforward TODO/FIXME items
   - Code smells: confusing names, mid-file imports, in-place mutation footguns, O(n) where O(1) exists, per-call allocations that should be cached, double-checked locking bugs, dead parameters

2. **Backlog** — only for genuinely blocked bugs:
   - Needs human verification, needs a plan session, logic that might be intentional and requires PM judgment
   - **NOT for:** "low confidence" findings — verify them and either fix or drop. NOT for "code smells" — those are fixable. NOT for anything you could fix in under 10 minutes.

3. **False positive** — pattern matched but not a bug:
   - Intentional patterns, comments/docs that mention bug patterns

**Bias toward fixing.** Same effort to fix a small bug as to document it. If you can fix it safely, fix it. **Code smells are fixable by definition** — they never belong in backlog. The only valid reasons to backlog are: (a) needs human judgment about intent, (b) fix requires a plan session due to scope, (c) blocked by external dependency.

**Deduplication:** Multiple agents may find the same cross-system issue. Merge duplicates.

**Output:** Two lists — "Fix now" and "Backlog" — grouped by file for efficient executor dispatch.

### Step 2.2: Capture Pre-Fix Baseline

If `--codex-verify` was passed AND the `codex-review-gate` skill is installed, capture the current HEAD before any fixes are applied:

```bash
PRE_FIX_REF=$(git rev-parse HEAD)
```

This ref is used in Phase 4.5 as the diff base for Codex review.

## Phase 3: Fix (dispatch Sonnet executors, parallel)

Dispatch Sonnet executors with `model: "sonnet"` to fix all "fix now" items. Group fixes by file/system to minimize conflicts.

Each executor receives:
- The finding list for its file group
- The source files to modify
- Clear acceptance criteria per fix

**Agent prompt must instruct:** "Fix the listed bugs. For each fix, verify the fix is correct by reading the result. Write a brief summary of changes to `{scratch-path}` using the Write tool."

**Post-fix:** Run the test suite again to verify fixes don't introduce regressions. If any test fails that wasn't failing before, revert that fix and move the finding to backlog with "regression introduced."

## Phase 3.5: Post-Fix API Verification (YOU do this)

Before committing any fixes, run docs-checker on the changed files to verify that the fixes themselves don't introduce hallucinated or incorrect API usage.

**Mandatory when `DOCS_VERIFY = true` (compiled/framework-heavy stacks). Recommended for any project where fixes reference external library APIs.**

1. **Identify changed files:**
   ```bash
   git diff --name-only
   ```

2. **Dispatch docs-checker:**
   Dispatch one `coordinator:docs-checker` agent against the set of changed files. Brief it: "Verify all external API claims in these modified files. Focus on claims that appear to be new or changed relative to common patterns. Report INCORRECT and suspicious-UNVERIFIED findings only — skip VERIFIED."

3. **Assess the result:**
   - **No INCORRECT findings:** Proceed to Phase 4.
   - **INCORRECT findings in a fix:** Revert that specific fix (`git checkout -- {file}`) and move the finding to backlog with note `"docs-checker: incorrect API in proposed fix — [detail]"`. The original bug remains open; the fix needs rework.
   - **UNVERIFIED with zero-hit UE naming pattern:** Flag to PM. Don't block — but note it in the Phase 4 report.

**Phase 3.5 does NOT re-run the full sweep.** It reads only the changed files, verifying that executor agents didn't introduce new API errors while fixing existing bugs.

## Phase 4: Report and Commit (YOU do this)

1. **Commit fixes:**
   ```bash
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "bug-sweep: fixed N bugs across M files"
   ```

2. **Update bug backlog** (`tasks/bug-backlog.md`) — only if there are genuinely blocked items:

   Header format:
   ```markdown
   # Bug Backlog

   > Last sweep: YYYY-MM-DD | Commit at sweep: [short hash] | Open: N items (P0: X, P1: Y, P2: Z)
   > Next sweep suggested: when code churn warrants it — workday-start tracks this

   | ID | System | Severity | Description | Why Blocked | Found | Cross-ref |
   |----|--------|----------|-------------|-------------|-------|-----------|
   ```

   ID format: `BS-{date}-{N}`. Cross-reference with `tasks/debt-backlog.md` if overlap exists.

   If no blocked items, update just the header line (last sweep date, commit hash, zero counts).

3. **Report to PM:**
   ```markdown
   ## Bug Sweep Complete

   **Scope:** [N] systems, [M] files scanned
   **Patterns applied:** [list]
   **Tests run:** [pass/fail/error counts]
   **Found:** [total] findings ([X] fixed, [Y] blocked, [Z] false positives)
   **Fixes applied:** [list with file:line refs]
   **Blocked items:** [list with "why blocked" for each, or "none"]
   **Docs verification (Phase 3.5):** [clean / N incorrect API claims in fixes reverted / skipped: not C++/UE and no external APIs touched]
   **Track C API sweep:** [N INCORRECT API findings fixed, N suspicious-UNVERIFIED flagged / skipped: `DOCS_VERIFY` not set for this stack]
   <!-- include only when --codex-verify was passed AND codex-review-gate skill is installed -->
   **Codex second opinion:** [N findings / clean / skipped: {reason} / not requested]
   ```

4. **Clean scratch:** `rm -rf tasks/scratch/bug-sweep/{run-id}/`
   Only delete after commit succeeds. If Phase 2/3 agents failed, scratch contains Phase 1 findings for recovery.

## Phase 4.5: Codex Verification (optional — `--codex-verify` only, opt-in add-on)

**Skip this entire phase unless BOTH `--codex-verify` was passed AND the `codex-review-gate` skill is installed.** If `--codex-verify` was passed but the skill is missing, the user was already told at Phase 0 announcement; proceed to Pattern Library without writing a `Codex second opinion:` line in the report.

If both conditions hold, run an independent-model review of the fixes via the Codex plugin. This gives a second opinion from a different model family (GPT-5.4) on whether the fixes are correct.

1. **Run Codex review:**
   Invoke `/codex:rescue` with: "Review the diff between {PRE_FIX_REF} and HEAD for code quality issues, bugs, and security vulnerabilities. Focus on P0/P1 findings. Return structured findings."

2. **Assess result by exit code:**
   - **Exit code 0 (success):** Append Codex findings to the Phase 4 report under a `## Codex Second Opinion` heading. If Codex found issues not caught by the Claude sweep, add them to the backlog — do NOT auto-fix Codex findings, report them for PM triage.
   - **Non-zero exit code (failure):** Report: _"Codex verification skipped: {reason from output/stderr}."_ Continue — this is non-blocking.

3. **Update the report:**
   Add to the Phase 4 report:
   ```
   **Codex second opinion:** [N findings / clean / skipped: {reason}]
   ```

If `--codex-verify` was not passed AND the `codex-review-gate` skill IS installed, add to the report:
```
**Codex second opinion:** not requested
```

If the skill is not installed at all, omit the `Codex second opinion:` line entirely from the report — default installs never mention Codex.

## Pattern Library, Cost Profile, Failure Modes

See `pipelines/bug-sweep/pattern-library.md` for the full pattern catalog (universal + per-language: Python, JS/TS, C++/UE, code smells), the cost profile table (small/medium/large repo agent counts and wall-clock estimates incl. `DOCS_VERIFY` overhead), and the full failure-modes prevention matrix.
