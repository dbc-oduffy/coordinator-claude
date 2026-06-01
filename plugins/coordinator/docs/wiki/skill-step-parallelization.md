# Skill Step Parallelization — Gates vs. Todo-Lists

> Numbered steps inside a skill body are NOT all gates. Many are colocated by topic, touching disjoint surfaces with no inter-step data dependency. Execute those in any order, and batch parallel tool calls where two are independent disk reads/writes against different paths.

## The failure mode this exists to prevent

Skills look like checklists, and the coordinator doctrine ("follow skills like a pilot follows a checklist") rewards careful linear walking. But pilots don't actually walk checklists linearly when the items are independent — they batch. Treating every numbered step as a gate costs:

- **Wall-clock latency** — 5-15 minutes per long-skill invocation, especially on `/handoff`, `/workstream-complete`, `/update-docs`, `/workday-start`.
- **PM patience** — the EM idling on Step N before doing Step N+1 when N+1 doesn't read N's output.
- **Context-pressure pain** — `/handoff` and `/workstream-complete` fire when context is most constrained, which is exactly when serialization hurts most.

The PM observation that prompted this convention (2026-05-20, mid-`/workweek-complete`): *"Claude, can we accelerate the rest of this please? I don't think we need to be so precious about this process."*

## The two-section convention

Skills authored or refactored under this convention surface an `## Execution Shape` block near the top of the body, naming:

1. **Sequential gates** — the small set of step→step edges that are real (Step N consumes Step M's file/value/decision). 1-5 gates is typical; rarely more.
2. **Todo-list cluster** — colocated steps with no inter-edges. Execute in any order, batch parallel tool calls where independent.

Doctrine-load-bearing linearity stays sequential — PM gates, reviewer HARD-RULE sequencing, state mutations that must commit before the next step reads them. The convention identifies what's *not* in that category.

## What counts as a true edge

A step→step edge is *true* when:

- Step N reads a file Step M just wrote (e.g., commit step reads `scope:` block written by handoff-author step).
- Step N's behavior changes based on Step M's verdict (e.g., trigger gate decides whether the skill body runs at all).
- Step N's output must be staged in Step M's commit (e.g., reviewer-integrator's edits must be in the final commit).

False edges (don't treat as gates):

- Two steps touch the same topic ("doc updates", "archive operations") but write disjoint files. Colocation by theme is NOT data dependency.
- A "commit at end" convention. The commit is one step; the *order* of file edits feeding it is unconstrained.
- A `pre-commit lint then commit` pattern where the lint output isn't read by the commit. The commit doesn't gate on the lint result — it just happens after by convention.

## Identifying the todo-list in an arbitrary skill

For each numbered step, answer:

- **Does this step's output get read by any later step?** If no → it's a todo-list item.
- **Does this step's verdict change any later step's behavior?** If no → todo-list item.
- **Is this step's file edit staged in a later commit?** If yes, it has a *fan-in* relationship to the commit — but not a sequential ordering relative to peer file edits. Multiple peer steps can fan in to one commit.

The dominant pattern in coordinator skills is the **post-integration cleanup cluster** — after the work has happened, 4-6 housekeeping steps update independent surfaces (lessons, plan docs, archive entries, orientation cache, project tracker). These all fan in to a final commit but don't sequence relative to each other.

## When you encounter a skill without an `## Execution Shape` block

Scan the numbered steps before walking them. Two-minute exercise:

1. List the steps.
2. For each, name what it READS and what it WRITES.
3. Cross-reference: any READ matched against a peer's WRITE is an edge.
4. The remainder is the todo-list.

If the analysis reveals substantial parallelism currently treated as sequential, **file a queue entry** (`tasks/improvement-queue.md` or `~/.claude/tasks/coordinator-improvement-queue.md` for cross-repo patterns) proposing the `## Execution Shape` refactor on that skill.

## Reference: skills currently with explicit Execution Shape

Don't maintain a static list — it decays. Enumerate live with grep:

```bash
grep -rl '## Execution Shape' plugins/coordinator/skills/
```

Same canonical answer at any point in time, no maintenance.

## Discoverability — this convention governs EM skill-execution, not subagent dispatch

*2026-05-21, claude-central.* The pointer to this convention in `coordinator/CLAUDE.md` landed under § Subagent Dispatch, but the convention governs **EM skill-execution behavior** — how the EM walks the numbered steps of a skill it is running itself — not how it dispatches subagents. The mis-filing is a discoverability hazard: an EM scanning for "how do I run this skill's steps efficiently" won't look under a subagent-dispatch heading. The convention's natural home is a § Core Principles or a dedicated § Skill Execution surface. (The CLAUDE.md re-home is gated on the 39900-byte hard limit's next trim window; this note records the intent so the re-home lands when the window opens.)

## Target-Selection-Discipline — Mine Empirical Usage Frequency Before Choosing Refactor Targets

*2026-05-21, claude-central.* When selecting which surfaces to refactor, parallelize, or extract, a-priori target selection ("these look like the hot ones") systematically mis-ranks. Mine the empirical usage frequency first: dispatch a `git log` + archive-count scout per candidate, and **rank by frequency × per-fire savings**, not by intuition about which surface "feels" central. A surface that fires rarely but is expensive per-fire can outrank a frequently-touched but cheap one — and the product is invisible without the count.

**Procedure:** (1) enumerate candidate surfaces; (2) per candidate, count invocations across `git log` history and archived sessions (the count is the *frequency* term); (3) estimate per-fire savings of the refactor (the *magnitude* term); (4) rank by the product; (5) refactor top-ranked first. This is the target-selection analog of the per-executor budget axis — the same "measure before you cut" discipline applied to *which* surface rather than *how big* the chunk. Composes with `agent-dispatch-economics.md` § Cluster Execution: once the ranking picks the novel item, the cluster pattern handles the surgical follow-ups.

## Spec backlink

Empirical survey + decision: `tasks/skill-step-survey/` (commands.md, skills-a.md, skills-b.md, usage-frequency.md). Spinoff: `tasks/handoffs/2026-05-20_231841_skill-step-gates-vs-todo-list.md`.
