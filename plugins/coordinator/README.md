# coordinator

Core orchestration plugin for the Dónal + Claude agent hierarchy. Always enabled on every project.

## What It Does

The coordinator plugin is the backbone of the system. It provides:

1. **The orchestration role** — the main session agent operates as EM (engineering manager), delegating work to specialized subagents rather than implementing directly
2. **Universal reviewers** — Patrik (code quality, architecture) and Zoli (ambition backstop) are available on every project regardless of domain
3. **Workflow skills** — 22 codified processes (SKILL.md) covering the full development lifecycle, plus 8 pipeline definitions (PIPELINE.md) backing commands
4. **Session commands** — slash commands for pipeline operations (dispatch executors, route reviews, manage handoffs)

## Components

### Agents

| Agent | Model | Role |
|-------|-------|------|
| **enricher** | Sonnet | Research agent — surveys codebases, traces deps, fills in stub details |
| **executor** | Sonnet | Implementation agent — follows specs precisely, reports DONE/DONE_WITH_CONCERNS/BLOCKED |
| **review-integrator** | Opus | Applies reviewer findings to artifacts with annotations, escalates disagreements |
| **staff-eng** | Opus | Senior staff engineer — rigorous review of code, plans, architecture, documentation |
| **ambition-advocate** | Opus | Backstop reviewer — challenges conservative recommendations, never a primary reviewer |

### Commands (21, all user-invocable via `/`)

| Command | Purpose |
|---------|---------|
| `/session-start` | Orient session — preflight, load context, choose work |
| `/session-end` | Wrap up finished work — capture lessons, update docs |
| `/handoff` | Save session state for next session handoff |
| `/workday-start` | Morning orientation — triage handoffs, surface staleness, align priorities |
| `/workday-complete` | End-of-day — update docs, consolidate branches, run health survey |
| `/update-docs` | Repo-wide documentation maintenance and sync (auto-chains `/distill` when thresholds met) |
| `/delegate-execution` | Dispatch enriched stubs to executor agents |
| `/execute-plan` | Execute a PM-approved implementation plan in the coordinator session |
| `/enrich-and-review` | Run enrichment pipeline on chunk directories |
| `/review-dispatch` | Route artifacts to the right reviewer |
| `/generate-repomap` | Generate a ranked repository map for LLM context injection |
| `/mise-en-place` | Autonomous backlog execution — gather ready items, execute without stopping |
| `/deep-research` | Deep research pipeline — internet sources (Pipeline A) or codebase (Pipeline B) |
| `/structured-research` | Batch research across multiple subjects with repeating structure and output schema |
| `/architecture-audit` | Bootstrap or refresh the architecture atlas via multi-phase agent pipeline |
| `/architecture-rotation` | Run the weekly architecture audit rotation — score, audit, apply, update ledger |
| `/code-health` | Night-shift code health review — scan commits, dispatch reviewer, apply findings |
| `/bug-sweep` | Systematic codebase bug hunt — fix AI-fixable bugs, defer blocked ones to backlog |
| `/distill` | Distill accumulated artifacts into wiki guides + decision records, then delete source material |
| `/pickup` | Resume work from a handoff — grab the baton and orient before continuing |
| `/autonomous` | Toggle autonomous execution mode — suppresses `/handoff` nudges from context pressure hook |

### Skills (23)

**Workflow & Planning:**
- `brainstorming` — Collaborative dialogue to refine ideas into designs. Scope assessment, design-for-isolation, existing-codebase awareness.
- `writing-plans` — Decompose designs into executable tasks. Scope checking, file structure mapping, TDD-oriented granularity.
- `executing-plans` — Execute plans task-by-task with review checkpoints. Prefers `/delegate-execution` in coordinator sessions.
- `verification-before-completion` — Prove it works before claiming it's done.
- `deep-research` — Multi-source investigation of repos or topics.

**Development Process:**
- `test-driven-development` — RED-GREEN-REFACTOR cycle, strictly enforced.
- `systematic-debugging` — Root-cause debugging process.
- `dispatching-parallel-agents` — Dispatch independent tasks in parallel.
- `stuck-detection` — Self-monitoring protocol — repetition, oscillation, analysis paralysis detection.

**Code Review:**
- `requesting-code-review` — Request review via `/review-dispatch`.
- `receiving-code-review` — How to receive and act on review feedback.

**Git & Branching:**
- `using-git-worktrees` — Isolated workspaces per feature.
- `finishing-a-development-branch` — Complete development, PR, merge.
- `merging-to-main` — PR creation, CI gating, merge, cleanup.
- `consolidate-git` — Branch cleanup: absorb unique commits from stale branches, delete them, merge to main.

**Writing & Meta:**
- `writing-skills` — TDD applied to skill/documentation authoring.
- `skill-discovery` — Find and use skills. SUBAGENT-STOP gate, instruction priority hierarchy.
- `validate` — Run all CI validation checks locally.

**Health & Maintenance:**
- `daily-code-health` — Review recent commits for issues, dispatch reviewer, update health tracking.
- `weekly-architecture-audit` — Systematic rotation through project systems. Weighted scoring for audit target selection.
- `deep-architecture-audit` — Deep-dive architecture audit of a specific system or subsystem.
- `debt-triage` — Review and prioritize the technical debt backlog. EM-PM conversation, not dispatched agent.
- `mise-en-place` — Autonomous backlog execution in a single run.
- `bug-sweep` — Systematic codebase sweep for bug patterns — fix AI-fixable, defer rest to backlog.
- `tracker-maintenance` — Maintain the project tracker — archive completed work, update dependencies, sweep for untracked commits.
- `lessons-trim` — Trim stale entries from lessons files, merge duplicates, clean up feature-scoped files.
- `handoff-archival` — Archive consumed handoffs older than 48 hours.
- `atlas-integrity-check` — Check changed files against the architecture atlas for unmapped entries.
- `artifact-consolidation` — Bulk prune accumulated artifacts without knowledge extraction. For distill-then-delete, use `/distill` instead.
- `project-onboarding` — Bootstrap project tracking infrastructure — tracker, tasks, archive, handoffs.

### Hooks

- **SessionStart** — Coordinator reminder (EM role/pipeline awareness), project orientation, UE knowledge distrust guard
- **PreToolUse (Bash)** — validate-commit: blocks bad commit patterns before they run
- **PreToolUse (WebSearch|WebFetch)** — suggest-sonnet-research: advisory to use deep-research pipelines instead of direct web calls
- **PostToolUse (ExitPlanMode)** — plan-persistence-check: ensures plan content is written to disk, not held in context
- **PostToolUse (all)** — context-pressure-advisory: monitors context usage, nudges handoff creation before compaction
- **SubagentStop** — executor-exit-watchdog: detects executor agents that exit without protocol-compliant status tags
- **PreCompact** — context-pressure-precompact: fires just before compaction, prompts immediate handoff creation

## Routing Extension Protocol

The coordinator defines the routing framework that domain plugins extend:

1. This plugin's `routing.md` defines universal reviewers (Patrik, Zoli) and the routing algorithm
2. Domain plugins contribute routing fragments via their own `routing.md` files
3. At dispatch time, `/review-dispatch` merges all fragments into a composite routing table
4. Signals from changed code determine which reviewer handles the review

See the parent [ARCHITECTURE.md](../ARCHITECTURE.md) for the full conceptual model.

## Per-Project Config

Create `.claude/coordinator.local.md` in your project:

```yaml
---
project_type: unreal    # unreal | game-docs | web | pure-docs
---
```

Default (no config): core-only (Patrik + Zoli).

## Recent Changes

### v1.3.1 (March 2026) — Artifact Distillation

- **`/distill` command:** New 6-phase pipeline that extracts knowledge from accumulated session artifacts (plans, handoffs, completed work) into evergreen wiki documents (`docs/guides/`, `docs/decisions/`), then deletes the source material. Haiku scans → Haiku QG → Sonnet synthesis → Opus assembly → PM approval → apply+delete.
- **`/update-docs` chaining:** Phase 12 added — auto-fires `/distill` when artifact count ≥50 or last distillation >14 days ago. PM gate in `/distill` Phase 4 provides the approval checkpoint. `--no-distill` flag to skip.
- **Mise-en-place guard:** Hibernate mode passes `--no-distill` to avoid blocking on PM approval overnight.
- **`artifact-consolidation` relationship:** Consolidation remains for bulk pruning without extraction. `/distill` supersedes it for the distill-then-delete workflow.

### v1.3.0 (March 2026) — Squad Expansion

Transforms the coordinator from a delivery-only pipeline into a full engineering squad with maintenance cadences, codebase health tracking, and structural "EM does not type code" enforcement.

- **Review-integrator:** New Opus agent that applies reviewer findings to artifacts. Replaces manual EM feedback application in review-dispatch (Phase 3.7), enrich-and-review (Phase 5), and delegate-execution (Phase 3). The EM now verifies rather than types.
- **Reviewer self-checks:** All 6 reviewers (Patrik, Zolí, Sid, Palí, Fru, Camelia) get built-in self-moderation prompts. Experimental — validate after 2 weeks.
- **Routing intelligence:** Effort calibration table, skip conditions, and EM override guidance added to routing.md.
- **Health infrastructure:** Three new skills (daily-code-health, weekly-architecture-audit, debt-triage) with health ledger and debt backlog templates per project.
- **Session-start health surface:** New Step 0g reads health ledger and surfaces findings (non-blocking). New maintenance menu option.
- **Workday-complete redesign:** Branch consolidation + health survey. No longer merges to main — merging is a deliberate, supervised act via /merge-to-main.
- **Merge-to-main hardening:** New Step 0 test suite gate with --force escape hatch. First Officer Doctrine: EM can refuse to merge.

### v1.2.0 (March 2026) — Write-Ahead Status Protocol

All pipeline phases now mark documents *before* starting work, not just on completion. This eliminates ambiguous "not started" state after crashes — a recurring source of expensive triage.

- **Enricher:** New write-ahead protocol — marks stub as "Enrichment in progress" before research, "Enriched — pending review" on completion. Includes crash recovery guidance.
- **Executor:** New write-ahead protocol — marks stub as "Execution in progress" before implementation. This is the one exception to "does not update stub documents" — status markers are infrastructure, not spec changes.
- **Enrich-and-review:** New Phase 2.5 (pre-enrichment status) and Phase 4.5 (pre-review status) — coordinator updates tracker and commits before dispatching agents.
- **Delegate-execution:** New Phase 1.5 — coordinator marks tracker as "Execution in progress" and commits before dispatching executors.
- **Review-dispatch:** New Phase 2.5 — marks artifact with reviewer name before dispatching.
- **Executing-plans:** Plan document updated on disk (not just the task list) before and after each task.
- **Writing-plans:** Plan header template now includes `Status:` field.

See [ARCHITECTURE.md](../ARCHITECTURE.md) § "The Write-Ahead Status Protocol" for the conceptual model and state machine.

### v1.1.0 (March 2026) — Superpowers v5.0.0 Absorption

- **Brainstorming:** Scope assessment before detailed questions; design-for-isolation principles; existing-codebase awareness
- **Writing-plans:** Scope check (decompose multi-system specs); file structure mapping before task decomposition
- **Executor:** New status protocol (DONE/DONE_WITH_CONCERNS replacing COMPLETED; NEEDS_CONTEXT split from NEEDS_COORDINATOR); expanded self-review with judgment checks; code organization awareness; expanded escalation encouragement
- **Delegate-execution:** Spec compliance check — coordinator verifies executor fidelity before routing to Patrik
- **Skill-discovery:** SUBAGENT-STOP gate; instruction priority hierarchy
- **Executing-plans:** Delegate-execution preference note for coordinator sessions

## Authors

Dónal O'Duffy & Claude
