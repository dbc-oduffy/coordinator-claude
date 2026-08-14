---
name: architecture-audit
description: "Rotational arch audit — score systems, audit the top, package spinoffs. Never edits code."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[system-name]"
---

# Architecture Audit — Rotational System Audit

Selects the highest-priority system from the health ledger, dispatches domain reviewers against
it, and **packages findings as spinoff candidates** down a disposition ladder — the audit itself
**never edits code**. Updates the health ledger's `Last targeted audit` clock and the atlas
metadata.

Run when `/workstream-start` surfaces "Last targeted audit >10 days", or any time PM intuition
wants a targeted review. `$ARGUMENTS` names a system directly, skipping Step 1.

**Announce at start:** _"I'm using /architecture-audit to audit [system name]."_

---

## Step 1: Select Rotation Target

No `state/health-ledger.md` and no `docs/architecture/systems-index.md` → stop: run
`/architecture-survey` first. `$ARGUMENTS` provided → skip to Step 2 with that system. Otherwise
select the highest-priority system in the ledger — selection signals and worked calibration: wiki
(no engine scorer exists yet). Report: _"Rotation target: [system]. Rationale: [why]."_

---

## Step 2: Review Existing Debt

Read `state/debt-backlog/*.yaml` (or `bin/query-records --type debt --status open`) for the target
system; present open items to the PM before/alongside the audit — full pipeline (plan → review →
execute), not inline here.

---

## Step 2.5: Load Atlas Context

`docs/architecture/systems/{target-system}.md` exists → include it in the reviewer dispatch as
background context. Absent → reviewer discovers from scratch.

---

## Step 2.75: Emit Ground-Truth File-Enumeration Artifact

`cartography file_index --target-root <system-dirs>` → write the `index` field to
`tasks/scratch/weekly-architecture-audit/{run-id}/ground-truth-files.txt`, commit it. Pass the
path in every analysis-agent prompt; the Opus reviewer diffs any "fabricated"/"non-existent" claim
against it before issuing a verdict.

---

## Step 3: Dispatch System Review

Check the target's **live** file count (not the atlas count — systems grow); small systems get a
direct Opus domain-reviewer dispatch, larger ones need Haiku→Sonnet pre-digestion first or the
reviewer overloads. Threshold, dispatch procedure, prompt sources, and multi-reviewer criteria:
wiki.

---

## Step 3.6: Scaffold the Canonical Audit Record

`coordinator-doc-new --type audit-record --system <target>` writes
`docs/architecture/audit-records/<YYYY-MM-DD>-<target>.md` — the scaffolded skeleton is
authoritative; the reviewer fills it in-place via `mode: auto`. Reviewer prompt must cover:
populate frontmatter (`grade`, `health_status`, `run_id`, `reviewer`), write the `### Diagram
(ASCII)` section, fill every prose section without flattening grade-rationale/ambition-check
content. Detail: wiki.

**Negative-spec (hard):** the three historical audit records (`2026-05-28-coordinator-runtime.md`
et al.) are frozen point-in-time records — they are NOT retrofitted to the canonical schema (plan
D4). The new shape governs only records authored after this step lands.

---

## Step 4: Package Findings as Spinoff Candidates (never edits code)

Disposition is EM judgment down a ladder:

- **Trivial, tradeoff-free, non-structural** → EM dispatches an executor immediately, no PM gate.
  **Hard guardrail:** any finding touching a module boundary, interface, or cross-system surface
  is ineligible regardless of size — always a spinoff candidate instead.
- **Mid-size cluster** → one bundled spinoff candidate, not N singles or one bloated plan.
- **Large/structural** → standalone spinoff candidate, or escalate to `/plan`. Scaffold a DR first
  when it's an architectural decision: `coordinator-doc-new --type decision --title "<title>"
  --out docs/decisions/DR-<NNN>-<slug>.md`.

Spinoff PM-gate applies only to the grouped/standalone path — surface `Candidate spinoff: <slug>
— <topic>. Authorize?` and block. No debt-backlog auto-write (rationale: wiki).

---

## Step 6: Update Health Ledger

Update the system's row (grade, status, audit date, open-issue counts) and the **`Last targeted
audit`** date only — never `Last full audit`. Calculate and update `Next rotation target` if
present. **Stage, do not commit** (`git add state/health-ledger.md`) — the commit lands only after
the Step 6.5 gate PASSes, so the clock never advances against a stale atlas.

---

## Step 6.5: Update Atlas Page (Pre-Commit Gate)

No atlas page for the target → skip entirely. Otherwise pick a branch:

- **Branch A (refresh inline):** edit the atlas body for findings, bump both `last_mapped` and
  `last_attested`, set `grade`/`health_status`, stage alongside the ledger.
- **Branch B (assert current):** zero body diff, bump `last_attested` only, stage, and the
  close-out commit message must contain `atlas-current-as-of: <YYYY-MM-DD>`.

Run `verify-arch-audit-atlas-refresh <AUDIT_DATE> <TARGET_SYSTEM> [<COMMIT_MSG_FILE>]` before
`git commit`. `PASS branch=A|B` → commit. `FAIL` → do not commit; amend per the branch you're on,
re-stage, re-run. Anti-scope and full branch mechanics: wiki.

---

## Step 6.75: Triage Scratch Files

Large-systems path used → `rm -rf tasks/scratch/weekly-architecture-audit/{run-id}/` (Haiku/Sonnet
output is fully consumed by the Opus reviewer).

---

## Step 7: Report

**Precondition:** the canonical audit record at
`docs/architecture/audit-records/<date>-<system>.md` exists with populated frontmatter and a
`### Diagram (ASCII)` section, staged/committed alongside the atlas + ledger close-out, and the
Step 6.5 gate returned `PASS` — on `FAIL`, fix per that step and re-attempt. Chat report ≠ on-disk
record — the FAIL message text: wiki.

```markdown
## Architecture Audit Complete

**System:** [name]
**Reviewer(s):** [name] at High effort [+ second-angle reviewer, or "none — single angle sufficed"]
**Previous grade:** [X] | **New grade:** [Y]
**Findings:** N total — [X → immediate executor, Y → spinoff candidate(s) surfaced to PM, Z → escalated to /plan]
**Spinoff candidates surfaced:** [list, or "none"]
**Next rotation target:** [system]
```

---

## Notes

Failure modes, cost profile, and relationship to `/architecture-survey`, `/review`/`/review-code`,
and `pipelines/weekly-architecture-audit/PIPELINE.md`: wiki.
