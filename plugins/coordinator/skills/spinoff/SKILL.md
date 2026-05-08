---
name: spinoff
description: Fork a mid-session topic into its own pickup-able handoff (a spinoff)
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "<slug> [optional one-line title]"
---

# Spinoff — Fork a Workstream Into Its Own Handoff

A **spinoff** is a handoff written mid-session by the current EM, addressed to a *future* picking-up EM, describing a workstream the current session does NOT intend to execute. Synonyms used in older artifacts: "orphan-promotion handoff," "ersatz-handoff." `spinoff` is the canonical term.

**When to use this vs. its neighbors:**

- Use `/handoff` when ending the *current* session's *current* work — predecessor links to whatever you're continuing.
- Use `/spinoff` mid-session when a topic comes up that deserves its own session and you don't want to context-switch into it now. The current session keeps its own work; the fork lives at `tasks/handoffs/` for someone else (or future-you) to pick up.
- Use the improvement queue (one-line entry) for half-formed ideas. A spinoff is the same level of detail as a real handoff: load-bearing context, references, acceptance criteria, anti-scope.

## Trigger phrases

"spinoff", "make a spinoff for X", "ersatz handoff", "orphan handoff", "fork off this workstream", "make a handoff for someone else", "carve out X into its own pickup", "split this off as a spinoff."

## Workflow

### Step 1: Capture the slug and title

The PM gives you `$ARGUMENTS` of shape `<slug> [optional title]`. The slug becomes part of the filename; the title is the H1 of the handoff body. If only a slug was provided, ask the PM for a one-line title before writing.

### Step 2: Author the body

**Do NOT add interactive AskUserQuestion ceremony.** The EM (you) writes the body from current session context. The PM has just told you what the spinoff covers; you have everything you need. A skill that auto-fills the body from heuristics will produce shallow spinoffs the picking-up EM can't act on.

Path: `tasks/handoffs/{YYYY-MM-DD}_{HHMMSS}_{slug}.md`

Frontmatter (all fields literal — do not paraphrase keys):

```yaml
---
title: <one-line title>
created: <YYYY-MM-DD>
branch: <current branch — git symbolic-ref>
status: active
kind: spinoff
predecessor: none
authoring_session: <one-line description of the session that wrote this>
workstream: <slug>
scope:
  - <pathspec 1>
  - <pathspec 2>
---
```

`status: active` (it's ready for pickup). `predecessor: none` always — spinoffs have no continuity ancestor. `authoring_session` replaces the predecessor link as the audit trail back to origin. `workstream` lets `/workday-start` and `/pickup` group related forks.

Body sections (adapted from the regular handoff template):

- `# <title>` (H1 mirrors frontmatter title)
- Opening paragraph: one sentence on **why this exists as its own session** — what triggered the fork, why it deserves separation from the current work.
- `## What this covers` — origin context. Plain English on the topic, who's affected, what surface is in play.
- `## Reference materials (read first)` — file paths the picking-up EM will need, each with a one-line "what's in it" annotation. Include any session-context artifacts (plan paths, scout outputs) that aren't obvious from a fresh `git log`.
- `## Specification` — the actual work spec. Be concrete enough that a context-less EM can act.
- `## Acceptance criteria` — checklist a picking-up EM gates completion against.
- `## Recommended next steps for the picking-up EM` — 3-7 numbered, each verifiable.
- `## Anti-scope` — failure modes a context-less EM might hit. Negative scope.
- (Optional) `## Out of scope` — adjacent work explicitly NOT included.

End the file with a single-line HTML comment marker for greppability:

```html
<!-- spinoff: <YYYY-MM-DD> by current EM during <authoring_session> -->
```

### Step 3: Mark in the source session

Append one line to your session task tracker (or session memory if no tracker exists) noting:

```
spinoff written: <path> — do NOT pick this up in current session.
```

This prevents the current EM from accidentally absorbing the work back into the active session.

### Step 4: Commit

Single explicit-path commit. Do NOT blanket-stage; the working tree probably has other concurrent-session files.

```bash
git add <handoff-path>
~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "chore(spinoff): <slug> [authored mid-session]"
```

The auto-push hook handles propagation.

### Step 5: Surface to PM

Print one line:

```
Spinoff written: <path> — workstream: <slug>. Pick up with /pickup <filename> from any session.
```

Then return to the work the current session was doing **before** the fork. A spinoff is a fork, not a context switch.

## Anti-scope

- **Don't bake content generation into this skill.** No heuristic templates that fill `## Specification` from the slug. The body is the value — the skill provides the shape, the EM provides the content.
- **Don't auto-delete or auto-merge spinoffs that get picked up.** `/update-docs`'s archival phase handles archival via the `<!-- consumed: -->` marker. Spinoffs follow the same path on consumption.
- **Don't extend `kind:` to other values speculatively.** Two values (`session-handoff`, `spinoff`) are sufficient until a third recurring shape surfaces.
- **Don't replace `/handoff` with `/spinoff`.** They serve different needs. The writer-of-spinoff still ends their own session with `/handoff`.
- **Don't migrate prior orphan-promotion handoffs.** Their lifecycle is over; renaming retroactively is churn. New spinoffs use the `kind:` field; old ones stay as-is.

## See also

- `commands/handoff.md` — end-of-session continuation handoffs.
- `commands/pickup.md` — picking up a handoff (recognizes `kind: spinoff` and emits a banner).
- `CLAUDE.md` § "Handoff Lineage — Single Predecessor, No Adjacency-Inference" — doctrine on why `predecessor: none` is correct for spinoffs.
- `schemas/handoff.yaml` — frontmatter schema enumerating allowed `kind:` values.
