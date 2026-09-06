---
title: Receiving code review
created: 2026-05-06
type: doctrine
related:
  - plugins/coordinator/skills/review/SKILL.md (§ A.3 — Sequencing)
  - plugins/coordinator/snippets/reviewer-calibration.md
  - plugins/coordinator/agents/review-integrator.md
  - docs/wiki/docs-checker-pre-review.md
  - docs/wiki/prior-art-checker.md
---

# Receiving Code Review

## Overview

Code review requires technical evaluation, not emotional performance.

**Core principle:** Verify before implementing. Ask before assuming. Technical correctness over social comfort.

The mechanical implementation lives in `snippets/reviewer-calibration.md` (synced into every reviewer prompt) and the review-integrator agent. This wiki carries the human-facing reception doctrine: how the EM (and the PM) treat review output.

## The Response Pattern

```
WHEN receiving code review feedback:

1. READ: Complete feedback without reacting
2. UNDERSTAND: Restate requirement in own words (or ask)
3. VERIFY: Check against codebase reality
4. EVALUATE: Technically sound for THIS codebase?
5. RESPOND: Technical acknowledgment or reasoned pushback
6. IMPLEMENT: One item at a time, test each
```

## Forbidden Responses

**NEVER:**
- "You're absolutely right!" (explicit CLAUDE.md violation)
- "Great point!" / "Excellent feedback!" (performative)
- "Let me implement that now" (before verification)

**INSTEAD:**
- Restate the technical requirement
- Ask clarifying questions
- Push back with technical reasoning if wrong
- Just start working (actions > words)

## Handling Unclear Feedback

```
IF any item is unclear:
  STOP - do not implement anything yet
  ASK for clarification on unclear items

WHY: Items may be related. Partial understanding = wrong implementation.
```

**Example:**
```
the PM: "Fix 1-6"
You understand 1,2,3,6. Unclear on 4,5.

WRONG: Implement 1,2,3,6 now, ask about 4,5 later
RIGHT: "I understand items 1,2,3,6. Need clarification on 4 and 5 before proceeding."
```

## Source-Specific Handling

### From Review Agents (the Staff Engineer, the Director of Engineering, the Game Dev Reviewer, the Front-End Reviewer, the UX Reviewer, the Data Science Reviewer)

This is where coordinators most often fail. You dispatched an Opus-level agent to review your work. **Use everything they give you.**

```
WHEN processing review agent output:
  1. Read the ENTIRE review — do not skim
  2. Build a TRIAGE TABLE for EVERY item (Critical, Important, Minor, nitpick — ALL of them):

     | # | Finding | Disposition | Reasoning |
     |---|---------|-------------|-----------|
     | 1 | [summary] | Applied / Captured / Dismissed | [what you did or why] |

     Dispositions — every finding gets exactly one:
       - Applied: implemented the fix (state what changed)
       - Captured: deferred to backlog/debt tracker (state where and why not now)
       - Dismissed: genuinely disagree or requires PM input (state reasoning)
     "Captured" is NOT a parking lot — it means a concrete entry exists somewhere.

  3. Do NOT "note for later" — there is no later
  4. Do NOT cherry-pick favorites and declare the review "addressed"
  5. Verify your triage table is 100% complete before moving on
  6. Present the completed triage table in your response

FORBIDDEN:
  - "I've addressed the key items from the review" (what about the rest?)
  - "Most of the feedback has been incorporated" (what was dropped?)
  - Summarizing the review without acting on every point
  - Treating Minor/P3 items as optional
```

**Why this matters:** We are spending Opus-level agents on reviews. If you gloss over items, that investment is wasted. The whole point is excellent code and docs — every item is an opportunity.

- **Half-rotation premise-check:** when a reviewer's finding cites a constant/seam/file that's about to be modified by another in-flight chunk of the same workstream, re-verify the premise against the post-merge artifact before applying the finding. Reviewer premises rot during multi-chunk dispatches.

- **Reverse a premature disposition when a later reviewer surfaces stronger evidence.** Dispositions in the triage table are not write-once. When Reviewer 2 (or a worker like test-evidence-parser) returns evidence that contradicts a `Dismissed` or `Captured` verdict from Reviewer 1, reopen the row — change the disposition, record the evidence, apply the fix. Stale disposition entries strand bugs under "addressed" framing. Single-reviewer high-confidence verdicts are most-likely to need reversal; flag `Dismissed` rows for re-check when the next reviewer's domain overlaps.

- **Post-review plan body sweep — grep for old framing, not just patch the cited line.** When a structural reviewer finding lands (renamed abstraction, inverted default, removed phase, reframed objective), grep the plan body for the OLD framing before declaring the integration done. Integrator patches the cited line; the rest of the plan body still quotes the pre-finding vocabulary. Body sweep is a one-grep step per structural finding — cheap insurance against half-applied edits that surface as confusion three sessions later.

- **Retroactive escalation framings need forward reframing, not mechanical application.** When a reviewer or PM escalates an item retroactively — "this should have been a ceremony / blocking gate / staff-session topic" — the finding's value is the anchor pattern for *future* work, not a mechanical patch to the artifact already in flight. Capture the doctrine update (wiki/skill edit, queue entry), reframe the anchor for forward use; do not retroactively rewrite the in-flight artifact to satisfy a ceremony that wasn't load-bearing when the work started.

### From the PM
- **Trusted** - implement after understanding
- **Still ask** if scope unclear
- **No performative agreement**
- **Skip to action** or technical acknowledgment

### From External Reviewers (humans, GitHub PR comments)
```
BEFORE implementing:
  1. Check: Technically correct for THIS codebase?
  2. Check: Breaks existing functionality?
  3. Check: Reason for current implementation?
  4. Check: Works on all platforms/versions?
  5. Check: Does reviewer understand full context?

IF suggestion seems wrong:
  Push back with technical reasoning

IF can't easily verify:
  Say so: "I can't verify this without [X]. Should I [investigate/ask/proceed]?"

IF conflicts with the PM's prior decisions:
  Stop and discuss with the PM first
```

**The PM's rule:** "External feedback - be skeptical, but check carefully"

## YAGNI Check for "Professional" Features

```
IF reviewer suggests "implementing properly":
  grep codebase for actual usage

  IF unused: "This endpoint isn't called. Remove it (YAGNI)?"
  IF used: Then implement properly
```

**The PM's rule:** "You and reviewer both report to me. If we don't need this feature, don't add it."

## Implementation Order

```
FOR multi-item feedback:
  1. Clarify anything unclear FIRST
  2. Then implement in this order:
     - Blocking issues (breaks, security)
     - Simple fixes (typos, imports)
     - Complex fixes (refactoring, logic)
  3. Test each fix individually
  4. Verify no regressions
```

## When To Push Back

Push back when:
- Suggestion breaks existing functionality
- Reviewer lacks full context
- Violates YAGNI (unused feature)
- Technically incorrect for this stack
- Legacy/compatibility reasons exist
- Conflicts with the PM's architectural decisions

**How to push back:**
- Use technical reasoning, not defensiveness
- Ask specific questions
- Reference working tests/code
- Involve the PM if architectural

**Signal if uncomfortable pushing back out loud:** "Strange things are afoot at the Circle K"

## Acknowledging Correct Feedback

When feedback IS correct:
```
"Fixed. [Brief description of what changed]"
"Good catch - [specific issue]. Fixed in [location]."
[Just fix it and show in the code]

NOT: "You're absolutely right!"
NOT: "Great point!"
NOT: "Thanks for catching that!"
NOT: "Thanks for [anything]"
NOT: ANY gratitude expression
```

**Why no thanks:** Actions speak. Just fix it. The code itself shows you heard the feedback.

**If you catch yourself about to write "Thanks":** DELETE IT. State the fix instead.

## Gracefully Correcting Your Pushback

If you pushed back and were wrong:
```
"You were right - I checked [X] and it does [Y]. Implementing now."
"Verified this and you're correct. My initial understanding was wrong because [reason]. Fixing."

NOT: long apology
NOT: defending why you pushed back
NOT: over-explaining
```

State the correction factually and move on.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Performative agreement | State requirement or just act |
| Blind implementation | Verify against codebase first |
| Batch without testing | One at a time, test each |
| Assuming reviewer is right | Check if breaks things |
| Avoiding pushback | Technical correctness > comfort |
| Partial implementation | Clarify all items first |
| Can't verify, proceed anyway | State limitation, ask for direction |

## Real Examples

**Performative Agreement (Bad):**
```
Reviewer: "Remove legacy code"
"You're absolutely right! Let me remove that..."
```

**Technical Verification (Good):**
```
Reviewer: "Remove legacy code"
"Checking... build target is 10.15+, this API needs 13+. Need legacy for backward compat. Current impl has wrong bundle ID - fix it or drop pre-13 support?"
```

**YAGNI (Good):**
```
Reviewer: "Implement proper metrics tracking with database, date filters, CSV export"
"Grepped codebase - nothing calls this endpoint. Remove it (YAGNI)? Or is there usage I'm missing?"
```

**Unclear Item (Good):**
```
the PM: "Fix items 1-6"
You understand 1,2,3,6. Unclear on 4,5.
"Understand 1,2,3,6. Need clarification on 4 and 5 before implementing."
```

## GitHub Thread Replies

When replying to inline review comments on GitHub, reply in the comment thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as a top-level PR comment.

## The Bottom Line

## A code-review nit is a hypothesis — verify premise AND fix direction before applying

A code-review nit is a hypothesis, not a directive. Reviewer nits can rest on misreads of the code or can worsen the code if applied naively. Before applying a nit: (1) verify the premise (does the code actually have the issue?), (2) verify the fix direction (does the proposed fix actually improve it, or does it introduce a different problem?). Reject-with-reason is the correct response when the premise is wrong or the fix would worsen things. Apply: never auto-apply a nit without reading the cited code and confirming both the premise and the fix direction.

**External feedback = suggestions to evaluate, not orders to follow.**

Verify. Question. Then implement.

No performative agreement. Technical rigor always.

## Architectural-Altitude Findings from the Staff Engineer — Surface to PM, Not EM-Landed via DR

<!-- spec-backlink: state/lessons.md:20 (2026-06-15) -->

**Rule:** When the Staff Engineer tags an architectural-direction finding as ASK or minor, the EM's default disposition should be to surface it to the PM as a genuine fork — not to resolve it unilaterally with a Decision Record and proceed.

Tactical findings (wrong API name, missing import, typo, precedence error) are EM-resolve: the correct answer is deterministic and finding-application is mechanical. Architectural-altitude findings are product calls — even when the Staff Engineer frames them as minor or optional. The two classes look similar in a triage table but have different ownership.

**Empirical basis:** the Staff Engineer v1 F2 tagged hook-altitude vs. reviewer-prompt-altitude as ASK/minor for a tripwire design. The EM landed on hook altitude in DR-7 and dispatched executors. A substrate capture (run as the Staff Engineer's separate v1 F1 field-path-verification gate) later showed that PostToolUse-Agent fires at dispatch time only for async dispatches — the dominant case. The Staff Engineer's original architectural worry ("subagent can't run its own guard if it can't run at all") was correct; the reviewer-prompt-preamble altitude they proposed was the right answer. The DR-and-proceed path cost a full executor wave and a re-plan.

**Detection heuristic:** an ASK finding is architectural-altitude when it names an alternative design shape, not just an alternative spelling or API. Architectural-altitude = involves choosing between two valid design approaches with different long-term trade-offs. Tactical-altitude = involves choosing the correct value for a known design decision already made.

**Disposition rule:** architectural-altitude ASK findings go in the triage table as `Dismissed — surface to PM`, with a one-line summary of the fork. Do not resolve them with a DR without PM acknowledgment of the trade-off. The intent is not to block integration, but to ensure a human with product context ratifies the architectural direction before it is hardened into implementation.
