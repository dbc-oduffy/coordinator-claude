# coordinator-claude

**A PM-native operating layer for AI engineering work.** An opinionated Claude Code plugin that turns product intent into scoped plans, delegated implementation, evidence, and ship/no-ship decisions. You're PM. Claude is EM. You stay technical enough to spot when something's wrong; the EM handles the rest.

**v4.0.0 is a much larger system than 3.x, not a port of it.** The doctrine half grew triggers and guards that run work no earlier version ran at all; the routines that used to be a written checklist the model had to notice and follow now compute their own next step from what is actually on disk. Doctrine that was hundreds of lines of prose is dozens of lines plus Python that enforces rather than suggests. The engine that does the enforcing lives in a separate repo, [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter), and is a hard dependency — which is also the release's real cost. Read [What a doctrine-only install gets you](#what-a-doctrine-only-install-gets-you) before you rely on an install without it.

## Who This Is For

You don't need to write code. You need to know enough to evaluate it — to spot when something smells wrong, to ask the right questions, to set direction. Amjad Masad (Replit's founder) [opined](https://youtu.be/PlDeqGQZ0CQ) that people who *don't* program may actually be better positioned for the LLM-coding world: they won't micromanage implementation. This plugin leans into that. It gives Claude standing authority to make engineering decisions — how to build, who to delegate to, when to refactor — while you hold product authority: what to build, what to cut, what ships. Just like an EM-PM dynamic.

What this system asks of the PM is altitude, not tactics. Architectural judgment, scope decisions, refactor-vs-patch calls, what-ships-and-what-doesn't. Slop is fought on the *plan* level — by treating each plan as an exhaustive software design document with named-reviewer pushback baked in, not by spot-checking commits afterward. The natural model defaults — act fast and move on, defer P2s into oblivion, size work in human-sprint timeframes — are the things this system is built to push back against. The PM sets direction; the EM and the named reviewers do the pushing.

This isn't a collection of prompt tricks. It's a **decision architecture**: routines (session orientation, plan review, multi-source code review, structured handoffs, daily flows) plus authority boundaries (EM owns implementation, PM owns scope/ship) plus reviewer personas that push back with fix-gates between them. Reviews are meaningful — blocking findings, not theatre. And the system actively reads its own accumulated wikis and lessons before drafting new plans (`prior-art-checker` pre-flight, `/learn-lessons` triage), so the scar tissue from past decisions informs the next one rather than sitting in a write-only memory file. It maps to how PM-EM collaboration actually feels in a real engineering team. The difference is that your "team" can work autonomously for hours, and you can review the output when you're ready.

## What This Is *Not*

- **Not another agent framework.** Claude Code already has subagents, plugins, skills, hooks, and MCP. This sits *on top of* that infrastructure — it doesn't compete with it.
- **Not a PRD-to-code pipeline.** Product intent is captured inside plan mode and acceptance criteria, not in a separate PRD funnel.
- **Not an autonomous coding agent.** The PM is in the loop on scope, tradeoffs, and ship decisions by design. Autonomous modes (`/mise-en-place`, `/autonomous`) exist for execution sprints, not for product authority.
- **Not a developer productivity tool.** The target user evaluates engineering work — they don't write it. If you want to be more productive at writing code yourself, you want vanilla Claude Code; this is for managing AI engineering work, not doing it.
- **Not a self-contained install any more.** As of v4.0.0 the executable half is a separate repo. That is a real cost and we'd rather you learn it here than by hitting the seam.
- **Not open source in the OSI sense.** Apache-2.0 with a Commons Clause rider — **source-available.** Use it at work, modify it, redistribute derivative works; you just can't resell the software itself. Same licence on both repos. See [LICENSE](LICENSE) and [COMMERCIAL.md](COMMERCIAL.md).
- **Not aimed at the fully non-technical PM** (yet). The current sweet spot is a PM with technical altitude but not technical hands — someone who has architectural judgment, recognizes unwise plan-shape, and can spot when a plan, an architectural choice, or a tradeoff sounds wrong from how the EM describes it, without ever reading a diff. The PM does not review commits, does not perform code review, does not sign off on PRs. That altitude is the load-bearing constraint: code review and PR sign-off are delegated to AI peers and named-persona staff-tier reviewers (see below). Complex codebases require a PM who can tell when something looks wrong from the conversation, not from the patch.

🤖 Agents: start here → [AGENTS.md](AGENTS.md)

## What v4 Does That 3.x Couldn't

"Who This Is For" above claims this is a decision architecture rather than a bag of prompt tricks, and that slop is fought at the plan level rather than spot-checked afterward. In 3.x that was substantially an aspiration: the architecture was described in prose, and prose only governs if the model notices it and chooses to apply it, every time, in every session. v4 is the release where most of it became mechanical. That is the leap — the bash→Python work and the two-repo split further down are how it was achieved, not what it is.

**The doctrine half gained triggers that run work no earlier version ran.** 87 hook scripts, all Python, wired into 42 registered hook entries across nine lifecycle events. They are not "more automation" — they do things a checklist cannot. A session *routes itself*: an unsized ask gets caught before it reaches implementation, and resuming work or starting an autonomous run fires from state rather than from you remembering the command. Dispatch is shaped at the moment of the call: the orchestrator gets pushed off work that belongs in a subagent, pointed at the cheapest model tier that can do the job, and caught when a dispatched agent returns having used no tools at all — a silent-failure mode that previously just looked like success. Role integrity is asserted at runtime, so a subagent that has read the doctrine cannot conclude it is the manager. Foreign-platform path assumptions are refused at the point of writing rather than found on someone else's machine. And the system polices its own doctrine: prose that has drifted into changelog-style narration, instruction files that have grown past their budget, and citations that no longer resolve are all caught by hooks rather than by a reviewer noticing.

**Skills compute their own next step instead of being walked by hand.** A new generation of skill moved the branching out of prose entirely: a read-only operation reads disk, git, and artifact frontmatter and returns the whole routing as one decision object, collapsing the model's job to the judgment the object could not resolve. `/pickup` is the first conversion and the pattern the rest of the frontage is being moved onto. Honest scope: this is a live migration, not a finished one, and the older prose decision-tree shape is **not** deprecated — it remains the correct shape for judgment-dense, low-frequency skills, where there is no mechanical branch inventory to compute.

**Hundreds of lines of prose became dozens, plus Python that enforces.** This is a quality argument before a size one. An instruction reaches an agent by one of four routes — the config files every session reads on boot, invocation, hook injection, or the prompt itself — and only the last is under a human's control at the moment it matters. The rest are text the model must notice and choose to apply, and every one of them is read on boot whether or not it gets used, so a *more* robust prose architecture is also a more expensive one to run. Prose is also untestable, and it drifts by copying: the same paragraph in forty agent bodies has already diverged, and fixing the bug means finding all forty. So the governing test became *for every rule, what artifact discharges it?* — where "the operator remembers" is not an answer. Agent bodies came down roughly 31.5% fleet-wide with a size ratchet underneath them to stop the regrowth; guard and advisory messages have a runtime-enforced length cap; per-command file-write hook processing folded from eight passes to two. The doctrine got shorter *and* sharper, because what was left after the bookkeeping moved out was almost entirely judgment — which is the thing large models are actually good at reading.

**What this costs is on the same page as what it buys.** v4 ships a materially smaller safety surface in this repo than 3.x did, and the engine is a second install. Both are set out plainly in [What a doctrine-only install gets you](#what-a-doctrine-only-install-gets-you) and in [CHANGELOG.md](CHANGELOG.md); neither is a footnote.

## Two Repos, One System

This used to be one thing: a plugin full of prompt text. It is now two things, and the second one is not a plugin at all.

- **`coordinator-claude`** (this repo) — the doctrine. Skills, agents, commands, hooks, personas, wikis. Text a model reads. **This is what an agent experiences.**
- **[`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter)** — the engine. A Python package, `coordinator_core`, that produces and mutates the authoritative on-disk work-state and computes the answers doctrine would otherwise have to ask someone to remember. It owns mechanism, not meaning. It is not a successor to this repo and it does not own doctrine.

The reason for the cut is that an operating system for AI engineering work has to do two unlike things. **Judgment** — should this be planned or just done? is this reviewer's finding real? — is genuinely a language problem, and belongs in prompt text. **Bookkeeping** — claim this handoff, stamp that frontmatter, compute which commits in this range have review coverage — has exactly one correct answer, and prompt text is the wrong substrate for it: it is re-derived at full inference cost every session, it cannot be unit-tested, and it drifts by copying into forty agent bodies that have already diverged. So: if an operation has one correct answer, it belongs in code that can be tested; if it requires judgment, it belongs in text a model reads. The engine is where the first kind went.

What that buys, concretely: a bug in a state operation gets fixed once instead of in every copy of a paragraph. State becomes checkable — the engine emits files you can read, diff, and assert against, rather than a claim the model makes about what it did. Multi-OS support becomes a property of one Python codebase instead of something every shell-shaped instruction has to re-earn. And the doctrine got *smaller and sharper*, which we did not anticipate: once the bookkeeping left, what remained was almost entirely judgment, which is what large models are actually good at reading.

**The full argument — including the cost side, and the one rule that governs the seam — is [docs/wiki/manifesto.md](docs/wiki/manifesto.md).** It is an argument, not a proof, and it says so.

### What a doctrine-only install gets you

Graceful degradation here is a clean line, not a fallback mode that half-works: **you lose the state machine, you keep the judgment.**

| Works without the engine | Needs the engine |
|---|---|
| Plan review, persona review, shaping, brainstorming | Claiming and reconciling handoffs |
| Reasoning about a diff | Resolving cross-repo memos |
| The sizing gate's judgment call | Stamping an artifact terminal |
| Session orientation from what's already on disk | Computing review coverage across a commit range |
| | Goals/roadmap emission, review-trail writes, release ops |

Most of the mutating flows are in the right-hand column. Of the 36 bundled skills, the large majority touch engine-installed surface in some form, so the honest summary is that ceremony-cadence work expects the engine present and judgment work does not.

**There is also a safety cost, and it is not cosmetic.** v4.0.0 deleted roughly 20 `block-*` guard hooks from this repo and moved their logic into `coordinator_core.write_guards`, which ships in the engine. **An install running only this repo has none of those guarantees** — no destructive-`rm` guard, no destructive-git guards, no `--no-verify` block, no subagent write-sandbox confinement, no plan-body or archive write protection. Three `block-*` hooks remain here, and all three are dispatch/workflow-shape guards, not destructive-action guards. Installing the engine restores the rest. We would rather state this loudly than soften it.

## Quick Start

You don't install this — your agent does. Open Claude Code in any project and paste:

```
Install coordinator-claude. The playbook is at
https://github.com/dbc-oduffy/coordinator-claude/blob/main/docs/agent-install.md
— read it, follow it, then install the engine from
https://github.com/dbc-oduffy/claude-klabauter (its INSTALL.md), and queue
/coordinator:repo-setup as the immediate next step after I restart Claude Code.
```

**The order is load-bearing.** This is the single thing most likely to break a new install:

1. **Install this plugin.** `claude plugin marketplace add dbc-oduffy/coordinator-claude`, then `claude plugin install coordinator@coordinator-claude`. The marketplace is the public GitHub repo, not your clone, so the install lives entirely under `~/.claude` — delete or move the clone afterward and the plugin keeps working.
2. **Restart Claude Code.**
3. **Run `/coordinator:install`.** This finishes the environment wiring, including depositing the `machine-local` registry resolver. Until it has run, the resolver is only a forwarder that exits 127 with `resolver not installed`.
4. **Install the engine.** Clone [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter) and follow its [`INSTALL.md`](https://github.com/dbc-oduffy/claude-klabauter/blob/main/INSTALL.md) — `python3 <klabauter-clone>/scripts/setup.py --i-am-agent` for an agent, `python3 <klabauter-clone>/scripts/setup.py` for a human, `--check` for a no-side-effects check. On Windows: `python <klabauter-clone>\scripts\setup.py`, same flags.
5. **Run `/coordinator:setup`.** The install-chain walker; it verifies the engine actually resolves and emits a chain-complete banner, or fails loud with remediation.
6. **Run `/coordinator:repo-setup`.** Bootstraps tracking infrastructure in your project.

**Do not substitute `pip install .` for step 4.** It works as an ordinary library-dependency install, but it skips the dependency check and registration the real installer performs, and leaves you with an engine that imports but is not set up.

**Do not start at step 4.** Installing the engine before this plugin's install has completed produces exit 127 and a remediation instruction that cannot succeed until step 3 is done.

**Auditing & uninstall** → [`docs/safety.md`](docs/safety.md) — what the install changes, what it does not do, audit commands, and exact uninstall steps.

**Why it's built this way** → [`docs/wiki/manifesto.md`](docs/wiki/manifesto.md) — why the system is split into a doctrine plugin and a separate engine, what the split buys, and what it costs.

**What we actually measured** → [`docs/evidence.md`](docs/evidence.md) — the experiments behind the design, including the ones that reversed a position we'd already written down, and an explicit line between what was measured and what changed on a single observed failure.

**Updating** → `/coordinator-update` checks whether a newer version has been published, computes a classified delta against your live install, and advises a migration path that preserves your customizations by default (renamed reviewer personas, per-project config, any structural divergence) — it never blind-overwrites. It's PM-invoked and advisory only: it computes and recommends, it doesn't apply anything without your explicit say-so.

## Prerequisites

Only two things are needed to *begin* — `git` and the Claude Code CLI. The rest are resolved as the install walks.

| Requirement | Why |
|---|---|
| `git` | Required. |
| Claude Code CLI | Required — `npm install -g @anthropic-ai/claude-code`. The canonical runtime, preferred over the desktop app. |
| **Python 3.11+** | Required. The plugin's hooks are Python, and the engine is a Python package. On Windows, **first** disable the Store `python`/`python3` App Execution Alias stubs (Settings › Apps › App execution aliases) — left on, `python3` resolves to a shim and every diagnostic afterwards misleads you. |
| `gh` (GitHub CLI) | Required for the merge/release ceremonies. |
| `node` | Only for the ceremony-gate JavaScript test suite. Nothing in the daily loop needs it. |
| `bash` | **No version floor.** Earlier releases required bash 4.3+; the script that justified it was ported to Python and the requirement is gone. The installer may still remark on bash on macOS's stock 3.2 — it is a remark, not a blocker. |

**Claude Code version:** tested with 2.1.186 via the native `claude plugin` CLI. A minimum has not been formally established.

**Platforms:** macOS, Linux, WSL, and Windows are all first-class targets. **The tested matrix is macOS and Linux** — Windows is supported and actively hardened but not yet in the tested matrix, so treat a Windows-only failure as a bug worth reporting rather than expected behaviour.

## Upgrading from an earlier release

**If you installed coordinator-claude before, you almost certainly have v2.7.0 (2026-06-01) or earlier** — that is the newest release this repo ever published. There was no public v3.x release. Everything between v2.7.0 and v4.0.0 lands on you at once, so read this list rather than assuming a version-number-sized jump.

**The one that will actually break your install:** the distribution went from **five plugins to one**. v2 shipped `coordinator`, `web-dev`, `data-science`, `deep-research`, and `notebooklm` as separate marketplace entries. They are now folded into a single `coordinator` plugin at the repo root, and the separate entries are retired. **You change what you install, not just your version** — install `coordinator@coordinator-claude` and nothing else.

Then, in rough order of how likely it is to bite:

- **The engine is now a separate, required repo.** See [Two Repos, One System](#two-repos-one-system). This is the largest structural change in the product's history.
- **Roughly 20 `block-*` safety hooks were deleted from this repo**, with their logic moved to the engine. A doctrine-only install is materially less guarded than v2.7.0 was. Detail above.
- **Every executable path was renamed.** About 360 files went from `.sh` to Python, and most of that surface relocated into the engine. Anything of yours that names a `.sh` path, or a `bin/<name>` location, is stale. The `sh`/`python` polyglot trampolines that briefly preserved old invocations were deleted outright — that carve-out was reconsidered and rejected.
- **Handoff records changed vocabulary.** `status: active | consumed` → `status: open | claimed`; `consumed_at`/`consumed_by` → `claimed_at`/`claimed_by`; `deployment_state: abandoned` → `continued | closed`, where `closed` carries a `closed_reason` of `cancelled`, `displaced`, or `stale`. Existing records are migrated, and the archived-handoff schema still reads the legacy values for old archived records. If you built anything that reads handoff frontmatter, it needs updating.
- **The lifecycle commands were renamed, and the deprecation aliases are gone.** `/session-start` is now `/workstream-start`, `/session-end` is `/workstream-complete`, `/project-onboarding` and `/bootstrap-repos` are `/repo-setup` (the latter with `--batch`), and `/coordinator:setup` no longer scaffolds a repo — that is `/coordinator:repo-setup`, and `/coordinator:setup` now unambiguously means the install-chain walker. The full table is in [CHANGELOG.md](CHANGELOG.md) under *Upgrading from v2.7.0*.
- **`coordinator:review-code` is retired** in favour of `coordinator:review --surface diff`. The `/review-code` slash command still resolves — it is a redirect shim now, not an independent pipeline.
- **`coordinator-schema-version` went v1 → v2**, and the artifact shapes were restandardized across the record family. Anything consuming coordinator record contracts should target the current schemas under `schemas/` and `cockpit-contract/schema/`.
- **`superseded` was retired as a handoff status** (before the v4 vocabulary change above), and the `code-architect` agent was removed — nothing ever dispatched it, so there is no migration.

New in the same span, worth knowing about: the sizing gate (below), first-class weekly goals/OKRs, a durable priority ledger that survives across sessions, automated checks on where a plan's stated justification actually came from, and enforcement — not just documentation — of the rule that text arriving inside tool output is never a command.

Full detail, including the parts we got wrong and corrected in place: [CHANGELOG.md](CHANGELOG.md).

## How a Session Works

Most tools hand you a bag of commands and wish you luck. This system has *routines* — woven into the session lifecycle so you don't have to remember them. Some fire automatically via lifecycle hooks (boot orientation, the context-pressure nudge); the rest are one-keystroke ceremonies the EM runs at the right moment. The distinction matters: *hooks* are what actually fire on their own; the slash commands below are invoked — by you, or by the EM on your behalf.

**Starting up.** When Claude opens a supported project, a `SessionStart` hook fires automatically — loading the current branch, pending handoffs, lessons from past sessions, project vitals, and an orientation cache. No cold start. Claude lands in the middle of the context window where performance is strongest, with forward-looking state already loaded. This is deliberate: research shows LLMs degrade toward the end of their context and, to a lesser extent, at the beginning ([Liu et al. 2023, "Lost in the Middle"](https://arxiv.org/abs/2307.03172)). The orientation hook front-loads context so the working session occupies the optimal window. The cache is now fresh by construction — it self-heals at boot rather than depending on a ceremony being invoked.

**Sizing, first.** Before anything gets planned, shaped, or dispatched, every ask passes through a sizing gate — a cheap t-shirt-size read against disk state that decides where it goes: a tiny fix is a direct edit, a vague or multi-subsystem ask routes to `/brainstorming` to converge on requirements, a shaped problem with real decision weight routes to `/plan`, and something needing PM-side scope alignment first routes to `/shape`. This is the EM's *first move* on a novel ask, not an optional pre-check — it's how a session begins, not a separate ceremony you invoke.

**Planning.** You describe what you want. Claude enters plan mode — but the plan isn't just written and executed. You review it. In a real dev team, the PM doesn't just say "build auth" and disappear; they review the spec, push back on scope, ask about edge cases. That's what happens here. The `coordinator:plan` skill is a decision-tree super-skill (triage → substrate → compose → exit) that mechanically binds the trigger word "plan" to the full pipeline: the prior-art-checker pre-flight cross-references the plan against accumulated wikis, lessons, and improvement queues to surface conflicts *before* an Opus reviewer touches it; the Staff Engineer then reviews; the integrator applies findings. For bigger decisions, `/staff-session` spawns role-based engineers who independently develop positions and debate to consensus — like pulling your tech lead and director of engineering into a room.

**Building.** Claude delegates to Sonnet subagents for implementation — cheaper, faster, fresh context. A `PreToolUse` hook nudges Claude away from doing implementation work directly, because the orchestrator's context is too valuable to spend on writing code. This is the same principle as a real EM: you don't want your engineering manager writing production code when they should be coordinating.

**Reviewing.** Code review comes from named personas with rich behavioral profiles — a domain expert reviews first (e.g., a web-dev specialist for front-end work, or a data-science specialist for ML pipelines), all findings are applied, then a generalist reviews the clean artifact. Sequential, with mandatory fix gates. Research supports both the persona mechanism (literature-backed for judgment-routing tasks; for mechanical bug-finding our own controlled experiment found no recall gain — that's why bug-sweeps use bare agents) and [multi-agent review gains](https://www.anthropic.com/engineering/multi-agent-research-system) (Anthropic's own eval showed 90.2% improvement over single-agent). Plan-review with personas — the system's main use of named reviewers — leans on industry-standard PRD/SDD review patterns; we have not separately benchmarked it. Reviewers are identified by stable role name rather than a hardcoded persona name, which fixed a real bug where renaming or removing a reviewer agent silently produced meaningless feedback.

**Staying coherent.** Long sessions hit a hard constraint: context compaction. When triggered, the model summarizes what it *thinks* happened — a retrospective reconstruction that loses intent. A `PostToolUse` hook monitors context pressure and prompts Claude to create a structured handoff *before* compaction fires: decisions made, state reached, explicit next steps. Each handoff chains forward from its predecessor. Research shows structured handoffs significantly outperform automatic summarization ([Kang et al. 2025, ACON](https://arxiv.org/abs/2510.00615); Sourcegraph [retired compaction](https://sourcegraph.com/blog) in their Amp agent in favor of explicit handoffs after measuring degradation).

**Navigating the codebase.** This system invests heavily in documentation-as-navigation. Claude's natural mode is grep-heavy — searching text, reading prose, following paper trails. An architecture atlas, project tracker, orientation caches, and structured comments throughout the codebase give Claude something to *find* when it searches. We call this "grep bait." It's why the doc maintenance pipeline and architecture atlas exist: not bureaucracy, but navigation infrastructure that lets Claude plan from 60 lines of orientation instead of reading 20 source files cold. Research artifacts, lessons files, and handoff documents all serve double duty — they record decisions *and* create searchable landmarks for future sessions.

**Wrapping up.** `/workstream-complete` captures lessons, updates documentation, and commits state. `/workday-complete` goes further: syncs docs, merges to main via PR, and optionally hibernates the machine. The cycle is continuous — each session starts where the last one left off.

**A tier above the workstream loop.** Everything above operates at the level of one ask, one plan, one merge. Goals/OKRs sit a level up: a per-repo goal artifact (`state/goals/<slug>.yaml`) records the strategic objective an initiative serves and tracks whether the fleet is winning against it — not "did this ship" but "did it move the number." Weekly priorities are first-class goal artifacts of their own, wired into session orientation. `/roadmap-planning` shapes raw research or intent into a ratified, graphed roadmap of batons that later plans and workstreams draw from, so a session doesn't have to re-derive "why are we doing this" from memory. This altitude is PM-gated by design — direction lives with the PM, not something the EM infers from ticket volume.

## What You Need to Remember

The EM handles most of this on its own. Your key moves:

| Command | When | What It Does |
|---------|------|-------------|
| `/workstream-start` | Beginning of work | Deliberate orientation — triage handoffs, surface staleness, choose work. PM-invoked; *not* auto-fired. (Boot context loads automatically via a separate `SessionStart` hook; this command is the optional deeper orient.) |
| `/pickup` | Resuming work | Load a handoff artifact and continue where you left off |
| `/handoff` | Stepping away | Save session state for the next session |
| `/staff-session` | Big decisions | Multi-perspective planning or review from persona-based contributors |
| `/mise-en-place` | Heads-down time | Claude burns through the backlog autonomously — no input needed |
| `/autonomous` | Override | Suppress handoff nudges when you want Claude to push through compaction |

That's it for daily use. Everything else — delegation, review routing, doc maintenance — the EM drives as part of its workflow; context-pressure management is the one piece handled automatically, by a `PostToolUse` hook. You don't have to ask for any of it.

## Flows

Don't memorize commands; learn five flows. Most of what the system does, you'll touch through one of these.

**Flow 1 — Build a feature.** You describe intent → Claude enters plan mode and proposes acceptance criteria + scope mode → you review and approve → Claude delegates implementation → reviewers (domain expert first, generalist second) check the artifact with fix gates between → for user-visible work or patches that smell like they should be refactors, **the VP-Product Reviewer** (`coordinator:vp-product`) — scope challenger, naming optional via `/coordinator:install` Phase 6 — stress-tests the choice → `/merging-to-main` produces a ship verdict and you decide.

**Flow 2 — Fix a bug.** Reproduction first (don't trust the report) → root cause via the [systematic-debugging guide](docs/wiki/systematic-debugging.md) → scoped fix in production-patch mode (minimal diff, no opportunistic refactors) → regression check → reviewer → merge. For codebase-wide grinds, `/bug-blitz` autonomously works through the bug backlog with EM-serial commits at each wave gate.

**Flow 3 — Resume work.** The boot `SessionStart` hook automatically loads orientation, lessons, and pending handoffs into context → optionally run `/workstream-start` for a deeper triage → you pick up via `/pickup <handoff>` or pick from the menu → Claude lands mid-context and starts where the last session stopped.

**Flow 4 — Autonomous sprint.** `/mise-en-place` gathers ready work, builds a compaction-proof flight recorder, and executes through the backlog without stopping. `/autonomous` suppresses handoff nudges when you want it to push through context pressure.

**Flow 5 — Architecture change.** `/staff-session plan` (multi-perspective debate) → migration plan with rollback → architecture mode review → implementation → verification → architecture atlas update via `/update-docs`.

**Closing the day:** `/workday-complete` validates, syncs, runs the daily review, and merges. `/workweek-complete` is the larger weekly ceremony with version bump and release notes — and it's the only place `/parallel-code-review` runs. That command is the pre-merge gate: it chunks the week's diff across parallel reviewer dispatches instead of one reviewer reading everything serially, then folds their findings into a single ship/no-ship verdict. It's deliberately *not* available outside `/workweek-complete` — a weekly gate invoked ad-hoc stops being a gate.

## How heavy is the workflow?

The system scales — a typo fix is a two-word instruction; a system rewrite is a multi-agent pipeline. Here are three representative tiers:

| Tier | Skill / command | Reviewer | Wall time |
|------|-----------------|----------|-----------|
| **Tiny edit** (typo, constant, rename) | Direct EM edit — no plan | None required | < 5 min |
| **Feature** (new command, new skill) | `/execute-plan` after PM approves a plan | Domain reviewer → the Staff Engineer (`coordinator:staff-eng`) generalist; the Director of Engineering (`coordinator:eng-director`) as backstop at High effort (sequential) | 30 min – 2 hrs |
| **System rewrite** (multi-plugin overhaul) | `/staff-session plan` → `/execute-plan` (with executor dispatch per [`docs/wiki/delegate-execution.md`](docs/wiki/delegate-execution.md)) | Full sequential chain + PM ship verdict | Half day+ |

<details>
<summary><strong>All Commands (appendix)</strong></summary>

The plugin ships **46** commands. Listed below are the 45 that are useful in a consumer install, grouped by where they sit in a session. The 46th, `/percolate`, publishes a working tree to a downstream mirror repo — it is a maintainer tool for shipping *this* project and has no use in an install that is the target of a publish rather than its source.

**Session cadence**

| Command | Purpose |
|---------|---------|
| `/workstream-start` | Orient session — preflight, load context, choose work |
| `/workstream-complete` | Wrap up finished work — capture lessons, update docs |
| `/workday-start` | Morning orient — triage handoffs, surface staleness, align priorities |
| `/workday-complete` | End-of-day wrap — validate, consolidate branches, review, changelog |
| `/workweek-start` | Weekly orient — review last week, set this week's priorities |
| `/workweek-complete` | Weekly release ceremony — validate, docs, release notes, merge |
| `/quick-wrap` | Short session close: commit, handle loose ends, stop — not `/workstream-complete` |
| `/pickup` | Resume from a handoff or action a cross-repo memo — grab the baton |
| `/handoff` | Mid-workstream save-state under context pressure — always a continuation |
| `/spinoff` | PM-gated: fork a mid-session topic into its own handoff |
| `/autonomous` | Toggle autonomous mode — suppresses handoff nudges near compaction |

**Intake — sizing, shaping, planning**

| Command | Purpose |
|---------|---------|
| `/brainstorming` | Shapes vague or multi-subsystem asks into requirements before planning |
| `/shape` | Converge with the PM on a problem's shape before any solutioning |
| `/plan` | Decision-weight planning: multi-file, abstraction, cross-system, agent scaffold, reversed prior |
| `/staff-session` | PM-gated: Agent Teams review for architecture calls (plan or review mode) |
| `/roadmap-planning` | PM-gated: shape research into a ratified, graphed roadmap of batons |
| `/research` | PM-gated deep research — web, repo, or structured |
| `/notebooklm-research` | PM-gated: NotebookLM research for video/audio sources |

**Execution**

| Command | Purpose |
|---------|---------|
| `/execute-plan` | Executes a PM-approved plan via dispatched per-chunk executor waves |
| `/enrich-and-review` | Runs the enrichment pipeline over plan chunk directories |
| `/mise-en-place` | Autonomous backlog run — flight-recorder prep, then run-through |
| `/dogfood` | Fix-through loop — invoke a new thing, fix bugs until it works |
| `/new-project` | Scaffolds and onboards a new repo (vs. `/repo-setup`'s onboard-existing) |
| `/repo-setup` | First-time setup for an existing repo, single or fleet-wide (`--batch`) |
| `/systematic-debugging` | Root-cause one known bug — reproduce, trace to source, fix, verify |

**Review and merge**

| Command | Purpose |
|---------|---------|
| `/review` | Review a plan/design doc or code diff — findings land on either one |
| `/review-code` | Redirect shim → `/review --surface diff`. Retired as an independent pipeline in v4.0.0; the command still resolves |
| `/parallel-code-review` | Weekly pre-merge code-review gate — chunk reviewers, one verdict. `/workweek-complete` only |
| `/plan-delivery-audit` | Triangulate plan claims against code and reviews for delivery status |
| `/architecture-audit` | Rotational arch audit — score systems, audit the top, package spinoffs. Never edits code |
| `/architecture-survey` | Build or refresh the architecture atlas via scout, analyst, synth |
| `/merging-to-main` | Merges a ready branch to main — release notes, PR, CI wait, cleanup |
| `/finishing-a-development-branch` | Presents merge, PR, or cleanup options once tests pass |
| `/consolidate-git` | Cleans up branch sprawl — consolidates and prunes stale branches |
| `/validate` | Run the project's fast test command at a cadence gate |

**Backlog and health**

| Command | Purpose |
|---------|---------|
| `/bug-sweep` | Codebase bug hunt — find and fix AI-fixable bugs, defer the rest |
| `/bug-blitz` | Grind the bug backlog and tests; fix small, surface big items to PM |
| `/debt-triage` | EM-PM ceremony to review and prioritize the technical debt backlog |
| `/code-health` | Night-shift code review — dispatch reviewer, apply findings, track |
| `/cruft-sweep` | Scan for reclaimable scratch and orphans; apply only if confirmed |
| `/learn-lessons` | Processes lessons/ entries as doctrine change-requests, local or central |
| `/distill` | Distill session artifacts to wiki and decisions; archive specs, drop scratch |
| `/update-docs` | Sync all documentation artifacts to the current codebase state |

**Install and lifecycle**

| Command | Purpose |
|---------|---------|
| `/install` | Installs the coordinator plugin — checks prereqs, configures project |
| `/uninstall` | Reverses the coordinator install — full removal or revert to marketplace |

Two more verbs ship as skills rather than commands, so they aren't in `commands/` and don't appear in the count: `/coordinator:setup` (the install-chain walker — see Quick Start step 5) and `/coordinator-update` (see [Updating](#quick-start) above).

</details>

<details>
<summary><strong>How this maps to real teams</strong></summary>

| Real Team Practice | coordinator-claude Equivalent |
|--------------------|-------------------------------|
| **Daily standup** | `/workstream-start` — what happened, what's blocked, what's next |
| **Sprint planning** | `/staff-session plan` — persona-based engineers debate approach |
| **Spec review** | Plan mode with PM sign-off — Claude proposes, you approve |
| **Code review** | `/review --surface diff` — domain expert first, generalist second, fix gates between |
| **Tech lead gut-check** | Any reviewer can be dispatched ad-hoc for a quick assessment |
| **Retrospective** | `/workstream-complete` — capture lessons, update docs |
| **Handoff between shifts** | `/handoff` — structured state capture, not "check the git log" |

The one role we don't have deeply embedded in workflows: **designer.** Meatspace designers are still better at that, and their judgment is going to remain difficult for LLMs to replicate. There's a vibe-design functionality, but it's not gonna rock your world.

</details>

<details>
<summary><strong>Under the hood — architecture details</strong></summary>

**Inverted capability delegation.** The coordinator sees ~8 thin MCP tools; domain agents access 40+ via proxy with full schemas. This saves ~40K tokens from the coordinator's context and forces delegation by design. A `PreToolUse` hook nudges the coordinator when it reaches for domain tools directly.

**Proactive artifact generation.** Before compaction fires, a hook prompts structured handoff creation — a prospective document capturing decisions, state, and next steps. Each artifact chains from its predecessor (cascade obligation) and opens with a synthesis of the prior handoff (anti-amnesia chain).

**Role-based sequential review.** Reviewers carry rich behavioral profiles — not just "code reviewer" but distinct roles with expertise domains and review lenses. Sequential review with mandatory fix gates means each reviewer sees a clean artifact. Role labels ship as defaults; an optional naming flow lets users bind personal names to roles if that aids their cognitive ease.

**6-layer project knowledge.** Structure, architecture, activity, temporal, intent, state — none bulk-loaded. A tiered context model loads a ~60-line orientation cache at L1, pulls detailed artifacts on demand at L2, and reserves L3 for deep storage read by subagents. An 11-phase maintenance pipeline fights doc staleness automatically.

**Agent Teams for planning.** Claude Code's [Agent Teams](https://docs.anthropic.com/en/docs/claude-code/agent-teams) enables multiple Claude sessions that communicate and coordinate. This system uses it for multi-perspective planning: persona-based debaters form independent positions, challenge each other, and a synthesizer cross-references into consensus. The same machinery backs the bundled `/research` pipelines (internet, repo, structured, NotebookLM).

**The artifact-shape contract.** Coordinator's on-disk state — handoffs, plans, decisions, review-trail entries, backlog queues — isn't a pile of prose for grep to stumble over. Each artifact type is a registered, versioned JSON Schema (published under `schemas/` and `cockpit-contract/schema/`), so a consumer can query "what's LIVE / BLOCKED / DONE" against the schema's own liveness mapping instead of re-deriving parsing logic per artifact type per consumer. That's the difference between a substrate you can query and one you can only grep.

**Cross-model delegation.** Haiku for mechanical checks, Sonnet for most execution, Opus for judgment and synthesis — routed by task weight, and as of v4.0.0 chosen using measured real-world startup cost, cheapest-first, rather than a hardcoded tier map.

**The engine underneath.** Skills issue their state-mutating operations (plan-tasks, roadmap emission, review-trail writes, release ops) through `coordinator_core` — a Python package exposing a JSON-RPC 2.0 registry of operations, invoked as `python3 -m coordinator_core.invoke <op> '<json>'`. It is command-type and spawn-per-call: there is no resident daemon, and nothing needs to be running first. A daemon was built, measured, and retired once ~59ms cold start proved invisible at commit, ceremony, and session cadence. It ships from [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter) and is a hard declared dependency. See [Two Repos, One System](#two-repos-one-system) for what works without it and what doesn't.

**Written for Windows, not ported to it.** Multi-OS support is a P0 property of one Python codebase rather than something each shell-shaped instruction re-earns. POSIX-only execution assumptions are now banned in code, not just in doctrine, and the degrading command shapes are blocked at the point of use with the performant alternative named in the refusal.

See [docs/wiki/](docs/wiki/) for the curated doctrine pages that ship with this release — including the testable claims about what each agent role promises and which hook enforces each promise. They are a published subset of a much larger internal corpus, chosen for what a consumer install actually needs.

This system's design responds directly to known failure modes: false completion, silent scope expansion, test theater, review laundering, context amnesia, integration blindness, and a dozen others.

</details>

## Plugins

A single **coordinator** plugin, at the repo root — core orchestration, all named reviewer personas, and every workflow skill, with domain and research capabilities bundled in rather than installed separately:

| Capability | Purpose | When It Activates |
|--------|---------|----------------|
| **Core orchestration** | Plan-enrich-chunk-review pipeline, session continuity, fan-out dispatch, all workflow skills | Always |
| **Front-end review** (web-dev) | Front-end architecture review + UX flow review | Web projects |
| **Data-science review** (data-science) | ML, statistics, data modeling review | ML/data work |
| **Research pipelines** (deep-research) | Internet, repo, structured, and NotebookLM research pipelines | On demand (`/coordinator:research`) |

Domain reviewers activate per-project via repo-root `coordinator.local.md` (`project_type`); there is nothing separate to install or enable.

## Customization

- **Name your reviewers (optional).** Role labels ship as the default — bind chosen names to role labels in `/coordinator:install` Phase 6 (Persona Customization), or hand-edit them across the plugin files.
- **Create your own domain reviewer.** The bundled domain reviewer agents are the reference pattern: `agents/senior-front-end.md` (Front-end Reviewer), `agents/staff-ux.md` (UX Reviewer), `agents/staff-data-sci.md` (Data Science Reviewer, ML/statistics). Each is a single agent prompt file with a behavioral profile and routing rules — copy one as a starting point for your own specialization, then activate it per-project via repo-root `coordinator.local.md`'s `project_type`.
- **Per-project configuration.** Create repo-root `coordinator.local.md` with `project_type` to control which reviewers activate.

## Companion Plugins

- **[Context7](https://github.com/upstash/context7)** — External library documentation lookup.

Optional. Coordinator works without it; relevant features degrade gracefully.

<details>
<summary><strong>Directory structure</strong></summary>

```
coordinator-claude/                 # flat Claude Code marketplace — single plugin at repo root
├── .claude-plugin/                 # marketplace.json (auto-discovery, one entry: coordinator) + plugin.json
├── agents/                         # 33 agent definitions: enricher, executor, docs-checker,
│                                    #   generalist + domain reviewers (senior-front-end, staff-ux,
│                                    #   staff-data-sci), eng-director, research agents
├── bin/                            # CLI helpers behind commands/ and hooks/ — Python, no shell
├── commands/                       # 46 workflow commands (hook/ceremony auto-runners)
├── hooks/                          # context pressure, orientation, commit validation, tier-usage
│                                    #   instrumentation — Python scripts plus hooks.json
├── lib/                            # shared Python helpers behind bin/ and hooks/
├── skills/                         # 36 workflow skills — planning, sizing, goals/OKR, review,
│                                    #   debugging — plus the OSS-only coordinator-update skill
├── snippets/                       # shared prompt fragments consumed by skills/agents/commands
├── whoami/                         # plugin identity + health-sentinel package
├── cockpit-contract/schema/        # published slice of the artifact-shape contract
├── schemas/                        # goal/spike/registry JSON Schemas for the tracked artifact types
├── templates/                      # scaffolds: CLAUDE.md, .gitignore, machine-local registry, CI snippet
└── docs/
    ├── install/                    # install manifest + playbook internals
    ├── wiki/                       # curated doctrine pages, including manifesto.md
    ├── evidence.md                 # what was measured, and what wasn't
    ├── safety.md                   # what the install changes; audit + uninstall
    └── agent-install.md            # the install playbook entry point
```

The durable work-state this plugin's skills read and write does not live here — the engine produces it. See [Two Repos, One System](#two-repos-one-system).

</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

**Plugins not loading:**
- Check `enabledPlugins` in `~/.claude/settings.json` — must be `true`
- Check `~/.claude/plugins/installed_plugins.json` — must have entry with correct `installPath`
- Restart Claude Code (changes take effect on next session)
- `/coordinator:install` (run after restart) manages all config files automatically

**`machine-local` exits 127 with `resolver not installed`:**
- Expected before `/coordinator:install` has run. Run it, restart, and confirm `machine-local` resolves before installing the engine. Installing the engine first cannot succeed.

**Engine operations failing, or `/coordinator:setup` reporting the chain unsatisfied:**
- The engine is a separate install. Follow [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter)'s `INSTALL.md`, not `pip install .`
- On Windows, confirm `python3` is a real Python and not the Microsoft Store App-Execution-Alias stub

**Plugin cache not syncing after editing source:**
- Claude Code caches plugins by version. Re-run `claude plugin install coordinator@coordinator-claude` to pick up a newer published version; contributors editing plugin source locally, see [CONTRIBUTING.md](CONTRIBUTING.md).

**Per-project reviewer selection:**
- Create repo-root `coordinator.local.md` with `project_type` field
- Coordinator is always enabled; the bundled domain reviewers activate per-project based on `project_type`

</details>

---

[Dónal O'Duffy](https://github.com/dbc-oduffy) & Claude
