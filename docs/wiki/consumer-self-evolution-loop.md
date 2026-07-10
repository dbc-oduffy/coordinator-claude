<!-- RAG-bait: consumer self-evolution loop, learn-lessons local mode, downstream install, fleet-private improvement queue, dogfooding blindness, $GIT_ROOT/state resolution, no ~/.claude writes -->

# Consumer Self-Evolution Loop

> How a **downstream consumer** of `coordinator-claude` (a marketplace / byte-copy install that is NOT
> the DoE meta-repo) gets a working self-improvement loop on their own installed copy — entirely within
> their own repo, with zero dependency on DoE's central machinery — and why that loop is deliberately
> one-directional (their lessons never reach us).

This page states, for a consumer reading their own installed copy, three things that are true today and
are **not** open questions: (a) `learn-lessons` local mode works out of the box against their own
`state/`; (b) that gives them a genuine self-evolution loop; (c) DoE's central improvement queue is
fleet-private, does not ship to them, is not readable by them, and their local lessons will never reach
DoE. The last point is a PM-ratified accepted asymmetry (decision P-B, `state/roadmap/v3split/OVERVIEW.md`
§ "PM decisions banked"), handled by periodic release discipline — **not** a feedback channel.
<!-- Review: code-reviewer — P-B is stated under "PM decisions banked", not "Cluster 3b" (which only
     references it: "This aligns with P-B"). -->

## The loop a consumer already has

A consumer's self-evolution loop is: **capture → local promotion → local doctrine edits**, all against
their own repo's `state/` and their own installed plugin copy. Nothing routes off-machine; nothing
touches `~/.claude/state`; nothing depends on DoE or example-orchestration-hub being present.

- **Capture** — `coordinator-lesson-add` writes each lesson to `state/lessons/*.yaml` under the
  consumer's own git root.
- **Local promotion / routing** — `coordinator:learn-lessons` in **local mode** (the default when cwd is
  any repo other than the meta-repo — `skills/learn-lessons/SKILL.md:52`) classifies each `state/lessons/`
  entry and applies it in-place: `wiki-append`/`wiki-new` edits to the consumer's own `docs/wiki/`,
  `discard` to their own `archive/lessons-archived/`, `improvement-queue` appends to their own
  `state/improvement-queue/`, and the Phase 4.5 age-sweep bounds their own lessons file.
- **Local doctrine edits** — "helping the consumer evolve their own setup" is not a separate mechanism:
  routing a lesson to a `wiki-*` change literally edits the consumer's own installed doctrine surfaces.
  The same loop that evolves DoE's doctrine evolves theirs — just pointed at their disk.

The consumer runs `/coordinator:learn-lessons` from their own repo; local mode is auto-detected; no
`--central` gate, no PM cross-repo promotion, no example-orchestration-hub. That is the whole loop, and it is already built.

## Why it stays local — the resolution proof

Every write on the consumer-local path resolves to `$GIT_ROOT/state/` (the consumer's own repo), never
`~/.claude` and never example-orchestration-hub. This is enforced by a single discriminator repeated across the three seams:
**the `~/.claude`/example-orchestration-hub routing branch fires only when the current git root IS the meta-repo.** A
consumer is never the meta-repo, so that branch is dead code for them.

| Seam | Meta-repo branch (does NOT fire for a consumer) | Consumer (sibling-repo) branch |
|------|-------------------------------------------------|-------------------------------|
| `coordinator_state_root` (no `--central`, Rule 5) | meta-repo → example-orchestration-hub state | **`$GIT_ROOT/state`** — `lib/coordinator-state-root.sh:276-283` |
| `coordinator-queue-append._output_path` | `_same_path(git_root, home)` → example-orchestration-hub | **`git_root/<output_dir>`** — `bin/coordinator-queue-append:642-654` |
| `coordinator-lesson-add._lessons_dir` (dedup scan)† | `_same_path(root, home)` → example-orchestration-hub | **`root/state/lessons`** — `bin/coordinator-lesson-add:160-181` |

† Row 3 is a *derived read-side mirror* of row 2's write-path guard, not an independent third
enforcement point — kept in sync with `coordinator-queue-append` by convention, not shared code
(`bin/coordinator-lesson-add:141-143`: "Mirrors queue-append._output_path else-branch … so the
dedup scan looks where queue-append actually writes"). Rows 1 and 2 are genuine independent guards.
<!-- Review: code-reviewer — table presented all three rows as parallel/equally-weighted seams;
     row 3 is a dependent dedup pre-check mirroring row 2's authoritative write-path guard. -->

Local-mode `learn-lessons` scratch is repo-relative too: extraction writes to `tasks/learn-lessons-<date>/`
under the consumer's own root (`skills/learn-lessons/SKILL.md:226-233`), and the discard/age-sweep archive
is `archive/lessons-archived/YYYY-MM.md` "within each repo where local mode runs". The `~/.claude/tasks/…`
and `~/.claude/archive/…` paths elsewhere in that skill are all **central-mode** sections, which run *from*
`~/.claude` — cwd-relative `tasks/` there resolves to `~/.claude/tasks/` only because the meta-repo IS the
cwd, not because local mode ever targets `~/.claude`.

**Grep-verified negative** (grep the three scripts for `CLAUDE_HOME`/`EXAMPLE_ORCHESTRATION_HUB_ROOT`/`~/.claude` write targets:
every hit sits inside the `_same_path`/`coordinator_is_meta_repo` meta-repo branch): no `~/.claude`/`CLAUDE_HOME`/
example-orchestration-hub write target on the consumer-local capture→route path is reachable without the `_same_path(git_root, home)`
meta-repo guard being true. For a consumer that guard is always false.
<!-- Review: code-reviewer — "grep-verified" was asserted with no reproducible verification trail; added
     the actual verification clause so the claim is auditable. -->

This is the SSOT taxonomy's row for per-repo work state
(`state-placement-law.md:37`): "Only when `$GIT_ROOT` IS the meta-repo (`~/.claude`) does per-repo state
redirect to example-orchestration-hub."

## The fleet-private boundary (stated, not implied)

DoE's central improvement machinery is **fleet-private**. It does not ship to consumers, is not readable
by them, and consumers must not expect their local lessons to ever reach DoE.

- **`state/lessons-outbox/` and the central improvement queue
  (`$(coordinator_state_root --central)/improvement-queue/`) are DoE-internal.** The central `learn-lessons`
  drain (Phase 2.6, Phase 0.5 dedupe) is a **central-mode-only** operation, PM-invoked from `~/.claude`,
  that enumerates peer repos from *this machine's* `machine-local` registry
  (`skills/learn-lessons/SKILL.md:240-262`). It has no concept of a remote/other-operator machine. A
  consumer's `state/lessons/` is never visible to a DoE-run drain unless the consumer's disk is literally a
  machine DoE already scans.
- **There is no phone-home.** `coordinator-lesson-promote`'s only write target is a *local*
  `state/lessons-outbox/` directory, left uncommitted so a human/EM notices it in `git status` and drains it
  via a same-machine, pull-based central run. There is no push, no upload, no network call anywhere on the
  lesson path — in the bash CLI or its example-orchestration-hub-native port. For a consumer, an outbox entry (if they ever
  produce one) simply sits in their own repo forever; it is not a channel back to us.
- **The dogfooding-blindness gap is accepted, by design.** Publishing `coordinator-claude` downstream
  severs the loop: a consumer's lessons accumulate locally but never reach DoE's doctrine-evolution cycle,
  and DoE's doctrine improvements reach them only on the next marketplace/percolate release. This asymmetry
  is a **PM-ratified accepted cost** (decision P-B), handled by **release discipline** — DoE periodically
  cuts a fresh coordinator build and runs as a consumer — **not** by any feedback/telemetry/upload channel.
  A back-channel from consumer lessons to DoE was explicitly considered and **dropped** (option (d) in
  `state/roadmap/v3split/research-corpus/consumer-machinery-delivery.md`). It is out of scope, not a
  missing feature.

## Negative-spec

- This is not the **example-orchestration-hub-invoked delivery seam** (Cluster 3b-seam) — that is a separate, DEFERred
  deliverable gated on example-orchestration-hub maturity. Nothing here percolates `cc_invoke.py`,
  `coordinator_state_root`'s example-orchestration-hub-routing branches, or `_cc_route` into the OSS copy.
- The fleet-private central queue is **not** to be shipped, exposed, or wired to consumers in any form.
- No feedback / telemetry / upload channel from consumer lessons back to DoE. Dogfooding-blindness is the
  accepted asymmetry, closed only by release discipline.

## Related

- `skills/learn-lessons/SKILL.md` — the loop's implementation; local mode is the consumer-facing subset.
- `docs/wiki/state-placement-law.md` § Taxonomy — the SSOT for per-repo vs central/fleet-private state.
- `docs/wiki/learn-lessons-routing.md` — change-kind enum and local-mode auto-apply bounds.
- `state/roadmap/v3split/research-corpus/consumer-machinery-delivery.md` — the research corpus (Finding 1
  how the machinery works, Finding 3 the confirmed closed-system blindness gap, option (c) this loop, option
  (d) the dropped back-channel).
