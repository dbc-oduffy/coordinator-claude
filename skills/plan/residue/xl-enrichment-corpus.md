---
segment_id: xl-enrichment-corpus
route: plan
class: protected
order: 910
---

- _XL-sized plan, named Opus reviewer and review-integrator both done?_
  → Dispatch `coordinator:enricher` directly over the plan body — the same carrier the L lane
  uses. Then run a SECOND named-reviewer pass over the enriched body: an ordinary `/review`
  dispatch plus `review-integrator`. Same sequencing XL already gets for its first
  named-reviewer pass — no new carrier mechanism.
  → Read the enricher's residuals block before the pre-execute gate, not at close.
  → Default pair the Director of Engineering then the Staff Engineer, in that order: the Director of Engineering carries cross-repo/DRY altitude, the Staff Engineer
  then takes correctness and architecture one layer down. The pair is the EM's choice; the
  default is a default, not a rule.
