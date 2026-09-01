---
name: consolidate-git
description: "Cleans up branch sprawl — consolidates and prunes stale branches."
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Consolidate Git — Branch + Worktree Cleanup

## Overview

Reduce branch and worktree sprawl to a single clean workstream branch. Every local and remote
branch AND every worktree is inventoried for you — ownership, unique-commit evidence, and the
absorb/delete sequencing. Unconditional directives (no-unique-commit deletes, clean-worktree
removal, prune, fetch-prune) execute as soon as you reach them. What is left is yours to decide:
supersession verdicts on branches with unique commits, conflict resolution, the locked/dirty
worktree pause, and the merge-ready call.

**Consolidation and shipping are separate decisions — this skill never merges to main.** It
leaves the repo with one current branch holding all of *my* in-flight work, no leftover sibling
branches, no stale worktrees. Whether that branch is ready to ship is `/merging-to-main`'s call,
made after this skill reports and optionally offered via the `merge-ready` judgment point.

**Announce at start:** "I'm using the coordinator:consolidate-git skill to consolidate branches
and worktrees into the current branch. Merge to main is a separate step."

## Compute the Inventory

**On a PowerShell host, use the `.exe` launcher through the call operator** (Shape W), never the
`${...}` POSIX-shell form shown below. Ladder and shapes: `snippets/resolve-coordinator-bin.md`.

`consolidate-assemble brief` (per `snippets/resolve-coordinator-bin.md`)
returns the current-user + branch inventory (ownership category per branch and worktree),
unique-commit evidence per stale branch, absorb/delete directives, and the judgment points below.
It is READ-ONLY — every mutating action surfaces as a directive or a judgment point, never fires
silently.

**Worktrees are not exempt.** A worktree whose branch tip is already reachable from main or the
current branch is stale state, not active work — a lock from a long-finished isolation run is a
stale signal, not a veto, and its removal is proposed like any other stale branch. A
worktree with uncommitted changes is a genuine pause, not an auto-fire.

**Only branches/worktrees owned by the current git identity are candidates.** Everyone else's
are reported under `gates` but never touched.

## Resolve the Judgment Points

Each judgment point below carries its own evidence and per-option guidance in the decision
object — decide from it, never invent a verdict the evidence doesn't support.

**`j-absorb-<branch>` — supersession verdict.** You get the unique-commit list plus a
`git show --stat` per commit; nothing labels a commit "superseded" for you. Before
choosing **skip**, name the file(s) on the current branch that supersede each commit — "current
branch has a newer version" without a path is a guess, not evidence, and any commit touching a
file the current branch never touched must be absorbed, not skipped. Choosing **absorb** applies
the computed cherry-pick/merge selection (cherry-pick for small counts, merge for large)
via the closed CLI table — you are not hand-choosing the git verb.

**A ref can exist to hold objects rather than changes — the unique-commit count cannot see it.**
A `backup/`- or `pre-*`-named ref is doing its job precisely when it is identical to its source,
so faithfulness reads here as pure redundancy. Never resolve one on unique-commit count alone:
name what it was cut to insure against, and if that is unknown, report it and leave it. "Merged
into HEAD" and "safe to lose" are different predicates — the gap between them is a ref whose
objects live on no pushed remote.

**Conflict resolution (surfaces mid-directive-apply, not as a separate judgment point).**
Inspect conflicting files — if the current branch already supersedes the change, abort and skip,
noting it in the report; if genuinely needed, resolve and continue. Do not force through
conflicts blindly — each one is a signal that needs inspection, not a merge-strategy retry.

**Post-absorb re-verify on conflict-resolved shared infra.** Last-writer-wins silently reverts
edits when both sides touched the same hunk and the conflict was resolved naively. For any file
with a known specific change that went through conflict resolution, confirm the canonical phrase
from that change is still present in the result; if missing, re-apply it with a follow-up commit.
Weight this check toward shared files — plugin internals, shared scripts, project-wide configs —
touched by multiple branches in the consolidation.

**`j-worktree-dirty-<path>`.** Worktrees are forbidden — an override exists but requires explicit
PM permission via the EM — so a dirty worktree found here is stray debris to drain and remove,
never state to keep. The question is never "keep or remove" — it's "how do we safely get rid of
this without destroying uncommitted work." Dirty worktrees are surfaced, never removed silently.
**rescue** saves the uncommitted state (stash it out or commit it to a throwaway branch) before
removing the worktree, when the changes look worth keeping; **proceed** discards the uncommitted
state along with the worktree, when it's genuinely disposable. Default posture is pause for a
decision, not silent proceed — a lock is stale-signal, dirt is not.

**`j-behind-main`.** Fires only when the current branch is behind main. **merge-main-first**
ensures the final state includes everything before absorbing; **proceed-anyway** is the branch's
call if a stale main is expected.

**`j-merge-ready`.** Fires whenever any directive or judgment point exists. Offer
**chain-to-merge** only when the branch genuinely looks ship-ready (finished, reviewed work,
consolidation didn't leave unresolved skips or PM-flagged dirty worktrees, framing suggested
shipping intent) — otherwise **stop-here** is the default. Never turn this into a question that
ratifies default behavior; phrase chain-to-merge as a recommendation with the evidence behind it.

## Report

Summarize per the `branches`/`worktrees` gates: absorbed, skipped (with the
superseding evidence named), deleted (branches + worktrees), and left untouched (other owners).
Close with current branch, ahead-of-main count, and the merge-ready disposition.

## Edge Cases

**On main with no other branches:** abort early — nothing to consolidate.

**Remote branches with no local counterpart:** fetch first, so their commits are inspected
before a remote delete is proposed.

## What This Does NOT Do

- **Merge to main.** Consolidation lands everything on the current branch and stops; shipping is
  `/merging-to-main`, invoked separately by the PM (optionally recommended via `j-merge-ready`).
- **Rebase** — merges and cherry-picks only. Rebasing rewrites history for no benefit in a
  cleanup operation.
- **Touch other repos** — scoped to the current repository only.
- **Delete main** — always preserved as the merge target.
- **Force-delete branches** — safe delete (`-d`) only; `-D` needs explicit PM approval if `-d`
  refuses.
- **Touch other people's branches or worktrees** — ownership is tip-commit-author-scoped; every
  non-owned branch/worktree is reported, never modified.
