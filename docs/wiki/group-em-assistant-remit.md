# Group EM Assistant Remit

## Remit, widened to own the per-repo sensor half

A `coordinator:group-em-assistant` dispatch — unnamed, an `Agent`-tool background
subagent, never a separately spawned session
(`coordinator/agents/group-em-assistant.md`) — clears one `dispatches[]` bucket from
`workday-start-inbox-blitz-assemble`'s output on the inbox-blitz half: it reads the
named memos, runs the triage (and, on the paired `verify-*` entry, the verification)
exactly as the engine-emitted `brief` specifies, and writes its audit report to the
`report_path` the brief names. Outbound routing, per-memo triage, and claim
verification against the tree are genuinely delegable and this is what the assistant
absorbs on that half.

The remit DOES also include the per-repo sensor half used to hold: the watch
subprocess (arming `coordinator_core.group_em.watch`), the `Monitor` that wakes the
assistant off it, park-spool triage, and reading/holding the holder record in
`state/group-em-watch.json`. The assistant's existing per-repo binding already makes it
the right home — the sensor half is irreducibly per-repo, exactly like the inbox it
already reads. What it absorbs nothing of, on either half: no watch loop of its own
invention, no re-bucketing, no lifecycle-field edit, no outbound memo of its own, no
hand-edit of the watch holder record, no second `Monitor` over the park spool — the
negative spec in its own body (`coordinator/agents/group-em-assistant.md`) names all of
these. **Poke boundary:** the assistant triages and reports; it never nudges a peer.
Nudging is Navi's alone, or the repo's own Group EM's — the assistant gaining the
sensor half does not give it a second voice to nudge with.

## The asymmetric substrate

A subagent's send to its own spawning session is full two-way; its send to any
*different* session goes out under the parent's address and any reply lands in the
parent's conversation, not the subagent's — so an assistant can fire outbound at a
foreign EM but cannot hold a conversation with one. The full measurement, the harness
version it was taken at, and the three constraints that follow from it live in
`coordinator/snippets/subagent-messaging-constraints.md`, injected into the assistant's
body at dispatch time rather than restated here. That injected constraint set is also
where the subagent-only resolver alias `"main"` comes from — how the assistant
addresses its own Group EM.

Inbound reach — a Group EM's `SendMessage` reaching back INTO the assistant between
asks — is this shape's measured strength, not its open question:
`state/audits/2026-09-02-session-shaped-watcher-mechanics.md` leg (4) records this
repo's live Group EM messaging its watcher five times in one session with every
message arriving, plus a clean round trip whose reply echoed the exact sent text. That
is why this role stays a subagent rather than moving to a separately spawned session —
the session shape measured the opposite: listed by `ListAgents` but unreachable inbound
under two distinct address forms.

## What is actually shed — the dogfood measurement

Two real buckets, run 2026-08-30 against this repo's live inbox, both dispatched as real
`coordinator:group-em-assistant` subagents. The `fyi` run is the load-bearing one: it went
through `/group-em` § Inbox-blitz delegation with the nomination gate resolved first, so it
exercises the dispatch path the plan's exit criterion actually names, not just the agent.

Measured, in bytes:

| | `fyi` (17 memos) | `dominant` (6 memos) |
|---|---|---|
| Memo bodies read and triaged — stays in the assistant | **59,696 B** | **21,207 B** |
| Report written to `report_path` — stays out of the EM's context | **14,089 B** | **15,344 B** |
| Completion summary returned to the Group EM | **1,291 B** | **1,050 B** |

So for the `fyi` bucket, **1,291 B reached the Group EM's context against 73,785 B read and
produced by the assistant**; for `dominant`, 1,050 B against 36,551 B. The memo-by-memo reading,
the verification against disk, and the report authoring all stayed inside the assistant. These
are two buckets' measurements, not a general ratio, and they are not evidence for any percentage
beyond these runs.

The assistants' own token usage is the same fact from the other side: 76,179 and 98,747 tokens
respectively, none of it in the Group EM's window.

**What the return does carry is judgment, not volume.** Both summaries came back with confirmed
escalations — four in `fyi`, two dispatch-to-fix in `dominant` — and one route the verify pass
reversed against disk after triage had already classified it. The shed is the reading, never the
findings: an assistant that returned less than this would be cheaper and useless.

**Excluded by name: inbound replies.** Any reply a foreign EM sends back — to a memo the
assistant routed outbound, or to anything else — lands in the Group EM's own
conversation regardless of this dispatch, per the asymmetric substrate above. Nothing
measured here reduces that; the shed is triage-and-verification only, not
correspondence.
