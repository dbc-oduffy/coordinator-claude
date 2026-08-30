---
name: plan
description: "Invoke on any planning trigger from the PM — \"plan\", \"break this down\" — for decision-weight work: multi-file, abstraction, cross-system, agent scaffold, reversed prior. Invoke coordinator:sizing first if unsized."
description-budget: 260
version: 1.0.0
prerequisite:
  - agent:prior-art-checker
  - skill:coordinator:review
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# coordinator:plan

<!-- Purpose: Decision-tree router for plan-writing — triage, substrate verification, four-lens composition, pre-dispatch handoff to coordinator:review, mid-plan friction. Per-row predicate classification (engine-computable vs. genuinely-EM-judgment vs. untrusted-gate), with file:line evidence: state/audits/2026-08-08-plan-skill-predicate-classification.md — read that before proposing a new automation, don't re-sweep this file. Unconverted predicates get an engine-side producer via the `plan-assemble` contract chunk, never a hand-rolled router here. A plan-router may never auto-resolve a triage exit classified untrusted-gate (PM intent, a sender's memo prose) — that evidence originates outside this engine by design. Reviewer-routing tables belong to staff-session, not here. Rationale and category detail: wiki. -->

**Trigger:** EM is about to plan implementation work carrying decision weight (multi-file, new abstraction, cross-system, scaffolds new agents/skills, reverses a prior decision) OR the PM typed *"write a plan"*, *"break this down"*, *"plan the implementation"*.

**When NOT to use:** Trivial work (single-file fix, typo, link repoint, no abstraction) → just do it. Implementation-only ambiguity mid-coding → harness Plan tool inline. Architectural-tier (cross-system irreversible, multi-stakeholder) → surface to PM first. PM in exploration mode or problem-shape unconverged → `coordinator:shape` (Branch A). Spec vague or multi-subsystem → `coordinator:brainstorming`. Writing a SKILL.md → `plugin-dev:skill-development`. Plan written and needs review → `coordinator:review`. Stuck pattern → Branch E.

**A new skill/agent scaffold is Branch B, not architectural-tier.** *"Novel"*, *"new surface"*, *"be careful"*, *"this is unfamiliar"* are conservative-bias tells. Architectural-tier requires one of four positive criteria: cross-system-irreversible, multi-stakeholder, security/privacy boundary, naming-collision-with-product-policy. If you cannot name which fires, it is not architectural.

Route is resolved by the caller/engine before this skill loads (Branch A). The route-specific procedure detail below this point — Branch B substrate verification, Branch C composition lenses, Exit terminal specifics, Branch D drift handling, Branch E friction — is retrieved by the `plan-assemble brief` op, which reads the segment set scoped to the resolved route. Segment content: `coordinator/skills/plan/residue/`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## Branch A — Triage: should I plan, and at what altitude?

_Condition: a planning trigger has arrived; decide whether a plan doc is the right artifact._

- _An incoming sizing-object is present?_ (`coordinator:sizing` resolved this ask and handed a `state/sizings/<id>.yaml`, or the EM is picking up a sizing-routed baton citing one)
  → **Conform, don't gate — skip the rest of triage — but conform per the object's actual `route`.** The D5 shape-entry gate still wins over whatever base route the object carries — wiki § Shape-is-a-conditional-room, not this file.
  → **Arrival split, for `route: plan` and `route: spec-dispatch` alike.** **Fresh inbound** (the lobby resolved this ask for the first time, or the baton cites an object not yet conformed against this pass) → cite the object's `intent` (verbatim), `estimate`, and `appetite` when present (optional, usually absent — never block or backfill on it) in B.0's restatement, then proceed to **Branch B**. An unanswered post-size prompt does not gate plan authoring and is not re-asked here or at the execution gate. **Via the return edge** (Branch B's verified-scope-collapse row re-invoked sizing this pass) → conform identically but resume at **Branch C**, since Branch B already ran all-green — re-running wastes it and lets the collapse row fire twice.
  → **`route: spec-dispatch` is the S lane:** set `scope_mode: spec-dispatch`; the Exit resolves its light terminal. **OWES** full Branch B substrate verification, B.0's proportional doubt-check, the concurrent-session pre-flight, the cross-plan conflict scan, and both `scaffold-plan` invocation points. **SKIPS** Branch C's four-lens composition (an S-lane body is four parts: problem sentence, file scope, acceptance criteria, test surface) and the Opus plan review — the rest of Branch C runs at S-lane weight. **NEVER skips** scoped-commit discipline or ask-before-external-action.
  → **`route: shape` / `roadmap` / `pm-decision`** → **plan is not the room.** Do not enter Branch B; route to `coordinator:shape` or `coordinator:roadmap-planning`, or surface the choice. The engine sets `pm_decision_pending` and never auto-selects — the PM's pick lands in `xl_exit`, and a null `xl_exit` never means accept. `split` is retired: an ask decomposing into independently shippable pieces is `roadmap`. Preconditions: **`shape`** — JTBD unstated, or you cannot falsifiably restate the problem in the PM's vocabulary; **`roadmap`** — spans ≥2 workstreams, or carries/needs an initiative/goal FK; **`accept_multi_session`** — neither holds **and** the PM explicitly assented (`xl_exit: accept_multi_session`).
  → **plan requires a sizing-object and trampolines back without one — this is a wall, not a courtesy.** The do-not-build-a-wall anti-scope ruling is lifted for `plan` alone; it still governs `shape`, `roadmap-planning`, and `goal-setting` unchanged. Do not soften it back.
  → **What the machine actually enforces.** `scaffold-plan --sizing-object` refuses an unresolvable path; `assert-plan-sizing-citation` sweeps frontmatter only, never body prose. Neither catches ABSENCE — an omitted flag writes clean, and a body-only citation is invisible to both. Only the trampoline covers absence, as EM behaviour. Cite the wall as a rule that binds you, never a mechanism that would have caught you.
- _No sizing-object, and this ask has not been through the lobby — **whatever its provenance**?_
  → **STOP. Do not enter Branch B. Invoke `coordinator:sizing` directly** — never ask permission to size, never offer sizing as a question. On return, re-enter Branch A; the conform detent fires because an object now exists, so this row fires **at most once per invocation**. All six routes: **`plan`** → conform, Branch B as fresh inbound; **`spec-dispatch`** → conform, Branch B at S-lane weight; **`dispatch`** → plan is not the room; abandon the pass and dispatch directly (clean by construction — `scaffold-plan` runs at Exit, so nothing is scaffolded yet); **`shape`/`roadmap`** → the named room; **`pm-decision`** → surface the offered exits. **Termination:** sizing always writes an object before returning, so re-entry lands on the conform detent, never back here.
  - **Anti-gaming clause.** Satisfied only by **an artifact on disk in `state/sizings/` citing this ask** — not by already holding file:line substrate, not by silently concluding the work is plan-tier in your head, not by asking *"want me to plan that?"*.
  - **Provenance-blind, not just PM-direct-blind.** A picked-up cross-repo memo's `ask` is novel work in THIS repo, sized against the *sender's* substrate — it needs the lobby too. The trampoline fires for it.
  - **Carve-outs — exactly two, no more.** (1) A continuation is exempt only if its baton **cites** work already routed: a resolving `sizing_object`, or a plan — via `origin_plan_id`/`plan_ids`, or via a `deliverable_id` some plan on disk carries, the ordinary mid-execution baton's only link back. Every citation must resolve; an unresolvable one is a broken pointer, not a size — never re-litigate a resolved citation, and never audit a baton for one you were not handed. A baton citing none is unsized whatever its provenance — a spinoff mints its own fresh `deliverable_id`, naming only itself — and the trampoline fires. Tripwire: `A-BATON-IS-NOT-A-SIZING-ARTIFACT`. (2) The express lane is not a plan-side carve-out — PM ruling: *"just do it doesn't make it to planning anyway. that's an exit for the sizing lobby."* Such an ask never reaches `plan`.
- _Trivial?_ (single-file change, no new abstraction, scope obvious)
  → Just do it. No plan doc. _See `${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Plan and Hand Off._
- _Implementation-only ambiguity?_ (choosing between two valid shapes mid-typing)
  → Harness Plan tool inline. No plan doc.
- _PM has set a session axiom?_ (*"we are going to do X"* / *"build Z this session"* — a directive naming the work, not a question about it)
  → Disposition flips to **plan**, not brainstorm: the PM has chosen scope, and your job is to plan the named work, not re-litigate it. Continue to **Branch B**. The architectural-tier check still fires — an axiom does not override an architectural surface-to-PM. **This row disposes; it does not admit.** An axiom carries no exemption from the sizing wall: with no object on disk the trampoline row above fires first — it is provenance-blind by design — and re-entry lands on the conform detent.
- _Trigger arrived via a PM-handed pickup whose handoff prescribes a plan?_
  → **Already authorized — do NOT ask "want me to plan?".** A handoff is PM-authored, so an embedded plan trigger satisfies the `/plan` keyword-gate transitively. A T3 spinoff *fork* stays separately PM-gated (surface it as a one-line candidate) but must not block or be conflated with the plan. Continue to **Branch B**.
- _PM in exploration mode, OR problem-shape unconverged, OR the EM detects it is guessing at the problem?_
  → Propose `coordinator:shape` **before** committing to plan; its exit gate chains back here. This is the seam where premature convergence happens. **Precedence:** a PM session axiom and the architectural-tier check both win — `/shape` is the exploration branch, not an override of a directive to plan named work. _Discriminator:_ the PM HAS a problem and wants confirmation you understood it → `shape`; the PM does not know what to build at all → `brainstorming`.
- _Cross-repo work whose shared contract is itself the unknown, even when a handoff says "ready to execute" / "XS"?_ (negotiated co-design — the contract/hookspec/shared fixture takes round-trips to converge, not a single well-understood ask the sibling implements on their own surface)
  → **Invoke `coordinator:plan` anyway — do NOT execute off the handoff's t-shirt.** Handoff sizing runs systematically low here: investigation reveals the *structural* problem, planning reveals the *implementation blast radius* (N repos, M reviewers, contract fixtures still converging). Continue to **Branch B**.
  - **The existence of a sibling is not the trigger — negotiated co-design is.** A *memo* (one ask, the sibling implements it on their own surface) does not escalate here — it is a `blocked_by`/`awaiting_gate` fact, not coordination cost. If you cannot name the coordinating party and the shared contract still being negotiated, this row has not fired.
- _Non-trivial (default for everything else)?_ (multi-file, new abstraction, cross-system, scaffolds an agent/skill, reverses prior teardown, touches shared schema)
  → Continue to **Branch B**, and scope the eventual task list to the COMPLETE problem set.
- _Architectural-tier?_ (the four positive criteria above)
  → Surface to PM: *"this looks architectural — propose `/staff-session`, want me to draft the brief?"* Wait for PM.

---

**Known boundary:** this floor protects the plan path only — work mis-triaged as trivial at Branch A bypasses `/shape` and the doubt-check. Mitigation is EM alertness at that row, not a second doubt-check.

## Exit — Route-Selected Terminal

_Condition: body drafted and saved to `docs/plans/YYYY-MM-DD-<slug>.md`. Which terminal fires is selected by the inbound sizing route. `shape`/`roadmap`/`pm-decision` never reach here — Branch A diverted them before Branch B._

**The plan file MUST be produced and committed via `scaffold-plan`, not hand-authored.** It owns frontmatter-skeleton emission and the write-time commit as one named unit spanning two invocation points either side of body authoring. This holds for every terminal; only what follows the commit differs by route.

**Invocation point 1 — scaffold.** The generator is the single emission point for frontmatter — never hand-author field lists against `schemas/plan.schema.json`. If frontmatter was hand-authored, conform it now through the same invocation.

Invoke through the `.cmd` sibling by absolute path via the PowerShell call operator (Shape W) —
ladder and shapes: `snippets/resolve-coordinator-bin.md`.

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-doc-new.exe" --type plan --title "<title>" --sizing-object state/sizings/<the-object-that-routed-you-here>.yaml --out docs/plans/YYYY-MM-DD-<slug>.md`

**Pass `--sizing-object` — mandatory to the tool, not merely to you.** `coordinator-doc-new --type plan` hard-refuses without an explicit `--sizing-object`/`--no-sizing-object`, exit 1, nothing written. Branch A refused you entry without a sizing object, so you hold its path. The flag also writes the reverse edge onto the cited sizing (plan FK plus status flip, same transaction) — omit it and the sizing never learns it was routed.

`Read` the scaffolded file before authoring the body — `coordinator-doc-new` writes it via Bash, so the first `Write`/`Edit` bounces until it is read once.

**Invocation point 2 — commit.** Commit the moment the body is saved, *then* proceed to review, per
`snippets/scoped-commit-route.md` — pathspec exactly `docs/plans/<slug>.md`, subject
`plan(<slug>): draft`. Scope stays to the single plan doc, never a sweep commit. Distinct from the review-integrator's commit-after-integrate discipline.

---

## Test Surface

**No runtime test for this skill body** — prose-doctrine, not executable code. The applicable automated check is skill-body lint / frontmatter validation; the grep-asserts below stand in for a test harness, each a single `grep -c` against the named file.

| # | token | file | expect | threshold reason |
|---|---|---|---|---|
| 1 | `Eighth dimension` | core + `shared` segment | ≥2 | core alone false-passes (table self-citation) |
| 1 | `trampoline: true` | core + `shared` segment | ≥2 | DEC-4 signal, same hazard |
| 2 | `plan⇄spike` | core + `shared` segment | ≥2 | same hazard |
| 2 | `plan⇄spike` | `skills/spike/SKILL.md` | ≥1 | greppable from both sides |
| 3 | `coordinator:plan` | `skills/spike/SKILL.md` | ≥1 | spike's `viable` exit route |
| 3 | `coordinator:shape` | `skills/spike/SKILL.md` | ≥1 | spike's `not-viable` exit route |
| 4 | `"viable"` | `schemas/spike-result.schema.json` | ≥1 | verdict enum is schema-backed, not prose |
| 4 | `"not-viable"` | `schemas/spike-result.schema.json` | ≥1 | other arm of that enum |
| 5 | `plan⇄sizing` | core + `plan`-route + `shared` segments | ≥3 | same hazard, split across segments |
| 6 | `plan requires a sizing-object and trampolines back without one` | this file | ≥2 | 1 means only the self-reference survives, gate is gone |
