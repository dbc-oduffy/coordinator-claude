---
name: finishing-a-development-branch
description: "This skill should be used when coordinator work on a branch is complete and needs integration — extends superpowers:finishing-a-development-branch with CI-gated PR merge via merging-to-main, automated cleanup, and /delegate-execution workflow integration."
version: 1.0.0
---

> **Foundation:** This skill extends `superpowers:finishing-a-development-branch`. The superpowers skill provides core completion flow (verify tests, present options, execute, cleanup). This skill adds coordinator-specific automation: CI-gated PR merge via `merging-to-main` skill, and integration with `/delegate-execution` and `/execute-plan` workflows.

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests → Present options → Execute choice → Clean up.

**Announce at start:** "I'm using the coordinator:finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, verify tests pass:**

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 2: Determine Base Branch

```bash
# Try common base branches
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 3: Present Options

Present exactly these 4 options:

```
Implementation complete. What would you like to do?

1. Merge to main via PR (recommended)
2. Create a Pull Request (manual merge later)
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

**Don't add explanation** - keep options concise.

### Step 4: Execute Choice

#### Option 1: Merge to main via PR (Recommended)

Invoke the `merging-to-main` skill. This creates a PR, waits for CI checks, and merges
on success. Branch is deleted after merge.

If on a worktree: worktree is removed after merge (Step 5).

#### Option 2: Create a Pull Request (manual merge later)

Push the feature branch and create a PR, but do NOT merge. Use this when:
- You want the PM to review the PR before merging
- CI needs to pass but you're not ready to merge yet
- You want to come back to this later

```bash
git push -u origin <feature-branch>

gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed>

## Test Plan
- [ ] <verification steps>
EOF
)"
```

If on a worktree: keep the worktree active.

#### Option 3: Keep the branch as-is

Don't merge, don't create PR. Branch stays. Use this when:
- Work is in progress and not ready for review
- You plan to continue in another session

Report: "Keeping branch <name>. Worktree preserved at <path>."

If on a worktree: keep the worktree active.

#### Option 4: Discard this work

**Destructive.** Requires explicit confirmation by typing "discard".

```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>
- Worktree at <path>

Type 'discard' to confirm.
```

Wait for exact confirmation.

If confirmed:
```bash
git checkout <base-branch>
git branch -D <feature-branch>
```

Deletes the branch (local + remote) and removes the worktree if applicable (Step 5).

### Step 5: Cleanup Worktree

<!-- Review: Patrik — Option 2 keeps worktree active; contradicted the quick reference table -->
**For Options 1 and 4:**

Check if in worktree:
```bash
git worktree list | grep $(git branch --show-current)
```

If yes:
```bash
git worktree remove <worktree-path>
```

**For Option 3:** Keep worktree.

## Quick Reference

| Option | PR | Merge | Keep Worktree | Cleanup Branch |
|--------|-----|-------|---------------|----------------|
| 1. Merge via PR | ✓ | ✓ (CI-gated) | - | ✓ |
| 2. PR only | ✓ | - | ✓ | - |
| 3. Keep as-is | - | - | ✓ | - |
| 4. Discard | - | - | - | ✓ (force) |

## Common Mistakes

**Skipping test verification**
- **Problem:** Merge broken code, create failing PR
- **Fix:** Always verify tests before offering options

**Open-ended questions**
- **Problem:** "What should I do next?" → ambiguous
- **Fix:** Present exactly 4 structured options

**Automatic worktree cleanup**
- **Problem:** Remove worktree when might need it (Option 2, 3)
- **Fix:** Only cleanup for Options 1 and 4

**No confirmation for discard**
- **Problem:** Accidentally delete work
- **Fix:** Require typed "discard" confirmation

## Red Flags

**Never:**
- Proceed with failing tests
- Merge without verifying tests on result
- Delete work without confirmation
- Force-push without explicit request

**Always:**
- Verify tests before offering options
- Present exactly 4 options
- Get typed confirmation for Option 4
- Clean up worktree for Options 1 & 4 only

## Integration

**Called by:**
<!-- Review: Patrik — ghost caller references; subagent-driven-development and executing-plans no longer exist -->
- **/delegate-execution** — After all tasks complete
- **/execute-plan** (Step 3) — After all batches complete

**Pairs with:**
- **superpowers:using-git-worktrees** - Cleans up worktree created by that skill
