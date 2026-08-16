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

**Resolve `fleet_capability_index:` before dispatch (plan mode, non-blocking).** Same
op-invocation seam every `coordinator/hooks/scripts/*.py` dispatcher uses (resolve the sibling
control-plane engine root → `sys.path.insert` → in-process `coordinator_core.ipc.dispatch_message`
JSON-RPC, method `"fleet.aggregate_capability_index"`, `common_dir` scope via `_origin_worktree`
= this repo's cwd) — do not invent a second seam or author a DoE-side index builder; the fleet
index is produced entirely by the sibling aggregation op, this SKILL only resolves and reads it.
The op is read-only against every sibling and writes only `state/capabilities/fleet-index.json`
under THIS repo's worktree (`coordinator_core/ops/fleet/capability_index.py`).

1. Invoke the op. Any failure (engine unresolvable, import error, op exception) → resolve nothing,
   proceed without `fleet_capability_index:` — same posture as an absent `peer_repos`, never
   blocking.
2. Read the resulting `state/capabilities/fleet-index.json` against
   `coordinator/schemas/fleet-capability-index.schema.json` (AC8/F2) only far enough to confirm it
   parses. Unreadable/invalid JSON → treat as absent, same as step 1's failure. The `generated_at`/
   `ttl` staleness comparison (AC9) is NOT performed here — `prior-art-checker` performs it itself
   against the same file when it reads `fleet_capability_index:`, since this SKILL has no channel
   to hand a downgraded value to a consumer that independently re-reads the path.
3. Pass the index path as the `fleet_capability_index:` dispatch-brief field to
   `prior-art-checker`. Absent at any prior step → omit the field entirely; `prior-art-checker`
   already skips the Platform-capability bucket when it is absent.
