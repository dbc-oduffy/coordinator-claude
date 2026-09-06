# Phase 2: Update Source Indexes (or Create Them)

No `DIRECTORY.md`: dispatch one subagent per top-level source dir (`src/`, `Source/`, `lib/`,
`app/`, `packages/`, etc.) to catalog files (name, primary component, one-line purpose, key
exports, cross-dir deps) into a per-directory `DIRECTORY.md`; >2 dirs, stamp a
`coordinator-doc-new --type workflow`. Then write a root `DIRECTORY.md`: per-directory summary,
file counts, cross-directory dependency chains, "Last refreshed" timestamp. Default location:
project root; match project convention if different.

<!-- Review: review-integrator/overengineering-reviewer — invocation shape + tri-state semantics
     now live once, at detect-current-state.md § The updatedocs.gates invocation. -->

**Detect first.** The `directory-md-staleness` gate of `updatedocs.gates`
(`detect-current-state.md § The updatedocs.gates invocation` for the call shape and the
`unavailable`/`clean` semantics) reports whether an index's asserted counts and refresh date still
match disk. It discovers the index the way this page prescribes — root `DIRECTORY.md`, then
`docs/DIRECTORY.md`, then top-level directories — and `overrides["directory_md"]` pins an
explicitly-named path. A repo with no index anywhere reads `unavailable` with the path it looked
for, never `clean`; the scaffold branch above is what answers it. The gate detects only — every
write below stays yours.

`DIRECTORY.md` exists: diff against actual files, add/remove entries, update counts/timestamps/
deps, create per-directory indexes for any new directories.

No source changes and indexes exist: skip.
