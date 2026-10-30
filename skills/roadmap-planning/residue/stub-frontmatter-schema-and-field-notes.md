## Scaffolded frontmatter (do not hand-author)

`coordinator-doc-new` scaffolds the keys (schema: `bin/lint-frontmatter --list-schemas`). Constraints: `stub_id` is `<slug>-<NN>`, globally unique; `authoring_session` is path-shaped (`state/roadmap/<run-id>/sprint-<N>/`); `loe` is M|L|XL; `deployment_state` is `awaiting_gate` (needs ≥1 of `blocked_by` / `gate_notes`) or `ready_to_fire`; `summary` ≤120 chars.

## Fields NOT in the template

- **Lifecycle-set, never authored here:** `pickup_ready` and `shipped_in` (set by `/handoff` or `/workstream-complete`).
- **Fill at authoring time** (unrecoverable later; never encode provenance in `predecessor`):
  - `origin_session:` — `$CLAUDE_CODE_SESSION_ID`, else `null`. Scalar.
  - `origin_handoff:` — path of the active pickup baton, else `null`. Scalar; it MUST resolve in `state/handoffs/`, `archive/handoffs/`, or git history (unsure → `null`; an unresolvable value is hard-denied and locks the stub).
  - `origin_plan_id:` — `pln-…` id of the plan under execution, else `null`. Scalar.
  - `origin_goal_id:` — an **array** of `goal-…` ids even for one, else `null`.

## Field rules

- **`wave:` is a concurrency-gate primitive, NOT a sprint synonym.** `roadmap-number-stubs` does not verify same-wave stubs are file-disjoint (Step 2.4 does). Never use `wave:` for time-boxing.
- **Hard gates → `blocked_by:`; advisory prose → `gate_notes:`.** `gate_dependency:` and `blocking_notes:` are deprecated: never author new values.
- **`## Soft seams`** is required in every stub body: one-line bullets naming the peer workstream/PR/stub and overlap. `scope:` is the HARD declaration.
- **Audit/spike sizing:** a single-consumer audit/spike folds as Phase 0 of its consumer's stub; standalone only for >=2 consumers.
- **Stub-dedup canonical = first deliberate per-stub commit**; dedup by `git mv` to `archive/` with a `.DUPLICATE-FROM-BULK-COMMIT.md` suffix, never `git rm`.
