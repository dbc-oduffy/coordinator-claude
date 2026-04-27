---
description: "Staff session — Agent Teams-based collaborative planning and review. Two modes: plan (craft detailed plan from objectives) and review (critique existing artifact). Configurable tiers: lightweight (single reviewer), standard (2 debaters + synthesizer), full (3-5 debaters + synthesizer)."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "--mode plan|review --tier standard|full [--members \"patrik,zoli,...\"] <input>"
---

# Staff Session — Agent Teams Planning and Review Driver

The EM scopes the work, selects the team, creates the team, spawns all teammates, and is **freed**. The team works autonomously:
- **Debaters** (2-5, Opus, persona agents) — read input independently, research the codebase, form positions, debate peers via messaging, converge, write position documents, send DONE to synthesizer
- **Zolí / Synthesizer** (1, Opus) — Director of Engineering. Blocked until all debaters complete, then reads all positions and writes the final output through his ambition-calibrated lens. Represents all positions fairly but resolves contested topics with an eye toward what's achievable with AI execution capacity

**Lightweight tier falls through to `/review-dispatch` — no team created.**

## Arguments

`$ARGUMENTS`:
- `--mode plan|review` — required. `plan` for crafting a new plan from objectives; `review` for critiquing an existing artifact
- `--tier lightweight|standard|full` — required. `lightweight` routes to `/review-dispatch`. `standard` = 2 debaters. `full` = 3-5 debaters
- `--members "persona-a,persona-b,..."` — optional. Override auto-selection with explicit persona slugs (e.g., `"patrik,zoli"`)
- `<input>` — required. Plan mode: path to objectives document or free-text objectives. Review mode: path to the artifact to review

## Step 1 — Parse Arguments and Setup

Parse `$ARGUMENTS`:
- Extract `--mode` (plan|review) — required; fail with usage message if missing
- Extract `--tier` (lightweight|standard|full) — required; fail with usage message if missing
- Extract `--members` (optional) — comma-separated persona slugs
- Remaining text after flags is the `<input>` — artifact path or objectives

Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp, e.g., `2026-03-22-09h30`)

Record spawn timestamp:
```bash
date +%s
```

Generate topic slug from input (e.g., `camera-refactor-plan`, `pipeline-d-review`).

Create scratch directory:
```bash
mkdir -p tasks/scratch/staff-session/{run-id}
```

Set output path based on mode:
- **Plan mode:** `docs/plans/YYYY-MM-DD-{topic-slug}.md` (canonical output for `/enrich-and-review`)
- **Review mode:** `tasks/review-findings/YYYY-MM-DD-{topic-slug}-staff-review.md`

Set advisory path: `{scratch-dir}/advisory.md`

Announce: "Running `/staff-session --mode {mode} --tier {tier}` on '{topic}'."

## Step 2 — Tier Routing

**If `--tier lightweight`:**

Do NOT create a team. Route directly to `/review-dispatch` with the specified member (or `patrik` as default if `--members` not provided).

Announce: "Routing to `/review-dispatch` for single-reviewer gut-check."

**STOP — the rest of this command does not execute.**

**If `--tier standard` or `--tier full`:** Continue to Step 3.

## Step 3 — Scope (EM Direct)

Write `{scratch-dir}/scope.md`:

```markdown
# Staff Session Scope

**Mode:** {plan|review}
**Tier:** {standard|full}
**Run ID:** {run-id}
**Date:** {YYYY-MM-DD}
**Topic:** {topic}

## Objectives / Artifact

{If plan mode: paste or reference the objectives document — what the PM wants built and why. Include any context from conversation. The team writes the plan; the EM writes objectives and constraints only.}

{If review mode: path to the artifact being reviewed — {input-path}. Include any specific review focus areas the PM mentioned.}

## Context Files

{List any relevant files the PM mentioned, or auto-detected from the objectives/artifact — e.g., existing related plans, key source files, architecture docs. "None" if none.}

## Constraints

{Any PM-provided constraints: timeline pressure, dependencies, things to avoid, architectural boundaries. "None specified" if none.}

## Timing Preferences

{PM-specified ceiling, or defaults: plan mode 10 min, review mode 8 min.}
```

**Plan mode:** The EM does NOT write the plan. The EM writes objectives and constraints only. The team writes the plan.

**Review mode:** The EM provides the artifact path and any specific review focus areas. The EM does not pre-form opinions about findings.

## Step 4 — Select Team Composition

**If `--members` specified:** Use those exact personas. Validate each slug maps to a known persona agent. Fail with a clear error if any slug is unknown.

**If `--members` not specified:** Auto-select based on domain signals from the input topic and scope.

**Important: Zolí is the synthesizer, not a debater.** Zolí cannot appear in the debater list — he reads all debater positions and produces the final output. If the user specifies `--members "patrik,zoli"`, reject with: "Zolí is the staff session synthesizer — he can't also debate. Choose a different second debater, or I'll auto-select one."

| Domain Signal | Default Pair |
|---|---|
| Architecture / infrastructure | `patrik` + `sid` |
| Game dev / Unreal | `sid` + `patrik` |
| Frontend / UI | `pali` + `fru` |
| Data science / ML | `camelia` + `patrik` |
| Cross-cutting / unclear | `patrik` + `sid` |

For `--tier full`: add domain experts on top of the default pair. Use judgment based on the input topic to identify which additional personas are most relevant.

Determine debater count:
- `standard`: 2 debaters
- `full`: 3-5 debaters (determined by domain signals and persona relevance)

Announce team composition to PM before creating the team:
> "I'll run this with **{Persona A}** and **{Persona B}** [+ **{Persona C}**...] debating, plus a staff synthesizer. Proceeding."

Persona slug → agent file mapping:

| Slug | Agent File |
|---|---|
| `patrik` | `coordinator/agents/staff-eng.md` |
| `sid` | `game-dev/agents/staff-game-dev.md` |
| `fru` | `web-dev/agents/staff-ux.md` |
| `pali` | `web-dev/agents/senior-front-end.md` |
| `camelia` | `data-science/agents/staff-data-sci.md` |

**Note:** `zoli` is NOT a valid debater slug — he is the synthesizer. See Step 6.

## Step 5 — Create Team and Tasks

**Order matters.** Task IDs from earlier steps are referenced in blocking chain setup.

### Create Team

```
TeamCreate(team_name: "staff-{topic-slug}")
```

### Create Tasks

**1. Synthesizer task** (created first — will be blocked by all debaters later):
```
TaskCreate(
  subject: "Synthesize all debater positions into final {plan|findings}",
  description: "Read all position documents from {scratch-dir}/. Cross-reference, resolve conflicts, write output to {output-path} and {scratch-dir}/synthesis.md. If advisory warranted, write to {scratch-dir}/advisory.md."
)
```
Save as `{synthesizer-task-id}`.

**2. Debater tasks** (one per persona — no blockers on creation):
For each debater persona:
```
TaskCreate(
  subject: "{Persona Name}: {mode} session on {topic}",
  description: "Read scope from {scratch-dir}/scope.md. {Plan mode: Research codebase, form architectural position, debate peers, write consensus-ready plan contribution.} {Review mode: Review artifact at {input-path}, form findings, debate peers, write final position.} Output to {scratch-dir}/{persona-slug}-position.md. Send DONE to synthesizer when complete."
)
```
Collect all debater task IDs as `[{debater-A-id}, {debater-B-id}, ...]`.

**3. Block synthesizer on all debaters:**
```
TaskUpdate(taskId: "{synthesizer-task-id}", addBlockedBy: [{debater-A-id}, {debater-B-id}, ...])
```

## Step 6 — Spawn All Teammates

Read prompt templates from:
- Plan mode debaters: `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/planner-prompt-template.md`
- Review mode debaters: `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/reviewer-prompt-template.md`
- Synthesizer (both modes): `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/synthesizer-prompt-template.md`

For each debater, also read the persona identity excerpt from the persona's agent definition file (the persona identity section — name, role, review standards, output format). This is injected into the debater prompt template at `[PERSONA_IDENTITY]`.

Fill ALL template fields before spawning. Do not leave any `[BRACKETED_FIELD]` unfilled.

Common fields for all templates:
- `[TOPIC]` → topic string
- `[MODE]` → plan|review
- `[TIER]` → standard|full
- `[SCRATCH_DIR]` → full path to scratch directory
- `[SCOPE_FILE]` → `{scratch-dir}/scope.md`
- `[SPAWN_TIMESTAMP]` → Unix epoch seconds from Step 1
- `[TASK_ID]` → this teammate's task ID
- `[SYNTHESIZER_NAME]` → `"synthesizer"` (teammate name — used for DONE messages)
- `[OUTPUT_PATH]` → output path for the final document

Debater-specific fields:
- `[PERSONA_IDENTITY]` → persona identity excerpt from agent definition file
- `[PERSONA_SLUG]` → persona slug (e.g., `patrik`)
- `[POSITION_FILE]` → `{scratch-dir}/{persona-slug}-position.md`
- `[PEER_LIST]` → the other debaters' teammate names and persona slugs (for messaging)
- `[MIN_MINUTES]` → floor: 3 (both modes)
- `[MAX_MINUTES]` → ceiling: 10 (plan mode), 8 (review mode)
- `[INPUT_PATH]` → review mode only: path to artifact being reviewed

Synthesizer-specific fields:
- `[DEBATER_COUNT]` → number of debaters
- `[DEBATER_SLUGS]` → comma-separated persona slugs
- `[ADVISORY_PATH]` → `{scratch-dir}/advisory.md`

**Spawn ALL teammates in a single message (parallel):**

```
Agent(
  team_name: "staff-{topic-slug}",
  name: "{persona-slug-A}",
  model: "opus",
  subagent_type: "coordinator:{persona-agent-name-A}",
  prompt: <filled debater prompt for persona A>
)
TaskUpdate(taskId: "{debater-A-id}", owner: "{persona-slug-A}")

Agent(
  team_name: "staff-{topic-slug}",
  name: "{persona-slug-B}",
  model: "opus",
  subagent_type: "coordinator:{persona-agent-name-B}",
  prompt: <filled debater prompt for persona B>
)
TaskUpdate(taskId: "{debater-B-id}", owner: "{persona-slug-B}")

[repeat for each additional debater in full tier]

Agent(
  team_name: "staff-{topic-slug}",
  name: "synthesizer",
  model: "opus",
  subagent_type: "coordinator:eng-director",
  prompt: <filled synthesizer prompt>
)
TaskUpdate(taskId: "{synthesizer-task-id}", owner: "synthesizer")
```

Persona slug → subagent_type mapping:

| Slug | subagent_type |
|---|---|
| `patrik` | `coordinator:staff-eng` |
| `sid` | `game-dev:staff-game-dev` |
| `fru` | `web-dev:staff-ux` |
| `pali` | `web-dev:senior-front-end` |
| `camelia` | `data-science:staff-data-sci` |

## Step 7 — EM Is Freed

After spawning all teammates, announce:

> "Staff session running on '**{topic}**' with **{N} debaters** ({names}) + **1 synthesizer**.
>
> - Debate phase: floor 3 min, ceiling {MAX_MINUTES} min. Debaters research independently, form positions, and challenge each other.
> - Synthesizer unblocks when all debaters complete.
>
> I'm available for other work — I'll be notified when the synthesizer completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not send WRAP_UP. The team self-governs via the timing and convergence protocol in `team-protocol.md`.

## Step 8 — On Completion Notification

When you receive a notification that the synthesizer task is complete:

1. Read the output at `{output-path}`. Verify it has substantive content (not just headers or a stub).

2. Mode-specific verification:
   - **Plan mode:** Verify the plan has an `## Implementation Plan` section with tasks, files, and steps in `writing-plans` format. Verify `**Review:** Staff session ({participants}) — debated and synthesized. Ready for enrichment.` is present.
   - **Review mode:** Verify findings are structured with severities and persona attributions. Verify a `## Verdict` line is present.

3. Check for advisory: `test -f {scratch-dir}/advisory.md` — if the file exists, read it.

4. Commit the output:
   ```bash
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "staff-session: {mode} — {topic-slug}"
   ```

5. Archive the paper trail:
   ```bash
   mkdir -p docs/research/archive/YYYY-MM-DD-staff-{topic-slug}
   cp -r {scratch-dir}/* docs/research/archive/YYYY-MM-DD-staff-{topic-slug}/
   ```

6. Remove scratch directory:
   ```bash
   rm -rf {scratch-dir}
   ```

7. Shut down the team:
   ```
   TeamDelete(team_name: "staff-{topic-slug}")
   ```

8. Commit cleanup:
   ```bash
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "staff-session: archive + cleanup"
   ```

9. Present output to PM:
   - Mode-specific framing: plan mode → "Here's the staff session plan, ready for `/enrich-and-review`"; review mode → "Here are the synthesized findings"
   - Brief executive summary (2-3 bullets of the most important content)
   - Output path
   - If advisory exists: "The synthesizer flagged observations beyond scope — see `{scratch-dir}` (archived at `docs/research/archive/YYYY-MM-DD-staff-{topic-slug}/advisory.md`)."

## Error Handling

| Failure | Action |
|---------|--------|
| Single debater crashes (no position written) | Synthesizer works with remaining positions. Note the gap: "Missing perspective: {persona}." EM can supplement manually. |
| Majority debater failure (>50% crash) | EM is notified (only 1 or fewer debater tasks completed). `TeamDelete`, fall back to `/review-dispatch` for the same artifact. |
| Synthesizer fails | EM reads raw debater position documents from scratch dir. Manual synthesis is feasible — position docs are structured. |
| Team creation fails | Report to PM. Fall back to `/review-dispatch` or EM-authored plan. |
| DONE message not received (debater marked complete but synthesizer not woken) | Synthesizer checks `TaskList` on a polling cycle. If all debater tasks show `completed` but no DONE received after 2 minutes, synthesizer proceeds anyway. EM can send a manual nudge via `SendMessage` if synthesizer appears stalled. |
| Debate loops (debaters exchange challenges without converging) | Ceiling time is a hard cutoff. Diminishing returns detection also triggers convergence after 2 no-change exchanges. Position documents capture the disagreement; synthesizer resolves or presents as dissent. |
| Unknown persona slug in `--members` | Halt before team creation. Report the unknown slug and list valid slugs. Do not create a partial team. |
| Output file missing after synthesizer completes | Read `{scratch-dir}/synthesis.md` as fallback. If that is also missing, read raw position files and report to PM. |
