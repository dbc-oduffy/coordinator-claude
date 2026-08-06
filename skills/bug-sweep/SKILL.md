---
name: bug-sweep
description: "Codebase bug hunt — find and fix AI-fixable bugs, defer the rest."
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

1. **Detect stack:** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/bug-sweep-probes" detect-stack [path]` (defaults to cwd; scope to `$ARGUMENTS` when path-scoped). Returns `language_files`, `test_dirs`, `config_files`.

   **`DOCS_VERIFY` judgment call:** set `true` when the stack is a compiled language or large opinionated framework where "compiles" doesn't imply "as documented" (UE, C++, C#, Unity, Godot, Java/Spring, Rust). Leave `false` for TypeScript/JavaScript/Python — dense training data, rare hallucinations. When in doubt, enable it: the downside of a false positive is a few extra agents, the downside of a false negative is a silent wrong API. Enables Track C below and makes Phase 3.5 mandatory.

2. **Select patterns** from the Pattern Library (end of this document) per detected stack. Universal patterns always apply.

3. **Define search chunks** — 3-6 chunks by directory/system, from the architecture atlas (`docs/architecture/systems-index.md`) if it exists, else `DIRECTORY.md` or directory structure.

4. **Hot-zone rank:** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --since "30d" --where "nature=bugfix" --format json`. Aggregate by file-path-prefix; chunks over high-density paths dispatch first. Cooldown: paths with a bugfix completion in the last 7 days deprioritize — a path that is both hot-zone and cooled is a real conflict, surface it explicitly rather than picking silently. Record the ranking to `tasks/scratch/bug-sweep/{run-id}/hot-zone-ranking.md`; skip ranking (default directory order) if `query-completions` returns nothing.

5. **Check test suite** — identify the runner for Phase 1 Track B.

6. **Read `state/lessons/`** (directory of per-entry YAML, if it exists) for project-specific patterns to add.

7. **Generate run ID** (`YYYY-MM-DD-HHhMM`) and create `tasks/scratch/bug-sweep/{run-id}/`.

8. **Output:** chunk table with pattern assignments, hot-zone ranking, test runner command.

## Pre-Dispatch: Verify Backlog Against Current Code

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" brief bug-sweep`. Against an empty (or all-closed) `state/bug-backlog/`, no judgment point surfaces — skip straight to Phase 1. Against open entries, the brief surfaces `j-bug-sweep-pre-dispatch-verification-due`: whether to re-verify cited items against current HEAD before dispatch is a semantic read the engine has no opinion on — decide it.

If verifying, dispatch one Haiku agent per system, each checking its open items: read the cited `file:line` against HEAD, check `git log --oneline -5 {file}` for resolving commits, return `still-open` / `already-fixed` (with the resolving SHA, or `unattributed` if none is cleanly attributable). Drop `already-fixed` items from the dispatch queue and record the verified-fixed IDs + SHAs to `tasks/scratch/bug-sweep/{run-id}/pre-dispatch-already-fixed.md` — Phase 4 prunes the backlog from this file.

**Concurrent-EM peers can invert a verdict mid-pipeline.** Before dispatching verifiers, run `git fetch --quiet` and check `git log --since="1 hour ago" --remotes='origin/work/*' --oneline` for commits not on the current branch — non-empty output means a peer EM is active. When detected, escalate the verifier from Haiku to Sonnet and re-verify at Phase 1 launch (`git log --oneline -- <file>` since the verifier's read SHA). See ~/.claude/CLAUDE.md § Concurrent-EM Git Operations for the underlying shared-bus discipline.

**Before fixing any P0/P1 finding**, read the cited code yourself (or via a verifier subagent) and confirm the claim against current source — never trust the agent's paraphrase. P0 claims have measured a far higher false-positive rate than P2s; the higher the stated severity, the more the claim needs independent confirmation.

## Phase 1: Search + Test (dispatch leaf agents, parallel)

**Three parallel tracks:**

### Track A1 — Mechanical Pattern Grep (YOU do this, fast)

Deterministic grep across all chunks: `TODO`/`FIXME`/`HACK`/`XXX`/`BUG` comments, empty catch/except blocks, language-specific mechanical patterns (bare `except:`, `== null`, etc.). <30 seconds; feeds Track A2 as context.

### Track A2 — Semantic Analysis (dispatch one Sonnet per chunk)

This is the sweep's actual purpose and irreducibly a judgment call — no mechanical pattern set substitutes for it. Each agent gets its chunk's file list, assigned patterns, Track A1's grep results, and the hot-zone ranking (cooldown paths noted "recently fixed — deprioritized"). Per file: review grep findings for false positives, run deeper semantic analysis (error handling gaps, null access, resource leaks, logic errors, dead code, race conditions), and for each finding give severity (P0/P1/P2), confidence (HIGH/MEDIUM/LOW), file:line, description, AI-fixable-or-not. Include code smells alongside bugs — confusing names, structural issues, dead code, mutation footguns are all findings; do not invent a P3/"info" tier to downgrade them.

**Agent prompt must instruct:** "Cast a wide net. Report bugs AND code smells — both are worth fixing. Err on the side of reporting — false positives are cheap, missed issues are expensive. Use P0/P1/P2 severity ONLY — do not invent P3, 'info', or 'defer' tiers. A code smell that can be fixed in under 5 minutes is P2, not 'informational'. Write your complete findings to `{scratch-path}` using the Write tool. Return only a brief summary — the coordinator reads full output from disk."

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1-sonnet.md`

### Track B — Test Suite (EM runs; a Haiku agent parses the output)

Running a suite is Tier-U (or Tier-F if fast-tier-scoped) — subagents never invoke it, and `/bug-sweep` holds no implicit grant. Ask the PM: *"This sweep wants to run the test suite to fold failures into the findings — authorize?"*

**The ask is not the grant — write the token, don't just narrate the answer.** A grant is an explicit affirmative reply naming the suite/Tier-U as its subject ("yes, run the suite" / "authorized"), not adjacent approval of the sweep in general ("looks good, go ahead"). A terse "yes"/"authorized" alone still qualifies when it's a direct reply to this ask — the bar is a well-formed ask answered plainly, not a phrase to be repeated back verbatim. This disposition call is the PM's, not the engine's.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" brief bug-sweep` for the exact ask text (judgment point `j-bug-sweep-tier-u-grant`) and its paired write directive. On grant, apply it — `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply bug-sweep --decisions '{"j-bug-sweep-tier-u-grant":"granted"}'` — which shells out to `tier-u-grant-cli grant pm <note>` for you; no manual CLI construction. On decline, apply nothing, skip Track B, and report the decline — never substitute a subagent invocation as a workaround.

Immediately before firing (never on the strength of the conversation having happened earlier), recheck `tier-u-grant-cli check` — exit 0 grants, exit 1 halts. Then run the suite via `Bash` yourself and capture raw output; dispatch one `model: "haiku"` agent to parse it (never invoke it) into pass/fail/error counts and, per failure, error/file:line/likely source.

If no test suite exists, report that and skip.

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/tests-phase1-haiku.md`

### Track C — API Documentation Verification (`DOCS_VERIFY = true` stacks only)

Dispatch one `coordinator:docs-checker` agent per chunk (`model: "sonnet"`) against its chunk's source files. Its sidecar path is provisioned by claude-klabauter's `provision_report` and arrives in the dispatch brief — pass it through unchanged; do not compute or scaffold one. The agent scans external API references (class/function names, header includes, Blueprint nodes, UPROPERTY/UFUNCTION specifiers, enum values, SDK calls) against example-game-repo-docs (UE) or Context7 (non-UE) and returns a structured report.

**Rationale:** Claude's API knowledge is imperfect for compiled/opinionated stacks — wrong headers, nonexistent methods, wrong signatures can compile silently or fail only at link time. Track C surfaces these at the same triage priority as functional bugs.

**Feeding into triage:** `INCORRECT` → P1 finding ("API incorrect per example-game-repo-docs: [detail]"). `UNVERIFIED` with zero RAG hits on a UE-naming-convention symbol → P2 ("possible hallucinated API"). `UNVERIFIED` from server unavailability → drop, not actionable.

**Scratch path:** `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1-docschecker.md`

### Scratch Verification

Before Phase 2, confirm all expected scratch files exist (`ls tasks/scratch/bug-sweep/{run-id}/`). Re-dispatch once for any chunk agent that failed to write; if it fails again, proceed with what's available.

## Phase 1.5: Churn-Gated Findings Verification (conditional)

**Gate:** run iff `git rev-list --count <last-sweep-sha>..HEAD -- <chunk-paths>` (SHA from `state/bug-backlog/.meta.yaml`'s `last_sweep_commit:`) exceeds 200. Missing `.meta.yaml`, missing key, or count ≤200 → skip straight to Phase 2. Under heavy churn the highest-confidence P1s carry the highest false-positive rate — the sweeper pattern-matches on a bug shape a concurrent EM already fixed; low-churn sweeps don't invert this way, which is why the gate exists rather than running every time.

**Procedure:** dispatch one Haiku verifier per chunk against that chunk's `{chunk-name}-phase1-sonnet.md`, reading the cited `file:line` for every P0/P1 finding and returning `still-present` / `already-fixed` (resolving SHA or `unattributed`) / `pattern-shifted` (code no longer resembles either shape — finding is stale). Write to `tasks/scratch/bug-sweep/{run-id}/{chunk-name}-phase1.5-verification.md`. Phase 2 considers only `still-present` findings for triage; the rest drop out and are noted in the Phase 4 report.

## Phase 2: Triage (~5 min, YOU do this)

Read all Phase 1 findings from `tasks/scratch/bug-sweep/{run-id}/`. When `DOCS_VERIFY = true`, merge Track C's `INCORRECT` and suspicious-`UNVERIFIED` findings in before categorizing.

### Step 2.1: Categorize (the sweep's other irreducible judgment call)

1. **Fix now** — the default. Clear bug or smell + clear fix → fix it: missing error handling, dead code, swallowed exceptions, obvious-cause failed tests, straightforward TODO/FIXME; confusing names, mid-file imports, in-place mutation footguns, O(n) where O(1) exists, uncached per-call allocations, double-checked locking bugs, dead parameters.

2. **Backlog** — only genuinely blocked: needs human verification, needs a plan session, or intent-ambiguous logic needing PM judgment. Not for "low confidence" (verify and fix-or-drop), not for code smells (always fixable), not for anything under 10 minutes.

   **"Needs runtime confirmation" is not itself a reason to backlog when the fix is free and safe** (trivially correct by inspection, reverts cleanly, no migration, no user-visible change) — apply it now and note "fix applied; runtime confirmation deferred." A no-op fix costs nothing even if the bug turns out not to have been real; only backlog when the fix itself, not the confirmation, is unclear or risky.

3. **False positive** — pattern matched, not a bug: intentional patterns, comments/docs mentioning bug patterns.

**Bias toward fixing** — same effort to fix as to document. Code smells are fixable by definition and never belong in backlog; valid backlog reasons are intent judgment, plan-session scope, or an external blocker only. Merge cross-agent duplicates.

**Output:** "Fix now" / "Backlog" lists grouped by file. Also write `tasks/scratch/bug-sweep/{run-id}/phase2-fix-now.json` (Phase 4's mechanical diff gate consumes it), minimum field `file`:

```json
[
  {"id": "F-A-03", "file": "src/foo.py", "line": 142, "severity": "P1", "description": "missing threading.Lock on counter"}
]
```

## Phase 3: Fix (dispatch Sonnet executors, parallel)

Dispatch Sonnet executors, grouped by file/system to minimize conflicts. Each receives its finding group, the source files, and acceptance criteria per fix.

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

This contract exists because sweepers anchor on historical bug shapes after heavy churn — without it, an executor "fixes" an already-fixed bug with a byte-identical edit and honestly reports DONE.

**Post-fix:** re-run the test suite yourself to catch regressions — same Track B grant, no second ask; recheck it live via `tier-u-grant-cli check` rather than re-asking or re-applying. Any test failing that wasn't failing before → revert that fix, move the finding to backlog noting "regression introduced." Skip this re-run if Track B was declined or skipped.

## Phase 3.5: Post-Fix API Verification (YOU do this)

Before committing, run docs-checker on the changed files to confirm the fixes themselves don't introduce hallucinated or incorrect API usage. **Mandatory when `DOCS_VERIFY = true`; recommended whenever fixes touch external library APIs.**

1. `git diff --name-only` for the changed-file set.
2. Dispatch one `coordinator:docs-checker` agent against that set, using the sidecar path provisioned in the brief (never scaffold one). Brief it: "verify all external API claims in these modified files; report INCORRECT and suspicious-UNVERIFIED only."
3. **No INCORRECT findings** → Phase 4. **INCORRECT in a fix** → `git checkout -- {file}` to revert it, move the finding to backlog noting the docs-checker verdict; the original bug stays open. **UNVERIFIED, zero-hit UE-naming pattern** → flag to PM in the Phase 4 report, don't block.

Phase 3.5 reads only the changed files — it is not a re-sweep.

## Phase 4: Report and Commit (YOU do this)

0. **Mechanical diff gate — fail loud on zero-diff runs.** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/bug-sweep-probes" verify-diff --fix-now tasks/scratch/bug-sweep/{run-id}/phase2-fix-now.json` prints `expected_count`/`actual_changed_count`/`missing` and, when `missing` is non-empty, an alert to stderr (exit 1, informational — the calling agent decides how to surface it, not a hard failure). A non-empty `missing` list is the loud-failure counterpart to Phase 3's verify-first contract: executor `no-op` responses that claimed a fix. List it in the report as **Zero-diff fixes**; it doesn't block committing the real fixes.

1. **Commit fixes** via the named op — never narrate the git sequence and never `coordinator-safe-commit` here (lessons.md:207; `docs/wiki/scoped-safety-commits.md § Current Doctrine`): pass each `git diff --name-only` path as a `--wave-path` to `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply bug-sweep --wave-path <path>... --granularity per-wave --message "bug-sweep: fixed N bugs across M files"` — one op, one commit, engine-staged and engine-scoped so a concurrent session's staged files stay untouched.

2. **Prune already-fixed backlog entries (paper-trail commit), separate from step 1.** Read `pre-dispatch-already-fixed.md`; for each, stamp `status: closed`, `closed_at: <ISO date>`, `closed_by: <resolving-sha or unattributed>` and `git mv` it to `archive/bug-backlog/<YYYY-MM>/` — the op above doesn't rename, only stage-and-commit. Then invoke the same apply op, one `--wave-path` per renamed file, `--granularity per-wave`, `--message` naming each closed ID paired with its resolving SHA — the greppable answer to "what happened to that bug?" without scanning history. Skip this sub-step if pre-dispatch found nothing already-fixed.

3. **Append genuinely blocked items** via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-queue-append" --schema bug-backlog --surface <subsystem> --severity P1 --status open --title "<title>" --body "<description>" [--why-blocked "<reason>"] [--evidence <ref>]`, cross-referencing `state/debt-backlog/` overlap via `--evidence` where it exists. Creates `state/bug-backlog/<date>-<slug>.yaml` (filename is the canonical handle). Write/update `state/bug-backlog/.meta.yaml` with `last_sweep_commit:`/`last_sweep_at:` (zero counts too, if nothing appended), then invoke the same apply op scoped to the directory: `--wave-path state/bug-backlog/ --granularity per-wave --message "bug-sweep {run-id}: append <M> new blocked items, refresh .meta.yaml"`.

4. **Report to PM.**

   **Report by exception.** A fixed block of ten status lines is still an EM→PM reply and still owes the ≤200-word budget — a clean sweep spends that budget on facts the PM can read off the commit, and the same Stop-hook citation detector (D2) fires independently of length on per-fix `file:line` refs, which belong in the commit message, not here. Print what needs a reader, not what needs a checkbox.

   ```markdown
   ## Bug Sweep Complete

   **Found:** [total] findings ([X] fixed, [Y] blocked, [Z] false positives)
   **Fixes applied:** [N] fixed — [one-line characterization, e.g. "error-handling gaps and dead code across 3 files"]. Full file:line list is in the commit message.
   ```

   Then append a line **only** if its condition holds:

   | Line | Include only when |
   |---|---|
   | `**Tests run:**` | Track B ran and any test failed/errored — name the pass/fail/error counts |
   | `**Zero-diff fixes:**` | the mechanical diff gate's `missing` list is non-empty — list the no-op findings |
   | `**Phase 1.5 verification:**` | Phase 1.5 ran (churn gate tripped) — K still-present, L already-fixed, M pattern-shifted |
   | `**Blocked items:**` | N ≥ 1 — list each with its "why blocked" reason |
   | `**Docs verification (Phase 3.5):**` | `DOCS_VERIFY = true` and an INCORRECT finding was reverted from a fix |
   | `**Track C API sweep:**` | `DOCS_VERIFY = true` and it found INCORRECT or suspicious-UNVERIFIED items |

   **Negative-spec — these are gone, do not restore them.** `Scope`, `Patterns applied`, and `Backlog pruned` are no longer printed at all, in any form. Each was a count or file-list restatement of work the sweep's own commits already record, with no PM decision attached — `Scope`/`Patterns applied` duplicate Phase 0's own output, and `Backlog pruned`'s paper-trail commit (step 2) is its own record of what was pruned; there is no exception condition where the PM needs any of the three repeated in the reply. A clean Track B run, an untripped Phase 1.5 gate, and zero blocked items are likewise not printed — their absence is not a signal the phase was skipped, it is the reply narrowing to what needs a reader. A future reader must not re-add any of these "for completeness": completeness of the *sweep* is Phase 4's own job (the commits + backlog entries), completeness of the *report* is not the same thing.

5. **Leave scratch in place after commit.** `tasks/scratch/bug-sweep/{run-id}/` carries `file:line` citations other consumers may still need (cross-repo memos, plan amendments, a follow-on session picking up blocked items). Delete it (`rm -rf tasks/scratch/bug-sweep/{run-id}/`) at `/workstream-complete`'s session self-clean step, or on an explicit PM cleanup signal — whichever comes first. If the next step is a `/handoff`, note the scratch path in the handoff body.

## Pattern Library, Cost Profile, Failure Modes

See `pipelines/bug-sweep/pattern-library.md` for the full pattern catalog (universal + per-language: Python, JS/TS, C++/UE, code smells), the cost profile table (small/medium/large repo agent counts and wall-clock estimates incl. `DOCS_VERIFY` overhead), and the full failure-modes prevention matrix.
