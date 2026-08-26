---
segment_id: roadmap-triage-and-exit
surface: roadmap
class: protected
order: 7
---

**Triage lens — decomposition tradeoff.**

- _Finding argues the cluster-to-stub cut is wrong?_ (a stub that should be two, two that
  should be one, a seam drawn at the wrong boundary)
  → Surface to PM with the finding and the reasoning. Wait for direction. Roadmap reviews
  skew heavily toward this row, the way plan reviews skew toward artifact shape — most
  roadmap findings are about *where the lines fall*, not about what any one stub says.
- _(i) Scope-trim / drop-a-stub argument?_ → **Always escalation, never auto-trim.** Which
  stubs exist is the roadmap's product content; an EM trimming one has edited the PM's
  decision, not the reviewer's finding.
- _(ii) Re-sequencing argument?_ → PM. Ordering encodes delivery commitments the reviewer
  cannot see from the artifact.
- _(iii) A stub's internal design?_ → Not this altitude. Route it to that stub's downstream
  plan review rather than integrating it here.

**Triage lens — coverage claim.**

- _Reviewer claims a KEEP cluster is uncovered, or covered twice?_
  → Mechanically checkable, so check it rather than arguing it: every KEEP cluster must be
  named in exactly one stub's `covers:`. Confirm against the artifact before accepting or
  refusing the finding. A coverage claim is the one roadmap finding class that never
  needs a judgment call.

**Triage lens — worker dispatch recommendations.**

- _Worker Dispatch Recommendations block present?_
  → On roadmap reviews: `doc-link-checker` and `plan-coverage-checker` are the relevant
  pair. `test-evidence-parser`, `security-audit-worker`, and `dep-cve-auditor` do NOT fire
  — a roadmap has no runtime artifacts and no dependency manifest. A reviewer naming them
  has miscalibrated to the wrong altitude; surface it rather than dispatching.

**Exit gates.**

Both reviews integrated, both PM rounds passed, `status: final-approved`. Beyond that the
artifact carries its own mechanical gates — every KEEP cluster in exactly one `covers:`,
every stub `loe:` M–XL, `## Soft seams` present, the frontmatter validator and
`bin/lint-frontmatter` clean on `kind: roadmap-baton`, STUB-INDEX regenerating. **These are
the artifact's gates, not the reviewer's**, and a green reviewer verdict discharges none of
them. Run them; do not read them off a verdict that never checked them.

**A roadmap review does not authorize execution of anything.** Approval here approves the
DECOMPOSITION. Each stub still enters its own `coordinator:plan` and earns its own
execution authorization there — a PM's approval of the spine is not a standing grant to
start building its stubs, and treating it as one skips every gate the stub-level plan
exists to impose.
