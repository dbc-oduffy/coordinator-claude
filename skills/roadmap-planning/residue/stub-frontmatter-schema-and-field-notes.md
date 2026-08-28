## The scaffolded frontmatter schema (for reference; do not hand-author)

```yaml
---
title: <one-line>
created: <YYYY-MM-DD>
branch: <current-branch>
status: open
predecessor: none                 # load-bearing for spinoffs
kind: roadmap-baton
roadmap_id: <run-id>              # groups all stubs from one roadmap-planning invocation
stub_id: <slug>-<NN>              # globally-unique stub code; <slug> is this roadmap's short prefix, <NN> the zero-padded integer (min two digits, e.g. 04, 12)
deliverable_id: dlv-<slug>-<NN>  # durable join key; set to dlv-<stub_id> via mint-deliverable-id.py --stub-id
initiative: null                  # nullable FK to state/initiatives/<id>.yaml; set when this roadmap belongs to a named initiative
authoring_session: state/roadmap/<run-id>/sprint-<N>/   # path-shaped audit trail back to the sprint's authoring artifacts; /pickup can Read this deterministically
workstream: <slug>
sprint: <N>                       # sprint grouping (typically 1–4)
wave: <N>                         # serialization-order grouping within a sprint
loe: <M|L|XL>                     # whole-baton t-shirt, sizing's loe.tshirt vocabulary. XS/S
                                  # never ship alone; XXL means the roadmap is mis-made (2.1.6)
covers: [<cluster-id>, ...]       # coverage units folded into this baton; carries Phase 1
                                  # verdict accounting when one baton absorbs several clusters
deployment_state: awaiting_gate | ready_to_fire
blocking_notes: <one-line>        # advisory prose when awaiting_gate. awaiting_gate needs >=1 of
                                  # blocked_by / blocking_notes / gate_dependency; author the
                                  # first two (gate_dependency is deprecated, schema C2).
blocks: [<slug>-X, <slug>-Y]      # stub_ids that this stub unblocks when shipped
blocked_by: [<slug>-Z]            # stub_ids that must ship first
scope:
  - <pathspec 1>
  - <pathspec 2>
category: roadmap
summary: <one-line, ≤120 chars>
---
```

`authoring_session` is path-shaped so `/pickup` can deterministically `Read` origin context. The wiki schema describes this field as a one-line description; for roadmap stubs we narrow it to a directory path (roadmap-specific narrowing; wiki amends if the convention broadens).

## Two schema fields NOT in the template

They're populated by lifecycle events, not by `roadmap-planning`:

- **`pickup_ready: true`** — defaults to absent for roadmap stubs. Absence triggers a non-blocking warning at `/pickup` time (not a block); the EM proceeds to mutation. `awaiting_gate` + `blocked_by`/`blocking_notes` is the correct sequencing mechanism for stubs that must not be picked up yet — do not use `pickup_ready` absence as a gate.
- **`shipped_in: <sha-or-PR-ref>`** — never authored by the roadmap-planning skill. Set by `/handoff` or `/workstream-complete` post-execution when the work transitions to `deployment_state: shipped`. `/distill` requires this field present before deleting an archived stub (Phase 4c safety guard).

## Four more fields NOT in the scaffolded template — fill at stub-authoring time

`origin_session`, `origin_handoff`, `origin_plan_id`, `origin_goal_id` are not emitted by `_scaffold_spinoff_roadmap`. Resolve each from live session context when writing the stub; they are the cheapest to capture correctly and impossible to reconstruct an hour later:

- **`origin_session:`** — `$CLAUDE_CODE_SESSION_ID` if set in the environment. A global UUID (no prefix). Emit explicit `null` when the env var is unset. Scalar.
- **`origin_handoff:`** — the path of the active pickup baton this session was opened with (e.g. `state/handoffs/<YYYY-MM-DD>_<topic>.md`). Emit explicit `null` if this session has no active baton. Scalar. **Handoff paths only — a memo-origin session emits `null`.** The schema (engine repo Rule C2-1b) requires a `state/handoffs/` path when non-null; a `cross-repo/inbox/…` memo path fails validation and blocks pickup. Carry the memo citation in `authoring_session:` instead. **The value MUST resolve** — confirm the path exists in `state/handoffs/`, `archive/handoffs/`, or git history before writing it; if you cannot confirm the baton path resolves on disk, emit `null` instead of a guessed or stale path. **Warning:** an unresolvable `origin_handoff` is hard-denied at write time by the engine repo's `coordinator_core/write_guards/validate_frontmatter_schema_deny.py`, and once committed it locks the stub against ALL future Edits — the guard revalidates whole post-edit frontmatter, so even a body-only edit is denied. Archival does NOT trigger this: `dag.resolve_target` resolves through `archive/handoffs/YYYY-MM/` and then git history, so only a path that never existed fails.
- **`origin_plan_id:`** — the `pln-…` id of the plan under execution at roadmap-authoring time, if any. Emit explicit `null` otherwise. Scalar.
- **`origin_goal_id:`** — an **array** of `goal-…` ids (kebab-case slug, `goal-` prefix) for the goal(s) this roadmap serves. Emit explicit `null` when no goal context is active. **Array even for a single goal** (multi-goal roadmaps are a documented real case — a roadmap serving multiple goals maps many-to-many).

> **Origin-provenance axis — distinct from `predecessor`:** `origin_*` records *where this stub was spawned from* (session, baton, plan, goal). This is a DISTINCT axis from `predecessor` (continuation spine — always `none` for spinoff kinds), `forked_from` (branch-point ancestry, a handoff-path), and `deliverable_id` (the `dlv-` grouping key). Never encode origin provenance in `predecessor:`.
>
> **Producer note:** do NOT build a parallel auto-populator for these fields — this is documentation-level frontmatter-fill guidance, not scaffolding logic.

## Field semantics — clarifications

- **`wave: <N>` is a concurrency-gate primitive, NOT a sprint synonym.** Two distinct shapes:
  - **Wave** = single-dispatch parallel fan-out within a sprint, once verified. `roadmap-number-stubs` assigns a wave floor from DAG depth; it does NOT verify same-wave stubs are file-disjoint — that check is Step 2.4's judgment residue, run before fan-out, not a property the numbering op guarantees "by construction". Two independent (`blocked_by: []`) stubs at the same depth may also be numbered into distinct wave slots rather than sharing one, to satisfy Audit 2's `≤1 ready_to_fire` per `(roadmap_id, sprint, wave)` rule — see Step 2.1.5. Cost profile: one EM-session of dispatch + sync, once disjointness is confirmed. Risk profile: bounded — failure of one wave-N stub does not invalidate sibling stubs.
  - **Sprint** = a coherent slice of work with its own JTBD, research, and exit condition — not a time-box. Sprints run concurrently wherever nothing gates them; wave's "within a sprint" containment is scope nesting, not temporal nesting. Cost profile: multi-day, multi-session, with `/handoff` between sessions. Risk profile: compound — a sprint's architectural finding can invalidate a scope-nested later sprint's stubs authored against a now-wrong assumption.
  Do NOT use `wave:` for time-boxing or unit-of-effort grouping; `sprint:` is for that. Waves of one stub each are NOT a tell that a sprint sequence has been mislabelled as parallelism — under Audit 2 they are often correct by construction. Check `blocked_by` before concluding anything about sequencing.
- **Hard gates go in `blocked_by:`; advisory prose goes in `blocking_notes:`.** A hard gate is a precondition that must land before this stub can be dispatched at all — typically a sibling stub_id, a merged PR, or a flipped feature flag — and it belongs in `blocked_by` as a resolvable slug, which is what gives the gate an index instead of a free-text one-liner. Soft cross-repo seams (advisory cues like "consider coordinating with peer-repo PR-N" or "watch for X downstream") belong in the stub body's `## Soft seams` section, never in a machine-read gate field. `blocked_by` drives query-records surfacing and `/pickup` gating logic; polluting it with unresolvable text causes false "still gated" reports. (`gate_dependency:` is the deprecated predecessor of this pair — see Step 2.1. It still validates on existing records, so you will meet it in the corpus; do not author new values into it.)
- **Soft seams declared in body, not frontmatter.** Each stub MUST include a `## Soft seams` section in its body (Step 2.2) enumerating workstreams it may overlap with, advisory cross-repo coordination notes, and any "consider coordinating with X" cues. Format: bulleted list, each entry one line, naming the peer workstream/PR/stub and the nature of the overlap (file-region, schema-shape, timing). The frontmatter `scope:` block remains the HARD declaration (machine-readable, drives `/pickup` safety-commit pathspec); `## Soft seams` is the SOFT declaration (human-readable, drives EM judgment when sequencing parallel waves).
- **Audit-spike sizing heuristic — an instance of the Step 1.2 grain floor (`SKILL.md:66`).** A single-consumer audit/spike is sub-baton-grain: fold it as Phase 0 of that consumer's implementation stub rather than authoring a standalone one. Standalone audit stubs earn their own stub_id only when ≥2 downstream consumers will read the audit output to define their own behavior.
- **Stub-dedup canonical = git commit provenance, not the filename timestamp.** When two stubs of the same stub_id exist (e.g. `11xxxx_…_<slug>-3.md` and `14xxxx_…_<slug>-3.md`), the canonical is whichever was committed FIRST as a deliberate per-stub commit — NOT whichever has the earlier HHMMSS prefix. Filename timestamps can invert the truth when an HHMMSS-earlier draft gets bulk-committed later than the HHMMSS-later canonical. Determine canonical from `git log -- <each-stub-path>`, the STUB-INDEX, and any archival precedent. Dedup by `git mv` to `archive/` with a `.DUPLICATE-FROM-BULK-COMMIT.md` suffix, never `git rm`: a duplicate is often the richer draft, and the suffix keeps it for the implementing EM at zero cost.
