---
segment_id: plan-routing-and-sequencing
surface: plan
class: protected
order: 6
---

**Reviewer tier table:**

| Situation | Correct tier |
|---|---|
| Single-domain plan (new feature, doc redesign, refactor) | One Opus-persona reviewer (auto-detects domain from routing table) |
| Single-domain refactor where a domain reviewer already covered the load-bearing concerns | One reviewer (the domain persona). Do NOT chain a generalist (the Staff Engineer) backstop by default. **This default applies ONLY when the domain reviewer's findings demonstrably engaged the architectural layer** (abstraction boundaries, cross-system seams, the load-bearing design choice); a domain pass that returned only surface findings still warrants a generalist backstop. Generalist backstop is explicit opt-in: `--reviewers "<domain>,the Staff Engineer"`. |
| Cross-domain plan (e.g., UE + data pipeline, front-end + arch) | Two sequential Opus-persona reviewers: `--reviewers "<domain>,the Staff Engineer"` |
| Contested architectural choice with ≥2 valid approaches AND PM authorized | `/staff-session` review-mode |
| "This is important, I want it done right" | One Opus-persona reviewer (auto-detects domain) |
| "the Staff Engineer feels heavy for this; route to code-reviewer instead" | **Not a valid row.** `code-reviewer` is the Sonnet diff reviewer, not a plan reviewer. The Opus review is the named persona, or none (implement and let `code-reviewer` catch issues on the diff at `/workstream-complete`); the one Sonnet lens on a plan body is `plan-reviewer` — an accepted-XL step ahead of the persona that never replaces it, and the `spec-dispatch` lane's single pre-dispatch pass, which has no Opus review. _See the `plan`-route **Full terminal** row of `skills/plan/residue/plan-corpus.md`._ |

- _Plan is genuinely trivial?_ (one-line doc fix, typo, link repoint)
  → No review needed; commit and proceed.
- _PM has explicitly waived review on a non-trivial plan?_ ("ship it", "skip review", "straight to execution")
  → Exit; this skill does not run. Log the waiver in the plan frontmatter (`review: skipped per PM direction YYYY-MM-DD`).

_See `${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Dispatch — `/staff-session` is PM-gated; ask first._

**Sequencing (HARD RULE):** `coordinator/skills/review/SKILL.md` § A.3 governs unchanged — sequential, and the merge-gate parallel carve-out never reaches a plan review.
