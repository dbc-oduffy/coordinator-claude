# `Resolves:` commit-trailer convention

> Spec backlink: `docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md` § C4

## Purpose

A commit that completes work on a durable artifact (handoff, completion-entry,
roadmap item, or any other artifact carrying a stable ID) carries a git
trailer:

```
Resolves: <artifact-id>
```

One trailer line per resolved artifact; a single commit may carry multiple
`Resolves:` lines if it closes out more than one artifact at once:

```
Resolves: hnd-2026-07-08-abc123
Resolves: cmp-2026-07-08-def456
```

This is git-native: trailers live in the commit message body, survive
rebase/cherry-pick/archival, and are queryable with stock git tooling —
`git log --grep='^Resolves: <id>$'` or the structured `%(trailers:...)`
pretty-format (see `coordinator/bin/parse-resolves-trailer.sh` below). No new
schema field, no external index, no stored liveness/roll-up state — the set
of resolving commits for a given artifact-id is *derived* by querying commit
history on demand (`coordinator/bin/rollup-derive.sh`, C5).

## Sibling precedent — `Session-Id:` trailer

This convention follows the shape already shipped for the `Session-Id:` git
trailer, documented in `coordinator/docs/wiki/workstream-complete-review.md`
<!-- Review: code-reviewer (F3, nit) — replaced the paraphrased quoted
     section title with the actual heading text, verbatim, so a
     grep-based cross-reference tool can find it. -->
§ "Session-scoped diff via `--session-id` — fixes the brightline gate on
shared-branch concurrent EM work" (2026-06-15). That trailer is
injected by a `prepare-commit-msg` hook and consumed via
`git log --grep='^Session-Id: <id>$'` inside `review-brightline-gate.sh
--session-id`. The `Resolves:` trailer reuses the same shape — a plain
greppable git trailer, parsed with stock git subcommands, with no bespoke
storage.

**Zero-match semantics carry over unchanged: a vacuous pass, not a
hard-fail.** The `Session-Id:` doctrine states it explicitly:

> Zero-match semantics — fail-loud-non-blocking, NOT silent fallback. When
> `--session-id` filters to zero matching commits ... the vacuous pass is the
> calibrated shape — hard-fail would block every workstream-complete in the
> first session post-ship (no commits carry trailers yet) and re-create the
> route-around failure mode this fix exists to prevent.

The `Resolves:` trailer inherits this exactly: an artifact with **zero**
resolving commits (the normal pre-adoption state — no commit has referenced
it yet, or its lifecycle hasn't reached a resolving commit) is a vacuous pass,
not an error. `coordinator/bin/rollup-derive.sh` (C5) surfaces this as its own
explicit `no-resolving-commits` token — never collapsed into a `not-shipped`
verdict, for the identical reason the `Session-Id:` gate never collapses
zero-match into "gate failed": treating "no commits reference this yet" as
"confirmed not done" is a correctness bug, not a conservative default.

## Querying

Prefer git's structured trailer pretty-format over ad-hoc grep/sed when you
need the actual artifact-ID values (not just a yes/no match):

```bash
git log --format='%(trailers:key=Resolves,valueonly)' <commit>
```

This requires git ≥ ~2.15 (the release that added the `%(trailers:...)`
pretty-format token). See `coordinator/bin/parse-resolves-trailer.sh` for the
canonical parser, which pins this version floor and documents the fallback
path (`git interpret-trailers --parse`) for the same commit range.

For an existence check only (does *any* commit resolve this artifact), plain
`git log --all --grep='Resolves: <artifact-id>'` is sufficient and requires
no version floor beyond ordinary `--grep` support.

## Negative-spec

- Do **not** store a resolved/liveness/roll-up-state field on the artifact's
  own schema record as a substitute for this trailer — the trailer is the
  durable link; any derived status field the artifact schema carries (e.g. a
  terminal `deployment_state`) is *stamped from* a `rollup-derive.sh`
  derivation, never treated as the source of truth itself
  (`canonical-artifact-shapes.md`).
- Do **not** treat a `Resolves:` match found once as permanently valid — a
  resolving commit can leave `origin/main` (history rewrite, branch
  deletion); re-derive on every query rather than caching a prior result.
- Do **not** hard-fail on zero matching commits — see § Zero-match semantics
  above.

## Cross-references

- `coordinator/docs/wiki/workstream-complete-review.md` — sibling
  `Session-Id:` trailer convention and its zero-match semantics (cited
  above).
- `coordinator/bin/parse-resolves-trailer.sh` — the parser this convention
  specifies.
- `coordinator/bin/rollup-derive.sh` — the roll-up-derivation primitive that
  consumes the parser's output alongside `check-shipped-on-main.sh` (C5).
- `coordinator/docs/wiki/canonical-artifact-shapes.md` § lvv-01 — the
  stable-ID table (`hnd-`/`cmp-`/`pln-`/`dlv-` prefixes and their mint seam)
  whose IDs populate the `<artifact-id>` this trailer names, plus the
  ID-companion ancestry fields (`predecessor_id`/`origin_handoff_id`) this
  cluster added alongside the trailer.
