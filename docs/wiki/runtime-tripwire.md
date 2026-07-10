---
title: Runtime Tripwire — Model-Aware Nudge for Long-Running Background Executors
tags: [doctrine, hooks, agent-dispatch, executor-runtime]
status: active
---

# Runtime Tripwire — Model-Aware Nudge for Long-Running Background Executors

<!-- spec-backlink: docs/plans/2026-06-08-runtime-tripwire-background-executors.md § C5 -->

## §1 — What it actuates

The 15-minute executor-runtime ceiling in `CLAUDE.md` § Subagent Dispatch HARD RULE ("Size each executor ~5-10 min on one coherent surface (15 min hard ceiling; split before dispatch)") existed as prose doctrine without an actuator. The EM had no wall-clock awareness between dispatch and completion — the ceiling was a planning heuristic enforced only by convention.

The runtime tripwire makes this ceiling **actuator-backed.** When an executor crosses its per-model threshold, the hook fires a model-aware nudge on two channels simultaneously:

- **Agent-side (primary signal):** `additionalContext` injected on the agent's own tool-result channel, naming the overrun and prescribing the wrap shape.
- **EM-side (awareness signal):** `additionalContext` on the EM's channel (same channel as completion notifications), naming the specific `agentId`, elapsed minutes, and model so the EM can act.

The empirical trigger for this work: a zombie discriminator executor ran for 15+ minutes on 2026-06-08 (logged in `docs/problems/2026-06-08-runtime-tripwire-background-executors.md`), circling past the point where wall-clock and compaction-decay made further progress unlikely. The EM had no in-session signal until the agent returned.

Modeled directly on `hooks/scripts/context-pressure-advisory.sh`. Nudge-not-kill; EM is the authority.

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

**Authoritative copy lives in `hooks/scripts/runtime-tripwire-advisory.sh` (the agent-side hook). Quoted here for human readers; if the wiki and the hook ever diverge, the hook is the source of truth.**

The wrap-shape prescription injected via `additionalContext` when an executor crosses threshold:

> RUNTIME TRIPWIRE — you've been running ~N minutes (past the ~M min runtime tripwire for {model}). Past this point, dispatches commonly enter compaction-decay — running redundant tests, looking for more things to check, oscillating between approaches. **Trust-but-verify with the EM as authority:** form your own judgment, but assume the EM will evaluate it.
>
> **Wrap shape (the default):** stop starting new work; persist any partial state to disk now; write a successor-handoff stub naming what's left; return.
>
> **If you judge yourself genuinely close to a clean return (≤2-3 min):** say so explicitly in your return so the EM can decide whether to wait.

**Autonomous-run variant:** When the EM is running autonomously, the language is softened slightly (per the `context-pressure-advisory.sh` pattern) but the nudge is NOT suppressed. The wrap shape remains the same.

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
- **EM-side: first fire + single re-nudge at +5 min, then silence.** PM disposition 2026-06-08 (post-v1 amendment to OOS). The "let's give it just a few more minutes" pattern re-creates the original P1 (EM-blind-to-clock) on the *other* side of the first nudge — so the EM-side hook fires a single re-nudge `RUNTIME_TRIPWIRE_RESTAGE_SECONDS` (default 300) after the first fire, with escalating tone naming the staleness (*"your earlier wait judgment is now 5+ minutes stale"*). After that re-nudge fires (sentinel `/tmp/runtime-tripwire-em-restage-${agentId}`), the hook is silent for that dispatch — the third decision is intervene-or-accept. No escalating ladder (avoids training the EM to ignore early pings).
- **No per-dispatch threshold ergonomics in v1.** Env-var override is global, not per-dispatch. Per-dispatch threshold negotiation is deferred to v2 if empirical evidence shows env-var-only is insufficient.
- **Max-age cap — silent skip past `RUNTIME_TRIPWIRE_MAX_TRACK_MIN` (default 90 min).** `dispatched-agents.txt` is append-only with agentId dedup, never aged out. Past 90 min — well past Opus threshold (25) + restage (5) + a generous tail — a dispatch has either completed (the common case) or hung long enough that the EM has already made a decision; either way, further nudges become noise. Empirical trigger 2026-06-09: the audit-log `agentId`-field fix (commit `c268fb0f`) left a backlog of pre-fix executors whose completion records cannot be cross-referenced; they would otherwise have lingered in the tracker for the lifetime of the EM session. The cap is also a structural backstop against any future skip-cross-ref regression. Skip is silent — no fire-log entry, no nudge.

## §6 — Calibration evidence surface

Hooks append a one-line record to `state/runtime-tripwire-fire-log.tsv` on every fire, with the shape:

```
timestamp \t agentId \t model \t elapsed_min \t fire_type
```

where `fire_type` ∈ {`agent-side`, `em-side`, `em-side-restage`}.

This log is intended for triage at `/workweek-complete` Step 3.5 — wiring TBD. Recurring miscalibration surfaces empirically: if Sonnet=12 fires constantly on legitimately-progressing dispatches, that's the trigger to recalibrate via env-var override (and eventually a default bump via a plan).

**The failure mode this defends against:** a default that fires constantly trains the EM and agents to ignore the nudge — which regresses the actuator to status-quo prose-only doctrine. The log makes systematic miscalibration visible before it reaches that failure state.

**2026-06-09 — skip-if-completed false-positive fixed.** Empirical fire-log evidence (same `agentId` re-firing as `em-side-restage` long after the agent returned, e.g. `ae4c9a965adb5095f` at 10:39 then 10:48; multiple same-batch agents at 11:57 / 12:05 / 13:59) showed the EM-side hook was nudging on already-completed dispatches — exactly the train-EM-to-ignore failure mode this section warns about. Root cause: `agent-completion-log.sh` recorded `tool_input.name` (the optional addressable-teammate name, almost never set), and the EM-check skip grepped for `"name":"$agentId"`, which never matched. Fix: log `tool_response.agentId` and skip against that. Records before 2026-06-09 lack the `agentId` field; the failure mode is invisible to back-dated analysis but is fully captured going forward.

**2026-06-09 — orphan-tail follow-up: max-age cap added.** The `agentId`-field fix landed at 16:05 UTC, but C1-C7 executors dispatched at 13:16 UTC had already completed without an `agentId` in their audit-log entries; their dispatched-agents.txt rows had no path to skip-if-completed matching. The EM observed them as "stale runaways" hours after their work landed. Added `RUNTIME_TRIPWIRE_MAX_TRACK_MIN` (default 90 min) as a structural backstop — any dispatch older than the cap is silently skipped regardless of audit-log state. This is a positive complement to the bark-once + restage row in §5: it bounds the lifetime of an entry in the tracker, so any future audit-log schema regression has a known recovery horizon instead of session-lifetime contamination.

## §7 — Layered idle-EM coverage (2026-06-15)

<!-- spec-backlink: docs/plans/2026-06-15-runtime-tripwire-idle-em-layered-fix.md -->

The v1 wiring fired only on `PostToolUse`. Empirical evidence on 2026-06-15 (handoff `state/handoffs/2026-06-15_111753_runtime-tripwire-not-firing-on-20min-executor.md`) showed an EM in active PM conversation with a 20-min Sonnet executor in flight got no nudge for the entire dispatch window — the trigger surface was structurally silent in the exact case the tripwire was built for. The fix is layered coverage, each layer addressing a distinct failure shape:

| Layer | Trigger surface | Failure shape covered | Always-on? |
|---|---|---|---|
| **L1 — Activity wiring** | `PostToolUse` + `UserPromptSubmit` + `Stop` (all three fire `runtime-tripwire-em-check.sh`) | EM in active conversation with PM (no tool calls between dispatches) | Per-tracked-agent (driven by `dispatched-agents.txt`) |
| **L2 — asyncRewake-on-Stop watcher** | `Stop` event spawns `runtime-tripwire-stop-watcher.sh` as `asyncRewake: true` (parent exits 0; bg subprocess sleeps to threshold, emits stderr nudge, exits 2 → platform re-wakes EM with `<system-reminder>`) | Genuinely-idle EM: dispatches then sits silent (no PM turns at all) | Single PID-locked watcher per session, per-tracked-agent |
| **L3b — Session-wide EM clock heartbeat** | `state/orientation_cache.md` Pinboard line directs the EM to `CronCreate` a `*/5 * * * *` recurring tick (with a first-fire date/time stamp) at session-start, unless `COORDINATOR_DISABLE_HEARTBEAT=1` | General clock-drift in long sessions where no specific incident triggers L1 or L2 | Always-on once bootstrapped |

L1 fires fastest; L2 backstops genuine idle (no events at all); L3b provides ongoing real-time injection independent of specific dispatches. The layers compose — they don't substitute.

### Bootstrap path for L3b — orientation-cache fallback, not SessionStart-stdout

L3b was originally planned as a `SessionStart` hook that emits the heartbeat-bootstrap reminder via plain stdout. The empirical platform constraint (`additionalContext` is silently dropped on `SessionStart` per `state/coordinator-improvement-queue.md` and convergent pre-flight checks; stdout reliability was unverified at plan time) drove a **pre-specified fallback** (the Staff Engineer review finding #5): bootstrap from `state/orientation_cache.md` doctrine — a Pinboard line read every session under the existing Tier 0 orientation pattern. This is the path shipped in the autonomous run of 2026-06-15 (Probe B was deferred under session-boundary discipline; the fallback is the production code path). The `SessionStart`-stdout path is documented as the alternative that would activate if a future session probes the read path empirically and confirms WORKS — see plan §C3b-i.

### What this does NOT add

- **No new Bash run_in_background coverage** (OOS-2 from the 2026-06-08 plan still holds).
- **No L3a per-dispatch `CronCreate` HARD RULE.** the Staff Engineer review dropped this layer as structurally redundant with L3b (which already surfaces per-agent elapsed times every 5 min) and as a doctrine-as-discipline antipattern (HARD RULE depending on EM memory rather than structural enforcement).
- **No reflexive kill.** Same nudge-not-kill discipline as §4 above.

### Open caveats

- **L1 throttle is per-session, not per-event.** A `PostToolUse` fire at T0 consumes the 5-min throttle for all subsequent `UserPromptSubmit`/`Stop` events too. This is intentional (matches the `context-pressure-advisory.sh` pattern) but means a fresh dispatch crossing threshold mid-throttle is deferred up to 5 min. L2 asyncRewake-Stop is the backstop for cases where this matters.
- **L2 `asyncRewake` is platform-dependent.** The 2026-06-15 plan included a smoke probe (C0 Probe A) that was deferred to the autonomous run's natural-Stop event for empirical observation. If a future session observes `DOES-NOT-FIRE`, file a successor for L2 re-shape; L1 and L3b are independent and continue to deliver value.

---

## §8 — Hook altitude is structurally blind to async Agent dispatch bodies

<!-- spec-backlink: state/lessons.md:16 (2026-06-15) -->

**Rule:** PostToolUse-Agent fires exactly once per dispatch, at dispatch time, with `tool_response = {isAsync:true, status:"async_launched", agentId, outputFile, duration_ms:~2}`. There is NO `content` field and NO second hook event at completion. For backgrounded Agent dispatches (the dominant case per the HARD RULE in CLAUDE.md § Subagent Dispatch — `run_in_background: true` where the param is exposed, automatic on async-by-default builds), hook-altitude tripwires **cannot see the subagent's return body**.

The return body reaches the EM via `<task-notification><result>...</result></task-notification>` — a context channel, not a hook channel. Each `agentId` appears exactly once in `agent-audit.jsonl`.

**Consequence for tripwire design:** a hook that needs to scan an executor's completion body for a policy violation (e.g. "did the subagent commit when it shouldn't have?") cannot be wired as a PostToolUse hook against Agent dispatches. The only altitude with the body in view is the EM itself, reading the task-notification at resume time. Body-scanning logic belongs in `/workstream-complete` or `/parallel-code-review`, not in a hook script.

**Empirical basis (2026-06-15):** the nudge-quota-exhausted-agent C0 substrate capture revealed this shape while verifying the runtime-tripwire wiring. The PostToolUse event for an async Agent dispatch was logged with `duration_ms: 2` — the agent had not yet run; the hook fired at the scheduling seam, not the return seam.

**Design rule for future tripwires:** when the enforcement target is a subagent's output or action, wire EM-side body inspection into the skill that resumes after the dispatch — not a PreToolUse/PostToolUse hook. Hooks are the right surface for EM tool-call intercepts; they are structurally inert for async subagent bodies.

## §9 — Sibling post-hoc observer: dispatch-shape classifier

<!-- spec-backlink: archive/specs/2026-06/2026-06-22-invariant-verification-observers.md § C3 -->

`bin/classify-dispatch-shape.sh` is a **post-hoc, read-only observer** that fires at `/workstream-complete` Step 2.9b. It is NOT a runtime hook — it reads the on-disk record (plan Dispatch Ledger + `dispatched-agents.txt`) after the session is complete. No live process instrumentation.

**Signal:** the plan declares N > 1 parallel-permitted chunks in a gate-group (`runs: parallel`, `gate-kind ∈ {none, output-consumption-content, contract-change}`) but only 1 distinct executor-class agentId is attributable to the session → possible serial-grind. Emits a question-framed offer to stderr; exits 0 always.

**Offer shape** (per design-as-offers doctrine in `docs/wiki/eager-agent-calibration.md`): frames the observation as a question ("was this a serial grind, or an intentional pilot-then-expand / inline-EM choice?"), names the `fan-out-dispatch.sh` as the reshaping alternative, and acknowledges fidelity limits (multi-plan session mixing, pilot-then-expand valid shape).

**Relationship to this tripwire:** whereas the runtime tripwire actuates on wall-clock overrun of live executor dispatches (§1), the dispatch-shape classifier actuates on post-hoc ledger analysis. Both are offer-shaped (nudge, never kill or block). Neither instrument live process state directly.

**Registration:** see `docs/wiki/coordinator-tripwires.md` for the static-grep tripwire registry entry (if added). The classifier is a post-hoc observer, not a PreToolUse/PostToolUse hook, and does not block the commit gate.

## See also

- `docs/wiki/coordinator-tripwires.md` — full tripwire registry
- `docs/wiki/dispatching-parallel-agents.md` — executor dispatch doctrine and sizing
- `docs/wiki/eager-agent-calibration.md` — design-as-offers ethos that shapes how this nudge is framed
- `plugins/coordinator/em-operating-model.md` § EM clock heartbeat — L3b cadence rationale and opt-out
