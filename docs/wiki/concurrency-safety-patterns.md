---
title: Concurrency safety patterns
created: 2026-07-12
type: doctrine
related:
  - ~/.claude/CLAUDE.md § Concurrent-EM Git Operations
  - coordinator/docs/wiki/cross-repo-fleet-contract.md (O_EXCL collision-guard prior art)
---

<!-- RAG-bait: silent-overwrite fix, O_CREAT O_EXCL retry-with-suffix, fail-loud vs fail-quiet caller
     contract, singleton-to-shard conversion, session-keyed append-only artifact, TOCTOU promoter
     ordering, disjoint-decision vs disjoint-write safety argument -->

# Concurrency Safety Patterns

This page collects reusable patterns for making multi-writer artifacts safe under concurrent access —
distinct from any single incident's fix, these are shapes worth reapplying whenever a new "two sessions
can write the same file" surface is discovered.

**Before adding a new guard to this surface, run the necessity test in
[`guard-proportionality.md`](guard-proportionality.md).** Most of what a coordination guard wants to
prevent, the layer below — git's index lock, an `O_EXCL` create, an append-only shard — already
prevents. A guard that names no failure surviving that layer, or that holds for longer than the
operation it protects, is the standing-guard antipattern rather than a concurrency pattern.

## Pattern: bounded-retry-with-suffix for terminal (non-retrying) callers

When a **terminal caller does not itself retry** on a write collision, a bare `O_CREAT|O_EXCL` guard
that fails loud on collision is the WRONG default — it silently drops the caller's data, since nothing
upstream will retry the write. Use instead:

1. `O_CREAT|O_EXCL|O_WRONLY` create attempt.
2. On `FileExistsError`, retry with an incrementing numeric suffix (e.g. `<name>-1`, `<name>-2`, ...),
   bounded (e.g. ~1000 attempts).
3. Fail-loud is reserved for retry-cap exhaustion only — not for the first collision.

**Contrast** with `cross-repo-memo`'s `O_EXCL` collision guard (`cross-repo-memo:926-938`), which CAN
fail-loud on first collision, because its caller is designed to retry (a different sender picks a new
slug and resubmits). The discriminator is the caller's own retry contract, not the artifact type: same
`O_EXCL` primitive, opposite failure posture, because the calling contexts differ.

**Under an append-only contract, prefer creation-exclusivity over replace-atomicity to close a
check-then-write race.** A lockfile, or a hardened temp-file + `os.replace` path, is the wrong
instinct when the target contract is append-only: `os.replace` SUCCEEDS on collision, which is
exactly what makes the race silent — nothing built on top of a successful replace can detect that
it silently clobbered a concurrent writer. `O_CREAT|O_EXCL` makes the collision loud instead of
silent: the `FileExistsError` IS the collision detection. Reach for creation-exclusivity first
whenever the artifact is append-only; reserve replace-atomicity for genuine singleton-overwrite
semantics where the last writer is supposed to win.


## Pattern: singleton-to-session-shard conversion for high-concurrency multi-writer artifacts

When a singleton file has enough concurrent writer surfaces that overwrite races are frequent (rule of
thumb: many distinct writer call-sites, not just "two sessions happened to collide once"), converting
the singleton to **session-keyed append-only shards** is the right fix — not a smarter lock on the
singleton. Shape: `<nanos>-<sid>` naming (mirrors `coordinator-write-review-trail.sh`), reader selects
most-recent-for-my-session.

**This is disproportionate for low-writer-count artifacts.** A file written by exactly one
writer-per-ceremony (a regenerable rollup like a `pending-release.md`-style summary) that races only in
the rare case of two ceremonies running concurrently is a **transient, non-destructive** race — treat it
as a different severity class from a permanent silent-data-loss singleton with many writer surfaces
(e.g. a project-tracker-style file with ~10 writer surfaces). For the low-writer-count case, a
render-from-structured-queue redesign (derive the rollup from an underlying append-only source at read
time) is the more proportionate fix, not shard-conversion.


## Pattern: two overlapping-scan promoters need an explicit disjoint-WRITE argument, not just disjoint-decision

When two promoters/sweepers scan the same underlying set (e.g. a crash-orphan liveness reaper and a
deliverable-shipped promoter, both scanning `consumed/in_flight` items) but make different decisions on
each item, it is tempting to assume disjoint decisions imply safety under interleaving. **They do not,
on their own** — disjoint-DECISION does not establish disjoint-WRITE safety; two promoters can both
decide to act on the same item under a race and stomp each other's write even though their *decision
logic* never overlaps.

Argue safety explicitly via:

1. **Ordering** — run the more-specific closer BEFORE the general reaper, so the general pass only ever
   sees items the specific pass has already resolved.
2. **A TOCTOU re-read-immediately-before-mutate guard** — re-check the item's current state right
   before writing, not just at scan time, so a state change between scan and write is caught rather than
   blindly overwritten.

Both must be present and stated as an explicit argument in the design — "the two promoters have
disjoint decisions" alone is not a safety proof.


## Pattern: baseline a concurrency/timing test 6+ times before attributing a failure to your change

A concurrency or timing test that fails after your change is NOT evidence of a regression until
you have re-run the **untouched baseline** enough times to characterize its own flakiness. A
3-run sample is not a baseline — it routinely passes on the pre-change version by luck, which
frames a pre-existing flaky test as your regression.

Before concluding regression-vs-flaky on any concurrency/timing test:

1. Run the untouched (pre-change) version **6+ times**, not 3.
2. Capture **every** failing case across those runs, not just the one you happened to notice —
   the failure signature tells you whether it's your change or the test's own timing window.
3. Read the failing test's own documentation: a function that documents benign duplicates
   cleaned at consumption (the T20/T22 shape) is telling you the observed dupe is expected, not
   a defect your change introduced.

The asymmetry to internalize: a passing small sample proves nothing about a timing test; a
captured failure signature across a wider sample is what discriminates. (case: 2026-07-05 —
a T20/T22 pre-existing flake nearly mis-attributed to an unrelated change on a 3-run sample.)

## Pattern: a failed batch operation is not proof it did nothing

Error-handling code often encodes an unstated assumption that a failed batch operation was
atomic — that an operation returning non-zero left nothing behind. Treat that as a claim to
test, not to reason about: `git add` on a mixed batch can partially stage some paths and then
error on a later one, so a rollback scoped to the failure handler's own "acted" list silently
does nothing when that list reports empty on ANY failure — residue exists on disk while the
bookkeeping says none does.

The general shape: when a failure branch reports "nothing happened," ask what would prove it. If
the answer is a test nobody has written, the branch is a hypothesis wearing the costume of a
fact — and it bites hardest where the residue is invisible to the very bookkeeping meant to clean
it up. A review finding phrased as "this rests on an unverified assumption" is worth converting
into a cheap empirical check rather than leaving as a comment; the ambiguity usually collapses in
one direction the first time someone runs it. (Case: a commit pipeline's rollback, scoped to a
stage helper's reported acted-set, had nothing to undo after a real `git add` partial-failure —
fixed by reconciling post-failure index state directly rather than trusting the acted-list.)

## Pattern: a fire-once sentinel needs atomic claim, not read-then-write

A per-session "only once" cap implemented as `isfile()`-check-then-`touch()` silently fires twice
when the same guard is registered on two delivery surfaces that both run concurrently: both
copies observe "not yet fired" before either writes the sentinel, and both emit. Read-then-write
is not atomic across two independent processes, however unlikely the double-registration looks.

Claim the sentinel atomically instead — `O_CREAT|O_EXCL` — and have the loser of the race
suppress its own emission. Keep non-`EEXIST` write failures emitting (an unwritable sentinel
should degrade toward over-warning, not toward permanent silence). This is the same
creation-exclusivity discipline as the pattern above, applied to a fire-once guard rather than an
append-only artifact — land the fix as a wiki pattern here; it does not authorize editing any
specific hook script from this record alone.
