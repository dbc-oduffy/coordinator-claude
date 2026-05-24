---
name: workweek-complete
description: Weekly release ceremony — validate, update docs, cut release notes, version bump, merge to main, archive
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: ""
---

# Workweek Complete — Weekly Release Ceremony

PM-invoked, release-grade close. Reads the week-changelog as the canonical record of what shipped — does NOT reconstruct the week from `git log`. Heavy steps dropped from `/workday-complete` live here: `/update-docs`, ShellCheck, improvement-queue triage, scc, version bump, and merge.

**Design contract:** the week-changelog is the ledger. The weekly ceremony reads it, validates against it, and archives it. Release notes are drafted from it, not re-derived.

---

## Step 1: Read Week-Changelog — PM Confirmation Gate

Glob `tasks/week-changelog/*.md` (daily files, sorted by filename). Read HEADER.md and all daily files.

Surface to PM:

```
Week covers: D days (YYYY-MM-DD to YYYY-MM-DD)
Commits: N (range: <oldest-sha>..<newest-sha>)
Implemented workstreams: <list from Plans touched: implemented fields>
Blockers: <list or "none">
Priorities met: <from HEADER.md priorities vs. implemented plans>
```

Ask: _"Does this summary match your recollection? Proceed with release ceremony?"_

**Wait for PM confirmation before continuing.** This is the single explicit PM gate before the irreversible steps.

---

## Step 2: Full Validation (blocking)

Run the complete validation stack:

```bash
python .github/scripts/run-all-checks.py
node --test ~/.claude/plugins/coordinator/tests/plugin-ecosystem/run.js
```

Any blocking failure → stop and report. Fix before proceeding. Do not proceed to Step 3 on a failing validation.

---

## Step 3: Run `/update-docs`

Full multi-phase docs sweep. Commits and pushes to the current branch.

Wait for completion before proceeding.

---

## Step 4: Improvement-Queue Triage

Read `~/.claude/tasks/coordinator-improvement-queue.md`. Schema (DR-056 amended 2026-05-17) is main-line-only:
- **Main line:** `- YYYY-MM-DD | <source-repo> | <source-file>:<line> | <summary> | proposed target: <target>`
- **Optional recurrence suffix:** ` [recurring: N]` appended to the main line when N ≥ 1.

Note the oldest entry date and total active count.

**Triage triggers (any condition):**
- ≥ 5 active entries, OR
- Oldest entry is > 14 days ago, OR
- Any entry carries `[recurring: ≥3]` on its main line (recurring-without-action threshold).

If triggered:
1. Read the queue entries.
2. **Prioritize recurring-without-action items first** (any with `[recurring: ≥3]`).
3. For each prioritized entry, dispatch a small executor per the `proposed target` field.
4. Verify applied entries; delete the resolved entries from the queue (main-line `git rm`-equivalent — do NOT annotate as resolved).
5. Commit subject names each closed entry (`workweek triage: closed <id-or-summary>, <id-or-summary>`).
6. If > 15 total entries to triage, treat as a `/staff-session`-style multi-executor sweep.

If not triggered: note in summary — _"Improvement queue: K entries, oldest YYYY-MM-DD — no triage needed."_

**Write-time discipline (DR-056 amended 2026-05-17):** Append NEW entries as a single main line — no `recurring:` or `resolution:` sub-lines. The pruner (`/update-docs` Phase 11i) strips trivial sub-lines on every run, so writing them is wasted ceremony. Closure-log sections (`## History`, `## Resolved`, `## Processed`, `## Closed`, `## Done`, `## Archive`, `## Closeout`) are also stripped — do NOT create them.

**Prior-art sidecar scan (judgment-based):** While reading the improvement queue, also scan recent `docs/plans/**/*.prior-art-check*.md` sidecars for Conflicts dispositioned as `override-and-document`, `update-prior-art`, or `both`. Any wiki cited ≥3 times across those dispositions is a candidate for revision — surface to PM. Repeated `update-prior-art` against the same wiki is the strongest staleness signal (two plans correcting the same entry within a quarter ⇒ the entry is structurally stale, not just occasionally wrong). Full doctrine: `docs/wiki/prior-art-checker.md` § "Bidirectional resolution" and § "False-positive arbitration — feedback loop on wiki quality."

**Bug-backlog depth check:** Read `tasks/bug-backlog.md` if it exists. Count open items in P1 and P2 tables. (Closure-log sections like `## History` / `## Resolved` are stripped by `/update-docs` Phase 11i — if any survive in your read, count them as zero open items.) If the open count is ≥10, propose running `/bug-blitz` as part of this triage session — surface the count and ask PM: _"Bug backlog has N open P1/P2 items — run /bug-blitz now or defer?"_ If not triggered: note in summary — _"Bug backlog: N open P1/P2 items — no blitz needed."_ If the file is absent: skip silently.

---

## Step 4b: Install OOM Reproducer Freshness Check

If `bin/check-install-reproducer-fresh.sh` exists in the repo root:

```bash
bash bin/check-install-reproducer-fresh.sh
```

- **Exit 0 (marker fresh, < 24h):** Print notice; no test run; proceed to Step 5.
- **Exit 0 (test ran and passed):** Print pass notice; proceed to Step 5.
- **Exit 1 (test failed):** Halt and report. Do NOT proceed to Step 5 (scc), Step 6 (ShellCheck), or beyond until either the OOM reproducer passes or PM grants `--force` bypass.

This check is informational when the marker is fresh; it is a **blocking gate** only when the test is actually run and fails.

---

## Step 4c: UBT Pending-Record Merge Gate (UE plugin work only)

Scan for `*.ubt-compile.pending.json` records in `tasks/review-trail/` with no `.resolved.json` sibling:

```bash
UNRESOLVED=$(find tasks/review-trail -maxdepth 1 -name "*.ubt-compile.pending.json" -type f 2>/dev/null | while read -r f; do
  base="${f%.pending.json}"; [[ ! -f "${base}.resolved.json" ]] && echo "$f"
done)
```

Passes silently when none found. If any are unresolved, halt and emit their `sha_range` values with remediation: _"run /workday-complete on the affected day(s) or override with `COORDINATOR_OVERRIDE_UBT_GATE=1`."_ Non-UE repos have no pending records; this step passes silently. Mirrors Step 4b pattern.

---

## Step 4d: Skill Description Length Advisory

```bash
# Advisory only — never blocks. Both findings AND script crashes surface to stdout
# where the EM running the ceremony can fold them into the week's summary.
set +e
_DESC_OUT=$(${CLAUDE_PLUGIN_ROOT}/bin/check-description-length.sh 2>&1)
_DESC_RC=$?
set -e
echo "---"
echo "description-length advisory (rc=$_DESC_RC):"
echo "$_DESC_OUT"
echo "---"
# _DESC_RC is never propagated to ceremony exit
```

Informational. Note over-budget skills in the weekly summary (Step 1); address next session. A non-zero rc with no findings indicates a script crash — investigate out-of-band.

---

## Step 4e: Owner-File Invariant Lint Advisory

Applies only when `scripts/lint-owner-file-invariants.py` exists in the repo root — projects without the §1a "Owner-File Invariant Paragraph" convention (see `docs/wiki/rag-bait-conventions.md` §1a) pass silently.

```bash
# Advisory only — never blocks. Surfaces drift: owner files in scripts/owner_files.yaml
# that have lost or never had their "Invariant —" paragraph in the first 3000 chars.
if [[ -f scripts/lint-owner-file-invariants.py ]]; then
  set +e
  _LINT_OUT=$(python scripts/lint-owner-file-invariants.py 2>&1)
  _LINT_RC=$?
  set -e
  echo "---"
  echo "owner-file-invariant advisory (rc=$_LINT_RC):"
  echo "$_LINT_OUT"
  echo "---"
  # _LINT_RC is never propagated to ceremony exit
fi
```

Informational. Non-zero rc means a file in `scripts/owner_files.yaml` lost its `Invariant —` marker (rename, refactor, or accidental docstring rewrite). Note in the weekly summary; address next session. Fail-soft by design — convention shipped 2026-05-17, weekly drift detection is the right friction level. Pattern mirrors Step 4d; cadence doctrine: `docs/wiki/workday-workweek-cadence.md` lines 56–75 (weekly-only advisories).

---

## Step 4f: enabledPlugins Drift Audit Advisory

*Lesson 2026-05-14 — `enabledPlugins: true` entries drift silently across repos.* Plugin installs write `true` lines without review; cross-contamination compounds over months. **Per-repo advisory** — audits the current repo's `enabledPlugins` against its `project_type` / `stack_tags` from `.claude/coordinator.local.md` or `~/.claude/tasks/repo-registry.md`.

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

Advisory only — never blocks. `project_type: meta` short-circuits (all plugins intentional). When drift is reported, **full uninstall requires 3 steps** (removing the `enabledPlugins` line alone leaves a partial-install state): (1) remove entry from every project's `.claude/settings.json`; (2) remove from `~/.claude/plugins/installed_plugins.json`; (3) `rm -rf ~/.claude/plugins/cache/<marketplace>/<plugin>/`. EM surfaces the recipe; PM authorizes.

---

## Step 5: scc Snapshot

If `scc` is available (`which scc` or `~/bin/scc`):
```bash
scc --no-complexity --no-cocomo --no-duplicates --sort code
```

Record the compact summary (total lines, top 5 languages) in `tasks/code-stats-history.md` under a `## YYYY-MM-DD` heading (append; create the file if it doesn't exist). Weekly trend is the signal; daily delta is noise.

If `scc` is not installed: note in summary — _"scc not available — install for weekly code stats."_

---

## Step 6: ShellCheck Sweep

```bash
git ls-files '*.sh' | while read -r f; do
  tr -d '\r' < "$f" | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|$f:|g"
done
```

- **Issues found:** report and offer to fix. Most findings are quick mechanical fixes; fix what's straightforward, flag behavior-changing items for PM review.
- **Clean:** report _"ShellCheck: all .sh files clean."_
- **Not installed:** note in summary.

---

## Step 7: Parallel Code-Review Gate

### Step 7 prelude — trail-reading and scope computation

Before invoking `parallel-code-review`, compute the narrowed **code-semantics** scope from the session-end review trail. The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) always see the full week diff — only the code-semantics lens narrows, and that narrowed scope is then **chunked** into N disjoint file-scope partitions, one Sonnet `code-reviewer-weekly` per chunk. (The helper's JSON keys are still named `patrik`/`patrik_seam_files` for back-compat; post-restructure the `patrik` SHA set is the code-semantics chunking input and `patrik_seam_files` additionally feeds the Staff Engineer's Layer-2 pass in Step 7.5.)

Run the helper (fail-loud; reads `tasks/week-changelog/HEADER.md`, globs `tasks/review-trail/*.json`, writes `tasks/review-trail/.weekly-reviewer-scopes.json`):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/workweek-trail-scope.sh"
```

**Contract:** The helper parses `Week starting:` from HEADER.md, filters trail records to the current week by filename date-prefix, then computes:
- `reviewed_set` — union of all segment SHA sets
- `unreviewed_set` — weekly `origin/main..HEAD` SHAs minus `reviewed_set`
- `cross_segment_seams` — file paths touched by ≥2 distinct trail segments (pairwise intersection)
- `patrik_scope` — `unreviewed_set ∪ seam_SHAs`

Output JSON shape: `{ "patrik": [sha...], "patrik_seam_files": [path...], "mechanical_workers": "full" }`. Fail-loud on missing HEADER.md, unparseable `Week starting:` date, missing `sha_range`, or any git subprocess error. Implementation: `coordinator/lib/workweek-trail-scope.sh`.

---

After ShellCheck (Step 6) and before Tracker Reconciliation (Step 8), run the parallel code-review gate on the week's diff against `origin/main`.

Read `~/.claude/plugins/coordinator/skills/parallel-code-review/SKILL.md` and execute its steps. The skill snapshots the diff, chunks the narrowed code-semantics scope into N disjoint file-scope partitions, dispatches **N Sonnet `code-reviewer-weekly` chunks + 3 mechanical workers** (security-audit-worker + dep-cve-auditor + test-evidence-parser) in parallel into a no-rewrite synthesizer, and emits a structured `BLOCKED | WARN | OK` verdict. **the Staff Engineer is NOT in this gate** — he runs a separate architecture pass in Step 7.5. The brief that invokes parallel-code-review references `tasks/review-trail/.weekly-reviewer-scopes.json` so the synthesizer narrates 'code-semantics chunks scoped to gap+seams; mechanical workers full diff' in the verdict.

- **BLOCKED:** halt before Step 8 (Tracker Reconciliation) and Step 9 (Release Notes). Surface verdict line and findings-dir path to PM. Do NOT proceed to release notes or merge until either the issue is fixed and the gate is re-run, or `--force` bypass is granted.
- **WARN:** include the verdict line in the release-notes draft (Step 9); proceed.
- **OK:** proceed silently; verdict line still goes into the release-notes draft for the record.
- **OK (code-semantics trail-covered, mechanical clean):** when the trail covers all weekly code-semantics-tier scope AND no findings from any worker. Informational subvariant of OK; the dispatch still ran.

**Skip rules** (full detail in the skill body): skip entirely on <10 lines or internal-only paths; skip the code-semantics chunk reviewers on doc-only weeks (mechanical workers still run); skip the entire gate on plan-only weeks; `--force` escape passes through from `/workweek-complete --force`.

**Plan:** `docs/plans/2026-05-06-parallel-code-review-weekly-gate.md`; restructure `docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md`.

---

## Step 7.5: the Staff Engineer Layer-2 — Architecture Pass (advisory, does NOT gate merge)

The Staff Engineer comes off the diff-level gate (Step 7) and runs at architecture altitude instead. This step is **decoupled from the merge decision** — the mechanical gate (Step 7) is the only hard block. An architecture-altitude concern surfaces to the PM as a *recommendation*; it never silently blocks merge (DECISION D3).

**Run only when there is something architectural to read.** Skip Step 7.5 (note "no arch-tier signal this week") if ALL of: `arch_tier_candidates` is empty AND `convergent_findings` is empty AND the seam-file set is empty. Otherwise dispatch the Staff Engineer (`coordinator:staff-eng`, Opus) with these four inputs:

1. **Changelog digest** — the week's `tasks/week-changelog/*.md` daily summaries (what shipped, at a glance).
2. **`arch_tier_candidates`** — from `$FINDINGS_DIR/synthesis.json`; the findings the Sonnet chunk reviewers flagged `escalate_to_architecture: true`. This is the explicit "a Sonnet thought this needed Opus judgment" feed.
3. **`convergent_findings`** — from `synthesis.json`; issues independently flagged by ≥2 lenses. Convergence is a cross-cutting signal N independently-scoped Sonnets cannot self-produce.
4. **Seam-file set** — `patrik_seam_files` from `tasks/review-trail/.weekly-reviewer-scopes.json` (the actual cross-segment integration surface computed by `workweek-trail-scope.sh`). The integration surface is exactly where multi-session erosion lives.

**the Staff Engineer's output:** a tech-debt / refactor-consolidate / YAGNI architectural read. The Staff Engineer **produces candidates only — he never auto-authors spinoff files** (spinoff is PM-gated, `/spinoff` Step 0). He is read-only at this step.

**EM routes the Staff Engineer's candidates down the disposition ladder** (same ladder as the architecture-audit skill, Strand 3a):
- **Trivial / tradeoff-free AND non-structural** (one-liners, mechanical corrections, no module/interface/cross-system boundary touch) → EM dispatches an executor immediately; ordinary EM remit, no PM gate.
- **Mid-size cluster** → EM groups into ONE bundled spinoff candidate (`Candidate spinoff: <slug> — <topic>. Authorize?`), surfaced to PM.
- **Large / genuinely structural** → standalone spinoff candidate or escalate to `/plan`.

Any boundary-touching finding (module move, interface change, cross-system surface) is ineligible for the trivial path regardless of line count — it routes to a bundled/standalone spinoff candidate so it stays recorded.

**Surface the Staff Engineer's spinoff candidates to the PM alongside the release-notes draft (Step 9)** — they are part of the weekly read-out, not a merge blocker.

**Residual accepted loss (architectural OOS):** a cross-cutting erosion spanning multiple chunks that no individual Sonnet flags as architectural — and so never appears in `arch_tier_candidates` — is not caught at the weekly gate. Accepted because session-end covers within-session integration, the seam set + `convergent_findings` substantially close the gap, and an Opus full-diff read at weekly cadence is not justified by frequency.

---

## Step 7.6: Architecture Audit Staleness Fold

The rotational architecture audit (`/architecture-audit`) is easy for the PM to forget. Make it self-enforcing here on **two triggers**:

**Hard floor (automatic):** run the staleness check:
```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/check-arch-audit-staleness.sh"
```
It reads the `Last targeted audit` clock from `tasks/health-ledger.md`. `STALE` (>10 days, or never targeted-audited with a ledger present) → auto-fold a **targeted-on-diff** audit this cycle. `FRESH` → no fold. `UNKNOWN` (no ledger / unparseable) → do NOT auto-fold; note it and move on.

**EM discretion:** even when the clock reads `FRESH`, the EM MAY trigger the targeted audit when the week's churn warrants it (heavy multi-system churn — a large refactor landing across several systems — even on a fresh calendar).

**Scope when folded — targeted-on-diff (DECISION D6):** audit only the systems the week's diff actually touched (read diff-touched paths from the trail / `git diff --name-only origin/main...HEAD` mapped through `docs/architecture/file-index.md`), NOT a full atlas rebuild. The full breadth survey stays a deliberate PM invocation of `/architecture-survey`. Read `${CLAUDE_PLUGIN_ROOT}/skills/architecture-audit/SKILL.md` and run it scoped to the diff-touched systems.

**Disposition:** the folded audit **never edits code** — it packages findings as spinoff candidates down the disposition ladder (immediate executor for trivial+non-structural / bundled spinoff candidate / standalone-or-plan for large) and writes only the `Last targeted audit` clock + atlas metadata. Surface its spinoff candidates to the PM **alongside the Staff Engineer's Step 7.5 candidates and the release-notes draft (Step 9)** — a single architecture-candidate read-out. The fold does NOT block merge.

If skipped (FRESH and no EM churn trigger): note _"Architecture audit: fresh (Last targeted audit within 10d) — no fold."_ in the summary.

---

## Step 8: Tracker Reconciliation

Read `docs/project-tracker.md` (if it exists). For each workstream that appears in the week's `Plans touched: implemented` fields, verify the tracker status is updated to reflect completion. Fix in place.

Report: _"Tracker reconciliation: N workstreams updated."_

---

## Step 8.5: LoE High-Water Check — MANDATORY Before Step 9

**Purpose:** Surface any XL chain-terminal completion entries from the past week to the PM before release notes are drafted. This ensures large chains are explicitly acknowledged in the weekly summary, not silently folded into Other bucket prose.

> **This step is MANDATORY.** Do NOT proceed to Step 9 without completing it. A missing LoE check means large-scope work goes unacknowledged in the PM summary — the Phase 2 not-surveillance guarantee depends on this weekly surface point.

### 8.5.1 Query chain-terminal XL entries

```bash
bin/query-completions --since "7d" \
  --where "chain_terminal=true" \
  --where "chain_loe.tshirt=XL" \
  --format json
```

Alternatively, using the lower-level primitive:

```bash
bin/query-records --type completion \
  --since "7d" \
  --where "chain_terminal=true AND chain_loe.tshirt IN (XL)" \
  --format json
```

**Single-session XL entries** (no `chain_loe`, just `loe.tshirt: XL`) are surfaced separately by running the query a second time with `--where "loe.tshirt=XL AND chain_terminal=true"`. Union both result sets in the PM summary — the doctrine surfaces XL effort regardless of whether it came from one big session or aggregated across a chain.

### 8.5.2 Surface to PM

**If one or more XL chain-terminal entries are returned:**

For each entry, surface to the PM in the weekly summary with:
- `title:` — what was shipped
- `chain:` — the plan/handoff slug identifying the chain
- `chain_loe.sessions:` — how many sessions the chain spanned (if `chain_loe` block is present)
- `chain_loe.tshirt:` — aggregate t-shirt size at chain level (if present); else `loe.tshirt` for single-session XL entries
- Date span (earliest `created:` in the chain to this entry's `created:`)

Format in the PM summary:

```
**XL chain-terminal entries this week:**
- "<title>" — chain: <chain-slug>, <N sessions>, <date-start> to <date-end> [chain-level XL]
- "<title>" — single-session XL, <date>
```

**If the query returns zero entries:**

Note explicitly: _"No XL chain-terminal entries this week."_

Do NOT silently omit this note — its absence would be indistinguishable from a skipped step.

### 8.5.3 Proceed to Step 9

After surfacing (or noting absence), proceed to Step 9. No PM gate required here — this is informational surfacing, not a release blocker. The PM may choose to promote an XL entry to Highlights in the editorial bucketing step.

---

## Step 9: Editorial Bucketing + Release Notes Draft — PM Review Gate

**Purpose:** Convert per-entry completion records into an editorially-bucketed pending-release file, then draft human-readable release notes from it.

### 9.0 Ensure output directory exists

```bash
mkdir -p tasks/week-changelog/
```

Idempotent. Must run before any write to this path.

### 9.1 Query the week's completion entries

```bash
query-completions --since "7d" --where "status=pending-release" --format json
```

Collect all entries with `status: pending-release` from the past 7 days. If the query returns zero entries, skip to Step 9.4 and write an empty-week note.

### 9.2 Dispatch Sonnet editorial worker

Dispatch a Sonnet worker with the entry corpus. The worker assigns each entry to exactly one bucket and writes `tasks/week-changelog/YYYY-MM-DD-pending-release.md`.

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

EM override permitted for any entry — state overrides explicitly in the dispatch.

**Worker output format** (`tasks/week-changelog/YYYY-MM-DD-pending-release.md`):

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

Empty buckets: include the `## Heading` with `_none this week_`. Each entry cites its source file. WARN verdict from Step 7 goes verbatim under `_Code-review gate verdict:_`.

### 9.3 Worker writes pending-release file

Worker writes to `tasks/week-changelog/YYYY-MM-DD-pending-release.md`. Verify the file exists and is non-trivial before proceeding.

### 9.4 Draft release notes as thin wrapper

Read `tasks/week-changelog/YYYY-MM-DD-pending-release.md`. Write `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md` as a human-readable wrapper over the pending-release buckets — do NOT re-author; format for the reader:

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

Version is a placeholder (`vX.Y.Z`) until Step 10 confirms it.

Present to PM: _"Release notes drafted at `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md`. Bucketed: N Highlights, N Notable, N Other. Does this capture the week accurately?"_

**Wait for PM review.** The PM may request reclassifications or edits before proceeding. Update both `tasks/week-changelog/YYYY-MM-DD-pending-release.md` and the release-notes wrapper to reflect any PM adjustments.

---

## Step 10: Version Bump — PM Confirmation Gate

Propose a semver increment based on changelog content:
- **Major:** breaking change noted in any `Decisions:` field.
- **Minor:** new feature or new command shipped (`Plans touched: implemented` with new commands/skills).
- **Patch:** fixes, doc updates, refactors only.

Present to PM: _"Proposed: vX.Y.Z (rationale: [one line]). Confirm or adjust."_

**Wait for PM confirmation.** Update the release-notes filename and HEADER.md `Prior week released:` value to the confirmed version.

---

## Step 11: `/merge-to-main`

Invoke `/merge-to-main` only after PM has confirmed release notes (Step 9) and version (Step 10). Do NOT inline merge logic — the skill handles pre-merge test suite, PR creation, and merge.

---

## Step 12: Health Survey

Run the full health survey if available (e.g., `/health` or equivalent). Record output in `tasks/health-ledger.md` under today's date.

---

## Step 13: Reset Week-Changelog

Archive and reset the week's state:

1. Determine the current `Week starting:` date from HEADER.md — this is the archive path key.
2. Create `archive/week-changelogs/<week-starting>/`.
3. Move all daily files (`tasks/week-changelog/YYYY-MM-DD-*.md`) to the archive path. HEADER.md is NOT moved — it gets rewritten in place.
4. Create `archive/review-trail/<week-starting>/` and move `tasks/review-trail/*.json` (excluding `.gitkeep` and `.weekly-reviewer-scopes.json`) into it. `.gitkeep` stays so the dir remains tracked; transient `.weekly-reviewer-scopes.json` is deleted, not archived. **Archival ordering matters:** must run AFTER Step 7 consumes the trail (Step 13 is correctly downstream).

5. Write a fresh HEADER.md with the released version and a cleared `Last /workweek-start:` line:

```markdown
# Week Changelog

<!-- Directory convention: [see HEADER.md comment block] -->

**Week starting:** (not yet set — run /workweek-start to initialise)
**Prior week released:** vX.Y.Z (commit <merge-sha>, YYYY-MM-DD)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):**
- [ ] (run /workweek-start to set priorities)
```

6. Commit everything:
```bash
git add -- tasks/week-changelog/ archive/week-changelogs/<week-starting>/ \
           tasks/review-trail/ archive/review-trail/<week-starting>/
git commit -m "chore(workweek-complete): archive week <week-starting>, reset changelog + review-trail vX.Y.Z"
git push origin $(~/.claude/plugins/coordinator/bin/coordinator-current-branch)
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
**Next:** run /workweek-start to set priorities for the new week
```

---

### What This Does NOT Do

- **Auto-fire.** PM-invoked; `/workday-complete` surfaces the staleness signal.
- **Re-author from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 11 delegates to `/merge-to-main`.
- **Delete release notes or handoffs.** Only daily changelog files are archived.
- **Touch trail records via `/distill` or `/update-docs/handoff-archival`.** Per-session JSON written by `coordinator-write-review-trail.sh`, consumed by Step 7's prelude, archived here in Step 13 — never by handoff archival.

### Relationship to Other Commands

- **`/workday-complete`** — daily wrap; feeds the changelog this command reads.
- **`/workweek-start`** — weekly orient; detects Step 13's HEADER reset and re-inits.
- **`/merge-to-main`** — invoked in Step 11.
- **`/update-docs`** — invoked in Step 3; absorbed prior artifact-consolidation (Step 12) into Phase 8b 2026-05-06.
- **`bin/check-weekly-staleness.sh`** — informational script `/workday-complete` uses to nudge PM here.
- **`bin/check-arch-audit-staleness.sh`** — reads the `Last targeted audit` clock from `tasks/health-ledger.md`; consumed by Step 7.6 to decide whether to auto-fold a targeted-on-diff architecture audit (STALE = >10 days).
- **`/architecture-audit`** — the rotational audit folded in by Step 7.6 when stale; packages findings as spinoff candidates (never edits code), writes `Last targeted audit`.
- **`/architecture-survey`** — the full breadth survey (PM-invoked, not folded); writes `Last full audit`.
