---
name: architecture-audit
description: Rotational arch audit — scores systems, audits top-priority, packages spinoff candidates. Never edits code; updates Last-targeted-audit clock.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[system-name]"
---

# Architecture Audit — Rotational System Audit

Selects the highest-priority system from the health ledger using a weighted rotation formula, dispatches domain reviewers against it, and **packages the findings as spinoff candidates** down a disposition ladder — the audit pass itself **never edits code**. Updates the health ledger's `Last targeted audit` clock and the atlas metadata. Implements the rotational architecture audit pipeline as an invocable command.

Run this when the workstream-start prompt surfaces "Last targeted audit >10 days" or any time you want a targeted system review. When `$ARGUMENTS` names a system explicitly, that system is audited directly — skipping the rotation score calculation. Useful for targeted re-audits or when PM intuition overrides the formula.

> **Note on the two clocks (see Step 6):** this rotational audit writes **`Last targeted audit`**. The full breadth survey (`/architecture-survey`) writes **`Last full audit`**. They are intentionally separate — a targeted audit must NOT touch `Last full audit`, or it would falsely suppress the PM's nudge to run a real survey.

**Announce at start:** _"I'm using /architecture-audit to audit [system name]."_

---

## Arguments

`$ARGUMENTS` (optional) — name of the system to audit directly, e.g., `save-system` or `ui-core`.

- **Provided:** skip Step 1 score calculation; audit that system directly.
- **Omitted:** run Step 1 to calculate the rotation target from the health ledger.

---

## Step 1: Calculate Rotation Target

**Prerequisite check:** If `state/health-ledger.md` does NOT exist AND `docs/architecture/systems-index.md` does NOT exist:

> _"No baseline exists. Run `/architecture-survey` first to bootstrap the atlas and health ledger."_

Stop here.

If a health ledger exists but no atlas, proceed normally — this audit predates the atlas feature.

**Atlas directory structure:**

The atlas is evergreen reference, sibling to `docs/wiki/` and `docs/decisions/` — NOT under `tasks/`. Patches written here in Step 4 land in the persistent atlas, not transient work state.

```
docs/architecture/
├── systems-index.md          # System inventory with grades and metadata
├── file-index.md             # File-to-system mapping (one line per file)
├── cross-system-map.md       # ASCII dependency diagram
├── connectivity-matrix.md    # System-to-system connection matrix
├── audit-records/            # Canonical per-audit records (YYYY-MM-DD-<system>.md)
└── systems/                  # Per-system detail pages
    └── {system-name}.md      # Function inventory, flows, boundaries
```

**If `$ARGUMENTS` was provided:** skip score calculation; jump to Step 2 with that system as the target.

**Otherwise:** Read `state/health-ledger.md`. For each system in the index, calculate:

| Signal | Weight |
|--------|--------|
| CRITICAL status or open P0 | +15 |
| Never audited | +10 |
| >30 days since last audit | +5 |
| >14 days since last audit | +2 |
| Open P1 items | +3 each |
| Significant growth since last audit | +3 |
| Security-sensitive system | +2 |
| **Query-completions roadmap score (see below)** | **+0 to +10** |

**Query-completions roadmap score — run before selecting target:**

```bash
bin/query-completions --since "30d" --where "nature=roadmap" --format json \
  | jq -r '.[] | .subsystem // "unknown"' | sort | uniq -c | sort -rn
```

For each system, count the `nature: roadmap` entries touching it in the last 30 days and sum `loe.tshirt` weights (XS=1, S=2, M=4, L=8, XL=16) across those entries. Add to the base score:

| Roadmap activity (last 30d) | Additional weight |
|-----------------------------|-------------------|
| Aggregated LoE ≥ 16 (e.g. 1×XL or 2×L) | +10 |
| Aggregated LoE 8–15 | +6 |
| Aggregated LoE 4–7 | +3 |
| Aggregated LoE 1–3 | +1 |
| No roadmap entries | +0 |

**Rationale:** commit churn doesn't distinguish doctrine edits from refactors from feature work; `nature: roadmap` does. High LoE roadmap traffic signals architectural surface area that warrants a fresh audit — many small commits do not.

**Zero-result handling:** If `query-completions` returns no rows (fresh repo or no roadmap entries in 30d), omit the roadmap score column and proceed with the base health-ledger signals only.

**Pre-rotation drift surface (run before accepting the rotation pick):** invoke `bin/check-atlas-watch-drift.sh` and surface any `DRIFT` / `MISSING` / `ERROR` / `MALFORMED` / `STALE` lines for systems that are rotation candidates. Drift on the proposed target system bumps it to the top of the rotation regardless of formula score — a stale baseline invalidates the audit. This is detection-leg coverage for atlases that have decayed mechanically between rotations (e.g. probe-count drift, registry-version bumps, validator composition changes).

Select the highest-scoring system. Report: _"Rotation target: [system] (score: N). Rationale: [top signals including roadmap activity if non-zero]."_

**Open-P1 weight decays for recently-audited systems.** The open-P1 signal (+3 each) inflates the score of systems just audited — those are exactly the systems where P1s were recently surfaced and are most likely already tracked for action. Apply a decay: halve the open-P1 contribution for any system audited within the last 7 days, and zero it for any system audited within the last 3 days. This prevents the formula from re-selecting a freshly-audited system in the next rotation slot simply because the audit created new P1 items. *2026-05-28, project-rag + self.*

Note: These weights are initial estimates — adjust after 4 weeks based on whether rotation targets match intuition.

---

## Step 2: Review Existing Debt

Post-D5, the debt backlog is no longer the audit's output sink — it holds only items the EM/PM explicitly chose to **defer with a reason** (architectural OOS). Reading it here is still valid: pre-existing deferred items for the target system should be surfaced before auditing for new issues. Read `state/debt-backlog/*.yaml` (or run `bin/query-records --type debt --status open`) to find open items for the target system. If open items exist:

1. Present them to PM for prioritization — before auditing for new issues
2. Prioritized debt items go through the full pipeline: plan → review → execute
3. This happens before or alongside the audit, not inline

---

## Step 2.5: Load Atlas Context

Check for `docs/architecture/systems/{target-system}.md`.

- **Exists:** Include the atlas page in the reviewer's dispatch prompt as background context. This gives the reviewer structural knowledge (function inventory, flow diagrams, boundary catalog) so they focus on changes and quality assessment rather than rediscovery.
- **Does not exist:** Proceed without atlas context. Reviewer discovers the system from scratch.

---

## Step 2.75: Emit Ground-Truth File-Enumeration Artifact

**Before dispatching any analysis layer, commit a ground-truth file enumeration for the target system.** This prevents Haiku/Sonnet layers from working against stale or hallucinated file lists, and gives the Opus reviewer a stable reference to adjudicate "files exist / don't exist" claims.

```bash
# Emit and commit the ground-truth listing
find <system-dirs> -type f | sort > tasks/scratch/weekly-architecture-audit/{run-id}/ground-truth-files.txt
wc -l tasks/scratch/weekly-architecture-audit/{run-id}/ground-truth-files.txt
git add tasks/scratch/weekly-architecture-audit/{run-id}/ground-truth-files.txt
git commit -m "arch-audit: pin ground-truth file list for [system] before analysis"
```

Pass the path to this file in every analysis-agent prompt. When the Opus reviewer declares an inventory "fabricated" or "non-existent", it must diff the claim against `ground-truth-files.txt` before issuing the verdict. This gate was motivated by a 2026-05-28 audit where a flaky-harness enumeration briefly led the Opus judge to mis-declare inventories as fabricated.

*2026-05-28, self (`skills/architecture-audit/SKILL.md:Step3`).*

---

## Step 3: Dispatch System Review (Size-Gated)

Check the system's **live file count** at dispatch time. Do not use the atlas file count — systems may have grown since discovery.

### Systems ≤10 files — Direct Opus Dispatch

1. Identify the system's domain:
   - Game dev / Unreal → the Game Dev Reviewer
   - Frontend / UI → the Front-End Reviewer
   - ML / data → the Data Science Reviewer
   - Other / architecture → the Staff Engineer
2. Dispatch the domain reviewer with full system scope — all files in the system. Include the atlas page as context (per Step 2.5).
3. Reviewer grades the system and adds/updates the grade on the atlas page.
4. **Multi-reviewer is angle-motivated, not a mandatory backstop.** Dispatch a second (or third) reviewer ONLY when the system needs a distinct lens the first reviewer doesn't carry — e.g. `project-rag` reviewed by the Staff Engineer (architecture) AND the Data Science Reviewer (ML/retrieval) because both angles are load-bearing; a UE subsystem reviewed by the Game Dev Reviewer AND the Staff Engineer when gameplay + cross-system boundaries are both in scope. EM picks the angles based on what the system actually is. "Push back on lack of ambition" is ordinary EM remit (First Officer Doctrine § Staff Engineer Leverage) — it does not motivate a formal second reviewer on every audit.

### Systems >10 files — Haiku→Sonnet Pre-Digestion

0. **Generate run ID** — format: `YYYY-MM-DD-HHhMM`. Scratch directory: `tasks/scratch/weekly-architecture-audit/{run-id}/`

1. **Sub-chunk** the system into groups of 8-12 files, organized by concern (not alphabetical — group by what the files do together).

2. **Dispatch Haiku inventory agents (parallel)** — one per sub-chunk. Use the **Phase 1: Haiku Function-Level Inventory Prompt** from `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/agent-prompts.md`. These agents catalog what exists — no analysis. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md` as `[SCRATCH_PATH]`. Instruct each agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

   **Scratch verification:** Before dispatching Sonnet, verify all expected Haiku scratch files exist. Re-dispatch once on failure; skip that sub-chunk on second failure.

3. **Dispatch Sonnet analysis agents (parallel)** — one per system — reads ALL Haiku sub-chunk inventories from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase1-haiku.md`. Use the **Phase 2: Sonnet System Analysis Prompt (Audit variant, with grading)** from `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/agent-prompts.md`. Include the existing atlas page as context so Sonnet focuses on changes and quality assessment, not rediscovery. Pass scratch path `tasks/scratch/weekly-architecture-audit/{run-id}/{chunk-letter}-phase2-sonnet.md` as `[SCRATCH_PATH]`. Instruct each agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

   **Scratch verification:** Before dispatching Opus reviewer, verify Sonnet scratch files exist. Re-dispatch once on failure.

4. **Dispatch domain reviewer (Opus)** with summarized Sonnet findings (read from `tasks/scratch/weekly-architecture-audit/{run-id}/*-phase2-sonnet.md`). The reviewer brings judgment and cross-cutting insight — do NOT send raw files to the domain reviewer.

5. Reviewer grades the system and adds/updates the grade on the atlas page.

6. **Multi-reviewer is angle-motivated, not a mandatory backstop** (see Step 3 §≤10-files row 4). When a second angle is warranted, the additional reviewer reads the summarized Sonnet analysis, not raw files.

---

## Step 3.6: Scaffold the Canonical Audit Record

Run the scaffolder to emit the conformant skeleton at the canonical path:

```bash
coordinator-doc-new --type audit-record --system <target>
# → docs/architecture/audit-records/<YYYY-MM-DD>-<target>.md
```

The scaffolded skeleton is the **authoritative shape** — it carries the required YAML frontmatter (D1 field set: `run_id`, `system`, `grade`, `health_status`, `reviewer`, `created`; optional `mode`), the canonical body sections, and the addressable `### Diagram (ASCII)` fenced section. The canonical body-section list is the SSOT of the C2 scaffolder skeleton; the reviewer fills sections within it and does NOT choose its own shape.

**Dispatch the domain Opus reviewer with `mode: acceptEdits` and the scaffolded file path** so it edits the file in-place. The reviewer prompt MUST instruct the reviewer to:

1. **Populate frontmatter:** fill `grade` (A–F enum), `health_status` (HEALTHY|WATCH|ACTION|CRITICAL enum), `run_id` (format: `YYYY-MM-DD-HHhMM`), `reviewer`, and optionally `mode` (RESEARCH_ONLY|FULL|REMEDIATION).
2. **Write the `### Diagram (ASCII)` fenced flow diagram** — format and ≤100-char rule per `canonical-artifact-shapes.md § Diagram (ASCII) Rule` (the SSOT — cite it; do NOT copy rule text from `pipelines/deep-architecture-survey/agent-prompts.md`).
3. **Fill all named prose sections without flattening grade-rationale or ambition-check prose.** These sections carry human judgment — the guardrail is that no prose section is ever dropped to make room.

The reviewer prompt references the scaffolded skeleton file, not an independent restatement of the section list. Parallel restatement of the canonical section list is the drift path the shared contract prevents.

> **Negative-spec (hard):**
> - The reviewer MUST NOT flatten or drop any prose section (grade-rationale, ambition-check, or others) to make room for any other content.
> - The three historical audit records (`2026-05-28-coordinator-runtime.md` et al.) are frozen point-in-time records — they are NOT retrofitted to the canonical schema (plan D4). The new shape governs only records authored after this step lands.

---

## Step 4: Package Findings as Spinoff Candidates (the audit NEVER edits code)

**Principle (PM-confirmed, D4):** the audit pass itself **never edits code** — it reads, scores, and hands findings to the EM. The audit has no inline-fix step. Disposition is **EM judgment**, routed down a ladder (people over process — not a rigid everything-becomes-a-PM-gated-spinoff pipeline):

- **Trivial / tradeoff-free AND non-structural** (one-liners, mechanical corrections, no judgment) → the EM **dispatches an executor immediately** in a follow-up, saving spinoff ceremony. This is ordinary EM remit (acting on review findings) — NOT a PM-gated spinoff, no authorization needed.
  - **Guardrail (hard):** the immediate-executor path requires findings that are BOTH tradeoff-free AND non-structural. **Any finding touching a module boundary, interface, or cross-system surface is ineligible regardless of line count** — it routes to a bundled/standalone spinoff candidate (PM-gated + recorded). This guardrail is what makes retiring the auto-debt-backlog write (Step 5) safe: structural findings keep a visible record as spinoff-candidate artifacts.
- **Mid-size cluster** ("these 17 changes are too big for mechanical line-edits but too small for an individual plan") → the EM **groups them into ONE bundled spinoff candidate** rather than minting 17 separate ones or one bloated plan.
- **Large / genuinely structural** → standalone spinoff candidate, or escalate to `/plan`. When the finding constitutes an architectural decision that warrants a permanent record, scaffold the DR before surfacing the spinoff candidate: `coordinator-doc-new --type decision --title "<title>" --out docs/decisions/DR-<NNN>-<slug>.md` (emits conformant frontmatter from `schemas/decision.yaml`; canonical identity key `id`, temporal key `created`).

**Spinoff PM-gate applies to the spinoff path only.** For grouped/standalone candidates the EM surfaces `Candidate spinoff: <slug> — <topic>. Authorize?` and blocks — the audit **never auto-authors spinoff files** (`/spinoff` Step 0). The immediate-executor path is ordinary EM disposition and bypasses the gate by design.

The audit produces a **candidate list** as its output artifact; the EM routes each entry down the ladder above. No code is changed by the audit itself.

---

## Step 5: (retired — no auto-debt-backlog write)

**D5 (PM 2026-05-24): the audit no longer writes debt-backlog entries.** The disposition ladder (Step 4) + spinoff-candidate pattern is the dedicated home for audit findings — a finding either gets fixed now (executor), bundled (spinoff candidate), or escalated (plan). There is no separate "structural finding → debt-backlog entry" step.

The debt-backlog store (`state/debt-backlog/*.yaml`) remains for items the EM/PM **explicitly choose to defer with a reason** (architectural OOS) — not as the default sink for audit findings. PM rationale: "dedicated pattern for that — don't bundle everything into one ceremony." The Step 4 guardrail (structural findings always become recorded spinoff candidates) is what keeps anything from going dark now that the auto-write is gone.

---

## Step 6: Update Health Ledger

1. Update the system's row: new grade, status, audit date, open issue counts
2. Update the **`Last targeted audit`** date in the header — this rotational audit writes the targeted clock, NOT `Last full audit`. `check-arch-audit-staleness.sh` reads `Last targeted audit` for its >10-day comparison. Leave `Last full audit` untouched (only `/architecture-survey` writes it; touching it here would falsely suppress the survey nudge).
3. Calculate the next rotation target and update `Next rotation target` in the header (if present)
4. **Stage** the health-ledger update — do NOT commit yet. The health-ledger commit is **deferred until Step 6.5 gate PASSes** (see Step 6.5 below). On gate FAIL, the ledger commit does NOT land — this prevents `Last targeted audit` from advancing on an audit that closed against a stale atlas. The bundled close-out commit (atlas + ledger together, or sequenced atlas-then-ledger) lands after Step 6.5 gate PASS. The two-clock doctrine is preserved: `Last targeted audit` only is touched here; `Last full audit` is untouched (only `/architecture-survey` writes that clock — touching it here would falsely suppress the survey nudge).
   ```bash
   # Stage only — do NOT commit until after Step 6.5 gate PASS.
   git add state/health-ledger.md
   ```

---

## Step 6.5: Update Atlas Page (Pre-Commit Gate)

If `docs/architecture/systems/{target-system}.md` does not exist, skip this step entirely (no atlas to gate). Otherwise the atlas page MUST satisfy one of two branches before close-out commits land. The gate runs **before** `git commit` — it reads staged content and the intended commit message, NOT HEAD.

**Branch A (refresh inline):** if reviewer findings warrant changes:
1. Edit the atlas page body — add/remove functions mentioned in findings, update boundary entries if cross-system connections changed.
2. Bump BOTH `last_mapped` AND `last_attested` to the audit date in the YAML frontmatter. (Branch A bumps both because a content rotation IS the strongest form of attestation — narrow-attestation would let a just-rotated atlas read STALE under the 30d threshold.)
3. Add/update `grade: [A-F]` and `health_status: [HEALTHY|WATCH|ACTION|CRITICAL]` fields in the YAML frontmatter, after the `dependencies` field.
4. Stage the atlas page alongside the health-ledger update from Step 6.

**Branch B (assert current):** if the atlas is already accurate and no body changes are warranted:
1. Bump `last_attested` (NOT `last_mapped`) to the audit date. Zero body diff. Branch B records a currency assertion without a content rotation.
2. Stage the atlas page alongside the health-ledger update.
3. Prepare a close-out commit message containing the literal token `atlas-current-as-of: <YYYY-MM-DD>` (the audit date).

**Run the gate (before `git commit`):**

```bash
bash ${CLAUDE_PLUGIN_ROOT}/bin/verify-arch-audit-atlas-refresh.sh <AUDIT_DATE> <TARGET_SYSTEM> [<COMMIT_MSG_FILE>]
```

- On `PASS branch=A` or `PASS branch=B` → proceed to `git commit` (atlas + ledger together, or sequenced atlas-then-ledger).
- On `FAIL` → do NOT commit. Amend the working tree (Branch A: add the body diff that was missing) or the intended commit message (Branch B: add the `atlas-current-as-of:<date>` token), re-stage, and re-run the helper. The commit does NOT land until the gate returns PASS.

**Anti-scope (this gate ONLY):**
- The gate does NOT extend to `/architecture-survey` — `Last full audit` is exclusively that command's clock and this gate never touches it.
- The gate is NOT per-system hot-configurable (no per-system staleness window for the closeout gate).
- The gate does NOT opportunistically refresh non-target atlas pages — the weekly walk (`/workweek-complete` invocation of `check-atlas-watch-drift.sh`) surfaces drift on other pages; refresh of those is per-rotation EM judgment, not an inline side-effect of this audit.

---

## Step 6.75: Triage Scratch Files

If the large-systems path was used (>10 files), delete all scratch files — Haiku/Sonnet output was fully consumed by the Opus reviewer:

```bash
rm -rf tasks/scratch/weekly-architecture-audit/{run-id}/
```

---

## Step 7: Report

**Precondition (on-disk audit record):** The canonical audit record at `docs/architecture/audit-records/<date>-<system>.md` (scaffolded in Step 3.6 and filled by the reviewer in-place via `mode: acceptEdits`) MUST exist and carry populated frontmatter and a `### Diagram (ASCII)` section before proceeding. Stage and commit this file alongside the atlas + ledger close-out commit from Step 6.5.

**The chat report below is DISTINCT from the on-disk audit record.** The chat report is a session-close summary for the PM; the on-disk record at `docs/architecture/audit-records/<date>-<system>.md` is the durable machine-addressable artifact carrying frontmatter (`grade`, `health_status`, `run_id`) and the addressable `### Diagram (ASCII)` section. The chat report does not substitute for the disk record, and the disk record does not replace the chat report.

**Precondition (atlas gate):** `bin/verify-arch-audit-atlas-refresh.sh` returned `PASS branch=A` or `PASS branch=B` on the last attempt. If it returned `FAIL`, do NOT proceed to Step 7 — fix per Branch A or Branch B in Step 6.5 and re-attempt. The verbatim failure message is the iron-law signal:

```
FAIL: /architecture-audit Step 6.5 atlas-refresh gate not satisfied for <TARGET_SYSTEM>.
Either (a) refresh docs/architecture/systems/<TARGET_SYSTEM>.md inline before closing,
or (b) declare atlas-current-as-of:<YYYY-MM-DD> in the closeout commit message.
```

```markdown
## Architecture Audit Complete

**System:** [name]
**Reviewer(s):** [name] at High effort [+ second-angle reviewer: [name] — angle: [reason], or "none — single angle sufficed"]
**Previous grade:** [X] | **New grade:** [Y]
**Findings:** N total — [X → immediate executor (trivial+non-structural), Y → spinoff candidate(s) surfaced to PM, Z → escalated to /plan]
**Spinoff candidates surfaced:** [list of `Candidate spinoff: <slug>` prompts, or "none"]
**Next rotation target:** [system] (score: N)
```

---

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| No health ledger and no atlas | Fresh repo with no baseline | Run `/architecture-survey` first |
| Dispatching Opus reviewer with >10 files | Skipped size gate | Sub-chunk the system; use Haiku→Sonnet pre-digestion before Opus reviewer |
| Opus agent 529 overload | System too large for direct dispatch | Sub-chunk into 8-12 file groups; Haiku and Sonnet handle file reading |
| Sonnet findings lack depth | Sub-chunks too large (>12 files each) | Re-partition into smaller chunks; Sonnet performs better with focused scope |
| Reviewer misses structural detail the atlas has | Atlas page not included in Sonnet dispatch | Always include the atlas page in the Sonnet agent prompt as background context |

---

## Cost

**Small systems (≤10 files):** 1 Opus dispatch (domain reviewer); +1 only when a second angle is load-bearing (Step 3 row 4). No review-integrator pass — the audit edits nothing; findings route through the EM disposition ladder (immediate executor / spinoff candidate / plan) after the audit returns.

**Large systems (>10 files):** Haiku inventory agents (parallel, one per 8-12 file sub-chunk) + Sonnet analysis agents (parallel, one per sub-chunk) + 1 Opus domain reviewer (+1 angle-motivated reviewer only when warranted). Haiku and Sonnet costs are low; the Opus reviewer still dominates the total. Disposition of findings (immediate executor / spinoff candidate / plan) happens after the audit returns — the audit itself edits nothing.

---

## Relationship to Other Commands

- **`/architecture-survey`** — the full deep-audit command that bootstraps the atlas and health ledger. Run this first on a new project before running `/architecture-audit`.
- **`/review` / `/review-code`** — route a single artifact through a reviewer (plan-shaped via `/review`, code-shaped via `/review-code`). `/architecture-audit` orchestrates the full rotation loop including review, spinoff-candidate packaging (never inline edits), and ledger updates — it is not a thin wrapper around single-reviewer dispatch.
- **`pipelines/weekly-architecture-audit/PIPELINE.md`** — the pipeline definition this command executes. Contains the authoritative process specification; this command is the invocable surface for it.
- **`/architecture-survey`** — full system discovery and atlas construction. Use it when the atlas is stale or a system is entirely undocumented.
