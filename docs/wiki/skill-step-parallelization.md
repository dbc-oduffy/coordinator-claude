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

A step→step edge is *true* when one of these holds:

- **Disk-mediated value passing.** Step N reads from disk a value / file / decision that Step M just wrote (e.g., commit step reads `scope:` block written by handoff-author step).
- **Behavior change on verdict.** Step N's behavior changes if Step M's output differs (e.g., trigger gate decides whether the skill body runs at all).
- **Doctrine-encoded sequencing.** PM gates and reviewer HARD-RULE sequencing count as REAL edges — **the doctrine itself IS the data dependency**, even when no file is read. Examples: "PM authorizes /spinoff before fork" or "reviewer 1 lands before reviewer 2 dispatches" are edges even though no on-disk artifact passes between them.

**Parallelizable**, conversely, means **file-overlap empty AND no inter-step value passing in prose AND no doctrine-encoded ordering.** All three must hold.

False edges (do NOT treat as gates):

- Two steps touch the same topic ("doc updates", "archive operations") but write disjoint files. **Colocation by theme is not data dependency.**
- A "commit at end" convention. The commit is one step; the *order* of file edits feeding it is unconstrained. Soft conventions like this are not edges.
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

If the analysis reveals substantial parallelism currently treated as sequential, **file a queue entry** (`state/improvement-queue/` for project-local, or the central queue in example-orchestration-hub (`$(coordinator_state_root --central)/improvement-queue/` — see `state-placement-law.md`) via `coordinator-queue-append --schema improvement-queue --queue-scope central` for cross-repo patterns) proposing the `## Execution Shape` refactor on that skill.

## Reference: skills currently with explicit Execution Shape

Don't maintain a static list — it decays. Enumerate live with grep:

```bash
grep -rl '## Execution Shape' plugins/coordinator/skills/
```

Same canonical answer at any point in time, no maintenance.

## Discoverability — this convention governs EM skill-execution, not subagent dispatch

*2026-05-21, claude-central.* The pointer to this convention in `coordinator/CLAUDE.md` landed under § Subagent Dispatch, but the convention governs **EM skill-execution behavior** — how the EM walks the numbered steps of a skill it is running itself — not how it dispatches subagents. The mis-filing is a discoverability hazard: an EM scanning for "how do I run this skill's steps efficiently" won't look under a subagent-dispatch heading. The convention's natural home is a § Core Principles or a dedicated § Skill Execution surface. (The CLAUDE.md re-home is gated on the 39900-byte hard limit's next trim window; this note records the intent so the re-home lands when the window opens.)

## Orchestrator-class skills — ceiling is a class question, not a byte question

*2026-06-04, claude-central.* The 500-line skill ceiling was research-validated on **prose** skills (`coordinator:plan`, `coordinator:review`, `coordinator:brainstorming` shape). Orchestrator-class skills — `/handoff`, `/workstream-complete`, `/workday-complete`, `/workweek-complete`, `/architecture-audit`, `/merge-to-main` — are a different artifact: gate maps, recovery branches, frontmatter mutation routines, archival sweeps. The 2026-06-04 audit found a bimodal distribution: 8 orchestrators clustered near the 500-line ceiling, 1 breached at 520. That signal says the invariant is wrong for this class, not that 8 skills need byte-shuffling.

Three structural directions are on the table (PM decision pending):

1. **Tier the ceiling.** Orchestrators get a 700-line budget; prose stays at 500. Cheapest; preserves single-file readability for the gate-walking EM.
2. **ASIC the orchestration.** Move multi-step gates + archival sweeps + frontmatter mutations into `bin/` shell helpers; SKILL.md collapses to judgment-bearing one-liners that invoke helpers. Aligns with the "single-thread / non-resumable / non-idempotent are antipatterns" doctrine — helpers can become resumable and unit-testable in ways markdown can't.
3. **Conditional inclusion by `project_type`.** Load domain-specific procedure blocks at session time based on `coordinator.local.md`. Precedent: `architecture-audit/SKILL.md` `project_subtypes`-conditional pattern.

**EM preference is Option 2** (ASIC) — strongest alignment with existing doctrine, and the shell helpers become substrate the runtime-tripwire and `bin/fan-out-dispatch.sh` already pattern. But the decision is PM-gated; do not unilaterally start extracting orchestrator bodies before authorization.

**Until the decision lands, the operative rule for orchestrators is:** the 500-line hook may emit a one-line nag, but a breach is NOT a fight-the-hook trigger — file a queue entry naming the orchestrator, and surface to `/workweek-complete` triage. Prose-skill breaches still get split immediately.

**wsc wiring rule (post-ASIC).** New `workstream-complete` subsystems add a `bin/wsc-<name>.sh` script + a one-line invocation in the skill — never ~20 lines of inline prose+bash. The skill is a dispatcher of one-liners; inline mechanism is the rebound vector the two prior trims (76b276dad; 2026-06-15 ceremony-calibration) failed to hold against. `bin/check-wsc-inline-budget.sh` WARNs at `/workweek-complete` when inline bash-block count drifts above baseline.

## Survey results — skills A-F (10 skills)

*2026-05-21, claude-central.* Empirical survey of skills A through F surfaced the following partition:

- **Linear-by-design (6):** `brainstorming`, `consolidate-git`, `dogfood`, `enrich-and-review`, `execute-plan`, `finishing-a-development-branch`. Steps form a real chain — no parallelization opportunity.
- **Recoverable tail-parallelism (4):**
  - `architecture-rotation` — Step 4 → {5, 6.5, 6.75} fan-out on independent files. **Largest single opportunity: 5-15 min/audit.**
  - `bug-sweep` — Phase 4 commits split into 3 serial waves; waves themselves don't fan out as written.
  - `code-health` — Step 4 → {5, 6} touch independent files.
  - `debt-triage` — Steps {0, 1, 1b, 1c, 3b} are 5 independent read-only surfaces serialized for no reason.

Crucially, **no skill has a FALSE hard dependency to remove** — all savings come from running already-independent steps concurrently, not from rewriting data flow. The pattern across the 4 winners: the *tail* of the skill (post-judgment work — commits, file updates, archival) is what parallelizes, not the head (gate evaluation).

## Survey results — skills G-Z (16 skills) — top worst-offenders

*2026-05-21, claude-central.* The G-Z half of the survey identified three high-yield refactor targets:

1. **`handoff`** — Steps 2 / 2.5 / 2.6 / 2.7 / 2.8 / 2.9 / 2.10 read and write disjoint surfaces (`tasks/lessons.md`, plan files, `archive/completed/`, orientation cache pinboard, review trail). Only Step 1 → Step 3 is a true edge. Wave-parallelizing reclaims wall-clock under context pressure — which is *exactly when* `/handoff` fires. **5-15 min savings per fire.**
2. **`session-end` / `workstream-complete`** — Mirror of `handoff`; same surface-disjoint shape. **5-15 min per fire.**
3. **`merging-to-main`** — Step 1.5 three Parts surface-disjoint; demo-path doesn't consume ship-verdict. Step 1.6 UE check has 4 independent rows. **2-5 min per fire.**

These three plus `architecture-rotation` (from the A-F survey) are the top-priority refactor queue.

## Already-parallel skills (reference — do not "fix")

The survey confirmed the following are already running parallel where they should:

- `parallel-code-review` (the entire skill's purpose)
- `review` / `review-code` A.1 — three pre-flight checks (prior-art / docs-checker / plan-coverage) explicitly independent
- `session-start` Context Load — 10 checks explicitly marked independent
- `staff-session` Step 6 — team-spawn batched in a single message

Do not "improve" these — they're the reference shape.

## Doctrinally linear skills (do NOT parallelize)

Five skills are sequentially correct by doctrine and would BREAK if parallelized:

- `roadmap-planning` — PM gates + sequential-review HARD RULE.
- `learn-lessons` — central-before-strip-local, apply-before-queue-append.
- `spinoff` — atomic flow (one PM-authorized fork).
- `validate` — single bash invocation (no steps to parallelize).
- `enrich-and-review` Phase 5 — reviewers EXPLICITLY sequential per coordinator review doctrine.

If you find yourself proposing a parallelization of any of these, you're missing the gate the linearity encodes.

## Empirical usage frequency — top-10 ceremonies (2026-05-21 baseline)

Refactor priority is `frequency × per-fire savings`, not raw step count. Mined from `git log` (90d, all branches), archive directories, and on-disk artifact counts (total 1865 commits):

| Rank | Ceremony | Frequency | Source signal |
|---|---|---|---|
| 1 | `session-end` / `workstream-complete` | ~16-20/wk | ~261 raw subject matches |
| 2 | `handoff` | ~15/wk | 196 commit matches, 249 lifetime archived |
| 3 | `plan` | ~13/wk | 166 matches + 111 plan files |
| 4 | `review` | ~13/wk | 174 matches + 40 review-trail JSONs |
| 5 | `merging-to-main` | ~5/wk | 63 incl auto-merges |
| 6 | `pickup` | ~3.5/wk | 43 matches |
| 7 | `update-docs` | ~3/wk | 40 matches |
| 8 | `learn-lessons` | ~2.5/wk | 33 (90d) / 210 lifetime |
| 9 | `distill` | ~2/wk | 27-30 matches |
| 10 | `spinoff` | ~2/wk | 28 matches |

Refresh by re-running the survey at `tasks/skill-step-survey/usage-frequency.md` — these numbers age.

## Refactor target priority — frequency × per-fire savings ranking

*2026-05-21, claude-central.* Applying the `frequency × per-fire-savings` product:

1. **`plan`** — ~13/wk × multiple sequential pre-flights + sequential reviewers. **Single biggest yield.**
2. **`session-end` / `workstream-complete`** — ~16-20/wk × embedded code-reviewer + lessons + handoff-or-cap + review-trail. Small per-fire savings compound.
3. **`update-docs`** — ~3/wk × 11+ phases, many independent. Phase-graph refactor pays back per run.
4. **`workday-complete` / `workweek-complete`** — lower frequency but very tall ceremonies; per-fire wall-clock halving compounds quickly.
5. **`bug-blitz` / `bug-sweep`** — autonomous-wave shape; structurally parallel in spirit but worth auditing whether waves actually fire concurrently in practice.

## Target-Selection-Discipline — Mine Empirical Usage Frequency Before Choosing Refactor Targets

*2026-05-21, claude-central.* When selecting which surfaces to refactor, parallelize, or extract, a-priori target selection ("these look like the hot ones") systematically mis-ranks. Mine the empirical usage frequency first: dispatch a `git log` + archive-count scout per candidate, and **rank by frequency × per-fire savings**, not by intuition about which surface "feels" central. A surface that fires rarely but is expensive per-fire can outrank a frequently-touched but cheap one — and the product is invisible without the count.

**Procedure:** (1) enumerate candidate surfaces; (2) per candidate, count invocations across `git log` history and archived sessions (the count is the *frequency* term); (3) estimate per-fire savings of the refactor (the *magnitude* term); (4) rank by the product; (5) refactor top-ranked first. This is the target-selection analog of the per-executor budget axis — the same "measure before you cut" discipline applied to *which* surface rather than *how big* the chunk. Composes with `agent-dispatch-economics.md` § Cluster Execution: once the ranking picks the novel item, the cluster pattern handles the surgical follow-ups.

**Methodology caveats** (do not trust raw counts):

- `session-end` and `handoff` co-occur in commit subjects; raw matches inflate ceremony-fire counts by ~1.5-2×. Tight prefix counts (`handoff(`=21, `pickup:`=43, `chore(workday-start)`=34, `chore(update-docs)`=40) are closer to ground truth.
- `execute-plan` and `enrich-and-review` are sub-skills invoked from other ceremonies — their commits are tagged by the *parent* ceremony, so they look invisible in commit-prefix tallies.
- Conversational skills (`brainstorming`, exploration-mode) leave **no commit fingerprint by design** — frequency mining will under-rank them. Triangulate with archive-counts or in-session usage if a conversational skill is a refactor candidate.
- Low-frequency tall ceremonies (`workweek-complete` at ~1/wk but many phases) reward per-fire refactor more than their frequency rank suggests; weight by ceremony depth, not just count.

## Spec backlink

Empirical survey + decision: `tasks/skill-step-survey/` (commands.md, skills-a.md, skills-b.md, usage-frequency.md). Spinoff: `state/handoffs/2026-05-20_231841_skill-step-gates-vs-todo-list.md`.
