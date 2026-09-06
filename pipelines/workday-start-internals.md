# Workday-Start — Internals Reference

Detail companion to `commands/workday-start.md`. Step numbers refer to that command.

## Step -0.45 — Git-Hook Freshness Self-Heal (why)

On 2026-07-19, commit `af2133e4` ported the script invoked by the deployed
`.git/hooks/prepare-commit-msg` hook from bash to Python. The installer that generates that hook
body (claude-klabauter `coordinator/bin/lib/git_hook_install.py`) was already correct — it rewrites a stale hook on
mismatch when run — but nothing re-ran it after the port. The hook only fires at one-time
`repo-setup`, and the 2026-07-15 full-kill-keep-fast-orientation directive removed the SessionStart
boot hooks that might otherwise have self-healed it. Net effect: every commit in this repo was
silently blocked by a stale hook body until the gap was noticed and manually repaired.

The fix invokes the idempotent fleet installer (`coordinator-ensure-hooks-fleet`) once per
`/workday-start` — a per-day PM-invoked ceremony, not a per-spawn boot hook — so a stale or absent
hook self-heals within a day without reintroducing the per-session boot cost the 2026-07-15
directive deliberately killed.

**Fleet-wide, not cwd-only.** The per-repo entrypoint (`coordinator-ensure-prepare-commit-msg-hook`)
heals whichever single repo the ceremony runs in; every other
registered repo then drifts indefinitely, and the drift is silent in both directions — commits stop
being pushed AND stop carrying the `Session-Id` trailer `workstream-complete`'s review-trail
foreign-session guard keys on, so a session's own commits look foreign to its own close. Measured
2026-08-14: 12 of 14 working trees carried a pre-generation `post-commit`, and the
`prepare-commit-msg` leg was stale in every repo including this one. `coordinator-ensure-hooks-fleet`
walks the machine-local registry and heals both hook families in every registered EM tree
(publish mirrors excluded by `_classify_target`).

### The meta-repo `pre-commit` leg (added 2026-08-11)

Same failure class, one hook family later, and worse in its consequences. `~/.claude` was found
carrying a `.git/hooks/pre-commit` whose two gates were guarded `if [ -x "$_helper" ]` against
`plugins/coordinator/bin/` paths that stopped existing when the engine moved to
the klabauter mirror. A missing helper under that guard is not an error — it is a skip, so the hook
was present, looked installed, and enforced nothing.

Under it, four unscoped `safety-commit` sweeps landed 12 machine-local files in a meta-repo shared
between a Windows box and a Mac. Two were full `settings.json` snapshots carrying a hook chain of
machine-absolute paths — the payload that repoints the other machine's Bash/Edit/Write at a drive it
does not have, i.e. removes the tools needed to repair it. `project-rag/install-profile.json` proved
the collision was already live: one tracked copy held a Windows venv interpreter *and* a
`/Users/...` binding target simultaneously.

`install_meta_repo_precommit_hook` was already correct — it emits a `# gate-version: N` marker per
gate and rewrites on its absence, and a single re-run healed the stale hook. Its only callers were
`/coordinator:install` and `/coordinator:repo-setup`, both one-shot human ceremonies, so on any
machine set up before an engine move the hook stays dead indefinitely and silently. Step -0.45 is
now that scheduled caller, passing `$HOME/.claude` explicitly so the leg is cwd-independent.

Note the generated gates block on a missing script rather than skipping, which is the property the
two hand-written stanzas lacked; those were removed rather than repointed. A gate whose failure mode
is a silent skip is worse than no gate, because it also suppresses the question.

### Why a named entrypoint, not a `--fleet` flag

`coordinator-ensure-hooks-fleet` is a separate entrypoint rather than a flag on the two per-repo
ones deliberately: their `main()` reads no argv, so `--fleet` would be accepted and silently
ignored — doctrine reading as fixed while still healing one repo of fifteen. Scope belongs in the
name. The `pre-commit` leg is unaffected either way: it names one repo by construction, never cwd.

## Step 0 — Branch Setup (full procedure)

The goal is to ensure the active workstream branch reconciles with `origin/main` daily — not to create a new branch every day. The active workstream may be either:

- **Canonical** — `work/{machine}/{date-or-span}` (e.g. `work/machine-a/2026-05-06to07`). Span form is the normal shape when work runs across midnight.
- **Named long-lived workstream** — `migration/...`, `release/...`, `feature/...`, etc., authorized at create-time via the inline `COORDINATOR_OVERRIDE_BRANCH=1`. Once it exists with commits ahead of main, workday-start treats it as a legitimate workstream bus.

The hook polices branch *shape* at create-time, not branch *date* at workday-start. Daily ritual is **reconcile with origin/main**, applicable to both branch types. One active workstream branch per machine, kept current with main, until it's ready to merge.

**Implementation note:** the procedure below is the conceptual model; the live entrypoint is
Claude-klabauter `coordinator/bin/workday-start-step0.py`, which imports `cs_compute_machine`/`cs_parse_branch_span`/etc.
natively from `coordinator_core.machine_resolver` / `coordinator_core.daily_branch`
(de-bash campaign, unit "daily-branch" — `coordinator-daily-branch.sh` is retired).

### Step 0.1 — Sync main

Run `sync-main.py` first; abort if it exits non-zero. Never create or rename branches from stale main.

### Step 0.2 — Determine machine and today's date

```text
MACHINE=$(python3 -c 'from coordinator_core.machine_resolver import compute_machine; print(compute_machine())')   # always lowercase (the Staff Engineer F11; lib Phase 1)
TODAY=$(date +%Y-%m-%d)
CURRENT=$(git branch --show-current)
```

`MACHINE` is used in every branch name constructed below. Because `cs_compute_machine` lowercases its output unconditionally, new branches are always `work/<machine>/...` regardless of `$COMPUTERNAME` case.

### Step 0.3 — Precedence switch (evaluate in order; stop at first match)

**Check 1 — Stale-commit guard (runs first):**
```text
LAST_EPOCH=$(git log -1 --format="%ct" 2>/dev/null || echo 0)
NOW_EPOCH=$(date +%s)
AGE_DAYS=$(( (NOW_EPOCH - LAST_EPOCH) / 86400 ))
```
If `$AGE_DAYS > 2` AND `$CURRENT` matches `work/*/...` → jump to **Step 0.5 (consolidation)** using `$CURRENT` as the base. Do NOT rename; surface to PM via the A/B/C Branch Reconciliation Decision (see `commands/workday-start.md` § Step 0 conflict handling). Rationale: a stale span branch whose end-suffix happens to equal today is still dead work warranting triage, not a silent continue.

**Check 2 — Already-in-span (runs second):**
```text
LAST_EPOCH=$(git log -1 --format="%ct" 2>/dev/null || echo 0)
cs_should_prompt_rename "$CURRENT" "$TODAY" "$LAST_EPOCH"
SHOULD_PROMPT=$?
```
If `$SHOULD_PROMPT` is **1** and the branch is a valid `work/{machine}/...` form → exit Step 0 silently. Today is already within the branch's span. Proceed to Step 1.

**Check 3 — On main / detached / empty branch (runs third):**
If `$CURRENT == "main"` OR HEAD is detached OR `$CURRENT` is non-main with zero commits ahead of `origin/main` → create a fresh canonical workstream branch: check it out as `work/${MACHINE}/${TODAY}` under the inline `COORDINATOR_OVERRIDE_BRANCH=1` override (see Step 0.4's Override rationale for why the override is needed), then push it upstream with `git push -u origin`. Name collision with an already-merged branch: append `-2`. Then proceed to **Step 0.4.5 (reconcile)** and **Step 0.5 (consolidation)**.

This ceremony path passes `caller="ceremony"` and keeps the wider admission set above (main / detached / zero-ahead-non-span), the `-N` collision suffix loop, and the synchronous `push -u` — an EM is present and there is no shared boot budget to protect.

**The cut is serialized and is no longer this step's exclusive property.** `session_ensure_branch` consults the engine's liveness oracle with an explicit operation kind: a content-neutral fresh cut at HEAD **while on `main`** is permitted under live peers; checkout of a different commit and rename-with-remote-delete still refuse, and an `unknown` verdict still refuses. Exactly one session performs the cut — it is held under a tree-keyed lock — and concurrent sessions **inherit** the winner's branch rather than cutting their own. Four outcomes reach callers and each needs its own arm: `FRESH-CUT`, `ADOPTED-EXISTING` (today's branch already existed and HEAD was already at its tip), `INHERITED` (another session won the lock; the invariant holds), and `REFUSED-LIVE-PEERS`.

**A session that never runs this ceremony still gets the branch.** The same invariant is asserted at session boot by `day-branch-assert.py` (`startup` only), covering `/pickup`, `/clear` and a bare boot — none of which run Step 0 at all. That boot path is narrower than this one: `main` only, no `-N` suffix loop (it adopts today's existing branch instead), and no synchronous network push. The boot assert, not this ceremony, is therefore the owner of the invariant — it is the only surface that fires on every entry path. A machine on which no session boots at all cuts nothing, which is acceptable: a machine with no sessions produces no commits to protect.

**Why "empty branch" qualifies for fresh-cut:** a non-main branch with zero commits ahead is structurally indistinguishable from `main` for workstream purposes — it's an empty container, not work-in-progress. Cutting fresh from main is fine; nothing is being abandoned.

**Check 3.5 — Named long-lived workstream (runs between 3 and 4):**
If `$CURRENT` is non-main, `cs_parse_branch_span "$CURRENT"` returns non-zero (not `work/{machine}/...`), AND `git rev-list --count origin/main..HEAD` > 0 → this is an active named workstream bus (e.g. `migration/from-example-game-repo-...`, `release/v2.0`). Skip the rename procedure (which is `work/{machine}/...`-specific). Proceed directly to **Step 0.4.5 (reconcile)**, then **Step 0.5 (consolidation)** with this branch as base.

**Why not force a fresh daily here:** creating `work/{machine}/{today}` off main and abandoning the named workstream branch would strand potentially weeks of work on an inactive ref. The PM authorized this branch at create-time via the inline override; daily reconciliation keeps it current with main without forking.

**Consolidation scope for named workstreams:** Step 0.5 (merge open `work/{machine}/...` siblings into the active branch) is **skipped** when the active branch is a named long-lived workstream. The named bus is deliberately scoped (e.g. a migration, a release); folding generic daily work into it cross-pollutes the workstream history. Sibling `work/{machine}/...` branches stay where they are until their own session consolidates them, or until they're explicitly merged via `/consolidate-git`.

**Check 4 — Midnight-rename (runs last):**
Condition: `cs_should_prompt_rename "$CURRENT" "$TODAY" "$LAST_EPOCH"` returns 0. This means the current branch is a valid `work/{machine}/...` branch with recent commits that does not yet cover today.

**Rename target depends on `COMMITS_AHEAD` (origin/main..HEAD):**
- **`COMMITS_AHEAD > 0`** — genuine unmerged work crossing the day boundary → span suffix `work/{machine}/{start}to{today-DD}` (e.g. `work/machine-a/2026-06-01to02`). The span is honest: it advertises real multi-day WIP.
- **`COMMITS_AHEAD == 0`** — the branch's historical work has all merged to origin/main (or main has moved ahead and we are strictly behind). A span name here would be **misleading**: it claims multi-day WIP that no longer exists. Rename to **today-only** `work/{machine}/{today}` instead; the reconcile leg (Step 0.4.5) then fast-forwards onto origin/main. Doctrine 2026-06-02 — this is *reconciliation with an honest name*, not rotation: 0-ahead means there is no ongoing work to abandon, so "reconcile not rotate" is satisfied, not violated.

Run the rename procedure below silently (no prompt — engineering housekeeping, not a product call). Emit a one-line notice in the Morning Briefing:
```
Renamed $OLD → $NEW (crossed midnight)
```
PM can revert via `git branch -m` if they object.

### Step 0.4 — Rename procedure (the Staff Engineer F5 — atomic, reversible)

`START_DATE` comes from `cs_parse_branch_span` on the old branch name. `NEW` is computed by the same 0-ahead vs >0-ahead rule as Check 4 above: 0-ahead names today-only (`work/${MACHINE}/${TODAY}`); >0-ahead names the span suffix via `cs_format_span_suffix` on `START_DATE`/`TODAY`.

**Concurrent-rename race guard (plan Risk #3):** another session on this machine may have already renamed while this one prompted. Re-read the current branch name first; if it already ends in today's day-of-month suffix, another session won the race — report "Branch already renamed by another session — nothing to do," keep that branch as the active one, and skip straight to Step 0.5.

Otherwise the rename runs in two steps, both under the inline `COORDINATOR_OVERRIDE_BRANCH=1` override (see Override rationale below): first a cheap, reversible local rename (`git branch -m`), then an atomic remote rename via `git push --atomic`, which sends the new-ref-create and old-ref-delete refspecs in one transport round-trip so both succeed or both fail (requires git ≥2.4, GA since 2015). If the atomic push is rejected, roll back the local rename so local and remote stay consistent, then surface a clear error ("remote rename rejected; local rolled back … check remote ref-update hooks or push permissions") rather than leaving the two out of sync. On success, set the new branch's upstream tracking to `origin/${NEW}`; a failure here is surfaced as a visible warning, never silently swallowed, since the atomic push already published the ref and an unexpected `--set-upstream-to` failure is worth a human's attention.

**Override rationale:** `git branch -m` and `git push --atomic` are both hook-blocked ops when the target name is being mutated. The inline `COORDINATOR_OVERRIDE_BRANCH=1` is required on each of the three git commands (rename, push, rollback). Never export this variable — set it inline per command.

### Step 0.4.5 — Reconcile with origin/main (daily ritual)

Applies to any non-main active branch — canonical `work/{machine}/...` or named long-lived workstream. Runs after the precedence switch resolves and after any rename, before consolidation.

Fetch `origin/main` first. If the active branch already has `origin/main` as an ancestor, there is nothing to do. Otherwise attempt a fast-forward merge (`git merge --ff-only origin/main`, under the inline `COORDINATOR_OVERRIDE_BRANCH=1` override — see Override rationale below) and report the fast-forward. If the fast-forward isn't possible, fall back to an explicit `git merge --no-ff origin/main` (same override, with a `reconcile origin/main into <branch> (workday-start)` commit message) and report the merge. If that merge also fails, abort it (`git merge --abort`), report the conflict for the A/B/C Branch Reconciliation Decision, and stop — do not proceed to Step 0.5 until the PM resolves it.

**Why this replaces "cut a fresh daily off main":** other contributors push to `origin/main` independently. The active workstream branch needs that work folded in daily to stay mergeable — abandoning the branch and cutting a fresh one off main would lose the in-progress workstream. Conflicts on reconcile use the same A/B/C decision flow as consolidation conflicts (`commands/workday-start.md` § Step 0 conflict handling).

**Override rationale:** `git merge origin/main` does not mutate a branch ref, but the hook surface includes `git merge` in some shells (compound parsing). Inline override is cheap insurance; remove if hook coverage analysis confirms it's not needed.

### Step 0.5 — Consolidate open branches

**Superseded — conceptual model of retired auto-consolidation, not a live step.** This is the
pre-2026 auto-merge-siblings design the "conceptual model" note above describes; it was never
ported to `workday-start-step0.py`. Today's `/workday-start` does NOT auto-merge sibling
`work/{machine}/...` branches inline — consolidation is PM-invoked via `/consolidate-git` (see
`commands/workday-start.md` § Step 0 conflict handling, option A), and passive orphan detection
runs via `commands/workday-start.md` § Step 0.5 (Orphan Branch Sweep, a different mechanism: a
read-only `orphan-branch-sweep` scan, not a merge). The blocks below document the retired design
for historical rationale only — do not execute them.

Find open (unmerged) work branches for this machine by listing `work/*` branches not merged to main and filtering to this machine's prefix, case-folded (the legacy uppercase transition period is over but mixed-case strays still appear from manual branch creates).

Exclude the current active branch from the result list. For each remaining branch:
```text
COORDINATOR_OVERRIDE_BRANCH=1 \
COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 consolidate {branch-name}" \
git merge {branch-name} --no-ff -m "consolidate {branch-name} into active workstream branch"
```

- **Clean merge:** continue to next branch.
- **Conflict:** `git merge --abort` immediately. Report: _"Merge conflict consolidating {branch-name} — manual resolution required."_ Do not attempt automatic resolution. Surface to PM via the A/B/C Branch Reconciliation Decision.
- After all merges: old branches remain as refs (do not delete — PM may want to inspect).

### Step 0.6 — Push and report

**Superseded — conceptual model of a retired explicit push step, not a live step.** Like Step 0.5
above, this predates the per-commit auto-push hook (`coordinator-auto-push`, → global
`~/.claude/CLAUDE.md` § Git extras) that now covers `work/*`/`feature/*` crash-insurance pushing
on every commit; the current `commands/workday-start.md` numbering repurposes "Step 0.6" for the
unrelated Agent Worktree Sweep. Documented here for historical rationale only — do not execute.

The retired step resolved claude-klabauter's root (checking `REPO_CLAUDE_KLABAUTER`, then `CLAUDE_KLABAUTER_ROOT`, then falling back to the settings-home registry/pointer helper `_engine_root.py`), failing loud with remediation guidance if none resolved, and pushed the active branch computed via that root's `coordinator-current-branch.py`.

Report:
- _"On branch {active-branch}. Consolidated N open branches: {list}."_
- _"On branch {active-branch}. No open work branches to consolidate."_
- _"Renamed {old} → {new} to reflect midnight span."_ (if rename occurred)
- Conflicts blocked consolidation: flag clearly.

**Why this matters:** without consolidation, sessions pile up unmerged work branches indefinitely. The span-aware rename keeps the active branch name accurate without splitting the workstream history across a date boundary.

## Step 1 — Handoff reconciliation (rationale + procedure)

**Why filter to `ready_to_fire` for the primary actionable list, with `awaiting_gate` always surfaced as its own subsection:** the prior "surface everything" policy presumed the EM grep-walks every handoff to assess readiness — exactly the agentic-grep `deployment_state` is designed to obviate. Sub-second queryability for the actionable list requires a clear filter. The original 2026-05-08 revision hid `awaiting_gate` behind a 14-day staleness gate; empirical use (2026-05-15) showed this buried gated work the PM needed for cross-workstream planning — clear-gate, retarget, or pick-up-early decisions never reached the briefing. Revised behavior: `awaiting_gate` items always surface as a "Gated handoffs" subsection (count + list when present), with a >6-day flag for items where the gate may be stuck. Six days ≈ one working week — long enough to filter normal in-flight gates, short enough to catch ossification. **Archive policy unchanged:** handoffs are archived only via `/pickup` (the atomic archival event), supersession (chain-aware pass), or PM direction — never automatically based on age.

**Why cross-reference completed archive:** handoffs describe *intended* next steps. The completed archive records *outcomes*. A handoff can remain active even after the work it describes has shipped — especially when a different session completed the work without consuming the handoff. The cross-reference catches this, but the PM confirms before archival.

**Why git-reconcile pending items:** the completed archive records sessions that ran `/workday-complete` or `/update-docs` — it is not exhaustive. Executor sessions that commit and exit without ceremony never land in the archive. The git log is authoritative; the archive is a secondary cross-check. Both checks together cover failure modes the other misses.

### Reconciliation procedure (per handoff, before reporting items as actionable)

a. **Git log check:** extract handoff date from filename/header. Run:
   ```bash
   git log --oneline --since="<handoff-date>" --all
   ```
   Scan commit subjects for key nouns from each pending item. A subject clearly matching an item is strong evidence it shipped.

b. **Plan/stub closure check:** for any pending item that references a plan/stub file (`docs/plans/*.md`, `tasks/*/stub.md`, `tasks/*/todo.md`), determine closure via the following sources in priority order:

   1. **Git commit log by chunk-id prefix (preferred, canonical closure signal):** Run:
      ```bash
      git log --oneline -- <plan-path>
      ```
      A subject beginning `<chunk-id>:` (e.g., `C4b-workday-start: ...`) means that chunk shipped. If every chunk named in the plan's `## Tasks` spine has a matching `<chunk-id>:` commit, the plan itself is closed. The plan-body `## Dispatch Ledger` table is retired as a closure-signal source — executors no longer stamp per-chunk completion into plan bodies, so a plan-body `**Status:** Execution complete — pending verification` signal no longer appears here either.

   2. **Git commit log (fallback, broader search window):** Run:
      ```bash
      git log --oneline --since="<handoff-date>" --all
      ```
      A commit whose subject begins with `<chunk-id>:` (e.g., `C4b-workday-start: ...`) indicates that chunk shipped. A commit whose subject references a plan slug or feature name with "complete" / "done" semantics is strong evidence the plan closed.

   3. **Plan-header `Status:` field (EM-authored phase transitions):** The plan's top-level `**Status:**` or frontmatter `status:` field is still valid for phase-level closure (`status: shipped`, `status: complete`, `Status: Shipped`). This field is EM-authored and reflects review / enrichment / execution phase transitions — NOT per-chunk executor stamps. Read it only when the wave-map is absent or the plan has no chunks.

   4. **Stub-file `**Status:**` reads (enricher surface, still valid):** A `tasks/*/stub.md` or `tasks/*/todo.md` whose own `**Status:**` reads `Shipped`, `Completed`, or `Execution complete` is closed — these are enricher-authored stubs whose completion state the enricher writes, not executor-stamped plan bodies.

   > **Why the per-chunk executor stamp is gone:** the prior pattern had executors stamp `**Status:** Execution complete — pending verification` into their own chunk section of the plan body. This pattern was removed as part of the executor-sidecar-flight-recorder migration. Executors no longer stamp plan bodies; that signal is absent from `docs/plans/*.md`.

c. **Drop confirmed-closed items.** Verified-closed items do NOT surface as today's work. Note in the report as _"verified-closed since handoff"_ so the PM sees the reconciliation was done.

**Empirical baseline:** expect 30–60% of inherited items to be already closed. Skipping means the Morning Briefing recommends ghost work.

**Partial-completion claims:** before surfacing handoff items described as "stalled", "unfinished", or "partial", verify against `git log --oneline --all -- <relevant paths>`, the `archive/completed/` log, and live artifact state. The handoff's status is a hypothesis, not ground truth.

**Query the substrate directly.** There is no pre-rendered tracker artifact — the Step 1 queries above are the source of truth for current queue state, run live against git and the handoff/query-record substrate. A rendered snapshot goes stale the moment something ships after it was written; querying live avoids that drift.

## Step 5.5 — Orientation Cache Content Derivation

Generate `state/orientation_cache.md` — a compact, schema-conformant summary the SessionStart hook injects at every boot. **This step does not author the cache directly.** It invokes the shared regeneration routine, resolved via the settings-home forwarder (`snippets/resolve-coordinator-bin.md` Shape A — never a hand-derived `_cc_claude_klabauter` ladder):

```bash
"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/regenerate-orientation-cache" --invoker workday-start
```

The routine is the single source-of-truth derivation. This section documents the **canonical schema** that the routine produces and the verifier (claude-klabauter `coordinator/bin/verify-orientation-cache-sync.py`) enforces. Drift from this schema is a verifier failure at `/update-docs` Phase 11b.

**Why a schema, not prose:** four writers (`/workday-start`, `/update-docs`, `/workstream-complete`, `/handoff`) historically patched the cache with free-form sections, and there was no owner for subtraction. The cache accreted prior-session narrative ("publish-repo-topology-sync just shipped...", "the Staff Engineer R1 (9 findings folded)...", "AC7 dogfood waived by PM") that poisoned every subsequent boot. The schema below is the structural fix: every section is either (a) static template, (b) sentinel-regenerated from disk, or (c) absent. No free-form prose anywhere.

### Canonical schema

| Section | Shape | Source-of-truth | Tier |
|---|---|---|---|
| Frontmatter | `generated_by: <slug>` (single word — no parentheticals, no "patched by"), `generated_at: <ISO-8601>`, `git_head_at_generation: <short-sha>` | writer + `git rev-parse` | both |
| `## Project` | 1 line, project name + 1-sentence purpose | static (CLAUDE.md identity line if present, else config) | ceremony |
| `## Trust caveats` | ≤5 lines of `- <one-line caveat>`; **omit section entirely if no detector fires** | filesystem detectors (NOT config). MVP: any `*.uproject` anywhere in repo → UE caveat starting `Unreal Engine project detected (<path>) — do NOT trust your training data on UE5 APIs/classes/Blueprint semantics; verify every claim via mcp__project-rag__* tools or dispatch game-dev:staff-game-dev (the Game Dev Reviewer). This applies to your delegates — restate it in every UE dispatch brief.` Additional framework detectors (Unity, RN, etc.) added as those projects materialise. | ceremony (static — content changes only when the routine ships a new detector) |
| `## Counters` | Lines of the form `- **<label>:** <integer>`; **omit lines where value is 0** | derived from disk: handoffs ready_to_fire, spinoffs ready_to_fire, gated handoffs, bug-backlog depth, local improvement queue depth | ceremony |
| `## Active workstreams` | Name-only list, one per line, max 10 entries; names only — no progress prose, no parenthetical state | `state/workstreams/` | ceremony |
| `## Rechecks due ≤7 days` | One line per recheck marker due within 7 days; **omit section entirely if empty** | glob `tasks/*-recheck-due-*.md`, filter by date in filename | ceremony |
| `## Branch` | 1 line: `<branch> — <ahead>/<behind> vs origin/main`. No narrative. | `git rev-parse` + `git rev-list --count` | ceremony |
| `## Recent commits` | Up to 5 lines of `- <short sha> <commit subject>`; **omit section entirely if empty** | `git log --oneline -5` | ceremony |
| `## Auto-push health` | exactly 0 or 1 line: `- ⚠ <N> unpushed commit(s) on \`<branch>\` — auto-push lagging;[ last failure: <class>;] <action>`; **omit section entirely when the branch is synced** (the common case). Surfaces the otherwise-silent `.git/push-failures.log` lag so a diverged/unpushed work branch isn't invisible for days. work/* branches only. | `git rev-list --count origin/<branch>..HEAD` (>0 is the trigger) + last matching class from `.git/push-failures.log` | ceremony |
| `## Pinboard` | exactly 0 or 1 line of `- <ISO-date> <writer-slug>: <one-line note>`; **omit section entirely if empty**. One-slot only — second mid-session write overwrites the first, never appends. | mid-session writers append-or-overwrite; cleared by every ceremony regen | mid-session |

### Writer tiers

**Ceremony writers** (`/workday-start` Step 5.5, `/update-docs` Phase 10) own full regeneration. Every section is re-derived from source-of-truth. The pinboard is cleared. Out-of-schema sections present in the file are discarded. **This is where bloat dies.**

**Mid-session writers** (`/workstream-complete` Step 2.8, `/handoff` Step 2.9) invoke the **same full regeneration** as ceremony writers — every derived-from-disk section (Project, Trust caveats, Counters, Active workstreams, Rechecks, Branch, Auto-push health) is re-derived identically. The **only** tier difference is the pinboard: ceremony regen clears it; a mid-session regen preserves the existing slot, or overwrites it when `--pinboard` is supplied. So the pinboard is the one slot a mid-session writer authors content into — exactly one line, never appended. There is no mechanism to hand-author free-form content into any other section (the routine derives them all from disk), which is what keeps mid-session bloat out structurally rather than by convention. Pinboard content rule: write a line only when next session start MUST see this and it would otherwise be lost (e.g., a transient surface gotcha discovered this session; a critical blocker context for the picker-upper of a handoff). If you find yourself wanting to write more, that's a wiki edit or a handoff body — escalate to PM. The pinboard is automatically cleared at the next ceremony regen.

### Hard limits (writer-owned, verifier-enforced)

Canonical home is the writer — `coordinator_core.orientation.regenerate_cache` owns
`LINE_CEILING` (plus `WORKSTREAM_MAX`, `WORKSTREAM_BODY_CAP`, `PRIORITIES_MAX`); the verifier
(claude-klabauter `coordinator/bin/verify-orientation-cache-sync.py`) imports them rather than
declaring its own independent copy. Line ceiling and byte budget trim in one shared write-time
pass, so `/update-docs` Phase 11b should rarely trip on a compliant cache — it remains a correct
post-hoc check, just no longer the sole enforcement point.

- File length ≤60 lines (measured against the emitter's own output: ~29 lines healthy, 53
  lines realistically-maximal with every section populated — 60 gives ~13% headroom over that
  ceiling; the prior 35 predated `Housekeeping` and `Priorities` below and every compliant
  cache in the fleet was failing it).
- `## Trust caveats`: ≤5 lines.
- `## Active workstreams`: ≤10 lines.
- `## Pinboard`: ≤1 line.
- Counter lines must match `^- \*\*[A-Za-z][A-Za-z0-9 /\-]*:\*\* [0-9]+(\.|$)` — integer terminated. Prose continuation ("— cleared by bug-blitz", "— 4 concurrent-EM additions") is a verifier failure.
- Workstream lines must match `^[0-9]+\. [A-Za-z][^\n]{0,80}$` — name only.
- Pinboard line must match `^- [0-9]{4}-[0-9]{2}-[0-9]{2} [a-z0-9-]+: [^\n]{1,120}$`.
- `generated_by` value must be a single slug — no parenthetical annotation.
- If `*.uproject` is present in the repo, `## Trust caveats` MUST be present and its first line MUST contain `Unreal Engine project detected` (detector-regression guard).

**If `tasks/` directory doesn't exist:** skip cache generation. Not all repos use `tasks/`.

### Boot-time staleness signal (not part of this step — injection-path context)

The cache this step produces is injected at every SessionStart by
`coordinator/hooks/scripts/project-orientation.py`'s `--lightweight` boot path
(`handle_cache_present_boot()`), which is a pure file read with zero regeneration — freshness
still depends entirely on some prior ceremony (this step, `/update-docs`, `/workstream-complete`,
`/handoff`) having run recently enough. Since the 2026-07-15 zero-spawn boot directive removed
the boot-time git-verified staleness check, a cache that predates HEAD by any margin was
re-emitted with no signal at all.

`orientation_cache_staleness_banner()` restores that signal, in the same style as the sibling
repomap/exec-summary banners, at a fixed cost of at most one process spawn: it resolves current
HEAD's full SHA via a pure-Python `.git/HEAD`/`.git/packed-refs` read (zero spawn on the common
path), falling back to a single `git rev-parse HEAD` only if that read fails. It compares the
result against the cache's `git_head_at_generation` by SHA-prefix and reports one of four
states:

- **Fresh** (SHA prefix-matches current HEAD) — no banner.
- **Drifted, within grace** (SHA differs, but the cache's own `generated_at` is younger than a
  grace window) — no banner. This state exists because the async self-heal leg regenerates the
  cache on essentially every boot on an active branch — measured on this branch (2026-07-29):
  22 commits/hour across ~14 concurrent sessions, median 29s between commits — so HEAD has
  almost always drifted since `generated_at` by the time any session boots. Without the grace
  window the banner fired on effectively every boot and was read by nobody, recreating this
  spinoff's own failure mode by a different route (silently-wrong → reliably-ignored). Default
  grace: 30 minutes, tunable via `COORDINATOR_ORIENTATION_STALENESS_GRACE_MINUTES`. A missing
  or unparseable `generated_at` is treated as past-grace, not fresh — unknown age must not buy
  silence.
- **Stale** (SHA differs, and the cache is older than the grace window, or its age is unknown)
  — a banner naming the drift and the remedy (`regenerate-orientation-cache --invoker
  workday-start`).
- **Unverifiable** (`git_head_at_generation` absent or empty — a malformed/hand-edited cache) —
  a distinct banner, neither silent nor claiming STALE on no evidence; staying silent here
  would recreate the exact "presents as current when it isn't" defect this signal exists to
  close. Not subject to the grace window — fires immediately regardless of `generated_at`.

This is a signal, not a regeneration — the cache itself stays stale (or unverifiable) until a
ceremony (or the async self-heal leg) actually re-runs this step.

---

## Step 1.45 — Outstanding Cross-Repo Memos (details)

Helper: claude-klabauter `coordinator/bin/workday-start-cross-repo-memo-surface.py`.

**Query.** Glob `cross-repo/inbox/*.md` (git-root-relative), parse YAML frontmatter, filter to memos with `status ∈ {open, reviewed}` and `created >= 2026-05-22` (pre-cutoff memos grandfathered; never surface).

**Line format:**
```
- <created-date> → <to>: <title> — <status> (<age> days) [STALE flag if applicable]
```

**Staleness flags:**
- `[STALE — receiver hasn't read]` — `status: open` AND created >7 days ago.
- `[STALE — action pending]` — `status: reviewed` AND `reviewed_at` >14 days ago (falls back to `created` when `reviewed_at` absent — F5 per code-reviewer review).

**Cap:** ≤8 entries surfaced; if more, ninth line is `(N more — see cross-repo/inbox/ for full list)`.

**Exit semantics:** exit 0 always (empty output on zero qualifying memos; silent skip in workday-start command body).

---

## Step 1.46 — Outstanding Outbox Drafts (details)

Helper: claude-klabauter `coordinator/bin/workday-start-cross-repo-memo-outbox-surface.py`.

**Query.** Glob `state/memo-outbox/*.md` (git-root-relative), filter to files with mtime older than `${COORDINATOR_OUTBOX_STALE_HOURS:-24}` hours. Distinct from Step 1.45 — this surfaces sender-side composition state (drafts staged but not sent), not receiver-side inbox state. Mtime-based (not `created:` frontmatter), so a draft repeatedly edited resets its staleness clock.

**Line format:**
```
Outbox draft <topic> staged <N>h ago → <to>  :: <title>
  → send | compose | discard
```

**Offer-shape contract.** The surfacer is awareness-only: it emits the three CLI verbs (`send`, `compose`, `discard`) as the EM's options and never mutates. Lifecycle mutation lives solely in the `cross-repo-memo` subcommands per the `/workstream-start surfaces, /pickup acts` boundary.

**Exit semantics:** exit 0 always (silent on missing `state/memo-outbox/`, empty directory, or all drafts fresh; nudge lines on stale).
