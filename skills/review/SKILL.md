---
name: review
description: "Review a plan/design doc or code diff — findings land on either one."
version: 2.0.0
argument-hint: "--surface plan|diff"
---

# coordinator:review

<!-- Purpose: Merged decision-tree router for plan-review and code-review workflows, arg-branched on --surface plan|diff. Covers outgoing (pre-flight + dispatch) and incoming (triage + integrate) directions for both surfaces. Does NOT cover the frozen weekly diff at /workweek-complete Step 7 — that is coordinator:parallel-code-review. -->

**Trigger:** the skill runs whenever a reviewable artifact exists — a plan/design doc/RFC, or a code change (mid-session diff before commit, completed task before next dispatch, branch ready for `/merge-to-main`, PR landing inline) — outgoing when nothing on it has been reviewed yet, incoming when a reviewer's findings have landed and need processing.

**When NOT to use (either surface):** Frozen weekly diff at `/workweek-complete` Step 7 → `coordinator:parallel-code-review`. Stuck pattern (repeating or oscillating) → self-monitor and break the loop rather than dispatching a reviewer. Pure mechanical citation check with no Opus → run `docs-checker` directly. `--surface plan` mid-drafting (plan not finished) → keep writing. `--surface diff` mid-implementation (no clean review surface yet) → keep coding. `--surface diff` pure mechanical test-output classification → run the test invocation, capture stdout/stderr to a file, then dispatch `test-evidence-parser` directly to `Read` and classify that captured file.

`--surface` is resolved by the caller/engine before this skill loads. The surface-specific procedure detail below this point — pre-flight checks, reviewer tier tables, sequencing exceptions, triage asides, prior-art mutability, and the execution-authorization gate — is retrieved by the `review-assemble brief` op, which reads the segment set scoped to the resolved surface. Segment content: `coordinator/skills/review/residue/`.

**Dispatch authorization — invoking this skill IS the authorization.** The dispatches named below are part of this skill, not a separate thing to get cleared: whoever invoked it has already asked for them. A generic harness preference for working inline rather than delegating does not condition them — it is written for a bare assistant with no operating doctrine, and this system supersedes it by design. Re-asking spends the very context the dispatch exists to protect. The named PM gates in this skill still bind, and ask-before-external-action still binds; nothing else here is a permission question.

---

## Branch A — Outgoing

_Condition: a reviewable artifact exists for the given `--surface` — a plan/design doc/RFC, or a code change (committed or staged) — and no reviewer has been invoked yet on this iteration._

### A.1 — Pre-flight workers

Each surface's pre-flight checks fire independently of one another before dispatch, on their own conditions, and arrive with the assembled residue segment set.

**The diff freeze's range/slice-id is a real judgment call, not something the op resolves for you.** `code-reviewer` cannot obtain its own diff — its Bash is allowlist-confined and it has no `git show`/`git diff`/`git log` access — so before dispatching it, the diff must be frozen via the `freeze-review-diff` op, invoked with the caller-chosen range and slice-id. The op never defaults the range: only the caller knows whether this dispatch is session-scoped, branch/PR-scoped, or plan/chunk-scoped, and a shared `work/*` branch with concurrent sessions must never default to `origin/main...HEAD` (that sweeps sibling sessions' already-reviewed commits into this review). Inject the frozen diff path into the reviewer's dispatch brief as the primary artifact — a dispatch without it is incomplete, not merely suboptimal.

### A.2 — Reviewer selection and dispatch (shared spine)

**This gate dispatches. That is not a question to resolve before proceeding.** Invoking this skill is what authorizes the reviewer dispatch — there is no separate permission to obtain, and stopping here to ask for one is the single most common way this gate fails. If you notice a pull to check first, that is generic caution about spawning agents, not a judgment about this review; the gate does not function without reviewers. Select and dispatch.

**Routing table assembly:** Read the base routing table from `coordinator/routing.md`, scan all enabled plugins for root-level `routing.md` fragments, merge into a composite routing table. Match the artifact's signals against the composite table to identify Reviewer 1 (domain specialist) and Reviewer 2 (generalist, if needed). `coordinator/routing.md` is the source of truth for the signal → reviewer mapping (both surfaces route through the same composite table; see that file for the current fragment set and per-reviewer signals).

**Tier selection is surface-specific** (Sonnet-vs-Opus precedence, single-vs-cross-domain tables, the diff-only Sonnet dispatch pattern) — assembled by the op named above, from the residue segment set.

**Effort is PM-gated — it is not an EM dial.** `coordinator/routing.md`'s Effort field is PM-facing reference, NOT a parameter the EM sets, changes, or surfaces. Dispatch each persona at its natural Opus altitude; do **not** put an effort level (`High`, `Medium`, `Low`) in the dispatch prompt, and do not narrate one to the PM as the chosen level, unless the PM has explicitly named it. If the PM has not named an effort level, omit it entirely. Reading an effort off the table and applying it — even verbatim — is the overreach this rule prevents. The PM owns the effort dial; the EM owns reviewer selection and sequencing.

**the Director of Engineering standalone vs. The Director of Engineering backstop.** When the signal matches a cross-team or consumer-leak row in the routing table, dispatch the Director of Engineering directly as the primary reviewer — describe the standalone / DoE-altitude posture in the brief (do NOT pass a `mode` argument; that is the harness tool param and will error). Do NOT run the Staff Engineer first. Standalone the Director of Engineering is a peer of the Staff Engineer in technical rigor with the additional cross-team authority the Staff Engineer's EM altitude would hedge on. The routing table's chained-after-the Staff Engineer "backstop" entries are the usage for High-effort architectural reviews; that posture is still in play but does not exhaust the Director of Engineering's role.

If `--reviewers "name1,name2"` was provided, skip auto-detection. Use the explicit list — first name is Reviewer 1, second (if any) is Reviewer 2. Report: "PM-directed review: [name1] then [name2]."

**Matching review tier to complexity.** Match tier to complexity, not importance. Routing every "important" artifact to a staff session burns budget without finding more bugs. The heuristic: would a second reviewer likely **contradict** the first, or just add diminishing-return notes? If contradiction is unlikely, one reviewer is enough.

**Pipeline phases** (docs-checker, prior-art-checker/plan-coverage-checker, external-pattern-checker, integrator, backstop, report) are not optional — walk them inline. The applicable surface's phase walk is retrieved by the op named above and arrives with the assembled residue.

**Persist the reviewer/persona findings — provisioned sidecar, doc-handoff contract, no sentinel-append.** Every dispatched reviewer (persona or `code-reviewer`) is auto-provisioned its identity-typed sidecar at spawn (`state/subagent-share/<session>/<provision_key>.md` — `staff-eng-review` for the 6 personas, `review-findings` for `code-reviewer` and the mechanical review workers) — the path is already in the dispatch brief; the engine's `provision_report` capability created it at spawn. Persist findings with **Edit** on that pre-provisioned path — it already exists, so Edit is the direct tool; a Bash redirect is neither needed nor wanted here (`snippets/persona-persisting-findings.md`). There is no EM pre-scaffold, no sentinel-append (`snippets/findings-self-persist-sentinel.md` is not appended to the brief), no injected `docs/plans/*.review.md` path, no variant selection, and no `cs_write_review_claim`.

**Pattern A — persona / Opus reviewer (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering):** it writes its findings to the provisioned sidecar and returns `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. EM reads the returned path and passes it to the integrator. The diff-only Sonnet dispatch pattern (`code-reviewer`) is assembled by the op named above.

**Multi-reviewer chain (either surface):** each reviewer writes to its own provisioned sidecar; the integrator is dispatched once per reviewer pointing at that reviewer's returned path. The intake fails loud (BLOCKED) if the returned sidecar is a trivial/unfilled scaffold — the intake fill-guard, not a per-dispatch-site check.

### A.3 — Sequencing

**Sequential by default (HARD RULE), either surface.** Integrate Reviewer 1's findings via `coordinator:review-integrator` BEFORE dispatching Reviewer 2. The one exception is the merge-gate parallel carve-out, and it applies ONLY at `/workweek-complete` Step 7 on a frozen weekly diff with orthogonal lenses + a no-rewrite synthesizer — it never applies to mid-session, `/merge-to-main`, or `/workday-complete` diff reviews, and it never applies to plan reviews at all (plans are never parallelized; there is no carve-out on that surface).
_See `coordinator/snippets/em-operating-doctrine.md` § How to Review What Came Back._

---

## Branch B — Incoming

_Condition: a reviewer has returned output on the reviewed artifact. EM is deciding what to do with each finding._

**Forbidden triage outcomes (never valid):** defer-to-later, capture-for-backlog, time-estimate-as-rationale. If any of these would be the disposition, surface to PM — the PM decides whether to defer, not the EM.
_See ~/.claude/CLAUDE.md § Engineering Defaults ('Implement and iterate over deliberate and defer') and `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off ("STOP and re-plan when something goes sideways")._

**Provenance gate — resolve this BEFORE the triage table, because the table below routes only reviewer findings.** Every row's destination assumes the finding came from a dispatched reviewer's own sidecar. Check where the finding actually came from:

- _Finding came from a **reviewer** — a persona or `code-reviewer` — whose sidecar is at `state/subagent-share/<session>/<key>.md`?_
  → The triage table below applies as written. Continue.
- _Finding came from a **pre-flight lens checker** — `prior-art-checker`, `plan-coverage-checker`, `docs-checker`, `external-pattern-checker` — whose sidecar is at `state/plan-sidecars/<plan-stem>.<lens>.md`?_
  → **`coordinator:review-integrator` is the wrong agent and its intake guard will deny the dispatch.** It applies reviewer findings only, strictly from a `state/subagent-share/` path named in the prompt; a `state/plan-sidecars/` path is not one, however tradeoff-free the finding is. Applying a lens finding to a plan body is **plan-body maintenance → dispatch `coordinator:enricher`** with the lens sidecar path and the adjudicated items. This is the same fact `coordinator/snippets/em-operating-doctrine.md` states as *"pre-flight sidecars are consumed alongside the plan, not inserted into that chain"* — that clause says what not to do; this row says who does it instead, which is the half that was missing.
  → **Why this misroutes so reliably, named so it stops:** the tradeoff-free row below correctly forbids hand-authoring *however small it looks*, and until this gate existed it named exactly one non-hand-authoring destination. A correct reading of a loud prohibition plus a single offered destination produces the wrong dispatch every time — the defect was the incomplete destination set, not the EM's memory. Do not "fix" a denial here by hand-authoring the edit; that trades a guard hit for the exact failure the prohibition exists to prevent.

Walk each finding against the triage table below — it lands in exactly one row:

- _Tradeoff-free correctness fix?_ (factual error, broken citation, wrong API name, missing cross-reference or import, wrong precedence, internally inconsistent rule/identifier, off-by-one in a clear path)
  → Dispatch `coordinator:review-integrator` with `mode: "auto"` pointing at the reviewer's returned sidecar path (the `DONE: <path>` from A.2 above). EM spot-checks the diff. **Reviewer-sidecar findings only — see the provenance gate above.**
  **Never hand-author the fix yourself, however small it looks.** The integrator is not a cheaper typist — it is a *fresh agent that independently re-checks each finding against current disk before applying it*. That second check catches findings that were wrong, stale, or mis-scoped (a concurrent executor moved the schema; the rename collides with a constraint that landed after the review) — exactly what self-authoring discards by applying the reviewer's claim at face value. "One line / obvious" is the rationalization this rule defeats, not an exception to it.
  Three exceptions narrow the tradeoff-free-fold-in default: (a) a single-agent math/precedence/symbolic-reasoning finding needs verification against source before applying — that shape is exactly the one most prone to confident-but-wrong findings; (b) a reserved-word-collision finding gets double-quoted, not renamed, out from under its callers; (c) closure-bar fallback feasibility is engineering verification (read the cited file before asking), not a PM question.
  - _(i) Math / algebra / precedence / symbolic-reasoning finding from a single agent?_ → Verify against source before applying (exception (a) above).

- _Artifact-shape tradeoff?_ (architectural direction, scope question, sequencing call, file-organization call, abstraction boundary)
  → Surface to PM with finding + reasoning. Wait for direction. Plan reviews skew heavily toward this row — most plan findings are about *what to build*, not *how it's coded*.
  - _(i) YAGNI / scope-trim argument from reviewer?_ → **Always escalation, never auto-trim.** Even framed as tradeoff-free, YAGNI is a product decision. Surface to PM. _See `coordinator/snippets/em-operating-doctrine.md` § How to Decide._
  - _(ii) Refactor-over-patch signal?_ → Refactor is the default when AI is the implementer. Surface to PM with refactor proposal. _See ~/.claude/CLAUDE.md § Engineering Defaults ('Do the right thing, not the easy thing')._
  - _(iii) Build-vs-defer call?_ → Always PM. Never EM-unilateral. _See `coordinator/snippets/em-operating-doctrine.md` § How to Decide._

- _Multiple findings collectively suggest the artifact needs a structural refactor (not just patches)?_
  → Do NOT integrate piecemeal. Surface to PM with a refactor proposal — the aggregate signal is the finding.
  _See ~/.claude/CLAUDE.md § Engineering Defaults ('Refactor over patch') and § Convergence as Confidence._

- _Premise / hypothesis question?_ (reviewer challenges the artifact's framing or motivating hypothesis, or claims a bug/gap exists where the artifact is correct)
  → Read the cited evidence at its source, not the reviewer's paraphrase. Confirm or revise premise either way. Where that evidence lives for the resolved surface is assembled by the op named above, from the residue segment set.

- _Multiple reviewers converged on the same issue from different entry points?_
  → High-confidence; apply via integrator without per-finding verification. The threshold is independence + distinct entry points, not raw count — single-agent findings (especially math/logic/precedence) still require verification first. On reviewer divergence, read source rather than tiebreaking by vote.

- _Worker Dispatch Recommendations block present in reviewer output?_
  → Dispatch each named worker; reviewers name, EM dispatches. Feed worker output back into EM context either way. The surface-specific worker eligibility list (which workers fire on which surface, and the test-evidence-parser capture-before-dispatch rule) is assembled by the op named above, from the residue segment set.
  _See `coordinator/snippets/em-operating-doctrine.md` § How to Review What Came Back, "Reviewer-routed workers"._

- _Default / unmatched?_
  → Apply via integrator. Default is to integrate, not to ratify (the same tradeoff-free-fold-in default and its three exceptions from the first triage row above).

The diff-only triage residue (the performative-agreement guard, the executor out-of-scope reminder, and the probe-wiring brief authority note) is assembled by the op named above.

---

## Cross-reference exit

After Branch B completes for a multi-reviewer review and Reviewer 1 is integrated, return to **A.2** to dispatch Reviewer 2. This skill is re-entrant — each pass walks one direction.

The execution-authorization gate, its precondition, the stamp-op invocation, and prior-art mutability/reviewer-elevation treatment — plan-only concerns — are assembled by the op named above and arrive with the assembled residue.

After authorization, the EM (same session under the carve-out/`/autonomous`, or the fresh execution session under the default) owns the **dispatch-gate graph** before the first executor dispatch: enumerate touched files per task, mark file-overlap / output-consumption / contract-change gates (and only those — narrative causality is not a gate), size per-executor scope to ~5-10 min (15 min hard ceiling), and author parallel-wave prompts with explicit peer-scope prohibition. Procedure: `coordinator:execute-plan` Phase 1.5.
