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

1. **W1 — Negative-search rule** in the `coordinator:plan` skill (Branch B) (plan author).
2. **W2 — Counter-evidence pass** in `repo-specialist` (research stage).
3. **W3 — the Staff Engineer Pass 0** premise review (reviewer stage).
4. **W4 — Reversal-verb suggested staff-session escalation** (PM-discretion).
5. **W5 — review-integrator REJECTED handling** (integration stage).

## Key Patterns

**Re-verify reviewer premises against artifacts that land AFTER the review.** When a reviewer finding directs a rename/refactor whose feasibility depends on a downstream artifact (schema, contract doc, ecosystem constant), and that artifact lands or changes between review and execution, re-verify the premise against the landed artifact before acting. Example: a finding directed renaming `accept_hallucination_risk` → `accept_corpus_poisoning_risk`; the schema then landed with `additionalProperties: false` pinning the original key. Resolution: honor the finding's intent (clearer naming) in CLI flag values and banner text without forking the schema key. (Source: project-rag-ue-addon L13)

### W1 — Negative-search rule (coordinator:plan, Branch B)

Identify central nouns/abstractions in the prescription. Run `bin/query-records` + Grep against `state/lessons/` and `docs/wiki/` for those nouns paired with prohibition vocabulary: `do not | never | tear down | deprecated | forbidden | removed | do NOT`.

If a prohibition is found:
- (a) Acknowledge in §1 Objective + justify the reversal, **engaging with the original argument**, or
- (b) Recuse.

**Reversal-verb hint.** If §1 uses `restore | reintroduce | reconstitute | undo | re-add | bring back`, the skill suggests staff-session to PM (suggestion only — never mandatory).

### W2 — repo-specialist counter-evidence pass

After the positive analysis, search for prior-decision artifacts arguing AGAINST the hypothesis. Targets:
- `state/lessons/` (always — hard rule, regardless of scout-passed inputs)
- `docs/wiki/`
- `docs/decisions/`
- Archived plans whose successors superseded them

Output field: `counter_evidence: [{file, line, quote, relevance}]` or `none_found`. **Specialists do not adjudicate — they surface.**

### W3 — the Staff Engineer Pass 0 fields

Three new fields in the Staff Engineer's reviewer output:

- `premise_review`: `clean | needs-justification | refuted`.
- `alternatives_considered`: 0-3 high-level shapes the Staff Engineer names *without investigation*. Bare bullets with mandatory disclaimer "I haven't gone deep on this." Flat list, no ranking, no comparison, no judgment.
- `planning_quality`: one sentence max, only when a specific structural signal is present (zero alternatives, no negative-search, single-source).

A new verdict — `REJECTED` — fires only when premise is `refuted`.

### W3 hard guardrails (verbatim)

- the Staff Engineer does NOT investigate alternatives.
- the Staff Engineer does NOT pick winners.
- the Staff Engineer does NOT run a planning session.
- "I haven't gone deep on this" framing mandatory.
- the Staff Engineer does NOT rank or compare alternatives — list flat, no comparative judgments.

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

- **REJECTED trigger is `refuted` alone.** The original draft included "OR architecturally superior alternative", but that required the Staff Engineer to judge alternatives they have explicitly not investigated — contradicting the W3 "naming is high-level only" guardrail.
- **the Data Science Reviewer / the Front-End Reviewer / the UX Reviewer Pass 0 mirrors deferred.** Hit rate for premise-failure is structurally lower in those domains; revisit only on a measurable miss rate.
- **Calibration block schema unchanged.** Premise-challenge fields live in reviewer system prompts, not in the synced calibration block — the calibration block stays focused on confidence + AUTO-FIX/ASK routing.

## Unification Theses Must Be Audited on Fail-Open Branches

*Source: project-rag-ue-addon. [universal]*

A reviewer or plan that proposes "unify X and Y into a single surface" typically audits the happy path — the main execution branch where both X and Y are called and produce output. The fail-open branches (where X or Y is absent, returns None, raises, or degrades silently) are the cases most likely to diverge under unification and are routinely skipped.

**Rule.** Any unification thesis in a plan or review must be tested against the fail-open branches of both surfaces before the `premise_review` field can be `clean`. Concretely: identify the degraded-mode code path for each surface being unified (e.g. what happens when the probe library is missing, when the schema mismatches, when the daemon is offline) and assert that the unified surface preserves each surface's fail-open contract separately — not just the combined happy-path contract. A `REJECTED` verdict is warranted if the unification thesis has only been verified on the happy path.

## Shard-N / sequence-N failure indices are accumulation evidence — don't paraphrase past them at plan-write time

**When a source comment cites a failure at shard-N or sequence-N (e.g. `OOM@shard76`, `fail@post-shard-91`), those are accumulation numbers — a per-batch / per-density theory cannot explain a cap that succeeded on N-1 and failed on N. Re-weight that evidence at plan-write time; do not author a premise the cited comment already disproves.** A plan's P2 asserted "char-cap is one-dimensional and forced by worst-case density" and dispatched a calibration chunk — measurement on a fresh GPU showed 40 families fitting at the cap with 8.7% VRAM utilization, immediately invalidating the premise. The smoking gun was in a comment the plan author had READ at plan-write time: *"24000→OOM@cpp_chunks_shard76; 10000→OOM@cpp_comment; 6000→OOM@post-shard-91."* Shard-76 / post-shard-91 are accumulation indices; the predecessor handoff had even named "GPU allocator fragmentation after ~76 shards" and the author read past it. ~30 minutes burned on a falsifiable measurement that the cited evidence had already disproven. Discipline: at plan-write time, when a referenced source comment cites a sequence-N or shard-N failure, the premise must explain why N-1 succeeded — a density / per-batch story cannot, and an accumulation / fragmentation story must be on the table before the chunk dispatches. The reviewer-premise-challenge surface ratchets one notch: the premise-review field is not `clean` if the plan's own cited evidence contradicts it. (case: project-rag-ue-addon)

## A backlog entry's FIX DIRECTION is a hypothesis to falsify, not a spec to execute

*Source: internal case study. [universal]*

A backlog/bug entry that names a proposed fix (`'switch to fs-mtime'`, `'add a cache'`) is the reporter's guess **from where they noticed the symptom** — the same "proposers frame fixes from where they noticed the problem" failure the premise-challenge system exists to catch, applied to backlog items rather than reviewer findings. The fix direction can be actively wrong. Investigate the premise at plan-write time and treat FIX DIRECTION as a *claim to falsify*, not a task to execute.

Case: backlog item F1 proposed switching `_cs_session_live` Layer-2 to fs-mtime to stop a clock-skew masking. The masking did NOT reproduce — write and read share one date clock, so skew cancels — and the proposed fix would have *introduced* the masking by making the two sides use different clocks. The correct move was **prove-and-close** (ship a regression test proving skew-safety), not implement-the-suggested-fix. Discipline: before implementing a named backlog fix, reproduce the symptom the fix targets and verify the fix doesn't itself create it.

## Reference

- Related: [reviewer-routed-workers](reviewer-routed-workers.md)
- Source plan: `archive/specs/2026-05-04-reviewer-premise-challenge.md`
