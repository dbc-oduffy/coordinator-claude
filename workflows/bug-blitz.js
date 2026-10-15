export const meta = {
  name: "bug-blitz",
  description: "Submit a bug-blitz to the engine: args {targets: \"<red-set dir | failing-tests file | backlog>\", appetite?, limit?, budget_tokens?}. The engine parses the targets, mints the bug rows, and fires the grind. The confirm-green decision is the EM's, never an arg.",
  phases: ["submit"],
}

// The submit target, never the run. The PreToolUse(Workflow) hook (claude-klabauter
// `coordinator_core.hooks.submit_bug_blitz`, reached through
// `hooks/scripts/preuse-workflow-dispatch.py`) emits the bug grind from `args` and rewrites this
// call to fire it, so a submission never executes this body. The harness resolves `name` before
// any hook runs, which is why this file must exist, and only `.js` files load as named workflows.
// Reaching this body means the hook did not run: nothing was emitted, and it says so.
phase("submit")
return {
  halted: true,
  reason:
    "The engine did not take this bug-blitz submission: the PreToolUse(Workflow) hook did not " +
    "rewrite it. Report it; do not emit the grind by hand.",
  args,
}
