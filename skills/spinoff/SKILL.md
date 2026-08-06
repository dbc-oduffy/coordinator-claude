---
name: spinoff
description: "PM-GATED, never EM-initiated. Fork a mid-session topic into its own handoff."
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "<slug> [optional one-line title]"
---

# Spinoff — Fork a Workstream Into Its Own Handoff

A **spinoff** is a handoff written mid-session by the current EM, addressed to a *future* picking-up EM, describing a workstream the current session does NOT intend to execute. Synonyms used in older artifacts: "orphan-promotion handoff," "ersatz-handoff." `spinoff` is the canonical term.

The assembler computes the mechanical spine — deliverable/initiative id inheritance, `origin_*` provenance capture, frontmatter scaffolding, and the scoped commit — and returns one decision object. What follows is the judgment residue the assembler cannot resolve for you: it narrows the evidence, you decide.

Compute it via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/baton-assemble" brief spinoff <slug> [title]`. Every `judgment_points[]` entry in the returned object carries its own guidance inline — describing what each disposition means and how to carry it out, never a recommendation to pick from; resolve each one before its gated directive(s) proceed.

Feed those resolutions back by passing `--decisions` to `apply`: a JSON object mapping each `judgment_points[].id` to `{"disposition": "<value>"}`. The legal values for a given point are that point's own `dispositions[].value` entries from the same run's `brief` output — read them there rather than guessing. `{"value": "<v>"}` is accepted as an exact equivalent of `{"disposition": "<v>"}`, and sibling keys (a `decision_note`, for instance) are carried through; supplying both keys with disagreeing values fails loud.

---

## Step 0 — PM-authorization gate (hard requirement)

**Spinoffs require explicit PM authorization. The EM never initiates a spinoff on its own judgment.** If the PM has not typed `/spinoff`, named the skill, or explicitly said "spinoff this" / "make a spinoff for X" / one of its trigger phrases for *this specific topic*, STOP. Do not write a spinoff file.

Topic drift counts: an earlier "spinoff that auth thing" does NOT authorize a later spinoff of "the migration cleanup." Each spinoff is its own authorization.

**Paraphrase is not authorization.** A statement of *eventual intent* — "another session will do this," "we should spin that off sometime," "that's really its own workstream," "someone should pick that up" — is the EM observing that a spinoff *might* be warranted. It is NOT the PM invoking the spinoff primitive. The authorizing speech act is the literal trigger: `/spinoff`, the skill name, or a trigger phrase, directed at *this specific topic now*. When you find yourself inferring authorization from intent-shaped prose rather than a literal trigger, STOP and surface the candidate (one-line proposal, below) — do not promote your read of the PM's intent into a write.

If the EM identifies a candidate workstream that *would* warrant a spinoff but the PM has not authorized one, surface it as a one-line proposal — "Candidate spinoff: <slug> — <one-line topic>. Authorize?" — and wait. Do not proceed past Step 0 until the PM says yes.

Autonomous skills that previously auto-spinoffed (e.g. `/bug-blitz` Phase 2.1) MUST surface the candidate list and obtain PM authorization before writing any spinoff file. The rest of this skill only runs after authorization.

---

## Step 2 — Authoring discipline

**Do NOT add interactive AskUserQuestion ceremony.** The EM (you) writes the body from current session context. The PM has just told you what the spinoff covers; you have everything you need. A skill that auto-fills the body from heuristics will produce shallow spinoffs the picking-up EM can't act on.

The assembler scaffolds frontmatter and the canonical body-section skeleton; fill each section's content via Edit — the body is the value, never a placeholder stub. End the file with a single-line HTML comment marker for greppability:

```html
<!-- spinoff: <YYYY-MM-DD> by current EM during <authoring_session> -->
```

Then mark the fork in the source session's own task tracker (or session memory) so the current EM does not accidentally absorb the work back into the active session, and surface the written path + workstream slug to the PM before returning to the work the current session was already doing. A spinoff is a fork, not a context switch.

---

## `origin_*` vs `predecessor` vs `forked_from`

**Origin-provenance is a distinct axis from `predecessor`.** `origin_*` (`origin_session`, `origin_handoff`, `origin_handoff_id`, `origin_plan_id`, `origin_goal_id`) records *where this fork was spawned from* — session, baton, plan, goal. It is DISTINCT from `predecessor` (the continuation spine — always `none` for spinoffs) and from `forked_from` (branch-point ancestry, a handoff-path). Never set `predecessor:` to encode origin provenance; `predecessor: none` is invariant for all spinoff kinds. The assembler resolves and writes the `origin_*` fields; this note exists so you never confuse the axes when hand-adjusting frontmatter.

> **Producer note — `origin_*` is set for you; never hand-set it.** claude-klabauter's `handoff.author_fork` op owns the five `origin_*` fields. It resolves `origin_session` from the current session, then derives `origin_handoff`/`origin_handoff_id` by finding the baton that session currently holds (the handoff whose `claimed_by` matches it); `origin_plan_id`/`origin_goal_id` are caller-supplied. `coordinator-doc-new --type=spinoff` deliberately scaffolds **none** of them — their absence from a freshly-scaffolded file is correct, not a gap to fill in by hand.
>
> **`handoff.author_fork` is an op name, not a `bin/` executable.** It appears in the brief's `directives[]` as `"cli": "handoff.author_fork"`, but nothing under `settings-home/bin` answers to that name and invoking it as a shell command exits 127. `baton-assemble apply` dispatches it in-process through its own table. Do NOT build a parallel auto-populator, and do NOT hand-write the fields when the directive appears to fail.

**Run `apply`, not `brief`, when you mean to author.** `baton-assemble brief` is read-only — it *emits* `directives[]` as data and executes nothing. `baton-assemble apply` is what walks that list and actually mutates. Hand-executing a brief's directives one at a time is the mistake this paragraph exists to prevent: it silently skips every in-process op in the dispatch table, so the spinoff lands with its `origin_*` provenance missing.

---

## Anti-scope

- **`reviewed_at_workstream_complete:` does NOT apply to spinoffs.** Spinoffs are forks authored mid-session, not continuations of a session's own work — the workstream-complete review marker tracks what the *current* EM reviewed before handing off a workstream they were executing. A spinoff has no executed diff to review; it is a brief for someone else's future session. Do not add `reviewed_at_workstream_complete:` to spinoff frontmatter.
- **Don't bake content generation into this skill.** No heuristic templates that fill `## Specification` from the slug. The body is the value — the assembler provides the shape, the EM provides the content.
- **Don't auto-delete or auto-merge spinoffs that get picked up.** Spinoffs follow the standard handoff lifecycle on consumption: `/pickup` mutates frontmatter in place, then the picking-up session's `/handoff` (chain-archival) or `/workstream-complete` moves the file to `archive/handoffs/`. The `<!-- consumed: -->` marker is deprecated — do not write it.
- **Don't extend `kind:` to other values speculatively.** Further extension requires a documented recurring shape, not speculation — the hand-authorable set is deliberately narrower than the schema enum (see `schemas/handoff.schema.json` for the full list, including assembler-only kinds no human or EM may scaffold).
- **Don't replace `/handoff` with `/spinoff`.** They serve different needs. The writer-of-spinoff still ends their own session with `/handoff`.
- **Don't migrate prior orphan-promotion handoffs.** Their lifecycle is over; renaming retroactively is churn. New spinoffs use the `kind:` field; old ones stay as-is.

## See also

- `commands/handoff.md` — end-of-session continuation handoffs.
- `commands/pickup.md` — picking up a handoff (recognizes `kind: spinoff` and emits a banner).
- `CLAUDE.md` § "Handoff Lineage — Single Predecessor, No Adjacency-Inference" — doctrine on why `predecessor: none` is correct for spinoffs.
- `schemas/handoff.schema.json` — frontmatter schema enumerating allowed `kind:` values.
