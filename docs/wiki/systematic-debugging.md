---
title: Systematic Debugging
system: systematic-debugging
status: distilled
distilled_from:
  - plugins/coordinator/skills/systematic-debugging/SKILL.md
  - plugins/coordinator/skills/systematic-debugging/root-cause-tracing.md
  - plugins/coordinator/skills/systematic-debugging/defense-in-depth.md
  - plugins/coordinator/skills/systematic-debugging/condition-based-waiting.md
distilled_at: 2026-05-06
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
5. **Trace data flow.** When the error is deep in the call stack: where does the bad value originate? What called this with a bad value? Keep tracing up until you find the source. Fix at source, not at symptom. See [Backward Tracing](#backward-tracing-finding-the-original-trigger) below for the full backward tracing technique.

#### Step 3: Form 3–5 ranked falsifiable hypotheses before testing any

Single-hypothesis generation anchors on the first plausible idea. Resist it.

Generate 3–5 candidate hypotheses. Rank them by plausibility. Each hypothesis MUST complete this form:

> *"If \<X\> is the cause, then \<changing Y\> will make the bug disappear."*

If you cannot state the prediction — the hypothesis is a vibe. Discard it or sharpen it until it becomes testable. Show the ranked list before testing: the PM or another engineer often has domain knowledge that re-ranks instantly ("we just deployed a change to #3") or knows hypotheses already ruled out. Cheap checkpoint, big time saver.

**Do not proceed to Phase 2 until you have a loop you believe in and at least 3 ranked falsifiable hypotheses.**

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

1. **Create a failing test case.** Simplest reproduction. Automated if possible. MUST have before fixing. Apply `docs/wiki/test-driven-development.md`.
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

## Diagnose before mitigating — do not write architectural plans for unknown root causes

**Do not author an implementation plan for a failure class whose root cause is still unknown. Sequence evidence collection before design.**
**Why:** A plan drafted against a wrong premise (e.g., "VRAM saturation") becomes debt the moment real evidence lands. One session produced ~290 lines of "host-level VRAM guardrail" plan before a kernel-level event named a non-GPU Python process consuming 217 GB virtual — the plan was discarded unbuilt rather than retrofitted on wrong premises.
**How to apply:** run WMI / log / kernel-event diagnostics first → identify the actual offender → THEN design the fix. Premature mitigation plans mislead future readers and waste reviewer cycles on a plan the facts already contradict.

*Source: example-game-repo `state/lessons.md` (example-game-repo-L135, central-promoted 2026-05-28).*

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
| "The checker / lint is broken — look how it flags this fixture" | When a checker/lint fails on test fixtures or synthetic inputs, the first hypothesis is test-data degeneracy (fixture lacks a required field, was generated by an older shape, the synthetic input drifted). Fix the inputs or extend the whitelist inline BEFORE rewriting the checker. Rewriting a working checker to accept degenerate data is a recurring time-sink. |

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

**Test data degeneracy ≠ checker bug.** When a checker flags inputs your test fixture provided, fix the inputs or extend the whitelist inline. Don't blame the checker for catching what you fed it.

**Iteration-debugging signal is failure-mode shift, not failure count.** Same failure count with a different failure class is progress; track the class, not the integer.

## Debug Posture — Workarounds, Gates, and Refactor Leverage

These recipes name failure modes that recur across debugging sessions and the posture corrections that close them.

### Read code before walking process

Before invoking the debugging *process* (build a loop, form hypotheses, dispatch a scout), read the cited code path end-to-end. A four-minute read on the producer often collapses a multi-hour hypothesis chain — the bug is visible in the source, not in the symptom telemetry. Process is the fallback when the code read doesn't resolve it, not the entry point.

### Workarounds named for the wrong flag are bug-shaped

When a workaround uses an *incidental* flag (a behaviour-adjacent toggle that happens to suppress the symptom) instead of the *named contract* (the documented switch for this case), the workaround leaves the original bug live and adds a second one. Audit: does the flag's documented purpose actually describe what you're using it for? If not, find the named-contract flag or fix the underlying defect — don't ship the wrong-named lever.

### Bypassing one gate ≠ done — trace the full path

A failing gate is one node in a chain. Disabling, bypassing, or whitelisting past it does not validate that the *next* gate accepts the input. After any bypass-style fix, re-run the full path from entry to terminal effect; the symptom often re-surfaces two layers downstream where a quieter assertion now fails. "The gate stopped complaining" is not "the operation succeeded."

### Structural refactor as bug-closing leverage

When 3+ symptom fixes have failed in the same module, the cheapest *next* move is often a structural refactor — extracting the tangled state, narrowing the API, or splitting the responsibility — not a fourth symptom patch. The refactor closes whole classes of bugs (including the one you're chasing) by making the broken shape representable only as a compile/type error. Treat "we keep patching this" as a routing signal to refactor, not a count toward give-up.

### Test + handler are one unit — read both

When a test fails, read the test *and* the handler/producer/fixture it exercises in the same pass. Reading only one half routinely misattributes the bug: a test that "looks wrong" is often correctly exercising a broken handler, and a handler that "looks correct" is often built against a stale fixture shape. The pair is the unit of diagnosis.

### Exit codes are a truthful contract — believe them

Subprocess exit codes (and the structured-report fields they correspond to: `returncode`, `success: false`, non-zero `status`) are the cheapest ground-truth signal in the system. When a wrapper script reports success but the wrapped tool exited non-zero, the wrapper is lying — fix the wrapper, don't dismiss the exit code. Conversely, an exit-zero from a tool that should have failed is a contract bug worth its own investigation. Don't normalise exit codes away in reporting layers.

### Large unsigned exit codes may be signed –1, not a native crash

A subprocess that exits with code `4294967295` (0xFFFFFFFF) is reporting a signed –1 reinterpreted as an unsigned 32-bit value — not an SEH exception or native crash. Before concluding that a large unsigned exit code signals an unhandled structured exception, grep the subprocess's stdout/stderr logs for the real error: a Python traceback, a structured error message, or a logged exception will name the actual failure class. The OS surface (`returncode = 4294967295`) is accurate; the *interpretation* (crash vs. deliberate non-zero exit) requires the logs. Concrete example: UE Commandlet processes return `Commandlet->Main()` exit –1 as their error path; project-rag's F-NEW-5 was misclassified as an SEH crash for two release cycles before a debug-capture run surfaced a `TypeError` traceback at the Python layer.

*Source: example-sim-repo `state/lessons.md` (L8, central-promoted 2026-05-29).*

### No live diagnostic tracers that harm the host

Diagnostic instrumentation that mutates host state — flushing caches, restarting services, taking exclusive locks, writing to shared logs, holding the GIL — is not a diagnostic. It's a second incident. Read-only probes only (`get_*`, `inspect`, stat captures, structured logs). If you need a host-modifying probe, gate it behind explicit PM approval and treat it as a planned mutation, not a debug step. The classic failure mode: a tracer that "just dumps the state" pauses the game thread for 30s and the symptom you were chasing turns out to be the tracer.

### Empirical iteration converges; pure analysis doesn't

When a bug resists analysis-first attack (read code, form hypotheses, propose fix), switch to short empirical loops: run, observe, adjust, re-run. Each iteration narrows the failure class even when no individual run pinpoints the cause. Treat the loop count as a budget (3–5 iterations) and the failure-class shift (above) as the convergence signal. Analysis-only sessions on under-instrumented bugs are a stuck-detection trigger.

### Ship the fix without the full root cause when the symptom is bounded

Not every bug needs a complete root-cause story before the fix lands. When (a) the symptom is bounded (specific path, specific input class, specific environment), (b) the fix is narrow and reversible, and (c) the cost of continued investigation exceeds the cost of shipping with a partial-cause note — ship the fix, note the residual mystery in the commit/PR body, and move on. The Iron Law applies to *guess-and-check fix chains*, not to bounded-scope fixes with documented residuals. Don't conflate "no full root cause" with "no understanding."

---

## Supporting Techniques

The three sub-sections below were previously sibling files (`root-cause-tracing.md`, `defense-in-depth.md`, `condition-based-waiting.md`) inside the now-demoted `skills/systematic-debugging/` directory. They live here as deeper detail referenced from the phases above.

### Backward Tracing — Finding the Original Trigger

Bugs often manifest deep in the call stack (git init in wrong directory, file created in wrong location, database opened with wrong path). Your instinct is to fix where the error appears, but that's treating a symptom.

**Core principle:** Trace backward through the call chain until you find the original trigger, then fix at the source.

**Use when:** error happens deep in execution (not at entry point); stack trace shows a long call chain; unclear where invalid data originated; need to find which test/code triggers the problem.

#### The Tracing Process

1. **Observe the symptom** — `Error: git init failed in /home/dev/project/packages/core`.
2. **Find immediate cause.** What code directly causes this?
   ```typescript
   await execFileAsync('git', ['init'], { cwd: projectDir });
   ```
3. **Ask: what called this?**
   ```
   WorktreeManager.createSessionWorktree(projectDir, sessionId)
     → Session.initializeWorkspace()
     → Session.create()
     → test at Project.create()
   ```
4. **Keep tracing up.** What value was passed?
   - `projectDir = ''` (empty string!) — empty string as `cwd` resolves to `process.cwd()` (the source code directory).
5. **Find the original trigger.** Where did the empty string come from?
   ```typescript
   const context = setupCoreTest();         // Returns { tempDir: '' }
   Project.create('name', context.tempDir); // Accessed before beforeEach!
   ```

#### Adding Stack Traces When Manual Tracing Fails

```typescript
async function gitInit(directory: string) {
  const stack = new Error().stack;
  console.error('DEBUG git init:', {
    directory,
    cwd: process.cwd(),
    nodeEnv: process.env.NODE_ENV,
    stack,
  });
  await execFileAsync('git', ['init'], { cwd: directory });
}
```

**Critical:** Use `console.error()` in tests (not logger — may not show).

```bash
npm test 2>&1 | grep 'DEBUG git init'
```

Analyze stack traces by looking for test file names, finding the line number triggering the call, identifying the pattern (same test? same parameter?).

#### Finding Which Test Causes Pollution

If something appears during tests but you don't know which test, use the bisection script `find-polluter.sh`:

```bash
~/.claude/plugins/coordinator/bin/find-polluter.sh '.git' 'src/**/*.test.ts'
```

Runs tests one-by-one, stops at first polluter. See the script for usage.

#### Real Example — Empty `projectDir`

**Symptom:** `.git` created in `packages/core/` (source code).

**Trace chain:** `git init` runs in `process.cwd()` ← empty cwd parameter → WorktreeManager called with empty projectDir → Session.create() passed empty string → test accessed `context.tempDir` before `beforeEach` → `setupCoreTest()` returns `{ tempDir: '' }` initially.

**Root cause:** Top-level variable initialization accessing empty value.

**Fix:** Made `tempDir` a getter that throws if accessed before `beforeEach`. Then added defense-in-depth (next section).

#### Key Principle

**NEVER fix just where the error appears.** Trace back to find the original trigger. When you can trace one level up, do — only stop when this is genuinely the source. Then add validation at each layer (defense-in-depth) so the bug becomes structurally impossible.

#### Stack Trace Tips

- **In tests:** use `console.error()`, not the logger — logger may be suppressed.
- **Before operation:** log before the dangerous operation, not after it fails.
- **Include context:** directory, cwd, environment variables, timestamps.
- **Capture stack:** `new Error().stack` shows the complete call chain.

### Defense-in-Depth — Validation at Every Layer

When you fix a bug caused by invalid data, adding validation at one place feels sufficient. But that single check can be bypassed by different code paths, refactoring, or mocks.

**Core principle:** Validate at EVERY layer data passes through. Make the bug structurally impossible.

Single validation: "We fixed the bug." Multiple layers: "We made the bug impossible." Different layers catch different cases — entry validation catches most bugs, business logic catches edge cases, environment guards prevent context-specific dangers, debug logging helps when other layers fail.

#### The Four Layers

**Layer 1 — Entry Point Validation.** Reject obviously invalid input at the API boundary.
```typescript
function createProject(name: string, workingDirectory: string) {
  if (!workingDirectory || workingDirectory.trim() === '') {
    throw new Error('workingDirectory cannot be empty');
  }
  if (!existsSync(workingDirectory)) {
    throw new Error(`workingDirectory does not exist: ${workingDirectory}`);
  }
  if (!statSync(workingDirectory).isDirectory()) {
    throw new Error(`workingDirectory is not a directory: ${workingDirectory}`);
  }
  // ... proceed
}
```

**Layer 2 — Business Logic Validation.** Ensure data makes sense for this operation.
```typescript
function initializeWorkspace(projectDir: string, sessionId: string) {
  if (!projectDir) {
    throw new Error('projectDir required for workspace initialization');
  }
  // ... proceed
}
```

**Layer 3 — Environment Guards.** Prevent dangerous operations in specific contexts.
```typescript
async function gitInit(directory: string) {
  // In tests, refuse git init outside temp directories
  if (process.env.NODE_ENV === 'test') {
    const normalized = normalize(resolve(directory));
    const tmpDir = normalize(resolve(tmpdir()));
    if (!normalized.startsWith(tmpDir)) {
      throw new Error(`Refusing git init outside temp dir during tests: ${directory}`);
    }
  }
  // ... proceed
}
```

**Layer 4 — Debug Instrumentation.** Capture context for forensics.
```typescript
async function gitInit(directory: string) {
  const stack = new Error().stack;
  logger.debug('About to git init', {
    directory,
    cwd: process.cwd(),
    stack,
  });
  // ... proceed
}
```

#### Applying the Pattern

When you find a bug:

1. **Trace the data flow** — where does the bad value originate? Where used?
2. **Map all checkpoints** — list every point data passes through.
3. **Add validation at each layer** — entry, business, environment, debug.
4. **Test each layer** — try to bypass layer 1, verify layer 2 catches it.

#### Key Insight

All four layers are typically necessary. Different code paths bypass entry validation; mocks bypass business logic; edge cases on different platforms need environment guards; debug logging identifies structural misuse the other layers missed.

**Don't stop at one validation point.** Add checks at every layer.

### Condition-Based Waiting — Replacing Arbitrary Timeouts

Flaky tests often guess at timing with arbitrary delays. This creates race conditions where tests pass on fast machines but fail under load or in CI.

**Core principle:** Wait for the actual condition you care about, not a guess about how long it takes.

**Use when:** tests have arbitrary delays (`setTimeout`, `sleep`, `time.sleep()`); tests are flaky (pass sometimes, fail under load); tests time out when run in parallel; waiting for async operations to complete.

**Don't use when:** testing actual timing behavior (debounce, throttle intervals). Always document WHY if using an arbitrary timeout.

#### Core Pattern

```typescript
// ❌ BEFORE: Guessing at timing
await new Promise(r => setTimeout(r, 50));
const result = getResult();
expect(result).toBeDefined();

// ✅ AFTER: Waiting for condition
await waitFor(() => getResult() !== undefined);
const result = getResult();
expect(result).toBeDefined();
```

#### Quick Patterns

| Scenario | Pattern |
|----------|---------|
| Wait for event | `waitFor(() => events.find(e => e.type === 'DONE'))` |
| Wait for state | `waitFor(() => machine.state === 'ready')` |
| Wait for count | `waitFor(() => items.length >= 5)` |
| Wait for file | `waitFor(() => fs.existsSync(path))` |
| Complex condition | `waitFor(() => obj.ready && obj.value > 10)` |

#### Implementation

Generic polling function:

```typescript
async function waitFor<T>(
  condition: () => T | undefined | null | false,
  description: string,
  timeoutMs = 5000
): Promise<T> {
  const startTime = Date.now();

  while (true) {
    const result = condition();
    if (result) return result;

    if (Date.now() - startTime > timeoutMs) {
      throw new Error(`Timeout waiting for ${description} after ${timeoutMs}ms`);
    }

    await new Promise(r => setTimeout(r, 10)); // Poll every 10ms
  }
}
```

See `~/.claude/plugins/coordinator/examples/condition-based-waiting-example.ts` for a complete implementation with domain-specific helpers (`waitForEvent`, `waitForEventCount`, `waitForEventMatch`) from an actual debugging session. The example uses generic, self-contained types (`Event`, `EventType`, `EventManager`) with no external imports — copy it directly into any project and substitute your own event type values.

#### Common Mistakes

- **❌ Polling too fast:** `setTimeout(check, 1)` — wastes CPU. **✅ Fix:** Poll every 10ms.
- **❌ No timeout:** loop forever if condition never met. **✅ Fix:** always include timeout with clear error.
- **❌ Stale data:** caching state before the loop. **✅ Fix:** call the getter inside the loop for fresh data.

#### When Arbitrary Timeout IS Correct

```typescript
// Tool ticks every 100ms — need 2 ticks to verify partial output
await waitForEvent(manager, 'TOOL_STARTED'); // First: wait for condition
await new Promise(r => setTimeout(r, 200));   // Then: wait for timed behavior
// 200ms = 2 ticks at 100ms intervals — documented and justified
```

Requirements: (1) first wait for the triggering condition, (2) base the timeout on known timing (not guessing), (3) comment explaining WHY.

---

## Real-World Impact

Systematic approaches typically resolve issues in a single pass; guess-and-check approaches frequently require multiple sessions and introduce regressions. From a 2025-10-03 debugging session: a 5-level backward trace identified the root cause; a getter-validation fix at source closed the trigger; defense-in-depth added 4 validation layers; 1847 tests passed with zero pollution. From the same arc: 15 flaky tests across 3 files migrated to condition-based waiting — pass rate 60% → 100%, execution 40% faster, no race conditions.

## Clean-Environment Prerequisite for Performance Diagnoses

**A performance diagnosis taken while zombie processes or competing daemons contend is contaminated — profile under a clean process environment before trusting the premise.**

Concrete failure: two handoffs reported full-suite collection at 1230s (20.5 min) and prescribed a collection refactor; profiling found collection was actually ~4s — the 1230s was contention from 5 abandoned `pytest tests/` processes + a `tool_dogfood` test spawning the project-rag daemon (43 GB commit-leak). The real fixes were unrelated to the diagnosed cause (retry-storm fast-fail, IPv4, marker-deselecting heavy substrate tests).

Rule: `ps`/process-list + a clean re-run BEFORE trusting any perf number in a handoff. A newly-runnable test tier surfaces pre-existing failures the prior avoidance was hiding — expect and triage them, don't assume they're your regression. (Source: project-rag-ue-addon L57)

## Schema Migration and Dedup Patterns

**Mixed-separator dedup is FK-aware, not a single REPLACE.**

Two tables affected by the same root-cause bug need two different migrations: a no-collision column is a simple REPLACE; a TEXT PRIMARY KEY column is a collision-aware dedup-then-update because the key compresses rows that differ only in separator. Safe order: (1) inspect FK relationships, (2) DELETE loser rows from collision groups first, (3) UPDATE keepers to normalized form — never UPDATE before DELETE. (Source: example-game-repo L13)

**When normalizing one path column, inventory ALL path-typed columns across ALL tables before declaring done.**

Patching one column without auditing siblings leaves live consumer join paths silently broken — the AC table can pass clean because it uses LIKE predicates that don't care about separators. Before closing any separator/normalization patch, run `SELECT name FROM sqlite_master WHERE type='table'` and for each table run `PRAGMA table_info(t)` to identify every TEXT column with path semantics; apply the same normalization in the same commit. (Source: example-game-repo L53)

## Audit Your Own Fix for the Bug Class You Just Fixed

**When fixing a cwd-relative or path-resolution bug, the fix's own path references are the first thing to check.** The failure mode of a fix reintroducing the bug it fixes is a recurring AI-authoring pattern — a replacement script that calls `bin/helper.sh` (cwd-relative) to eliminate a different cwd-relative call reproduces the identical silent no-op. Grep your replacement for the same relative-path shape you are removing; use authoritative absolute paths or `$(dirname "$0")`-anchored resolution in the fix itself.

**How to apply:** before submitting any path-resolution fix for review, run `grep -nE '(^\./|^bin/|^scripts/)' <new-file>` (or equivalent) to enumerate relative path references in the replacement. Each hit is a candidate for the same bug. This self-audit is fastest and cheapest before a reviewer catches it.

*Source: meta-repo `state/lessons.md` (central-promoted 2026-05-29).*

## flaky process crash resisting code-layer fixes — rate-measure then fix at gate layer

A flaky test-PROCESS crash (hard abort, no traceback) that resists code-layer fixes is upstream of the code — it is a gate-layer problem (process isolation, spawn flags, resource limits). Before escalating to architectural changes: measure the crash rate (N/M runs) before AND after each candidate fix. If the rate does not improve after 3 code-layer candidates, the locus is the gate layer (spawn flags, isolation wrapper, OS resource limit). Apply: quantify the crash rate first; treat "rate unchanged after code fix" as evidence of wrong locus.

## An Audit/Dogfood That Names a Broken Symptom Names a Probe, Not a Fix-Locus

When an audit or dogfood run reports a named probe or command as BROKEN, that names the **symptom surface**, not necessarily the code path that produces it. There may be multiple resolvers of that symptom, and the plan's cited helper may not be the one the symptom flows through.

**Rule:** when a finding cites a failing probe/command, grep for ALL code paths that produce that symptom before pinning the fix-locus. Runtime-verify the *named* probe post-fix — a fix that targets a different resolver leaves the named probe still broken. Sister to the fix-locus-discrimination principle in CLAUDE.md § Pre-Dispatch Verification ("Audit symptom is correct; locus may be wrong").

**Empirical basis (2026-06-18, example-game-workbench-repo):** macOS dogfood HF3 reported `check_machine_local_registry` BROKEN; the plan fixed `_machine_local_get` (a *different* machine-local resolver) and the symptom probe stayed broken — caught only by C5 runtime verification, not plan review.

*(Source: example-game-repo-L120, central-promoted 2026-06-20.)*

## A Test/Reviewer Claim of "Code Exits 0 / Returns Wrong Value" Can Be a Test-Harness Artifact

Before editing production code to satisfy a failing test or reviewer's "it returns X" claim, **reproduce the behavior in isolation** — if production is correct standalone, the bug is in the harness, not the code. Corollary: a shell helper that returns a result via a **global variable** is silently broken when callers wrap it in `out=$(fn ...)` — the global mutation happens in the command-substitution subshell and never reaches the parent.

**Rule:** (1) before fixing production to satisfy a test or reviewer-claimed runtime value, run a direct 12-line repro outside the harness and compare. (2) Never communicate a result from a shell helper via a global when callers may use `$(...)` — return it, write it to a file (files survive subshells), or print it on a sentinel line.

**Empirical basis (2026-06-19, example-game-workbench-repo):** a code-reviewer reported `example_game_repo_recover.sh --step reverse-drift` exiting 0 on a halt (spec: 1), diagnosed as two production bugs. Direct repro gave exit **1** — production was correct. Root cause: `run_recover_mock` set `_LAST_RC=$_rc` while every caller ran `out=$(run_recover_mock ...)`, so `_LAST_RC` was set in the subshell and the parent read the stale `0`. One of the reviewer's two findings was a phantom caused by the harness. Pairs with the P0/P1 verification gate and tool-output-flakiness ("don't infer from a single read").

*(Source: example-game-repo-L174, central-promoted 2026-06-20.)*

## Read the captured crash traceback before trusting a static file:line diagnosis of a daemon crash

For a won't-bind / crashloop daemon, a static source trace produces confident-but-wrong root causes — one session generated four hypotheses, all excluded, before the operator read the actual captured traceback (the crashloop giveup sentinel / daemon stderr log) and found the real cause in one step.

**Rule:** for runtime crash diagnosis of a daemon or backgrounded process, get the **captured traceback first** — the giveup sentinel, the crashloop stderr log, the last-run capture. Static file:line tracing is a fallback, not the primary. This is the daemon-crash instance of § Ground Truth Beats Derived Signals: the traceback is the ground truth; the static trace is a derived signal.

*Source: project-rag.*

## A NOT-NULL / schema-mismatch insert bug usually has SIBLING writer sites — grep every writer of the table

When an insert bug is a schema-mismatch (omitting a NOT-NULL column, wrong column set), the site you fix is rarely the only one. Fixing the obvious per-row inserter leaves sibling writers — staging→output `INSERT-SELECT`s, band-swap copies, bulk migrators — with the identical omission, and they surface only later when a different test exercises that path.

**Rule:** on any NOT-NULL / schema-mismatch insert fix, `grep` **every writer** of the affected table (every `INSERT`, `INSERT-SELECT`, and `REPLACE` naming it), not just the inserter the failure pointed at, and apply the fix to all of them in the same change. Sister to § Audit Your Own Fix for the Bug Class You Just Fixed and to the DB/indexer "inventory ALL path-typed columns" rule in `implementation-standards-by-domain.md`.

*Source: project-rag.*

## Reference

- **Aux script:** `~/.claude/plugins/coordinator/bin/find-polluter.sh` — bisection-based test polluter finder.
- **Aux example:** `~/.claude/plugins/coordinator/examples/condition-based-waiting-example.ts` — concrete `waitFor` helpers from a real debugging session.
- **Related doctrine:** [test-driven-development](test-driven-development.md), [verification-before-completion](verification-before-completion.md), [stuck-detection](stuck-detection.md).
