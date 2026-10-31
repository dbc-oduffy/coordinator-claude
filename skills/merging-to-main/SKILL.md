---
name: merging-to-main
description: Keyword-gated by name. Merge a ready branch to main via PR.
argument-hint: "[--force] [--force-merge-active-branch]"
version: 2.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Merging to Main

Merge a work or feature branch to main via PR, gated by local validation (no GitHub Actions).
`merge-assemble` computes the gates and directives (`d0`-`d8`); what follows is what it cannot
precompute: judgment calls and steps depending on live PR/merge state.

**Announce at start:** "I'm using the coordinator:merging-to-main skill to merge this branch to main."

On a PowerShell host, invoke the `.exe` launcher by absolute path through the call operator
(Shape W) — ladder and shapes: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.
Compute and apply are one verb (`brief` is removed): `merge-assemble apply [--session-id <id>] [--force] [--decisions-file <path>]`. Resolve every `judgment_points[]` entry it returns, via `--decisions-file`, before its gated directive(s) proceed. `--force` bypasses only the node ceremony hard-gate (`d0`).

EM may refuse to merge and alert the PM on a branch with known issues.

## Step 1: Test Suite Gate

Pre-authorized Tier-U ceremony — grant first: `tier-u-grant-cli grant ceremony
"merging-to-main implicit Tier-U grant for the pre-merge unscoped project test suite" --ceremony
merging-to-main`.

`d0` (`node --test "${CLAUDE_PLUGIN_ROOT}/tests/plugin-ecosystem/run.js"` — the plugin root, never the repo root; halt-on-fail) runs first, then the project's
**fast** tier: `fast_test_cmd` from `coordinator.local.md` (else `pnpm test`/`npm test`, `python3 -m pytest`,
or project-specific from `CLAUDE.md`/`package.json`). Never `full_test_cmd`. **This is the most expensive step in the whole
ceremony** — a machine-wide event (magnitude: `python3 coordinator/tests/_spawn_budget.py`). Fail on either →
halt: _"Test suite failed. Fix first, or use `/merging-to-main --force` to bypass for hotfixes."_

**`--force`** (skill flag, distinct from `apply`'s): skips this step including the Tier-U grant and
`d0`. Log: _"Force-merge requested — test suite gate bypassed."_

**Accepted red.** A suite red on a baseline predating the branch, with the PM's merge order: run it
(never `--force`), archive its `state/test-runs/<suite>-last.*` under
`state/audits/<date>-<branch>-red-set/`, cite that path in the PR verification line, merge. A
failure outside that set, or a red set the branch introduced, still halts (recipe: wiki § Accepted red).

## Step 2: Pre-flight

Commit only paths this session touched, on the commit invocation itself (detail: wiki).

On a work/feature branch → continue. On main with unpushed commits ahead of `origin/main` →
auto-recover via `merge-recovery-and-tag-cut recovery-branch` (cuts a fresh `work/<host>/<date>`
branch off the pre-sync state, pushes, resets main, prints `BRANCH=<name>`), then continue there. On main with nothing unpushed → abort:
_"Already on main with nothing to merge. Switch to a work or feature branch first."_

Resolve the branch via `coordinator-current-branch`, then `coordinator-invoke push.outstanding '{}'`: it pushes commits ahead (MUTATING, never a read).

## Step 3: Release Surface (your call)

`d6`/`d3`/`d5`/`d1`/`d2` are directives (illegal-path scan, coverage gate, portability sweep,
tag-prefix resolution, release-tag plan); `d2` only plans the tag: nothing is created or pushed
until Step 7. Judgment:

**Ship verdict (`ship_verdict`).** EM decides and records it:
`**Ship verdict:** [ship | ship-behind-flag | hold | split | spike-only] — [rationale]`.
All but `hold`/`split` need no PM confirmation. Don't
merge on `hold`/`split` without PM redirect. `/staff-session vp-product` gives a second opinion.
Meanings: wiki § Ship verdict table.

**Release-note framing.** Prefer the latest `state/week-changelog/*-pending-release.md`
accumulator; absent, draft inline by impact (template: wiki). Cutting a tag: omit entries already
in an `archive/releases/*.yaml` index. Write the notes to the repo-root `CHANGELOG.md`, committed
before Step 5, under `## [X.Y.Z] - YYYY-MM-DD` (tag) else `## [Unreleased]`; absent file or
section: create it (begins-at line, backfill) per `coordinator/docs/wiki/release-and-distribution/changelog-and-release-surfaces.md`.
`$RELEASE_NOTES` is that section. `tasks/`/`tmp/`-only merges get an "Internal" line only.

**Demo path** (user-visible merges): append a Demo Path section (template: wiki) to the PR body.

**Version-bump (`version_bump_final`).** On a `ship` verdict the EM picks patch or minor (`d2`
proposes), no confirmation, setting `version_bump_final` before `d2` plans the tag. A major bump,
or any bump on a non-`ship` verdict, needs a PM ruling.

**Portability (`portability_disposition`).** Empty sweep report continues silently; non-empty needs
a per-finding PM disposition (options: wiki). Not a blocker; `COORDINATOR_OVERRIDE_PORTABILITY=1`
skips it once.

## Step 4: UE-specific checks (`project_type: unreal-engine`, or `game-dev` with `project_subtypes: unreal`)

Otherwise skip. Detection table (all five checks): wiki. UBT and reverse-drift gates halt on
non-zero with remediation (or the matching `COORDINATOR_OVERRIDE_*`). Plugin-version-matrix,
structural-index-schema, and install-path touches need eyeball diff-path classification
<!-- engine-gap: field=merge.touched_path_classes producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->.
A schema bump needs `schema-migration-auditor` dispatched, the Staff Engineer review before merge.

## Step 5: Create PR

Compose the PR body via `merge-gate-and-pr pr-body --ship-verdict "$SHIP_VERDICT" --summary
"$SUMMARY" --release-notes "$RELEASE_NOTES" --verification "$VERIFICATION" --risk "$RISK" --links
"$LINKS" --commit-range main..HEAD` (`d4`), then `gh pr create --base main --head "$BRANCH" --title
"$TITLE" --body "$BODY"`. Pass `--release-notes` and `--demo-path` without headings of their own;
version headings at `###` or lower. Exit 2 `unrecognized arguments` (older engine): rerun without
`--summary`, `--verification`, `--risk`, `--links`. State the bump in the PR body: _"Version bump:
{kind} ({old} → {new}) — EM-decided on a ship verdict."_ (awaiting a PM ruling: _"Suggested bump:
… — pending PM."_)

## Step 6: Local Validation Confirmation

Confirm Step 1's run passed on the exact head being merged (re-run `/validate` if commits landed
since). A failure blocks merge.

## Step 7: Merge

Pre-merge quiet check: `merge-gate-and-pr active-branch-guard --pr "$PR"` halts if the PR's newest
commit is younger than 300 seconds; override with `--force-merge-active-branch`.

Merge via `gh pr merge` (no `--delete-branch`), merge commit (never squash). Delete the head branch
only when its remote tip is an ancestor of the base; otherwise keep it and report the tip and its
unmerged-commit count. Recovery recipes ("base branch policy prohibits", "head not up to date"):
wiki. **Merge conflicts** — do not force through; offer the PM merge-main-in-and-resolve
(recommended) or rebase; stop and wait.

**IF `d2` PLANNED A RELEASE TAG, CUT IT NOW, AT THE MERGE COMMIT:**

    merge-recovery-and-tag-cut cut-tag <tag> --pr <PR>
    git fetch origin --tags && git rev-list --count <tag>..origin/main

A refusal (tag exists elsewhere on origin, `gh` missing, PR not merged) or a non-zero count stops
the ceremony. **Never force-push or retarget a tag.** Why: wiki § Tag-contains-release guard.

Once the merge lands, trigger the SCIP rebuild best-effort in the background (never blocks): `"$_py"
"${CLAUDE_PLUGIN_ROOT:-<content-root>/coordinator}/bin/scip-rebuild-at-ceremony.py" --ceremony
merge-to-main` (§ Plugin-local `coordinator/bin/`, `resolve-coordinator-bin.md`). Then run
`post_ceremony_skills` (wiki).

## Step 8: Post-Merge Re-Verify Shared Infra

After a conflict-resolved or concurrently-edited merge, confirm each touched file keeps a canonical
phrase from your change at `HEAD`; missing → re-apply, push a follow-up.

## Step 9: Local Cleanup

Report the structural-index staleness (`.structural-index/refresh-last.json`) in one line; the next `/workday-start` refreshes it. Never refresh here (`A-REINDEX-IS-A-STALENESS-FLAG-NEVER-AN-AGENT-TRIGGER`).

Check out main (`COORDINATOR_OVERRIDE_BRANCH=1`), pull, delete the local branch. Clear any stray
worktree (`git worktree remove <path>`).

## Step 10: Completion-Log Status Flip

When a release tag was cut: `mkdir -p archive/release-notes/`, `git mv` the accumulator into it
(best-effort), scoped-commit the release index (`archive/releases/<tag>.yaml`) + accumulator, push to main.

## Step 11: Report

Four lines: `## Merged to Main`, then `- **PR:** {url}`, `- **Merge commit:** {sha}`,
`- **Branch deleted:** {branch} (local + remote)`, `- **Now on:** main @ {sha}`.

`d8` (`orphan-branch-sweep --format text --severity-min warning`, non-`OK` lines) surfaces other
in-flight branches: _"Multiple work branches in flight — verify these don't carry work intended for
this PR."_

The auto-memory drain gate is gone from this ceremony; do not restore it.

## Red Flags

**Never:** squash commits; push directly to main. Concurrent writers: cap commit sweeps at ~6; don't loop to converge.

**Called by:** `coordinator:finishing-a-development-branch` (Option 1); PM/EM, never `/workday-complete`.
