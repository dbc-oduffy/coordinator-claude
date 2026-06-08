---
title: Plan Coverage Check — session-complete-rename
created: 2026-06-01
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-06-01-session-complete-rename.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-01-session-complete-rename.md`
**Verdict:** INCOMPLETE
**Oracle items:** Two-part oracle — (a) per-file occurrence enumeration (plan states 92 files / 379 occurrences; disk has 95 files); (b) 6-item intentional-keep list
**Slate items:** 8 chunks (C1–C8)
**Missed:** 16 | **Ambiguous:** 20 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 1

---

### Lens 1 — Coverage (Oracle-vs-Slate Cross-Reference)

**Oracle re-run result:** `grep -rl "session-end" plugins/coordinator-claude/coordinator` returns **95 files** on disk at check time. The plan states 92 files (baseline at plan-write). The plan acknowledges that "drift up from the handoff's 90/321 from concurrent work" explains count movement, and instructs to "reconcile against the keep-list, not the raw count." Three additional files are present. All 95 files are cross-referenced below.

#### Classification method

C5 explicitly names a wiki group list followed by "remaining wikis" — this is an M:N consolidation clause for wikis. Wikis found on disk but not in C5's explicit list are classified **AMBIGUOUS** (consolidating catch-all without explicit citation). C5's explicit skill list does NOT carry a "remaining skills" clause; unlisted skills with hits are **MISSED**. No chunk covers `bin/` (other than C3), `lib/`, `commands/` (other than C6 which covers `workday-complete.md` and `distill.md`), `agents/`, `canonical-structure.yaml`, `pipelines/*` (other than C5 "pipelines/*" — see note), `tests/`, `dist/oss-only-skills/`, or `docs/plans/` hits.

**Note on `pipelines/*`:** C5 says "pipelines/*" — this is a wildcard that covers all files under `pipelines/`. Files in `pipelines/` are therefore AMBIGUOUS (consolidating clause without per-file enumeration), not MISSED.

#### MISSED audit items (no slate entry, no architectural OOS)

**MISSED-1: `lib/coordinator-session.sh`**
- Hit: `"└── <session-id>-<YYYY-MM-DD>/   archived after session-end or handoff"` — prose command reference
- No chunk names `lib/` files. C5 names wikis, skills, commands, hooks, pipelines, agents. `lib/` is absent from all chunks.
- **Resolution options:** add to C5 scope | add to OOS with architectural reason (spec-backlink only — but this hit is a prose comment, not a spec-backlink filename) | amend oracle with explanatory note (oracle-was-wrong)

**MISSED-2: `lib/workweek-trail-scope.sh`**
- Hit: `"# Reads the session-end review trail records for the current week"` — prose command reference in header
- Same `lib/` gap as MISSED-1.
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-3: `bin/coordinator-write-review-trail.sh`**
- Hits: `"Purpose: records a code-review marker after /session-end or /handoff review"` (L4); `"Spec backlink: docs/plans/2026-05-08-session-end-review-and-marker-trail.md § T2"` (L8); `"Per docs/plans/2026-05-08-session-end-review-and-marker-trail.md § Considered Alternatives"` (L33)
- L4 is a live command reference (`/session-end`). L8 and L33 are spec-backlink filename references — keep-list item 4 applies to those. The `/session-end` prose reference at L4 is not covered.
- C3 covers only `bin/regenerate-orientation-cache.sh`. No chunk covers this file.
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-4: `bin/coordinator-session-loe.sh`**
- Hit: `"Consumed by /session-end, /handoff, and chain-aggregation (Chunk 5)."` — prose command reference
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-5: `bin/aggregate-chain-loe.sh`**
- Hits: `"chain-terminal /session-end"` (L6); `"session-end can keep the terminal session's own per-session \`loe:\`"` (L584) — both are prose command references
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-6: `bin/coordinator-safe-commit`**
- Hit: `\bsession-end\b` appears inside a regex pattern string — `grep -qiE '(\bhandoff\b|\bspinoff\b|...\bsession-end\b|...)` (L713–715). This is a **functional regex pattern** that matches commit subjects containing the string `session-end`. After the rename, commits about the renamed ceremony will say `session-complete` in their subjects, but this pattern will still pass (it also matches `session-complete` if added). The pattern as written will miss `session-complete` commits. This is the most operationally significant miss: the safe-commit branch-name/ceremony-check regex needs `\bsession-complete\b` added alongside the existing `\bsession-end\b` entry.
- **Resolution options:** add to C5 scope (or new C chunk for bin/ functional code) | architectural-OOS | oracle-was-wrong

**MISSED-7: `bin/check-no-monolith-completion-append.sh`**
- Hits: `"the session-end"` (L28); `"session-end/SKILL.md"` (L31) — L31 is a path reference to the deprecated stub (keep-list item 3 applies post-rename); L28 is a prose reference
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-8: `bin/cross-repo-memo`**
- Hits: `"session-end notes"` (L50); `"session-end notes"` (L884) — prose command references
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-9: `README.md` (root coordinator README)**
- Hit: `"| \`/session-end\` | Wrap up finished work — capture lessons, update docs |"` — live command reference in a command-reference table
- C6 covers only `dist/publish-repo-toplevel/README.md`. The root `README.md` at `plugins/coordinator/README.md` is distinct and not in any chunk.
- **Resolution options:** add to C6 scope | architectural-OOS | oracle-was-wrong

**MISSED-10: `commands/workday-start.md`**
- Hit: `"durable snapshot at \`state/handoff-tracker.md\` (refreshed by \`/session-end\` and \`/handoff\`"` — prose command reference
- C5 lists `commands/workday-complete.md` and `commands/distill.md`. `commands/workday-start.md` is not listed. C5 does not have a "remaining commands" clause.
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-11: `commands/mise-en-place.md`**
- Hits: `"per \`docs/wiki/session-end-review.md\`"` (L245) — wiki path reference (the wiki itself will be renamed in C5, so refs to it also need updating); `"session-end review doctrine"` (L244) — prose reference
- C5 does not list `commands/mise-en-place.md`.
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-12: `canonical-structure.yaml`**
- Hit: `"state/review-trail/ — review records written by /session-end and /handoff."` — prose command reference in YAML
- Not covered by any chunk.
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-13: `agents/review-integrator.md`**
- C5 lists agents (implicitly — "Commands/hooks/pipelines/agents") but the only named agent file is `agents/code-reviewer-weekly.md`. C5 says "agents" without "remaining agents." The review-integrator hit needs verification.
- Wait — C5 lists `agents/code-reviewer-weekly.md (4)` as an explicit named file. It does not list `agents/review-integrator.md`. No "remaining agents" clause.
- Hit: `"chain-end review (session-end \`code-reviewer\` or..." ` — prose command reference
- **Resolution options:** add to C5 scope | architectural-OOS | oracle-was-wrong

**MISSED-14: `dist/oss-only-skills/coordinator-update/SKILL.md`**
- Hit: `"Author handoffs, spinoffs, or session-end artifacts."` — prose command reference
- Not in any chunk. C6 covers `dist/publish-repo-toplevel/` but not `dist/oss-only-skills/`.
- **Resolution options:** add to C6 scope | architectural-OOS | oracle-was-wrong

**MISSED-15: Unlisted skills (9 files)**
C5 explicit skill list: `handoff/SKILL.md`, `pickup/SKILL.md`, `execute-plan/SKILL.md`, `roadmap-planning/SKILL.md`, `project-onboarding/SKILL.md`, `plan/SKILL.md`. The following skills with hits are NOT listed and C5 has no "remaining skills" clause:
- `skills/session-start/SKILL.md` — prose command references (multiple)
- `skills/spinoff/SKILL.md` — `/session-end` Step 2.7 reference
- `skills/review/SKILL.md` — command reference in routing table
- `skills/review-code/SKILL.md` — command reference
- `skills/plan-delivery-audit/SKILL.md` — `session-end-review.md` path reference
- `skills/learn-lessons/SKILL.md` — command reference
- `skills/finishing-a-development-branch/SKILL.md` — command reference
- `skills/dogfood/SKILL.md` — command reference in table
- `skills/parallel-code-review/SKILL.md` — command reference

**Counted as one MISSED item (MISSED-15) covering 9 files** — all share the same gap: C5 does not carry a "remaining skills" clause, and none appear in C5's explicit list.
- **Resolution options:** add "remaining skills" to C5 explicit scope | enumerate each by name | architectural-OOS | oracle-was-wrong

**MISSED-16: `hooks/scripts/tests/test-nudge-improvement-queue-write.sh`**
- Hit: `printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"coordinator:session-end"}}]}}' > "$BIG_SKILL_TRANSCRIPT"` — this is a **functional string** in a test fixture; after the rename, the test may need updating to use `coordinator:session-complete` OR the test deliberately exercises the deprecated skill name. Regardless, no chunk covers hook test files.
- C5 covers `hooks/scripts/nudge-unauthorized-handoff.sh` and `hooks/scripts/session-init.sh` but not `hooks/scripts/tests/`.
- **Resolution options:** add to C5 scope | architectural-OOS (test fixture intentionally exercises deprecated alias — valid keep) | oracle-was-wrong

---

### Ambiguous audit items (signal-partial — informational only)

The following files contain `session-end` hits and fall under C5's consolidating clauses ("remaining wikis", "pipelines/*") but are not explicitly enumerated. Classification: AMBIGUOUS.

1. `docs/wiki/review-integration-doctrine.md` — under C5 "remaining wikis"
2. `docs/wiki/ceremony-calibration.md` — under C5 "remaining wikis"
3. `docs/wiki/getting-started.md` — under C5 "remaining wikis"
4. `docs/wiki/daily-branch-discipline.md` — under C5 "remaining wikis"
5. `docs/wiki/multi-source-daemon.md` — under C5 "remaining wikis"
6. `docs/wiki/plan-delivery-audit.md` — under C5 "remaining wikis"
7. `docs/wiki/reviewer-routed-workers.md` — under C5 "remaining wikis"
8. `docs/wiki/skill-budget-discipline.md` — under C5 "remaining wikis"
9. `docs/wiki/skill-step-parallelization.md` — under C5 "remaining wikis"
10. `docs/wiki/sibling-surface-parity-testing.md` — under C5 "remaining wikis"
11. `docs/wiki/setup-reference-detail.md` — under C5 "remaining wikis"
12. `docs/wiki/tiered-context-loading.md` — under C5 "remaining wikis"
13. `docs/wiki/windows-crash-forensics.md` — under C5 "remaining wikis"
14. `docs/wiki/weekly-gate-architecture.md` — under C5 "remaining wikis"
15. `docs/wiki/verification-discipline.md` — under C5 "remaining wikis"
16. `docs/wiki/writing-plans.md` — under C5 "remaining wikis"
17. `docs/wiki/scoped-safety-commits.md` — under C5 "remaining wikis"
18. `docs/wiki/super-skill-architecture.md` — under C5 "remaining wikis"
19. `docs/wiki/spinoff-handoffs.md` — under C5 "remaining wikis"
20. `docs/wiki/DIRECTORY_GUIDE.md` — under C5 "remaining wikis"
21. `pipelines/update-docs/handoff-archival.md` — under C5 "pipelines/*"
22. `pipelines/executing-plans/PIPELINE.md` — under C5 "pipelines/*"
23. `pipelines/mise-en-place/PIPELINE.md` — under C5 "pipelines/*" (note: C5 says "commands/distill.md (4)" — the PIPELINE file `pipelines/mise-en-place/PIPELINE.md` is a distinct hit)
24. `pipelines/workday-start-internals.md` — under C5 "pipelines/*"

**Note for EM:** The "remaining wikis" and "pipelines/*" language in C5 is a consolidating catch-all. AMBIGUOUS items here don't gate INCOMPLETE but the executor needs explicit direction that these catch-all clauses authorize renaming those files too.

**Files classified as keep-list items (not MISSED, not AMBIGUOUS):**
- `bin/tests/test-coordinator-write-review-trail.sh` — L7 hit is spec-backlink filename only → keep-list item 4
- `tests/plugin-ecosystem/handoff-schema.test.js` — spec-backlink filename only → keep-list item 4
- `tests/fixtures/plan-deviation-reconciliation-fixture.md` — `session-end-deviation-reconciliation-gate.md` filename in comment → keep-list item 4
- `tests/fixtures/plan-deviation-reconciliation-dryrun-trace.md` — same → keep-list item 4
- `whoami/tests/project_rag/test_envelope_conformance.py` — L186: "2026-05-21 session-end code review" is a historical provenance comment, not a command reference → keep-list adjacent (historical marker); EM should verify intent
- `whoami/coordinator_whoami/project_rag/envelope.py` — "2026-05-21-whoami-first-class-substrate session-end" in a code comment is a historical date-provenance marker → keep-list adjacent
- `bin/tests/test-check-no-monolith-completion-append.sh` — hit is a fixture filename `session-end-clean.md` inside a heredoc → historical test fixture, not a command reference
- `bin/tests/test-schema-completion-entry.js` — hits are test fixture data with `session-end crash` in title strings → test data, not command references
- `bin/tests/test-query-completions.js` — same pattern; test fixture data
- `docs/plans/2026-06-01-session-boot-nomenclature.md` — keep-list item 6 explicitly
- `docs/plans/2026-06-01-session-complete-rename.md.prior-art-check.md` — sidecar artifact, not subject to sweep
- `docs/plans/2026-06-01-session-boot-nomenclature.md.plan-coverage-check.md` — sidecar artifact
- `docs/plans/2026-06-01-session-complete-rename.md` — the plan itself
- `docs/plans/2026-05-27-fan-out-default-doctrine.md` — hit is `"## Outcome (session-end 2026-05-27)"` — a historical session heading in a completed plan → keep-list item 4 (historical plan artifact)

---

### Weak OOS / hedges (appetite-based deferrals)

**No weak OOS or appetite hedges found.**

The only hedge token hit is AC9: `"Percolation follow-up noted, not executed."` This sits in the Acceptance Criteria table under AC9, which is classified `advisory`. The corresponding C8 text states: `"Percolation note (do NOT execute): next /percolate to OSS coordinator-claude must carry the renamed skill + the deprecation stub + the CHANGELOG entry together so the published artifact is coherent."` This is OOS-JUSTIFIED: the reason given is architectural — the published artifact must be coherent at percolation time, and pre-execution would violate the publish-direction constraint (source → publish-repo, one-way; percolation is a separate ceremony). Not an appetite hedge.

No tokens matching `future work`, `TBD`, `if time permits`, `nice to have`, `defer to`, `punt on`, `deferred` found in the plan body (excluding the AC table and Anti-scope, which are correct exclusion zones).

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

**DRIFT-1: File count discrepancy — plan claims 92 files, disk has 95**

Plan (L31): `"grep -rl session-end plugins/coordinator-claude/coordinator → 92 files / 379 occurrences"`

Disk at check time: 95 files. The plan acknowledges concurrent work drift: `"drift up from the handoff's 90/321 from concurrent work"`. Three additional files are present at check time beyond the plan's baseline. Two of these (`docs/plans/2026-06-01-session-boot-nomenclature.md.plan-coverage-check.md` and `docs/plans/2026-06-01-session-complete-rename.md.prior-art-check.md`) are sidecar artifacts produced after plan-write that will not require sweep. The third is `docs/plans/2026-06-01-session-complete-rename.md` itself (the plan was authored after the baseline grep).

**This is not a blocking drift** — the plan's own reconciliation instruction ("reconcile against the keep-list, not the raw count") handles this. Reporting for EM awareness. No amend needed.

**No other substrate drift found:**
- `skills/session-end/SKILL.md` — exists on disk ✓ (57,303 bytes)
- `bin/regenerate-orientation-cache.sh` — exists ✓; case arm `session-end|handoff) TIER=mid-session ;;` confirmed at L44 ✓; doc-comment lines at L9/14/18/38 confirmed ✓; plan cites L45 for doc-comment — L45 is `*)...echo ERROR: unknown invoker` which is not a doc comment but is a case arm; the doc-comment line about `--invoker session-end` is at L18, not L45. The "L45" cited in the plan appears to refer to the case arm line. The symbol `session-end|handoff` in the case arm is present and correct. **VERDICT: FALSE-POSITIVE for drift** — line number L45 in the plan description refers to a case arm (found at L44 on disk, one-line drift within ±50-line window). Confirmed present; no drift.
- `schemas/handoff.yaml` L101 — `reviewed_at_session_end: string` confirmed at L101 ✓
- `schemas/handoff-archived.yaml` L48 — `reviewed_at_session_end: string` confirmed at L48 ✓
- `schemas/completion-entry.yaml` — exists ✓
- `CLAUDE.md` L38 — `session-end` in "contact-points" enumeration confirmed at L38 ✓
- `CLAUDE.md` L139 — `/handoff` and `/session-end` are mutually exclusive confirmed at L139 ✓
- `CLAUDE.md` L141 — `/session-end` Step 2.7 reference confirmed at L141 ✓
- `CLAUDE.md` L159 — `session-end/workday/workweek` in test-readiness note confirmed at L159 ✓
- `CLAUDE.md` L182 — `Session-end / weekly marker trail` confirmed at L184 (plan says L182; found at L184 — within ±50-line window; symbol present) ✓
- `dist/publish-repo-toplevel/CHANGELOG.md` L39/135/147/238/343/396/399/544 — all confirmed as historical `session-end` entries ✓
- `docs/wiki/session-end-review.md` — exists on disk ✓
- `dist/publish-repo-toplevel/README.md` — exists ✓

---

### Verdict logic

**INCOMPLETE** — 16 MISSED items (including one compound item covering 9 unlisted skill files and one high-risk functional regex in `bin/coordinator-safe-commit`). 20 AMBIGUOUS items present for EM read-through (consolidating catch-all coverage; do not gate). 0 weak-OOS. 0 appetite hedges. 1 non-blocking file-count note.

**BLOCKED-SURFACE-TO-PM threshold not reached:** 16 MISSED out of ~95 files = 16.8%, below the 20% threshold. 1 substrate-drift finding (non-blocking), below the ≥3 threshold.

**EM actions before named reviewer dispatch:**

1. **Highest priority — `bin/coordinator-safe-commit` (MISSED-6):** Contains a functional regex `\bsession-end\b` in a ceremony-detection branch gate (L713). After the rename, `session-complete` commits will not match. Add `\bsession-complete\b` to that pattern alongside the kept `\bsession-end\b` (deprecation tolerance). Assign to C5 or a new C chunk.

2. **`hooks/scripts/tests/test-nudge-improvement-queue-write.sh` (MISSED-16):** Contains a functional test string `"coordinator:session-end"` in a fixture transcript. EM must decide: (a) update the fixture to use `coordinator:session-complete`, OR (b) designate as an intentional keep-list test for the deprecated alias (architecturally justified). Either way, the chunk slate needs to cover this file's disposition.

3. **9 unlisted skills (MISSED-15):** Add a "remaining skills" clause to C5, or enumerate each skill explicitly. All 9 have live command references needing rename.

4. **`bin/coordinator-write-review-trail.sh` (MISSED-3), `bin/coordinator-session-loe.sh` (MISSED-4), `bin/aggregate-chain-loe.sh` (MISSED-5):** Functional command references in bin/ files. Add to C5 or extend C3.

5. **`lib/coordinator-session.sh`, `lib/workweek-trail-scope.sh` (MISSED-1, MISSED-2):** Prose command references in lib/ files.

6. **`bin/cross-repo-memo` (MISSED-8), `commands/workday-start.md` (MISSED-10), `commands/mise-en-place.md` (MISSED-11), `agents/review-integrator.md` (MISSED-13), `canonical-structure.yaml` (MISSED-12), `README.md` root (MISSED-9), `dist/oss-only-skills/coordinator-update/SKILL.md` (MISSED-14), `bin/check-no-monolith-completion-append.sh` (MISSED-7):** Add to appropriate chunks.

7. **AMBIGUOUS wikis and pipelines:** Confirm to the executor that "remaining wikis" and "pipelines/*" in C5 authorizes renaming all files in those groups, not just the explicitly listed ones.

---

**Cost estimate:** ~12K tokens (95 file grep + targeted per-file spot checks + substrate line-number verification across ~15 cited locations)
