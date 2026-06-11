# Session-Boot Nomenclature Reorientation (front half)

**Date:** 2026-06-01
**Author:** EM (Striker session)
**Scope mode:** `feature` (introduces a vocabulary convention — "session boot" — that must be defined once and applied consistently)
**Status:** SUPERSEDED (2026-06-01) — do NOT execute.

> **Superseded by:** the unified `workstream-*` rename, master brief at `state/handoffs/2026-06-01_132000_05c3317c.md`. The PM pivoted: rather than coin "session boot" for the machinery, rename the skills off the word "session" entirely (`/session-start → /workstream-start`, `/session-end → /workstream-complete`) and adhere to platform vocabulary (`SessionStart` is the platform hook; "session boot" coinage is reverted). The "session boot" front-half shipped in `cadb320b` is to be reverted by the successor. This plan and its sidecars are retained as audit trail only.

## Problem (falsifiable restatement)

Today the token `session start` / `session-start` / `SessionStart` names **two different things**, and the confusion is patched with scattered disambiguation memos rather than fixed at the nomenclature level:

1. **`/session-start`** — the explicit, PM-invoked orientation *skill* (`skills/session-start/SKILL.md`: "Orient session — preflight, load context, choose work").
2. **The automatic machinery that fires when a Claude session opens** — the `SessionStart` platform hook block in `hooks.json` plus its scripts (`session-init.sh`, `project-orientation.sh`, `coordinator-reminder.sh`, `ue-knowledge-distrust.sh`) and the Tier-0 `orientation_cache` read.

Because both collapse to "session start," doctrine has accumulated scabs to keep them apart: a parenthetical at `coordinator/CLAUDE.md` L7-8, a whole wiki, and skill-internal notes.

**The fix:** establish **"session boot"** as the canonical, defined term for the automatic machinery (path #2) — the term is already in organic use across ~6 prior-art surfaces (see C1 note); this plan formalizes it, not coins it. Reserve **`/session-start`** strictly for the skill (path #1). Define the term once in `CONTEXT.md`, apply it across every ambiguous reference, and reframe the disambiguation scabs into plain statements.

<!-- Review: the Staff Engineer (Finding 2) — "coin" is factually wrong; "session boot" already appears in tiered-context-loading.md, implementation-standards-by-domain.md, learn-lessons-routing.md, daily-branch-discipline.md, eager-agent-calibration.md, coordinator/CLAUDE.md L149. The plan formalizes an existing informal convention; "coin" undercuts a nomenclature plan's authority. -->

**Falsifiable done-state:** after this change, (a) `CONTEXT.md` formalizes "session boot" as the canonical defined term and defines the ceremony grid; (b) the `coordinator/CLAUDE.md` L7-8 parenthetical is no longer a *disambiguation* (it becomes a plain factual clause); (c) every prose/comment reference to the automatic path says "session boot," every reference to the skill says `/session-start`, and `SessionStart` (PascalCase) appears only when naming the literal platform hook matcher.

<!-- Review: the Staff Engineer (Finding 2) — "coin" replaced with "formalizes" / "canonical defined term" throughout done-state bullet; same rationale as problem-statement fix. -->

### Platform constraint (load-bearing)

The literal hook key in `hooks.json` is `SessionStart` — a **Claude Code platform identifier we cannot rename.** This is therefore a **prose/concept reorientation, not a machinery rename.** We do not touch what executes. `SessionStart` (PascalCase, no slash) is retained wherever we refer to the literal hook matcher; "session boot" is the human/doctrine term for the concept; `/session-start` is the skill. Runtime risk ≈ zero.

### Resolved open item

`hooks.json` contains only `SessionStart` and `PreCompact` matchers — **no `Stop`/`SessionEnd` hook.** The back-end "auto-fire" of `/session-end` is doctrine prose, not a platform hook. Therefore the back end has no automatic machinery and needs **no "session teardown" coinage.** The front/back asymmetry is intentional and correct: front = machinery ("session boot") + skill (`/session-start`); back = skill only.

### Inferred intent (flagged for PM)

- Inferring the PM wants the `CLAUDE.md` L7-8 scab *reframed away*, not merely softened. ✅ safe — "instead of leaving this as a scab."
- Inferring "session boot" should be a *real, greppable convention* (defined in `CONTEXT.md`), not just informal prose. ✅ safe — "reorient our nomenclature."
- **EM-decided (not PM-altitude):** keep the wiki *filename* `plugin-session-start-hooks.md` (it's literally about the platform `SessionStart` hook); reframe its intro rather than `git mv`. Avoids link-rot churn across its 6 referrers.

## Out of scope (separate, spun-off workstream)

The `/session-end → /session-complete` rename is **NOT** in this plan. It is a 321-occurrence / 90-file identifier rename with runtime-token + stored-data couplings, forked to `state/handoffs/2026-06-01_125306_session-complete-rename.md` (workstream `session-complete-rename`). This plan touches **disjoint files** from that one (no `session-end` edits here).

## Cross-plan coordination

Scanned `docs/plans/*.md` for `session-start` / `session boot` file-scope and seam overlap:
- `2026-05-30-onboarding-install-redesign.md`, `2026-05-30-pickup-cross-repo-memo-fork.md`, `2026-05-27-fan-out-default-doctrine.md` reference `/session-start` only as a *surfacing point* (correct skill usage) — no file-overlap, no conflict.
- Related workstream: the `session-complete-rename` spinoff (back half). Disjoint file scope (`session-end` vs `session-start`/boot). Picking-up EM of that spinoff is instructed to run a cross-plan scan against this plan.
- No overlapping file scope or seam citations requiring amendment.

## Acceptance criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|----|-------------------|---------------------|---------------|--------|
| AC1 | `CONTEXT.md` defines "session boot" (the automatic session-open machinery) and the ceremony grid `{session,workday,workweek} × {start,complete}`. | `grep:"**session boot** —" ~/.claude/CONTEXT.md` returns the glossary-entry anchor | gate | pending realization |
<!-- Review: the Staff Engineer (Finding 4) — tightened test to grep for the glossary-entry prefix "**session boot** —" so the gate discriminates "definition landed" from an incidental string occurrence. -->
| AC2 | The `coordinator/CLAUDE.md` L7-8 parenthetical no longer reads as a skill-vs-boot *disambiguation*; it states the Tier-0 boot read fact plainly using "session boot". | `cited:coordinator/CLAUDE.md § Session Orientation` reviewer-confirmed | gate | pending realization |
| AC3 | Every prose/comment reference to the automatic path uses "session boot"; `SessionStart` (PascalCase) appears only for the literal hook matcher; `/session-start` only for the skill. | `cited:` reviewer reads each edited site | gate | pending realization |
| AC4 | The hooks wiki intro states these hooks constitute the "session boot" path and are distinct from the `/session-start` skill; filename unchanged. | `grep:"session boot" docs/wiki/plugin-session-start-hooks.md` | gate | pending realization |
| AC5 | No machinery behavior changed — `hooks.json` matchers, script bodies, and the `SessionStart` key are byte-identical except where a comment is reworded. | `grep:` diff shows no logic lines changed in hooks.json/scripts | gate | pending realization |
| AC6 | Percolation follow-up to OSS via `setup/publish.sh` is noted (not executed). | `cited:` plan closeout section | advisory | pending realization |

## Chunks

Execution is **EM-direct via `/execute-plan`** (not executor fan-out): each occurrence requires skill-vs-machinery classification judgment that a mechanical find-replace would get wrong. The classification below is the executor's spec.

### C1 — Define the vocabulary (`CONTEXT.md`)
Add two glossary entries to `~/.claude/CONTEXT.md`:
- **session boot** — the automatic machinery that runs when a Claude Code session opens: the `SessionStart` platform-hook block in `hooks.json` and its scripts (`session-init.sh`, `project-orientation.sh`, `coordinator-reminder.sh`, `ue-knowledge-distrust.sh`), plus the Tier-0 `orientation_cache` read. Distinct from `/session-start` (the skill). The literal platform hook event is `SessionStart`; "session boot" is the concept it implements.
- **ceremony grid** — the explicit, PM-invoked lifecycle skills form a 2×3 grid: `{session, workday, workweek} × {start, complete}`. `-start` = front-of-unit orientation; `-complete` = end-of-unit wrap-up. (Note: `/session-end → /session-complete` is in flight — workstream `session-complete-rename`.) _Vocabulary note: "ceremony" here means a lifecycle invocation point; this is distinct from `ceremony-calibration.md`'s use of "ceremony" to mean heavyweight process weight (plan pipeline, sizing pass, skill extraction). Same word, different scope._

Also add to `CONTEXT.md § Flagged ambiguities`:
- 2026-06-01: `/session-start` (the PM-invoked skill), `SessionStart` (the platform hook matcher), and "session start" (free prose) were conflated across doctrine. Resolved: three-token taxonomy formalized. "session boot" is now the canonical human/doctrine term for the automatic machinery; `SessionStart` (PascalCase, no slash) is reserved for the literal platform hook key; `/session-start` (slash, lowercase) is the skill. See `coordinator/CONTEXT.md § Terms`.

<!-- Review: the Staff Engineer (Finding 3) — prior-art Claims #5 and #6 flagged two executor-required CONTEXT.md actions not in the original C1: (a) a Flagged ambiguities entry recording the 2026-06-01 /session-start-vs-SessionStart conflation resolution, mirroring the 2026-04-29 format; (b) a vocabulary-collision note in the ceremony-grid entry distinguishing it from ceremony-calibration.md's "ceremony" sense. -->

### C2 — `coordinator/CLAUDE.md` (the primary scab)
- L7: reframe the parenthetical `(/session-start reads lessons.md deliberately — a PM-invoked survey, not a boot read.)` into a plain statement now that the terms are distinct, e.g. "(The `/session-start` skill surveys `lessons.md` deliberately; session boot does not read it.)"
- L8: `**/session-start is PM-invoked, not EM-judged.**` — fine as-is (correctly names the skill); verify no "boot" ambiguity.
- L14 ("Tier 0 — Boot"), L141, L149 ("read at every session boot"): confirm these use "session boot" / "boot" for the machinery consistently. L149 already says "session boot" ✓.

### C3 — Hooks wiki (`docs/wiki/plugin-session-start-hooks.md`)
- Add a one-line framing clarifier near the top: these are the **`SessionStart` platform hooks that constitute the "session boot" path** — distinct from the `/session-start` *skill*. The literal hook event name (`SessionStart`) stays; the filename stays (it is literally about the platform hook).
- **Reword L8 explicitly:** "the expected session-start behavior never fires" → "the expected session-boot behavior never fires". Rationale: this sentence names the machinery path (the hook not firing = boot machinery absent); "session-start" in this free-prose context is ambiguous under the new three-token taxonomy and should use the hyphenated "session-boot" form.
- Do **not** `git mv` the file.

<!-- Review: the Staff Engineer (Finding 1) — without the explicit L8 reword, the reframed intro asserts a distinction the body violates. Convergent with prior-art Claim #1 (coverage sidecar Ambiguous #3). The hyphenated "session-boot" form is appropriate here as it names the concept (not the skill's slash-prefix and not the PascalCase matcher). -->

### C4 — `skills/session-start/SKILL.md` (internal ambiguous nouns)
Classify each occurrence skill-vs-machinery and edit accordingly:
- L26 `CLAUDE_INVOKING_COMMAND=session-start` — this is the *skill's own invoking-command token*; **keep** (it correctly identifies the skill).
- L28-30 (crash-insurance note acknowledging boot-redundancy): reword to "session boot also reads `orientation_cache`" where it means the machinery.
- L55 ("session-start fires many times per day"): this means the *skill* being invoked — keep `/session-start`, but disambiguate from `/workday-start` cadence as already written.
- L97 ("session-start branch creation here is a safety fallback"): means the skill — keep.
- L133 ("Session-start surfaces RED verdicts only"): means the skill's behavior — keep, ensure capitalized noun reads as the skill.
- L140 (bootstrap notice): "bootstrap" here = first-install notice, leave unless it reads as boot-machinery.

### C5 — Remaining prose/comment surfaces (machinery references → "session boot")
For each, use "session boot" for the automatic path, keep `SessionStart` for the literal matcher, keep `/session-start` for the skill:
- `commands/setup.md` L65 ("every coordinator session boot" ✓ already correct — verify), L480 (points to `/session-start` skill — keep).
- `commands/workday-complete.md` L81 ("at every session boot" ✓ — verify).
- `commands/workday-start.md` L309 ("SessionStart hook-script existence probe" — `SessionStart` here = literal matcher, keep PascalCase).
- `bin/check-em-environment.sh` L10 ("A SessionStart hook fires on every boot" — keep `SessionStart` matcher; "boot"→"session boot" if it sharpens).
- `bin/check-rag-state.sh` L26 ("writes these markers at session start" → "at session boot").
- `bin/scan-addon-health.sh` L19/226/246/256/284 + `bin/tests/test-scan-addon-health-hookprobe.sh` (8 sites): these refer to the **`SessionStart` hook machinery** under test — keep `SessionStart` (PascalCase, literal matcher); only reword free-prose "session start" → "session boot".
- `bin/coordinator-doctor-sentinel.sh` L307 ("the spine that /session-start depends on" — names the skill, keep).

**Also address these 6 sites pre-classified from the coverage sidecar (promoted from C6 residual):**
<!-- Review: the Staff Engineer (Finding 0) — enumeration discipline: pre-classify known machinery-sense sites rather than delegating to executor self-classification in C6. -->

- `hooks/scripts/session-init.sh` L2 (`# SessionStart hook: Initialize…`) — `SessionStart` here = literal hook matcher name in PascalCase; **keep**. L30 ("never blocks session start") → "never blocks session boot" (free prose, machinery context — this is the boot script itself). L132 ("can never block or fail session start") → "can never block or fail session boot" (same reasoning). L132 via comment header: same.
- `hooks/scripts/coordinator-reminder.sh` — one occurrence in free prose naming the machinery; confirm content and reword to "session boot" if it uses "session start" as free prose (machinery context — the script IS part of the boot machinery).
- `docs/wiki/plugin-session-start-hooks.md` L8 — handled explicitly in C3 above.
- `docs/wiki/tiered-context-loading.md` L29 ("it was loaded at session start" — machinery, boot context) → "it was loaded at session boot". L95 (table cell "Auto-loaded at session start — no tool call needed") → "Auto-loaded at session boot — no tool call needed".
- `docs/wiki/coordinator-tripwires.md` — two occurrences; grep to read full content: if a occurrence is the `SessionStart` hook name (PascalCase, literal matcher) **keep**; if free-prose referring to the boot machinery → "session boot". Classify per-occurrence on disk.
- `pipelines/workday-start-internals.md` — one occurrence already uses "boot" correctly ("the `SessionStart` hook injects at every boot" — `SessionStart` = literal matcher, "boot" already correct). **Verify, no change expected.**

### C6 — Closeout (residual backstop)
- **Residual re-grep:** `grep -rn "session start\|session-start" plugins/coordinator-claude/coordinator` to catch any hits NOT already classified by C2–C5 above. Every hit should resolve to one of: skill = `/session-start`, machinery = "session boot", literal matcher = `SessionStart`. C5's pre-enumerated sites have been classified; C6 handles only genuinely un-enumerated residuals.
- Note the `setup/publish.sh` percolation follow-up to OSS coordinator-claude (do **not** execute here).

**C6 residual resolution (executed 2026-06-01):** the tree-wide `grep -i "session start"` surfaced ~30 spaced-form hits. They classify into a FOURTH, legitimate category the original three-token taxonomy under-specified: **temporal "session start"** = *the moment a session begins* ("at/since session start", "the next session starts cold", the skill's own H1 title) — kept as-is; it is not the machinery and "session boot" would read awkwardly there. Only the **boot-hook-script siblings** of the already-changed `session-init.sh` were reclassified for consistency: `check-dropped-tracked-files.sh` L20, `guard-settings-integrity.sh` L40, `settings-integrity-guard.md` L32 ("never blocks session start" → "never blocks session boot"). `coordinator-tripwires.md` has zero spaced "session start" occurrences (the coverage sidecar's "2 occurrences" were `SessionStart` matchers — legit keep). The temporal-vs-machinery distinction was added to the CONTEXT.md `session boot` `_Avoid_` note so the convention is deterministic for future greppers. **C4 (session-start SKILL.md) required zero edits** — the plan's assumed L28-30 `orientation_cache` machinery reference does not exist on disk (L28-30 is commit crash-insurance; the genuine boot ref at L288 already reads correctly).

<!-- Review: the Staff Engineer (Finding 0) — C6 reworded from primary classifier for known sites to residual-catch backstop/verification step. The 6 coverage-sidecar ambiguous sites are now explicit in C5 with per-site treatments. C6 and C5 no longer overlap: C5 owns the enumerated surface, C6 owns residuals the grep finds that are not in C5's list. -->

## Anti-scope / failure modes
- Do **not** rename the `SessionStart` hook key or any script — pure prose change.
- Do **not** touch `session-end` (separate spinoff).
- Do **not** mechanically find-replace "session-start" → "session boot" — many occurrences correctly name the *skill* and must stay `/session-start`. Classification is per-occurrence.
- Do **not** `git mv` the hooks wiki.

## Dispatch Ledger

C5 is split into C5a (shell/bin comments) and C5b (doc/command/pipeline prose) for budget. C6 is EM-inline: it owns the residual re-grep, the percolation note, AND `coordinator-tripwires.md` (pulled out of the wave — the sibling `session-complete-rename` session also edits that file, so the EM handles it last with a fresh disk read to avoid a concurrent-edit clobber).

| dispatch # | chunk-id | one-line brief | write-files | runs | est-min | status |
|---|---|---|---|---|---|---|
| 1 | C1 | CONTEXT.md glossary (session boot + ceremony grid) + Flagged ambiguities entry | `~/.claude/CONTEXT.md` | parallel | 6 | done |
| 2 | C2 | coordinator/CLAUDE.md — reframe L7 scab; verify L8/14/141/149 | `coordinator/CLAUDE.md` | parallel | 4 | done |
| 3 | C3 | hooks wiki — intro clarifier + L8 reword (no git mv) | `docs/wiki/plugin-session-start-hooks.md` | parallel | 4 | done |
| 4 | C4 | session-start SKILL.md — reword L28-30 to "session boot"; keep skill-sense sites | `skills/session-start/SKILL.md` | parallel | 5 | done |
| 5 | C5a | shell/bin free-prose → "session boot"; keep `SessionStart` matchers + skill refs | `bin/check-em-environment.sh`, `bin/check-rag-state.sh`, `bin/scan-addon-health.sh`, `bin/tests/test-scan-addon-health-hookprobe.sh`, `bin/coordinator-doctor-sentinel.sh`, `hooks/scripts/session-init.sh`, `hooks/scripts/coordinator-reminder.sh` | parallel | 8 | done |
| 6 | C5b | doc/command/pipeline free-prose → "session boot"; keep `SessionStart` matchers + skill refs | `commands/setup.md`, `commands/workday-complete.md`, `commands/workday-start.md`, `docs/wiki/tiered-context-loading.md`, `pipelines/workday-start-internals.md` | parallel | 7 | done |
| 7 | C6 | residual re-grep + `coordinator-tripwires.md` (sibling-overlap) + percolation note | `docs/wiki/coordinator-tripwires.md` | inline (EM), after #1-#6 | 6 | done |
