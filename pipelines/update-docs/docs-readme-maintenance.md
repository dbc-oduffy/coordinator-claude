# Phase 2b: Maintain `docs/README.md`

Missing: create with sections — Wikis and Guides (table from `docs/wiki/DIRECTORY_GUIDE.md` or a
walk of `docs/wiki/**/*.md`; a split page's `<name>/README.md` is the one row for `<name>`),
Plans (pointer + count + recent list, canonical home `docs/plans/`), Research (pointer to
`docs/research/`, top 5–10 recent), Design Specifications (table from `docs/specs/`,
`docs/superpowers/specs/`, or project-specific), Reference Documentation (table of top-level
`docs/*.md`). Footer: `*Last updated: YYYY-MM-DD. Maintained by /update-docs.*`

<!-- Review: review-integrator/overengineering-reviewer — invocation shape lives once at
     detect-current-state.md § The updatedocs.gates invocation. -->

**Detect first.** `updatedocs.gates` (`detect-current-state.md § The updatedocs.gates invocation`
for the call shape) — the `docs-readme-index-drift` gate
names the drifted sections, the unindexed files, and any dead links. It detects and never writes:
the Wikis-and-Guides Topic column is a hand-written summary per entry, so the sync below stays
yours. A verdict of `unavailable` means the gate could not see the corpus — fall back to the walk.

Exists: sync each section against current state (add/remove/update); update the footer
timestamp.

Include in the Phase 9 commit.
