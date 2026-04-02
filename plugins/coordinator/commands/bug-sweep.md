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

`--codex-verify` — after fixes are committed, run a Codex review on the diff as a second-opinion check from a different model family. Optional; off by default. Requires Codex CLI installed and authenticated (`/codex:setup`).

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

2. **Select patterns** from the Pattern Library (end of this document) based on detected stack. Universal patterns always apply. Language-specific patterns apply per detected language.

3. **Define search chunks** — split codebase into 3-6 chunks by directory/system. If architecture atlas exists (`tasks/architecture-atlas/systems-index.md`), use its system boundaries. Otherwise, derive from `DIRECTORY.md` or directory structure.

4. **Check test suite** — identify the test runner and prepare to run it in Phase 1.

5. **Read `tasks/lessons.md`** (if exists) for project-specific gotchas to add as patterns.

6. **Generate run ID** — format: `YYYY-MM-DD-HHhMM` (current timestamp). Create scratch directory: `tasks/scratch/bug-sweep/{run-id}/`

7. **Output:** Chunk table with pattern assignments + test runner command.

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

**Agent prompt must instruct:** "Cast a wide net. Report everything that looks like a bug, even if only moderately confident. Err on the side of reporting — false positives are cheap, missed bugs are expensive. Write your complete findings to `{scratch-path}` using the Write tool. Return only a brief summary (finding count, any blockers) — the coordinator reads full output from disk."

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1-sonnet.md`

### Track B — Test Suite (dispatch one Haiku agent)

Dispatch one agent with `model: "haiku"`. Run the test suite (`pytest`, `jest`, `npm test`, `cargo test`, etc.). Capture pass/fail/error counts. For each failure: extract the error, test file:line, and likely source.

If no test suite exists, report that fact and skip.

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/tests-phase1-haiku.md`

### Scratch Verification

Before proceeding to Phase 2, verify all expected scratch files exist (`ls tasks/scratch/bug-sweep/{run-id}/`). If any chunk agent failed to write, re-dispatch once. If it fails again, proceed with available findings.

## Phase 2: Triage (~5 min, YOU do this)

Read all Phase 1 findings from `tasks/scratch/bug-sweep/{run-id}/`.

### Step 2.0: Verify Findings Against Current Code

Dispatch one Haiku agent per chunk with `model: "haiku"`. Each agent receives the findings for its chunk and:
1. Reads each cited file:line — does the code the agent described actually exist there?
2. Checks recent history — `git log --oneline -5 {file}` to see if recent commits addressed it
3. Returns a verified/stale verdict per finding

Drop all stale findings before categorizing.

### Step 2.1: Categorize

1. **Fix now** — the default. If the bug is clear and the fix is clear, fix it:
   - Missing error handling, dead code, swallowed exceptions, failed tests with obvious cause, straightforward TODO/FIXME items

2. **Backlog** — only for genuinely blocked bugs:
   - Needs human verification, needs a plan session, logic that might be intentional and requires PM judgment

3. **False positive** — pattern matched but not a bug:
   - Intentional patterns, comments/docs that mention bug patterns

**Bias toward fixing.** Same effort to fix a small bug as to document it. If you can fix it safely, fix it.

**Deduplication:** Multiple agents may find the same cross-system issue. Merge duplicates.

**Output:** Two lists — "Fix now" and "Backlog" — grouped by file for efficient executor dispatch.

### Step 2.2: Capture Pre-Fix Baseline

If `--codex-verify` was passed, capture the current HEAD before any fixes are applied:

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

## Phase 4: Report and Commit (YOU do this)

1. **Commit fixes:**
   ```bash
   git add -A
   git commit -m "bug-sweep: fixed N bugs across M files"
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
   **Codex second opinion:** [N findings / clean / skipped: {reason} / not requested]
   ```

4. **Clean scratch:** `rm -rf tasks/scratch/bug-sweep/{run-id}/`
   Only delete after commit succeeds. If Phase 2/3 agents failed, scratch contains Phase 1 findings for recovery.

## Phase 4.5: Codex Verification (optional — `--codex-verify` only)

If `--codex-verify` was passed, run an independent-model review of the fixes via the Codex plugin. This gives a second opinion from a different model family (GPT-5.4) on whether the fixes are correct.

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

If `--codex-verify` was not passed, add to the report:
```
**Codex second opinion:** not requested
```

## Pattern Library

### Bug Patterns — Universal (all languages)

- `TODO`, `FIXME`, `HACK`, `XXX`, `BUG` comments — potential deferred bugs
- Empty catch/except blocks — swallowed errors
- Unreachable code after return/throw/raise

### Bug Patterns — Python

- Bare `except:` without exception type
- `except Exception as e: pass` — swallowed
- Mutable default arguments (`def f(x=[])`)
- `is` comparison with literals (should be `==`)
- Missing `await` on async calls

### Bug Patterns — JavaScript/TypeScript

- Unhandled promise rejections (`.then()` without `.catch()`)
- Missing `key` prop in React lists

### Bug Patterns — C++/Unreal

- Raw `new` without matching `delete` (memory leak)
- Missing `nullptr` checks after `Cast<>()` or `FindObject()`
- `UPROPERTY()` missing on UObject pointers (GC won't track them)
- Missing `Super::` calls in overridden lifecycle functions

### Structural Patterns (OFF by default)

Include only if PM explicitly requests a broader sweep: `== null` vs `=== null`, `var` vs `let`/`const`, `any` types, functions >200 lines, duplicated code, `FString` concat in hot loops.

## Cost Profile

| Scenario | Sonnet Agents | Executors | Wall-Clock |
|----------|---------------|-----------|------------|
| Small repo, 3 systems | 4 (3 search + 1 test) | 2-3 | ~15-25 min |
| Medium repo, 6 systems | 7 (6 search + 1 test) | 3-5 | ~25-40 min |
| Large repo, 8+ systems | 9+ | 4-6 | ~35-50 min |

## Failure Modes

| Failure | Prevention |
|---------|------------|
| False positive flood | Phase 2 triage with explicit "false positive" category |
| Fix introduces regression | Post-fix test suite run; revert and defer if new failures |
| Sonnet over-reports low-confidence issues | Filter by confidence; LOW → backlog |
| Pattern library misses project-specific bugs | Phase 0 reads `tasks/lessons.md` for known gotchas |
| Test suite doesn't exist | Report the gap, sweep code-only |
| Executor fix conflicts across files | Group fixes by file/system |
| Executor agent failure | Re-dispatch once. Second failure → move finding to backlog with `fix-blocked: agent failure`. Keep scratch files for manual review. |
