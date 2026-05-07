---
name: merging-to-main
description: Use when a branch is ready to merge to main. Drafts release notes, creates PR, waits for CI, merges, cleans up.
description-budget: 225
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

1. **Run the coordinator hook test suite first:**
   ```bash
   node --test ~/.claude/tests/plugins/run.js
   ```
   If this fails, halt and report which tests failed before proceeding. The hook suite
   covers load-bearing infrastructure (coordinator-safe-commit, verify-preamble-sync,
   coordinator-auto-push, session-init) and must pass before any merge.

2. **Detect project test runner:** Look for common test commands:
   - `pnpm test` or `npm test` (Node.js projects)
   - `pytest` or `python -m pytest` (Python projects)
   - `/validate` skill (all projects with CI)
   - Project-specific test commands from `CLAUDE.md` or `package.json`

3. **Run the project test suite.** If tests pass: proceed to Step 1. If tests fail: alert the PM and halt — _"Test suite failed before merge. Fix the failures first, or use `/merge-to-main --force` to bypass the test gate for hotfixes."_ Do NOT proceed to PR creation.

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
   # Sync-main invariant: verify origin/main is reachable before creating branch.
   # If local main is ahead of origin/main, abort rather than creating a stale branch.
   ~/.claude/plugins/coordinator-claude/coordinator/bin/sync-main.sh || {
     echo "sync-main.sh failed — local main has diverged. Investigate before creating a recovery branch."
     exit 1
   }
   # Determine branch name using git-workflow conventions
   BRANCH="work/$(hostname | tr '[:upper:]' '[:lower:]')/$(date +%Y-%m-%d)"
   # Review: patrik F1 — inline override required; block-off-daily-branch.sh hook
   # would deny git checkout -b and git checkout here without it.
   COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="merging-to-main step 1 create recovery branch" \
     git checkout -b "$BRANCH"
   git push origin "$BRANCH" --set-upstream
   # Reset local main back to origin
   COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="merging-to-main step 1 checkout main for reset" \
     git checkout main && git reset --hard origin/main
   COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="merging-to-main step 1 return to work branch" \
     git checkout "$BRANCH"
   ```
   Then proceed to step 3 on the new branch.

   **If on main with no unpushed commits:** abort:
   _"Already on main with nothing to merge. Switch to a work or feature branch first."_

3. **Verify remote is up-to-date:**
   ```bash
   _BR=$(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)
   git log origin/"$_BR"..HEAD 2>/dev/null
   ```
   If unpushed commits exist, push explicitly:
   ```bash
   git push origin "$_BR" --set-upstream
   ```

### Step 1.5: Build PR Body (mandatory, every merge)

Every merge to `main` produces a PR body composed of four parts: ship verdict, VP-Product verdict (when applicable), release notes, and demo path (user-visible work only). LLM authoring overhead is near-zero — omitting any part imposes a cost on downstream readers.

**Part 1 — Ship Verdict (every merge)**

Before creating the PR, the EM stages a one-line ship verdict for the PR body:

```markdown
**Ship verdict:** [ship | ship-behind-flag | hold | split | spike-only] — [one-sentence rationale]
```

| Verdict | Meaning |
|---------|---------|
| **ship** | Acceptance criteria satisfied (or explicitly waived); evidence supports merge to main; no blocking concerns |
| **ship-behind-flag** | Code is ready, but rollout should be gated (feature flag, percentage rollout, opt-in). Name the flag |
| **hold** | Don't merge yet — specific concern remains. Name it |
| **split** | This branch contains two changes that should land separately. Name them and recommend split-then-merge |
| **spike-only** | Code is informative but not for production. Document findings, don't merge to main |

The EM **stages** the verdict; the PM **confirms or overrides**. Don't merge on a `hold` or `split` verdict without explicit PM redirect. For routine `ship` verdicts on small internal merges, the PM's silent acceptance is fine — but the verdict line is always present so future-you can scan history and see the call.

**Part 2 — VP-Product Reviewer Review (user-visible, perf/concurrency, third-patch-in-six-months, or refactor-cheaper-than-patch)**

Dispatch **the VP-Product Reviewer (`coordinator:vp-product`, `agents/vp-product.md`)** as a primary reviewer for any merge that:

- changes user-visible behavior (UI, copy, defaults, error states, permissions, public APIs), **or**
- touches performance, concurrency, scalability, or extensibility surface, **or**
- is a **patch** in an area that has accumulated prior patches (third patch in six months → mandatory VP-Product Reviewer), **or**
- the EM proposes an approach where a refactor would plausibly be cheaper than the patch.

Skip the VP-Product Reviewer entirely for: pure doc updates, test-infrastructure-only changes, dep bumps with no API surface change, and trivial typo fixes.

The VP-Product Reviewer's job is to ask the dumb questions experienced engineers skip — *"why single-threaded when multi-thread is 30 lines?"*, *"have you considered a different shape?"*, *"is this YAGNI legitimate or laziness in costume?"* The output is a structured review with a `shape_assessment`, a `refactor_recommendation`, and 1–3 alternative shapes considered. See `agents/vp-product.md` for full doctrine.

**Output** — append the VP-Product Reviewer's verdict line to the PR body:

```markdown
**VP-Product verdict:** [APPROVED | APPROVED_WITH_NOTES | REQUIRES_CHANGES | REJECTED] — shape: [right | acceptable | wrong] — refactor: [recommend-refactor | recommend-patch | undecided] — [one-sentence rationale]
```

If `REQUIRES_CHANGES` or `REJECTED`: dispatch the review-integrator to apply the VP-Product Reviewer's findings before drafting the ship verdict. Do not hand-wave them away. If the EM disagrees with the VP-Product Reviewer on a refactor recommendation, the EM must articulate the disagreement in the PR body — silent override is the failure mode this gate exists to prevent.

**Part 3 — Release Notes (every merge)**

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

**Part 4 — Demo Path (user-visible only)**

For user-visible merges, append a **Demo Path** section to the PR body:

```markdown
### Demo Path

**Setup:** [commands, seed data, environment]
**Steps:**
1. [user action]
2. [user action]
3. [observe result]
**Expected:** [what should happen]
**Known limitations:** [what *not* to claim from this demo]
```

For internal merges, omit. The point is to make every user-visible increment demonstrable — not to add ceremony.

The composed PR body is what flows into Step 2's `gh pr create --body`.

### Step 1.6: UE-specific check items (project_type: unreal)

If `coordinator.local.md` declares `project_type` includes `unreal`, run these three additional checks after the main release-readiness steps. The coord-claude steps run first; this UE addendum runs after.

| Check | Detection | Action |
|---|---|---|
| **Plugin version matrix touched?** | Path globs: `control/plugin/**`, `control/server/**`, `.github/workflows/build-plugin-*.yml` (any path match triggers the check) | Verify CI matrix run for all 5 UE versions (5.3–5.7) is green; flag if the diff post-dates the last green CI run |
| **Structural-index schema bumped?** | Path globs: `mcp_server/structural_index/*.py`, `project-rag/cli.py`, `scripts/download-structural-index.sh`. Content-grep patterns: `MIN_SUPPORTED_SCHEMA`, `authority_version`, `manifest_version` (any path or grep match triggers the check) | Dispatch `schema-migration-auditor` to enumerate downstream readers; require the Staff Engineer review of the audit before merge |
| **Customer-facing install path touched?** | Path globs: `scripts/install-*.{sh,ps1}`, `scripts/lib/install-shell-utils.{sh,ps1}`, `marketplace.json`, `docs/wiki/holodeck-for-your-ue-project.md` | Verify customer-deployment doc parity (no hardcoded `X:/DroneSim`, no internal-PC assumptions); replay install-shell-utils tests in `tests/install/` |

If `project_type` does not include `unreal`, skip this step entirely.

### Step 2: Create PR

```bash
BRANCH=$(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)

# Title based on branch type
# work/striker/2026-03-13 → "Work: striker 2026-03-13"
# feature/my-feature → "Feature: my-feature"

# PR body = ship verdict + VP-Product Reviewer verdict (when run) + release notes + demo path (Step 1.5 Parts 1–4)
BODY="$(cat <<EOF
$SHIP_VERDICT
$VP_PRODUCT_VERDICT

$RELEASE_NOTES

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
  _"CI failed on {check}. Fix the issue and re-run `/merge-to-main`, or investigate with the four-phase root-cause process at `docs/wiki/systematic-debugging.md`."_

### Step 4: Merge

**Pre-merge quiet check (5-minute activity gate).** Source branches still receiving commits in the last 5 minutes indicate active work that may not belong in this merge. Run before `gh pr merge`:

```bash
# Get the timestamp of the last commit on the PR's source branch via gh
last_iso=$(gh pr view "$PR" --json commits -q '.commits[-1].committedDate')
last=$(python -c "import datetime,sys; print(int(datetime.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00')).timestamp()))" "$last_iso")
now=$(python -c "import time; print(int(time.time()))")
if [ $((now - last)) -lt 300 ]; then
  branch=$(gh pr view "$PR" --json headRefName -q .headRefName)
  echo "Source branch $branch has commits younger than 5 minutes — wait for activity to settle, or pass --force-merge-active-branch."
  exit 1
fi
```

**Note:** `gh pr view --json commits` returns commits in chronological order (verified against gh 2.87.3). `.commits[-1]` is the newest commit.

**Override:** If `$ARGUMENTS` contains `--force-merge-active-branch`, skip this gate entirely. Use for deliberate fast merges where the 5-minute window is known-safe.

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
git push origin $(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)
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
# Review: patrik F1 — inline override required; switching to main is off-daily.
COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="merging-to-main step 5 checkout main post-merge" \
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

**Other unmerged branches:**

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/orphan-branch-sweep.sh --format text --severity-min warning | grep -v "^OK"
```

If any output: include in the report and recommend: _"Multiple work branches in flight — verify these don't carry work intended for this PR."_

## Red Flags

**Never:** squash commits (we want the breadcrumb trail); push directly to main.

**Use judgment:** CI failures are advisory — review them, but they don't block merge. Force push is allowed by the ruleset if needed.

**Concurrent-writer caveat:** When `/merge-to-main` runs alongside an active concurrent writer (orphan-promotion handoff, parallel session), cap commit sweeps at ~6 and accept a moving target. Don't loop trying to converge.

## Integration

**Called by:**
- **coordinator:finishing-a-development-branch** (Option 1) — delegates merge workflow here
- Invoked directly by PM/EM when ready to merge (no longer called by /workday-complete)

**Pairs with:**
- No worktrees — worktrees are forbidden. Use the daily branch for WIP parking.
