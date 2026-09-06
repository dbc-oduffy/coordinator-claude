---
title: Overriding and tracking upstream
created: 2026-07-09
type: doctrine
related:
  - coordinator/docs/wiki/adapting-your-doctrine.md
  - coordinator/CLAUDE.md (retired, file deleted; § Working Relationship & Engagement
    has no direct successor heading — closest surviving list is global-doctrine/CLAUDE.md
    § Posture, invariant safety core)
  - claude-klabauter coordinator/lib/resolve-coordinator-clone.py  (§ _resolve_source_mode)
  - coordinator/docs/wiki/DIRECTORY_GUIDE.md
---

<!-- RAG-bait: personal CLAUDE.md layer composition, --plugin-dir auto-load, floor-invariance guarantee, dev-repo vs installed coordinator-claude, additive top layer, override without forking, track-upstream pattern -->

# Overriding and Tracking Upstream

> **Correction.** This page's original text described `coordinator/CLAUDE.md` as part of
> "the coordinator doctrine tree" that "auto-loads into every session as the coordinator floor" via
> `--plugin-dir`. That is false — see
> `coordinator/docs/wiki/claude-md-delivery-topology.md`. `--plugin-dir` genuinely delivers
> `skills/`, `agents/`, `hooks/`, `commands/`, and `lib/` live from the resolved tree; it does **not**
> deliver `coordinator/CLAUDE.md`. That file reached only DoE-claude sessions, only after a
> `coordinator/`-rooted Read, and did not survive `/compact`. It never reached a sibling-repo
> session at all. The corrections below replace every place this page previously leaned on the false
> mechanism. **Addendum.** `coordinator/CLAUDE.md` was subsequently
> deleted outright; its doctrine now lives split across `global-doctrine/CLAUDE.md` (all-agents
> surface) and `coordinator/snippets/em-operating-doctrine.md` (EM-only channel, delivered by a
> SessionStart hook). Every `coordinator/CLAUDE.md § <heading>` citation below is now historical —
> a record of what the retired file used to say, not a live pointer.

This page names the mechanism by which your personal `~/.claude/CLAUDE.md` **composes with** — rather
than replaces or edits — the coordinator plugin's live-resolved surface, while still tracking upstream
as it updates. `adapting-your-doctrine.md` names the fork boundary (doctrine-layer edits are
encouraged, hook/enforcement edits are a fork); this page fills the gap that boundary leaves open: the
HOW of composition.

## Two layers, one session

Every session loads two kinds of surface:

1. **The coordinator plugin's live-resolved surface** — `skills/`, `agents/`, `hooks/`, `commands/`,
   and `lib/` — resolved live via `--plugin-dir`. Which concrete tree that points at — your working
   DoE clone during dev-loop iteration, or an installed `coordinator-claude` package otherwise — is
   decided by the source-mode selector: the `.coordinator-dev-repo` marker plus
   `_resolve_source_mode` (dev-repo-present → working clone; else → installed package; ambiguous → fail
   loud). This page does not re-document that selector's resolution rungs — see
   claude-klabauter `coordinator/lib/resolve-coordinator-clone.py` for the implementation.
   **`coordinator/CLAUDE.md` is not part of this delivery** — see the correction banner above.
2. **Your personal `~/.claude/CLAUDE.md`**, the one always-on fleet-wide doctrine prose surface, loaded
   at boot and again after every compaction, in every session and every dispatched subagent (except
   the built-in `Explore`/`Plan` agents).

## The composition mechanism

Overriding is additive, not surgical: you add prose to your OWN file. You do not open the resolved
coordinator plugin surface and edit its files — that surface is not yours to touch, and on a fresh
machine or after an upstream update it will not contain your edit anyway. Your `~/.claude/CLAUDE.md`
is git-tracked, persists across every resolver outcome, and is where any personal tuning belongs.

**This is not the same mechanism as the "extend not replace" convention that governs a project-level
`CLAUDE.md` extending the global `~/.claude/CLAUDE.md` floor.** Both are prose
files in the same personal-authoring layer, one scoped to a repo. The personal-layer-over-plugin-surface
composition described on this page is a different seam entirely: one side (`--plugin-dir`) is a
resolved, non-editable machinery surface (skills/agents/hooks/commands/lib); the other
(`~/.claude/CLAUDE.md`) is your own editable prose file. Citing the project/global "extend not replace"
rule as the explanation for THIS composition is a category error — don't make it.

## Floor invariance — corrected, and now an open question rather than a settled structural fact

**Prior text (false, retained here only as the record of what was corrected):** *"the floor arrives via
the `--plugin-dir`-resolved coordinator tree… the floor invariants… keep firing, because they live in
the tree, not in the file you hold the pen on."* That claim depended on `coordinator/CLAUDE.md` — where
the floor invariants (verification before done, the PM-facing ask-before-external-action gate, the
pre-execute plan-authorization gate, review sequencing) are written down as prose — reaching every
session via `--plugin-dir`. It doesn't. See the correction banner at the top of this page.

What actually still holds structurally, without relying on `coordinator/CLAUDE.md` prose reaching
anyone: the **hook-enforced** floor gates (e.g. PreToolUse checks) are delivered by `--plugin-dir` along
with `hooks/`, so where a floor invariant is backed by an actual hook rather than by prose alone, that
enforcement is real and fleet-wide-ish in the sense the hook mechanism reaches. But the floor invariants
that exist only as prose guidance in `coordinator/CLAUDE.md` — with no hook behind them — do **not**
reliably reach a session the way this page previously claimed, and the "you cannot edit your way out of
the floor" framing is not a settled structural guarantee for those. Whether/how coordinator should
deliver that prose-level floor fleet-wide (a skill, a `SessionStart`-emitted `additionalContext`, a
per-repo `@import`) is an open, unratified engineering question — see
`claude-md-delivery-topology.md` § Trap A. This page does not resolve it.

This revises the guarantee `adapting-your-doctrine.md` names under "One invariant survives every edit on
the supported side" — that page's framing inherits the same correction; check it has been updated before
citing it as settled.

## Tracking upstream

Because your personal layer is a separate file from the resolved plugin surface, upstream updates to
that surface (a plugin update, a new installed `coordinator-claude` version, or your own DoE clone
advancing) never clobber your personal prose — there's nothing to merge, because the two never occupied
the same file. Your override survives every upstream refresh because the seam between the two layers
runs in both directions — this part of the mechanism is unaffected by the `coordinator/CLAUDE.md`
correction above, since it was never about doctrine-prose delivery, only about file-identity.

## Negative-spec

- This page does not document `_resolve_source_mode` or the `.coordinator-dev-repo` marker's
  resolution rungs — that is claude-klabauter `coordinator/lib/resolve-coordinator-clone.py`'s remit (built in v3split-06).
  This page only documents how the personal layer composes with whichever tree that selector resolves.
- This page does not cover hook/enforcement-substrate editing — that is the fork side of the
  Mirror-Universe boundary in `adapting-your-doctrine.md`, out of scope here as there.
- "Shim" is deliberately avoided in this page's title and body — that word is reserved for
  `COORDINATOR_SHIM_RC`'s RC-injection meaning elsewhere in the codebase; using it here would collide.
- This page does not re-litigate how coordinator should deliver prose-level doctrine (like the floor
  invariants) fleet-wide — that is an open PM/EM question named in
  `claude-md-delivery-topology.md`, not something to re-derive here.

## Related

- `coordinator/docs/wiki/claude-md-delivery-topology.md` — the authoritative account of what actually
  reaches whom; read before citing this page's floor-invariance claims.
- `coordinator/docs/wiki/adapting-your-doctrine.md` § "One invariant survives every edit on the supported
  side" — the posture-customization framing of the same floor-invariance guarantee, carrying the same
  correction.
- `coordinator/CLAUDE.md` § Working Relationship & Engagement (retired, file deleted; no
  direct successor heading located — closest surviving list is `global-doctrine/CLAUDE.md`
  § Posture, invariant safety core) — the floor invariants list this page's floor-invariance
  discussion cites (prose text; delivery to a given session was never guaranteed by `--plugin-dir`
  even before deletion — see the correction banner above).
- claude-klabauter `coordinator/lib/resolve-coordinator-clone.py` § `_resolve_source_mode` — the dev-repo-vs-installed
  selector this page references but does not re-document.
