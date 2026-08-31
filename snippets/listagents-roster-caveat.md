<!-- canonical source for listagents-roster-caveat — edit here, then run bin/verify-snippet-sync listagents-roster-caveat --fix -->
<!-- consumers: fixed list in snippets/registry.toml [snippet.listagents-roster-caveat] -->

## ListAgents Roster Is A View, Not The Registry

Discover a peer's address by calling `ListAgents` and copying the name a row prints verbatim, then
`SendMessage` to that name. But the roster it renders can UNDER-REPORT — a thin or empty roster is
never proof a peer is gone. The durable source is the session registry
(`~/.claude/sessions/<pid>.json`), not this view; a peer missing from `ListAgents` is evidence about
that view, not about the peer. See
`coordinator/docs/wiki/coordinator-tripwires/a-thin-listagents-roster-is-not-proof-a-peer-is-gone.md`.
