---
title: Overriding and tracking upstream
created: 2026-07-09
type: doctrine
related:
  - coordinator/docs/wiki/adapting-your-doctrine.md
  - coordinator/CLAUDE.md  (§ Working Relationship & Engagement)
  - coordinator/lib/resolve-coordinator-clone.sh  (§ _rcc_resolve_source_mode)
  - coordinator/docs/wiki/DIRECTORY_GUIDE.md
---

<!-- RAG-bait: personal CLAUDE.md layer composition, --plugin-dir auto-load, floor-invariance guarantee, dev-repo vs installed coordinator-claude, additive top layer, override without forking, track-upstream pattern -->

# Overriding and Tracking Upstream

This page names the mechanism by which your personal `~/.claude/CLAUDE.md` **composes with** — rather
than replaces or edits — the coordinator doctrine tree, while still tracking upstream as it updates.
`adapting-your-doctrine.md` names the fork boundary (doctrine-layer edits are encouraged, hook/enforcement
edits are a fork); this page fills the gap that boundary leaves open: the HOW of composition.

## Two layers, one session

Every session loads two doctrine sources:

1. **The coordinator doctrine tree**, resolved live via `--plugin-dir`. Which concrete tree that points
   at — your working DoE clone during dev-loop iteration, or an installed `coordinator-claude` package
   otherwise — is decided by the source-mode selector: the `.coordinator-dev-repo` marker plus
   `_rcc_resolve_source_mode` (dev-repo-present → working clone; else → installed package; ambiguous → fail
   loud). This page does not re-document that selector's resolution rungs — see
   `coordinator/lib/resolve-coordinator-clone.sh` for the implementation. What matters here is only that
   whichever tree it resolves to, it auto-loads into every session as the coordinator floor.
2. **Your personal `~/.claude/CLAUDE.md`**, loaded ALONGSIDE the resolved tree — not merged into it, not
   overriding it, just co-present in the same context window.

## The composition mechanism

Overriding is additive, not surgical: you add prose to your OWN file. You do not open the resolved
coordinator tree and edit its files — that tree is not yours to touch, and on a fresh machine or after an
upstream update it will not contain your edit anyway. Your `~/.claude/CLAUDE.md` is git-tracked, persists
across every resolver outcome, and is where any personal tuning belongs.

**This is not the same mechanism as the "extend not replace" convention that governs a project-level
`CLAUDE.md` extending the global `~/.claude/CLAUDE.md` floor.** Both are prose
files in the same personal-authoring layer, one scoped to a repo. The personal-layer-over-doctrine-tree
composition described on this page is a different seam entirely: one side (`--plugin-dir`) is a resolved,
non-editable tree; the other (`~/.claude/CLAUDE.md`) is your own editable file loading alongside it. Citing
the project/global "extend not replace" rule as the explanation for THIS composition is a category error —
don't make it.

## Floor invariance — the single most important fact here

**You cannot edit your way out of the safety floor**, and the reason is structural, not a promise: the
floor arrives via the `--plugin-dir`-resolved coordinator tree, a tree you do not edit. Your personal
`~/.claude/CLAUDE.md` — the file you CAN edit freely and are encouraged to — is a separate, additive file.
No matter how much prose you add, remove, or rewrite in your own file, the floor invariants named in
`coordinator/CLAUDE.md` § Working Relationship & Engagement (verification before done, the PM-facing
ask-before-external-action gate, the pre-execute plan-authorization gate, review sequencing, and the rest)
keep firing, because they live in the tree, not in the file you hold the pen on.

This is the same guarantee `adapting-your-doctrine.md` names under "One invariant survives every edit on
the supported side" — that page states it from the posture-customization angle; this page states it from
the layer-composition angle. Read together, they're the same fact seen from two directions: you can push a
posture arbitrarily far in your own file, and the tree underneath keeps the floor firing regardless.

## Tracking upstream

Because your personal layer is a separate file from the resolved tree, upstream updates to the tree (a
plugin update, a new installed `coordinator-claude` version, or your own DoE clone advancing) never
clobber your personal prose — there's nothing to merge, because the two never occupied the same file. Your
override survives every upstream refresh for the same structural reason the floor survives every personal
edit: the seam between the two layers runs in both directions.

## Negative-spec

- This page does not document `_rcc_resolve_source_mode` or the `.coordinator-dev-repo` marker's
  resolution rungs — that is `coordinator/lib/resolve-coordinator-clone.sh`'s remit (built in v3split-06).
  This page only documents how the personal layer composes with whichever tree that selector resolves.
- This page does not cover hook/enforcement-substrate editing — that is the fork side of the
  Mirror-Universe boundary in `adapting-your-doctrine.md`, out of scope here as there.
- "Shim" is deliberately avoided in this page's title and body — that word is reserved for
  `COORDINATOR_SHIM_RC`'s RC-injection meaning elsewhere in the codebase; using it here would collide.

## Related

- `coordinator/docs/wiki/adapting-your-doctrine.md` § "One invariant survives every edit on the supported
  side" — the posture-customization framing of the same floor-invariance guarantee.
- `coordinator/CLAUDE.md` § Working Relationship & Engagement — the floor invariants list this page's
  floor-invariance guarantee cites.
- `coordinator/lib/resolve-coordinator-clone.sh` § `_rcc_resolve_source_mode` — the dev-repo-vs-installed
  selector this page references but does not re-document.
