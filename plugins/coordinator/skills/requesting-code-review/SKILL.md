---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements
version: 1.0.0
---

# Requesting Code Review

Use `/review-dispatch` to route to named reviewers (Patrik, Palí, Sid, Camelia, Fru) to catch issues before they cascade.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:**
<!-- Review: Patrik — ghost reference to deleted workflow -->
- After each task in /delegate-execution workflow
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## How to Request

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Consider docs-checker pre-flight:**

For artifacts that cite external APIs — especially C++ or Unreal Engine code — the EM should consider running the `docs-checker` agent before dispatching the Opus reviewer. docs-checker catches mechanical errors (wrong API name, wrong signature, wrong header) at Sonnet cost, leaving the Opus reviewer free to focus on architecture and design. The skip is an EM call and is silent — no flag needed. Pure prose, in-repo-only references, and trivial in-distribution code don't warrant it. **Skipping docs-checker does NOT mean skipping the review — only the PM may waive a review on an EM plan.** Full decision rules: `docs/wiki/docs-checker-pre-review.md`. Mechanical flow: `commands/review-dispatch.md` Phase 2.7.

**3. Dispatch code-reviewer subagent:**

Use `/review-dispatch` to route to the appropriate named reviewer. Fill the context template at `code-reviewer.md` to provide the review scope.

**Placeholders:**
- `{WHAT_WAS_IMPLEMENTED}` - What you just built
- `{PLAN_OR_REQUIREMENTS}` - What it should do
- `{BASE_SHA}` - Starting commit
- `{HEAD_SHA}` - Ending commit
- `{DESCRIPTION}` - Brief summary

**4. Act on ALL feedback:**
- Go through the review line-by-line — every item, every severity
- Fix Critical, Important, AND Minor issues before proceeding
- The only reasons to skip an item: (a) it requires PM input, or (b) you genuinely disagree (flag to PM with reasoning)
- Do NOT "note for later" — later never comes
- If the review has many items, use a checklist to track completion

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request code review before proceeding.

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[Invoke /review-dispatch — routes to named reviewer based on artifact signals]
  WHAT_WAS_IMPLEMENTED: Verification and repair functions for conversation index
  PLAN_OR_REQUIREMENTS: Task 2 from docs/plans/deployment-plan.md
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661
  DESCRIPTION: Added verifyIndex() and repairIndex() with 4 issue types

[Subagent returns]:
  Strengths: Clean architecture, real tests
  Issues:
    Important: Missing progress indicators
    Minor: Magic number (100) for reporting interval
  Assessment: Ready to proceed

You: [Fix progress indicators]
[Continue to Task 3]
```

## Integration with Workflows

**Delegate-Execution Workflow:**
- Review after EACH task
- Catch issues before they compound
- Fix before moving to next task

**Executing Plans:**
- Review after each batch (3 tasks)
- Get feedback, apply, continue

**Ad-Hoc Development:**
- Review before merge
- Review when stuck

## Matching Review Tier to Plan Complexity

**Match review tier to plan complexity, not plan importance.**

Staff sessions (2+ reviewers + synthesizer) are for contested architectural decisions or cross-domain plans where multiple expert perspectives are genuinely needed and may contradict each other. Most plans — even important ones — need a single domain reviewer routed through `/review-dispatch`.

Routing every "important" plan to a staff session burns budget without finding more bugs. Importance is not the trigger; genuine multi-perspective contention is.

| Situation | Correct tier |
|-----------|--------------|
| New feature implementation, single domain | `/review-dispatch` → one reviewer |
| Cross-domain plan (e.g., UE + data pipeline) | `/review-dispatch` → two sequential reviewers |
| Contested architectural choice with 2+ valid approaches | Staff session |
| "This is important, I want it done right" | `/review-dispatch` → one reviewer |
| Plan touches auth, security, billing — high stakes but clear approach | `/review-dispatch` → one reviewer |

The heuristic: would a second reviewer likely **contradict** the first, or just add diminishing-return notes? If contradiction is unlikely, one reviewer is enough.

## Red Flags

**Never:**
- Skip review because "it's simple"
- Ignore ANY review item regardless of severity
- "Note for later" or "defer" minor issues — address them now
- Cherry-pick from a review and declare it "addressed"
- Argue with valid technical feedback

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: requesting-code-review/code-reviewer.md
