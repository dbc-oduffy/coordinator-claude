---
name: parallel-code-review
description: Weekly chunked code-review gate. /workweek-complete only.
argument-hint: "[--force] [--gate-mode strict|advisory]"
version: 2.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Parallel Code Review

## Overview

The /workweek-complete pre-merge code-review gate: snapshots the week's diff against
`origin/main`, dispatches N `code-reviewer-weekly` chunk reviewers over the narrowed
code-semantics scope plus `security-audit-worker` over the full diff in one parallel Workflow, runs
the deps and tests scripts, and reduces BLOCKED/WARN/OK with `weekly-gate-synthesize.py`. Enforces
`${CLAUDE_PLUGIN_ROOT}/snippets/em-operating-doctrine.md` § How to Review What Came Back.
The Staff Engineer's Layer-2 pass runs separately at Step 7.5 (wiki).

## Wrong-Context Refusal

Invoked exclusively from coordinator:/workweek-complete, by the top-level EM
(`A-SKILL-PHASE-NAMES-ITS-ACTOR`). Reached any other way — STOP, surface the misroute to the PM
(`coordinator/skills/review/SKILL.md` § A.3 governs every other surface).

---

## Gate, Chunk, and Resolver Decisions

Three CLI calls drive dispatch shape; each prints a decision envelope whose `next_move` field is
the literal next step to take. **Every CLI on this page is resolved per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`** (Shape A/B on POSIX hosts); **on a
PowerShell host, invoke the `.exe` launcher by absolute path through the call operator** (Shape W),
never the `${...}` POSIX-shell form shown below.

- **Gate:** `parallel-review-gate-decision gate --range "origin/main...HEAD" [--force]`.
  `judgment_points` is always `[]` here.
- **Chunking:** same binary, `chunk --scope-files-file <scope-files> --seam-manifest-file
  <seam-manifest> [--target-size 25] --out "$FINDINGS_DIR/chunk-manifest.tsv"` — `<scope-files>`
  is `staff_eng_scope`'s narrowed code-semantics scope (the 3 specialists still see the full
  diff), `<seam-manifest>` a `<file>\t<session_id>` TSV. Skip entirely on a doc-only week; write
  `printf 'skipped: doc-only\n' > "$FINDINGS_DIR/code_semantics_skip.sentinel"` instead.
- **Test resolver:** `parallel-review-gate-decision resolver-branch --resolver-exit
  "$RESOLVER_EXIT" --test-cmd "$TEST_CMD"` (values per Test-Output Capture below).

**Rule 5 is the one EM judgment here, never auto-fired.** On a large catch-up span where every
workstream has a review-trail verdict, run `rule5-inputs --scope-shas-file <scope-shas>
--seam-files-file <seam-files> --review-trail-dir state/review-trail`; **(a) skip** (record
`incrementally-reviewed`, name the records) or **(b) narrow** to `unreviewed_set` (wiki).

---

## Pre-Flight Orthogonality Assertion

Before dispatch: `parallel-review-orthogonality-guard guard`. Non-zero — do not dispatch, surface
to the PM.

After chunking, before chunk-reviewer dispatch: same command with `--chunk-manifest
"$FINDINGS_DIR/chunk-manifest.tsv"`. Non-zero — re-chunk.

---

## Snapshot

Invoke `parallel-review-orthogonality-guard snapshot --range "origin/main...HEAD"`. Capture its four printed fields as
`$FINDINGS_DIR`, `$WEEKLY_SLICE_ID`, `$DIFF_PATH`, `$HEAD_SHA_PATH` — the only copies; readers
take them directly, never from `$FINDINGS_DIR`.

### Test-Output Capture — Tier-U, EM-only

`/workweek-complete` holds this ceremony's implicit Tier-U grant. Consult it anyway:
`tier-u-grant-cli check`.
Ungranted (exit 1, or malformed/absent) — halt, surface to the PM, skip this step.

Resolve: `coordinator-resolve-validation-cmd --full` → `$TEST_CMD` / `$RESOLVER_EXIT`. Set
`TEST_OUTPUT_PATH="state/review-trail/diffs/${WEEKLY_SLICE_ID}.test.log"`, then run the
resolver-branch decision above and act on its `next_move`.

On `RESOLVER_EXIT=2`, omit `--test-output`: `weekly-gate-tests.py` writes `tests.md` with status
`not-run`, scored as an absent lens.

---

## Parallel Dispatch

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

**Before the Workflow, run the two scripts** (resolved like every CLI on this page):
`weekly-gate-deps.py --diff "$DIFF_PATH" --repo . --out "$FINDINGS_DIR/deps.md"` and
`weekly-gate-tests.py [--test-output "$TEST_OUTPUT_PATH"] --out "$FINDINGS_DIR/tests.md"`.

**Dispatch the span as one Workflow — `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/review-wave.mjs", args: {pluginRoot: "${CLAUDE_PLUGIN_ROOT}", ...}})`** (both resolved to absolute paths, never repo-relative). It encodes the
chunk and security legs below; its `args` contract is in the script's header.
Pre-provision each dispatched agent's sidecar first —
`provision-sidecar --agent-type <type> --provision-key <slice-id>` — and inject the printed path
as `sidecar_path:` in its brief: a Workflow spawn never auto-provisions one.

The gate is not a checkpoint: reviewers run to completion without EM authorization.

**Hand-dispatch is the fallback for a broken vehicle, not a preference.** If the Workflow refuses,
dispatch all active reviewers in one multi-tool-call batch and say why. Each reviewer reads its own
frozen input and writes only its own findings file.

- **Chunk reviewers** (`agents/code-reviewer-weekly.md`, skip all if `SKIP_CODE_SEMANTICS=1`): one
  per chunk, its file-scope list plus `$DIFF_PATH`, writing **only** `$FINDINGS_DIR/chunk-<k>.md`
  incrementally, marking `escalate_to_architecture: true` where relevant. Applied findings land
  in the diff, verified via `review-findings-ledger verify`.
- **security-audit-worker**: `$DIFF_PATH` → `$FINDINGS_DIR/security.md`.
- **`weekly-gate-deps.py`**: repo manifests at HEAD vs. `$DIFF_PATH` → `$FINDINGS_DIR/deps.md`.
- **`weekly-gate-tests.py`**: `$TEST_OUTPUT_PATH` → `$FINDINGS_DIR/tests.md`.

Before the Workflow, run the two mechanical scripts (code, no agent; names and flags pinned in
`coordinator/lib/weekly_gate.py` `SCRIPT_CLIS`):

- `weekly-gate-deps.py --diff "$DIFF_PATH" --repo . --out "$FINDINGS_DIR/deps.md"`
- `weekly-gate-tests.py --test-output "$TEST_OUTPUT_PATH" --out "$FINDINGS_DIR/tests.md"` (skip on
  `RESOLVER_EXIT=2`; it surfaces as absent, not failed)

These lenses are orthogonal; the N chunk reviewers partition one by file-scope (wiki).

Reviewers never commit. A chunk reviewer's footprint is exactly its one `chunk-<k>.md`;
anything else is a contract violation to revert.
<!-- engine-gap: field=chunks[k].footprint producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

## Lens-Domain Manifest

`verify-parallel-review-lens-orthogonality` parses this table (agent files exist, no shared lens
domain, at least four rows) and fails closed.

| Reviewer | Lens domain |
|---|---|
| `agents/code-reviewer-weekly.md` | code semantics |
| `agents/security-audit-worker.md` | source security |
| `bin/weekly-gate-deps.py` | dependency CVEs |
| `bin/weekly-gate-tests.py` | test evidence |

---

## Synthesis Pre-Flight and Run

Each expected agent-written findings file (chunk-*.md, security.md, or the skip sentinel on a
doc-only week) must exist and be >1KB. Script-written `deps.md` and `tests.md` are gated by their
status field (`ok`/`not-run`/`failed`), never size: `not-run` scores an absent lens. A failing/missing
agent file: `lens_coverage[<reviewer>]: failed_disk_read`, degrade to WARN, never "no findings = no
issues."

**Quota-exhausted dispatch.** Scan each returned slice against
`resets HH:MM`, or a sub-1KB body with `quota`/`rate limit`, before synthesis — a
match (or the `QUOTA-EXHAUSTED-DISPATCH:` envelope) is excluded from synthesis. Re-dispatch after
the wait or escalate partial coverage to the PM; the gate holds.

Any other failed dispatch: retry once via `SendMessage` (never redispatch from scratch), then
`failed_disk_read`/WARN degrade — an infra dropout never blocks.

Once all present files pass, run `weekly-gate-synthesize.py --findings-dir "$FINDINGS_DIR"
--head-sha-path "$HEAD_SHA_PATH"`. It owns verdict computation, convergence detection, and
`arch_tier_candidates` aggregation, and writes `$FINDINGS_DIR/synthesis.json`.

---

## Verdict Emission and Gate Behavior

Read `verdict`/counts from `$FINDINGS_DIR/synthesis.json`, format:

```markdown
**Code-review gate:** [BLOCKED|WARN|OK] — convergent: N — code-semantics: <N chunks, P0/P1/P2/nit counts> — arch-tier candidates: <count> — security: <count> — deps: <count> — tests: <pass/fail/flake>
```

BLOCKED halts `/workweek-complete` before Step 9 and Step 11, surfacing the line and
`synthesis.json` path to the PM — fix and re-run, or `--force`, never proceed silently. WARN
carries the line into the release-notes draft (Step 9) and the PR body. OK proceeds silently.
`arch-tier candidates` feeds the Staff Engineer's Layer-2 pass, never this verdict.

Cost, examples, chunking algorithm, carve-out mapping: wiki.
