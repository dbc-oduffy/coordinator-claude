---
segment_id: carried-items
case: carried-items
class: protected
order: 30
---

**Cascading unresolved items (only when there IS a predecessor).** Any item in the predecessor's `## Recommended Next Steps` / `## Carried Forward` that this session did not complete carries forward into the new handoff's `## Carried Forward`, origin annotation preserved. Items leave the cascade only by completion or explicit PM dismissal — never silent drop.

**`carried_items:` frontmatter is the count of record, not the prose `_(carried via N handoffs)_` annotation.** Every `## Carried Forward` entry not brand-new to this handoff MUST have a matching `carried_items:` entry (schema: `coordinator/schemas/handoff.schema.json` `carried_items`), keyed on a stable `carry_id` that survives re-wording — never re-derive the count from prose or key identity on description text.

- **Minting.** A brand-new item mints a fresh `carry_id` (`cf-<slug>-<6hex>`); a continuing item keeps its `carry_id` byte-identical.
- **The disposition gate is not enforced at either of `/handoff`'s commits — run `handoff-carry-gate` yourself before committing** (resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; engine: `coordinator_core/ops/handoff_carry_gate.py` `evaluate_gate`). It REFUSES exactly three things: a missing or non-string `carry_id`, an unrecognized `disposition`, and a terminal disposition (`closed`/`spun_off`/`blocked`) with an empty `disposition_detail`. Carry depth is not among them.
- **Sanctioned exits.** `disposition` is `closed` (`disposition_detail` names why), `spun_off` (names the spinoff handoff), or `blocked` (a genuine external/hardware dependency; names the blocking condition).
