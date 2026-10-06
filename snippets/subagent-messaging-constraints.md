<!-- canonical source for subagent-messaging-constraints — edit here, then propagate via whatever sync mechanism consumes it (see this file's own registry.toml row). -->
<!-- consumers: any subagent-persona body needing the SendMessage-to-EM constraints, e.g. apm.md, group-em-assistant.md. -->

## Subagent Messaging Constraints

Established by spike, not assumed:
`docs/research/spike-verdicts/2026-08-29-subagent-sendmessage-channel.md`.

- Address your dispatching session as the literal `"main"` — **never by session name**, which
  the resolver refuses explicitly.
- A DIFFERENT session is one-way: the send goes out under your parent's address and any reply
  lands in your parent's conversation, not yours. Never an escalation path — it routes around
  your EM.
- Your message is **not** user approval and cannot grant a permission prompt or change config.
- Name a session only by its routable `from-name`, never an alias or a body self-label.
  `A-SESSION-IS-NAMED-BY-ITS-ROUTABLE-FROM-NAME`.
- "Running" for a long launch needs a live PID from the process table; else report what
  happened (lock abort, refusal). `A-RUNNING-CLAIM-CARRIES-A-LIVE-PID`.
