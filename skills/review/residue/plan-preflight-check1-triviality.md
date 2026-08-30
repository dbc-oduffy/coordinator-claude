---
segment_id: plan-preflight-check1-triviality
surface: plan
class: protected
order: 2
---

**Check 1 — Triviality and pre-dispatch field resolution (prior-art-checker)**

- _Plan covers non-trivial work?_ (design docs, RFCs, architectural plans; anything beyond a single-file fix)
  → `prior-art-checker` is auto-provisioned its sidecar at spawn (`state/plan-sidecars/<plan-stem>.<lens>.md`, computed by claude-klabauter's `provision_report` — no manual pre-scaffold). Dispatch it with the plan path; pass the provisioned sidecar path from the dispatch brief through unchanged, and read the agent's returned pointer for the sidecar it wrote. Act on buckets: **Conflicts** → surface to PM with wiki quote before continuing; **Compatible-but-relevant** → fold reference into plan's "Considered alternatives"; **Silent** → no action.
- _Plan is genuinely trivial?_ (one-line doc fix, typo, link repoint, no design content)
  → Skip `prior-art-checker`.

**Resolve `fleet_capability_index:` before dispatch (plan mode, non-blocking).** Use the same
op-invocation seam every `coordinator/hooks/scripts/*.py` dispatcher uses (sibling engine root →
`sys.path.insert` → in-process `coordinator_core.ipc.dispatch_message`, method
`"fleet.aggregate_capability_index"`, `common_dir` scope via `_origin_worktree`). **Never invent a
second seam or author a DoE-side index builder** — the sibling op produces the index
(`coordinator_core/ops/fleet/capability_index.py`); this skill only resolves and reads it. The op
is read-only against every sibling and writes only under THIS repo's worktree.

1. Invoke the op. Any failure (engine unresolvable, import error, op exception) → proceed without
   the field, never blocking.
2. Read `state/capabilities/fleet-index.json` only far enough to confirm it parses against
   `coordinator/schemas/fleet-capability-index.schema.json` (AC8/F2); invalid JSON → treat as
   absent. Do NOT perform the `generated_at`/`ttl` staleness check (AC9) — `prior-art-checker`
   re-reads the path and does it itself.
3. Pass the path as the `fleet_capability_index:` dispatch-brief field. Absent at any prior step →
   omit the field entirely; `prior-art-checker` already skips its Platform-capability bucket.
