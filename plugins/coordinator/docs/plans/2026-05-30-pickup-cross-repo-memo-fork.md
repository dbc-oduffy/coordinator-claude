# Plan — Widen `/pickup` to treat cross-repo memos as a first-class baton

**Date:** 2026-05-30
**Author:** claude-central-em (DoE altitude)
**Scope mode:** `feature`
**Status:** Executed + committed 2026-05-30 (C1–C6; wave commits 2fb92954…e99a596c + C6 test)
**Review:** the Staff Engineer REQUIRES_CHANGES → integrated 2026-05-30
**Slug:** `pickup-cross-repo-memo-fork`

---

## Problem (PM vocabulary, falsifiable)

When the PM hands the EM a **naked cross-repo memo path as a prompt** (literally just the
filepath, no verb), the EM confabulates: it acts before reading the memo, asks the PM how to
act on a memo it hasn't read, and in the worst observed case *rewrites the memo into what it
assumed the memo should say*. Root cause: a bare artifact-path-as-prompt arrives with **no
procedure attached**, so the model improvises a frame over an unread file — the same
void-filling confabulation signature seen in the tool-output-flakiness cluster.

Memos are already first-class queryable inbound artifacts (surfaced at `/session-start` §
Outstanding cross-repo memos AND `/workday-start` Step 1.45, both via
`workday-start-cross-repo-memo-surface.sh`), with a real lifecycle (`open → actioned`,
`decision:` enum). But `/pickup` — the natural "read-this-baton-and-act" verb — is **100%
handoff-shaped** and has zero awareness of memos. A memo path handed to `/pickup` today is
misread as a handoff (Step 2 globs `tasks/handoffs/`; Step 3 mutates handoff schema
`status: active → consumed`, `deployment_state`).

Four sub-problems:

1. **No memo ingest procedure.** `/pickup` needs a form-classification fork
   (handoff / spinoff / **memo**) with **read-before-reasoning** as the first act of the memo
   branch. A memo *is* a baton from another place — you must read it to act on it — so `/pickup`
   is the right verb (PM-ratified; the alternative is inventing a second verb for a
   structurally-identical "inbound artifact with a lifecycle state").

2. **Memos don't self-declare their shape.** A new sender-declared `kind:` frontmatter field
   (proposed enum `ask | consult | fyi`) lets the pickup fork branch deterministically and lets
   surfacing prioritize (an `ask`/`consult` surfaces with urgency; an `fyi` is a quiet log line).
   This is a producer-side gap in the `cross-repo-memo` CLI worth fixing **and utilizing**.

3. **A memo-ask is a peer hypothesis, not a command.** Picking up a memo-ask means the
   receiving EM **adjudicates and owns** the disposition for *this* repo's customers/consumers —
   weighs it, may action it, may decline with a logged rationale, may propose. The sender's ask
   is a suggestion from a peer EM/DoE, not a work order. **This is the load-bearing reason the
   fork exists.** Crucially, the supporting doctrine *already exists* in
   `cross-repo-communication.md` (§ "Memo-lifecycle adjudication is EM work", § "Memo content is
   hypothesis — verify before acting") — it is simply **unreachable at the naked-path moment**
   because no procedure invokes it. The fix wires existing doctrine into the pickup procedure; it
   does not author a new stance.

4. **Receipt-as-state, not ack-memos.** The receiver marks the memo `open → actioned` in place
   (with `decision:` + note), or it ages out to `cross-repo/archive/`. The sender just looks at
   the receiver's inbox/archive — same machine, same disk — when prompted. No two-sided protocol,
   no ack-memo sent back. This already exists in the lifecycle; the plan only ensures the pickup
   memo branch *drives the flip* so the inbox doesn't drift.

---

## Doubt-check (B.0)

**Biggest uncertainty (highest-rework scope boundary):** whether memos should carry a *new*
`kind` field at all, vs. the body+title already conveying shape (cf. the wiki's own Two-Clause
Hookspec Proposal Test — "schema surface without behavioral benefit is anti-pattern"). If the
reviewer rules against a new field, Chunks C2/C3/C4 (CLI flag, schema, surfacing-priority)
collapse, leaving only C1 (pickup fork) + C5 (doctrine). **Disposition:** the PM ratified
self-declaring shape in shaping dialogue ("great callout, worth a fix *and* utilization"), so the
field is in-scope; **enum membership and required-vs-optional are the key reviewer questions**,
flagged explicitly to the Staff Engineer below. This is reviewer-tier, not a PM question — the PM already made
the product call.

**Autonomy-stance reconciliation (refines the shaping framing):** the shaping language was "ends
in a PROPOSAL, not auto-execution." Existing doctrine is more precise and I am encoding the
precise version: memo adjudication is *EM work* — the EM does **not** reflexively bounce "what
should I do?" to the PM (§ "Memo-lifecycle adjudication is EM work" forbids exactly that). So the
encoded stance is **adjudicate-and-own**, mirroring "reviewer findings: apply, don't ratify":
- Tradeoff-free ask the EM endorses → action it, mark `actioned` with `decision: accepted`.
- Genuine product/tradeoff/architectural fork → surface to PM (this is the "proposal" case).
- Disagree / wrong for this repo's consumers → `decision: declined` with a logged rationale.
"Not a command" means *weighed and owned*, not *always escalated*. This is EM application of
existing doctrine, consistent with both the PM's intent and the wiki — not a new PM decision.

**7-dim confidence:** no-duplicate ✓ (autonomy doctrine cited not duplicated; `kind` genuinely
new) · no-fabrication ✓ (every cited path/field/line read against disk) · architecture-compatible
✓ (`kind` optional + back-compat default; fork keys off path+frontmatter, both reliable;
unknown-optional-field tolerated by validator) · official-docs-read ✓ · reference-impl-seen ✓
(spinoff-roadmap `kind` enum in schema.js is the adding-a-kind-enum reference) · root-cause-known
✓ (naked-path → no-procedure → void-fill) · fix-locus discrimination ✓ (pickup=front door;
`kind`=CLI+schema producer side; autonomy=wiki cited from pickup — each at its right layer).

---

## Pinned interface — the `kind` enum (shared by C2/C3/C4/C5)

> **VERBATIM** — every chunk consumes this exact set. Do not vary.

```
kind: ask | consult | fyi
```

- **`ask`** — sender requests the receiver *do* something (action request). Surfaces with urgency.
  Receiver disposition: adjudicate-and-own (action → `decision: accepted` + `decision_note`; or
  decline → `decision: declined` + `decision_note`). Terminal: `actioned`.
- **`consult`** — sender requests the receiver's *input/opinion* (a question, not a directive).
  Surfaces with urgency. Receiver disposition: **reply-in-place** — capture the response in
  `actioned_note` directly on the memo, then mark `status: actioned`. Sender reads the response on
  the same machine. NO return-memo. Terminal: `actioned` with a substantive response captured.
  (Distinct from `ask`: the receiver is not being asked to act, only to respond. The enum value is
  load-bearing — it changes the receiver's disposition, not just the urgency label.)
- **`fyi`** — informational; no action or response expected (notification). Quiet log line.
  Receiver disposition: acknowledge only — `status: actioned` + `actioned_note: "noted —
  informational"`. No `decision` field.

  <!-- Review: the Staff Engineer F6 — enum descriptions updated to make `consult`'s reply-in-place terminal
  distinct from `ask`'s adjudicate-and-own terminal. The distinction keeps the enum non-cosmetic. -->

**Negative-spec — `ack` is NOT a `kind`.** An acknowledgement is **receipt-state** (the receiver
flipping `status: open → actioned` with `decision: accepted` + note), never a sender-declared
kind and never a return-memo. This directly serves the PM's stated goal ("stops us sending an
x-repo memo that is an acknowledgement") and is consistent with the existing wiki rule "don't
send an ack-of-ack when the inbound was a confirmation." `nudge` from the shaping list collapses
into `ask` (a nudge is a low-urgency re-ask; a separate enum value adds surface without behavior).

**Back-compat:** `kind` is **optional**; absent (all pre-2026-05-30 memos) is interpreted as
`ask` (the safe default — surfaces with urgency, never silently downgrades an unlabeled memo to
quiet `fyi`). No grandfather migration; no hard requirement that would reject existing memos.

**`kind` lockstep set (new — analogous to the four-coupled-path-declarations rule).** The `kind`
field appears in exactly these enforced sites, which must stay in lockstep:
1. CLI writer — `cross-repo-memo` `_compose_frontmatter` (emits `kind:` when `--kind` given)
2. Schema declaration — `schemas/cross-repo-memo.yaml` (`optional:` block, enum)
3. Schema validation — `bin/lib/schema.js` (memo cross-field rules, enum membership)
4. Surface parser — `workday-start-cross-repo-memo-surface.sh` (reads `kind` for priority)
Document this set in the wiki chunk (C5).

---

## Chunks (disjoint-write; fan-out candidates with the enum pinned)

All five author chunks write **disjoint files** and consume the pinned enum as a *read*
contract (not write-overlap), so they fan out in parallel; C6 verifies the round-trip at merge.

### C1 — `/pickup` form-classification fork + memo branch
**Writes:** `skills/pickup/SKILL.md` only.
- New **Step 1.5 (Classify the artifact)** before the existing handoff flow: read the artifact
  *first* (read-before-reasoning, stated explicitly as the anti-confabulation gate), then classify
  by **path + frontmatter shape** (both reliable signals already on disk):
  - `tasks/handoffs/` + handoff schema (`status: active|consumed`, `deployment_state`) → existing
    handoff flow (Steps 2–6 unchanged).
  - `cross-repo/inbox/` (or any file with memo frontmatter: `from:` + `to:` + `status: open|actioned`)
    → **new memo branch** (below).
  - `kind: spinoff` in `tasks/handoffs/` → existing spinoff banner.
- **Memo branch** (new subsection):
  1. **Read the whole memo before any other action.** Explicit STOP: do not summarize-to-PM, do
     not act, do not edit until read. (Directly targets the observed failure.)
  2. **Verify premises** — reuse the existing § "Memo content is hypothesis" discipline by
     reference (cite the wiki; do not duplicate): grep cited locus/symbol in *this* repo,
     `git fetch` + scan for concurrent action on the topic, archive-sweep for same-topic terminal
     artifacts (standdown/superseded).
  3. **Branch on `kind`** (default `ask` when absent):
     - `fyi` → acknowledge only; write `status: actioned` + `actioned_note: "noted — informational"`
       (no `decision`). Commit. No proposal.
     - `ask` → **adjudicate-and-own** per the autonomy stance (cite
       `cross-repo-communication.md` § "Memo-lifecycle adjudication is EM work"): weigh against
       this repo's customers/consumers; then either action (→ `status: actioned` + `decision: accepted`
       + `decision_note: <what was done>`) or decline (→ `status: actioned` + `decision: declined`
       + `decision_note: <rationale>`) or — only on a genuine product/tradeoff/architectural
       fork — surface to PM. Terminal: `actioned`.
     - `consult` → the sender wants INPUT, not an action. Write the response INTO the memo in
       place (capture in `actioned_note`), then mark `status: actioned`. The sender reads the
       response on the same machine — NO return-memo (consistent with receipt-as-state / no-ack-memo
       doctrine). Terminal: `actioned` with a substantive response captured.

     <!-- Review: the Staff Engineer F0 — enum collision guard: MUST write `status: actioned` (simple-model
     terminal). MUST NEVER write `status: action_taken` — that is a grandfathered-only value whose
     schema.js cross-field rule (bin/lib/schema.js:664-671) requires both `action_taken_at` AND
     `decision`. `decision` on `actioned` is an audit choice the branch makes, not a schema
     requirement. -->

     <!-- Review: the Staff Engineer F1 — pinned note-field mapping: `decision_note` is rationale alongside a
     decision; `actioned_note` is a free-text note at actioning time (zero existing writers). The
     four-case mapping above is the verbatim pin. -->

     <!-- Review: the Staff Engineer F6 — consult/ask disposition split: `consult` is reply-in-place (receiver
     captures input/response in memo), not adjudicate-and-own. Both terminals are `actioned`. The
     split keeps the `consult` enum value load-bearing rather than cosmetic. -->
  4. **Receipt-as-state:** the flip + commit IS the receipt; sender reads it on the same machine.
     No return-memo (negative-spec, cite the ack-of-ack rule).
- **No handoff-schema mutation on the memo path** — memos use `open → actioned`, not
  `active → consumed`/`deployment_state`. Explicit negative-spec so the existing Step 5 mutation
  block is not wrongly applied.
- **Argument-hint + description** update: `/pickup` now accepts a handoff *or* memo path.
- **Test surface:** SKILL.md is prose; the behavioral assertion is the round-trip in C6. Add a
  worked memo-pickup example to the skill (mirrors the existing spinoff/recovery banner examples).

### C2 — `cross-repo-memo` CLI `--kind` flag
**Writes:** `bin/cross-repo-memo`, `bin/cross-repo-memo.test.py`.
- Add `--kind {ask,consult,fyi}` argparse arg (optional, default `None` → omit field; CLI does
  **not** stamp a default so absence stays meaningful and the reader applies the `ask` default).
- `_compose_frontmatter`: emit `kind: <value>` when provided (quoted via `_yaml_quote` for
  consistency, though enum values are slug-safe).
- Help text: document the enum + the "absent = ask" reader convention + the `ack`-is-not-a-kind
  negative-spec.
- Tests: each enum value round-trips into frontmatter; omitted `--kind` emits no `kind:` line;
  invalid value rejected (exit 2, argparse `choices`).

### C3 — memo schema: `kind` enum declaration + validation
**Writes:** `schemas/cross-repo-memo.yaml`, `bin/lib/schema.js`.
- `cross-repo-memo.yaml` `optional:` block: add `kind` as `{type: enum, values: [ask, consult, fyi]}`.
- `schema.js` memo cross-field rules: validate `kind` ∈ enum **when present** (optional; absent is
  valid). Mirror the existing `decision` enum validation shape (lines ~663–700). Do **not** make
  `kind` required (no grandfather rejection of pre-2026-05-30 memos).
- Keep the existing grandfather cutoff semantics untouched.

### C4 — surfacing priority by `kind`
**Writes:** `bin/workday-start-cross-repo-memo-surface.sh`,
`bin/workday-start-cross-repo-memo-surface.test.sh`.
- Parse `kind` from frontmatter (default `ask` when absent — the reader applies the default).
- Priority ordering: `ask`/`consult` first (urgent), `fyi` last (quiet). Within a band, keep the
  existing created-date ascending sort.
- Line annotation: append `[fyi]` (quiet) vs. an urgency marker for `ask`/`consult` — exact marker
  text is an EM/reviewer call; keep it consistent with the existing `[STALE]` flag style.
- One change covers **both** `/session-start` and `/workday-start` (shared helper). State this in
  the chunk so neither surface is missed.
- Tests: a mixed inbox sorts ask/consult above fyi; an unlabeled memo (no `kind`) sorts as `ask`.

### C5 — doctrine: crystallize the pickup-time autonomy gate + document `kind`
**Writes:** `docs/wiki/cross-repo-communication.md` only.
- New § "Picking up a memo — the adjudicate-and-own gate": a short section that **points to** the
  existing § "Memo-lifecycle adjudication is EM work" and § "Memo content is hypothesis," framing
  them as the pickup-branch contract. Do **not** restate them (synthesis discipline — cite, don't
  re-author). State the calibrated stance (action tradeoff-free / decline-with-rationale / surface
  only genuine forks) and the "ask = peer hypothesis, not command" framing.
- Document the `kind` enum (membership, semantics, `ack`-is-receipt-state negative-spec, absent=ask
  default) in the § Schema block.
- Add the **`kind` lockstep set** (the 4 sites above) as a subsection mirroring § "Four coupled
  path declarations — keep in lockstep." **Criticality distinction (mandatory — document explicitly
  in the wiki):** the four path declarations are a delivery-guard SECURITY boundary (a desync
  silently drops memos — `cross-repo-communication.md:98` calls it "the worst class of failure");
  the `kind` lockstep governs surfacing PRIORITY (a desync degrades prioritization, it does NOT
  drop memos). Cross-reference the four-path rule but do not conflate or flatten the difference in
  criticality between the two lockstep sets.
  <!-- Review: the Staff Engineer F5 — criticality distinction added; the two lockstep sets differ in failure
  mode (silent drop vs. priority degradation) and must be documented as explicitly distinct even
  though they mirror each other in form. -->
- Update the § Schema `status:`/`decision:` bullets to mention `kind:` alongside.

### C6 — round-trip verification (merge gate, EM-serial)

<!-- Review: the Staff Engineer F2 — C6 split honestly into two parts with distinct claims. The original C6
only exercised C2/C3/C4 (kind plumbing), not C1 (the pickup branch — the load-bearing surface).
AC2 and AC7 are now wired to part (2), not prose-presence. -->

**C6a — kind-contract round-trip** (C2/C3/C4 contract only)
**Writes:** extend `cross-repo-memo.test.py` or a small test in the existing suite (final path is
the executor's call).
- For each `kind ∈ {ask, consult, fyi}`: CLI writes a memo → `schema.js` validates green →
  surfacing helper parses and bands it correctly. Plus: a no-`kind` memo validates green and bands
  as `ask`.
- **Claim:** proves the kind contract agrees across C2/C3/C4. Does NOT prove that the pickup baton
  path (C1 memo branch) behaves correctly — that is C6b's job.
- Binds: AC4, AC5, AC6 (the kind-plumbing ACs).

**C6b — memo-fixture behavioral assertion** (C1 pickup branch)
**Writes:** a fixture-based test (standalone file or extension of the suite — executor's call).
- A fixture memo file with `status: open` routes to the memo branch (not the handoff branch).
- The `open → actioned` flip with decision/note writes schema-green frontmatter.
- **Negative-spec assertion:** the handoff `active → consumed` / `deployment_state` mutation is
  NOT applied to the memo fixture. (This is the mechanical proof AC2 requires — a prose grep of
  SKILL.md is insufficient; the behavior must be asserted.)
- Binds: AC2 (no handoff-schema mutation) and AC7 (round-trip baton path green).

---

## Convention contact-points (per CLAUDE.md § Adding a Convention)

| Surface | Touched in |
| --- | --- |
| `/pickup` skill | C1 (memo fork + branch) |
| `cross-repo-memo` CLI | C2 (`--kind`) |
| Memo schema (yaml + schema.js) | C3 |
| Surfacing helper (`/session-start` + `/workday-start`) | C4 |
| `cross-repo-communication.md` doctrine | C5 |
| Canonical artifact agents encounter | the memo frontmatter itself (now carries `kind`) |

**No path moves / renames** → no `doc-link-checker` closeout needed. **No shared-symbol
mutation** (`kind` is additive, not a rename of an existing field) → no reverse-reference scan
beyond the lockstep set documented in C5.

**Architectural OOS — `/session-start` entry point (not a gap; a deliberate boundary):**
`/session-start` surfaces outstanding memos for awareness (via `workday-start-cross-repo-memo-surface.sh`)
but ACTING on a memo is always a `/pickup`. We will not teach two entry points the same fork —
`/session-start` surfaces, `/pickup` acts. This is an architectural boundary, not an appetite-based
deferral: two teaching surfaces for the same procedure create divergence risk and conflate surfacing
(awareness) with action (lifecycle mutation). Encode this as a cross-reference in C5 (note the
`/session-start` surface role in the wiki's pickup-gate section) rather than a new chunk.

<!-- Review: the Staff Engineer F3 — OOS note added as architectural (not appetite). The fork lives only in
/pickup; session-start is surfacing-only. Placed in § Convention contact-points per finding
instruction. -->

---

## Cross-plan coordination

Scanned `docs/plans/` for overlapping file scope and seam citations on `cross-repo-memo`,
`cross-repo/inbox`, `pickup`, and the memo schema: the active substrate traces to
`2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md` and
`2026-05-23-cross-repo-inbox-archive-restructure.md` (both shipped — this plan *extends* their
schema with an additive optional field, does not reverse them; the single-surface, no-closure-
subcommand, receiver-edits-in-place model is preserved and depended upon). No live plan claims
the `kind` field or the pickup memo-fork. No conflicts.

---

## Acceptance Criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
| --- | --- | --- | --- | --- |
| AC1 | `/pickup <memo-path>` classifies as memo (not handoff) and the skill's memo branch reads-before-reasoning | `grep:## Memo Branch@plugins/coordinator/skills/pickup/SKILL.md` | gate | realized |
| AC2 | `/pickup` never applies handoff-schema mutation (`active→consumed`) to a memo | `grep:consumed@plugins/coordinator/bin/cross-repo-memo-c6.test.py` | gate | realized |
| AC3 | Memo branch encodes adjudicate-and-own (action / decline-with-rationale / surface-only-genuine-forks), citing the wiki — not naive always-escalate | `grep:adjudicate-and-own@plugins/coordinator/skills/pickup/SKILL.md` | gate | realized |
| AC4 | CLI `--kind {ask,consult,fyi}` round-trips into frontmatter; omitted → no `kind:` line | `grep:def test_kind_ask_round_trips@plugins/coordinator/bin/cross-repo-memo.test.py` | gate | realized |
| AC5 | `schema.js` validates `kind` enum when present; absent is valid (no grandfather rejection) | `node:plugins/coordinator/bin/lib/schema.test.js` | gate | realized |
| AC6 | Surfacing bands ask/consult above fyi; unlabeled memo bands as ask; covers both session-start + workday-start | `grep:band ordering@plugins/coordinator/bin/workday-start-cross-repo-memo-surface.test.sh` | gate | realized |
| AC7 | Round-trip: memo fixture routes to memo branch; open→actioned flip with decision/note validates schema-green; handoff mutation NOT applied | `grep:test_c6a_kind_roundtrip_schema_and_band@plugins/coordinator/bin/cross-repo-memo-c6.test.py` | gate | realized |
| AC8 | `kind` lockstep set documented in wiki; `ack`-is-receipt-state negative-spec present | `grep:lockstep set@plugins/coordinator/docs/wiki/cross-repo-communication.md` | gate | realized |

<!-- AC-oracle binding note: AC5 executes (node --test). AC1/AC3/AC8 are prose/doc presence (grep is the correct mechanism). AC2/AC4/AC6/AC7 presence-bind to their test files because the acceptance-oracle's executable prefixes are pytest/node/cargo only — there is no standalone-python/bash runner prefix. Those suites (cross-repo-memo.test.py 35/35, cross-repo-memo-c6.test.py 9/9, workday-start-cross-repo-memo-surface.test.sh 21/21) were run green during execution; their EXECUTION gate is the repo's run-all-checks at /merge-to-main. Follow-up worth noting: an oracle `script:` prefix for standalone test runners would let AC2/4/6/7 bind to execution. -->
<!-- Status: all chunks C1–C6 executed + committed 2026-05-30 (2fb92954 C1, c9e650e1 C2, 6f14ec58 C3, f121a02a C4, e99a596c C5, + C6 test). -->


---

## Key reviewer questions (for the Staff Engineer / the named Opus reviewer)

1. **Enum membership (#2).** Is `ask | consult | fyi` the right set? Does `consult` earn
   distinctness from `ask`, or collapse? Is dropping `nudge`/`ack` correct? (PM ratified
   *that* memos self-declare shape; *which* values is the open call.)
2. **Required vs. optional `kind`.** Plan proposes optional + reader-default `ask`. Is a
   grandfathered-required field better for forcing senders to declare? (Tradeoff: friction vs.
   silent-default ambiguity.)
3. **Autonomy stance calibration (#3).** Is adjudicate-and-own (vs. always-propose-to-PM) the
   right encoding given the existing "memo adjudication is EM work" doctrine? Scrutinize that the
   pickup branch can't be read as "obey the sender."
4. **Scope completeness.** ~~Does the memo fork need a peer in the `validate-frontmatter-schema.js`
   PreToolUse hook (offer-shape `kind` nudge on hand-edited memos), or is CLI+schema sufficient?~~
   **RESOLVED — no hook peer needed.** `kind` is sender-declared at CLI-write and immutable
   thereafter; the only legitimate hand-edit (the receiver's `open → actioned` flip) never touches
   `kind`, so a `kind` nudge would be pure noise. C3 schema validation already rejects an
   out-of-enum `kind` if one is ever hand-introduced. CLI + schema is sufficient.
   <!-- Review: the Staff Engineer F4 — resolved in-plan per reviewer rationale. -->

---

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| AC2/AC4/AC6/AC7 oracle cells presence-bind (`grep:`) to their test files rather than executing them | the acceptance-oracle's executable prefixes are pytest/node/cargo only — there is no standalone-`python`/`bash` runner prefix. The suites DO run green (35+9 python, 21 bash, verified during execution); their execution gate is the repo's `run-all-checks` at `/merge-to-main`. Follow-up noted: an oracle `script:` prefix would let these bind to execution. | 3d4c6da2 |
| C6b's handoff-mutation-rejection asserts on `status: consumed` (enum violation), not `deployment_state` | `deployment_state` alone does not trigger memo-schema rejection — schema.js tolerates unknown optional fields (verified). The `status: consumed` enum violation is the actual rejection pivot; the combined-field case still proves the negative-spec. | f8e54eef |

> Provenance-only (not crystallized by `/distill`). The ALLOWLIST-section reality is already correct: the `kind` enum, lifecycle, and autonomy stance all shipped as planned; these two deviations are binding-mechanism nuances, not design changes.
