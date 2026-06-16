<!-- canonical source for the plan-doc out-of-scope block emitted by fan-out-dispatch.sh -->
<!-- Spec backlink: docs/plans/2026-06-15-execute-plan-plan-doc-oos-injection.md -->
<!--
Purpose: Names the plan document as out-of-scope for every coordinator:executor dispatch,
mirroring the existing Peer-Scope and Destructive-action prohibition blocks. The PreToolUse
hook block-subagent-plan-body-write.sh enforces this at the tool-call layer; this brief-side
block names the constraint so the executor doesn't burn context attempting the write before
the hook denies it.
-->

## Out-of-scope — plan document, do NOT touch

Do NOT edit the plan markdown body — not the header `Status:`, not your assigned chunk-section, not the dispatch ledger, not the acceptance-criteria checkboxes. The plan document is EM-owned and integrator-owned. Plan-status hygiene is owned by the EM via the dispatch ledger; chunk-level execution state is owned by you via the per-chunk flight sidecar (`tasks/<plan-slug>/flight/<chunk-id>.md`) named in your dispatch brief's `sidecar_path:` field.

The PreToolUse hook `block-subagent-plan-body-write.sh` will DENY any Write/Edit/MultiEdit/NotebookEdit you attempt on `docs/plans/**/*.md`. Attempting the write wastes context; the hook is the gate, this block names the rule so you don't try.

There is no executor-side override. If a plan-body edit is genuinely required for your task, the EM will set COORDINATOR_OVERRIDE_SUBAGENT_PLAN_BODY=1 in your dispatch environment. If you encounter the hook DENY without that override set, the dispatch was misconfigured — return a BLOCKED report and stop.
