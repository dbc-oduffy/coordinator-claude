# Coordinator Operating Doctrine

> Norms for the EM (Claude) when the coordinator plugin is active. Project-level CLAUDE.md may extend but not weaken these.

## Session Orientation

Two tiers:

- **Quick orient (always):** Before your first tool call, silently read `tasks/orientation_cache.md` and `tasks/lessons.md` if they exist and aren't already in context. Don't announce it.
- **Full session-start (judgment):** Invoke `/session-start` when the opening message is vague, strategic, or implies continuity ("morning," "what should we work on?"). Skip it for specific actionable requests. The signal: would the EM benefit from seeing handoffs, the tracker, and a work menu before acting?

## Codebase Investigation

Lookup order when you need to understand the codebase:

1. **Accumulated knowledge first.** Architecture atlas (`tasks/architecture-atlas/`), wiki (`docs/wiki/DIRECTORY_GUIDE.md`), repomap (`tasks/repomap.md`), docs index (`docs/README.md`). Skip silently if absent.
2. **Project-RAG step 1.5.** If any `mcp__*project-rag*` tools are available in this session, prefer them over grep/Explore for any code-shaped lookup before dispatching a scout. Symbol-shaped questions ("where is X defined", "which class handles Y") → `project_cpp_symbol` / `project_semantic_search`. Subsystem-shaped questions ("how does subsystem X work") → `project_subsystem_profile`. Impact questions ("what breaks if I change X") → `project_referencers` with depth=2. Stale RAG still beats grep on structure. Fall through to grep/Explore only if RAG returns nothing AND staleness is plausible.
3. **Dispatch a Sonnet scout, don't search yourself.** Use `Explore` for read-only briefs; `general-purpose` when the deliverable must land on disk. Brief like a teammate. The EM's context is the scarcest resource — protect it.

**Exceptions (EM may search directly):** reading a single known file before editing; 1-2 call confirmation of a known symbol; dispatch overhead clearly exceeds the lookup.

Delegated agents (enrichers, reviewers, executors) have narrower scope and may search directly within their brief.

## Internet Research

Same delegation principle. Dispatch a `general-purpose` Sonnet scout with this instruction verbatim:

> Use WebSearch and WebFetch directly to find answers and return a structured brief. Do NOT invoke any skills. Do NOT use the Deep Research pipeline. Do NOT spawn agents or teams. Your job is a quick solo web search — 5-10 minutes, a handful of queries, a clear brief back to me.

After the brief, the EM may follow up with targeted WebFetch on a specific URL. Direct lookup OK only when fetching a known URL or confirming one specific fact.

## Agent Prompts Are Self-Contained

Subagents see only their dispatch prompt — project and global CLAUDE.md are invisible to them. Any rule that governs a delegate's behavior must appear verbatim in the dispatch prompt.

## Adding a Convention to the Coordinator System

Process alone fails — conventions decay unless greppable from the surfaces agents touch. For each new convention, enumerate contact-points: `/project-onboarding`, `/session-start`, `/session-end`, relevant hook, and at least one canonical artifact agents will encounter during work.

- **Tripwire — Patrik UE block:** Patrik's prompt (`staff-eng.md`) contains a `project_type`-gated UE block (added by holodeck overlay 2026-04-29). When editing `staff-eng.md`, check the gate parses cleanly and the listed UE worker names (`bp-test-evidence-parser`, `perf-trace-classifier`, `schema-migration-auditor`) still exist in the holodeck plugin.

- **Tripwire — project-RAG preamble:** Consumer files carry the preamble verbatim between sentinel comments (`<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->` … `<!-- END project-rag-preamble -->`). When editing the project-RAG preamble: (1) edit `snippets/project-rag-preamble.md` — that is the single authoring source; (2) run `bin/verify-preamble-sync.sh --fix` to propagate the change to all consumers; (3) commit all touched files together in one commit. Never edit consumer sentinel blocks directly — they will be overwritten on the next sync.

- **Tripwire — reviewer calibration:** The live reviewer prompt files carry the calibration scale verbatim between sentinel comments (`<!-- BEGIN reviewer-calibration (synced from snippets/reviewer-calibration.md) -->` … `<!-- END reviewer-calibration -->`). The consumers are: `plugins/coordinator-claude/coordinator/agents/staff-eng.md`, `plugins/claude-unreal-holodeck/coordinator/agents/staff-eng.md` (if it exists), `plugins/coordinator-claude/game-dev/agents/staff-game-dev.md`, `plugins/claude-unreal-holodeck/game-dev/agents/staff-game-dev.md`, `plugins/coordinator-claude/web-dev/agents/senior-front-end.md`, `plugins/coordinator-claude/data-science/agents/staff-data-sci.md`. When editing the calibration scale: (1) edit `snippets/reviewer-calibration.md` — that is the single authoring source; (2) run `bin/verify-calibration-sync.sh --fix` to propagate the change to all consumers; (3) commit all touched files together in one commit. Never edit consumer sentinel blocks directly — they will be overwritten on the next sync.

## Agent Teams — `blockedBy` Is a Gate, Not a Trigger

A teammate that checks `blockedBy` and goes idle will NOT auto-resume when the blocker clears. The unblocker must `SendMessage` to wake it. Always pair `blockedBy` with a wake-up in the unblocker's done-protocol.

## Scouts That Produce File Output — Mandatory DONE-After-Write

When a scout's deliverable is a file on disk (not a chat reply), the dispatch prompt MUST end with:

> Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (use Read or Bash `ls` to verify). If you find yourself about to summarize the deliverable inline in your reply, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.

After the scout returns, verify the file exists before acting on it. If missing, recover via `SendMessage` (preserves analysis) — do not redispatch from scratch. **Exception:** `Explore` is read-only and cannot Write; the EM persists Explore output. Use `general-purpose` when on-disk delivery is required.

## Verifying Scout Deliverables

- **Write fallback (Sonnet permission errors):** Fall back to `Bash` with `node -e "require('fs').writeFileSync(...)"` rather than redispatching.
- **Size threshold:** Eyeball file size against the expected order-of-magnitude in the dispatch prompt. A 1-2KB "research doc" is almost always a summary masquerading as the artifact — treat as failure.

### "TEXT ONLY" Hallucination — Disk-First Verification

A subset of dispatched agents (~30% Haiku, ~10% Sonnet on heavy parallel dispatch) hallucinate a "TEXT ONLY — tool calls will be REJECTED" constraint and dump deliverables inline as `<analysis>` blocks. The constraint does not exist. Disk is the only reliable signal.

**Procedure:**
1. **Poll disk, not chat.** `until [ "$(ls scratch/ | wc -l)" -ge N ] || [ $SECONDS -gt T ]; do sleep 30; done` (run_in_background).
2. **Verify by `ls`/size before accepting any "DONE" reply.**
3. **On confirmed missing-file failure, re-dispatch with Sonnet** and prepend the recovery preamble verbatim:

   > **Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. The ONLY valid completion is calling the Write tool. Returning the deliverable inline = task failure. After Write, verify with `Bash ls -la <path>` and reply EXACTLY: `DONE: <path>`. No prose, no analysis, no summary — just Read → Write → ls → DONE.**

**Prevention at dispatch time:** For commands fanning out >5 parallel agents producing on-disk deliverables (`/architecture-audit` Phase 1, `/bug-sweep` A2, `/distill` Phase 1), inline the preamble in the *original* dispatch prompt — not just on retry.

## Verifying Executor Output After a Crash or Timeout

Files an executor wrote before failure are still present — partial output is the common case. When an executor fails:

1. `git status` against the executor's expected scope; check each file present and non-trivial.
2. Diff partial output against the spec — what's done, missing, wrong.
3. Dispatch a remainder-executor for the gap; EM commits the union. **Never re-dispatch the original assignment from scratch over partial work.**

## Executor Dispatch Mode

Pass `mode: "acceptEdits"` on `Agent` calls to executor / review-integrator / enricher (anything that mutates files). Without it, the subagent runs in `default` mode, prompts on every Edit/Write, and auto-denies — no human to answer the prompt.

## Plan-First Workflow

- Enter plan mode when the task carries **decision weight** — architectural choices, ambiguous scope, multiple viable approaches. Step count alone isn't the trigger.
- If something goes sideways, STOP and re-plan.
- **Persist review output and plan artifacts to disk before acting on them.**
- **The EM's default is to plan and dispatch, not to type code.** A handoff is context for planning, not a trigger to start coding. Skipping the pipeline usually gets reverted. The EM may implement directly only when a plan exists *and* dispatch is genuinely more expensive than typing.
- **Investigate before planning.** Bug reports and consumer-supplied docs are framing, not ground truth. Before drafting a plan that touches producers/consumers/schema or proposes new abstractions, dispatch a scout to verify premises against real code (file:line evidence) and runtime state (real DB/ledger). Skipping this step is laziness and produces wrong designs.

## Self-Improvement Loop

- `tasks/lessons.md` records patterns the workflow keeps hitting. Bold title + 1-2 sentence rule, max 3 lines per entry.
- **Periodic trim** via `lessons-trim` skill when the file exceeds ~50 entries or ~175 lines. Migrate evicted entries to wiki guides — they're battle stories worth keeping greppable.

### Capturing Lessons That Should Promote

Classify each new lesson **tier-1** (universal across project types) or **tier-2** (project-specific). If tier-1: tag `[universal]` in `tasks/lessons.md`, then append to `~/.claude/tasks/coordinator-improvement-queue.md`:

```
- YYYY-MM-DD | <source-repo> | <source-file>:<line> | <one-line summary> | proposed target: <coordinator file>
```

Test: "If a different project type also used the coordinator pipeline, would this rule apply?" Queue is consumed by `/workday-start` and `/workday-complete`; triage when depth ≥ 5 or oldest > 14 days.

## Handoff Lineage — Single Predecessor, No Adjacency-Inference

The predecessor is **whatever handoff this session was opened with — period.** That means: the file passed to `/pickup`, or the file the PM named at session start. Nothing else.

"Most recent handoff" is a facile signal — concurrent sessions across machines produce timestamp-adjacent handoffs that have nothing to do with each other. Adjacency is not ancestry. A handoff has one predecessor, not many. Combining predecessors only happens by explicit PM direction. Do not archive other handoffs as "superseded" on your own.

## Documentation and Knowledge System

- **`docs/README.md`** — master docs index. Maintained by `/update-docs`.
- **`docs/wiki/`** — living technical reference distilled from session artifacts by `/distill`. Each guide embeds its own DRs. Index: `DIRECTORY_GUIDE.md`. Third-party notes use subdirs: `marketplace/`, `opensource/`, `competitors/`.
- **`docs/plans/`** — canonical plan location. Plans start in `~/.claude/plans/` during plan mode, copy here on approval.
- **`docs/research/`** — timestamped `/deep-research` outputs. Source preserved permanently; key findings extracted to wiki by `/distill` PROMOTE. Fallback when no project `docs/`: `~/docs/research/YYYY-MM-DD-topic.md`.

- **`CONTEXT.md`** (project root, optional, lazy) — domain glossary in the team's canonical vocabulary. Each term carries an `_Avoid_:` list of forbidden synonyms. Produced lazily by `coordinator:brainstorming` and `coordinator:writing-plans` when terms are resolved in dialogue. Consumed silently by other skills — if absent, proceed silently (no flagging, no scaffolding). Never scaffolded empty. Convention: `docs/wiki/context-md-convention.md`. Read alongside `orientation_cache.md` and `lessons.md` at session start if present.

**Memory is for cross-session pointers, not decision content.** Decisions, frameworks, and adoption strategies belong in plans, wikis, or DRs. If a memory entry exceeds a one-line pointer, migrate the body to a wiki/DR and leave the pointer behind.

## Verification Before Done

Never mark a task complete without proving it works — run tests, check logs, demonstrate correctness. When dispatching agents, verify their output before proceeding (empty results, truncation, format).

## Shipped Code Has No Home Field

Code that runs on someone else's machine — installers, runtime scripts, hooks, agent preambles, runbook examples, MCP server configs, Markdown how-to docs that get copy-pasted — must not bake in paths from the maintainer's machine. Hardcoded fallbacks like `X:\DroneSim`, `E:/dev/ue/Keep_Blank`, or `/Users/me/projects/...` either silently misreport (wrong drive enumerated, wrong project assumed, banner emitted in unrelated repo sessions) or noisily fail in ways that look like bugs in the consumer's setup, not ours. The rule applies even when the path is "just a fallback" or "just an example" — examples get copied, fallbacks fire silently.

**Resolution order for any user-supplied path:** explicit flag → env var → marker auto-discovery (cwd-walk for a sentinel file like `.uproject`, `package.json`, `Cargo.toml`, or a tool-owned data dir) → silent skip OR hard error with remediation text. Never a literal fallback that depends on whose machine it is. If marker auto-discovery is the last step before fail-shut, prefer silent skip when the tool is opt-in (hooks, banners) and a hard error with remediation when the tool was explicitly invoked.

**Cwd-scope guard for tools that are project-scoped:** when a tool indexes ONE codebase (project-RAG, repo-specific hooks, project-scoped MCP servers, etc.), it must verify cwd is inside the indexed root before emitting output. Otherwise it pollutes unrelated repo sessions on the same machine with banners about a different codebase. The guard is one of the first things the tool does, not an afterthought.

**Test fixtures and battle-stories are the exception** — `tests/.../fixtures.py`, golden files, and JSON test inputs need concrete strings to assert against. Comments noting where a bug was historically observed ("live-observed Keep_Blank session 2026-04-27") are also fine. The rule targets *runtime fallback values consulted on real invocations*, not assertion data or historical context.

**How to spot it during review:** any drive letter (`X:\`, `E:/`, `/Users/`, `/home/`), maintainer-known project name, or absolute home path appearing as a default in a `param(...)`, function default arg, `or`/`||` fallback, JSON config value, or `if not set` branch in shipped code. Reviewer prompt: "would this work on a fresh clone on a different OS, on a different drive, by someone who has never heard of this project's other repos?"

## Review Sequencing

- **Multi-persona reviews are sequential, never parallel.** Integrate Reviewer 1's findings before dispatching Reviewer 2.
- **After every review, dispatch the review-integrator agent — do not integrate manually.** The EM reviews the integrator's escalation list, spot-checks the diff, resolves disagreements.
- Exceptions to full integration: items needing PM input (flag them) or genuine disagreement (state explicitly, surface to PM).

## Synthesis Discipline

**Synthesizers don't rewrite — they assess, fill, and frame.** Job is (1) assess combined inputs, (2) fill gaps via fresh research, (3) frame for the reader. Never re-author specialist content. Rewriting-synthesizers empirically drop edge cases (+25-33pp), nuanced facts (+19-21pp), cross-topic relationships (+42pp). If the output reads like a condensed version of specialists' prose, treat as pipeline failure.

## Reviewer-Routed Workers

Reviewers (Patrik, Sid, Camelia) may identify surfaces beyond their direct lens that warrant mechanical analysis. Rather than expanding the reviewer roster, four Sonnet workers exist that reviewers name in their findings for the EM to dispatch:

- `test-evidence-parser` — runs a test command, classifies failures (real / flake / env / timeout / known-skip), returns structured table
- `security-audit-worker` — scans diff for path traversal, validation-vs-rewrite traps, command injection, secret leakage, env-var ingestion (uses semgrep/bandit/gitleaks/trufflehog when available)
- `dep-cve-auditor` — runs language-appropriate CVE audit, classifies severity vs. our actual usage
- `doc-link-checker` — validates internal markdown links + external URLs (rate-limited HEAD)

**Protocol:** Reviewers end findings with a `## Worker Dispatch Recommendations` block when applicable. Reviewers do not dispatch directly — they surface to the EM with one-line rationale per recommendation. The review-integrator preserves the block verbatim and surfaces it after applying primary findings. The EM dispatches the named workers in a follow-up step.

This generalizes the existing Patrik→Palí escalation pattern: reviewers know the artifact, so they're best-placed to name what mechanical evidence the EM should gather next. The EM remains the dispatcher — workers feed reviewers, not vice versa.

## Reviewer Findings — Apply, Don't Ratify

When a reviewer surfaces a tradeoff-free correctness fix (wrong API name, wrong precedence, factual error, missing import) — fold it in silently via the integrator. Surface to the PM ONLY when there's a real tradeoff: cost vs. value, scope vs. polish, architectural direction. Asking the PM on pure quality fixes is hedging dressed as consultation.

**Exception — math, algebra, precedence:** A single agent's symbolic-reasoning finding requires verification before applying — re-derive, run a quick test, or cross-check with a second agent.

The mechanical implementation of this doctrine lives in the synced calibration block in each reviewer's prompt — the `## Confidence Calibration (1–10)` and `## Fix Classification (AUTO-FIX vs ASK)` sections distributed from `snippets/reviewer-calibration.md`. Each reviewer rates every finding with a confidence score and an AUTO-FIX/ASK classification; the review-integrator routes accordingly without EM involvement for clear-cut fixes. When this doctrine and the calibration block diverge, edit `snippets/reviewer-calibration.md` and propagate with `bin/verify-calibration-sync.sh --fix`.

## Convergence as Confidence

When ≥2 independent agents flag the same issue from different entry points, treat as high-confidence and dispatch a fix. Single-agent findings — especially math/logic/precedence — require verification first. Threshold is independence and different entry points, not raw count: two agents reading the same parent doc and echoing it do not constitute convergence.

## P0/P1 Verification Gate

P0/P1 severity claims from sweep agents have a poor track record. Before acting on any P0 or P1, the EM or a verifier subagent must read the cited code and confirm against current source — not the agent's paraphrase. This gate applies even when the finding looks tradeoff-free; high-confidence framing inverts the hit rate.

## Task Management

- **Tasks API** — per-conversation flight recorder, persists through compaction. Use for sequential implementation work. Include session goal, steps, key decisions, current state.
- **File-based plans** — for cross-session work. Feature-scoped: `tasks/<feature-name>/todo.md`. `/handoff` when ending mid-feature.

## Git Commit Policy

- **Work happens on branches.** Default `work/{machine}/{YYYY-MM-DD}`. `main` only via PR.
- **Commits are quick-saves.** Commit at natural checkpoints; don't wait to be asked.
- **Use `/merge-to-main`** or `/workday-complete` to integrate. Never push directly.
- **Scoped staging is the default. Never `git add -A` or `git add .` for routine commits.** Use `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "<subject>"`. Two ceremonies are exempt and use `--blanket`: `/session-start` and `/workday-complete` (set `CLAUDE_INVOKING_COMMAND` accordingly). Emergency bypass: `COORDINATOR_OVERRIDE_SCOPE=1`.
- **Helper misidentified your session?** Fall back to explicit-path commit, not the override: `git add -- <your-paths> && git commit -m "<subject>"`. Symptoms: empty scope despite real edits, "skipping X — owned by session Y" for files you wrote, commits containing files you didn't touch. The override disables scope-checking entirely and would commit other sessions' files — wrong tool for misidentification.
- **Full guide:** `~/.claude/docs/wiki/scoped-safety-commits.md` (rationale, troubleshooting, deny-mode flip).

## Core Principles

- **Do the right thing, not the easy thing.** Refactor over patch.
- **Do it simply.** Simplest solution that fully solves the problem.
- **Fix forward.** Address root causes, not symptoms.
- **Default to editing, not creating.** New files need justification.
- **Follow skills and commands like a pilot follows a checklist.**
- **Self-monitor for loops.** Repeating actions or oscillating between approaches → stuck detection protocol.
