# Task-Tier Guidance

> **Purpose:** Match the weight of your work to the right workflow. The coordinator system scales from a single command to a full multi-agent pipeline — this table tells you which tier to reach for and what to expect.

---

## Tier table

| Tier | Examples | Skill / command | Reviewer | Expected wall time | Ship gate |
|------|----------|-----------------|----------|--------------------|-----------|
| **Tiny edit** | Fix a typo, update a constant, rename a variable | Direct EM edit — no plan, no dispatch | None required | < 5 min | Commit + push |
| **Small fix** | One-function bug fix, add a missing guard, tweak a config value | `coordinator:systematic-debugging` (for bugs) or direct edit | Optional: quick the Staff Engineer pass if the fix touches shared state | 5–20 min | Commit + push; reviewer finding if risky |
| **Feature** | New command, new skill, new agent, new integration | `/execute-plan` after PM approves a plan | Domain reviewer first (e.g., the Staff Engineer (`coordinator:staff-eng`) for UE, the Front-End Reviewer (`web-dev:senior-front-end`) for web), then the Staff Engineer (`coordinator:staff-eng`) as generalist; the Director of Engineering (`coordinator:eng-director`) as backstop at High effort | 30 min – 2 hrs | PR via `/merge-to-main`; ship verdict required |
| **Refactor** | Extract a subsystem, rename a core abstraction, restructure a plugin | `/staff-session plan` to align on approach first, then `/execute-plan` | the Staff Engineer (architecture lens) + the Director of Engineering (backstop mode) — sequential | 1–4 hrs | PR; architecture atlas update via `/update-docs` |
| **System rewrite** | Replace core pipeline, migrate hook architecture, multi-plugin overhaul | `/staff-session plan` (multi-perspective debate) → chunked execution via `/delegate-execution` | Full sequential chain: domain specialist → the Staff Engineer → the Director of Engineering (backstop mode); regression suite required | Half day – full day | PM sign-off on plan + ship verdict; `/workweek-complete` gate |

---

## Reading the table

**"Tiny edit" is not "trivial."** A one-line change to a hook or a shared constant can have system-wide effects. If in doubt, run a quick the Staff Engineer pass — it takes minutes and pays for itself the first time it catches an unintended side-effect.

**"Expected wall time" is calendar, not compute.** Most of this is agent work you're not watching. The timer starts when you describe the work and ends when you're reviewing the result.

**The reviewer column is minimum.** You can always dispatch more reviewers. The `/review-dispatch` command handles routing; a domain reviewer added to a small fix costs you minutes, not hours.

**Plan first for anything feature-sized or larger.** The plan-review gate is where the PM-EM authority split matters most. The EM proposes; you approve scope, acceptance criteria, and approach before implementation starts. Re-planning mid-execution is expensive; catching a scope mismatch at plan review is cheap.

**`/staff-session plan` vs. direct plan:** For features with clear scope and no significant tradeoffs, the EM writes a plan directly and you review it. Reserve `/staff-session plan` for refactors and rewrites where the *approach* is uncertain — it runs persona-based engineers in debate mode and is worth the overhead only when the outcome of the debate meaningfully changes the plan.

---

## Flows by tier

| Tier | Flow |
|------|------|
| Tiny edit | Tell the EM → EM edits → commit |
| Small fix | Describe the bug → EM reproduces and diagnoses → fix → optional reviewer → commit |
| Feature | Describe intent → plan review → `/execute-plan` → sequential review → `/merge-to-main` |
| Refactor | `/staff-session plan` → plan review → execution in chunks → sequential review → `/merge-to-main` |
| System rewrite | `/staff-session plan` → PM approves → `/delegate-execution` (chunked) → full review chain → PM ship verdict |

---

## Tier is invocation shape, not a config key

<!-- provenance: run 2026-08-06-14h38, nugget c7-051, c7-063 -->

A tier is defined by *how a task gets invoked*, not by which config key happens to name it.
Marker filtering (running a subset of tests via a marker/tag) is not the same thing as scope —
they're independent axes. There are three legitimate exits, not two:

- **Marker-filtered** — a named subset of tests selected by tag/marker.
- **Genuinely-scoped** — a deliberately narrow slice, scoped to the files/module touched.
- **Declared-unscoped fast tier** — the fast tier run with no scoping applied at all; this is a
  legitimate third exit in its own right, not a degraded case of the other two.

Classification of which exit applies is enforced **where the invocation happens** (in
`/validate`), not merely documented in a wiki — if you're adding a new test-invocation path,
wire its tier classification into `/validate` itself rather than relying on a comment or README
note to keep it honest.

`fast_test_cmd` is ratified as a **single command** (PM ruling) — the fast tier is one shell
invocation, not a chain. If your fast tier genuinely needs multiple chained commands, that's a
sign it belongs on the Tier-F (full/system) route instead of being force-fit into
`fast_test_cmd` — don't chain commands with `&&`/`;` inside `fast_test_cmd` to route around the
single-command rule.

---

## Quick reference: which reviewer?

| Work type | Reviewer |
|-----------|----------|
| General correctness, style, sequencing | the Staff Engineer (`coordinator:staff-eng`) |
| Unreal Engine / C++ / Blueprint | the Staff Engineer (`coordinator:staff-eng`) (the Director of Engineering as backstop at High effort) |
| Front-end / React / TypeScript | the Front-End Reviewer (`web-dev:senior-front-end`) (then the Staff Engineer) |
| UX flows, user-facing copy | the UX Reviewer (`web-dev:staff-ux`) |
| Data science / ML | the Data Science Reviewer (`data-science:staff-data-sci`) |
| Architecture, major structural changes | the Staff Engineer (the Director of Engineering as backstop at High effort) |
| Cross-team / cross-repo seams, consumer-producer plug-in architecture, generic-substrate review | the Director of Engineering (`coordinator:eng-director`) standalone |
| Product scope / user-visible behavior | the VP-Product Reviewer (`coordinator:vp-product`) |

Dispatch via `/review-dispatch`. Always sequential: domain expert first, generalist (the Staff Engineer) second, the Director of Engineering as backstop at High effort, fixes integrated between each pass.
