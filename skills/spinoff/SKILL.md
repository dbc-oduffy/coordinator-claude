---
name: spinoff
description: "PM-GATED, never EM-initiated. Fork a mid-session topic into a handoff."
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "<slug> [optional one-line title]"
---

# Spinoff — Fork a Workstream Into Its Own Handoff

A **spinoff** is a handoff written mid-session by the current EM, addressed to a *future* picking-up EM, describing a workstream the current session does NOT intend to execute. (`spinoff` is canonical over "orphan-promotion handoff" / "ersatz-handoff".)

The mechanical spine — deliverable/initiative id inheritance, `origin_*` provenance capture, frontmatter scaffolding, and the scoped commit — is computed for you; you decide what it cannot resolve.

Compute it via `baton-assemble brief spinoff <slug> [title]`, resolved per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` (Shape W on PowerShell hosts). Every `judgment_points[]` entry carries its own guidance inline; resolve each one before its gated directive(s) proceed.

Feed resolutions back via `--decisions-file <path>` to `apply`: a JSON object mapping each `judgment_points[].id` to `{"disposition": "<value>"}`, a value from that point's own `dispositions[].value` in the same run's `brief`. `{"value": "<v>"}` is equivalent, sibling keys (a `decision_note`) are carried through, and both keys with disagreeing values fails loud.

**Run `apply`, not `brief`, when you mean to author.** `brief` is read-only; `apply` mutates. Hand-executing a brief's directives skips every in-process op, so the spinoff lands without its `origin_*` provenance.

## Step 0 — PM-authorization gate (hard requirement)

**Spinoffs require explicit PM authorization. The EM never initiates one on its own judgment.** Absent `/spinoff`, the skill name, or a trigger phrase directed at *this specific topic*, STOP — write no file. Topic drift counts: an earlier authorization does not cover a later topic. **Paraphrase is not authorization**: "another session will do this" or "we should spin that off sometime" is the EM observing a spinoff *might* be warranted.

No authorization? Surface a one-line proposal — "Candidate spinoff: `<slug>` — `<one-line topic>`. Authorize?" — and wait. Autonomous skills that previously auto-spinoffed (e.g. `/bug-blitz` Phase 2.1) obey this identically. Nothing below Step 0 runs until the PM says yes.

The single standing exception: `/mise-prep` mints staged batons for out-of-set missing-seam flags it could not handle, on the engine mint path and never via this skill.

## Step 2 — Authoring discipline

**Do NOT add interactive AskUserQuestion ceremony.** The EM writes the body from current session context; auto-filling it from heuristics produces shallow spinoffs.

Frontmatter and the canonical body-section skeleton are scaffolded; fill each section's content via Edit — the body is the value, never a placeholder stub. `coordinator-doc-new.py`'s `_spinoff_marker` stamps the trailing greppability marker — do not hand-type it.

Keep a hand-written `summary:` at or under 140 characters, or pass the title through `baton-assemble` instead; a hand-edit after scaffolding lands untruncated.

**`## Acceptance criteria` is a checkbox list — `- [ ]` / `- [x]`, never prose bullets.** The completeness gate at `/workstream-complete` counts boxes under that heading; zero boxes returns `indeterminate`.

Then mark the fork in the source session's own task tracker (or session memory) so the current EM does not absorb the work back, and surface the written path + workstream slug to the PM before returning to the prior work. A spinoff is a fork, not a context switch.

## `origin_*` vs `predecessor` vs `forked_from`

**Three distinct axes — never collapse them.** `origin_*` (`origin_session`, `origin_handoff`, `origin_handoff_id`, `origin_plan_id`, `origin_goal_id`) records *where this fork was spawned from*. `predecessor` is the continuation spine — invariantly `none` for every spinoff kind. `forked_from` is branch-point ancestry, a handoff-path.

**`origin_*` is set for you; never hand-set it.** The `handoff.author_fork` op owns all five; `coordinator-doc-new --type=spinoff` deliberately scaffolds **none** of them — their absence from a fresh file is correct. `handoff.author_fork` is an op name, not a `bin/` executable (exit 127) — `baton-assemble apply` dispatches it in-process. Do NOT build a parallel auto-populator or hand-write the fields when the directive appears to fail.

A spinoff carries only what `handoff.author_fork` derives — no session-local task list or review state. Everything else the picker needs goes in the body by hand.

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
