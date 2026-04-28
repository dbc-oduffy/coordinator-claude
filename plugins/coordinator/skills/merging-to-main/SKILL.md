---
name: merging-to-main
description: Use when work on a branch is ready to merge to main — creates PR, waits for CI, merges, cleans up.
argument-hint: "[--force]"
version: 1.0.0
---

# Merging to Main

## Overview

Merge a work or feature branch to main via PR with CI gating. Creates the PR, waits for checks, merges on success, and cleans up the branch.

**Announce at start:** "I'm using the coordinator:merging-to-main skill to merge this branch to main."

## The Process

### Step 0: Test Suite Gate

Before creating a PR, attempt the project's test suite to catch issues early.

1. **Detect test runner:** Look for common test commands:
   - `pnpm test` or `npm test` (Node.js projects)
   - `pytest` or `python -m pytest` (Python projects)
   - `/validate` skill (all projects with CI)
   - Project-specific test commands from `CLAUDE.md` or `package.json`

2. **Run the test suite.** If tests pass: proceed to Step 1.

3. **If tests fail:** Alert the PM and halt:
   _"Test suite failed before merge. Fix the failures first, or use `/merge-to-main --force` to bypass the test gate for hotfixes."_
   Do NOT proceed to PR creation.

4. **`--force` escape hatch:** If `$ARGUMENTS` contains `--force`:
   - Skip the test suite entirely
   - Log: _"Force-merge requested — test suite gate bypassed."_
   - Proceed to Step 1
   - This is for hotfixes where the PM/EM has decided the merge is urgent

5. **First Officer Doctrine:** If the EM detects the branch has known issues (from health survey or prior test failures), the EM can refuse to merge and alert the PM. The EM is empowered to protect main.

### Step 1: Pre-flight

1. **Check for uncommitted changes.** If any exist:
   ```bash
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "pre-merge quick-save"
   ```

2. **Handle current branch:**

   **If on a work/feature branch:** proceed to step 3.

   **If on main with unpushed commits ahead of origin/main:**
   These commits need to go through a PR, not be pushed directly. Auto-recover:
   ```bash
   # Determine branch name using git-workflow conventions
   BRANCH="work/$(hostname | tr '[:upper:]' '[:lower:]')/$(date +%Y-%m-%d)"
   git checkout -b "$BRANCH"
   git push origin "$BRANCH" --set-upstream
   # Reset local main back to origin
   git checkout main && git reset --hard origin/main
   git checkout "$BRANCH"
   ```
   Then proceed to step 3 on the new branch.

   **If on main with no unpushed commits:** abort:
   _"Already on main with nothing to merge. Switch to a work or feature branch first."_

3. **Verify remote is up-to-date:**
   ```bash
   git log origin/$(git branch --show-current)..HEAD 2>/dev/null
   ```
   If unpushed commits exist, push explicitly:
   ```bash
   git push origin $(git branch --show-current) --set-upstream
   ```

### Step 2: Create PR

```bash
BRANCH=$(git branch --show-current)

# Generate title based on branch type
# work/striker/2026-03-13 → "Work: striker 2026-03-13"
# feature/my-feature → "Feature: my-feature"

# Generate body from commit log
BODY=$(git log main..HEAD --oneline)

gh pr create --base main --head "$BRANCH" --title "$TITLE" --body "$BODY"
```

- Title: `"Work: {machine} {date}"` for work branches, `"Feature: {name}"` for feature branches.
- Body: auto-generated from `git log main..HEAD --oneline`.

### Step 3: Wait for CI

```bash
gh pr checks <pr-number> --watch
```

This blocks until all checks complete.

- **If checks pass:** proceed to Step 4.
- **If "no checks reported"** (exit code 1 with that message): this means the repo has
  no CI configured. Treat as a pass and proceed to Step 4.
- **If checks fail:** report which checks failed. Do NOT merge. Stop and report:
  _"CI failed on {check}. Fix the issue and re-run `/merge-to-main`, or investigate with `coordinator:systematic-debugging`."_

### Step 4: Merge

Use merge commit (not squash) — preserves commit history as breadcrumbs.

```bash
gh pr merge <pr-number> --merge --delete-branch
```

**If "base branch policy prohibits the merge":**
This can happen if the ruleset configuration requires conditions not yet met.
Auto-recover with `--auto`, which tells GitHub to merge as soon as all
requirements are satisfied:
```bash
gh pr merge <pr-number> --merge --delete-branch --auto
```
Then wait briefly and verify the merge completed:
```bash
sleep 5 && gh pr view <pr-number> --json state --jq '.state'
```
If state is `MERGED`, proceed to Step 5. If still `OPEN`, the auto-merge is queued —
wait and check again.

**Note:** As of 2026-03-13, rulesets no longer require status checks or block force push.
The primary gate is the PR requirement (0 approvals). CI runs advisory.

**If "head branch is not up to date with base":**
This is expected when main has advanced (e.g., a previous branch was just merged).
Auto-recover — do NOT stop or ask:
```bash
git fetch origin main
git merge origin/main -m "merge main into work branch"
git push origin $(git branch --show-current)
gh pr merge <pr-number> --merge --delete-branch  # retry
```

**If merge conflicts (actual file conflicts):**
Do NOT force. Report conflicting files and suggest:
_"Main has diverged with conflicts. Options: (a) merge main into this branch and resolve conflicts, (b) rebase onto main. Recommend (a) for simplicity."_
Stop and wait for PM judgment.

### Step 4.5: Post-Merge Re-Verify Shared Infra (geneva T1.7)

After the merge completes — especially when merge conflicts were resolved or when main had concurrent edits to shared files (plugin internals, shared scripts, configs) — re-verify that your intended changes survived.

**Why this matters:** Last-writer-wins silently reverts edits when both sides touched the same hunk and the conflict was resolved naively. A merge that "succeeded" may have dropped your change without any warning.

**Verification steps:**

1. For each file you specifically edited on this branch, run:
   ```bash
   git show HEAD:<file-path> | grep -F "<canonical phrase from your change>"
   ```
2. If a canonical phrase is missing, your change was overwritten. Re-apply it and push a follow-up commit immediately.
3. Pay particular attention to shared infra files (`~/.claude/`, config files, shared scripts) — these are the highest-risk files in concurrent-session environments.

### Step 5: Local Cleanup

```bash
git checkout main
git pull origin main
git branch -d <branch>  # local branch delete
```

If on a worktree: `git worktree remove <path>` instead.

### Step 6: Report

```
## Merged to Main
- **PR:** {url}
- **Merge commit:** {sha}
- **Branch deleted:** {branch} (local + remote)
- **Now on:** main @ {sha}
```

## Red Flags

**Never:**
- Squash commits (we want the breadcrumb trail)
- Push directly to main (use PRs)

**Use judgment:**
- CI failures are advisory — review them, but they don't block merge
- Force push is allowed by the ruleset if needed

**Always:**
- Verify remote is synced before creating PR
- Wait for all CI checks to complete
- Use merge commits to preserve history
- Clean up branch after successful merge

## Integration

**Called by:**
- **coordinator:finishing-a-development-branch** (Option 1) — delegates merge workflow here
- Invoked directly by PM/EM when ready to merge (no longer called by /workday-complete)

**Pairs with:**
- **coordinator:using-git-worktrees** — cleans up worktree after merge
