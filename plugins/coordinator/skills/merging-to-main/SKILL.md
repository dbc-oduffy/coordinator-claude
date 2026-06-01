---
name: merging-to-main
description: Use when a branch is ready to merge to main. Drafts release notes, creates PR, waits for CI, merges, cleans up.
description-budget: 225
argument-hint: "[--force]"
version: 1.1.0
---

# Merging to Main

## Overview

Merge a work or feature branch to main via PR with CI gating.

**Announce at start:** "I'm using the coordinator:merging-to-main skill to merge this branch to main."

## The Process

### Step 0: Acceptance-Oracle Gate + Test Suite Gate

#### Step 0a: Acceptance-Oracle Gate (AUTHORITATIVE)

<!-- spec-backlink: archive/specs/2026-05-24-acceptance-oracle-with-teeth.md §2.3 — authoritative gate seam topology -->

Before any test-suite or PR work, run the acceptance-oracle gate for the branch's plan.

**Plan-path discovery (try in order):**
1. Frontmatter `plan:` field on the branch's most-recent plan document.
2. Explicit `--plan <path>` flag in `$ARGUMENTS`.
3. If neither yields a path → **skip-with-offer**: _"No plan path found — acceptance oracle can be validated manually with `bash check-acceptance-oracle.sh <plan-path>` if a plan exists for this branch."_ Continue to Step 0b.

**If `COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1` is set:**
Skip the gate entirely. Log: _"Acceptance-oracle gate bypassed via COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1 — exceptional use only."_ Continue to Step 0b.

**If plan path resolved AND the plan contains a bindable `## Acceptance Criteria` table** (columns: `ID | Criterion | Test | Binding-Class | Status`):

```bash
bash check-acceptance-oracle.sh <plan-path>
```

- **Exit 0 (all gate-bound rows green or cited-resolved):** Log the verdict and continue to Step 0b. _"Acceptance oracle: all gate-bound tests pass."_
- **Non-zero exit (any gate-bound row red or missing):** Hard-block the merge:
  ```
  Merge blocked: acceptance oracle has red or unresolved gate-bound tests.
  
  <verdict from check-acceptance-oracle.sh>
  
  Fix the failing tests and re-run /merge-to-main, or set
  COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1 to bypass (exceptional use only —
  the accepted accommodation for environment-bound tests is cited: rows, not this override).
  ```
  Stop. Do NOT proceed to PR creation.

**If plan path resolved but no bindable `## Acceptance Criteria` table** (old-form plan):
Skip-with-offer: _"Plan found but no bindable acceptance-criteria table — oracle gate skipped. Consider upgrading (`docs/wiki/writing-plans.md` § Acceptance Oracle)."_ Continue to Step 0b.

#### Step 0b: Test Suite Gate

1. **Run the coordinator hook test suite first:**
   ```bash
   node --test ~/.claude/plugins/coordinator/tests/plugin-ecosystem/run.js
   ```
   If this fails, halt and report which tests failed. The hook suite covers load-bearing infra
   (coordinator-safe-commit, verify-preamble-sync, coordinator-auto-push, session-init) and must pass before any merge.

2. **Detect project test runner:** `pnpm test` / `npm test` (Node.js), `pytest` / `python -m pytest` (Python), `/validate` (CI), or project-specific from `CLAUDE.md`/`package.json`.

3. **Run the project test suite.** Pass → proceed to Step 1. Fail → halt: _"Test suite failed. Fix first, or use `/merge-to-main --force` to bypass for hotfixes."_ Do NOT proceed to PR creation.

4. **`--force` escape hatch:** Skips Step 0b only — acceptance-oracle gate (Step 0a) is NOT bypassed; use `COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1` for that. Log: _"Force-merge requested — test suite gate bypassed."_ Proceed to Step 1.

5. **First Officer Doctrine:** EM may refuse to merge and alert the PM if the branch has known issues.

### Step 1: Pre-flight

1. **Check for uncommitted changes.** Commit only paths this session touched — do NOT use coordinator-safe-commit here (SC-DR-008):
   ```bash
   git add -- <path1> <path2> ... && git commit -m "pre-merge quick-save" -- <path1> <path2> ...
   ```

2. **Handle current branch:**

   **If on a work/feature branch:** proceed to step 3.

   **If on main with unpushed commits ahead of origin/main:**
   Auto-recover: commits go through a PR, not a direct push.
   ```bash
   ~/.claude/plugins/coordinator/bin/sync-main.sh || {
     echo "sync-main.sh failed — local main has diverged. Investigate before creating a recovery branch."
     exit 1
   }
   BRANCH="work/$(hostname | tr '[:upper:]' '[:lower:]')/$(date +%Y-%m-%d)"
   # Review: patrik F1 — inline override required; block-off-daily-branch.sh hook
   # would deny git checkout -b and git checkout here without it.
   COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="merging-to-main step 1 create recovery branch" \
     git checkout -b "$BRANCH"
   git push origin "$BRANCH" --set-upstream
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
   _BR=$(~/.claude/plugins/coordinator/bin/coordinator-current-branch)
   git log origin/"$_BR"..HEAD 2>/dev/null
   ```
   If unpushed commits exist, push explicitly:
   ```bash
   git push origin "$_BR" --set-upstream
   ```

### Step 1.5: Build PR Body (mandatory, every merge)

Every merge to `main` produces a PR body composed of three parts: ship verdict, release notes, and demo path (user-visible work only). The VP-of-Product lens is the PM's lens — applied in meatspace; request `/staff-session` with `vp-product` for a structured second opinion.

**Part 1 — Ship Verdict (every merge)**

EM stages one line; PM confirms or overrides. Don't merge on `hold`/`split` without PM redirect. Always present for audit history.

```markdown
**Ship verdict:** [ship | ship-behind-flag | hold | split | spike-only] — [one-sentence rationale]
```

| Verdict | Meaning |
|---------|---------|
| **ship** | AC satisfied/waived; evidence supports merge; no blocking concerns |
| **ship-behind-flag** | Code ready but rollout should be gated. Name the flag |
| **hold** | Don't merge — specific concern remains. Name it |
| **split** | Two changes that should land separately. Name them |
| **spike-only** | Informative only — don't merge to main |

**Part 2 — Release Notes (every merge)**

```bash
PENDING_RELEASE=$(ls tasks/week-changelog/*-pending-release.md 2>/dev/null | sort | tail -1)
```

- **`$PENDING_RELEASE` set (normal path):** Use as primary; skip steps 1–5, go to step 6. Set `PENDING_RELEASE_FILE="$PENDING_RELEASE"` (retain for Step 5.5).
- **Absent (emergency-release path):** Draft inline via steps 1–5. Set `PENDING_RELEASE_FILE=""`.

1. **Inventory the merge:**
   ```bash
   COMMITS=$(git log main..HEAD --oneline) && CHANGED_FILES=$(git diff --name-only main..HEAD)
   COMMIT_COUNT=$(git rev-list --count main..HEAD) && STATS=$(git diff --shortstat main..HEAD)
   ```

2. **Group by impact** (don't mirror commit-by-commit): **Added**, **Changed**, **Fixed**, **Deps**, **Internal** (omit if trivial). Single-commit dep-bump merges still get a one-line note — don't skip "trivial" merges.

3. **Detect repo-root `CHANGELOG.md`:**
   ```bash
   if [ -f CHANGELOG.md ]; then HAS_CHANGELOG=1; else HAS_CHANGELOG=0; fi
   ```
   Present → always update it. Absent → do NOT auto-create; embed notes in PR body only.

4. **Determine version bump suggestion** (advisory — surfaced for PM, never auto-applied):
   - If `version_source: tag` in `coordinator.local.md`: do NOT read the manifest (may be frozen sentinel). Surface `version per docs/wiki/versioning-convention.md — PM to confirm number`; skip the rest.
   - Otherwise (`version_source: manifest`, the default): read ecosystem manifest (`package.json` / `pyproject.toml` / `Cargo.toml`). Suggest: **patch** (fixes/deps/internal), **minor** (new compat features), **major** (breaking). When unsure, suggest lower.

   **Tagged-publish leg** (drives off bump suggestion — no separate triviality gate):

   Evaluate both before proposing:
   - Bump suggestion is `>= patch` (not a skip).
   - Merge touches more than `tasks/`, `tmp/`, or other internal-only paths.

   If BOTH hold, **check `coordinator.local.md` for `tag_anchor`** to select publish mode:

   <!-- tag_anchor=git-tag mode (C4, 2026-06-01): registry-property opt-in for repos that use
        annotated git tags as the sole disclosure anchor (no GitHub Releases / no OSS publish repo).
        Declared via `tag_anchor: git-tag` in coordinator.local.md frontmatter.
        Spec: docs/plans/2026-06-01-version-disclosure-and-boot-currency-hook.md § C4 -->

   **Mode A — `tag_anchor: git-tag` (repo declares git-tag-only mode):**

   If `coordinator.local.md` frontmatter `tag_anchor: git-tag`, this is a git-tag-only disclosure
   repo — propose ONLY the annotated tag, no GitHub Release step. Two OPTIONAL companion fields
   (defaults reproduce bare-`v*`, manifest-driven behavior; repos without them are unchanged — see DR-149):

   - **`tag_prefix:`** (default empty) — namespace prefix. Empty → `vX.Y.Z`; `holodeck-` → `holodeck-vX.Y.Z`.
     The cut here and the consumer's currency check MUST resolve the same `${tag_prefix}v*` pattern.
     **Coupling warning:** `tag_prefix` and the consumer's currency-check resolver drift silently — update in lockstep.
   - **`version_source:`** (default `manifest`) — `manifest` → read ecosystem manifest for version SSOT;
     `tag` → latest `${tag_prefix}v*` tag is the SSOT; manifest is NOT read (may be a frozen sentinel,
     e.g. holodeck's `pyproject` at `0.0.0`). Number choice per consumer's `versioning-convention.md` (PM-confirmed).

   Propose:

   ```
   Suggested bump: <prefix>vX.Y.Z (patch|minor|major — rationale, or "per versioning-convention.md").
   Tagged publish: propose cutting the annotated git tag <prefix>vX.Y.Z on origin/main.
   Confirm version and tag, or adjust.
   ```

   PM confirms inline (release surface — never a silent EM auto-tag). Mode A only when `tag_anchor: git-tag` is explicitly set; repos without it use Mode B. Before adding, confirm GitHub Releases are not in use for the version line this tag governs.

   On confirmation, cut and push the annotated tag:

   ```bash
   # Replace the version with the confirmed number — do not run this block literally.
   # tag_anchor=git-tag mode: annotated ${TAG_PREFIX}v* tag is the sole disclosure anchor.
   # → project-rag/docs/plans/2026-06-01-version-disclosure-and-boot-currency-hook.md § C4; DR-149.
   # Fail-loud on quoted tag_prefix (detect-then-fail-loud, not detect-then-silently-pick).
   TAG_PREFIX="$(awk -F':[ \t]*' '
     /^---[ \t]*$/          { f++; next }
     f==1 && /^tag_prefix:/ { v=$2; sub(/[ \t]+#.*$/, "", v); print v; exit }
     f>=2                   { exit }
   ' coordinator.local.md)"
   case "$TAG_PREFIX" in
     *[\"\']*) echo "FATAL: tag_prefix in coordinator.local.md must be unquoted (got: $TAG_PREFIX)" >&2; exit 1 ;;
   esac
   TAG="${TAG_PREFIX}vX.Y.Z"                    # e.g. v0.9.0  OR  holodeck-v0.4.0
   git fetch origin main
   MERGE_SHA="$(git rev-parse origin/main)"
   # Idempotent on retry: only (re)cut+push the tag if it does not already point at MERGE_SHA.
   existing="$(git rev-parse "$TAG" 2>/dev/null || true)"
   if [ "$existing" != "$MERGE_SHA" ]; then
       git tag -a "$TAG" "$MERGE_SHA" -m "$TAG"
       git push origin "$TAG"
   fi
   ```

   No `gh release` command is run. `git tag -a` is hardcoded (annotated-never-lightweight). Tag-cut is idempotent.

   **Mode B — default (no `tag_anchor` field, or `tag_anchor` is not `git-tag`):**

   Propose a **tagged version bump + GitHub-release publish** alongside the bump suggestion:

   ```
   Suggested bump: vX.Y.Z (patch|minor|major — rationale).
   Tagged publish: propose cutting the vX.Y.Z git tag on coordinator-claude and un-drafting
   the corresponding GitHub release. Confirm version and publish, or adjust.
   ```

   PM confirms inline. On confirmation, **cut and push the `v*` git tag explicitly** — do NOT rely on un-drafting a release to create the tag as a side-effect:

   ```bash
   # The boot currency check anchors on the latest v* GIT TAG via git ls-remote --tags, NOT
   # the Release object. Tag MUST be pushed first — un-drafted release without tag push leaves
   # consumers on stale anchor. → docs/wiki/release-cadence-and-currency-notification.md
   git fetch origin main
   MERGE_SHA="$(git rev-parse origin/main)"
   # Idempotent on retry: only (re)cut+push the tag if it does not already point at MERGE_SHA.
   existing="$(git rev-parse "vX.Y.Z" 2>/dev/null || true)"
   if [ "$existing" != "$MERGE_SHA" ]; then
       git tag -a "vX.Y.Z" "$MERGE_SHA" -m "vX.Y.Z"
       git push origin "vX.Y.Z"
   fi
   # Then publish the human-facing release (un-draft existing, or create if absent):
   gh release edit vX.Y.Z --repo dbc-oduffy/coordinator-claude --draft=false --latest \
     || gh release create vX.Y.Z --repo dbc-oduffy/coordinator-claude --latest --notes-file <release-notes>
   ```

   `git push origin vX.Y.Z` is load-bearing for currency; `gh release` is human-facing discoverability. Both run; release-edit failure must not leave the tag un-pushed. Tag-cut is idempotent.

   **Publish target:** OSS publish repo(s) touched by this workstream (e.g. `dbc-oduffy/coordinator-claude`). Release notes from Step 1.5 Part 2 are the release body.

   **Claude Prime (`source_is_live`) is NEVER tagged.** The meta-repo at `~/.claude` has `propagation_mode = "source_is_live"` — skip this leg silently when active repo is the meta-repo.

   If either condition does NOT hold (bump is skip-eligible or merge is internal-only), skip the tagged-publish proposal silently.

5. **Draft the entry:**
   ```markdown
   ## v{suggested-version} — {YYYY-MM-DD}
   ### Added / Changed / Fixed / Deps / Internal
   - {one-line bullet per logical change; omit empty sections}
   ```
   For trivial single-commit merges, collapse to a single bullet — don't pad sections that don't apply.

6. **If `HAS_CHANGELOG=1`:** prepend entry to `CHANGELOG.md` (above prior entries, below header). Commit on branch:
   ```bash
   git add -- CHANGELOG.md && git commit -m "docs(changelog): release notes for upcoming merge" -- CHANGELOG.md
   git push origin "$BRANCH"
   ```

7. **Stash entry text** for use as PR body in Step 2.

**Skip rule (rare):** Skip only when the merge ONLY touches `tasks/`, `tmp/`, or other internal-only paths. Log: _"Release notes skipped — merge touches only internal-tracking paths."_ Even then, prefer a one-line "Internal" entry over a skip.

**Part 3 — Demo Path (user-visible merges only)**

Append to PR body (omit for internal merges):
```markdown
### Demo Path
**Setup:** [commands, seed data, environment]
**Steps:** 1. [action] 2. [action] 3. [observe result]
**Expected:** [what should happen] | **Known limitations:** [what *not* to claim]
```
The composed PR body flows into Step 2's `gh pr create --body`.

### Step 1.6: UE-specific check items (project_type: game-dev, project_subtypes: unreal)

If `coordinator.local.md` declares `project_type: game-dev` AND `project_subtypes` contains `unreal`, run these additional checks after the main release-readiness steps.

| Check | Detection | Action |
|---|---|---|
| **Plugin version matrix touched?** | Path globs: `control/plugin/**`, `control/server/**`, `.github/workflows/build-plugin-*.yml` (any path match triggers the check) | Verify CI matrix run for all 5 UE versions (5.3–5.7) is green; flag if the diff post-dates the last green CI run |
| **Structural-index schema bumped?** | Path globs: `mcp_server/structural_index/*.py`, `project-rag/cli.py`, `scripts/download-structural-index.sh`. Content-grep patterns: `MIN_SUPPORTED_SCHEMA`, `authority_version`, `manifest_version` (any path or grep match triggers the check) | Dispatch `schema-migration-auditor` to enumerate downstream readers; require the Staff Engineer review of the audit before merge |
| **Customer-facing install path touched?** | Path globs: `scripts/install-*.{sh,ps1}`, `scripts/lib/install-shell-utils.{sh,ps1}`, `marketplace.json`, `docs/wiki/holodeck-for-your-ue-project.md` | Verify customer-deployment doc parity (no hardcoded local drive paths to peer repos, no internal-PC assumptions); replay install-shell-utils tests in `tests/install/` |
| **UBT gate** | `bin/check-ubt-build-fresh.sh` exists in cwd | Scan `tasks/review-trail/` for any `*.ubt-compile.pending.json` records without a corresponding `*.ubt-compile.resolved.json` sibling. If found, halt with remediation: run `/workday-complete` to resolve the pending records, or override with `COORDINATOR_OVERRIDE_UBT_GATE=1` (same escape hatch as Step 0c). A pending record WITH a resolved sibling passes silently. |
| **Reverse-drift gate** | `bin/check-reverse-drift.sh` is executable in cwd | Run it. On non-zero exit (a `copy_install` live install hand-edited since last install — the case forward-SHA `check-plugin-drift.sh` is blind to), halt with the script's remediation: run `holodeck_recover --step reverse-drift` to back-propagate live→source, or override with `COORDINATOR_OVERRIDE_REVERSE_DRIFT=1`. No script present → passes silently. Mirrors `/workweek-complete` Step 4g. |

Otherwise skip.

### Step 2: Create PR

```bash
BRANCH=$(~/.claude/plugins/coordinator/bin/coordinator-current-branch)
# work/<machine>/2026-03-13 → "Work: <machine> 2026-03-13"; feature/my-feature → "Feature: my-feature"
BODY="$(cat <<EOF
$SHIP_VERDICT
$YK_VERDICT

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

- Body: ship verdict + release notes + demo path (Step 1.5 Parts 1–3); commit log collapsed in `<details>`.
- If version bump suggested but not PM-confirmed, surface: _"Suggested bump: patch ({old} → {new}) — confirm before tagging."_

### Step 3: Wait for CI

```bash
gh pr checks <pr-number> --watch
```

- **Checks pass:** proceed to Step 4.
- **"no checks reported"** (exit 1): no CI configured — treat as pass, proceed to Step 4.
- **Checks fail:** report which failed. Do NOT merge. _"CI failed on {check}. Fix and re-run `/merge-to-main`, or investigate via `docs/wiki/systematic-debugging.md`."_

### Step 4: Merge

**Pre-merge quiet check (5-minute activity gate).** Run before `gh pr merge`:

```bash
last_iso=$(gh pr view "$PR" --json commits -q '.commits[-1].committedDate')
last=$(python -c "import datetime,sys; print(int(datetime.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00')).timestamp()))" "$last_iso")
now=$(python -c "import time; print(int(time.time()))")
if [ $((now - last)) -lt 300 ]; then
  branch=$(gh pr view "$PR" --json headRefName -q .headRefName)
  echo "Source branch $branch has commits younger than 5 minutes — wait for activity to settle, or pass --force-merge-active-branch."
  exit 1
fi
```

**Note:** `gh pr view --json commits` returns commits in chronological order (verified against gh 2.87.3). `.commits[-1]` is the newest.

**Override:** If `$ARGUMENTS` contains `--force-merge-active-branch`, skip this gate entirely.

Use merge commit (not squash) — preserves commit history as breadcrumbs.

```bash
gh pr merge <pr-number> --merge --delete-branch
```

**If "base branch policy prohibits the merge":**
Auto-recover with `--auto` (merges when requirements are satisfied):
```bash
gh pr merge <pr-number> --merge --delete-branch --auto
```
Verify:
```bash
sleep 5 && gh pr view <pr-number> --json state --jq '.state'
```
If `MERGED`, proceed to Step 5. If still `OPEN`, auto-merge is queued — wait and check again.

**Note:** As of 2026-03-13, rulesets no longer require status checks or block force push. Primary gate is the PR requirement (0 approvals). CI advisory.

**If "head branch is not up to date with base":**
Auto-recover — do NOT stop or ask:
```bash
git fetch origin main
git merge origin/main -m "merge main into work branch"
git push origin $(~/.claude/plugins/coordinator/bin/coordinator-current-branch)
gh pr merge <pr-number> --merge --delete-branch  # retry
```

**If merge conflicts:** Do NOT force. Report conflicting files: _"Main has diverged. Options: (a) merge main in and resolve conflicts, (b) rebase. Recommend (a)."_ Stop and wait for PM.

### Step 4.5: Post-Merge Re-Verify Shared Infra (geneva T1.7)

After merge — especially when conflicts were resolved or main had concurrent edits — re-verify intended changes survived (last-writer-wins silently reverts edits on naively resolved hunks).

1. For each file edited on this branch:
   ```bash
   git show HEAD:<file-path> | grep -F "<canonical phrase from your change>"
   ```
2. If a canonical phrase is missing, your change was overwritten — re-apply and push a follow-up commit immediately.
3. Highest-risk files: shared infra (`~/.claude/`, config files, shared scripts).

### Step 5: Local Cleanup

```bash
# Review: patrik F1 — inline override required; switching to main is off-daily.
COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="merging-to-main step 5 checkout main post-merge" \
  git checkout main
git pull origin main
git branch -d <branch>  # local branch delete
```

If on a worktree: `git worktree remove <path>` instead.

### Step 5.5: Post-Merge Completion-Log Status Flip

_Runs only when `$PENDING_RELEASE_FILE` was set in Step 1.5. Skip if empty._

1. **Ensure archive directory exists:** `mkdir -p archive/release-notes/`

2. **Flip all `pending-release` completion entries to `released`:**
   ```bash
   ENTRY_PATHS=$(query-completions --where "status=pending-release" --format paths)
   MERGE_SHA=$(git rev-parse HEAD)
   MERGE_DATE=$(date +%Y-%m-%d)
   # For each entry path, set frontmatter — do NOT use git add -A.
   ```
   Set four frontmatter fields in each entry:
   ```yaml
   status: released
   released_in: <version-tag>       # e.g. v1.4.0
   released_at: <MERGE_DATE>
   released_sha: <MERGE_SHA>
   ```

3. **Archive the pending-release file:**
   ```bash
   PENDING_BASENAME=$(basename "$PENDING_RELEASE_FILE")
   git mv "$PENDING_RELEASE_FILE" "archive/release-notes/${PENDING_BASENAME%-pending-release.md}-${VERSION_TAG}-pending-release.md"
   ```

4. **Commit on main — scoped, never `git add -A`:**
   ```bash
   ARCHIVED_PENDING="archive/release-notes/${PENDING_BASENAME%-pending-release.md}-${VERSION_TAG}-pending-release.md"
   git add -- $ENTRY_PATHS "$ARCHIVED_PENDING"
   # git add -- "$RELEASE_FILE"   # if a human-readable release notes file was written
   git commit -m "release: flip completion entries to released for ${VERSION_TAG}" -- $ENTRY_PATHS "$ARCHIVED_PENDING"
   ```
   Alternative if shell word-splitting on `$ENTRY_PATHS` is awkward: use `git add --pathspec-from-file=<tmpfile>`.

   ```bash
   git push origin main
   ```

**Result:** all `pending-release` entries stamped `released`; pending-release file archived under `archive/release-notes/`.

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
~/.claude/plugins/coordinator/bin/orphan-branch-sweep.sh --format text --severity-min warning | grep -v "^OK"
```
If any output, include in the report: _"Multiple work branches in flight — verify these don't carry work intended for this PR."_

## Red Flags

**Never:** squash commits; push directly to main.

**Use judgment:** CI failures are advisory — review them, but they don't block merge. Force push is allowed by the ruleset if needed.

**Concurrent-writer caveat:** When `/merge-to-main` runs alongside an active concurrent writer, cap commit sweeps at ~6 and accept a moving target. Don't loop trying to converge.

## Integration

**Called by:** `coordinator:finishing-a-development-branch` (Option 1); PM/EM directly (no longer called by `/workday-complete`).

**Pairs with:** No worktrees — worktrees are forbidden. Use the daily branch for WIP parking.
