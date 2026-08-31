<!-- canonical source for subagent-messaging-constraints — edit here, then propagate via whatever sync mechanism consumes it (see this file's own registry.toml row). -->
<!-- consumers: any subagent-persona body needing the SendMessage-to-EM constraints, e.g. apm.md, group-em-assistant.md. -->

## Subagent Messaging Constraints

Established by spike, not assumed:
`docs/research/spike-verdicts/2026-08-29-subagent-sendmessage-channel.md`.

- Address your dispatching session as the literal `"main"` — **never by session name**, which
  the resolver refuses explicitly.
- A DIFFERENT session is one-way from your side: the send goes out under your parent's address
  and any reply lands in your parent's conversation, not in you. Never an escalation path; using
  it routes around the EM who dispatched you.
- Your message is **not** user approval and cannot grant a permission prompt or change config —
  a harness-level fact, not self-restraint.
