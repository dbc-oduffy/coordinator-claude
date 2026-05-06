# Daily-branch discipline

> **The rule.** In any project's main checkout, the active branch is **either** today's `work/{machine}/{YYYY-MM-DD}` **or** `main` (read-only). Nothing else. Real-time enforcement; no `/workday-complete`-time cleanup.

> **The shape.** The daily branch is a **shared bus for every concurrent EM session on this machine** — not a single-session workspace. Multiple sessions committing in parallel is the default; sibling commits and out-of-scope dirty files belong to peer sessions, not to contamination. Scoped-staging (`coordinator-safe-commit --scope-from`, runtime overlap gate) is the everyday discipline that makes shared-bus safe.

## Why

Postmortem source: `X:/project-rag/archive/2026-05-05_branch-sprawl-postmortem.md`.

The anti-pattern was mechanical:

```
git checkout -b feature/advisory-2026-05-05   # create sibling branch
git stash push -u                             # park WIP on it
git checkout -                                # back to daily
```

Result: an empty branch (zero commits) and a dangling stash labelled with that branch. `git branch -d` later cleans the branch but `refs/stash` is a separate ref namespace — the stash survives every consolidation, accumulating across weeks. Multiple sibling stashes referencing long-dead branches is the silent compounding mechanism.

The chokepoint is step 1. Block off-daily branch creation/switch and the rest cannot happen.

## Enforcement surfaces

Two contact-points (see CLAUDE.md tripwire):

1. **`block-off-daily-branch.sh`** — PreToolUse Bash hook. Catches `git checkout`, `git switch`, `git branch -m/-M/--move/-c/-C/--copy`, `git stash branch`, `git worktree add`, **and `git commit`** (Check 6, consolidated here from `validate-commit.sh` per Patrik F11 review). Allow-list: today's daily (case-insensitive) and `main`. Emits JSON `permissionDecision: "deny"` per the [PreToolUse contract](../../plugins/coordinator-claude/coordinator/docs/pretooluse-deny-contract.md). `validate-commit.sh` Checks 1-5 remain there for commit-content validation; Check 6 was moved here.
2. **Doctrine** — CLAUDE.md § Concurrent-EM Git Operations, first bullet. Authoritative reference for the rule.

## Supported "park WIP" recipes

The hook does **not** ban stash. It bans creating a sibling branch first. Park WIP via:

- **Commit on the daily.** Intentionally messy commits are fine on `work/*` branches — they're quick-saves, not history.
  ```
  git add -- <paths> && git commit -m "WIP: <subject>"
  ```
- **Stash on the daily.** Do not change branches first.
  ```
  git stash push -u -m "<subject>"
  ```

The unsupported move (and the structural reason this page exists):

```
git checkout -b feature/X && git stash push -u && git checkout -
```

This is what produces empty branches and orphan stashes by construction. The hook denies step 1.

## Override

`COORDINATOR_OVERRIDE_BRANCH=1` — bypasses both the PreToolUse hook and Check 6 for one Bash call. Logged to:

- `.git/coordinator-sessions/{session_id}/branch-discipline.log` (per-session denials)
- `.git/coordinator-sessions/_branch-overrides/overrides.log` (override invocations)

Optional companion: `COORDINATOR_OVERRIDE_BRANCH_REASON="<text>"` — written alongside the override entry. Encouraged.

Inline-only — never export. The skills that legitimately need the override set it on the single offending command:

- `/workday-start` — creates today's daily (`git checkout -b work/{machine}/{TODAY}`).
- `/merge-to-main` — may operate against integration branches during the merge ceremony.
- `/consolidate-git` — by definition switches across branches to absorb commits.

If you're tempted to export the variable in your shell, stop and ask: am I building a fourth skill that needs it? Add it to the doctrine tripwire and to this page.

## Failure modes the hook catches

Mapped to the postmortem patterns:

| Postmortem pattern | Caught by | How |
|---|---|---|
| Pattern 2 — checkout-stash-checkback anti-pattern | PreToolUse hook | Denies the `checkout -b feature/X` at step 1 |
| Pattern 3 — orphan stashes outlive deleted branches | Eliminated structurally | If non-daily branches never exist, stashes can't reference them |
| Stale-day inheritance (yesterday's branch carried into today) | Check 6 | Denies the next commit; prompts `/workday-start` |
| Pattern 4 — speculative `feature/<topic>-<date>` naming from planning prose | PreToolUse hook | The branch can't be created, so the cosmetic naming has nowhere to land |

## Midnight crossings

The date used by both the hook and the commit-time check is computed in **local time** via `date +%Y-%m-%d`. A session that starts before midnight and runs past it will compute a different daily branch name after midnight than it did at start.

**What happens:** the first `git commit` after midnight is denied because the current branch is now "yesterday's daily." The first `git checkout` to a different branch is similarly denied.

**Recovery:** run `/workday-start` to roll the daily branch forward. It creates `work/{machine}/{new-date}`, merges the overnight work from the previous day's branch, and the hook is satisfied for the rest of the new session.

**In the deny message:** the hook says "If you've crossed midnight in a long session, run /workday-start to roll the daily forward."

**No grace window** — the PM's mandate is "use the daily for the day." Sessions that span midnight are expected to use `/workday-start` to advance. A configurable grace window is a future option; the current design is strict.

## Edge cases the hook does NOT catch

- **`git checkout <sha>` / `git checkout <tag>`** — detached HEAD. Allowed (not a branch op). Commit-time check catches any subsequent commit, since the resulting `HEAD` is not a branch ref.
- **`git checkout -- <path>`** — file restore. Allowed (no branch involved).
- **`git checkout origin/<remote>`** — produces detached HEAD. Allowed; same commit-time fallback.
- **`git checkout --orphan <name>`** — the hook now checks the orphan name and denies if it is not today's daily or main. `--orphan` onto an allowed name is permitted.
- **Linked worktrees (already created)** — the hook exits silently when run inside a `worktrees/` git-dir. Doctrine bans worktree creation; the audit catches existing ones separately. The hook's `worktree add` deny prevents new ones.
- **Compound commands beyond the first git op** — the hook inspects the first `git <branch-op>` it finds. Subsequent ops in `git checkout -b foo && git checkout -b bar` are not separately validated, but step 1 already denies, so step 2 doesn't run.
- **`git -C <path>` / `cd <path> && git ...`** — cross-repo forms are denied outright when a branch-mutating subcommand follows. Use `COORDINATOR_OVERRIDE_BRANCH=1` for legitimate cross-repo work.

## See also

- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — sibling enforcement on commit *content* (which files); this page enforces commit *location* (which branch). The two hooks are siblings on the same PreToolUse Bash matcher.
- [`pretooluse-deny-contract.md`](../../plugins/coordinator-claude/coordinator/docs/pretooluse-deny-contract.md) — JSON deny mechanics.
- `archive/2026-05-05_branch-sprawl-postmortem.md` (project-rag repo) — original incident.
- `~/.claude/plans/2026-05-05-daily-branch-discipline-hook.md` — plan & rollout for this enforcement.
