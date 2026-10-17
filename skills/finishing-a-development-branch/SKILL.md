---
name: finishing-a-development-branch
description: "Presents merge, PR, or cleanup options once tests pass."
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Finishing a Development Branch

**Announce at start:** "I'm using the coordinator:finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, check whether test evidence already covers this branch.** If this session already has fast-tier or targeted-test evidence for the current diff, report it as-is and move to Step 2 — this step is not a cadence gate that reruns tests on every branch finish.

If no such evidence exists, prefer targeted tests covering the touched files over the fast tier. Reaching for the fast tier means reaching for the grant first — this skill is not on the implicit-grant ceremony list (`/workday-complete`, `/workweek-complete`, `/merging-to-main`), so check `tier-u-grant-cli check` first (PowerShell: the `.exe` launcher, Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`). Exit 0 = granted: run `coordinator-resolve-validation-cmd --fast` (rc 0 = run the result and capture its exit code; rc 2 = no `fast_test_cmd` — skipped, not failed). Exit 1 halts: ask the PM for a session grant, run under a ceremony that holds the implicit grant, or report `Validation: skipped`. A full-suite gate belongs to the downstream merge ceremony. A chained `fast_test_cmd` (`a && b`, pipe) is denied by the invocation guard — configure a single command with a wrapper script.

**Tests failing:** show the failures, say "Tests failing (<N> failures). Must fix before completing; cannot proceed with merge/PR until tests pass," and stop. **Tests passing:** continue.

### Step 2: Determine Base Branch

`git merge-base HEAD main`, falling back to `git merge-base HEAD master`; or ask: "This branch split from main - is that correct?"

### Step 3: Present Options

Present exactly these 3 options, with no added explanation:

```
Implementation complete. What would you like to do?

1. Merge to main via PR (recommended)
2. Create a Pull Request (manual merge later)
3. Keep the branch as-is (I'll handle it later)

Which option?
```

**No "discard" option:** if the PM wants to throw the work away they say so, through deliberate destructive-action confirmation, not a numbered menu.

**No worktrees.** Worktrees are forbidden — work happens on the active workstream branch. An
override exists but requires explicit PM permission via the EM. A stray worktree found in Step 5
is debris to remove, not state to preserve.

### Step 4: Execute Choice

#### Option 1: Merge to main via PR (Recommended)

Invoke the `merging-to-main` skill: it creates a PR, confirms local validation, and merges on
success. The branch is deleted only when its remote tip is an ancestor of the base
(`merging-to-main` Step 7).

#### Option 2: Create a Pull Request (manual merge later)

Push (`git push -u origin <feature-branch>`) and create the PR with `gh pr create`; do NOT merge.
`gh pr create --body` bypasses GitHub's own template fill, so compose the body yourself from the repo's `.github/pull_request_template.md`: read it, fill every section, drop `## Demo path` when nothing is user-visible, and don't leave its guidance comments in. Where the repo has no copy, use the plugin's `templates/github-pull-request-template.md`.

#### Option 3: Keep the branch as-is

Don't merge, don't create a PR. Report: "Keeping branch <name>."

#### Perforce submit slot (repos with `vcs_mirror: p4` only)

A git-only repo (no `vcs_mirror: p4` in `coordinator.local.md` frontmatter) skips this subsection.
In a p4-mirrored repo, push already shelved the session's pending changelist (engine behavior;
this skill neither reconciles nor shelves). Offer a fourth option: "submit the session changelist."

1. Call the engine op `p4.session_state` for this session, passing `repo_key` read from
   `p4_repo_key` in `coordinator.local.md` frontmatter — the op takes it and never derives it, and
   neither do you: no `p4_repo_key` beside the marker means the workspace predates the key, so say
   so and stop rather than guessing one. Never read the session `meta.json` yourself. No
   `p4_change` in the result → nothing to submit; say so.
2. Read the submit slot, `p4_submit_tool`, from `coordinator.local.md` frontmatter. Shape and
   failure modes: `coordinator/contract/p4-provider-fragment.md` § Validation and failure.
3. Slot filled → call that fully qualified MCP tool (`mcp__<server>__<tool>`) as a **direct MCP
   tool call**, passing `changelist` as the integer parsed from `p4_change` (a decimal string) and
   `repo_key` as the same string from step 1 — the provider's identity keys are all named
   `p4.<repo_key>.*` — never through `execute_domain_tool` or any other by-name dispatcher. The
   provider's own human-confirmation prompt is the gate; this skill adds none and never
   pre-approves. Submit renumbers the changelist — afterwards report the number the provider
   returned, never `p4_change`.
4. Slot empty → state "no Perforce submit provider installed"; the shelf is the hand-off and a
   human submits it in P4V or Swarm. Never run `p4 submit` via Bash/PowerShell — the p4 verb fence
   denies it.

### Step 5: Remove Any Stray Worktree

If `git worktree list` shows the current branch (`git branch --show-current`) in a worktree,
remove it (`git worktree remove <worktree-path>`) whichever option was chosen: worktrees are
forbidden, so any found here is stray debris.

## Red Flags

**Never:** proceed with failing tests; merge without verifying tests on the result; offer discard
as a numbered option; force-push without explicit request. **Always:** verify tests first; present
exactly 3 options.

## Integration

**Called by:** the executor-dispatch workflow after all tasks complete; the PM directly when a
branch is ready for disposition.

**Not called by `/execute-plan`:** it finalizes and offers `/workstream-complete` but does **not**
chain into branch disposition, which reaches the keyword-gated `/merging-to-main`; disposition is
a separate, PM-invoked decision.
