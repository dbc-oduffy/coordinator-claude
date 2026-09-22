---
segment_id: l-enrichment-corpus
route: plan
class: protected
order: 900
---

- _L-sized plan, named Opus reviewer and review-integrator both done?_
  → Dispatch `coordinator:enricher` over the plan body. No second named-review cycle — the EM
  absorbs that pass; they have watched the plan evolve and the enricher's in-body marks carry
  what needs an eye.
  → Read the enricher's residuals block before the pre-execute gate, not at close.
