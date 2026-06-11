---
name: consolidate-git
description-budget: 250
description: "Cleans up branch sprawl. Triggers: consolidate branches, clean up branches, stale branches, merge all branches."
version: 1.0.0
---

# Consolidate Git — Branch + Worktree Cleanup

## Overview

Reduce branch and worktree sprawl to a single clean workstream branch. Inventories all local and remote branches AND all worktrees, absorbs any unique commits into the current branch, deletes stale branches, and removes stale worktrees (including locked ones whose work has been absorbed).

**This skill does NOT merge to main by default.** Consolidation and shipping are separate decisions. The goal here is to leave the repo with one current branch holding all of *my* in-flight work, no leftover sibling branches, no stale worktrees. Whether that branch is ready to ship to main is a separate judgment for `/merge-to-main`, made after this skill reports. At the end, the EM MAY ask the PM whether to chain into `/merge-to-main` if the consolidated branch looks merge-ready — but the default exit is "consolidation complete, branch is yours."

**Worktrees are not exempt.** A worktree whose branch tip is already absorbed into main (or the current branch) is *stale state*, not active work — the branch lock is a stale signal, not a permanent reservation. The skill removes such worktrees by default. Worktrees with genuine unique commits proceed through the same absorb-or-skip evidence gate as any other branch.

**Announce at start:** "I'm using the coordinator:consolidate-git skill to consolidate branches and worktrees into the current branch. Merge to main is a separate step."

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

**Only branches categorized as "mine (stale)" proceed to Steps 2–5.** Other people's branches are reported but never touched.

### Step 1.5: Inventory Worktrees

Enumerate all worktrees and join against the branch inventory. A worktree is just another checkout of a branch — its branch is subject to the same absorb-or-skip logic as any other branch. The only special handling: the worktree directory itself must be removed before the branch can be deleted.

```bash
git worktree list --porcelain
```

For each worktree (excluding the primary `.git`-owning checkout):

1. Record the worktree path, branch, HEAD sha, and lock state (the `locked` line in porcelain output).
2. Treat the branch the same way as any local branch in Step 1c — owner check by tip-commit author, category by reachability:
   - Branch tip reachable from `origin/main` OR from the current branch → **stale (worktree absorbed)** → candidate for removal.
   - Branch tip has unique commits → **stale (worktree has unique work)** → goes through Steps 2–4 like any other branch.
   - Tip author is not me → **other's worktree — skipped** (report only).

Add a Worktrees section to the inventory table:

```
### Worktrees
| Path | Branch | Locked | Owner | Category |
|------|--------|--------|-------|----------|
| .claude/worktrees/agent-a07… | worktree-agent-a07… | yes | me | stale (absorbed into main) |
| .claude/worktrees/agent-aec… | worktree-agent-aec… | yes | me | stale (absorbed into main) |
```

**Locked is not a veto.** A lock from a long-finished isolation run is exactly the state this skill exists to clean up. If the branch is absorbed, the worktree gets removed in Step 5 with `--force` after the lock is cleared (`git worktree unlock <path>`). If the worktree has uncommitted changes (`git -C <path> status --porcelain` non-empty), surface them to the PM before removing — that is genuine in-flight work and warrants pause.

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
- **Has unique commits** — proceeds to Step 3 (inspection), then Step 4 (verdict)

**Do NOT label a branch "superseded," "stale-experiment," "already-applied," or any other verdict at this step.** The only categories Step 2 emits are *no unique commits* and *has unique commits — count N*. Anything else is a Step 4 verdict and requires Step 3 evidence first.

### Step 3: Inspect Unique Commits (Evidence Gate)

**Hard gate: no verdict may be emitted before this step's output is on the page.**

For each branch flagged "has unique commits" in Step 2, run BOTH:

```bash
git log --oneline <current-branch>..<stale-branch-or-origin/...>
git show --stat <each-commit-sha>
```

Then emit an inspection table to the PM **before** proposing any absorb/skip decision:

```
### Inspection: <branch-name> (<N> unique commits)
- <sha> <subject> — files: <path1>, <path2> (+X/-Y)
- <sha> <subject> — files: <path1> (+X/-Y)
```

For commits whose diff is non-trivial (>~20 lines or touches shared infra / plugin internals / configs), also run `git show <sha>` and quote the load-bearing hunks in 1–3 lines.

**Self-check before moving to Step 4 — answer each in one sentence, in the message:**
1. Have I actually run `git show --stat` (or `git show`) on every listed sha? (If no: stop, run it.)
2. For each commit, what file(s) on the current branch supersede it, named by path? (If "current branch has a newer version" without a path, that's a guess, not evidence.)
3. Are any of these commits touching files the current branch never touched? (If yes: not superseded — must absorb.)

A "superseded" verdict that names no superseding path on the current branch is a doctrine violation — go back and look.

### Step 4: Absorb or Skip (Verdict)

Only after Step 3's inspection table and self-check are on the page, for each branch:

1. **Choose absorption strategy (inline override required on each git op that touches off-daily branches):**
   - **Cherry-pick** (default for 1-3 commits):
     ```bash
     # Review: patrik F1 — inline override required; cherry-pick from stale branches
     # is an off-daily operation caught by block-off-daily-branch.sh.
     COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="consolidate-git step 3 cherry-pick from <stale-branch>" \
       git cherry-pick <commit> --no-edit
     ```
   - **Merge** (for branches with many commits):
     ```bash
     COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="consolidate-git step 3 merge <stale-branch>" \
       git merge <stale-branch> --no-edit
     ```
3. **If conflicts arise:**
   - Inspect the conflicting files — determine if the current branch already supersedes the change
   - If superseded: abort (`git cherry-pick --abort` or `git merge --abort`) and skip — note this in the report
   - If genuinely needed: resolve conflicts, then continue
   - Do NOT force through conflicts blindly — each conflict is a signal that needs inspection

**Report each absorption decision to the PM:**
> "Branch `work/striker/2026-03-20` has 2 unique commits — both are experiment data snapshots already superseded by current branch. Skipping."

or:

> "Branch `feature/auth-rewrite` has 5 unique commits with real code changes. Cherry-picking into current branch."

### Step 5: Delete Stale Branches and Worktrees

After all unique commits are absorbed (or explicitly skipped), remove stale worktrees first (a branch checked out in a worktree cannot be `git branch -d`'d), then delete the branches.

**5a. Remove stale worktrees:**

For each worktree categorized as stale in Step 1.5 (and not flagged as having uncommitted changes the PM elected to preserve):

```bash
# Clear the lock if present — the lock is leftover isolation-mode state, not a live reservation.
git worktree unlock <path> 2>/dev/null || true

# Remove the worktree. --force is needed because locked/checked-out worktrees
# refuse plain `git worktree remove`. Safe here: we already verified the branch
# tip is reachable from main / current and the working tree is clean (or PM-approved).
git worktree remove --force <path>
```

After removing all stale worktrees, prune any administrative remnants:

```bash
git worktree prune
```

**5b. Delete branches:**

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

### Step 6: Post-Absorb Re-Verify Shared Infra (geneva T1.7)

When conflicts were resolved during cherry-pick or merge in Step 4 — especially on shared files (plugin internals, shared scripts, configs) — re-verify that the absorbed changes actually survived.

**Why this matters:** Last-writer-wins silently reverts edits when both sides touched the same hunk and the conflict was resolved naively. An absorption that "succeeded" may have silently dropped changes from the source branch.

**Verification steps:**

1. For each file with a known specific change:
   ```bash
   git show HEAD:<file-path> | grep -F "<canonical phrase from your change>"
   ```
2. If a canonical phrase is missing, your change was overwritten. Re-apply it with a follow-up commit.
3. This is especially important for `~/.claude/` plugin files and project-wide config files touched by multiple branches in the consolidation.

### Step 7: Report

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
- Worktrees: .claude/worktrees/agent-a07… (branch absorbed into main), .claude/worktrees/agent-aec… (branch absorbed into main)

### Left Untouched (other owners)
- `feature/bar` (alice@co.com) — not ours, skipped

### Current State
- On branch: `work/striker/2026-03-23` @ {sha}
- Ahead of `origin/main` by N commits — not merged (consolidation only)
- All of *my* sibling branches and worktrees absorbed or removed; only main + other owners' branches remain
```

### Step 8: Optional Merge-to-Main Prompt (EM Judgment)

After reporting, the EM MAY ask the PM whether to chain into `/merge-to-main` — but only when the consolidated branch looks merge-ready. Default exit is to stop here.

Skip the prompt when:
- The current branch is already main (nothing to merge).
- Consolidation produced unresolved skips, dirty worktrees flagged for PM review, or conflicts that warranted pause.
- The branch is mid-workstream (recent commits suggest active development, not a ready checkpoint).

Offer the prompt when:
- Consolidated branch contains finished, reviewed work and would have been a `/merge-to-main` candidate before consolidation started.
- The PM's framing for invoking consolidation suggested shipping intent.

Phrase as a recommendation, not a question to ratify default behavior:

> "Consolidated branch looks merge-ready (N commits ahead of main, all absorbed work passes review). Want me to chain into `/merge-to-main`?"

Otherwise: stop. Merge to main is a separate invocation.

## Edge Cases

**If on main with no other branches:** Abort early — nothing to consolidate.

**If the current branch is behind main:** Merge main into the current branch first before absorbing other branches — ensures the final state includes everything.

**If a stale branch has diverged significantly:** Prefer merge over cherry-pick. If the merge has extensive conflicts, flag to the PM rather than resolving silently — the PM may want to inspect before committing.

**If remote branches have no local counterpart:** Fetch them first (`git fetch origin <branch>`) to inspect their commits, then delete the remote after inspection.

## What This Does NOT Do

- **Merge to main** — consolidation lands everything on the current branch and stops. Shipping is `/merge-to-main`, invoked separately by the PM (optionally suggested by the EM in Step 8 when the branch looks merge-ready).
- **Rebase** — merges and cherry-picks only. Rebasing rewrites history and adds risk for no benefit in a cleanup operation.
- **Touch other repos** — scoped to the current repository only.
- **Delete main** — main is always preserved as the merge target.
- **Force-delete branches** — uses `-d` (safe) by default. `-D` only with explicit PM approval.
- **Touch other people's branches or worktrees** — only branches/worktrees where the tip commit author matches the current user's `git config user.email` are candidates. Everyone else's are reported but never modified or deleted.
- **Remove worktrees with uncommitted changes silently** — dirty worktrees are surfaced to the PM. The default for stale-but-clean (including locked) is removal; the default for dirty is pause.
