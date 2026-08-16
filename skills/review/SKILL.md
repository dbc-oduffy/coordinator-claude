---
name: review
description: "Review a plan/design doc or code diff — findings land on either one."
version: 2.0.0
argument-hint: "--surface plan|diff"
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# coordinator:review

<!-- Purpose: Merged decision-tree router for plan-review and code-review workflows, arg-branched on --surface plan|diff. Covers outgoing (pre-flight + dispatch) and incoming (triage + integrate) directions for both surfaces. Does NOT cover the frozen weekly diff at /workweek-complete Step 7 — that is coordinator:parallel-code-review. -->

**Trigger:** a reviewable artifact exists — a plan/design doc/RFC, or a code change — outgoing when nothing on it has been reviewed yet, incoming when a reviewer's findings have landed.

**When NOT to use:** frozen weekly diff at `/workweek-complete` Step 7 → `coordinator:parallel-code-review`. Stuck/oscillating → self-monitor, don't dispatch a reviewer. Pure mechanical citation check, no Opus → `docs-checker` directly. `--surface plan` mid-drafting, or `--surface diff` mid-implementation → keep working. `--surface diff` pure test-output classification → capture stdout/stderr to a file, dispatch `test-evidence-parser` on it.

`--surface` is resolved before this skill loads. Pre-flight checks, reviewer-tier precedence, sequencing exceptions, and prior-art mutability are retrieved by `review-assemble brief`, scoped to the resolved surface (segment set: `coordinator/skills/review/residue/`).

**Invoking this skill IS the dispatch request** — not a separate ask. Doesn't waive any gate this skill names for itself (execution-authorization, per-session cross-repo-commit assent, ask-before-external-action). Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## Branch A — Outgoing

_A reviewable artifact exists for `--surface`, no reviewer invoked yet this iteration._

### A.1 — Pre-flight

**Diff freeze:** only the caller knows the intended range — `code-reviewer` never selects its own. Freeze via `freeze-review-diff` with the caller-chosen range and slice-id before dispatch; never default a shared `work/*` branch to `origin/main...HEAD` (sweeps in sibling sessions' reviewed commits). Inject the frozen diff path as the primary dispatch artifact.

**Reviewers don't execute.** Bash is read-only inspection — no interpreter, scratch files, or test runs. A runtime claim gets the EM running the probe before dispatch and pasting captured output into the brief as evidence, never a task. Verdict line's `executed: <yes|no>` discloses whether a WARN was empirically checked or hand-traced.

### A.2 — Reviewer selection and dispatch

<!-- engine-gap: field=review.reviewer_selection producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
Reviewer selection (routing-table match, tier precedence, effort) is a signal-lookup a program can compute; no producer emits it yet. Until then:

- **Routing table:** merge `coordinator/routing.md` with every enabled plugin's `routing.md` fragments into one composite table; match signals to identify Reviewer 1 (domain specialist) and Reviewer 2 (generalist, if needed) — same table both surfaces.
- **Tier precedence** (Sonnet-vs-Opus, single-vs-cross-domain) is surface-specific, assembled by `review-assemble brief`.
- **Effort is PM-gated, not an EM dial.** `routing.md`'s Effort field is PM-facing reference only — never put a level in a dispatch prompt or narrate one unless the PM named it.
- **the Director of Engineering:** cross-team/consumer-leak signal → dispatch standalone as primary (director-altitude posture in brief; no `mode` arg), skip the Staff Engineer. Chained-after-the Staff Engineer ("backstop") is the High-effort-architectural routing entry, not the Director of Engineering's only mode.
- `--reviewers "name1,name2"` skips auto-detection; report "PM-directed review: [name1] then [name2]."
- **Tier vs. complexity, not importance:** one reviewer suffices unless a second would likely *contradict*, not just add diminishing-return notes.

**Pipeline phases** (docs-checker, prior-art-checker/plan-coverage-checker, external-pattern-checker, integrator, backstop, report) aren't optional — walk them inline per the surface's assembled phase list.

**Persist findings on the pre-provisioned sidecar** (`state/subagent-share/<session>/<provision_key>.md`, already in the dispatch brief — `staff-eng-review` for personas, `review-findings` for `code-reviewer`) via **Edit**, not a Bash redirect or hand-scaffold.

**Persona/Opus reviewer** writes findings to its sidecar, returns `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`; EM passes that path to the integrator. `code-reviewer`'s diff-only Sonnet pattern is assembled by the op.

**Multi-reviewer chain:** each reviewer gets its own provisioned sidecar; integrator dispatches once per reviewer against its returned path. A trivial/unfilled returned sidecar fails loud (BLOCKED) at intake.

### A.3 — Sequencing

Sequential by default; integrate Reviewer 1 before dispatching Reviewer 2 — see `em-operating-doctrine.md` § How to Review What Came Back. One exception: the merge-gate parallel carve-out, ONLY at `/workweek-complete` Step 7 on a frozen weekly diff with orthogonal lenses + a no-rewrite synthesizer. Never applies mid-session, at `/merge-to-main`, at `/workday-complete`, or to plan reviews (plans are never parallelized).

---

## Branch B — Incoming

_A reviewer has returned output; EM is deciding disposition per finding._

**Forbidden:** defer-to-later, capture-for-backlog, time-estimate-as-rationale. Any of these → surface to PM, the EM does not decide to defer.

**Provenance gate — resolve before triage.** Reviewer (persona/`code-reviewer`) sidecar at `state/subagent-share/<session>/<key>.md`? → table below applies. Pre-flight lens checker (`prior-art-checker`, `plan-coverage-checker`, `docs-checker`, `external-pattern-checker`) sidecar at `state/plan-sidecars/<plan-stem>.<lens>.md`? → `review-integrator`'s intake guard denies it; dispatch `coordinator:enricher` with the lens sidecar path + adjudicated items instead. Never hand-author around the denial.

<!-- engine-gap: field=review.finding_disposition producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
Finding classification/disposition below is a lookup a program can compute from finding shape; no producer emits it yet.

- **Tradeoff-free correctness fix** (factual error, broken citation, wrong API/precedence, internally inconsistent rule, clear-path off-by-one) → dispatch `review-integrator` (`mode: "auto"`) at the reviewer's sidecar; EM spot-checks the diff. **Never hand-author** — the integrator re-checks each finding against current disk, catching stale/mis-scoped claims self-authoring would apply at face value. Exceptions: (a) single-agent math/precedence/symbolic-reasoning needs source verification first; (b) reserved-word collisions get double-quoted, not renamed; (c) closure-bar fallback feasibility is engineering verification (read the cited file), not a PM question.
- **Artifact-shape tradeoff** (architectural direction, scope, sequencing, file organization, abstraction boundary) → surface to PM with finding + reasoning, wait. Plan reviews skew heavily here. YAGNI/scope-trim, refactor-over-patch, and build-vs-defer are always PM, never auto-trimmed even framed tradeoff-free.
- **Multiple findings imply a structural refactor** → don't integrate piecemeal; surface a refactor proposal.
- **Premise/hypothesis challenge** (reviewer disputes the artifact's framing, or claims a bug where it's correct) → read the cited evidence at source, not the paraphrase; confirm or revise the premise.
- **Independent reviewers converge on the same issue** → high-confidence, apply via integrator without per-finding verification. Single-agent findings (especially math/logic/precedence) still need it. On divergence, read source rather than tiebreak by vote.
- **Worker Dispatch Recommendations block present** → dispatch each named worker (reviewers name, EM dispatches), feed output back into EM context. Surface-specific eligibility and the test-evidence-parser capture-before-dispatch rule are assembled by the op.
- **Default/unmatched** → apply via integrator; default is integrate, not ratify, same exceptions as above.

---

## Cross-reference exit

After Branch B for a multi-reviewer review and Reviewer 1 is integrated, return to A.2 for Reviewer 2 — this skill is re-entrant.

Execution-authorization gate, stamp-op invocation, and prior-art mutability/reviewer-elevation (plan-only) are assembled by `review-assemble brief`.

After authorization, the EM owns the dispatch-gate graph before the first executor dispatch: enumerate touched files per task, mark file-overlap/output-consumption/contract-change gates only, size per-executor scope ~5-10 min (15 min ceiling), author parallel-wave prompts with explicit peer-scope prohibition. Procedure: `coordinator:execute-plan` Phase 1.5.
