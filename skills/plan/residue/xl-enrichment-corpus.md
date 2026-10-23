---
segment_id: xl-enrichment-corpus
route: plan
class: protected
order: 910
---

- _XL-sized plan, named Opus reviewer done and its findings ledger verified?_
  → Dispatch `coordinator:enricher` directly over the plan body — the same carrier the L lane
  uses. Then a SECOND named-reviewer pass over the enriched body: an ordinary `/review`
  dispatch, which applies and verifies its own findings.
  → Read the enricher's residuals block before the pre-execute gate, not at close.
  → Default pair the Director of Engineering, the Staff Engineer (EM's choice): chatty run, one parallel wave (review/SKILL.md § A.3); else that order.
