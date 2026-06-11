---
kind: plan
slug: partitioned-review-integrator-fan-out
status: active
scope_mode: production-patch
authored: 2026-06-09
authored_by: em-striker
problem_set: inline (see Problem)
---

# Partitioned-Review Integrator: Fan-Out Actuator + Doctrine Reinforcement

## Problem

When `/workstream-complete` Step 2.9 partitions code review across N slices (big-diff brightline fires), doctrine says integrators MUST dispatch 1:1 in parallel with slice reviewers. **This rule is being violated empirically** — 2026-06-09, an EM session held all slice reviewer outputs, then dispatched one union-integrator across the merged finding set, exactly the shape § Partitioning explicitly bans. PM caught it; EM owned the miss as a calibration failure.

Scout investigation (agent `ab0f0854e326f9ca2`, 2026-06-09) confirmed the root cause has three reinforcing layers:

1. **Trigger-surface visibility (P1).** The 1:1 parallel rule lives in `skills/workstream-complete/SKILL.md:351` (sub-bullet under partitioning mechanics), `docs/wiki/review-integration-doctrine.md:106`, and `agents/review-integrator.md:33` (intake check on the integrator side). None of these surfaces fire at the seam the EM actually reads — the inline reviewer output. `agents/code-reviewer.md` (the agent prompt the EM reads when dispatching/receiving a slice) names no partition shape at all.
2. **Mechanical actuator absent (P2 — STRUCTURAL).** `bin/fan-out-dispatch.sh` (594 lines) exists to make parallel executor dispatch the path of least resistance. **No integrator equivalent exists.** Manual N-prompt construction is the friction floor — collation is cheaper to type than fan-out, and synthesis instinct ("let me see all findings together to prioritize") wins by default.
3. **Doctrine asymmetry (P2).** `CLAUDE.md:190` § Review Sequencing states the hard rule (sequential) and the synthesizer-exception (parallel + no-rewrite synthesizer at merge-gate). It **omits the partition-integrator exception entirely** — that exception lives only in skill + wiki, not co-located with the rule. An EM reading the hard rule sees no partition-integrator carve-out.

P2 (mechanical actuator) is the structural lever: once parallel integrator dispatch is one command (`bin/fan-out-integrator.sh`), the economics flip and synthesis-collation is the off-script choice. P1 (trigger-surface visibility) and the doctrine-asymmetry fix are reinforcement at the right surfaces — they pay off in residual visibility once the actuator is in place.

## Scope mode

`production-patch` — three discrete, named-locus fixes; no new abstraction beyond a new bin script that mirrors an existing pattern; no architectural surface change.

## Acceptance Criteria

| ID  | Criterion (prose)                                                                                                                                                                                                                  | Test (typed-prefix)                                                                                                  | Binding-Class | Status              |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------- | ------------------- |
| AC1 | `bin/fan-out-integrator.sh` exists with bash shebang (executable bit verified by `exec-bit.test.js` pre-commit hook)                                                                                                              | `grep:#!/usr/bin/env bash@plugins/coordinator/bin/fan-out-integrator.sh`                           | gate          | shipped             |
| AC2 | Script takes N reviewer sidecar paths via stdin TSV or `--spec <file>`, validates each exists, emits N paste-ready `coordinator:review-integrator` dispatch prompts to stdout, EM reminders to stderr (test T1)                       | `bash:plugins/coordinator/bin/tests/test-fan-out-integrator.sh`                                    | gate          | shipped             |
| AC3 | Script fails loudly on missing sidecar (T4), overlap (T3), non-git cwd (T5), empty spec (T6), malformed row (T7) — all five error paths exercised by the same test suite                                                              | `bash:plugins/coordinator/bin/tests/test-fan-out-integrator.sh`                                    | gate          | shipped             |
| AC4 | Each emitted block names ONE reviewer slice (path + slice paths), includes destructive-action prohibition, names peer integrators with parallel-dispatch language (test T2)                                                            | `bash:plugins/coordinator/bin/tests/test-fan-out-integrator.sh`                                    | gate          | shipped             |
| AC5 | `agents/code-reviewer.md` carries a "Partitioned-dispatch hand-off note" section telling the EM, at reviewer return, to dispatch its integrator via `bin/fan-out-integrator.sh` in parallel with peer integrators                    | `grep:fan-out-integrator@plugins/coordinator/agents/code-reviewer.md`                              | gate          | shipped             |
| AC6 | `CLAUDE.md` § Review Sequencing carries the partition-integrator exception co-located with the synthesizer-exception, naming the 1:1 parallel dispatch shape and cross-referencing `review-integration-doctrine.md`                  | `grep:partitioned-code-review integrators@plugins/coordinator/CLAUDE.md`                           | gate          | shipped             |
| AC7 | `skills/workstream-complete/SKILL.md` § Partitioning large surfaces item 2 points at `bin/fan-out-integrator.sh` as the canonical mechanism                                                                                          | `grep:fan-out-integrator.sh@plugins/coordinator/skills/workstream-complete/SKILL.md`               | gate          | shipped             |
| AC8 | Both shell files pass `bash -n` syntax check (verified at integrator commit `da247c6b`; ongoing verification is the test-suite run which exits 1 if either file has a syntax error since invocation would fail)                       | `bash:plugins/coordinator/bin/tests/test-fan-out-integrator.sh`                                    | gate          | shipped             |

## Cross-plan coordination

Scanned `docs/plans/` for `fan-out` / `integrator` / `review-integrator` overlaps:

- **`2026-05-27-fan-out-default-doctrine.md`** — established `bin/fan-out-dispatch.sh`. This plan extends the *same pattern* to integrators. No conflict: parallel actuator at a sibling seam.
- **`2026-05-30-fan-out-skill-to-methodology-demotion.md`** — confirmed fan-out is methodology, not a skill. Reinforces: P2 is a bin script + skill-step pointer, NOT a new `/fan-out-integrator` skill.
- **`2026-06-09-executor-sidecar-flight-recorder.md`** — same-day plan, touches `fan-out-dispatch.sh` to add `--plan` / sidecar emission. **No file overlap** (that plan modifies `fan-out-dispatch.sh`; this plan creates `fan-out-integrator.sh`). Sidecar pattern is NOT in-scope for this plan — integrator dispatches don't author handoffs and don't need flight recorders (the integrator's job is a single bounded edit pass per slice).

No conflicts — scanned, no overlapping file scope or seam citations beyond the noted same-pattern extension.

## Chunks

**EM-serial commits after each chunk.** The actuator chunk ships before the doctrine-reinforcement chunks so the doctrine edits can reference the actual script path.

### Chunk 1 — `bin/fan-out-integrator.sh` + test (P2, STRUCTURAL)

**Goal:** create the actuator. After this chunk, parallel integrator dispatch is one command; union-integrator is the off-script choice.

**In-scope files (write):**
- `plugins/coordinator/bin/fan-out-integrator.sh` (new)
- `plugins/coordinator/bin/tests/test-fan-out-integrator.sh` (new)

**In-scope files (read for pattern reference):**
- `plugins/coordinator/bin/fan-out-dispatch.sh` (model — mirror its shape, NOT a copy)
- `plugins/coordinator/snippets/peer-scope-block.md` (reuse for peer-integrator block)
- `plugins/coordinator/agents/review-integrator.md` (read once to confirm dispatch prompt shape)

**Spec for the script:**

**Input format (TSV on stdin or `--spec <file>`), one row per slice:**
```
<slice-id>TAB<reviewer-sidecar-path>TAB<comma-separated-file-paths>
```

- `<slice-id>` — e.g. `slice-A`, `slice-B` (mirrors fan-out-dispatch chunk-id convention).
- `<reviewer-sidecar-path>` — path to the `code-reviewer` slice's output file on disk. MUST exist; the integrator will be instructed to consume findings from this path.
- `<comma-separated-file-paths>` — the slice's review scope (same paths the source reviewer was scoped to). Used for overlap validation and to scope the integrator's edit pass.

**Output:** N paste-ready dispatch blocks to stdout, each invoking `coordinator:review-integrator` scoped to one slice. EM reminders to stderr.

**Per-block content (the dispatch prompt shape):**
- Brief: "Integrate findings from `<reviewer-sidecar-path>` into the codebase. Slice: `<slice-id>`."
- In-scope files: the slice's path list.
- **Peer-integrator block** — names other slices' integrators by `<slice-id>` + scope, telling each integrator "your peers are firing in parallel right now; do NOT wait, do NOT collate, your scope is yours alone."
- Destructive-action prohibition (per executor pattern).
- Disk-first verification preamble (re-use `snippets/text-only-recovery-preamble.md`).
- `expected_branch:` captured from `git branch --show-current`.

**Mechanics (mirroring `fan-out-dispatch.sh`):**
- Same arg parsing (`--spec`, `--help`), same git-repo precondition, same overlap-detection pass, same error-on-empty-rows discipline.
- Use `python3` for `{{peer_slices}}` substitution (per fan-out-dispatch comment: bash `${var/pat/repl}` corrupts backslashes on Windows paths).
- **NO `--plan` / sidecar emission** — integrators are single-pass edits, not flight-recorder workloads.
- **NO fat-chunk NOTE, NO memory-headroom probe** — N is small (matches slice count, typically 2-4) and integrator dispatches are I/O-bound not RAM-bound. The cores-proxy "large wave" advisory does not apply.
- Add a precondition the executor variant lacks: **each cited reviewer sidecar MUST exist on disk** (`-f` test); a missing sidecar is exit 1 with explanatory stderr.

**Test (`bin/tests/test-fan-out-integrator.sh`) — assertion set:**
1. Happy path: 3 slices, no overlap, all sidecars present → 3 blocks emitted to stdout, exit 0.
2. Per-block structure: each block contains exactly one slice-id, names peer slices, includes destructive-action prohibition, includes the reviewer-sidecar path verbatim in the Brief.
3. Overlap detection: 2 slices claim the same file → exit 1, no partial output.
4. Missing sidecar: cited path doesn't exist → exit 1 with the missing-path in stderr.
5. Non-git-repo cwd: exit 2 with remediation message.
6. Empty spec: exit 2.
7. Malformed row (wrong field count): exit 1 with row number in stderr.

**Out-of-scope this chunk:** no edits to `agents/`, `CLAUDE.md`, or `skills/`. Those are Chunks 2-4.

**Hard constraints:**
- Bash 3.2 + BSD coreutils compatible (`#!/usr/bin/env bash`, no `declare -A`, no `mapfile`, no `${v^^}`, no `grep -P`, no `sed -i`, no `realpath` without fallback chain).
- `bash -n` clean before commit.
- No `git add -A` / commits inside the script. EM commits serially after chunk completion.

### Chunk 2 — `agents/code-reviewer.md` partitioned-dispatch hand-off note (P1)

**Goal:** at the seam where the EM reads slice reviewer output, the agent prompt names the parallel-integrator dispatch shape.

**In-scope files (write):**
- `plugins/coordinator/agents/code-reviewer.md` (one new section added)

**Content to add (placement: after § "Output structure", before § "Spec completion lens"):**

```markdown
## Partitioned-dispatch hand-off note

When this review is one slice of a partitioned `code-reviewer` dispatch (per
`skills/workstream-complete/SKILL.md` § Partitioning large surfaces), the EM
receiving your report MUST dispatch the integrator for your slice in **parallel**
with peer-slice integrators — not after waiting for all slices to return.

Mechanism: `bin/fan-out-integrator.sh` (input: TSV of `<slice-id>TAB<your-sidecar-path>TAB<your-scope-files>`,
one row per slice; output: N parallel `coordinator:review-integrator` dispatch
blocks). Collating N reviewers' findings into one union-integrator is the doctrine
violation this row exists to prevent — the partition was applied because one
Sonnet couldn't fit the whole surface; the same constraint binds the integrator.

This note is a reminder to the EM reading your output, not an instruction to you.
You do not dispatch anything. See `docs/wiki/review-integration-doctrine.md` §
Integrator dispatches are 1:1 with reviewer slices for full rationale.
```

**Out-of-scope:** any other edit to `code-reviewer.md`. This is a single new section addition.

### Chunk 3 — `CLAUDE.md` § Review Sequencing partition-integrator exception (P2)

**Goal:** the partition-integrator exception is greppable from the same surface as the hard rule.

**In-scope files (write):**
- `plugins/coordinator/CLAUDE.md` (one new bullet added after the existing first bullet at line 190)

**Content to add (placement: as a new sub-bullet under the existing "Multi-persona reviews are sequential" rule, between current line 190 and 191):**

```markdown
- **Exception — partitioned-code-review integrators at workstream-complete:** When `code-reviewer` is fanned out to N parallel slices (per `skills/workstream-complete/SKILL.md` § Partitioning large surfaces), integrators dispatch in parallel 1:1 with reviewer slices, not sequentially. The structural reason: one reviewer couldn't fit the whole surface, so one integrator can't either. Mechanism: `bin/fan-out-integrator.sh`. Distinct from the synthesizer exception above — partition-integrator has no synthesizer; integrators touch disjoint file sets by construction. → `docs/wiki/review-integration-doctrine.md` § Integrator dispatches are 1:1 with reviewer slices.
```

**Out-of-scope:** any other edit to `CLAUDE.md`. This is a single new bullet addition co-located with the existing exception sub-clause.

### Chunk 4 — `skills/workstream-complete/SKILL.md` redirect to actuator

**Goal:** existing partition-procedure row 2 points at `bin/fan-out-integrator.sh` so the path-of-least-resistance is the script, not manual N-prompt construction.

**In-scope files (write):**
- `plugins/coordinator/skills/workstream-complete/SKILL.md` (edit line 351, the existing "Dispatch in parallel; integrators are 1:1…" sub-bullet)

**Content change:** insert a sentence after "No collation into a single union-integrator." pointing at the actuator:

```markdown
**Mechanism:** `bin/fan-out-integrator.sh` (input: TSV of `<slice-id>TAB<reviewer-sidecar-path>TAB<scope-files>`; output: N parallel `coordinator:review-integrator` dispatch blocks). Manual N-prompt construction is permitted only when the script is unavailable — collation is never permitted.
```

**Out-of-scope:** any other edit to SKILL.md. This is a single sentence insertion at one line.

## Out-of-scope (architectural deferrals)

None. All three scout-identified gaps ship in this plan. P5 (no scope-trim YAGNI) — there's no candidate item that would have been deferred; the scope is exactly the structural fix + its two reinforcement edits.

## Risks

- **Cross-plan touch on `bin/fan-out-dispatch.sh`:** the executor-sidecar-flight-recorder plan (same day) is editing that file. This plan creates a *new* file (`fan-out-integrator.sh`), so no file-overlap. The risk is *pattern drift* — if the sidecar plan changes how the executor variant handles e.g. peer-scope substitution, the integrator variant might lag behind. Mitigation: the integrator script mirrors patterns by *imitation*, not by sourcing — drift is acceptable; the two scripts have different responsibilities.
- **Discoverability lag for the doctrine-reinforcement edits:** the doctrine edits in Chunks 2-3 land in CLAUDE.md and an agent prompt; both are read at session start / dispatch time. No special promotion needed beyond the commit.

## Test plan

- Chunk 1: test script (`bin/tests/test-fan-out-integrator.sh`) runs green. 7 assertions covering happy-path + 5 error paths + per-block structure.
- Chunks 2-4: AC5/AC6/AC7 grep assertions. No runtime test — these are doctrine edits read at session start, validated by content presence.
- AC8: `bash -n` on both new shell files.

## Closeout

`doc-link-checker` NOT scheduled — no paths moved, no renames. The grep-assertion ACs (AC5-AC7) verify the cross-references resolve.

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| AC table cells initially violated the S1-S4 typed-prefix grammar (`grep:` cells missing `@path` separator, `bash:` cells with inline prose, AC8 used `bash -n cmd` shape instead of test-script path) — caught by the Step 3.8 acceptance-oracle gate, fixed in place before workstream commit | Plan author over-relied on prose-shaped Test cells (the exact failure mode the 2026-06-09 grammar-first AC rewrite exists to prevent — orientation pinboard names this). Plan-coverage-checker Lens 4 would have caught this at plan-write time; this plan skipped `coordinator:review` per PM ("just execute") so the grammar lens never ran. AC8 collapsed: standalone `bash -n` check unrepresentable in `bash:<path>` shape — instead, the test-script run covers AC8 transitively (script with syntax error would fail to exec) | pending (this commit) |
| Partition-integrator pattern dogfooded on its own birth-commit (1055 LOC, 3 surfaces → PARTITION-MANDATORY brightline). Used `bin/fan-out-integrator.sh` to emit the two integrator dispatch prompts | Brightline gate fired post-commit. The script existed on disk pre-integration; happy coincidence that the actuator was usable on its own birth review | `da247c6b` |
| `block-subagent-plan-body-write` hook blocked the slice-B integrator from applying F2/F3 (plan frontmatter + P3 relabel); EM applied directly | Hook is correct behavior — plan bodies are EM-owned per coordinator doctrine. Integrator escalated cleanly with specific edit instructions; EM applied with three `Edit` calls | `da247c6b` |
