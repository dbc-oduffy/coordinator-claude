# coordinator

Core orchestration plugin for the Dónal + Claude agent hierarchy. Always enabled on every project.

This plugin addresses six failure modes that compound silently in sustained AI-assisted development. Each maps to named skills and commands.

---

## Failure Mode 1 — EM loses the thread across sessions

*The session ends, context compresses, and the next session starts cold. Decisions made, approaches abandoned, lessons learned — all gone. The EM re-derives the same conclusions and makes the same mistakes.*

**Addressed by:**
- `/handoff` — Snapshot session state to disk before context pressure hits. Includes goal, decisions, tried-and-abandoned, next steps.
- `/pickup` — Resume from a handoff with full orientation before continuing. Never cold-start.
- `/session-start` — Full session orientation: triage handoffs, surface staleness, choose work. Invoke when the opening is vague or strategic.
- `tasks/lessons.md` + `lessons-trim` skill — Persistent pattern capture. Lessons promote to wiki when they generalize. Trim when file exceeds ~50 entries.
- `handoff-archival` skill — Periodic cleanup of consumed handoffs.
- `/workday-start` / `/workday-complete` — Full-day framing: morning triage and evening consolidation.

---

## Failure Mode 2 — Agent gets underspecified work

*A stub goes to an executor with vague file paths, assumed context, and fuzzy acceptance criteria. The executor fills in gaps by hallucinating plausible-looking details. The output looks right until someone reads it carefully.*

**Addressed by:**
- `brainstorming` skill — Explore intent, scope, and design before committing. Scope assessment, design-for-isolation, existing-codebase awareness.
- `writing-plans` skill — Decompose into executable stubs: file paths, implementation steps, verification criteria, TDD-oriented granularity.
- `/enrich-and-review` — Dispatch research agents to fill stubs with codebase facts (actual paths, current patterns, dependency maps) before any executor touches code.
- `/delegate-execution` — Dispatch enriched stubs to executors. Spec compliance check before routing to Patrik.
- `enricher` agent — Sonnet research agent that surveys codebases, traces dependencies, fills in stub details.
- Write-ahead status protocol — Stubs marked "in progress" *before* work begins, so a crash leaves a recoverable state rather than an ambiguous "not started."

---

## Failure Mode 3 — Code review produces noise, not signal

*Reviewer returns 30 findings. Six are real problems. Twenty-four are style preferences, redundant observations, and concerns the PM needs to adjudicate. The EM spends more time triaging the review than reading the code.*

**Addressed by:**
- `/review-dispatch` — Route artifacts to the right reviewer based on change signals (code, architecture, domain). Includes effort calibration, skip conditions, and EM override guidance.
- Sequential review discipline — Multi-persona reviews are sequential, never parallel. Reviewer 2 sees Reviewer 1's findings integrated; insights compound.
- `review-integrator` agent (Opus) — Applies reviewer findings to artifacts with annotations. Escalates disagreements. The EM verifies rather than types.
- Backstop pattern — Zoli (ambition advocate) challenges conservative Patrik recommendations. Mandatory for high-effort reviews.
- `requesting-code-review` / `receiving-code-review` skills — Codified protocol for preparation, routing, and applying feedback.
- Reviewer-routed workers — Reviewers name mechanical analysis workers (`test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`) in their findings. EM dispatches them as a follow-up step, not during the review.

---

## Failure Mode 4 — Synthesizer rewrites instead of synthesizes

*A synthesizer agent receives three specialist reports and returns a summary that reads like a condensed version of the specialists' prose. Edge cases drop. Cross-topic relationships vanish. Nuanced facts smooth over.*

**Addressed by:**
- Synthesis Discipline (coordinator CLAUDE.md) — Synthesizers assess, fill, and frame. Never re-author specialist content. Rewriting-synthesizers empirically drop edge cases (+25–33pp), nuanced facts (+19–21pp), cross-topic relationships (+42pp).
- Pipeline C v2.1 (`/structured-research`) — Hard file-existence gate, CONTESTED change type for unresolved peer challenges, adversarial verifier dynamics, forced reflection after each source fetch.
- `/distill` — 6-phase pipeline: Haiku scans → Haiku QG → Sonnet synthesis → Opus assembly → PM gate → apply+delete. Synthesis of session artifacts into evergreen wiki guides.
- `deep-research` skill / `/deep-research` — Multi-source investigation. Pipeline A (internet), Pipeline B (codebase), Pipeline C (structured schema research), Pipeline D (NotebookLM media).

---

## Failure Mode 5 — Codebase debt accumulates invisibly

*No session flags architecture drift. No process surfaces the accumulation. The system works until it doesn't, and by then the debt is load-bearing.*

**Addressed by:**
- `/architecture-audit` — Bootstrap or refresh the architecture atlas via multi-phase agent pipeline. Produces a structured, queryable record of system architecture.
- `/architecture-rotation` — Weekly rotation through project systems. Weighted scoring for audit target selection. Systematic coverage rather than reactive triage.
- `debt-triage` skill — Review and prioritize the technical debt backlog. EM-PM conversation, not a dispatched agent. Keeps PM aligned on what's accumulating.
- `/code-health` — Night-shift code health review: scan recent commits, dispatch reviewer, apply findings, update health ledger.
- `weekly-architecture-audit` / `deep-architecture-audit` skills — Structured audit protocols with health ledger templates.
- `atlas-integrity-check` skill — Check changed files against the architecture atlas for unmapped entries.

---

## Failure Mode 6 — Bugs ship without root-cause diagnosis

*An agent identifies a symptom and patches it. The root cause stays in place. Two sessions later, a variant of the same bug appears. The patch list grows; the underlying issue doesn't.*

**Addressed by:**
- `systematic-debugging` skill — Root-cause debugging process. Diagnose before proposing fixes. Post-item-4: feedback-loop-first framing.
- `test-driven-development` skill — RED-GREEN-REFACTOR cycle, strictly enforced. Tests verify real behavior, not mock behavior.
- `/bug-sweep` — Systematic codebase bug hunt: fix AI-fixable bugs, defer blocked ones to backlog. Optional `--codex-verify` flag uses `codex-review-gate` (opt-in add-on) as an independent-model second opinion.
- `verification-before-completion` skill — Prove it works before claiming done. Catches the "it should work" class of failures.
- `stuck-detection` skill — Self-monitoring protocol. Repetition, oscillation, analysis paralysis detection. Prevents thrashing on hard bugs from consuming session context.
- P0/P1 verification gate (coordinator CLAUDE.md) — High-severity sweep findings require EM or verifier to read cited code against current source before acting. High-confidence framing inverts the hit rate.

---

## Reference

Full component inventory for the record. The failure-mode sections above are the navigational surface; this is the index.

### Agents

| Agent | Model | Role |
|-------|-------|------|
| **enricher** | Sonnet | Research agent — surveys codebases, traces deps, fills in stub details |
| **executor** | Sonnet | Implementation agent — follows specs precisely, reports DONE/DONE_WITH_CONCERNS/BLOCKED |
| **review-integrator** | Opus | Applies reviewer findings to artifacts with annotations, escalates disagreements |
| **staff-eng** | Opus | Senior staff engineer — rigorous review of code, plans, architecture, documentation |
| **ambition-advocate** | Opus | Backstop reviewer — challenges conservative recommendations, never a primary reviewer |

### Commands (23)

| Command | Purpose |
|---------|---------|
| `/session-start` | Orient session — preflight, load context, choose work |
| `/session-end` | Wrap up finished work — capture lessons, update docs |
| `/handoff` | Save session state for next session handoff |
| `/pickup` | Resume work from a handoff — grab the baton and orient before continuing |
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
| `/daily-review` | Strategic daily review — inventory today's work, summarize what shipped, get architectural perspective |
| `/autonomous` | Toggle autonomous execution mode — suppresses `/handoff` nudges from context pressure hook |
| `/setup` | Set up the coordinator plugin — check prerequisites, verify environment, configure project |

### Skills (25+)

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
- `handoff-archival` — Archive consumed handoffs.
- `codex-review-gate` — **Opt-in add-on** (install via `setup/install.sh --enable-codex`). Runs Codex code review as an independent-model second opinion in `/workweek-complete` and `/bug-sweep --codex-verify`. Requires the external [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) plugin. Default installs omit it.
- `atlas-integrity-check` — Check changed files against the architecture atlas for unmapped entries.
- `artifact-consolidation` — Bulk prune accumulated artifacts without knowledge extraction. For distill-then-delete, use `/distill` instead.
- `project-onboarding` — Bootstrap project tracking infrastructure — tracker, tasks, archive, handoffs.

### Hooks

- **SessionStart** — Coordinator reminder (EM role/pipeline awareness), project orientation, UE knowledge distrust guard
- **PreToolUse (Bash)** — validate-commit: blocks bad commit patterns before they run
- **PreToolUse (WebSearch|WebFetch)** — suggest-sonnet-research: advisory to use deep-research pipelines instead of direct web calls
- **PostToolUse (ExitPlanMode)** — plan-persistence-check: ensures plan content is written to disk, not held in context
- **PostToolUse (all)** — context-pressure-advisory: monitors context usage, nudges handoff creation before compaction
- **PreCompact** — context-pressure-precompact: fires just before compaction, prompts immediate handoff creation

### Routing Extension Protocol

The coordinator defines the routing framework that domain plugins extend:

1. This plugin's `routing.md` defines universal reviewers (Patrik, Zoli) and the routing algorithm
2. Domain plugins contribute routing fragments via their own `routing.md` files
3. At dispatch time, `/review-dispatch` merges all fragments into a composite routing table
4. Signals from changed code determine which reviewer handles the review

See the parent [ARCHITECTURE.md](../ARCHITECTURE.md) for the full conceptual model.

### Per-Project Config

Create `coordinator.local.md` in your project:

```yaml
---
project_type: unreal    # unreal | game-docs | web | pure-docs
---
```

Default (no config): core-only (Patrik + Zoli).

---

## Recent Changes

### v1.4.0 (April 2026) — Pipeline C v2.1: Structured Research Upgrade

Brings Pipeline C (structured research) to v2.1 parity with Pipeline A and B. Fixes a synthesizer prose-slippage bug and adds adversarial peer dynamics.

- **Synthesizer output-first ordering:** Skeleton structured data file written immediately as crash insurance (step 2 of 8, not step 5 of 9). Final output overwrites the skeleton after reconciliation and validation. Annotations written separately to `synthesis-annotations.md` — no more ambiguous `synthesis.md` that could be mistaken for the deliverable.
- **Hard file-existence gate:** EM Step 6 now checks whether the structured data file exists at `[OUTPUT_PATH]` before attempting content validation. Missing file blocks archival and triggers a correction message to the synthesizer. Fixes the COD prose-slippage incident where the synthesizer wrote prose only and the EM archived without catching it.
- **CONTESTED change type:** New fifth change type for unresolved peer challenges (joining CONFIRMED/UPDATED/NEW/REFUTED). Verifiers produce CONTESTED when a 2-minute challenge timeout expires. Synthesizer MUST resolve all CONTESTED fields — they do not pass through to the output.
- **Adversarial verifier dynamics:** Mandatory challenge self-check ("Have I challenged at least one peer's schema field value?"), no acknowledgment-only messages, resolution protocol with evidence-or-concede.
- **SCHEMA_OVERLAP message category:** Adapted from Pipeline A's OVERLAP — cross-field evidence sharing ("While researching {my_field}, I found evidence relevant to your field {their_field}") rather than ownership negotiation. Natural fit for schema-mapped research.
- **Forced reflection:** After each source fetch, verifiers assess which schema fields were populated or changed. Helps the synthesizer trace which sources drove which field changes.
- **EM spec quality checklist:** 6-item quality gate before team dispatch — schema field clarity, falsifiable acceptance criteria, clean topic→field mapping, existing data loaded, extractable gate rules, adversarial search terms included.
- **Scout adversarial pass-through:** Scout brief now includes adversarial queries; scout flags topics with no adversarial sources found.

**Files changed:** `deep-research/` plugin — 4 pipeline templates (verifier, synthesizer, scout, team-protocol), 1 command (structured.md), 1 agent definition (structured-synthesizer.md), CLAUDE.md.

### v1.3.1 (March 2026) — Artifact Distillation

- **`/distill` command:** New 6-phase pipeline that extracts knowledge from accumulated session artifacts (plans, handoffs, completed work) into evergreen wiki documents (`docs/wiki/`, `docs/decisions/`), then deletes the source material. Haiku scans → Haiku QG → Sonnet synthesis → Opus assembly → PM approval → apply+delete.
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

---

## Authors

Dónal O'Duffy & Claude
