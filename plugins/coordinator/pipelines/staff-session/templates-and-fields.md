# Staff Session — Templates and Field Reference

Detail companion to `commands/staff-session.md`. Holds the scope.md template, the per-template field lists, and the error-handling matrix. Step numbers refer to the command.

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

{If plan mode: paste or reference the objectives document — what the PM wants built and why. Include any context from conversation. The team writes the plan; the EM writes objectives and constraints only.}

{If review mode: path to the artifact being reviewed — {input-path}. Include any specific review focus areas the PM mentioned.}

## Context Files

{List any relevant files the PM mentioned, or auto-detected from the objectives/artifact — e.g., existing related plans, key source files, architecture docs. "None" if none.}

## Constraints

{Any PM-provided constraints: timeline pressure, dependencies, things to avoid, architectural boundaries. "None specified" if none.}

## Timing Preferences

{PM-specified ceiling, or defaults: plan mode 10 min, review mode 8 min.}
```

**Plan mode:** EM writes objectives and constraints only — never the plan itself. **Review mode:** EM provides the artifact path and focus areas; never pre-forms findings.

## Step 6 — Template field reference

Read prompts from:
- Plan mode debaters: `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/planner-prompt-template.md`
- Review mode debaters: `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/reviewer-prompt-template.md`
- Synthesizer (both): `${CLAUDE_PLUGIN_ROOT}/pipelines/staff-session/synthesizer-prompt-template.md`

Also read each persona's identity excerpt (name, role, review standards, output format) from its agent definition file — injected at `[PERSONA_IDENTITY]`.

Fill ALL `[BRACKETED_FIELD]` placeholders before spawning.

**Common fields (all templates):**
- `[TOPIC]` → topic string
- `[MODE]` → plan|review
- `[TIER]` → standard|full
- `[SCRATCH_DIR]` → full path to scratch directory
- `[SCOPE_FILE]` → `{scratch-dir}/scope.md`
- `[SPAWN_TIMESTAMP]` → Unix epoch seconds from Step 1
- `[TASK_ID]` → this teammate's task ID
- `[SYNTHESIZER_NAME]` → `"synthesizer"` (teammate name — used for DONE messages)
- `[OUTPUT_PATH]` → output path for the final document

**Debater-specific:**
- `[PERSONA_IDENTITY]` → identity excerpt from agent definition
- `[PERSONA_SLUG]` → e.g., `patrik`
- `[POSITION_FILE]` → `{scratch-dir}/{persona-slug}-position.md`
- `[PEER_LIST]` → other debaters' teammate names + persona slugs (for messaging)
- `[MIN_MINUTES]` → 3 (both modes)
- `[MAX_MINUTES]` → 10 (plan), 8 (review)
- `[INPUT_PATH]` → review mode only: artifact being reviewed

**Synthesizer-specific:**
- `[DEBATER_COUNT]` → number of debaters
- `[DEBATER_SLUGS]` → comma-separated persona slugs
- `[ADVISORY_PATH]` → `{scratch-dir}/advisory.md`

## Error Handling Matrix

| Failure | Action |
|---------|--------|
| Single debater crashes (no position written) | Synthesizer works with remaining positions. Note the gap: "Missing perspective: {persona}." EM can supplement manually. |
| Majority debater failure (>50% crash) | EM is notified (only 1 or fewer debater tasks completed). `TeamDelete`, fall back to `/review-dispatch`. |
| Synthesizer fails | EM reads raw debater positions from scratch dir. Manual synthesis is feasible — positions are structured. |
| Team creation fails | Report to PM. Fall back to `/review-dispatch` or EM-authored plan. |
| DONE not received (debater complete but synthesizer not woken) | Synthesizer polls `TaskList`; if all debaters `completed` but no DONE after 2 min, proceeds anyway. EM may `SendMessage` nudge if synthesizer appears stalled. |
| Debate loops without converging | Ceiling time is hard cutoff; diminishing-returns detection also triggers convergence after 2 no-change exchanges. Position docs capture the disagreement; synthesizer resolves or presents as dissent. |
| Unknown persona slug in `--members` | Halt before team creation. Report unknown slug, list valid slugs. Do not create a partial team. |
| Output file missing after synthesizer completes | Read `{scratch-dir}/synthesis.md` as fallback. If also missing, read raw positions and report to PM. |
