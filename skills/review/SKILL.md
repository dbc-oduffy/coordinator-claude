---
name: review
description: Review a plan, diff, or roadmap slice; findings land on it.
version: 2.0.0
argument-hint: "--surface plan|diff|roadmap"
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# coordinator:review

**Trigger:** a reviewable artifact exists (plan/design doc/RFC, code change, roadmap spine/sprint slice) — outgoing when unreviewed, incoming when a reviewer's findings have landed.

**When NOT to use:** frozen weekly diff at `/workweek-complete` Step 7 → `coordinator:parallel-code-review`. Stuck/oscillating → self-monitor, don't dispatch a reviewer. Pure mechanical citation check, no Opus → `docs-checker` directly. `--surface plan` mid-drafting, `--surface diff` mid-implementation, or `--surface roadmap` before the PM has shape-approved the spine → keep working. A finding about how one stub will be BUILT is plan altitude, not roadmap altitude → route it to that stub's own plan review. `--surface diff` pure test-output classification → capture stdout/stderr to a file, run `bin/weekly-gate-tests.py --test-output` on it.

`--surface` is resolved before this skill loads. Surface-scoped pre-flight, tier precedence, sequencing exceptions and prior-art mutability come from `review-assemble brief` (segments: `coordinator/skills/review/residue/`).

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## Branch A — Outgoing

_A reviewable artifact exists for `--surface`, no reviewer invoked yet this iteration._

### A.1 — Pre-flight

**Diff freeze:** the caller picks the range, never `code-reviewer`. Freeze via `freeze-review-diff` with the range and slice-id before dispatch; never default a shared `work/*` branch to `origin/main...HEAD`. Inject the frozen diff path as the primary artifact.

**Reviewers don't execute.** Bash is read-only. The EM runs any runtime probe before dispatch and pastes the output into the brief; the verdict's `executed: <yes|no>` discloses it.

### A.2 — Reviewer selection and dispatch

<!-- engine-gap: field=review.reviewer_selection producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->
No producer automates reviewer selection yet. Until then:

- **Routing table:** merge `coordinator/routing.md` with every enabled plugin's `routing.md` fragments; match signals to Reviewer 1 (domain specialist) and Reviewer 2 (generalist, if needed).
- **Start from the plan's `review_signals`**, resolving ids through `coordinator/contract/review-signals.json`. An id absent from the contract surfaces loudly. Hand-matching prose is the fallback only for a plan with **no** `review_signals` field.
- **Effort is PM-gated.** Never put a level in a dispatch prompt unless the PM named it.
- **the Director of Engineering:** cross-team/consumer-leak signal → standalone primary (director-altitude posture in brief; no `mode` arg), skip the Staff Engineer. "Backstop" is the High-effort-architectural entry.
- `--reviewers "a,b"` skips auto-detection; report "PM-directed review: [a] then [b]."
- One reviewer suffices unless a second would likely *contradict*.

Pipeline phases aren't optional — walk them per the assembled phase list.

**Persist findings on the pre-provisioned sidecar** (`state/subagent-share/<session>/<provision_key>.md`) via **Edit**, not a Bash redirect.

**Persona/Opus reviewer** applies every finding in place, writes the `## Findings Ledger` to its sidecar, runs `review-findings-ledger verify --sidecar <path>`, and returns `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`.

**Multi-reviewer chain:** each reviewer gets its own sidecar and verifies its own ledger. An unfilled returned sidecar fails loud (BLOCKED) at intake.

### A.3 — Sequencing

**Code review (a diff): per executor group in plan runs; reviewers apply their own findings.** Slice owners, Kira and the named personas apply in place with exact-text `Edit`s. Kira (`overengineering-reviewer`) edits shipped code only, never plans, and runs only when the EM or PM names Kira. Only a rebuild verdict goes back to the EM; there is no second review round. `/review-code` verifies its own ledger before a second reviewer.

**Plan review:** one parallel wave, each reviewer applying its own findings; a chatty run claims regions by mail (`CLAIM <region>`; review-integration-doctrine.md); a post-wave ledger verify catches lost edits.

**Pre-flight sidecars are consumed alongside the plan.** Non-XL: the Sonnet pre-flights (`docs-checker`, `prior-art-checker`, `plan-coverage-checker`) gate before the Opus reviewer; accepted-XL adds a `plan-reviewer` pass ahead, so four Sonnet-tier passes precede the Opus persona. `plan-coverage-checker` has no EM opt-out.

**Angelique (apm) trigger — size-gated, plan-review-only.** Ladder on `sizing_object` (`estimate.tshirt`): XS/S Sonnet `plan-reviewer`, M and L the Staff Engineer, XL+ adds Angelique and the Director of Engineering. XL is the APM floor; add no second threshold surface. Kira is on no rung and never gates (`blocking_verdicts` is `null`).

---

## Branch B — Incoming

_A reviewer has returned output, having applied every finding in place and verified its own ledger._

**The double-check is a disagreement scan, not a re-adjudication.** Read the applied diff and the ledger; reject what you disagree with via `review-findings-ledger reject --sidecar <path> --finding <id> --reason "<one line>"` — only the EM may run `reject`.

The reviewer applies everything under an `OK`/`WARN`/`BLOCKED` verdict; under `REJECTED`/`PIVOT` (premise failure) or a Kira `rebuild_recommended: true`, it applies nothing and logs every row `suspended`.

**Default is apply once, then continue.** A plan is redone only on an `UNSAVEABLE` finding that names why, or after n attempts on one problem space, when the route is research or a spike, never another plan (`A-REVIEWER-RETURNS-UNSAVEABLE-ONLY-WHEN-THE-PLAN-CANNOT-BE-SAVED`).

**Forbidden:** defer-to-later, capture-for-backlog, time-estimate-as-rationale — surface to PM; the EM does not decide to defer. Rejecting needs a reason.

**Provenance gate — resolve before triage.** Sidecar at `state/subagent-share/<session>/<key>.md` (persona/`code-reviewer`) → the ledger contract applies. Pre-flight lens checker sidecar at `.coordinator-local/plan-sidecars/<plan-stem>.<lens>.md` → dispatch `coordinator:enricher` with that path + adjudicated items; a lens sidecar is never a findings-ledger sidecar.

**An artifact-shape tradeoff** the reviewer applied anyway: read the reasoning, `reject` with a reason if you disagree. YAGNI/scope-trim, refactor-over-patch and build-vs-defer stay PM calls when the finding raises one.

**Worker Dispatch Recommendations block present** → dispatch each named worker (reviewers name,
EM dispatches), feed output back into EM context. Surface-specific eligibility and the
capture-before-classify rule are assembled by the op.

**Rejecting a finding from a plan body makes an existing `mise_prepped_*` attest STALE**, as applying one does. Route to a re-gate (`<settings-home>/bin/mise-prep-gate <plan>`), never a re-stamp. Tripwire: `A-PRESENT-MISE-PREPPED-STAMP-IS-NOT-A-CERTIFICATION`; `coordinator/docs/wiki/lesson-triage/mise-prepped-attest.md`.

**`/review` fires on exiting `/plan`**: the EM invokes it in the same turn, unprompted.

---

## Cross-reference exit

Outside a chatty run, once Reviewer 1's findings are applied, return to A.2 for Reviewer 2.

Execution-authorization gate and stamp-op invocation come from `review-assemble brief`. `/review` writes `reviewer:` + `status: reviewed`; nothing here stamps a plan mise-prepped.

After authorization, the EM owns the dispatch-gate graph before the first executor dispatch: `coordinator:execute-plan` Phase 1.5.
