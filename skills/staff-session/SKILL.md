---
name: staff-session
description: "PM-GATED, never from a subagent. Chatty-Workflow review for architecture calls."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "Workflow"]
argument-hint: "--mode plan|review --tier standard|full [--members \"the Staff Engineer,the Director of Engineering,...\"] <input>"
---

# Staff Session — Chatty-Workflow Planning and Review Driver

The EM scopes the work, selects the debaters, fires ONE background `Workflow`, and is **freed**; the
Workflow then runs the debate as rounds and synthesizes autonomously. Roles, models and counts:
`pipelines/staff-session/team-protocol.md` § Roles — read there, don't re-derive. Doctrine:
`coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md`.

**Lightweight tier falls through to single-reviewer dispatch via `/review` (plan) or
`/review-code` (code) — no Workflow fired.**

## Arguments

`$ARGUMENTS`:
- `--mode plan|review` — required.
- `--tier lightweight|standard|full` — required. `lightweight` → single-reviewer dispatch.
  `standard` = 2 debaters. `full` = 3-5 debaters.
- `--members "persona-a,persona-b,..."` — optional override of auto-selection.
- `<input>` — required. Plan mode: objectives document/text. Review mode: artifact path.

## Step 1 — Parse Arguments and Setup

Parse `--mode`, `--tier` (both required — fail with usage message if missing), `--members`
(optional), remaining text as `<input>`.

Generate run ID (`YYYY-MM-DD-HHhMM`), spawn timestamp, topic slug from input. Create
`docs/research/{run-id}-workdir/` (shared paper-trail convention with
`/coordinator:notebooklm-research` — detail: wiki). Set output path: plan mode →
`docs/plans/YYYY-MM-DD-{topic-slug}.md`; review mode →
`state/review-findings/YYYY-MM-DD-{topic-slug}-staff-review.md`. Advisory path:
`{scratch-dir}/advisory.md`.

Announce: "Running `/staff-session --mode {mode} --tier {tier}` on '{topic}'."

## Step 2 — Tier Routing

**`--tier lightweight`:** do NOT fire a Workflow. Route to `/review` (plan artifacts) or
`/review-code` (code artifacts) with the specified member (default `the Staff Engineer`). Announce and
**STOP — the rest of this command does not execute.**

**`standard`/`full`:** fires the chatty Workflow. Continue to Step 3.

## Step 3 — Scope (EM Direct)

Write `{scratch-dir}/scope.md` per the template in `pipelines/staff-session/templates-and-fields.md`
§ Step 3. Plan mode: EM writes objectives and constraints only — never the plan. Review mode: EM
provides artifact path and focus areas only — never pre-formed findings.

## Step 4 — Select Debaters

`--members` specified → those exact slugs are the debater list.

Not specified → match topic + scope to a domain category (the one piece of genuine judgment this
step retains). For `--tier full`, judgment-select 1-3 additional personas and append to an
explicit override list.

**Resolve the roster via the CLI, not a hand-maintained table:**

Shape W (rung 0) — ladder and shapes: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.
    `& "$env:COORDINATOR_SETTINGS_HOME\bin\staff-session-assemble.exe" --session-mode <plan|review> (--domain-signal "<category>" | --slug <slug> [--slug <slug> ...]) --json`

Returns `{personas: [{slug, agent_file, subagent_type}, ...], narration, source}`. Fails loud
(usage exit) on an unresolvable domain signal, unknown slug, or `the Director of Engineering` as a debater — surface that
error to the PM verbatim. `the Director of Engineering` is never a valid debater slug — fixed synthesizer identity
(`coordinator:eng-director`), the Workflow's synthesizer stage in Step 6. Resolver mechanics: wiki.

Debater count from the resolved roster: `standard` = 2 (default pair), `full` = 3-5 (default pair
+ judgment-selected additions).

Announce composition to PM before firing the Workflow, using the resolved `personas[].slug`:
> "I'll run this with **{Persona A}** and **{Persona B}** [+ **{Persona C}**...] debating, plus a
> staff synthesizer. Proceeding."

## Step 5 — Fill Prompts

The prompt templates in `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/` are not filled by hand: the
manifest `staff-session.manifest.yaml` names them, and the Workflow reads per-run values from
`scope.md`. Complete `{scratch-dir}/scope.md` with the run fields, the output and advisory paths,
and the Roster table from Step 4's `personas[]` (`slug`, `subagent_type` as `agent_type`,
persona name, perspective, `agent_file`) — see `pipelines/staff-session/templates-and-fields.md`
§ Template vocabulary and the brief. Create `{scratch-dir}/mail/`.

## Step 6 — Fire the Workflow

Emit the Workflow from the manifest; the EM supplies the brief and roster, never a script. CLI
resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` (Shape W, rung 0, on a
PowerShell host: `& "$env:COORDINATOR_SETTINGS_HOME\bin\emit-dispatch-workflow.exe" --pipeline
staff-session ...` with the same flags):

    ${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/emit-dispatch-workflow --pipeline staff-session --brief {scratch-dir}/scope.md --flag mode=<plan|review> --list roster=<slug>=<agent_type>,<slug>=<agent_type>,... --out {scratch-dir}/staff-session.workflow.mjs

`--brief` is the path to `scope.md` (a missing file is refused); `--list roster` carries one
`slug=agent_type` per debater from the Roster table Step 5 wrote (`agent_type` is Step 4's
`subagent_type`, never hardcoded — e.g. game-dev personas use `game-dev:`, not `coordinator:`);
`--flag mode` is the session mode, and an absent one is refused. Fire the printed `Workflow` line as ONE background `Workflow`. The graph is
`staff-session.manifest.yaml`: round 1 (all debaters in parallel), one rebuttal round for each
debater with unread mail, then the synthesizer (`coordinator:eng-director`) as overseer, the only
output to the EM. Ordering is the manifest's `depends_on`; there are no tasks or `blockedBy`.

## Step 7 — EM Is Freed

After firing, announce:

> "Staff session running on '**{topic}**' with **{N} debaters** ({names}) + **1 synthesizer**.
> Round 1 positions and challenges, one rebuttal round, then synthesis. I'm available for other
> work — I'll be notified when the Workflow completes."

**You are now free to continue with the PM.** Do not poll, monitor, or message the agents — the
script self-governs via `team-protocol.md`.

## Step 8 — On Workflow Completion Notification

1. Read `{output-path}`; verify substantive content (not just headers/a stub).
2. Mode-specific verification: plan mode → `## Implementation Plan` section with
   tasks/files/steps, and the marker `**Review:** Staff session ({participants}) — debated and
   synthesized. Ready for enrichment.` present byte-exact (this line is the single authoritative
   producer copy `enrich-and-review`'s gate matches against — never hand-type a second copy).
   Review mode → findings structured with severities/persona attributions, `## Verdict` line
   present.
3. Check for advisory: `test -f {scratch-dir}/advisory.md`; read if present.
4. Commit the output artifact (scoped): `git add -- {output-path}` then `git commit -m
   "staff-session: {mode} — {topic-slug}" -- {output-path}`. Then commit the paper trail as an
   explicit file list, not the whole workdir: `git add -- {scratch-dir}/scope.md
   {scratch-dir}/*-position.md {scratch-dir}/synthesis.md {scratch-dir}/advisory.md` then
   `git commit -m "staff-session: paper trail — {topic-slug}" -- {scratch-dir}/scope.md
   {scratch-dir}/*-position.md {scratch-dir}/synthesis.md {scratch-dir}/advisory.md` (omit
   `advisory.md` from both commands when the synthesizer wrote none) — the archive op in item 5
   cannot archive an untracked workdir; detail: wiki.
5. Archive-and-cleanup: invoke `fleet.archive_paper_trail` with `run_id={run-id}`,
   `topic_slug={topic-slug}`, `dry_run=false`. Moves `{scratch-dir}` to
   `docs/research/archive/YYYY-MM-DD-{topic-slug}/`, lands one scoped commit, removes the source
   tree. Safe no-op on re-run. Mechanics and CLI-trampoline caveat: wiki.
6. Present to PM: mode-specific framing ("ready for `/enrich-and-review`" / "synthesized
   findings"), 2-3 bullet executive summary, output path, and — if advisory exists — a pointer to
   the archived advisory.

## Error Handling

See `pipelines/staff-session/templates-and-fields.md` § Error Handling Matrix for the full
failure-mode → action table (debater crash, synthesizer failure, Workflow refusal, non-convergence,
unknown slug, missing output).
