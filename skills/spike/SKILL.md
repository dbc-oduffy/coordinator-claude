---
name: spike
description: "Bounded spike: web research plus local study to a verdict."
version: 1.0.0
triggers:
  - /spike
  - spike <mechanism>
  - prove this works
  - derisk the mechanism
argument-hint: "<mechanism-or-question>"
---

# /spike — Mechanism-Derisking Investigation

Prove — or disprove — that a specific mechanism is viable before a plan commits to it. Binary,
same shape as `/dogfood`: converges to a viable/not-viable verdict, or switches gears — no
open-ended "keep researching" path (that's `coordinator:research`).

spike is the research door's verdict class (`coordinator/commands/research.md`).

Siblings: `coordinator:research` is broad, non-binary, and runs no code on this machine.
`coordinator:systematic-debugging` is backward-looking (why did one known thing break).
`coordinator:dogfood` is fix-through on a thing already built. `coordinator:shape` is
problem-shaping (what to build), not mechanism-proving (can we build it this way).

**Announce at start:** "Running `/spike <mechanism>` — bounded derisking investigation. Binary
outcome: viable or not-viable."

## Invoke Gating — Structural, Not Self-Classified

One invocation surface, two entry paths — the gate is a structural signal, never a runtime
self-classification:

- **Research-door entry (default).** The PM says 'spike', or the EM sizes
  `research.value_class: spike`. The EM's sizing is the authority
  (`A-RESEARCH-RUNS-ON-THE-EMS-SIZING-NEVER-A-PM-GATE`). A bare `/spike <mechanism>` with no structural
  signal present is ALWAYS this variant.
- **Plan-trampoline.** EM-reachable, no PM round-trip — only when `coordinator:plan` Branch B
  substrate verification carries an explicit `trampoline: true`-style signal on an unproven
  mechanism gate (`coordinator/skills/plan/SKILL.md`, the eighth verification dimension). Absence
  of that signal is dispositive — never infer the trampoline path from context.

## Both Halves Required

1. **External web research** — how others solve this, what official docs say, known pitfalls.
   Scoped to this mechanism.
2. **Local empirical study** — install the dependency, run the probe, measure. The half
   `coordinator:research` structurally cannot do.

A web-only investigation is `/research` wearing a spike costume — dispatch research instead, or
finish the empirical half before declaring a verdict.

## Probes Are Throwaway

Probe scripts are derisking scaffolding — discarded once the measurement is taken and the verdict
recorded. Never commit them to the persistent test suite; that is the plan's own tests' job once
drafted around a proven mechanism.

## Durable Output — the Verdict Record

Write to `docs/research/spike-verdicts/YYYY-MM-DD-<mechanism-slug>.md`, validated against
`spike-result.schema.json`. No `state/handoffs/` lifecycle fields (no `status`,
`deployment_state`, `pickup_ready`) — a verdict record is evidence, not a baton.

Carries: research findings, empirical measurements, binary verdict (`viable`/`not-viable`),
`gated_route` (the downstream plan/chunk/decision this verdict gates, when reached via the
trampoline), `discharged_by` (required and non-null whenever `gated_route` is a non-empty
string).

**No live routing intent may leave the session unlanded.** If `gated_route` names a downstream
target, write that intent onto the real target before the session ends — the plan the spike
gates, an existing baton already carrying the work, or a PM-facing surface for a
`coordinator:shape`-reached verdict — and name it in `discharged_by`. The schema rejects a
non-empty `gated_route` paired with a null `discharged_by`.

**A spike carried as plan rows owes no verdict record.** Tripwire: `A-SPIKE-CARRIED-AS-PLAN-ROWS-OWES-NO-VERDICT-RECORD`.

## Exit Routing — the Verdict Routes It

| Verdict | Route |
|---|---|
| **viable** | → `coordinator:plan` (fresh, authored around the now-proven mechanism), OR resume the trampolined plan — Branch B re-enters with the eighth dimension GREEN off the verdict record, not a full seven-dimension re-run |
| **not-viable** | → `coordinator:shape` / PM — picking a different mechanism is a problem-shaping question, not a spike question |

Not an EM judgment call once the verdict lands — the verdict is the router. This wiring is the
**plan⇄spike back-edge**: `coordinator:plan` Branch B trampolines into a spike on an unproven
mechanism gate, and this skill's viable-verdict exit resumes that trampolined plan. Both verdict
rows and the `plan⇄spike back-edge` phrase must stay grep-assertable from this file and
`plan/SKILL.md`.

## `coordinator:spike` vs. `scope_mode: spike`

Complementary, not colliding. `scope_mode: spike` is a plan-header enum describing a *plan's own*
discovery mode. `coordinator:spike` is a distinct upstream *invocation* that runs before a plan
exists and produces a verdict record gating whether/how one gets drafted.

## Destructive-Action Prohibition

`/spike` writes files (probes, the verdict record) and can run multi-pass autonomously. No
exceptions, not proposed, not authorization-requested mid-run: `rm -rf`, `git reset --hard`,
`git push --force`, `git rebase`, deleting outside the spike's own scratch/probe directory, `gh
pr merge`, `--no-verify`/`--no-gpg-sign`, hibernate/shutdown/power-off, killing other processes.

## Out of Scope

Retrofitting historical spikes into verdict records. Editing the `/research` or `/dogfood` skill
bodies. A generic pipeline-graph engine — the shape→spike→plan edges are wired point-to-point. A
central gating-registry file. A new `deployment_state` enum value for the trampoline path. A new
primary manifest docType beyond the verdict-record schema. Discovery-surface registration
(`/workstream-start`, pipeline-graph cross-refs) is a separate concern.
