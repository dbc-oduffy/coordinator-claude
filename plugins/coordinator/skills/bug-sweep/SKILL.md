---
name: bug-sweep
description: Systematic codebase bug hunt — find and fix all AI-fixable bugs in-session, defer blocked ones to backlog
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[path]"
---

# Bug Sweep — Systematic Codebase Bug Hunt

Sweep the codebase for bug patterns, fix everything AI-fixable in-session, defer human-dependent bugs to the backlog. Not a daily check — use when code churn warrants it.

**This command occupies your context for ~20-40 min. It is not background work.**

**Not for:** Recent-commit review (use daily-code-health), architectural debt (use weekly-architecture-audit), or single known bugs (just fix them).

## Arguments

`$ARGUMENTS` is an optional path to scope the sweep. If omitted, the full codebase is scanned.

Announce: "I'm running `/bug-sweep` — systematic bug hunt [scoped to X / across the full codebase]."

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

3. **Define search chunks** — split codebase into 3-6 chunks by directory/system. If architecture atlas exists (`docs/architecture/systems-index.md`), use its system boundaries. Otherwise, derive from `DIRECTORY.md` or directory structure.

4. **Hot-zone identification — rank chunks by recent bugfix density (YOU do this):**

   ```bash
   "$HOME/.claude/plugins/coordinator/bin/query-completions.sh" --since "30d" --where "nature=bugfix" --format json
   ```

   Aggregate results by file-path-prefix or chain to identify which subsystems have the highest recent bugfix traffic. Chunks covering high-density paths rank first in Phase 1 dispatch order — they are statistically more likely to contain latent follow-on bugs.

   **Cooldown filter:** also note any paths with a `nature: bugfix` completion in the last 7 days. These areas were just touched; deprioritize them in the dispatch queue to avoid redundant re-sweep of freshly-fixed ground. When cooldown paths overlap with hot-zone paths, surface the conflict explicitly: "Path X is both a hot zone (N bugfixes/30d) and recently cooled (fixed Y days ago) — sweep at P2 priority."

   Record the ranked chunk order and any cooldown exclusions in the run scratch directory: `tasks/scratch/bug-sweep/{run-id}/hot-zone-ranking.md`. Phase 1 agent dispatch brief cites this file for ordering rationale.

   If `query-completions` returns no results (empty log or Phase 1 not yet shipped), skip ranking and proceed with default directory-order chunks.

5. **Check test suite** — identify the test runner and prepare to run it in Phase 1.

6. **Read `tasks/lessons.md`** (if exists) for project-specific gotchas to add as patterns.

7. **Generate run ID** — format: `YYYY-MM-DD-HHhMM` (current timestamp). Create scratch directory: `tasks/scratch/bug-sweep/{run-id}/`

8. **Output:** Chunk table with pattern assignments, hot-zone ranking (from step 4), and test runner command.

## Pre-Dispatch: Verify Backlog Against Current Code (geneva T1.1, single landing across 3 files)

**Before dispatching any Phase 1 agents, verify that known backlog items are still applicable.**

If this sweep is re-running against a prior bug backlog (`tasks/bug-backlog.md`), dispatch one Haiku agent per system to check each open item before Phase 1 begins:

1. Read each cited file:line — does the bug pattern still exist in HEAD?
2. Check recent history — `git log --oneline -5 {file}` to see if recent commits addressed it
3. Return a `still-open` / `already-fixed` verdict per item, **with the resolving commit SHA cited for each `already-fixed`** (from the `git log` check in step 2 — `--first-parent` on the cited file is enough; if no clear single SHA, cite the range or `unattributed`).

Drop `already-fixed` items from the dispatch queue before any Phase 1 agents are launched. **Record the verified-fixed IDs + their resolving SHAs** to `tasks/scratch/bug-sweep/{run-id}/pre-dispatch-already-fixed.md` — Phase 4 reads this file to prune the backlog.

**Why verify first:** In one measured run, 11 of 20 backlog items were already fixed before dispatch — fixes landed through other workstreams without updating the tracker. Dispatching agents on ghost debt wastes time and produces false findings.

**Concurrent-EM windows can invert stale/fixed mid-pipeline — escalate verifier to Sonnet.** *2026-05-18, claude-unreal-holodeck.* When the verifier was a Haiku and the bug-sweep ran during active concurrent-EM activity, two failure shapes emerged: (a) a bug was verified `still-open` at Phase 0.5, fixed by a concurrent EM 90 seconds later, then a Phase 1 dispatcher fired a duplicate fix; (b) a bug was verified `already-fixed` citing SHA X, but SHA X had been reverted by a concurrent EM and the bug was live again at dispatch time. Defense: detect concurrent-EM activity via remote-tracking refs — each machine runs one daily branch (`work/{machine}/{date-or-span}`) and auto-push lands work on `origin/work/{machine}/*`, so peer EMs are visible only through remote refs. Use `git fetch --quiet && git log --since="1 hour ago" --remotes='origin/work/*' --oneline | grep -v "$(git rev-parse --abbrev-ref HEAD)"` to see commits from peer machines on their own daily branches; non-empty output = concurrent peer EM active. When detected, escalate the Pre-Dispatch verifier from Haiku to Sonnet, and add a re-verify step at Phase 1 launch (`git log --oneline -- <file>` since the verifier's read SHA). Cross-link: see CLAUDE.md § Concurrent-EM Git Operations for the shared-bus discipline this mitigates.

**Why prune at Phase 4:** Without this, backlog rows accumulate forever — every sweep verifies-and-drops the same already-fixed items from its dispatch queue but leaves them sitting in the file. The next sweep re-verifies them at cost. Prune-on-detect breaks the cycle. The paper trail is the resolving commit SHA in the Phase 4 backlog-prune commit subject.

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

Dispatch one agent per chunk with `model: "sonnet"`. Each agent receives its chunk's file list, assigned patterns, the Track A1 grep results for its chunk, AND the hot-zone ranking from `tasks/scratch/bug-sweep/{run-id}/hot-zone-ranking.md` (written in Phase 0 step 4). High-density chunks (top of the ranking) apply extra scrutiny; cooldown-flagged paths are noted in the brief with "recently fixed — deprioritized." For each file:
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

## Phase 1.5: Churn-Gated Findings Verification (conditional)

**Gate:** Run Phase 1.5 iff commits-since-last-sweep > 200 on the swept paths. Cheap check: `git rev-list --count <last-sweep-sha>..HEAD -- <chunk-paths>` against the SHA captured in `tasks/bug-backlog.md` header ("Commit at sweep:"). If no prior sweep SHA exists or the count is ≤200, SKIP Phase 1.5 and go straight to Phase 2.

**Why gated on churn:** *2026-05-28, project-rag (809 commits since prior sweep).* Sonnet sweepers pattern-match on historical bug shapes. Under heavy churn, the highest-confidence P1 findings have the highest false-positive rate — concurrent EMs already fixed the loud bugs, but the sweeper still remembers their shape. Low-churn sweeps don't show this inversion; Phase 1.5 cost (4 Haiku, ~10K tokens each, <5 min) is not worth paying every run.

**Procedure:** Dispatch one Haiku verifier per chunk. Each verifier receives the chunk's Phase 1 findings file (`{chunk-name}-phase1-sonnet.md`) and reads the cited file:line for every P0/P1 finding. For each, return one of:

- `still-present` — current source matches the buggy state described
- `already-fixed` — current source is in the fixed state (cite the resolving SHA from `git log -1 --format=%H -- <file>` filtered since the last-sweep SHA, or `unattributed`)
- `pattern-shifted` — code at the cited location no longer resembles either the buggy or fixed shape (likely refactored away; finding is stale)

Write verdicts to `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1.5-verification.md`. Phase 2 reads this file alongside the Phase 1 findings file for the same chunk and considers only `still-present` findings for triage; `already-fixed` and `pattern-shifted` drop out and are noted in the Phase 4 report.

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

**Also write `tasks/scratch/bug-sweep/{run-id}/phase2-fix-now.json`** — machine-readable list of fix-now findings, consumed by the Phase 4 mechanical diff gate. Schema:

```json
[
  {"id": "F-A-03", "file": "src/foo.py", "line": 142, "severity": "P1", "description": "missing threading.Lock on counter"}
]
```

Minimum required field: `file` (the Phase 4 gate joins on this). `id`, `line`, `severity`, `description` improve the PM report.

## Phase 3: Fix (dispatch Sonnet executors, parallel)

Dispatch Sonnet executors with `model: "sonnet"` to fix all "fix now" items. Group fixes by file/system to minimize conflicts.

Each executor receives:
- The finding list for its file group
- The source files to modify
- Clear acceptance criteria per fix

**Agent prompt must instruct (verbatim — verify-first executor contract):**

> Fix the listed bugs. For each fix:
> 1. Read the cited line range.
> 2. Determine whether the code is in the buggy state described OR already in the fixed state.
> 3. If already fixed, report `no-op — already in HEAD` for that finding and SKIP without editing.
> 4. If buggy, apply the fix and re-read to verify the edit landed.
>
> **Do NOT apply an edit that produces byte-identical content.** An Edit that succeeds with no diff is a false-positive finding, not a fix.
>
> Write a brief summary of changes to `{scratch-path}` using the Write tool. The summary MUST distinguish `fixed` vs `no-op — already in HEAD` per finding.

**Why verify-first:** *2026-05-28, project-rag.* After 800+ commits of intervening churn, Sonnet sweepers anchor on historical bug shapes; 11/11 fix-now P1s in one run were already fixed in HEAD. Executors honestly "fixed" them with byte-identical edits and reported DONE. The verify-first contract converts that silent-success failure mode into an explicit `no-op` per finding.

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

0. **Mechanical diff gate — fail loud on zero-diff runs.** Before commit, assert that fix-now-claimed files actually changed on disk (requires bash — uses process substitution):

   ```bash
   EXPECTED_FILES=$(jq -r '.[].file' < tasks/scratch/bug-sweep/{run-id}/phase2-fix-now.json | sort -u)
   ACTUAL_CHANGED=$(git diff --name-only | sort -u)
   MISSING=$(comm -23 <(echo "$EXPECTED_FILES") <(echo "$ACTUAL_CHANGED"))
   if [ -n "$MISSING" ]; then
     echo "ALERT: fix-now files with no diff (likely false-positive cohort):"
     echo "$MISSING"
   fi
   ```

   If `MISSING` is non-empty, surface each file in the Phase 4 PM report under a **Zero-diff fixes** line — these were executor `no-op` responses (finding already in HEAD). This is the loud-failure counterpart to the verify-first contract in Phase 3: it converts "executor reported DONE, no fixes landed" from a silent class into an explicit count. Do not block commit on a non-empty MISSING set — the remaining real fixes still ship — but the count goes in the report so the false-positive rate is visible.

1. **Commit fixes:**
   ```bash
   # Plain-git scoped commit — do NOT use coordinator-safe-commit here (lessons.md:207, SC-DR-008)
   SWEEP_FILES=$(git diff --name-only)
   git add -- $SWEEP_FILES && git commit -m "bug-sweep: fixed N bugs across M files" -- $SWEEP_FILES
   ```

2. **Prune already-fixed rows from the existing backlog (paper-trail commit).** Before appending new blocked items, read `tasks/scratch/bug-sweep/{run-id}/pre-dispatch-already-fixed.md` (written during Pre-Dispatch). For each entry there:
   - Delete the corresponding row from the active P1/P2 tables in `tasks/bug-backlog.md`.
   - Do NOT move it to a "resolved" section in the same file — the paper trail is the resolving commit SHA from the pre-dispatch scan, captured in this commit's subject.

   Commit the prune (separate from the fixes commit in step 1):
   ```bash
   git reset && git add -- tasks/bug-backlog.md && \
     git commit -m "bug-sweep {run-id}: prune already-fixed — <BS-ID-1>→<sha1>, <BS-ID-2>→<sha2>, ..."
   ```
   The commit subject names each closed ID paired with the SHA that resolved it (or `unattributed` when no single SHA is identifiable). This is the greppable record — `git log --all -- tasks/bug-backlog.md | grep BS-NNNN` answers "what happened to that bug?" without scanning backlog history.

   Skip this sub-step entirely if no already-fixed items were detected pre-dispatch.

3. **Update bug backlog** (`tasks/bug-backlog.md`) — append genuinely blocked items from this sweep + refresh the header:

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

   Commit this update separately from the prune in step 2:
   ```bash
   git reset && git add -- tasks/bug-backlog.md && \
     git commit -m "bug-sweep {run-id}: append <M> new blocked items, refresh header"
   ```

4. **Report to PM:**
   ```markdown
   ## Bug Sweep Complete

   **Scope:** [N] systems, [M] files scanned
   **Patterns applied:** [list]
   **Tests run:** [pass/fail/error counts]
   **Found:** [total] findings ([X] fixed, [Y] blocked, [Z] false positives)
   **Fixes applied:** [list with file:line refs]
   **Zero-diff fixes:** [N fix-now findings where executor reported no-op (finding already in HEAD) / none]
   **Phase 1.5 verification:** [ran (churn=X commits): K still-present, L already-fixed, M pattern-shifted / skipped: <200 commits since last sweep / skipped: no prior sweep record]
   **Backlog pruned:** [N already-fixed items removed with paper-trail commit / none]
   **Blocked items:** [list with "why blocked" for each, or "none"]
   **Docs verification (Phase 3.5):** [clean / N incorrect API claims in fixes reverted / skipped: not C++/UE and no external APIs touched]
   **Track C API sweep:** [N INCORRECT API findings fixed, N suspicious-UNVERIFIED flagged / skipped: `DOCS_VERIFY` not set for this stack]
   ```

5. **Clean scratch:** `rm -rf tasks/scratch/bug-sweep/{run-id}/`
   Only delete after commit succeeds. If Phase 2/3 agents failed, scratch contains Phase 1 findings for recovery.

## Pattern Library, Cost Profile, Failure Modes

See `pipelines/bug-sweep/pattern-library.md` for the full pattern catalog (universal + per-language: Python, JS/TS, C++/UE, code smells), the cost profile table (small/medium/large repo agent counts and wall-clock estimates incl. `DOCS_VERIFY` overhead), and the full failure-modes prevention matrix.
