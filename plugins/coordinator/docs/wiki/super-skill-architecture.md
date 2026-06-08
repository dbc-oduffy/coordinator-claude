# Super-Skill Architecture — Decision-Tree Skill Pattern

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

## Version History — v2.0.0 Breaking Changes (2026-05-07)

coordinator-claude v2.0.0 introduced four breaking changes related to super-skills:

1. **Skill renames at dispatch surface:** `coordinator:writing-plans` → `coordinator:plan`; `coordinator:requesting-code-review` → `coordinator:review-code`; `coordinator:using-git-worktrees` removed (rule lives in CLAUDE.md)
2. **Branch-walking semantics:** coordinator:plan and coordinator:review are now decision-tree super-skills with branch-walking semantics (Branch A triage → B substrate → C compose → Exit). Old `writing-plans` was prose; new shape changes invocation expectations.
3. **description-budget validator** runs **advisory-only** in `/workweek-complete` (no longer a blocking gate). Skills exceeding the limit get flagged in the weekly summary; the convention itself (default ≤150, PM-gated ≤175, custom via `description-budget:` frontmatter) still applies — but a one-off overshoot does not block any ceremony.
4. **Daily-branch span-aware rename** changes branch-naming semantics: `work/{machine}/{date}` may now carry across days as `work/{machine}/{span}` with silent midnight rename.

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

## Reference

- Pattern spec: `archive/specs/2026-05-06-decision-tree-skill-pattern.md`
- coordinator:plan: `plugins/coordinator/skills/plan/SKILL.md`
- coordinator:review: `plugins/coordinator/skills/review/SKILL.md`
- coordinator:review-code: `plugins/coordinator/skills/review-code/SKILL.md`
- Writing-skills wiki (skill TDD): `docs/wiki/writing-skills.md`
- Skill budget discipline: `docs/wiki/skill-budget-discipline.md`
