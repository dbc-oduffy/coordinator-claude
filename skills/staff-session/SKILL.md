---
name: staff-session
description: "PM-GATED, never from a subagent. Agent Teams review for architecture calls."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "--mode plan|review --tier standard|full [--members \"the Staff Engineer,the Director of Engineering,...\"] <input>"
---

# Staff Session — Agent Teams Planning and Review Driver

The EM scopes the work, selects the team, creates the team, spawns all teammates, and is **freed**. The team works autonomously:
- **Debaters** (2-5, Opus, persona agents) — read input independently, research the codebase, form positions, debate peers via messaging, converge, write position documents, send DONE to synthesizer
- **the Director of Engineering / Synthesizer** (1, Opus) — Director of Engineering. Blocked until all debaters complete, then reads all positions and writes the final output through their ambition-calibrated lens. Represents all positions fairly but resolves contested topics with an eye toward what's achievable with AI execution capacity

**Lightweight tier falls through to single-reviewer dispatch via `/review` (plan) or `/review-code` (code) — no team created.**

## Arguments

`$ARGUMENTS`:
- `--mode plan|review` — required. `plan` for crafting a new plan from objectives; `review` for critiquing an existing artifact
- `--tier lightweight|standard|full` — required. `lightweight` routes to single-reviewer dispatch (`/review` for plan artifacts, `/review-code` for code artifacts). `standard` = 2 debaters. `full` = 3-5 debaters
- `--members "persona-a,persona-b,..."` — optional. Override auto-selection with explicit persona slugs (e.g., `"the Staff Engineer,the Director of Engineering"`)
- `<input>` — required. Plan mode: path to objectives document or free-text objectives. Review mode: path to the artifact to review

## Step 1 — Parse Arguments and Setup

Parse `$ARGUMENTS`:
- Extract `--mode` (plan|review) — required; fail with usage message if missing
- Extract `--tier` (lightweight|standard|full) — required; fail with usage message if missing
- Extract `--members` (optional) — comma-separated persona slugs
- Remaining text after flags is the `<input>` — artifact path or objectives

Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp, e.g., `2026-03-22-09h30`)

Record spawn timestamp via `date +%s`.

Generate topic slug from input (e.g., `camera-refactor-plan`, `pipeline-d-review`).

Create the workdir: `mkdir -p docs/research/{run-id}-workdir/`. This is the same paper-trail
convention `/coordinator:notebooklm-research` uses (`docs/research/{run-id}-workdir`) — sharing
it is what lets Step 8's archive-and-cleanup op (claude-klabauter `fleet.archive_paper_trail`) serve both
call sites from one module rather than two near-identical implementations.

Set output path based on mode:
- **Plan mode:** `docs/plans/YYYY-MM-DD-{topic-slug}.md` (canonical output for `/enrich-and-review`)
- **Review mode:** `state/review-findings/YYYY-MM-DD-{topic-slug}-staff-review.md`

Set advisory path: `{scratch-dir}/advisory.md`

Announce: "Running `/staff-session --mode {mode} --tier {tier}` on '{topic}'."

## Step 2 — Tier Routing

**If `--tier lightweight`:**

Do NOT create a team. Route directly to `/review` (plan artifacts) or `/review-code` (code artifacts) with the specified member (or `the Staff Engineer` as default if `--members` not provided).

Announce: "Routing to single-reviewer dispatch (`/review` or `/review-code`) for single-reviewer gut-check."

**STOP — the rest of this command does not execute.**

**If `--tier standard` or `--tier full`:** Continue to Step 3.

## Step 3 — Scope (EM Direct)

Write `{scratch-dir}/scope.md` per the template in `pipelines/staff-session/templates-and-fields.md` § Step 3. Plan mode: EM writes objectives and constraints only — never the plan. Review mode: EM provides artifact path and focus areas only — never pre-formed findings.

## Step 4 — Select Team Composition

**If `--members` specified:** those exact slugs are the debater list.

**If `--members` not specified:** match the input topic + scope to a domain category (e.g.
architecture/infrastructure, game dev/Unreal, frontend/UI, data science/ML, cross-cutting/unclear)
— this categorization is the one piece of genuine judgment this step retains; everything
downstream of it is resolved, not looked up.

**For `--tier full`:** on top of whatever pair the category resolves to, judgment-select 1-3
additional personas most relevant to the topic and append their slugs to an explicit override
list for the roster call below.

**Resolve the roster — do not hand-maintain a lookup table for this.** Call
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/staff-session-assemble"
--session-mode <plan|review> (--domain-signal "<category>" | --slug <slug> [--slug <slug> ...])
--json`. The CLI reads DoE-claude's doctrine-side `coordinator/routing.md` (F1 reconciliation —
the roster DATA lives there, not in this skill or in the resolver) and returns `{personas:
[{slug, agent_file, subagent_type}, ...], narration, source}`. It fails loud (usage exit) on an
unresolvable domain signal, an unknown slug, or `the Director of Engineering` appearing as a debater — surface that
error to the PM verbatim rather than re-deriving the rejection rule here.
<!-- Caution: the resolver module lives in claude-klabauter
(coordinator_core/staff_session_assemble); its coordinator/bin/ CLI trampoline (the
`staff-session-assemble` name invoked above) is the agreed entrypoint name for that trampoline —
confirm it is verified-live before relying on it blindly. -->

**Note:** `the Director of Engineering` is never a valid debater slug — they are the synthesizer, spawned separately in
Step 6 with a fixed identity (`coordinator:eng-director`), never resolved through this roster
call.

Determine debater count from the resolved roster: `standard` = 2 (the resolved default pair),
`full` = 3-5 (default pair + the judgment-selected additions above, all passed as an explicit
`--slug` list to the same call).

Announce team composition to PM before creating the team, using the resolved `personas[].slug`:
> "I'll run this with **{Persona A}** and **{Persona B}** [+ **{Persona C}**...] debating, plus a staff synthesizer. Proceeding."

## Step 5 — Create Tasks

**Order matters.** Task IDs from earlier steps are referenced in blocking chain setup.

Spawn the first teammate via the `Agent` tool — the team auto-forms on first spawn; no explicit create step.

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

Read the planner / reviewer / synthesizer prompt templates from `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/`. For each debater, read the persona identity excerpt from its agent definition file (`personas[].agent_file` from Step 4's resolved roster, injected at `[PERSONA_IDENTITY]`). Fill ALL `[BRACKETED_FIELD]` placeholders before spawning — **see `pipelines/staff-session/templates-and-fields.md` § Step 6 for the full common/debater/synthesizer field list.**

**Spawn ALL teammates in a single message (parallel):**

```
Agent(
  name: "{persona-slug-A}",
  model: "opus",
  # prefix varies by persona; resolved via Step 4's staff-session-assemble roster call,
  # never hardcoded here (e.g., game-dev: for the Game Dev Reviewer, not coordinator:) — use the
  # `subagent_type` field the CLI returned for this slug.
  subagent_type: "{personas[A].subagent_type}",
  prompt: <filled debater prompt for persona A>
)
TaskUpdate(taskId: "{debater-A-id}", owner: "{persona-slug-A}")

Agent(
  name: "{persona-slug-B}",
  model: "opus",
  subagent_type: "{personas[B].subagent_type}",
  prompt: <filled debater prompt for persona B>
)
TaskUpdate(taskId: "{debater-B-id}", owner: "{persona-slug-B}")

[repeat for each additional debater in full tier]

Agent(
  name: "synthesizer",
  model: "opus",
  subagent_type: "coordinator:eng-director",
  prompt: <filled synthesizer prompt>
)
TaskUpdate(taskId: "{synthesizer-task-id}", owner: "synthesizer")
```

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
   - **Plan mode:** Verify the plan has an `## Implementation Plan` section with tasks, files, and steps in plan format. Verify the marker
     `**Review:** Staff session ({participants}) — debated and synthesized. Ready for enrichment.`
     is present, byte-exact. <!-- Marker-string pin: this line is the single authoritative
     producer copy of the marker string `enrich-and-review`'s Phase 0 gate matches against.
     Consumers cite THIS anchor (staff-session/SKILL.md Step 8, item 2) — never hand-type a
     second copy of the string. -->
   - **Review mode:** Verify findings are structured with severities and persona attributions. Verify a `## Verdict` line is present.

3. Check for advisory: `test -f {scratch-dir}/advisory.md` — if the file exists, read it.

4. Commit the output artifact (plain-git scoped — lessons.md:207; `docs/wiki/scoped-safety-commits.md § Current Doctrine`): `git add --
   {output-path}` then `git commit -m "staff-session: {mode} — {topic-slug}" -- {output-path}`.
   This is the deliverable itself (the plan or review-findings file), distinct from the paper
   trail archived below — it stays at its canonical location, it is not moved.

   Then commit the paper trail too, same scoped form:
   `git add -- {scratch-dir}` then `git commit -m "staff-session: paper trail — {topic-slug}" -- {scratch-dir}`.
   **Item 5 cannot archive an untracked workdir.** Its `git mv` fails `fatal: not under version
   control`, and staging alone does not rescue it — the op works through a private index seeded
   from `git read-tree HEAD`, which cannot see the shared index. Only a real commit works; that is
   measured behaviour of the op, not an inference from reading it. The commit belongs **here**
   rather than beside Step 1's `mkdir`, because what item 5 needs is the tree's state at
   invocation time: everything the session wrote into the workdir after creation would otherwise
   be untracked again by the time the op runs.
   <!-- Negative spec: do NOT push this commit down into the archival op. An op may commit content
   it authored on a path it owns, never content it merely found — `docs/wiki/scoped-safety-commits.md`
   carries the incident from this same op family where the accepted fix was subtractive and adding
   `git add` in front did NOT help. -->

5. Archive-and-cleanup. Invoke the archive-and-cleanup op — claude-klabauter's `fleet.archive_paper_trail`
   (claude-klabauter `coordinator_core/ops/fleet/archive_paper_trail.py`, `register_op
   "fleet.archive_paper_trail"`) — with `run_id={run-id}`, `topic_slug={topic-slug}`,
   `dry_run=false`. It moves `{scratch-dir}` (Step 1's `docs/research/{run-id}-workdir`) to
   `docs/research/archive/YYYY-MM-DD-{topic-slug}/` via `git mv` and lands ONE scoped commit
   covering the move (`docs/wiki/scoped-safety-commits.md § Current Doctrine`), then removes the
   now-empty source tree — the mkdir, copy,
   remove, stage, and commit this step used to spell out as five separate fenced commands are
   this one op call. Re-running it after a prior success is a safe no-op
   (`already_archived: true`) rather than a silent re-merge.
   <!-- Caution: the op module is landed (verified on disk); its coordinator/bin/ CLI trampoline
   for direct skill-level invocation may not yet be landed — verify before relying on direct
   invocation. -->

6. The team auto-cleans on session exit — no explicit teardown step.

7. Present output to PM:
   - Mode-specific framing: plan mode → "Here's the staff session plan, ready for `/enrich-and-review`"; review mode → "Here are the synthesized findings"
   - Brief executive summary (2-3 bullets of the most important content)
   - Output path
   - If advisory exists: "The synthesizer flagged observations beyond scope — see `{scratch-dir}` (archived at `docs/research/archive/YYYY-MM-DD-{topic-slug}/advisory.md`)."

## Error Handling

See `pipelines/staff-session/templates-and-fields.md` § Error Handling Matrix for the full failure-mode → action table (debater crash, synthesizer failure, DONE-not-received, debate loops, unknown slug, missing output).
