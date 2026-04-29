---
name: systematic-debugging
description: "This skill should be used when encountering any bug, test failure, or unexpected behavior — before proposing fixes. Triggers on: 'something is broken', 'test is failing', 'unexpected behavior', 'debug this'."
version: 1.0.0
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## When to Use

For ANY technical issue: test failures, bugs, unexpected behavior, performance problems, build failures, integration issues.

**Especially when:** under time pressure (emergencies make guessing tempting), "just one quick fix" seems obvious, you've already tried multiple fixes, previous fix didn't work, you don't fully understand the issue.

**Don't skip when:** issue seems simple (simple bugs have root causes too), you're in a hurry (rushing guarantees rework), manager wants it fixed NOW (systematic is faster than thrashing).

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Build the Feedback Loop

**This is the skill. Everything else is mechanical.**

If you have a fast, deterministic, agent-runnable pass/fail signal for the bug, you will find the cause. If you don't have one, no amount of staring at code will save you. Spend disproportionate effort here. Be aggressive. Be creative. Refuse to give up.

A 2-second deterministic loop is a debugging superpower. A 30-second flaky loop is barely better than no loop. Treat the loop itself as a product — once you have one, ask: can it be faster? Sharper signal? More deterministic?

**Do not proceed to Phase 2 until you have a loop you believe in.**

#### Step 1: Build the feedback loop

Try techniques in this order — cheapest and most common first. If rung N doesn't fit, drop to rung N+1:

1. **Failing test** — a unit or integration test that reproduces the bug deterministically. Best outcome. Try this first.
2. **curl / HTTP probe** — for network/API bugs, a single curl command that demonstrates the bad response.
3. **CLI fixture** — a command-line invocation with fixed inputs that reliably triggers the failure.
4. **Headless browser** — for UI bugs where the DOM state is the signal; Playwright/Puppeteer script that captures the failure.
5. **Trace replay** — capture a request/event trace, replay it in isolation. Good for distributed or async bugs.
6. **Throwaway harness** — a small scratch script that wires just enough of the system to expose the failure.
7. **Fuzz** — property-based or random input generation to locate the minimal triggering input.
8. **Bisection** — `git bisect` or binary search across config/data space to find the first broken state.
9. **Differential** — run the same path against two environments (working vs. broken, old version vs. new) and diff the outputs.
10. **HITL bash** — last resort: a structured script that drives a human through precise steps and captures their observations. Even then, structure the interaction so the loop is repeatable.

If you genuinely cannot build a loop — stop. Do not proceed to hypothesise. State explicitly what was tried, ask for env access, a captured artifact, or permission to instrument.

#### Step 2: Read, reproduce, and gather evidence

1. **Read error messages carefully.** Don't skip past errors. Read stack traces completely. Note line numbers, file paths, error codes.
2. **Reproduce consistently.** Can you trigger it reliably? What are the exact steps? If not reproducible → raise the reproduction rate; don't try to make a flaky bug deterministic, just make it frequent enough to diagnose.
3. **Check recent changes.** Git diff, recent commits, new dependencies, config changes, environmental differences.
4. **Gather evidence in multi-component systems.** When the system has multiple components (CI → build → signing, API → service → DB), add diagnostic instrumentation at each component boundary BEFORE proposing fixes — log data entering and exiting each component, verify env/config propagation, check state at each layer. Run once to see WHERE it breaks, then investigate that specific component. A single diagnostic pass beats hypothesis ping-pong.
5. **Trace data flow.** When the error is deep in the call stack: where does the bad value originate? What called this with a bad value? Keep tracing up until you find the source. Fix at source, not at symptom. See `root-cause-tracing.md` for the full backward tracing technique.

#### Step 3: Form 3–5 ranked falsifiable hypotheses before testing any

Single-hypothesis generation anchors on the first plausible idea. Resist it.

Generate 3–5 candidate hypotheses. Rank them by plausibility. Each hypothesis MUST complete this form:

> *"If \<X\> is the cause, then \<changing Y\> will make the bug disappear."*

If you cannot state the prediction — the hypothesis is a vibe. Discard it or sharpen it until it becomes testable. Show the ranked list before testing: the PM or another engineer often has domain knowledge that re-ranks instantly ("we just deployed a change to #3") or knows hypotheses already ruled out. Cheap checkpoint, big time saver.

**Do not proceed to Phase 2 until you have a loop you believe in and at least 3 ranked falsifiable hypotheses.**

<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
**If MCP tools matching `mcp__*project-rag*` are available in this session, prefer them over grep/Explore for any code-shaped lookup.** Symbol-shaped questions ("where is X defined", "find the function that does Y") → `project_cpp_symbol` / `project_semantic_search`. Subsystem-shaped questions ("how does X work") → `project_subsystem_profile`. Impact questions ("what breaks if I change X") → `project_referencers` with depth=2. Stale RAG still beats grep on structure. Fall through to grep/Explore only if RAG returns nothing AND staleness is plausible.
<!-- END project-rag-preamble -->

### Phase 2: Pattern Analysis

1. **Find working examples** — locate similar working code in the same codebase.
2. **Compare against references** — if implementing a pattern, read the reference COMPLETELY. Don't skim.
3. **Identify differences** — list every difference, however small. Don't assume "that can't matter."
4. **Understand dependencies** — what other components, settings, env, assumptions does this need?

### Phase 3: Hypothesis and Testing

1. **Work from your ranked list (Phase 1 Step 3).** Take the top-ranked falsifiable hypothesis. State it: "I think X is the root cause because Y — if true, changing Z will make the bug disappear." Be specific.
2. **Test minimally.** Smallest possible change. One variable at a time.
3. **Verify before continuing.** Worked → Phase 4. Didn't work → strike that hypothesis, take the next one from the ranked list. Don't add more fixes on top.
4. **When you don't know, say so.** Don't pretend. Ask, research.

### Phase 4: Implementation

1. **Create a failing test case.** Simplest reproduction. Automated if possible. MUST have before fixing. Use `coordinator:test-driven-development`.
2. **Implement a single fix.** Address the root cause. ONE change. No "while I'm here" improvements.
3. **Verify fix.** Test passes? Other tests still pass? Issue actually resolved?
4. **If fix doesn't work — STOP.** Count attempts: <3 → return to Phase 1 with new info. ≥3 → question architecture (step 5). Don't attempt fix #4 without architectural discussion.
5. **If 3+ fixes failed: question architecture.** Patterns indicating an architectural problem: each fix reveals new shared state/coupling in a different place; fixes require "massive refactoring"; each fix creates new symptoms elsewhere. STOP and ask: is this pattern fundamentally sound, or are we sticking with it through inertia? Discuss with the PM. This is NOT a failed hypothesis — it's a wrong architecture.

## Red Flags — STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "It's probably X, let me fix that"
- "Pattern says X but I'll adapt it differently"
- Proposing solutions before tracing data flow
- "One more fix attempt" (when already tried 2+)
- Each fix reveals a new problem in a different place

All of these mean: STOP. Return to Phase 1.

## PM Signals You're Doing It Wrong

"Is that not happening?" / "Will it show us...?" / "Stop guessing" / "Ultrathink this" / "We're stuck?" — when you see these, return to Phase 1.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic is FASTER than guess-and-check. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write the test after confirming fix works" | Untested fixes don't stick. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question pattern, don't fix again. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| 1. Feedback Loop | Build loop, gather evidence, 3–5 falsifiable hypotheses | Loop you believe in + ranked hypotheses |
| 2. Pattern | Find working examples, compare | Identify differences |
| 3. Hypothesis | Form theory, test minimally | Confirmed or new hypothesis |
| 4. Implementation | Create test, fix, verify | Bug resolved, tests pass |

## When Process Reveals "No Root Cause"

If investigation reveals the issue is truly environmental, timing-dependent, or external: document what you investigated, implement appropriate handling (retry, timeout, error message), add monitoring. **But: 95% of "no root cause" cases are incomplete investigation.**

## Data Before Dispatch

Before dispatching agents on a debug/fix task, identify and run the smallest diagnostic that exposes ground truth — a test runner, curl probe, `git show`, single inspect call. Target <60 seconds. Measured data beats speculation: a 20-second `pnpm test:unit` once identified 3 of 9 misdiagnosed root cause categories; a single `curl + getent hosts + ss -tlnp` identified two root causes that multiple hypothesis-driven commits had failed to isolate.

**Rule:** Hypothesis-driven dispatch without first running a diagnostic is a stuck-detection trigger. If the fix plan contains "the cause is probably X" without a supporting diagnostic, stop and get the data.

## Ground Truth Beats Derived Signals

Prefer the cheapest direct read of the system's source-of-truth over reasoning from derived/secondary signals:

- **Empirical audit before fix code.** When a reviewer mandates a specific mechanism, audit that the mechanism applies before any fix code lands. A one-hour audit beats a half-day of wrong-fix code.
- **Cheap N-way diagnostic before any single fix.** When N tools might be broken, ship the per-symptom reporter that surfaces all N states at once, then dispatch with data.
- **Trust the original log, not the derived timing claim.** Cross-reference the upstream/server-side log directly rather than trusting timing inferences from downstream. A "client timeout" hypothesis from the Node side may actually be game-thread blockage from the editor side; fixing the wrong layer wastes a session.

**The unifying check before any fix:** "What's the cheapest read of the system that would directly confirm or refute my hypothesis?" If <5 minutes, do it before writing fix code.

## Supporting Techniques

In this directory:
- `root-cause-tracing.md` — backward tracing through call stack
- `defense-in-depth.md` — validation at multiple layers post-root-cause
- `condition-based-waiting.md` — replace arbitrary timeouts with condition polling

**Related skills:** `coordinator:test-driven-development` (Phase 4 step 1), `coordinator:verification-before-completion`.

## Real-World Impact

Systematic approaches typically resolve issues in a single pass; guess-and-check approaches frequently require multiple sessions and introduce regressions.
