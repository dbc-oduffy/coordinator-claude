---
title: Runtime Tripwire — Model-Aware Nudge for Long-Running Background Executors
tags: [doctrine, hooks, agent-dispatch, executor-runtime]
status: active
---

# Runtime Tripwire — Model-Aware Nudge for Long-Running Background Executors

<!-- spec-backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md § C5 -->

> **This tripwire does not currently fire (PM ruling) — both caller-side surfaces are stood
> down, not restorable by a flag flip.** `runtime-tripwire-em-check.py`'s subagent-overrun
> nudge, its dispatch-tracking loop, `_check_subagent_arrival`, `_runtime_threshold_minutes`,
> and the tests pinning them were excised entirely (no live `_SUBAGENT_OVERRUN_TRIPWIRE_ENABLED`
> constant remains); `runtime-tripwire-stop-watcher.py`'s `Stop` registration remains removed
> from `coordinator/hooks/hooks.json` (script retained on disk). Measured basis: 681 fires over
> 26 days concerning only 6 distinct agents against a 0.59% genuine stall rate;
> `7a928d741`'s demotion of the `"unknown"` arrival state to suppressing stopped the false-fire
> storm but, since subagent transcripts are absent for ~99.5% of dispatched-agent rows, also
> left the nudge unable to fire on a real stall — a nudge that mostly cannot fire, ~99.4% wrong
> on the rare occasions it did. **Restore recipe:** reconstitute `_check_subagent_arrival`,
> `_runtime_threshold_minutes`, the dispatch-tracking loop body, and the retired tests from git
> history (verbatim recipe: `archive/debt-backlog/2026-08/2026-08-29-runtime-tripwire-em-check-py-four-overengin-a1f27c2e8c.yaml`),
> AND re-add the `Stop` registration for `runtime-tripwire-stop-watcher.py` in
> `coordinator/hooks/hooks.json`. The engine-side prerequisite the stand-down named (a durable
> arrival record) still does not exist, so restore remains blocked on that regardless. The rest
> of this page describes the design as it existed before excision and is preserved as the
> recoverable record, not as a description of current live behaviour — except §2 and the
> `RUNTIME_TRIPWIRE_MAX_TRACK_MIN` cap, both of which remain genuinely live today, the former
> in `runtime-tripwire-stop-watcher.py`'s own threshold read, the latter in that same script's
> tracked-dispatch cap (see §5/§6 notes below).

## §1 — What it actuates

The 15-minute executor-runtime ceiling in `CLAUDE.md` § Subagent Dispatch HARD RULE ("Size each executor ~5-10 min on one coherent surface (15 min hard ceiling; split before dispatch)") existed as prose doctrine without an actuator. The EM had no wall-clock awareness between dispatch and completion — the ceiling was a planning heuristic enforced only by convention.

The runtime tripwire makes this ceiling **actuator-backed.** When an executor crosses its per-model threshold, the hook fires a model-aware nudge on two channels simultaneously:

- **Agent-side (primary signal):** `additionalContext` injected on the agent's own tool-result channel, naming the overrun and prescribing the wrap shape.
- **EM-side (awareness signal):** `additionalContext` on the EM's channel (same channel as completion notifications), naming the specific `agentId`, elapsed minutes, and model so the EM can act.

The empirical trigger for this work: a zombie discriminator executor ran for 15+ minutes on 2026-06-08 (logged in `docs/problems/2026-06-08-runtime-tripwire-background-executors.md`), circling past the point where wall-clock and compaction-decay made further progress unlikely. The EM had no in-session signal until the agent returned.

Modeled directly on the compaction-advisory pattern (`coordinator/hooks/scripts/context-pressure-precompact.py`). Nudge-not-kill; EM is the authority.

## §2 — Threshold table

Per-model defaults and env-var overrides:

| Model family | Default threshold | Env var override |
|---|---|---|
| Opus | 25 min | `RUNTIME_TRIPWIRE_OPUS_MIN` |
| Sonnet | 12 min | `RUNTIME_TRIPWIRE_SONNET_MIN` |
| Haiku | 10 min | `RUNTIME_TRIPWIRE_HAIKU_MIN` |

**Sonnet and the HARD RULE ceiling.** Sonnet trips at 12 min, 3 minutes before the `CLAUDE.md` HARD RULE 15-min hard ceiling. The buffer exists so the wrap shape (persist → write successor stub → return) lands before the agent crosses doctrine. PM disposition 2026-06-08 (`docs/problems/2026-06-08-runtime-tripwire-background-executors.md` P3): Sonnet = 12 was chosen explicitly over 15 to give this 3-minute execution margin.

Unknown model defaults to 25 (Opus default), matching the existing compaction-advisory's bias-toward-Opus failure direction.

## §3 — Wrap shape — the canonical prescription

**Authoritative copy lives in the agent-side hook. Quoted here for human readers; if the wiki and the hook ever diverge, the hook is the source of truth.**

The wrap-shape prescription injected via `additionalContext` when an executor crosses threshold:

> RUNTIME TRIPWIRE — you've been running ~N minutes (past the ~M min runtime tripwire for {model}). Past this point, dispatches commonly enter compaction-decay — running redundant tests, looking for more things to check, oscillating between approaches. **Trust-but-verify with the EM as authority:** form your own judgment, but assume the EM will evaluate it.
>
> **Wrap shape (the default):** stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return.
>
> **If you judge yourself genuinely close to a clean return (≤2-3 min):** say so explicitly in your return so the EM can decide whether to wait.

**Autonomous-run variant:** When the EM is running autonomously, the language is softened slightly (per the compaction-advisory pattern) but the nudge is NOT suppressed. The wrap shape remains the same.

## §4 — EM authority

Per the ratified problem-set P4 (`docs/problems/2026-06-08-runtime-tripwire-background-executors.md`): the EM is the authority over the dispatch (trust-but-verify); the agent's judgment is a *signal* to the EM, not the terminal call.

Concretely, when the nudge fires:

1. Both the agent and the EM see it.
2. The agent forms a judgment: "close to clean return" vs. "circling and should wrap."
3. The EM evaluates that judgment against visible progress — TaskList state, recent tool calls, disk artifacts.
4. The EM decides: wait for the clean return, plan a successor dispatch now, or `TaskStop` the agent.

Neither the hook nor the EM reflexively kills. The hook fires a prescription; the EM decides the disposition. This mirrors the compaction-advisory pattern (`context-pressure-advisory.sh`) where the agent surfaces pressure and proposes wrap; EM decides whether the proposed action is right for the situation.

## §5 — What it does NOT do

Verbatim from the ratified problem-set OOS (`docs/problems/2026-06-08-runtime-tripwire-background-executors.md`):

- **No auto-kill on overrun.** The hook nudges; it does not terminate. The EM holds `TaskStop` authority.
- **No `Bash run_in_background` coverage.** Out of scope. The tripwire covers `Agent` dispatch calls only; long-running `Bash` shells are not tracked.
- **No mid-flight threshold renegotiation.** The threshold for a given dispatch is fixed at dispatch time via the model identity. No per-dispatch override ergonomics in v1 — env-var override is the only knob.
- **Agent-side: bark-once per dispatch.** No automatic re-nudge to the agent. The sentinel (`/tmp/runtime-tripwire-agent-${SESSION_ID}`) fires once per dispatch and is not cleared automatically. The agent already got the wrap-shape on first fire; re-nudging it just repeats the same prescription.
- **EM-side re-nudge/restage: excised.** `RUNTIME_TRIPWIRE_RESTAGE_SECONDS` and the single-re-nudge-then-silence mechanism it gated (previously: fire once, restage once at +5 min, then silence for that dispatch) had zero remaining readers once the dispatch-tracking loop was excised — the env var and its sentinel (`/tmp/runtime-tripwire-em-restage-${agentId}`) are gone, not merely dormant. Restore recipe above.
- **No per-dispatch threshold ergonomics in v1.** Env-var override is global, not per-dispatch. Per-dispatch threshold negotiation is deferred to v2 if empirical evidence shows env-var-only is insufficient.
- **Max-age cap — still live, in `runtime-tripwire-stop-watcher.py`.** `RUNTIME_TRIPWIRE_MAX_TRACK_MIN` (default 90 min) is read by the stop-watcher script's own tracked-dispatch cap, independent of the excised EM-side dispatch-tracking loop above. Past 90 min a dispatch has either completed or hung long enough that further nudges become noise; skip is silent — no fire-log entry, no nudge.

## §6 — Calibration evidence surface

Hooks append a one-line record to `state/runtime-tripwire-fire-log.tsv` on every fire, with the shape:

```
timestamp \t agentId \t model \t elapsed_min \t fire_type
```

where `fire_type` ∈ {`agent-side`, `em-side`} — `em-side-restage` was excised along with the
re-nudge mechanism it named (see §5).

This log is intended for triage at `/workweek-complete` Step 3.5 — wiring TBD. Recurring miscalibration surfaces empirically: if Sonnet=12 fires constantly on legitimately-progressing dispatches, that's the trigger to recalibrate via env-var override (and eventually a default bump via a plan).

**The failure mode this defends against:** a default that fires constantly trains the EM and agents to ignore the nudge — which regresses the actuator to status-quo prose-only doctrine. The log makes systematic miscalibration visible before it reaches that failure state.

**2026-06-09 — skip-if-completed false-positive fixed.** Empirical fire-log evidence (same `agentId` re-firing as `em-side-restage` long after the agent returned, e.g. `ae4c9a965adb5095f` at 10:39 then 10:48; multiple same-batch agents at 11:57 / 12:05 / 13:59) showed the EM-side hook was nudging on already-completed dispatches — exactly the train-EM-to-ignore failure mode this section warns about. Root cause: `agent-completion-log.py` recorded `tool_input.name` (the optional addressable-teammate name, almost never set), and the EM-check skip grepped for `"name":"$agentId"`, which never matched. Fix: log `tool_response.agentId` and skip against that. Records before 2026-06-09 lack the `agentId` field; the failure mode is invisible to back-dated analysis but is fully captured going forward.

**Orphan-tail follow-up: max-age cap.** An `agentId`-field fix can leave rows dispatched before the fix without an `agentId` in their audit-log entries, so their dispatched-agents.txt rows have no path to skip-if-completed matching and read as stale runaways hours after their work landed. `RUNTIME_TRIPWIRE_MAX_TRACK_MIN` (default 90 min) is a structural backstop for exactly this: any dispatch older than the cap is silently skipped regardless of audit-log state — read today by `runtime-tripwire-stop-watcher.py` (see §5), the EM-side dispatch-tracking loop having been excised.

**`agent-audit.jsonl` completion cross-check: retired (deliberately, and correctly).** The SUBAGENTSTOP TRIGGER-LOSS branch does not use `agent-audit.jsonl` as a completion signal, on measured justification: that branch fired 681 times over 26 days concerning only 6 distinct agents, against a 0.59% genuine stall rate, and diagnosed the root cause precisely — **`agent-audit.jsonl` is a DISPATCH log, not a completion log.** Every record has exactly one shape (`agentId`, `description`, `logged_at`, `name`, `subagent_type` — no exit status, no completion field, ever), and it is written by the SAME `PostToolUse:Agent` event that writes `dispatched-agents.txt`. Every dispatched row is therefore present in the audit log by construction, 100% of the time, regardless of whether the dispatch ever returned — the commit measured 1336/1336 rows matching this way. A membership check against this file cannot distinguish "returned" from "still running"; it suppresses every row unconditionally. The commit replaced that dead cross-check with a per-agent transcript-arrival oracle (`hooks.subagent_arrival_check`) as the sole completion/liveness signal.

**2026-07-31 — a same-day false restoration, reverted the same day.** The arrival oracle above answers `"unknown"` for the overwhelming majority of agents (measured on this repo: 14 subagent transcript files on disk against 3,083 distinct dispatched agentIds), and the hook at the time treated `"unknown"` as fire-worthy ("fail toward firing") — so the EM-side hook fired on essentially every completed dispatch. A cross-repo memo misdiagnosed this as the loss of a working `agent-audit.jsonl` completion oracle (reading `d75402345`'s retirement backwards) and this file briefly restored an audit-log completion cross-check on that premise. It was reverted within the same day once the dispatch-log-not-completion-log fact above was verified directly (6,245 audit-log records, one shape, no exceptions; every `dispatched-agents.txt` row present by construction). **The actual, correct fix, landed and retained:**

- The arrival oracle (`hooks.subagent_arrival_check`) nudges ONLY on a confirmed `"running"`; both `"arrived"` and `"unknown"` now suppress. `"unknown"` does not fail toward firing, because it is the overwhelmingly common no-information case (absent/unreadable transcript), not evidence of a live agent.
- There is deliberately NO `agent-audit.jsonl` completion cross-check anywhere in this hook. It cannot be one — see above.

**Do not reintroduce an `agent-audit.jsonl` completion cross-check here** — this has been tried twice (a predecessor branch, then again briefly afterward) and measured wrong both times, for the identical structural reason (same-event, same-instant write to both files).

## §7 — Layered idle-EM coverage

<!-- spec-backlink: docs/plans/2026-06-15-runtime-tripwire-idle-em-layered-fix.md -->

The v1 wiring fired only on `PostToolUse`. Empirical evidence on 2026-06-15 (handoff `state/handoffs/2026-06-15_111753_runtime-tripwire-not-firing-on-20min-executor.md`) showed an EM in active PM conversation with a 20-min Sonnet executor in flight got no nudge for the entire dispatch window — the trigger surface was structurally silent in the exact case the tripwire was built for. The fix is layered coverage, each layer addressing a distinct failure shape:

| Layer | Trigger surface | Failure shape covered | Always-on? |
|---|---|---|---|
| **L1 — Activity wiring** | `PostToolUse` + `UserPromptSubmit` + `Stop` (all three fire `runtime-tripwire-em-check.py`) | EM in active conversation with PM (no tool calls between dispatches) | Per-tracked-agent (driven by `dispatched-agents.txt`) |
| **L2 — asyncRewake-on-Stop watcher** | `Stop` event spawns `runtime-tripwire-stop-watcher.py` as `asyncRewake: true` (parent exits 0; bg subprocess sleeps to threshold, emits stderr nudge, exits 2 → platform re-wakes EM with `<system-reminder>`) | Genuinely-idle EM: dispatches then sits silent (no PM turns at all) | Single PID-locked watcher per session, per-tracked-agent |
| **L3b — Session-wide EM clock heartbeat** | `state/orientation_cache.md` Pinboard line directs the EM to `CronCreate` a `*/5 * * * *` recurring tick (with a first-fire date/time stamp) at session-start, unless `COORDINATOR_DISABLE_HEARTBEAT=1` | General clock-drift in long sessions where no specific incident triggers L1 or L2 | Always-on once bootstrapped |

L1 fires fastest; L2 backstops genuine idle (no events at all); L3b provides ongoing real-time injection independent of specific dispatches. The layers compose — they don't substitute.

### Bootstrap path for L3b — orientation-cache fallback, not SessionStart-stdout

L3b was originally planned as a `SessionStart` hook that emits the heartbeat-bootstrap reminder via plain stdout. The empirical platform constraint (`additionalContext` is silently dropped on `SessionStart` per `state/coordinator-improvement-queue.md` and convergent pre-flight checks; stdout reliability was unverified at plan time) drove a **pre-specified fallback** (the Staff Engineer review finding #5): bootstrap from `state/orientation_cache.md` doctrine — a Pinboard line read every session under the existing Tier 0 orientation pattern. This is the path shipped in production (Probe B was deferred under session-boundary discipline; the fallback is the production code path). The `SessionStart`-stdout path is documented as the alternative that would activate if a future session probes the read path empirically and confirms WORKS — see plan §C3b-i.

### What this does NOT add

- **No new Bash run_in_background coverage** (OOS-2 from the originating plan still holds).
- **No L3a per-dispatch `CronCreate` HARD RULE.** the Staff Engineer review dropped this layer as structurally redundant with L3b (which already surfaces per-agent elapsed times every 5 min) and as a doctrine-as-discipline antipattern (HARD RULE depending on EM memory rather than structural enforcement).
- **No reflexive kill.** Same nudge-not-kill discipline as §4 above.

### Open caveats

- **L1 throttle is per-session, not per-event.** A `PostToolUse` fire at T0 consumes the 5-min throttle for all subsequent `UserPromptSubmit`/`Stop` events too. This is intentional (matches the compaction-advisory pattern) but means a fresh dispatch crossing threshold mid-throttle is deferred up to 5 min. L2 asyncRewake-Stop is the backstop for cases where this matters.
- **L2 `asyncRewake` is platform-dependent.** The 2026-06-15 plan included a smoke probe (C0 Probe A) that was deferred to the autonomous run's natural-Stop event for empirical observation. If a future session observes `DOES-NOT-FIRE`, file a successor for L2 re-shape; L1 and L3b are independent and continue to deliver value.

---

## §8 — Hook altitude is structurally blind to async Agent dispatch bodies

<!-- spec-backlink: state/lessons.md:16 (2026-06-15) -->

**Rule:** PostToolUse-Agent fires exactly once per dispatch, at dispatch time, with `tool_response = {isAsync:true, status:"async_launched", agentId, outputFile, duration_ms:~2}`. There is NO `content` field and NO second hook event at completion. For backgrounded Agent dispatches (the dominant case per the HARD RULE in CLAUDE.md § Subagent Dispatch — `run_in_background: true` where the param is exposed, automatic on async-by-default builds), hook-altitude tripwires **cannot see the subagent's return body**.

The return body reaches the EM via `<task-notification><result>...</result></task-notification>` — a context channel, not a hook channel. Each `agentId` appears exactly once in `agent-audit.jsonl`.

**Consequence for tripwire design:** a hook that needs to scan an executor's completion body for a policy violation (e.g. "did the subagent commit when it shouldn't have?") cannot be wired as a PostToolUse hook against Agent dispatches. The only altitude with the body in view is the EM itself, reading the task-notification at resume time. Body-scanning logic belongs in `/workstream-complete` or `/parallel-code-review`, not in a hook script.

**Empirical basis:** the nudge-quota-exhausted-agent C0 substrate capture revealed this shape while verifying the runtime-tripwire wiring. The PostToolUse event for an async Agent dispatch was logged with `duration_ms: 2` — the agent had not yet run; the hook fired at the scheduling seam, not the return seam.

**Design rule for future tripwires:** when the enforcement target is a subagent's output or action, wire EM-side body inspection into the skill that resumes after the dispatch — not a PreToolUse/PostToolUse hook. Hooks are the right surface for EM tool-call intercepts; they are structurally inert for async subagent bodies.

## §9 — Sibling post-hoc observer: dispatch-shape classifier

<!-- spec-backlink: archive/specs/2026-06/2026-06-22-invariant-verification-observers.md § C3 -->

Claude-klabauter `coordinator/bin/classify-dispatch-shape.py` is a **post-hoc, read-only observer** that fires as `/workstream-complete`'s `d-classify-dispatch-shape` directive. It is NOT a runtime hook — it reads the on-disk record (the plan's `## Tasks` spine non-deferred rows / fan-out TSV row count + `dispatched-agents.txt`) after the session is complete. No live process instrumentation.

**Signal:** the plan declares N > 1 parallel-permitted chunks in a gate-group (`runs: parallel`, `gate-kind ∈ {none, output-consumption-content, contract-change}`) but only 1 distinct executor-class agentId is attributable to the session → possible serial-grind. Emits a question-framed offer to stderr; exits 0 always.

**Offer shape** (per design-as-offers doctrine in `docs/wiki/eager-agent-calibration.md`): frames the observation as a question ("was this a serial grind, or an intentional pilot-then-expand / inline-EM choice?"), names `fan-out-dispatch.py` as the reshaping alternative, and acknowledges fidelity limits (multi-plan session mixing, pilot-then-expand valid shape).

**Relationship to this tripwire:** whereas the runtime tripwire actuates on wall-clock overrun of live executor dispatches (§1), the dispatch-shape classifier actuates on post-hoc ledger analysis. Both are offer-shaped (nudge, never kill or block). Neither instrument live process state directly.

**Registration:** see `coordinator/docs/wiki/coordinator-tripwires/` for the static-grep tripwire registry entry (if added). The classifier is a post-hoc observer, not a PreToolUse/PostToolUse hook, and does not block the commit gate.

## See also

- `coordinator/docs/wiki/coordinator-tripwires/` — full tripwire registry
- `docs/wiki/dispatching-parallel-agents.md` — executor dispatch doctrine and sizing
- `docs/wiki/eager-agent-calibration.md` — design-as-offers ethos that shapes how this nudge is framed
- `em-operating-model.md` § EM clock heartbeat — L3b cadence rationale and opt-out
