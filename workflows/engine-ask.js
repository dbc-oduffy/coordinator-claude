export const meta = {
  name: "engine-ask",
  description: "Submit an engineering ask to the engine: args {ask: \"<the PM's words, verbatim>\"} or {sizing: \"<state/sizings/x.yaml>\"}, optional repo, optional source: \"relayed\" for words that are not the PM's own (a Group EM relay, a peer's request, a memo). The engine fires the run. Multi-ask form: args {asks: [{ask: \"<slice, carrying the full PM verbatim>\", label?: \"<short name>\", writes?: [\"<path>\", ...]}], confirm_split?: bool} beside the single {ask}; submit distinct initiatives as separate asks in one submission, never bundled. Returns {parent_id, runs: [{run_id, label, after?}]}, and each run sends its own completion notification. A single {ask} that sizing finds separable comes back split and auto-fires unless confirm_split is set.",
  phases: ["submit"],
}

// The submit target, never the run. The PreToolUse(Workflow) hook (claude-klabauter
// `coordinator_core.hooks.submit_engine_ask`, reached through
// `hooks/scripts/preuse-workflow-dispatch.py`) emits the warp run from `args` and rewrites this
// call to fire it, so a submission never executes this body. The harness resolves `name` before
// any hook runs, which is why this file must exist, and only `.js` files load as named workflows.
// Reaching this body means the hook did not run: nothing was emitted, and it says so.
phase("submit")
return {
  halted: true,
  reason:
    "The engine did not take this submission: the coordinator PreToolUse(Workflow) hook did not " +
    "rewrite it, so nothing was emitted or run. Tell the PM the engine submit hook is down; do not size or dispatch by hand.",
  args,
}
