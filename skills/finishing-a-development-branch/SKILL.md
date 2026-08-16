---
name: finishing-a-development-branch
description: "Presents merge, PR, or cleanup options once tests pass."
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests → Present options → Execute choice → Clean up.

**Announce at start:** "I'm using the coordinator:finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, check whether test evidence already covers this branch.** If this session already has fast-tier or targeted-test evidence for the current diff, report it as-is and move to Step 2 — this step is not a cadence gate that reruns tests on every branch finish.

If no such evidence exists, a scoped run beats a broad one: prefer targeted tests covering the touched files over the fast tier. Reaching for the fast tier at all means reaching for the grant first — this skill is not on the implicit-grant ceremony list (`/workday-complete`, `/workweek-complete`, `/merging-to-main`), so before invoking a resolved Tier F command, check
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" check` (the same session-scoped token Tier U consumes). Exit 0 = granted, resolve and run via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-resolve-validation-cmd" --fast` (rc 0 = resolved, run the result and capture its exit code; rc 2 = no `fast_test_cmd` configured — skipped, not failed). Exit 1 (ungranted) halts before invoking it: ask the PM for a session grant, run under a ceremony that already holds the implicit grant, or defer and report `Validation: skipped` for this invocation. Either way, a full-suite gate belongs to the merge ceremony downstream (Option 1 chains into `merging-to-main`, which runs its own CI-gated checks) — this step never substitutes for that gate. Interim caveat: a chained `fast_test_cmd` (`a && b`, `a; b`, a pipe) is denied by the invocation guard today — don't reshape the command to dodge it; configure `fast_test_cmd` as a single command, with multi-step logic in a wrapper script instead.

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 2: Determine Base Branch

Try common base branches: `git merge-base HEAD main`, falling back to `git merge-base HEAD master` if that fails.

Or ask: "This branch split from main - is that correct?"

### Step 3: Present Options

Present exactly these 3 options:

```
Implementation complete. What would you like to do?

1. Merge to main via PR (recommended)
2. Create a Pull Request (manual merge later)
3. Keep the branch as-is (I'll handle it later)

Which option?
```

**Don't add explanation** - keep options concise.

**Why no "discard" option:** when this skill fires, work is reviewed, tested, and committed. Offering discard as a peer of "merge" treats the choice as ambivalent when it isn't. If the PM genuinely wants to throw the work away, they'll say so explicitly — and that path goes through deliberate destructive-action confirmation, not a numbered menu.

**No worktrees.** Worktrees are forbidden — work happens on the active workstream branch. An
override exists but requires explicit PM permission via the EM. If a stray worktree turns up
during Step 5 below, that's debris to remove, not state to preserve.

### Step 4: Execute Choice

#### Option 1: Merge to main via PR (Recommended)

Invoke the `merging-to-main` skill. This creates a PR, waits for CI checks, and merges
on success. Branch is deleted after merge.

#### Option 2: Create a Pull Request (manual merge later)

Push the feature branch and create a PR, but do NOT merge. Use this when:
- You want the PM to review the PR before merging
- CI needs to pass but you're not ready to merge yet
- You want to come back to this later

Push the feature branch (`git push -u origin <feature-branch>`), then create the PR with `gh pr create`, giving it a title and a body with `## Summary` (2-3 bullets of what changed) and `## Test Plan` (verification steps as a checklist) sections.

#### Option 3: Keep the branch as-is

Don't merge, don't create PR. Branch stays. Use this when:
- Work is in progress and not ready for review
- You plan to continue in another session

Report: "Keeping branch <name>."

### Step 5: Remove Any Stray Worktree

Check if in a worktree by grepping `git worktree list` for the current branch name (`git branch --show-current`).

If yes, remove it (`git worktree remove <worktree-path>`) — regardless of which option was chosen. Worktrees are forbidden, so any found here is stray debris left behind, not deliberately preserved state.

## Quick Reference

| Option | PR | Merge | Cleanup Branch |
|--------|-----|-------|---------------|
| 1. Merge via PR | ✓ | ✓ (CI-gated) | ✓ |
| 2. PR only | ✓ | - | - |
| 3. Keep as-is | - | - | - |

## Common Mistakes

**Skipping test verification**
- **Problem:** Merge broken code, create failing PR
- **Fix:** Always verify tests before offering options

**Open-ended questions**
- **Problem:** "What should I do next?" → ambiguous
- **Fix:** Present exactly 3 structured options

**Offering discard as a numbered option**
- **Problem/Fix:** see Step 3, "Why no 'discard' option" — don't restate it here.

## Red Flags

**Never:**
- Proceed with failing tests
- Merge without verifying tests on result
- Offer discard as a numbered menu option
- Force-push without explicit request

**Always:**
- Verify tests before offering options
- Present exactly 3 options
- Remove any stray worktree found, regardless of chosen option

## Integration

**Called by:**
- **Executor-dispatch workflow** — After all tasks complete
- **The PM directly** — when a branch is ready for disposition (merge / PR / keep)

**Not called by:**
- **/execute-plan** — execute-plan finalizes and offers `/workstream-complete`; it deliberately does **not** chain into branch disposition, since that reaches the keyword-gated `/merge-to-main`. Branch disposition is a separate, PM-invoked decision.

**Pairs with:**
- **`consolidate-git`** — operates on sibling branches/worktrees, not the current branch; kept as a
  separate skill from this one rather than folded, since a "fold thin engines into their only
  caller" consolidation only applies when the two skills share one caller and scope — these don't.

**Extraction note:** the Step 3 3-option menu is the judgment residue an assembler cannot
resolve — it stays hand-authored prose, not a computed op.
