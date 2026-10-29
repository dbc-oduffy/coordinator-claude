export const meta = {
  name: "engine-ask",
  description: "Submit an engineering ask to the engine: args {ask: \"<the PM's words, verbatim>\"} (one recorded PM turn, exact; further PM turns go in context: [\"<turn>\", ...], never joined into ask) or {sizing: \"<state/sizings/x.yaml>\"}, optional repo, source: \"pm\" for the PM's own words or \"relayed\" for anything else (a relay, a peer's request, a memo); always pass it with {ask}, never with {sizing}: an unmarked ask defaults to pm only on the session's first turn, relayed after. The engine fires the run; a {sizing} carrying a research block emits the research run instead of the plan chain. Multi-ask form: args {asks: [{ask: \"<slice, carrying the full PM verbatim>\", label?: \"<short name>\", writes?: [\"<path>\", ...]}], confirm_split?: bool} beside the single {ask}; submit distinct initiatives as separate asks in one submission, never bundled. Returns {parent_id, runs: [{run_id, label, after?}]}, and each run sends its own completion notification. after is engine output, never a submission key: the engine derives it from siblings whose declared writes overlap, and holds a sibling run only for those predecessors. Every asks entry may also carry context (string or list) and em_context (what the EM already knows; never a pre-fire read); each lands on that entry's own sizing and run, and a top-level context beside a multi-element asks is refused. An unknown top-level args key or asks-entry key is refused before any write, naming the key and the accepted keys. An engine-ask always runs through to commit and takes no stop or park switch; a plan wanted without execution is /plan-blitz, never an engine-ask. Any ask entry may add route_preference (\"goal\"|\"roadmap\"|\"plan\") and em_rationale (a non-empty string of at most 2000 characters; longer is refused before any write, so trim it to the two or three facts that change routing and put the rest in context): advisory only: sizing routes from what it finds and, where its route differs, tells the EM why. Put only the PM verbatim in ask; EM framing goes in em_rationale, never appended to ask, which demotes the whole ask to relayed. A single {ask} that sizing finds separable comes back split and auto-fires unless confirm_split is set.",
  phases: ["submit"],
}

// The submit target, never the run. The PreToolUse(Workflow) hook (claude-klabauter
// `coordinator_core.hooks.submit_engine_ask`, reached through
// `hooks/scripts/preuse-workflow-dispatch.py`) emits the warp run from `args` and rewrites this
// call to fire it, so a submission never executes this body. The harness resolves `name` before
// any hook runs, which is why this file must exist, and only `.js` files load as named workflows.
// Reaching this body means the hook did not rewrite the call: nothing was emitted. That is not
// proof the hook is down — a refusal arrives as the hook's named deny reason, so read that first.
phase("submit")
return {
  halted: true,
  reason:
    "The engine did not take this submission: the coordinator PreToolUse(Workflow) hook did not " +
    "rewrite it, so nothing was emitted or run. Read the hook's reason in this call's hook output: a named " +
    "refusal is the engine declining these args, so fix the args and resubmit. With no hook output at all " +
    "the hook is not running: retry once, then do the work by hand (dispatch the agents yourself, scoped " +
    "commits) and file this failure to claude-klabauter-em.",
  args,
}
