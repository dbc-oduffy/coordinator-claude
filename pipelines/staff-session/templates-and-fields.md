# Staff Session — Templates and Field Reference

Detail companion to `coordinator/skills/staff-session/SKILL.md`. Holds the scope.md template, the per-template field lists, and the error-handling matrix. Step numbers refer to the skill.

## Step 3 — scope.md template

Write to `{scratch-dir}/scope.md`:

```markdown
# Staff Session Scope

**Mode:** {plan|review}
**Tier:** {standard|full}
**Run ID:** {run-id}
**Date:** {YYYY-MM-DD}
**Topic:** {topic}

## Objectives / Artifact

{If plan mode: paste or reference the objectives document — what the PM wants built and why. Include any context from conversation. The debaters write the plan; the EM writes objectives and constraints only.}

{If review mode: path to the artifact being reviewed — {input-path}. Include any specific review focus areas the PM mentioned.}

## Context Files

{List any relevant files the PM mentioned, or auto-detected from the objectives/artifact — e.g., existing related plans, key source files, architecture docs. "None" if none.}

## Constraints

{Any PM-provided constraints: timeline pressure, dependencies, things to avoid, architectural boundaries. "None specified" if none.}

## Timing Preferences

{PM-specified preferences, or "None".}

## Output

- output_path: {path of the final document}
- advisory_path: {scratch-dir}/advisory.md
{Review mode only:}
- artifact_path: {input-path}

## Roster

| slug | agent_type | persona name | perspective | agent_file |
|------|-----------|--------------|-------------|------------|
| {personas[i].slug} | {personas[i].subagent_type} | {name} | {one-line perspective} | {personas[i].agent_file} |
```

The Roster table is the manifest's `roster` list: `slug` is `{{item}}` and `agent_type` is the per-item agent type of the round-1 and rebuttal stages. Never hardcode it (game-dev personas use `game-dev:`).

**Plan mode:** EM writes objectives and constraints only — never the plan itself. **Review mode:** EM provides the artifact path and focus areas; never pre-forms findings.

## Template vocabulary and the brief

The stage graph is `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/staff-session.manifest.yaml`: round 1 (`round1-plan` or `round1-review`, selected by the `mode` flag, one agent per roster row) -> `mailcheck` -> `rebuttal` (over the slugs the mail-check returns) -> `synthesizer`. Templates beside it:

- `planner-prompt-template.md` (plan-mode round 1), `reviewer-prompt-template.md` (review-mode round 1)
- `mailcheck-prompt-template.md`, `continuation-prompt-template.md` (rebuttal, both modes)
- `synthesizer-prompt-template.md` (both modes)

Templates carry no per-run bracket fields. They use the closed `{{...}}` set (`{{brief}}`, `{{item}}`, `{{scratch_dir}}`, `{{stage.<id>.output}}`) and read every other value from the brief, `scope.md`.

**Brief fields the templates read** (the Step 3 template above supplies each):
- `run_id` (Run ID), `mode`, `tier`, `date`, `topic`
- the objectives (plan mode) or `artifact_path` (review mode), and the Context Files list
- `output_path`, `advisory_path`
- the Roster: one row per debater, with `slug`, `agent_type`, persona name, perspective, `agent_file`

A persona's identity is its agent definition, loaded through the roster's `agent_type`. The EM does not inject an identity excerpt.

## Error Handling Matrix

| Failure | Action |
|---------|--------|
| Single debater crashes (no position written) | Synthesizer works with remaining positions. Note the gap: "Missing perspective: {persona}." EM can supplement manually. |
| Majority debater failure (>50% crash) | Synthesizer returns a failure summary without synthesizing; fall back to single-reviewer dispatch via `/review` (plan) or `/review-code` (code). |
| Synthesizer fails | EM reads raw debater positions from scratch dir. Manual synthesis is feasible — positions are structured. |
| Workflow refuses to start | Report to PM. Fall back to single-reviewer dispatch via `/review` (plan) or `/review-code` (code), or EM-authored plan. |
| Debate does not converge | The rebuttal round is bounded at one. Position docs capture the disagreement; synthesizer resolves or presents as dissent. |
| Unknown persona slug in `--members` | Halt before firing the Workflow. Report unknown slug, list valid slugs. Do not run a partial roster. |
| Output file missing after synthesizer completes | Read `{scratch-dir}/synthesis.md` as fallback. If also missing, read raw positions and report to PM. |
