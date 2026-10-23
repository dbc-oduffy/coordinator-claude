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

Ask the PM only about direction, priority, YAGNI, publishing; gates follow `interaction_mode`. `A-LOCAL-WRITE-IS-RECOVERABLE-ONLY-PUBLISHING-IS-IRREVERSIBLE`

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
