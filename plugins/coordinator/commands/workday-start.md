---
description: Morning orientation — triage handoffs, surface staleness, align priorities
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

Prepare the day's session-start calls to be maximally efficient. Ensure context is fresh, priorities are clear, and any overnight health findings are surfaced.

**Announce at start:** "I'm running workday-start to prepare the day's context."

## Step 0: Branch Setup

Ensure all work today happens on a proper work branch, and consolidate any lingering open branches from previous days.

1. **Determine today's work branch name:**
   - Machine name: run `hostname` and lowercase it.
   - Today's branch: `work/{machine}/{YYYY-MM-DD}`

2. **If already on today's work branch:** Skip to Step 1.

3. **Find open (unmerged) work branches owned by this user** — branches that have diverged from main but haven't been merged, scoped to the current git user's machine name:
   ```bash
   git branch --list "work/{machine}/*" --no-merged main
   ```
   Use the same `{machine}` derived in step 1 (the current machine's hostname, lowercased). This scopes consolidation to branches owned by this user on this machine — collaborators' `work/{their-machine}/*` branches are never touched.

   Exclude today's branch name from the result list.

4. **Create (or checkout) today's branch:**
   - If the branch doesn't exist: `git checkout -b work/{machine}/{YYYY-MM-DD}`
   - If it already exists locally: `git checkout work/{machine}/{YYYY-MM-DD}`
   - If name collides with an already-merged branch, append suffix: `work/{machine}/{YYYY-MM-DD}-2`

5. **Consolidate open branches** — for each branch found in step 3:
   ```bash
   git merge {branch-name} --no-ff -m "consolidate {branch-name} into today's work branch"
   ```
   - If merge succeeds cleanly: proceed to the next branch.
   - If merge conflict: **stop immediately.** Abort the merge: `git merge --abort`. Report: _"Merge conflict consolidating {branch-name} — manual resolution required. Continuing workday-start without consolidating this branch."_ Do not attempt to resolve the conflict automatically.
   - After all merges: the old branches remain as refs (do not delete them — the PM may want to inspect them).

6. **Push today's branch to establish remote tracking:**
   ```bash
   git push -u origin work/{machine}/{YYYY-MM-DD}
   ```

7. **Report:**
   - If consolidation happened: _"On branch {today-branch}. Consolidated N open branches: {list}."_
   - If nothing to consolidate: _"On branch {today-branch}. No open work branches to consolidate."_
   - If any conflicts blocked consolidation: flag them clearly.

**Why this matters:** Without this step, sessions can pile up unmerged work branches indefinitely. The daily consolidation keeps branch history clean and surfaces any accumulated divergence early — before it becomes a merge nightmare.

## Step 1: Handoff Triage

Read all files in `tasks/handoffs/`. For each:

1. **Check age** — filename includes timestamp (`YYYY-MM-DD_HHMMSS_sessionid.md`)
2. **Check branch activity** — is the handoff's referenced branch still active? Any commits since the handoff was written?
3. **Categorize** each handoff:
   - **Active** — has recent branch activity, or references open/in-progress work
   - **Aging** — older, no branch activity, but not explicitly consumed
   - **Likely consumed** — work appears in the completed archive (cross-reference below)
4. **Surface everything, archive nothing.** Report all handoffs to the PM with their status. Handoff archival happens only when a handoff is explicitly consumed (via `/pickup`) or the PM directs it — never automatically based on age.
5. **Cross-reference against completed archive:** Read `archive/completed/YYYY-MM.md` (current month, plus previous month if within the first 7 days). For each handoff, check whether the work it describes appears in the completed archive — match on workstream names, feature names, commit hashes, or distinctive keywords. If a match is found, flag it: _"Handoff [file] describes [work] — archive/completed shows this shipped on [date] (commit: [hash]). Likely consumed — archive it?"_
6. **Report:** "N active handoffs. M aging (no recent activity). K appear already completed per archive — ask PM about archival."

**Why surface-only:** Handoffs are archived only when consumed (`/pickup` marks them) or when the PM explicitly directs archival. An old handoff that nobody picked up is a signal that work was deferred — not that the handoff is stale. workday-start surfaces the state; the PM decides what to do about it.

**Why cross-reference completed archive:** Handoffs describe *intended* next steps. The completed archive records *outcomes*. A handoff can remain active even after the work it describes has shipped — especially when a different session completed the work without consuming the handoff. The cross-reference catches this, but the PM confirms before archival.

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

**Skip silently** if `ToolSearch` does not find any `mcp__holodeck-project-rag__*`
tool. This is the same gate pattern used in Step (project-rag block) of
`session-start.md` — coordinator does not depend on the project-rag plugin; it
only adapts when the plugin is present. No warning emitted on skip.

When present:

1. Resolve the registered project root from `~/.claude.json`:
   ```bash
   python -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude.json'))); print(d['mcpServers']['holodeck-project-rag']['args'][-1])"
   ```
   This returns the `--project-root` value passed to the MCP server boot.

2. Locate the holodeck-project-rag plugin's cli.py. The path is recorded in
   `~/.claude.json` → `mcpServers.holodeck-project-rag.args` (the script path).
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

Surface the project's current state and help align on today's focus:

1. Read `docs/project-tracker.md` (if exists):
   - Active workstreams and their statuses
   - Items that are Ready or Executing
   - Blocked items and their blockers
2. Read `ACTION-ITEMS.md` or equivalent (if exists):
   - Outstanding action items
3. Read `tasks/health-ledger.md` (if exists):
   - Systems at ACTION/CRITICAL status
   - Overdue audits
4. Read `tasks/bug-backlog.md` (if exists):
   - Open bug count and severity distribution
5. Read `tasks/debt-backlog.md` (if exists):
   - Open debt count
6. Read `tasks/architecture-atlas/systems-index.md` (if exists):
   - Number of mapped systems
   - Any systems with `last_mapped` date >90 days ago (stale)
   - If file doesn't exist: note "no atlas" for the report
7. **Reconcile active work against completed archive:** Read `archive/completed/YYYY-MM.md` (current month + previous month if within first 7 days). Cross-reference:
   - **Tracker items** marked Ready/Executing/In Progress → do any match completed archive entries? If so, flag: _"Tracker shows [workstream] as [status], but archive/completed records it shipped on [date]."_
   - **Action items** still listed as open → do any match completed entries? Flag the same way.
   - **Bug/debt backlog items** still open → do any match entries in the archive marked as fixes?
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

### Alignment Check
- [N mismatches found between active trackers and completed archive / all aligned]
- [List each mismatch: "Tracker: X is Executing — Archive: shipped YYYY-MM-DD"]
- [List each handoff flagged as likely completed]

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

Generate `tasks/orientation_cache.md` — a compact summary for the SessionStart hook to inject in subsequent sessions instead of raw repomap/DIRECTORY content.

**Content derivation:**
1. **Key Documentation:** If `docs/README.md` exists, include a `## Key Documentation` section:
   ```
   ## Key Documentation
   - **Master docs index:** [`docs/README.md`](../docs/README.md) — wikis, research, specs, plans, reference
   - **Wiki guides:** [`docs/guides/`](../docs/guides/) — [N] living guides with embedded decision records
   - **Research outputs:** [`docs/research/`](../docs/research/) — [N] timestamped research files
   - **Plans:** [`docs/plans/`](../docs/plans/) — [N] implementation and design plans
   ```
   Count the files in each directory. If `docs/guides/DIRECTORY_GUIDE.md` exists, reference it. If `docs/README.md` does NOT exist, note: _"No docs/README.md — run `/update-docs` or `/project-onboarding` to create one."_
2. **Structure:** Read `tasks/repomap.md`, extract top 15 entries by rank. Note total file count.
3. **Navigation:** Read `DIRECTORY.md` or `docs/DIRECTORY.md`, summarize at directory level (directory name + file count + purpose).
4. **Code Statistics:** Run `scc --no-complexity --no-cocomo --no-duplicates --sort code` (if scc is available). Include a compact summary: total lines of code, top 5 languages with line counts. This calibrates session agents on project scale. If scc is not installed, skip silently — `~/bin/scc` is the conventional install path on Windows.
5. **Health Snapshot:** Compact version of the Morning Briefing's health data (already in context from Steps 3-4).
6. **Doc Inventory:** Checklist of standard docs (already checked in Step 2).
7. **Staleness markers:** Repomap age, last update-docs run (already checked in Step 2).
8. **Yesterday's Strategic Review:** Read the most recent file in `archive/daily-summaries/` (glob for `YYYY-MM-DD.md`, sort descending, take first). If a daily summary exists and has a `## Strategic Review` section, extract a 3-5 line excerpt covering the key alignment findings, debt items, and bridging opportunities. Include as a `## Yesterday` section in the orientation cache. This gives every subsequent session automatic strategic context without reading a separate file. If no daily summaries exist, skip silently.

**Frontmatter:** Include `generated_by`, `generated_at` (ISO 8601), `git_head_at_generation` (current HEAD short hash).

**Target: 40-60 lines.** This replaces ~300 lines of raw hook injection for subsequent sessions.

**If `tasks/` directory doesn't exist:** Skip. Not all repos use `tasks/`.

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

If `$ARGUMENTS` is provided, include it as a focus hint in the Morning Briefing: _"Requested focus: {arguments}"_
