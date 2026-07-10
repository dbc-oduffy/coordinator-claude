---
name: workweek-complete
description: Weekly release ceremony — validate, update docs, cut release notes, version bump, merge to main, archive
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: ""
---
<!-- Updated 2026-06-15 by structured-queue-medium-rollout C13: Step 4 surfaces queue depth via query-records.sh --type bug/debt/improvement; central queue stays markdown -->

# Workweek Complete — Weekly Release Ceremony

PM-invoked, release-grade close. Reads the week-changelog as the canonical record of what shipped — does NOT reconstruct the week from `git log`. Heavy steps dropped from `/workday-complete` live here: `/update-docs`, ShellCheck, improvement-queue triage, scc, version bump, and merge.

**Design contract:** the week-changelog is the ledger. The weekly ceremony reads it, validates against it, and archives it. Release notes are drafted from it, not re-derived.

---

## Step 1: Read Week-Changelog — PM Confirmation Gate

### Step 1a: Enumerate the ledger BEFORE concluding anything about its content

Substrate-blindness is the failure mode this step exists to prevent: an EM that "looks for" the ledger and concludes it's empty when files are sitting on disk. Print the inventory:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/list-week-changelog.sh"
```

Then Read HEADER.md and every daily file. **Pre-condition for the off-cycle / PM-blocking branches in Step 9:** any subsequent step that asserts "no ledger" / "no daily blocks" / "no `/workweek-start` was run" must quote a specific line from the output above as evidence. If the output shows ≥1 daily file with non-zero commit-lines, the ledger is non-empty by definition and the ceremony proceeds with what's there — the off-cycle/PM-blocking branches in Step 9 are gated behind this evidence requirement.

### Step 1b: Backfill missing daily blocks

A skipped `/workday-complete` must reduce fidelity, not erase the day. Run:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/backfill-week-changelog-gaps.sh"
```

Past-date synthesized blocks stay frozen (the day's commit set is closed). **Today's `-backfill.md` is overwritable by design** — commits land throughout the day and an early-morning backfill goes stale by ceremony time. The script re-emits today's synthesized block on every run; human-curated daily blocks (no `-backfill` suffix) are always sacred. Prints one line per backfilled/refreshed date. Synthesized blocks feed Step 9 editorial bucketing the same as human-curated ones (the worker reads `Commit log` when `Scope:` is empty). Name any backfilled dates in the Step 1c summary so the PM can amend before release-notes drafting.

### Step 1c: Surface summary

Surface to PM:

```
Week covers: D days (YYYY-MM-DD to YYYY-MM-DD)
Commits: N (range: <oldest-sha>..<newest-sha>)
Implemented workstreams: <list from Plans touched: implemented fields>
Blockers: <list or "none">
Priorities met: <from merged HEADER.priorities.*.md fragments vs. implemented plans>
```

**Priorities merge-on-read:** glob `state/week-changelog/HEADER.priorities.*.md` (one fragment per `/workweek-start` writer this week — HEADER.md itself no longer carries the Priorities checklist inline, only a pointer line). Read every fragment found and union their checklist items into one merged list before computing "met" vs. "missed". Do not treat any single fragment as authoritative or drop fragments that look duplicative — each is an independent collaborator's set. If no fragments exist, report "no priorities were set this week". (Fragments persist until the next full reset archives them — see `workweek-start.md` § Step 6.)
<!-- Review: code-reviewer — F6: cross-reference the write-side reset lifecycle so a
     reader auditing "priorities met vs missed" knows stale fragments from an
     abandoned mid-week re-run could still be present and unioned in. -->

Ask: _"Does this summary match your recollection? Proceed with release ceremony?"_

**Wait for PM confirmation before continuing.** This is the single explicit PM gate before the irreversible steps.

---

## Step 2: Full Validation (blocking)

Run the complete validation stack:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
_LIB="$_cc_root/lib/coordinator-resolve-validation-cmd.sh"
_RESOLVE_TMP=$(mktemp)
trap 'rm -f "$_RESOLVE_TMP"' EXIT

if [[ -f "$_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_LIB"
  CMD=$(cs_resolve_fast_test_cmd 2>"$_RESOLVE_TMP")
  RC_RESOLVE=$?
else
  echo "WARN: resolver lib not found at $_LIB — skipping fast-test gate" >&2
  RC_RESOLVE=2
  CMD=""
fi

if [[ $RC_RESOLVE -eq 0 ]]; then
  # bash -c (child-shell sandbox) — matches workday-complete and skills/validate/SKILL.md;
  # prevents assignment-injection clobber of caller state via the resolved command.
  bash -c "$CMD"
  RC_CMD=$?
  # Validation: $RC_CMD  (0 = pass, non-zero = fail)
elif [[ $RC_RESOLVE -eq 2 ]]; then
  # Validation: skipped  (no fast_test_cmd configured — see stderr for remediation)
  RC_CMD=0
  [[ -s "$_RESOLVE_TMP" ]] && cat "$_RESOLVE_TMP" >&2
fi

node --test "$_cc_root/tests/plugin-ecosystem/run.js"
```

Capture exit codes — they populate `Validation:` in the changelog block:
- **`Validation: 0`** — fast-tier passed; plugin ecosystem check passed.
- **`Validation: <non-zero>`** — configured fast-test command failed. Stop and fix before proceeding.
- **`Validation: skipped`** — no `fast_test_cmd` configured in `coordinator.local.md` and `$COORDINATOR_FAST_TEST_CMD` is unset. Set one or the other; proceed with awareness that fast-tier was not run.

Any blocking failure → stop and report. Fix before proceeding. Do not proceed to Step 3 on a failing validation.

> Full-tier cadence gate — not a per-commit reflex; cap parallelism at ~50% cores. → `docs/wiki/test-design-discipline.md § Posture: Proportional Test-Running`.

---

## Step 3: Run `/update-docs`

Full multi-phase docs sweep. Commits and pushes to the current branch.

Wait for completion before proceeding.

---

## Step 3.5: Runtime-Tripwire Fire-Log Triage

Before queue triage, read the runtime-tripwire fire-log:

```bash
_FIRE_LOG="$(coordinator_state_root --central)/runtime-tripwire-fire-log.tsv"
if [[ -f "$_FIRE_LOG" ]]; then
  wc -l < "$_FIRE_LOG"
  # Summarize fire counts by fire_type (columns: timestamp, agentId, model, elapsed_min, fire_type)
  awk -F'\t' 'NR>1 {count[$5]++} END {for (t in count) print t, count[t]}' "$_FIRE_LOG" | sort
  # Surface recurring agents (same agentId fired ≥3 times)
  awk -F'\t' 'NR>1 {count[$2]++} END {for (id in count) if (count[id]>=3) print count[id], id}' "$_FIRE_LOG" | sort -rn | head -20
else
  echo "runtime-tripwire-fire-log.tsv absent — skipping."
fi
```

**Triage signal:** If `em-side` fires dominate (≥50% of entries) or any `agentId` fires ≥3 times, treat as miscalibration evidence. Surface to PM: _"Tripwire fire-log shows N recurring dispatches — consider recalibrating `SONNET_MAX_MINUTES` or the dispatch-size ceiling."_ See `docs/wiki/runtime-tripwire.md` §6 for the recalibration mechanism. Recurring `agent-side` fires at reasonable elapsed times indicate legitimate long executors; no action needed.

---

## Step 4: Improvement-Queue Triage

Read the central improvement queue (`$(coordinator_state_root --central)/coordinator-improvement-queue.md`, example-orchestration-hub-resident — see `docs/wiki/state-placement-law.md`). Note oldest entry date and total active count.

**Triage triggers (any):** ≥5 active entries; oldest >14 days ago; any `[recurring: ≥3]`.

If triggered: (1) read entries, (2) prioritize `[recurring: ≥3]` first, (3) dispatch small executor per `proposed target`, (4) delete resolved entries (do NOT annotate), (5) commit naming closed entries, (6) >15 entries → `/staff-session`-style sweep.

If not triggered: note _"Improvement queue: K entries, oldest YYYY-MM-DD — no triage needed."_

**Write-time discipline (DR-056):** Append NEW entries as a single main line — no sub-lines, no closure-log sections (`## History`, `## Resolved`, `## Done`, etc.) — the pruner strips them.

**Prior-art sidecar scan (judgment-based):** Scan recent `docs/plans/**/*.prior-art-check*.md` sidecars for Conflicts dispositioned as `override-and-document`, `update-prior-art`, or `both`. Any wiki cited ≥3 times is a revision candidate — surface to PM. Full doctrine: `docs/wiki/prior-art-checker.md` § "Bidirectional resolution".

**Bug-backlog depth check:** Use `bin/query-records.sh --type bug --where 'severity in (P1,P2),status=open' | wc -l` to count open P1/P2 items. If ≥10, ask PM: _"Bug backlog has N open P1/P2 items — run /bug-blitz now or defer?"_ Otherwise note in summary. If `state/bug-backlog/` directory absent or empty: skip silently.

- **Portability sweep on the week's diff.** Run
  `portability-sweep <repo-root> --diff-only $(week-start-sha)..HEAD --report-format md`.
  Surface findings to the weekly triage list. Treat the same as the merge-time
  step: PM dispositions; never a workweek-complete blocker.

### Initiative-Govern Sweep

<!-- spec-backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C5 (AC6) -->
<!-- sole ritual home — NOT workday-complete, workstream-start, or workweek-start;
     DR-209 (example-orchestration-hub-em) suggested workweek-start, but the PM ratified workweek-complete:
     backward-looking cadence fits an initiative sweep; queue-triage dispatch teeth already
     live in this step (predecessor handoff Key Decision #6). -->

Run the unattached-record lens then the candidate detector:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
# Lens: every artifact with initiative == null across queues, roadmap stubs, handoffs, plans
# Review: code-reviewer — F9 (volume): first-run --unattached can be high-volume; --limit 50 prevents a wall of output.
# Re-run with --type (e.g. --type bug) for deeper per-type inspection.
node "$_cc_root/bin/query-records.js" --unattached --limit 50
# Detector: cluster unattached items; emits candidate initiative labels (≥3-item floor)
# Review: code-reviewer — F1: detect-initiative-candidates is a Node.js script (#!/usr/bin/env node); bash invocation bypasses shebang and fails.
node "$_cc_root/bin/detect-initiative-candidates"
```

**Surface to PM:** for each candidate cluster output by the detector, show the suggested label, item count, and representative items. Then prompt: _"Confirmed initiatives to name? Run `coordinator-initiative create` for new ones, `coordinator-initiative attach <artifact-path> <id>` to link existing items."_

**If no candidates:** note _"Initiative sweep: N unattached records — no candidate clusters above ≥3-item floor."_ and continue.

**Negative-spec — sole ritual home.** This sweep MUST NOT be added to `/workday-complete`, `/workstream-start`, or `/workweek-start`. Placement at `/workweek-complete` is PM-ratified (backward-looking cadence, queue-triage context). The detector is **read-only** — it surfaces candidates; the human authors the cut via `coordinator-initiative create`/`attach`. No auto-creation of initiatives from this step.

### Cruft-sweep verification (read-only)

Surface the Layer 1 cruft-sweep cadence in the weekly summary. Read-only — no `--apply` from here.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
# Last sweep timestamp + reclaimable size (if log exists)
if [[ -f "$(coordinator_state_root --central)/cruft-sweep-log.md" ]]; then
  # Review: Slice C reviewer F5 — log is pipe-delimited; awk '{print $1}' returns "|" not timestamp.
  # Use field-split on "|" and strip spaces from field 2 (the timestamp column).
  LAST=$(tail -1 "$(coordinator_state_root --central)/cruft-sweep-log.md" | awk -F'|' '{gsub(/ /, "", $2); print $2}')
  echo "Cruft-sweep last run: ${LAST:-never}"
fi
bash "$_cc_root/bin/cruft-sweep.sh" --class all --dry-run --quiet 2>&1 | tail -1
```

If staleness exceeds 21 days OR the dry-run reports > 2 GB reclaimable, surface a one-line note in the weekly summary: _"Cruft-sweep cadence drift — N days since last run, X MB reclaimable. Invoke `/cruft-sweep` to action."_

See `docs/wiki/cruft-sweep-cadence.md` for the full cadence + class breakdown.

### Workstream-complete inline-budget advisory (read-only)

Surface drift in the `workstream-complete` skill's inline bash-block count — the rebound barrier that keeps it a dispatcher of one-liners (new mechanism should land as a `bin/wsc-*.sh` script, not inline). Non-blocking WARN.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/check-wsc-inline-budget.sh" 2>&1 | tail -1
```

If it prints `WARN: ... exceeds baseline`, surface a one-line note in the weekly summary: _"workstream-complete inline-budget drift — new mechanism inlined instead of extracted to a `bin/wsc-*.sh` script. See `skill-step-parallelization.md` § wsc wiring rule."_ Exit 1 is the WARN signal, not a gate.

---

## Step 4.5: Weekly KR Re-assessment

<!-- spec-backlink: docs/plans/2026-07-06-goal-setting-okr-legibility-system.md § C6 -->
<!-- Advisory — non-blocking; does NOT gate Step 5 or beyond -->

Run the weekly KR re-assessment helper. It reads **existing signal only** (completions, handoffs, week-changelog HEADER) — no new instrumentation. For each `state/goals/*.md` artifact it proposes a per-KR status and a `perceptible_movement` flag. KRs with no movement AND `weekly_perceptible: true` are flagged as _"maybe-not-a-goal — no perceptible movement this week"_.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
# Review: code-reviewer F9 — guard added so advisory step no-ops cleanly if script not yet installed
[[ -f "${_cc_root}/bin/reassess-goal-krs.sh" ]] || { echo "INFO: reassess-goal-krs.sh not installed — skipping KR re-assessment"; exit 0; }
bash "${_cc_root}/bin/reassess-goal-krs.sh" --since 7d
```

- **No `state/goals/` directory:** the script prints `INFO: No goals directory found` and exits 0 — skip.
- **Goals found:** review the proposed statuses and any `*** maybe-not-a-goal` flags. These are **proposals for EM/PM confirmation** — the live `status` field in each artifact is not overwritten. Confirm, adjust, or reclassify as appropriate before continuing.
- **Advisory only:** this step is non-blocking. Do NOT halt the workweek-complete ceremony on KR signal gaps; surface findings in the weekly summary instead.

**Negative-spec:** this step MUST NOT auto-set `status:` fields in goal artifacts. Proposed statuses are written as a comment block for explicit human review only.

---

## Step 4b: Install OOM Reproducer Freshness Check

If `bin/check-install-reproducer-fresh.sh` exists in the repo root:

```bash
bash bin/check-install-reproducer-fresh.sh
```

- **Exit 0 (marker fresh, <24h):** notice; proceed.
- **Exit 0 (test ran and passed):** proceed.
- **Exit 1 (test failed):** halt and report; do NOT proceed to Step 5+ until fixed or PM grants `--force`.

Informational when fresh; **blocking gate** only when the test runs and fails.

---

## Step 4c: UBT Pending-Record Merge Gate (UE plugin work only)

Scan for `*.ubt-compile.pending.json` records in `state/review-trail/` with no `.resolved.json` sibling:

```bash
UNRESOLVED=$(find state/review-trail -maxdepth 1 -name "*.ubt-compile.pending.json" -type f 2>/dev/null | while read -r f; do
  base="${f%.pending.json}"; [[ ! -f "${base}.resolved.json" ]] && echo "$f"
done)
```

Passes silently when none found. If unresolved: halt and emit `sha_range` values — _"run /workday-complete on the affected day(s) or override with `COORDINATOR_OVERRIDE_UBT_GATE=1`."_ Non-UE repos no-op silently.

---

## Step 4d: Skill Description Length Advisory

```bash
set +e
_DESC_OUT=$(${CLAUDE_PLUGIN_ROOT}/bin/check-description-length.sh 2>&1); _DESC_RC=$?
set -e
echo "---"; echo "description-length advisory (rc=$_DESC_RC):"; echo "$_DESC_OUT"; echo "---"
```

Informational — never blocks. Note over-budget skills in the weekly summary; address next session.

---

## Step 4e: Owner-File Invariant Lint Advisory

Presence-detected. Applies only when `scripts/lint-owner-file-invariants.py` exists — repos without the §1a convention (`docs/wiki/rag-bait-conventions.md` §1a) pass silently.

```bash
if [[ -f scripts/lint-owner-file-invariants.py ]]; then
  set +e
  # python3-first resolver — `python` is absent on modern macOS / many Linux.
  # No interpreter → clean SKIP with notice (advisory step); do NOT fall back to a
  # literal `python3` that 127s and surfaces as a spurious rc into the weekly summary.
  PY="$(command -v python3 || command -v python)"
  if [[ -z "$PY" ]]; then
    echo "---"; echo "owner-file-invariant advisory: SKIP — no python3/python on PATH"; echo "---"
  else
    _LINT_OUT=$("$PY" scripts/lint-owner-file-invariants.py 2>&1); _LINT_RC=$?
    echo "---"; echo "owner-file-invariant advisory (rc=$_LINT_RC):"; echo "$_LINT_OUT"; echo "---"
  fi
  set -e
fi
```

Informational. Non-zero rc means a file in `scripts/owner_files.yaml` lost its `Invariant —` marker. Note in weekly summary; address next session. Cadence doctrine: `docs/wiki/workday-workweek-cadence.md` lines 56–75.

---

## Step 4f: enabledPlugins Drift Audit Advisory

Per-repo advisory — audits current repo's `enabledPlugins` against `project_type` / `stack_tags` from repo-root `coordinator.local.md` or the central state repo-registry (`$(coordinator_state_root --central)/repo-registry.md`, example-orchestration-hub-resident — see `docs/wiki/state-placement-law.md`).

```bash
set +e
if [[ -f .claude/settings.json ]]; then
  _EP_OUT=$(${CLAUDE_PLUGIN_ROOT}/bin/audit-enabled-plugins.sh 2>&1); _EP_RC=$?
else
  _EP_OUT="(no .claude/settings.json — skipped)"; _EP_RC=0
fi
set -e
echo "---"; echo "enabledPlugins drift advisory (rc=$_EP_RC):"; echo "$_EP_OUT"; echo "---"
```

Advisory only — never blocks. `project_type: meta` short-circuits (all plugins intentional). When drift is reported, full uninstall requires removing the entry from `.claude/settings.json`, from `~/.claude/plugins/installed_plugins.json`, and from `~/.claude/plugins/cache/<marketplace>/<plugin>/` — EM surfaces the recipe, PM authorizes.

---

## Step 4g: Reverse-Drift Merge Gate (copy_install plugins only)

Blocking gate for plugins whose live install is a copy of source (`copy_install` in `plugin.mirrors`). The forward-SHA `check-plugin-drift.sh` is structurally blind to a live install that was hand-edited *after* the last install — each plugin's registered `reverse_drift_cmd` closes that direction by digest-comparing live against source.

Detection is delegated to the per-plugin `reverse_drift_cmd` registered in `plugin.mirrors.<name>` and discovered through the machine-local registry — so the gate fires from any cwd, not only the example-game-repo source repo. The reader script is referenced by its **authoritative absolute path**; a cwd-relative `bin/...` path would reproduce the exact silent-no-op bug this gate's 2026-05-28 rework fixed (DR-146). Never shorten it.

**Per-repo scoping (`--scope-repo`).** The gate is scoped to the repo running `/workweek-complete`: the meta-repo (`~/.claude`, the coordinator home) checks **every** `copy_install` plugin on the machine (the 2026-05-28 §Chunk 3 meta-repo-coverage intent); a **consumer repo** (project-rag, example-sim-repo, etc.) checks only `copy_install` plugins whose `source_path` IS that repo — usually none, so a clean no-op. This stops a consumer-repo release from gating on a *sibling* plugin's live-install drift, which violates the dependency-direction invariant (a host must never be forced to sync with a consumer's state). The repo root is resolved via `git rev-parse --show-toplevel` and passed through; path forms are normalized inside the reader (Windows `X:/` vs MSYS `/x/` vs `$HOME` `/c/`).

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
# Discover registered reverse-drift commands via the machine-local registry,
# scoped to THIS repo (see Per-repo scoping above).
# Absolute path is load-bearing — see DR-146 and docs/wiki/machine-local-registry.md § reverse_drift_cmd.
# `|| REVDRIFT_RC=$?` (not a bare `RC=$?` on the next line) so a non-zero rc is captured
# even if this block is paste-run under `set -e` — otherwise the shell aborts on the
# assignment before rc is read, and the fail-loud branches below never fire.
REVDRIFT_SCOPE_REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
REVDRIFT_RC=0
REVDRIFT_ROWS="$("$_cc_root/bin/list-reverse-drift-cmds.sh" --scope-repo "$REVDRIFT_SCOPE_REPO")" || REVDRIFT_RC=$?

if [[ $REVDRIFT_RC -eq 3 ]]; then
  # copy_install plugins ARE registered but none carry a reverse_drift_cmd: the gate is blind.
  echo "Reverse-drift gate MISCONFIGURED — copy_install plugins exist but none have a reverse_drift_cmd. Register with: machine-local set plugin.mirrors.<name>.reverse_drift_cmd '<invocation>'. See docs/wiki/machine-local-registry.md § reverse_drift_cmd."
  [[ "${COORDINATOR_OVERRIDE_REVERSE_DRIFT:-0}" == "1" ]] || exit 1
elif [[ $REVDRIFT_RC -ne 0 ]]; then
  echo "Reverse-drift gate: reader exited with an unexpected code (rc=$REVDRIFT_RC) — e.g. a registry-read or invocation error. Check the reader output above before merging."
  [[ "${COORDINATOR_OVERRIDE_REVERSE_DRIFT:-0}" == "1" ]] || exit 1
else
  # rc==0: run each registered command from its source_path. Empty rows = no
  # copy_install plugins on this machine = genuinely N/A (clean pass).
  REVERSE_DRIFT_FAIL=0
  while IFS='|' read -r PLUGIN SRC CMD; do
    [[ -z "$PLUGIN" ]] && continue
    # bash -euo pipefail -c (not plain bash -c) so a pipeline failure inside the
    # registered reverse_drift_cmd fails-fast rather than being masked — matches the
    # hardened refresh_cmd invocation (refresh-plugin-live-install.sh:393, code-reviewer F7).
    if ! ( cd "$SRC" && bash -euo pipefail -c "$CMD" ); then
      REVERSE_DRIFT_FAIL=1
    fi
  done <<< "$REVDRIFT_ROWS"
  if [[ $REVERSE_DRIFT_FAIL -ne 0 ]]; then
    echo "Reverse-drift gate FAILED. Remediation: run \`example_game_repo_recover --step reverse-drift\` to back-propagate live→source, or override with COORDINATOR_OVERRIDE_REVERSE_DRIFT=1."
    [[ "${COORDINATOR_OVERRIDE_REVERSE_DRIFT:-0}" == "1" ]] || exit 1
  fi
fi
```

Do NOT proceed to Step 5 until the gate passes or PM grants override. Note `reverse_drift_cmd` is registry-supplied and shell-evaluated once by `bash -c` — operators MUST single-quote the value in `registry.local.toml` (same idiom as `refresh_cmd`). Detection logic remains example-game-repo-owned (`X:/example-game-workbench-repo/bin/check-reverse-drift.sh`; `docs/plans/2026-05-26-game-dev-ownership-and-bidirectional-install-drift.md` AC7); this gate only routes to it via the registry.

---

## Step 4h: CVE Recheck (change-aware)

Weekly dependency-CVE audit. **Change-aware:** dispatch the auditor only when a tracked manifest has changed in the last week — otherwise skip silently with a one-line note.

```bash
# Tracked manifest globs (subset of dep-cve-auditor's detection table).
_MANIFESTS=(package.json package-lock.json yarn.lock pnpm-lock.yaml \
            requirements.txt requirements.lock pyproject.toml uv.lock \
            Cargo.toml Cargo.lock go.mod go.sum)

# Any tracked manifest present at all? If none, the repo has no dep surface — skip.
_PRESENT=$(git ls-files -- "${_MANIFESTS[@]}" 2>/dev/null | head -1)
if [[ -z "$_PRESENT" ]]; then
  echo "CVE recheck: no tracked dependency manifests in this repo — skipped."
else
  # Did any change in the last two weeks? (14-day window — covers slipped workweeks;
  # double-audit is a cheap no-op report, missed-audit is a silently-unscanned CVE.)
  _CHANGED=$(git log --since="14 days ago" --name-only --pretty=format: -- \
             "${_MANIFESTS[@]}" 2>/dev/null | sort -u | grep -v '^$' || true)
  if [[ -z "$_CHANGED" ]]; then
    echo "CVE recheck: dependency manifests unchanged in the last 14 days — skipped."
  else
    echo "CVE recheck: manifests changed this week — dispatching dep-cve-auditor:"
    echo "$_CHANGED" | sed 's/^/  - /'
    # EM dispatches dep-cve-auditor with output path state/review-findings/<week>-cve/deps.md
  fi
fi
```

- **Skip cases** (no dispatch, one-line note in summary): no tracked manifests present, OR manifests present but none changed in the last 14 days.
- **Dispatch case:** at least one manifest changed → dispatch `dep-cve-auditor` (Sonnet worker) with output path `state/review-findings/<week-starting>-cve/deps.md`. Surface its verdict alongside Step 7's gate verdict in Step 9 release notes if any findings warrant it.

**Windows spawn discipline — include this in every `dep-cve-auditor` dispatch prompt:**

> Cross-platform shell — Windows console-flash discipline: Do NOT use bare `python3 -c "…"` or `python -c "…"` for any ad-hoc Python. On Windows these resolve to the venv's console-subsystem `python.exe` and trigger focus-stealing popup windows (~20+ per audit run). If you need an ad-hoc Python one-liner, first check for a project-local quiet wrapper: `project_rag_scripts/python-quiet.sh` (project-rag repos), `bin/python-quiet.sh`, or `bin/python-quiet.ps1`. Route through it if found (`bash project_rag_scripts/python-quiet.sh -c "…"`). If no wrapper exists, document the limitation in the report rather than spawning bare Python. The audit tools themselves (pip-audit, npm audit, cargo audit, govulncheck) are exempt — they are invoked as first-class CLIs, not Python one-liners. References: `docs/wiki/intel-fortran-rtl-console-popup.md` (consuming repo), `docs/wiki/cross-platform-shell-portability.md` (coordinator plugin).

Advisory step — does NOT block merge. The change-aware gate is what makes this cheap: ~/.claude meta-repo (scripts-only `package.json`) skips silently every week; a repo with active dep churn audits when there's something new to audit.

<!-- spec: change-aware-cve-recheck — see commit history; replaces the dropped tasks/cve-recheck-due-*.md marker mechanism (2026-06-08) -->

---

## Step 5: scc Snapshot

If `scc` is available (`which scc` or `~/bin/scc`):
```bash
scc --no-complexity --no-cocomo --no-duplicates --sort code
```

Record the compact summary (total lines, top 5 languages) in `state/code-stats-history.md` under a `## YYYY-MM-DD` heading (append; create the file if it doesn't exist). Weekly trend is the signal; daily delta is noise.

If `scc` is not installed: note in summary — _"scc not available — install for weekly code stats."_

---

## Step 6: ShellCheck Sweep + Console-Flash Guard

```bash
git ls-files '*.sh' | while read -r f; do
  tr -d '\r' < "$f" | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|$f:|g"
done
```

- **Issues found:** report and offer to fix. Most findings are quick mechanical fixes; fix what's straightforward, flag behavior-changing items for PM review.
- **Clean:** report _"ShellCheck: all .sh files clean."_
- **Not installed:** note in summary.

**Console-flash guard (CONSOLE-FLASH-GUARD):** After ShellCheck, run the spawn-suppression guard:

```bash
# Runs from the coordinator plugin root regardless of cwd.
_GUARD="${CLAUDE_PLUGIN_ROOT}/bin/verify-no-console-flash.sh"
if [[ -f "$_GUARD" ]]; then
  bash "$_GUARD" "$HOME/.claude/plugins"
  _FLASH_RC=$?
  if [[ $_FLASH_RC -ne 0 ]]; then
    echo "Console-flash guard: UNSUPPRESSED spawns found (see above). Fix before merging."
  else
    echo "Console-flash guard: OK"
  fi
else
  echo "Console-flash guard: guard not found at $_GUARD — install or check CLAUDE_PLUGIN_ROOT"
fi
```

- **Issues found:** report and offer to fix; same offer-and-fix shape as ShellCheck. Route bare python/node/powershell spawns through `lib/spawn-hidden.sh` or add `# verify-no-console-flash: allow` if the spawn is verifiably not on the Windows hot-path.
- **Clean:** report _"Console-flash guard: OK"_.
- **Guard missing:** note in summary — install or check `$CLAUDE_PLUGIN_ROOT`.

<!-- spec: CONSOLE-FLASH-GUARD; see docs/wiki/coordinator-tripwires.md § Console-window flash and docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 4 -->

---

## Step 7: Parallel Code-Review Gate

> Architecture and rationale: `docs/wiki/weekly-gate-architecture.md § Step 7`.

<!-- Review: code-reviewer F5 — plan D2 required this gate on BOTH /merge-to-main AND /workweek-complete;
     an illegal path committed between merge-to-main runs would survive to the weekly merge without it. -->

**Illegal-path backstop gate.**  Scan all tracked and staged paths for NTFS-illegal characters before
the parallel code-review.

<!-- Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D2 -->
<!-- Belt-and-suspenders with the pre-commit hook: catches any NTFS-illegal path that slipped in
     between /merge-to-main runs (which also runs this gate at Step 1.4). -->

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/check-no-illegal-paths.sh"
```

**Non-zero exit: halt.** Rename or remove the offending path, re-commit, then re-run `/workweek-complete`.

**Compute scope.** Run the trail helper (fail-loud; reads `state/week-changelog/HEADER.md`, globs `state/review-trail/*.json`, writes a session-keyed shard `state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json` — never a singleton overwrite, so two concurrent weekly gates never clobber each other's computed scope):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/workweek-trail-scope.sh"
```

**Read the scope shard.** Select the shard for THIS session: glob `state/review-trail/.weekly-reviewer-scopes-*.json`, prefer the newest shard whose filename's `<SID_SHORT>` suffix matches this session's own session-id (first 8 chars, resolved the same way the helper resolves it — `CLAUDE_SESSION_ID` / `CLAUDE_CODE_SESSION_ID` / `cs_resolve_session_id`), falling back to the newest shard overall if no session-matching shard is found. Single-operator behavior is unchanged: with exactly one shard present, that shard is read.

**Run gate.** After ShellCheck (Step 6) and before Tracker Reconciliation (Step 8), read `~/.claude/plugins/coordinator/skills/parallel-code-review/SKILL.md` and execute its steps. The brief references the selected scope shard (see "Read the scope shard" above). The Staff Engineer is NOT in this gate — see Step 7.5.

- **BLOCKED:** halt before Step 8 and Step 9; surface verdict line + findings-dir path to PM. Do not proceed until fixed or `--force` granted.
- **WARN:** include verdict line in release-notes draft (Step 9); proceed.
- **OK:** proceed; verdict line goes into release-notes draft for the record.

**Skip rules** (full detail in skill body): <10 lines or internal-only → skip entirely; doc-only week → skip code-semantics chunks (mechanical workers still run); plan-only week → skip entire gate; `--force` passes through.

---

## Step 7.4: Codex Review Gate (default-ON, advisory, does NOT gate merge)

> Architecture and rationale: `docs/plans/2026-06-14-codex-reviewer-integration-opt-in.md` (restoration of historical `codex-review-gate` skill, original ship `b31942c` 2026-04-01, distill-lost in `bb096b9e`, restored 2026-06-14).

Independent-model second opinion on the weekly diff. Codex sees the merge-gate diff (`origin/main..HEAD`) and flags anything the Sonnet chunk reviewers may share blind spots on. **Runs by default on every `/workweek-complete`**; when the `codex-review-gate` skill is absent (user never opted in at `/coordinator:install`), the Codex CLI is not installed/unauthed, or no diff exists against `origin/main`, the step gracefully skips (no-op, one log line).

**Invoke** `skill:codex-review-gate` with:

- `scope: workweek-merge-diff`
- `base: origin/main`
- `required: false`

**Advisory only.** This step never blocks merge. Step 7's BLOCKED/WARN/OK synthesizer verdict remains the sole merge gate; Step 8 (Tracker Reconciliation) does NOT consume Step 7.4's output. Codex findings are reported in this step's body but are NOT fed into the merge-decision rollup. P0/P1 Codex findings are surfaced to the PM as a separate advisory line; P2 findings note in the week-changelog.

**Graceful fallback contract:** skill absent → log `Codex review gate: skill not installed — skipped (run /coordinator:install to opt in)` and continue. CLI absent/unauthed → log the reason returned by the skill (`not installed` / `not authenticated` / connection error) and continue. No diff against `origin/main` → log `Codex review gate: no diff against origin/main — skipped` and continue. None of these are gate failures.

---

## Step 7.5: the Staff Engineer Layer-2 — Architecture Pass (advisory, does NOT gate merge)

> Architecture and rationale: `docs/wiki/weekly-gate-architecture.md § Step 7.5`. Disposition ladder and accepted-loss reasoning are documented there.

**Run condition:** skip (note "no arch-tier signal this week") if ALL of: `arch_tier_candidates` empty AND `convergent_findings` empty AND seam-file set empty AND daily strategic-observer trail carries no `for-weekly-arch-review` flags.

**Otherwise** dispatch the Staff Engineer (`coordinator:staff-eng`, Opus) with five inputs: (1) changelog digest, (2) `arch_tier_candidates` from `$FINDINGS_DIR/synthesis.json`, (3) `convergent_findings` from `synthesis.json`, (4) `patrik_seam_files` from the scope shard selected in Step 7's "Read the scope shard" (glob `state/review-trail/.weekly-reviewer-scopes-*.json`, newest session-matching shard, else newest overall), (5) daily strategic-observer trail (`archive/daily-summaries/*.md` DSR rows tagged `for-weekly-arch-review`).

The Staff Engineer produces candidates only — never auto-authors spinoffs. EM routes candidates down the disposition ladder (trivial+non-structural → immediate executor; mid-size cluster → bundled spinoff candidate; large/structural → standalone spinoff or `/plan`).

**Surface the Staff Engineer's spinoff candidates to PM alongside the release-notes draft (Step 9).**

---

## Step 7.6: Architecture Audit Staleness Fold

> Architecture and rationale: `docs/wiki/weekly-gate-architecture.md § Step 7.6`. Scope (DECISION D6) and disposition ladder documented there.

**Run the staleness check:**
```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/check-arch-audit-staleness.sh"
```

- `STALE` (>10 days or never targeted-audited) → auto-fold a targeted-on-diff audit: read `${CLAUDE_PLUGIN_ROOT}/skills/architecture-audit/SKILL.md` and run it scoped to diff-touched systems only.
- `FRESH` → no fold (EM may still trigger on heavy multi-system churn).
- `UNKNOWN` → do NOT auto-fold; note and move on.

The folded audit never edits code — packages findings as spinoff candidates; writes only `Last targeted audit` clock + atlas metadata. Surface candidates alongside the Staff Engineer's Step 7.5 candidates and the release-notes draft (Step 9). Does NOT block merge.

If skipped (FRESH and no EM churn trigger): note _"Architecture audit: fresh (Last targeted audit within 10d) — no fold."_ in the summary.

---

## Step 7.7: Weekly Atlas Drift Walk

> Complement to Step 7.6 — Step 7.6 reads the rotation clock (`Last targeted audit`); this sub-step walks the per-system `<name>.watch.sh` scripts and the atlas `last_mapped` frontmatter to surface decay between rotations.

**Run the drift walk** (STALE walk default-on at 30 days):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/check-atlas-watch-drift.sh"
```

Surface in the weekly report:

- Any `DRIFT` / `MISSING` line → structural finding; folds into the weekly architecture-audit pipeline (Step 7.6) alongside the Staff Engineer's Step 7.5 candidates.
- Any `ERROR` / `MALFORMED` line → helper-script issue requiring author attention (the `<name>.watch.sh` broke or its stdout is garbage; never silently treated as FRESH).
- Any `STALE` line (atlas `last_mapped` >30d) → EM-judgment surface: either ratify the atlas as still-current (commit-message `atlas-current-as-of:<date>` token on a no-op `last_mapped` bump per the Step 6.5 closeout gate) or schedule a refresh pass via `/architecture-audit`.

Does NOT block merge; does NOT auto-dispatch refresh executors — the surface IS the gate. Note in the weekly summary: _"Atlas drift walk: N DRIFT, N STALE, N ERROR — [folded into Step 7.6 / surfaced for EM judgment]."_

---

## Step 8: Tracker Reconciliation

Read `docs/project-tracker.md` (if it exists). For each workstream that appears in the week's `Plans touched: implemented` fields, verify the tracker status is updated to reflect completion. Fix in place.

Report: _"Tracker reconciliation: N workstreams updated."_

---

## Step 8.5: LoE High-Water Check — MANDATORY Before Step 9

> **MANDATORY.** Do NOT proceed to Step 9 without completing it. Surfaces XL chain-terminal completion entries so large chains are explicitly acknowledged in the weekly summary, not silently folded into Other bucket prose.

### 8.5.1 Query chain-terminal XL entries

```bash
bin/query-completions --since "7d" \
  --where "chain_terminal=true" \
  --where "chain_loe.tshirt=XL" \
  --format json
```

Run a second time with `--where "loe.tshirt=XL AND chain_terminal=true"` to surface single-session XL entries (no `chain_loe`). Union both result sets in the PM summary.

### 8.5.2 Surface to PM

For each returned entry include: `title`, `chain` slug, `chain_loe.sessions`, `chain_loe.tshirt` (or `loe.tshirt` for single-session XL), date span. Format:

```
**XL chain-terminal entries this week:**
- "<title>" — chain: <chain-slug>, <N sessions>, <date-start> to <date-end> [chain-level XL]
- "<title>" — single-session XL, <date>
```

**If zero entries:** note explicitly _"No XL chain-terminal entries this week."_ — do NOT silently omit (absence is indistinguishable from a skipped step).

No PM gate required — informational surfacing only. PM may promote an XL entry to Highlights in Step 9 editorial bucketing.

---

## Step 9: Editorial Bucketing + Release Notes Draft — PM Review Gate

### 9.0 Ensure output directory exists

```bash
mkdir -p state/week-changelog/
```

### 9.1 Query the week's completion entries

Derive the week-start date from the changelog header so the query covers the full actual week —
a hardcoded `7d` window misses entries on a longer-than-7-day week, and the default `--limit 50`
silently truncates busy weeks (50 of 173 entries kept in the 2026-06-27 run, dropping the
entire release headline). Extract the date from `state/week-changelog/HEADER.md` and always
pass `--limit 1000` to prevent silent corpus truncation.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
# Derive week-start from HEADER.md line: **Week starting:** YYYY-MM-DD
week_start=$(grep -m1 '\*\*Week starting:\*\*' state/week-changelog/HEADER.md \
  | sed 's/.*\*\*Week starting:\*\*[[:space:]]*//')
"$_cc_root/bin/query-completions.sh" \
  --since "$week_start" --where "status=pending-release" --format json --limit 1000
```

Zero entries → skip to Step 9.4 with an empty-week note.

### 9.1.5 Detect-only reconcile pass (pre-release backstop)

<!-- spec-backlink: docs/plans/2026-06-27-post-summary-completion-loop-closure.md § C5b -->
<!-- purpose: guaranteed-complete backstop — iterates ALL pending-release entries before the
     accounting index freezes; advisory/non-blocking; detect-only (no --append) because this
     is a cross-session bulk over entries not necessarily authored by the current session. -->

Before handing the corpus to the editorial worker, run a detect-only pass to surface any
completion entry whose `commits:` list is missing session commits. This is the last mutable
moment before entries are stamped `released` — advisory warnings here are still actionable.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
RECONCILE_PATHS=$(
  "$_cc_root/bin/query-completions.sh" \
    --since "$week_start" --where "status=pending-release" --format paths --limit 1000
)
# DETECT-ONLY — do NOT pass --append; release is a cross-session bulk over entries
# this session did not necessarily author. reconcile-completion-commits.sh is the helper.
for ENTRY in $RECONCILE_PATHS; do
  AUTHORED_BY=$(grep -m1 '^authored_by:' "$ENTRY" | awk -F': *' '{v=$2; sub(/[[:space:]]*#.*$/,"",v); gsub(/^"|"$/,"",v); print v}')
  # Skip entries where authored_by is absent, empty, or the literal string "null".
  if [ -z "$AUTHORED_BY" ] || [ "$AUTHORED_BY" = "null" ]; then continue; fi
  # Review: code-reviewer Slice-B F1 — bare call masked by 2>/dev/null → silent false-clean; use full path
  DELTA=$(${CLAUDE_PLUGIN_ROOT}/bin/reconcile-completion-commits.sh --session-id "$AUTHORED_BY" "$ENTRY" 2>/dev/null \
    | grep -o 'delta=[0-9]*' | cut -d= -f2)
  if [ "${DELTA:-0}" -gt 0 ]; then
    echo "⚠ entry $(basename "$ENTRY"): $DELTA session commit(s) unaccounted — reconcile before release"
  fi
done
```

Advisory only — the ceremony does NOT hard-fail on unaccounted commits. If any warnings appear,
fold the missing SHAs into the relevant entry (via `reconcile-completion-commits.sh --append`)
before proceeding to Step 9.2.

### 9.2 Dispatch Sonnet editorial worker

Dispatch a Sonnet worker with the entry corpus. Worker assigns each entry to one bucket, writes `state/week-changelog/YYYY-MM-DD-pending-release.md`.

**Default bucket rules** (primary key: `nature`; refined by `loe.tshirt` when present):

| nature | tshirt | Bucket |
|--------|--------|--------|
| roadmap | L, XL | **Highlights** |
| roadmap | S, M | **Notable** |
| roadmap | XS | **Other** |
| bugfix (user-visible) | any | **Notable** |
| bugfix | XL | **Notable** |
| bugfix | S, M, L | **Other** |
| tech-debt / infra | non-XL | **Other** |
| tech-debt / infra | XL | **Notable** (EM call) |

EM override permitted — state explicitly in the dispatch. **Worker output format:**

```markdown
# Pending Release — YYYY-MM-DD

_Source entries queried: N_
_Code-review gate verdict: [OK | WARN <verdict-line> | not-run]_

## Highlights
- <summary> — [source](relative/path/to/per-entry-file.md)

## Notable
- <summary> — [source](relative/path/to/per-entry-file.md)

## Other
- <summary> — [source](relative/path/to/per-entry-file.md)
- ... and assorted fixes  _(collapse long tails ≥5 similar entries; not for Highlights/Notable)_
```

Empty buckets: `## Heading` with `_none this week_`. Each entry cites its source file. WARN verdict from Step 7 goes verbatim under `_Code-review gate verdict:_`. Verify file exists and is non-trivial before proceeding.

### 9.4 Draft release notes as thin wrapper

Read pending-release file. Write `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md` — do NOT re-author; format for the reader:

```markdown
# Release Notes — vX.Y.Z (YYYY-MM-DD)

## Highlights
<paste Highlights bucket, reformatted for prose if desired>

## Notable Changes
<paste Notable bucket>

## Other Changes
<paste Other bucket>

---
_Code-review gate: [verdict]_
```

Version is a placeholder until Step 10 confirms it.

Present to PM: _"Release notes drafted at `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md`. Bucketed: N Highlights, N Notable, N Other. Does this capture the week accurately?"_

**Wait for PM review.** Update both files to reflect any reclassifications.

---

## Step 10: Version Bump — PM Confirmation Gate

**Consumer convention takes precedence.** If the repo has `docs/wiki/versioning-convention.md`, that doc is the authority for *which* number/artifact is the canonical product version and *how* to bump it — read it first and follow it. The repo-agnostic semver heuristic below is the fallback for repos with no convention doc. (A repo with multiple version namespaces — pyproject, package.json, `.uplugin`, git tags — should not have its scheme guessed here; the convention doc exists precisely to name the one that ships.)

Fallback heuristic (no convention doc present) — propose a semver increment based on changelog content:
- **Major:** breaking change noted in any `Decisions:` field.
- **Minor:** new feature or new command shipped (`Plans touched: implemented` with new commands/skills).
- **Patch:** fixes, doc updates, refactors only.

Either way the governing principle is the same: a version bump communicates user-noticeable change — consolidate the delta since the last user-visible release into ONE bump.

Present to PM: _"Proposed: vX.Y.Z (rationale: [one line]). Confirm or adjust."_

**Wait for PM confirmation.** Update the release-notes filename and HEADER.md `Prior week released:` value to the confirmed version.

**Stamp ALL version surfaces together (coordinator-claude).** A version bump is one atomic move across every surface — `docs/wiki/versioning-convention.md` names the SSOT (`coordinator/.claude-plugin/plugin.json` `.version`) and the invariant. In the same commit that stamps the CHANGELOG `[Unreleased] → [X.Y.Z] — <date>` (Step 9):

1. `coordinator/.claude-plugin/plugin.json` `.version` → `X.Y.Z`
2. `.claude-plugin/marketplace.json` `.metadata.version` → `X.Y.Z`

Then **run the consistency gate before proceeding to merge** — it fails loud if any surface lags. Resolve the gate path layout-agnostically (meta-repo source layout vs flat OSS publish layout):

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
gate="$_cc_root/bin/check-version-consistency.sh"
[[ -f "$gate" ]] || gate="$(git rev-parse --show-toplevel)/coordinator/bin/check-version-consistency.sh"
bash "$gate"
```

A non-zero exit here means a surface was missed — fix it before Step 11. (This is the gate that would have caught the 2.7.1/2.1.1/2.8.1 drift surfaced on 2026-06-22.)

---

## Step 10.5: Release Publish — Backstop Un-Draft (catch-all for non-merge-tagged work)

<!-- spec-backlink: archive/specs/2026-06/2026-06-01-boot-currency-notification-hook.md § C1 — Release cadence -->
<!-- purpose: belt-and-suspenders catch-all for non-trivial work that reached main via direct
     daily-branch commits that bypassed /merge-to-main (and therefore bypassed the per-merge
     tagged-publish leg in skills/merging-to-main/SKILL.md Step 1.5). -->

**Precondition:** PM has confirmed the version at Step 10 (i.e., `$VERSION_TAG` is set, e.g. `v2.7.0`).

**Skip when:** the week's non-trivial work was ALREADY tagged and published per-merge via the `/merge-to-main` tagged-publish leg. Verify:

```bash
gh release view "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude --json isDraft,isLatest 2>/dev/null
```

- `isDraft=false, isLatest=true` → already published; skip this step and note _"Release already published at $VERSION_TAG — no backstop action needed."_
- Draft exists (`isDraft=true`) OR no release for the tag → proceed with the backstop below.
- Tag does not exist yet → create the release (see below).

**Backstop action — un-draft or create the release:**

If a draft release for `$VERSION_TAG` exists:
```bash
gh release edit "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude --draft=false --latest
```

If no release exists yet for `$VERSION_TAG` (e.g., the tag was never created):
```bash
# Use the release-notes file drafted in Step 9.4 as the body.
gh release create "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude \
  --title "$VERSION_TAG" \
  --notes-file "archive/release-notes/$(date +%Y-%m-%d)-${VERSION_TAG}.md" \
  --latest
```

**Scope:** coordinator-claude only on this plan. Deep-research-claude release publishing is owned by the deep-research-currency-notification spinoff (`state/handoffs/2026-06-01_122922_deep-research-currency-notification.md`). **Claude Prime (`source_is_live`) is never tagged** — skip silently when the active repo is the `~/.claude` meta-repo.

Surface to PM: _"Release $VERSION_TAG published on coordinator-claude (or already published — no action)."_

---

## Step 11: `/merge-to-main`

Invoke `/merge-to-main` only after PM has confirmed release notes (Step 9) and version (Step 10). Do NOT inline merge logic — the skill handles pre-merge test suite, PR creation, and merge.

---

## Step 12: Health Survey

Run the full health survey if available (e.g., `/health` or equivalent). Record output in `state/health-ledger.md` under today's date.

---

## Step 13: Reset Week-Changelog

Archive and reset the week's state:

1. Determine the current `Week starting:` date from HEADER.md — this is the archive path key.
2. Create `archive/week-changelogs/<week-starting>/`.
3. Move all daily files (`state/week-changelog/YYYY-MM-DD-*.md`) to the archive path. HEADER.md is NOT moved — it gets rewritten in place.
4. Move every priorities fragment (`state/week-changelog/HEADER.priorities.*.md`) to the same archive path — the merged priorities for the closing week become historical record alongside the daily files that satisfied (or didn't) them. The new week starts with zero fragments; `/workweek-start` re-creates them per-writer as priorities are set.
5. Create `archive/review-trail/<week-starting>/` and move `state/review-trail/*.json` (excluding `.gitkeep` and any `.weekly-reviewer-scopes-*.json` shard) into it. `.gitkeep` stays so the dir remains tracked; transient `.weekly-reviewer-scopes-*.json` shards are deleted, not archived (`rm -f state/review-trail/.weekly-reviewer-scopes-*.json`). **Archival ordering matters:** must run AFTER Step 7 consumes the trail (Step 13 is correctly downstream).

6. Write a fresh HEADER.md with the released version and a cleared `Last /workweek-start:` line:

```markdown
# Week Changelog

<!-- Directory convention: [see HEADER.md comment block] -->

**Week starting:** (not yet set — run /workweek-start to initialise)
**Prior week released:** vX.Y.Z (commit <merge-sha>, YYYY-MM-DD)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):** see `HEADER.priorities.*.md` fragments — none yet; run /workweek-start to set priorities.
```

7. Commit everything (the fragment glob is covered by the `state/week-changelog/` directory add — no separate pathspec needed):
```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
git add -- state/week-changelog/ archive/week-changelogs/<week-starting>/ \
           state/review-trail/ archive/review-trail/<week-starting>/
git commit -m "chore(workweek-complete): archive week <week-starting>, reset changelog + review-trail vX.Y.Z"
git push origin "$("$_cc_root/bin/coordinator-current-branch")"
```

---

## Step 13.5: Project Post-Ceremony Command Hook

Advisory, non-blocking. Runs the repo's own opt-in `workweek_complete_post_command:` (declared in `coordinator.local.md`) via the shared `coordinator-ceremony-hook.sh` helper, so a consumer repo can publish its settled weekly state (analog of the daily publish at `/workday-complete` Step 10.5) without a bespoke terminal step. Placed after Step 13 (week-changelog + review-trail archived and reset — the weekly settled state) and before Step 14 (Final Summary), so the hook line is available to fold into the summary template.

A failing or unconfigured hook NEVER fails the ceremony — see `docs/plans/2026-07-08-ceremony-post-command-hook-seam.md` § "The seam".

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
# Review: code-reviewer (F1) — guard is defensive-only against the helper-script-absent
# (install-drift) case; the helper itself is contracted always-exit-0, so this `||` fires
# only if `bash <path>` itself can't find/exec the script (e.g. exit 127).
_HOOK_OUT="$(bash "$_cc_root/bin/coordinator-ceremony-hook.sh" workweek-complete)" \
  || echo "[workweek-complete] WARN: ceremony-hook exited non-zero (non-blocking)" >&2
if [ -n "$_HOOK_OUT" ]; then printf '%s\n' "$_HOOK_OUT"; fi
```

---

## Step 14: Final Summary

```
## Workweek Complete

**Week:** YYYY-MM-DD to YYYY-MM-DD (D days, N commits)
**Shipped:** [list of shipped workstreams]
**Version:** vX.Y.Z
**Release notes:** archive/release-notes/YYYY-MM-DD-vX.Y.Z.md
**Validation:** [pass / failures described]
**Docs updated:** [/update-docs completed]
**Improvement queue:** [K entries processed / no triage needed]
**Bug backlog:** [N open P1/P2 items — /bug-blitz proposed/deferred/not needed / file absent]
**Code stats:** [summary or "scc not available"]
**ShellCheck:** [clean / N issues fixed]
**Code-review gate:** [BLOCKED|WARN|OK] — convergent: N — code-semantics (N chunks) / security / deps / tests summary
**Arch pass (Step 7.5):** [N arch-tier candidates surfaced / no arch-tier signal this week]
**Arch audit fold (Step 7.6):** [folded targeted-on-diff audit — N spinoff candidates surfaced / fresh — no fold / staleness UNKNOWN]
**Tracker:** [N workstreams updated]
**Merged to main:** [yes — PR #N / blocked: reason]
**Week-changelog:** archived to archive/week-changelogs/<week-starting>/, HEADER.md reset
**Post-ceremony hook:** [only rendered when Step 13.5's hook produced output, e.g. "ran <redacted-cmd> (exit 0)"]
**Next:** run /workweek-start to set priorities for the new week
```

---

### What This Does NOT Do

- **Auto-fire.** PM-invoked; `/workday-complete` surfaces the staleness signal.
- **Re-author from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 11 delegates to `/merge-to-main`.
- **Delete release notes or handoffs.** Only daily changelog files are archived.
- **Touch trail records via `/distill` or `/update-docs/handoff-archival`.** Trail JSON is archived in Step 13 only — never by handoff archival.

### Relationship to Other Commands

- **`/workday-complete`** — daily wrap; feeds the changelog this command reads.
- **`/workweek-start`** — weekly orient; detects Step 13's HEADER reset and re-inits.
- **`/merge-to-main`** — invoked in Step 11.
- **`/update-docs`** — invoked in Step 3.
- **`check-weekly-staleness.sh`** — staleness nudge used by `/workday-complete`.
- **`check-arch-audit-staleness.sh`** — reads `Last targeted audit` clock; consumed by Step 7.6 (STALE >10 days → auto-fold).
- **`/architecture-audit`** — folded in by Step 7.6 when stale; writes `Last targeted audit`.
- **`/architecture-survey`** — full breadth survey (PM-invoked only); writes `Last full audit`.
