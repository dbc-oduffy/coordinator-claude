# Daily-branch discipline

> **The rule.** In any project's main checkout, the active branch is **either** an active workstream branch **or** `main` (read-only). Two legitimate workstream shapes:
> 1. **Canonical** — span-aware `work/{machine}/{date-or-span}` (e.g. `work/striker/2026-05-07` or `work/striker/2026-05-07to08`). Hook-allowed by default.
> 2. **Named long-lived workstream** — `migration/...`, `release/...`, `feature/<name>`, etc., created via inline `COORDINATOR_OVERRIDE_BRANCH=1` when the PM authorizes a multi-day bus that's structurally separate from generic dailies. Once it exists with commits ahead of main, workday-start treats it as a legitimate workstream bus and reconciles it with origin/main daily, the same as a canonical branch.
>
> The hook polices branch *shape* at create-time, not branch *date* at workday-start — commit-time date-enforcement (Check 6) was decommissioned 2026-05-07 per PM call. The daily ritual is **reconcile with origin/main** (`/workday-start` Step 0.4.5), not branch-rotation. Cutting a fresh daily off main when an active workstream exists would abandon ongoing work; doctrine 2026-05-13 explicitly prohibits this.
>
> **Honest-name rule.** At midnight-rename (Step 0 Check 4): `COMMITS_AHEAD > 0` → span suffix `{start}to{today}` (honest WIP); `COMMITS_AHEAD == 0` → today-only `work/{machine}/{today}` + ff-to-main, because the history has all merged and a span would advertise WIP that no longer exists. Still reconciliation, not rotation — the ref is renamed, not abandoned. (`/merge-to-main` *deletes* the merged branch; rename preserves it.)

> **The shape.** An active workstream branch (canonical or named) is a **shared bus for every concurrent EM session on this machine** — not a single-session workspace. Multiple sessions committing in parallel is the default; sibling commits and out-of-scope dirty files belong to peer sessions, not to contamination. Scoped-staging (`coordinator-safe-commit --scope-from`, runtime overlap gate) is the everyday discipline that makes shared-bus safe.

## Why

Postmortem source: a peer repo's `archive/2026-05-05_branch-sprawl-postmortem.md` (private — citation pointer for the source authors).

The anti-pattern was mechanical:

```
git checkout -b feature/advisory-2026-05-05   # create sibling branch
git stash push -u                             # park WIP on it
git checkout -                                # back to daily
```

Result: an empty branch (zero commits) and a dangling stash labelled with that branch. `git branch -d` later cleans the branch but `refs/stash` is a separate ref namespace — the stash survives every consolidation, accumulating across weeks. Multiple sibling stashes referencing long-dead branches is the silent compounding mechanism.

The chokepoint is step 1. Block off-daily branch creation/switch and the rest cannot happen.

### Orphan-branch prevention (sibling branches with zero commits)

Beyond the postmortem's checkout-stash-checkback anti-pattern, two adjacent failure modes share the same generator and ship as a single hardened pipeline (PR #57, v1.6.0, 2026-05-01):

- **Empty branches with dangling stashes.** Creating a sibling branch and parking WIP via `git stash` produces a stash labelled with that branch. Even after `git branch -d` cleans the branch, `refs/stash` is a separate ref namespace — the stash survives every consolidation and accumulates across weeks.
- **Branches that "look shipped" but aren't.** A branch whose PR was merged still accrues commits if the source branch isn't deleted; those post-merge commits are not on `origin/main` despite the branch's "merged" status.

Both modes are caught by `orphan-branch-sweep.sh` with three severity tiers:

- **CRITICAL** — merged PR exists AND `commits_after_pr_merge > 0`. The branch claims "shipped" but carries unshipped work.
- **WARNING** — no PR exists AND `ahead > 0` AND (branch-name date is ≥2 days old OR `age_h > 36`). Calibrated against the parallel-machine workflow so a sibling machine's same-day daily isn't flagged.
- **OK** — everything else.

Flags: `--format json|text`, `--severity-min ok|warning|critical`, `--include-remote`, `--max-age-days N` (default 30).

The companion `sync-main.sh` enforces the invariant `local main == origin/main` before any branch creation. On `main`: `git fetch origin main && git pull --ff-only`. On non-main: `git fetch origin main:main` (refspec form updates local main without checkout — load-bearing per the Staff Engineer F5). `--strict` makes the >50-commits-behind warning a hard error.

### `/workday-start` Step 0 — Branch Reconciliation Decision (A/B/C)

When branch consolidation hits a merge conflict, the EM presents a structured decision rather than improvising:

- **A — Run `/consolidate-git` now.** Absorb the conflicting branch into the current daily.
- **B — Defer.** Write `tasks/.deferred-branches.md` with a re-check date. Surface prominently next interactive workday-start.
- **C — Archive as dead.** Move to `archive/{machine}/{date}/{old-branch-name}`.

Interactive: hard-block until PM picks. Non-interactive (overnight, no TTY): auto-defer with `reason="auto-deferred, awaiting PM"` and `re-check=today`.

### Cross-machine identity considerations

The branch-name date is **local** (`date +%Y-%m-%d`). The orphan sweep's WARNING tier is calibrated by last-commit time (`tip_ct`) rather than branch-name date — this prevents false-positive WARNING noise on legitimate active span branches like `work/<machine>/2026-05-01to07`. Sessions that span midnight roll forward via `/workday-start`; see [Midnight crossings](#midnight-crossings).

Portable timestamp parsing matters. The 5-min quiet-gate before merge uses `gh pr view --json commits` for timestamps (no local fetch dependency) and Python ISO-8601 parsing — `date -d` differs across Windows/macOS/Linux. Pre-implementation sanity check: verify `gh` returns commits in chronological order; otherwise sort: `.commits | sort_by(.committedDate) | last`.

## Enforcement surfaces

Two contact-points (see CLAUDE.md tripwire):

1. **`session-ensure-branch.sh`** — SessionStart hook. Fires at `startup`/`clear` events. When the active branch is `main`, detached HEAD, or a zero-ahead non-span branch, cuts `work/{machine}/{today}`, pushes, and emits a one-line heads-up via `additionalContext`. Silent no-op on a valid `work/*` span branch. Active behavior, not a block — the agent is moved, never nagged. (`block-off-daily-branch.sh` retired 2026-07-05, strang-04 — replaced by this SessionStart branch-ensure hook.)
2. **Doctrine** — CLAUDE.md § Concurrent-EM Git Operations, first bullet. Authoritative reference for the rule.

## Supported "park WIP" recipes

The hook does **not** ban stash. It bans creating a sibling branch first. Park WIP via:

- **Commit on the daily.** Intentionally messy commits are fine on `work/*` branches — they're quick-saves, not history.
  ```
  git add -- <paths> && git commit -m "WIP: <subject>"
  ```
  Test-breadth posture at commit time (commit ≠ test gate; full tier at cadence only): → `docs/wiki/test-design-discipline.md § Posture: Proportional Test-Running`.
- **Stash on the daily.** Do not change branches first.
  ```
  git stash push -u -m "<subject>"
  ```

The unsupported move (and the structural reason this page exists):

```
git checkout -b feature/X && git stash push -u && git checkout -
```

This is what produces empty branches and orphan stashes by construction. The hook denies step 1.

**Stash on a shared bus is owner-ambiguous.** `refs/stash` is a single global ref per repo, NOT scoped per session — on the shared daily branch, `stash@{0}` may belong to a sibling EM. Always push WITH a message (`git stash push -u -m "<subject>"`) and NEVER `git stash pop` without `git stash list` confirming `stash@{0}` is yours (branch + subject match). A `git stash push -- <path>` that prints *"No local changes to save"* is a no-op (a sibling may have already committed your edit) — a subsequent bare `pop` then pops the sibling's stash. Full stash hazard catalog (stale-stash diff-before-pop, wrong-owner pop, recovery): [`concurrent-em-hazards.md`](./concurrent-em-hazards.md) §§ H6–H7.

## Override

`COORDINATOR_OVERRIDE_BRANCH=1` — bypasses the PreToolUse hook for one Bash call. Logged to:

- `.git/coordinator-sessions/{session_id}/branch-discipline.log` (per-session denials)
- `.git/coordinator-sessions/_branch-overrides/overrides.log` (override invocations)

Optional companion: `COORDINATOR_OVERRIDE_BRANCH_REASON="<text>"` — written alongside the override entry. Encouraged.

Inline-only — never export. The skills that legitimately need the override set it on the single offending command:

- `/workday-start` — creates `work/{machine}/{today}` or renames active branch forward to span form (`git branch -m`).
- `/merge-to-main` — may operate against integration branches during the merge ceremony.
- `/consolidate-git` — by definition switches across branches to absorb commits.
- `/workday-complete` Step 10.5 — preemptive branch rename (optional prompt).

If you're tempted to export the variable in your shell, stop and ask: am I building a fourth skill that needs it? Add it to the doctrine tripwire and to this page.

## Never test-commit on a live auto-push branch

The post-commit auto-push hook pushes every commit on a `work/*` / `feature/*` branch to origin immediately — so a throwaway `git commit --allow-empty` made to test signing or commit mechanics is on the remote before you can drop it, and removing it then needs a force-push that is unsafe with concurrent EMs sharing the branch. **Never make a test/experimental commit on a live auto-push branch.** Test signing and commit mechanics in a throwaway temp repo (`git init` in a tmpdir), or sign without committing at all (`ssh-keygen -Y sign`). Composes with [`scoped-safety-commits.md`](./scoped-safety-commits.md) § Smoke-Testing the Commit Helper — Always Use `--dry-run` (the same "a smoke test that actually commits is a real commit" hazard, one layer up at the push surface). Source: example-game-workbench-repo.

## Failure modes the hook catches

Mapped to the postmortem patterns:

| Postmortem pattern | Caught by | How |
|---|---|---|
| Pattern 2 — checkout-stash-checkback anti-pattern | PreToolUse hook | Denies the `checkout -b feature/X` at step 1 |
| Pattern 3 — orphan stashes outlive deleted branches | Eliminated structurally | If non-workstream branches never exist, stashes can't reference them |
| Stale-day inheritance (yesterday's branch carried into today) | `/workday-start` auto-rename | Silently renames `work/<machine>/2026-05-06` → `work/<machine>/2026-05-06to07` and notes it in the Morning Briefing; no commit block |
| Pattern 4 — speculative `feature/<topic>-<date>` naming from planning prose | PreToolUse hook | The branch can't be created, so the cosmetic naming has nowhere to land |

## Mixed-Case Branch Tripwire

**Problem (2026-05-07):** `lib/coordinator-daily-branch.sh:129` normalizes branch names to lowercase before the allow-list check, silently accepting non-canonical (mixed-case) branch creation. When `git checkout -b work/<MACHINE>/2026-05-07` is run, the hook allows it because the normalized form is in the allow-list. `.git/HEAD` stores `work/<MACHINE>/2026-05-07`, but the on-disk canonical ref is lowercase. Result: `git branch --show-current` returns uppercase, `git push origin <uppercase>` fails ("cannot be resolved to branch").

**Fix:** `cs_is_canonical_branch` function checks whether the proposed `work/*` name is already in canonical lowercase form. Creation of mixed-case `work/*` names is rejected at hook time with a remediation message naming the canonical form.

**Defense-in-depth layers** (all now in place):
1. Creation-time hook rejection (cs_is_canonical_branch)
2. Runtime canonicalization in coordinator-auto-push (case-agnostic push)
3. Migration helper: `migrate-branch-canonical-case.sh` (idempotent: rename local + remote)
4. Doctrine: CLAUDE.md § Concurrent-EM Git Operations bullet 1 span-aware framing

**Contact points requiring sync:**
1. `lib/coordinator-daily-branch.sh` (shared library — cs_is_canonical_branch + cs_compute_machine)
2. `coordinator/CLAUDE.md § Concurrent-EM Git Operations` bullet 1
3. This wiki (daily-branch-discipline.md)
Note: `hooks/scripts/block-off-daily-branch.sh` (PreToolUse hook) was retired 2026-07-05 (strang-04); replaced by the `session-ensure-branch.sh` SessionStart hook.

Source: `archive/specs/2026-05-07-mixed-case-branch-creation-tripwire.md` (formerly `docs/plans/2026-05-07-mixed-case-branch-creation-tripwire.md` @ d0fcc842).

## Span-Aware Branch Naming

Daily branches can now carry across days as a span: `work/{machine}/{date}to{dd}` (e.g. `work/<machine>/2026-05-07to08`). This eliminates the need for a branch rename at every midnight crossing. Optional Step 10.5 in `/workday-complete` prompts for a preemptive end-of-day rename to tomorrow's suffix using atomic-rename-with-rollback.

**Midnight crossings:** The wiki's Midnight crossings section has been rewritten around the span-aware rename flow. No grace window required — the span form is valid for any consecutive date range.

Source: `tasks/daily-branch-doctrine-rethink/` Phase 4+5 execution, 2026-05-07.

## Midnight crossings

Sessions that span midnight are normal and expected. The hook polices branch *shape*, not branch *date* — there is no commit block after midnight, and no grace window concept.

**What happens at midnight:** nothing automatic. The session continues committing on `work/<machine>/2026-05-06` (or whatever the active branch is). The first `/workday-start` after midnight performs the rename automatically.

**Span-aware rename flow:** when `/workday-start` detects that the active branch's start-date is yesterday (or earlier) and there were commits within the last 48h, it renames silently — no prompt — and emits a one-line notice in the Morning Briefing:
> "Renamed `work/<machine>/2026-05-06` → `work/<machine>/2026-05-06to07` (crossed midnight)"

This is engineering housekeeping under the EM's remit, not a product call; the EM does not ask. PM can revert via `git branch -m` if they object. The rename is atomic (`git push --atomic origin <new>:<new> :<old>`) with local rollback on remote failure.

**Preemptive rename:** `/workday-complete` Step 10.5 offers to rename forward preemptively (e.g. to `2026-05-06to07`) before the session ends, so tomorrow's first commit doesn't trigger the prompt. Optional; default off.

**Retired hook's role (historical):** `block-off-daily-branch.sh` enforced *shape* — `work/{machine}/{anything-that-parses}` was allowed; `feature/X` or bare topic branches were denied. Retired 2026-07-05 (strang-04). The SessionStart `session-ensure-branch.sh` hook now actively cuts the correct branch at session open rather than blocking mid-session checkout attempts.

## Edge cases the hook does NOT catch

- **`git checkout <sha>` / `git checkout <tag>`** — detached HEAD. Allowed (not a branch op). Commit-time check catches any subsequent commit, since the resulting `HEAD` is not a branch ref.
- **`git checkout -- <path>`** — file restore. Allowed (no branch involved).
- **`git checkout origin/<remote>`** — produces detached HEAD. Allowed; same commit-time fallback.
- **`git checkout --orphan <name>`** — the hook checks the orphan name and denies if it is not an allowed workstream branch or main. `--orphan` onto an allowed name is permitted.
- **Linked worktrees (already created)** — the hook exits silently when run inside a `worktrees/` git-dir. Doctrine bans worktree creation; the audit catches existing ones separately. The hook's `worktree add` deny prevents new ones.
- **Compound commands beyond the first git op** — the hook inspects the first `git <branch-op>` it finds. Subsequent ops in `git checkout -b foo && git checkout -b bar` are not separately validated, but step 1 already denies, so step 2 doesn't run.
- **`git -C <path>` / `git --git-dir=<path>/.git`** — cross-repo forms are policed by the same shape rules (allowed if the target branch name is canonical `work/{machine}/{date-or-span}` or `main`; denied otherwise). No override needed for shape-canonical names. The parser captures the `-C <path>` value to validate `is_local_branch` and `@{-1}` resolution against the sibling repo's refs, not `$GIT_ROOT`. (Relaxed from outright deny by spec `2026-05-08-daily-branch-discipline-cross-repo.md`.)
- **`cd <path> && git ...`** — cross-repo via `cd` is denied outright when a branch-mutating subcommand follows; the hook subprocess cannot resolve the post-`cd` cwd (`$GIT_ROOT` is captured at entry, before the `cd`). Use `COORDINATOR_OVERRIDE_BRANCH=1` for legitimate cd-then-git cross-repo work.

**`session-init.sh` committing to `main` during orphan-handoff sweep (fixed 2026-05-20)**

`session-init.sh` ran an orphan-handoff sweep that called `git mv` + `git commit` on whatever branch was currently checked out. Post-`/merge-to-main`, the active branch was often `main` — violating read-only-main doctrine and causing `sync-main.sh` to abort on the next workday-start (`local main != origin/main`).

Fix: a branch guard was added at the top of the sweep block. If the current branch is `main`, orphan handoffs are noted but not committed — they are picked up by the next session that boots on a live work branch.

This failure mode is not hookable at the PreToolUse layer (the script runs at SessionStart, not from a Bash tool call). The guard lives in the script itself.

## "Shipped" definition — branch tip ≠ origin/main

`check-shipped-on-main.sh <commit>` is the authoritative gate. Branch-tip is not shipping. PR-merged-from-this-branch is shipping IFF no further commits landed on the source branch after the merge. Run it before any handoff/doc/lessons/memory update asserts shipping. Edit-A wording in CLAUDE.md § Verification Before Done is the doctrine surface; this script is the enforcement.

## R-3 Sonnet-dispatch prohibition (verbatim)

Inlined in every Sonnet-dispatching autonomous skill (`/update-docs`, `/distill`, `/architecture-survey`, `/mise-en-place`, `/workday-complete`, `/workweek-complete`):

> DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly.

Tripwire entry in CLAUDE.md § "Adding a Convention to the Coordinator System" enumerates these skills. New write-capable autonomous skills must be added there.

## Verifying handoff premises (shared-bus reconciliation)

The active workstream branch is a shared bus across concurrent sessions, so handoffs authored against it can be stale by the time a successor reads them. Two reconciliation tripwires before treating a handoff as ground truth:

- **Handoff red-counts are hypothesis, not baseline.** Handoff-cited failure counts (red tests, broken paths) are hypothesis, not baseline. Before treating the count as actionable, `git stash push -u` your local changes, check out the handoff's claimed HEAD, and re-run — the count may already be stale from concurrent commits or local dirty state.
- **Same-session staleness — pre-write the diff.** Before writing a handoff, grep the workstream's commits since session start (`git log --since='session-start' --oneline`) to distinguish in-session fixes (already shipped to branch) from refactor-deferred work. Authors conflate these into a single "pending" bullet, stranding successors.

## `git log origin/HEAD..HEAD` misleads on feature branches

*2026-05-16, example-game-workbench-repo.* `git log origin/HEAD..HEAD` is a common shape for "what hasn't been pushed yet?" — but `origin/HEAD` is the *remote's default branch* (almost always `origin/main`), not the upstream of the current branch. On any feature/work branch, this query returns "every commit since main diverged," which on a span branch is days of work, not the unpushed delta.

**Rule:** for "what's unpushed on this branch?" use `git log origin/$(git branch --show-current)..HEAD`. The right comparand is the current branch's own upstream, not the remote default. The cs_compute_machine / cs_is_canonical_branch path correctly resolves the canonical lowercase form; downstream `git log` callers must use that form, not `origin/HEAD`.

This bites worst on script wrappers and skill-body procedures that paste `origin/HEAD..HEAD` from a how-to that was written against `main`-only workflows.

## Rewording a buried commit on a shared dirty-tree branch — plumbing only

*2026-05-26, project-rag.* To reword a commit that concurrent sessions have buried under later commits (and left uncommitted WIP in the tree), `git rebase` aborts on the dirty tree and `git checkout --detach` reverts tracked files — both risk the sibling's work. **Use pure plumbing, never `rebase`/`checkout`:** plumbing rebuilds the commit chain as objects and swings the branch ref atomically, never touching the working tree or index.

1. Rebuild the target: `git commit-tree <tree> -p <parent> -F msg` — reuse each child's exact `^{tree}` with rewritten parents, preserving author/committer ident+date.
2. Replay each child reusing its tree.
3. **GATE on `final^{tree} == old_tip^{tree}`** before moving the ref — proves the rewrite is content-identical.
4. `git push --force-with-lease=<branch>:<old-origin-sha>` so a racing sibling push aborts safely.
5. Abort if any commit in range is a merge — single-parent reuse is unsafe.

Cross-referenced as H8 in [`concurrent-em-hazards.md`](./concurrent-em-hazards.md). Default discipline remains: prefer new commits over `--amend` on a shared bus; only reach for plumbing when a subject genuinely must be corrected.

## Peer-session detection on the shared bus

The bus is shared, so a sibling EM may be co-driving — detection is read-side and explicit:

- **Peers are visible via remotes, not `--branches`.** `git branch --branches` is structurally wrong for concurrent-EM detection; enumerate peer machines' active work via `git for-each-ref refs/remotes/origin/work/` (or `git log origin/work/{peer}/*`).
- **Before authoring an overlapping code fix**, run a `git log --oneline -- <target-paths>` peer check — a sibling may have already landed it; grep sibling plans before reverting apparent "out-of-scope drift" as contamination.
- Pickup- and plan-time concurrent-work surfacing is catalogued in [`concurrent-em-hazards.md`](./concurrent-em-hazards.md) § "Detecting Concurrent Work at Pickup / Plan-Time".

## Workstream-complete chain-diff scoping on long-lived shared branches

**`merge-base origin/main..HEAD` sweeps the ENTIRE shared daily branch, not just the current session's commits.** On a long-lived span branch (`work/<machine>/2026-05-26to27`) that carries multiple sessions' worth of commits, a workstream-complete diff using this range surfaces all prior sessions' work — making the review meaningless (too broad) and the commit subject misleading.

Scope the workstream-complete review to the session's own commits instead:

```bash
# Commits authored during this session only:
git log --oneline <session-start-sha>..HEAD
git diff <session-start-sha>..HEAD
```

This is especially important for **spinoffs** (`predecessor: none`) — a spinoff operates on the same shared branch but represents a distinct workstream fork. Its chain-diff must not silently include the parent chain's commits. Record `session-start-sha` at `/pickup` time (or session open) to make the scoping mechanical.

## Machine-token derivation — one deliberately-seeded canonical source

The machine token embedded in branch names (`work/{machine}/{date}`) must come from a single, explicitly-seeded canonical source — not from an existing branch name, not from an eventually-consistent substrate label, and not from a hostname value that may have drifted inside a long-running process.

### Incident synthesis: two failures, one class

**2026-06-11 failure (stale inherited label).** Branch `work/striker/2026-06-11` was authored on the Mac (BettaAir), not Striker, because the authoring session inherited the wrong machine token from yesterday's substrate. The orientation_cache pinboard, handoff body, and branch name all propagated the wrong name — no internal contradiction to surface the error. This incident produced the original rule (line 250, below): *"derive the machine token from `hostname` … or from `machine-local get machine-name` (registry helper), not from copying the previous day's branch token."*

**2026-06-22 failure (stale per-process hostname).** A session launched before a machine-rename propagated to its process environment kept recomputing a stale slug from `hostname` on every call. The branch forked silently into a second slug (`work/macbookair/*` alongside `work/betta-air/*`). Same class: a value gone stale relative to true machine identity.

**Synthesis.** Both incidents are the same failure class — any value that re-derives machine identity from a potentially-stale source silently forks branch lineage. The fix is **one deliberately-seeded canonical value** that is written once at a known-good moment and detected-then-fail-loud on drift, rather than silently trusted.

### Layered precedence — `cs_compute_machine`

The resolver (`cs_compute_machine`, in `lib/coordinator-daily-branch.sh`) applies this precedence:

```
$COORDINATOR_MACHINE           → highest-precedence explicit override, unchanged
machine-local get coordinator.machine_slug  → registry-pinned canonical (primary, when present)
live hostname (cs_compute_machine_live)     → graceful fallback on fresh / pre-seed installs
"unknown"                                   → last resort
```

The resolver is **pure read** — it never writes. This keeps the function safe to call from the PreToolUse hook context. Write authority is confined to `coordinator:install` (eager seed) and `/workday-start` Step 0 (lazy self-heal), per `machine-local-registry.md §7` ("the reader is read-only … write authority belongs to the operator, always").

The `machine-local get coordinator.machine_slug` step degrades gracefully: a 127 (CLI absent, e.g. broken install) or 1 (key absent, e.g. pre-seed) never aborts the resolver — the call is wrapped with `|| true` or a `command -v machine-local` pre-check.

A sibling pure-hostname helper **`cs_compute_machine_live`** (`$COORDINATOR_MACHINE` → `hostname` → "unknown", NO registry read) exists as the seed source and drift-detection comparator. Using it for seeding avoids circularity (seeding from the registry-preferring resolver) and avoids persisting a transient `COORDINATOR_MACHINE` override into the registry.

### The lineage anchor — `:250`

The original 2026-06-11 rule already named `machine-local get machine-name` (registry helper) as an acceptable source alongside `hostname`. This plan (2026-06-22) elevates that registry read to primary and pins the key name as `coordinator.machine_slug`. The elevation is consistent with, not contrary to, the standing rule; the `:250` clause is the lineage anchor.

### Anti-pattern: inheriting a branch token is prohibited

Deriving the machine token by copying yesterday's branch name, reading it from an existing substrate label (orientation_cache, handoff body, branch listing), or from any other eventually-consistent source is **prohibited**. This prohibition is unchanged from 2026-06-11. `coordinator.machine_slug` is not a substrate to be inherited — it is an explicitly-seeded canonical value with operator authority over mutation.

### Drift detection at `/workday-start`

When `coordinator.machine_slug` is already set, `/workday-start` Step 0 compares the persisted slug against `cs_compute_machine_live`. On mismatch, it surfaces the drift to the operator with both remediations as equal branches — it does **not** silently overwrite:

> `Machine-slug drift: persisted='betta-air', this session's hostname yields 'macbookair'.`
> `  Option 1 — stale session: this process has a stale hostname. Keeping persisted value is correct; no action needed.`
> `  Option 2 — machine renamed: run 'machine-local set coordinator.machine_slug <correct-slug>' to update the registry.`

This is the correct adjudicator (interactive context; operator can immediately correct) and honours the global "detect-then-silently-pick is a footgun" principle.

### Snippet-sync verifier

The `cs_compute_machine` function body lives in `lib/coordinator-daily-branch.sh`. The former inline mirror in `hooks/scripts/block-off-daily-branch.sh` and the companion `bin/verify-coordinator-daily-branch-sync.sh` (which asserted byte-equality of that mirror) were both deleted when the hook was retired (2026-07-05, strang-04). The new `session-ensure-branch.sh` hook sources the lib directly — no inline mirror, no sync verifier needed.

## See also

- [`concurrent-em-hazards.md`](./concurrent-em-hazards.md) — the symptom-indexed hazard catalog + recovery procedures for the shared-tree failure class. This page owns commit *location*; that page owns the cross-cutting narrative.
- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — sibling enforcement on commit *content* (which files); this page enforces commit *location* (which branch). The two hooks are siblings on the same PreToolUse Bash matcher.
- [`pretooluse-deny-contract.md`](../pretooluse-deny-contract.md) — JSON deny mechanics.
- `archive/2026-05-05_branch-sprawl-postmortem.md` (peer repo, private) — original incident.
- `~/.claude/plans/2026-05-05-daily-branch-discipline-hook.md` — plan & rollout for the real-time enforcement hook.
- `~/.claude/archive/specs/2026-05-01-orphan-branch-prevention.md` — orphan-branch sweep + sync-main + check-shipped-on-main pipeline (PR #57, v1.6.0).
