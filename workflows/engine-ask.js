export const meta = {
  name: "engine-ask",
  description: "Submit an engineering ask to the engine: args {ask: \"<the PM's words, verbatim>\"} (one recorded PM turn, exact; further PM turns go in context: [\"<turn>\", ...], never joined into ask) or {sizing: \"<state/sizings/x.yaml>\"}, optional repo, source: \"pm\" for the PM's own words or \"relayed\" for anything else (a Group EM relay, a peer's request, a memo); always pass it, since an unmarked ask defaults to pm only on the session's first turn and to relayed after. The engine fires the run; a {sizing} carrying a research block emits the research run instead of the plan chain. Multi-ask form: args {asks: [{ask: \"<slice, carrying the full PM verbatim>\", label?: \"<short name>\", writes?: [\"<path>\", ...]}], confirm_split?: bool} beside the single {ask}; submit distinct initiatives as separate asks in one submission, never bundled. Returns {parent_id, runs: [{run_id, label, after?}]}, and each run sends its own completion notification. One parent runs at most max(1, physical cores / 4) runs at once; a ready run past that budget comes back queued, naming the runs holding the slots, and fires when one closes. That budget is the only reason an independent run is held. Any ask entry may add route_preference (\"goal\"|\"roadmap\"|\"plan\") and em_rationale (<=2000 chars): advisory only: sizing routes from what it finds and, where its route differs, tells the EM why. Put only the PM verbatim in ask; EM framing goes in em_rationale, never appended to ask, which demotes the whole ask to relayed. A single {ask} that sizing finds separable comes back split and auto-fires unless confirm_split is set.",
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
