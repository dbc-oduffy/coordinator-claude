---
name: spinoff
description: "PM-GATED, never EM-initiated. Fork a mid-session topic into a handoff."
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "<slug> [optional one-line title]"
---

# Spinoff — Fork a Workstream Into Its Own Handoff

A **spinoff** is a handoff written mid-session by the current EM, addressed to a *future* picking-up EM, describing a workstream the current session does NOT intend to execute. Older artifacts say "orphan-promotion handoff" or "ersatz-handoff"; `spinoff` is canonical.

The mechanical spine — deliverable/initiative id inheritance, `origin_*` provenance capture, frontmatter scaffolding, and the scoped commit — is computed for you. What follows is what it cannot resolve: the evidence is narrowed, you decide.

Compute it via `baton-assemble brief spinoff <slug> [title]`, resolved per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` (Shape W on PowerShell hosts). Every `judgment_points[]` entry in the returned object carries its own guidance inline — describing what each disposition means and how to carry it out, never a recommendation to pick from; resolve each one before its gated directive(s) proceed.

Feed those resolutions back by passing `--decisions-file <path>` to `apply`: a JSON object mapping each `judgment_points[].id` to `{"disposition": "<value>"}`. The legal values for a point are that point's own `dispositions[].value` entries from the same run's `brief` output. `{"value": "<v>"}` is an exact equivalent, sibling keys (a `decision_note`) are carried through, and supplying both keys with disagreeing values fails loud.

---

## Step 0 — PM-authorization gate (hard requirement)

**Spinoffs require explicit PM authorization. The EM never initiates one on its own judgment.** Absent `/spinoff`, the skill name, or a trigger phrase directed at *this specific topic*, STOP — write no file. Topic drift counts: an earlier "spinoff that auth thing" does not authorize a later spinoff of "the migration cleanup."

**Paraphrase is not authorization.** Statements of *eventual intent* — "another session will do this," "we should spin that off sometime" — are the EM observing a spinoff *might* be warranted, not the PM invoking the primitive.

No authorization? Surface a one-line proposal — "Candidate spinoff: `<slug>` — `<one-line topic>`. Authorize?" — and wait. Autonomous skills that previously auto-spinoffed (e.g. `/bug-blitz` Phase 2.1) obey this identically. Nothing below Step 0 runs until the PM says yes.

The single standing exception: `/mise-prep` mints staged batons for out-of-set missing-seam flags it could not handle, on the engine mint path and never via this skill, under the PM's "this can at least spawn a spinoff baton".

---

## Step 2 — Authoring discipline

**Do NOT add interactive AskUserQuestion ceremony.** The EM writes the body from current session context; the PM has just told you what the spinoff covers. Auto-filling the body from heuristics produces shallow spinoffs the picking-up EM can't act on.

Frontmatter and the canonical body-section skeleton are scaffolded for you; fill each section's content via Edit — the body is the value, never a placeholder stub. `coordinator-doc-new.py`'s `_spinoff_marker` already stamps the trailing greppability marker — do not hand-type it.

Keep a hand-written `summary:` at or under 140 characters, or pass the title through `baton-assemble` instead. `handoff_author_fork.py` truncates `summary` ahead of the claim gate, but a hand-edit after scaffolding lands untruncated.

**`## Acceptance criteria` is a checkbox list — `- [ ]` / `- [x]`, never prose bullets.** The completeness gate at `/workstream-complete` counts boxes under that heading; zero boxes returns `indeterminate`. A trailing colon or parenthetical on the heading is fine, and a nested `###` under it still counts.

Then mark the fork in the source session's own task tracker (or session memory) so the current EM does not absorb the work back, and surface the written path + workstream slug to the PM before returning to the prior work. A spinoff is a fork, not a context switch.

---

## `origin_*` vs `predecessor` vs `forked_from`

**Three distinct axes — never collapse them.** `origin_*` (`origin_session`, `origin_handoff`, `origin_handoff_id`, `origin_plan_id`, `origin_goal_id`) records *where this fork was spawned from*. `predecessor` is the continuation spine — invariantly `none` for every spinoff kind, never a place to encode origin provenance. `forked_from` is branch-point ancestry, a handoff-path.

> **Producer note — `origin_*` is set for you; never hand-set it.** The `handoff.author_fork` op owns all five: it resolves `origin_session` from the current session, derives `origin_handoff`/`origin_handoff_id` from the baton that session holds (`claimed_by` match), and takes `origin_plan_id`/`origin_goal_id` from the caller. `coordinator-doc-new --type=spinoff` deliberately scaffolds **none** of them — their absence from a fresh file is correct.
>
> **`handoff.author_fork` is an op name, not a `bin/` executable** (exit 127) — `baton-assemble apply` dispatches it in-process. Do NOT build a parallel auto-populator or hand-write the fields when the directive appears to fail.

**Run `apply`, not `brief`, when you mean to author.** `brief` is read-only — it *emits* `directives[]` as data. `apply` walks that list and mutates. Hand-executing a brief's directives skips every in-process op, so the spinoff lands without its `origin_*` provenance.

---

## What travels with a spinoff

A spinoff carries only what `handoff.author_fork` derives (`origin_*`, id inheritance, scaffold) — no session-local task list or review state. Everything else the picker needs goes in the body by hand.

## Anti-scope

- **`reviewed_at_workstream_complete:` does NOT apply to spinoffs** — a spinoff has no executed diff to review; never add it to spinoff frontmatter.
- **Don't bake content generation into this skill** — the scaffold provides the shape, the EM the content.
- **Don't auto-delete or auto-merge picked-up spinoffs.** They follow the standard handoff lifecycle (`/pickup` mutates frontmatter; the picker's `/handoff` or `/workstream-complete` archives). The `<!-- consumed: -->` marker is deprecated — never write it.
- **Don't extend `kind:` to other values speculatively.** The hand-authorable set is deliberately narrower than the schema enum (see `schemas/handoff.schema.json`, including engine-only kinds no human or EM may scaffold).
- **Don't replace `/handoff` with `/spinoff`** — the spinoff writer still ends their own session with `/handoff`. Don't migrate prior orphan-promotion handoffs.

`venue: workstation` marks a spinoff that needs a human or a workstation session at a terminal — a cloud pickup sweep lists it as not-claimable. Absent, or `venue: any`, means either venue may claim it.

## See also

- `skills/handoff/SKILL.md` — end-of-session continuation handoffs.
- `skills/pickup/SKILL.md` — picking up a handoff (recognizes `kind: spinoff`).
- `CLAUDE.md` § "Handoff Lineage — Single Predecessor, No Adjacency-Inference".
- `schemas/handoff.schema.json` — allowed `kind:` values.
