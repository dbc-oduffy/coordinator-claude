<!-- canonical source for the plan-doc out-of-scope block emitted by fan-out-dispatch.py -->
<!--
Purpose: Names the plan document as out-of-scope for every coordinator:executor dispatch,
mirroring the existing Peer-Scope and Destructive-action prohibition blocks. The PreToolUse
guard block_subagent_plan_body_write (an engine-side write guard) enforces this at the
tool-call layer; this brief-side block names the constraint so the executor doesn't burn
context attempting the write before the hook denies it.
-->

## Out-of-scope — plan document, do NOT touch

Do NOT edit the plan markdown body — not the header `Status:`, not your assigned chunk-section, not the wave-map, not the acceptance-criteria checkboxes. The plan document is EM-owned and integrator-owned. Plan-status hygiene is owned by the EM via the wave-map; chunk-level execution state is owned by you via the per-chunk run-report sidecar (`state/subagent-share/<session-id>/<provision_key>.md`) named in your dispatch brief's `sidecar_path:` field.

The PreToolUse guard `block_subagent_plan_body_write` will DENY any Write/Edit/MultiEdit/NotebookEdit you attempt on `docs/plans/**/*.md`. Attempting the write wastes context; the hook is the gate, this block names the rule so you don't try.

Editing the plan document is never inside your remit, under any circumstance, in this dispatch. If your task appears to genuinely require a plan-body edit, that is itself a sign the dispatch scoped you incorrectly, not a problem for you to route around — return a BLOCKED report describing the requirement and stop. Do not retry the write, and do not look for another way to make the edit land.
