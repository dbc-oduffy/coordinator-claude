---
title: Review integration doctrine
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator-claude/coordinator/docs/wiki/receiving-code-review.md
  - plugins/coordinator-claude/coordinator/docs/wiki/reviewer-premise-challenge.md
  - plugins/coordinator-claude/coordinator/docs/wiki/prior-art-checker.md
  - plugins/coordinator-claude/coordinator/docs/wiki/docs-checker-pre-review.md
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

Chain-end review (session-end Sonnet or Sonnet+the Staff Engineer on the landed diff) catches a different class: boundary-relabeling bugs (where a function's name or contract shifted during implementation), integration-seam mismatches (where two independently-implemented chunks don't compose), and structural drift from the plan. These defects are invisible at plan time because they emerge from the gap between intent and implementation.

Running only plan-time review and skipping chain-end review is not "sufficient review" — it is review that structurally cannot see the defect class that most commonly survives execution.

→ coordinator/CLAUDE.md § Session-end review and marker trail (under Review Sequencing) for the chain-end review procedure.

## Single-agent math and precedence findings need verification

A single reviewer flagging a logic error, arithmetic mistake, or operator-precedence bug requires verification before integration — do not apply single-agent math/precedence findings silently. The false-positive rate on single-agent findings of this class is high enough that acting on them without verification introduces regressions.

The confidence threshold is convergence: two or more independent agents flagging the same issue from different entry points. One agent with high-confidence framing is not the same as convergence.

→ coordinator/CLAUDE.md § Convergence as Confidence  
→ coordinator/CLAUDE.md § P0/P1 Verification Gate

## Re-run mechanical pre-flights after material plan amendments

Pre-flights (path scout, prior-art-checker, docs-checker) are point-in-time. A material plan amendment — adding a new component, changing a schema decision, reordering chunks — creates a new claim surface that the original pre-flight did not cover. Stale pre-flight findings at integration cause the integrator to accept or reject findings against a plan that no longer matches what was reviewed.

The rule: after any material amendment, re-run the relevant pre-flights before dispatching the next reviewer. "Material" means any change that alters paths, APIs, schema fields, or architectural approach. Prose clarifications and wording changes do not require re-run.

→ coordinator/CLAUDE.md § Plan-First Workflow → Pre-Dispatch Verification ("Re-run mechanical pre-flights after material plan amendments")  
→ `docs/wiki/prior-art-checker.md` for prior-art-checker procedure  
→ `docs/wiki/docs-checker-pre-review.md` for docs-checker procedure
