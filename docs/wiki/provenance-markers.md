# Provenance Markers

> Purpose: enumerate the frontmatter keys that record where a `/distill`-harvested artifact's
> content went, and the exclusion rule that keeps a reference inside one of those blocks from
> being mistaken for a live dependency by active-reference checking.

## The problem this contract closes

`/distill`'s delete-guard `check_active_reference` (Guard 3) matches a deletion candidate's
repo-relative path anywhere in the corpus it scans (`docs/`, `tasks/`, `archive/`). A harvested
artifact's own harvest-provenance frontmatter block records that same repo-relative path — so the
artifact's provenance block trips the active-reference check against *itself*, and the artifact is
retained as "still actively referenced" even though the only citation is its own tombstone. This
silently defeats delete-by-default. The fix is not a code patch to one guard; it is a vocabulary
contract naming which frontmatter blocks are tombstones, not dependencies, so any consumer of
active-reference logic can apply the same exclusion consistently.

## The marker key set (the contract)

Two keys are the currently-enforced provenance-marker vocabulary:

- **`archived_handoff:`** — handoff harvest provenance. A list; each item carries `path:` (a
  repo-relative `archive/handoffs/<name>.md`), plus `workstream`, `last_verbose_sha`, and
  `distilled`. Defined in `coordinator/commands/distill.md` § "Provenance frontmatter — new
  `archived_handoff:` key".
- **`cross_repo_memo:`** — cross-repo memo harvest provenance. A list; each item carries `path:`
  (a repo-relative `cross-repo/archive/<name>.md`), plus `from`, `to`, and `distilled`. Defined in
  `coordinator/commands/distill.md` § "Provenance frontmatter — `cross_repo_memo:` key".

**Under consideration, not yet in the enforced set:** `provenance:` (archived-spec harvest
provenance — specs trim in place rather than delete, so exclusion matters less here and this key
is lower priority) and `judgment_provenance:` (codebase-judgment entries). These are candidates
the engine owner may fold into the exclusion set later; they are not part of it today. Do not
treat either key as excluded from active-reference until this section is updated.

## Semantics

- A deletion candidate cited **only** inside provenance-marker blocks → active-reference PASSES →
  the candidate is deletable. The block is the candidate's tombstone, not a caller.
- A deletion candidate cited **anywhere outside** a provenance-marker block — prose body,
  non-provenance frontmatter — → active-reference BLOCKS → the candidate is retained. This is
  unchanged from today's behavior for every reference that isn't a provenance marker.

No delete hole is opened by this contract: a citation outside a marker block still pins the
candidate exactly as it does now. The contract only narrows what counts as "still referenced," it
never widens what counts as "safe to delete."

## Cross-repo consumption

DoE owns this vocabulary; the engine — claude-klabauter's `active_reference_guard` in
`coordinator_core/distill/_common.py` — consumes it, holding a local set of excluded keys in
lockstep with a back-pointer comment to this file. This is the same ownership split as
`SIDECAR_SUFFIXES`, whose own code comment already names DoE's contract as the eventual
cross-repo single owner: DoE authors and evolves the vocabulary here, the engine mirrors it
locally rather than reading it live.

The engine's mirror is `coordinator_core/distill/_common.py :: PROVENANCE_MARKER_KEYS`, holding
exactly the two enforced keys above. `active_reference_guard` is match-location-aware against it:
cited only inside a recognized marker block passes; cited anywhere else blocks; cited both inside
and outside blocks; an unrecognized lookalike key blocks. `check_harvest_provenance` (Guard 7) is
unaffected — the same block remains positive durable-capture proof for it.

Adding a key here is a cross-repo change, not a local edit: the engine mirrors this set rather
than reading it live, so a key added here without a matching engine change is not enforced, and a
key added engine-side without landing here has no upstream. `provenance:` and
`judgment_provenance:` are the standing candidates and are deliberately NOT in the set.
