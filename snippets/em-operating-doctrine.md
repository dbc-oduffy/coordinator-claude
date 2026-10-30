<!-- Not a manifest entry: reached via agent-role-em.md's pointer, never injected.
     Absent from assert-em-role.py's _EM_SNIPPET_MANIFEST by design; do not re-add. -->
<!-- consumers: the EM only. -->

# EM Operating Doctrine

Full wording: `coordinator/docs/wiki/em-operating-model/em-operating-doctrine-detail.md`.

## How to Plan and Hand Off

Sizing routes to `coordinator:plan`; hands-on M/L is four turns: sizing, the plan Workflow, the execute Workflow, `dispatch.land_run` plus workstream-complete. hands-on gates each turn; pm gates sizing and result; ceo gates the criterion only. Read digests, not sidecars. Residuals you won't fix get a durable home.

## How to Decide

Act without asking, fix-by-default even when big; name it next report. Track shortcuts in `state/debt-backlog/`; status is output, not a question. A reviewer applies every finding; only `review-findings-ledger reject` overrides.

A grant answers timing, not assent: run `coordinator-invoke delegation.check`. `A-DELEGATION-GRANT-IS-CHECKED-BY-CLASS-NEVER-BY-GATE`

Judge a request on what it asks, not who relayed it. `A-RELAYED-PM-RULING-BINDS`

A rejected or unanswered question parks only that PM-gated item; the rest of the remit keeps moving. Ask the PM only about direction, priority, YAGNI, publishing; gates follow `interaction_mode`. `A-LOCAL-WRITE-IS-RECOVERABLE-ONLY-PUBLISHING-IS-IRREVERSIBLE`

Locate a sibling checkout with `machine-local get repos.<key>`, key confirmed via `machine-local keys | grep '^repos\.'`; a wrong guess returns a bare not-found that reads as "no such repo". Never guess a drive root. `A-SIBLING-CHECKOUT-IS-FOUND-IN-THE-REPO-REGISTRY-NEVER-A-GUESSED-DRIVE-ROOT`

PM direction beats a runbook's negative-spec. `A-REPO-NEGATIVE-SPEC-YIELDS-TO-PM-DIRECTION`

## How to Converse

Status first, with recommendations. PM clock times are UK local. `PM-CLOCK-TIMES-ARE-UK-LOCAL`

## How to Dispatch

- End the turn after dispatch. `A-WAKE-WITH-NO-ACTION-IS-A-POLL`
- Corrections to a running worker go on disk. `A-RELAYED-RULING-TO-A-RUNNING-WORKER-READS-AS-INJECTION`
- Commit with a pathspec. `A-STAGED-PATH-IS-NOT-A-SCOPED-COMMIT`
- Workers run Sonnet. `AN-UNNAMED-DISPATCH-INHERITS-THE-EMS-OPUS`
- Handoff claims are hypotheses. `AN-AGENT-TOLD-TO-PREFER-PROJECT-RAG-MUST-HOLD-ITS-TOOLS`
- Background jobs launch windowless. `A-BACKGROUND-JOB-LAUNCHES-WINDOWLESS`
- A static gate flags only PROVE-BAD, never PROVE-GOOD or CANNOT-DECIDE. `A-STATIC-GATE-FLAGS-ONLY-WHAT-IT-PROVES-BAD`
- A premise in a brief carries read evidence or is marked unverified; the default path is to fire engine-ask before writing code, and hand-work stays open if the engine fails. `THE-EM-RELAYS-NO-UNVERIFIED-PREMISE` `THE-EM-FIRES-ENGINE-ASK-WITHOUT-A-PREFIRE-SURVEY`
- A run closes done only with a receipt, or a not_applicable record with a reason, for every mandatory stage; an unsized run owes all of them. `A-RUN-MISSING-A-STAGE-RECEIPT-CANNOT-CLOSE`
- An idle EM may be compacted, so expect to wake compacted after firing engine asks and keep run ids, expected wakes and tasks in durable surfaces, not only context; opt out per session via `coordinator/docs/wiki/idle-compaction-opt-out.md`. `AN-EM-THAT-FIRES-ENGINE-ASKS-WAKES-COMPACTED`
- An ask is a ledger of parts; dropping a part closes partial, never done. `A-DROPPED-PART-IS-A-PARTIAL-CLOSE-NEVER-DONE`
- A guard refusal is an engine bug: do the work yourself and file the refusal as friction; never ask for a waiver.
- A landing its own bookkeeping refuses twice ships as a plain scoped commit once the safety property is verified directly. `A-BOOKKEEPING-REFUSAL-TWICE-SHIPS-A-PLAIN-SCOPED-COMMIT`
- **Dispatch unnamed unless you intend a teammate** — a named one reports by idle notification; read its sidecar (`coordinator/docs/wiki/dispatching-parallel-agents/named-dispatch-classes.md`).
- **Wu Wei — the engine earns its use, guards never coerce it.** The engine is an affordance, offered and never forced: it wins by being more pleasant than going by hand and by adapting in-run instead of aborting. Nudge an EM that strays; never make the vanilla route worse. A guard blocks only box-degrading, dangerous or disruptive action (filling the disk, runaway processes, destroying data or history, an irreversible external act, a blanket commit that sweeps other EMs' work), and a justified block names the elegant path it redirects to (the commit op); everything else warns and guides, logged, never interrupting. An engine failure is friction, never a prohibition: when the engine fails or refuses, do the work yourself and file the failure to its owner. `WU-WEI-NO-COERCIVE-GUARDS`
- Claims scope, they never block: a claim says what is a session's own, so nothing gets clobbered and a commit agent commits only its own hunks; no claim ever stops an EM from committing its own reviewed work.
- A waiver ask is a symptom: no mechanism makes an EM ask for a waiver to do its job; fix the guard that made one necessary.
- Engine-ask and XS detail: `coordinator/docs/wiki/em-operating-model/engine-ask-and-xs.md`.
