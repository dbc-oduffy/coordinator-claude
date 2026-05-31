---
title: Reviewer Premise Challenge
system: reviewer-premise-challenge
status: distilled
distilled_from:
  - archive/specs/2026-05-04-reviewer-premise-challenge.md
distilled_at: 2026-05-06
distilled_run: 2026-05-06-13h00
---

# Reviewer Premise Challenge

## Overview

**Premise-challenge** is the doctrine that reviewers must engage with a plan's *premise* — not just its spelling, structure, or local correctness. A reviewer who only fixes typos rubber-stamps load-bearing assumptions. The system is a **layered defense** at five intervention points; reviewer-side calibration is the LAST and most expensive of the five. Cheap upstream gates close the common case; reviewer-side backstop catches what slips through.

## Architecture

### Five intervention points (cheapest first)

1. **W1 — Negative-search rule** in the `writing-plans` SKILL (plan author).
2. **W2 — Counter-evidence pass** in `repo-specialist` (research stage).
3. **W3 — Patrik Pass 0** premise review (reviewer stage).
4. **W4 — Reversal-verb suggested staff-session escalation** (PM-discretion).
5. **W5 — review-integrator REJECTED handling** (integration stage).

## Key Patterns

**Re-verify reviewer premises against artifacts that land AFTER the review.** When a reviewer finding directs a rename/refactor whose feasibility depends on a downstream artifact (schema, contract doc, ecosystem constant), and that artifact lands or changes between review and execution, re-verify the premise against the landed artifact before acting. Example: a finding directed renaming `accept_hallucination_risk` → `accept_corpus_poisoning_risk`; the schema then landed with `additionalProperties: false` pinning the original key. Resolution: honor the finding's intent (clearer naming) in CLI flag values and banner text without forking the schema key. (Source: project-rag-ue-addon L13)

### W1 — Negative-search rule (writing-plans SKILL)

Identify central nouns/abstractions in the prescription. Run `bin/query-records` + Grep against `tasks/lessons.md` and `docs/wiki/` for those nouns paired with prohibition vocabulary: `do not | never | tear down | deprecated | forbidden | removed | do NOT`.

If a prohibition is found:
- (a) Acknowledge in §1 Objective + justify the reversal, **engaging with the original argument**, or
- (b) Recuse.

**Reversal-verb hint.** If §1 uses `restore | reintroduce | reconstitute | undo | re-add | bring back`, the skill suggests staff-session to PM (suggestion only — never mandatory).

### W2 — repo-specialist counter-evidence pass

After the positive analysis, search for prior-decision artifacts arguing AGAINST the hypothesis. Targets:
- `tasks/lessons.md` (always — hard rule, regardless of scout-passed inputs)
- `docs/wiki/`
- `docs/decisions/`
- Archived plans whose successors superseded them

Output field: `counter_evidence: [{file, line, quote, relevance}]` or `none_found`. **Specialists do not adjudicate — they surface.**

### W3 — Patrik Pass 0 fields

Three new fields in Patrik's reviewer output:

- `premise_review`: `clean | needs-justification | refuted`.
- `alternatives_considered`: 0-3 high-level shapes Patrik names *without investigation*. Bare bullets with mandatory disclaimer "I haven't gone deep on this." Flat list, no ranking, no comparison, no judgment.
- `planning_quality`: one sentence max, only when a specific structural signal is present (zero alternatives, no negative-search, single-source).

A new verdict — `REJECTED` — fires only when premise is `refuted`.

### W3 hard guardrails (verbatim)

- Patrik does NOT investigate alternatives.
- Patrik does NOT pick winners.
- Patrik does NOT run a planning session.
- "I haven't gone deep on this" framing mandatory.
- Patrik does NOT rank or compare alternatives — list flat, no comparative judgments.

### W5 — review-integrator REJECTED handling

The integrator **does NOT apply findings inline** when verdict is `REJECTED`. Instead it surfaces a prominent block:

```
REJECTED — replan recommended

[premise refutation summary]
[alternatives considered]
[rationale]
```

All standard findings are recorded below the block for EM override visibility. EM may override `REJECTED` iff PM agrees. Override format:

> PM-overridden REJECT. PM said: '<verbatim>'. Reasoning: <reasoning>.

The verbatim quote (or PM-confirmed quoted summary) is the audit trail. **No silent overrides.**

## Gotchas

- **Empirical audit before fix code when a reviewer mandates a specific mechanism.** When a reviewer finding prescribes a concrete mechanism (e.g. "use X pattern", "add Y guard"), verify that the mechanism is applicable before writing fix code. A one-hour audit beats a half-day of wrong-fix code. The W3 Pass 0 finding is a hypothesis based on the plan text; the executor verifying at the code level often discovers the scope is narrower or the mechanism doesn't apply. Auditability rule: if the fix has structural side-effects, audit first, then fix.

- **Validator/parser-semantics claims from reviewers are folklore until measured.** When a reviewer claims a validator, parser, linter, or schema engine "will reject X" / "already enforces Y" / "rewrites Z under the hood", treat the claim as a hypothesis — not as load-bearing input to the disposition table. Stakes-proportionate empirical check: feed the asserted input to the actual tool and observe. For non-trivial-stakes findings (anything that gates merge, changes a schema, or removes a guard), the empirical check is mandatory before AUTO-FIX or apply. A reviewer-asserted semantic is one source; the running tool is the other; convergence between them is the green-light, not the reviewer's confidence alone. This is structurally similar to the convergence-as-confidence rule in coordinator CLAUDE.md but specifically for tool-behavior claims, which have the highest folklore rate.

- **REJECTED trigger is `refuted` alone.** The original draft included "OR architecturally superior alternative", but that required Patrik to judge alternatives he's explicitly not investigated — contradicting the W3 "naming is high-level only" guardrail.
- **Camelia / Palí / Fru Pass 0 mirrors deferred.** Hit rate for premise-failure is structurally lower in those domains; revisit only on a measurable miss rate.
- **Calibration block schema unchanged.** Premise-challenge fields live in reviewer system prompts, not in the synced calibration block — the calibration block stays focused on confidence + AUTO-FIX/ASK routing.

## Unification Theses Must Be Audited on Fail-Open Branches

*Source: project-rag-ue-addon, 2026-05-29. [universal]*

A reviewer or plan that proposes "unify X and Y into a single surface" typically audits the happy path — the main execution branch where both X and Y are called and produce output. The fail-open branches (where X or Y is absent, returns None, raises, or degrades silently) are the cases most likely to diverge under unification and are routinely skipped.

**Rule.** Any unification thesis in a plan or review must be tested against the fail-open branches of both surfaces before the `premise_review` field can be `clean`. Concretely: identify the degraded-mode code path for each surface being unified (e.g. what happens when the probe library is missing, when the schema mismatches, when the daemon is offline) and assert that the unified surface preserves each surface's fail-open contract separately — not just the combined happy-path contract. A `REJECTED` verdict is warranted if the unification thesis has only been verified on the happy path.

## Reference

- Related: [reviewer-routed-workers](reviewer-routed-workers.md)
- Source plan: `archive/specs/2026-05-04-reviewer-premise-challenge.md`
