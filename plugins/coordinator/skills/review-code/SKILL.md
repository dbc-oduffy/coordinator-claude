---
name: review-code
description: Use when a code change / diff / PR is ready for review or code-review findings have landed.
version: 1.0.0
spec_backlink: docs/plans/2026-05-06-review-code-super-skill.md
---

# coordinator:review-code

<!-- Purpose: Decision-tree router for code-review workflows (diffs, PRs, post-implementation, mid-session pre-merge). Covers outgoing (pre-flight + dispatch) and incoming (triage + integrate) directions. Sibling to coordinator:review (which covers plan reviews); merge-gate carve-out is coordinator:parallel-code-review. -->

**Trigger:** EM has a code change ready for review (outgoing): mid-session diff before commit, completed task before next dispatch, branch ready for `/merge-to-main`, PR landing inline. OR a code-review's findings have landed and need processing (incoming).

**When NOT to use:** Plan / design doc / RFC review → `coordinator:review`. Frozen weekly diff at `/workweek-complete` Step 7 → `coordinator:parallel-code-review`. Mid-implementation (no clean review surface yet) → keep coding. Stuck pattern → `coordinator:stuck-detection`. Pure mechanical citation check with no Opus → run `docs-checker` directly. Pure mechanical test-output classification → dispatch `test-evidence-parser` directly.

---

## Branch A — Outgoing

_Condition: a code change exists (committed or staged); no reviewer has been invoked on this iteration._

### A.1 — Pre-flight workers (run BEFORE the Opus reviewer)

Three independent checks. Each fires or skips on its own condition; multiple can fire on the same diff.

**Check 1 — TDD compliance (self-check, no agent)**

- _Code introduces new behavior (feature, fix, refactor that changes externally observable behavior)?_
  → Verify against the TDD checklist before dispatching reviewer. If any test was written *after* the production code, surface to PM with the gap — the review will surface it anyway and a pre-review acknowledgment is cheaper than a Staff Engineer finding.
  _See `docs/wiki/test-driven-development.md` § Verification Checklist._
- _Code is config-only / doc-only / generated code?_
  → Skip TDD self-check.

**Check 2 — Cited external APIs (docs-checker)**

- _Code cites C++ or Unreal Engine APIs?_
  → Mandatory dispatch of `docs-checker`. Other external APIs are EM judgment; in-repo-only skips.
  _See `docs/wiki/docs-checker-pre-review.md` for the full row table._

**Check 3 — Test evidence (test-evidence-parser)**

- _Diff includes **unintended** failing tests, runtime artifacts, or stack traces in the work-in-progress notes?_ (i.e., evidence of a problem the EM has not yet diagnosed — NOT verdict-bearing smoke output where a BLOCK or WARN is the expected outcome)
  → Dispatch `test-evidence-parser` with the failing test command. Read the structured output. Real failures block the dispatch; flakes/env failures get logged and the review proceeds.
  _See `docs/wiki/reviewer-routed-workers.md` § test-evidence-parser._
- _Diff has clean test runs (or no test surface yet — pre-TDD scaffold)?_
  → Skip `test-evidence-parser` at pre-flight; reviewer may still call it via Worker Dispatch Recommendations.

_(EM-initiated pre-flight; the normal case is reviewer-routed dispatch via the Worker Dispatch Recommendations block at Branch B — see `docs/wiki/reviewer-routed-workers.md` § Gotchas. Pre-flight loses the routing-intelligence framing, so use only when the diff already exhibits failure evidence the reviewer would otherwise stumble into cold.)_

### A.2 — Reviewer selection and dispatch

Match tier to complexity, not importance. Routing every "important" diff to a staff session burns budget without finding more bugs. The heuristic: would a second reviewer likely **contradict** the first, or just add diminishing-return notes? If contradiction is unlikely, one reviewer is enough.

| Situation | Correct tier |
|---|---|
| Single-subsystem code change (one feature, one bug fix, one refactor) | `/review-dispatch <range> code` → one reviewer (auto-detects domain). For known-target single-reviewer cases (e.g., obvious Staff Engineer or Game Dev Reviewer match), direct `Agent(subagent_type=...)` dispatch is an acceptable shortcut; `/review-dispatch` is preferred for routing intelligence. |
| Cross-subsystem code change (e.g., UE + Python pipeline; front-end + auth backend) | `/review-dispatch <range> code --reviewers "<domain>,staff-eng"` → two sequential reviewers |
| Contested architectural code change with ≥2 valid implementations AND PM authorized | `/staff-session` review-mode |
| "This is important, I want it done right" | `/review-dispatch <range> code` → one reviewer |
| Code touches auth, security, billing — high stakes but clear approach | `/review-dispatch <range> code` → one reviewer |

- _Code change is genuinely trivial?_ (typo, comment-only, single-line config bump with no behavior change)
  → No review needed; commit and proceed.
- _PM has explicitly waived review on a non-trivial change?_ ("ship it", "skip review", "straight to merge")
  → Exit; this skill does not run. Log the waiver in commit message or PR description: `review: skipped per PM direction YYYY-MM-DD` (greppable).

_See CLAUDE.md § Challenging the PM — `/staff-session` is PM-gated; ask first._

### A.3 — Sequencing

- **In-session code reviews → sequential (HARD RULE).** Integrate Reviewer 1's findings via `coordinator:review-integrator` BEFORE dispatching Reviewer 2.
  _See CLAUDE.md § Review Sequencing._
- **Merge-gate parallel carve-out applies ONLY at `/workweek-complete` Step 7** on a frozen weekly diff with orthogonal lenses + no-rewrite synthesizer. Does NOT apply to mid-session, `/merge-to-main`, or `/workday-complete` reviews.
  _See CLAUDE.md § Review Sequencing ¶ exception (merge-gate code review on frozen diff)._
- _Frozen weekly diff at `/workweek-complete` Step 7?_
  → Exit this skill; use `coordinator:parallel-code-review`.

---

## Branch B — Incoming

_Condition: a reviewer has returned output on a code change. EM is deciding what to do with each finding._

**Forbidden triage outcomes (never valid):** defer-to-later, capture-for-backlog, time-estimate-as-rationale. If any of these would be the disposition, surface to PM — the PM decides whether to defer, not the EM.
_See CLAUDE.md § Plan-First Workflow ¶ implement-and-iterate (project-level) and § Operating Assumptions (global `~/.claude/CLAUDE.md`)._

Walk each finding against the triage table — it lands in exactly one row:

- _Tradeoff-free correctness fix?_ (wrong API name, broken citation, missing import, wrong precedence, factual error, internally inconsistent identifier, off-by-one in clear path)
  → Dispatch `coordinator:review-integrator` with `mode: "acceptEdits"` and the findings. EM spot-checks the diff.
  _See CLAUDE.md § Reviewer findings — apply, don't ratify._
  - _(i) Math / algebra / precedence / symbolic-reasoning finding from a single agent?_ → Verify against source before applying. _See CLAUDE.md ¶ Exception — math, algebra, precedence._

- _Code-shape tradeoff?_ (architectural direction, scope question, file-organization call, abstraction boundary)
  → Surface to PM with finding + reasoning. Wait for direction.
  _See CLAUDE.md § Reviewer findings — apply, don't ratify (escalation triggers)._
  - _(i) YAGNI / scope-trim argument?_ → **Always escalation, never auto-trim.** YAGNI is a product decision. _See CLAUDE.md § Challenging the PM._
  - _(ii) Refactor-over-patch signal?_ → Refactor is the **default** when AI is the implementer. Surface to PM with refactor proposal, not a piecemeal fix. _See CLAUDE.md § Core Principles ('Do the right thing, not the easy thing')._
  - _(iii) Build-vs-defer call?_ → Always PM. _See CLAUDE.md § Challenging the PM ¶ Ask the PM when._

- _Multiple findings collectively suggest a structural refactor (not just patches)?_
  → Do NOT integrate piecemeal. Surface to PM with refactor proposal — the aggregate signal is the finding.
  _See CLAUDE.md § Core Principles ('Refactor over patch') and § Convergence as Confidence._

- _Premise / hypothesis question?_ (reviewer challenges what the code is supposed to do, or claims a bug exists where the code is correct)
  → Read the cited code at the cited line — not the reviewer's paraphrase. Confirm or revise.
  _See `docs/wiki/reviewer-premise-challenge.md` and CLAUDE.md § P0/P1 Verification Gate._

- _Multiple reviewers converged on the same issue from different entry points?_
  → High-confidence; apply via integrator without per-finding verification.
  _See CLAUDE.md § Convergence as Confidence._

- _Worker Dispatch Recommendations block present in reviewer output?_
  → Dispatch each named worker. For code reviews, all four are in scope: `test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`. Reviewers name only the workers that fire on this diff (e.g., `dep-cve-auditor` only if the diff touches dependency manifests; `security-audit-worker` only if the diff plausibly touches an attack surface). Feed worker output back into EM context. Reviewers do not dispatch — EM does.
  _See `docs/wiki/reviewer-routed-workers.md` and CLAUDE.md § Reviewer-Routed Workers._

- _Performative-agreement urge?_ ("you're absolutely right!", "great catch!", "thanks for catching that")
  → STOP. Delete the urge. State the fix factually.
  _See `docs/wiki/receiving-code-review.md` § Forbidden Responses._

- _Default / unmatched?_
  → Apply via integrator. Default is to integrate, not to ratify.
  _See `docs/wiki/receiving-code-review.md` (triage tables, push-back patterns, performative-agreement guard) and CLAUDE.md § Reviewer findings — apply, don't ratify._

---

## Cross-reference exit

After Branch B completes for a multi-reviewer review and Reviewer 1 is integrated, return to **A.2** to dispatch Reviewer 2. This skill is re-entrant — each pass walks one direction.
