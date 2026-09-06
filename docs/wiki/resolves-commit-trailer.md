# `Resolves:` commit-trailer convention

> Spec backlink: `docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md` § C4
> Producer backlink: `docs/plans/2026-08-01-baton-spine-information-integrity.md` § A1

## Producer

**This trailer now has a live producer.** From lvv-01/C4 onward, this
convention, its parser (`parse_resolves_trailer.py`), and its oracle (`rollup_derive.py`) all
shipped — but **nothing ever wrote the trailer**: zero commits in claude-klabauter's history carried
it, and it was absent from claude-klabauter's `coordinator_core/contract/
commit-trailer-producer-contract.md`. `rollup_derive` therefore returned `no-resolving-commits`
for every deliverable claude-klabauter has ever shipped, stranding every roadmap baton `in_flight`
regardless of actual completion.

The producer is claude-klabauter's `commit.anchors` op
(`coordinator_core/ops/commit_anchors.py`), registered in
`coordinator_core/contract/commit-trailer-producer-contract.md` § 1.1/§ 1.2b as an eighth
trailer key. It stamps `Resolves: <dlv-id>` **only at the workstream-complete / ship-handoff
ceremony's completion event** — reusing the same `deliverable_id` it already resolves for
`Deliverable-Id:` from the staged plan's frontmatter, gated on an additional signal: a staged
`archive/completed/*.md` completion entry in the same commit. An ordinary mid-flight commit
(carrying `Deliverable-Id:` alone, from a workstream's first commit onward) never emits
`Resolves:` — that conflation (workstream-membership vs. completion) is exactly the defect this
producer exists to avoid. `rollup_derive.py`'s existing exact-key join is left semantically
unchanged; this is a producer-side fix, never a consumer-side join widen.

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

**The line must sit in the message's final paragraph, with no blank line between
it and the other trailers.** Git recognizes trailers only in the last block of the
message, so a `Resolves:` line set off as its own paragraph — above a
`Co-Authored-By:` block, say — is prose, not a trailer, and the oracle sees
nothing. Nothing warns you: the commit succeeds, the line is plainly visible in
`git log`, and `rollup-derive` answers `no-resolving-commits` as if you had never
written it. Verify with `git log -1 --format='%(trailers:key=Resolves,valueonly)'` — empty
output means the trailer did not take. The repair is a **new** commit carrying a
well-formed trailer, never an amend: `rollup-derive` unions every commit carrying
the trailer rather than reading only the newest, and on a shared branch an amend
lands on whoever committed last (§ AMEND-ON-SHARED-BRANCH in
`coordinator/docs/wiki/coordinator-tripwires/`).

This is git-native: trailers live in the commit message body, survive
rebase/cherry-pick/archival, and are queryable with stock git tooling —
`git log --grep='^Resolves: <id>$'` or the structured `%(trailers:...)`
pretty-format (see claude-klabauter `coordinator/bin/parse-resolves-trailer.py`
below). No new schema field, no external index, no stored liveness/roll-up
state — the set of resolving commits for a given artifact-id is *derived* by
querying commit history on demand (claude-klabauter
`coordinator/bin/rollup-derive.py`, C5).

## Sibling precedent — `Session-Id:` trailer

This convention follows the shape already shipped for the `Session-Id:` git
trailer, documented in `coordinator/docs/wiki/workstream-complete-review.md`
<!-- Review: code-reviewer (F3, nit) — replaced the paraphrased quoted
     section title with the actual heading text, verbatim, so a
     grep-based cross-reference tool can find it. -->
§ "Session-scoped diff via `--session-id` — fixes the brightline gate on
shared-branch concurrent EM work". That trailer is
injected by a `prepare-commit-msg` hook and consumed via
`git log --grep='^Session-Id: <id>$'` inside `review-brightline-gate.py
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
not an error. Claude-klabauter `coordinator/bin/rollup-derive.py` (C5) surfaces this as its own
explicit `no-resolving-commits` token — never collapsed into a `not-shipped`
verdict, for the identical reason the `Session-Id:` gate never collapses
zero-match into "gate failed": treating "no commits reference this yet" as
"confirmed not done" is a correctness bug, not a conservative default.

### Zero *match* stays quiet; zero *join* goes loud

The vacuous-pass rule above governs a closer that resolved its inputs fine and then found no
resolving commits. It never governed a closer that could not resolve its inputs at all — that case
was reported as success too, which is what let one defect be rediscovered by hand by four separate
EMs on four separate days. Claude-klabauter's closers now separate the two
(`fdbff578b7dc`, corrected at `40bf1064a124`):

- **Join resolved, zero resolving commits** — unchanged. Vacuous pass, `no-resolving-commits`,
  exit 0. The Session-Id reasoning above is untouched.
- **Zero candidates** — the caller supplied artifacts that carry no roadmap-origin linkage at all
  (a memo-sourced plan with no `roadmap_id` is the common one). Genuinely nothing to do. Quiet,
  exit 0, flagged `no_candidates: true`.
- **Unjoinable inputs** — a named artifact carries join keys that resolve to nothing. Not "nothing
  to close"; "I could not read what you gave me." Loud, exit 1, naming the artifact and every key
  looked for.

**The discriminator is artifact contents, never which caller invoked the closer.** `pairs_resolved
== 0` on its own does not tell the two zero cases apart — an early framing that a per-target closer
has no zero-candidates case was wrong at the ceremony seam, where `post_commit_tail` calls
`close_origin_stub` for every plan a close-out touches, non-roadmap plans included. `pairs_resolved
> 0` with `closed == 0` remains a legitimate quiet success throughout.

Two things a reader gets wrong here. **The token did not move**: `no-resolving-commits` continues to
mean the quiet thing, so a consumer must never infer the loud case from it, and the four-token
contract registered in `DIRECTORY_GUIDE.md` and cited by `canonical-artifact-shapes.md` is
unchanged. **The moving axis is the exit code, not the verdict**: the Session-Id precedent forbids
collapsing zero-match into a failure *verdict* and says nothing about exit codes, so this narrows
the contract without reversing that precedent.
`verification-discipline.md` records the neighbouring defect in this family (the reaper inheriting
`promote-shipped-in-flight-stubs.py`'s fail-open `best_ct=-1` idiom); this runs opposite to it.

## Querying

Prefer git's structured trailer pretty-format over ad-hoc grep/sed when you
need the actual artifact-ID values (not just a yes/no match):

```bash
git log --format='%(trailers:key=Resolves,valueonly)' <commit>
```

This requires git ≥ ~2.15 (the release that added the `%(trailers:...)`
pretty-format token). See claude-klabauter `coordinator/bin/parse-resolves-trailer.py`
for the canonical parser, which pins this version floor and documents the fallback
path (`git interpret-trailers --parse`) for the same commit range.

For an existence check only (does *any* commit resolve this artifact), plain
`git log --all --grep='Resolves: <artifact-id>'` requires no version floor beyond
ordinary `--grep` support — but **it is not equivalent to what the oracle sees, and
the gap is a trap.** `--grep` matches the whole message as text; `rollup-derive`
keeps only candidates whose *parsed* trailer value matches exactly. A malformed
trailer (§ Purpose) matches the grep and fails the parse, so grep-says-yes /
oracle-says-`no-resolving-commits` is a real and reachable disagreement — and it
means your commit is malformed, never that the oracle is broken. When the two
disagree, believe the `%(trailers:...)` read.

## Negative-spec

- Do **not** store a resolved/liveness/roll-up-state field on the artifact's
  own schema record as a substitute for this trailer — the trailer is the
  durable link; any derived status field the artifact schema carries (e.g. a
  terminal `deployment_state`) is *stamped from* a `rollup-derive.py`
  derivation, never treated as the source of truth itself
  (`canonical-artifact-shapes.md`).
- Do **not** treat a `Resolves:` match found once as permanently valid — a
  resolving commit can leave `origin/main` (history rewrite, branch
  deletion); re-derive on every query rather than caching a prior result.
- Do **not** hard-fail on zero matching commits — see § Zero-match semantics
  above. Do **not** read that as licence to stay quiet when the *join itself*
  failed and no commit was ever queried — see § Zero *match* stays quiet;
  zero *join* goes loud.

## Sibling precedent — `Deliverable-Id:` trailer

A third member of this family, alongside `Resolves:` and `Session-Id:` — same
git-trailer shape, distinct join key. The three do not overlap in what they
name:

- **`Resolves:`** marks *completion* of a durable artifact (a handoff,
  completion-entry, or roadmap item reaches a terminal state because of this
  commit).
- **`Session-Id:`** marks *who committed* — the coordinator session that ran
  `git commit`, independent of what the commit was for.
- **`Deliverable-Id:`** marks *workstream membership* — which deliverable
  (`dlv-...`) this commit belongs to, independent of which session typed it.

`Deliverable-Id:` is produced by claude-klabauter
`coordinator/bin/coordinator-prepare-commit-msg`, which reads
`<git-dir>/coordinator-sessions/<sid>/session-shape.json` and stamps
`pickup.deliverable_id` (written at claim time by
`coordinator_core/archive_stamp.py::_record_pickup_best_effort` →
`coordinator_core/ops/session/record_pickup.py`) as the trailer value,
alongside `Session-Id:`. Both trailers share the same omit-rather-than-guess
discipline: a resolved session-id that fails UUID-shape validation omits
`Session-Id:` entirely, and since `Deliverable-Id:` resolution is keyed off
that same session-id, it is skipped too — a missing trailer is
coverage-neutral, a wrong one mis-attributes. The field is documented on the
schema at `coordinator/schemas/session-shape.schema.json`
(`pickup.deliverable_id` / `pickup_history[].deliverable_id`), pattern
`^dlv-[0-9a-zA-Z][0-9a-zA-Z-]*$`.

**Why it exists.** `Session-Id:` alone conflated "who ran `git commit`" with
"what work the commit was" — a session that spun off a baton and also shipped
unrelated work donated all of it to the spinoff's coverage attribution,
penalising exactly the behaviour the fleet wants to reward. Reported
independently by project-rag (8 commits with zero file overlap with the
workstream) and example-cockpit-repo.

**Consumer.** `coordinator_core/coverage.py`'s `_derive_dag_chain_set` Step 3.
For a chain-mode node whose handoff carries a `deliverable_id`, the node's
segment is the union of:

1. commits stamped with a matching `Deliverable-Id:` trailer, and
2. commits matching the node's `Session-Id:` that carry **no**
   `Deliverable-Id:` trailer at all (the legacy-history fallback).

Nodes without a `deliverable_id` keep the plain `Session-Id:`-only segment,
byte-identical to prior behaviour.

**Forward-only — read this before trusting an old chain's verdict.** Leg (2)
above means every commit made before this trailer shipped, and every commit
made since by a session/workstream that never adopted `deliverable_id`, stays
attributed exactly as it was under the old Session-Id-only rule. The fix
stops the gate from acquiring *new* false positives; it does not retroactively
re-attribute or clear old ones. An old chain's coverage verdict is no more or
less trustworthy after this trailer shipped than it was before.

**Attribution follows the work, not the typist.** A commit stamped with a
matching `Deliverable-Id:` is attributed to that workstream even when a
different session's `Session-Id:` is on the same commit — this is the
corrective the fix exists to make, not an edge case of it.

## Cross-references

- claude-klabauter `coordinator_core/ops/commit_anchors.py` — the producer: stamps
  `Resolves: <dlv-id>` at the completion event, gated on a staged `archive/completed/*.md` entry.
- claude-klabauter `coordinator_core/contract/commit-trailer-producer-contract.md` § 1.1/§ 1.2b —
  the registry entry for this key, alongside `Deliverable-Id:`'s membership-grain sibling row.
- `coordinator/docs/wiki/workstream-complete-review.md` — sibling
  `Session-Id:` trailer convention and its zero-match semantics (cited
  above).
- claude-klabauter `coordinator/bin/parse-resolves-trailer.py` — the parser this
  convention specifies.
- claude-klabauter `coordinator/bin/rollup-derive.py` — the roll-up-derivation primitive that
  consumes the parser's output alongside `check-shipped-on-main.py` (C5).
- `coordinator/docs/wiki/canonical-artifact-shapes.md` § lvv-01 — the
  stable-ID table (`hnd-`/`cmp-`/`pln-`/`dlv-` prefixes and their mint seam)
  whose IDs populate the `<artifact-id>` this trailer names, plus the
  ID-companion ancestry fields (`predecessor_id`/`origin_handoff_id`) this
  cluster added alongside the trailer.
- `coordinator/schemas/session-shape.schema.json` — `pickup.deliverable_id` /
  `pickup_history[].deliverable_id`, the source field the `Deliverable-Id:`
  trailer is stamped from.
- claude-klabauter `coordinator/bin/coordinator-prepare-commit-msg` — the
  producer of both `Session-Id:` and `Deliverable-Id:`.
- claude-klabauter `coordinator_core/coverage.py`'s `_derive_dag_chain_set` —
  the consumer of `Deliverable-Id:` for DAG-mode segment attribution.
