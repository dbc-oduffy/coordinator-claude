---
segment_id: plan-corpus
route: plan
class: protected
order: 880
---

- **None, and `scope_mode` is `feature`/`architecture`/`spike`** → produce the forced-articulation block before drafting tasks, surfacing its material items to the PM: **(1)** restate the problem(s) in the PM's vocabulary, falsifiably; **(2)** name your single biggest uncertainty; **(3)** flag any intent you inferred that the PM did not state.

**Un-gaming clauses for step (2)** — a yes/no "I have the shape ✓" is banned:
1. The least-certain item must be **the scope boundary whose wrong guess costs the most rework**, not merely "something you're unsure about."
2. State the **probability-weighted consequence** ("if I'm wrong about X, chunks C2–C4 are rework"). A trivial selection self-evidently fails this.
3. It must be a **PM-altitude question** (product intent, scope boundary, success criteria). Tactical uncertainties (naming, test framework, commit shape, file structure) are **disqualified as off-altitude**, not merely low-stakes — resolve them, never surface them.

## Branch C — Compose the plan body

_Condition: substrate verified. The four PM doctrinal lenses bind here: time (agent-scoped only) / refactor>patch / PM-owned YAGNI / soon=now._

- _Scope mode declared?_ (prototype | production-patch | feature | architecture | spike | spec-dispatch | audit) → Pick one before drafting. Mode shapes review depth and the evidence bar. `schemas/plan.schema.json` types the field as a free string: this list is doctrine, not validation.

- _Composing the plan body?_ → Capture the **prime exit criterion**: one sentence, in the PM's own words from plan composition, plus a `derived_from` link to the sizing object whose `intent`/`intent_source` already hold those words. No `derived_from` to cite ⇒ put the sentence in front of the PM once, at ratification. **The ordering is the mechanism:** the baseline falsifier is run and recorded BEFORE the task spine is authored. The EM does NOT hand-write the falsifier: dispatch `coordinator:exit-criterion-falsifier` (C13) with the prime exit criterion statement and NOTHING ELSE — not the ACs, not the spine — and accept or reject what it returns. Reject a report whose `## Clause coverage` names a clause no instrument covers. **What the instrument may
OBSERVE is doctrine, not the falsifier's choice: artifact state the work leaves behind — a file's
content, a field's value, a row's status, a test's result. Never process residue about the work:
commit subjects or messages, branch names, PR titles, ceremony logs.**

**If the criterion is not observable in artifact state, the CRITERION is wrong — never add a chunk
to make it observable.** Rewrite it against what the work actually produces, or accept a narrower
one you can observe.

**An artifact-state check must respect a ratified absence** — a plan may rule an artifact out of
scope (no migration, no shim, no row). **Where the plan has ratified an absence, the instrument
observes THAT — the absence is the expected state, and its appearance is the failure.** Check what
the plan decided before writing a presence assertion. Measured failure tells behind these three
rules, and the review cycle their absence cost: writing-plans.md § Prime Exit Criterion.
- _Composing exit criteria?_ -> Name the plan's own targeted tests plus its acceptance oracle; a fast/full suite going green is never the criterion. See writing-plans.md Test Surface.
- _Full-coverage check: does the task list cover the COMPLETE problem set, or only the slice fitting this session?_
  → **Consume the computed evidence.** `plan-coverage-checker`'s Lens 1 (Phase 2, Oracle-vs-Slate Cross-Reference) reports the set-difference; run it, or read its sidecar, before asserting coverage by inspection. Disposing of any gap is the EM's call.

  → **Default scope is the complete problem set — a session boundary is a scheduling constraint on execution, not a scoping input on the body.** **Partial-to-fit-one-session is the anti-pattern.** ADR, lineage and docs chunks go under `## Distill pass`, not the spine.

- _Plan will go through `coordinator:review`?_
  → The reviewer's design lens is the prime exit criterion and its falsifier delta, not a checkbox table: does the stated criterion actually falsify against the drafted spine, and does every acceptance fact resolve to either a falsifier leg or a spine row with a real disposition? No test-cell grammar, no mechanical gate.
- _Refactor-or-patch?_ → Default to refactor when AI is the implementer and the patch lands in a patch-accumulating area. If a reviewer would propose a refactor, propose it now. The verdict stays the EM's call; bring evidence: `git log -- <locus path>` and a check of `state/debt-*/` for a row already naming this locus.

- _The drafted spine carries 5+ candidate scope-cut rows?_ (disposition `backlogged`/`wont_do`, or `open` rows carrying `case_against`) — a literal count over the spine's typed disposition fields, no judgment in the count itself.
  → That volume means the plan is mis-scoped, not that each cut needs individual disposition. Stop enumerating IDs; describe the shape the cuts form, bucket them, and propose one spinoff per bucket — the `plan⇄sizing` return edge, not a push-through.

- _Writing `## Anti-scope`, or any prose about how the plan gets executed?_
  → **Name no execution vehicle.** Anti-scope binds the change; the vehicle is the executing EM's
  call at dispatch time, default a background Workflow. *"Do not fan this out"* / *"EM-sequenced,
  chunk at a time"* will be overridden, so write the real constraint instead: a shared write target
  is a `depends_on` edge on the spine, a Workflow-inexpressible shape is a named carve-out
  (`coordinator/docs/wiki/em-operating-model/workflow-orchestration.md`). Tripwire: `A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`.
- _Wave shape depends on something this plan has not established ("do X, then decide")?_
  → That is a **spike chunk before execution**, not a licence to grind chunk-at-a-time. An
  unresolved decision left in the body bounces at `/execute-plan` Phase 1.4 anyway.

- _Plan mutates a shared symbol (state enum, gameplay tag, public field, exported signature)?_ → Add a reverse-reference scan subsection listing every consumer.

- _Drafting tasks?_ → Declare `review_signals` first, from `coordinator/contract/review-signals.json` — membership is enforced by the contract's parity test plus the frontmatter write guard where a coordinator engine is installed, never by an enum here or in the schema. An absent field is a positive claim: no specialist and no external-docs surface is in play, not an oversight to fill in later.

- _Plan amends an assumption another live plan depends on?_
  → **Edit the body of every affected sibling in this same change.** (1) grep `docs/plans/` for references to the amended assumption; (2) edit each hit inline; (3) add `**Amended <YYYY-MM-DD> by <this-plan-slug>:** <one-line change>` at the top of each; (4) commit the amending plan and all edited siblings together.
- _Plan supersedes another plan or its seam?_ (declares `supersedes:`/`predecessor_plan:`, or replaces a chunk/AC wholesale — distinct from *amending*)
  → **Append `**Superseded <YYYY-MM-DD> by <this-plan-slug>:** <reason>` to the top of the superseded plan in the same commit.** This rides the sibling-amendment pass; no new automation. *Amend* = a sibling's assumption shifted in place; *supersede* = replaced wholesale. The note is a backstop, not a substitute for HEAD-drift discovery.
- _Plan retires a surface, path, flag, or mechanism some doctrine describes?_ → a spine row adds its claim to `coordinator/contract/retired-claims.json` (claim, witness, signature, legacy_sites); the guard's red list is the sweep scope. Tripwire: `RETIRED-CLAIMS-REGISTRY`.
- _Plan scaffolds a new autonomous skill / agent / command?_
  → Apply the skill-scaffold checklist before drafting: (1) destructive-action prohibition block for any write-capable autonomous skill; (2) explicit out-of-scope list; (3) spinoff-schema awareness if it can author handoffs (`kind`/`predecessor`/`deployment_state`); (4) recheck-marker semantics if it has a cadence; (5) discovery-surface integration (where does it announce itself?); (6) **platform-vocabulary collision check on the invokable name** — grep the proposed verb against the platform's command/primitive surface AND this repo's own `coordinator/commands/` and `coordinator/skills/*/SKILL.md` verbs.

- _Drafting tasks, Branch C — authoring for width?_
  → Put contracts/types/stubs/schema in an interface-first chunk in wave 0; many small disjoint
  chunks with file-level `writes`; `reads_at_head` by default, `consumes` only for real output
  consumption; critical path <= ~1/3 of dispatchable rows; width < 3 needs a `## Width rationale`
  section. Tokens `A-REFERENCE-READ-DECLARED-AS-AN-ORDERING-EDGE-SERIALISES-THE-PLAN` and
  `A-SPINE-THAT-CHAINS-EVERY-CHUNK-CANNOT-BE-SCHEDULED-WIDE`. writing-plans.md § Authoring for
  width.

- _Why write the task spine at all?_ → _See writing-plans.md § Why the Task Spine Pays Off — the Design-as-Offers Case_

---

| `plan` | **Full terminal.** Invoke `coordinator:review` immediately with a named Opus persona. Do not ask the PM whether to proceed — plan→review is the pipeline, not a checkpoint; review-or-not is gated inside `coordinator:review` Branch A.2. **XL lane:** when the plan's cited sizing object has `estimate.tshirt == XL` **AND** `xl_exit == accept_multi_session`, dispatch `plan-reviewer` and integrate it via `review-integrator` BEFORE the three pre-flights and the named Opus persona; a null `xl_exit` never fires the branch. The `plan-reviewer` dispatch brief names `docs/plans/<slug>.md` in its prompt prose, and that plan must be the **first** `docs/plans/` citation in the brief (the sidecar is keyed off the first match). Every other `plan`-route plan skips this step. **The absent-sizing-object case cannot reach this Exit** — Branch A's wall refuses Branch B without one. |

**Reviewer altitude on the `plan` route:** a named Opus persona, or no review; the XL lane above adds a Sonnet `plan-reviewer` lens ahead of the persona and never replaces it (rationale: writing-plans.md § Prime Exit Criterion).

**The full pipeline for the `plan`-route terminal:** (1) substrate verification (Branch B), (2) body composition with the four lenses (Branch C), (3) XL lane only: `plan-reviewer` → `review-integrator`, (4) `docs-checker` / `prior-art-checker` / **`plan-coverage-checker`** pre-flights via `coordinator:review`, (5) named Opus reviewer, who applies every finding in place and verifies via `review-findings-ledger verify`. A non-XL plan runs steps 1, 2, 4, 5. Skipping `coordinator:plan` skips the pipeline.

---
