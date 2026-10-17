---
segment_id: xl-enrichment-corpus
route: plan
class: protected
order: 910
---

- _XL-sized plan, named Opus reviewer done and its findings ledger verified?_
  → Dispatch `coordinator:enricher` directly over the plan body — the same carrier the L lane
  uses. Then run a SECOND named-reviewer pass over the enriched body: an ordinary `/review`
  dispatch, which applies and verifies its own findings the same way.
  → Read the enricher's residuals block before the pre-execute gate, not at close.
  → Default pair the Director of Engineering then the Staff Engineer (cross-repo/DRY altitude, then correctness and architecture); the pair is the EM's choice.
