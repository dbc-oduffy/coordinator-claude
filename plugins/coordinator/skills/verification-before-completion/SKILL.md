---
name: verification-before-completion
description: Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always
version: 1.0.0
---

# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Multi-File Executor Verification

Two universal rules that apply after any executor or apply-agent dispatch:

### (a) Diff is ground truth — not the agent's chat summary

Executor and apply-agents consistently under-count their own work in chat (observed repeatedly in distill and architecture-audit runs). After any multi-file executor dispatch:

1. Run `git diff --stat <expected-path-glob>` — treat the diff as ground truth, not the agent's completion report.
2. **Empty diff for an agent that claimed work = re-dispatch** with the explicit list of unfinished files. Do not accept "I completed all files" alongside a zero-line diff.
3. For spec-driven dispatches that mandate a canonical phrase or pattern across N files, also run `grep -l "<canonical phrase>" <target-files>`. File count alone is not proof — the canonical content must actually appear.


### (c) Edit tool success is not proof of change (DroneSim T1.3)

After a sequence of Edit calls — especially before claiming a fix is in or before commit — run `git diff <file>` (or `git diff --stat`) to confirm the bytes actually moved. Edit returns success on no-ops where the new_string already matched.

### (d) Subagents may "fix" things without producing diffs (fifa T1.4)

Subagents conflate "this is correct now" with "I made it correct." Before reporting fixes applied, executor prompts should include `git status --short` + `git diff --stat`; report actual diff stats, not self-narrated counts of intended changes. "No-op, target was already correct" is a valid outcome — and an honest one.

### (b) Match verification to the change you made (L274)

Verification must target the actual side effects of YOUR action. Running an unrelated expensive process ("ran the full test suite, all green") as "verification" of a one-line change is cargo-cult.

- Made a code edit? Re-Read the file and grep for the changed symbol.
- Added a pattern across files? `grep -l` the pattern across those files.
- Fixed a specific code path? Exercise that path — don't just run unrelated tests.

"I made the edit" without re-Read is an assertion, not evidence.

| Verification Claim | Must Run | Not Sufficient |
|--------------------|----------|----------------|
| N files updated by executor | `git diff --stat` showing N files | Agent chat summary |
| Canonical phrase applied across files | `grep -l "<phrase>" <targets>` | "All files processed" |
| One-line bug fix | Re-Read file + grep for change | Full test suite passing |
| Pattern applied consistently | Targeted grep on changed files | Build success |

## Format Validation (fifa T1.3)

For batch outputs with a known schema, existence checks are not enough. Prefer a sweep confirming each file contains the canonical block before reporting completion.

**Why this is distinct from existence checks:** A file can exist and still be schema-nonconformant. In a 64-nation pipeline, 3 nations produced prose-only syntheses (no JSON block) and 2 had non-standard JSON root keys — 5/64 files would have silently passed an existence check.

**Sweep pattern:**
```bash
# Confirm JSON block present
grep -l '```json' outputs/*.md

# Confirm expected root key (jq)
for f in outputs/*.json; do jq -e '.expected_root_key' "$f" > /dev/null || echo "FAIL: $f"; done
```

**Failure modes to check explicitly:**
- Prose-only output when structured format was required (no code fence / no JSON block)
- Non-standard root keys (e.g. `data` instead of `results`, `output` instead of expected key)
- Truncated output (file exists but JSON is incomplete / malformed)

Run this sweep before reporting batch completion — not after.

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Why This Matters

From 24 failure memories:
- your human partner said "I don't believe you" - trust broken
- Undefined functions shipped - would crash
- Missing requirements shipped - incomplete features
- Time wasted on false completion → redirect → rework
- Violates: "Honesty is a core value. If you lie, you'll be replaced."

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

## Scope-Conformance Check After Executor Returns (geneva T1.5)

Before staging any executor output: (1) run `git diff --stat` to enumerate changed paths, (2) confirm each path is within the dispatch's declared scope, (3) stash or revert any out-of-scope edits.

Out-of-scope edits are common failure modes: test file deletions, unrelated refactors, autonomous commits the executor made despite instructions. The check is mechanical and must happen before the coordinator reads the diff semantically.

See `commands/delegate-execution.md` → "Scope-Conformance Check" for the dispatch-prompt clause that enforces this on the executor side.

## Definition of Done (acceptance gate before declaring completion)

For any plan with declared acceptance criteria, "done" means more than green tests. Before claiming completion or moving to merge:

- [ ] Every **acceptance criterion** is satisfied (or explicitly waived in writing with PM acknowledgement).
- [ ] Tests/checks ran and the output is captured (link or excerpt — not "trust me").
- [ ] If user-visible: **manual demo path verified** — you actually walked the steps, not just inferred from green tests.
- [ ] If user-visible OR if scope is patch-where-refactor-might-be-cheaper: **YK** (`agents/vp-product.md`) has been dispatched and findings are integrated. YK verdict line is staged for the PR body.
- [ ] Technical reviewer has run if scope mode warrants it (production-patch and feature: yes; prototype/spike: optional).
- [ ] **Known limitations** are documented — what *isn't* covered, what edge cases were deferred.
- [ ] **Rollback or mitigation** is named — if this turns out wrong in production, what's the recovery move?
- [ ] **Ship verdict** is staged for the PM (see `coordinator:merging-to-main`).

This is the bridge between engineering output and PM confidence. "The agent says it's done" is not the gate; this is.

## The Bottom Line

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.
