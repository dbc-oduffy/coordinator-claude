# Task-Tier Guidance

> **Purpose:** Match the weight of your work to the right workflow. The coordinator system scales from a single command to a full multi-agent pipeline — this table tells you which tier to reach for and what to expect.

---

## Tier table

| Tier | Examples | Skill / command | Reviewer | Expected wall time | Ship gate |
|------|----------|-----------------|----------|--------------------|-----------|
| **Tiny edit** | Fix a typo, update a constant, rename a variable | Direct EM edit — no plan, no dispatch | None required | < 5 min | Commit + push |
| **Small fix** | One-function bug fix, add a missing guard, tweak a config value | `coordinator:systematic-debugging` (for bugs) or direct edit | Optional: quick Zolí pass if the fix touches shared state | 5–20 min | Commit + push; reviewer finding if risky |
| **Feature** | New command, new skill, new agent, new integration | `/execute-plan` after PM approves a plan | Domain reviewer first (e.g., Patrik for UE, Palí for web), then Zolí | 30 min – 2 hrs | PR via `/merge-to-main`; ship verdict required |
| **Refactor** | Extract a subsystem, rename a core abstraction, restructure a plugin | `/staff-session plan` to align on approach first, then `/execute-plan` | Patrik (architecture lens) + Zolí (generalist) — sequential | 1–4 hrs | PR; architecture atlas update via `/update-docs` |
| **System rewrite** | Replace core pipeline, migrate hook architecture, multi-plugin overhaul | `/staff-session plan` (multi-perspective debate) → chunked execution via `/delegate-execution` | Full sequential chain: domain specialist → Patrik → Zolí; regression suite required | Half day – full day | PM sign-off on plan + ship verdict; `/workweek-complete` gate |

---

## Reading the table

**"Tiny edit" is not "trivial."** A one-line change to a hook or a shared constant can have system-wide effects. If in doubt, run a quick Zolí pass — it takes minutes and pays for itself the first time it catches an unintended side-effect.

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

## Quick reference: which reviewer?

| Work type | Reviewer |
|-----------|----------|
| General correctness, style, sequencing | Zolí |
| Unreal Engine / C++ / Blueprint | Patrik (then Zolí) |
| Front-end / React / TypeScript | Palí (then Zolí) |
| UX flows, user-facing copy | Fru |
| Data science / ML | Camelia |
| Architecture, major structural changes | Patrik |
| Product scope / user-visible behavior | YK |

Dispatch via `/review-dispatch`. Always sequential: domain expert first, generalist (Zolí) second, fixes integrated between each pass.
