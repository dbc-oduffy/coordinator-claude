---
title: Held-Out Slice Sealing Pattern
status: living
last_updated: 2026-05-14
applies_to: any ML/data-validation workflow where evaluation-slice contamination is a risk
source: project-rag-ue-addon/docs/wiki/held-out-slice-sealing-doctrine.md
note: plugin-bundled UNIVERSAL companion; project-local source is canonical for project context
---

# Held-Out Slice Sealing Pattern

Operational pattern for sealing a held-out evaluation slice across
multi-wave authoring where authoring agents and evaluation share a
substrate. First codified in `project-rag-ue-addon` during the tc-2 V1.1
rule library effort (2026-05-13); reusable across any workflow with
disjoint-pattern construction or post-hoc selection risk.

The project-local source wiki at
`project-rag-ue-addon/docs/wiki/held-out-slice-sealing-doctrine.md` carries
the full V1.1 context (IDs, file paths, wave sequencing). This file
extracts the universal pattern.

## The Risk Being Mitigated

Reading held-out misses during authoring and naming the rule (or model
feature) shape that would have caught them is textbook slice
contamination — the artifact's authoring is causally downstream of the
slice it will be evaluated against. The slice can no longer evaluate the
artifact honestly.

This shows up especially in:

- Eval-driven **rule libraries** where rule authoring and evaluation share
  an EM/executor lineage.
- ML **feature engineering** when error analysis of held-out predictions
  reshapes the feature set.
- **Statistical evaluation** where the sample population was constructed
  by excluding the training population (a disjoint-pattern test
  masquerading as a held-out generalization test).

## Banner-Sealing — Two-Layer Mechanism

Sealing is enforced by two layers, neither sufficient alone:

1. **Banner-sealing — human-readable.** HTML comment banners on Markdown
   and JSON sibling files; manifest-table banners on machine-readable
   sources. Convention: `<!-- SEALED-<version> -->`. Documentation, not
   enforcement.

2. **Operational gate — existence-of-file.** A retirement flag (e.g.
   `eval/heldout-retired.flag`) gates the metrics harness. After the
   single evaluation wave completes, the flag is created and the harness
   refuses to re-run against the retired slice. This is the layer that
   fails loud.

The banner is **NOT code-enforced** by itself — harnesses generally take
paths as CLI args; no whitelisted-access affordance lives in the harness.
Code-enforcement lives in the retirement flag, not the seal.

## Banner-with-Redirect, Not Move-Based Sealing

Move-based sealing (relocate the held-out files to a `_sealed/`
directory) is rejected: the metrics harness carries hard-coded paths;
moving the files breaks the harness without making the seal more robust.
Banner-with-retirement-flag preserves path stability and pairs cleanly
with the gate.

If a wave needs to *evaluate* the held-out slice, banners come off for one
metrics run, then go back on alongside flag creation. The slice is
single-shot by design; re-running metrics after a tweak re-contaminates
it.

## The Lifecycle — Seal → Mine → Evaluate Once → Retire

1. **Seal** at the wave that constructs the slice. Banners on every
   held-out artifact; a NEVER-READ list of held-out IDs **inlined
   verbatim** into all downstream executor prompts. Inlined, not referenced
   by path — reference-by-path leaves contamination open if the file is
   read for any reason.
2. **Mine** the authoring waves. Artifact shapes come from
   visible-population density, not held-out-miss inspection.
3. **Evaluate once.** The EM is the single human in the loop for
   seal-break: banners come off, metrics run, fresh report lands, banners
   go back on.
4. **Retire.** The retirement flag is created. Future evaluation uses a
   fresh telemetry-driven slice, not a slice-mining-derived one.

The lifecycle is **one-shot by design**. Any further iteration on this
slice — re-running metrics after a tweak to check if it helped — would
re-contaminate it.

## The NEVER-READ List — Inlined, Not Referenced

The held-out IDs are inlined verbatim in every dispatch prompt for waves
that author or shape-mine. Not in a referenced file. Not in a
"see `eval/sealed-ids.txt`" pointer. **Inlined.** Executors that need to
evaluate get the unseal authority for that one wave only.

## When to Use This Pattern

- Eval-driven artifact library where authoring and evaluation share an
  EM/executor lineage.
- Statistical evaluation where the sample population was constructed by
  exclusion from a fixed pool.
- Any workflow where reading the held-out surface during authoring is
  physically possible (i.e. not strictly enforced by infrastructure).

## When NOT to Use This Pattern

- **True held-out via telemetry collection.** Telemetry-driven slices are
  not constructed by exclusion from a fixed pool; sealing is not the right
  primitive.
- **Strict k-fold cross-validation.** K-fold ships its own leakage
  controls; banner-sealing layered on top adds friction without value.
