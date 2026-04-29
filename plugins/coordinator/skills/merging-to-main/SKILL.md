---
name: merging-to-main
description: Use when work on a branch is ready to merge to main — drafts release notes, creates PR, waits for CI, merges, cleans up. Always emits release-notes (even for tiny merges) so downstream consumers can see what changed.
argument-hint: "[--force]"
version: 1.1.0
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

### Step 1.5: Draft Release Notes (mandatory, every merge)

Every merge to `main` gets a release-notes summary — even small ones (`v4.1.422`-style patch granularity). The reasoning: with LLM authoring overhead near-zero, omitting consumer-facing notes is a cost we impose on downstream readers (other agents, future-you, marketplace consumers, anyone pulling the publish repo). Don't do that.

This step ALWAYS runs — no opt-out. It is the most consumer-visible artifact of the merge.

1. **Inventory the merge:**
   ```bash
   COMMITS=$(git log main..HEAD --oneline)
   COMMIT_COUNT=$(git rev-list --count main..HEAD)
   CHANGED_FILES=$(git diff --name-only main..HEAD)
   STATS=$(git diff --shortstat main..HEAD)
   ```

2. **Group changes by impact category** (don't mirror commit-by-commit; group by what a reader cares about):
   - **Added** — new features, new files, new capabilities
   - **Changed** — behavior changes, refactors with user-visible effect, API changes
   - **Fixed** — bug fixes, regression repairs
   - **Deps** — dependency bumps, CVE remediation, transitive updates
   - **Internal** — refactors with no user-visible effect (omit if trivial; keep if substantive)

   Single-commit dependency-bump merges still get a one-line note (e.g. _"Deps: bump express past path-to-regexp CVE; transitive only, no API surface change."_). Don't skip "trivial" merges — that's how CHANGELOGs rot.

3. **Detect repo-root `CHANGELOG.md`:**
   ```bash
   if [ -f CHANGELOG.md ]; then HAS_CHANGELOG=1; else HAS_CHANGELOG=0; fi
   ```
   - If present: this repo has external consumers and an established notes convention. Always update it.
   - If absent: do NOT auto-create. Embed notes in PR body only.

4. **Determine version bump suggestion** (advisory — surfaced for PM, never auto-applied):
   - Read `package.json` `version` field (or equivalent for the repo's ecosystem).
   - Suggest based on diff scope:
     - **patch** — bug fixes, dep bumps, internal refactors
     - **minor** — new backwards-compatible features
     - **major** — breaking changes, removed APIs
   - If unsure between two levels, suggest the lower one and let the PM override.

5. **Draft the entry.** Format:
   ```markdown
   ## v{suggested-version} — {YYYY-MM-DD}

   ### Added
   - {one-line bullet per logical addition}

   ### Changed
   - {one-line bullet per logical change}

   ### Fixed
   - {one-line bullet per fix}

   ### Deps
   - {one-line bullet per dep change, including CVE refs if applicable}

   ### Internal
   - {one-liners for substantive internal refactors; omit section if all trivial}
   ```

   For trivial single-commit merges, collapse to a single bullet under one section — don't pad sections that don't apply.

6. **If `HAS_CHANGELOG=1`:** prepend the new entry to `CHANGELOG.md` (above prior entries, below any header). Commit on the same branch:
   ```bash
   git add CHANGELOG.md
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "docs(changelog): release notes for upcoming merge"
   git push origin "$BRANCH"
   ```
   This commit lands as part of the PR — consumers reading the merge see the notes inline with the work.

7. **Stash the entry text** for use as the PR body in Step 2. Whether or not CHANGELOG.md exists, the entry is the PR body's primary content.

**Skip rule (rare):** Only skip release notes when the merge contains zero user-visible changes — i.e., it ONLY touches `tasks/`, `tmp/`, or other intentionally-non-consumer-facing paths. In that case, log: _"Release notes skipped — merge touches only internal-tracking paths."_ Even then, prefer a one-line "Internal" entry over a skip.

### Step 1.6: UE-specific check items (project_type: unreal)

If `coordinator.local.md` declares `project_type` includes `unreal`, run these three additional checks after the main release-readiness steps. The coord-claude steps run first; this UE addendum runs after.

| Check | Detection | Action |
|---|---|---|
| **Plugin version matrix touched?** | Path globs: `control/plugin/**`, `control/server/**`, `.github/workflows/build-plugin-*.yml` (any path match triggers the check) | Verify CI matrix run for all 5 UE versions (5.3–5.7) is green; flag if the diff post-dates the last green CI run |
| **Structural-index schema bumped?** | Path globs: `mcp_server/structural_index/*.py`, `plugin/holodeck-project-rag/cli.py`, `scripts/download-structural-index.sh`. Content-grep patterns: `MIN_SUPPORTED_SCHEMA`, `authority_version`, `manifest_version` (any path or grep match triggers the check) | Dispatch `schema-migration-auditor` to enumerate downstream readers; require Patrik review of the audit before merge |
| **Customer-facing install path touched?** | Path globs: `scripts/install-*.{sh,ps1}`, `scripts/lib/install-shell-utils.{sh,ps1}`, `marketplace.json`, `docs/wiki/holodeck-for-your-ue-project.md` | Verify customer-deployment doc parity (no hardcoded `X:/DroneSim`, no internal-PC assumptions); replay install-shell-utils tests in `tests/install/` |

If `project_type` does not include `unreal`, skip this step entirely.

### Step 2: Create PR

```bash
BRANCH=$(git branch --show-current)

# Title based on branch type
# work/striker/2026-03-13 → "Work: striker 2026-03-13"
# feature/my-feature → "Feature: my-feature"

# PR body = release notes from Step 1.5 + commit log appendix
BODY="$(cat <<EOF
$RELEASE_NOTES_FROM_STEP_1_5

---

<details>
<summary>Commit log</summary>

$(git log main..HEAD --oneline)
</details>
EOF
)"

gh pr create --base main --head "$BRANCH" --title "$TITLE" --body "$BODY"
```

- Title: `"Work: {machine} {date}"` for work branches, `"Feature: {name}"` for feature branches.
- Body: structured release notes from Step 1.5 (primary), with the raw commit log collapsed in a `<details>` appendix for traceability.
- If a version bump was suggested in Step 1.5 and the PM hasn't confirmed it, surface in the PR body: _"Suggested bump: patch ({old} → {new}) — confirm before tagging."_

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
- Draft release notes (Step 1.5) — every merge, even patch-level
- Verify remote is synced before creating PR
- Wait for all CI checks to complete
- Use merge commits to preserve history
- Clean up branch after successful merge

**Why release-notes-on-every-merge:** With LLM authoring overhead near-zero, omitting consumer notes is a cost imposed on downstream readers. Other agents reading the publish repos, future-you scanning history, marketplace consumers pulling updates — all benefit. The "humans don't bother for small stuff" pattern doesn't apply here; we have the cycles to be more cognizant.

## Integration

**Called by:**
- **coordinator:finishing-a-development-branch** (Option 1) — delegates merge workflow here
- Invoked directly by PM/EM when ready to merge (no longer called by /workday-complete)

**Pairs with:**
- **coordinator:using-git-worktrees** — cleans up worktree after merge
