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
| Single-domain refactor where a domain reviewer already covered the load-bearing concerns | One reviewer (the domain persona). Do NOT chain a generalist (the Staff Engineer) backstop by default — empirically the second pass yields P2 framings, not architectural redirects. **This default applies ONLY when the domain reviewer's findings demonstrably engaged the architectural layer** (abstraction boundaries, cross-system seams, the load-bearing design choice) — NOT merely that a domain pass ran. A domain pass that returned only surface findings does NOT license skipping the generalist; in that case a generalist backstop is still warranted. Generalist backstop is explicit opt-in: `--reviewers "<domain>,the Staff Engineer"`. |
| Cross-domain plan (e.g., UE + data pipeline, front-end + arch) | Two sequential Opus-persona reviewers: `--reviewers "<domain>,the Staff Engineer"` |
| Contested architectural choice with ≥2 valid approaches AND PM authorized | `/staff-session` review-mode |
| "This is important, I want it done right" | One Opus-persona reviewer (auto-detects domain) |
| "the Staff Engineer feels heavy for this; route to code-reviewer instead" | **Not a valid row.** `code-reviewer` is the Sonnet diff reviewer, not a plan reviewer. The fork is named Opus persona OR skip review (implement and let `code-reviewer` catch issues on the diff at `/workstream-complete`). Sonnet-on-plan-body is not on the menu. _See `skills/plan/SKILL.md` § Exit ¶ Reviewer altitude is binary._ |

- _Plan is genuinely trivial?_ (one-line doc fix, typo, link repoint)
  → No review needed; commit and proceed.
- _PM has explicitly waived review on a non-trivial plan?_ ("ship it", "skip review", "straight to execution")
  → Exit; this skill does not run. Log the waiver in the plan frontmatter (`review: skipped per PM direction YYYY-MM-DD`).

_See `${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Dispatch — `/staff-session` is PM-gated; ask first._

**Sequencing (HARD RULE):** `coordinator/skills/review/SKILL.md` § A.3 governs unchanged — sequential, and the merge-gate parallel carve-out never reaches a plan review.
