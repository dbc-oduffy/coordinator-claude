---
segment_id: carried-items
case: carried-items
class: protected
order: 30
---

**Cascading unresolved items (only when there IS a predecessor).** Any item in the predecessor's `## Recommended Next Steps` / `## Carried Forward` that this session did not complete carries forward into the new handoff's `## Carried Forward`, with its origin annotation preserved. Items leave the cascade only by completion or explicit PM dismissal — never silent drop.

**The prose `_(carried via N handoffs)_` annotation is not the count of record — `carried_items:` frontmatter is.** Every `## Carried Forward` entry that is not brand-new to this handoff MUST have a matching `carried_items:` frontmatter entry (schema: `coordinator/schemas/handoff.schema.json` `carried_items`), keyed on a stable `carry_id` that survives re-wording — never re-derive the count from prose, never key identity on the description text.

- **Minting `carried_items`.** A brand-new item mints a fresh `carry_id` (`cf-<slug>-<6hex>`). An item continuing from the predecessor keeps that `carry_id` byte-identical. That is the whole rule — identity threads through re-wording, and nothing counts the hops.
- **The disposition gate is not enforced at the commit seam — unwired, not removed.** No commit route runs it, so a handoff whose `carried_items` declare undeclared state will commit. It is reachable in two places you must invoke deliberately: `baton_assemble/apply.py`'s `_dispatch_handoff_carry_gate` (over the PREDECESSOR's array, at apply time) and the standalone `handoff-carry-gate` CLI (resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`: Shape A/B on POSIX hosts, Shape W on PowerShell). Both delegate to `coordinator_core/ops/handoff_carry_gate.py`'s `evaluate_gate`. It REFUSES exactly three things: a missing or non-string `carry_id`, an unrecognized `disposition`, and a terminal disposition (`closed`/`spun_off`/`blocked`) with an empty `disposition_detail`. **Carry depth is not among them.** Author to those three rules; neither of `/handoff`'s two commits (apply's successor mint, then your authoring commit carrying the items) is gated, so run `handoff-carry-gate` yourself before committing.
- **Sanctioned exits.** Set `disposition` to `closed` (with `disposition_detail` naming why), `spun_off` (with `disposition_detail` naming the spinoff handoff), or `blocked` (a genuine external/hardware dependency, with `disposition_detail` naming the concrete blocking condition).
