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

## Step 1: `/validate` (blocking gate)

### Step 1 preamble: UBT Pending-Record Resolution (UE work only)

If `bin/check-ubt-build-fresh.sh` exists in the cwd, scan `tasks/review-trail/` for `*.ubt-compile.pending.json` records that have NO corresponding `*.ubt-compile.resolved.json` sibling. For each unresolved pair, run the UBT build (via the script) and write a new resolved record. Exit non-zero if any record resolves to `verdict=blocked` — this is a **blocking gate**. Non-UE repos see no change (script absent → silent skip).

```bash
[ -x bin/check-ubt-build-fresh.sh ] && \
  bin/check-ubt-build-fresh.sh --since HEAD --mode resolve
```

- **Exit 0 (no pending records, or all resolved to ok):** proceed.
- **Exit 1 (one or more resolved to blocked):** halt and report. Fix the C++ compile error, then run `/workday-complete` again. Override with `COORDINATOR_OVERRIDE_UBT_GATE=1` only when the PM explicitly authorises bypassing the gate.
- **Script absent:** skip silently. Uses `[ -x bin/<name>.sh ]` presence-detection per the convention established in `/session-end` Step 2.9.

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
0. `~/.claude/plugins/coordinator/bin/sync-main.sh` — non-zero exit → report and stop.
1. Recompute machine name lowercase for this step (Patrik F2 — do not rely on inherited shell scope):
   ```bash
   TODAY=$(date +%Y-%m-%d)
   _LIB="$HOME/.claude/plugins/coordinator/lib/coordinator-daily-branch.sh"
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
4. Reconcile with `origin/main`:
   ```bash
   # Precondition: Step 3 sub-step 0 (sync-main.sh) MUST have run before this
   # block — it fetches origin/main, ensuring rev-list operates on a fresh ref.
   # Without that fetch, the behind-check may spuriously claim "already current"
   # when origin has moved.

   # Guard: origin/main missing (fresh clone, network issue, renamed remote).
   # rev-list against a missing ref errors to stderr + empty stdout → falls
   # through to rebase with an opaque "unknown revision" failure.
   if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
     echo "origin/main not present locally — skipping reconcile step"
   # Skip rebase if HEAD already contains origin/main (ahead-only state).
   # Blind rebase in this state walks back through merge commits and replays
   # them needlessly — see 2026-05-15 session evidence (645 ahead / 0 behind
   # triggered a full replay with nothing to integrate).
   elif [[ "$(git rev-list --count HEAD..origin/main)" == "0" ]]; then
     echo "branch already contains origin/main — no rebase needed"
   else
     git rebase origin/main || git merge origin/main  # fallback on non-trivial conflicts
   fi
   ```
5. `git push origin $(~/.claude/plugins/coordinator/bin/coordinator-current-branch) --force-with-lease` — on rejection, fetch-rebase-retry once; second failure → report to PM.
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

Also query today's completion entries and write to scratch for analyst use:

```bash
TODAY=$(date +%Y-%m-%d)
query-completions --where "created=$TODAY" --format json \
  > tasks/daily-review-scratch/completions-today.json
```

The analyst reads `completions-today.json` alongside `inventory.md` — completion entries are the
primary source for the **Work Completed** section of the daily summary. `git log` scanning is
**deprecated** as the primary source; use it only to catch work that predates the completion-log
schema (pre-Chunk-1 sessions) by checking if `completions-today.json` is empty.

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
| Game dev / Unreal Engine | Sid |
| Frontend / UI | Palí |
| Data / ML / science | Camelia |
| Mixed, backend, or architecture | Patrik |

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

## Step 4.5: Completion-Log Clustering Pass

<!-- Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 4 -->

Groups today's completion entries by `chain:` field and synthesizes a machine-readable `narrative:`
for each multi-entry chain. Single-entry chains are left as-is (title + body suffice). This pass
is idempotent — re-running on an already-clustered day is a no-op.

**Purpose:** enables `/workweek-complete` editorial bucketing to read `narrative:` fields rather
than re-deriving contribution summaries from raw entries.

### Step 4.5a: Query and Group

```bash
TODAY=$(date +%Y-%m-%d)
query-completions --where "created=$TODAY" --format json > /tmp/completions-cluster-$TODAY.json
```

Parse the JSON output. Group entries by their `chain:` field value. Entries with no `chain:` field
(or `chain: ""`) form singleton groups — skip them in Step 4.5b.

### Step 4.5b: Synthesize Narratives for Multi-Entry Chains

For each `chain:` group with **≥ 2 entries**:

1. **Identify the lead entry** — lexicographically first file path in the chain (e.g.,
   `archive/completions/2026-05-19/chunk-1a.md` sorts before `archive/completions/2026-05-19/chunk-1b.md`).

2. **Idempotency check** — read the lead entry's frontmatter. If `narrative:` is already present
   AND the `body:` field of no entry in the chain has changed since `narrative:` was written,
   **skip this chain** (no-op).

3. **Dispatch a Sonnet `general-purpose` worker** (≤2KB output) with this prompt (inline — no
   subagent skill expansion):

   > You are synthesizing the contribution narrative for a completion-log chain.
   >
   > Chain entries (JSON):
   > `<paste chain entries JSON>`
   >
   > Write ONE paragraph (3–6 sentences) summarizing the chain's combined contribution for the day.
   > Rules:
   > - Preserve commit SHAs verbatim when referenced.
   > - No editorial bucketing (Features / Fixes / etc.) — that is `/workweek-complete`'s job.
   > - Describe what was built/fixed/changed and why it matters to the workstream.
   > - Keep it ≤300 words.
   >
   > Reply with ONLY the paragraph text. No preamble.

4. **Write the result** — using `Edit` on the lead entry's file, insert `narrative: |` as a
   new YAML frontmatter field with the worker's paragraph as its block-scalar value.

5. **Mark non-lead entries** — for each non-lead entry in the chain, insert
   `narrative_in: <path-to-lead-entry>` into its frontmatter. Skip if already present.

### Step 4.5c: Single-Entry Chains

Skip — no narrative synthesis needed. The entry's own `title:` and `body:` are the record.

### Step 4.5d: Idempotency Guarantee

Re-running Step 4.5 on the same day:
- Chains where every entry's `narrative:` / `narrative_in:` is already set AND no `body:`
  has changed → **all skipped** (zero writes, zero dispatches).
- Chains where a `body:` changed since the last run → narrative re-synthesized (worker
  dispatched, lead entry overwritten).

### Step 4.5e: No Commit Here

Do **not** commit in Step 4.5. The completion-entry files are committed by Step 9 alongside the
changelog row.

**AC verification:** on a day with 5 entries across 2 chains (e.g., chain A has 3 entries, chain B
has 2 entries), Step 4.5 dispatches 2 Sonnet workers and writes 2 `narrative:` fields (one per
lead entry) plus 3 `narrative_in:` back-references (2 for chain A non-leads, 1 for chain B
non-lead). Running Step 4.5 again immediately afterward is a no-op (0 dispatches, 0 writes).

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
2. `query-completions --where "created=$TODAY" --format json` — gather today's per-entry completion-log records (replaces the prior monolith-read flow).
3. Reconcile: add missing entries via per-entry write (per `skills/session-end/SKILL.md` Step 2.6 schema), fix inaccurate ones, skip trivial commits.
4. If `docs/project-tracker.md` exists, verify completed workstreams have updated status.
5. Report: _"Archive audit: N entries verified, M added, K corrected."_

---

<!-- Step 7 intentionally removed (tier-usage telemetry rip-out, 2026-05-18). Cross-refs to Steps 8–11 in other files preserved; do not reuse this number. -->

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
<!-- Review: Patrik — previous regex ^chore|^doc|^session-end quick-save matched
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
**Links:** archive/daily-summaries/YYYY-MM-DD.md, archive/completed/YYYY-MM/ (per-entry files; query via `bin/query-completions --where "created=$TODAY"`)
```

Commit and push — include the daily summary artifact alongside the changelog row:
```bash
git add -- "$CHANGELOG_FILE" "archive/daily-summaries/$TODAY.md"
git commit -m "chore(week-changelog): daily block $TODAY $MACHINE"
git push origin $(~/.claude/plugins/coordinator/bin/coordinator-current-branch)
```

---

## Step 10: Weekly Staleness Check

```bash
~/.claude/plugins/coordinator/bin/check-weekly-staleness.sh
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
