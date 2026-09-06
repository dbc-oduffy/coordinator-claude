# Super-Skill Architecture — Decision-Tree Skill Pattern

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-05/2026-05-07-dogfood-super-skill.md, archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md, docs/plans/2026-07-12-spike-pipeline-skill.md, archive/specs/2026-05/2026-05-06-skill-budget-structural-cleanup.md -->

> Spec backlink: `archive/specs/2026-05-06-decision-tree-skill-pattern.md` (adopted 2026-05-06).

---
provenance:
  kind: distilled-spec
  source_plans:
    - path: docs/plans/2026-05-06-decision-tree-skill-pattern.md
      last_verbose_sha: 1048b2ecee5be7f96824353c4601b97f6fb7448a
    - path: docs/plans/2026-05-06-plan-super-skill.md
      last_verbose_sha: b654bd9648d9776da999470a8113cdf55e6ac683
    - path: docs/plans/2026-05-06-review-code-super-skill.md
      last_verbose_sha: 72039b6ccabe74d4d16b5040eea36ead5d70baef
    - path: docs/plans/2026-05-06-review-super-skill.md
      last_verbose_sha: 3911b7704403240cd98e96bdc128794caf3081f4
  distilled_run: 2026-05-08-1032
---

Coordinator skills come in two shapes: **narrative** (prose explaining principles) and **decision-tree** (a branching router the EM walks at trigger time). Starting 2026-05-06, all new coordinator super-skills use the decision-tree shape. This guide describes the pattern, its contract, and its build sequence.

---

## Overview

**Why decision-tree skills exist.** Narrative skills decay: the EM is expected to absorb prose at boot or skim at trigger time, and behaviour depends on holding the narrative in working memory between sessions. Decision-tree skills replace prose with a tree: the EM matches the trigger condition, walks one branch top-to-bottom, and takes the terminal action. No working-memory load. The skill *is* the procedure.

**What changes.** Long-form doctrine extracts to `docs/wiki/` as reference material. The skill becomes a router into existing doctrine, not a second copy of it.

**Current super-skills (as of 2026-05-07):**
- `coordinator:plan` — replaces `writing-plans`; 5 branches (Triage / Substrate / Body / Exit / Friction)
- `coordinator:review` — refactored; Branch A outgoing (pre-flight + dispatch) / Branch B incoming (triage + integrate)
- `coordinator:review-code` — replaces `requesting-code-review`; counterpart for code/diff/PR review

---

## Contract — Seven Hard Requirements

**Scope note.** This contract governs the **decision-tree generation** (Generation 2 in the
lineage below) — a prose tree the EM walks branch-by-branch. It is not deprecated and remains
the correct shape for judgment-dense, low-frequency skills. A newer generation exists for the
opposite case — see § Generation 3 — Computed Skill, below.

Every decision-tree skill MUST satisfy all seven:

1. **Description ≤175 chars** — advertises the trigger only, NOT the procedure. Trigger keywords go in the SKILL.md body, not the description. (Aligned with skill-budget Phase D.)

2. **Body is a tree, not paragraphs** — MUST contain ≥3 markdown bullet/heading levels of branching AND zero paragraphs longer than 3 lines outside the top-of-body Trigger/When-NOT-to-use block. If the body fails either count, refactor before shipping.

3. **Tree depth ≤3 levels** — deeper means the skill is doing too much; split or push detail to a wiki the branch links to.

4. **Each terminal branch terminates in exactly one of:**
   - (a) **Dispatch** — invoke a named agent with a specified brief
   - (b) **Doctrine link** — `→ see CLAUDE.md § <heading>`
   - (c) **Wiki link** — `→ see docs/wiki/<file>.md` (optionally with anchor)
   - (d) **Inline action** — a single imperative, ≤2 lines
   - **No terminal may be a paragraph of guidance.** If a branch needs more than two lines of prose, the prose belongs in a wiki and the branch becomes (c).

5. **No doctrine duplication** — if CLAUDE.md or a wiki already states the rule, the branch links; it does not restate. The skill is a router into existing doctrine.

6. **Branches are mutually-exclusive AND collectively exhaustive** — every reachable case maps to exactly one branch, or the tree includes an explicit default/else terminal. "Trivial vs. non-trivial" is acceptable IF the skill defines what makes something trivial in one line at the top.

7. **Trigger and When-NOT-to-use block at top** — the top of the skill body must state the trigger conditions and explicitly enumerate anti-triggers (conditions that route elsewhere). Anti-triggers should name the alternative action.

---

## Build Sequence

Multi-session effort. Land the pattern first; build one super-skill per session afterward.

1. **Pattern (done)** — this guide
2. **`coordinator:prior-art-checker` agent** — wiki/lessons recall agent called as a branch node
3. **`coordinator:review`** — plan reviews only; first consumer of prior-art-checker
4. **`coordinator:plan`** — replaces `writing-plans`
5. **`coordinator:review-code`** — code reviews; each review-side super-skill consumes different parts of methodology skills
6. **Cleanup pass** — delete or name-only the methodology skills absorbed as branches; gated on all three super-skills shipping

---

## coordinator:plan — Trigger Conditions

**Trigger:** EM is about to plan implementation work where the spec carries decision weight (multi-file, new abstraction, cross-system, scaffolds new agents/skills, reverses a prior decision) OR PM typed any of: "write a plan", "let's plan", "break this down", "plan the implementation".

**When NOT to use:**
- Trivial work (single-file fix, typo, link repoint, no abstraction) → just do it, no plan
- Implementation ambiguity mid-coding → use harness Plan tool inline
- Architectural-tier (cross-system irreversible, multi-stakeholder) → surface to PM, propose /staff-session
- Vague / multi-subsystem / pre-decomposition → /brainstorming first, then return
- Skill-authoring → /writing-skills
- Plan already written, review needed → /review
- Stuck pattern → /stuck-detection

---

## Skill Renames and Structural Notes

1. **Skill renames at dispatch surface:** `coordinator:writing-plans` → `coordinator:plan`; `coordinator:requesting-code-review` → `coordinator:review-code`; `coordinator:using-git-worktrees` removed (rule lives in CLAUDE.md)
2. **Branch-walking semantics:** coordinator:plan and coordinator:review are decision-tree super-skills with branch-walking semantics (Branch A triage → B substrate → C compose → Exit), not prose skills.
3. **description-budget convention** (default ≤150, PM-gated ≤175, custom via `description-budget:` frontmatter) applies to skill descriptions. It is enforced by `coordinator/tests/test_boot_description_envelope.py` in the repo's pytest tier — per-file cap plus a shrink-only per-surface aggregate byte ratchet, across agents, skills, and commands. The separate weekly `check-description-length` advisory scans the `~/.claude/plugins/` install tree and covers no coordinator surface; see `docs/wiki/skill-budget-discipline.md § Description Budget Hard Limit`.
4. **Daily-branch span-aware rename** changes branch-naming semantics: `work/{machine}/{date}` may carry across days as `work/{machine}/{span}` with silent midnight rename.

---

## Dogfood Walk-Through Protocol

Each new super-skill must be walk-through validated before shipping:
1. EM walks the decision tree on a real recent scenario that would have triggered the skill
2. The Staff Engineer walks independently and appends findings to the fixture
3. Verdict CONCURRENT (no gaps) or CONCURRENT_WITH_NITS (minor gaps applied inline)
4. Walk-through fixture lives at `tasks/super-skill-walkthroughs/<skill-name>.md`

---

## Shipping Patterns — Belt-and-Suspenders and Sibling Templates

### Infrastructure features need belt-and-suspenders: process + grep bait

A new convention (like `docs/README.md` maintenance, or a new hook contract) only sticks if it is greppable from every contact point agents encounter — `/repo-setup` scaffolds it, `/workstream-start` surfaces it, `/workstream-complete` patches it, hooks enforce it. Process alone is insufficient: if the phrase doesn't appear in enough places that any agent stumbling around will find it, the convention decays between sessions. When adding a cross-cutting convention to the coordinator system, enumerate its contact points and plant the phrase at each one before shipping.

### Sibling super-skills ship faster by reusing the prior instance as a template

When shipping the Nth instance of a stable super-skill pattern (e.g. a third decision-tree skill after `coordinator:plan` and `coordinator:review`), the prior instance is the structural template — not just a reference. Use its Branch A/A.1/A.2/A.3 + Branch B + cross-reference exit + contract self-check + migration table + recall-validation AC list as the starting scaffold. Empirical: drafting `coordinator:review-code` from `coordinator:review`'s design plan compressed the Staff Engineer's R1 findings from 11 (against a from-scratch design) to 1 substantive depth-violation + 9 minor/nit polishing fixes.

## Dogfood as Super-Skill — Binary-Outcome Loop, Not a Backlog Feeder

<!-- src: plan05-012, plan05-013, plan05-014, plan05-015, plan05-017 -->

`/dogfood` is a decision-tree super-skill in its own right (not a linear checklist), governing how new coordinator capability gets validated before "stable" is declared.

**Binary outcome doctrine — no third path.** Every observation during a dogfood loop resolves one of two ways:
- It's a bug → fix it now, in this session, on this branch.
- It reveals the thing is fundamentally wrong-shape → stop the loop, switch gears into replan/refactor.

There is no "log to known-bugs and keep going." That is file-and-defer wearing a dogfood costume — the same anti-pattern the improvement-queue admission rule (`coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Improvement Queue") forbids for in-session failures generally.

**Three-tier gate system, declared at invocation, not inferred mid-run.** The skill's scope and intensity are a PM-declared parameter at invocation time:
- `--narrow` (default) — single smoke surface
- `--broad` — multi-surface happy path
- `--shakedown` — comprehensive matrix coverage; without a declared coverage matrix, `--shakedown` silently degrades to `--broad`

**Four pre-flight gates before entering the loop:** (1) idempotent re-run, (2) machine-parseable progress, (3) framing audit, (4) coverage matrix declared (`--shakedown` only).

**Loop exit criteria — all three required:**
1. Primary handoff goal met — succeeds end-to-end on latest pass.
2. No NEW bugs surfaced inside the fix-through cone in the last iteration.
3. PM signals stop, OR the EM proposes converge and the PM confirms.

Alternative exits are switch-gears (fundamental wrong-shape) or a PM stop. "Budget exhausted, file remainder to backlog" is explicitly NOT an exit path — that's the file-and-defer anti-pattern re-appearing at the loop boundary.

**Doctrinal framing (carried into the dogfood skill body verbatim):** *"Handoffs are mid-stream baton-passes, not end-of-session ceremony. Shipped ≠ handed-off."* This line disambiguates a dogfood-in-progress handoff from a completion handoff — the loop is still open, the session is passing a baton, not closing a workstream.

---

## Generation 3 — Computed Skill

<!-- src: docs/plans/2026-07-23-computed-skills-pickup-beachhead.md § Vocabulary -->

The decision-tree shape above is **Generation 2** of the coordinator skill lineage. A further
generation exists for skills whose branching is dense enough, and frequent enough, that walking
a prose tree by hand is itself the bottleneck: **computed skill**, where a claude-klabauter assembler CLI
computes the routing and the EM resolves only whatever judgment residue the assembler cannot
decide. See `CONTEXT.md § computed skill` for the term's full definition and the four-generation
lineage table (Narrative → Decision-tree super-skill → ASIC helper-extraction → Computed skill).

**When to reach for which — not a replacement, a fork by shape:**
- **Stay with the Generation 2 super-skill contract above** when a skill's branches are
  genuinely judgment-dense — the routing decision depends on human/product context an
  assembler cannot observe (e.g. `coordinator:plan` triage, `coordinator:review` incoming
  disposition).
- **Reach for a computed skill** when a skill is high-frequency AND high-mechanical-density —
  most of its branches are a mechanical function of disk state, git state, or frontmatter an
  assembler can read directly, and the EM's prose-tree walk is pure overhead on top of that.

**Assembler contract:** `coordinator/docs/wiki/computed-skills.md` (in progress — first
consumer is `coordinator:pickup`).

**Discovery surface.** A skill considering the computed shape should surface it at
skill-authoring time, not leave it as tribal knowledge of this wiki page — the skill-authoring
entrypoint (`coordinator/docs/wiki/writing-skills.md`) is the intended pointer-back location;
until that cross-reference lands, this section is the canonical discovery surface.

---

## Spike — Derisking Primitive as a Pipeline Node

<!-- src: plan33-008, plan33-009, plan33-010, plan33-036 -->

`/spike` is the newest addition to the super-skill family — a bounded, binary-outcome derisking primitive that sits as a node in the plan pipeline graph rather than as a standalone tool.

**Definition — two-part fusion, both halves mandatory.** A spike fuses external research (docs, prior art, library capability checks) with local empirical study (throwaway probes against the actual codebase). Neither half alone satisfies the primitive — research-only skips whether it actually works here; probe-only skips whether the approach is sound elsewhere. The verdict is durable: a standalone `spike-result` record under `docs/research/spike-verdicts/`, not a transient chat conclusion and not a handoff — a spike verdict is evidence, not a work-continuance baton, and lives in its own schema-typed home.

**Routing — spike is graph-native, not a side quest.** The pipeline shape is `shape → spike → plan`, with `plan ⇄ spike` back-edges: a plan in progress can trampoline back into a spike when a derisking question surfaces mid-plan, and the spike's verdict routes back into plan authoring or resumption.
- **Viable verdict** → routes to `/plan` (new or resumed).
- **Not-viable verdict** → routes to `/shape` or directly to the PM — the problem framing itself needs revisiting, not just the plan.

**Gating split by structural discriminator, not by feel.** Research-heavy spikes (external unknowns dominate) are PM-gated at invocation — same posture as `/staff-session`. Plan-trampoline spikes (a plan author needs to derisk one specific sub-question mid-authoring) are EM-reachable directly, but only when the dispatching context carries an explicit `trampoline:true` signal — the discriminator is structural (is this plan-internal or a fresh research question), not a judgment call the EM makes ad hoc.

**Why this belongs in the super-skill family:** spike is throwaway-probe-shaped (matches the "bounded, single-purpose, decision-tree-walked" contract of § Contract above) but its terminal is neither dispatch nor doctrine-link — it's a durable verdict artifact that feeds back into the graph. This is the first super-skill whose exit shape is "produce a record consumed by a sibling super-skill" rather than "take an inline action."

---

## Skill Consolidation — Fold Thin Engines Into Their Only Callers

<!-- src: plan07-005, plan07-006 -->

Not every skill-surface reduction is a decision-tree conversion; some prior-generation skills collapse entirely because they were never doing independent work. Four skills folded: `daily-review` → `/workday-complete` Step 4, `generate-repomap` → `bin/generate-repomap.py` (now claude-klabauter `coordinator/bin/generate-repomap.py`), `review-dispatch` → `docs/wiki/reviewer-pipeline.md` + inlined into `/review`/`/review-code`, `setup-percolate` → `/percolate` Branch 0.

**The generalizable rule:** when a skill is a thin engine called only by user-facing surfaces (empirically: `review-dispatch` had 2 callers, `generate-repomap` had 4), fold it into them — keep one tier, not three. A middle layer earns its keep only by adding *judgment*; a pure pass-through engine adds none. This is the negative case for the super-skill pattern above: not every skill needs to become a decision tree — some need to disappear into their callers instead. Net effect of the consolidation pass: 30→26 skills, -4 user-facing surfaces, no functional regression.

**A second, distinct cause of the same consolidation: an Anthropic too-many-skills flag.**

> **PM first-hand observation, logged 2026-07-27, not reproduced from documentation.** Anthropic's
> tooling directly flagged the coordinator-claude skill catalog as too large, stating that only
> the most-used `n` skills would load and offering "raise the cap" as the remedy. This flag was a
> cause of the v2 "super-skills" consolidation — the glut of over-separated skills was folded into
> fewer, larger ones partly in response to it.

This is recorded here as an added cause, not a replacement for the ones already documented above
(thin-engine folding) or in `archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md`
(which additionally cites a description-character-budget CI gate we built ourselves). Those records are true as far as
they go; none of them independently traces this specific Anthropic-tooling flag, because it was
never logged at the time — this paragraph is that missing log entry, added retrospectively.
Causes are plural here: a thin-skill-folding pass and a hard external skill-count cap are exactly
the kind of pressure that reinforce each other, not competing explanations. See
`docs/wiki/skill-budget-discipline.md` for the fuller first-hand account and the two questions
that remain genuinely UNSETTLED (the specific figure, and whether an over-budget skill loses only
its description or drops from the listing entirely).

---

## Reference

- Pattern spec: `archive/specs/2026-05-06-decision-tree-skill-pattern.md`
- coordinator:plan: `plugins/coordinator/skills/plan/SKILL.md`
- coordinator:review: `plugins/coordinator/skills/review/SKILL.md`
- coordinator:review-code: `plugins/coordinator/skills/review-code/SKILL.md`
- Writing-skills wiki (skill TDD): `docs/wiki/writing-skills.md`
- Skill budget discipline: `docs/wiki/skill-budget-discipline.md`
- Dogfood super-skill spec: `archive/specs/2026-05/2026-05-07-dogfood-super-skill.md`
- Spike pipeline skill plan: `docs/plans/2026-07-12-spike-pipeline-skill.md`
- Computed skill (Generation 3): `CONTEXT.md § computed skill`, `coordinator/docs/wiki/computed-skills.md`

## Superpowers gap-analysis verdict — capability surface is complete

*Source: claude-central.* The Superpowers external-pattern audit (cross-referenced against `coordinator/` skills + `bin/` helpers + hooks) returned **no net-new capability gaps**. The audit lens was: "is there a load-bearing pattern in Superpowers that coordinator structurally lacks?" — and the verdict is no.

This is a meaningful negative result, not a no-op:

- **Refactor target selection** should not pull from Superpowers' shape inventory looking for "missing pieces"; coordinator's super-skill surface is feature-complete relative to the comparable OSS template.
- **Future Superpowers releases** can be audited the same way — the procedure is `tasks/<survey>/` scout listing patterns, cross-grep against coordinator skill registry, and verdict. The pattern is in `architecture-survey.md`.
- **The negative result is itself wiki-worthy** — null-result audits fold the rule into the producer skill rather than leaving the absence implicit; no current doctrine heading names "Self-Improvement Loop" directly.

If a Superpowers feature surfaces later that does feel like a structural gap, the move is `coordinator:architecture-audit` against the named subsystem, not a Superpowers porting exercise.
