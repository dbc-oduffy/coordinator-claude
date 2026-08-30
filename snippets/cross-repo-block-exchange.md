<!-- canonical source for cross-repo-block-exchange — edit here. Read from one place only
     (coordinator/skills/execute-plan/SKILL.md and coordinator/skills/workstream-complete/SKILL.md,
     both pointers, not pastes); not registered in registry.toml, per that file's own header
     comment on paste-governed vs read-from-one-place snippets — this one is the latter. -->
<!-- consumers: coordinator/skills/execute-plan/SKILL.md, coordinator/skills/workstream-complete/SKILL.md (pointers, not pastes) -->

# A cross-repo block opens a conversation

A leg blocked on a sibling repo may not be parked on the word "blocked". It rests only on an
**addressed, answered exchange**. Full definition, adversarial cases, and the carrier decision:
`coordinator/docs/wiki/cross-repo-block-exchange-predicate.md`.

## The three conjuncts

1. **Declared** — the leg's `external_gate` entry names `owner_repo` and carries
   `closure_key: {kind: memo-thread, id: <basename of the memo we sent>}`.
2. **Addressed** — that memo has a `state/memo-outbox/sent-ledger.jsonl` row with a non-null
   `delivery_commit_sha`, a `delivered_to` under the receiver's `cross-repo/inbox/`, a `--list-receivers`
   receiver id, and `kind: ask` or `consult`.
3. **Answered** — an inbox or archive memo `from: <owner_repo>` whose `in_reply_to` names that
   basename, whose body takes a position on the ask.

**Answered "no" satisfies conjunct 3.** Silence never does, and is never an answer.

## What this does not do

- **Sending is not exchanging.** Conjunct 3 exists to refuse exactly that.
- **It clears nothing.** `cleared: true` remains the only clearing path; this predicate governs
  whether a leg may *rest while still blocked*.
- **It grants no commit right.** `DR-127` stands: no standing cross-repo grant, in either
  direction. An answered "no" ends the exchange, not the boundary.
- **It builds no channel.** The inbox, the outbox, and the sent-ledger carry it.

## Where it goes when unanswered

An addressed memo with no answer is an open escalation, not a rest. Its disposition comes from
`coordinator/docs/wiki/group-em-escalation-threshold.md` — do not invent a second threshold.

## What the report must say

Where a plan is unstamped because of a cross-repo leg, name **which conjunct failed** —
undeclared, unaddressed, or unanswered — never "blocked on `<repo>`". Tripwire:
`A-SENT-MEMO-IS-NOT-AN-EXCHANGE`.
