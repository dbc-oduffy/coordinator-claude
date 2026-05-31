---
title: Review integration doctrine
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator/docs/wiki/receiving-code-review.md
  - plugins/coordinator/docs/wiki/reviewer-premise-challenge.md
  - plugins/coordinator/docs/wiki/prior-art-checker.md
  - plugins/coordinator/docs/wiki/docs-checker-pre-review.md
---

# Review Integration Doctrine

How to receive and apply reviewer findings correctly — the failure modes that appear at integration time rather than review time.

## Re-verify reviewer premises against artifacts landing after review

Schemas, function signatures, and file layouts can change between when a reviewer writes their findings and when the integrator applies them. A reviewer that writes "confirm field X exists before shipping" may be referencing a schema that has since been updated by a concurrent executor. Integrating the finding blindly adds a redundant check or, worse, rewrites something that no longer needs rewriting.

Integrator discipline: before accepting any finding that contains "TBD," "confirm later," "verify before applying," or a premise about a schema/path/API, read the current state of the referenced artifact. If the premise no longer holds, drop the finding (not the whole review — just that finding) and note the drop in the integrator's report.

This is structural at concurrent-EM cadence. On shared branches, an executor may have landed changes while the review was in flight. The reviewer's frame is a snapshot; the integrator works against HEAD.

## Apply tradeoff-free fixes silently; surface tradeoffs to PM

→ coordinator/CLAUDE.md § Reviewer findings — apply, don't ratify

Correctness fixes (wrong API name, missing import, factual error, precedence) fold into the artifact via the integrator without EM narration or PM escalation. These have no tradeoff; the finding is simply correct.

Tradeoffs (cost vs. value, scope expansion, architectural direction, visible behavior change) go to the PM before integrating. The integrator writes an escalation list; the EM presents it. The PM decides.

The failure mode this prevents: EM treating every review finding as a question requiring PM sign-off, which bogs down integration and inverts the relationship between mechanical correctness and product judgment.

## Chain-end review and plan-time review catch different defect classes

Plan-time review (the Staff Engineer on the stub, prior-art-checker on the plan) checks substrate and approach: are the paths real, is the schema correct, does this contradict prior doctrine, is the architecture coherent? These checks work against the plan artifact before any code is written.

Chain-end review (session-end `code-reviewer` or `code-reviewer`+the Staff Engineer on the landed diff) catches a different class: boundary-relabeling bugs (where a function's name or contract shifted during implementation), integration-seam mismatches (where two independently-implemented chunks don't compose), and structural drift from the plan. These defects are invisible at plan time because they emerge from the gap between intent and implementation.

Running only plan-time review and skipping chain-end review is not "sufficient review" — it is review that structurally cannot see the defect class that most commonly survives execution.

→ coordinator/CLAUDE.md § Session-end review and marker trail (under Review Sequencing) for the chain-end review procedure.

## Single-agent math and precedence findings need verification

A single reviewer flagging a logic error, arithmetic mistake, or operator-precedence bug requires verification before integration — do not apply single-agent math/precedence findings silently. The false-positive rate on single-agent findings of this class is high enough that acting on them without verification introduces regressions.

The confidence threshold is convergence: two or more independent agents flagging the same issue from different entry points. One agent with high-confidence framing is not the same as convergence.

→ coordinator/CLAUDE.md § Convergence as Confidence  
→ coordinator/CLAUDE.md § P0/P1 Verification Gate

## Pre-flight sidecars do not require integration before the first reviewer

The sequential-review HARD RULE ("integrate Reviewer 1 before Reviewer 2") applies to **named persona reviewers** — the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering. It does NOT apply between a Sonnet pre-flight (docs-checker, prior-art-checker, external-pattern-checker) and the first named reviewer.

The reasoning is structural, not a convenience exception. The named reviewer is exactly the agent whose Opus-tier architectural judgment we want shaping direction-of-correction on prior-art Conflicts. Front-loading EM disposition before the reviewer sees the plan inverts the leverage: it forces the EM to make architectural calls the reviewer was dispatched to make, and it freezes prior art into "plan must yield" rather than asking which surface is the more current artifact. The post-reviewer integrator pass is where prior-art-side edits land — across the plan, the wiki, or both — per the reviewer's recommendation and the EM's direction call.

What this means in practice:

- **docs-checker** AUTO-FIX corrections land inline per its own contract (`docs/wiki/docs-checker-pre-review.md`). No integrator pass between docs-checker and the reviewer; the sidecar travels with the artifact for the reviewer's awareness.
- **prior-art-checker** sidecar travels unintegrated. The reviewer sees `Conflicts` / `Compatible-but-relevant` / `Silent` buckets and recommends a direction-of-correction per Conflict. EM pre-disposition in the dispatch brief is optional, reserved for cases where the direction is mechanically obvious (e.g., a Conflict against load-bearing doctrine that's already settled). When the EM does pre-dispose and the reviewer disagrees, the integrator escalates as ASK — never silently applies either direction. → `agents/review-integrator.md § Prior-Art Conflict Resolution`.
- **external-pattern-checker** sidecar folds into the reviewer's dispatch prompt as ad-hoc context (per its own consumption contract), not as an integration step.

What still requires integration between artifacts: every pass between two named persona reviewers. If the Staff Engineer runs first and recommends changes, the integrator lands them before the Game Dev Reviewer sees the artifact. That's the rule the HARD RULE was written to enforce, and it's unaffected.

→ coordinator/CLAUDE.md § Review Sequencing (pre-flight carve-out bullet)  
→ `docs/wiki/prior-art-checker.md § Bidirectional resolution`  
→ `agents/review-integrator.md § Prior-Art Conflict Resolution`

## Re-run mechanical pre-flights after material plan amendments

Pre-flights (path scout, prior-art-checker, docs-checker) are point-in-time. A material plan amendment — adding a new component, changing a schema decision, reordering chunks — creates a new claim surface that the original pre-flight did not cover. Stale pre-flight findings at integration cause the integrator to accept or reject findings against a plan that no longer matches what was reviewed.

The rule: after any material amendment, re-run the relevant pre-flights before dispatching the next reviewer. "Material" means any change that alters paths, APIs, schema fields, or architectural approach. Prose clarifications and wording changes do not require re-run.

→ coordinator/CLAUDE.md § Plan-First Workflow → Pre-Dispatch Verification ("Re-run mechanical pre-flights after material plan amendments")  
→ `docs/wiki/prior-art-checker.md` for prior-art-checker procedure  
→ `docs/wiki/docs-checker-pre-review.md` for docs-checker procedure

## EM persists inline reviewer output before dispatching the integrator

When a reviewer agent's tool surface omits Write/Edit (the Sonnet `code-reviewer` is the
canonical case — its frontmatter `tools:` list contains no Write or Edit, so it physically
cannot write files), the reviewer returns findings as its final assistant message rather
than writing to the spec'd sidecar path. The `review-integrator` reads from disk per its
intake contract — if findings live only in chat, the integrator either re-derives them
(lossy) or fabricates dispositions on an EM paraphrase (unsafe).

**EM is the persistence layer when the reviewer cannot write.** When a reviewer dispatch
returns inline-with-no-file, do NOT retry the reviewer hoping it writes next time — the
tool absence is structural, not a transient hallucination, and retrying produces the same
inline output. Persist the reviewer's verbatim output to the spec'd sidecar path via
`Write`, preserve the finding-by-finding schema, add a frontmatter line noting
`persisted_by: EM (reviewer returned inline per its own tool surface)`. Then dispatch the
integrator pointing at the disk path as usual. This preserves the audit trail and lets the
integrator operate on canonical findings rather than a paraphrase. The same pattern applies
to any future reviewer whose tool surface omits Write.

**Why not rewrite:** the EM transcribing inline reviewer output is not "synthesis" — it is
persistence. Preserve verbatim. The integrator's job is to read the disk artifact; the EM's
job is to make sure that artifact exists.

→ `agents/code-reviewer.md` — the canonical write-restricted reviewer (read-only tool surface)

## Cross-session review convergence routes through the integrator, not SUPERSEDED prose

**Cross-session review outputs flow through the review-integrator on a single canonical artifact — "SUPERSEDED" prose is not review provenance.**
**Why:** When concurrent EM sessions independently produce review outputs against parallel artifacts, marking the loser SUPERSEDED with a "findings carry forward" assertion is structurally unverifiable — Session B's enrichment may never have seen Session A's reviewer pass.
**How to apply:** at convergence time, the EM that supersedes MUST dispatch the review-integrator with the loser's findings as input and the winner artifact as target — same as a normal integrator pass. Review provenance is not transitive across artifact splits; an asserted carry-forward is just prose. Pairs with `coordinator/CLAUDE.md` § Cross-session reviews converge on one canonical artifact.

*Source: holodeck `tasks/lessons.md` (holodeck-L121, central-promoted 2026-05-28).*
