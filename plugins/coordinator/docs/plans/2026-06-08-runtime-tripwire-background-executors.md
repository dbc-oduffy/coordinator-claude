---
title: Runtime tripwire — model-aware nudge for long-running background executors
date: 2026-06-08
scope_mode: feature
tshirt: M
problem_set: docs/problems/2026-06-08-runtime-tripwire-background-executors.md
status: shipped
---

<!-- Review: the Staff Engineer — REQUIRES_CHANGES integrated 2026-06-08. Bulk dispositions below.

## the Staff Engineer Review Dispositions (2026-06-08)

The Staff Engineer returned REQUIRES_CHANGES with 4 major + 6 minor findings. 9 are tradeoff-free
correctness or doc fixes (integrated as-specified); 1 (F7 Sonnet threshold) was surfaced
to PM, who chose Sonnet = 12 (3-min wrap buffer before the 15-min hard ceiling).
No findings declined.

- F1 (major, correctness — async race): Applied. C4 spec now mandates async:false for
  track-dispatched-agents.sh, agent-completion-log.sh, and both new hooks. Note added
  citing claude-code-platform-gotchas.md async-race shape.
- F2 (major, correctness — subagent-detect mechanism): Applied. Architecture paragraph
  rewritten to commit to HOOK_INPUT.session_id as discriminator. New C0 probe chunk added
  before C1 to empirically verify the discriminator. AC10 added.
- F3 (major, correctness — TRANSCRIPT_HASH undefined): Applied. All TRANSCRIPT_HASH
  references in C2 replaced with SESSION_ID. Sentinel is now
  /tmp/runtime-tripwire-agent-${SESSION_ID}.
- F4 (major, testing — existing test file missing from C3): Applied. C3 write targets now
  include hooks/scripts/tests/test-track-dispatched-agents.sh. T1/T5 test cases updated
  in C3 spec.
- F5 (minor, architecture — wrap-shape duplication): Applied, path (b). C5 wiki §3 now
  states authoritative copy lives in the hook script; wiki quotes for human readers.
  AC5 updated to grep the hook file, not the wiki.
- F6 (minor, correctness — transcript-timestamp fragility): Applied. C2 spec now uses
  the agentId → em-session-id back-pointer → dispatched-agents.txt lookup for start time
  rather than parsing the transcript's first user-message timestamp.
- F7 (minor, calibration — Sonnet threshold): Applied. PM chose Sonnet = 12. C1 default
  table, AC3, and C5 wiki §2 updated accordingly with PM disposition noted inline.
- F8 (minor, correctness — Architecture summary misleading): Applied. Line updated to
  describe dispatched-agents.txt lookup via HOOK_INPUT.session_id resolution.
- F9 (minor, correctness — agent-completion-log.sh async race): Applied, folded into F1.
  C3 spec also adds: skip runtime check for an agentId whose return IS the triggering
  PostToolUse event.
- F10 (minor, documentation — R3 reactive, no detection mechanism): Applied. R3 mitigation
  now includes fire-log TSV. C5 wiki spec includes §6 naming the calibration evidence
  surface.
-->

# Runtime tripwire — model-aware nudge for long-running background executors

> Problem-set: [`docs/problems/2026-06-08-runtime-tripwire-background-executors.md`](../../../../../docs/problems/2026-06-08-runtime-tripwire-background-executors.md) (note: meta-repo path; ratified 2026-06-08, predates plugin-bundled `docs/problems/` convention which does not yet exist).

## Goal

Make the existing 15-min executor-runtime ceiling (`CLAUDE.md` § Subagent Dispatch HARD RULE) **actuator-backed** with a model-aware nudge that reaches both the executing agent (primary signal, on the agent's tool-result channel) and the EM (awareness signal, on the same channel as completion notifications). Modeled directly on `hooks/scripts/context-pressure-advisory.sh`. Nudge-not-kill; EM is the authority (trust-but-verify), agent's judgment is signal.

## Cross-plan coordination

Scanned `docs/plans/` for `runtime.tripwire`, `agent.overrun`, `wall.clock.{executor}` — no overlapping file scope or seam citations. No sibling plan touched.

## Acceptance Criteria

| ID  | Criterion (prose) | Test (typed-prefix) | Binding | Status |
|-----|-------------------|---------------------|---------|--------|
| AC1 | Agent-side hook fires `additionalContext` containing the wrap-shape prescription when elapsed exceeds the per-model threshold | `bash:bin/tests/test-runtime-tripwire-agent-side.sh` | gate-bound | realized — bin/tests/test-runtime-tripwire-agent-side.sh T3 + T6 (Slice-B integration adds T6) |
| AC2 | EM-side hook emits an awareness `additionalContext` naming the overrunning `agentId` and elapsed minutes when any tracked dispatch exceeds threshold | `bash:bin/tests/test-runtime-tripwire-em-side.sh` | gate-bound | realized — bin/tests/test-runtime-tripwire-em-side.sh T3 + T8 |
| AC3 | Per-model thresholds default to Opus 25 min / Sonnet 12 min / Haiku 10 min; each is env-var overrideable (`RUNTIME_TRIPWIRE_OPUS_MIN` / `_SONNET_MIN` / `_HAIKU_MIN`) | `bash:bin/tests/test-runtime-tripwire-thresholds.sh` | gate-bound | realized — bin/tests/test-runtime-tripwire-thresholds.sh 10/10 |
| AC4 | Bark-once per dispatch (sentinel scoped to firing `session_id`), not per tool-call | `grep:bin/tests/test-runtime-tripwire-bark-once.sh` | gate-bound | realized — bin/tests/test-runtime-tripwire-bark-once.sh 10/10 + em-side T7 |
| AC5 | Wrap-shape `additionalContext` prescribes: stop starting new work; persist partial state to disk; write a successor-handoff stub naming what's left; return | `grep:hooks/scripts/runtime-tripwire-advisory.sh` (literal strings from the prescription) | gate-bound | realized — grep:hooks/scripts/runtime-tripwire-advisory.sh confirmed 3× per canonical string |
| AC6 | No fire under threshold; no fire on `Bash run_in_background` shells (out-of-scope per problem-set OOS-1) | `bash:bin/tests/test-runtime-tripwire-no-false-fire.sh` | gate-bound | realized — bin/tests/test-runtime-tripwire-no-false-fire.sh (after Slice-B GIT_DIR fix) |
| AC7 | EM-side nudge cites the specific dispatch (`agentId` + elapsed minutes + model) so EM can act on the right target | `grep:bin/tests/test-runtime-tripwire-em-side.sh` (assert agentId in output) | gate-bound | realized — bin/tests/test-runtime-tripwire-em-side.sh T3 agentId assertion |
| AC8 | Hooks are bash-3.2 / BSD-coreutils portable per CLAUDE.md cross-platform doctrine | `bash:bin/check-shell-portability.sh hooks/scripts/runtime-tripwire-advisory.sh hooks/scripts/runtime-tripwire-em-check.sh` | gate-bound | cited-resolved — bash -n clean on all 4 hook scripts; manual portability check (no associative arrays, BSD/GNU stat dual-path) |
| AC9 | `CLAUDE.md` § Subagent Dispatch HARD RULE row (15-min ceiling) now points to the wiki entry surfacing the actuator | `grep:plugins/coordinator/CLAUDE.md` ("runtime-tripwire") | gate-bound | realized — CLAUDE.md:51 contains "runtime-tripwire" pointer |
| AC10 | C0 probe artifact written to `/tmp/runtime-tripwire-probe.log` and `HOOK_INPUT.session_id` classification (subagent vs EM) recorded | `bash:bin/tests/test-runtime-tripwire-probe.sh` (or manual read of probe log) | gate-bound | cited-resolved — C0 Classification block + problem-set ratification record |

## Architecture

**Two hooks, one shared threshold lib, one doctrine surface.**

- **Agent-side primary nudge** — new `hooks/scripts/runtime-tripwire-advisory.sh`, registered on PostToolUse with empty matcher (fires in subagent sessions because hook config is inherited). Computes elapsed from `dispatched-at` column in the EM's `dispatched-agents.txt` (looked up via the agent's own agentId back-pointer, resolved from `HOOK_INPUT.session_id`); emits `additionalContext` with the wrap-shape prescription when past threshold. Bark-once via `/tmp/runtime-tripwire-agent-${SESSION_ID}` sentinel, where `SESSION_ID` is taken from `HOOK_INPUT.session_id` (the firing session, distinct in subagent vs EM per `claude-code-platform-gotchas.md:154`).
- **EM-side awareness nudge** — new `hooks/scripts/runtime-tripwire-em-check.sh`, registered on EM-side PostToolUse (empty matcher). Self-throttled (5 min like the compaction advisory). Reads `<em_sid>/dispatched-agents.txt` for this EM session (sid resolved from `HOOK_INPUT.session_id` per the platform-gotchas wiki), cross-references each `agentId`'s `dispatched-at` field against its per-model threshold, emits one-line `additionalContext` naming each overrunning dispatch. Bark-once per `agentId`.
- **Dispatch-start stamping** — extend `hooks/scripts/track-dispatched-agents.sh` to write `dispatched-at` (Unix epoch) alongside the existing `agentId | model | subagent_type` record.
- **Shared thresholds** — `hooks/scripts/lib/runtime-thresholds.sh` (sourced by both hook scripts), table keyed on model family with env-var overrides.
- **Doctrine surface** — short `docs/wiki/runtime-tripwire.md` (~40 lines: actuator description, threshold table, wrap-shape doctrine inlined here as the canonical reference, EM-authority note). `CLAUDE.md` § Subagent Dispatch HARD RULE row gains a parenthetical pointer.

**Subagent-detection mechanism** — the agent-side hook fires in *both* EM and subagent sessions (empty matcher inherited). It distinguishes by inspecting `HOOK_INPUT.session_id` (the firing session's id, which is distinct in a subagent vs the EM per `claude-code-platform-gotchas.md:154`). The hook checks whether `HOOK_INPUT.session_id` appears under `.git/coordinator-sessions/.agents/*/em-session-id.txt` (present → this is a subagent) vs. absent (this is the EM session). **Important:** `CLAUDE_CODE_SESSION_ID` env var is NOT used for this purpose — it inherits the EM's session id inside subagents (per `claude-code-platform-gotchas.md:33-50`) and would give the wrong answer. Only `HOOK_INPUT.session_id` is reliable here. In the EM session the agent-side script no-ops (the EM-side check does that work).

**Why two scripts, not one** — the agent-side fires inside the subagent (its session_id, its transcript), the EM-side fires inside the EM (different transcript, needs cross-reference to subagent dispatches via the existing `.git/coordinator-sessions/.agents/` ledger). Same script with branching is feasible but harder to read; two scripts with one shared lib is the cleaner shape.

## Chunks

### C0 — Subagent-detect probe (dispatched first; gates C1)

**Write target:** `/tmp/runtime-tripwire-probe.log` (runtime artifact, not checked in)

**Spec:**
- Write a temporary 10-line probe hook at `hooks/scripts/runtime-tripwire-probe.sh` (deleted after C0).
- The probe logs two fields on every PostToolUse fire: `HOOK_INPUT.session_id` (parsed from stdin via jq) and `$CLAUDE_CODE_SESSION_ID` env var.
- Format: `FIRING_SESSION_ID=<val> ENV_SESSION_ID=<val>` appended to `/tmp/runtime-tripwire-probe.log`.
- Register the probe temporarily in `hooks/hooks.json` under PostToolUse empty matcher; unregister at end of C0.
- Dispatch a one-shot Sonnet subagent (any trivial task — e.g., `echo hello`). Read `/tmp/runtime-tripwire-probe.log`.
- Confirm: `FIRING_SESSION_ID` differs from parent EM's session id (proving subagents get a distinct id in `HOOK_INPUT.session_id`); `ENV_SESSION_ID` matches the EM's session id (proving the env var inherits — do NOT use it as discriminator).
- Record classification finding in a brief comment at the top of `hooks/scripts/runtime-tripwire-advisory.sh` stub (created in C2).
- Clean up probe hook + unregister from hooks.json.

**AC10 satisfied:** probe log written + classification recorded before C1 begins.

**Hard constraints:** explicit file scope above; no commits; no out-of-scope edits; probe hook is temporary — must be removed from hooks.json before C0 returns.

### C1 — Shared thresholds lib (dispatch after C0; pins the contract C2/C3 consume)
**Status:** Execution complete — pending verification (executor completed 2026-06-08)

**Write target:** `hooks/scripts/lib/runtime-thresholds.sh` (new)

**Spec:**
- Bash-sourced library exposing `runtime_threshold_minutes(MODEL_ID)` → echoes integer minutes.
- Model-family detection: same regex shape as `context-pressure-advisory.sh:168-194` (`*opus*` / `*sonnet*` / `*haiku*` / `[1m]` suffix / `-1m` infix).
- Default table: Opus = 25, Sonnet = 12, Haiku = 10. (Sonnet = 12 gives a 3-min wrap buffer before the 15-min CLAUDE.md HARD RULE ceiling — PM-dispositioned 2026-06-08.)
- Env-var overrides: `RUNTIME_TRIPWIRE_OPUS_MIN`, `RUNTIME_TRIPWIRE_SONNET_MIN`, `RUNTIME_TRIPWIRE_HAIKU_MIN`.
- Unknown model → echo `25` (Opus default, matches the existing compaction-advisory's bias-toward-Opus failure direction).
- Bash 3.2 / BSD coreutils portable (no associative arrays, no GNU-isms).

**Test surface:** `bin/tests/test-runtime-tripwire-thresholds.sh` parameterized cases (5 model IDs × default + override).

**Hard constraints:** explicit file scope above; no commits; no out-of-scope edits; no fallback escape hatches (if the model is unknown, return Opus default and continue — do not silently disable).

### C2 — Agent-side runtime nudge hook

**Write target:** `hooks/scripts/runtime-tripwire-advisory.sh` (new). **Depends on C1.**

**Spec:**
- PostToolUse hook shape: read `HOOK_INPUT` from stdin (jq or sed fallback per `context-pressure-advisory.sh:31-38`).
- Subagent-detect: parse `HOOK_INPUT.session_id` from stdin. Check whether that session_id appears under any `.git/coordinator-sessions/.agents/*/em-session-id.txt`. If NOT found, exit 0 (this is the EM session; EM-side hook handles its half). **Do NOT use `$CLAUDE_CODE_SESSION_ID` env var for this check** — it inherits the EM's id in subagents and will give the wrong answer (per `claude-code-platform-gotchas.md:33-50`, confirmed by C0 probe).
- Source `lib/runtime-thresholds.sh`.
- Detect model from transcript (reuse the `grep -m1 -oE '"model"[[:space:]]*:[[:space:]]*"claude-[^"]*"'` shape from `context-pressure-advisory.sh:154`).
- Compute elapsed: read own agentId from `HOOK_INPUT.tool_response.agentId` (or equivalent platform field confirmed via C0 probe). Look up `.git/coordinator-sessions/.agents/<agentId>/em-session-id.txt` to find the EM session id. Read `<em_sid>/dispatched-agents.txt`, find own row, use `dispatched-at` column (Unix epoch) as start time. Compute `now - dispatched-at` in minutes. This is the single source of truth and avoids parsing transcript timestamps.
- If elapsed ≥ threshold AND no bark-once sentinel (`/tmp/runtime-tripwire-agent-${SESSION_ID}`, where `SESSION_ID` = `HOOK_INPUT.session_id`, matching the existing `context-pressure-throttle-${SESSION_ID}` pattern), emit `additionalContext` JSON containing:
  - One-line header naming model + elapsed.
  - Wrap-shape prescription block (inlined — see C5 for canonical text; authoritative copy lives in this script):
    > "You've been running ~N minutes (past the ~M min runtime tripwire for {model}). Past this point, dispatches commonly enter compaction-decay — running redundant tests, looking for more things to check, oscillating between approaches. **Trust-but-verify with the EM as authority:** form your own judgment, but assume the EM will evaluate it.
    > **Wrap shape (the default):** stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return.
    > **If you judge yourself genuinely close to a clean return (≤2-3 min):** say so explicitly in your return so the EM can decide whether to wait."
- Touch the sentinel.
- Autonomous-run-aware: read `/tmp/autonomous-run-${PARENT_EM_SESSION_ID}` (looked up via the .agents back-pointer); if autonomous, soften the language slightly per the compaction-advisory pattern but do NOT suppress the nudge.
- All `set -uo pipefail`; explicit `|| true` on stat/jq/find; fail-open on missing data.

**Test surface:** `bin/tests/test-runtime-tripwire-agent-side.sh` with mocked transcript (timestamps + model line) + temp sentinel dir.

**Hard constraints:** as C1.

### C3 — EM-side awareness nudge hook + tracker extension

**Write targets:**
- `hooks/scripts/runtime-tripwire-em-check.sh` (new)
- `hooks/scripts/track-dispatched-agents.sh` (extend record shape with `dispatched-at` column)
- `hooks/scripts/tests/test-track-dispatched-agents.sh` (existing test file — update for new column shape)

**Depends on C1.** Touches `track-dispatched-agents.sh` (read by `coordinator-safe-commit` per the existing file header) — backward-compatible: append column, legacy 3-column records parse with `dispatched-at = 0`.

**Spec for `runtime-tripwire-em-check.sh`:**
- PostToolUse hook (EM session). Self-throttle 5 min via `/tmp/runtime-tripwire-em-throttle-${SESSION_ID}` (same pattern as `context-pressure-advisory.sh:100-115`).
- Subagent-detect inverse: parse `HOOK_INPUT.session_id` from stdin. If that session_id IS found under any `.git/coordinator-sessions/.agents/*/em-session-id.txt`, exit 0 (this is the subagent path; agent-side hook handles). **Do NOT use `$CLAUDE_CODE_SESSION_ID`** — same reason as C2.
- Enumerate `.git/coordinator-sessions/<em_sid>/dispatched-agents.txt`; for each record, parse `agentId | model | subagent_type | dispatched-at`.
- For each: if `dispatched-at > 0` AND `now - dispatched-at` ≥ `runtime_threshold_minutes(model) * 60`, AND no per-agentId sentinel (`/tmp/runtime-tripwire-em-${agentId}`), include in nudge.
- **Skip-if-returning:** if the firing PostToolUse event carries `tool_response.agentId` for an agent that just returned (i.e., the agent return IS the triggering event), skip the runtime check for that agentId — it's already in wrap-state by definition. The agent-completion-log.sh hook records completion; cross-reference to detect this case.
- Emit ONE `additionalContext` block listing all overrun dispatches: `agentId | model | elapsed-min`. Touch each sentinel.
- Skip dispatches whose `agentId` has a corresponding `.agents/<agentId>/em-session-id.txt` entry showing the agent has already returned (presence of agent-completion-log entry — reuse existing surface).

**Spec for `track-dispatched-agents.sh` extension:**
- Append `\t$(date +%s)` to the existing record line.
- Update file-header comment to document new column.
- Legacy-record read in `coordinator-safe-commit` (or wherever): missing 4th column → treat as 0.

**Spec for `test-track-dispatched-agents.sh` update:**
- Update T1 to assert 4-column shape: `cut -f4` returns a non-empty integer matching `^[0-9]+$`.
- Update T5 (backward-compat case): seed a legacy 3-column record (`agentId\tmodel\tsubagent_type`) and assert it still parses with `dispatched-at = 0`.

**Test surface:** `bin/tests/test-runtime-tripwire-em-side.sh` with seeded `.agents/` ledger fixtures.

**Hard constraints:** as C1. Plus: **shared symbol** — `dispatched-agents.txt` record shape is mutated; sweep `git grep -l dispatched-agents.txt` for readers and verify each gracefully handles 4-column or returns column 1 only.

### C4 — Hooks.json wiring

**Write target:** `hooks/hooks.json`

**Spec:**
- Add `runtime-tripwire-advisory.sh` to the existing PostToolUse empty-matcher block (currently houses `context-pressure-advisory.sh`). Register with `async: false`. (Review: the Staff Engineer — async:true hooks on PostToolUse can fire after the session they're reading from has already mutated; must be synchronous to avoid stale-read races per `claude-code-platform-gotchas.md`.)
- Add `runtime-tripwire-em-check.sh` to the same block. Register with `async: false` for the same reason.
- Flip `track-dispatched-agents.sh` to `async: false` if currently `async: true`. (The `dispatched-at` write must complete before any hook that reads `dispatched-agents.txt` fires for that dispatch.)
- Flip `agent-completion-log.sh` to `async: false` if currently `async: true`. (The completion record must be visible to `runtime-tripwire-em-check.sh`'s skip-if-returning check.)
- Both new hooks `timeout: 5`. Order: after `context-pressure-advisory.sh` (they're independent; ordering is for log readability).

**Test surface:** `grep:hooks/hooks.json` confirms both new hooks registered with empty matcher under PostToolUse, all four named hooks have `async: false`.

**Hard constraints:** as C1. Touches no other JSON.

### C5 — Doctrine surface

**Write targets:**
- `docs/wiki/runtime-tripwire.md` (new)
- `CLAUDE.md` § Subagent Dispatch HARD RULE row (one-line pointer addition)

**Spec for wiki:**
- Title, frontmatter.
- Section 1: "What it actuates." (Cites the 15-min ceiling that already exists in `CLAUDE.md`.)
- Section 2: "Threshold table." (Per-model defaults: Opus = 25 min, Sonnet = 12 min, Haiku = 10 min. Override env vars. Document the Sonnet relationship explicitly: "Sonnet trips at 12 min, 3 min before the CLAUDE.md HARD RULE 15-min hard ceiling — the buffer exists so the wrap-shape (persist → write successor stub → return) lands before the agent crosses doctrine." Note PM disposition 2026-06-08 inline.)
- Section 3: "Wrap shape — the canonical prescription." (Quoted here for human readers; authoritative copy lives in `hooks/scripts/runtime-tripwire-advisory.sh` — the hook script is the single source of truth for exact wording.)
- Section 4: "EM authority." (Trust-but-verify; agent judgment is signal; EM decides whether to wait, plan successor, or TaskStop.)
- Section 5: "What it does NOT do." (No auto-kill; no run_in_background coverage; no mid-flight threshold renegotiation — quoted from problem-set OOS.)
- Section 6: "Calibration evidence surface." (`state/runtime-tripwire-fire-log.tsv` — hooks append one record per fire (`timestamp \t agentId \t model \t elapsed_min \t fire_type`). Surveyed at `/workweek-complete` Step 4 queue triage; recurring miscalibration surfaces empirically rather than waiting for a PM complaint.)

**Spec for CLAUDE.md edit:**
- The HARD RULE row at `CLAUDE.md:51` currently reads: *"Size each executor ~5-10 min on one coherent surface (15 min hard ceiling; split before dispatch)."* Append: *" — runtime-tripwire actuates this ceiling via `docs/wiki/runtime-tripwire.md`."*

> **Shipped note:** Actual attachment landed mid-sentence after `fan-out-dispatch.sh` reference, not at end of sentence as forecast — equivalent meaning, slightly different anchor.

**Test surface:** `grep:hooks/scripts/runtime-tripwire-advisory.sh` for the wrap-shape canonical strings AC5 asserts on (authoritative copy is the hook script, not the wiki); `grep:CLAUDE.md` for the pointer per AC9.

**Hard constraints:** as C1. CLAUDE.md edit is single-line append per `document-bloat-trim.md` defaults.

### C6 — Tests

**Write targets:**
- `bin/tests/test-runtime-tripwire-thresholds.sh`
- `bin/tests/test-runtime-tripwire-agent-side.sh`
- `bin/tests/test-runtime-tripwire-em-side.sh`
- `bin/tests/test-runtime-tripwire-bark-once.sh`
- `bin/tests/test-runtime-tripwire-no-false-fire.sh`

**Depends on C1–C5.** Last chunk.

**Spec:** Each test script: shebang, set -euo pipefail, temp-dir setup, fixture seeding, hook invocation via piped JSON HOOK_INPUT, assertion on stdout JSON via jq, cleanup. Pattern shape per existing `bin/tests/test-detect-onboarding-offer.sh`.

**Hard constraints:** as C1. Plus: tests must pass on bash 3.2 (per AC8 doctrine).

## Dispatch sequencing

- **C0** dispatches first, alone (empirically verifies the `HOOK_INPUT.session_id` discriminator before any spec bets on it).
- **C1** after C0 (pins the shared-lib interface; C0 classification finding annotated in C1 output).
- **C2 + C3 + C5 in parallel** after C1 returns (disjoint write targets; C5 doctrine consumes the threshold defaults that C1 froze).
- **C4** after C2, C3 (registers the new scripts; flips async flags only after scripts exist).
- **C6** last (tests the realized surface).

T-shirt: M. Each chunk sized ~5-10 min on one coherent surface. C3 is the borderline one (two write targets, schema extension) — if executor returns mid-work, EM splits it into C3a (tracker schema bump) and C3b (em-check.sh) as a follow-up dispatch.

## Out of scope (per problem-set)

- Auto-kill on overrun (problem-set OOS).
- `Bash run_in_background` long-running shells (problem-set OOS — `Agent` matcher only).
- Mid-dispatch threshold renegotiation (problem-set OOS).
- ~~Re-nudge cadence after first fire~~ — **AMENDED 2026-06-08:** single EM-side re-nudge at +5 min shipped in-scope per PM disposition mid-session. See problem-set OOS-4 (also amended) and commit a35439e2.
- Custom per-dispatch threshold ergonomics (problem-set OOS — defer to v2 if env-vars prove insufficient).

## Risks

- **R1 — Subagent-detect mechanism is the load-bearing platform assumption.** The agent-side hook fires in subagent sessions because hook config is inherited (confirmed by reading `context-pressure-advisory.sh` already firing inside subagents per its self-throttle pattern), but the subagent-detect heuristic (check `HOOK_INPUT.session_id` against `.agents/*/em-session-id.txt`) is empirical — hence C0 validates it before C1 bets the design on it. **Mitigation:** C0 probe confirms `HOOK_INPUT.session_id` is distinct in subagent vs EM. C2 test (`test-runtime-tripwire-agent-side.sh`) explicitly asserts subagent-path vs. EM-path branching against fixture sessions. If platform behavior changes, this test catches it.
- **R2 — `dispatched-at` schema extension reaches `coordinator-safe-commit` and other readers of `dispatched-agents.txt`.** **Mitigation:** C3 spec mandates a sweep of `git grep -l dispatched-agents.txt` and a backward-compat path (3-col records parse with `dispatched-at = 0`). Updated `test-track-dispatched-agents.sh` T5 asserts the legacy path.
- **R3 — Threshold defaults (25/12/10) are best-guess.** **Mitigation:** env-var override on day one (AC3); calibrate empirically via `state/runtime-tripwire-fire-log.tsv`. Hooks append a one-line record to that file on every fire (`timestamp \t agentId \t model \t elapsed_min \t fire_type`). Intended for triage at `/workweek-complete` Step 4 — wiring TBD; recurring miscalibration surfaces empirically rather than waiting for a PM complaint.

## Dispatch Ledger

Built 2026-06-08 at execute-plan Phase 1.5 / 1.6. One row per chunk; serial chain = N rows (`after #N`), not one long-lived executor. 12 dispatches total (C0 inline EM; C1 alone; Wave 2 fans out 4; C4 alone; Wave 4 fans out 5 tests).

| # | chunk-id | one-line brief | write-files | runs | est-min | status |
|---|---|---|---|---|---|---|
| 1 | C0 | Empirical probe — confirm HOOK_INPUT.session_id is distinct in subagent vs EM (CLAUDE_CODE_SESSION_ID is not) | (resolved by prior probe — see C0 Classification block below) | inline (EM) | 8 | verified |
| 2 | C1 | Shared thresholds lib — Opus=25 / Sonnet=12 / Haiku=10 + env-var overrides | hooks/scripts/lib/runtime-thresholds.sh | after #1 | 5 | committed |
| 3 | C2 | Agent-side runtime nudge hook | hooks/scripts/runtime-tripwire-advisory.sh | after #2, parallel | 10 | committed |
| 4 | C3a | Tracker schema bump (dispatched-at column) + test update | hooks/scripts/track-dispatched-agents.sh, hooks/scripts/tests/test-track-dispatched-agents.sh | after #2, parallel | 6 | committed |
| 5 | C3b | EM-side awareness nudge hook (em-check.sh) | hooks/scripts/runtime-tripwire-em-check.sh | after #2, parallel | 10 | committed |
| 6 | C5 | Doctrine wiki + CLAUDE.md pointer | docs/wiki/runtime-tripwire.md, plugins/coordinator/CLAUDE.md | after #2, parallel | 6 | committed |
| 7 | C4 | hooks.json wiring — register new hooks + flip 4 async:true→false | hooks/hooks.json | after #3,#4,#5,#6 | 3 | committed |
| 8 | C6a | Test thresholds lib | bin/tests/test-runtime-tripwire-thresholds.sh | after #7, parallel | 4 | committed |
| 9 | C6b | Test agent-side hook | bin/tests/test-runtime-tripwire-agent-side.sh | after #7, parallel | 5 | committed |
| 10 | C6c | Test EM-side hook | bin/tests/test-runtime-tripwire-em-side.sh | after #7, parallel | 5 | committed |
| 11 | C6d | Test bark-once sentinel | bin/tests/test-runtime-tripwire-bark-once.sh | after #7, parallel | 4 | committed |
| 12 | C6e | Test no-false-fire | bin/tests/test-runtime-tripwire-no-false-fire.sh | after #7, parallel | 4 | committed |

**Status legend:** `pending` → `dispatched` → `verified` → `committed`. Updated on disk as each transition lands.

### C0 Classification (2026-06-08, EM-inline)

The platform behavior C0 was designed to verify is already documented from a prior empirical probe:

- `docs/wiki/claude-code-platform-gotchas.md:154-158` ("PostToolUse JSON does not carry parent-session pointer") records the 2026-05-05 finding (`tasks/probes/2026-05-05-probe-0-2-results.md`): **session isolation between EM and dispatched agents is complete at both the env and hook levels**. The `HOOK_INPUT.session_id` field is the firing session's distinct id; subagents and EM produce different values.
- `docs/wiki/claude-code-platform-gotchas.md:33-50` ("`session_id` in subprocesses") records (2.1.150+ live probe 2026-05-23): **`CLAUDE_CODE_SESSION_ID` env var inherits the dispatching EM's id** in subagents — it must NOT be used as the subagent-vs-EM discriminator.

**Discriminator pinned for C2 + C3b:**
- READ: `HOOK_INPUT.session_id` (parse from stdin via jq).
- DO NOT READ: `$CLAUDE_CODE_SESSION_ID` env var (inherits EM's id; gives wrong answer in subagent).
- Subagent-detect test: `HOOK_INPUT.session_id` appears under `.git/coordinator-sessions/.agents/<aid>/em-session-id.txt` → this IS a subagent. Absent → this is the EM session.

No temp probe hook registered (avoids shared `hooks.json` mutation hazard with concurrent EM sessions).

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| C0 shipped as inspection-of-existing-platform-gotchas-evidence, NOT as temp-probe-hook + dispatched one-shot subagent (was: register `hooks/scripts/runtime-tripwire-probe.sh` temporarily in `hooks/hooks.json`, dispatch Sonnet subagent, read `/tmp/runtime-tripwire-probe.log`) | Existing probe artifacts (`docs/wiki/claude-code-platform-gotchas.md:33-50` from 2026-05-23 live probe + `:154-158` from 2026-05-05 probe-0-2-results.md) already answered the load-bearing discriminator question. Spec-as-written would have mutated shared `hooks.json` mid-session — concurrent-EM hazard. Substitute approach satisfies the same AC10 ("HOOK_INPUT.session_id classification recorded") via the C0 Classification block above. | c61cee9d |
| EM-side +5 re-nudge SHIPPED (was: OOS-4 "Re-nudge cadence after first fire — bark-once per dispatch is the v1; revisit only if empirically needed") | PM observation 2026-06-08 (~15 min after the v1 commit): "let's give it just a few more minutes" pattern re-creates P1 (EM-blind-to-clock) on the *other* side of the first nudge. The v1 hedge was empirical-evidence-pending; the observation IS the evidence. Problem-set OOS-4 amended inline with full rationale. Implementation: single +5 EM-only re-nudge with escalating tone, then silence. | a35439e2 |
| Wave-2 dispatch ledger row status edits were freelanced by 4 of ~8 executors (was: ledger is EM-owned, executors don't touch the plan doc) | Executors want to communicate progress; the dispatch brief OOS prohibition + peer-scope prohibition was insufficient. EM mitigation in-session: `git checkout HEAD -- <plan-path>` before each wave's union commit. Captured as a [universal] lesson (`state/lessons.md`) for structural fix downstream — restructure dispatch shape, don't re-prohibit. | (no commit — reverted) |
| C3 shipped split as C3a (tracker schema bump) + C3b (em-check.sh) (was: C3 as a single chunk covering both write targets) | C3 was flagged as borderline at spec time ("if executor returns mid-work, EM splits"); executor did return mid-work on the tracker extension, so the split was exercised as designed. Reflected in dispatch ledger rows 4 (C3a) and 5 (C3b). No spec deviation — contingency explicitly named. | — |

## Confidence

- 7-dim confidence checklist: green.
- Cross-plan scan: no overlap.
- Substrate verified: `context-pressure-advisory.sh` and `track-dispatched-agents.sh` read at write-time.
- Problem-set ratified by PM 2026-06-08, four rounds of convergence.
- the Staff Engineer review integrated 2026-06-08 (REQUIRES_CHANGES → all 10 findings applied).
