# Review-Trail Minting Gap

<!-- Spec backlink: run 2026-08-06-14h38, derived from nugget c8-013
     (archive/completed/2026-07/2026-07-27-adhoc-2b4b88.md) -->

> How the coordinator system tracks *who reviewed what, when* — and the structural gap in
> that tracking discovered during the 2026-07-27 review-trail investigation.

---

## Overview

Provenance markers are the disk-truth records that let a downstream consumer — a future EM,
an audit, a review — answer "was this reviewed, by whom, and when?" without relying on
memory or chat history. `state/review-trail/*.json` is the canonical location for these
records in the coordinator system.

<!-- Spec backlink: run 2026-08-06-14h38, derived from nugget c8-013 -->
The review-trail directory is architecturally underspecified: nothing mints
`state/review-trail/*.json` at dispatch time. There is exactly one writer, and it lives
inside the `workstream-complete` ceremony, gated *behind* a judgment point (the ceremony's
review-and-integrate decision). This means a session that reviews work, integrates it, and
ends — without ever reaching the `workstream-complete` ceremony — leaves no review-trail
artifact behind. The review happened; the provenance of that review is invisible to any
downstream consumer reading disk state.

---

## Architecture

**Current writer:** `workstream-complete` ceremony, single write path, post-judgment.

**Gap:** any review-and-integrate flow that doesn't route through `workstream-complete`
(ad-hoc sessions, mid-workstream reviews, spinoff-triggered reviews) has no writer at all.
The review-trail directory's population is a side effect of one ceremony's completion, not a
first-class event emitted at the moment review actually happens.

**Consequence for downstream consumers:** a query like "what was reviewed in this session"
against `state/review-trail/` can silently under-report — absence of a record is not
evidence absence of review, but nothing on disk distinguishes "no review occurred" from
"review occurred, ceremony never ran."

---

## Key Patterns

- **Provenance should be minted at the review event itself**, not deferred to a downstream
  ceremony that may or may not run. The gap above is a structural argument for moving the
  write earlier in the flow, not for adding a second late writer.
- **Disk-truth over memory.** Per the discharge test (`coordinator/docs/wiki/invisible-doctrine.md`),
  a provenance fact that only "the operator remembers" is not discharged — it needs an
  artifact. The review-trail directory is the intended artifact; the minting hole means the
  intent is not yet fully discharged.

---

## Gotchas

- **Don't assume `state/review-trail/` is complete.** A session that reviews and integrates
  work but exits before `workstream-complete` runs leaves zero trace there. Treat an empty
  or sparse review-trail as inconclusive, not as proof no review happened.
- **This is a spinoff-shaped gap, not a patch-shaped one.** The nugget that identified this
  (`c8-013`) was explicitly framed as requiring a structural fix — a new writer at the
  review-event boundary — rather than a local tweak to the existing `workstream-complete`
  writer.

---

## Reference

- Source: `archive/completed/2026-07/2026-07-27-adhoc-2b4b88.md`
- Related: `coordinator/docs/wiki/invisible-doctrine.md` (discharge test)
- Existing writer: `workstream-complete` ceremony (see `coordinator/skills/` for the
  ceremony definition)

---

## `/spinoff` origin_* provenance — stamper, not author, writes it

<!-- Spec backlink: run 2026-08-06-14h38, derived from nugget c8-048
     (archive/completed/2026-07/2026-07-27-adhoc-6dad39.md) -->

A separate provenance gap, distinct from the review-trail hole above: an earlier `/spinoff`
run landed all 11 spinoffs with `origin_*` provenance frontmatter unset. Every spinoff file
wrote and linted clean, so nothing flagged the gap at authoring time.

**Root cause:** the responsibility split between the pipeline's two directives (d1, d3) was
wrong. Directive d3 authored a correctly-stamped file, but had nothing left to read by the
time it ran — d1's file (the one actually landing on disk) carried no `origin_*` fields at
all, and d3's correctly-stamped output never merged into it.

**PM-ruled fix:** d3 is rewired from *author* to *stamper* — it does not author a separate
file, it writes `origin_*` provenance directly onto d1's file after d1 produces it.

**Lesson:** when a provenance field's producer and its writer are split across two directives
in a pipeline, the directive that owns the on-disk artifact must be the one that stamps
provenance onto it. A downstream directive authoring a separately correct file that never
merges into the landing artifact is a silent no-op, not a fix.

All 11 pre-existing spinoffs needed `origin_*` hand-set as a one-time backfill; this was not a
recurring step — new spinoffs get the field via the rewired d3 stamper going forward.
