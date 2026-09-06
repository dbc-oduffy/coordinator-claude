# Computed-skills conversion checklist (DR-090 per-baton review)

> Spec backlinks: `docs/decisions/DR-090-the-unit-of-extraction-is-the-mechanical-step.md`;
> `coordinator/docs/wiki/computed-skills.md` § Generalizing this pattern (AC14);
> `docs/plans/2026-07-24-canonical-resolution-engine.md` chunk W1-A3 / AC-11 / AC-12.
>
> This is the discharge artifact for AC-11: every computed-skills conversion baton —
> **including convert #2 (`workstream-complete`) and every conversion after it** — is held
> against this checklist at review, not against reviewer memory of DR-090's prose. DR-090
> itself states this rule binds by review, not by a test
> (`coordinator-tripwires.md § SKILL-NARRATES-PROCEDURE`); this file is that review's
> instrument.

## How to use this

Run each item below against the converted `SKILL.md` / `agent.md` (or the diff that produced
it). An item that fails is a finding, not a style nit — DR-090 frames it as a correctness
defect (procedure invisible to every existing gate), not a preference.

## Checklist

- [ ] **Intent + a named op only.** Every mutating step states what the caller wants and names
      an existing op the engine resolves (via the settings-home bin seam, per the precedence
      ladder in `coordinator/snippets/resolve-coordinator-bin.md`: rung 0 / Shape W on a
      PowerShell host, the POSIX shapes A/B otherwise). The surface never carries a command
      payload for the EM to transcribe into a shell.
- [ ] **Zero command fences.** No fenced multi-line shell/python payload survives. Cross-ref
      `coordinator-tripwires.md § NO-MULTI-LINE-SHELL-FENCE`: a shell fence is allowed only as
      exactly one metachar-free command line; a multi-command payload belongs in a named
      claude-klabauter CLI, not pasted prose.
- [ ] **Inline-mechanism budget gate run and clean (AC-11).** Run
      `check-surface-inline-budget <converted-surface-path> <baseline-path>`, resolved per
      `coordinator/snippets/resolve-coordinator-bin.md` (rung 0 / Shape W on a PowerShell host),
      against the converted `SKILL.md`/`agent.md` — a
      WARN means a new inline mechanism (bash fence, `_cc_trusted=0` copy, narrated step, or an
      inline-backtick payload) crept back into a surface that was supposed to have been converted
      away from it. No baseline file yet for this surface is not a pass — establish one (the
      current clean count) before the conversion is reviewed done. This is the generalized
      anti-rebound successor to `check-wsc-inline-budget` (that one stays scoped to
      `workstream-complete/SKILL.md` and is unaffected by this item).
- [ ] **Zero narrated procedures.** The surface names ops; it does not narrate an ordinal step
      sequence ("stage this, then commit that"). Applies **regardless of fencing** — the unit
      of extraction is the mechanical *step*, not the mechanical *branch* (DR-090). Tells to
      scan for: an ordinal or a "then" joining two mutations in one sentence/step; an
      inline-backticked mutation (`git commit`, a write, an `mv`) inside imperative prose,
      fence or no fence. Cross-ref `coordinator-tripwires.md § SKILL-NARRATES-PROCEDURE`.
- [ ] **Zero placeholder-by-inference.** No `[choose one|placeholder]` token the model must
      resolve by inference. The op computes and owns its own arg resolution; a placeholder in
      prose is a directive the engine hasn't been given yet, not a caller's job to guess.
- [ ] **Zero call-site invariants.** The surface doesn't restate a guardrail the op should
      enforce itself (e.g. "never `git add -A`" written at the call site instead of inside the
      op). An invariant enforced at a call site is enforced at zero call sites; the same
      invariant coded inside the op is enforced every time it runs.
- [ ] **The discharge test.** For every rule the converted surface implies, name the artifact
      that discharges it — a directive, a judgment point, a gate, a test. If the honest answer
      is "the operator remembers," the conversion is not finished. Cross-ref
      `coordinator/docs/wiki/invisible-doctrine.md` (the north star this checklist serves).
- [ ] **Tutorial prose deletes, it does not relocate.** Procedure a competent model already has
      (the strip test: reduce the step to its intent — does a competent engineer need anything
      further to act on it?) is neither doctrine nor archaeology. It is cut outright, not moved
      to a wiki or DR alongside the two dispositions the frontage roadmap already names.
- [ ] **A live gate needs a directive home before the body is rewritten, or it silently
      drops.** Every mutating gate present in the source prose — not just every step —
      must have an identified `directives[]`/`judgment_points[]` home named *before* the
      rewrite pass that deletes the narrated body around it. A gate with no assigned home
      going into the rewrite does not fail loudly; it evaporates, because nothing in the
      converted body or the manifest names it as missing. Caught at `workstream-complete`
      convert #2: the Step 2.96 completeness-checklist WARN gate had no directive owner
      until the plan-coverage-checker's delta pass forced one — promoted here from
      incident to a standing checklist item so a future converter's coverage pass is a
      review-instrument check, not a rediscovery. Cross-ref
      `docs/plans/2026-07-26-workstream-complete-computed-frontage.md` C2i.
- [ ] **The completion test.** Thinner and less imperative is *evidence* a port converged,
      never the bar a port is measured against — line-count and fence-count heuristics can
      flag a candidate but can never render the verdict, and "still long" is not itself a
      finding (same-day universal lesson `state/lessons/2026-07-26-universal-thin-is-not-
      the-bar-a-long-ski-40be3485c6a5.yaml`). A skill whose judgment load is genuinely
      front-loaded and text-heavy may legitimately converge well above a shorter sibling's
      line count; a short file with a manufactured judgment_point invented to force brevity
      has FAILED this item, not passed it. What the port is actually measured against is
      the item above it and the two below it: no relocated-not-removed narration, no
      self-navigated branch table, the delivery seam exercised. A faithful transliteration
      that still reads "run this, then that" — even with every individual command now a
      clean single-line invocation — has relocated the antipattern regardless of resulting
      length.
- [ ] **Push, not pull — the skill body branches on nothing the engine resolved (realization
      #6).** Grep the converted body for classification / branch-selection vocabulary — `if
      <classification>`, "if memo", "if spinoff", "branch on", "if a peer is live", "Memo
      Branch", a prose `if …/else` — and expect it **empty**. Deterministic if/else is code in a
      markdown fence one abstraction up: it branches on facts the engine already computed, so it
      belongs in the engine, and what reaches the operator is its resolved output, never the
      branch table. The classification-appropriate adventure is *injected at fire time*, keyed on
      the material — never a section the operator scrolls to find (a pull is the rulebook defect
      intact). **Line-count of the skill body is a real success criterion, not a vanity metric.**
      A body that got *shorter* but still self-navigates a branch table has FAILED this item.
      Cross-ref `invisible-doctrine.md` § realization #6 "The adventure".
- [ ] **The delivery seam is exercised, not asserted (realization #5).** "The assembler returns
      the object" ≠ "the operator receives the adventure." Trace the wire end-to-end and
      **exercise it under a realistic full payload** — not by reading both ends and assuming they
      meet: (a) the consuming surface does not duplicate logic the compute layer resolved, and
      (b) the hook/caller actually reaches and invokes the mutation layer — not a CLI verb that
      doesn't exist yet (the silent fail-open trap). The resolved guidance must render **in the
      operator's hands as a protected segment**, never riding a first-dropped, JSON-dumped
      evidence tail that a render budget sacrifices on the exact path it exists to serve. A green
      unit test on the compute layer and a correct-looking hook are each necessary and NEITHER is
      sufficient. The pickup exemplar's delivery-seam finding is the canonical trap; cross-ref
      `invisible-doctrine.md` § realization #5 "The seam".
- [ ] **The ergonomics/discharge test (AC-12).** The canonical path is genuinely *cheaper*
      (fewer keystrokes, less thinking) than the ad-hoc path it replaces, verified at a dogfood
      gate. A technically-correct conversion that makes the right thing harder has FAILED this
      item regardless of how cleanly it passes every item above.

## Non-goals

This checklist does not re-derive the three-tier model, the census procedure, or the
eight-key schema shape — those live in `computed-skills.md` § Decision-Object Schema-of-Record
(DR-047) and § Generalizing this pattern (AC14), and are followed once per conversion, upstream
of this review. This file is the review instrument that comes *after* that build, not a
substitute for it.
