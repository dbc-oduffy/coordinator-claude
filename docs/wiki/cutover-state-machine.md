# Cutover State Machine

Purpose: document the phase-gated migration primitive that discharges the
widen/dual-write/retire safety property — *do not advance a phase until every
consumer is confirmed* — as an engine-derived gate rather than operator memory.
Spec backlink: `docs/plans/2026-07-25-cutover-state-machine.md`.

## Shipped surface

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-028 -->

Shipped: the schema, two claude-klabauter ops (`cutover.gate`, `cutover.advance`), the
hard-deny hand-edit guard, a `cutover-cli` forwarder, this wiki, and eight
cutover records. The gate derives its consumer set from the record's
executable `gate_source` at call time — never from a stored claim — and
re-verifies each `confirmed_consumers[]` entry's `verified_by` artifact
before returning a verdict (§ The derive-don't-trust rule, § Signal 2, below).

## The phase model

Every schema/vocabulary migration in this repo runs the same dance, formalized
here as a four-phase state machine on a `state/roadmap/**/cutovers/*.md`
record (`coordinator/schemas/cutover.schema.json`):

| Phase | Meaning |
|---|---|
| `reader-widen` | New readers tolerate both the old and new form; the old form is still the sole producer. |
| `dual-write` | Producers write both forms during the compat window. |
| `retiring` | Old-form producers have stopped; the consumer-visible break is imminent or underway. Gated: requires non-empty `confirmed_consumers`. |
| `retired` | The old form is fully removed. Gated: requires `gate_source` — the derivation that proved no consumer still needs it. |

Advance between phases is performable ONLY through `cutover.advance`
(claude-klabauter `coordinator_core/ops/cutover_advance.py`), which calls
`cutover.gate` internally and refuses on non-coverage. A hand-edit of `phase`
is intercepted by the `block_cutover_phase_hand_edit` write guard (below) —
there is no path from operator keystroke to phase change that skips the gate.

## The derive-don't-trust rule, and why

A gate that compares a hand-authored `confirmed_consumers` list against a
hand-authored known-consumer list discharges nothing — the operator can
under-list both, and the gate cheerfully passes. The safety property survives
only if the known set is **derived by the engine at advance time**, never read
off the record's own claim.

This is DR-084's own lesson, learned the expensive way and written down as
*"recount before applying, not before deciding."* DR-084 widened
the handoff terminal vocabulary to add `closed` + `closed_reason`. Three days
later an executor tried to close a genuinely dead baton (`roadmap-lvv-07`) and
found `archive-stamp-cli` had no verb that wrote it — the widen had shipped, a
consumer was never migrated, and nobody noticed until someone tried to use the
new vocabulary. The record was corrupted (a zero-byte-diff archive left
`status: open` on an archived handoff) and reverted in `f145480d`. The doctrine
against this failure was already written down three times before it recurred
— DR-028 (additive-then-destructive phasing), DR-029 (multi-consumer compat
windows), DR-084 itself (the worked instance) — and prose is precisely what
kept failing. The cutover primitive exists to make the rule discharge
mechanically instead of by recollection.

Concretely, `cutover.gate` (`claude-klabauter coordinator_core/ops/cutover_gate.py`)
runs a **two-way agreement test**, not a one-way subset check — subset
containment is vacuously satisfied by the empty set, so a bare
`derive(gate_source) ⊄ confirmed_consumers` predicate passes clean whenever the
derivation matches nothing. It refuses unless all hold:

1. `derive(gate_source) ≠ ∅` — an empty derived set is INDETERMINATE (exit 2 /
   HALT), never PASS.
2. `confirmed_consumers ⊆ derive(gate_source)` — a claimed consumer the
   derivation cannot re-find proves the derivation is narrower than known
   truth, a defect in `gate_source`, not evidence of coverage.
3. The derived cardinality has not shrunk since the previous advance without
   an explicit, schema-admitted `derivation_narrowed_reason` — every call
   appends `{phase, derived_count, derived_ids, at}` to the record's
   `derivation_history`, so narrowing is visible in the diff rather than
   silent.

## `closed_reason` on a memo-deliverable handoff — send the stand-down notice

<!-- spec-backlink: docs/decisions/DR-097-sibling-notification-duty-on-terminal-events.md -->

Closing a handoff into this vocabulary's `closed` + `closed_reason:` (DR-084)
is one write short of done when the handoff's own deliverable was a
cross-repo memo to a named receiver: send that receiver a stand-down notice
before treating the close as terminal, so their side doesn't keep watching
for a baton that already landed. This is the DoE→sibling direction
(claude-klabauter named per DR-097), not a fleet-wide broadcast — one receiver,
the one the deliverable was addressed to. The close itself still writes
`closed_reason:` exactly as DR-084 defines it; the notice is the one
additional step, not a replacement for it.

## `gate_source.kind` is a closed enum — the one place this wiki restates the why

Everywhere else in this primitive (`cutover.schema.json`'s `allOf`,
`cutover_gate.py`'s dispatch), the multi-modality requirement is carried as
*what* a derivation must cover — schema shape and engine implementation. This
section is the only place the *why* is restated, deliberately: a rule enforced
only in prose is re-authored per record and silently drifts, which is the
exact pattern this plan's own Problem section indicts DR-028/DR-029/DR-084 for.

`gate_source.kind` is therefore a **closed enum of engine-implemented
derivation kinds** — one member to start, `value-vocabulary` — rather than a
free-form descriptor the operator fills in per record. Each kind binds to a
fixed, engine-implemented derivation-mode set: `value-vocabulary` always
enumerates both writers *and* hardcoded-enum readers, unconditionally, because
that is what the kind IS, not an option a record author can under-select.
DR-084's own near-miss — `consumed-marker.js`'s `TERMINAL_DEPLOYMENT`, a
hardcoded-enum reader a writer-only sweep would have missed — is the concrete
case a per-record authoring choice would have reproduced inside the gate
itself. Binding the mode set to the kind converts *"the operator must
remember both modes"* into *"the operator names the shape and the engine runs
what that shape implies."* An enum of one is still a gate; a free-form string
is not.

## The two-layer gate split

Two independently necessary layers, neither sufficient alone:

- **The sanctioned advance is a registered op** (`cutover.gate` /
  `cutover.advance`) — the discharge path. `cutover.gate`
  (`@register_op("cutover.gate")`, `claude-klabauter coordinator_core/ops/cutover_gate.py`)
  is a pure, COMPUTE_ONLY, read-only derivation-and-verdict op: it re-derives
  `gate_source` at call time (never trusts the stored list), evaluates the
  two-way agreement test above, re-verifies every `confirmed_consumers[].verified_by`
  (signal 2 — below), and returns a `coverage_gate`-shaped verdict
  (`verdict_line`, `notes[]`, `exit_code`: 0 PASS, 2 REFUSE/INDETERMINATE→HALT,
  1 setup error). `cutover.advance` calls it internally and only writes the
  phase bump on PASS — no operator types frontmatter.
- **The unsanctioned hand-edit is closed by a hard-deny write guard**, not by
  the schema. A cutover record is a markdown file with frontmatter, so
  `phase: dual-write` → `phase: retiring` is a two-character `Edit`. The
  schema's `allOf if/then` blocks catch a record whose phase and
  consumer-list *shape* disagree (e.g. `retiring` with an empty
  `confirmed_consumers`) — they do NOT catch a hand-edit in general:
  `validate-frontmatter-schema.py` is warn-by-default and its deny branch is
  gated on `COORDINATOR_SCHEMA_STRICT=1`; even in strict mode, hand-flipping
  `phase` alone on a record whose `confirmed_consumers` is already non-empty
  violates no `allOf` coupling. The actual discharge is
  `claude-klabauter coordinator_core/write_guards/block_cutover_phase_hand_edit.py`
  — a hard-deny PreToolUse guard on `Write`/`Edit`/`MultiEdit` against a
  cutover record's `phase` field, modelled on `block_consumed_handoff_edit.py`,
  naming `cutover-cli advance` as the route rather than issuing a bare denial.
  **Residual, stated plainly:** write guards intercept the agent's own tool
  calls; an external editor or a shell redirect against the file still gets
  through. That residual is accepted — the guard covers the dominant
  agent-mediated path and the diff remains reviewable — but "cannot be routed
  around" overstates it; the correct claim is "the agent-mediated hand-edit
  path is closed, a residual out-of-band edit path remains and is accepted."

## Signal 2 — per-consumer re-verification, not a stored claim

`confirmed_consumers[].verified_by` is a typed, machine-recheckable reference
(`kind`: `test-node-id | probe-op-key | commit-sha`, plus a `ref` shaped to
match), never free prose. `cutover.gate` RE-VERIFIES it at every advance —
re-runs the pytest node id, re-invokes the probe op-key, or `git show`s the
commit SHA — rather than merely reading the stored claim. A `verified_by` the
gate cannot re-verify (the artifact does not exist, the test now fails, the
SHA is unreachable) is a REFUSE (INDETERMINATE), never a pass. This is the
second of two independent signals: signal 1 is the engine-authored,
sweep-shaped derivation (`gate_source` says who the consumers ARE); signal 2
is the consumer-authored, assertion-shaped verification artifact (`verified_by`
says that consumer HANDLES the new form). Two authors, two mechanisms — this
is the dual-gate rule (below) translated from schema-version drift into
vocabulary cutover.

### A sibling's bulk rename orphans `verified_by` refs silently, and INDETERMINATE is where the record then sits

Signal 2's re-verification is only as durable as the paths inside the refs, and
those paths point into a repo whose EM owes this record nothing. On 2026-07-25,
Claude-klabauter's `3e818e6b` renamed 63 `coordinator/bin/*.test.py` files to
pytest-collectable names — a good change, correctly scoped to their own tree —
and in doing so invalidated **nine** `verified_by` refs held by a single DoE-side
cutover record (`closed-reason-terminal`). Nothing on either side noticed. It
surfaced only because their EM happened to spot one stale path while answering an
unrelated question.

The reason it stayed quiet is the verdict itself. An unresolvable `verified_by`
yields INDETERMINATE, not REFUSE — and INDETERMINATE reads as *"gate ran, no
REFUSE"* to anything doing a coarse check. **That is strictly worse than a claim
the gate can check and reject:** a REFUSE is a demand for work, an INDETERMINATE
is an absence of signal wearing a verdict's clothing. Note the asymmetry that
makes it invisible from both sides — a sibling's own test suite fails loudly when
a path in its `_CONSUMERS` list stops existing, but there is no equivalent
tripwire for a DoE record's ref naming one of that sibling's files.

Two operator consequences:

- **Re-run the gate after any sibling change to a path the record's refs span** —
  a rename, a directory move, a test-module split. Re-derivation is cheap; a
  record silently un-verifiable for a week is not.
- **Fix an orphaned ref by re-confirming the successor through `confirm-consumer`,
  not by editing the ref forward in place.** A ref that does not resolve is
  evidence the confirmation needs re-doing, not a pointer worth patching. The one
  narrow exception is a pure file rename where the cited assertion is provably
  byte-identical — and even then, re-run it and re-confirm through the CLI,
  because a claim the gate cannot independently re-verify is worth nothing
  regardless of how confident its author is.

## Foreign-repo reach — fail-closed, not withheld

`gate_source.repos[]` names every repo the derivation's `paths[]` span, each
annotated `foreign: true` when the local engine cannot scan it (anything
outside DoE-claude + claude-klabauter `coordinator/bin/`). The derivation itself only
reports which repos it scanned versus which are unscanned and foreign — it
does not decide PASS/REFUSE. `cutover.gate` does: a `foreign: true` repo with
no sibling-sourced confirmation is a REFUSE with `exit_code 2`
(INDETERMINATE/HALT), never PASS. A retrofit record whose consumers live
partly in an unreachable sibling repo (example-game-repo, project-rag, ue-addon,
Cockpit) is authored anyway and expected to read INDETERMINATE — that is the
honest verdict, not a defect to paper over, pending a fleet-token-sweep
capability that would let the gate see past the reach boundary.

## Cross-repo obligations — `confirmed_consumers` vs. `cross-repo-commitments`

`state/cross-repo-commitments/*.yaml`
(`coordinator/schemas/cross-repo-commitment.schema.json`) is a populated,
already-schema-backed convention meaning *"sibling X owes us Y, durably"* —
exactly the semantics a foreign-repo `confirmed_consumers` entry needs. The
decided relationship, stated explicitly so this repo does not ship two
parallel ways to record the same sibling obligation:

- **A foreign-repo entry in `confirmed_consumers` carries an FK to a
  `cross-repo-commitment` record** (via that record's filename or `memo`
  field) rather than re-stating the obligation inline.
- **The commitment record is the sibling-sourced signal** — it is authored
  and closed by the cross-repo memo lifecycle, independent of this primitive.
- **The cutover record references it** — the cutover's `confirmed_consumers[].verified_by`
  points at the commitment as evidence a foreign consumer has confirmed, the
  same way a local entry points at a test node id or commit SHA.
- **Neither duplicates the other.** The commitment record does not gain a
  phase axis, and the cutover record does not gain its own free-form
  cross-repo-confirmation shape. This is the natural composition of signal 2
  (above) for the foreign-repo case: the sibling is the author of signal 2,
  and their own commitment record is the artifact that carries it.

## The `applies_to` double-star is load-bearing, not cosmetic

`cutover.schema.json`'s `applies_to: state/roadmap/**/cutovers/*.md` uses a
double-star between `state/roadmap/` and `cutovers/*.md`, not a single `*`.
This is a lint-enumeration concern, not a style choice: claude-klabauter's
`_lint_collect_files_for_glob` (`schema_validate.py:3211-3247`) only recurses
past the glob's fixed non-wildcard prefix when it contains `**` — the narrower
`state/roadmap/*/cutovers/*.md` form makes the batch lint sweep enumerate
**zero** cutover records, regardless of how many roadmap namespaces
(`lifecycle-vocab`, `v3split`, `owner-axis-rollout`, `cockpit-contract`, …)
each host one. A record that validates in isolation but is never enumerated
by the sweep is invisible to the exact gate this primitive exists to make
mechanical.

## Correctness fixes found by running the gate, not by reading it

<!-- spec-backlink: run 2026-08-06-14h38, nuggets c7-029, c7-045 -->

The implementation ran seven chunks beyond the authorizing plan's 24, and all
seven were correctness fixes surfaced by exercising the gate against real
records rather than by review of the code: the gate had shipped without its
own core `derived ⊆ confirmed` clause; it passed a record with only 2 of 13
consumers confirmed while still printing an agreement-holds verdict; the
derivation missed extensionless `python3` scripts (files with no `.py` suffix
that are still Python); and an exemplar pattern targeted the wrong, newly
renamed token. A fifth and sixth: the prose filter meant for frontmatter was
misapplied to fenced code-block calls, and an unclassifiable consumer was
bucketed as dead rather than as blocking. All of these were **invisible to the
45 passing tests** — the tests exercised the gate's shape, not its behavior
against the specific records it had to classify correctly. The second prose-
filter defect is itself notable: it shipped inside the very primitive built to
enforce the census property it violated, and the requirement it broke was
recorded only in a closure note, not in a place the gate's own test suite
would have caught drifting from it. The operational lesson: a gate whose job
is to prevent silent gaps needs to be run against its own worked examples
before being trusted, not just unit-tested in isolation.

## `close-handoff --reason` — the verb DR-084 needed and didn't have

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-030 -->

`close-handoff --reason` is now a landed verb, filling the vocabulary gap
DR-084 widened for but never wired a writer to. This is the concrete fix for
the exact gap the `roadmap-lvv-07` corruption (§ The derive-don't-trust rule,
above) exposed three days after DR-084 shipped: the vocabulary existed, but no
CLI verb could write `closed` + `closed_reason` for a handoff, so an executor
trying to close a genuinely dead baton had no compliant path and the record
was hand-edited into a corrupt (zero-byte-diff, still `status: open`) state
instead. `close-handoff --reason` closes that specific hole.

## Declined: a standalone symbol-caller-census tool

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-052 -->

A proposal to build a dedicated symbol-caller-census tool was declined during
the stale-bin plan repair sweep: re-deriving live consumers by hand found
**1** live caller, not the 5 assumed when the tool was proposed — too small a
surface to justify a new standalone primitive. Claude-Klabauter's `repo-census.py` is
adjacent prior art already covering similar ground. The underlying
requirement (know who currently calls a symbol before acting on it) was
folded into the cutover-state-machine's own derivation primitive
(`gate_source` / `cutover.gate`, above) instead of becoming a second,
parallel census tool — one more instance of this repo's general preference
for extending an existing schema-backed mechanism over minting a new one (see
also § Adjacent convention, below, for the same reasoning applied to
`migration-kill-list`).

## Adjacent convention — why not extend `state/migration-kill-list/`

`state/migration-kill-list/` records something that is **terminal and dead** —
a script or code path that was killed, with a `resurrect_iff` bar for bringing
it back. A cutover record tracks the opposite lifecycle facet: **active,
in-flight phase state** — a migration still moving through
reader-widen/dual-write/retiring/retired, with a live gate that can advance or
refuse it. Extending the kill-list schema to also carry phase/consumer/gate
fields would conflate a closed-book record with an open one; the kill-list's
own shape (kill reason, resurrection bar) has no notion of "not yet advanced."
A new schema-backed directory is warranted because these are genuinely
different facets of the same broader migration-doctrine, not a duplicate
convention for the same thing.

## Prior art this structuralises

- **DR-028** — additive-then-destructive phasing.
- **DR-029** — multi-consumer compat windows.
- **DR-084** — the worked instance ("recount before applying, not before
  deciding") and the live near-miss (`archive-stamp-cli`) this primitive's
  first exemplar record (`state/roadmap/lifecycle-vocab/cutovers/closed-reason-terminal.md`)
  tracks.

## Established cross-repo pattern — reader-first ordering

The gate advances the **retiring** phase — the consumer-visible break — not
the producer's widen. This follows the already-ratified reader-first rule:
`coordinator/docs/wiki/schema-version-gate.md` § Reader-first ordering and
`coordinator/docs/wiki/cross-repo-handshake-doctrine.md` establish that a
reader-first widen is a *consumer* responsibility, and that section's own
header instructs callers to reference the established pattern rather than
re-derive it. The narrower producer-emit-hold-removal /
reader-first-consumer-owned memo (`cross-repo/archive/2026-07-08-claude-klabauter-em-claude-klabauter-cockpit-v290-and-emit-hold-doctrine.md`)
is the concrete instance of the same rule this plan cites elsewhere; this wiki
is its canonical, repo-general form — the memo stays scoped to its own
producer/consumer pair, this page is where the rule lives for every future
cutover.

## Operator flow

1. Author a record under `state/roadmap/<namespace>/cutovers/*.md`: `surface`,
   starting `phase` (usually `reader-widen`), `gate_source` (kind + pattern +
   paths + repos), and any already-migrated `confirmed_consumers` with typed
   `verified_by` evidence.
2. As consumers migrate, add `confirmed_consumers` entries via
   `cutover-cli confirm-consumer` (claude-klabauter `coordinator/bin/cutover-cli`)
   rather than a hand-edit of the array — the record stays a claim under test,
   never a source of truth.
3. `cutover-cli show <record>` to inspect current phase and derivation
   history.
4. `cutover-cli advance <record> --to <phase>` to attempt the phase bump.
   Internally this calls `cutover.gate`, which re-derives, re-verifies, and
   either REFUSEs (naming the unconfirmed consumers and what would confirm
   them — design-as-offers, never a bare denial) or writes the phase bump.
   A hand-edit of `phase` in the record file itself is hard-denied by
   `block_cutover_phase_hand_edit`, which names this same `cutover-cli
   advance` route in its deny text.
5. `retiring` requires non-empty `confirmed_consumers`; `retired` additionally
   requires `gate_source` — the derivation that proved no consumer still
   needs the old form.

## The census — is this worth it?

Re-derived at pickup, per the baton's own acceptance criterion: **12 live
consumer files across ~7 distinct cutover surfaces**
(`closed-reason-terminal`, the plan/initiative/goal `abandoned`→`closed_reason`
rename, the flat-tree removal two-gate cutover, the DR-084 skill-layer/bin
`claimed_by`/`consumed_by` dual-read window, the cockpit-contract
`owner`→`repo_owner` rename, the cockpit-contract v2.7.0 `backlog_history`
reader-widen-before-emit dance, and the owner-axis vocabulary freeze/contract
publication surface) — well above the "below three, decline and stop"
threshold this baton was authorized against. The decline branch was closed at
pickup, and the retrofit (one record per surface, not per consumer file) is
the resulting scope: every distinct live surface the census found gets a
record, several surfaces already had more than one hand-rolled consumer plan
asking for the same underlying cutover.

## Cross-references

- `coordinator/docs/wiki/schema-version-gate.md` § Reader-first ordering, §
  Dual-gate requirement.
- `coordinator/docs/wiki/cross-repo-handshake-doctrine.md`.
- `docs/plans/2026-07-08-producer-emit-hold-removal-reader-first-consumer-owned.md`.
- `coordinator/docs/wiki/invisible-doctrine.md` § The discharge test.
- `docs/decisions/DR-028-cutover-phasing-additive-then-destructive.md`,
  `docs/decisions/DR-029-multi-consumer-durable-surface-compat-window-migration.md`,
  `docs/decisions/DR-084-handoff-lifecycle-vocabulary-overhaul-open-claimed-continued-closed.md`.
- `state/cross-repo-commitments/*.yaml`,
  `coordinator/schemas/cross-repo-commitment.schema.json`.
- `state/migration-kill-list/`.
- `docs/plans/2026-07-25-cutover-state-machine.md` — the authorizing plan.
