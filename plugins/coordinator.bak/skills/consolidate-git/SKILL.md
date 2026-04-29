---
name: consolidate-git
description: Use when the repo has multiple stale branches that need cleaning up — inventories all branches, absorbs unique commits into the current branch, deletes stale branches, and merges to main. This skill should be used when the user asks to "clean up branches", "consolidate branches", "consolidate git", "merge all branches", or mentions stale/old branches that need cleanup.
version: 1.0.0
---

# Consolidate Git — Branch Cleanup + Merge

## Overview

Reduce branch sprawl to a single clean main. Inventories all local and remote branches, absorbs any unique commits into the current branch, deletes stale branches, then merges to main via `/merge-to-main`.

**Announce at start:** "I'm using the coordinator:consolidate-git skill to consolidate all branches and merge to main."

## The Process

### Step 1: Inventory Branches

List all local and remote branches, determine ownership, and categorize.

**1a. Identify the current user:**

```bash
MY_EMAIL=$(git config user.email)
```

**1b. List all branches with tip author:**

```bash
git branch -a
```

For each branch (excluding main and the current branch), check the author of the most recent commit on the tip:

```bash
# Local branch:
git log -1 --format='%ae' <branch>

# Remote-only branch:
git log -1 --format='%ae' origin/<branch>
```

**1c. Categorize each branch:**

| Category | Definition | Action |
|----------|-----------|--------|
| **current** | The checked-out branch | Absorb target — everything merges here |
| **main** | The trunk branch | Merge target — current branch merges here at the end |
| **mine (stale)** | Tip author matches `$MY_EMAIL` | Check for unique commits, absorb if any, then delete |
| **other's** | Tip author does NOT match `$MY_EMAIL` | **Leave untouched** |

**1d. Present the inventory to the PM as a table:**

```
| Branch | Local | Remote | Owner | Category |
|--------|-------|--------|-------|----------|
| main | yes | yes | — | trunk |
| work/striker/2026-03-20 | yes | yes | me | mine (stale) |
| feature/foo | no | yes | me | mine (stale) |
| feature/bar | no | yes | alice@co.com | other's — skipped |
| work/striker/2026-03-23 | yes (current) | yes | me | current |
```

**Only branches categorized as "mine (stale)" proceed to Steps 2–4.** Other people's branches are reported but never touched.

### Step 2: Check for Unique Commits

For each stale branch, check if it has commits not in the current branch:

```bash
# For local branches:
git log --oneline <current-branch>..<stale-branch>

# For remote-only branches:
git log --oneline <current-branch>..origin/<stale-branch>
```

Categorize the result:
- **No unique commits** — safe to delete immediately
- **Has unique commits** — inspect them, then absorb or skip

### Step 3: Absorb Unique Commits

For each stale branch with unique commits:

1. **Inspect the commits** — `git show --stat <commit>` to understand what changed
2. **Choose absorption strategy:**
   - **Cherry-pick** (default for 1-3 commits): `git cherry-pick <commit> --no-edit`
   - **Merge** (for branches with many commits): `git merge <stale-branch> --no-edit`
3. **If conflicts arise:**
   - Inspect the conflicting files — determine if the current branch already supersedes the change
   - If superseded: abort (`git cherry-pick --abort` or `git merge --abort`) and skip — note this in the report
   - If genuinely needed: resolve conflicts, then continue
   - Do NOT force through conflicts blindly — each conflict is a signal that needs inspection

**Report each absorption decision to the PM:**
> "Branch `work/striker/2026-03-20` has 2 unique commits — both are experiment data snapshots already superseded by current branch. Skipping."

or:

> "Branch `feature/auth-rewrite` has 5 unique commits with real code changes. Cherry-picking into current branch."

### Step 4: Delete Stale Branches

After all unique commits are absorbed (or explicitly skipped), delete stale branches:

```bash
# Local branches — use safe delete (-d), not force delete (-D)
git branch -d <branch>

# Remote branches — batch deletions into one push
git push origin --delete <branch1> <branch2> <branch3>
```

**Use `-d` (safe delete), not `-D`.**  Safe delete will refuse if the branch has unmerged commits — this is a final safety net. If `-d` refuses, investigate before escalating to `-D` with PM approval.

After deletion, prune stale remote tracking refs:

```bash
git fetch --prune
```

### Step 5: Merge to Main

Invoke `/merge-to-main` to create a PR, wait for CI, merge, and clean up.

If the current branch IS main (because all work was already absorbed and we're cleaning remotes only), skip this step.

### Step 6: Report

```
## Branch Consolidation Complete

### Absorbed
- `work/striker/2026-03-20` — no unique commits (already merged)
- `feature/foo` — 3 commits cherry-picked into current branch

### Skipped (superseded)
- `work/striker/2026-03-19` — 1 commit (stale experiment data, current branch has newer version)

### Deleted
- Local: work/striker/2026-03-20, work/striker/2026-03-19
- Remote: origin/work/striker/2026-03-20, origin/work/striker/2026-03-19, origin/feature/foo

### Left Untouched (other owners)
- `feature/bar` (alice@co.com) — not ours, skipped

### Merged to Main
- PR: {url}
- Now on: main @ {sha}
- All of *our* branches cleaned — only main + other owners' branches remain
```

## Edge Cases

**If on main with no other branches:** Abort early — nothing to consolidate.

**If the current branch is behind main:** Merge main into the current branch first before absorbing other branches — ensures the final state includes everything.

**If a stale branch has diverged significantly:** Prefer merge over cherry-pick. If the merge has extensive conflicts, flag to the PM rather than resolving silently — the PM may want to inspect before committing.

**If remote branches have no local counterpart:** Fetch them first (`git fetch origin <branch>`) to inspect their commits, then delete the remote after inspection.

## What This Does NOT Do

- **Rebase** — merges and cherry-picks only. Rebasing rewrites history and adds risk for no benefit in a cleanup operation.
- **Touch other repos** — scoped to the current repository only.
- **Delete main** — main is always preserved as the merge target.
- **Force-delete branches** — uses `-d` (safe) by default. `-D` only with explicit PM approval.
- **Touch other people's branches** — only branches where the tip commit author matches the current user's `git config user.email` are candidates. Everyone else's branches are reported but never modified or deleted.
