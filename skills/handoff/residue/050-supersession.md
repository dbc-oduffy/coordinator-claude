---
segment_id: supersession
case: predecessor
class: protected
order: 50
---

## Supersession — Genuine Dead-End (case ii)

**There is no working automated route today. `handoff.archive_transition` is suspended —
permanently, with no replacement planned** (p50 250.0ms / max 828.1ms against a 200ms bar, n=24;
`spinoff: null`). Both `baton-assemble apply`'s `d6` and the manual `supersede` verb dispatch to
it and fail `-32006`. That is correct behaviour, not a defect to file and not a transient to
retry.

**So supersede by hand, and record why in the same breath.** Stamp the predecessor
`deployment_state: continued` with `continued_into:` naming the successor, and put the reason in
a frontmatter comment so a later reader sees a deliberate act rather than a lapse. `closed_reason`
is not the place — the schema couples it to `deployment_state: closed` and admits only
`cancelled|displaced|stale`, none of which mean this. Leave the archival `git mv` for whoever
reconciles these once a route exists; a hand-stamped flip without the move is the honest
half-state, and inventing a private archival convention is worse than the gap.

**Do not reach for a route that drives the suspended op from a third door.** One exists —
`archive-stamp-cli`'s supersede path imports the op module's `_handler` directly, past both doors
the suspension guards — and the engine plane named it WITHOUT blessing it: it fails the
suspension bar's own middle clause (a caller must be able to drive the mechanism *without* the
op; this is the op, at the op's cost), its `fallback` slot is deliberately empty, and it may be
closed at any time. A bypass disclosed with a caveat attached is not a sanctioned fallback. If
you use it because you must move today, say so in the frontmatter comment rather than letting it
read as the supported path.

Full operator mechanics — the `d6` directive, the manual `supersede` verb, `chain` vs
`supersede`, `reconcile_close_terminal`, and the roadmap-baton refusal rationale — are the baton
lifecycle's, not this residue block's. They are documented against the op and are therefore
currently unreachable in their entirety; the paragraph below survives for when a route returns.
**`--exclude` is required on the manual `supersede` verb** — without it the live-children guard
sees the successor as a live child and the op silently retains rather than superseding.

**Hand-authoring an audit record is not the close** — a reconcile narrated into a
`*-baton-reconciled-closed.md` file without the frontmatter flip leaves the baton resurfacing as
pickup-ready; stamp the frontmatter in the same breath as the record. Supersession is a
PM-or-roadmap event, not an EM unilateral call on adjacent handoffs — do not park another
session's handoff without an explicit successor link or a named dead-end reason.

**Send the stand-down notice before you stamp `closed`.** If the handoff's deliverable was a
memo to a named receiver — today that means the doctrine-plane→engine-repo pair specifically,
not a fleet-wide broadcast — the named receiver is still waiting: draft and send that receiver a
stand-down notice via the settings-home forwarder (Shape W, per
`snippets/resolve-coordinator-bin.md`) — `& "$env:COORDINATOR_SETTINGS_HOME\bin\cross-repo-memo.exe"`
— before hand-authoring `closed_reason`, so they don't keep waiting on a workstream that already
ended.

**A roadmap-baton judgment point is a routing decision, not a defect.** When the engine declines
to arm `d6` on a roadmap-baton predecessor, route the supersession through the roadmap owner —
never file it as a defect, never reach for the manual `supersede` verb to route around it. No baton state admits an
automated supersede there: `--exclude` hides the successor from the live-children guard, and a
roadmap baton's dependents are not visible to the op making the call.
