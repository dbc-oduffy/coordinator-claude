---
title: Prior-Art Check — 2026-06-08-repo-setup-consolidation
created: 2026-06-08
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-06-08-repo-setup-consolidation.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-08-repo-setup-consolidation.md`
**Verdict:** WARN
**Claims checked:** 23
**Conflicts:** 1 | **Compatible-but-relevant:** 5 | **Silent:** 17
**Corpora consulted:** project-wikis (100+ files indexed, 14 files with old-name hits cross-referenced against chunk scope) | global-wikis (52 files indexed) | lessons.md (80 entries scanned) | improvement-queue (60+ entries scanned)

---

### Conflicts (plan contradicts prior art)

- **Claim #22 — rename sweep file enumeration:** The plan's AC3 test uses a case-sensitive grep pattern to confirm zero residual references: `grep: -r 'project-onboarding\|bootstrap-repos' coordinator/` filtered against the allow-list returns 0 hits.
  - **Plan asserts:** "Zero literal references to `project-onboarding` or `bootstrap-repos` remain in coordinator tree" — verified by `grep: -r 'project-onboarding\|bootstrap-repos' coordinator/` (AC3 Test cell).
  - **Prior art (`state/lessons.md`, entry dated 2026-06-01):** "**Rename-sweep file enumeration must be case-insensitive [universal]** — Building the file-list for a multi-file identifier rename with case-sensitive `grep -lE "token"` silently omits files whose ONLY occurrence is a capitalized variant (`Session-start` vs `session-start`), so they get assigned to no sweep group and survive (2026-06-01, workstream-* rename: `probe-cwd-project-rag-relevance.sh` had only `Session-start` and slipped every group until the final reconcile grep — which was `-i` — caught it). Enumerate with `grep -ril`; the convergence grep must also be `-i`."
  - **Why this is a conflict:** The plan's AC3 convergence grep is case-sensitive; the lesson mandates `-i` for all rename-sweep convergence greps. A file containing only a capitalized variant (`Project-Onboarding`, `Bootstrap-Repos`) would pass AC3 silently.
  - **Candidate directions for EM:**
    - `update-plan` — amend AC3 Test cell to use `grep -ri` (case-insensitive) in addition to the literal-pattern check; this is the lesson's prescribed fix shape
    - `both` — AC3 update is mechanical; the lesson itself is already in lessons.md pending promotion — may want to confirm it routes to `docs/wiki/cleanup-sweep-hazards.md` or `writing-plans.md`
  - **Lean:** The fix is a two-character change to the AC3 Test cell (`grep: -ri`). There is no architectural tradeoff. Update-plan is the obvious direction.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #1 — single-entry-point consolidation:** The plan merges two surfaces into one `/repo-setup` command+skill with mode selection via `--batch`.
  - **Plan covers:** "Single skill, single command: `skills/repo-setup/SKILL.md` and `commands/repo-setup.md`. Two modes selected by argument."
  - **Prior art (`docs/wiki/coordinator-tripwires.md`, SINGLE-ENTRY-POINT-ADDRESSABILITY-CHECK entry):** "**Single-Entry-Point addressability check (SINGLE-ENTRY-POINT-ADDRESSABILITY-CHECK):** [universal] Single-Entry-Point consolidation (all health behind one doctor verb; no `/fix-X` / `/check-Y` proliferation) must pair with selective addressability — the one surface must stay aimable (triage-first default, cluster/probe/symptom selection, `--full` as explicit warhammer). A consolidated diagnostic that fires its whole probe battery on every invocation is a hammer; consolidation without addressability is the failure mode."
  - **Subtype:** `cite`
  - **Suggested action:** The `--batch` flag is precisely the selective-addressability mechanism the tripwire demands — the plan is aligned. However, the plan does not cite this tripwire, and executor stubs for C1/C2 would benefit from having the greppable token `SINGLE-ENTRY-POINT-ADDRESSABILITY-CHECK` visible so a code reviewer can verify the contract. Consider adding a one-line reference in the pinned-interfaces section or the C1 stub.

- **Claim #1 (already cited by plan) — 2026-05-30-onboarding-install-redesign.md:** The plan explicitly supersedes this plan and names it in `supersedes:` frontmatter, Decision-#0, and the Cross-plan coordination section.
  - **Plan covers:** "This plan reverses that architectural choice. PM authorization: 2026-06-08, in full cognizance of the reversal." (Decision-#0)
  - **Prior art (`docs/plans/2026-05-30-onboarding-install-redesign.md`):** Established the three-surfaces architecture with PM and the Staff Engineer review; the choice this plan reverses.
  - **Subtype:** `cite`
  - **Suggested action:** Already fully handled by the plan — no additional action needed. Noted for completeness.

- **Claim #1 (already cited by plan) — 2026-05-30-organic-ramp-concurrency-doctrine.md:** Plan explicitly notes it was checked and no amendment is needed.
  - **Subtype:** `cite`
  - **Suggested action:** Already handled — no additional action needed.

- **Claim #22 (rename sweep) — cleanup-sweep-hazards.md §21 and §29:** Rename sweeps must grep three pattern shapes independently: direct literals, variable assignments (`<VAR>=.*<oldname>`), and (for Python) patch-decorator strings.
  - **Plan covers:** AC3 uses a grep for literal references only (`-r 'project-onboarding\|bootstrap-repos'`).
  - **Prior art (`docs/wiki/cleanup-sweep-hazards.md` §29):** "**Directory-rename sweeps must grep variable-assignment indirections, not just path literals.** A `scripts/` → `project_rag_ue_addon_scripts/` rename left `SCRIPTS_DIR="$ADDON_ROOT/scripts"` in `build_engine_structural_index.sh`, silently breaking the from-source rebuild — every `$SCRIPTS_DIR/...` invocation 404'd. Rule: rename sweeps must grep three pattern shapes independently: 1. Direct literals: `oldname/` in path strings; 2. Variable assignments: `<VAR>=.*<oldname>` — catches the indirect case."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's AC3 literal grep is necessary but may not be sufficient. Shell scripts may have constructs like `SKILL_NAME="project-onboarding"` or `SKILL_DIR=".../project-onboarding"` that are variables rather than literal slash-command strings. Given that the plan itself enumerates 35 files including `lib/` and `bin/` scripts, a variable-assignment grep pass (e.g., `grep -ri 'project.onboarding\|bootstrap.repos'` covering indirect variable forms) in C10 or as an additional AC3 pattern would close this. Alternatively, the EM may judge that the 35 files are already fully enumerated and a literal-plus-case-insensitive grep is sufficient — but the wiki recommends verifying all three shapes.

- **Claim #14 — wiki rename `project-onboarding-claude-md-render.md` → `repo-setup-claude-md-render.md`:** The plan renames this wiki via `git mv` in C7 and relies on C10 doc-link-checker to catch inbound link breakage.
  - **Plan covers:** "C7 — `docs/wiki/project-onboarding-claude-md-render.md` → `docs/wiki/repo-setup-claude-md-render.md` (git mv)" and "C10 — doc-link-checker over `docs/wiki/` + `dist/` for residual broken refs."
  - **Prior art (`docs/wiki/coordinator-installer-shape.md` §3, line 128):** "Both `/coordinator:setup` and `/project-onboarding` render templates. The shared helper is `render-template.sh`... A test suite lives at `bin/tests/test-render-template.sh`." And in §3 (the Render-template primitive section): "Why the narrow contract matters — `project-onboarding/templates/CLAUDE.md.template` originally used `{{IF_GLOBAL}}...{{/IF_GLOBAL}}` conditional blocks... C5 in the implementation plan). This was the *cost* of keeping the helper scope-minimal — driver code constructs the appropriate value strings before calling the helper, rather than the helper growing a conditional engine."
  - **Subtype:** `cite`
  - **Suggested action:** `coordinator-installer-shape.md` §3 contains a prose reference to `/project-onboarding` in an explanatory/historical context (explaining why the narrow render-template contract was chosen). This file IS in C6's scope, so the executor will update it. The prose reference is historical-context (explaining a past decision) rather than a functional command invocation — verify in C6 whether the prose should be updated to `/repo-setup` or preserved as historical context (analogous to how AC3 exempts `docs/plans/2026-05-30-*`). The plan does not call this out explicitly.

---

### Silent areas (no prior art found)

- Claim #2 — `--batch` flag as explicit opt-in for fleet-non-interactive mode: no prior art on batch-flag UX shape for coordinator commands.
- Claim #3 — `lib/bootstrap-orchestrate.sh` repurposed as batch driver: no prior art on orchestrator-lib repurposing patterns.
- Claim #4 — `lib/detect-onboarding-offer.sh` vocabulary-only rename: no prior art on offer-line vocabulary constraints.
- Claim #5 — skill location `skills/repo-setup/SKILL.md` via `git mv`: no prior art on skill directory naming conventions beyond `naming-discipline.md` (informational).
- Claim #6 — replace `commands/bootstrap-repos.md` with `commands/repo-setup.md`: no prior art.
- Claim #7 — absent flag = single-repo interactive default: no prior art.
- Claim #8 — offer-line never emits `--batch` in per-repo offer: no prior art.
- Claim #9 — C1 gates C2-C9 parallel dispatch: compatible with `dispatching-parallel-agents.md` (file-overlap = serial gate); no conflict.
- Claim #10 — history preserved via `git mv`: no prior art beyond general scoped-safety-commits discipline.
- Claim #11 — C7 wiki rename via `git mv`: no prior art specific to wiki renames beyond the 2026-06-01 session-complete-rename precedent (already cited by plan).
- Claim #12 — no template churn: no prior art.
- Claim #13 — AC3 exempts historical archive references: no prior art.
- Claim #15 — CLAUDE.md "Adding a Convention" contact-point update in C8: no prior art conflict. Plan correctly identifies line 38 as needing update.
- Claim #16 — `coordinator-currency.yaml` location and API unchanged: no prior art conflict.
- Claim #17 — `bin/scaffold-canonical-structure.sh` unchanged: no prior art conflict.
- Claim #18 — no changes to coordinator:setup flow: no prior art conflict.
- Claim #19 — amendment note on 2026-05-30 plan (C9): no prior art conflict; plan's cross-plan reconciliation discipline is correctly applied per `skills/plan` Branch C.
- Claim #20 — C10 doc-link-checker closeout: compatible with `reviewer-routed-workers.md` path-rename trigger; no conflict.
- Claim #21 — no archive churn: no prior art conflict.
- Claim #23 — no changes to 2026-06-01-session-complete-rename.md (descriptive references only): no prior art conflict.

---

### Verdict logic

**WARN** — one conflict surfaced (Claim #22, case-sensitive convergence grep in AC3 contradicts the 2026-06-01 "Rename-sweep file enumeration must be case-insensitive" lesson). This is a low-complexity fix: the AC3 Test cell needs `-i` added to the grep invocation. The EM should choose a direction (most likely `update-plan`) before dispatching the Opus reviewer.

The compatible-but-relevant items are informational. Items #1 (SINGLE-ENTRY-POINT-ADDRESSABILITY-CHECK) and #22b (variable-assignment grep pattern) are the most actionable — they could tighten the plan's executor stubs at low cost.

The plan-author has already done thorough prior-art work on the architectural reversal (Decision-#0), cross-plan coordination section, and substrate verification. The items surfaced here are all in the mechanical/sweep layer, not the architectural layer.

---

**Cost estimate:** ~8K tokens (23 claims × ~12 corpus reads, targeted grep passes, 5 full-file reads)
