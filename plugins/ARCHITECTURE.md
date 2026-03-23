# Architecture — How the Agent Hierarchy Works

This document explains the conceptual model behind the oduffy-custom plugin system: why it exists, how the pieces fit together, and the design philosophy that shapes it.

## The Problem

Claude Code is a capable coding assistant, but by default it operates as a single undifferentiated agent. It writes code, reviews code, plans work, and executes plans — all in the same voice, with no structure for when to do what. This creates several problems at scale:

1. **No separation of concerns.** The same agent that writes code also reviews it, which is like asking an author to proofread their own manuscript.
2. **No workflow memory.** Each session starts fresh. Best practices (TDD, plan-before-code, verify-before-done) must be re-established each time.
3. **No specialization.** A single agent can't simultaneously optimize for "follow the spec faithfully" (executor) and "challenge whether the approach is right" (reviewer).
4. **Context window pressure.** A single long session accumulates context that degrades output quality. Delegating to fresh subagents keeps each agent's context focused.

## The Solution: Structured Roles

The plugin system addresses this by splitting Claude into **named roles** with distinct mandates, and connecting them through a **pipeline** with codified transition rules.

### The Roles

**Coordinator (EM / First Officer)**
The main session agent. Operates as engineering manager to the human's product manager. Orchestrates work, makes delegation decisions, verifies output, and manages the pipeline. Does not write implementation code directly — delegates to executors. Reserves its context window for decisions, not typing.

**Executor**
A fresh Sonnet-class subagent dispatched for each implementation task. Receives a well-specified stub (the enriched plan for one piece of work), implements it faithfully, runs validation, and reports back. Explicitly told: "you are the typist, not the architect." If the spec is ambiguous, it stops and escalates rather than guessing.

**Enricher**
A research subagent that surveys codebases, traces dependencies, and fills in the concrete details (file paths, function signatures, integration points) that a plan stub needs before an executor can implement it. Does not make architectural decisions — flags them for the coordinator.

**Reviewers** — each a named role with a distinct domain focus:

| Reviewer | Domain | Focus |
|----------|--------|-------|
| **Patrik** | Code quality, architecture, security | Correctness, documentation completeness, architectural soundness, error handling. Adversarial framing: assumes the code has defects. |
| **Zolí** | Ambition backstop | Challenges conservative recommendations when AI execution capacity changes the cost calculus. Only invoked as a backstop to Patrik, never as a primary reviewer. |
| **Sid** | Game development, Unreal Engine | Engine-appropriate patterns, Blueprint/C++ architecture, game performance, replication. Researches UE documentation rather than guessing. |
| **Palí** | Front-end architecture | Design system adherence, token validation, component patterns, CSS architecture. Pragmatic — "close enough" to design specs is often correct when it means using standard utilities. |
| **Fru** | UX flow review | Trust signals, clarity assessment, cognitive load, accessibility. Reviews user-facing features for whether they make sense to a human. |
| **Camelia** | Data science, ML/AI | Statistical validity, ML methodology, data quality, experimental design. Complements Patrik's engineering lens with quantitative expertise. |

### Why Named Roles?

The human names are ergonomic shorthand — saying "Patrik" is faster than "staff-eng with the code quality focus." What matters is the domain focus and review checklist each role carries. The value comes from coverage specialization, not identity.

## The Pipeline

### Full Feature Pipeline

```
 User describes what they want
           |
     [Brainstorming]         Skill: collaborative dialogue to refine idea into design
           |
      [Write Plan]           Skill: decompose design into bite-sized executable tasks
           |
     [Enrich Stubs]          Agent: enricher fills in file paths, code patterns, deps
           |
   [Review Enrichment]       Agent: reviewer validates enriched stubs before execution
           |
    [Execute Tasks]          Agent: executor implements each stub faithfully
           |
  [Spec Compliance Check]    Coordinator: did executor build what the stub specified?
           |
    [Code Quality Review]    Agent: Patrik (+ domain reviewer if applicable)
           |
   [Ambition Backstop]       Agent: Zoli challenges conservative recommendations (optional)
           |
      [Ship / Merge]         Skill: finish branch, create PR, merge
```

Each transition is explicit. The coordinator verifies output at every checkpoint before advancing to the next stage.

### Why So Many Steps?

The pipeline optimizes for **correctness over speed**. In AI-assisted development, the bottleneck isn't writing code — it's catching mistakes before they compound. Each pipeline stage is a checkpoint that catches a different class of error:

- Brainstorming catches **wrong direction** (building the wrong thing)
- Plan writing catches **wrong decomposition** (tasks too large, wrong order, missing dependencies)
- Enrichment catches **wrong assumptions** (file doesn't exist, API changed, pattern doesn't match)
- Execution catches **wrong implementation** (type errors, logic bugs, validation failures)
- Spec compliance catches **spec drift** (executor built something different than specified)
- Code review catches **quality issues** (naming, architecture, maintainability, security)
- Ambition backstop catches **unnecessary conservatism** (patching when refactoring is warranted)

### Staff Sessions (Agent Teams-Based Planning and Review)

The `/staff-session` command introduces a parallel-debate alternative to the sequential pipeline. Instead of the coordinator writing a plan and passing it through reviewers one at a time, staff engineers (persona agents) work as an Agent Teams team — debating simultaneously, challenging each other's positions, and converging on a consensus output.

**Two genres:**
- **Plan mode** — Staff engineers craft a detailed plan from PM/EM objectives. Replaces both the EM-authored plan and the plan-review gate.
- **Review mode** — Staff engineers collaboratively critique an existing artifact, producing synthesized findings with reinforced/unique/contested classifications.

**Three tiers:** Lightweight (falls through to single-reviewer `/review-dispatch`), Standard (2 debaters + synthesizer), Full (3-5 debaters + synthesizer).

The debate protocol (POSITION/CHALLENGE/CONCESSION/QUESTION messages) is structurally different from research cross-pollination (FINDING/CONTRADICTION). It models a deliberative process, not a discovery process — closer to a parliamentary debate than a research team.

### Lighter-Weight Paths

Not everything goes through the full pipeline. The system supports:

- **Direct execution** — For small, well-understood changes, the coordinator can skip brainstorming and planning
- **Single-session plan execution** — For plans that don't need enrichment, execute directly with the executing-plans skill
- **Review-only** — Route existing code to reviewers without the execution pipeline
- **Staff session** — For planning and review that benefits from multi-perspective debate (`/staff-session`)

## Design Philosophy

### Separation of Concerns via Subagents

Each subagent gets a fresh context window optimized for its specific task. An executor doesn't carry the weight of design decisions. A reviewer doesn't carry the weight of implementation details. This mirrors how human teams work — the person who writes code and the person who reviews it bring different cognitive states to the work.

### Skills as Codified Best Practices

Skills encode workflow knowledge that would otherwise need to be re-established each session. "Always brainstorm before building." "Always write a failing test first." "Always verify before claiming done." These aren't suggestions — they're codified as skills that the coordinator follows automatically.

The skill-discovery system ensures skills are checked before any action. Even a 1% chance a skill applies triggers a check. This prevents the common failure mode where Claude skips a workflow step because it "seemed simple."

### The Instruction Priority Hierarchy

When instructions conflict (and they will), the resolution order is:

1. **User's explicit instructions** (CLAUDE.md, direct requests) — highest priority
2. **Coordinator skills** — override default system behavior where they conflict
3. **Default system prompt** — lowest priority

This means the human always has the final word, but the coordinator's codified practices override Claude's default "just do it" tendencies.

### Context Window as Scarce Resource

The coordinator's context window is its most precious resource. Every file read, every subagent report, every decision eats into it. The dispatch threshold reflects this: delegate based on **context cost**, not task size. Even trivial tasks go to executors when the coordinator has concurrent work competing for context.

This is why the executor is Sonnet (fast, cheap, good at following specs) while reviewers are Opus (slower, more expensive, better at judgment). Match the model to the cognitive demands of the role.

## Boot-Time Behavioral Priming

The routing mechanism described below only works if the coordinator *actually uses it* — and by default, it doesn't. LLMs default to executing tasks directly rather than delegating to specialists, even when those specialists are fully described in reference documentation. Having the information is necessary but not sufficient; the agent also needs an *imperative instruction* to route rather than execute.

This is the role of the **capability catalog** (`coordinator/capability-catalog.md`): a ~220-token behavioral primer injected at every session start via the coordinator's `SessionStart` hook. Its header — "Specialists — Route, Don't Execute" — is the key line. The rest is a compact roster of available specialists with one-line routing guidance for each.

### Why Not Just Plugin CLAUDE.md Files?

Every plugin already has a CLAUDE.md describing its agents, routing rules, and capabilities in detail. But reference documentation and behavioral instruction are processed differently by LLMs. A CLAUDE.md says "here's how the world-builder agent works" — the model reads this as informational context. The catalog says "you have specialists with superior tools; before using a tool yourself, ask: would a specialist produce better results?" — the model reads this as a behavioral directive.

The catalog is the primer; the CLAUDE.md files are the deep reference. Both are needed. The catalog tells the EM *to route*; the CLAUDE.md tells dispatched agents *how to operate*.

### Design Decisions

**Universal emission.** The catalog includes all specialists (~220 tokens) regardless of which plugins are relevant to the current project. The alternative — per-project filtering with YAML parsing and section tags — was ~10x the complexity for ~70 tokens saved. A UE specialist entry in a web project's session start costs nothing; a missing specialist entry in a UE project's session start costs a wrong routing decision.

**Meta-mode exclusion.** When working on the orchestration infrastructure itself (the `~/.claude` repo, `project_type: meta`), the catalog is suppressed. The EM is editing the very agent definitions it would otherwise route to — it should execute directly, not delegate to specialists whose system prompts it's modifying.

**Graceful degradation.** If the catalog file is missing, the hook emits nothing and no error. Rollback is a single file deletion.

## How Routing Works

The review dispatch system uses a **composable routing table**:

1. The coordinator plugin defines universal reviewers (Patrik, Zoli) in its `routing.md`
2. Each enabled domain plugin contributes a routing fragment (e.g., game-dev registers Sid)
3. At dispatch time, `/review-dispatch` merges all fragments into a composite table
4. The changed code's signals (front-end? game logic? architecture?) determine which reviewer gets it
5. If no domain reviewer matches, Patrik handles it (universal fallback)

This is extensible — adding a new domain (e.g., mobile-dev) means creating a new plugin with a routing fragment and an agent definition. The coordinator doesn't need to change.

### The Sequential Review Protocol

For post-execution code review and per-stub enrichment reviews:

1. Domain specialist reviews first (if signal matches)
2. Coordinator incorporates feedback
3. Patrik catches regressions (generalist pass)
4. Zoli challenges conservatism (backstop, when warranted)

This mirrors how real teams work: the domain expert reviews for correctness, then a senior generalist reviews for quality and architecture.

**For pre-chunking plan review and collaborative planning**, the system offers an alternative: **staff sessions** (see above). These use parallel debate instead of sequential critique — reviewers talk to each other directly, challenging and conceding in real time. The sequential protocol was originally an optimization to avoid duplicate findings and wasted context; Agent Teams changes this tradeoff by enabling direct inter-agent communication.

### The Write-Ahead Status Protocol

Every phase transition in the pipeline follows a **write-ahead** pattern: mark the document *before* starting work, then update it *after* completing. This is the same principle as a database WAL (Write-Ahead Log) — if a session crashes mid-phase, the document shows "in progress" rather than misleading "not started," eliminating expensive post-crash triage.

The protocol operates on two layers:

1. **Tracker README** — The coordinator marks status before dispatching any agent and commits the update. This is the WAL record: it must persist before agents launch.
2. **Stub/plan document header** — The agent marks its own status line as its first action after reading the document. This creates a second breadcrumb inside the document itself.

With both layers, crash state is unambiguous:
- Tracker says "in progress" but stub says "pending" → agent never started (coordinator dispatched but agent crashed on init)
- Both say "in progress" → agent was mid-work (check enrichment findings or partial code for progress)
- Stub says "complete" but tracker still says "in progress" → agent finished but coordinator crashed before updating tracker

Status values flow through a defined state machine:

```
Pending enrichment
    → Enrichment in progress
        → Enriched — pending review
            → Under review by [Name]
                → Enriched and reviewed
                    → Execution in progress
                        → Execution complete — pending verification
                            → Done
```

Any phase can also transition to `Blocked — [reason]` and back.

## Key Architectural Decisions

**Why plugins, not a single CLAUDE.md?**
Modularity. Game dev agents and MCP servers shouldn't load when working on a web project. Plugins can be toggled per-project. The coordinator is always-on; domain plugins are opt-in.

**Why disable Superpowers and absorb selectively?**
Superpowers is a general-purpose skill framework. We wanted named agents, a specific review pipeline, and the First Officer organizational model. Rather than fight Superpowers' defaults, we absorbed the valuable parts (workflow skills, design guidance) and built our own orchestration layer.

**Why named reviewers instead of generic "review this code"?**
Reproducibility. "Patrik, review this" produces consistently different output than "review this code." Named characters with written mandates create stable perspectives that the human can learn to predict and trust.

**Why Sonnet for executors, Opus for reviewers?**
Executors follow specs — speed and cost matter more than judgment. Reviewers make judgment calls — depth of analysis matters more than speed. Match the model to the cognitive demands.

## Authors

Dónal O'Duffy & Claude
