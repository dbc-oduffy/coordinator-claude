# Skill Budget Discipline

> Spec backlinks: `archive/specs/2026-05-06-skill-budget-phases-bcd.md`, `archive/specs/2026-05-06-skill-budget-structural-cleanup.md`.

---
provenance:
  kind: distilled-spec
  source_plans:
    - path: docs/plans/2026-05-06-skill-budget-phases-bcd.md
      last_verbose_sha: 813075af33e4add9d0c1fc5f5c7b8bbc35a1865a
    - path: docs/plans/2026-05-06-skill-budget-structural-cleanup.md
      last_verbose_sha: c7bfce032fdca4437e2bbfa43e1405b4b79f7ebb
    - path: docs/plans/2026-05-06-phase-e-learn-lessons.md
      last_verbose_sha: 400504b33d6b3bb0a61e4ac9eed7d22012b1b346
  distilled_run: 2026-05-08-1032
---

Every loaded skill description is **always in context** — length compounds into aggregate token budget. Skill budget discipline is the practice of keeping the always-on description budget minimal so context remains available for actual work.

---

## Why Skill Budget Matters

The Claude Code harness loads all enabled skill descriptions at every session start, unconditionally. 88 enabled skills at ~200-600 tokens each = 17,000–52,000 tokens of constant overhead. Skills past a threshold (~60-70 loaded skills) may trigger truncation in the /skill-listing command, making discovery invisible.

Key finding from the 2026-05-06 audit: **many skills had zero invocations over 30 days** — they were pure description-budget load with no behavioral value. The audit identified ~30 candidates for removal, demotion, or description trim, with an estimated 6-8K token savings.

---

## Utilization Audit Findings (2026-05-06, 30-day window)

**Heavy (≥25 invocations/30d):** coordinator:pickup (602), coordinator:handoff (425), coordinator:session-end (366), coordinator:update-docs (66), coordinator:merging-to-main (53), coordinator:workday-start (44), coordinator:mise-en-place (31)

**Zero invocations (methodology skills — passive doctrine burden):** requesting-code-review, receiving-code-review, dispatching-parallel-agents, verification-before-completion, test-driven-development, stuck-detection, systematic-debugging, skill-discovery

Caveat: cross-machine sessions undercounted 30-50%; passive-doctrine skills may be referenced by agents without explicit invocation.

---

## Phase A Cleanup Actions (executed 2026-05-06, commit e40441f)

PM-authorized cleanup:
- Disabled 5 unused official-marketplace plugins globally
- Added skillOverrides to hide 4 builtins, name-only 5 builtins + 3 passive-doctrine skills
- Deleted 4 dead coordinator skills (lessons-trim, using-git-worktrees, skill-discovery, inspiration-audit)
- Demoted 3 lifecycle subroutines (tracker-maintenance, handoff-archival, atlas-integrity-check) out of skill surface — /update-docs can still Read them but they don't register as skills
- Removed /update-docs tail-call from /mise-en-place

**Rejected:** /doctor cluster (PM: "bug-sweep is not a doctor mode"); session-end / workday-complete merge (PM: distinct cadences).

---

## Description Budget Hard Limit

Phase D: trim all skill descriptions to ≤150/175 chars. The `description-budget` validator runs **advisory-only** in `/workweek-complete` (no longer a blocking gate). Skills exceeding the limit get flagged in the weekly summary; the convention itself (default ≤150, PM-gated ≤175, custom via `description-budget:` frontmatter) still applies — but a one-off overshoot does not block any ceremony.

---

## Per-Project Plugin Gating

Skills are disabled globally and re-enabled per-project via settings.json `enabledPlugins` array:
- game-dev, web-dev, data-science, holodeck-control, holodeck-docs: disabled globally on non-UE-project machines
- coordinator: always enabled globally
- Per-project override: add to project settings.json `enabledPlugins`

On Windows with holodeck-flavored plugins, cygpath translation and node-merge fallback are required because plugin paths use MSYS-style separators.

---

## Decision Records

| DR | Decision | Status |
|----|----------|--------|
| decision-tree-skill-pattern | Adopt decision-tree pattern over narrative skills for all new super-skills | Accepted 2026-05-06 |
| Phase A cleanup | Disable unused plugins + delete dead skills + demote lifecycle subroutines | Accepted 2026-05-06 |
| description-budget hard limit | Phase E enforces ≤150/175 char descriptions via CI gate | Accepted 2026-05-06 |

---

## Reference

- Super-skill architecture: `docs/wiki/super-skill-architecture.md`
- Per-project plugin gating: `docs/wiki/per-project-plugin-gating.md`
