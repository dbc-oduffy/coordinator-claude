---
segment_id: supersession
case: predecessor
class: protected
order: 50
---

## Supersession — Genuine Dead-End (case ii)

Full operator mechanics — the `d6` directive, the manual `supersede` verb, `chain` vs
`supersede`, `reconcile_close_terminal`, and the roadmap-baton refusal rationale — are the baton
lifecycle's, not this residue block's. **`--exclude` is required on the manual
`supersede` verb** — without it the live-children guard sees the successor as a live child and
the op silently retains rather than superseding.

**Hand-authoring an audit record is not the close** — a reconcile narrated into a
`*-baton-reconciled-closed.md` file without the frontmatter flip leaves the baton resurfacing as
pickup-ready; stamp the frontmatter in the same breath as the record. Supersession is a
PM-or-roadmap event, not an EM unilateral call on adjacent handoffs — do not park another
session's handoff without an explicit successor link or a named dead-end reason.

**Send the stand-down notice before you stamp `closed`.** If the handoff's deliverable was a
memo to a named receiver — today that means the doctrine-plane→engine-repo pair specifically,
not a fleet-wide broadcast — the named receiver is still waiting: draft and send that receiver a
stand-down notice via the settings-home forwarder (Shape W, per
`snippets/resolve-coordinator-bin.md`) — `& "$env:COORDINATOR_SETTINGS_HOME\bin\cross-repo-memo.cmd"`
— before hand-authoring `closed_reason`, so they don't keep waiting on a workstream that already
ended.

**A roadmap-baton judgment point is a routing decision, not a defect.** When the engine declines
to arm `d6` on a roadmap-baton predecessor, route the supersession through the roadmap owner —
never file it as a defect, never reach for the manual `supersede` verb to route around it. No baton state admits an
automated supersede there: `--exclude` hides the successor from the live-children guard, and a
roadmap baton's dependents are not visible to the op making the call.
