---
name: parallel-code-review
description: Pre-merge weekly code-review gate — 4 orthogonal reviewers + no-rewrite synthesizer (BLOCKED/WARN/OK). Invoked only from /workweek-complete.
description-budget: 350
argument-hint: "[--force] [--gate-mode strict|advisory]"
version: 1.0.0
---

<!-- Spec backlink: docs/plans/2026-05-06-parallel-code-review-weekly-gate.md Phase 3 -->

# Parallel Code Review

## Overview

I'm using coordinator:parallel-code-review for the /workweek-complete pre-merge code-review gate.

This skill snapshots the week's diff against `origin/main`, dispatches four orthogonal reviewers in parallel, synthesizes their findings into a structured verdict, and halts or proceeds accordingly before release notes are drafted. It is the enforcement surface for the parallel-review merge-gate carve-out pinned in `coordinator/CLAUDE.md` § Review Sequencing.

---

## Wrong-Context Refusal

**This skill is invoked exclusively from coordinator:/workweek-complete.** If you are reading this skill from any other context — `/workday-complete`, `/merge-to-main`, `/bug-sweep`, ad-hoc invocation — STOP. Do not proceed. Surface the misroute to the PM.

Daily wrap and per-merge surfaces have their own (lighter) review patterns. Running 4 parallel reviewers outside the weekly cadence is order-of-magnitude wrong. The sequential-review HARD RULE in `coordinator/CLAUDE.md` § Review Sequencing applies to all other surfaces; this skill's carve-out is exclusively for the weekly gate at a frozen merge-boundary diff.

(There is no runnable bash check here. The refusal is a narrative instruction the EM honours when reading the skill. The frontmatter `description` field reinforces this for any automated router.)

---

## Lens-Domain Manifest

The four reviewers cover orthogonal lens domains. No two reviewers share a domain — this is the independence property that makes convergent findings meaningful.

| Reviewer | Lens domain | Rationale |
|---|---|---|
| Patrik (`agents/staff-eng.md`) | code-semantics | Reads code semantically — correctness, architecture, naming, error handling, SOLID, premise review. |
| security-audit-worker (`agents/security-audit-worker.md`) | pattern-scan | Runs semgrep/bandit/gitleaks/trufflehog over the diff; pattern-matches injection, traversal, secret leakage. |
| dep-cve-auditor (`agents/dep-cve-auditor.md`) | dep-tree | Runs language-appropriate CVE audit; classifies vs. actual usage in the diff. |
| test-evidence-parser (`agents/test-evidence-parser.md`) | test-runtime | Runs the test command, classifies failures (real / flake / env / timeout / known-skip). |

**Adding a 5th reviewer requires editing this table AND `bin/verify-parallel-review-lens-orthogonality.sh`.** The verify-script asserts no two reviewers share a lens-domain; `/update-docs` Phase 11 fails if a collision is introduced. Agent files are NOT the source of truth for the manifest — this skill owns it. See plan `docs/plans/2026-05-06-parallel-code-review-weekly-gate.md` Phase 3.5.

---

## Gating Rules

**Rule 1 wins over Rule 2; Rule 2 wins over Rule 3; Rule 3 wins over default. Rules are evaluated with `grep -E` for consistency.**

- **Rule 1 (skip-all-tiny-or-internal):** if `git diff --shortstat origin/main...HEAD` shows fewer than 10 changed lines OR all changed files match `^(tasks/|tmp/|archive/|\.claude/scheduled_tasks)`, log `Code-review gate: SKIPPED (rule 1 — diff <10 lines or internal-only paths).` and exit 0. **Note: `docs/wiki/` is intentionally NOT in this filter** — wiki edits remain eligible for security-audit-worker (gitleaks may catch leaked secrets in code samples). A week with <10 lines changed is implausible at weekly cadence; this rule exists for completeness.

- **Rule 2 (skip-patrik-on-doc-only):** if every changed file matches `\.(md|rst|txt)$` AND no file matches `\.(py|js|ts|sh|c|cpp|h|hpp|rs|go|java|cs)$`, set `SKIP_PATRIK=1`. Run mechanical workers only. Doc-only weeks are possible but rare at weekly cadence.

- **Rule 3 (skip-entire-gate-on-plan-only):** if every changed file matches `^docs/plans/`, log `Code-review gate: SKIPPED (rule 3 — plan-only diff; staff-eng review on plans goes through /review-dispatch).` and exit 0. Plan-only diffs are handled at authoring time via `/review-dispatch`, not at the weekly boundary.

- **Rule 4 (`--force` escape):** if `$ARGUMENTS` contains `--force`, log `Code-review gate: BYPASSED via --force.` and exit 0.

### Worked examples — weekly-cadence reality

| Rule | Sample diff | Expected gate behavior |
|---|---|---|
| Rule 1 | 4 changed lines in `tasks/some-task/todo.md` | SKIPPED (rule 1 — diff <10 lines or internal-only paths) |
| Rule 2 | `docs/wiki/tiered-context-loading.md` only (no code files) | SKIP_PATRIK=1 — mechanical workers run; Patrik skipped |
| Rule 3 | `docs/plans/2026-05-06-foo.md` only | SKIPPED (rule 3 — plan-only diff) |
| Rule 4 | Any diff with `--force` | BYPASSED via --force |
| Default | 500-2000 changed lines, mixed `.ts` + `.md` + `.sh` | All 4 reviewers run — **this is the typical week** |

At weekly cadence (`/workweek-complete`), the typical week has 500-2000 changed lines mixed code+docs+plans — none of Rules 1-3 fire and the default (run all four reviewers) is the common path. The skip rules exist for completeness, not as the dominant cadence.

---

## Pre-Flight Orthogonality Assertion

Before dispatch, assert that agent files exist and no two reviewers share a lens domain:

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/verify-parallel-review-lens-orthogonality.sh || {
  echo "Lens-orthogonality assertion failed; refusing to dispatch."
  exit 1
}
```

If this fails: do NOT proceed with the parallel dispatch. Surface the failure to the PM — it means either an agent file has gone missing or the manifest table above has been edited to introduce a domain collision.

---

## Snapshot

Freeze the diff and current HEAD before dispatching any reviewers. This is the "frozen diff at merge boundary" guarantee from the carve-out's condition (a).

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
FINDINGS_DIR="tasks/review-findings/$TS"
mkdir -p "$FINDINGS_DIR"
git diff origin/main...HEAD > "$FINDINGS_DIR/diff.patch"
git rev-parse HEAD > "$FINDINGS_DIR/head.sha"
```

`head.sha` records the HEAD at snapshot time. The synthesizer compares against current HEAD at synthesis time; if the branch has advanced (head drift), it emits `verdict: WARN` with `head_drift: true` per Risk 8 in the plan.

---

## Parallel Dispatch

Dispatch all four reviewers (or the active subset per gating rules) in a single multi-tool-call batch. All four dispatches go out simultaneously — this is the independence guarantee. Each reviewer reads `$FINDINGS_DIR/diff.patch` and writes its findings to its own file in `$FINDINGS_DIR/`.

Per-reviewer dispatch shape (actual prompts assembled at dispatch time from the agent files):

- **Patrik** (skip if `SKIP_PATRIK=1`): read `$FINDINGS_DIR/diff.patch`, perform a full code review (correctness, architecture, naming, error handling, SOLID, premise review), output verbatim findings to `$FINDINGS_DIR/patrik.md`. **Read-only review — no AUTO-FIX at this gate.** We are at a release boundary; the integrator is a separate cycle.

- **security-audit-worker**: scan `$FINDINGS_DIR/diff.patch` for injection vectors, secret leakage (gitleaks), unsafe patterns, path traversal. Output to `$FINDINGS_DIR/security.md`.

- **dep-cve-auditor**: scan repo dependency manifests at HEAD, classify CVEs against actual usage in the diff. Output to `$FINDINGS_DIR/deps.md`.

- **test-evidence-parser**: run the project test command, collect output, classify failures as real / flake / env / timeout / known-skip. Output to `$FINDINGS_DIR/tests.md`.

Each dispatcher prompt must include `expected_branch: <current-branch>`. Reviewers do not commit — they write findings to disk only. The disk-first doctrine applies: each file must exist and be >1KB before proceeding to the synthesizer.

---

## Synthesizer Pre-Flight and Dispatch

Before dispatching the synthesizer, validate each expected findings file:

- Each of the 4 findings files (or the dispatched subset per gating rules) must exist on disk.
- Each must be non-empty — apply the 1KB threshold from disk-first doctrine (`coordinator/CLAUDE.md` § Scouts and Disk-First Verification). A 1-2KB file where the brief expected substantially more is a summary masquerading as a deliverable; treat as a failed dispatch.
- If a file fails this check: emit `verdict: WARN` with `lens_coverage[<reviewer>]: failed_disk_read` and surface to EM. **Do NOT default a missing reviewer's findings to "no findings = no issues"** — that silently downgrades coverage without visibility.

Once all present files pass pre-flight, dispatch Sonnet `parallel-review-synthesizer` (`agents/parallel-review-synthesizer.md`). It reads the validated findings files from disk, applies the no-rewrite contract, and writes `$FINDINGS_DIR/synthesis.json`. The synthesizer must not be dispatched until all reviewer findings are on disk.

---

## Verdict Emission

Read `$FINDINGS_DIR/synthesis.json`. Format the one-line verdict for the release-notes draft (Step 9 of /workweek-complete) and eventual PR body:

```markdown
**Code-review gate:** [BLOCKED|WARN|OK] — convergent: N — patrik: <P0/P1/P2/P3 counts> — security: <count> — deps: <count> — tests: <pass/fail/flake>
```

Return this string plus the findings-dir path on stdout for the calling command to consume.

---

## Gate Behavior

### BLOCKED

Exit non-zero. `/workweek-complete` halts before Step 9 (Release Notes) and before Step 11 (`/merge-to-main`). Surface the verdict line and path to `$FINDINGS_DIR/synthesis.json` to the PM.

Resolution: fix the flagged issue and re-run the skill, or pass `--force` to bypass. Do NOT proceed to release notes or merge while BLOCKED without explicit PM direction.

Triggered by: any P0/P1 from Patrik OR any HIGH-severity finding from security-audit-worker OR any unfixed CVE ≥ HIGH from dep-cve-auditor OR any real (non-flake) test failure.

### WARN

Exit 0. Include the verdict line in the release-notes draft (Step 9) and carry it into the eventual PR body via `/merge-to-main`'s normal release-notes pickup.

Triggered by: no BLOCKED triggers AND any P2/P3 from Patrik OR MEDIUM/LOW security finding OR MEDIUM CVE OR `convergent_findings` count ≥ 1.

### OK

Exit 0. Verdict line still goes into the release-notes draft for the record; no warning block in the release notes. Proceed silently.

---

## Cost Discipline

At weekly cadence (~1 invocation/week × ~75-200K tokens per invocation = ~75-200K tokens/week), token cost is trivial compared to a per-merge cadence. No per-invocation budget cap is applied. See `coordinator/CLAUDE.md` § Workday/Workweek Cadence for cadence context. Token-budget tripwire was Gate-1 Finding-3 conditional on per-merge cadence; at weekly cadence it is no longer load-bearing (PM direction 2026-05-06).

---

## Recovery and Resume

If any of the 4 reviewer dispatches fails, retry once via `SendMessage` (per `coordinator/CLAUDE.md` § Scouts and Disk-First Verification — resume from transcript, do not redispatch from scratch). Second failure after retry: emit `verdict: WARN` with `lens_coverage[<reviewer>]: failed` and DO NOT block on infra noise. A single reviewer dropping out due to infra failure degrades to WARN, not BLOCKED — only genuine code-quality findings trigger BLOCKED.

---

## Carve-Out Enforcement Mapping

The parallel-review carve-out in `coordinator/CLAUDE.md` § Review Sequencing has three trigger conditions, each with a named enforcement mechanism in this skill:

| Carve-out condition | Enforcement mechanism |
|---|---|
| (a) Frozen diff at merge boundary | Snapshot section above: `git diff origin/main...HEAD > diff.patch`; `head.sha` records HEAD at snapshot time; synthesizer checks for head drift. |
| (b) All reviewers are orthogonal lenses | Lens-domain manifest table in this skill; verified by `bin/verify-parallel-review-lens-orthogonality.sh` in `/update-docs` Phase 11. |
| (c) No-rewrite synthesizer | Output schema in `agents/parallel-review-synthesizer.md` with `evidence_quote` verbatim fields; `verdict_rationale` is the only synthesizer-authored prose (one sentence). |

This mapping makes the doctrine bullet auditable from the skill — per plan `docs/plans/2026-05-06-parallel-code-review-weekly-gate.md` Phase 4A (Patrik R1 F10).
