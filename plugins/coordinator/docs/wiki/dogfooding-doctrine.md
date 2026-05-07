---
title: Dogfooding Doctrine
kind: doctrine
created: 2026-05-07
status: active
related:
  - plugins/coordinator-claude/coordinator/skills/dogfood/SKILL.md
  - docs/plans/2026-05-07-dogfood-super-skill.md
  - tasks/dogfood-prior-art/holodeck-insights-report.md
  - tasks/dogfood-prior-art/dronesim-shakedown-report.md
---

# Dogfooding Doctrine

<!-- spec backlink: docs/plans/2026-05-07-dogfood-super-skill.md -->

## What Dogfooding Is — Binary Outcome Rule

**Dogfooding means using a newly-built thing to see whether it actually works.** The canonical targets: a new skill, an install process, a pipeline, a script, a suite of commands you just shipped.

The outcome is binary. No third path:

- Either an observation is a bug → **fix it now, in this session, on this branch.**
- Or the observations reveal the thing is fundamentally wrong-shape → **switch gears: stop the loop, enter replan/refactor.**
- **Never** "log to known-bugs and keep going." That is file-and-defer wearing a dogfood costume.

This is distinct from its siblings in the coordinator workflow:

| Skill | Work source | Fix scope |
|-------|-------------|-----------|
| `/dogfood` | Invokes a new thing; exercises it until it works or gets replanned | Whatever the smoke surface reveals |
| `/bug-blitz` | Works `tasks/bug-backlog.md` (pre-existing known bugs) | Scoped per backlog item |
| `/bug-sweep` | Searches the repo for AI-fixable bugs | Codebase-wide |

The critical distinction: a dogfood session is invocation-driven and fix-through by default. A bug-blitz is backlog-driven and item-scoped. They do not compose via remainder hand-off — `/dogfood` does not file remainder to the backlog.

## Three Tiers Explained

The tier controls scope and budget. PM declares at invocation.

### `--narrow` — Single Surface

One install, one command, one happy-path sequence. "Does it work?" Tight budget. No mid-loop PM check-in unless the surface explodes into unexpected complexity.

**Example:** Running `holodeck:setup` for the first time after shipping the plugin. The narrow pass checks: does install succeed? Does the post-install smoke probe pass? That's it — multi-surface coverage is out of scope.

### `--broad` — Multi-Surface Happy Path

End-to-end flow across multiple commands/skills/agents. Larger budget. Auto-handoffs survive compaction across sessions.

**Example:** After shipping a new set of coordinator commands, a broad pass exercises: `/session-start`, a plan dispatch, an executor dispatch, and `/session-end`. Each surface gets narrow treatment; the broad tier covers the connective tissue between them.

### `--shakedown` — Comprehensive Coverage Matrix

Every declared tool/surface/path exercised once with realistic input. Requires a PM-declared coverage matrix at invocation (persisted to `tasks/dogfood-<target>-<date>/coverage-matrix.md`). Without a declared matrix, `--shakedown` degrades to `--broad`.

**Example:** project-rag dogfooded on its own repo — every RAG tool (symbol search, semantic search, referencers, subsystem profile) exercised against real code, with a pre-declared matrix confirming each tool's exercise.

Shakedown is a *kind* of dogfood, not a separate activity. It composes inward: shakedown of a multi-tool surface = broad dogfood across each tool's narrow surface, with a coverage-matrix overlay.

## The File-and-Defer Trap

<!-- negative-spec: empirical source at tasks/dogfood-prior-art/holodeck-insights-report.md; citation below -->

The holodeck install dogfood session (2026-05-07) revealed the trap with precision. The session's strongest finding, quoted from `tasks/dogfood-prior-art/holodeck-insights-report.md`:

> "The pull toward file-and-defer came from handoff scope language, not EM behavior — phrases like 'do not expand scope, single goal, smoke verification only' accidentally invite defer-posture when bugs surface."

When the EM opened the session from a handoff that said "smoke verification only," the framing nudged toward treating every bug as out-of-scope. The bugs were real, in-cone, and fixable — but the inherited language made filing them feel like the correct move.

**Pre-Flight Gate 3 (Framing Audit) exists to break this trap before entering the loop.** When scope language from a handoff or inherited context invites verification-only posture, the EM surfaces it to PM explicitly and forces confirmation of fix-through posture before proceeding. This gate is hardcoded — it runs first, every invocation, including autonomous runs.

## Self-Dogfood-First Doctrine

<!-- source: tasks/dogfood-prior-art/dronesim-shakedown-report.md §5 -->

The DroneSim shakedown report (`tasks/dogfood-prior-art/dronesim-shakedown-report.md`, §5) quantified the cost of inverting the default: approximately **67% of the bugs the consumer team absorbed should have surfaced on the producer side first via self-dogfood**.

The DroneSim case is the canonical inverted shape: cross-repo consumer team (DroneSim) dogfooding a sibling dependency (project-rag) before the producer had dogfooded itself. The consumer absorbed bugs the producer should have fixed before shipping. Multi-cycle, release-gated, expensive.

**Self-dogfood-first doctrine:**

1. When a thing is built in repo X, the canonical first dogfood invocation is `/dogfood` *in repo X*.
2. Cross-repo dogfood is a deliberate follow-up after self-dogfood converges — not a substitute.
3. When `/dogfood` is invoked with a target from a different repo, the skill's first action is to surface the self-dogfood-first default and require PM acknowledgment.

This is a soft check (prompt-level), not a hard enforcement gate. The `/workweek-complete` cross-repo dogfood audit (Step 7) detects drift: any cross-repo `/dogfood` invocation during the week is checked for a preceding self-dogfood pass. Drift detected in that audit routes to `tasks/lessons.md`.

## Cone Classification — In-Cone / Out-of-Cone / Surface-and-Skip

Every observation during the loop must be explicitly classified. The classification determines the action; it is mandatory and logged.

### In-Cone — Fix-Now

The default. Mechanical fixes are in-scope by definition because the dogfood IS the test:

- Validator gaps, missing fallbacks, false-success exits, off-by-one errors
- Missing flag handling, idempotency gaps
- **The skill/script/pipeline body itself** — if dogfooding a new skill and the skill has a bug, fixing the skill is the whole point
- Doctrine and wiki files the target depends on, when the smoke trips them

In-cone is the default: the question is "is there a real reason this isn't fix-now?" — not "do I have permission to fix this?"

**Worked example — holodeck commit `e35c6551`.** During the holodeck install dogfood, the install script's post-install probe returned a false success exit while stderr carried a warning about a missing probe. Classification: in-cone (emission-side false positive, structural fix required). Fix: capture in-process probe truth at decision time; emit one consistent signal. Smoke evidence in commit body: "probe now returns exit 1 on missing probe; prior pass exit 0 + stderr WARNING confirmed false success pattern."

**Worked example — holodeck commit `ab951c2a`.** Subsequent pass surfaced that the status file claimed "ready" while the downstream consumer (holodeck-doctor probe 14) reported not-found. Classification: in-cone (cross-channel contradiction). Fix: status file now written only after downstream readiness probe fires. Smoke evidence in commit body: "pass N-1 status=ready + probe=not-found; pass N status written post-probe, probe fires clean."

### Out-of-Cone — Switch-Gears

When the bug requires architectural rework that the plan author should re-do. Three signals:

- ≥3 distinct failures attributable to the same architectural shape decision (the shape is the bug)
- Fixing would require reversing a load-bearing structural choice in the thing being dogfooded
- The `pass-<N>-modes.json` tuple count hits ≥3–4 distinct `{component, error-class}` entries in one pass

On out-of-cone classification, loop ends on PM confirm. The dogfood session's output is the replan ask, not a converged thing.

### Surface-and-Skip

Reserved for genuinely external scope: PM-level product decisions, externalities (PRs, signing, network dependencies), or architectural rework that is out-of-cone. **Surface-and-skip is the rare exception, not the conservative move.**

Each instance requires a structured entry:
```json
{ "category": "pm-product | externality | architectural-rework", "evidence": "<link-or-pointer>" }
```

Entries land in `tasks/dogfood-<target>-<date>/surface-and-skip.md`, **not** `tasks/bug-backlog.md`. Skip-ratio threshold: >40% over the session, or >2 consecutive skips without an interleaved fix-now, triggers "is this dogfood the wrong shape?" surface to PM.

## Switch-Gears Triggers

Switch-gears is a judgment call, but two empirical signals are well-grounded.

### Failure-Mode Shift Threshold

When a single iteration surfaces ≥3–4 distinct failure *modes* (not bugs — modes: same component, same error class), the loop has transitioned from "verify a fix" to "discover-more-bugs." The per-iteration `pass-<N>-modes.json` makes this mechanical: count tuples.

**DroneSim inflection point:** "Retries 1–3 each surfaced a different bug; retry 4 surfaced two more" — this is the empirical inflection that defines the threshold. Retries 1–3 are normal fix-through. When retry 4 brings two new modes on top of the prior three, the session has entered discovery mode. That's out-of-cone for a fix-through loop.

### Same Seam, Different Bugs

≥3 distinct failures attributable to the same architectural shape decision means the shape is the bug. No fix count will converge the session; the right action is out-of-cone classification and a replan ask.

**Example:** Three separate passes each surface a different failure in the same hook script — exit-code mismatch, path resolution error, env-var not propagated. All three trace to the hook receiving state late in the pipeline rather than at the point of truth. The seam is wrong; patching callers will not converge.

## Worked Examples — Holodeck Commits

Both commits below demonstrate the canonical fix-through shape: smoke invocation → cross-channel contradiction surfaced → structural fix → smoke evidence in commit body.

**`e35c6551`** (holodeck install dogfood, pass 2):

The install script exited 0 and wrote `status: ready` while stderr carried `WARNING: plugin-index probe returned not-found`. Cone: in-cone (emission-side false positive). Fix: probe truth captured in-process before status file is written; status file writes only on probe success. Commit body: "pass 1 exit=0 + status=ready + stderr WARNING; pass 2 exit=1 on missing probe, probe-fires-then-status-writes, exit=0 clean." This is the canonical cross-channel observation shape.

**`ab951c2a`** (holodeck install dogfood, pass 3):

Fix from `e35c6551` revealed a downstream consumer (holodeck-doctor probe 14) was reading the status file before the probe had propagated. Cone: in-cone (same emission surface, different channel gap). Fix: status file gated on readiness probe firing from the consumer's perspective, not just the producer's write. Commit body: "pass 2 status=ready + probe 14=not-found; pass 3 probe fires clean before status written, probe 14 reports ready."

These two commits are the DroneSim report's "three bugs surfaced in strict sequence" pattern, rendered on the holodeck surface: each bug was invisible until the shallower one was fixed.

## How This Doctrine Was Built

Two prior-art reports inform this doctrine, both at `~/.claude/tasks/dogfood-prior-art/`:

- **`holodeck-insights-report.md`** — retrospective from a 2026-05-07 self-dogfood session on the holodeck install/setup pipeline. Strongest finding: the file-and-defer pull came from inherited handoff language, not EM behavior. This is the canonical self-dogfood shape (fix-through, converged).

- **`dronesim-shakedown-report.md`** — five-cycle shakedown campaign of project-rag by the DroneSim consumer team. Strongest finding: ~67% of bugs absorbed by the consumer were reachable from the producer's machine via self-dogfood. This is the canonical inverted shape (cross-repo before self-dogfood, multi-cycle, expensive).

The two cases are complementary: holodeck is the right shape; DroneSim is the cautionary inversion. Doctrine calibrates against both.
