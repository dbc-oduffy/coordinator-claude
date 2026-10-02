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

- **Lifecycle-set, never authored here:** `pickup_ready` (absence is not a gate — gate with
  `awaiting_gate` + `blocked_by`/`gate_notes`) and `shipped_in` (set by `/handoff` or
  `/workstream-complete`; `/distill` requires it before deleting an archived stub).
- **Fill at authoring time** (`_scaffold_spinoff_roadmap` does not emit them; they cannot be
  reconstructed later):
  - `origin_session:` — `$CLAUDE_CODE_SESSION_ID`, else explicit `null`. Scalar.
  - `origin_handoff:` — path of the active pickup baton, else explicit `null`. Scalar. Handoff
    paths only: a memo-origin session emits `null` (memo citation goes in `authoring_session:`). The
    path MUST resolve in `state/handoffs/`, `archive/handoffs/`, or git history; unsure → `null`. An
    unresolvable value is hard-denied at write time and locks the stub against all later Edits.
  - `origin_plan_id:` — `pln-…` id of the plan under execution, else `null`. Scalar.
  - `origin_goal_id:` — an **array** of `goal-…` ids even for one goal, else `null`.
  - Origin provenance is a distinct axis from `predecessor` — never encode it there. Do not build an
    auto-populator.

## Field rules

- **`wave:` is a concurrency-gate primitive, NOT a sprint synonym.** Wave = parallel fan-out within
  a sprint; `roadmap-number-stubs` does NOT verify same-wave stubs are file-disjoint (Step 2.4
  does). Sprint = a slice with its own JTBD and exit condition, not a time-box. Never use `wave:`
  for time-boxing; check `blocked_by` before judging single-stub waves.
- **Hard gates → `blocked_by:` (resolvable slugs); advisory prose → `gate_notes:`.** Soft seams
  never go in a machine-read gate field. `gate_dependency:` and `blocking_notes:` are deprecated:
  meet them in the corpus, never author new values.
- **`## Soft seams`** is required in every stub body (Step 2.2): one-line bullets naming the peer
  workstream/PR/stub and the overlap nature. `scope:` is the HARD declaration; Soft seams the SOFT.
- **Audit/spike sizing:** a single-consumer audit/spike folds as Phase 0 of that consumer's stub;
  standalone only when ≥2 downstream consumers read its output.
- **Stub-dedup canonical = first deliberate per-stub commit** (`git log -- <path>`), not the earlier
  filename timestamp. Dedup by `git mv` to `archive/` with a `.DUPLICATE-FROM-BULK-COMMIT.md`
  suffix, never `git rm`.

Rationale and mechanics: wiki `roadmap-planning-residue.md` § Stub frontmatter — field notes.
