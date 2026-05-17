---
title: OOM Reproducer Strategy for Multi-Agent Fan-Out Workflows
description: Four-dimension assertion pattern for fan-out OOM failures. Single-dimension reproducers reliably miss the failure mode; this guide explains why and what to assert instead.
---

# OOM Reproducer Strategy for Multi-Agent Fan-Out Workflows

> When a fan-out workflow hits out-of-memory failures, a one-dimensional reproducer (just peak RSS, or
> just concurrent sessions) almost always misses the actual failure mode. This guide describes the
> four-dimension assertion pattern that reliably captures fan-out OOM failures.

## The Four Dimensions

A complete fan-out OOM reproducer asserts all of:

1. **Peak RSS** — maximum resident set size at the moment of failure (not average). Use
   `/usr/bin/time -v` or `process.memoryUsage().rss` sampled at peak. Sampling on a fixed interval
   misses spikes that resolve between samples; sample at the end of each subagent wave instead.

2. **Commit count** — number of concurrent in-flight commits. OOM often surfaces only above a threshold
   commit density, not above a session count threshold. A single session doing 20 rapid-fire commits can
   hit the same failure as 20 sessions doing one each.

3. **Concurrent-session count** — number of EM sessions active simultaneously. This is the fan-out
   width, not the depth. A wide shallow fan-out (20 sessions × 1 commit each) and a narrow deep fan-out
   (2 sessions × 10 commits each) have different memory profiles; both need coverage.

4. **Wall-clock time** — duration of the fan-out wave. Memory leaks that are invisible at 30 seconds
   become OOM at 5 minutes. Long-running waves accumulate allocations that short-running tests never
   exercise.

## Why Single-Dimension Tests Fail

Single-dimension tests pass for the wrong reason: the failure mode is an interaction between dimensions.

- A test that checks only **peak RSS** will pass if it does not exercise enough concurrent commits — the
  heap may stay low because session overlap is minimal.
- A test that checks only **session count** will pass at low commit density — 20 idle sessions use far
  less memory than 20 sessions each writing a large artifact and committing.
- A test that checks only **commit count** will pass at short wall-clock times — the GC has time to
  collect between commits when they are spaced far apart.
- A test that checks only **wall-clock time** will pass if the fan-out width is narrow — a long-running
  single session does not reproduce the interaction that emerges from a wide concurrent fan-out.

Only when all four dimensions are under assertion simultaneously does the reproducer reliably catch
the failure before it reaches production.

## Minimum Viable Reproducer Structure

Use `node:test` syntax (not `describe`/`it`):

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';

test('fan-out OOM reproducer: stays within bounds under full fan-out load', async (t) => {
  // Arrange: N sessions, M commits per session, T-second deadline
  const N = 20;   // fan-out width
  const M = 5;    // commits per session
  const T = 30;   // wall-clock deadline (seconds)
  const RSS_LIMIT_MB = 512;

  const start = Date.now();

  // Act: run fan-out to completion (replace with real fan-out harness)
  const results = await runFanOut({ sessions: N, commitsPerSession: M });

  const wallClockSec = (Date.now() - start) / 1000;
  const peakRssMB = results.peakRss / (1024 * 1024);

  // Assert: peak RSS within bounds
  assert.ok(peakRssMB < RSS_LIMIT_MB,
    `Peak RSS ${peakRssMB.toFixed(1)} MB exceeded limit ${RSS_LIMIT_MB} MB`);

  // Assert: all commits landed (no silent drops)
  assert.strictEqual(results.commitCount, N * M,
    `Expected ${N * M} commits, got ${results.commitCount}`);

  // Assert: fan-out width reached N (confirmed full parallelism)
  assert.strictEqual(results.peakConcurrentSessions, N,
    `Expected ${N} concurrent sessions, reached only ${results.peakConcurrentSessions}`);

  // Assert: completed within wall-clock deadline
  assert.ok(wallClockSec < T + 5,  // +5s buffer for CI jitter
    `Fan-out took ${wallClockSec.toFixed(1)}s, exceeded ${T}s deadline`);
});
```

All four dimensions appear as explicit assertions. If any one is missing, the test does not constitute
a valid fan-out OOM reproducer.

## Applies To

Any multi-agent pipeline with a fan-out wave:

- Parallel enrichers writing to disk and committing
- Parallel reviewers each producing a findings file
- Parallel executors writing to different sections of a shared artifact
- Any pattern where N subagents run concurrently and commit results

It does NOT apply to sequential pipelines (one subagent at a time, no overlap).

## Sampling Peak RSS

The naive approach — sampling RSS once at the end — misses the peak if memory was released during the
wave. Sample at the boundary of each subagent completion and track the running maximum:

```js
// Node.js: track peak RSS across async wave
let peakRss = 0;
function sampleRss() {
  const { rss } = process.memoryUsage();
  if (rss > peakRss) peakRss = rss;
}
// Call sampleRss() at the end of each subagent's promise resolution
```

On Unix, `/usr/bin/time -v` reports "Maximum resident set size" at process exit — reliable for
single-process tests, but does not capture sub-process peak in a fan-out.

## Related

- `docs/wiki/round-trip-contract-tests.md` — broader contract-test doctrine
- `coordinator/CLAUDE.md` § Implementation Standards — pointer to this wiki
