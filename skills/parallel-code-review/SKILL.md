---
name: parallel-code-review
description: Weekly chunked code-review gate. /workweek-complete only.
argument-hint: "[--force] [--gate-mode strict|advisory]"
version: 2.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Parallel Code Review

## Overview

The /workweek-complete pre-merge gate: snapshots the week's diff, dispatches N
`code-reviewer-weekly` chunk reviewers plus `security-audit-worker` in one Workflow, runs the deps
and tests scripts, and reduces BLOCKED/WARN/OK with `weekly-gate-synthesize.py`. Enforces
`${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Review What Came Back.

## Wrong-Context Refusal

Invoked only from coordinator:/workweek-complete, by the top-level EM (`A-SKILL-PHASE-NAMES-ITS-ACTOR`).
Reached any other way — STOP, surface the misroute to the PM (see `review` § A.3).

---

## Gate, Chunk, and Resolver Decisions

Three CLI calls drive dispatch shape; each prints an envelope whose `next_move` is the literal next
step. **Every CLI here is resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`**;
on PowerShell invoke the `.exe` launcher by absolute path via the call operator (Shape W).

- **Gate:** `parallel-review-gate-decision gate --range "origin/main...HEAD" [--force]`.
  `judgment_points` is always `[]` here.
- **Chunking:** same binary, `chunk --scope-files-file <scope-files> --seam-manifest-file
  <seam-manifest> [--target-size 25] --out "$FINDINGS_DIR/chunk-manifest.tsv"` — `<scope-files>`
  is `staff_eng_scope`'s narrowed scope, `<seam-manifest>` a `<file>\t<session_id>` TSV. On a
  doc-only week skip and write `printf 'skipped: doc-only\n' > "$FINDINGS_DIR/code_semantics_skip.sentinel"`.
- **Test resolver:** `parallel-review-gate-decision resolver-branch --resolver-exit
  "$RESOLVER_EXIT" --test-cmd "$TEST_CMD"` (values per Test-Output Capture below).

**Rule 5 is the one EM judgment here, never auto-fired.** On a large catch-up span with a
review-trail verdict per workstream, run `rule5-inputs --scope-shas-file <scope-shas>
--seam-files-file <seam-files> --review-trail-dir state/review-trail`; **(a) skip** (record
`incrementally-reviewed`) or **(b) narrow** to `unreviewed_set` (wiki).

## Pre-Flight Orthogonality Assertion

Before dispatch: `parallel-review-orthogonality-guard guard`; non-zero — do not dispatch, surface to
the PM. After chunking: same command with `--chunk-manifest "$FINDINGS_DIR/chunk-manifest.tsv"`;
non-zero — re-chunk.

## Snapshot

`parallel-review-orthogonality-guard snapshot --range "origin/main...HEAD"`; capture its four fields as `$FINDINGS_DIR`, `$WEEKLY_SLICE_ID`, `$DIFF_PATH`, `$HEAD_SHA_PATH` — the only copies.

### Test-Output Capture — Tier-U, EM-only

Run `tier-u-grant-cli check`; ungranted (exit 1, malformed/absent) — halt, surface to the PM, skip this step.
Resolve: `coordinator-resolve-validation-cmd --full` → `$TEST_CMD` / `$RESOLVER_EXIT`. Set
`TEST_OUTPUT_PATH="state/review-trail/diffs/${WEEKLY_SLICE_ID}.test.log"`, run resolver-branch
and act on its `next_move`. On `RESOLVER_EXIT=2`, omit `--test-output`:
`tests.md` gets status `not-run`, scored as an absent lens.

## Parallel Dispatch

> **Do not ask whether to dispatch** — invoking this skill IS the request; reviewers run to completion without EM authorization.

**Before the Workflow, run the two scripts:**
`weekly-gate-deps.py --diff "$DIFF_PATH" --repo . --out "$FINDINGS_DIR/deps.md"` and
`weekly-gate-tests.py [--test-output "$TEST_OUTPUT_PATH"] --out "$FINDINGS_DIR/tests.md"` (omit
`--test-output` on `RESOLVER_EXIT=2`; it surfaces as absent, not failed).

**Dispatch the span as one Workflow — `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/review-wave.mjs", args: {pluginRoot: "${CLAUDE_PLUGIN_ROOT}", ...}})`** (absolute paths). It encodes the
chunk and security legs below; its `args` contract is in the script's header. Pre-provision each
agent's sidecar first (`provision-sidecar --agent-type <type> --provision-key <slice-id>`) and
inject the printed path as `sidecar_path:` in its brief; a Workflow spawn never auto-provisions one.

**Hand-dispatch is the fallback for a broken Workflow only:** dispatch all reviewers in one batch
and say why. Each reviewer writes only its own findings file.

- **Chunk reviewers** (`agents/code-reviewer-weekly.md`, skip all if `SKIP_CODE_SEMANTICS=1`): one
  per chunk, its file-scope list plus `$DIFF_PATH`, writing **only** `$FINDINGS_DIR/chunk-<k>.md`,
  marking `escalate_to_architecture: true` where relevant. Applied findings are verified via
  `review-findings-ledger verify`.
- **security-audit-worker**: `$DIFF_PATH` → `$FINDINGS_DIR/security.md`.

The two scripts (flags pinned in `coordinator/lib/weekly_gate.py` `SCRIPT_CLIS`) are separate lenses
from the chunk reviewers, which partition one lens by file-scope.

Reviewers never commit. A chunk reviewer's footprint is its one `chunk-<k>.md`; anything else is
a contract violation to revert.
<!-- engine-gap: field=chunks[k].footprint producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

## Lens-Domain Manifest

`verify-parallel-review-lens-orthogonality` parses this table and fails closed.

| Reviewer | Lens domain |
|---|---|
| `agents/code-reviewer-weekly.md` | code semantics |
| `agents/security-audit-worker.md` | source security |
| `bin/weekly-gate-deps.py` | dependency CVEs |
| `bin/weekly-gate-tests.py` | test evidence |

---

## Synthesis Pre-Flight and Run

Each agent-written findings file (chunk-*.md, security.md, or the skip sentinel on a doc-only week)
must exist and be >1KB. `deps.md` and `tests.md` are gated by status (`ok`/`not-run`/`failed`),
never size: `not-run` scores an absent lens. A failing/missing agent file:
`lens_coverage[<reviewer>]: failed_disk_read`, degrade to WARN, never "no findings = no issues."

**Quota-exhausted dispatch.** Before synthesis scan each slice for `resets HH:MM`, or a sub-1KB
body with `quota`/`rate limit`; a match (or the `QUOTA-EXHAUSTED-DISPATCH:` envelope) is excluded.
Re-dispatch after the wait or escalate partial coverage to the PM; the gate holds.

Any other failed dispatch: retry once via `SendMessage`, then `failed_disk_read`/WARN.

Once all present files pass, run `weekly-gate-synthesize.py --findings-dir "$FINDINGS_DIR"
--head-sha-path "$HEAD_SHA_PATH"` (writes `$FINDINGS_DIR/synthesis.json`).

---

## Verdict Emission and Gate Behavior

Read `verdict`/counts from `$FINDINGS_DIR/synthesis.json`, format:

```markdown
**Code-review gate:** [BLOCKED|WARN|OK] — convergent: N — code-semantics: <N chunks, P0/P1/P2/nit counts> — arch-tier candidates: <count> — security: <count> — deps: <count> — tests: <pass/fail/flake>
```

BLOCKED halts `/workweek-complete` before Step 9 and Step 11, surfacing the line and
`synthesis.json` path to the PM — fix and re-run, or `--force`. WARN carries the line into the
release-notes draft (Step 9) and the PR body. OK proceeds silently. `arch-tier candidates` feeds
The Staff Engineer's Layer-2 pass, never this verdict.

Background: `coordinator/docs/wiki/skills-corpus/parallel-code-review-residue.md`.
