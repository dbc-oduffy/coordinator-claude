# Daily-branch discipline

> **The rule.** In any project's main checkout, the active branch is **either** an active workstream branch **or** `main` (read-only). Two legitimate workstream shapes:
> 1. **Canonical** — span-aware `work/{machine}/{date-or-span}` (e.g. `work/machine-a/2026-05-07` or `work/machine-a/2026-05-07to08`). Hook-allowed by default.
> 2. **Named long-lived workstream** — `migration/...`, `release/...`, `feature/<name>`, etc., created via inline `COORDINATOR_OVERRIDE_BRANCH=1` when the PM authorizes a multi-day bus that's structurally separate from generic dailies. Once it exists with commits ahead of main, workday-start treats it as a legitimate workstream bus and reconciles it with origin/main daily, the same as a canonical branch.
>
> The hook polices branch *shape* at create-time, not branch *date* at workday-start — commit-time date-enforcement (Check 6) was decommissioned per PM call. The daily ritual is **reconcile with origin/main** (`/workday-start` Step 0.4.5), not branch-rotation. Cutting a fresh daily off main when an active workstream exists would abandon ongoing work; doctrine explicitly prohibits this.
>
> **Honest-name rule.** At midnight-rename (Step 0 Check 4): `COMMITS_AHEAD > 0` → span suffix `{start}to{today}` (honest WIP); `COMMITS_AHEAD == 0` → today-only `work/{machine}/{today}` + ff-to-main, because the history has all merged and a span would advertise WIP that has already landed. Still reconciliation, not rotation — the ref is renamed, not abandoned. (`/merge-to-main` *deletes* the merged branch; rename preserves it.)

> **The shape.** An active workstream branch (canonical or named) is a **shared bus for every concurrent EM session on this machine** — not a single-session workspace. Multiple sessions committing in parallel is the default; sibling commits and out-of-scope dirty files belong to peer sessions, not to contamination. Scoped-staging (`coordinator-safe-commit --scope-from`, runtime overlap gate) is the everyday discipline that makes shared-bus safe.

## Concurrent sessions share the branch, not only the tree

The worktree ban ("parallel agents share one tree, separated by disjoint file scope, never by
checkout") silently assumes one tree **and** one branch. It is not enough on its own, because the
branch is a property of the tree rather than of the session: **any checkout moves the ref under
every concurrent session in that tree.**

Disjoint *file scope* is a real isolation boundary. Disjoint *branch intent* is not isolable at
all. Two sessions holding genuinely disjoint file scopes still collide the instant one of them
cuts a branch — the peer's next commit, on unrelated files, lands on a branch it never checked
out and knows nothing about.

**The rule.** Cutting or switching a branch mid-execution is out-of-bounds. An executing session
commits to the tree's active branch with scoped pathspecs — the shared-bus discipline above.
Branch transitions belong to the ceremonies that own them (`/workday-start` Step 0,
`/merging-to-main`), which consult the engine's `branch_mutation_verdict` liveness oracle before
mutating: `/workday-start` Step 0 via `session_ensure_branch`, `/merging-to-main`'s on-main
auto-recover arm via `merge-recovery-and-tag-cut`. Both are engine-resident and both fail closed —
an `unknown` verdict counts as refused, and under live peers they decline to cut and say so rather
than moving the ref. **That buys safety, not discipline:** a refused cut leaves the session on
`main` with branch discipline not in force, which is a visible refusal rather than a silent
hazard. A branch genuinely needed outside a ceremony is a **PM-gated ask: warn the PM before
cutting.**

**Why the gate rather than a repair procedure.** There is no safe unilateral recovery once the
ref has moved, in either direction. Switching the tree back, or resetting the offending branch,
breaks the *other* live session in exactly the way yours was broken. The asymmetry is why this is
prevention-only: the sole actor with a view of all live sessions is the PM.

**On Windows this is a load question, not just a correctness one.** Every branch switch rewrites
a large set of files in the shared tree, and each touch lands on a hook surface that is already
the dominant per-tool-call cost on this fleet. Branch churn multiplies file-touch events into
that surface; "fewer branches" is a measurable reduction in a load the operator physically feels,
not tidiness. See `docs/wiki/windows-process-spawn-and-console.md` for the spawn arithmetic.

## Why

A branch-sprawl postmortem from a real incident motivated this page. The anti-pattern was mechanical:

```
git checkout -b feature/advisory-2026-05-05   # create sibling branch
git stash push -u                             # park WIP on it
git checkout -                                # back to daily
```

Result: an empty branch (zero commits) and a dangling stash labelled with that branch. `git branch -d` later cleans the branch but `refs/stash` is a separate ref namespace — the stash survives every consolidation, accumulating across weeks. Multiple sibling stashes referencing long-dead branches is the silent compounding mechanism.

The chokepoint is step 1. Block off-daily branch creation/switch and the rest cannot happen.

### Orphan-branch prevention (sibling branches with zero commits)

Beyond the postmortem's checkout-stash-checkback anti-pattern, two adjacent failure modes share the same generator and ship as a single hardened pipeline:

- **Empty branches with dangling stashes.** Creating a sibling branch and parking WIP via `git stash` produces a stash labelled with that branch. Even after `git branch -d` cleans the branch, `refs/stash` is a separate ref namespace — the stash survives every consolidation and accumulates across weeks.
- **Branches that "look shipped" but aren't.** A branch whose PR was merged still accrues commits if the source branch isn't deleted; those post-merge commits are not on `origin/main` despite the branch's "merged" status.

Both modes are caught by `orphan-branch-sweep.py` with three severity tiers:

- **CRITICAL** — merged PR exists AND `commits_after_pr_merge > 0`. The branch claims "shipped" but carries unshipped work.
- **WARNING** — no PR exists AND `ahead > 0` AND (branch-name date is ≥2 days old OR `age_h > 36`). Calibrated against the parallel-machine workflow so a sibling machine's same-day daily isn't flagged.
- **OK** — everything else.

Flags: `--format json|text`, `--severity-min ok|warning|critical`, `--include-remote`, `--max-age-days N` (default 30).

The companion `sync-main.py` enforces the invariant `local main == origin/main` before any branch creation. On `main`: `git fetch origin main && git pull --ff-only`. On non-main: `git fetch origin main:main` (refspec form updates local main without checkout — this ordering is load-bearing, not incidental). `--strict` makes the >50-commits-behind warning a hard error.

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

> **Current status.** Create-time branch-shape policing **is live**, but not as a
> `coordinator/hooks/scripts/` hook — no branch-discipline hook script exists there, and none is
> registered in any `hooks/*.json`. It runs engine-side, as a registered guard inside the
> `PreToolUse(Bash|PowerShell)` dispatch multiplexer:
> `block_noncanonical_branch_creation` (`coordinator_core/bash_guards/dispatch.py:1645`,
> `ADVISORY_REWRITE` band), which calls the `is_canonical_branch` oracle over `checkout -b/-B`,
> `switch -c/-C`, and `branch <name>`. **It checks naming only** — no liveness import, so a
> canonically-named cut that moves the ref under live peers passes it. Peer-liveness is enforced
> at the decision points instead (§ Concurrent sessions share the branch, above).
> Alongside that: **`/workday-start` Step 0** (a ceremony step) and **EM self-discipline**.
> The shape oracles this page describes (`cs_is_canonical_branch`, `cs_compute_machine`) were
> **ported, not deleted** — they live in the native machine-resolver module
> (`coordinator_core/daily_branch.py`; see that module's own docstring for the old-name →
> new-name mapping). Sections below that describe a *hook* denying something describe **retired**
> plumbing unless explicitly marked current: the deny survives, the hook-script delivery
> mechanism does not. Read them for what the mechanism does, not for where it lives.

Two contact-points (see CLAUDE.md tripwire):

1. **`/workday-start` Step 0** (`workday-start-day-branch-resolve`) — the precedence switch + rename procedure that cuts/reconciles `work/{machine}/{today}`. A former SessionStart hook did this at boot; it was retired once `/workday-start` absorbed the check, and an earlier PreToolUse predecessor was retired before that. Branch-ensure is now a ceremony step, not a SessionStart hook.
2. **Doctrine** — global `CLAUDE.md` § Concurrent-EM Git Operations, first bullet. Authoritative reference for the rule.

**Where the override is actually consumed today.** No PreToolUse hook exists to bypass, so
`COORDINATOR_OVERRIDE_BRANCH`'s live consumers are all engine-resident, not skill-body. This is
illustrative, not exhaustive — do not treat it as an enumeration of every internal consumer:

- `/workday-start` Step 0 — the engine-side reconciliation op sets it on its own subprocess git
  calls during branch rename/reconcile.
- `merging-to-main` (also referenced as `/merge-to-main` elsewhere on this page) — sets it inline
  when operating against integration branches during the merge ceremony.
- `consolidate-git` — the skill body itself does not set this variable at all; the override
  moved into an engine-side branch-absorption op, which sets it on its own subprocess git calls
  when absorbing a branch.
- There is no `/workday-complete` Step 10.5 and no preemptive-branch-rename logic anywhere in this
  repo — `coordinator/commands/workday-complete.md` ends at Step 10 ("Final Summary"). Earlier
  drafts of this page documented a Step 10.5; it was either never built or removed without the
  doc following. § Span-Aware Branch Naming and § Midnight crossings below have been corrected to
  say so directly.

## Branch-set precedence rule

**The rule.** An active workstream branch with commits ahead of `main` means DO NOT cut a sibling
branch. Commit or `git stash push -u -m "<subject>"` on the current branch instead.

This is a rule about the state of the **branch set** — is there already a live workstream bus with
unshipped commits anywhere in this checkout's branches — and it is deliberately distinct from the
*shape* rule below, which is about the **name** of the branch being created. The two rules have
separate coverage and neither substitutes for the other.

**Where a narrower version is enforced today.** `/workday-start` Step 0
(`coordinator/bin/workday-start-step0.py:328-410`, Checks 1/2/3.5/4 — engine-side code) enforces
precedence against the **current branch only**, not against the branch set. Its Check 3 delegates
to `session_ensure_branch`, whose gate (`coordinator/lib/session_ensure_branch.py:100-110`) fires
only on `is_main or is_detached or is_zero_ahead_non_span` — so standing on `main` with zero
commits ahead (the ordinary post-merge / post-`/consolidate-git` position), it fresh-cuts
unconditionally, however many other live workstream branches with commits ahead exist beside it.

**Where the branch-set version is enforced.** Nowhere. Specifically not at the manual Bash seam
(`git checkout -b` / `git switch -c` typed by hand), which is where the reported sprawl was
generated.

**The ceremony is not a clean non-participant in branch sprawl, either.** The collision-suffix loop
(`session_ensure_branch.py:114-122`, and Step 0's own Check 4 collision guard at
`workday-start-step0.py:401-408`) appends `-2`, `-3`, … `-9` on a name collision, and is a
plausible producer of some of the reported `-2`/`-3` branches.

These are engine-resident files, outside this page's own change surface.

## Create-time branch-shape rule

**The rule.** `is_canonical_branch` (`coordinator_core/daily_branch.py:146`, engine-side native
module; the pre-port bash name was `cs_is_canonical_branch`) already rejects non-canonical branch
names — verified by execution, it returns False for `work/<machine>/2026-07-13-closeout`, `-2`,
`-3`, `-ci-green`, `fix/open-or-create-build-index-optout`, and `docs/scoped-to-memo-pins`, and
True only for the bare `work/<machine>/2026-07-13`.

That is six of the seven branches in the reported incident — everything except the one legitimate
cut.

**Deny-band vs advisory.** This shape check is the **deny-band half** of the enforcement ask: no
new predicate needed, highest coverage of the reported incident, and the oracle is wired at
tool-use time today via `block_noncanonical_branch_creation` (see the status block above) —
naming only, no liveness. The precedence rule above is the **advisory**
half by contrast, because its corrective action is committing or stashing someone else's
in-progress uncommitted work — a judgment call that cannot be taken on their behalf.

## Supported "park WIP" recipes

The hook does **not** ban stash. It bans creating a sibling branch first. Park WIP via:

- **Commit on the daily.** Intentionally messy commits are fine on `work/*` branches — they're quick-saves, not history.
  Use the coordinator engine's scoped-commit helper with the WIP paths/message — it selects the safe commit
  mechanism for you, so a partial-hunk stage never needs hand-classifying (→ `scoped-safety-commits.md § SC-DR-015`).
  Test-breadth posture at commit time is proportional — commit is not a test gate; run the full tier only at cadence checkpoints.
- **Stash on the daily.** Do not change branches first.
  ```
  git stash push -u -m "<subject>"
  ```

The unsupported move (and the structural reason this page exists):

```
git checkout -b feature/X && git stash push -u && git checkout -
```

This is what produces empty branches and orphan stashes by construction. The hook denies step 1.

**Stash on a shared bus is owner-ambiguous.** `refs/stash` is a single global ref per repo, NOT scoped per session — on the shared daily branch, `stash@{0}` may belong to a sibling EM. Always push WITH a message (`git stash push -u -m "<subject>"`) and NEVER `git stash pop` without `git stash list` confirming `stash@{0}` is yours (branch + subject match). A `git stash push -- <path>` that prints *"No local changes to save"* is a no-op (a sibling may have already committed your edit) — a subsequent bare `pop` then pops the sibling's stash.

## Override

**Zombie variable — has setters, has no reader, and the two forms it was documented in had
opposite fates.** `COORDINATOR_OVERRIDE_BRANCH=1` was meant to bypass a branch-discipline
PreToolUse hook, but per the status block above that hook is not installed anywhere in the fleet
today, and nothing today reads this variable as a boolean hook-bypass gate. The variable was
documented in two distinct forms, and they were not equally reachable:

- **The env-channel form** — `COORDINATOR_OVERRIDE_BRANCH` set as *subprocess env* on a setter's
  own git call — **is structurally unreachable, by construction, and always was.** A PreToolUse
  hook runs as a fresh subprocess per tool-use event; it receives the *candidate command string*
  as inert text to inspect, never shell-execs it, and never inherits the calling process's env the
  way a child-of-child subprocess would. Env set on the git subprocess you're about to run is
  invisible to the hook process that gates whether that Bash call is allowed to happen at all.
  This unreachability is pinned by a test:
  `coordinator_core/bash_guards/tests/test_override_unreachability_boundary.py`.
- **The inline-prefix form** — `COORDINATOR_OVERRIDE_BRANCH=1 git ...` typed as the literal
  leading text of the candidate command — **was NOT unreachable by construction, and it worked.**
  It was string-detected off the candidate command text and audit-logged to
  `.git/coordinator-sessions/_branch-overrides/overrides.log` (one long-lived consumer repo still
  carries 64 surviving entries tagged `OVERRIDE(inline)`) until the create-time hook's retirement. The mechanism remains observable to a guard today:
  `coordinator_core/bash_guards/_command_tokenizer.py` `resolve_command_positions` still peels
  leading env assignments. What forecloses the inline form now is **deliberate fleet policy** —
  override *keys* are human-operator and pre-launch per `docs/reference/guard-override-keys.md`
  (engine-resident) — NOT an impossibility of construction. Pre-launch is not the only
  operator channel: the engine also carries an additive fourth route — an in-session,
  one-shot, per-guard unlock sentinel created at the moment of denial, the env keys
  unchanged and still valid. Its taker is a human operator, except for one enumerated pair of
  guard names an EM may self-grant; the sentinel writes a durable record of the stated reason
  before it mints. Cite that reference for the current shape rather than asserting
  pre-launch-only or human-only. A future guard MAY be designed around
  the inline form if the engine chooses to re-open it; that is an engine-side call, not a
  doctrinal ban.

A future reinstatement of a create-time hook must not assume the env-channel form's existing
plumbing gives it a working escape hatch — it does not, by construction, and never did. The
inline-prefix form is a different question entirely: it is currently closed by policy, not by
impossibility.

**Name collision worth knowing.** `coordinator_core/consolidate_assemble/apply.py` reads the same
variable name, but as a **branch name to compare against**, not a boolean: it selects a forced
branch-delete (`git branch -D`) over the default safe delete (`git branch -d`) only when
`COORDINATOR_OVERRIDE_BRANCH` equals the branch it is about to delete. One name, two unrelated
meanings — do not assume setting it to `1` interacts with this consumer at all.

**Logging surfaces — one real, one is not.** Only the general commit-side log below is live:

- `.git/coordinator-sessions/{session_id}/branch-discipline.log` — **no writer exists anywhere in
  the fleet.** Nothing produces this file.
- `.git/coordinator-sessions/_branch-overrides/overrides.log` — written by the retired create-time
  hook; the file persists on disk in repos that used it (one such repo carries 64
  entries, `OVERRIDE(inline)` records with full command text) and is the audit trail proving the
  inline-prefix hatch was string-detected and functional. No current writer.
  <!-- Review: the Director of Engineering finding 4 — corrected from "no writer exists / nothing produces this file",
  which was false; on-disk evidence in a consumer repo refutes it. -->
- `.git/coordinator-sessions/<session_id>/overrides.log` (note: per-session, not the
  branch-scoped path above) **is real** — but it logs commit-side overrides (blanket-add,
  no-verify, safe-commit, staged-pathspec-divergence), not branch operations. No branch code
  writes to it.

Optional companion: `COORDINATOR_OVERRIDE_BRANCH_REASON="<text>"` — still set alongside the
variable by every current setter, for whatever future audit trail may exist. Not currently logged
anywhere branch-specific (see above).

Inline-only — never export. The skills/ops that currently set the variable on their own
subprocess git calls (illustrative, not exhaustive — see § Enforcement surfaces above):

- `/workday-start` Step 0 — engine-side reconciliation during branch rename/reconcile.
- `merging-to-main` — may operate against integration branches during the merge ceremony.
- `consolidate-git` — the skill body does not set it directly; an engine-side branch-absorption
  op does, when absorbing a branch.
- There is no `/workday-complete` Step 10.5 — see § Enforcement surfaces above; it does not exist
  on disk.

If you're tempted to export the variable in your shell, stop and ask: am I building a fourth
consumer that needs it? Given the variable currently has no working PreToolUse-bypass effect,
also ask whether you actually need it at all, or are cargo-culting an inline-env-prefix pattern
from a since-retired hook era.

## Never test-commit on a live auto-push branch

The post-commit auto-push hook pushes every commit on a `work/*` / `feature/*` branch to origin immediately — so a throwaway `git commit --allow-empty` made to test signing or commit mechanics is on the remote before you can drop it, and removing it then needs a force-push that is unsafe with concurrent EMs sharing the branch. **Never make a test/experimental commit on a live auto-push branch.** Test signing and commit mechanics in a throwaway temp repo (`git init` in a tmpdir), or sign without committing at all (`ssh-keygen -Y sign`). Composes with [`scoped-safety-commits.md`](./scoped-safety-commits.md) § Smoke-Testing the Commit Helper — Always Use `--dry-run` (the same "a smoke test that actually commits is a real commit" hazard, one layer up at the push surface).

## Failure modes — what currently catches them (hook retired)

Mapped to the postmortem patterns. No hook *script* catches Patterns 2 and 4; its deny survives as an engine-side guard (status block above), so both rows are covered — by name-shape only:

| Postmortem pattern | Caught by | How |
|---|---|---|
| Pattern 2 — checkout-stash-checkback anti-pattern | `block_noncanonical_branch_creation` (engine guard, advisory-rewrite band) | Step 1's `checkout -b feature/X` is a non-canonical name; the guard catches it at create time. A canonically-named cut is *not* caught — that hazard is peer-liveness, covered at the decision points |
| Pattern 3 — orphan stashes outlive deleted branches | Eliminated structurally | If non-workstream branches never exist, stashes can't reference them (structural, not hook-dependent — still holds) |
| Stale-day inheritance (yesterday's branch carried into today) | `/workday-start` auto-rename | Silently renames `work/<machine>/2026-05-06` → `work/<machine>/2026-05-06to07` and notes it in the Morning Briefing; no commit block |
| Pattern 4 — speculative `feature/<topic>-<date>` naming from planning prose | `block_noncanonical_branch_creation` (engine guard, advisory-rewrite band) | `feature/<topic>-<date>` fails `is_canonical_branch`; the guard fires at create time |

## Mixed-Case Branch Tripwire

**Problem:** a mixed-case `work/*` branch name — e.g. `git checkout -b work/<MACHINE>/2026-05-07` — leaves `.git/HEAD` storing the mixed-case form while the on-disk canonical ref convention is lowercase. Result: `git branch --show-current` returns uppercase, `git push origin <uppercase>` fails ("cannot be resolved to branch").

**How it is caught:** the `is_canonical_branch` oracle checks whether a proposed `work/*` name is already in canonical lowercase form and rejects the mixed-case creation with a remediation message naming the canonical form. The delivery mechanism changed — it was a creation-time PreToolUse hook script, it is now the engine-side `block_noncanonical_branch_creation` guard (see status block, § Enforcement surfaces above) — the check itself did not.

**What catches this today:**
1. Creation-time rejection via the `is_canonical_branch` oracle — **enforced again**, now as the engine-side `block_noncanonical_branch_creation` guard rather than the retired hook script (see status block, § Enforcement surfaces). A mixed-case `work/*` name is non-canonical, so it fires.
2. Runtime canonicalization in coordinator-auto-push (case-agnostic push) — still live; a second net at push time.
3. Migration helper: `migrate-branch-canonical-case.py` (idempotent: rename local + remote) — still available for cleanup after the fact.
4. Doctrine: global `CLAUDE.md` § Concurrent-EM Git Operations bullet 1 span-aware framing — the doctrine reference behind the guard.

**Contact points requiring sync:**
1. The native `is_canonical_branch` + `compute_machine` resolvers (the successors to an earlier shell-script implementation) — survive as unwired, importable Python; still worth keeping correct even though nothing calls them at tool-use time.
2. Global `CLAUDE.md § Concurrent-EM Git Operations` bullet 1
3. This wiki (daily-branch-discipline.md)

Note: `/workday-start` Step 0 reconciles branches it touches at that ceremony point and does not intercept an ad hoc `git checkout -b`; that interception is the engine guard's job, not the ceremony's. The two are complementary nets, not substitutes.

## Span-Aware Branch Naming

Daily branches can now carry across days as a span: `work/{machine}/{date}to{dd}` (e.g. `work/<machine>/2026-05-07to08`). This eliminates the need for a branch rename at every midnight crossing. **There is no Step 10.5 in `/workday-complete` and no preemptive-rename prompt anywhere in this repo** — `coordinator/commands/workday-complete.md` ends at Step 10 ("Final Summary"); see § Enforcement surfaces above. The rename that actually happens is `/workday-start`'s next-morning auto-rename, described in § Midnight crossings below.

**Midnight crossings:** The wiki's Midnight crossings section has been rewritten around the span-aware rename flow. No grace window required — the span form is valid for any consecutive date range.

## Midnight crossings

Sessions that span midnight are normal and expected. The hook polices branch *shape*, not branch *date* — there is no commit block after midnight, and no grace window concept.

**What happens at midnight:** nothing automatic. The session continues committing on `work/<machine>/2026-05-06` (or whatever the active branch is). The first `/workday-start` after midnight performs the rename automatically.

**Span-aware rename flow:** when `/workday-start` detects that the active branch's start-date is yesterday (or earlier) and there were commits within the last 48h, it renames silently — no prompt — and emits a one-line notice in the Morning Briefing:
> "Renamed `work/<machine>/2026-05-06` → `work/<machine>/2026-05-06to07` (crossed midnight)"

This is engineering housekeeping under the EM's remit, not a product call; the EM does not ask. PM can revert via `git branch -m` if they object. The rename is atomic (`git push --atomic origin <new>:<new> :<old>`) with local rollback on remote failure.

**Preemptive rename: does not exist.** An earlier draft of this page documented a
`/workday-complete` Step 10.5 that offered to rename forward preemptively before the session
ends. No such step, prompt, or logic exists anywhere in this repo — see § Enforcement surfaces
above. The only rename that happens is the next-morning `/workday-start` auto-rename described
just above.

**Retired hook's role (historical):** the original PreToolUse hook enforced *shape* — `work/{machine}/{anything-that-parses}` was allowed; `feature/X` or bare topic branches were denied. Its SessionStart successor briefly cut the correct branch at session open; that hook is also gone, and the same check now runs as `/workday-start` Step 0, not at session boot.

## Edge cases — historical hook coverage map

**Read as a specification, not a live coverage map.** This section describes the retired create-time
PreToolUse hook's coverage boundaries. The successor engine guard
(`block_noncanonical_branch_creation`, § Enforcement surfaces) re-implements the name-shape deny
over `checkout -b/-B`, `switch -c/-C`, `branch <name>` — so the core denies fire again — but the
edge-form coverage below (`--orphan`, `-C <path>`, `cd … && git …`, compound commands) was the *old*
hook's parser behaviour and has NOT been verified against the successor. Treat each form here as
unconfirmed until read in `coordinator_core/bash_guards/`.

- **`git checkout <sha>` / `git checkout <tag>`** — detached HEAD. Allowed (not a branch op). Commit-time check catches any subsequent commit, since the resulting `HEAD` is not a branch ref.
- **`git checkout -- <path>`** — file restore. Allowed (no branch involved).
- **`git checkout origin/<remote>`** — produces detached HEAD. Allowed; same commit-time fallback.
- **`git checkout --orphan <name>`** — the hook checked the orphan name and denied if it was not an allowed workstream branch or main. `--orphan` onto an allowed name was permitted.
- **Linked worktrees (already created)** — the hook exited silently when run inside a `worktrees/` git-dir. Doctrine bans worktree creation; the audit catches existing ones separately. The worktree-creation deny is a **separate, live** guard at the tool seam, not part of this retired hook — see global doctrine § No git worktrees.
- **Compound commands beyond the first git op** — the hook inspected only the first `git <branch-op>` it found. Subsequent ops in `git checkout -b foo && git checkout -b bar` were never separately validated; coverage relied on step 1 denying so step 2 never ran. **Any reinstatement must not inherit this** — a precedence-based check that denies step 1 but leaves step 2 unvalidated is trivially bypassed by reordering.
- **`git -C <path>` / `git --git-dir=<path>/.git`** — cross-repo forms were policed by the same shape rules (allowed if the target branch name was canonical `work/{machine}/{date-or-span}` or `main`; denied otherwise). No override was needed for shape-canonical names. The parser captured the `-C <path>` value to validate `is_local_branch` and `@{-1}` resolution against the sibling repo's refs, not `$GIT_ROOT`.
- **`cd <path> && git ...`** — historical: when the hook was live, cross-repo via `cd` was denied outright when a branch-mutating subcommand followed, because the hook subprocess couldn't resolve the post-`cd` cwd (`$GIT_ROOT` was captured at entry, before the `cd`), and `COORDINATOR_OVERRIDE_BRANCH=1` was the sanctioned bypass for legitimate cd-then-git cross-repo work. With no hook installed today (see status block, § Enforcement surfaces), this form is not denied at all — nothing currently blocks it.

**`session-init.sh` committing to `main` during orphan-handoff sweep (fixed)**

`session-init.sh` ran an orphan-handoff sweep that called `git mv` + `git commit` on whatever branch was currently checked out. Post-`/merge-to-main`, the active branch was often `main` — violating read-only-main doctrine and causing `sync-main.py` to abort on the next workday-start (`local main != origin/main`).

Fix: a branch guard was added at the top of the sweep block. If the current branch is `main`, orphan handoffs are noted but not committed — they are picked up by the next session that boots on a live work branch.

This failure mode is not hookable at the PreToolUse layer (the script runs at SessionStart, not from a Bash tool call). The guard lives in the script itself.

## "Shipped" definition — branch tip ≠ origin/main

`check-shipped-on-main.py <commit>` is the authoritative gate. Branch-tip is not shipping. PR-merged-from-this-branch is shipping IFF no further commits landed on the source branch after the merge. Run it before any handoff/doc/lessons/memory update asserts shipping. CLAUDE.md § Verification Before Done is the doctrine surface; this script is the enforcement.

## Align on branch; never wait on merge-to-main

The shared pushed branch is the alignment/coordination surface for all in-flight work — it is already the review buffer (global `CLAUDE.md` § Concurrent-EM Git Operations), and it is equally the *dependency* buffer. Dependent work, downstream legs, cross-repo memos, and sibling coordination proceed off branch-pushed commits. **They do NOT wait for `/merge-to-main`.**

Two gates, two owners, deliberately decoupled:

- **Branch-landing = the work-gate (EM, do-now).** Aligning is pushing to the shared branch. Once your work is committed and pushed, dependents can build on it, memos can cite it, and coupled legs can proceed — cite branch + SHA.
- **Merge-to-main = the ship/sync-gate (PM-owned).** Carrying the branch to `origin/main` and synchronizing coupled go-lives is PM-owned, held deliberately apart from work progress. An EM never defers, sequences, or holds back work behind "once this is on main" — that re-implements a gate the PM already owns.

**This does not weaken the "'Shipped' means on `origin/main`" definition above.** That rule governs the honesty of a *shipped claim* — don't assert shipped-to-main until `check-shipped-on-main.py` passes. It does not gate *work*: do the dependent work now off the branch and describe its state accurately ("landed on branch `<name>` at `<SHA>`, pending PM merge to main"). Claim-honesty and work-gating are different axes — only the *claim* waits for main.

**Anti-pattern tell** (the attitude this section exists to kill): "after this merges," "once it's on main, then we'll…," "waiting on main before X," or queuing a memo / downstream leg / dependent task "for after merge." Any of these is the deferral reflex — push, align on the branch, proceed; the PM carries it to main on their cadence.

## R-3 Sonnet-dispatch prohibition (verbatim)

Inlined in every Sonnet-dispatching autonomous skill (`/update-docs`, `/distill`, `/architecture-survey`, `/mise-en-place`, `/workday-complete`, `/workweek-complete`):

> DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly.

Tripwire entry in CLAUDE.md § "Adding a Convention to the Coordinator System" enumerates these skills. New write-capable autonomous skills must be added there.

## Verifying handoff premises (shared-bus reconciliation)

The active workstream branch is a shared bus across concurrent sessions, so handoffs authored against it can be stale by the time a successor reads them. Two reconciliation tripwires before treating a handoff as ground truth:

- **Handoff red-counts are hypothesis, not baseline.** Handoff-cited failure counts (red tests, broken paths) are hypothesis, not baseline. Before treating the count as actionable, `git stash push -u` your local changes, check out the handoff's claimed HEAD, and re-run — the count may already be stale from concurrent commits or local dirty state.
- **Same-session staleness — pre-write the diff.** Before writing a handoff, grep the workstream's commits since session start (`git log --since='session-start' --oneline`) to distinguish in-session fixes (already shipped to branch) from refactor-deferred work. Authors conflate these into a single "pending" bullet, stranding successors.

## `git log origin/HEAD..HEAD` misleads on feature branches

`git log origin/HEAD..HEAD` is a common shape for "what hasn't been pushed yet?" — but `origin/HEAD` is the *remote's default branch* (almost always `origin/main`), not the upstream of the current branch. On any feature/work branch, this query returns "every commit since main diverged," which on a span branch is days of work, not the unpushed delta.

**Rule:** for "what's unpushed on this branch?" use `git log origin/$(git branch --show-current)..HEAD`. The right comparand is the current branch's own upstream, not the remote default. The cs_compute_machine / cs_is_canonical_branch path correctly resolves the canonical lowercase form; downstream `git log` callers must use that form, not `origin/HEAD`.

This bites worst on script wrappers and skill-body procedures that paste `origin/HEAD..HEAD` from a how-to that was written against `main`-only workflows.

## Rewording a buried commit on a shared dirty-tree branch — plumbing only

To reword a commit that concurrent sessions have buried under later commits (and left uncommitted WIP in the tree), `git rebase` aborts on the dirty tree and `git checkout --detach` reverts tracked files — both risk the sibling's work. **Use pure plumbing, never `rebase`/`checkout`:** plumbing rebuilds the commit chain as objects and swings the branch ref atomically, never touching the working tree or index.

1. Rebuild the target: `git commit-tree <tree> -p <parent> -F msg` — reuse each child's exact `^{tree}` with rewritten parents, preserving author/committer ident+date.
2. Replay each child reusing its tree.
3. **GATE on `final^{tree} == old_tip^{tree}`** before moving the ref — proves the rewrite is content-identical.
4. `git push --force-with-lease=<branch>:<old-origin-sha>` so a racing sibling push aborts safely.
5. Abort if any commit in range is a merge — single-parent reuse is unsafe.

Default discipline remains: prefer new commits over `--amend` on a shared bus; only reach for plumbing when a subject genuinely must be corrected.

## Peer-session detection on the shared bus

The bus is shared, so a sibling EM may be co-driving — detection is read-side and explicit:

- **Peers are visible via remotes, not `--branches`.** `git branch --branches` is structurally wrong for concurrent-EM detection; enumerate peer machines' active work via `git for-each-ref refs/remotes/origin/work/` (or `git log origin/work/{peer}/*`).
- **Before authoring an overlapping code fix**, run a `git log --oneline -- <target-paths>` peer check — a sibling may have already landed it; grep sibling plans before reverting apparent "out-of-scope drift" as contamination.
- Pickup- and plan-time concurrent-work surfacing follows the same discipline: check for peer activity before assuming a clean slate.

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

**Failure 1 (stale inherited label).** A branch was authored on the wrong machine's token — e.g. `work/machine-a/<date>` cut on a laptop that was actually registered as `machine-b` — because the authoring session inherited the wrong machine token from yesterday's substrate. The orientation_cache pinboard, handoff body, and branch name all propagated the wrong name — no internal contradiction to surface the error. This incident produced the original rule: *"derive the machine token from `hostname` … or from `machine-local get machine-name` (registry helper), not from copying the previous day's branch token."*

**Failure 2 (stale per-process hostname).** A session launched before a machine-rename propagated to its process environment kept recomputing a stale slug from `hostname` on every call. The branch forked silently into a second slug (e.g. `work/newname/*` alongside `work/oldname/*`). Same class: a value gone stale relative to true machine identity.

**Synthesis.** Both incidents are the same failure class — any value that re-derives machine identity from a potentially-stale source silently forks branch lineage. The fix is **one deliberately-seeded canonical value** that is written once at a known-good moment and detected-then-fail-loud on drift, rather than silently trusted.

### Layered precedence — `cs_compute_machine`

The resolver (`cs_compute_machine`, natively a machine-resolver module — the successor to an earlier shell-script implementation) applies this precedence:

```
$COORDINATOR_MACHINE           → highest-precedence explicit override, unchanged
machine-local get coordinator.machine_slug  → registry-pinned canonical (primary, when present)
live hostname (cs_compute_machine_live)     → graceful fallback on fresh / pre-seed installs
"unknown"                                   → last resort
```

The resolver is **pure read** — it never writes. This kept the function safe to call from a PreToolUse hook context when one existed, and remains true today even though no such hook currently calls it (see status block, § Enforcement surfaces). Write authority is confined to `coordinator:install` (eager seed) and `/workday-start` Step 0 (lazy self-heal) — the reader is read-only, and write authority belongs to the operator, always.

The `machine-local get coordinator.machine_slug` step degrades gracefully: a 127 (CLI absent, e.g. broken install) or 1 (key absent, e.g. pre-seed) never aborts the resolver — the call is wrapped with `|| true` or a `command -v machine-local` pre-check.

A sibling pure-hostname helper **`cs_compute_machine_live`** (`$COORDINATOR_MACHINE` → `hostname` → "unknown", NO registry read) exists as the seed source and drift-detection comparator. Using it for seeding avoids circularity (seeding from the registry-preferring resolver) and avoids persisting a transient `COORDINATOR_MACHINE` override into the registry.

### The lineage anchor

The original rule already named `machine-local get machine-name` (registry helper) as an acceptable source alongside `hostname`. A later revision elevates that registry read to primary and pins the key name as `coordinator.machine_slug`. The elevation is consistent with, not contrary to, the standing rule.

### Anti-pattern: inheriting a branch token is prohibited

Deriving the machine token by copying yesterday's branch name, reading it from an existing substrate label (orientation_cache, handoff body, branch listing), or from any other eventually-consistent source is **prohibited**. `coordinator.machine_slug` is not a substrate to be inherited — it is an explicitly-seeded canonical value with operator authority over mutation.

### Drift detection at `/workday-start`

When `coordinator.machine_slug` is already set, `/workday-start` Step 0 compares the persisted slug against `cs_compute_machine_live`. On mismatch, it surfaces the drift to the operator with both remediations as equal branches — it does **not** silently overwrite:

> `Machine-slug drift: persisted='oldname', this session's hostname yields 'newname'.`
> `  Option 1 — stale session: this process has a stale hostname. Keeping persisted value is correct; no action needed.`
> `  Option 2 — machine renamed: run 'machine-local set coordinator.machine_slug <correct-slug>' to update the registry.`

This is the correct adjudicator (interactive context; operator can immediately correct) and honours the global "detect-then-silently-pick is a footgun" principle.

### Snippet-sync verifier

The `cs_compute_machine` function body now lives natively in the machine-resolver module (`coordinator_core/daily_branch.py`), replacing an earlier shell-script implementation. The former inline mirror and its companion byte-equality sync verifier were both deleted when the old hook was retired. No `session-ensure-branch.sh` file exists on disk anywhere in the fleet — that hook was never carried forward, not merely rewired to import the native module. The native module itself is real and importable; it simply has no hook calling it today (see status block, § Enforcement surfaces).

## See also

- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — sibling enforcement on commit *content* (which files); this page enforces commit *location* (which branch). This page's create-time hook is retired and unwired (see status block, § Enforcement surfaces), so the two pages do not share a PreToolUse Bash matcher on this page's side; `scoped-safety-commits.md`'s own hook may or may not still be live (check that page directly rather than trusting this cross-reference for its status).
