# Executor Sidecar and Discipline

<!-- distilled: run 2026-07-19-synth; sources: 2026-05-27-cqcs-cluster1-delegate-constraint-adherence.md, 2026-05-05-executor-touched-branch-pin.md, 2026-05-05-issue-a-agent-id-linkage.md, archive/specs/2026-03/2026-03-08-agent-hierarchy-design.md, 2026-06-15-execute-plan-plan-doc-oos-injection.md, 2026-06-15-executor-no-self-commit-em-only-gate.md, 2026-07-13-subagent-run-report-subsume.md, 2026-07-16_144733_59903006-30d2-4392-87da-7fa571bd7047.md -->

Reference for the mechanisms that keep executor subagents inside their lane: the run-report sidecar (record-of-work surface), the plan-body/archive immutability hooks, the touched-files/branch-pin scope guards, and the self-commit gate. These are the enforced, structural counterparts to the doctrine prose in `agents/executor.md`.

## Overview

An executor is a scoped subagent: it gets a dispatch brief, a declared file scope, and (usually) a sidecar to record its work. Four independent enforcement families keep it honest:

1. **Sidecar / run-report** — where the executor records what it did, separate from the plan it's executing.
2. **Plan-body immutability** — the executor cannot edit the plan doc it's working from.
3. **Archive-write confinement** — the executor cannot write into `archive/` except one sanctioned fallback path.
4. **Touched-files / branch-pin scope** — commits are checked against declared scope, and self-commit is gated to EM-only by default.

## Key Decisions

### Sidecar mechanism: universal run-report subsumes flight-recorder
<!-- src: plan34-005 plan34-006 plan34-007 plan34-008 plan34-009 plan34-010 plan34-011 plan34-013 -->

The flight-recorder sidecar was **subsumed**, not left to coexist alongside a newer mechanism — PM-ratified over the additive-option alternative (DEC-1). There is now one sidecar mechanism for every scoped subagent, chunk executors included.

- **Injection point**: folds into `enforce-agent-dispatch-mode.py`, the single `updatedInput` emitter allowed per `Agent` matcher. The emit-gate widens to fire on *either* mode-elevation-needed *or* sidecar-provisioned (DEC-2).
- **Schema**: a superset of flight-recorder fields plus universal fields. `divergence` is object-typed (`{diverged, summary, detail}`), not an array — this keeps it backward-compatible with existing flight-recorder consumers (DEC-3).
- **Injection framing is unconditional, not an offer (revised post-DR-091)**: DEC-4 governs whether a sidecar gets provisioned at all — only `report_sidecar`-eligible types get one prescaffolded, so ineligible types aren't over-provisioned with empty docs. It never licensed treating a sidecar that WAS provisioned as optional to fill. DR-091 made that explicit: the sidecar is prescaffolded before the agent's first tool call and its required fields (`divergence`, etc.) are a deliverable. The injected notice text reads "fill it in as part of this dispatch... completing it is expected, not optional" rather than "if you need it" — a live dogfood run found an executor read the old offer-shaped wording as license to leave its sidecar at scaffold.
- **Eligibility (`report_sidecar` policy key)**: a distinct write-capable/multi-step allowlist drawn across both confined *and* exempt agent categories — not a subset of confined alone. A miss fails open to ineligible. `coordinator:executor` is included (DEC-5).
- **Deterministic `provision_key` for chunk executors**: pre-flattened as `<plan-slug>.<chunk-id>` — a single dotted segment (e.g. `2026-07-13-subagent-run-report-subsume.C5`). The dot survives sanitization because it's on the character whitelist, which is what prevents a `<plan-slug>/<chunk-id>` nested form from colliding (DEC-6).
- **Migration then retirement**: the flight-recorder producer chain — claude-klabauter `coordinator/bin/fan-out-dispatch.py`, `coordinator-doc-new`, `execute-plan`, `workstream-complete`'s `d-fold-execution-observations` directive, `coordinator-fold-execution-record` — migrates onto the run-report shape first; only then does the flight-recorder schema and the `tasks/*/flight/` path get retired (DEC-7).
- **Carve-out enforcement lives in a different hook family than expected**: the `tasks/<slug>/flight/` write carve-out is enforced inside the plan-body-immutability hook chain (`coordinator/hooks/scripts/preuse-write-dispatch.py`, dispatching to claude-klabauter's `block_subagent_plan_body_write.py` write-guard), not the sandbox/archive-write hook. Don't look for it under the sandbox confinement family.

### Plan-body immutability
<!-- src: plan17-012 -->

Executors do NOT edit the plan markdown body they're executing — no touching `Status:`, chunk sections, the ledger, or acceptance criteria. `coordinator/hooks/scripts/preuse-write-dispatch.py` (PreToolUse hook; dispatches to claude-klabauter's `block_subagent_plan_body_write.py` write-guard) denies these writes structurally. The dispatch brief must explicitly name the plan doc as out-of-scope, so the executor doesn't burn context attempting (and getting blocked on) a write it was never going to be allowed to make.

### Archive-write confinement, with one sanctioned exception
<!-- src: plan11-039 plan11-040 plan11-041 plan11-042 plan11-043 plan11-044 -->

Project-claude-klabauter's `coordinator_core/write_guards/block_subagent_archive_write.py` is a PreToolUse deny hook: it emits `hookSpecificOutput.permissionDecision` to stdout and exits 0. This is the **correct** deny protocol — do not use `{"decision":"block"}` to stderr with exit 1, which is a non-blocking failure mode that silently lets the write through.

The hook exempts, by path shape, the executor's one authorized fallback write: a completion-log entry at `archive/completed/YYYY-MM/<entry>.md`, per `executor.md § Archive Fallback`. This is explicitly sanctioned behavior, not a gap — the hook must not block it.

PM resolution on scope: **HYBRID** — keep the archive subagent-block hook *and* baseline rules, applied across all 10 flagged paths (not hook-only, not doctrine-only). Two of the resulting entries deserved standalone treatment: E1 (sidecar immutability landed as a `## Sidecar Immutability` section in `agents/review-integrator.md`'s baseline prompt, not just the dispatch brief) and E5 (the archive-write hook itself, above). The remaining entries (E2–E4, E6–E10) are narrower doctrine calibrations — coarse `agent_id` gating, sidecar disposition annotation, dogfood binding — folded into existing surfaces rather than new mechanisms.

### Touched-files scope and branch-pin
<!-- src: plan03-006 plan03-007 plan03-008 -->

Scope tracking uses **`agent_id` linkage**, not `parent_session_id`. Two mechanical writers cooperate: an EM-side `track-dispatched-agents.py` (PostToolUse hook on the `Agent` tool) and a modified `track-touched-files.py` that writes `agent_id` from the subagent side.

`--scope-from` mode deliberately **skips** the agent-id union — the declared scope is treated as exhaustive. Any out-of-scope dirty file fails the commit unless `--allow-out-of-scope-dirty` is passed. This is a stricter, opt-in mode distinct from the default agent-id-union scope check.

(The original plan that proposed this was split after the Staff Engineer review: Issue C moved to a session-misidentification fix, Issue A became the agent-id-linkage plan above, and Issue B carried forward unchanged in the parent plan.)

### Executor self-commit gate (EM-only by default)
<!-- src: plan17-014 plan17-015 plan17-016 plan17-017 -->

Per the PM's commit-model ruling (AC6, the subagent commit model), the executor does not commit
at all — it writes/edits and reports back, the EM commits. Claude-Klabauter's M4 PreToolUse guard
(`coordinator_core/bash_guards/`) denies any `git commit` (plain or via `coordinator-safe-commit`)
that resolves to a Sonnet/Haiku subagent context; there is no authorized executor commit path. See
`scoped-safety-commits.md § 8` and SC-DR-006/SC-DR-008 for the parallel gate there.

Executors set no context variable and take no gate-arming first action. Enforcement is
non-cooperative: the PreToolUse chain resolves the caller from harness-supplied identity the agent
cannot unset, and a confined executor's Bash is allowlist-confined — `git commit`,
`coordinator-safe-commit`, `scoped-git-commit`, and the invoke CLI on any committing op are denied
however the command is spelled. Nothing an executor does or omits arms or disarms this. A signal
the subagent could `unset` (a cooperative, fail-open env-var gate) would not meet this bar, which
is why enforcement is non-cooperative and harness-resolved rather than agent-armed.

## Patterns

### Escalation classes: FIXABLE vs STRUCTURAL vs BLOCKED
<!-- src: plan01-003 -->

Executor failures split into two classes with different handling:

- **FIXABLE** — type errors, import issues, minor logic bugs. Fix-forward, capped at 2 attempts.
- **STRUCTURAL** — the approach is wrong, the spec contradicts itself, a dependency is missing, or the change would break an unexpected surface. Escalate *immediately* with a structured BLOCKED report: name the specific issue, what was tried, and a suggested resolution. This lets the coordinator update the spec and re-dispatch rather than burning attempts on a doomed approach.

The discriminator is the same correctness-vs-direction split used elsewhere in doctrine: a FIXABLE problem is local and mechanical; a STRUCTURAL one means the spec or plan itself needs to change before more attempts are useful.

### Recovering partial executor output after a crash
<!-- src: hand01-025; also c7-014 (distill run 2026-08-06-14h38) -->

When an executor's output survives a crash mid-chunk, the recovery path is **recover, not re-run**: verify the partial output against the plan's acceptance criteria, then commit the verified union. A live example (C9) recovered this way rather than being re-dispatched from scratch — re-running throws away correct partial work that a verification pass could have salvaged.

The same recover-not-rerun precedent holds at wave scale, not just per-chunk: in a five-way parallel executor wave, two of the five crashed mid-response. Their partial work had already persisted to disk, so the remainder executors picked it up and finished it rather than the crashed chunks being re-run from scratch. This is the multi-agent-wave analogue of the single-executor recovery pattern above — persisted partial work survives a crash and is a completion input for whichever executor picks it up next, not a discard-and-restart signal.

### Freeze a review slice per-commit, not as a range, on a shared branch
<!-- src: lessons-outbox c6f577e0, from claude-klabauter-em 2026-08-03; re-hit independently 2026-08-04 -->

A partitioned `/workstream-complete` review that freezes its slices with a contiguous range —
`git diff <first>^..<last>` across this session's own commits, or the `range=` the brightline
gate prints — hands the reviewer someone else's work. On a concurrent shared branch that range
also spans interleaved peer commits, and if the range base predates a file's creation the
reviewer sees untouched files as brand-new additions.

The skill already states that a review-trail `sha_range` must contain only this session's own
commits, and that a contiguous range spanning them is usually impossible on a concurrent branch.
**The identical constraint applies to freezing the review DIFF itself** — that is the part
nothing said, and the part that keeps getting re-learned.

Freeze per-commit (`<sha>~1..<sha>` — `~1`, never `^`: cmd.exe eats a literal `^` in argv on Windows) and concatenate, or filter the range by an explicit pathspec
of the session's own touched files.

Two symptoms to recognise, both of which cost a reviewer a diversion before they reach you:
a reviewer reporting a finding about a file you do not recognise touching, and a reviewer
reporting a one-line edit as a several-hundred-line "new file".

### Residual routing: mid-execution discoveries go to ceremony, not plan prose
<!-- distilled: run 2026-08-06-14h38; src: c12-015 (archive/completed/2026-08/2026-08-06-adhoc-e08d6c.md) -->

A residual discovered mid-execution — a defect, gap, or follow-up noticed while working a chunk but out of scope for it — is **routed, never written into the plan body as prose**. Dumping it inline (an ad-hoc paragraph under the chunk, a footnote in the ledger) is itself the violation this rule targets; it also collides with plan-body immutability (§ above) since the executor cannot edit that surface anyway.

`execute-plan § 3d` names the **closed exit set** for a residual — exactly one of:

- dispatch a follow-up agent,
- add a spine row,
- `coordinator-queue-append` (structured bug/debt/improvement queue entry),
- raise a PM scope question.

**Rejected: an inline-rationale license.** A residual has no row, no id, no grouping — there is nothing for a future reader to file it under, so "just leave a note explaining why" is not an accepted sixth option. If none of the four exits fit, that itself is a signal the residual needs PM scoping, not prose.

**Safety net**, in case a residual slips past the point of discovery: `/quick-wrap` step 2 and `/workstream-complete`'s Execution-Residual Sweep both re-check for undisposed residuals before close.

**Tripwire**: `RESIDUAL-ROUTING-NOT-PROSE` — grep for this identifier before authoring any doctrine or dispatch text that might re-introduce an inline-rationale escape hatch.

## Reference

| Mechanism | Enforcement | Bypass surface |
|---|---|---|
| Sidecar / run-report | `enforce-agent-dispatch-mode.py` injection + `report_sidecar` policy key | N/A — provisioned unconditionally for eligible types; filling it is a deliverable (DR-091), not optional |
| Plan-body immutability | `preuse-write-dispatch.py` (PreToolUse deny; dispatches to claude-klabauter's `block_subagent_plan_body_write.py`) | none (hard block) |
| Archive-write confinement | claude-klabauter `block_subagent_archive_write.py` (PreToolUse deny, path-shape exempt) | sanctioned `archive/completed/YYYY-MM/<entry>.md` path only |
| Touched-files scope | `track-dispatched-agents.py` + `track-touched-files.py` (agent_id linkage) | `--scope-from` + `--allow-out-of-scope-dirty` |
| Self-commit gate | Claude-Klabauter's `coordinator_core/bash_guards/` PreToolUse guard denies every subagent-context `git commit` (plain or via `coordinator-safe-commit`), non-cooperatively | none — see PM's commit-model ruling |
