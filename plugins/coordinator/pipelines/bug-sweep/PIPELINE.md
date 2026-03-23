# Bug Sweep — Systematic Codebase Bug Hunt

> Referenced by `/bug-sweep`. This is a pipeline definition, not an invocable skill.

## Overview

A dedicated operation that sweeps the entire codebase for bug patterns, fixes everything AI-fixable in-session, and defers human-dependent bugs to the bug backlog. Not a daily check — use irregularly when code churn warrants it.

**Announce at start:** "I'm using /bug-sweep to sweep the codebase for bugs."

## When to Use

- When the PM or EM decides it's time for a bug hunt (not on a fixed schedule)
- After major merges or dependency updates
- When the bug backlog has been empty for a while and it's time to sweep again
- When test failures accumulate and need systematic attention
- Suggestion from workday-start: "No bug sweep in 30+ days. Consider running one."

**Not for:** Recent-commit review (use daily-code-health), architectural debt (use weekly-architecture-audit), or single known bugs (just fix them).

## The Process

### Phase 0: Scope and Pattern Selection (Coordinator, ~5 min)

1. **Detect project stack** — scan for language files, test frameworks, build systems:
   ```bash
   # Language detection
   find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.cpp" -o -name "*.h" | head -20
   # Test framework detection
   ls -d tests/ __tests__/ spec/ test/ 2>/dev/null
   # Config files
   ls pytest.ini pyproject.toml jest.config.* tsconfig.json CMakeLists.txt 2>/dev/null
   ```

2. **Select patterns** from the Pattern Library (below) based on detected stack. Universal patterns always apply. Language-specific patterns apply per detected language.

3. **Define search chunks** — split codebase into 3-6 chunks by directory/system. If architecture atlas exists (`tasks/architecture-atlas/systems-index.md`), use its system boundaries. Otherwise, derive from `DIRECTORY.md` or directory structure.

4. **Check test suite** — identify the test runner and prepare to run it in Phase 1.

5. **Read `tasks/lessons.md`** (if exists) for project-specific gotchas to add as patterns.

6. **Generate run ID** — format: `YYYY-MM-DD-HHhMM` (current timestamp). This identifies the scratch directory: `tasks/scratch/bug-sweep/{run-id}/`

7. **Output:** Chunk table with pattern assignments + test runner command.

### Phase 1: Search + Test (Sonnet agents, parallel)

**Two parallel tracks:**

#### Track A1 — Mechanical Pattern Grep (Coordinator, fast)

Before dispatching Sonnet agents, the coordinator runs deterministic grep searches across all chunks simultaneously via Bash. These are pattern-library entries that can be found with regex — no LLM needed:
- `TODO`, `FIXME`, `HACK`, `XXX`, `BUG` comments
- Empty catch/except blocks
- Language-specific mechanical patterns (bare `except:`, `== null`, etc.)

This is fast (<30 seconds) and produces a grep findings list that feeds into Track A2 as context.

#### Track A2 — Semantic Analysis (one Sonnet per chunk)

Each agent receives its chunk's file list, assigned patterns, AND the Track A1 grep results for its chunk. For each file:
- Review grep findings for false positives (intentional catch-and-ignore, etc.)
- Run deeper semantic analysis (LLM reads the code and identifies: error handling gaps, potential null access, resource leaks, logic errors, dead code paths, race conditions)
- For each finding: severity (P0/P1/P2), confidence (HIGH/MEDIUM/LOW), file:line, description, and whether it's AI-fixable or needs human verification

**Write-to-disk:** Each agent writes its complete findings to `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1-sonnet.md` using the Write tool. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) The agent returns a brief summary (3-5 lines) to the coordinator: file written, finding count, any blockers. The coordinator reads full output from disk — agents do NOT return it in conversation.

#### Track B — Test Suite (one Haiku agent)

**Why Haiku:** Running a test command and capturing stdout is mechanical work — no semantic judgment needed. The coordinator triages the results.

- Run the test suite: `pytest`, `jest`, `npm test`, `cargo test`, etc.
- Capture results: which tests passed, which failed, which errored
- For each failure: extract the error, the test file:line, and the likely source of the bug
- If no test suite exists, report that fact and skip

**Write-to-disk:** The test agent writes its complete results to `tasks/scratch/bug-sweep/{run-id}/tests-phase1-haiku.md` using the Write tool. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) Returns a brief summary (pass/fail counts, notable failures) to the coordinator. Full output read from disk.

**Key instruction for all Phase 1 agents:** "Cast a wide net. Report everything that looks like a bug, even if you're only moderately confident. The coordinator will triage. Err on the side of reporting — false positives are cheap, missed bugs are expensive."

**Output:** Per-chunk finding lists + test results.

**Scratch verification:** Before proceeding to Phase 2, verify all expected scratch files exist (`ls tasks/scratch/bug-sweep/{run-id}/`). If any chunk agent failed to write, re-dispatch once. If it fails again, proceed with available findings — the triage will cover fewer chunks but should not stall.

### Phase 2: Triage (Coordinator, ~5 min)

The coordinator reads all Phase 1 findings from `tasks/scratch/bug-sweep/{run-id}/` and categorizes.

#### Step 2.0: Verify Findings Against Current Code

Before categorizing, verify that each P1/HIGH-confidence finding actually exists in the current code. Phase 1 agents demonstrably hallucinate bugs that were fixed by prior sweeps or that never existed.

**Method:** Dispatch a Haiku agent per chunk with `model: haiku`. This is mechanical read-and-confirm work — no judgment needed. Each agent receives the findings for its chunk and:

1. **Reads each cited file:line** — does the code the agent described actually exist there?
2. **Checks recent history** — `git log --oneline -5 {file}` to see if recent commits addressed it
3. **Returns a verified/stale verdict per finding** — findings where the bug no longer exists are marked "already fixed"

Drop all stale findings before proceeding to categorization. This step is fast (< 2 minutes) and prevents wasted executor dispatches on ghost bugs.

#### Step 2.1: Categorize

1. **Fix now** — the default. If the bug is clear and the fix is clear, just fix it. This includes:
   - Missing error handling (add it)
   - Dead code (remove it)
   - Swallowed exceptions (add logging or re-raise)
   - Failed tests with obvious cause
   - TODO/FIXME items that are straightforward
   - Small scoping decisions the EM can make (e.g., "keep this Unix-only and fix the bash bugs")

2. **Backlog** — only for bugs that genuinely can't be fixed in-session:
   - Needs human verification (manual testing, visual check, play-testing)
   - Needs a plan session (fix is large enough that getting it wrong would be expensive to undo)
   - Logic that might be intentional and requires PM judgment

3. **False positive** — pattern matched but it's not actually a bug:
   - Intentional patterns (e.g., catch-and-ignore for expected errors)
   - Comments/docs that mention bug patterns but aren't code

**Bias toward fixing.** It's roughly the same effort to fix a small bug as to document it in a backlog. If you can fix it safely, fix it — don't create backlog entries for things you could have just done. The backlog exists for genuinely blocked items, not as a parking lot.

**Deduplication:** Multiple agents may find the same cross-system issue. Merge duplicates, keep the most detailed description.

**Output:** Two lists — "Fix now" and "Backlog" — with findings grouped by file for efficient executor dispatch.

### Phase 3: Fix (Executor agents, parallel)

Dispatch Sonnet executors to fix all "AI-fixable NOW" items. Group fixes by file/system to minimize merge conflicts.

Each executor receives:
- The finding list for its file group
- The source files to modify
- Clear acceptance criteria per fix

**Post-fix:** Run the test suite again to verify fixes don't introduce regressions. If any test fails that wasn't failing before, revert that fix and move the finding to "Needs human verification."

### Phase 4: Report and Commit (Coordinator)

1. **Commit fixes:**
   ```bash
   git add -A
   git commit -m "bug-sweep: fixed N bugs across M files"
   ```

2. **Update bug backlog** (only if there are genuinely blocked items) — `tasks/bug-backlog.md`:

   If the file doesn't exist and there are blocked items, create it:

   ```markdown
   # Bug Backlog

   > Last sweep: YYYY-MM-DD | Commit at sweep: [short hash] | Open: N items
   > Next sweep suggested: when code churn warrants it — workday-start tracks this

   | ID | System | Severity | Description | Why Blocked | Found | Cross-ref |
   |----|--------|----------|-------------|-------------|-------|-----------|
   ```

   ID format: `BS-{date}-{N}`. Only genuinely blocked bugs go here — things needing human verification or a plan session. Fixed bugs belong in the git history, not the backlog. Remove entries when resolved; don't mark them "fixed" and leave them.

   **Cross-referencing:** Before adding a new entry, check `tasks/debt-backlog.md` for existing items affecting the same files. If overlap exists, populate the `Cross-ref` field on both entries (e.g., `Cross-ref: WAA-2026-03-19-1`). This prevents dual-tracking the same issue.

3. **Report to PM:**
   ```markdown
   ## Bug Sweep Complete

   **Scope:** [N] systems, [M] files scanned
   **Patterns applied:** [list]
   **Tests run:** [pass/fail/error counts]
   **Found:** [total] findings ([X] fixed, [Y] blocked, [Z] false positives)
   **Fixes applied:** [list with file:line refs]
   **Blocked items:** [list with "why blocked" for each, or "none"]
   ```

4. **Triage scratch files:** Delete all scratch files — findings are fully consumed by the triage and fix phases.

   **Recovery on failure:** If a Phase 2/3 agent fails, the scratch directory contains the completed Phase 1 findings. Re-dispatching the failed phase will read from the existing scratch files — do NOT delete the scratch directory until all phases complete successfully. Only delete after Phase 4 commit succeeds.
   ```bash
   rm -rf tasks/scratch/bug-sweep/{run-id}/
   ```

## Pattern Library

Patterns are split into **bug patterns** (correctness issues — the core of bug-sweep) and **structural patterns** (style/debt — these belong to daily-code-health and weekly-architecture-audit). Bug-sweep uses only bug patterns by default. The PM can request structural patterns be included for a broader sweep.

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
- Missing `key` prop in React lists (causes rendering bugs)

### Bug Patterns — C++/Unreal

- Raw `new` without matching `delete` (memory leak)
- Missing `nullptr` checks after `Cast<>()` or `FindObject()`
- `UPROPERTY()` missing on UObject pointers (GC won't track them)
- Missing `Super::` calls in overridden lifecycle functions

### Structural Patterns (OFF by default)

These belong to daily-code-health / weekly-architecture-audit. Include only if the PM explicitly requests a broader sweep.

- `== null` instead of `=== null` (style, but rarely a runtime bug)
- `var` instead of `let`/`const` (style)
- `any` type annotations (type safety gap, not a bug)
- Functions >200 lines (complexity smell, not a bug)
- Duplicated code blocks (divergence risk, not a bug)
- `FString` concatenation in hot loops (performance, not correctness)

**Note:** This library grows over time. The coordinator may discover project-specific patterns during Phase 0 (e.g., reading `tasks/lessons.md` for known gotchas) and add them to the pattern set for that sweep.

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
| Sonnet over-reports low-confidence issues | Coordinator filters by confidence; LOW → human-dependent backlog |
| Pattern library misses project-specific bugs | Phase 0 reads `tasks/lessons.md` for known gotchas |
| Test suite doesn't exist | Report the gap, suggest adding tests, sweep code-only |
| Executor fix conflicts across files | Group fixes by file/system to minimize overlap |
| Executor agent failure in Phase 3 (Sonnet executor crashes mid-fix) | Agent crash, context limit, or 529 overload during fix dispatch | Re-dispatch once. If second failure, move the affected finding from "fix-now" to backlog with status `fix-blocked: agent failure`. Do NOT delete scratch files — Phase 1 findings remain there for manual review or future resumption. |
