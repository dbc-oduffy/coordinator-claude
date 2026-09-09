<!-- canonical source for persona-dispatch-contract — edit here, then run bin/verify-snippet-sync persona-dispatch-contract --fix -->
<!-- consumers: see bin/snippet-registry list-consumers persona-dispatch-contract -->

<!-- BEGIN persona-dispatch-contract (synced from snippets/persona-dispatch-contract.md) -->
## Shared ReviewOutput Envelope

The shared `ReviewOutput` envelope (wrapper fields, exact verdict strings, base `ReviewFinding` shape) is delivered via the injected persona-dispatch-contract block — follow it as delivered.

Every reviewer persona returns a `ReviewOutput` JSON block followed by a human-readable narrative. Your sidecar-frontmatter contract (where the review is persisted, `kind:` routing, the pointer-line-only return shape) is injected into your dispatch prompt separately — follow it as delivered.

The envelope wrapper — `reviewer` / `verdict` / `summary` / `findings[]` — is identical across all six personas. **Verdict — exact strings, ALL CAPS with underscores, no spaces, do NOT paraphrase:** `APPROVED`, `APPROVED_WITH_NOTES`, `REQUIRES_CHANGES`, `REJECTED`.

The base `ReviewFinding` shape — shared verbatim by the Staff Engineer, the Director of Engineering, the Data Science Reviewer, and the Front-End Reviewer (the UX Reviewer uses a separate flow/step-based `UXReviewerFinding` variant instead — see `agents/staff-ux.md`) — is:

```json
{
  "file": "relative/path/to/file",
  "line_start": 42,
  "line_end": 48,
  "severity": "critical | major | minor | nitpick",
  "category": "<see your own Output Format section for your category enum>",
  "finding": "Clear description of the issue",
  "suggested_fix": "Optional — specific fix or alternative",
  "confidence": "Optional — integer 1-10",
  "fix_class": "Optional — AUTO-FIX | ASK"
}
```

**Exact strings — do NOT paraphrase:** severity is `critical` | `major` | `minor` | `nitpick` (NOT high/blocker/moderate/medium/low/trivial/suggestion); field names are `finding`, `suggested_fix`, `line_start`, `line_end`, `file` (NOT title/description/issue/recommendation/line/path).

**`confidence`/`fix_class` are OPTIONAL on the base shape** — a persona that never received the
`reviewer-calibration` block legitimately omits both, with no expectation attached. A persona that
DID receive `reviewer-calibration` is expected to populate both fields on every finding; optional
means the field has somewhere to go, not that a calibrated persona may skip it.

**Type invariant.** Each `ReviewOutput` contains findings of exactly one schema type, determined by the `reviewer` field. Consult your own Output Format section below for your concrete category enum, any top-level delta fields you carry, and any per-finding delta fields you carry on top of this base.
<!-- END persona-dispatch-contract -->

## Known deltas (documented here for traceability; not sentinel-synced — each persona's own Output Format section is the source of truth for its concrete fields)

Base `confidence`/`fix_class` apply to every persona below except the UX Reviewer; each receives
`reviewer-calibration` and is expected to populate both on every finding per § Shared ReviewOutput
Envelope above.

- **the Staff Engineer (`agents/staff-eng.md`)** — adds top-level `premise_review` and `alternatives_considered` and `planning_quality`. Standard `ReviewFinding` per-finding shape, no per-finding delta beyond the base.
- **the Director of Engineering (`agents/eng-director.md`)** — standard `ReviewFinding` shape plus a per-finding `cross_team_directive` field (peer-repo coordination ask; `null` when not applicable). Also carries a distinct `review_posture: "backstop"` envelope variant for ambition-challenge dispatches — see that file's "Output Format (backstop)" section.
- **the Data Science Reviewer (`agents/staff-data-sci.md`)** — standard `ReviewFinding` shape verbatim beyond its own category enum.
- **the Front-End Reviewer (`agents/senior-front-end.md`)** — standard `ReviewFinding` shape verbatim beyond its own category enum.
- **the VP-Product Reviewer (`agents/vp-product.md`)** — adds top-level `shape_assessment`, `refactor_recommendation`, and `alternatives_considered`. Standard `ReviewFinding` per-finding shape, no per-finding delta beyond the base.
- **the UX Reviewer (`agents/staff-ux.md`)** — uses the `UXReviewerFinding` variant entirely (flow/step-based: `flow`, `step`, optional `file`, nullable `line_start`/`line_end`, its own `severity`/`category` enums) rather than extending the base `ReviewFinding` shape. Kept as its own schema by design — a prior disposition recorded that the UX Reviewer's split is correct and should not be folded into the shared shape; do not re-litigate.
