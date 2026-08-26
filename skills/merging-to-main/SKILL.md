---
name: merging-to-main
description: "Keyword-gated by name. Merges a ready branch to main: PR, CI, cleanup."
argument-hint: "[--force] [--force-merge-active-branch]"
version: 2.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Merging to Main

## Overview

Merge a work or feature branch to main via PR with CI gating. `merge-assemble` computes the node
ceremony hard-gate, tag-prefix resolution, release-tag cut, coverage gate, PR body, portability
sweep, illegal-path scan, completion-log flip, and orphan-branch sweep. What follows is what it
cannot precompute: your judgment calls, plus the steps depending on live PR/merge state (branch
recovery, PR creation, the merge, local cleanup).

**Announce at start:** "I'm using the coordinator:merging-to-main skill to merge this branch to main."

On a PowerShell host, use the `.cmd` sibling through the call operator (Shape W) — ladder and
shapes: `snippets/resolve-coordinator-bin.md`.
Compute: `merge-assemble brief [--tag-prefix <prefix>]`, resolved per that ladder. Resolve every `judgment_points[]` entry before its gated directive(s) proceed. Apply: same CLI's `apply [--session-id <id>] [--force] [--decisions <json>]` — `apply`'s own `--force` bypasses only the node ceremony hard-gate (`d0`).

**First Officer Doctrine:** EM may refuse to merge and alert the PM on a branch with known issues.

---

## Step 1: Test Suite Gate

Pre-authorized Tier-U ceremony — grant first: `tier-u-grant-cli grant ceremony
"merging-to-main implicit Tier-U grant for the pre-merge unscoped project test suite" --ceremony
merging-to-main`.

`d0` (`node --test tests/plugin-ecosystem/run.js`, halt-on-fail) runs first, then detect and run
the project's own test runner (`pnpm test`/`npm test`, `pytest`/`python -m pytest`, `/validate`, or
project-specific from `CLAUDE.md`/`package.json`). **This is the most expensive step in the whole
ceremony** — the project's full suite is a machine-wide event, not a cheap check; its actual
magnitude is whatever `python coordinator/tests/_spawn_budget.py` reports for this repo, never a
hardcoded figure here, but treat "run the suite" as heavy every time you grant it. Fail on either →
halt: _"Test suite failed. Fix first, or use `/merge-to-main --force` to bypass for hotfixes."_

**`--force`** (skill flag, distinct from `apply`'s): skips this step including the Tier-U grant and
`d0`. Log: _"Force-merge requested — test suite gate bypassed."_

---

## Step 2: Pre-flight

Commit only paths this session touched, on the commit invocation itself (detail: wiki).

On a work/feature branch → continue. On main with unpushed commits ahead of `origin/main` →
auto-recover via `merge-recovery-and-tag-cut recovery-branch` (syncs local main, cuts a fresh
`work/<host>/<date>` branch off the pre-sync state, pushes, hard-resets main, returns to the new
branch, prints `BRANCH=<name>`), then continue there. On main with nothing unpushed → abort:
_"Already on main with nothing to merge. Switch to a work or feature branch first."_

Resolve the branch via `coordinator-current-branch`, compare against its remote (`git log
origin/<branch>..HEAD`), push with `--set-upstream` if unpushed commits exist.

---

## Step 3: Release Surface (your call)

`d6`/`d3`/`d5`/`d1`/`d2` are directives (illegal-path scan, coverage gate, portability sweep,
tag-prefix resolution, release-tag cut). Judgment:

**Ship verdict (`ship_verdict`).** EM stages one line, PM confirms or overrides; don't merge on
`hold`/`split` without PM redirect. `/staff-session vp-product` gives a structured second opinion.

```markdown
**Ship verdict:** [ship | ship-behind-flag | hold | split | spike-only] — [one-sentence rationale]
```

| Verdict | Meaning |
|---|---|
| ship | AC satisfied/waived, evidence supports merge |
| ship-behind-flag | Ready but gated — name the flag |
| hold | Don't merge — name the concern |
| split | Two changes land separately — name them |
| spike-only | Informative only, don't merge |

**Release-note framing.** Prefer the most recent `state/week-changelog/*-pending-release.md`
accumulator; absent, draft inline grouped by impact (Added/Changed/Fixed/Deps/Internal, omit
empty — even a trivial merge gets one line; template: wiki). Prepend to a repo-root `CHANGELOG.md`
if one exists, committed before Step 5. Skip only for `tasks/`/`tmp/`-only merges (still get an
"Internal" line).

**Demo path** (user-visible merges) — append a Demo Path section (template: wiki) to the PR body.

**Version-bump (`version_bump_final`).** `version_bump` is a proposal only — confirm/override
before `d2` fires (mode detail: wiki).

**Portability (`portability_disposition`).** Empty sweep report continues silently; non-empty needs
a per-finding PM disposition (options: wiki). Not a merge blocker;
`COORDINATOR_OVERRIDE_PORTABILITY=1` skips it for a one-off.

---

## Step 4: UE-specific checks (`project_type: game-dev`, `project_subtypes: unreal`)

Otherwise skip. Full table: wiki. UBT gate and reverse-drift gate have live producers
(`scan_unresolved_ubt_records.py`, `list_reverse_drift_cmds.py`) — non-zero halts with remediation
(`/workday-complete` / `example_game_repo_recover --step reverse-drift`, or the matching
`COORDINATOR_OVERRIDE_*`). Plugin-version-matrix, structural-index-schema, and
customer-facing-install-path touches still need eyeball diff-path classification — no producer yet
<!-- engine-gap: field=merge.touched_path_classes producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->.
- **Plugin version matrix** — detection: touches under `control/plugin/**`. Action: verify the
  5-version CI matrix is green.
- **Customer-facing install path** — detection: touches under `scripts/install-*.{sh,ps1}`.
  Action: verify doc parity and replay `tests/install/`.

A schema bump needs `schema-migration-auditor` dispatched, the Staff Engineer review before merge.

---

## Step 5: Create PR

Compose the PR body via `merge-gate-and-pr pr-body --ship-verdict "$SHIP_VERDICT" --release-notes
"$RELEASE_NOTES" --commit-range main..HEAD` (`d4`), then `gh pr create --base main --head "$BRANCH"
--title "$TITLE" --body "$BODY"`.

If a version bump was suggested but not yet PM-confirmed, surface it in the PR body: _"Suggested
bump: patch ({old} → {new}) — confirm before tagging."_

---

## Step 6: Wait for CI

`gh pr checks --watch`. `ci_failure_interpretation`: "no checks reported" (exit 1) is a pass; a real
failure blocks merge — _"CI failed on {check}. Fix and re-run `/merge-to-main`, or investigate via
`coordinator:systematic-debugging`."_ A flaky-retry re-runs CI instead of blocking.

---

## Step 7: Merge

Pre-merge quiet check: `merge-gate-and-pr active-branch-guard --pr "$PR"` halts if the PR's newest
commit is younger than 300 seconds. Override with the skill's own `--force-merge-active-branch`.

Merge via `gh pr merge` with `--delete-branch`, merge commit (never squash). Recovery recipes for
"base branch policy prohibits" and "head not up to date": wiki. **Merge conflicts** — do not force
through; offer the PM merge-main-in-and-resolve (recommended) or rebase; stop and wait.

CI is advisory; the PR requirement (0 approvals) is the primary gate.

---

## Step 8: Post-Merge Re-Verify Shared Infra

After a conflict-resolved or concurrently-edited merge, confirm each touched file still carries a
canonical phrase from your change at `HEAD` — last-writer-wins can silently revert a naively
resolved hunk. Highest risk: shared infra. Missing phrase → re-apply and push a follow-up commit.

---

## Step 9: Local Cleanup

Check out main (`COORDINATOR_OVERRIDE_BRANCH=1`), pull, delete the local branch. Any stray worktree
found here is debris to clear (`git worktree remove <path>`), not state to keep.

---

## Step 10: Completion-Log Status Flip

Runs when a release tag was cut (`d2` landed); skip otherwise. `mkdir -p
archive/release-notes/`, then `d7` (`merge-release-notes-derive flip-tags <tag> <sha> <date>
$ENTRY_PATHS`) flips every matching entry to the earliest release tag whose history contains it. The
`reconcile-sweep` verb that once preceded the flip is retired with the rest of the completion-
reconcile family; the CLI carries `flip-tags` alone, so there is no unaccounted-commit pass here.
Best-effort `git mv` the pending-release accumulator to `archive/release-notes/`, scoped-commit
`$ENTRY_PATHS` + accumulator + release notes file, push to main.

---

## Step 11: Report

```
## Merged to Main
- **PR:** {url}
- **Merge commit:** {sha}
- **Branch deleted:** {branch} (local + remote)
- **Now on:** main @ {sha}
```

`d8` (`orphan-branch-sweep --format text --severity-min warning`, non-`OK` lines) surfaces other
in-flight branches: _"Multiple work branches in flight — verify these don't carry work intended for
this PR."_

**Negative-spec — the auto-memory drain gate is gone from this ceremony, do not restore it.** PM
directive, 2026-08-07: the gate's cadence at every merge was too aggressive. It stays live at
`/workday-complete` and `/workweek-complete` only.

## Red Flags

**Never:** squash commits; push directly to main. Concurrent-writer caveat: cap commit sweeps at
~6 and accept a moving target — don't loop trying to converge.

## Integration

**Called by:** `coordinator:finishing-a-development-branch` (Option 1); PM/EM directly, never
`/workday-complete`. **Pairs with:** `finishing-a-development-branch` (its Step 5 handles stray
worktree removal the same way).
