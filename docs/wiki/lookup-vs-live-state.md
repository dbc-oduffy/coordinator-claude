# Lookup Tables vs Live State

> Lookup tables (chunk-id-lookup.txt, structural-index manifests, asset registries, frontmatter indexes) are append-only snapshots of *every variant ever generated*. Live consumers carry *one* variant. "Entry exists in the lookup" is necessary but not sufficient for "this entry matches the consumer's current state."

*Lesson surface: project-rag — a downstream tool succeeded its post-condition check by finding the cited ID in the lookup table, but the live consumer carried a different variant of the same ID. The lookup confirmed fabrication-absence; it did not confirm freshness.*

## The asymmetry

A lookup table is built by accumulating outputs from many runs over time. Once an entry lands, it stays — even if the producer's contract has shifted such that a fresh run would emit a different shape. The lookup is a history of "what was ever produced," not "what is currently producible."

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

## Which state plane does the op read? (worktree-local vs central)

Presence-vs-freshness has a sibling failure: an op that resolves entities or records from the *wrong state plane*. A producer reading its input from the **scanned worktree** returns empty — not wrong-shaped, empty — when the entities it references are **central-resident** elsewhere, and vice versa. The record exists; the live op just isn't looking at the plane where it lives.

Two instances, same shape:

- **`deliverable.rollup` resolves `state/initiatives/<id>.yaml` from the scanned worktree** (`deliverable_rollup.py:291`), but DoE's initiative entities are central-resident in claude-klabauter. Every correctly-populated FK rendered empty (`artifacts_matched: 1`, `advances_initiatives: []`) — proof: the same op returns the resolved edge once the entity is copied into the scanned worktree. Populating the FK does not lift recall until the op reads the plane the entity lives on.
- **`audit-roadmap.py` (via `cc_records_query`) defaults its query `--root` to `coordinator_claude_klabauter_root`**, so a locally-authored roadmap's spinoff-roadmap stubs are invisible to a bare `audit-roadmap.py <run-id>` — it reports 0 stubs / coverage-0 / "Audit 5 skipped" even with 9 valid stubs on disk. Pin `CLAUDE_KLABAUTER_ROOT=<repo-root>` (or `--root <repo>`) when auditing a non-claude-klabauter-resident roadmap.

Rule: before assuming substrate population activates a capability, confirm **which state plane the op resolves against** — worktree-local vs central store. A cross-entity FK, a records query, or any resolver silently picks one plane; if your data lives on the other, the op returns empty and the on-disk presence check still passes.

## Running code arbitrates over a stale wiki

When a wiki's stated path/location disagrees with where a *writer that actually runs* puts the file, trust the writer and flag the doc drift. `state-placement-law.md` and `machine-local-registry.md` said `setup/` had relocated to `<settings-home>/setup/`, but the migrate script + install-substrate write it to `~/.claude/setup/`; a failing uninstall test fixture surfaced the drift. The code that runs is authoritative — a wiki is a snapshot of intent, the writer's target is live state. Let the failing test fixture arbitrate the disagreement rather than trusting the prose.

## Membership is a query, not a substring grep

A presence check via raw `grep` for a sentinel string can match a *prose mention* of the sentinel — a doc explaining the sync rule — rather than an actual synced block. Confirm consumer/registry membership through the mechanism's **own list command** (e.g. `verify-snippet-sync prior-art-check-consumption --list`), not a substring scan. The false positive is not benign: a grep-match on a BEGIN-sentinel *mention* flipped a dispatch-gate classification (thought `prior-art-checker.md` was a sync consumer → serial gate; `--list` showed it wasn't → disjoint parallel wave). Same presence-vs-truth asymmetry as the rest of this wiki, one layer down: "the string appears" is necessary but not sufficient for "this is a registered member."

## Where this surfaces in this codebase

- `chunk-id-lookup.txt` and structural-index manifests in project-RAG — append-only, every regeneration adds to the table.
- Asset registries in UE projects — `manage_asset_registry` shows every variant ever cooked into the registry, not what the editor currently has loaded.
- Frontmatter-indexed records (handoffs, plans, decisions) — `bin/query-records` reads the on-disk frontmatter, which is live; but downstream caches of those records can stale-snapshot.

## Cross-references

- [`pre-dispatch-verification.md`](./pre-dispatch-verification.md) — substrate verification at plan-write time; presence-vs-freshness is the same shape.
- [`verification-before-completion.md`](./verification-before-completion.md) — "lookup says present" is not "consumer sees correct value."
- [`round-trip-contract-tests.md`](./round-trip-contract-tests.md) — at least one test must run real producer feeding real consumer; the round-trip catches the staleness class lookup-presence misses.
