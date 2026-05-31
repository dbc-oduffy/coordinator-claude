<!-- AC10 dry-run fixture for archive/specs/2026-05-26-session-end-deviation-reconciliation-gate.md -->
---
title: "Fixture: deviation reconciliation dry-run"
date: 2026-05-26
created: 2026-05-26
scope_mode: feature
status: closed
author: fixture
---

# Fixture Plan — Deviation Reconciliation Dry-Run

> This is a minimal representative plan doc for AC10 behavioral dry-run validation of
> `/distill` Phase 5a against the deviation-reconciliation spec. It carries:
> (i) a `## Decisions Made` section with a `SHIPPED: X (was: Y)` corrected line, and
> (ii) a `## Deviations` table.
>
> Expected behavior under `/distill --dry-run Phase 5a`:
> - `## Decisions Made` ALLOWLIST section: survives; the `SHIPPED:` line's `(was: Y)` half
>   maps to `[SUPERSEDED]`, not `[DECISION]`; no spurious halt.
> - `## Deviations` section: classified as `[EPHEMERAL]`, dropped WITHOUT re-homing scan;
>   no spurious negative-AC halt triggered by the table content.
> - Corrected ALLOWLIST line (shipped shape `X`) crystallizes normally.

## Goal

Validate the retry-on-failure transport for the widget ingestion pipeline.

## Premise

The original design used synchronous transport. Async transport was chosen at implementation
time to avoid blocking the main thread under high ingestion load.

## Decisions Made

- **Transport mode:** SHIPPED: async message queue with retry (was: synchronous HTTP transport). Chosen to avoid main-thread blocking under high ingestion load; the synchronous approach was ruled out after load testing showed 3× latency increase at p99.
- **Retry policy:** fixed 3-attempt backoff with 500 ms interval; no circuit breaker in scope.

## Acceptance Criteria

| ID | Criterion | Test | Binding-Class | Status |
|----|-----------|------|---------------|--------|
| AC1 | Widget ingestion succeeds under normal load | `bash: bin/test-ingest.sh` | gate-bound | shipped |
| AC2 | Retry recovers from transient network failure | `bash: bin/test-retry.sh` | gate-bound | shipped |

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| Async transport instead of synchronous | Load testing at Step 2 showed synchronous blocked main thread at p99; PM authorized pivot | `a1b2c3d` |
| Retry interval bumped from 200 ms to 500 ms | 200 ms caused thundering-herd on transient failures in staging; 500 ms cleared the issue | `b2c3d4e` |
| Dropped the circuit-breaker requirement | Original plan said the transport MUST include a circuit breaker; descoped after the retry policy proved sufficient under staging load | `c3d4e5f` |

<!-- AC10 assertion (iii) tripwire: the row above carries an AC-shaped token (`MUST`) that exists ONLY in this dropped `## Deviations` section and has NO semantically-equivalent line in any surviving ALLOWLIST section. Without the heading-classifier exemption, the negative-AC silent-loss guard would HALT on this line. With the exemption, the line is excluded from the set-diff scan and no halt fires. This is what makes the exemption load-bearing — remove this row and assertion (iii) passes trivially whether or not the exemption exists.

     TOKENIZER NOTE (per session-end code-reviewer Finding 2): /distill is agent-executed doctrine, not a regex engine — the negative-AC guard's "AC-shaped token line" is read as "a line CONTAINING an AC-shaped token," so the `MUST` mid-table-cell above IS detected. If /distill is ever reimplemented as a script, that script MUST tokenize mid-cell content (not anchor to line-start) for this tripwire to remain load-bearing.

     MAINTENANCE OBLIGATION (per Finding 6): AC10 is gate-bound but verified by the hand-trace at plan-deviation-reconciliation-dryrun-trace.md, not a runnable assertion. If distill.md § Negative AC — Silent-Loss Guard or § Phase 5a re-homing changes, the trace is stale and MUST be re-executed manually. -->
