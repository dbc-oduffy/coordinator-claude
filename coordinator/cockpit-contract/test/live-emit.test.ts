/**
 * live-emit.test.ts — real-emitter end-to-end + privacy gate tests.
 *
 * AC9:  Spawn the real emit-cockpit-snapshot.sh against the live ~/.claude repo
 *       and prove the output passes SnapshotEnvelope.parse + per-entity schema
 *       validation.  Catches "emitter forgot to project a new field" drift — the
 *       failure mode that caused the prior zero-valid-records bug.
 *
 * AC3b: Prove acceptance_criteria is emitted as ratio-only {done, total} and that
 *       NO prose substring leaks anywhere in the emitted handoff record (privacy
 *       hard constraint for the all-staff web tier).
 *
 * Performance: both describe blocks share a single emitter run (via outer beforeAll)
 * to keep total wall-clock within the vitest worker RPC timeout window.
 *
 * Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C5
 * Contract version: 2.0 (SnapshotEnvelope shape)
 */
import { existsSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

// Review: code-reviewer F2/F7 — async spawn frees the vitest worker event loop so the
// RPC heartbeat (onTaskUpdate) is not starved during the ~55s emitter run. execFileSync
// blocks the thread entirely; promisify(execFile) yields back to the event loop.
const execFileAsync = promisify(execFile);
import { describe, it, beforeAll, afterAll, expect } from "vitest";
import type { z } from "zod";
import { ENTITY_SCHEMAS, SnapshotEnvelope } from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));

// Emitter lives two levels above cockpit-contract/ in coordinator/bin/
const emitterPath = join(here, "..", "..", "bin", "emit-cockpit-snapshot.sh");

// Review: code-reviewer — dist/index.js absence must be a hard throw, not a skip;
// describe.skipIf(!distPresent) silently false-greens in CI (the exact footgun this
// gate exists to prevent). The prepare script runs on install, so dist is guaranteed
// in any real `pnpm install && pnpm test`; absent dist = broken environment, not a
// skip condition.
const distIndexPath = join(here, "..", "dist", "index.js");
if (!existsSync(distIndexPath)) {
  throw new Error(
    `[live-emit.test] dist/index.js not found — run 'pnpm build' before 'pnpm test'. Path: ${distIndexPath}`,
  );
}

// Structural guard: if the emitter is missing the path resolution is wrong and
// the test would silently false-skip.  Fail hard at module load time instead.
if (!existsSync(emitterPath)) {
  throw new Error(
    `[live-emit.test] emitter not found at resolved path:\n  ${emitterPath}\n` +
      `Expected: ~/.claude/plugins/coordinator/bin/emit-cockpit-snapshot.sh\n` +
      `Check join(here, "..", "..", "bin", ...) resolution.`,
  );
}

// ─── Root path (for AC3b handoff injection) ──────────────────────────────────
// here = ~/.claude/plugins/coordinator/cockpit-contract/test
// 5 levels up → ~/.claude
const claudeRoot = join(here, "..", "..", "..", "..", "..");
const handoffsDir = join(claudeRoot, "state", "handoffs");

// ═══════════════════════════════════════════════════════════════════════════════
// Shared fixture — both AC9 and AC3b use one emitter run.
//
// AC3b requires a synthetic handoff to be on disk BEFORE the emitter runs,
// so the setup writes the temp handoff, runs the emitter, parses the output,
// and caches it for both test blocks.  Cleanup (temp handoff + tmp out file)
// happens in the outer afterAll.
// ═══════════════════════════════════════════════════════════════════════════════

type Envelope = z.infer<typeof SnapshotEnvelope>;

// Outer wrapper carries the single emitter invocation shared by both blocks.
// Review: code-reviewer — unconditional after F1 hard-throw; if we reach here, dist is present.
describe("live-emit suite (AC9 + AC3b)", () => {
  // ── AC3b constants ──────────────────────────────────────────────────────────
  // Review: code-reviewer — Date.now()-only name can collide under parallel workers; append UUID suffix.
  const tmpHandoffName = `ZZZ-livetest-ac3b-${Date.now()}-${crypto.randomUUID().slice(0, 8)}.md`;
  const tmpHandoffPath = join(handoffsDir, tmpHandoffName);
  const expectedRelPath = `state/handoffs/${tmpHandoffName}`;

  const DISTINCTIVE_ALPHA = "DISTINCTIVE_PROSE_ALPHA the quick brown fox";
  const DISTINCTIVE_BETA = "DISTINCTIVE_PROSE_BETA jumps over the lazy dog";

  // Minimal valid handoff — all four fields required by the emitter quarantine
  // select() must be present, and status/deployment_state must be valid enums.
  const handoffContent = `---
title: "ZZZ Live Test AC3b Handoff"
created: 2026-06-26
status: active
deployment_state: in_flight
kind: session-handoff
workstream: livetest-ac3b
predecessor: none
scope: []
---

# ZZZ Live Test Handoff (AC3b)

This synthetic handoff is written and deleted by the live-emit test suite.

## Acceptance criteria

- [x] ${DISTINCTIVE_ALPHA}
- [ ] ${DISTINCTIVE_BETA}
`;

  // ── Shared state populated by beforeAll ────────────────────────────────────
  let envelope: Envelope | null = null;
  let tmpOutPath = "";

  beforeAll(async () => {
    // 1. Write the AC3b synthetic handoff so the emitter picks it up
    writeFileSync(tmpHandoffPath, handoffContent, "utf8");

    // 2. Run the emitter (single invocation shared by both test blocks).
    //    Review: code-reviewer F2/F7 — async so the vitest worker event loop stays free
    //    to send RPC heartbeats (onTaskUpdate) during the ~55s emitter run. The sync
    //    execFileSync variant blocks the entire worker thread and starves the heartbeat,
    //    causing ELIFECYCLE even when all tests pass. timeout+killSignal still guard a
    //    real emitter hang; cwd=claudeRoot from F4; maxBuffer=10MB for emitter stderr.
    tmpOutPath = join(tmpdir(), `cockpit-live-emit-${Date.now()}.json`);
    try {
      await execFileAsync("bash", [emitterPath, "--out", tmpOutPath], {
        cwd: claudeRoot,
        encoding: "utf8",
        timeout: 110_000,
        killSignal: "SIGTERM",
        maxBuffer: 1024 * 1024 * 10,
      });
    } catch (err: unknown) {
      const e = err as { stderr?: string; stdout?: string };
      throw new Error(
        `Emitter exited non-zero.\nstderr:\n${e.stderr ?? "(none)"}\nstdout:\n${e.stdout ?? "(none)"}`,
      );
    }

    // 3. Parse and cache the envelope
    const raw: unknown = JSON.parse(readFileSync(tmpOutPath, "utf8"));
    envelope = SnapshotEnvelope.parse(raw);
  }, 120_000);

  afterAll(() => {
    // MANDATORY cleanup — temp handoff must not remain in state/handoffs/
    try {
      if (existsSync(tmpHandoffPath)) {
        unlinkSync(tmpHandoffPath);
      }
    } catch {
      /* best-effort */
    }
    // Cleanup emitter temp output
    try {
      if (tmpOutPath && existsSync(tmpOutPath)) {
        unlinkSync(tmpOutPath);
      }
    } catch {
      /* best-effort */
    }
  });

  // ─── AC9: real-emitter end-to-end drift gate ─────────────────────────────
  describe("AC9 — real-emitter end-to-end drift gate", () => {
    it("SnapshotEnvelope.parse succeeds and every entity array validates against its schema", () => {
      // beforeAll guarantees this; TypeScript narrowing guard
      if (!envelope) throw new Error("envelope not set — beforeAll failed");

      const schemas = ENTITY_SCHEMAS;

      // Top-level parse already happened in beforeAll (it would have thrown).
      // Validate each entity array element individually for precise error index.
      envelope.handoffs.forEach((rec, i) => {
        try {
          schemas["handoff-summary"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `handoffs[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.coordinator_roots.forEach((rec, i) => {
        try {
          schemas["coordinator-root"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `coordinator_roots[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.branches.forEach((rec, i) => {
        try {
          schemas["branch"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `branches[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.review_trail.forEach((rec, i) => {
        try {
          schemas["review-trail"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `review_trail[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.plans.forEach((rec, i) => {
        try {
          schemas["plan-summary"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `plans[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.cross_repo_memos.forEach((rec, i) => {
        try {
          schemas["cross-repo-memo-summary"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `cross_repo_memos[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.completion_rollups.day.forEach((rec, i) => {
        try {
          schemas["day-rollup"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `completion_rollups.day[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.completion_rollups.week.forEach((rec, i) => {
        try {
          schemas["week-rollup"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `completion_rollups.week[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      // Review: code-reviewer — F3: per-element coverage was missing for backlogs,
      // routine_signals, goals_current, and lessons. Top-level SnapshotEnvelope.parse
      // catches shape drift, but per-element loops give precise index-keyed error messages
      // for the same failure mode that caused the prior zero-valid-records bug.
      envelope.backlogs.bug.forEach((rec, i) => {
        try {
          schemas["backlog-item-summary"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `backlogs.bug[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.backlogs.debt.forEach((rec, i) => {
        try {
          schemas["backlog-item-summary"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `backlogs.debt[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.backlogs.improvement.forEach((rec, i) => {
        try {
          schemas["backlog-item-summary"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `backlogs.improvement[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.routine_signals.forEach((rec, i) => {
        try {
          schemas["routine-signal"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `routine_signals[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.goals_current.forEach((rec, i) => {
        try {
          schemas["goal"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `goals_current[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      envelope.lessons.forEach((rec, i) => {
        try {
          schemas["lesson-summary"]!.parse(rec);
        } catch (e) {
          throw new Error(
            `lessons[${i}] failed schema parse: ${String(e)}`,
          );
        }
      });

      // Fleet must be non-empty — the local meta-repo is always element [0]
      expect(
        envelope.coordinator_roots.length,
        "coordinator_roots must have at least 1 entry (local meta-repo)",
      ).toBeGreaterThanOrEqual(1);
    });
  });

  // ─── AC3b: privacy guarantee (ratio-only, no prose leak) ─────────────────
  describe("AC3b — acceptance_criteria ratio-only, no prose leak", () => {
    it("emitted handoff record has acceptance_criteria as {done,total} only — no prose substring leaks", () => {
      if (!envelope) throw new Error("envelope not set — beforeAll failed");

      // Find the synthetic handoff record by its provenance.path
      const record = envelope.handoffs.find(
        (h) => h.provenance.path === expectedRelPath,
      );

      expect(
        record,
        `Could not find temp handoff in emitted output (expected provenance.path === "${expectedRelPath}").\n` +
          `Emitted handoff paths: ${envelope.handoffs.map((h) => h.provenance.path).join(", ")}`,
      ).toBeDefined();

      // Review: code-reviewer — F6: unreachable at runtime; satisfies TypeScript narrowing.
      if (!record) return;

      // Ratio-only: must be exactly {done: 1, total: 2}
      expect(
        record.acceptance_criteria,
        "acceptance_criteria must be {done: 1, total: 2}",
      ).toEqual({ done: 1, total: 2 });

      // Privacy: no prose substring anywhere in the serialised record
      const serialised = JSON.stringify(record);
      expect(
        serialised,
        `acceptance_criteria prose leaked: "${DISTINCTIVE_ALPHA}" found in emitted record`,
      ).not.toContain(DISTINCTIVE_ALPHA);
      expect(
        serialised,
        `acceptance_criteria prose leaked: "${DISTINCTIVE_BETA}" found in emitted record`,
      ).not.toContain(DISTINCTIVE_BETA);
    });
  });
});
