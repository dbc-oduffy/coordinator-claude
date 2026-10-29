---
name: consolidate-git
description: "Absorb every branch into the current one by true merge, then prune."
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Consolidate Git — Branch + Worktree Cleanup

## Overview

Consolidate every branch's commits into the current branch so none is orphaned. Every branch and worktree
is inventoried for you (ownership, unique-commit evidence, absorb/delete sequencing).
Unconditional directives (no-unique-commit deletes, clean-worktree removal, prune) execute as you
reach them. Yours to decide: supersession verdicts, conflict resolution, the locked/dirty worktree
pause, and the merge-ready call.

**Consolidation and shipping are separate decisions — this skill never merges to main.** It leaves
one current branch holding every branch's work, no orphaned commits, no stale worktrees;
shipping is `/merging-to-main`'s call (optionally offered via `merge-ready`).

**Announce at start:** "Using coordinator:consolidate-git to consolidate branches and worktrees
into the current branch; merge to main is separate."

## Compute the Inventory

**On a PowerShell host, use the `.exe` launcher through the call operator** (Shape W), never the
`${...}` POSIX-shell form. Ladder and shapes: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

`consolidate-assemble brief` returns the current-user + branch inventory (ownership category per
branch and worktree), unique-commit evidence per stale branch, absorb/delete directives, and the
judgment points below. It is READ-ONLY — every mutating action surfaces as a directive or a
judgment point, never fires silently.

**Worktrees are not exempt.** One whose tip is reachable from main or the current branch is stale
(a lock is a stale signal, not a veto); a dirty one is a genuine pause.

**Every branch on every box, any owner, is a candidate** — local, remote-only, and `cloud-session`
(tip authored by `noreply@anthropic.com`; an `Operator:` trailer equal to your git email makes it
`mine-stale`). The point is no orphaned commits: all work across the boxes lands in the current
branch, which is why this pairs with `/merging-to-main`. A branch the brief withholds under `gates`
as another owner's is still absorbed; only `refs/preserve/*` is never touched.

## Resolve the Judgment Points

**Re-verify against origin before the first mutating action.** `brief` is a snapshot; a concurrent
`git reset` can fork local from origin invisibly to a tree-diff. If either side holds a commit the
other lacks (`<branch>` vs `origin/<branch>`), the brief is stale — re-run it before absorbing,
deleting, or merging.

**`consolidate-assemble apply` executes with no preview** — every unconditional directive (deletes,
worktree removals, prune) fires. Read `brief` first and pass `--decisions-file`; never run a bare
`apply` to see what it would do. A commit that looks orphaned mid-run: wiki § Consolidate-git.

Each judgment point carries its own evidence and per-option guidance in the decision object —
decide from it, never invent a verdict the evidence doesn't support.

**`j-delete-<branch>` — zero-unique-commit `cloud-session` branch.** **delete** once its tip is
reachable from main or the current branch and it heads no open PR, which you check with `gh pr list`.
Otherwise **keep**. Before any remote delete, run `git merge-base --is-ancestor <remote tip> origin/<base>`; "a PR merged" is not evidence. A tip with commits outside the base is kept; report its count and SHA. `mine-stale` branches with zero unique commits delete unconditionally; a
`cloud-session` branch always gets a verdict, because its owner is inferred, not proven.

**`j-absorb-<branch>` — supersession verdict.** You get the unique-commit list plus a
`git show --stat` per commit; nothing labels a commit "superseded" for you. Before choosing
**skip**, name the file(s) on the current branch that supersede each commit — "current branch has
a newer version" without a path is a guess, and any commit touching a file the current branch never
touched must be absorbed. **absorb** is a true `git merge` per branch, never a cherry-pick, so
each source tip becomes reachable. **Superseded or reverted on purpose** is not **skip**: run
`git merge -s ours <branch>` with the superseding sha in the message — its commits stay reachable
and the dead code does not return. A verdict never deletes a branch whose tip is unreachable from
the current branch.

**Delete gate.** Before deleting any local or remote branch, confirm no live session on any box has
it checked out or is pushing to it. A live branch is absorbed, not deleted.

**Test gate.** Run the ratchet or targeted tests after the absorbs and before `/merging-to-main`; a
red from an absorb blocks the merge.

**keep.** A branch the PM wants left alive (e.g. committed to within N hours) is neither absorbed
nor deleted: **skip** is a delete verdict, so leave that point unresolved (no directive depending
on it fires) and report the branch as `kept` with the PM's stated reason.

**A ref can exist to hold objects rather than changes.** Never resolve a `backup/`- or
`pre-*`-named ref on unique-commit count: name what it insures against, and if unknown, report and
leave it. "Merged into HEAD" is not "safe to lose".

**Conflict resolution (surfaces mid-directive-apply).** If the current branch already supersedes
the change, abort and skip (note it); else resolve and continue. Never force through conflicts.

**Post-absorb:** confirm a conflict-resolved shared file kept its canonical phrase; re-apply if lost.

**`j-worktree-dirty-<path>`.** Worktrees are forbidden, so a dirty one is stray debris to drain,
never state to keep; the question is how to remove it without destroying uncommitted work. Surface
it, never remove silently. **rescue** saves the state (stash or throwaway-branch commit) before
removal; **proceed** discards it when genuinely disposable. Default is pause for a decision.

**`j-behind-main`.** Fires only when the current branch is behind main. **merge-main-first**
ensures the final state includes everything before absorbing; **proceed-anyway** if a stale main
is expected.

**`j-merge-ready`.** Fires whenever any directive or judgment point exists. Offer
**chain-to-merge** only when the branch looks ship-ready (finished, reviewed, no unresolved skips
or flagged dirty worktrees) — otherwise **stop-here**. Phrase it as a recommendation with evidence.

## Report

Per the `branches`/`worktrees` gates: absorbed, skipped (superseding evidence named), kept,
deleted, left untouched (`refs/preserve/*` only); then current branch, ahead-of-main count, merge-ready disposition.

## Edge Cases

**On main with no other branches:** abort early — nothing to consolidate.

**Remote branches with no local counterpart:** fetch first, so their commits are inspected
before a remote delete is proposed. Cross-device reconciliation: wiki § Consolidate-git.

## What This Does NOT Do

- **Merge to main.** Consolidation stops on the current branch; shipping is `/merging-to-main`,
  invoked separately by the PM (optionally recommended via `j-merge-ready`).
- **Rebase or cherry-pick** — true merges only.
- **Touch `refs/preserve/*`.**
- **Touch other repos** — scoped to the current repository only.
- **Delete main** — always preserved as the merge target.
- **Force-delete branches** — safe delete (`-d`) only; `-D` needs explicit PM approval if `-d`
  refuses.
- **Delete a branch it has not absorbed** — ownership decides reporting, never exclusion.
