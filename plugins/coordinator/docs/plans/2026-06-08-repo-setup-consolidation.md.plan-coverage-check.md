---
title: Plan Coverage Check — 2026-06-08-repo-setup-consolidation
created: 2026-06-08
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: docs/plans/2026-06-08-repo-setup-consolidation.md
---

## Plan Coverage Verification

**Plan:** `docs/plans/2026-06-08-repo-setup-consolidation.md`
**Verdict:** INCOMPLETE
**Oracle items:** 32 explicit named items (source: `## Substrate` section, file enumeration list; 2 commands + 2 lib + 3 bin + 1 yaml + 1 CLAUDE.md + 3 skills + ~15 wikis + 4 plan-related + 2 dist)
**Slate items:** 10 (C1-C10)
**Missed:** 5 | **Ambiguous:** 2 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 1

---

### Lens 1 — Coverage (Oracle-vs-Slate Cross-Reference)

#### MATCHED items (signal-confirmed)

All explicitly-named oracle files map cleanly to a chunk:

| Oracle file | Owning chunk | Signal |
|---|---|---|
| `skills/project-onboarding/SKILL.md` | C1 | shared file-path |
| `commands/bootstrap-repos.md` | C2 | shared file-path |
| `commands/setup.md` | C5 | shared file-path |
| `lib/bootstrap-orchestrate.sh` | C3 | shared file-path |
| `lib/detect-onboarding-offer.sh` | C3 | shared file-path |
| `bin/coordinator-doctor-sentinel.sh` | C4 | shared file-path |
| `bin/detect-project-runtime.sh` | C4 | shared file-path |
| `bin/tests/test-detect-onboarding-offer.sh` | C4 | shared file-path |
| `canonical-structure.yaml` | C4 | shared file-path |
| `coordinator/CLAUDE.md` | C8 | shared file-path |
| `skills/workstream-start/SKILL.md` | C8 | shared file-path |
| `skills/roadmap-planning/SKILL.md` | C8 | shared file-path |
| All 14 wikis in `docs/wiki/` | C6 + C7 | shared file-path (see wiki analysis below) |
| `docs/plans/2026-05-30-onboarding-install-redesign.md` | C9 | shared file-path |
| `dist/publish-repo-toplevel/CHANGELOG.md` | C9 | shared file-path |
| `dist/publish-repo-toplevel/README.md` | C9 | shared file-path |

#### Wiki coverage analysis (C6 + C7)

The plan states "~15 wikis". A live grep of `docs/wiki/*.md` for `project-onboarding|bootstrap-repos` returns **exactly 14 files**:

**C6 (Batch A — 8 wikis):**
`coordinator-doctor.md`, `coordinator-installer-shape.md`, `coordinator-installer-status-schema.md`, `coordinator-tripwires.md`, `super-skill-architecture.md`, `setup-reference-detail.md`, `delegate-execution.md`, `DIRECTORY_GUIDE.md`

**C7 (Batch B — 6 wikis):**
`concurrent-em-hazards.md`, `cross-plugin-whoami-contract.md`, `gitattributes-lfs-carve-outs.md`, `handoff-tracker-system.md`, `lfs-coordinator-auto-push-merge.md`, `project-onboarding-claude-md-render.md`

C6 + C7 = 14 wikis, matching the actual grep count exactly. No overlap. No omission within the wiki tree. The oracle's "~15" approximation is slightly off (actual: 14) but the chunk slate is correct.

#### AMBIGUOUS items

1. **Plan sidecars** — The oracle says "4 plan-related (the two 2026-05-30 plans, their sidecars, and `2026-06-01-session-complete-rename.md`)". The actual grep found 5 plan files outside this plan itself: `2026-05-30-onboarding-install-redesign.md` + its 2 sidecars (`.plan-coverage-check.md`, `.prior-art-check.md`) + `2026-06-01-session-complete-rename.md` + its sidecar (`2026-06-01-session-complete-rename.md.plan-coverage-check.md`). C9 only explicitly owns the 2026-05-30 plan body. The plan's OOS section says "Historical references in archive/ remain as-is" and AC3's allow-list covers "their `.plan-coverage-check.md` / `.prior-art-check.md` sidecars (historical records)". The sidecar files are explicitly allowed to retain old references under AC3. This is AMBIGUOUS (coverage by allow-list exclusion rather than explicit C9 citation) but not MISSED — the EM should verify AC3's allow-list text matches every sidecar pattern on disk.

2. **`dist/publish-repo-docs/agent-install.md`** — C9 says "(if it references the old names — verify in chunk)". A live grep confirms this file has zero references to `project-onboarding` or `bootstrap-repos` as of 2026-06-08. The conditional is correctly written; this file is not in scope at HEAD. AMBIGUOUS signal (file exists, no current drift) — no action needed, but the EM should confirm C9's verification step closes cleanly.

---

### Missed audit items (no slate entry, no architectural OOS)

The live repo-wide grep (`grep -r 'project-onboarding|bootstrap-repos'`) found **5 files with live references** that are not in the plan's oracle and not claimed by any chunk C1-C9. After consolidation, these will cause AC3 failures (AC3 requires zero references outside its allow-list):

#### MISSED-1: `README.md` (coordinator root)

**Oracle entry:** Not present.
**Live reference:** `README.md` line 169: `- \`project-onboarding\` — Bootstrap project tracking infrastructure — tracker, tasks, archive, handoffs.`
**Owning chunk:** None.
**AC3 status:** Not in AC3 allow-list. Will cause AC3 grep to return a hit after consolidation.
**Resolution options:** add-to-slate (add a C2 or C5 write-set entry) | add-to-OOS with architectural reason | amend oracle with explanatory note (oracle-was-wrong).

#### MISSED-2: `lib/coordinator-currency.sh`

**Oracle entry:** Not present.
**Live reference:** `lib/coordinator-currency.sh` line 5: `# Consumed by /project-onboarding (stamp write),`
**Owning chunk:** None.
**AC3 status:** Not in AC3 allow-list. Will cause AC3 grep hit.
**Resolution options:** add-to-slate (add to C3's write-set alongside the other lib helpers) | add-to-OOS with architectural reason | amend oracle with explanatory note.

#### MISSED-3: `bin/doctor-probes.toml`

**Oracle entry:** Not present.
**Live reference:** `bin/doctor-probes.toml` line 214: `remediation = "Re-run /project-onboarding to stamp this repo with the current coordinator schema version"`
**Owning chunk:** None. C4 owns `bin/coordinator-doctor-sentinel.sh` and `bin/detect-project-runtime.sh` and `bin/tests/test-detect-onboarding-offer.sh` but does not name `bin/doctor-probes.toml`.
**AC3 status:** Not in AC3 allow-list. User-facing remediation message will name the old command post-consolidation.
**Resolution options:** add-to-slate (add to C4's write-set) | add-to-OOS with architectural reason | amend oracle.

#### MISSED-4: `whoami/coordinator_whoami/project_rag/envelope.py`

**Oracle entry:** Not present.
**Live reference:** `whoami/coordinator_whoami/project_rag/envelope.py` line 33: `# non-empty; the "unbound" branch in downstream consumers (project-onboarding,`
**Owning chunk:** None. The plan has no `whoami/` chunk.
**AC3 status:** Not in AC3 allow-list (AC3 filters `coordinator/` tree — whether `whoami/` is under `coordinator/` depends on repo root). If in scope of the AC3 grep, this will be a hit.
**Resolution options:** add-to-slate | add-to-OOS (comment-only, no functional change — architectural case is plausible) | amend oracle with explanatory note.

#### MISSED-5: `whoami/tests/project_rag/test_envelope_conformance.py`

**Oracle entry:** Not present.
**Live reference:** `whoami/tests/project_rag/test_envelope_conformance.py` line 195: `The "unbound" branch in /project-onboarding and /session-start could never fire.`
**Owning chunk:** None.
**AC3 status:** Same as MISSED-4 — depends on AC3 grep scope.
**Resolution options:** add-to-slate | add-to-OOS (test comment, no functional impact) | amend oracle with explanatory note.

---

### Ambiguous audit items (signal-partial — informational only)

1. **Plan sidecars for 2026-05-30 and 2026-06-01** — See discussion in AMBIGUOUS section above. AC3 allow-list covers them by pattern. EM should confirm the allow-list regex `docs/plans/2026-05-30-*` and `docs/plans/2026-06-01-*` actually matches all sidecar filename variants (`.plan-coverage-check.md`, `.prior-art-check.md`). Does NOT count toward INCOMPLETE.

2. **`dist/publish-repo-docs/agent-install.md`** — C9 carries a conditional verification instruction; live disk state shows zero references. No action required at HEAD. Does NOT count toward INCOMPLETE.

---

### Weak OOS / hedges (appetite-based deferrals)

None found. No hedge tokens (`follow-up`, `TBD`, `if time permits`, `defer`, `future work`, `not now`, `for now ... later`) appear in the plan body. The Out of Scope section items are all architecturally framed:

- "No new behavior in single-repo mode" — scope boundary, not appetite hedge (behavior is preserved verbatim, no new functionality is deferred).
- "No template churn" — irreversibility argument (templates are shared across consumers; rename churn with no functional change is pure risk-add).
- "No `coordinator:setup` flow change" — scope boundary (setup chain kept current shape; only verb-rename touches it via C5).
- "No archive churn" — explicit architectural reason: archives are time-frozen historical records.
- "No OSS-distribution shape change" — pure rename-repoint, explicitly bounded; agent-install.md confirmed zero references at HEAD.

All OOS items pass the architectural-justification test.

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

#### DRIFT-1: Oracle count mismatch ("35 files" vs. actual 39 files in grep)

**Plan citation:** "**35 files** reference `project-onboarding` or `bootstrap-repos`" (Substrate section)
**Disk state:** Live grep of the full coordinator tree returns **39 files** with matches (including this plan itself = 38 files to fix). The 5 MISSED files above account for the difference between 34 (oracle's named items accounting for 1 from "this plan itself") and 38 actual.
**Note:** This is a count-level substrate inaccuracy, not a path drift. The named file categories are all correct on disk. The issue is that the oracle undercounts by 4-5 unlisted files.
**Suggested action:** Amend the oracle count or add the missing files to the oracle + slate.

#### All named path citations — CONFIRMED on disk

Every file path cited explicitly in the plan was verified present at HEAD:

| Path cited | Disk state |
|---|---|
| `skills/project-onboarding/SKILL.md` | EXISTS; line 2: `name: project-onboarding` ✓ |
| `commands/bootstrap-repos.md` | EXISTS ✓ |
| `lib/bootstrap-orchestrate.sh` | EXISTS; line 3 references `coordinator:bootstrap-repos` ✓ |
| `lib/detect-onboarding-offer.sh` | EXISTS; lines 4-5 reference `/project-onboarding` ✓ |
| `bin/coordinator-doctor-sentinel.sh` | EXISTS; lines 441, 444 reference `/project-onboarding` ✓ |
| `bin/detect-project-runtime.sh` | EXISTS; lines 3, 10, 124 reference `project-onboarding` ✓ |
| `bin/tests/test-detect-onboarding-offer.sh` | EXISTS; lines 158-161 match cited content ✓ |
| `canonical-structure.yaml` | EXISTS; line 3 and line 21 reference `project-onboarding` ✓ |
| `coordinator/CLAUDE.md` | EXISTS; line 38 references `/project-onboarding` in contact-points list ✓ |
| `docs/plans/2026-05-30-onboarding-install-redesign.md` | EXISTS; line 57 contains "Command names unchanged" with `/project-onboarding` ✓ |
| `commands/setup.md` | EXISTS ✓ |
| `skills/workstream-start/SKILL.md` | EXISTS ✓ |
| `skills/roadmap-planning/SKILL.md` | EXISTS ✓ |
| `dist/publish-repo-toplevel/CHANGELOG.md` | EXISTS ✓ |
| `dist/publish-repo-toplevel/README.md` | EXISTS ✓ |
| `dist/publish-repo-docs/agent-install.md` | EXISTS; zero matches for old names (C9 conditional resolves as skip) ✓ |
| All 14 named wikis in C6 + C7 | EXISTS on disk ✓ |

**Line-number verification:** All cited line numbers (`SKILL.md` line 2, `bootstrap-orchestrate.sh` line 3, `detect-onboarding-offer.sh` lines 4-5, `doctor-sentinel.sh` lines 441/444, `detect-project-runtime.sh` lines 3/10/124, `test-detect-onboarding-offer.sh` lines 158-161, `canonical-structure.yaml` lines 3/21, `CLAUDE.md` line 38, `2026-05-30` plan line 57) all confirmed present within the cited line numbers or within ±50-line tolerance. No line-drift found.

---

### Verdict logic

**Verdict: INCOMPLETE**

Reason: 5 MISSED oracle items (MISSED-1 through MISSED-5) — files with live `project-onboarding` references that are not in the plan's oracle and not claimed by any chunk. All 5 will cause **AC3 failures** after C1-C9 execute, because AC3 requires zero `project-onboarding|bootstrap-repos` references in the coordinator tree outside its explicit allow-list, and none of these 5 files appear in that allow-list.

BLOCKED-SURFACE-TO-PM threshold not reached: 5 MISSED out of ~32 oracle items = ~16% (threshold is ≥20%). Substrate-drift count is 1 (count mismatch only, no path-level drift; threshold is ≥3).

**EM action before named-reviewer dispatch:** resolve each MISSED item using one of the three valid resolutions:
1. `add-to-slate` — add the file to the owning chunk's write-set (MISSED-2 → C3; MISSED-3 → C4; MISSED-1 → C2 or C5; MISSED-4/5 → new mini-chunk or C8)
2. `architectural-OOS` — document why the reference is intentionally preserved (only plausible for MISSED-4/5 which are comment-only in `whoami/` Python code)
3. `oracle-was-wrong` — amend the oracle with an explanatory note (only valid if these references are genuinely not within AC3's grep scope — verify AC3's grep path prefix)

The fastest resolution: verify whether AC3's grep scope (`grep -r ... coordinator/`) includes `whoami/` — if not, MISSED-4/5 can be oracle-was-wrong (out of AC3 scope). MISSED-1, MISSED-2, MISSED-3 are clearly in scope and need slate entries.

---

**Cost estimate:** ~4,200 tokens (32 oracle items × 1 slate cross-reference pass + 39 substrate verifications via grep/read)
