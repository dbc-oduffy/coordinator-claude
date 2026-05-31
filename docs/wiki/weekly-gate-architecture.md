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

Before invoking `parallel-code-review`, the EM computes the narrowed **code-semantics** scope from the session-end review trail. The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) always see the full week diff — only the code-semantics lens narrows, and that narrowed scope is then **chunked** into N disjoint file-scope partitions, one Sonnet `code-reviewer-weekly` per chunk.

> The helper's JSON keys are still named `patrik`/`patrik_seam_files` for back-compat; post-restructure the `patrik` SHA set is the code-semantics chunking input and `patrik_seam_files` additionally feeds Patrik's Layer-2 pass in Step 7.5.

### Trail helper contract

`bash "${CLAUDE_PLUGIN_ROOT}/lib/workweek-trail-scope.sh"` — fail-loud; reads `tasks/week-changelog/HEADER.md`, globs `tasks/review-trail/*.json`, writes `tasks/review-trail/.weekly-reviewer-scopes.json`.

The helper parses `Week starting:` from HEADER.md, filters trail records to the current week by filename date-prefix, then computes:

- `reviewed_set` — union of all segment SHA sets
- `unreviewed_set` — weekly `origin/main..HEAD` SHAs minus `reviewed_set`
- `cross_segment_seams` — file paths touched by ≥2 distinct trail segments (pairwise intersection)
- `patrik_scope` — `unreviewed_set ∪ seam_SHAs`

Output JSON shape: `{ "patrik": [sha...], "patrik_seam_files": [path...], "mechanical_workers": "full" }`. Fail-loud on missing HEADER.md, unparseable `Week starting:` date, missing `sha_range`, or any git subprocess error. Implementation: `coordinator/lib/workweek-trail-scope.sh`.

### Gate structure

The `parallel-code-review` skill dispatches **N Sonnet `code-reviewer-weekly` chunks + 3 mechanical workers** (security-audit-worker + dep-cve-auditor + test-evidence-parser) in parallel into a no-rewrite synthesizer. It emits a structured `BLOCKED | WARN | OK` verdict.

**Patrik is NOT in this gate** — he runs a separate architecture pass in Step 7.5 (DECISION D3). The step-7 gate is the only hard merge block. The brief references `tasks/review-trail/.weekly-reviewer-scopes.json` so the synthesizer narrates 'code-semantics chunks scoped to gap+seams; mechanical workers full diff' in the verdict.

### Verdict handling

- **BLOCKED:** halt before Step 8 (Tracker Reconciliation) and Step 9 (Release Notes). Surface verdict line and findings-dir path to PM. Do NOT proceed to release notes or merge until either the issue is fixed and the gate is re-run, or `--force` bypass is granted.
- **WARN:** include the verdict line in the release-notes draft (Step 9); proceed.
- **OK:** proceed silently; verdict line still goes into the release-notes draft for the record.
- **OK (code-semantics trail-covered, mechanical clean):** when the trail covers all weekly code-semantics-tier scope AND no findings from any worker. Informational subvariant of OK; the dispatch still ran.

### Skip rules

Full detail in the `parallel-code-review` skill body: skip entirely on <10 lines or internal-only paths; skip the code-semantics chunk reviewers on doc-only weeks (mechanical workers still run); skip the entire gate on plan-only weeks; `--force` escape passes through from `/workweek-complete --force`.

---

## Step 7.5 — Patrik Layer-2 Architecture Pass

### Design rationale

Patrik comes off the diff-level gate (Step 7) and runs at architecture altitude instead. This step is **decoupled from the merge decision** — the mechanical gate (Step 7) is the only hard block. An architecture-altitude concern surfaces to the PM as a *recommendation*; it never silently blocks merge (DECISION D3).

### Run condition

**Run only when there is something architectural to read.** Skip Step 7.5 (note "no arch-tier signal this week") if ALL of: `arch_tier_candidates` is empty AND `convergent_findings` is empty AND the seam-file set is empty AND the week's daily strategic-observer trail carries no `for-weekly-arch-review` flags.

### Inputs

When the run condition is met, dispatch Patrik (`coordinator:staff-eng`, Opus) with five inputs:

1. **Changelog digest** — the week's `tasks/week-changelog/*.md` daily summaries (what shipped, at a glance).
2. **`arch_tier_candidates`** — from `$FINDINGS_DIR/synthesis.json`; the findings the Sonnet chunk reviewers flagged `escalate_to_architecture: true`. This is the explicit "a Sonnet thought this needed Opus judgment" feed.
3. **`convergent_findings`** — from `synthesis.json`; issues independently flagged by ≥2 lenses. Convergence is a cross-cutting signal N independently-scoped Sonnets cannot self-produce.
4. **Seam-file set** — `patrik_seam_files` from `tasks/review-trail/.weekly-reviewer-scopes.json` (the actual cross-segment integration surface computed by `workweek-trail-scope.sh`). The integration surface is exactly where multi-session erosion lives.
5. **Daily strategic-observer trail** — the week's accumulated daily paper trail authored *for* this pass: the `## Strategic Review (Sonnet daily observer)` sections across `archive/daily-summaries/*.md` and the `tasks/debt-backlog.md` DSR rows tagged `for-weekly-arch-review`. The daily Sonnet observer (workday-complete Step 4c) flags candidates; this is where future-Patrik adjudicates them. A flag here is signal a single day's Sonnet thought worth an Opus look — treat it like input #2, but accumulated across the week rather than from the chunk reviewers.

### Output and disposition ladder

**Patrik's output:** a tech-debt / refactor-consolidate / YAGNI architectural read. Patrik **produces candidates only — he never auto-authors spinoff files** (spinoff is PM-gated, `/spinoff` Step 0). He is read-only at this step.

**EM routes Patrik's candidates down the disposition ladder** (same ladder as the architecture-audit skill, Strand 3a):
- **Trivial / tradeoff-free AND non-structural** (one-liners, mechanical corrections, no module/interface/cross-system boundary touch) → EM dispatches an executor immediately; ordinary EM remit, no PM gate.
- **Mid-size cluster** → EM groups into ONE bundled spinoff candidate (`Candidate spinoff: <slug> — <topic>. Authorize?`), surfaced to PM.
- **Large / genuinely structural** → standalone spinoff candidate or escalate to `/plan`.

Any boundary-touching finding (module move, interface change, cross-system surface) is ineligible for the trivial path regardless of line count — it routes to a bundled/standalone spinoff candidate so it stays recorded.

**Surface Patrik's spinoff candidates to the PM alongside the release-notes draft (Step 9)** — they are part of the weekly read-out, not a merge blocker.

### Accepted loss

**Residual accepted loss (architectural OOS):** a cross-cutting erosion spanning multiple chunks that no individual Sonnet flags as architectural — and so never appears in `arch_tier_candidates` — is not caught at the weekly gate. Accepted because session-end covers within-session integration, the seam set + `convergent_findings` substantially close the gap, and an Opus full-diff read at weekly cadence is not justified by frequency.

---

## Step 7.6 — Architecture Audit Staleness Fold

### Two triggers

The rotational architecture audit (`/architecture-audit`) is easy for the PM to forget. Step 7.6 makes it self-enforcing on two triggers:

**Hard floor (automatic):** `bash "${CLAUDE_PLUGIN_ROOT}/bin/check-arch-audit-staleness.sh"` reads the `Last targeted audit` clock from `tasks/health-ledger.md`:
- `STALE` (>10 days, or never targeted-audited with a ledger present) → auto-fold a **targeted-on-diff** audit this cycle.
- `FRESH` → no fold.
- `UNKNOWN` (no ledger / unparseable) → do NOT auto-fold; note it and move on.

**EM discretion:** even when the clock reads `FRESH`, the EM MAY trigger the targeted audit when the week's churn warrants it (heavy multi-system churn — a large refactor landing across several systems — even on a fresh calendar).

### Scope when folded (DECISION D6)

Audit only the systems the week's diff actually touched (read diff-touched paths from the trail / `git diff --name-only origin/main...HEAD` mapped through `docs/architecture/file-index.md`), NOT a full atlas rebuild. The full breadth survey stays a deliberate PM invocation of `/architecture-survey`.

### Disposition

The folded audit **never edits code** — it packages findings as spinoff candidates down the disposition ladder (immediate executor for trivial+non-structural / bundled spinoff candidate / standalone-or-plan for large) and writes only the `Last targeted audit` clock + atlas metadata. Surface its spinoff candidates to the PM **alongside Patrik's Step 7.5 candidates and the release-notes draft (Step 9)** — a single architecture-candidate read-out. The fold does NOT block merge.
