---
name: workday-complete
description: End-of-day orchestration — validate, consolidate branches, daily review, append to week-changelog
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Lightweight daily wrap: validate, consolidate branches, run the strategic daily review, append to the week-changelog, and surface staleness signals. **Does NOT merge to main.** Heavy ceremony (docs sweep, ShellCheck, improvement-queue triage) is weekly — see `/workweek-complete`.

## Design Rationale

Daily is a branch wrap, not a release ceremony. Handoffs archive at their natural trigger; the tracker is touched when the work touches it. The changelog append converts "weekly EM does archaeology" into "weekly EM reads a structured ledger."

---

## Step 0: Pre-stage Validator Suite (blocking gate)

Run all pre-stage validators before any staging or git operations. These validators must pass before the workday-complete ceremony proceeds. A failure here means something in the codebase is out of spec — fix it before committing.

### 0a: UE override drift check

```bash
# verify-ue-overrides.sh created by Phase B; if not yet present, skip 0a and run Phase B first
${CLAUDE_PLUGIN_ROOT}/bin/verify-ue-overrides.sh
```

- **Exit 0:** all known UE-context dirs carry the expected override — proceed.
- **Exit 1:** one or more dirs are missing the UE plugin override. Run `${CLAUDE_PLUGIN_ROOT}/bin/claude-ue-bootstrap.sh <dir>` for each flagged dir, then re-run the check before continuing.

### 0b: Skill description length check

```bash
${CLAUDE_PLUGIN_ROOT}/bin/check-description-length.sh
```

- **Exit 0:** all skill descriptions are within their per-skill budget (see `description-budget:` frontmatter field, or ≤175 PM-gated, or ≤150 default) — proceed.
- **Exit 1:** one or more skill descriptions exceed the limit. Fix the failing SKILL.md file(s) before proceeding. Do NOT continue to Step 1 until this passes.

Both validators must exit 0. A partial pass (one OK, one failing) still blocks.

---

### 0c: UBT pending-record resolution (UE plugin work only)

If `bin/check-ubt-build-fresh.sh` exists in the cwd, scan `tasks/review-trail/` for `*.ubt-compile.pending.json` records that have NO corresponding `*.ubt-compile.resolved.json` sibling. For each unresolved pair, run the UBT build (via the script) and write a new resolved record. Exit non-zero if any record resolves to `verdict=blocked` — this is a **blocking gate**.

```bash
[ -x bin/check-ubt-build-fresh.sh ] && \
  bin/check-ubt-build-fresh.sh --since HEAD --mode resolve
```

- **Exit 0 (no pending records, or all resolved to ok):** proceed.
- **Exit 1 (one or more resolved to blocked):** halt and report. Fix the C++ compile error, then run `/workday-complete` again. Override with `COORDINATOR_OVERRIDE_UBT_GATE=1` only when the PM explicitly authorises bypassing the gate.
- **Script absent:** skip silently (non-UE repos see no change). Uses `[ -x bin/<name>.sh ]` presence-detection per the convention established in `/session-end` Step 2.9.

---

## Step 1: `/validate` (blocking gate)

```bash
python .github/scripts/run-all-checks.py
```

Capture the exit code — it populates `Validation:` in the changelog block.

- **Build failure:** stop and fix.
- **Non-build failure:** fix what's quick, flag the rest, proceed.

---

## Step 2: RAG Staleness Nudge (informational)

If `ToolSearch` finds any `mcp__project-rag__*` tool, run the staleness survey. Surface in the final summary only if verdict is `stale` or `very-stale`. Skip silently otherwise.

---

## Step 3: Branch Consolidation

<!-- Phase 5 F2: recompute MACHINE lowercase via cs_compute_machine + grep -iE for case-insensitive
     legacy-branch tolerance. Span branches (work/striker/2026-05-06to07) must also be discovered. -->
0. `~/.claude/plugins/coordinator-claude/coordinator/bin/sync-main.sh` — non-zero exit → report and stop.
1. Recompute machine name lowercase for this step (the Staff Engineer F2 — do not rely on inherited shell scope):
   ```bash
   TODAY=$(date +%Y-%m-%d)
   _LIB="$HOME/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-daily-branch.sh"
   if [[ -f "$_LIB" ]]; then
     # shellcheck source=/dev/null
     source "$_LIB"
     MACHINE=$(cs_compute_machine)
   else
     MACHINE=$(hostname | tr '[:upper:]' '[:lower:]' | tr ' .' '-' | tr -cd 'a-z0-9-')
   fi
   ```
2. Discover active workstream branches — case-insensitive to catch both legacy `work/STRIKER/...` and
   new `work/striker/...` branches, as well as span-form `work/striker/2026-05-06to07`:
   ```bash
   git branch --list | grep -iE "^\*? *work/$MACHINE/$TODAY"
   ```
3. Merge siblings into current branch. Non-trivial conflicts → report and halt.
4. Rebase on `origin/main`; fall back to merge if rebase fails with non-trivial conflicts.
5. `git push origin $(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch) --force-with-lease` — on rejection, fetch-rebase-retry once; second failure → report to PM.
6. Delete merged sibling branches:
   ```bash
   git branch --merged | grep -iE "work/$MACHINE/$TODAY" | grep -v "$(git branch --show-current)" | xargs -r git branch -d
   ```

Feature branches are excluded — they are intentionally long-lived.

---

## Step 4: Strategic Daily Review

Produce `archive/daily-summaries/YYYY-MM-DD.md`. Heavy-weight templates, the failure-mode table,
health-ledger schema, and debt-backlog DSR-ID format live in
`docs/wiki/daily-summary-procedure.md` (plugin-relative) — walk that wiki for detail; do not
re-author it inline.

**Skip condition:** zero new commits AND no agent-driven changes outside commits → write a one-line
summary noting "no work today" and skip Steps 4b–4e.

### Step 4a: Inventory Generation

```bash
mkdir -p tasks/daily-review-scratch
bash "${CLAUDE_PLUGIN_ROOT}/coordinator/bin/standup.sh" > tasks/daily-review-scratch/inventory.md
```

The script emits: baseline SHA/timestamp, commit inventory, file-change summary by directory,
touched handoffs, touched todos, active handoffs.

### Step 4b: Analyst Dispatch

Dispatch a **Sonnet** analyst agent (`model: "sonnet"`, `run_in_background: true`).

Full prompt template: `docs/wiki/daily-summary-procedure.md` § Sonnet Analyst Prompt Template.
Summary of what the analyst does:
1. Reads `tasks/daily-review-scratch/inventory.md`.
2. Reads `git diff <baseline>..HEAD` (targeted reads if diff >3000 lines).
3. Reads commit messages and any referenced plan docs.
4. Writes `archive/daily-summaries/YYYY-MM-DD.md` — Work Completed, Systems Affected,
   Architectural Decisions sections. Creates the directory if needed.

Wait for the analyst to complete before Step 4c.

### Step 4c: Reviewer Dispatch

Route to a reviewer based on the dominant domain of today's work. Full routing table:
`docs/wiki/daily-summary-procedure.md` § Routing Table.

Quick reference:

| Dominant change type | Reviewer |
|---|---|
| Game dev / Unreal Engine | the Game Dev Reviewer |
| Frontend / UI | Palí |
| Data / ML / science | the Data Science Reviewer |
| Mixed, backend, or architecture | the Staff Engineer |

Dispatch the selected reviewer as a **Sonnet** agent.

Full prompt template: `docs/wiki/daily-summary-procedure.md` § Sonnet Reviewer Prompt Template.
The reviewer appends a `## Strategic Review` section to the daily summary and optionally adds
rows to `tasks/debt-backlog.md` (DSR-{date}-{N} format — see wiki for schema).

### Step 4d: Health Ledger Update

After the reviewer completes:
1. Read `tasks/health-ledger.md`. If missing, create from schema in
   `docs/wiki/daily-summary-procedure.md` § Health Ledger Entry Schema.
2. Update `Last daily check` to today's date.
3. Update grades for any system flagged by the reviewer; add new rows (grade `?`) for systems
   touched by commits that have no row yet.

### Step 4e: No Commit Here

Do **not** commit in Step 4. Step 9 stages and commits `archive/daily-summaries/YYYY-MM-DD.md`
alongside the changelog row.

### Step 4f: Clean Scratch

```bash
rm -rf tasks/daily-review-scratch
```

---

## Step 5: Plugin Validation Suite (blocking gate)

```bash
node --test ~/.claude/tests/plugins/run.js
```

Capture exit code for the changelog `Validation:` field.

- **Hook-behavior failures:** blocking — stop and fix.
- **Non-hook failures:** report in summary, flag for morning, do not block git steps.
- **Calibration-sync sentinel:** informational unless Borrow #5 has fully landed.

---

## Step 6: Completed Archive Audit

1. `git log --oneline --since="$TODAY 00:00" --until="$TODAY 23:59"` — gather today's commits.
2. Read `archive/completed/YYYY-MM.md`; find entries under today's heading.
3. Reconcile: add missing entries, fix inaccurate ones, skip trivial commits.
4. If `docs/project-tracker.md` exists, verify completed workstreams have updated status.
5. Report: _"Archive audit: N entries verified, M added, K corrected."_

---

## Step 7: Tier Usage Report

```bash
find "${HOME}/.claude/projects" -name "*.json" -path "*/tier-usage/*" 2>/dev/null | \
while read -r f; do cat "$f"; done | \
python3 -c "
import json, sys
totals = {'tier1': 0, 'tier2': 0, 'tier3': 0, 'tier4': 0}
missing_rationale = 0; sessions = 0
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        data = json.loads(line)
        c = data.get('counts', {})
        for k in totals: totals[k] += c.get(k, 0)
        missing_rationale += sum(1 for d in data.get('tier4_dispatches', []) if not d.get('rationale_present', True))
        sessions += 1
    except Exception: pass
if sessions > 0:
    print(f'Tier usage today ({sessions} sessions): tier1={totals[\"tier1\"]} tier2={totals[\"tier2\"]} tier3={totals[\"tier3\"]} tier4={totals[\"tier4\"]} ({missing_rationale} tier-4 missing rationale)')
" 2>/dev/null || true
```

Skip silently if no tier-usage files exist.

---

## Step 8: Improvement-Queue Depth Nudge (read-only)

Read `~/.claude/tasks/coordinator-improvement-queue.md`. Count `- ` lines in `## Active queue`.

- **≥ 5 entries:** emit in final summary: _"Coordinator-improvement queue: K entries (oldest: YYYY-MM-DD) — consider `/workweek-complete` to triage."_
- **Otherwise:** skip silently.

No triage action at daily cadence — triage is weekly.

---

## Step 9: Append to Week-Changelog

```bash
MACHINE=$(hostname | tr '[:upper:]' '[:lower:]' | tr ' .' '-' | tr -cd 'a-z0-9-')
TODAY=$(date +%Y-%m-%d)
CHANGELOG_FILE="tasks/week-changelog/$TODAY-$MACHINE.md"
```

**Staleness guard:** read `tasks/week-changelog/HEADER.md`. If `Week starting:` is set and today is >14 days past it, emit a hard warning and skip the append:
> "WARN: HEADER.md is stale (week started >14 days ago). Was `/workweek-complete` skipped?"

**Synthesise the block** from today's handoffs (`tasks/handoffs/YYYY-MM-DD-*.md`) and the Step 4
daily summary (`archive/daily-summaries/YYYY-MM-DD.md`). Extract `Decisions:` and `Blockers:`
from handoff content — do NOT re-author them. `Validation:` is auto-filled from Steps 1 and 5
exit codes — it is not LLM-authored prose.

**`Reviewed:` field** — read all `tasks/review-trail/*.json` files whose filename begins with today's date (`YYYY-MM-DD-*`). For each record, emit one line:
```
**Reviewed:** sha_range=<sha_range> reviewer=<reviewer> verdict=<verdict> diff_loc=<diff_loc>
```
Multiple records produce multiple `**Reviewed:**` lines — one per record. If today had non-trivial commits (any commit subject NOT matching `^(chore|docs?)([(:]|$)|^session-end quick-save`) AND no review-trail records for today exist, emit exactly one fallback line:
<!-- Review: the Staff Engineer — previous regex ^chore|^doc|^session-end quick-save matched
     "docker:" and "chored" as trivial; tightened to require conventional-commits
     punctuation after chore/doc(s) or an exact prefix match. -->
```
**Reviewed:** none — flag for /workweek-complete Step 7
```
If today's commits are all trivial AND no records exist, omit the `**Reviewed:**` field entirely — do not emit an empty line.

```markdown
## YYYY-MM-DD — {hostname}

**Branch:** work/{hostname}/YYYY-MM-DD
**Commits:** N (range: <oldest-sha>..<newest-sha>)
**Scope:** <one-line summary from $ARGUMENTS or derived from commit subjects>
**Plans touched:** docs/plans/YYYY-MM-DD-foo.md (status: in-progress|shipped|reverted)
**Handoffs:** tasks/handoffs/YYYY-MM-DD-foo.md
**Decisions:** <extracted from today's handoffs — not re-authored>
**Blockers:** <extracted from handoffs, or "none">
**Validation:** validate=<exit-code-step-1> plugin-suite=<exit-code-step-5>
**Reviewed:** sha_range=<sha_range> reviewer=<reviewer> verdict=<verdict> diff_loc=<diff_loc>
**Links:** archive/daily-summaries/YYYY-MM-DD.md, archive/completed/YYYY-MM.md
```

Commit and push — include the daily summary artifact alongside the changelog row:
```bash
git add -- "$CHANGELOG_FILE" "archive/daily-summaries/$TODAY.md"
git commit -m "chore(week-changelog): daily block $TODAY $MACHINE"
git push origin $(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)
```

---

## Step 10: Weekly Staleness Check

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/check-weekly-staleness.sh
```

- **STALE:** _"Weekly is stale: D days, N commits since last `/workweek-complete`. Run it when ready."_
- **MILD:** _"Weekly cadence: mild staleness. Consider `/workweek-complete` soon."_
- **FRESH / UNKNOWN:** skip silently.

---

## Step 11: Final Summary

```
## Workday Complete

**Validation:** [N checks passed / N failed]
**Branches consolidated:** [N merged into current]
**Branch state:** [branch name], rebased on main, pushed
**Daily review:** [produced archive/daily-summaries/YYYY-MM-DD.md]
**Plugin validation:** [N tests passed / N failures]
**Archive audit:** [N verified, M added, K corrected]
**Week-changelog:** [appended YYYY-MM-DD-{hostname}.md / skipped: reason]
**Weekly staleness:** [STALE / MILD / FRESH]
**NOT merged to main** — use `/merge-to-main` when ready
```

If `$ARGUMENTS` is provided, include as a top line: _"Day summary: {arguments}"_

---

### What This Does NOT Do

- **Merge to main.** Use `/merge-to-main` — it runs the test suite first.
- **Run `/update-docs`.** Weekly cadence only — via `/workweek-complete`.
- **Triage the improvement queue.** Daily depth nudge only; triage is weekly.
- **Run ShellCheck or scc stats.** All moved to `/workweek-complete`.
- **Delete the work branch.** Stays alive for morning review.
- **Delete handoffs.** workday-complete does not delete handoffs. Lifecycle (revised 2026-05-08): `/pickup` archives them atomically (`tasks/handoffs/` → `archive/handoffs/`); `/distill` deletes from the archive after extraction (opt-out via `--no-delete`), gated by extraction-artifact + `shipped_in:` + active-reference + distillation-log guards. Spec: `docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` § Phase 4.

### Concurrent Session Safety

Per-machine files under `tasks/week-changelog/` eliminate concurrent-write conflicts. HEADER.md is touched only by the two weekly commands (PM-invoked, serial). Health files are global — workday-complete is the single daily writer.

> **Force-with-lease rejection (Step 3):** fetch-rebase-retry once. Second failure → report to PM.

### Relationship to Other Commands

- **`/merge-to-main`** — deliberate supervised merge; run in the morning.
- **`archive/daily-summaries/YYYY-MM-DD.md`** — produced by Step 4; feeds Step 9 synthesis.
- **`/workweek-complete`** — weekly release ceremony: docs sweep, ShellCheck, triage, version bump, merge.
- **`/workweek-start`** — PM-facing weekly orient; sets priorities in HEADER.md.
