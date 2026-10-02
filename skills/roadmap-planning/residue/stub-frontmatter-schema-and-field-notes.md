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
stub_id: <slug>-<NN>              # globally-unique; <NN> zero-padded, min two digits
deliverable_id: dlv-<slug>-<NN>  # durable join key; via mint-deliverable-id.py --stub-id
initiative: null                  # nullable FK to state/initiatives/<id>.yaml
authoring_session: state/roadmap/<run-id>/sprint-<N>/   # path-shaped; /pickup Reads it
workstream: <slug>
sprint: <N>                       # sprint grouping (typically 1–4)
wave: <N>                         # serialization-order grouping within a sprint
loe: <M|L|XL>                     # whole-baton t-shirt; XS/S never ship alone; XXL = mis-made (2.1.6)
covers: [<cluster-id>, ...]       # coverage units folded into this baton
deployment_state: awaiting_gate | ready_to_fire
gate_notes: <one-line>            # advisory prose; awaiting_gate needs >=1 of blocked_by / gate_notes
blocks: [<slug>-X, <slug>-Y]      # stub_ids this stub unblocks when shipped
blocked_by: [<slug>-Z]            # stub_ids that must ship first
scope:
  - <pathspec 1>
  - <pathspec 2>
category: roadmap
summary: <one-line, ≤120 chars>
---
```

## Fields NOT in the template

- **Lifecycle-set, never authored here:** `pickup_ready` (gate with `awaiting_gate` + `blocked_by`/`gate_notes`) and `shipped_in` (set by `/handoff` or `/workstream-complete`).
- **Fill at authoring time** (the scaffolder does not emit them; unrecoverable later):
  - `origin_session:` — `$CLAUDE_CODE_SESSION_ID`, else `null`. Scalar.
  - `origin_handoff:` — path of the active pickup baton, else `null`. Scalar; handoff paths only, and it MUST resolve in `state/handoffs/`, `archive/handoffs/`, or git history (unsure → `null`; an unresolvable value is hard-denied and locks the stub).
  - `origin_plan_id:` — `pln-…` id of the plan under execution, else `null`. Scalar.
  - `origin_goal_id:` — an **array** of `goal-…` ids even for one, else `null`.
  - Distinct from `predecessor`; never encode provenance there.

## Field rules

- **`wave:` is a concurrency-gate primitive, NOT a sprint synonym.** `roadmap-number-stubs` does not verify same-wave stubs are file-disjoint (Step 2.4 does). Never use `wave:` for time-boxing.
- **Hard gates → `blocked_by:`; advisory prose → `gate_notes:`.** `gate_dependency:` and `blocking_notes:` are deprecated: never author new values.
- **`## Soft seams`** is required in every stub body: one-line bullets naming the peer workstream/PR/stub and overlap. `scope:` is the HARD declaration.
- **Audit/spike sizing:** a single-consumer audit/spike folds as Phase 0 of its consumer's stub; standalone only for >=2 consumers.
- **Stub-dedup canonical = first deliberate per-stub commit**; dedup by `git mv` to `archive/` with a `.DUPLICATE-FROM-BULK-COMMIT.md` suffix, never `git rm`.

Rationale: wiki `roadmap-planning-residue.md` § Stub frontmatter — field notes.
