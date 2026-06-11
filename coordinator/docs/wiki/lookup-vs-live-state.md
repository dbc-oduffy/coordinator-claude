# Lookup Tables vs Live State

> Lookup tables (chunk-id-lookup.txt, structural-index manifests, asset registries, frontmatter indexes) are append-only snapshots of *every variant ever generated*. Live consumers carry *one* variant. "Entry exists in the lookup" is necessary but not sufficient for "this entry matches the consumer's current state."

*Lesson surface: 2026-05-16, project-rag — a downstream tool succeeded its post-condition check by finding the cited ID in the lookup table, but the live consumer carried a different variant of the same ID. The lookup confirmed fabrication-absence; it did not confirm freshness.*

## The asymmetry

A lookup table is built by accumulating outputs from many runs over time. Once an entry lands, it stays — even if the producer's contract has shifted such that a fresh run would no longer emit that exact shape. The lookup is a history of "what was ever produced," not "what is currently producible."

A live consumer reads its input from the current state of the producer. If the producer regenerated since the lookup was last updated, the consumer's input may diverge from the lookup's recorded form for the same conceptual entry.

Post-condition tests that gate on "entry exists in lookup" catch one class of bug:
- **Fabrication.** An ID that was never produced (typo, hallucinated, off-by-one). The lookup is the right witness — if it's not there, it wasn't produced.

They do NOT catch:
- **Staleness.** An ID that was produced under contract V1 but the live consumer expects contract V2. The lookup has the V1 entry; the test passes; the consumer fails downstream because the V2 reader can't parse V1's shape.

## Rule

When a test or audit relies on a lookup-table presence check, pair it with a live-consumer cross-check:

1. **Lookup check:** does the entry exist? (catches fabrication)
2. **Live-state check:** does the live producer, run now, produce the same entry shape as the lookup carries? (catches staleness)

The two checks together are the contract. Either alone is admissible only when staleness is structurally impossible (the producer is immutable, the lookup is regenerated on every run, etc.).

## The deterministic-prediction detection pattern

The Data Science Reviewer's deterministic-prediction pattern is the general detection mechanism: before re-running an expensive producer to validate a contract change, re-score existing results against the new labels. If the existing results still match the new labels, you have evidence of freshness. If they diverge, you have a label-vs-result mismatch that signals either a real shift or a stale snapshot — but you know to investigate before re-running.

This generalizes to lookup-table audits: re-evaluate the lookup's entries against the current consumer's expectations before declaring "still good." Cheap, deterministic, surfaces the staleness class that presence-checks miss.

## Where this surfaces in this codebase

- `chunk-id-lookup.txt` and structural-index manifests in project-RAG — append-only, every regeneration adds to the table.
- Asset registries in UE projects — `manage_asset_registry` shows every variant ever cooked into the registry, not what the editor currently has loaded.
- Frontmatter-indexed records (handoffs, plans, decisions) — `bin/query-records` reads the on-disk frontmatter, which is live; but downstream caches of those records can stale-snapshot.

## Cross-references

- [`pre-dispatch-verification.md`](./pre-dispatch-verification.md) — substrate verification at plan-write time; presence-vs-freshness is the same shape.
- [`verification-before-completion.md`](./verification-before-completion.md) — "lookup says present" is not "consumer sees correct value."
- [`round-trip-contract-tests.md`](./round-trip-contract-tests.md) — at least one test must run real producer feeding real consumer; the round-trip catches the staleness class lookup-presence misses.
