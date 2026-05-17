---
name: workday-start
description: Morning orientation — triage handoffs, surface staleness, align priorities
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

Prepare the day's session-start calls to be maximally efficient. Ensure context is fresh, priorities are clear, and any overnight health findings are surfaced.

**Announce at start:** "I'm running workday-start to prepare the day's context."

## Step -1: Session Reaper

Run the session reaper before any other work to bound stale-session accumulation. Capture stdout to a log file; do not echo the reaped-session lines into the Morning Briefing prose.

```bash
REAP_LOG=$(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-reap-sessions 2>/dev/null)
if [[ -n "$REAP_LOG" ]]; then
  mkdir -p ~/.claude/logs
  printf '%s  %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$REAP_LOG" >> ~/.claude/logs/coordinator-reap.log
fi
```

If the wrapper exits non-zero (lib not found), continue — the reaper is operational hygiene, not a gate.

## Step 0: Branch Setup

Ensure work happens on an active workstream branch and reconcile it with `origin/main` daily. The active workstream may be either canonical (`work/{machine}/{date-or-span}`, machine always lowercase) **or** a named long-lived workstream bus (e.g. `migration/...`, `release/...`, `feature/...`) that the PM authorized. The daily ritual is **reconcile with origin/main**, not branch-rotation: as long as a single active workstream branch exists locally, keep loading work onto it until it's ready to merge. Consolidate lingering sibling `work/{machine}/...` branches into the active one.

**Sync-main invariant (run first, before any branch creation or rename):**
```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/sync-main.sh
```
If `sync-main.sh` exits non-zero, abort Step 0 and surface the divergence to the PM. Do not create a branch from stale main.

**Step 0 precedence switch** — evaluate conditions in order; stop at the first match:

1. **Stale-commit check (runs first):** Determine the epoch of the last commit on the current branch:
   ```bash
   LAST_EPOCH=$(git log -1 --format="%ct" 2>/dev/null || echo 0)
   NOW_EPOCH=$(date +%s)
   AGE_DAYS=$(( (NOW_EPOCH - LAST_EPOCH) / 86400 ))
   ```
   If `$AGE_DAYS > 2` AND the current branch is a `work/{machine}/...` branch → do NOT prompt rename. Surface to PM via the Branch Reconciliation A/B/C flow (below). This check runs first because a stale span branch whose end-suffix happens to equal today is still dead work that warrants A/B/C triage, not a silent exit.

2. **Already-in-span check (runs second):** Use `cs_should_prompt_rename` from the lib (sources automatically — see internals). If the current branch's end-suffix already matches today's date, exit Step 0 silently — no rename, no new branch needed.

3. **On main / detached / empty branch (runs third):** If the current branch is `main` or detached HEAD OR is non-main with zero commits ahead of `origin/main`, create a fresh canonical workstream branch:
   ```bash
   MACHINE=$(cs_compute_machine)   # always lowercase
   TODAY=$(date +%Y-%m-%d)
   COORDINATOR_OVERRIDE_BRANCH=1 \
   COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 create workstream branch" \
   git checkout -b "work/${MACHINE}/${TODAY}"
   git push -u origin "work/${MACHINE}/${TODAY}"
   ```

4. **Named long-lived workstream (runs fourth):** If `$CURRENT` is non-main, does NOT match `work/{machine}/...`, AND is ahead of `origin/main` → treat as an active named workstream bus. **Do not** create a fresh daily — that would abandon ongoing work. Skip the rename procedure (it is `work/{machine}/...`-specific) and proceed to the **daily origin/main reconcile** below, then continue to consolidation. The PM authorizes named workstreams via the inline override at branch-create time; once they exist, workday-start treats them as legitimate buses.

5. **Midnight-rename (runs last):** If the current branch is a `work/{machine}/...` branch whose last commit is ≤48h ago AND the end-suffix does NOT match today → run the rename procedure below silently and emit a one-line notice in the Morning Briefing (`Renamed work/striker/2026-05-06 → work/striker/2026-05-06to07 (crossed midnight)`). Do NOT prompt — this is engineering housekeeping, not a product call. The PM can revert via `git branch -m` if they object.

**Daily origin/main reconcile (runs after precedence resolves, for ANY non-main active branch):**
```bash
git fetch origin main
if git merge-base --is-ancestor origin/main HEAD; then
  : # already includes origin/main — nothing to do
elif COORDINATOR_OVERRIDE_BRANCH=1 \
     COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 reconcile origin/main" \
     git merge --ff-only origin/main 2>/dev/null; then
  echo "Fast-forwarded $(git branch --show-current) to include origin/main."
else
  if ! COORDINATOR_OVERRIDE_BRANCH=1 \
       COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 reconcile origin/main (merge)" \
       git merge --no-ff origin/main -m "reconcile origin/main into $(git branch --show-current) (workday-start)"; then
    git merge --abort
    echo "Reconcile conflict — surface to PM via A/B/C Branch Reconciliation Decision."
    # Fall through to conflict handling below; do not silently continue.
  fi
fi
```
This is the daily ritual that replaces "cut a fresh daily off main." Other contributors' work on `origin/main` is folded into the active workstream branch on each workday-start. Conflicts here go through the same A/B/C flow as consolidation conflicts.

**Rename procedure (the Staff Engineer F5 — atomic, reversible):**
```bash
OLD=$(git branch --show-current)
MACHINE=$(cs_compute_machine)
TODAY=$(date +%Y-%m-%d)
# Compute new name using cs_format_span_suffix from the lib
START_DATE=$(cs_parse_branch_span "$OLD" | awk '{print $1}')
NEW="work/${MACHINE}/$(cs_format_span_suffix "$START_DATE" "$TODAY")"

# Concurrent-rename race guard: re-check before touching refs
CURRENT=$(git branch --show-current)
TODAY_DD=$(date +%d)
if [[ "$CURRENT" == *"to${TODAY_DD}" ]]; then
  echo "Branch already renamed by another session — nothing to do."
  exit 0
fi

# Step a: local rename (cheap, reversible)
COORDINATOR_OVERRIDE_BRANCH=1 \
COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 rename across midnight" \
git branch -m "$OLD" "$NEW"

# Step b: atomic remote rename (both halves succeed or both fail; git ≥2.4)
if ! COORDINATOR_OVERRIDE_BRANCH=1 \
     COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 atomic rename push" \
     git push --atomic origin "${NEW}:${NEW}" ":${OLD}"; then
  # Roll back local rename on remote failure
  COORDINATOR_OVERRIDE_BRANCH=1 \
  COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 rename rollback after atomic push failure" \
  git branch -m "$NEW" "$OLD"
  echo "ERROR: remote rename rejected; local rolled back. Manual recovery may be needed."
  exit 1
fi

# Step c: re-wire local tracking so @{upstream} resolves correctly.
# git push --atomic creates the remote ref but does NOT update the local
# tracking pointer; @{upstream} stays pointed at the now-deleted OLD ref
# until this runs. Without it, coordinator-auto-push silently misroutes.
git branch --set-upstream-to="origin/${NEW}" "${NEW}"
```

After a successful rename, continue with the branch-consolidation flow (open unmerged `work/{machine}/*` branches, A/B/C conflict handling) using the new branch name as base.

**Inline override required:** every `git checkout`, `git merge`, `git branch -m`, and `git push --atomic` in Step 0 that touches off-daily refs must carry `COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 <action>"`. The `block-off-daily-branch.sh` hook denies these operations without the inline override. This now includes `git branch -m` for the rename flow. See `pipelines/workday-start-internals.md` § Step 0 for the full procedure.

**Full procedure, conflict handling, and rationale:** see `pipelines/workday-start-internals.md` § Step 0.

### Step 0 conflict handling — Branch Reconciliation Decision

When `git merge --no-ff` of a lingering branch hits a conflict, **do not silently continue**. Abort the merge and produce a **Branch Reconciliation Decision** block in the Morning Briefing naming each conflicting branch:

**Interactive sessions (TTY attached):** Hard-block until the PM chooses one of:
- **Option A — Consolidate now:** PM accepts the conflict and runs `/consolidate-git` immediately. The skill chains into it; workday-start resumes after consolidation completes.
- **Option B — Defer:** PM explicitly defers the branch. Write one entry to `tasks/.deferred-branches.md`:
  ```
  {branch} | reason: {PM-provided reason} | re-check: {today + 7 days} | deferred-by: workday-start {today}
  ```
  The next workday-start will surface this entry prominently if the re-check date has passed.
- **Option C — Archive (abandon):** PM signals the branch is dead. Rename it `archive/{machine}/{today}/{original-branch-name}` locally; push the renamed ref; delete the old ref. Stop tracking.

**Non-interactive sessions (no TTY — overnight/mise-en-place chained):** Auto-defer unresolved branches with `reason=auto-deferred, awaiting PM` and `re-check={today}`. Emit a note in the Morning Briefing. The next interactive workday-start will surface them prominently and force the A/B/C decision.

## Step 0.5: Orphan Branch Sweep

Run `bin/orphan-branch-sweep.sh --format text --severity-min warning`. For each line returned:

- **CRITICAL** entries → surface in the Morning Briefing under a `### Orphan Sweep` section. Include the branch name, the merged PR number, and the count of post-merge commits. Recommend: _"Investigate before opening new work — these commits may be orphaned. Salvage via PR or consolidate into today's branch."_
- **WARNING** entries → surface as a heads-up in the same section. Recommend: _"Open a PR or consolidate before the branch goes stale."_
- **No output** → skip silently (do not emit "no orphans found" — noise).

Append the rendered section to the Morning Briefing template in Step 5 (after `### Alignment Check`, before `### Priority Suggestions`).

## Step 0.6: Agent Worktree Sweep

Claude Code 2.1.x auto-creates per-dispatch worktrees under `<repo>/.claude/worktrees/agent-<hash>/` for backgrounded `Agent` calls. They persist locked until session deletion (no auto-cleanup on agent completion) and accumulate across days. Doctrine forbids worktrees as a parallelism mechanism — see `docs/wiki/dispatching-parallel-agents.md` § Worktree vs. Same-Worktree Dispatch — so any agent worktree on disk is unintended residue.

Run the sweep in `--reap` mode to consolidate and remove:

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/agent-worktree-sweep.sh --reap --format text
```

Per-worktree disposition:
- **`empty-clean`** (no commits ahead of the active branch, no dirty files) → removed silently.
- **`commits-clean`** (commits ahead, no dirty files) → cherry-picked onto the active workstream branch (carries `COORDINATOR_OVERRIDE_BRANCH=1` for the off-daily hook), then removed. Cherry-pick conflict aborts the pick, leaves the worktree intact, exit 3.
- **`dirty`** (uncommitted changes) → left alone. Almost always benign bystander dirt (e.g. `.claude/settings.local.json` permission auto-adds), but the EM does not auto-discard.

**Surface in the Morning Briefing under a new `### Agent Worktrees` section** if anything other than `empty-clean → removed` was reported:

```
### Agent Worktrees
- [N] worktrees swept ([K] removed clean, [S] salvaged + removed, [D] dirty retained, [F] salvage-conflict).
- Dirty retained: [list paths]. Inspect with `cd <path> && git status` and either commit, discard, or `git worktree remove --force` after triage.
- Salvage-conflict: [list paths]. Cherry-pick stopped on a conflict; resolve manually or remove if the commits aren't worth recovering.
```

If every worktree was clean (or none existed), omit the section.

**Why here, not Step 0.5:** Orphan-branch-sweep (Step 0.5) operates on user-owned `work/*` and `feature/*` branches — agent-isolation worktrees use ephemeral `worktree-agent-*` branches that don't match those patterns, so they're invisible to that pass.

## Step 0.7: Consumed-Marker Frontmatter Sync

Belt-and-suspenders against the most common handoff-frontmatter drift: EMs sometimes mark work shipped with an inline `<!-- consumed: YYYY-MM-DD [notes] -->` body marker but forget to flip `status:` / `deployment_state:` in frontmatter. Step 1's `query-records` calls read frontmatter as authoritative, so unflipped records surface in `ready_to_fire` queries and waste triage attention.

```bash
node ~/.claude/plugins/coordinator-claude/coordinator/bin/normalize-consumed-frontmatter.js
```

The script is idempotent; prints a one-line no-drift notice to stderr when nothing changes. Each surfaced change line names the file and the field flips; if more than a handful surface, mention the count in the Morning Briefing — recurring drift is a doctrine signal worth surfacing to the PM (consider `coordinator:learn-lessons` if it recurs across days).
<!-- Review: the Staff Engineer F6 — "silent on no-op" was inaccurate; the script writes "No drift" to stderr. Updated to accurate phrasing. Do not redirect stderr — the diagnostic has value when an EM debugs why nothing flipped. -->

Scans handoffs + plans + decisions + reviews. Also strips `gate_dependency:` on flipped records — the field is only meaningful while `deployment_state: awaiting_gate` and is stale noise once shipped. Terminal states (`status: superseded`, `deployment_state: abandoned`) are preserved.

## Step 1: Handoff Triage

Query-driven, not grep-driven. Two `bin/query-records` calls — sub-second by construction.

### Step 1.1: Actionable-now handoffs

```bash
bin/query-records --type handoff \
  --where "deployment_state=ready_to_fire AND status=active" \
  --sort "-created" --format markdown-list
```

Routing on `kind:` (spinoffs cluster separately):

- **`kind: spinoff` and `kind: spinoff-roadmap`** — both are pickup-able forks. List together in a "Spinoffs awaiting pickup" subsection. `spinoff-roadmap` rows additionally cluster by `roadmap_id:` (group all stubs from a single roadmap-planning run) — surface roadmap heading + stub count, not raw rows, when `roadmap_id` is non-empty and the count > 3.
- **`kind: session-handoff`** (or absent) and **`kind: recovery`** — list together in a "Continuation handoffs" subsection. Recovery rows get a `(recovery)` suffix so the PM can see at a glance which continuations came from a crashed/killed prior session.

### Step 1.2: Gated handoffs (always surface count; flag stale subset)

Two queries — first lists everything `awaiting_gate`, second flags the stale subset:

```bash
bin/query-records --type handoff \
  --where "deployment_state=awaiting_gate AND status=active" \
  --sort "-created" --format markdown-list

bin/query-records --type handoff \
  --where "deployment_state=awaiting_gate AND status=active" \
  --older-than 6d --format markdown-list
```

- **If any `awaiting_gate` exist:** surface the full list as a "Gated handoffs" subsection (titles + gate_dependency, not bodies). Morning briefing is the right surface for cross-workstream gate awareness — silently filtering them buries actionable triage decisions (clear gate, retarget, pick up early).
- **If any are >6 days old:** additionally flag _"{M} handoffs awaiting_gate >6 days — gate may be stuck; consider triage, PM clear-gate, or close out."_
- **If none exist:** skip silently.

Threshold rationale: six days is roughly one working week. Long enough that a gate that hasn't cleared deserves a glance; short enough to catch drift before it ossifies. The prior 14-day threshold + only-emit-if-stale pattern buried gated handoffs that the PM needed for cross-workstream planning.

### Step 1.3: Reconcile pending items against git (MANDATORY before declaring any item actionable)

Per-handoff in the `ready_to_fire` set: (a) `git log --oneline --since="<handoff-date>" --all` and scan subjects for matching pending items; (b) Read referenced plan/stub `**Status:**` fields; (c) drop confirmed-closed items from the actionable list, note as "verified-closed since handoff" in the report. Empirical baseline: 30–60% of inherited items are already closed. **Full procedure + rationale:** see `pipelines/workday-start-internals.md` § Step 1.

### Step 1.4: Cross-reference against completed archive (sanity check)

Read `archive/completed/YYYY-MM.md` (current month, plus previous month if within the first 7 days). For each `ready_to_fire` handoff, check whether the work it describes appears as completed — match on workstream names, feature names, commit hashes, or distinctive keywords. If a match is found, flag it: _"Handoff [file] describes [work] — archive/completed shows this shipped on [date] (commit: [hash]). Likely already done — pick up to confirm and archive, or close out?"_

### Step 1.5: Report

_"{N} actionable handoffs ({K} continuations, {S} spinoffs incl. {R} roadmap stubs in {G} groups). {G} awaiting_gate (of which {M} >6 days) [if any]. {X} items verified-closed by git reconciliation."_ Omit any clause whose count is zero.

**Why query, not grep (doctrine reversal documented 2026-05-08, revised 2026-05-15):** the prior "surface everything, archive nothing" policy assumed the EM grep-walks every handoff to assess readiness — exactly the agentic-grep `deployment_state` is designed to obviate. Filtering to `ready_to_fire` for the primary actionable list remains correct; `awaiting_gate` items now surface as their own subsection (count always, list always when present) rather than hiding behind a staleness gate, so cross-workstream gate awareness reaches the PM.

## Step 1.5: Coordinator-Improvement Queue Check

Read `~/.claude/tasks/coordinator-improvement-queue.md` (if it exists). Count `- ` lines in `## Active queue`; note the oldest date and any entries carrying `[recurring: ≥3]` on the main line (DR-056 amended 2026-05-17 — main-line-only schema).

Also read the local `tasks/improvement-queue.md` (if it exists in the current repo). Count its `## Active queue` entries.

**If the combined queue is notable (any of the below):**
- Central queue ≥ 5 active entries, OR
- Oldest entry > 14 days old, OR
- Any entry carries `[recurring: ≥3]` on its main line, OR
- Local queue has ≥ 1 active entry

Surface in the Morning Briefing. The EM decides whether to advocate based on depth — this is judgment, not a threshold trigger. Examples:

- Light: _"Coordinator-improvement queue has [K] entries (oldest: YYYY-MM-DD)."_
- Deep: _"Improvement queue is at [K] central + [L] local. [N] items have recurring ≥ 3 — urgency for those to become structural fixes is building. Want to dedicate some time today to clearing some?"_

If the file does not exist or both queues are empty, skip silently.

## Step 1.55: Bug Backlog Depth Check

Read `tasks/bug-backlog.md` (if it exists). Count table rows in the P1 and P2 sections, stopping before any `## Resolved` section. Exclude header rows and separator lines — count only data rows.

If the combined P1+P2 open count is ≥ 10, surface in the Morning Briefing. The EM advocates based on depth:

- Moderate (10–19): _"Bug backlog has [N] open P1/P2 items. `/bug-blitz` can grind these down autonomously."_
- Heavy (≥ 20): _"Bug backlog is at [N] open P1/P2 items — grinding pressure is building. Worth dedicating a session to `/bug-blitz` before it compounds."_

If the file does not exist, or the P1+P2 count is < 10, skip silently.

## Step 1.6: Scheduled Rechecks

Glob `tasks/cookbook-recheck-due-*.md`, `tasks/inspiration-recheck-due-*.md` (open-source comparison rechecks per `docs/wiki/opensource/`), `tasks/lesson-triage-recheck-due-*.md` (cross-project learn-lessons cadence per `coordinator:learn-lessons`), and `tasks/recheck-due-*.md` (general scheduled-recheck markers). Each marker filename ends in `-YYYY-MM-DD.md` indicating the due date.

For each marker found:
- **If today's date ≥ due date**, surface to the PM in the Morning Briefing's Priority Suggestions: _"Scheduled recheck due: `<filename>` (due {YYYY-MM-DD}). Procedure inside the file."_
- **If due date is within 7 days**, surface as a heads-up: _"Scheduled recheck upcoming: `<filename>` (due {YYYY-MM-DD}, in {N} days)."_
- **Otherwise**, skip silently.

If no marker files exist, skip silently. Do not auto-execute the recheck procedure — these markers are PM-actioned, not auto-dispatched.

## Step 1.7: Project-RAG Preamble Drift Check

Run `bin/verify-preamble-sync.sh` (relative to the coordinator plugin root, typically `~/.claude/plugins/coordinator-claude/coordinator/bin/verify-preamble-sync.sh`).

- **If no consumers found** (script exits 0 with "no consumers found" message): skip silently.
- **If all consumers OK** (exit 0, all lines show `OK`): skip silently.
- **If any MISMATCH or MISSING_END** (exit non-zero): surface to PM in the Morning Briefing under a new **Preamble Drift** line:

  _"project-rag-preamble drift detected in [N] consumer(s): [list files]. Run `bin/verify-preamble-sync.sh --fix` to repair, then commit all touched files together."_

**Do NOT auto-fix.** The EM should investigate which consumer drifted and why before applying `--fix`. A drift may indicate an intentional local edit that needs to be merged back into the canonical snippet rather than simply overwritten.

## Step 1.8: Auto-Push Failure Surface

Silent `coordinator-auto-push` failures (e.g. case-mismatched branch refs on Windows; expired credentials; SSH agent unreachable) accumulate in `.git/push-failures.log` without any visible signal until the next manual push. This step makes them visible the next morning, not 75 minutes later.

```bash
LOG=".git/push-failures.log"
if [[ -s "$LOG" ]]; then
  TOTAL=$(wc -l < "$LOG" | tr -d ' ')
  RECENT_24H=$(awk -v cutoff="$(date -d '24 hours ago' -Iseconds 2>/dev/null || date -v-1d -Iseconds 2>/dev/null)" \
    '$0 >= "[" cutoff' "$LOG" | wc -l | tr -d ' ')
  LAST_LINE=$(tail -1 "$LOG")
fi
```

**Surface in the Morning Briefing under a new `### Auto-Push Health` section if any of:**
- `RECENT_24H ≥ 1` (fresh failure since yesterday — almost always actionable)
- `TOTAL ≥ 5` (chronic backlog)

Format:
```
### Auto-Push Health
- [N] failures in last 24h (total log: [M] lines). Most recent: [LAST_LINE].
- Investigate before opening new work — silent push failures usually indicate a credential/branch-case/agent issue that will keep firing on every commit.
- Cleanup after fix: `> .git/push-failures.log` (truncate; do not delete the file — the helper appends in-place).
```

**If `RECENT_24H == 0` AND `TOTAL < 5`:** skip silently — the log is either empty or carries old, already-resolved entries.

**Cross-repo extension (deferred):** the handoff that drove this section calls for scanning *all* coordinator-tracked repos, but no registry of tracked repos exists yet. V1 checks the current repo only. If a registry lands (`~/.claude/coordinator-tracked-repos.txt` or similar), extend this step to glob across listed roots.

- **Last session-end review (informational):** if `tasks/review-trail/` has any records, surface the most recent one (`ls -t tasks/review-trail/*.json | head -1`) so the EM picks up the chain knowing what was reviewed and where the un-reviewed gap begins.

## Step 2: Doc Freshness

Check if documentation is stale relative to recent code changes:

1. Find the last update-docs run:
   ```bash
   git log --oneline --grep="update-docs\|workday-complete" --since="7 days ago" -1
   ```
2. Find commits since that run:
   ```bash
   git log --oneline <last-update-docs-commit>..HEAD
   ```
3. **If commits exist since last update-docs:** Flag: _"Docs are stale — [N] commits since last update-docs. Recommend running `/update-docs` before feature work."_ Do NOT dispatch update-docs automatically — it commits files, which would race with any other workday-start operations on the working tree. The PM can invoke it after workday-start completes.
4. **If no commits since:** "Docs are current."

## Step 3: Test Staleness

Check if the test suite should be run:

1. Detect test framework (same as bug-sweep Phase 0)
2. If tests exist:
   - Find the most recent test-related commit or CI run
   - Find code changes since then
   - **If code changed since last test run:** Flag: _"Tests haven't been run since [N] commits ago. Recommend running test suite."_
   - Don't run them automatically — the PM decides. But surface the staleness.
3. If no tests exist: skip silently

## Step 3.5: Bug Sweep Staleness

Check if a bug sweep should be suggested — based on **code churn since last sweep**, not just calendar time:

1. Read `tasks/bug-backlog.md` header for `Last sweep:` date and `Commit at sweep:` hash

   **Expected header format** (written by `/bug-sweep`):
   `> Last sweep: YYYY-MM-DD | Commit at sweep: [short hash] | Open: N items (P0: X, P1: Y, P2: Z)`
   Parse `Last sweep:` for date and `Commit at sweep:` for the anchor hash.

2. If no backlog exists: no sweep has ever run. Check codebase substance:
   ```bash
   # Count source files (not docs, configs, or generated files)
   find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.cpp" -o -name "*.h" -o -name "*.cs" -o -name "*.go" -o -name "*.rs" | grep -v node_modules | grep -v __pycache__ | wc -l
   ```
   If the repo has >50 source files, suggest a first sweep: _"No bug sweep has ever run on this codebase ([N] source files). Recommend running bug-sweep."_
   If <50 source files, skip silently — small repos don't need formal sweeps.
3. If backlog exists, count commits since the sweep's anchor commit:
   ```bash
   git rev-list --count <sweep-commit>..HEAD
   ```
4. **Suggest sweep if:**
   - >50 commits since last sweep AND >7 days since last sweep (significant churn with time floor — prevents nagging during sprint-mode work), OR
   - >14 days since last sweep AND >20 commits since last sweep (moderate churn + time)
   - _"Bug sweep last ran [date] ([N] commits ago). Recommend running bug-sweep before new feature work."_
5. If few commits since last sweep: "Bug sweep is current ([N] commits since last sweep)."

**The trigger is churn, not calendar.** A repo with no commits in 2 months doesn't need sweeping. A repo with 80 commits in a week might, but we wait at least 7 days to avoid suggestion fatigue during intensive work.

## Step 3.6: Project-RAG Staleness (conditional)

**Skip silently** if `ToolSearch` does not find any `mcp__project-rag__*`
tool. This is the same gate pattern used in Step (project-rag block) of
`session-start.md` — coordinator does not depend on the project-rag plugin; it
only adapts when the plugin is present. No warning emitted on skip.

When present:

1. Resolve the registered project root from `~/.claude.json`:
   ```bash
   python -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude.json'))); print(d['mcpServers']['project-rag']['args'][-1])"
   ```
   This returns the `--project-root` value passed to the MCP server boot.

2. Locate the project-rag plugin's cli.py. The path is recorded in
   `~/.claude.json` → `mcpServers.project-rag.args` (the script path).
   Use the same parse as step 1 to extract it.

3. Invoke the staleness survey:
   ```bash
   python <plugin-cli-path> staleness-survey --project-root <project-root> --json
   ```

4. Parse the JSON. If `verdict == "current"`, emit nothing. Otherwise inline
   the rendered output into the Morning Briefing under a new **Project-RAG**
   line (template below).

**Flag-only — never auto-run.** A reindex (`/project-rag:index --incremental`)
can race with an open editor and risks project-lock contention. The PM invokes
the recommendation manually after `/workday-start` completes.

## Step 4: Priority Alignment

Run the deterministic priority script and let it frame the opening surface:

```bash
bash plugins/coordinator-claude/coordinator/bin/whats-next.sh
```

The script emits three sections: improvement-queue head (top 5 entries),
`docs/project-tracker.md` rows with status Ready or Executing, and open
handoffs (filename + line-1 heading). Use the output as-is — do not
reconstruct it from prose. Frame the output for the PM in the Morning
Briefing under § Priority Suggestions.

**Reconcile active work against completed archive:** Read
`archive/completed/YYYY-MM.md` (current month + previous month if within
first 7 days). Cross-reference tracker Ready/Executing items and open
handoffs against the completed archive:
- **Tracker items** marked Ready/Executing → do any match completed archive entries? Flag: _"Tracker shows [workstream] as [status], but archive/completed records it shipped on [date]."_
- **Open handoffs** → do any appear in the archive as shipped? Flag the same way.
- This is a **fuzzy match on names/descriptions**, not an exact ID join. When unsure, flag as "possible match — verify" rather than auto-resolving.
- Report mismatches in the Morning Briefing under a new **Alignment Check** section.

## Step 5: Morning Briefing

Present a concise morning report:

```markdown
## Good Morning — Workday Start

**Date:** YYYY-MM-DD
**Branch:** [current branch]

### Context Freshness
- Handoffs: [N] actionable for today, [M] stale (flagged for /update-docs archival)
- Docs: [current / stale — N commits since last update-docs]
- Tests: [current / N commits since last run — suggest running]
- Health: last daily check [today/N days ago], last weekly audit [N days ago]
- Atlas: [N systems mapped, M stale >90 days / no atlas]
- Bug backlog: [N open (P0: X, P1: Y) / empty / no backlog]
- Bug sweep: [current (N commits since) / suggest sweep (N commits since last)]
- Project-RAG: [{verdict} — {age}, {code_commits} commits / {asset_changes} assets / verdict source: {recommendation_command}] _(omit this line if verdict is `current`)_
- Tools: [missing optional tools, if any — see below]

### Tool Availability
Check for optional tools that enhance the pipeline. Surface missing ones as install suggestions:
- **scc** (code statistics): Check `scc` on PATH, then `~/bin/scc`. If missing: _"scc not installed — code statistics won't appear in orientation. Install: `winget install BenBoyter.scc` (or download to ~/bin/scc)."_
- **shellcheck** (shell linting): Check `shellcheck` on PATH. If missing: _"shellcheck not installed — .sh files won't be linted on commit. Install: `winget install koalaman.shellcheck`."_

If both are present, report: _"Tools: scc + shellcheck available."_ Only nag for missing tools — don't repeat if already installed.

### Handoffs
- **Continuation:** [N active, M aging, K likely-consumed]
- **Spinoffs awaiting pickup:** [list each: filename — title — age — workstream]
  _(Omit this bullet if no spinoffs exist.)_
- **Stale spinoffs (≥14 days):** [list each with a one-line nudge]
  _(Omit this bullet if no stale spinoffs exist.)_

### Alignment Check
- [N mismatches found between active trackers and completed archive / all aligned]
- [List each mismatch: "Tracker: X is Executing — Archive: shipped YYYY-MM-DD"]
- [List each handoff flagged as likely completed]

### Orphan Sweep
_(Omit this section entirely if orphan-branch-sweep.sh produced no WARNING or CRITICAL output.)_
- **CRITICAL:** [branch] — PR #N merged, [M] commits added after merge. Investigate before new work.
- **WARNING:** [branch] — no PR, [N] commits, branch date [YYYY-MM-DD]. Open a PR or consolidate.

### Agent Worktrees
_(Omit this section entirely if Step 0.6 found nothing or only `empty-clean → removed` worktrees.)_
- [N] worktrees swept ([K] removed clean, [S] salvaged + removed, [D] dirty retained, [F] salvage-conflict).
- Dirty retained: [list paths]. Inspect with `cd <path> && git status` and either commit, discard, or `git worktree remove --force` after triage.
- Salvage-conflict: [list paths]. Cherry-pick stopped on a conflict; resolve manually or remove if the commits aren't worth recovering.

### Auto-Push Health
_(Omit this section entirely if Step 1.8 found `RECENT_24H == 0` AND `TOTAL < 5`.)_
- [N] failures in last 24h (total log: [M] lines). Most recent: [last log line].
- Investigate before opening new work — silent push failures usually indicate a credential/branch-case/agent issue that will keep firing on every commit.

### Priority Suggestions
Based on project state:
1. **[If bugs exist]** Fix [top severity bug] before new feature work
2. **[If sweep stale]** Run bug-sweep — [N] commits since last sweep
3. **[If tests stale]** Run test suite to verify current state
4. **[If atlas stale]** Consider running deep-architecture-audit refresh
5. **[If tracker items ready]** [Workstream X] is ready for execution
6. **[If debt high]** Debt backlog has [N] items — consider debt-triage

### What should today's focus be?
[Surface tracker Ready items, handoff action items, and PM-facing options]
```

**Set marker:** Write `tasks/.workday-start-marker` with today's date. Single location, no dependency on health tracking subsystem. Session-start checks this one file.
```
YYYY-MM-DD
```

## Step 5.5: Write Orientation Cache

Generate `tasks/orientation_cache.md` — a compact 40-60 line summary the SessionStart hook injects in subsequent sessions instead of raw repomap/DIRECTORY content. Sections: Key Documentation (from `docs/README.md`), Structure (top 15 from repomap), Navigation (from DIRECTORY.md), Code Statistics (`scc` if available), Health Snapshot, Doc Inventory, Staleness markers, Yesterday's Strategic Review (from `archive/daily-summaries/`). Frontmatter: `generated_by`, `generated_at`, `git_head_at_generation`. Skip if `tasks/` doesn't exist.

The Health Snapshot includes handoff state mirroring the Step 1 split: one line for continuation handoffs, a separate line for spinoffs (`Spinoffs: N awaiting pickup (T stale)`). Omit the spinoffs line if N=0.

**Full content derivation per section:** see `pipelines/workday-start-internals.md` § Step 5.5.

## What This Does NOT Do

- **Run bug-sweep.** That's a dedicated operation the PM invokes when ready.
- **Run daily-code-health.** That's the night shift (workday-complete Step 3).
- **Run deep-architecture-audit.** That's monthly. workday-start just surfaces atlas staleness.
- **Merge to main.** Use `/merge-to-main` for that.
- **Choose work.** That's session-start's Engage section. workday-start prepares the ground; session-start picks the work.
- **Replace session-start.** workday-start prepares the ground; session-start picks the work.
- **Auto-dispatch update-docs.** It commits files, which would race with workday-start operations. Flag staleness; the PM invokes manually after workday-start completes.

## Relationship to Other Commands

- **`session-start`** — runs per-session (many per day). workday-start runs once. Session-start detects if workday-start ran today and skips redundant checks.
- **`workday-complete`** — the evening counterpart. Runs update-docs, consolidates branches, runs health survey.
- **`update-docs`** — may be recommended by workday-start if docs are stale. Not auto-dispatched.
- **`bug-sweep`** — independent skill. workday-start surfaces backlog state but doesn't run the sweep.

## Concurrent Session Safety

workday-start is read-only for all project tracking files. It writes only one file: `tasks/.workday-start-marker`. Multiple sessions can safely read the same health files; the marker is a simple date string with no merge-conflict risk.

**Failure mode to avoid:** Acting on stale handoff items that a concurrent session already shipped. Prevention: the mandatory git log + plan status reconciliation in Step 1, item 6 — run it before propagating any inherited items into Priority Suggestions or the work menu.

If `$ARGUMENTS` is provided, include it as a focus hint in the Morning Briefing: _"Requested focus: {arguments}"_
