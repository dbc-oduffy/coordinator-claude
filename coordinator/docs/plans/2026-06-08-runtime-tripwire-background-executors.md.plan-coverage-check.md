---
title: Plan Coverage Check — 2026-06-08-runtime-tripwire-background-executors
created: 2026-06-08
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-06-08-runtime-tripwire-background-executors.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-08-runtime-tripwire-background-executors.md`
**Verdict:** COMPLETE
**Oracle items:** 4 (source: ratified problem-set: `docs/problems/2026-06-08-runtime-tripwire-background-executors.md`, `status: ratified`, ratified by PM Dónal O'Duffy 2026-06-08)
**Slate items:** 6 chunks (C1–C6) + 9 ACs (AC1–AC9)
**Missed:** 0 | **Ambiguous:** 0 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 0

### Missed audit items (no slate entry, no architectural OOS)

None.

### Ambiguous audit items (signal-partial — informational only)

None.

### Weak OOS / hedges (appetite-based deferrals)

None.

Two hedge tokens were found in the plan body and classified:

1. **Line 174 — "follow-up dispatch"** (`C3 is the borderline one (two write targets, schema extension) — if executor returns mid-work, EM splits it into C3a (tracker schema bump) and C3b (em-check.sh) as a follow-up dispatch.`)
   Stage 2 classification: **FALSE-POSITIVE** — this is operational contingency framing for executor crash-recovery, not a scope-cut. The work described is still within C3's scope; the "follow-up dispatch" is a recovery mechanism, not a deferral.

2. **Line 182 — "defer to v2"** (`Custom per-dispatch threshold ergonomics (problem-set OOS — defer to v2 if env-vars prove insufficient).`)
   Stage 1 classification: **FALSE-POSITIVE** — token sits under the `## Out of scope (per problem-set)` heading (matches the OOS exclusion in Stage 1). The architectural reason is present in the cited problem-set (`coordinator:plan` decides the mechanism; the problem does not prescribe override ergonomics). The "v2" qualifier is informal language within an OOS section that has architectural backing.

### Substrate drift (in-repo paths/symbols cited that don't match disk)

None.

Verification detail:

| Citation | Disk state | Result |
|---|---|---|
| `hooks/scripts/context-pressure-advisory.sh:168-194` (model-detection regex / case statement) | Lines 168–194: `case "$MODEL_ID" in … *\[1m\]*) … *-1m*) … *opus*) … *sonnet*) … *haiku*) … *)` — matches plan's cited regex shape | VERIFIED |
| `hooks/scripts/context-pressure-advisory.sh:154` (model-grep pattern) | Line 154: `MODEL_ID=$(grep -m1 -oE '"model"[[:space:]]*:[[:space:]]*"claude-[^"]*"' "$TRANSCRIPT_PATH" …)` — matches plan's C2 spec citing this exact pattern shape | VERIFIED |
| `hooks/scripts/context-pressure-advisory.sh:100-115` (self-throttle pattern) | Lines 100–115: `THROTTLE_SENTINEL="/tmp/context-pressure-throttle-${SESSION_ID}"` / `THROTTLE_SECONDS=300` / `stat -f %m` (macOS) / `stat -c %Y` (Linux) mtime check — matches plan's C3 spec "same pattern as `context-pressure-advisory.sh:100-115`" | VERIFIED |
| `hooks/scripts/context-pressure-advisory.sh:31-38` (HOOK_INPUT parsing) | Lines 31–38: jq/sed fallback block for `SESSION_ID` and `TRANSCRIPT_PATH` — matches plan's C2 spec "jq or sed fallback per `context-pressure-advisory.sh:31-38`" | VERIFIED |
| `hooks/scripts/track-dispatched-agents.sh` | File exists; record shape is 3-column tab-delimited (`agentId\tmodel\tsubagent_type`); plan's C3 spec correctly describes extending to 4-column with `dispatched-at` appended | VERIFIED |
| `CLAUDE.md:51` (HARD RULE row) | Line 51: `- **HARD RULE — small-remit-and-many beats large-remit-and-one, every time.** Size each executor ~5-10 min on one coherent surface (15 min hard ceiling; split before dispatch).` — matches plan's C5 spec quoted text exactly | VERIFIED |
| `.git/coordinator-sessions/.agents/*/em-session-id.txt` (ledger structure) | Structure exists in meta-repo git root (`~/.claude/.git/coordinator-sessions/.agents/<agentId>/em-session-id.txt`); sampled agent dir confirmed file present | VERIFIED |
| `bin/tests/test-detect-onboarding-offer.sh` (test pattern reference) | File exists at `plugins/coordinator/bin/tests/test-detect-onboarding-offer.sh`; plan's C6 spec cites this as the pattern shape for new test scripts | VERIFIED |

**One path note (not a drift finding):** The plan references the problem-set at `docs/problems/2026-06-08-runtime-tripwire-background-executors.md` and includes an explicit note: "note: meta-repo path; ratified 2026-06-08, predates plugin-bundled `docs/problems/` convention which does not yet exist." The file exists at `~/.claude/docs/problems/2026-06-08-runtime-tripwire-background-executors.md` (meta-repo root), not inside the plugin tree. The plan acknowledges this discrepancy from current convention explicitly — the citation is intentional and accurate for the actual file location. No drift finding warranted.

### Lens 1 — Coverage cross-reference

| Oracle item | Matching slate entries | Signal type |
|---|---|---|
| P1 — Background executors degrade through compaction-decay past budget | C2 (agent-side nudge hook firing on elapsed ≥ threshold), C3 (EM-side awareness nudge), AC1 (agent-side hook fires `additionalContext`), AC2 (EM-side awareness nudge) | Shared symbol: "compaction-decay", "elapsed", "threshold"; shared path: `runtime-tripwire-advisory.sh` |
| P2 — Agent is the primary signal target; EM receives secondary signal | C2 (PostToolUse `additionalContext` injection to agent), C3 (EM-side PostToolUse `additionalContext`), AC1, AC2, AC7 (EM nudge cites `agentId` + elapsed + model) | Shared noun phrase: "agent-side primary nudge", "EM-side awareness nudge"; shared symbol: `additionalContext` |
| P3 — Thresholds are per-model (Opus 25 / Sonnet 15 / Haiku 10), env-var overrideable | C1 (shared thresholds lib `runtime_threshold_minutes(MODEL_ID)`, Opus=25/Sonnet=15/Haiku=10), AC3 (defaults + env-var overrides) | Shared symbol: `RUNTIME_TRIPWIRE_OPUS_MIN`, threshold values 25/15/10; shared path: `hooks/scripts/lib/runtime-thresholds.sh` |
| P4 — Nudge-not-kill; EM authority; wrap-shape prescribed | C2 (wrap-shape `additionalContext` text inlined), C5 (wiki §3 "Wrap shape — canonical prescription", §4 "EM authority"), AC5 (wrap-shape literal strings assertion), AC9 (CLAUDE.md pointer) | Shared noun phrase: "wrap shape", "EM authority", "trust-but-verify"; shared symbol: "stop starting new work", "successor-handoff stub" |

All five OOS items in the plan have OOS-ARCHITECTURAL treatment:
- Auto-kill: cited problem-set OOS with reason "destructive on false positives, removes agent judgment."
- `Bash run_in_background`: cited problem-set OOS with reason "intentionally long-lived; a runtime nudge would misfire constantly."
- Mid-dispatch threshold renegotiation: cited problem-set OOS with reason "renegotiable threshold becomes a snooze button."
- Re-nudge cadence: cited problem-set OOS with "bark-once per dispatch is the v1; revisit only if empirically needed" — this is the problem-set's own framing (the problem-set explicitly marks this as "calibration knob, settled in `coordinator:plan`"). The plan's OOS section faithfully mirrors the problem-set's OOS designation. ARCHITECTURAL.
- Custom per-dispatch threshold ergonomics: cited problem-set OOS with reason "mechanism is design, not problem-shape." ARCHITECTURAL.

### Verdict logic

**COMPLETE** — zero MISSED, zero weak-OOS (all hedge tokens classified FALSE-POSITIVE after stage-1 and stage-2 analysis), zero substrate-drift findings. All four ratified problems have signal-confirmed links to named slate entries. All OOS items have architectural backing from the ratified problem-set.

**Cost estimate:** ~4,200 tokens estimated (4 oracle items × 2 substrate reads + 8 targeted citations verified)
