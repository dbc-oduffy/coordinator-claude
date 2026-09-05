---
title: "Weekly Gate Architecture — Steps 7, 7.5, 7.6"
kind: wiki
created: 2026-05-28
---

# Weekly Gate Architecture — Steps 7, 7.5, 7.6

> Architecture and rationale for the weekly code-review gate and advisory passes in `/workweek-complete`.
> Procedural steps (what the EM actually runs) live in `commands/workweek-complete.md` §§ Step 7 / 7.5 / 7.6.
>
> Plans: `docs/plans/2026-05-06-parallel-code-review-weekly-gate.md`;
> restructure: `docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md`.

---

## Step 7 — Parallel Chunk-Review Gate

### Trail-reading and scope computation

Before invoking `parallel-code-review`, the EM computes the narrowed **code-semantics** scope from the workstream-complete review trail. The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) always see the full week diff — only the code-semantics lens narrows, and that narrowed scope is then **chunked** into N disjoint file-scope partitions, one Sonnet `code-reviewer-weekly` per chunk.

> The helper's JSON keys are role slugs, not persona names (producer-side, claude-klabauter `a78271b1a`, no back-compat shim): the `staff_eng` SHA set is the code-semantics chunking input and `staff_eng_seam_files` additionally feeds the Staff Engineer's Layer-2 pass in Step 7.5.

### Trail helper contract

`"$PYTHON_BIN" "${PYTHON_ARGS[@]}" "$_cc_claude_klabauter/coordinator/lib/workweek-trail-scope.py"` (naked-Python trampoline over `coordinator_core.ops.workweek_trail_scope`, renamed to its native `.py` extension in the 2026-07-21/22 bash-clean-slate residual migration, now claude-klabauter resident post-b644d5a9 — guarded trusted-root resolve; see CLAUDE-PLUGIN-ROOT-SOURCE-GUARD, `coordinator/docs/wiki/coordinator-tripwires/draft-plan-aging.md`) — fail-loud; reads `state/week-changelog/HEADER.md`, globs `state/review-trail/*.json`, writes a session-keyed `state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json` shard.

The helper parses `Week starting:` from HEADER.md, filters trail records to the current week by filename date-prefix, then computes:

- `reviewed_set` — union of all segment SHA sets
- `unreviewed_set` — weekly `origin/main..HEAD` SHAs minus `reviewed_set`
- `cross_segment_seams` — file paths touched by ≥2 distinct trail segments (pairwise intersection)
- `staff_eng_scope` — `unreviewed_set ∪ seam_SHAs`

Output JSON shape: `{ "staff_eng": [sha...], "staff_eng_seam_files": [path...], "mechanical_workers": "full" }`. Fail-loud on missing HEADER.md, unparseable `Week starting:` date, missing `sha_range`, or any git subprocess error. Implementation: claude-klabauter `coordinator/lib/workweek-trail-scope.py`.

### Coverage-gate batching hazard — single-commit trail records get under-credited

*DoE-claude. [universal]*

The review-coverage-gate DAG mode delegates to `coordinator_core` `build_reviewed_set` (`coverage.py`), which **batches all trail `sha_range`s into one** `git rev-list A^..A B^..B …` call. With multiple *single-commit* ranges drawn from interleaved history, git's combined positive/negative refs exclude every commit but the newest — the batched result reads 1 where the per-record union is 6. The correct per-record fallback only fires on batch `rc != 0`, so a clean-but-wrong batch silently under-credits coverage and the gate reports `UNCOVERED` against work that was in fact reviewed.

**Workaround (chain-terminal cap only):** after writing per-commit trail records, if the gate reports `UNCOVERED`, verify the per-record union actually covers the chain, then set `COORDINATOR_OVERRIDE_COVERAGE_GATE=1` and report to claude-klabauter. **Real fix (engine-tier):** `coverage.py` must union per-record, not batch — a claude-klabauter-owned `coordinator_core` bug (`CLAUDE.md` § Subject-matter routing — engine-tier bugs route to claude-klabauter Python reimplementation), not a DoE bash patch.

### Gate structure

The `parallel-code-review` skill dispatches **N Sonnet `code-reviewer-weekly` chunks + 3 mechanical workers** (security-audit-worker + dep-cve-auditor + test-evidence-parser) in parallel into a no-rewrite synthesizer. It emits a structured `BLOCKED | WARN | OK` verdict.

**the Staff Engineer is NOT in this gate** — they run a separate architecture pass in Step 7.5 (DECISION D3). The step-7 gate is the only hard merge block. The brief references `state/review-trail/.weekly-reviewer-scopes.json` so the synthesizer narrates 'code-semantics chunks scoped to gap+seams; mechanical workers full diff' in the verdict.

### Verdict handling

- **BLOCKED:** halt before Step 8 (Tracker Reconciliation) and Step 9 (Release Notes). Surface verdict line and findings-dir path to PM. Do NOT proceed to release notes or merge until either the issue is fixed and the gate is re-run, or `--force` bypass is granted.
- **WARN:** include the verdict line in the release-notes draft (Step 9); proceed.
- **OK:** proceed silently; verdict line still goes into the release-notes draft for the record.
- **OK (code-semantics trail-covered, mechanical clean):** when the trail covers all weekly code-semantics-tier scope AND no findings from any worker. Informational subvariant of OK; the dispatch still ran.

### Skip rules

Full detail in the `parallel-code-review` skill body: skip entirely on <10 lines or internal-only paths; skip the code-semantics chunk reviewers on doc-only weeks (mechanical workers still run); skip the entire gate on plan-only weeks; `--force` escape passes through from `/workweek-complete --force`.

**Rule 5 — already-reviewed-span (EM-judgment, not auto-fired).** The weekly gate is built for one week's *incremental* diff. On a large catch-up span it re-reviews code already reviewed at `/workstream-complete` time, and does so with *strictly less* context — the original reviews ran with the plan doc, chunk briefs, and acceptance criteria in the reviewer's window; the weekly chunk-reviewer sees a raw file slice with none of that. The failure mode is compounded by seam explosion: `staff_eng_seam_files` is every file touched by ≥2 segments, and a multi-week span has massive cross-workstream file overlap, so the seam set balloons (cockpit's first weekly in ~2.5 weeks: 1970 commits → 2960 seam files) even though `unreviewed_set` is near-empty. On such a span the EM MAY either **skip the chunk gate** (record `incrementally-reviewed`, naming the week's `state/review-trail/*.json` records as the evidence trail) or **narrow it to the genuinely un-reviewed subset** (`unreviewed_set` — weekly-diff SHAs with no trail coverage; drop the seam-only contribution to `staff_eng`). This is a deliberate EM call because the trigger is *disproportionality on an already-reviewed span*, which the mechanical `git diff` predicates of Rules 1–4 cannot cleanly threshold. Origin: `cross-repo/inbox/2026-07-13-example-cockpit-repo-em-workweek-gate-overkill-on-large-reviewed-spans.md`.

---

## Step 7.5 — the Staff Engineer Layer-2 Architecture Pass

### Design rationale

The Staff Engineer comes off the diff-level gate (Step 7) and runs at architecture altitude instead. This step is **decoupled from the merge decision** — the mechanical gate (Step 7) is the only hard block. An architecture-altitude concern surfaces to the PM as a *recommendation*; it never silently blocks merge (DECISION D3).

### Run condition

**Run only when there is something architectural to read.** Skip Step 7.5 (note "no arch-tier signal this week") if ALL of: `arch_tier_candidates` is empty AND `convergent_findings` is empty AND the seam-file set is empty AND the week's daily strategic-observer trail carries no `for-weekly-arch-review` flags.

**Large already-reviewed span — default-off, EM-discretion fire.** On the Step 7 Rule 5 condition (large catch-up, ballooning seam set, commits dominated by review-trail verdicts) the seam-file set alone MUST NOT auto-fire this pass: seam count scales with span size, not architectural risk, so a 2960-seam-file span would trigger a disproportionate Opus pass for no signal. Treat the seam-file trigger as inert on such a span and default the step OFF; the EM fires it at discretion only when cross-workstream drift is genuinely plausible. This is a discretion gate, not a removal — the arch-pass keeps its unique value (it catches CROSS-workstream drift per-workstream reviews structurally cannot see). Note that when Step 7 took the Rule 5 skip, `arch_tier_candidates` / `convergent_findings` are absent (no `synthesis.json`), so on a skipped span only the seam-file (now inert) and DSR-flag triggers remain.

### Inputs

When the run condition is met, dispatch the Staff Engineer (`coordinator:staff-eng`, Opus) with five inputs:

1. **Changelog digest** — the week's `state/week-changelog/*.md` daily summaries (what shipped, at a glance).
2. **`arch_tier_candidates`** — from `$FINDINGS_DIR/synthesis.json`; the findings the Sonnet chunk reviewers flagged `escalate_to_architecture: true`. This is the explicit "a Sonnet thought this needed Opus judgment" feed.
3. **`convergent_findings`** — from `synthesis.json`; issues independently flagged by ≥2 lenses. Convergence is a cross-cutting signal N independently-scoped Sonnets cannot self-produce.
4. **Seam-file set** — `staff_eng_seam_files` from `state/review-trail/.weekly-reviewer-scopes.json` (the actual cross-segment integration surface computed by `workweek-trail-scope.py`). The integration surface is exactly where multi-session erosion lives.
5. **Daily strategic-observer trail** — the week's accumulated daily paper trail authored *for* this pass: the `## Strategic Review (Sonnet daily observer)` sections across `archive/daily-summaries/*.md` and the `state/debt-backlog/*.yaml` entries tagged `for-weekly-arch-review` (the debt-backlog is a directory of per-entry YAML, not a flat markdown file — see `docs/wiki/debt-backlog-schema.md`). The daily Sonnet observer (workday-complete Step 4c) flags candidates; this is where future-the Staff Engineer adjudicates them. A flag here is signal a single day's Sonnet thought worth an Opus look — treat it like input #2, but accumulated across the week rather than from the chunk reviewers.

### Output and disposition ladder

**the Staff Engineer's output:** a tech-debt / refactor-consolidate / YAGNI architectural read. The Staff Engineer **produces candidates only — never auto-authors spinoff files** (spinoff is PM-gated, `/spinoff` Step 0). Read-only at this step.

**EM routes the Staff Engineer's candidates down the disposition ladder** (same ladder as the architecture-audit skill, Strand 3a):
- **Trivial / tradeoff-free AND non-structural** (one-liners, mechanical corrections, no module/interface/cross-system boundary touch) → EM dispatches an executor immediately; ordinary EM remit, no PM gate.
- **Mid-size cluster** → EM groups into ONE bundled spinoff candidate (`Candidate spinoff: <slug> — <topic>. Authorize?`), surfaced to PM.
- **Large / genuinely structural** → standalone spinoff candidate or escalate to `/plan`.

Any boundary-touching finding (module move, interface change, cross-system surface) is ineligible for the trivial path regardless of line count — it routes to a bundled/standalone spinoff candidate so it stays recorded.

**Surface the Staff Engineer's spinoff candidates to the PM alongside the release-notes draft (Step 9)** — they are part of the weekly read-out, not a merge blocker.

### Accepted loss

**Residual accepted loss (architectural OOS):** a cross-cutting erosion spanning multiple chunks that no individual Sonnet flags as architectural — and so never appears in `arch_tier_candidates` — is not caught at the weekly gate. Accepted because workstream-complete covers within-session integration, the seam set + `convergent_findings` substantially close the gap, and an Opus full-diff read at weekly cadence is not justified by frequency.

---

## Step 7.6 — Architecture Audit Staleness Fold

### Two triggers

The rotational architecture audit (`/architecture-audit`) is easy for the PM to forget. Step 7.6 makes it self-enforcing on two triggers:

**Hard floor (automatic):** `python "$_cc_claude_klabauter/coordinator/bin/check-arch-audit-staleness.py"` (guarded trusted-root resolve; see CLAUDE-PLUGIN-ROOT-SOURCE-GUARD, `coordinator/docs/wiki/coordinator-tripwires/draft-plan-aging.md`; claude-klabauter resident post-b644d5a9) reads the `Last targeted audit` clock from `state/health-ledger.md`:
- `STALE` (>10 days, or never targeted-audited with a ledger present) → auto-fold a **targeted-on-diff** audit this cycle.
- `FRESH` → no fold.
- `UNKNOWN` (no ledger / unparseable) → do NOT auto-fold; note it and move on.

**EM discretion:** even when the clock reads `FRESH`, the EM MAY trigger the targeted audit when the week's churn warrants it (heavy multi-system churn — a large refactor landing across several systems — even on a fresh calendar).

### Scope when folded (DECISION D6)

Audit only the systems the week's diff actually touched (read diff-touched paths from the trail / `git diff --name-only origin/main...HEAD` mapped through `docs/architecture/file-index.md`), NOT a full atlas rebuild. The full breadth survey stays a deliberate PM invocation of `/architecture-survey`.

### Disposition

The folded audit **never edits code** — it packages findings as spinoff candidates down the disposition ladder (immediate executor for trivial+non-structural / bundled spinoff candidate / standalone-or-plan for large) and writes only the `Last targeted audit` clock + atlas metadata. Surface its spinoff candidates to the PM **alongside the Staff Engineer's Step 7.5 candidates and the release-notes draft (Step 9)** — a single architecture-candidate read-out. The fold does NOT block merge.
