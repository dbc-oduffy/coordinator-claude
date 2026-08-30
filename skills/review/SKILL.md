---
name: review
description: "Review a plan/design doc, a code diff, or a roadmap spine/sprint slice — findings land on the artifact."
version: 2.0.0
argument-hint: "--surface plan|diff|roadmap"
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# coordinator:review

<!-- Purpose: Merged decision-tree router for plan-review, code-review, and roadmap/sprint-review workflows, arg-branched on --surface plan|diff|roadmap. Covers outgoing (pre-flight + dispatch) and incoming (triage + integrate) directions for both surfaces. Does NOT cover the frozen weekly diff at /workweek-complete Step 7 — that is coordinator:parallel-code-review. -->

**Trigger:** a reviewable artifact exists — a plan/design doc/RFC, a code change, or a roadmap spine/sprint slice — outgoing when nothing on it has been reviewed yet, incoming when a reviewer's findings have landed.

**When NOT to use:** frozen weekly diff at `/workweek-complete` Step 7 → `coordinator:parallel-code-review`. Stuck/oscillating → self-monitor, don't dispatch a reviewer. Pure mechanical citation check, no Opus → `docs-checker` directly. `--surface plan` mid-drafting, `--surface diff` mid-implementation, or `--surface roadmap` before the PM has shape-approved the spine → keep working. A finding about how one stub will be BUILT is plan altitude, not roadmap altitude → route it to that stub's own plan review. `--surface diff` pure test-output classification → capture stdout/stderr to a file, dispatch `test-evidence-parser` on it.

`--surface` is resolved before this skill loads. Pre-flight checks, reviewer-tier precedence, sequencing exceptions, and prior-art mutability are retrieved by `review-assemble brief`, scoped to the resolved surface (segment set: `coordinator/skills/review/residue/`).

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## Branch A — Outgoing

_A reviewable artifact exists for `--surface`, no reviewer invoked yet this iteration._

### A.1 — Pre-flight

**Diff freeze:** only the caller knows the intended range — `code-reviewer` never selects its own. Freeze via `freeze-review-diff` with the caller-chosen range and slice-id before dispatch; never default a shared `work/*` branch to `origin/main...HEAD` (sweeps in sibling sessions' reviewed commits). Inject the frozen diff path as the primary dispatch artifact.

**Reviewers don't execute.** Bash is read-only inspection — no interpreter, scratch files, or test runs. A runtime claim gets the EM running the probe before dispatch and pasting its output into the brief as evidence, never a task. The verdict's `executed: <yes|no>` discloses whether a WARN was empirically checked or hand-traced.

### A.2 — Reviewer selection and dispatch

<!-- engine-gap: field=review.reviewer_selection producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
Reviewer selection (routing-table match, tier precedence, effort) is a signal-lookup a program can compute; no producer AUTOMATES it yet — the plan carries the input, nothing yet merges it at dispatch time. Until then:

- **Routing table:** merge `coordinator/routing.md` with every enabled plugin's `routing.md` fragments into one composite table; match signals to identify Reviewer 1 (domain specialist) and Reviewer 2 (generalist, if needed) — same table both surfaces.
- **Read `review_signals` off the plan first.** A plan carrying the field resolves each id through `coordinator/contract/review-signals.json` — membership is enforced by the contract's parity test plus the frontmatter write guard where a coordinator engine is installed, never by a second copy of the vocabulary here. An id present in `review_signals` but ABSENT from the contract surfaces loudly (name the unrecognized id, do not proceed as if unset) rather than silently falling through to prose-matching. Hand-matching the routing table against prose is the fallback for a plan carrying **no** `review_signals` field at all, not the default path.
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

**Reviews are sequential, never parallel** — integrate finding-set 1 before dispatching reviewer 2. One exception: the merge-gate carve-out at `/workweek-complete` Step 7 — frozen weekly diff, orthogonal lenses, no-rewrite synthesizer. Never mid-session, at `/merge-to-main`, at `/workday-complete`, or on plan reviews (never parallelized).

**Pre-flight sidecars are consumed alongside the plan**, never inserted into that chain; two Sonnet pre-flights gate before an Opus reviewer, and `plan-coverage-checker` has no EM opt-out.

**Angelique (apm) trigger — size-gated, plan-review-only.** They are wired into the `full` review
tier's final stage (`contract/review-roster-fragment.json`), sequenced last — after
`code-reviewer`/the Staff Engineer and after the Director of Engineering (`eng-director`) — since their ELI5-and-challenge pass makes
most sense against a plan the technical and DoE-altitude passes have already shaped. They have no
`review-signals.json` entry: they are SIZE-gated on the plan's own `sizing_object` (frontmatter
citation -> `estimate.tshirt`), not subject-matter-signal-gated, so they are reachable purely via the
roster's tier walk. **They never gate:** their `blocking_verdicts` entry is `null`, identical to
`coordinator:docs-checker` — they challenge, they do not block.

**They fire at M and above.** The tier walk's consumer bucketing (`XS/S -> lightweight`,
`M/L -> standard`, `XL/XXL -> full`, `coordinator/tests/test_review_roster_fragment.py:56`) lives in
the sizing-consumer's dispatch-emit engine, outside this repo, and cannot express a floor between M
and L. They are therefore rostered in **both** `standard` and `full`, which makes M-and-above one
rule rather than a threshold this file re-derives. Their `effort: low` is what makes that
affordable at M volume — the challenge is a set of standing questions, not a deep technical audit.
Never add a second threshold surface here to carve M back out; the roster membership IS the
threshold.

---

## Branch B — Incoming

_A reviewer has returned output. The integrator applies; the EM checks whether anything should
come back out._

**The double-check is a disagreement scan, not a re-adjudication.** Findings reaching the EM have
already been filtered at the reviewer and dispositioned by the integrator, so re-judging each one
repeats the pipeline's work. Read the applied diff and the integrator's escalations, and revert
what you disagree with. The classification below is where escalations land, not a per-finding gate
the EM walks.

**Integration is not measured by count.** "Every nitpick must land" is not the bar — severity and
the integrator's confidence floor do the filtering, and reverting a nit you disagree with is a
correct outcome, not a skipped step.

**Forbidden:** defer-to-later, capture-for-backlog, time-estimate-as-rationale. Any of these → surface to PM, the EM does not decide to defer. Reverting a finding you disagree with is none of those — it is a disposition, and it belongs in the triage record with its reason.

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

**`/review` fires on exiting `/plan`, not after an announcement.** Naming review as the next step
and stopping is the failure this sequencing exists to remove — the EM invokes it, in the same turn,
without waiting to be asked. Same rule as the review gate's own vehicle
(`coordinator:parallel-code-review`): a gate that waits to be told to continue is not a gate.

---

## Cross-reference exit

After Branch B for a multi-reviewer review and Reviewer 1 is integrated, return to A.2 for Reviewer 2 — this skill is re-entrant.

Execution-authorization gate, stamp-op invocation, and prior-art mutability/reviewer-elevation (plan-only) are assembled by `review-assemble brief`.

After authorization, the EM owns the dispatch-gate graph before the first executor dispatch: enumerate touched files per task, mark file-overlap/output-consumption/contract-change gates only, size per-executor scope ~5-10 min (15 min ceiling), author parallel-wave prompts with explicit peer-scope prohibition. Procedure: `coordinator:execute-plan` Phase 1.5.
