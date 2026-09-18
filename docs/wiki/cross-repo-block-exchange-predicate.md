# cross-repo-block-exchange-predicate — when a blocked leg may rest

A component blocked on a sibling repo may not be parked on the word "blocked". It may rest only
once it can show an **addressed, answered exchange**. This page is the single definition of that
predicate. Consumed by `coordinator/snippets/cross-repo-block-exchange.md` and, through it, by the
close and execute gates — do not define a second one; extend this page instead.

The predicate exists because "C7 is blocked on claude-klabauter" reads as a wall and is a comms problem. It
is written to be unsatisfiable by going through the motions: sending is not exchanging, and silence
is not an answer.

## The three conjuncts

A leg blocked on `owner_repo` may be parked only when all three hold.

1. **Declared.** The leg carries an `external_gate` entry naming `owner_repo`, with a
   `closure_key` of `kind: memo-thread` whose `id` is the basename of the memo this side sent.
   The thread is named on the gate, before any answer exists.
2. **Addressed.** That memo was actually delivered to a party that can act: a
   `state/memo-outbox/sent-ledger.jsonl` row for it whose `delivered_to` names a path under the
   receiver's `cross-repo/inbox/` and whose `delivery_commit_sha` is non-null, addressed to a
   receiver id from `--list-receivers`, and of `kind: ask` or `kind: consult`.
3. **Answered.** A memo exists in `cross-repo/inbox/` or `cross-repo/archive/` whose `from:` is
   `owner_repo` and whose `in_reply_to:` normalizes to that same basename, and whose body takes a
   position on the ask.

**Answered "no" satisfies conjunct 3 and is a legitimate terminal state for the exchange.** What is
never legitimate is silence read as an answer.

## What each conjunct refuses

Written as the adversarial case first — what a session trying to clear this cheaply would do, and
which conjunct stops it.

| The move | Refused by |
|---|---|
| Send the memo and wait | 3 — no reply exists |
| Send an `fyi` | 2 — an `fyi` invites no answer and cannot open an exchange |
| Address a repo, a publish mirror, or a central id rather than a receiver | 2 — not a `--list-receivers` id |
| Draft a memo and never deliver it | 2 — `delivery_commit_sha` is null |
| Write the reply into our own inbox by hand | 3 — `from:` must be `owner_repo`; delivery is the sender's commit |
| Point at an unrelated inbound memo from the same peer | 3 — `in_reply_to` must name *our* memo |
| Accept a bare receipt ack — "got it, queued" | 3 — an ack that names no disposition is receipt, not an answer |
| Cite prose: "we agreed in session", "this was discussed" | 1 — no `closure_key`, so there is no thread to check |

## The residue that is not mechanical

Conjuncts 1 and 2 are checkable off disk. Conjunct 3's *linkage* is checkable off disk; whether the
reply **takes a position on the ask** is not, and this page does not pretend otherwise. That
judgment is the EM's, and it is recorded — one sentence plus the reply's basename in the gate's
`closure_evidence`. An unrecorded judgment did not happen.

## Silence has a route, not a rest

An addressed memo with no answer is not a terminal state. It is an open escalation, and its
disposition comes from the existing shared threshold —
`coordinator/docs/wiki/group-em-escalation-threshold.md`. Do not define a second one here, and do
not let "we're waiting" become permanent by omission.

## `external_gate` is the carrier — no new field

Evaluated and decided: `plan-tasks.schema.json`'s `external_gate` already carries every part of
this. No field is added, and no schema bump is owed.

- `closure_key` with `kind: memo-thread` already names a memo thread by basename, in the form
  `in_reply_to` normalizes to, and is writable **before** the discharge by construction. That is
  exactly conjunct 1.
- The exchange state is **derived** from that key against the inbox, never stored. Storing
  "answered: true" beside a key that already resolves would give one fact two homes that desync.
- `closure_evidence` holds the recorded judgment; `cleared` remains the one clearing path, and
  nothing on this page clears a gate.
- `closure_key` stays **optional on the schema**. The obligation is doctrinal and applies at
  rest, not at authoring: a gate may be *written* without a key; a leg may not be *rested on*
  without one. Making it `required` would retroactively invalidate a corpus written correctly
  under the rules then in force — the same objection that settled DR-183 — and, under DR-097,
  would serialize this baton behind a sibling re-vendoring for no gain.

## Route to a named peer, not to a repo

"Blocked on claude-klabauter" names an organisation, not a party that can answer. Where the sibling repo has
a sitting Group EM, that is the address, resolved through the nomination record
(`coordinator/bin/group-em-nomination.py who --repo <repo-root> --json`) and turned into an
addressable peer by `coordinator/bin/resolve-peer-address.py`, per
`group-em-escalation-threshold.md` § Point.

Where there is no sitting Group EM, or the record does not resolve, the memo path is the address.
**That fallback is not a degraded mode** — it is what the fleet uses today, and the predicate is
fully satisfiable over it. Conjunct 2's requirement is a receiver that can act, not a session id.

The two-way leg is session↔session; assistant subagents are outbound-only into foreign sessions
(`docs/research/spike-verdicts/2026-08-29-subagent-sendmessage-channel.md`). Routing a blocked leg
is therefore an addressing act, not a delegation to an assistant.

## No new channel

`cross-repo/inbox/`, `state/memo-outbox/`, and `state/memo-outbox/sent-ledger.jsonl` already carry
the fleet's cross-repo traffic and already hold every field this predicate reads. A second surface
would fragment the record of who asked whom what, which is the one thing the predicate depends on.

## Composition with the close gate

`/execute-plan`'s wrap offer branches on whether the plan actually stamped `implemented`, never on
how shipped the session feels — tripwire `AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`. This
predicate does not add a second refusal. It makes the existing one **specific**: where the unstamped
reason is a cross-repo leg, the report names which conjunct failed — undeclared, unaddressed, or
unanswered — instead of "blocked on claude-klabauter".

The two meet at the boundary: a blocked leg with no exchange is not a legitimate reason to close,
and the refusal can now say which part is missing.

## The boundary this does not move

A memo is a gate, not a size. Nothing here grants, implies, or designs around a cross-repo commit
right: no standing grant survives in either direction, and on a durable host with a live fleet a
commit into a sibling repo needs per-session PM assent obtained at execution dispatch (`DR-127`; on
a managed-remote host the gate stands down to a warning and the assent moves to the PR terminal —
`DR-cross-repo-write-gating-stands-down-on-a-managed-remote-host`). An answered "no" ends the
exchange; it does not license fixing their tree.

## The falsifier

*Two sessions reading the same parked leg agree on whether it may rest, because each conjunct is a
yes/no fact about an artifact on disk rather than a judgment about how hard the EM tried.*

## See also

- `coordinator/snippets/cross-repo-block-exchange.md` — the operative rule, read from one place.
- `coordinator/docs/wiki/group-em-escalation-threshold.md` — where an unanswered exchange goes.
- `coordinator/docs/wiki/cross-repo-communication.md` § Cross-repo memo lifecycle, § `discharges`.
- `coordinator/docs/wiki/coordinator-tripwires/a-sent-memo-is-not-an-exchange.md`.
