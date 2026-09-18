<!-- canonical source for premise-check-class-5-semantics — edit here, then run bin/verify-snippet-sync premise-check-class-5-semantics --fix -->
<!-- consumers: no sync-tool-governed consumer. The one live consumer is `coordinator/workflows/plan-blitz.mjs`, which carries this text inside its hand-synced `PREMISE_CHECK_CONTRACT` constant — a `.mjs` target cannot take the sentinel paste a registry row governs (tripwire `verify-snippet-sync-has-no-language-awareness.md`). Edit here, then hand-carry into that constant. Do NOT enrol `agents/plan-coverage-checker.md`: its Lens 3 declares the semantic check out of scope, which is why this half was split out of premise-check-contract.md in the first place. -->

<!-- BEGIN premise-check-class-5-semantics (synced from snippets/premise-check-class-5-semantics.md) -->
## Premise Check Contract — Class 5 (Semantics)

The judgment half of the premise check, delivered only to consumers that enact it. It extends
`premise-check-contract.md`'s mechanical classes 1-3 and is meaningless without them: a consumer
that receives this block receives that one too.

**Class 5 — semantics (judgment, new).** A claim that code EXISTS is not a claim it BEHAVES as
described. This class fires on either of two conditions:

1. The repo carries a surface that FORBIDS the plan's assumption — a wiki page that says so, or a
   sanctioned resolver that raises instead of defaulting.
2. Defect vocabulary (wrong, broken, fails, silently, unsafely) appears in the plan's description
   of in-repo behaviour — the cheaper, second firing condition.

On either trigger, open the cited symbol and compare its actual behaviour against the plan's claim
before trusting it — a substrate pre-flight verifies existence, not described behaviour, so a
claim that code EXISTS is never treated as a claim it BEHAVES as described. Where NEITHER surface
fires, class 5 degrades to reviewer judgment and the verdict must say so plainly rather than
guessing — this asymmetry is why the pass reports and does not refuse.

**Class 5 is PROVISIONAL.** Classes 1-3 generalize from a measured corpus; class 5's second firing
condition (defect vocabulary) generalizes from ONE incident (2026-07-27: a plan claimed a model
resolver's default was defective when it was in fact a PM-ratified asymmetry, caught only because
a defect-vocabulary trigger like this one would have flagged it for a symbol read). That is
enough to ship it as an acceptance criterion and not enough to call the trigger calibrated. The
mark comes off once a later session has counted enough real firings, in
`state/audits/2026-09-06-blitz-conversion-re-measurement.md`'s Arm C table, to say the trigger's
precision — each row sourced from a wave's per-baton `*.premise-check.md` sidecar under that
wave's trail directory (`sidecarFor(trailDir, batonId, 'premise-check')` in `plan-blitz.mjs`).
Until a wave has actually run this check, that table is empty and the PROVISIONAL mark stands —
an empty table is not evidence the trigger is miscalibrated, only that it has not fired yet. Until
the mark comes off, a class-5 finding carries the same weight as any other finding — only the
TRIGGER is under review, not the finding's validity.

**Mechanical vs. judgment split, carried over verbatim.** Classes 1, 2 and 3 are mechanical:
existence either holds or does not. Class 5 is judgment: it requires reading a symbol's actual
behaviour and comparing it to a claim. A verdict that mixes the two without labeling which is
which loses the distinction that lets a reader gauge rework altitude at a glance.

Reporting carries the mechanical contract's rule unchanged, with one class-5 case named: a
semantic-check miss with no forbidding surface and no defect vocabulary is reported as "semantic
check not applicable, degrades to reviewer judgment," not withheld.
<!-- END premise-check-class-5-semantics -->
