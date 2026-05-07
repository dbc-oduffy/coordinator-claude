# 07 — Super-skills

> Why most skills are prose, why the load-bearing ones can't be, and what we did about it.

## The problem with skills as prose

A skill in this system is a behavioral protocol — a checklist a pilot follows, not a paragraph a reader internalizes. That distinction was clear in the docs from early on. It was less clear in the actual skill bodies.

By v1.x we had ~50 skills. Most were prose: "Step 1: consider whether this is X or Y. If X, do A. If Y, do B." Read fast, sound reasonable, ship.

For passive skills — orientation, conventions, naming — that worked. The skill loaded into context, shaped behavior, and the cost of skimming-instead-of-checklisting was small. The skill nudged; the EM did roughly the right thing.

For *load-bearing* skills, prose failed. Plan-writing was the worst case. "Plan" is a trigger word that's supposed to invoke a specific pipeline:

1. Triage — is this actually plan-shaped, or is the right answer a thirty-second edit?
2. Substrate verification — paths, framework names, helper APIs grepped against disk before drafting
3. Composition — the four PM doctrinal lenses (acceptance criteria, non-goals, scope mode, definition of ready)
4. Exit — prior-art-checker → the Staff Engineer (`coordinator:staff-eng`) → integrator chain

When that procedure lived as prose inside `coordinator:writing-plans`, the EM read it, internalized "yeah I know how to write a plan," and wrote a plan body straight to disk via the `Write` tool — bypassing every gate. The skill loaded; the procedure didn't run. By the time anyone noticed, the plan had been reviewed by the Staff Engineer against unverified substrate, the prior-art-checker had never been dispatched, and the four lenses had been satisfied in vibes rather than fields.

This wasn't a one-off. It was structural. Procedure-as-prose is procedure that gets skimmed.

## The super-skill pattern

A super-skill isn't a longer skill. It's a different *shape*: a decision-tree router with named branches, where the EM walks branches by condition rather than reading prose. The shape we landed on for `coordinator:plan`:

- **Branch A — Triage.** Is this plan-shaped? If no → exit to a thirty-second edit. If yes → continue. Triage lives *inside* the skill, not in the EM's pre-skill judgment, because the failure mode the skill exists to prevent is the EM judging "this doesn't need a skill" and skipping it.
- **Branch B — Substrate.** Verify paths, framework names, helper APIs against disk. Produce a substrate-verified context block.
- **Branch C — Compose.** Walk the four PM lenses. Each lens is a structured field, not a paragraph.
- **Exit — Handoff.** Dispatch the prior-art-checker pre-flight, then the Staff Engineer, then the integrator. The skill exits to a chain, not to "now write the plan."

Long-form doctrine — the *why* behind each branch — moved to `docs/wiki/writing-plans.md`. Reference material lives in wikis. Procedure lives in skills. Conflating them produced the prose skills that got skimmed.

## What got renamed, what got removed

Three renames and one deletion shipped in v2.0.0:

- `coordinator:writing-plans` → `coordinator:plan`. Refactored from prose to super-skill shape.
- `coordinator:requesting-code-review` → `coordinator:review-code`. Same refactor.
- `coordinator:requesting-review` → `coordinator:review`. Same refactor.
- `coordinator:using-git-worktrees` removed entirely. The doctrine carried by that skill — "worktrees forbidden, the daily branch is the integration surface" — collapsed to a one-line bullet in `CLAUDE.md` § Concurrent-EM Git Operations. A skill whose entire content is "don't do this" doesn't need to exist; the rule belongs in the doctrine file the EM already loads.

Names matter. `writing-plans` reads like a how-to guide. `plan` reads like a verb the EM is being asked to invoke. The rename is the invocation cue.

## Plan-trigger binding

The other half of the fix was mechanical. `CLAUDE.md` § Plan-First Workflow now states, in bold:

> **Plan is a skill invocation, not a writing instruction.** When the PM types any of "plan", "let's plan", "write a plan", "draft a plan", "break this down", "plan the implementation" — the EM's first action is `Skill(coordinator:plan)`, period. Triage of "should I plan vs. just do it" lives inside the skill (Branch A), not in the EM's pre-skill judgment.

That paragraph exists because the EM kept hearing "plan" and reaching for `Write` instead of `Skill`. Mechanically binding the trigger word to the skill invocation closes the gap. Writing a plan body to disk via `Write` without first invoking the skill is now an explicit doctrine violation, re-do via the skill.

## What hasn't changed

Most skills are still prose. That's fine. A skill that says "when committing, prefer scoped staging over `git add -A`" doesn't need a decision tree — the EM either remembers or doesn't, and the cost of forgetting is bounded.

Super-skill shape is reserved for the load-bearing ones — the skills where skipping a step has expensive downstream consequences. Plan, review, review-code. Maybe one or two more in the future. Most things stay prose.

## The lesson the system learned about itself

Doctrine lives in two layers. **Procedure** — the steps you walk every time, in order, no improvisation — belongs in a skill, structured as a decision tree, mechanically bound to its trigger. **Reference** — the *why* behind each step, the long-form rationale, the edge cases — belongs in a wiki.

Mixing them produces prose skills that read well and get skimmed. Separating them produces skills that fire reliably and wikis that get read on demand. The wiki doesn't need to be loaded; the skill does. Conflating the two media costs you both.
