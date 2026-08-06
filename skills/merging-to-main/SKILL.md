---
name: merging-to-main
description: "Merges a ready branch to main — release notes, PR, CI wait, cleanup."
argument-hint: "[--force] [--force-merge-active-branch]"
version: 2.0.0
---

# Merging to Main

## Overview

Merge a work or feature branch to main via PR with CI gating, computed by the `merge-assemble`
assembler.

**Announce at start:** "I'm using the coordinator:merging-to-main skill to merge this branch to main."

The assembler computes the mechanical spine — the node ceremony hard-gate, tag-prefix resolution,
the release-tag cut, the coverage gate, the PR body, the portability sweep, the illegal-path scan,
the completion-log flip, and the orphan-branch sweep — and returns one decision object for the
merge. What follows is the judgment residue the assembler cannot resolve for you, plus the handful
of steps (branch recovery, PR creation, the merge itself, local cleanup) that stay outside its
closed CLI table because they depend on live PR/merge state the assembler can't precompute.

Compute it via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/merge-assemble" brief [--tag-prefix <prefix>]`. Every `judgment_points[]` entry in the returned object carries its own guidance inline — describing what each disposition means and how to carry it out, never a recommendation to pick from; resolve each one before its gated directive(s) proceed. Apply via the same CLI's `apply [--session-id <id>] [--force] [--decisions <json>]` once judgment is resolved — `apply`'s own `--force` bypasses only the node ceremony hard-gate (`d0`), nothing else.

**First Officer Doctrine:** EM may refuse to merge and alert the PM if the branch has known issues — the assembler computes gates, it does not override this authority.

---

## Step 1: Test Suite Gate

This ceremony is one of a small set pre-authorized to run the full, unscoped project test suite
(Tier-U) without a live per-run PM grant. Run that Tier-U grant before either test invocation:
`tier-u-grant-cli grant ceremony
"merging-to-main implicit Tier-U grant for the pre-merge unscoped project test suite" --ceremony
merging-to-main`.

The node hook test suite (`d0` — `node --test tests/plugin-ecosystem/run.js`, halt-on-fail; covers
load-bearing infra: coordinator-safe-commit, verify-snippet-sync, coordinator-auto-push,
session-init) is a computed directive. Then detect and run the project's own test runner
(`pnpm test`/`npm test`, `pytest`/`python -m pytest`, `/validate`, or project-specific from
`CLAUDE.md`/`package.json`) — this leg is not in the assembler's closed CLI table (the runner
differs per repo) and stays a manual detect-and-run step. Fail on either → halt: _"Test suite
failed. Fix first, or use `/merge-to-main --force` to bypass for hotfixes."_

**`--force`** (the skill's own flag, distinct from `apply`'s): skips this whole step, including the
Tier-U grant and `d0`. Log: _"Force-merge requested — test suite gate bypassed."_

---

## Step 2: Pre-flight

Commit only paths this session touched — do NOT use `coordinator-safe-commit` here (see
`docs/wiki/scoped-safety-commits.md § Current Doctrine`); the pathspec sits on the commit itself,
no separate `git add` needed.

**Current branch:**
- On a work/feature branch → continue.
- On main with unpushed commits ahead of `origin/main` → auto-recover via `merge-recovery-and-tag-cut recovery-branch` (syncs local main to `origin/main`, cuts a fresh `work/<host>/<date>` branch off the pre-sync state, pushes it, hard-resets main, returns to the new branch, prints `BRANCH=<name>`), then continue there.
- On main with nothing unpushed → abort: _"Already on main with nothing to merge. Switch to a work or feature branch first."_

Resolve the current branch via `coordinator-current-branch`, compare against its remote
(`git log origin/<branch>..HEAD`), and push with `--set-upstream` if unpushed commits exist.

---

## Step 3: Release Surface (judgment residue)

The assembler's decision object carries the readiness gates as directives — `d6` (illegal-path
scan), `d3` (unscoped review-coverage gate, `origin/main..HEAD`), `d5` (portability sweep,
gated on the `portability_disposition` judgment point), `d1`/`d2` (tag-prefix resolution and the
release-tag cut, gated on `ship_verdict` and `version_bump_final`). What remains is judgment:

**Ship verdict (`ship_verdict`).** Every gate has reported — ship, or hold? EM stages one line, PM
confirms or overrides; don't merge on `hold`/`split` without PM redirect. The VP-of-Product lens is
the PM's lens, applied in meatspace — request `/staff-session` with `vp-product` for a structured
second opinion.

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

**Release-note framing.** Prefer the most recent `state/week-changelog/*-pending-release.md`
accumulator as the PR body's release notes when one exists. Absent, draft inline: group commits by
impact (**Added / Changed / Fixed / Deps / Internal** — omit empty sections; even a trivial
single-commit merge gets a one-line note, never a skip):

```markdown
## v{suggested-version} — {YYYY-MM-DD}
### Added / Changed / Fixed / Deps / Internal
- {one-line bullet per logical change}
```

If a repo-root `CHANGELOG.md` exists, prepend the entry there and commit the update on the branch
before Step 5. Skip drafting only when the merge touches exclusively `tasks/`, `tmp/`, or other
internal-only paths — a one-line "Internal" entry beats a skip even then.

**Demo path** (user-visible merges only) — append to the PR body:

```markdown
### Demo Path
**Setup:** [commands, seed data, environment]
**Steps:** 1. [action] 2. [action] 3. [observe result]
**Expected:** [what should happen] | **Known limitations:** [what *not* to claim]
```

**Version-bump choice (`version_bump_final`).** The assembler's `version_bump` field is a proposal
only. Confirm the number or override it before `d2` fires. `coordinator.local.md`'s `tag_anchor` /
`version_source` / `tag_prefix` fields select git-tag-only vs. GitHub-release publish mode.
`Claude Prime` (`source_is_live`
propagation) is never tagged — the assembler skips the tagged-publish leg silently there, and
silently when the bump is skip-eligible or the merge is internal-only.

**Portability disposition (`portability_disposition`).** `d5` runs the sweep; an empty report
continues silently. A non-empty report needs a PM disposition per finding — **fix-now** (apply
inline or `--apply-safe`, sibling category only), **allowlist-with-reason**
(`portability-allowlist.toml`), or **accept-and-track** (note in PR description, merge proceeds).
Not a merge blocker; `COORDINATOR_OVERRIDE_PORTABILITY=1` skips the whole leg for a one-off.

---

## Step 4: UE-specific checks (`project_type: game-dev`, `project_subtypes: unreal`)

| Check | Detection | Action |
|---|---|---|
| **Plugin version matrix touched?** | `control/plugin/**`, `control/server/**`, `.github/workflows/build-plugin-*.yml` | Verify CI matrix run for all 5 UE versions (5.3–5.7) is green; flag if the diff post-dates the last green CI run |
| **Structural-index schema bumped?** | `mcp_server/structural_index/*.py`, `project-rag/cli.py`, `extract_structural_index.py`; content-grep `MIN_SUPPORTED_SCHEMA`/`authority_version`/`manifest_version` | Dispatch `schema-migration-auditor`; require the Staff Engineer review before merge |
| **Customer-facing install path touched?** | `scripts/install-*.{sh,ps1}`, `scripts/lib/install-shell-utils.{sh,ps1}`, `marketplace.json` | Verify customer-deployment doc parity; replay `tests/install/` |
| **UBT gate** | `scan_unresolved_ubt_records.py` applies to cwd | Scan `state/review-trail/` for `*.ubt-compile.pending.json` without a resolved sibling; halt with remediation (`/workday-complete`, or `COORDINATOR_OVERRIDE_UBT_GATE=1`) |
| **Reverse-drift gate** | `list_reverse_drift_cmds.py` applies to cwd | Non-zero exit → halt with remediation (`example_game_repo_recover --step reverse-drift`, or `COORDINATOR_OVERRIDE_REVERSE_DRIFT=1`) |

Otherwise skip. Mirrors `/workweek-complete` Step 4g's UBT/reverse-drift legs.

---

## Step 5: Create PR

Resolve the current branch via `coordinator-current-branch`, then compose the PR body via
`merge-gate-and-pr pr-body --ship-verdict "$SHIP_VERDICT" --release-notes "$RELEASE_NOTES"
--commit-range main..HEAD` (`d4`) — it prints the composed body (ship verdict + release notes +
optional demo path + a collapsed `<details>` commit log). Create the PR: `gh pr create --base main
--head "$BRANCH" --title "$TITLE" --body "$BODY"`.

If a version bump was suggested but not yet PM-confirmed, surface it in the PR body: _"Suggested
bump: patch ({old} → {new}) — confirm before tagging."_

---

## Step 6: Wait for CI

`gh pr checks --watch`. **CI interpretation (`ci_failure_interpretation`):** "no checks reported"
(exit 1) is a pass — no CI configured. A real failure blocks merge — report which check failed and
stop: _"CI failed on {check}. Fix and re-run `/merge-to-main`, or investigate via
`coordinator:systematic-debugging`."_ A flaky-retry re-runs CI instead of blocking.

---

## Step 7: Merge

Pre-merge quiet check (5-minute activity gate): `merge-gate-and-pr active-branch-guard --pr "$PR"`
halts if the PR's newest commit is younger than 300 seconds. Override with the skill's own
`--force-merge-active-branch` flag (pass `--force` through to the guard, or skip the gate entirely).

Merge via `gh pr merge` with `--delete-branch`, merge commit (never squash) — preserves history as
breadcrumbs.

- **"base branch policy prohibits the merge"** → retry with `--auto`; poll `gh pr view` until
  `MERGED`.
- **"head branch is not up to date with base"** → `git fetch origin main`, `git merge origin/main`,
  push, retry `gh pr merge`.
- **Merge conflicts (`merge_conflict_resolution`)** — do not force through. Report the conflicting
  files and offer the PM the standard choice: merge main in and resolve, or rebase (recommend the
  former); stop and wait.

Rulesets do not require status checks or block force push — CI is advisory; the PR requirement
(0 approvals) is the primary gate.

---

## Step 8: Post-Merge Re-Verify Shared Infra

After a conflict-resolved or concurrently-edited merge, confirm each file this branch touched still
carries a canonical phrase from your change at `HEAD` — last-writer-wins silently reverts naively
resolved hunks. Highest risk: shared infra (`~/.claude/`, config files, shared scripts). A missing
phrase means the change was overwritten — re-apply and push a follow-up commit immediately.

---

## Step 9: Local Cleanup

Worktrees are forbidden — work happens on the daily branch. An override exists but requires
explicit PM permission via the EM. If this branch is on a stray worktree anyway, that's debris to
clear, not state to keep.

Check out main (`COORDINATOR_OVERRIDE_BRANCH=1`), pull, delete the local branch. On a worktree:
`git worktree remove <path>` instead.

---

## Step 9b: Auto-Memory Drain (blocking gate, no consumes-manifest CLI)

Auto-memory is ephemeral by definition — this ceremony drains it to zero every close. Run:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-auto-memory-drained" --root .
```

Exit 0: nothing under the auto-memory store — proceed to Step 10. Exit 1: it prints every
residual `*.md` path (index and/or sibling body files) to stderr. For EACH one, resolve exactly
one disposition — silence is not a disposition:

- **PROMOTE** — write the fact to its durable home (doctrine, wiki, `docs/decisions/`,
  `state/lessons/` via `/learn-lessons`, or the orientation cache — per C1's channel contract) and
  note the target path. This is a real authoring act: most memory rows are private shorthand that
  will not survive a reader who lacks the session, so restate the claim in the destination's own
  voice rather than copying the row verbatim.
- **DROP** — say so explicitly.

Then delete every file the gate named (the gate itself never mutates — it only detects residue)
and re-run the command above to confirm exit 0. Record the full disposition list — path,
PROMOTE/DROP, and target path for each PROMOTE — in Step 11's report; the memory dir carries no
git history, so this ceremony's own output is the only record of what was destroyed.

**On the first gate invocation this ceremony exiting 0 immediately (no residue ever printed):**
the store was empty from the start — omit the `**Auto-memory drain:**` line entirely.
**If the gate ever printed residue this run, even once:** the disposition list is mandatory in
the report — even though the store is empty by the time you write it. Omitting the line at that
point would erase the only record of what was destroyed.

ZERO MEANS THE DIRECTORY, NOT THE INDEX — a drained `MEMORY.md` with surviving sibling body files
still fails the gate and is not done. This complements the write-time size cap on the auto-memory
store (a spatial bound), not a duplicate of it (a temporal bound); neither supersedes the other.

---

## Step 10: Completion-Log Status Flip

Runs whenever the assembler cut a release tag this merge (`d2` landed). Skip when it didn't —
either the bump was skip-eligible or the merge touched only internal-only paths, so no tag exists
yet to attribute entries against.

1. `mkdir -p archive/release-notes/`.
2. Advisory sweep: `merge-release-notes-derive reconcile-sweep` — prints unaccounted-commit warnings
   per `pending-release` entry; non-blocking, fold and resolve before continuing.
3. `d7` (`merge-release-notes-derive flip-tags <tag> <sha> <date> $ENTRY_PATHS`) flips every matching
   `pending-release` entry, each resolved to the earliest release tag whose commit history actually
   contains it — not blanket-stamped with this merge's tag.
4. Best-effort: `git mv` the pending-release accumulator, if one exists, to
   `archive/release-notes/`.
5. Scoped commit (never `git add -A`) of `$ENTRY_PATHS` + the archived accumulator + any release
   notes file, then push to main.

---

## Step 11: Report

```
## Merged to Main
- **PR:** {url}
- **Merge commit:** {sha}
- **Branch deleted:** {branch} (local + remote)
- **Now on:** main @ {sha}
- **Auto-memory drain:** [Step 9b disposition list: path -> PROMOTE(target) or DROP, one per line — omit entirely ONLY if the gate exited 0 on its first invocation this ceremony; mandatory if it ever printed residue this run, even though the store is now empty]
```

`d8` (`orphan-branch-sweep --format text --severity-min warning`, filtered to non-`OK` lines) surfaces
other in-flight branches: _"Multiple work branches in flight — verify these don't carry work
intended for this PR."_

## Red Flags

**Never:** squash commits; push directly to main.

**Concurrent-writer caveat:** running alongside an active concurrent writer, cap commit sweeps at
~6 and accept a moving target — don't loop trying to converge.

## Integration

**Called by:** `coordinator:finishing-a-development-branch` (Option 1); PM/EM directly (no longer
called by `/workday-complete`).

**Pairs with:** `coordinator:finishing-a-development-branch` (its Step 5 handles stray worktree
removal the same way).
