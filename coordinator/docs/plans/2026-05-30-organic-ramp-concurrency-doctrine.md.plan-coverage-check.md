---
title: Plan Coverage Check — 2026-05-30-organic-ramp-concurrency-doctrine
created: 2026-05-30
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md`
**Verdict:** INCOMPLETE
**Oracle items:** 6 (source: `## Surfaces & out-of-scope` table, rows C1–C6 — heuristic 3, table with file/lines/change columns)
**Slate items:** 6 (source: `## Chunks` section, entries C1–C6)
**Missed:** 0 | **Ambiguous:** 0 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 1
**Advisory:** No PM-ratified problem-set found. The plan declares `problem_set: inline (§ Problem)` but the `## Problem` section contains no `> Ratified by PM <name> <date>` blockquote — the inline block is therefore `draft` status and does not count as a ratified problem-set. EM: confirm problem understanding with the PM before dispatch, or add the ratification blockquote.

---

### Missed audit items (no slate entry, no architectural OOS)

None. All 6 oracle rows have signal-confirmed slate entries.

---

### Ambiguous audit items (signal-partial — informational only)

None.

---

### Weak OOS / hedges (appetite-based deferrals)

None. No hedge tokens found in plan body. The OOS section items are architecturally justified:

- `dispatching-parallel-agents.md:168` — explicitly justified as "generic 'a concurrency cap' as an *example* of a load-bearing scalar; the sentence is about pinning shared scalars, not about the value 6-8." Architectural reason: the sentence's meaning is unrelated to the general cap.
- `architecture-survey.md:270`, `pipelines/bug-sweep/pattern-library.md:52`, `pipelines/artifact-distillation/PIPELINE.md:453` — pipeline-specific agent-count calibrations, explicitly distinguished from the general concurrency cap. Architectural reason: different scope, different governance.
- `hooks/scripts/context-pressure-advisory.sh:125,210` — "6-8 bytes/token", explicitly noted as unrelated. Architectural reason: different unit, different meaning.
- Both CLAUDE.md files — explicitly verified cap-number-free on 2026-05-30. No edit needed.
- `docs/plans/2026-05-27-fan-out-default-doctrine.md:68` — historical closed plan; supersession recorded in this plan's frontmatter. Architectural reason: closed plans are not edited per coordinator doctrine.

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

**DRIFT-1 — Internal plan constant contradiction: fallback value is `12` in C2 prose but `16` in the pinned contract table.**

Plan citation (C2 chunk description, line 137):
> `Add LARGE_WAVE_THRESHOLD="${LARGE_WAVE_THRESHOLD:-12}".`

Plan citation (pinned contract table, row for `fan-out-dispatch.sh` threshold, line 76):
> `fallback \`16\` when machine-local is unset/unavailable (OSS user pre-setup) — never the old \`8\``

And in the resolution-order paragraph (line 85–88):
> `env var → machine-local get fan_out.large_wave_threshold ... → fallback 16`

The pinned contract specifies fallback `16`; the C2 chunk description specifies `12`. An executor authoring C2 from the chunk description alone will implement the wrong fallback. The pinned contract section is explicitly marked "load-bearing — read before editing any of Chunks 2–4", making the contradiction a correctness risk for the C4 test assertions.

Current disk state: `LARGE_WAVE_THRESHOLD` does not yet exist in `bin/fan-out-dispatch.sh` (the variable is being introduced by this plan). The value to implement is therefore determined solely by the plan — and the plan contradicts itself.

Suggested action: amend C2 chunk description to read `"${LARGE_WAVE_THRESHOLD:-16}"` to match the pinned contract. The pinned contract (`:76` and the resolution-order paragraph) should be treated as authoritative since it is explicitly marked load-bearing.

---

### Verified in-repo citations (Lens 3 — confirmed clean)

The following plan citations were verified against current disk state and confirmed accurate:

| Plan citation | Disk verification |
|---|---|
| `fan-out-dispatch.sh:281–285` WARNING mechanism | Line 281: comment `# Cap-breach warning`; line 283: `if [[ "$CHUNK_COUNT" -gt 8 ]]`; line 284: `echo "WARNING: ${CHUNK_COUNT} chunks..."`. Exact match. |
| `fan-out-dispatch.sh:300` `FAT_CHUNK_THRESHOLD` pattern | Line 300: `FAT_CHUNK_THRESHOLD="${FAT_CHUNK_THRESHOLD:-4}"`. Exact match. |
| `fan-out-dispatch.sh:307` fat-chunk NOTE | Line 307: `echo "NOTE: chunk '${CHUNK_IDS[$i]}' owns..."`. Exact match. |
| `fan-out-dispatch.sh:318–320` heredoc reminder | Lines 318–320: `Concurrency cap: 6-8 concurrent background agents per wave...` / `Use a pilot->expand ramp: launch 4-6 agents, observe completion, then expand.` Exact match. |
| `fan-out-dispatch.test.sh:342` D3 assert `"6-8"` | Line 342: `_assert_stderr_contains "D3: cap reminder on stderr" "6-8" "$STDERR_C"`. Exact match. |
| `fan-out-dispatch.test.sh:347–372` Test E | Lines 347–372: Test E block — 9-chunk spec, asserts WARNING/PM call on stdout. Exact match. |
| `skills/fan-out/SKILL.md:105–116` Step 1.5 Cap-Breach Gate | Lines 105–116: heading `## Step 1.5 — Cap-Breach Gate (HARD STOP before dispatch)`, WARNING grep, CAP_BREACH logic. Exact match. |
| `skills/fan-out/SKILL.md:120–127` Step 2 | Lines 120–127: `## Step 2 — Concurrency Budget Check`, bands `1–6 / 7–8 / >8`. Exact match. |
| `skills/fan-out/SKILL.md:179` failure table row | Line 179: `\| chunk-count > 8 (cap-breach WARNING in stdout) \| STOP at Step 1.5...`. Exact match. |
| `skills/fan-out/SKILL.md:3` description line | Line 3: `description: "Dispatch a parallel wave ... dispatches up to 6–8 agents concurrently..."`. Exact match. |
| `skills/fan-out/SKILL.md:81` NOTE/WARNING distinction | Line 81: fat-chunk backstop prose, "It deliberately uses `NOTE:`, never `WARNING:`...". Exact match. |
| `dispatching-parallel-agents.md:19–28` Concurrency Budget | Lines 19–28: `## Concurrency Budget` / `Hard cap: 6-8 concurrent...`. Exact match. |
| `dispatching-parallel-agents.md:187` `6–8` reference | Line 187: `Respects the 6–8 concurrency cap; halts and reports...`. Exact match. |
| `dispatching-parallel-agents.md:168` (OOS, left untouched) | Line 168: "a concurrency cap" as load-bearing scalar example. Confirmed OOS classification accurate — no general cap value cited. |
| `README.md:142` `up-to-6–8` | Line 142: `fan-out — In-the-moment parallel executor wave: overlap pass via fan-out-dispatch.sh, scoped prompts, up-to-6–8 concurrent dispatch...`. Exact match. |
| `commands/setup.md` (C6 target) | File exists at `plugins/coordinator/commands/setup.md`. Phase 3 documents machine-local registry substrate setup. No `fan_out.large_wave_threshold` key present yet (correctly — C6 adds it). |
| `~/.claude/bin/machine-local` CLI | File exists at `C:\Users\oduffy\.claude\bin\machine-local`. Confirmed. |
| `~/.claude/machine-local/registry.local.toml` | File exists at `C:\Users\oduffy\.claude\machine-local\registry.local.toml`. Confirmed. |

---

### Coverage cross-reference (Lens 1 — oracle vs. slate)

All 6 oracle rows matched to slate chunks by shared file-path citation (signal (a)):

| Oracle row | Slate chunk | Match signal |
|---|---|---|
| C1 — `docs/wiki/dispatching-parallel-agents.md` lines 19–28, 187 | C1 chunk — same file, same lines | Shared file-path |
| C2 — `bin/fan-out-dispatch.sh` lines 280–285, 294, 312–328 | C2 chunk — same file, same lines | Shared file-path |
| C3 — `skills/fan-out/SKILL.md` lines 3, 81, 105–116, 120–127, 179 | C3 chunk — same file, same lines | Shared file-path |
| C4 — `bin/fan-out-dispatch.test.sh` lines 342, 347–372 | C4 chunk — same file, same lines | Shared file-path |
| C5 — `README.md:142` | C5 chunk — same file, same line | Shared file-path |
| C6 — `commands/setup.md` (new step) | C6 chunk — same file | Shared file-path |

Re-grep of cited files confirmed no in-scope cap occurrence is unaddressed by the slate. The only unmatched grep hits were:
- `dispatching-parallel-agents.md:168` — explicitly OOS (architectural justification present)
- The grep match on line 205 of `dispatching-parallel-agents.md` was a false-positive on digit sequences unrelated to the concurrency cap (no `6-8` or `4-6` phrase in context)

---

### Verdict logic

**INCOMPLETE** — 1 substrate-drift finding (DRIFT-1: internal plan contradiction on the `LARGE_WAVE_THRESHOLD` fallback value: C2 chunk says `12`, pinned contract says `16`). EM must resolve before dispatch to C2 to prevent the executor from implementing the wrong fallback value.

Resolution options:
- **Amend the plan:** Update C2 chunk description to specify `16` (matching the pinned contract, which is explicitly load-bearing).
- **Amend the pinned contract:** If `12` was the intended design decision, update the pinned contract table and resolution-order paragraph to say `12`. Then C4 test assertions must also use `12` as the threshold input for Test E (currently the test uses 9 chunks for `>8`; if the threshold becomes 12, Test E needs ≥12 chunks to trigger the NOTE).

Advisory: The inline problem-set block lacks the `> Ratified by PM` marker required to count as ratified. Add `> Ratified by PM Dónal O'Duffy 2026-05-30` inside `## Problem` to satisfy the spec, or leave as-is if the PM confirmation is understood to be captured in the plan body prose ("Converged design (PM decisions, 2026-05-30)"). This is advisory only and does not change the INCOMPLETE verdict.

**Cost estimate:** ~4,200 tokens (6 oracle items × substrate verification of ~18 cited paths/symbols)
