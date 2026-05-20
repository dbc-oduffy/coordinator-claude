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
REAP_LOG=$(~/.claude/plugins/coordinator/bin/coordinator-reap-sessions 2>/dev/null)
if [[ -n "$REAP_LOG" ]]; then
  mkdir -p ~/.claude/logs
  printf '%s  %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$REAP_LOG" >> ~/.claude/logs/coordinator-reap.log
fi
```

If the wrapper exits non-zero (lib not found), continue — the reaper is operational hygiene, not a gate.

## Step 0: Branch Setup

Ensure work happens on an active workstream branch and reconcile with `origin/main` daily. The active workstream may be canonical (`work/{machine}/{date-or-span}`, machine lowercase) **or** a named long-lived bus (`migration/...`, `release/...`, `feature/...`) the PM authorized. Daily ritual is **reconcile with origin/main**, not rotation: keep loading the same active branch until it's ready to merge.

**Precedence switch** (evaluate in order; stop at first match): (1) stale-commit (>2 days) → A/B/C Branch Reconciliation flow; (2) already-in-span → silent exit; (3) on main/detached/empty → create `work/{machine}/{today}`; (4) named long-lived bus → skip rename, proceed to reconcile; (5) midnight-rename → atomic rename procedure + one-line briefing notice.

Every off-daily ref operation requires `COORDINATOR_OVERRIDE_BRANCH=1 COORDINATOR_OVERRIDE_BRANCH_REASON="workday-start step 0 <action>"`.

**Run the canonical Step 0 script — do not transcribe the procedure inline:**

```bash
bash ~/.claude/plugins/coordinator/bin/workday-start-step0.sh
```

The script encapsulates sync-main, the precedence switch (Checks 1–4 + 3.5), the rename procedure (Step 0.4), and the reconcile flow (Step 0.4.5).

**Stdout shape:** one line on IN-SPAN (no reconcile needed); two lines on FRESH-CUT / NAMED-WORKSTREAM / RENAMED (precedence status + reconcile status: `ALREADY-CURRENT`, `RECONCILED-FF`, or `RECONCILED-MERGE`). Surface both in the Morning Briefing.

Exit codes: `0` success; `2` `STALE-NEEDS-ABC` → invoke A/B/C flow below; `3` `RECONCILE-CONFLICT` → PM resolves; `1` unexpected error → halt.

**Why a script, not inline bash:** the procedure was empirically EM-skippable when expressed as a prose reference — concentrating precedence + rename + reconcile in a single invokable removes EM judgment from a deterministic procedure. Full rationale: `pipelines/workday-start-internals.md` § Step 0.

**Step 0 is not EM-skippable on judgment.** "Reconcile not rotate" governs whether to *abandon* the branch (no), not whether to *rename* the suffix at midnight (yes, via Check 4). Legitimate skips are only the precedence outcomes the script reports (`IN-SPAN`, `NAMED-WORKSTREAM`, `FRESH-CUT`). Any other path MUST execute the rename when Check 4 fires; Step 0.45 below is the tripwire catching silent skips.

### Step 0.45: Post-Step-0 Span Assertion

After the precedence switch resolves, verify the active branch's name covers today. This catches EM judgment-skips, rename failures, and silent fall-throughs — the library helpers return correct results, but a Step 0 path that never invokes rename leaves the working tree out of sync.

```bash
source ~/.claude/plugins/coordinator/lib/coordinator-daily-branch.sh
CURRENT=$(git branch --show-current)
TODAY=$(date +%Y-%m-%d)
SPAN_ASSERT_FAIL=
SPAN_ASSERT_MSG=

if cs_parse_branch_span "$CURRENT" > /dev/null 2>&1; then
  END_DATE=$(cs_parse_branch_span "$CURRENT" | awk '{print $2}')
  if [[ "$END_DATE" != "$TODAY" ]]; then
    SPAN_ASSERT_FAIL=1
    EXPECTED="work/$(cs_compute_machine)/$(cs_format_span_suffix "$(cs_parse_branch_span "$CURRENT" | awk '{print $1}')" "$TODAY")"
    SPAN_ASSERT_MSG="Active branch \`$CURRENT\` does not cover today ($TODAY) — end=$END_DATE, expected rename to \`$EXPECTED\`. Step 0 Check 4 did not fire. The library helpers work; the rename was skipped at the command level. Re-run \`/workday-start\` Step 0 manually or rename inline."
  fi
fi
```

- **If `$SPAN_ASSERT_FAIL` is set:** surface `$SPAN_ASSERT_MSG` as a top-line `### Branch Span Mismatch` block in the Morning Briefing (above `### Context Freshness`). Do NOT auto-rename here — the assertion is a tripwire, not a retry mechanism.
- **If the branch does not parse as `work/{machine}/...`** (named long-lived workstream, `main`, or other authorized shape): skip the assertion silently. Check 3.5 in Step 0 already covered this case by design.
- **If the branch parses and end-DD == today:** skip silently — Step 0 did its job.

Rationale: empirical drift (2026-05-18) — EM cited "reconcile not rotate" to skip the suffix bump. That doctrine forbids *abandoning* the branch, not skipping the midnight rename.

### Step 0 conflict handling — Branch Reconciliation Decision

When `git merge --no-ff` of a lingering branch hits a conflict, **do not silently continue**. Abort the merge and produce a **Branch Reconciliation Decision** block in the Morning Briefing naming each conflicting branch:

**Interactive sessions (TTY attached):** Hard-block until the PM chooses one of:
- **A — Consolidate now:** run `/consolidate-git`; resume after.
- **B — Defer:** write `tasks/.deferred-branches.md` entry: `{branch} | reason: {reason} | re-check: {today+7d} | deferred-by: workday-start {today}`. Surfaced next morning if re-check date passed.
- **C — Archive (abandon):** rename `archive/{machine}/{today}/{branch}` locally; push; delete old ref.

**Non-interactive sessions (no TTY):** Auto-defer with `reason=auto-deferred, awaiting PM` and `re-check={today}`; emit note in the Morning Briefing. Next interactive run forces A/B/C.

## Step 0.5: Orphan Branch Sweep

Run `bin/orphan-branch-sweep.sh --format text --severity-min warning`. For each line returned:

- **CRITICAL** entries → surface in the Morning Briefing under a `### Orphan Sweep` section. Include the branch name, the merged PR number, and the count of post-merge commits. Recommend: _"Investigate before opening new work — these commits may be orphaned. Salvage via PR or consolidate into today's branch."_
- **WARNING** entries → surface as a heads-up in the same section. Recommend: _"Open a PR or consolidate before the branch goes stale."_
- **No output** → skip silently (do not emit "no orphans found" — noise).

Append the rendered section to the Morning Briefing template in Step 5 (after `### Alignment Check`, before `### Priority Suggestions`).

## Step 0.6: Agent Worktree Sweep

Claude Code 2.1.x auto-creates per-dispatch worktrees under `<repo>/.claude/worktrees/agent-<hash>/` that accumulate and are never auto-cleaned. Doctrine forbids worktrees as a parallelism mechanism (→ `docs/wiki/dispatching-parallel-agents.md` § Worktree vs. Same-Worktree Dispatch); any on disk is unintended residue.

Run the sweep in `--reap` mode to consolidate and remove:

```bash
~/.claude/plugins/coordinator/bin/agent-worktree-sweep.sh --reap --format text
```

Per-worktree disposition:
- **`empty-clean`** (no commits ahead of the active branch, no dirty files) → removed silently.
- **`commits-clean`** (commits ahead, no dirty files) → cherry-picked onto the active workstream branch (carries `COORDINATOR_OVERRIDE_BRANCH=1` for the off-daily hook), then removed. Cherry-pick conflict aborts the pick, leaves the worktree intact, exit 3.
- **`dirty-benign`** (uncommitted changes confined to the known auto-add allowlist: `.claude/settings.local.json`, `.last-cleanup`) → `git worktree remove --force`. This is the common "Claude Code permission auto-add" residue and discarding it is correct — the same file in the main worktree is authoritative.
- **`dirty`** (anything outside the benign allowlist, including commits-ahead-AND-dirty) → left alone. EM must triage.

**Surface in the Morning Briefing under a new `### Agent Worktrees` section** only when something other than `empty-clean → removed` / `dirty-benign → removed` happened. Pure benign-discard runs are silent — clearing residue is the point, not a reportable event.

```
### Agent Worktrees
- [N] worktrees swept ([K] removed clean, [B] benign-dirty removed, [S] salvaged + removed, [D] dirty retained, [F] salvage-conflict).
- Dirty retained: [list paths]. Inspect with `cd <path> && git status` and either commit, discard, or `git worktree remove --force` after triage.
- Salvage-conflict: [list paths]. Cherry-pick stopped on a conflict; resolve manually or remove if the commits aren't worth recovering.
```

All-clean or all-benign-discarded runs omit the section entirely. **Do not** emit "dirty retained" lines under "probably benign" framing — if it were benign by the allowlist, the script removed it; outside the allowlist, the EM triages.

**Why here, not Step 0.5:** orphan-branch-sweep matches `work/*` / `feature/*`; agent worktrees use ephemeral `worktree-agent-*` branches invisible to that pass.

## Step 0.7: Consumed-Marker Frontmatter Sync

Belt-and-suspenders against the most common handoff-frontmatter drift: EMs sometimes mark work shipped with an inline `<!-- consumed: YYYY-MM-DD [notes] -->` body marker but forget to flip `status:` / `deployment_state:` in frontmatter. Step 1's `query-records` calls read frontmatter as authoritative, so unflipped records surface in `ready_to_fire` queries and waste triage attention.

```bash
node ~/.claude/plugins/coordinator/bin/normalize-consumed-frontmatter.js
```

Idempotent; prints a one-line no-drift notice to stderr when nothing changes. Each change line names the file and the field flips; if more than a handful surface, mention the count — recurring drift is a doctrine signal worth surfacing to the PM (consider `coordinator:learn-lessons` if it recurs across days). Scans handoffs + plans + decisions + reviews. Strips `gate_dependency:` on flipped records (only meaningful while `awaiting_gate`); preserves terminal states (`status: superseded`, `deployment_state: abandoned`).

## Step 0.8: Stale-Executing Plan Nudge

*Lesson 2026-05-16, project-rag — session-init orphan-sweep archives handoffs without running workstream-end ceremony.* When `session-init.sh` silently archives an orphaned handoff (consumed_by session died), the driving plan body in `docs/plans/` stays `status: executing` forever. Step 0.7 already flips frontmatter where consumed-markers exist; this step catches the inverse — plans whose handoff was silently archived without ceremony, or where the code landed on branch without the EM flipping the plan to `implemented`.

```bash
# Advisory: list plans with status:executing untouched >3 days (git mtime).
# Stale-executing = orphaned handoff or shipped work with unfipped plan.
stale_executing=$(
  for plan in docs/plans/*.md; do
    [[ -f "$plan" ]] || continue
    awk '/^---$/{n++; next} n==1' "$plan" 2>/dev/null \
      | grep -qE '^status:[[:space:]]*executing' || continue
    last_commit=$(git log -1 --format=%ct -- "$plan" 2>/dev/null)
    [[ -z "$last_commit" ]] && continue
    age_days=$(( ($(date +%s) - last_commit) / 86400 ))
    [[ "$age_days" -gt 3 ]] && echo "  - $plan (status: executing, untouched ${age_days}d)"
  done
)
if [[ -n "$stale_executing" ]]; then
  echo "Stale-executing plan advisory (status:executing untouched >3d — likely orphaned):"
  echo "$stale_executing"
  echo "Triage: flip to status:implemented, status:abandoned, or pick back up."
fi
```

Advisory only — never blocks the ceremony. Recurring entries across multiple `/workday-start` runs are the doctrine signal.

**Also read `tasks/orphan-sweep-notes.md` if present** — `session-init.sh` appends a line per orphan-archive event. Surface those alongside the stale-executing list in the Morning Briefing, then rotate the file:

```bash
# Header is 4 lines; ">4" means at least 1 event line is present.
# Rotation preserves the 4-line header so the next event lands on line 5.
if [[ -f tasks/orphan-sweep-notes.md ]] && [[ $(wc -l < tasks/orphan-sweep-notes.md) -gt 4 ]]; then
  echo "Orphan handoffs archived by session-init since last workday-start:"
  tail -n +5 tasks/orphan-sweep-notes.md
  head -n 4 tasks/orphan-sweep-notes.md > tasks/orphan-sweep-notes.md.new \
    && mv tasks/orphan-sweep-notes.md.new tasks/orphan-sweep-notes.md
fi
```

Non-empty on days when concurrent sessions died mid-pickup overnight.

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

Threshold: six days ≈ one working week — uncleared gates deserve a glance before they ossify.

### Step 1.3: Reconcile pending items against git (MANDATORY before declaring any item actionable)

Per-handoff in the `ready_to_fire` set: (a) `git log --oneline --since="<handoff-date>" --all` and scan subjects for matching pending items; (b) Read referenced plan/stub `**Status:**` fields; (c) drop confirmed-closed items from the actionable list, note as "verified-closed since handoff" in the report. Empirical baseline: 30–60% of inherited items are already closed. **Full procedure + rationale:** see `pipelines/workday-start-internals.md` § Step 1.

### Step 1.4: Cross-reference against completed archive (sanity check)

Query the completed archive for recent entries:
```bash
query-completions --where "created>=$(date -d '30 days ago' +%Y-%m-%d)" --sort "created" --format json
```

**Legacy fallback:** if `query-completions` returns empty AND `archive/completed/legacy/YYYY-MM.md` exists, read the legacy monolith for this reconciliation check only (read-only; no writes to the legacy path).

For each `ready_to_fire` handoff, check whether the work it describes appears as completed in the query results — match on workstream names, feature names, commit hashes, or distinctive keywords. If a match is found, flag it: _"Handoff [file] describes [work] — archive/completed shows this shipped on [date] (commit: [hash]). Likely already done — pick up to confirm and archive, or close out?"_

### Step 1.5: Report

_"{N} actionable handoffs ({K} continuations, {S} spinoffs incl. {R} roadmap stubs in {G} groups). {G} awaiting_gate (of which {M} >6 days) [if any]. {X} items verified-closed by git reconciliation."_ Omit any clause whose count is zero.

**Why query, not grep (doctrine reversal 2026-05-08, revised 2026-05-15):** `deployment_state` exists to obviate grep-walks. `ready_to_fire` for the primary list; `awaiting_gate` surfaces as its own subsection (count always, list when present) so cross-workstream gate awareness reaches the PM.

## Step 1.55: Recent Roadmap Orientation

Surface last quarter's top-10 roadmap completions by size for a 30-second narrative orientation — grounding the day's work in recent delivery context before triage decisions. Per `docs/wiki/orientation-surfacing-doctrine.md` count-always pattern: a fixed subsection heading renders regardless of row count.

```bash
bin/query-records --type completion --since "90d" --where "nature=roadmap" \
  --sort "-loe.tshirt" --limit 10 --format markdown-list
```

Render the results under a fixed subsection heading in the Morning Briefing (Step 5), inside the `### Handoffs` block:

```markdown
#### Recent roadmap (last 90d, top-10 by size)
<results — one bullet per row, or "(none)" when the query returns zero rows>
```

The `(none)` case is expected on brand-new or un-migrated repos. Surface the heading regardless — count-always. `bin/query-completions.sh` with equivalent flags is also accepted.

## Step 1.6: Coordinator-Improvement Queue Check

Read `~/.claude/tasks/coordinator-improvement-queue.md` (if it exists). Count `- ` lines in `## Active queue`; note the oldest date and any entries carrying `[recurring: ≥3]` on the main line (DR-056 amended 2026-05-17 — main-line-only schema).

Also read the local `tasks/improvement-queue.md` (if it exists in the current repo). Count its `## Active queue` entries.

Surface in the Morning Briefing when notable: central ≥ 5 entries, oldest >14 days, any `[recurring: ≥3]`, or local ≥ 1. EM advocates based on depth — judgment, not a threshold trigger. Skip silently when both queues are empty or absent.

## Step 1.65: Bug Backlog Depth Check

Read `tasks/bug-backlog.md` (if it exists). Count P1+P2 data rows (stop before `## Resolved`; exclude headers and separators). Surface in the Morning Briefing when ≥ 10: moderate (10–19) → `/bug-blitz` suggestion; heavy (≥ 20) → stronger nudge. Skip silently if absent or <10.

## Step 1.7: Scheduled Rechecks

Glob `tasks/cookbook-recheck-due-*.md`, `tasks/inspiration-recheck-due-*.md` (open-source comparison rechecks per `docs/wiki/opensource/`), `tasks/lesson-triage-recheck-due-*.md` (cross-project learn-lessons cadence per `coordinator:learn-lessons`), and `tasks/recheck-due-*.md` (general scheduled-recheck markers). Each marker filename ends in `-YYYY-MM-DD.md` indicating the due date.

For each marker found:
- **If today's date ≥ due date**, surface to the PM in the Morning Briefing's Priority Suggestions: _"Scheduled recheck due: `<filename>` (due {YYYY-MM-DD}). Procedure inside the file."_
- **If due date is within 7 days**, surface as a heads-up: _"Scheduled recheck upcoming: `<filename>` (due {YYYY-MM-DD}, in {N} days)."_
- **Otherwise**, skip silently.

If no marker files exist, skip silently. Do not auto-execute the recheck procedure — these markers are PM-actioned, not auto-dispatched.

## Step 1.8: Project-RAG Preamble Drift Check

Run `bin/verify-preamble-sync.sh` (relative to the coordinator plugin root, typically `~/.claude/plugins/coordinator/bin/verify-preamble-sync.sh`).

- **If no consumers found** (script exits 0 with "no consumers found" message): skip silently.
- **If all consumers OK** (exit 0, all lines show `OK`): skip silently.
- **If any MISMATCH or MISSING_END** (exit non-zero): surface to PM in the Morning Briefing under a new **Preamble Drift** line:

  _"project-rag-preamble drift detected in [N] consumer(s): [list files]. Run `bin/verify-preamble-sync.sh --fix` to repair, then commit all touched files together."_

**Do NOT auto-fix.** The EM should investigate which consumer drifted and why before applying `--fix`. A drift may indicate an intentional local edit that needs to be merged back into the canonical snippet rather than simply overwritten.

## Step 1.9: Auto-Push Failure Surface

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

## Step 1.10: Addon Health Sentinels

Plugins that ship a doctor skill write a sentinel at `~/.claude/plugins/<plugin>/data/doctor-last-run.json`. Run `bin/scan-addon-health.sh --red-and-stale` to surface RED + stale (>24h) verdicts; on non-empty output, render under a new `### Addon Health` section (between `### Auto-Push Health` and `### Priority Suggestions`); on empty, omit. Schema + EM dispatch flow: `docs/wiki/addon-health-sentinel.md`.

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
   find . \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.cpp" -o -name "*.h" -o -name "*.cs" -o -name "*.go" -o -name "*.rs" \) \
     | grep -v node_modules | grep -v __pycache__ | wc -l
   ```
   If >50 source files: _"No bug sweep has ever run on this codebase ([N] source files). Recommend running bug-sweep."_ If <50, skip silently.
3. If backlog exists, count commits since the sweep's anchor commit:
   ```bash
   git rev-list --count <sweep-commit>..HEAD
   ```
4. **Suggest sweep if:**
   - >50 commits since last sweep AND >7 days since last sweep (significant churn with time floor — prevents nagging during sprint-mode work), OR
   - >14 days since last sweep AND >20 commits since last sweep (moderate churn + time)
   - _"Bug sweep last ran [date] ([N] commits ago). Recommend running bug-sweep before new feature work."_
5. If few commits since last sweep: "Bug sweep is current ([N] commits since last sweep)."

**The trigger is churn, not calendar** — wait the 7-day floor to avoid suggestion fatigue during sprint-mode work.

## Step 3.6: Project-RAG Staleness (conditional)

**Skip silently** if `ToolSearch` finds no `mcp__project-rag__*` tool — same gate pattern as `session-start.md`. Coordinator does not depend on project-rag; it only adapts when present.

When present:

1. Resolve the registered project root from `~/.claude.json`:
   ```bash
   python -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude.json'))); print(d['mcpServers']['project-rag']['args'][-1])"
   ```
   Returns the `--project-root` value passed to the MCP server boot.

2. Locate the plugin's cli.py via `~/.claude.json` → `mcpServers.project-rag.args` (script path; same parse as step 1).

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
bash plugins/coordinator/bin/whats-next.sh
```

The script emits three sections: improvement-queue head (top 5 entries), `docs/project-tracker.md` rows with status Ready or Executing, and open handoffs (filename + line-1 heading). Use as-is — frame for the PM under § Priority Suggestions; do not reconstruct from prose.

**Reconcile active work against completed archive:** Run `query-completions --where "created>=$(date -d '30 days ago' +%Y-%m-%d)" --sort "created" --format json` (or fall back to `archive/completed/legacy/YYYY-MM.md` if query returns empty and the legacy monolith exists). Cross-reference tracker Ready/Executing items and open handoffs against the completed archive:
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

### Branch Span Mismatch
_(Omit this section entirely unless Step 0.45's `$SPAN_ASSERT_FAIL` was set. When present, render `$SPAN_ASSERT_MSG` verbatim — this is the loudest tripwire in the briefing and PM should see it first.)_

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
Check PATH for `scc` (also `~/bin/scc`) and `shellcheck`. Surface install hint for each missing tool (`winget install BenBoyter.scc` / `winget install koalaman.shellcheck`). When both present: _"Tools: scc + shellcheck available."_ Only nag when missing.

### Handoffs
- **Continuation:** [N active, M aging, K likely-consumed]
- **Spinoffs awaiting pickup:** [list each: filename — title — age — workstream]
  _(Omit this bullet if no spinoffs exist.)_
- **Stale spinoffs (≥14 days):** [list each with a one-line nudge]
  _(Omit this bullet if no stale spinoffs exist.)_

#### Recent roadmap (last 90d, top-10 by size)
_(Results from Step 1.55 query — one bullet per row. Render "(none)" when the query returns zero rows. Heading always present — count-always per orientation-surfacing-doctrine.)_

### Alignment Check
- [N mismatches found between active trackers and completed archive / all aligned]
- [List each mismatch: "Tracker: X is Executing — Archive: shipped YYYY-MM-DD"]
- [List each handoff flagged as likely completed]

### Orphan Sweep / Agent Worktrees / Auto-Push Health / Addon Health
Each section omitted unless its step (0.5 / 0.6 / 1.9 / 1.10) produced surfaceable findings; render only the non-empty rows from that step's structured output.

### Priority Suggestions
Pull from the active state: bugs (top severity first), stale sweep, stale tests, stale atlas, tracker Ready rows, deep debt backlog. Order by urgency, not by template.

### What should today's focus be?
[Surface tracker Ready items, handoff action items, and PM-facing options]
```

**Set marker:** Write `tasks/.workday-start-marker` with today's date (single line). Session-start checks this one file.

## Step 5.5: Write Orientation Cache

Generate `tasks/orientation_cache.md` — a compact 40-60 line summary the SessionStart hook injects instead of raw repomap/DIRECTORY content. Skip if `tasks/` doesn't exist. Health Snapshot includes a Step-1 mirrored split: one line for continuation handoffs, a separate line for spinoffs (omitted if N=0).

**Full content derivation per section:** see `pipelines/workday-start-internals.md` § Step 5.5.

## What This Does NOT Do

- Run bug-sweep / daily-code-health / deep-architecture-audit / update-docs — those are dedicated invocations (PM, /workday-complete, monthly, manual after this completes respectively).
- Merge to main — use `/merge-to-main`.
- Choose work — that's session-start's Engage section.

## Relationship to Other Commands

`workday-start` runs once/day; `session-start` runs per-session (many/day) and skips redundant checks when the marker is fresh. `/workday-complete` is the evening counterpart. `/update-docs` and `/bug-sweep` are recommended (not dispatched) when state warrants.

## Concurrent Session Safety

Read-only for all tracking files; writes only `tasks/.workday-start-marker` (date string, no merge-conflict risk). Failure mode to avoid: acting on stale handoff items a concurrent session already shipped — Step 1.3's git reconciliation is the prevention.

If `$ARGUMENTS` is provided, include as a focus hint in the Briefing: _"Requested focus: {arguments}"_
