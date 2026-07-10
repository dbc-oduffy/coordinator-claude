# Setup-Class Skills Produce, Don't Prescribe

> Setup-class skills (those that scaffold a project, install a tool, or initialize a new surface) produce minimum-viable versions of all artifacts the downstream system relies on. Downstream skills add to these artifacts as content accumulates; they do NOT create-from-scratch what setup should have produced.

## The principle

A setup-class skill runs at the moment of maximum-possible context for the new surface: the operator has just answered the configuration questions, the EM has just ratified the workstream definitions, the project type is freshly pinned. That seam is the right place to author the load-bearing minimum-viable artifacts downstream skills will *add to* later. Punting them to a downstream skill — "go run `/update-docs` next" — is structurally wrong: at the seam the downstream skill is invoked, it has nothing to operate on. The pipeline runs as a no-op while taxing the operator's attention with ceremony.

The rule: setup produces what downstream relies on the existence of, even when day-1 content is structural-only — provided the artifact is genuinely load-bearing and setup has enough context to seed it meaningfully (not empty scaffolding). Downstream skills then self-gate when invoked against fresh substrate, emitting a one-line acknowledgment that there is nothing to do rather than running a no-op pipeline.

## Why "produce, not prescribe"

The current failure mode this principle replaces: a setup-class skill ends its REPORT with a "Next Steps" list naming N downstream skills the operator should now run. Each named skill has nothing to do (the artifacts it would update don't exist yet), but the prescription is procedural — the operator dispatches them anyway, deferring to the documented flow. The setup conversation ends with two empty pipelines instead of "you're set up — tell me what you want to build."

The fix is shape-inversion, not better documentation of the next-steps list. Setup itself produces the minimum-viable artifacts; downstream skills self-gate. The operator's last impression is *completion*, not *more ceremony*.

## Instances

| Setup skill | Produces (minimum-viable) | Downstream self-gates |
|---|---|---|
| `/coordinator:repo-setup` | `state/orientation_cache.md` (eager, from Phase 2 PM-ratified inputs); `docs/project-tracker.md`, `docs/README.md`, `CLAUDE.md` (already eager) | `/update-docs` no-ops loudly on fresh repo (3-axis conjunctive threshold: no `DIRECTORY.md`, no `archive/completed/`, no `tasks/` artifacts); `/workstream-start` consumes the `state/.repo-setup-just-ran` sentinel and emits the alternative one-liner |

## Applying this principle to a new setup-class skill

When designing a new setup-class skill (e.g., `/coordinator:install`, `/example-game-repo:install`, or a future tool-install surface):

1. **Identify the load-bearing downstream artifacts.** What files do downstream skills *rely on the existence of* in their normal-case flow? Those are candidates for eager seeding.
2. **Apply the lazy-creation rule per candidate.** Does the setup conversation provide *meaningful day-1 content* for this artifact (not just a placeholder header)? If yes, seed it eagerly. If no, leave it LAZY — empty scaffolding trains agents to ignore the directory and has zero signal value (see `skills/repo-setup/SKILL.md` § Lazy-creation discipline).
3. **Add a precondition probe to each downstream consumer.** Each skill that runs against the seeded artifacts must self-gate when invoked on fresh substrate — emit a one-line acknowledgment and exit, do not run a no-op pipeline. The probe threshold biases toward false-negative-NEVER (if any axis suggests real work is due, run the full pipeline).

The rule is **not** "scaffold every possible artifact" — it is "scaffold what the downstream system relies on the existence of, when setup has meaningful content to put in it."

## Failure mode this prevents

The Phase 4 REPORT antipattern: end the setup conversation with a "go run two more skills" list where neither skill has anything to do on a freshly-scaffolded surface. The first-time operator's last impression is two no-op pipelines, not "you're set up — tell me what to build." Cumulative tax: the same misalignment surfaces in adjacent shapes (operator voluntarily runs `/workstream-start` five minutes after setup, hits an empty work-menu, concludes the skill is broken).

The inversion fixes the root: setup produces, downstream self-gates.

## Adjacent doctrine

→ [`post-install-onboarding-pattern.md`](post-install-onboarding-pattern.md) — the EM-facilitated guided tour at install-tail. **Distinct from this doctrine** — that one is about the *conversation* (orient / make it yours / test drive); this one is about the *substrate* (what setup writes to disk). The two compose: setup produces minimum-viable substrate, then the post-install tour offers an optional guided walkthrough of what was installed.
→ [`getting-started.md`](getting-started.md) — coordinator's operator-facing tour (the instance of `post-install-onboarding-pattern.md` for this plugin).
→ `skills/repo-setup/SKILL.md` § Lazy-creation discipline — the in-skill articulation of the underlying "meaningful day-1 content" rule that this principle generalizes.
