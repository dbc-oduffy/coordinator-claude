---
segment_id: diff-tier-and-routing
surface: diff
class: protected
order: 30
---

**`--surface diff` precedence — tier table before routing table.** Consult the tier table below BEFORE the routing table's composite signal match: the tier table decides Sonnet-vs-Opus (a single-subsystem diff with no domain signal routes to `code-reviewer` at Sonnet); the routing table fires only once the tier table selected Opus. Applying `routing.md`'s Fallback Rule (unmatched signal → the Staff Engineer at Medium) first sends Sonnet-shaped diffs to an Opus persona — the violation `agents/code-reviewer.md` exists to prevent.

**`--surface diff` only — Personas are Opus-only.** the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering carry `model: opus`; dispatching one with a `model: "sonnet"` override is a doctrine violation. Sonnet-tier code review uses `code-reviewer` (`agents/code-reviewer.md`); Sonnet-tier mechanical analysis uses the relevant worker (`test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`).

**`--surface diff` tier table:**

| Situation | Correct tier |
|---|---|
| Single-subsystem code change (one feature, one bug fix, one refactor) | One reviewer. **Sonnet-tier (post-implementation, mid-session, no architectural call):** `code-reviewer`. **Opus-tier (domain-flagged, architectural, named-persona match):** dispatch the matching persona at Opus. For known-target single-reviewer cases, direct `Agent(subagent_type=...)` dispatch is an acceptable shortcut; routing table is preferred for routing intelligence. **Never** dispatch a persona with `model: "sonnet"` — that is the violation `code-reviewer` exists to replace. |
| Cross-subsystem code change (e.g., UE + Python pipeline; front-end + auth backend) | Two sequential reviewers: `--reviewers "<domain>,the Staff Engineer"` |
| Contested architectural code change with ≥2 valid implementations AND PM authorized | `/staff-session` review-mode |
| "This is important, I want it done right" | One reviewer (auto-detects domain) |
| Code touches auth, security, billing — high stakes but clear approach | One reviewer (auto-detects domain) |

- _Code change is genuinely trivial?_ (typo, comment-only, single-line config bump with no behavior change)
  → No review needed; commit and proceed.
- _PM has explicitly waived review on a non-trivial change?_ ("ship it", "skip review", "straight to merge")
  → Exit; this skill does not run. Log the waiver in commit message or PR description: `review: skipped per PM direction YYYY-MM-DD` (greppable).

_See `${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Dispatch — `/staff-session` is PM-gated; ask first._
