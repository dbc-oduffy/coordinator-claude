---
segment_id: supersession
case: predecessor
class: protected
order: 50
---

## Supersession (case ii)

**`d6`'s supersession route is the supported path.** Both `baton-assemble apply`'s `d6` and the
manual `supersede` verb dispatch through `housekeeping.cycle` and land the archival half. The op
key `handoff.archive_transition` is permanently dead — a route still naming it fails `-32006`; do
not restore it.
Run `d6` with `mode='supersede'` and `--continued-into` naming the successor; do not hand-stamp
`deployment_state: continued` as a substitute for running it, and do not restore
`handoff.reconcile_open` (dead, superseded by K-057).

**`--exclude` is required on the manual `supersede` verb** — without it the live-children guard
sees the successor as a live child and the op silently retains rather than superseding.

**Hand-authoring an audit record is not the close** — stamp the frontmatter in the same breath
as the record, or the baton resurfaces as pickup-ready. Supersession is a PM-or-roadmap event,
not an EM unilateral call — do not park another session's handoff without an explicit successor
link or a named dead-end reason.

**Send the stand-down notice before you stamp `closed`.** If the handoff's deliverable was a
memo to a named receiver (the doctrine-plane→engine-repo pair, not a broadcast), send that
receiver a stand-down notice via the settings-home forwarder (Shape W, per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`) — `& "$env:COORDINATOR_SETTINGS_HOME\bin\cross-repo-memo.exe"`
— before hand-authoring `closed_reason`, so they don't keep waiting on a workstream that already
ended.

**A roadmap-baton judgment point is a routing decision, not a defect.** When the engine declines
to arm `d6` on a roadmap-baton predecessor, route the supersession through the roadmap owner —
never file it as a defect, never reach for the manual `supersede` verb to route around it.