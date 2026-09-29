---
name: review
description: "Review a plan/design doc, code diff, or roadmap spine/slice — findings land on the artifact."
version: 2.0.0
spec_backlink: archive/specs/2026-05/2026-05-06-review-super-skill.md
argument-hint: "--surface plan|diff|roadmap"
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# coordinator:review

<!-- Purpose: Merged decision-tree router for plan-review, code-review, and roadmap/sprint-review workflows, arg-branched on --surface plan|diff|roadmap. Covers outgoing (pre-flight + dispatch) and incoming (applied-findings triage) directions for both surfaces. Does NOT cover the frozen weekly diff at /workweek-complete Step 7 — that is coordinator:parallel-code-review. -->

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
<!-- Review: code-reviewer — Finding: reviewers must never execute; a runtime claim is EM-verified before dispatch, not delegated to the reviewer's own Bash. -->

### A.2 — Reviewer selection and dispatch

<!-- engine-gap: field=review.reviewer_selection producer=unknown memo=2026-08-14-coordinator-content-repo-em-three-cut-obligations-from-the-corpus-grind.md -->
Reviewer selection (routing-table match, tier precedence, effort) is a signal-lookup a program can compute; no producer AUTOMATES it yet — the plan carries the input, nothing yet merges it at dispatch time. Until then:

- **Routing table:** merge `coordinator/routing.md` with every enabled plugin's `routing.md` fragments into one composite table; match signals to identify Reviewer 1 (domain specialist) and Reviewer 2 (generalist, if needed) — same table both surfaces.
- **Read `review_signals` off the plan first.** A plan carrying the field resolves each id through `coordinator/contract/review-signals.json` — membership is enforced by the contract's parity test plus the frontmatter write guard where a coordinator engine is installed, never by a second copy of the vocabulary here. An id present in `review_signals` but ABSENT from the contract surfaces loudly (name the unrecognized id, do not proceed as if unset) rather than silently falling through to prose-matching. Hand-matching the routing table against prose is the fallback for a plan carrying **no** `review_signals` field at all, not the default path.
- **Tier precedence** (Sonnet-vs-Opus, single-vs-cross-domain) is surface-specific, assembled by `review-assemble brief`.
- **Effort is PM-gated, not an EM dial.** `routing.md`'s Effort field is PM-facing reference only — never put a level in a dispatch prompt or narrate one unless the PM named it.
- **the Director of Engineering:** cross-team/consumer-leak signal → dispatch standalone as primary (director-altitude posture in brief; no `mode` arg), skip the Staff Engineer. Chained-after-the Staff Engineer ("backstop") is the High-effort-architectural routing entry, not the Director of Engineering's only mode.
- `--reviewers "name1,name2"` skips auto-detection; report "PM-directed review: [name1] then [name2]."
- **Tier vs. complexity, not importance:** one reviewer suffices unless a second would likely *contradict*, not just add diminishing-return notes.

**Pipeline phases** (docs-checker, prior-art-checker/plan-coverage-checker, external-pattern-checker, backstop, report) aren't optional — walk them inline per the surface's assembled phase list. The reviewer applies its own findings; there is no separate integrate phase.

**Persist findings on the pre-provisioned sidecar** (`state/subagent-share/<session>/<provision_key>.md`, already in the dispatch brief — `staff-eng-review` for personas, `review-findings` for `code-reviewer`) via **Edit**, not a Bash redirect or hand-scaffold.
<!-- Review: code-reviewer — Finding: pipeline phases run inline per the assembled phase list; the reviewer applies its own findings, there is no separate integrate phase. -->

**Persona/Opus reviewer** applies every finding in place, writes the `## Findings Ledger` to its sidecar, runs `review-findings-ledger verify --sidecar <path>`, and returns `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`; the EM reads the applied diff and the verified ledger. `code-reviewer`'s diff-only Sonnet pattern is assembled by the op.

**Multi-reviewer chain:** each reviewer gets its own provisioned sidecar, applies its own findings, and verifies its own ledger against its returned path. A trivial/unfilled returned sidecar fails loud (BLOCKED) at intake.

### A.3 — Sequencing

<!-- Review: code-reviewer — Finding: code review over a diff runs as one parallel wave where every reviewer applies its own findings; plan review over one artifact stays ordered. -->
**Code review (a diff) is one parallel wave, and every reviewer applies its own findings.**
Slice owners, Kira and the named personas all apply in place with exact-text `Edit`s, including
findings outside their own slice. Nothing downstream applies findings; only a rebuild verdict
goes back to the EM. There is no second review round. The invariant is
"no write against stale text": every writer applies with an exact-text `Edit`, which fails rather
than clobbers when another writer moved the text first. This runs inside the execute
workflow's review stage (`coordinator/skills/execute-plan/SKILL.md`); a diff reviewed outside that
workflow (`/review-code` ad hoc) applies and verifies its own findings ledger before a second
reviewer touches the same diff.

**Plan review over one plan artifact stays ordered.** Reviewers apply their findings in place on
the plan body, so Reviewer 1 applies and verifies its own findings before Reviewer 2 is dispatched.
This is unchanged: only code review over a diff runs as a parallel wave.

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

_A reviewer has returned output, having already applied every finding in place and verified its
own findings ledger. The EM checks whether anything should come back out._

**The double-check is a disagreement scan, not a re-adjudication.** Findings reaching the EM have
already been applied by the reviewer itself and logged to its ledger, so re-judging each one
repeats the pipeline's work. Read the applied diff and the reviewer's findings ledger, and reject
what you disagree with via `review-findings-ledger reject --sidecar <path> --finding <id> --reason
"<one line>"` — only the EM may run `reject`; a subagent invoking it is denied.

**Application is not measured by count.** "Every nitpick must land" is not the bar for the EM's
double-check — reverting (rejecting) a nit you disagree with is a correct outcome, not a skipped
step. It is the reviewer, not the EM, that applies everything under an `OK`/`WARN`/`BLOCKED`
verdict; under `REJECTED`/`PIVOT` (premise failure) or a Kira `rebuild_recommended: true`, the
reviewer applies nothing and logs every row `suspended`.

**Forbidden:** defer-to-later, capture-for-backlog, time-estimate-as-rationale. Any of these →
surface to PM, the EM does not decide to defer. Rejecting a finding you disagree with is none of
those — it is a disposition, and it needs a reason via `reject`.

**Provenance gate — resolve before triage.** Reviewer (persona/`code-reviewer`) sidecar at
`state/subagent-share/<session>/<key>.md`? → the ledger contract above applies. Pre-flight lens
checker (`prior-art-checker`, `plan-coverage-checker`, `docs-checker`, `external-pattern-checker`)
sidecar at `.coordinator-local/plan-sidecars/<plan-stem>.<lens>.md`? → dispatch `coordinator:enricher`
with the lens sidecar path + adjudicated items instead; a pre-flight lens sidecar is never a
findings-ledger sidecar. Never hand-author around this.
<!-- Review: code-reviewer — Finding: a pre-flight lens sidecar is never a findings-ledger sidecar; route each to its own consumer, never hand-author around the split. -->

**An artifact-shape tradeoff** (architectural direction, scope, sequencing, file organization,
abstraction boundary) the reviewer applied anyway is exactly the case the EM's double-check exists
for: read the reasoning, and `reject` it with a reason if the EM disagrees with the direction.
YAGNI/scope-trim, refactor-over-patch, and build-vs-defer stay PM calls when the finding itself
raises one — the reviewer applying the edit does not resolve who owns that call.

**Worker Dispatch Recommendations block present** → dispatch each named worker (reviewers name,
EM dispatches), feed output back into EM context. Surface-specific eligibility and the
test-evidence-parser capture-before-dispatch rule are assembled by the op.

**Rejecting a finding from a plan body invalidates its mise-prep stamp** the same way applying one
did. `mise_prepped_sha` is `canonical_body_sha` of the plan BODY, so a reviewer's or the EM's edit
makes any existing `mise_prepped_*` attest STALE — not absent. Say STALE and route to a re-gate
(`"${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/mise-prep-gate" <plan>`), never to a re-stamp: re-stamping records a
pass the bar was never re-run for. Never read `mise_prepped_by` for presence; the predicate is a
recomputed sha, at every caller. Tripwire:
`A-PRESENT-MISE-PREPPED-STAMP-IS-NOT-A-CERTIFICATION`; four states, four repairs:
`coordinator/docs/wiki/lesson-triage/mise-prepped-attest.md`.

**`/review` fires on exiting `/plan`, not after an announcement.** Naming review as the next step
and stopping is the failure this sequencing exists to remove — the EM invokes it, in the same turn,
without waiting to be asked. Same rule as the review gate's own vehicle
(`coordinator:parallel-code-review`): a gate that waits to be told to continue is not a gate.

---

## Cross-reference exit

After Branch B for a multi-reviewer review and Reviewer 1's findings are applied and verified, return to A.2 for Reviewer 2 — this skill is re-entrant.

Execution-authorization gate, stamp-op invocation, and prior-art mutability/reviewer-elevation (plan-only) are assembled by `review-assemble brief`.

`status: reviewed` and the mise-prep attest are orthogonal by construction — three producers, three
artifacts: `/review` writes `reviewer:` + `status: reviewed`, a blitz landing writes
`status: approved`, and unattended clearance writes `mise_prepped_*`. This skill produces the
first and never the third; nothing here stamps a plan mise-prepped.

After authorization, the EM owns the dispatch-gate graph before the first executor dispatch: enumerate touched files per task, mark file-overlap/output-consumption/contract-change gates only, size per-executor scope ~5-10 min (15 min ceiling), author parallel-wave prompts with explicit peer-scope prohibition. Procedure: `coordinator:execute-plan` Phase 1.5.
