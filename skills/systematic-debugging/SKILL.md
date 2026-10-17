---
name: systematic-debugging
description: "Root-cause one known bug: reproduce, trace, fix, verify."
version: 1.0.0
triggers:
  - /systematic-debugging
  - debug this
  - chase down this bug
  - track down this issue
  - why is X failing
  - root cause this
  - this test keeps failing
  - it works sometimes
argument-hint: "<the symptom, or a path/error to start from>"
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# /systematic-debugging — Root-Cause Discipline for a Single Issue

Walk one identified failure to its root cause and fix it there. The fastest fix that *actually holds* starts by finding the cause: every wrong patch adds a variable and can mask the real one.

**This is the single-issue tool.** You have a specific symptom in hand. Siblings:
- **`/bug-sweep`** — searches the whole repo for unknown bugs (broad, discovery).
- **`/bug-blitz`** — grinds a known backlog of many bugs (broad, batch).
- **`/dogfood`** — exercises a newly-built thing until it works (broad, shakedown).
- **`/systematic-debugging`** — one known failure, traced to root cause and fixed (narrow, depth).

Holding more than one unrelated symptom: use a sibling. Exactly one: you're in the right place.

**Announce at start:** "Running `/systematic-debugging` on <symptom> — pinning the premise before I touch anything."

## When this earns its keep

Any single technical issue where the cause isn't yet *known* (not merely suspected): test failure, runtime bug, build break, flaky behavior, perf cliff, integration mismatch. It earns the most under the conditions that make guessing tempting — time pressure, a fix that "looks obvious," a previous patch that didn't take, or a borrowed root cause from someone else's repo.

Skip it when the cause is already proven (just fix it) or you have a *pile* of issues (sweep/blitz).

## Phase 0 — Pin the premise (the cheap step everyone skips)

Confirm the bug you're chasing is the bug that exists (~2 minutes).

1. **Is it still broken on HEAD?** Stale dogfood logs, predecessor handoffs, and backlog entries may describe already-fixed state. `git log --oneline -- <cited-paths>` since the report's date, then re-run the failing case on current HEAD. An unverified "broken today" is a hypothesis, not a signal.
2. **Is the root cause borrowed?** A cause from a handoff, a cross-repo memo, or another repo's diagnosis is *hypothesis, not ground truth*. Read the cited code on your own disk before acting; a matching symptom does not imply a matching cause.
3. **Is the signal real?** Tool output that was empty, garbled, or contradictory may mean the channel failed, not the code. Re-read once, solo. Two reads disagreeing → read a third way.

If Phase 0 dissolves the bug (already fixed / not reproducible here / phantom signal), say so and stop.

## Phase 1 — Reproduce and read the evidence

1. **Reproduce reliably.** Get a reliable repro before forming theories. Exact steps; does it fire every time? Without an on-demand trigger you're gathering data, not debugging.
2. **Read the error completely.** The build/error stream is the contract: stack traces, line numbers, codes, the *whole* trace. → coordinator CLAUDE.md § Investigation funnel.
3. **Instrument the boundaries in multi-component systems.** When the failure crosses layers (CI → build → sign, request → service → DB, MCP → daemon → editor), log what enters and exits each boundary and run **once** to see *which* layer breaks before theorizing.
4. **Check what changed.** `git diff` / recent commits / new deps / config drift. The delta is the highest-prior suspect.

## Phase 2 — Trace to the source, discriminate the locus

The bug usually *appears* far from where it *originates*. Fixing where the error surfaces is symptom-patching.

1. **Trace backward.** Ask "what passed this bad value / state?" and walk up the call chain to the original trigger. When reading isn't enough, log a stack trace right before the failing operation.
2. **Discriminate symptom-locus from root-locus.** Name both: where it *manifests* vs. where it *originates*. A reporter is usually right about the symptom and can be wrong about the locus — verify the producing code before accepting any fix-site. → coordinator CLAUDE.md § Audit symptom is correct; locus may be wrong; § Fix-locus discrimination.
3. **State one hypothesis, in writing.** "I think X is the root cause because Y." Specific, falsifiable, one at a time. Three theories means tracing isn't finished.

## Phase 3 — Fix at the source

1. **One change, at the root.** Resist "while I'm here" bundling — it muddies the verification signal.
2. **Guards match the condition, not the container.** Gate on the actual invalid condition; substring-on-path filters and state-proxy liveness checks reject legitimate cases. → coordinator CLAUDE.md § Guards match conditions.
3. **Consider defense-in-depth where the bug was structurally possible.** Validating at each layer the data crosses can make the bug *structurally impossible* — worth it when the blast radius justifies it.

## Phase 4 — Verify with fresh evidence

1. **Re-run the repro; prove it, don't assert it.** A test written to catch this must be *run*, not just read. → coordinator CLAUDE.md § Verification Before Done.
2. **Check for collateral.** Run the surrounding tests, not just the one.
3. **Land a regression test where one's missing**, ideally *before* the fix so you watch it go red→green.

### When the fix doesn't take

A patch that doesn't work is information, not a prompt to pile on another.

- **< 3 attempts:** return to Phase 1 with what the failed attempt taught you and form a *new* hypothesis. Don't stack fixes on an unconfirmed one.
- **≥ 3 attempts, each surfacing a new problem elsewhere:** stop debugging and question the architecture. That pattern signals the shape is wrong, not the patch. Surface it to the PM as an architectural call, not a fourth attempt. → coordinator ~/.claude/CLAUDE.md § Engineering Defaults (refactor over patch).

## Related doctrine

- coordinator CLAUDE.md §§ Investigation funnel, Verifying Handoff Premises, Verification Before Done, P0/P1 Verification Gate, Convergence as Confidence.
- Siblings: `/bug-sweep`, `/bug-blitz`, `/dogfood`, `/code-health`.
