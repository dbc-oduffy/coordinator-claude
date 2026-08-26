---
segment_id: plan-corpus
route: plan
class: protected
order: 880
---

- **None, and `scope_mode` is `feature`/`architecture`/`spike`** → produce the forced-articulation block before drafting tasks, surfacing its material items to the PM: **(1)** restate the problem(s) in the PM's vocabulary, falsifiably; **(2)** name your single biggest uncertainty; **(3)** flag any intent you inferred that the PM did not state.

**Un-gaming clauses for step (2)** — a yes/no "I have the shape ✓" is banned, because EM confidence couples with helpfulness and self-reports green every time:
1. The least-certain item must be **the scope boundary whose wrong guess costs the most rework**, not merely "something you're unsure about."
2. State the **probability-weighted consequence** ("if I'm wrong about X, chunks C2–C4 are rework"). A trivial selection self-evidently fails this.
3. It must be a **PM-altitude question** (product intent, scope boundary, success criteria). Tactical uncertainties (naming, test framework, commit shape, file structure) are **disqualified as off-altitude**, not merely low-stakes, however unsure you are. Resolving them is your job; surfacing them is noise.

## Branch C — Compose the plan body

_Condition: substrate verified. The four PM doctrinal lenses bind here — this is where the wrong shape gets baked in: time (agent-scoped only) / refactor>patch / PM-owned YAGNI / soon=now._

- _Scope mode declared?_ (prototype | production-patch | feature | architecture | spike | spec-dispatch | audit) → Pick one before drafting. Mode shapes review depth and the evidence bar. `schemas/plan.schema.json` types the field as a free string, so this list is doctrine, not validation.
- _Full-coverage check: does the task list cover the COMPLETE problem set, or only the slice fitting this session?_
  → **The evidence is already computed — consume it, don't eyeball it.** `plan-coverage-checker`'s Lens 1 (Phase 2, Oracle-vs-Slate Cross-Reference) already cross-references every problem-set/oracle item against the drafted spine and reports the set-difference. Run it (or read its sidecar if this pass already invoked it as a pre-flight) before asserting coverage by inspection; the EM's disposition of any gap it reports is still the judgment call below.

  → **Default scope is the complete problem set — a session boundary is a scheduling constraint on execution, not a scoping input on the body.** Planning MAY span sessions; `/handoff-for-execution` mid-plan is normal continuity, not evidence of mis-scoping. **Partial-to-fit-one-session is the anti-pattern:** a task list stopping because the session felt long enough rather than because the problem is covered.

- _Plan will go through `coordinator:review`?_
  → AC tables are OPTIONAL, in `ID | Criterion | Status` form, serving as the reviewer's design lens. No test-cell grammar, no mechanical gate.
- _Refactor-or-patch?_ → Default to refactor when AI is the implementer and the patch lands in a patch-accumulating area. If a reviewer would propose a refactor, propose it now. **The verdict stays the EM's judgment call, but bring the evidence rather than deciding cold:** `git log -- <locus path>` for the patch-accretion history at the fix locus, and a check of `state/debt-*/` for any existing row already naming this locus. Absence of a debt row is itself signal, not silence to fill in — a busy `git log` with no debt row means the pattern was never named, not that it doesn't exist.

- _The drafted spine carries 5+ candidate scope-cut rows?_ (disposition `backlogged`/`wont_do`, or `open` rows carrying `case_against`) — a literal count over the spine's typed disposition fields, no judgment in the count itself.
  → That volume means the plan is mis-scoped, not that each cut needs individual disposition. Stop enumerating IDs; describe the shape the cuts form, bucket them, and propose one spinoff per bucket. Same move as the `plan⇄sizing` return edge: a plan discovering mid-draft that its scope was mis-read routes back to re-scoping rather than pushing through.

- _Writing `## Anti-scope`, or any prose about how the plan gets executed?_
  → **Name no execution vehicle.** Anti-scope binds the change; the vehicle is the executing EM's
  call at dispatch time, default a background Workflow. *"Do not fan this out"* / *"EM-sequenced,
  chunk at a time"* will be overridden, so write the real constraint instead: a shared write target
  is a `depends_on` edge on the spine, a Workflow-inexpressible shape is a named carve-out
  (`docs/wiki/workflow-orchestration.md`). Tripwire: `A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`.
- _Wave shape depends on something this plan has not established ("do X, then decide")?_
  → That is a **spike chunk before execution**, not a licence to grind chunk-at-a-time. An
  unresolved decision left in the body bounces at `/execute-plan` Phase 1.4 anyway.

- _Plan mutates a shared symbol (state enum, gameplay tag, public field, exported signature)?_ → Add a reverse-reference scan subsection listing every consumer.

- _Drafting tasks?_ → Declare `review_signals` first, from `coordinator/contract/review-signals.json` — membership is enforced by the contract's parity test plus the frontmatter write guard where a coordinator engine is installed, never by an enum here or in the schema. An absent field is a positive claim: no specialist and no external-docs surface is in play, not an oversight to fill in later.

- _Plan amends an assumption another live plan depends on?_
  → **Edit the body of every affected sibling in this same change.** (1) grep `docs/plans/` for references to the amended assumption; (2) edit each hit inline so the assumption matches the new shape; (3) add `**Amended <YYYY-MM-DD> by <this-plan-slug>:** <one-line change>` at the top of each; (4) commit the amending plan and all edited siblings together. Silent drift is the failure mode — a sibling still citing the old shape gets dispatched against stale substrate.
- _Plan supersedes another plan or its seam?_ (declares `supersedes:`/`predecessor_plan:`, or replaces a chunk/AC wholesale — distinct from *amending*)
  → **Append `**Superseded <YYYY-MM-DD> by <this-plan-slug>:** <reason>` to the top of the superseded plan in the same commit.** This rides the sibling-amendment pass; no new automation. The distinct token is deliberate: *amend* = a sibling's assumption shifted in place; *supersede* = the plan/seam is replaced wholesale. The note is a **backstop** the original session sees at next `/workstream-start`; it does not replace same-session HEAD-drift discovery.
- _Plan scaffolds a new autonomous skill / agent / command?_
  → Apply the skill-scaffold checklist before drafting: (1) destructive-action prohibition block for any write-capable autonomous skill; (2) explicit out-of-scope list; (3) spinoff-schema awareness if it can author handoffs (`kind`/`predecessor`/`deployment_state`); (4) recheck-marker semantics if it has a cadence; (5) discovery-surface integration (where does it announce itself?); (6) **platform-vocabulary collision check on the invokable name** — grep the proposed verb against the platform's command/primitive surface, since a collision forces a confusing skill→methodology demotion later.

- _Downstream renderer needs to jump to a chunk by id?_
  → **Contract, not yet wired to an emitter:** a sidecar `docs/plans/<slug>.chunk-index.json` mapping `{chunk_id: {heading, line_start, line_end}}` per `### C<n> — <title>` heading, in document order. The emission point is `scaffold-plan`'s write-time commit, which lives in the control-plane, and this has not landed there. Until it does, do not hand-roll the sidecar — treat chunk-id jump-to as heading-anchor-only and cite this row when the emitter work is picked up.

---

| `plan` | **Full terminal.** Invoke `coordinator:review` immediately with a named Opus persona. Do not ask the PM whether to proceed — plan→review is the pipeline, not a checkpoint; review-or-not is gated inside `coordinator:review` Branch A.2. **The absent-sizing-object case cannot reach this Exit** — Branch A's wall refuses Branch B without one, so every plan here carries one by construction. Arriving with none cited is a diagnosis, not a state this table handles: the trampoline was bypassed upstream. |

**Reviewer altitude is binary: named Opus persona, or no review.** Plan review is an Opus-persona judgment task (the Staff Engineer / the Game Dev Reviewer / the Director of Engineering / the Data Science Reviewer / the Front-End Reviewer / the UX Reviewer). There is no Sonnet-tier plan reviewer, and `code-reviewer` is not one — it is the Sonnet **diff** reviewer, scoped to weak tests, dead code, unclear naming, and correctness/security on a frozen diff. Reaching for it because "the Staff Engineer feels heavy for this plan" is the failure mode this prevents. The fork: plan merits review → named persona; it does not → skip review, implement, let `code-reviewer` catch the diff. The M rung still gets a named-persona review. **The light terminal is an instance of "no review", not a third reviewer tier — the fork stays two-valued.**

**The full pipeline for the `plan`-route terminal:** (1) substrate verification (Branch B), (2) body composition with the four lenses (Branch C), (3) `docs-checker` / `prior-art-checker` / **`plan-coverage-checker`** pre-flights via `coordinator:review`, (4) named Opus reviewer, (5) review-integrator. Skipping `coordinator:plan` skips the pipeline; *"I'll just write the plan and skip review"*, *"let me ask first before invoking review"*, and *"I'll send this to `code-reviewer` instead of the Staff Engineer"* are the three failure modes this skill exists to prevent.

---
