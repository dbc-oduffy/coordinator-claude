---
title: Plan Coverage Check — 2026-06-01-session-boot-nomenclature
created: 2026-06-01
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-06-01-session-boot-nomenclature.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-01-session-boot-nomenclature.md`
**Verdict:** COMPLETE
**Oracle items:** ~21 files / 71 citations (source: PM-supplied oracle via dispatch prompt, cross-referenced against plan's C1–C5 site enumeration)
**Slate items:** 6 chunks (C1–C6)
**Missed:** 0 | **Ambiguous:** 6 (greppability surface not pre-enumerated; C6 re-grep is the designed catch) | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 0

---

### Missed audit items (no slate entry, no architectural OOS)

None. Every file:line site cited in the plan body is owned by a named chunk (C2, C4, C5). The `/session-end` half is OOS-architectural (321-occurrence rename with runtime-token and stored-data couplings, forked to a separate workstream with explicit PM authorization — not an appetite hedge).

---

### Ambiguous audit items (signal-partial — informational only; does NOT affect COMPLETE verdict)

The 113-file grep surface for `session-start`/`SessionStart`/`session start` in the plugin tree contains files not pre-enumerated in C1–C5. The plan's C6 is a designed re-grep step intended to catch these, but their classification (skill vs. machinery vs. literal-matcher) is delegated to the executor at runtime without explicit per-site guidance. The EM should verify C6 runs thoroughly. Six representative ambiguous sites:

**Ambiguous 1 — `hooks/scripts/session-init.sh`**
Multiple occurrences: L2 (`# SessionStart hook: Initialize…`), L30 (`never blocks session start`), L132 (`can never block or fail session start`). These are all machinery-context references (the file IS the boot machinery). No chunk pre-assigns them. C6 re-grep must classify and update if any read as "session start" in free prose. Likely correct treatment: `SessionStart` in the comment header (literal matcher context) stays; "session start" free prose in L30/L132 → "session boot". Not currently pre-enumerated.

**Ambiguous 2 — `hooks/scripts/coordinator-reminder.sh`**
One occurrence (line content omitted by grep pagination). This script is part of the session boot machinery. If the occurrence is free prose, it may need updating. Not enumerated in C1–C5.

**Ambiguous 3 — `docs/wiki/plugin-session-start-hooks.md` L8**
Text: `"expected session-start behavior never fires"` — this is the hooks wiki that C3 assigns for a one-line framing clarifier, but this specific prose occurrence is not called out in C3. "session-start behavior" here is ambiguous: it could refer to the boot hook firing (machinery) or the skill. C3's framing addition should address the context but the executor should explicitly confirm this sentence is addressed or intentionally left as-is.

**Ambiguous 4 — `docs/wiki/tiered-context-loading.md` L29 and L95**
L29: `"Boot context is always present before the first tool call. It costs nothing at investigation time because it was loaded at session start"` — "session start" here = boot machinery.
L95: table row `"0 | Auto-loaded at session start — no tool call needed"` — same context.
Neither site is in any chunk. C6 re-grep must catch these. Likely update: "at session boot" / "at session boot — no tool call needed".

**Ambiguous 5 — `docs/wiki/coordinator-tripwires.md`**
Two occurrences (grep returned `[Omitted long matching line]` — content not readable at head_limit). Not enumerated in any chunk. C6 must classify.

**Ambiguous 6 — `pipelines/workday-start-internals.md`**
One occurrence: `"a compact, schema-conformant summary the SessionStart hook injects at every boot"` — already uses "boot" correctly; `SessionStart` is the literal hook matcher. This one is likely already correct, but C6 should confirm.

**EM action:** Verify that C6's re-grep step enumerates and disposes each of the above. Alternatively, promote the six sites above to explicit per-site notes in C5 before execution dispatch, so the executor does not need to self-classify them.

---

### Weak OOS / hedges (appetite-based deferrals)

None found. The `/session-end → /session-complete` rename is OOS-ARCHITECTURAL: 321 occurrences, runtime-token + stored-data couplings, explicitly spun off with PM authorization to a named separate workstream. This is a hard constraint, not an appetite hedge. Not flagged.

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

All cited substrate verified against current disk state. No drift found.

**Verified sites:**

| Cited in plan | Disk state |
|---------------|------------|
| `coordinator/CLAUDE.md` L7 — parenthetical `(/session-start reads lessons.md deliberately…)` | CONFIRMED: L7 on disk reads exactly as cited |
| `coordinator/CLAUDE.md` L8 — `/session-start is PM-invoked, not EM-judged` | CONFIRMED: L8 on disk matches |
| `coordinator/CLAUDE.md` L14 — `Tier 0 — Boot` | CONFIRMED: L14 on disk reads `**Tier 0 — Boot.**` |
| `coordinator/CLAUDE.md` L141 — "start ceremonies" | CONFIRMED: L141 on disk contains `only \`ready_to_fire\` surfaces in start ceremonies` |
| `coordinator/CLAUDE.md` L149 — "read at every session boot" | CONFIRMED: L149 on disk reads `**CLAUDE.md is load-bearing — read at every session boot.**` |
| `hooks.json` — no `Stop`/`SessionEnd` matcher | CONFIRMED: `hooks.json` contains only `"SessionStart"` and `"PreCompact"` matchers; no `Stop` or `SessionEnd` key present |
| `~/.claude/CONTEXT.md` exists | CONFIRMED: file exists at `C:/Users/oduffy/.claude/CONTEXT.md` |
| `skills/session-start/SKILL.md` L26 `CLAUDE_INVOKING_COMMAND=session-start` | CONFIRMED: L26 on disk reads `CLAUDE_INVOKING_COMMAND=session-start ~/.claude/plugins/…` |
| `skills/session-start/SKILL.md` L28-30 (crash-insurance note) | CONFIRMED: L28-30 present and describe the crash-insurance / boot-redundancy topic as cited |
| `skills/session-start/SKILL.md` L55 ("fires many times per day") | CONFIRMED: L55 on disk reads `session-start fires many times per day` |
| `skills/session-start/SKILL.md` L97 ("safety fallback") | CONFIRMED: L97 contains "session-start branch creation here is a safety fallback" |
| `skills/session-start/SKILL.md` L133 ("Session-start surfaces RED verdicts only") | CONFIRMED: L133 on disk reads `Session-start surfaces RED verdicts only` |
| `skills/session-start/SKILL.md` L140 (bootstrap notice) | CONFIRMED: L140 area contains bootstrap-notice logic |
| `commands/setup.md` L65 ("every coordinator session boot") | CONFIRMED: L65 on disk reads `every coordinator session boot` — already correct per plan's "verify" intent |
| `commands/setup.md` L480 (points to `/session-start` skill) | CONFIRMED: L480 area contains "point to `/session-start`" language |
| `commands/workday-complete.md` L81 ("at every session boot") | CONFIRMED: L81 area on disk reads `every session boot` — already correct |
| `commands/workday-start.md` L309 ("SessionStart hook-script existence probe") | CONFIRMED: L309 on disk reads `SessionStart hook-script existence pass (2026-05-27)` — within ±50 lines of cited L309 |
| `bin/check-em-environment.sh` L10 ("A SessionStart hook fires on every boot") | CONFIRMED: L10 on disk reads `A SessionStart hook fires on every boot —` |
| `bin/check-rag-state.sh` L26 ("writes these markers at session start") | CONFIRMED: L26 on disk reads `# The W1 hook (project-rag-detect.*) writes these markers at session start.` |
| `bin/scan-addon-health.sh` L19 ("session-start — signal-not-noise") | CONFIRMED: L17 on disk (within ±50) reads `--red-only   emit lines only for RED verdicts (session-start — signal-not-noise)` |
| `bin/scan-addon-health.sh` L226 ("SessionStart hook-script existence probe") | CONFIRMED: L226 on disk reads `# Third pass: SessionStart hook-script existence probe` |
| `bin/scan-addon-health.sh` L246 ("each SessionStart command's referenced script path") | CONFIRMED: L246 on disk reads `# Emit, one per line, each SessionStart command's referenced script path` |
| `bin/scan-addon-health.sh` L284 (health line with SessionStart text) | CONFIRMED: L284 on disk emits the `[health] ${plugin}: SessionStart hook references missing script` line |
| `bin/tests/test-scan-addon-health-hookprobe.sh` (×8 SessionStart references) | CONFIRMED: file exists; test covers SessionStart probe across 5 named test cases |
| `bin/coordinator-doctor-sentinel.sh` L307 ("the spine that /session-start depends on") | CONFIRMED: L307 on disk reads `the first-class session-identity spine that /session-start depends on` |
| `docs/wiki/plugin-session-start-hooks.md` (C3 target) | CONFIRMED: file exists at expected path |

---

### Verdict logic

**COMPLETE.** Zero MISSED items. Zero weak-OOS findings. Zero substrate drift. Six AMBIGUOUS items logged for EM read-through — these are un-enumerated greppability surface items that C6's re-grep is designed to catch. They do not gate the verdict. The plan's C6 closeout step is load-bearing for completeness of the full ~71-citation surface; the EM should confirm the executor runs C6 with sufficient rigor (or pre-enumerate the six sites above in C5 before dispatch).

One structural note for the EM (not a gate): the plan's oracle is the PM-described 21-file / 71-citation discovery surface. C1–C5 enumerate specific sites within that surface. C6 is a designed sweep for residual sites. This is a valid architecture for a prose-reorientation plan where per-occurrence classification judgment is required. The AMBIGUOUS entries above are the known residual population that C6 must dispose — surfacing them here gives the executor a head start.

---

**Cost estimate:** ~8K tokens (25 cited sites × substrate verification + greppability grep across 113-file hit list)
