# System Architecture

This document explains how coordinator-claude works: the PM-EM model, agent roles, pipeline flow, and extension points.

## The PM-EM Model

coordinator-claude implements a **PM-EM (Product Manager / Engineering Manager) dynamic** in your Claude sessions:

- **You are the PM.** You set direction, make product decisions, approve designs, and give the go/no-go on merges.
- **Claude is the EM.** Claude orchestrates work, delegates to specialists, manages pipeline flow, and verifies output. The EM doesn't write code directly — they ensure the right work gets done correctly.

This isn't just metaphor. The coordinator agent is explicitly instructed to delegate implementation to executor agents, route reviews to named reviewers, and reserve their context window for decisions rather than typing. An EM who opens a file and starts editing code has left the bridge unmanned.

### Why This Model?

Traditional Claude Code usage has one agent doing everything: writing code, reviewing it, planning work, executing plans. This creates predictable quality problems:
- The same agent reviewing its own work misses its own blind spots
- Long sessions accumulate context that degrades output quality
- No separation between "follow spec faithfully" and "challenge whether the spec is right"
- No persistent workflow knowledge — best practices must be re-established each session

The PM-EM model addresses all four.

## Three-Tier Delegation

The system uses three model tiers, each matched to the cognitive demands of their role:

| Tier | Model | Roles | Why |
|------|-------|-------|-----|
| Opus | Orchestrator | Coordinator (EM), reviewers (Patrik, Sid, Camelia, etc.), research orchestrators | Judgment, analysis, architectural decisions |
| Sonnet | Executor | Executor agents, enricher agents, review-integrator, research synthesizers | Faithful spec-following, implementation, research |
| Haiku | Verifier | Mechanical checks, template validation, compile verification, discovery scouts | Speed, cost, high-throughput mechanical work |

### The Dispatch Rule

Match the model to the cognitive demands, not the importance of the task. A trivial but architecturally significant decision goes to Opus. A complex but mechanical implementation goes to Sonnet.

## Agent Roles

### Coordinator (EM)
The main session agent. Lives in your terminal. Makes delegation decisions, verifies output, manages pipeline transitions. Does NOT write implementation code in project repos.

### Executor
Fresh Sonnet subagent dispatched per task. Receives a fully-specified stub, implements it faithfully, runs validation, reports back. The "typist, not the architect." Stops and escalates if the spec is ambiguous.

### Enricher
Research subagent. Surveys codebases, traces dependencies, fills concrete details into plan stubs (file paths, function signatures, integration points) so executors can implement without additional research.

### Review-Integrator
Applies reviewer findings to artifacts after review dispatch. Receives structured findings, applies every finding with annotations, escalates disagreements rather than silently skipping them.

### Reviewers (Opus)

| Reviewer | Domain | Focus |
|----------|--------|-------|
| **Patrik** | Code quality, architecture, security | Correctness, documentation completeness, architectural soundness, error handling. Adversarial framing: assumes the code has defects. |
| **Zolí** | Ambition backstop | Challenges conservative recommendations when AI execution capacity changes the cost calculus. Only invoked as a backstop to Patrik. |
| **Sid** | Game dev, Unreal Engine | Engine-appropriate patterns, Blueprint/C++ architecture, game performance, replication. Researches documentation rather than guessing. |
| **Palí** | Front-end | Design system adherence, token validation, component patterns. "Close enough" to design specs is often correct when it means using standard utilities. |
| **Fru** | UX flow | Trust signals, clarity, cognitive load, accessibility. Reviews user-facing features for whether they make sense to a human. |
| **Camelia** | Data science, ML/AI | Statistical validity, ML methodology, data quality, experimental design. Complements Patrik's engineering lens with quantitative expertise. |

### Research Orchestrators (Opus)
Dispatch Haiku scouts and Sonnet verifiers, evaluate quality gates, synthesize final output. Three pipeline modes:
- **Pipeline A (Internet):** Multi-source web research with cross-verification and source grading
- **Pipeline B (Codebase):** 2 Haiku scouts build file inventories, 4 Sonnet specialists analyze architecture with real-time cross-pollination, Opus synthesizes
- **Pipeline C (Structured Batch):** Schema-driven research across N entities with repeating structure

## The Full Pipeline

A feature typically flows through:

```
Brainstorm -> Plan -> Enrich -> Review Enrichment -> Execute -> Spec Check -> Code Review -> Backstop -> Ship
  (skill)   (skill) (enricher)    (reviewer)       (executor) (coordinator) (Patrik+domain) (Zoli)    (skill)
```

Each stage is a quality checkpoint:
- **Brainstorm** catches wrong direction
- **Plan** catches wrong decomposition
- **Enrich** catches wrong assumptions (file doesn't exist, API changed)
- **Execute** catches wrong implementation
- **Spec check** catches spec drift (executor built something different)
- **Code review** catches quality issues
- **Backstop** catches unnecessary conservatism

Not every change needs the full pipeline. Lighter paths:
- Direct execution for small, well-understood changes
- Review-only for auditing existing code
- Single-session plan execution (no enrichment needed)

### Autonomous Batch Execution (Mise-en-Place)

When the PM authorizes a straight-shot through the backlog (`/mise-en-place`), the EM front-loads parallelism planning:

1. **Inventory** all ready items and their file footprints (which files each item will modify)
2. **Build waves** — group file-disjoint items into parallel batches. Items sharing files go in separate waves.
3. **Execute wave by wave** — all items in a wave dispatch concurrently to Sonnet executors. A wave gate between batches ensures later items see earlier changes.
4. **No worktrees** — all executors operate on the same worktree. The file-disjoint constraint is the coordination mechanism; worktree overhead (branch creation, merge resolution) costs more than it saves at agent speed.

This transforms what would be sequential N-item execution into M-wave execution where each wave may contain multiple concurrent items.

## Review Routing

The routing system is **composable**:

1. Coordinator defines universal reviewers (Patrik, Zolí) in `plugins/coordinator/routing.md`
2. Domain plugins contribute fragments via their own `routing.md` (e.g., game-dev registers Sid)
3. `/review-dispatch` merges all fragments at dispatch time
4. Changed code signals determine which reviewer handles it
5. Unmatched signals fall back to Patrik

Sequential review protocol (for non-trivial changes):
1. Domain specialist first (if applicable)
2. Coordinator applies findings
3. Patrik catches regressions (generalist pass)
4. Zolí challenges conservatism (backstop, when warranted)

### Backstop Reconciliation

When Zolí (backstop) returns:
- `BACKSTOP_AGREES` — Patrik's conservative approach is genuinely appropriate; proceed
- `BACKSTOP_CHALLENGES` — Both perspectives surface to coordinator/PM for resolution
- `BACKSTOP_OVERRIDES` — The conservative approach is clearly wrong; rare "iceberg" territory

## Session Lifecycle

### Session Start
The SessionStart hook fires and injects:
1. Orientation documents (repo map, DIRECTORY.md if present)
2. EM discipline reminder (context-aware: full model for this repo, light-touch for project repos)

Then `/session-start` command runs the full orientation protocol.

### Session Continuity
State survives compaction through:
- **Tasks API** (TaskCreate/TaskUpdate/TaskList/TaskGet) — per-conversation flight recorder, persists through compaction by design
- **Handoffs** — structured disk-based state capture between sessions
- **Orientation cache** — compact project awareness document, sub-second load
- **Plan documents** — on-disk specs with write-ahead status fields

Context pressure is monitored by a three-layer hook system:
- **PreCompact** — writes a sentinel + state snapshot to `/tmp/` before compaction fires
- **PostToolUse** — (1) bridges the PreCompact snapshot into context on the first tool use after compaction, (2) mid-chain threshold safety net (5 min throttle, 10 min session-age gate)
- **Stop** — primary threshold check, fires once per turn (10 min session-age gate). Both threshold checks share bark-once sentinels to avoid duplicate warnings.

### Session End
`/session-end` captures lessons, updates docs, commits. `/handoff` creates a structured state dump for the next session.

## Plugin Extension Model

The plugin system is designed for extension. Each plugin contributes:
- `agents/` — agent definitions with YAML frontmatter
- `routing.md` — routing fragment (optional, for domain-specific reviewers)
- `skills/` — skill definitions (optional, coordinator plugin only)
- `commands/` — slash commands (optional, coordinator plugin only)
- `hooks/` — hook scripts (optional)
- `CLAUDE.md` — project-context instructions injected automatically

To add a new domain (e.g., mobile-dev, security, devops):
1. Create `plugins/my-domain/`
2. Add `agents/my-reviewer.md` with YAML frontmatter
3. Add `routing.md` with the routing fragment
4. Enable in `settings.json`

The coordinator does not need to change. See [docs/customization.md](customization.md) for details.

## Project Knowledge: Layered Context, Not Bulk Injection

Most AI coding tools solve the "large codebase" problem by building a repo map — a structural index of files, classes, and functions — and injecting it at the start of every interaction. It works, but it has a ceiling: a repo map tells you *what exists*, not *why it exists*, *what state it's in*, or *what to do next*.

This system maintains several complementary knowledge layers instead:

| Layer | Artifact | What It Captures | How It's Maintained |
|-------|----------|-----------------|-------------------|
| **Structure** | `DIRECTORY.md` | File-by-file index with purpose annotations | Auto-generated, updated by `/update-docs` when source files change |
| **Architecture** | Architecture atlas (`tasks/architecture-atlas/`) | System boundaries, connectivity, health scores | Multi-agent audit pipeline; weekly rotation targets stalest system |
| **Activity** | Repo map (`.claude/repomap.md`) | Git-activity-ranked file list, fitted to token budget | Generated on demand; ranked by churn, not just existence |
| **Intent** | Project tracker, roadmaps, plan docs | What's being built, what's blocked, what shipped | PM-maintained with EM assistance; `/update-docs` syncs status |
| **State** | Health ledger, bug/debt backlogs | Known issues, sweep results, system health | Updated by sweeps and audits; surfaced at session start |

None of these are loaded in bulk. The system uses a **tiered context model**:

```
L1 (always in context)   CLAUDE.md + MEMORY.md + orientation cache (~60 lines)
L2 (on-demand)           DIRECTORY.md, atlas, repomap, tracker, backlogs
L3 (deep storage)        Codebase, git history — read by subagents, never bulk-loaded
```

The **orientation cache** is the key. Generated by `/workday-start`, it's a ~60-line ephemeral summary that distills L2 artifacts into a compact briefing: top-ranked files, directory structure at a glance, health snapshot, doc freshness, and pointers to every L2 artifact for drill-down.

### Fighting Staleness

The hard part of maintaining project documentation isn't generating it — it's keeping it current. `/update-docs` is an 11-phase maintenance pipeline that syncs all documentation artifacts against the codebase on every run: refreshing source indexes, archiving completed work, trimming lessons, checking the architecture atlas for unmapped files, and flagging drift. `/workday-start` surfaces staleness metrics at the top of each day.

### "Grep Bait" as a Design Principle

Copious, status-tagged documentation across wikis, plans, archives, and trackers creates a secondary benefit: even a vague PM directive like "finish up that blueprint graph handling" produces hits across multiple artifacts — each with dates, status, and context. The documentation isn't just for reading; it's searchable surface area that makes the codebase self-describing.

## The Write-Ahead Status Protocol

Every pipeline phase follows a write-ahead pattern: mark the document *before* starting work, update *after* completing. This prevents ambiguous state after crashes.

Status values flow through a defined state machine:

```
Pending enrichment
  -> Enrichment in progress
    -> Enriched -- pending review
      -> Under review by [Name]
        -> Enriched and reviewed
          -> Execution in progress
            -> Execution complete -- pending verification
              -> Done
```

Two-layer breadcrumbs:
1. **Tracker** — coordinator marks status before dispatch, commits it
2. **Stub document** — agent marks its own status as first action

With both layers, crash state is unambiguous. See `plugins/coordinator/ARCHITECTURE.md` for the full state machine.
