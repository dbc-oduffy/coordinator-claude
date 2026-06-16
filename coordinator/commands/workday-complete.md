---
name: workday-complete
description: End-of-day orchestration — validate, consolidate branches, daily review, append to week-changelog
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Lightweight daily wrap: validate, consolidate branches, run the strategic daily review, append to the week-changelog, and surface staleness signals. **Does NOT merge to main.** Heavy ceremony (docs sweep, ShellCheck, improvement-queue triage) is weekly — see `/workweek-complete`.

Daily is a branch wrap, not a release ceremony. Each step below is an explicit script under `~/.claude/plugins/coordinator/bin/`; the prose names the contract, the script enforces it. All scripts are idempotent (re-running is a no-op when state is unchanged) and portable per `docs/wiki/cross-platform-shell-portability.md`.

---

## Step 1: Validate (blocking gate)

```bash
eval "$(~/.claude/plugins/coordinator/bin/workday-complete-step1-validate.sh)"
RC_STEP1=$?
```

The script runs the UBT pending-record resolution (UE work only, presence-detected) then the configured fast-test command. Emits `RC_UBT=… RC_VALIDATE=…` on stdout for the caller to consume in Step 9. All other output is on stderr.

**Exit-code branch:**
- `0` — both gates ok or skipped. Proceed.
- `1` — UBT resolved blocked. Stop and fix the C++ compile error. Override with `COORDINATOR_OVERRIDE_UBT_GATE=1` only when the PM authorises.
- `2` — fast-test build failure. Stop and fix.
- `3` — fast-test test failures only. Fix what's quick, flag the rest, proceed.
- `4` — resolver lib missing (configure `fast_test_cmd:` in `coordinator.local.md` or `$COORDINATOR_FAST_TEST_CMD`).

---

## Step 1.5: Cruft Sweep Apply (Layer 1 mechanical floor)

```bash
bash ~/.claude/plugins/coordinator/bin/cruft-sweep.sh --class all --apply --quiet \
  || echo "[workday-complete] WARN: cruft-sweep Step 1.5 exited non-zero (non-blocking) — check ~/.claude/state/cruft-sweep-log.md" >&2
```

Non-blocking. Lock-protected (concurrent invocations no-op), idempotent. Doctrine: `docs/wiki/cruft-sweep-cadence.md` § Layer 1.

---

## Step 2: RAG Staleness Nudge (informational)

If `ToolSearch` finds any `mcp__project-rag__*` tool, run the staleness survey. Surface in the final summary only if verdict is `stale` or `very-stale`. Skip silently otherwise.

---

## Step 2.5: Pre-terminate Dirty-Tree Disposition

Auto-disposes orphaned housekeeping files via path-prefix classification. Three valid dispositions — Commit, Gitignore, Discard — never stash (PM ruling 2026-06-16, `cross-repo/inbox/2026-06-16-workday-complete-dirty-tree-autonomy.md`).

```bash
bash ~/.claude/plugins/coordinator/bin/workday-complete-step2_5-dirty-tree.sh
RC_STEP2_5=$?
```

The script walks `git status --porcelain` and acts:
- **EOL phantoms / submodule pointers / `state/handoffs/`** → skip (concurrent-session territory).
- **Allow-listed housekeeping roots** (`cross-repo/inbox/`, `state/review-trail/`, `state/memos/`, `state/lessons-outbox/`, improvement/debt/bug-backlog dirs, `tasks/audits/`, `archive/`, plan pre-flight sidecars, etc.) → single batched explicit-path commit.
- **Transient patterns** (`logs/*`, `*.log`, `*.pid`, `.DS_Store`) → add to `.gitignore`, remove from index, commit gitignore.
- **`.tmp.<pid>.<nanos>` orphans** → list, do NOT auto-delete (per CLAUDE.md § Verifying Executor Output — diff against target first).
- **Source-tree edits without attribution** → list and exit 2 (PM surface).

**Exit-code branch:**
- `0` — all clear-wins handled, nothing ambiguous remains. Proceed.
- `2` — clear-wins handled, but source-tree or ambiguous paths remain. Surface the script's stderr listing to the PM and ask: _"Adopt-commit (mine, forgot to attribute), discard (abandoned), or attribute to another session?"_ Wait for response before proceeding.

**If in doubt — look harder.** Read the file, `git log -- <path>` for prior touches, grep for the workstream, check `state/handoffs/` and `archive/handoffs/` for a `scope:` block that names it. Bailing to "I cannot decide" is the failure mode.

**Auto-disposition is workday-complete-specific by design.** The dirty-tree gate is replicated across all three session terminators (workstream-complete, handoff, workday-complete), but the disposition diverges: workstream-complete and handoff terminate mid-session with a smaller, fresher tree where unattributable-to-this-session is a real signal worth surfacing. The daily wrap is different — it absorbs the day's housekeeping accumulation across all sessions. Do NOT propagate this allow-list to the other two terminators (memo OOS clause).

---

## Step 3: Branch Consolidation

```bash
bash ~/.claude/plugins/coordinator/bin/workday-complete-step3-consolidate.sh
RC_STEP3=$?
```

The script: syncs main, discovers same-machine sibling workstream branches (case-insensitive, includes span-form), merges them into current, reconciles with `origin/main` (guarded against ahead-only no-op), pushes with `--force-with-lease` (one fetch-rebase-retry on rejection), and deletes merged siblings. Feature branches excluded.

**Exit-code branch:**
- `0` — full success.
- `1` — `sync-main` aborted. Report and stop.
- `2` — merge conflict during sibling merge. Report and halt.
- `3` — reconcile conflict with origin/main.
- `4` — push rejected twice. Report to PM.
- `5` — `cs_compute_machine` lib unavailable.

**Args:** `--no-push` for PM-deferred push; `--dry-run` for inspection.

---

## Step 4: Strategic Daily Review

Produce `archive/daily-summaries/YYYY-MM-DD.md`. Heavy-weight templates, the failure-mode table, health-ledger schema, and debt-backlog DSR-ID format live in `docs/wiki/daily-summary-procedure.md` — walk that wiki for detail; do not re-author it inline.

**Skip condition:** zero new commits AND no agent-driven changes outside commits → write a one-line summary noting "no work today" and skip 4b–4e.

### Step 4a: Inventory Generation

```bash
mkdir -p tasks/daily-review-scratch
bash "${CLAUDE_PLUGIN_ROOT}/bin/standup.sh" > tasks/daily-review-scratch/inventory.md
TODAY=$(date +%Y-%m-%d)
"$HOME/.claude/plugins/coordinator/bin/query-completions.sh" --where "created=$TODAY" --format json \
  > tasks/daily-review-scratch/completions-today.json
```

`completions-today.json` is the primary source for the **Work Completed** section. `git log` scanning is deprecated except as a fallback for pre-completion-log sessions (when the JSON is empty).

### Step 4b: Analyst Dispatch (Sonnet, background)

Dispatch a Sonnet analyst (`model: "sonnet"`, `run_in_background: true`). It reads `inventory.md` + `completions-today.json` + `git diff <baseline>..HEAD`, then writes `archive/daily-summaries/YYYY-MM-DD.md` with Work Completed / Systems Affected / Architectural Decisions sections.

Full prompt template: `docs/wiki/daily-summary-procedure.md` § Sonnet Analyst Prompt Template.

Wait for the analyst before Step 4c.

### Step 4c: Strategic Observer Dispatch (Sonnet, non-persona)

Dispatch an **unnamed Sonnet worker** (`general-purpose`, `model: "sonnet"`) — NOT a named persona. Personas (the Staff Engineer / the Game Dev Reviewer / the Data Science Reviewer / the Front-End Reviewer) are Opus-only and reserved for `/workweek-complete` Step 7.5, the merge gate, and explicit architectural decisions.

The observer leaves a paper trail for future-the Staff Engineer — alignment notes, debt candidates, architectural-risk flags. It renders **no final architectural verdict**; weekly Opus the Staff Engineer adjudicates. Appends `## Strategic Review (Sonnet daily observer)` to the daily summary; writes flagged items as `state/debt-backlog.md` rows (DSR-{date}-{N}), tagging architectural flags `for-weekly-arch-review`.

Full prompt template: `docs/wiki/daily-summary-procedure.md` § Daily Strategic Observer Prompt Template.

### Step 4d: Health Ledger Update

1. Read `state/health-ledger.md`. If missing, create from schema in `docs/wiki/daily-summary-procedure.md` § Health Ledger Entry Schema.
2. Add rows (grade `?`, unaudited) for any system touched today with no row yet.
3. Do **NOT** touch audit clocks (`Last full audit`, `Last targeted audit`) or any grade — those are written only by `/architecture-survey` (full) and `/architecture-audit` (targeted).

### Step 4e: Clean Scratch

```bash
rm -rf tasks/daily-review-scratch
```

The daily summary artifact is committed by Step 9 alongside the changelog row — not here.

---

## Step 4.5: Completion-Log Clustering Pass

<!-- Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 4 -->

Groups today's completion entries by `chain:` field and synthesizes a machine-readable `narrative:` for each multi-entry chain. Single-entry chains skip. Enables `/workweek-complete` editorial bucketing to read `narrative:` rather than re-derive.

```bash
TODAY=$(date +%Y-%m-%d)
"$HOME/.claude/plugins/coordinator/bin/query-completions.sh" --where "created=$TODAY" --format json > /tmp/completions-cluster-$TODAY.json
```

Parse the JSON, group by `chain:`. For each group with ≥2 entries:

1. **Lead entry:** lexicographically first file path in the chain.
2. **Idempotency:** if the lead entry already has `narrative:` AND the body text below the closing `---` of every entry is byte-identical to when it was written → skip this chain.
3. **Dispatch a Sonnet `general-purpose` worker** with this inline prompt:

   > You are synthesizing the contribution narrative for a completion-log chain.
   >
   > Chain entries (JSON): `<paste chain entries JSON>`
   >
   > Write ONE paragraph (3–6 sentences) summarizing the chain's combined contribution. Rules: preserve commit SHAs verbatim; no editorial bucketing (Features/Fixes/etc — that's `/workweek-complete`'s job); describe what was built/fixed/changed and why it matters; ≤300 words.
   >
   > Reply with ONLY the paragraph text. No preamble.

4. **Write the result** — `Edit` the lead entry's frontmatter to insert `narrative: |` as a block scalar.
5. **Mark non-lead entries** — insert `narrative_in: <path-to-lead-entry>` into each non-lead's frontmatter (skip if already present).

No commit here. Step 9 stages and commits the entry files alongside the changelog row.

---

## Step 5: Plugin Validation Suite (blocking gate)

```bash
node --test ~/.claude/plugins/coordinator/tests/plugin-ecosystem/run.js
RC_PLUGIN_SUITE=$?
```

- **Hook-behavior failures:** blocking — stop and fix.
- **Non-hook failures:** report in summary, flag for morning, do not block git steps.

`RC_PLUGIN_SUITE` populates the changelog `Validation:` field in Step 9.

---

## Step 6: Completed Archive Audit

1. `git log --oneline --since="$TODAY 00:00" --until="$TODAY 23:59"` — today's commits.
2. `query-completions --where "created=$TODAY" --format json` — today's per-entry completion records.
3. Reconcile: add missing entries via per-entry write (per `skills/workstream-complete/SKILL.md` Step 2.6 schema), fix inaccurate ones, skip trivial commits.
4. If `docs/project-tracker.md` exists, verify completed workstreams have updated status.
5. Report: _"Archive audit: N verified, M added, K corrected."_

---

<!-- Step 7 intentionally removed (tier-usage telemetry rip-out, 2026-05-18). Do not reuse this number. -->

## Step 8: Improvement-Queue Depth Nudge (read-only)

Read `~/.claude/state/coordinator-improvement-queue.md`. Count `- ` lines in `## Active queue`.

- **≥ 5 entries:** emit in final summary: _"Coordinator-improvement queue: K entries (oldest: YYYY-MM-DD) — consider `/workweek-complete` to triage."_
- **Otherwise:** skip silently.

No triage at daily cadence — triage is weekly.

---

## Step 9: Append to Week-Changelog

```bash
RC_VALIDATE="${RC_VALIDATE:-skipped}" \
RC_PLUGIN_SUITE="${RC_PLUGIN_SUITE:-n/a}" \
bash ~/.claude/plugins/coordinator/bin/workday-complete-step9-append-changelog.sh "$ARGUMENTS"
RC_STEP9=$?
```

The script:
- Checks `state/week-changelog/HEADER.md` staleness; emits hard WARN and skips if `Week starting:` is >14 days past today.
- Synthesises a per-machine block from today's handoffs (`state/handoffs/YYYY-MM-DD-*.md`), the daily summary, and review-trail records (via `bin/list-review-trail-records.sh --date-prefix "$TODAY"`).
- Extracts `Decisions:` and `Blockers:` from handoff bodies (does not re-author).
- Auto-fills `Validation:` from the env vars above.
- Emits one `**Reviewed:**` line per record; falls back to `**Reviewed:** none — flag for /workweek-complete Step 7` only when today had non-trivial commits and no records exist; omits the field entirely when all today's commits are trivial.
- Idempotent: re-running on the same day with unchanged inputs is a no-op (no new commit, no push).
- Commits `$CHANGELOG_FILE` + `archive/daily-summaries/$TODAY.md` together and pushes.

**Exit-code branch:**
- `0` — block written, committed, pushed.
- `1` — write or commit error.
- `2` — push rejected (caller decides retry).
- `3` — HEADER staleness skip (informational).

**Args:** `--dry-run`, `--no-push`.

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

**Validation:** [step1 exit code]
**Branches consolidated:** [step3 summary]
**Branch state:** [branch name], rebased on main, pushed
**Daily review:** [archive/daily-summaries/YYYY-MM-DD.md]
**Plugin validation:** [step5 N pass / N fail]
**Archive audit:** [step6 summary]
**Week-changelog:** [step9 summary]
**Weekly staleness:** [STALE / MILD / FRESH]
**NOT merged to main** — use `/merge-to-main` when ready
```

If `$ARGUMENTS` is provided, prepend: _"Day summary: {arguments}"_.

---

### What This Does NOT Do

- **Merge to main** — `/merge-to-main` runs the test suite first.
- **`/update-docs`** — weekly only.
- **Triage the improvement queue** — depth nudge only; triage is weekly.
- **ShellCheck or scc stats** — `/workweek-complete`.
- **Delete the work branch** — stays alive for morning.
- **Delete handoffs** — `/pickup` archives, `/distill` deletes from archive (guarded). Spec: `docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` § Phase 4.

### Concurrent Session Safety

Per-machine files under `state/week-changelog/` eliminate concurrent-write conflicts. HEADER.md is touched only by the two weekly commands. Health files are global — workday-complete is the single daily writer.

### Relationship to Other Commands

- **`/merge-to-main`** — supervised merge; morning.
- **`archive/daily-summaries/YYYY-MM-DD.md`** — produced by Step 4; feeds Step 9.
- **`/workweek-complete`** — weekly release: docs sweep, ShellCheck, triage, version bump, merge.
- **`/workweek-start`** — PM-facing weekly orient; sets priorities in HEADER.md.
