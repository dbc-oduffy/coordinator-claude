---
title: Orientation-supersession layer for the install-spinoff contract
status: implemented
shipped_in: a50a394c
scope_mode: feature
created: 2026-06-01
author_session: claude-central-em
problem_set: inline (see § Problem)
source_memo: cross-repo/inbox/2026-06-01-orientation-supersession-layer.md
parent_plan: docs/plans/2026-05-30-onboarding-install-redesign.md
---

# Orientation-supersession layer for the install-spinoff contract

## Problem

The install-spinoff layer (`docs/wiki/agent-install-contract.md` § Install-spinoff layer,
shipped 2026-06-01 in `35828787`) governs **install legs**: a downstream repo seeds a
`kind: spinoff` baton carrying `install_chain_order:` into `~/.claude/tasks/handoffs/`, and the
spine-builder (`templates/handoffs/continue-onboarding-and-installation.md` Step 0) sweeps those
legs and drives each to conclusion.

There is **no orientation or supersession semantics** anywhere in the contract or the spine
template. The concrete need (from the accepted memo, `project-rag-ue-addon-em`): when a user
installs the UE addon, they should be oriented around **UE capabilities** (addon tools + engine
corpus) rather than vanilla project-rag's generic-project orientation. The addon wants to seed an
orientation baton that **supersedes** vanilla project-rag's orientation *when the addon is present*,
and the post-reboot Coordinator EM laying the spine must be able to *see and honor* that supersession.

**Restated falsifiably (B.0 doubt-check):** Today, an addon cannot express "prefer my orientation
over repo X's orientation" in any form the spine-builder reads. After this plan, an addon-seeded
baton can declare `supersedes: <orientation-id>`, and the spine-builder Step 0 will defer X's
orientation from the install-chain spine **iff** the superseding baton is present — leaving X's
orientation as the correct default when the addon is absent.

**Biggest scope-boundary uncertainty (the one the Staff Engineer resolves, not the PM):** whether orientation
warrants a *separate baton* or is an *attribute of the addon's existing install leg*. This plan
defaults to **reuse the existing spinoff frame** — the orientation assertion rides as `supersedes:`
on a `kind: spinoff` baton, no new `kind`. The plan body pins this; the Staff Engineer may push back on the
spine-builder seam. No PM-altitude uncertainty remains — the PM ratified the reuse direction this
session.

## Design direction (PM-ratified 2026-06-01 — not re-litigated here)

1. **Reuse the existing `supersedes:` / `superseded_by:` pointer *vocabulary* (the field names), not
   its terminal *semantics*.** The vocabulary is established: the handoff `status:` enum carries
   `superseded` (coordinator CLAUDE.md § Handoff Lineage), and `cross-repo-communication.md` uses
   `supersedes: <old-path>` for memo re-issue. **Precise scope of "reuse":** the schema-aware rule
   `status: superseded ⇒ superseded_by:` at `bin/lib/schema.js:708` is wired to the **memo** schema,
   NOT the handoff/baton schema — so baton-level awareness of `supersedes:` is **new**, and (per C3)
   the memo rule does NOT transfer verbatim because orientation-supersession is conditional+live, not
   terminal. We reuse the *field name* to stay idiomatic; we deliberately do NOT reuse the
   terminal-`superseded_by:` coupling. **Do NOT invent a parallel orientation-supersession
   vocabulary** — that would violate the install-spinoff layer's "no new folder, no new convention"
   ethos.

2. **No new `kind: orientation`.** An orientation assertion rides the existing `kind: spinoff` frame.
   The addon's install-leg baton (or a sibling baton it seeds) simply carries `supersedes:`.

3. **The one genuinely new surface is a spine-builder Step 0 resolution rule.** When a baton present
   in `tasks/handoffs/` declares `supersedes: <X>`, the spine-builder drops/defers `<X>`'s
   orientation from the install-chain spine in favor of the declaring baton's.

4. **Load-bearing semantic seam — conditional+live, NOT unconditional+terminal.** Existing
   supersession (memo / handoff `status: superseded`) is *terminal*: the superseded artifact is dead
   and never picked up. Orientation-supersession is *conditional+live*: vanilla project-rag
   orientation is the **correct default when the addon is absent**. Therefore the superseded
   orientation is **never stamped `status: superseded`** — that would kill it globally. Supersession
   is *asserted by the present declaring baton* and *resolved at spine-build time* (present → defer X;
   absent → X stands). This is the single distinction that prevents a naive copy of the terminal
   semantics, and it is the reason a `superseded_by:` back-pointer is NOT written on X.

5. **Coordinator stays agnostic.** It hardcodes no orientation, no addon, no order. It honors
   whatever supersession a *present* baton declares. The resolution rule is generic
   (`supersedes: <any-id>`), not UE/project-rag-specific.

## Out of scope

- **The yielding half (project-rag side).** For supersession to *take effect*, vanilla project-rag's
  orientation (`getting-started.md` three-movement tour + `mark-oriented` flow) must yield when
  superseded. `project-rag-em` owns that separately. This plan defines only the **contract convention**
  the addon and project-rag conform to — it does not edit project-rag.
- **The addon's actual orientation baton + its install/seed script.** `project-rag-ue-addon-em`
  authors that against the shape this plan ratifies (memo: "We'll plan our orientation baton against
  whatever shape you ratify").

## Substrate (verified 2026-06-01)

| Path | Role | Verified |
|---|---|---|
| `docs/wiki/agent-install-contract.md` (§ Install-spinoff layer, L361+) | Contract — gets the new convention subsection | read this session |
| `templates/handoffs/continue-onboarding-and-installation.md` (Step 0, L56–94) | Spine-builder — gets the resolution rule | read this session |
| `docs/wiki/spinoff-handoffs.md` | Spinoff/baton schema doc — documents the reused field | grep this session |
| `bin/lib/schema.js` (`CROSS_FIELD_RULES.handoff`, L491+) | Baton validator — **permissive cross-field, not strict-unknown-reject**; new `supersedes:` is accepted without a schema change | read this session |

**Key validator finding:** `validateFrontmatter` for `handoff` applies *targeted cross-field rules*
only (deployment_state/gate_dependency coupling, graph-fields-require-roadmap-kind). It does **not**
reject unknown properties. So a formal `schema.js` rule for orientation-supersession is **optional
robustness, not a prerequisite** — which is precisely the memo's own fork ("the formal-field path
matches the robustness bar… or live as an EM-readable convention"). This plan's default (C3): add
*one light, correctly-shaped* cross-field rule, because the memo explicitly asked for the install
layer's robustness bar — but the rule must encode the *conditional-live* semantic, not the
terminal-`superseded_by` shape (see C3 for why the memo rule does NOT transfer verbatim).

## Acceptance Criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|---|---|---|---|---|
| AC1 | `agent-install-contract.md` defines an orientation-supersession convention that reuses `supersedes:` and explicitly states no new `kind` is introduced | `grep: "supersedes:" docs/wiki/agent-install-contract.md` AND `grep: "no new \`kind\`\|kind: spinoff" §orientation` | gate | realized a50a394c |
| AC2 | The contract documents the conditional+live semantic (superseded orientation is the default when the declaring baton is absent; never stamped `status: superseded`) | `cited: agent-install-contract.md § orientation-supersession states "never status: superseded" + "default when absent"` | gate | realized a50a394c |
| AC3 | Spine-builder Step 0 carries the resolution rule (present baton `supersedes: X` → defer X from the spine) | `grep: "supersedes:" templates/handoffs/continue-onboarding-and-installation.md` | gate | realized a50a394c |
| AC4 | Coordinator agnosticism preserved — the resolution rule names no specific addon/orientation/order | `cited: resolution rule is generic over supersedes:<id>, no project-rag/UE literal in the rule logic` | gate | realized a50a394c |
| AC5 | Downstream conformance guidance present (how an addon seeds a baton that declares `supersedes:`) | `grep: orientation conformance step in agent-install-contract.md § Guidance for conforming repos` | gate | realized a50a394c |
| AC6 | Validator cross-field rule (`supersedes:` permitted only on `kind: spinoff`, not `spinoff-roadmap`) is present in `bin/lib/schema.js` CROSS_FIELD_RULES handoff block and encodes conditional-live, not terminal-`superseded_by` | `pytest/grep: bin/lib/schema.test.js covers the orientation supersedes: kind-gate rule` | gate | realized a50a394c |
<!-- the Director of Engineering F1: "convention-only, no schema rule" escape hatch removed — the kind-gate rule is REQUIRED. AC6 is satisfied only by the realized cross-field rule + its test. -->

## Chunks

> All four chunks write **disjoint files** and apply a convention **pinned in this plan body** (§ Design
> direction). Writes do not overlap, so they are parallelizable — but the convention must read
> coherently across all four surfaces, so a **unified seam review** (the Staff Engineer) runs across the combined
> diff, not per-chunk. EM holds the serial commit after the wave.

### C1 — Contract convention subsection (`agent-install-contract.md`)
<!-- TEMPLATE: executor adapts heading depth/anchor to the existing § Install-spinoff layer structure -->
Add a subsection under § Install-spinoff layer: **Orientation-supersession**. It MUST:
- Define that an addon-seeded `kind: spinoff` baton MAY carry `supersedes: <orientation-id>` to assert
  its orientation should be preferred over `<orientation-id>` when the baton is present.
  <!-- the Director of Engineering F2: show placeholder first so no single consumer id reads as canonical form -->
  The `supersedes:` value is an **orientation identifier** (an opaque id the superseded repo
  publishes, e.g. `<repo>-orientation` — for example `project-rag-orientation`), not a file path —
  keeping coordinator agnostic.
- State explicitly: **no new `kind`** — orientation rides the spinoff frame.
- State the conditional+live semantic verbatim-clearly: the superseded orientation is **never** marked
  `status: superseded`; it remains the correct default when the declaring baton is absent; supersession
  is resolved at spine-build time, not by a status flip or a `superseded_by:` back-pointer.
  <!-- the Director of Engineering F3: pre-reboot seeding discipline — same requirement as install legs -->
  A conforming repo MUST seed its superseding baton **before the coordinator reboot** — the same
  pre-reboot seeding discipline already required for install legs (agent-install-contract.md § Guidance
  for conforming repos, step 1) — so the declaring baton is present when the spine is laid at Step 0
  (built once per durable session).
- Cross-reference the spine-builder rule (C3 target) and the conforming-repo guidance (C2).
- **Test surface:** AC1, AC2, AC5 greps/citations.

### C2 — Downstream conformance guidance (`agent-install-contract.md` § Guidance for conforming repos)
<!-- same file as C1 → see seam note: C1 and C2 share agent-install-contract.md, so they are ONE
     executor (write-overlap), not two parallel ones. -->
Extend the existing "Guidance for conforming (downstream) repos" numbered list with the orientation
step: an addon that wants to supersede another repo's orientation seeds its baton with
`supersedes: <orientation-id>` (via `cp`/`sed`, not Write — same seeding discipline as install legs),
and publishes its own orientation as a normal spinoff leg. Reaffirm the "teach the other side in a
wiki, don't code their ceremony" split. **Test surface:** AC5.

> **C1+C2 are one executor** (shared file `agent-install-contract.md` = write-overlap). Combined remit
> ~8–10 min on one coherent surface.

### C3 — Spine-builder resolution rule + validator decision
Two disjoint targets, but one design decision (the resolution semantic), so one executor:
1. **`templates/handoffs/continue-onboarding-and-installation.md` Step 0:** after the existing
   `install_chain_order:` sweep, add the resolution pass — "for each present baton declaring
   `supersedes: <X>`, drop/defer `<X>`'s orientation from the spine; if no baton declares
   `supersedes: <X>`, `<X>` stands." Keep it generic over `<X>`; name no specific repo.
   <!-- the Director of Engineering F2: executor MUST include a greppable agnosticism comment in the resolution rule,
        mirroring agent-install-contract.md L449-450 language:
        "generic over supersedes:<any-id>; names no specific repo/orientation/order." -->
   <!-- TEMPLATE: executor writes the grep/loop in the template's existing bash-snippet style -->
2. **Validator decision (`bin/lib/schema.js`):** the kind-gate cross-field rule is **REQUIRED** —
   not optional. The rule: `supersedes:` on a handoff baton is permitted only on `kind: spinoff`
   (not `spinoff-roadmap`), mirroring the graph-fields kind-gate at `bin/lib/schema.js:516-528`
   (~8 lines in `CROSS_FIELD_RULES.handoff`). This rule lives in the handoff block (L491-634),
   **NOT** the memo block at L708 — that structural placement is itself what marks it as the
   conditional-live variant (not the terminal `status: superseded ⇒ superseded_by:` shape). The
   rule does NOT copy the memo's terminal coupling. Extend `bin/lib/schema.test.js` to cover it.
   <!-- the Director of Engineering F1: disambiguation is load-bearing at instance #1 across multiple conforming repos;
        "convention-only" escape hatch removed — the kind-gate cross-field rule is mandatory.
        Structural placement (handoff block vs memo block) disambiguates the two supersedes: uses. -->
- **Test surface:** AC3, AC4, AC6. Extend `bin/lib/schema.test.js` for the kind-gate rule.

### C4 — Spinoff schema doc note (`docs/wiki/spinoff-handoffs.md`)
Add a short note in the frontmatter-schema section: `supersedes:` is an optional field on a
`kind: spinoff` baton used by the orientation-supersession convention (cross-ref the contract). Clarify
it is **distinct** from the terminal `status: superseded` lifecycle state — `supersedes:` on a live
baton asserts a *spine-build-time preference*, it does not mark this baton or any other as dead.
- <!-- the Director of Engineering F1/F4 (folded): the disambiguation note added here MUST use the SAME two-domain contrast
     text as the schema-doc note added to docs/wiki/cross-repo-communication.md (if that note is added),
     so there is ONE canonical disambiguation, not two drifting copies.
     Canonical contrast text: "supersedes: on a memo = terminal (paired with superseded_by: +
     status: superseded, wired in CROSS_FIELD_RULES memo block); supersedes: on a live baton =
     conditional+live, spine-build-time preference (never flips status, no back-pointer, wired in
     CROSS_FIELD_RULES handoff block)."
     Executor: if docs/wiki/cross-repo-communication.md also receives a disambiguation note this wave,
     copy this exact two-sentence contrast to both surfaces and cross-reference each from the other. -->
- **Test surface:** AC2 (reinforces the conditional-live distinction in the schema doc).

## Dispatch Ledger

| dispatch # | chunk-id | one-line brief | write-files | runs | est-min | status |
|---|---|---|---|---|---|---|
| 1 | C1+C2 | Orientation-supersession convention subsection + conforming-repo guidance step | `docs/wiki/agent-install-contract.md` | parallel | 9 | committed a50a394c |
| 2 | C3 | Spine-builder Step 0 resolution rule + REQUIRED kind-gate validator rule + test | `templates/handoffs/continue-onboarding-and-installation.md`, `bin/lib/schema.js`, `bin/lib/schema.test.js` | parallel | 12 | committed a50a394c |
| 3 | C4 | Schema-doc note + identical disambiguation contrast across both wiki surfaces | `docs/wiki/spinoff-handoffs.md`, `docs/wiki/cross-repo-communication.md` | parallel | 7 | committed a50a394c |

<!-- 3 chunks = 3 dispatch rows. Disjoint write-files; convention pinned in § Design direction +
     C4 canonical contrast text (L186-189), so all three author concurrently. EM holds the serial
     commit + unified seam check after the wave (plan § Chunks blockquote). -->

## Cross-plan coordination

Scanned `docs/plans/*.md` for the substrate file paths and the new convention nouns
(`orientation-supersession`, `supersedes` on batons, `install_chain_order`).

- **`docs/plans/2026-05-30-onboarding-install-redesign.md`** (`status: implemented`) — the parent that
  shipped the install-spinoff layer this plan extends. **Relationship: additive extension, no
  conflict.** This plan adds a subsection to the contract that plan authored; it amends no assumption
  that plan's executors depend on (the `install_chain_order:` sweep is preserved, the resolution rule
  is layered after it).
- No other plan references these paths or the new convention nouns. No file-scope or seam overlap.

## Notes / coordinator-side only

The reciprocal half (project-rag's orientation yielding) is `project-rag-em`'s; the addon's baton is
`project-rag-ue-addon-em`'s. After this contract lands, the reply path to the addon EM is the
memo receipt already committed (`actioned: accepted`) — the ratified shape is then readable in
`agent-install-contract.md` on the shared machine; per `cross-repo-communication.md` no ack-of-ack
memo is sent. If the addon EM needs the shape pointed out explicitly, that is a PM-relay one-liner,
not a new memo.
