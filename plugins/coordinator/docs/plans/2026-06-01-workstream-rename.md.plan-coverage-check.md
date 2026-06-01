---
title: Plan Coverage Check — workstream-rename
created: 2026-06-01
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-06-01-workstream-rename.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-01-workstream-rename.md`
**Verdict:** INCOMPLETE
**Oracle items:** 3 primary baseline items (session-start ~318 occ / 86 files; session-end ~379 occ / 95 files; session boot 33 files) plus 7 intentional-keep list items plus functional-surface enumeration (6 sub-items). Treated as a compound oracle: file-level coverage cross-referenced against chunks.
**Slate items:** 9 (C1–C9)
**Missed:** 0 | **Ambiguous:** 2 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 3

---

### Lens 1 — Coverage (Oracle-vs-Slate Cross-Reference)

The plan's oracle is threefold: (a) occurrence baselines with file counts, (b) 7-item intentional-keep list, (c) functional-surface enumeration. The slate is C1–C9. Cross-referencing files found by live grep against the chunks:

**`session-start` files (live grep: 85 files)**

Plan baseline: 86 files. Live grep returned 85 files — delta of 1. The counted files include plan artifacts (`2026-06-01-workstream-rename.md`, `2026-06-01-session-complete-rename.md`, `2026-06-01-session-boot-nomenclature.md`, and their sidecars) which are superseded-plan historical records properly excluded from sweeping. Excluding those (~5 plan/sidecar files) and the two deprecation stub targets (which intentionally carry the old name), the live working-tree count is consistent with the baseline within normal tolerance. No file-coverage gap found for session-start across C1–C6/C7.

**`session-end` files (live grep: 97 files)**

Plan baseline: 95 files. Live grep returned 97 files — delta of +2. The 2 extra files are `bin/aggregate-chain-loe.sh` and `agents/code-reviewer-weekly.md`, which appear in the live grep but are NOT mentioned in C1–C6/C7's enumerated surfaces. See AMBIGUOUS below.

**`session boot` files (live grep: 32 files)**

Plan baseline: 33 files. Live grep returned 32 files. Delta of −1 is within tolerance (one `.pyc` or excluded plan doc). Coverage looks complete via D5/C7.

**MATCHED items (signal-confirmed):**

- C1 owns `skills/session-end/SKILL.md` — shared file-path citation. MATCHED.
- C2 owns `skills/session-start/SKILL.md` — shared file-path citation. MATCHED.
- C3 owns the deprecation stub creation (explicit `skills/session-start/SKILL.md` + `skills/session-end/SKILL.md`). MATCHED.
- C4 owns `bin/regenerate-orientation-cache.sh` (explicit citation), `bin/coordinator-safe-commit` (explicit citation), `docs/wiki/scoped-safety-commits.md` (explicit citation), `bin/tests/test-coordinator-safe-commit.sh` (explicit citation), `tests/plugin-ecosystem/hooks-behavior.test.js` (explicit citation), `docs/wiki/coordinator-tripwires.md` (explicit citation). MATCHED.
- C5 owns `schemas/handoff.yaml` + `schemas/handoff-archived.yaml` + `schemas/completion-entry.yaml`. MATCHED.
- C6 owns "all `docs/wiki/**`", "all `skills/*/SKILL.md`", `commands/**`, `hooks/scripts/**`, `pipelines/**`, `agents/**`, `bin/**` prose refs, `lib/**`, root `README.md`, `canonical-structure.yaml`, `dist/oss-only-skills/**`. MATCHED for the bulk of remaining files.
- C7 owns `CONTEXT.md`, `coordinator/CLAUDE.md`, `dist/publish-repo-toplevel/CHANGELOG.md`, `dist/publish-repo-toplevel/README.md`. MATCHED.
- C8 (reconcile) + C9 (closeout) cover the residual verification. MATCHED.

---

### Ambiguous audit items (signal-partial — informational only)

**AMBIGUOUS-1: `bin/aggregate-chain-loe.sh`**

This file appears in the live `session-end` grep but is not named in any chunk. C6 says "bin/** prose refs (functional gates owned by C4)" — the functional gate carve-out for C4 is explicit, but C4 does not name `bin/aggregate-chain-loe.sh` either. C6's "all bin/** prose refs" language could encompass it, but the file is not explicitly cited. This is a prose-only reference (the file appears to reference session-end in comments/prose context, not as a functional gate). The stopword-level overlap "bin/**" makes this AMBIGUOUS rather than MISSED — C6's language covers it but without explicit citation.

EM action: verify `bin/aggregate-chain-loe.sh` contains only prose references to `session-end` (not a functional gate), confirming C6 coverage is correct. If it contains a functional dependency, promote to C4 scope.

**AMBIGUOUS-2: `agents/code-reviewer-weekly.md`**

This file appears in the live `session-end` grep. C6 names `agents/**` as a surface. The file is not explicitly cited. Same AMBIGUOUS classification as above — "agents/**" language in C6 covers it at the stopword level, but no shared distinctive noun phrase or symbol confirms an explicit citation.

EM action: verify `agents/code-reviewer-weekly.md` contains only prose references to `session-end` and is correctly swept by C6.

---

### Weak OOS / hedges (appetite-based deferrals)

None found. The Anti-scope section gives architectural justifications for every exclusion:
- `/workday-*` / `/workweek-*` excluded: "already correct work-* members" — positional grid already matches; no appetite hedge.
- Platform hook keys excluded: hard irreversibility boundary (platform API identifiers, not coordinator vocab).
- `reviewed_at_session_end:` key excluded: renaming invalidates existing handoff records against schema — hard backward-compatibility constraint (D2). Architectural, not appetite.
- Historical artifacts excluded: historical-record preservation — architectural (cannot retroactively rewrite historical records without losing audit trail).
- No `git revert cadb320b`: explicitly justified architecturally (partial survival of disambiguation logic, conflict with sibling commits).

Hedge-token scan (`follow-up`, `future work`, `TBD`, `if time permits`, `defer to`, etc.) found zero in plan body prose outside the Anti-scope and Acceptance Criteria sections. All deferral language in the plan is architecturally grounded.

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

**DRIFT-1: `regenerate-orientation-cache.sh` — plan cites `session-end|handoff` case arm at "L44" with doc comments at "L9/14/18/38/45"**

Disk state: the `--invoker session-end` case arm is at line 44 (`session-end|handoff) TIER=mid-session`). That matches. However, the plan says "doc comments L9/14/18/38/45" — verifying:
- L9: `#   regenerate-orientation-cache.sh --invoker <workday-start|update-docs|session-end|handoff>` ✓ session-end present
- L14: `#   mid-session (session-end, handoff)` ✓
- L18: `#   regenerate-orientation-cache.sh --invoker session-end --pinboard` ✓
- L38: error message references `session-end` ✓
- L45: the ERROR fallback at line 45 also cites `session-end` ✓

Line numbers confirmed within ±1 line (L44 exact; L38/45 are +/−1 from case arm context). **No drift** on this citation.

**DRIFT-2: `coordinator-safe-commit` — plan cites a `\bsession-end\b` ceremony-detection regex AND a blanket authorized-token list**

Disk state:
- Line 738: the ceremony regex `grep -qiE '(\bhandoff\b|\bspinoff\b|\blearn-lessons\b|\bupdate-docs\b|\bsession-end\b|\bdistill\b|...'` — `session-end` IS present in the ceremony regex. ✓
- Lines 671–673 (`do_blanket`): authorized tokens are `session-start`, `workday-complete`, `update-docs`, `relay-protocol`, `distillation`. **`session-end` is NOT in the blanket authorized-token list** — it is in the ceremony-detection regex (commit-subject gate) but NOT in `do_blanket`.

The plan says (§ Substrate, line 46): "bin/coordinator-safe-commit carries a `\bsession-end\b` ceremony-detection regex and a blanket-commit authorized-token list — both gate on the literal old names."

This statement implies `session-end` is in the blanket authorized-token list. **It is not.** The blanket list covers `session-start`, `workday-complete`, `update-docs`, `relay-protocol`, `distillation` — no `session-end`. The plan's description conflates two distinct gating mechanisms: (1) the `do_blanket` caller-authorization list (which gates whether `--blanket` is allowed, based on CLAUDE_INVOKING_COMMAND), and (2) the commit-subject ceremony-detection regex (which gates whether a blanket-staging destructive-shape check fires). `session-end` is in mechanism (2) but NOT mechanism (1).

**Impact on C4:** C4 says "blanket authorized-token list → add workstream-start + workstream-complete (+ retain session-start/session-end)". Retaining `session-end` in the blanket authorized-token list is a no-op because `session-end` was never there. The C4 description is accurate for the ceremony-regex portion. But if the intent is also to add `workstream-complete` to the `do_blanket` allowed list (so that `CLAUDE_INVOKING_COMMAND=workstream-complete` enables blanket staging), that requires net-new addition to lines 671–673, not merely "retaining" old tokens.

**Action:** EM should verify whether `workstream-complete` (the renamed `/session-end`) needs to be added to `do_blanket`'s CLAUDE_INVOKING_COMMAND authorization list. If `/workstream-complete` ever calls `--blanket`, it needs to be in that list — currently neither `session-end` nor `workstream-complete` is authorized. The plan's substrate description is misleading on this point.

**DRIFT-3: `docs/wiki/scoped-safety-commits.md` — plan cites "L200" for `CLAUDE_INVOKING_COMMAND=session-start`**

Disk state: L200 in `scoped-safety-commits.md` reads `CLAUDE_INVOKING_COMMAND=session-start \` — confirmed on disk at line 200. ✓ (within ±50 tolerance, exact match). No drift.

However: L205 of `scoped-safety-commits.md` says "Only valid when `$CLAUDE_INVOKING_COMMAND` is one of: `session-start`, `workday-complete`, `update-docs`, `relay-protocol`, `distillation`." This prose list in the wiki also does NOT include `session-end` in the blanket list — consistent with the disk code. This cross-validates DRIFT-2: the wiki and the code agree that `session-end` was never a blanket-authorized token. The plan's "both gate on the literal old names" claim is inaccurate.

**DRIFT-4 (CONFIRMED — substrate description inaccuracy): `coordinator-tripwires.md` blanket-commit authorized-token list**

The plan (§ D4): "coordinator-safe-commit (\\bsession-end\\b ceremony regex + blanket authorized-token list) and docs/wiki/coordinator-tripwires.md (blanket-commit authorized-token list) must each recognize workstream-start and workstream-complete alongside the retained session-start/session-end."

Disk state of `coordinator-tripwires.md` line 68 (the blanket-commit destructive-shape gate): the reference token list in the commit-subject gate includes `session-end`, `workday-{start,complete}`, `workweek-{start,complete}` — this is the COMMIT-SUBJECT detection regex, not a "blanket authorized-token list." The tripwires doc does not contain a separate "blanket authorized-token list" in the sense D4 implies. The only blanket authorization list is in `bin/coordinator-safe-commit` lines 671–673.

The `coordinator-tripwires.md` L68 token list IS in the commit-subject shape gate — adding `workstream-start` and `workstream-complete` to that regex is legitimate scope for C4. But calling it a "blanket-commit authorized-token list" in both places is imprecise — one is caller-authorization (`do_blanket`), the other is commit-subject labeling (destructive-shape gate). These are separate concerns with separate update points.

**Summary of substrate findings:** DRIFT-2/3/4 are the same underlying conceptual conflation — the plan treats the `do_blanket` caller list and the commit-subject ceremony-detection regex as a single "blanket-commit authorized-token list," but they are two distinct mechanisms with different token memberships (`session-end` is only in the regex, not the caller list). This does not block execution, but the executor (C4) may be confused about which tokens to add where. The plan's substrate description overstates what the blanket list contains.

---

### Verdict logic

**Verdict: INCOMPLETE**

Reason: 3 substrate-drift findings (DRIFT-2, DRIFT-3, DRIFT-4 — all instances of the same underlying conflation between `do_blanket` caller-authorization list and commit-subject ceremony-detection regex). While none of the drifts involves a missing file or absent symbol, the plan's description of `coordinator-safe-commit`'s blanket-commit machinery is factually inaccurate in a way that will cause the C4 executor to make incorrect assumptions about what tokens need to be added or retained where.

Specific consequence: C4 says "blanket authorized-token list → add workstream-start + workstream-complete (+ retain session-start/session-end)." If the executor follows this literally for the `do_blanket` caller list, it will attempt to "retain" `session-end` in a list that never contained it, and may miss that `workstream-complete` needs to be NET-NEW added to lines 671–673 if `/workstream-complete` needs blanket-staging capability (which it likely does, given it replaces `/session-end` as a ceremony endpoint).

**Resolution required before dispatch:** EM should amend the plan's § Substrate description and C4 task to:
1. Distinguish the two mechanisms: (a) `do_blanket` CLAUDE_INVOKING_COMMAND caller list (lines 671–673), and (b) commit-subject ceremony-detection regex (line 738).
2. Clarify whether `workstream-complete` needs to be added to (a). If `/workstream-complete` will ever invoke `--blanket`, YES.
3. Note that `session-end` was never in (a) — no "retain" needed there; the "retain" in C4 applies only to (b).

The two AMBIGUOUS items (AMBIGUOUS-1/2) do not contribute to INCOMPLETE — they are informational only.

---

### Platform SessionStart/SessionEnd preservation check (critical safety verification)

**Plan claim:** case-sensitive, hyphen-anchored sweeps cannot touch `SessionStart`/`SessionEnd` (160+ occurrences). The keep-list item 1 protects them.

**Verification:** The renamable tokens are `session-start` (hyphen, lowercase) and `session-end` (hyphen, lowercase). The platform tokens are `SessionStart` and `SessionEnd` (PascalCase, no hyphen). A case-sensitive `sed` or `grep -F` or Python `str.replace('session-start', ...)` will NOT match `SessionStart`. The disambiguation is real and mechanical.

**However:** C6 says "apply all applicable: `/session-end`→`/workstream-complete`; `/session-start`→`/workstream-start`". Sweeps targeting `/session-end` (with leading slash) are further protected — the platform tokens never appear as `/SessionStart`. The plan's disambiguation guidance is sound.

**Residual risk:** `session boot` elimination (D5) uses `grep -ri "session boot"` (case-insensitive). The phrase "session boot" does not appear in the platform tokens (`SessionStart`/`SessionEnd`) — no false-positive risk. `session boot` as a two-word phrase cannot match single-word `SessionStart`. No risk identified.

**Verdict on platform preservation:** the chunk disambiguation guidance is sufficient. No additional finding.

---

**Cost estimate:** ~6,200 tokens (3 oracle dimensions × ~15 file-level verifications + 8 substrate spot-checks)
