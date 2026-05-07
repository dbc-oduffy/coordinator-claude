---
title: external-pattern-checker pre-review doctrine
created: 2026-05-07
type: doctrine
related:
  - docs/wiki/prior-art-checker.md
  - docs/wiki/docs-checker-pre-review.md
  - plugins/coordinator-claude/coordinator/agents/external-pattern-checker.md
  - plugins/coordinator-claude/coordinator/skills/review-dispatch/SKILL.md
---

<!-- Spec backlink: ~/.claude/plans/external-pattern-checker.md Phase 2 -->

# external-pattern-checker Pre-Review Doctrine

## What is external-pattern-checker?

external-pattern-checker is an opt-in Sonnet-tier pre-flight that scans a plan's Silent claims — the claims prior-art-checker found no internal prior art for — and does a bounded web triage to determine whether external experience is worth pulling in before the Opus reviewer sees the plan.

It writes a sidecar at `<plan-path>.external-pattern.md` with four buckets: `Signal Worth Deeper Research`, `Light Context Surfaced`, `Cautionary Note`, `No External Signal`. The verdict (`RESEARCH-RECOMMENDED` / `LIGHT-CONTEXT-AVAILABLE` / `NO-EXTERNAL-SIGNAL` / `DEGRADED` / `SCOPE-MISMATCH`) is advisory. The EM decides whether to act.

**It is opt-in. It never runs by default.**

## Lens Boundaries

| Agent | Question | Corpus | Default |
|---|---|---|---|
| **docs-checker** | "Are the external API claims correct?" | Context7, LSP, project-RAG | Run by default for C++/UE; EM discretion otherwise |
| **prior-art-checker** | "Have *we* already learned this?" | Project + global wikis, lessons, central queue | Run by default for plans |
| **external-pattern-checker** | "Is there enough external signal here that we should dispatch deeper research — and is there a quick caution worth surfacing now?" | Bounded triage scan (≤ 5 WebFetch, ≤ 2 WebSearch, ≤ 6 topics) | **Opt-in only — never default-on** |

These three agents are not substitutes. They answer different questions, consult different corpora, and produce different outputs. Running one does not reduce the value of running another.

## Why Not Fold Into prior-art-checker?

Three reasons the external triage belongs in a separate agent rather than an extension of prior-art-checker:

**1. Silent is a clean signal — don't dilute it.**
prior-art-checker's `Silent` verdict is load-bearing: it tells the EM and reviewer "we have no established doctrine here — decide fresh." If prior-art-checker sometimes fetches external context when claims are Silent, the Silent verdict becomes ambiguous: does it mean "no internal prior art and no external signal" or "no internal prior art but I didn't check external"? The signal degrades. A separate agent preserves the clean semantics.

**2. Lens confusion compounds across the pipeline.**
docs-checker verifies facts. prior-art-checker recalls doctrine. A prior-art-checker that also fetches web context blurs the boundary with both docs-checker (factual verification) and the `general-purpose` Sonnet scout (open research). Downstream consumers — Opus reviewers, the review-integrator, future EM sessions — rely on the lens boundary to know what kind of trust to place in each sidecar.

**3. Latency creep on a default-on agent.**
prior-art-checker runs by default on every plan. Adding bounded web calls to a default-on agent turns a 2–5K token scan into a 10–25K token scan on every plan review. Opt-in is the correct default: pay the cost only when the two-condition trigger gate is met.

## When Does It Run? — The Two-Condition Trigger Gate

The EM may invoke external-pattern-checker during `review-dispatch` Phase 2.7c only when **both** conditions hold:

**Condition A:** prior-art-checker returned `Silent` on architecturally-loaded claims — where "architecturally-loaded" means the claim involves a new abstraction, protocol, or doctrine surface (not a constant bump, test fix, or rename).

**Condition B:** The plan is in `scope_mode` `architecture` or `feature` AND the topic is one the project has struggled with empirically, evidenced by **either**:
- ≥ 2 entries in `tasks/lessons.md` or `coordinator-improvement-queue.md` sharing a noun-phrase from the plan's central abstractions, **or**
- ≥ 1 archived handoff in `archive/handoffs/` whose body matches the same noun-phrase AND contains "reverted" / "abandoned" / "rolled back".

**PM can also invoke it directly.** When the PM says "run external-pattern-check on this plan," the two-condition gate is bypassed — PM authorization is sufficient.

If neither condition holds, the EM does not invoke it. The cost exceeds the value for routine plans.

## Anti-Patterns

**Running it default-on.** external-pattern-checker is explicitly opt-in. It should never appear in a skill, command, or hook as a default step. The prior-art-checker's `Silent` bucket is the upstream gate — and even that is not sufficient alone (both trigger conditions must hold).

**Using it as a research pipeline.** If you find yourself dispatching external-pattern-checker to do the research you need, you are using the wrong tool. The agent's job is to determine whether a `general-purpose` web scout or `/deep-research` is warranted — not to complete that research itself. When the sidecar says `RESEARCH-RECOMMENDED`, dispatch the appropriate tool. Do not re-dispatch external-pattern-checker with looser instructions.

**Citing the sidecar as authoritative.** The sidecar header says "External triage, not prior art — informational, not authoritative." An EM who writes "external-pattern-checker confirmed X is the right approach" has misread the sidecar. The agent reports external signal; it does not validate design decisions.

**Invoking when prior-art returned Compatible-but-relevant on the same claim.** If prior-art-checker already found internal doctrine covering a claim and classified it Compatible-but-relevant, running external-pattern-checker on the same claim is redundant. The internal prior art takes precedence; external triage adds noise, not signal.

**Invoking on prototype or patch scope.** Plans in `scope_mode: prototype` or `scope_mode: patch` are too narrow for the external triage cost to be justified. The agent abstains automatically (SCOPE-MISMATCH) but the EM should not dispatch it for these cases in the first place.

**Conflating with the `general-purpose` Sonnet web scout.** The `general-purpose` scout produces a free-form brief from an open-ended session. external-pattern-checker produces a structured sidecar with hard caps. They are not interchangeable. Use the scout when you know you need research; use external-pattern-checker when you are uncertain whether external research is warranted.

**Treating external-pattern-checker as a mandatory gate before `/deep-research`.** `/deep-research` is PM-invoked directly when external research is known-needed. external-pattern-checker exists for the case where the EM is *uncertain* whether external research is warranted at all. If the PM has already decided to run `/deep-research`, skip external-pattern-checker — it is redundant in that case.

## Dogfood Expectations

**Cost target:** Each run should consume 5K–20K tokens. A run under 5K tokens likely found no signal (and could have short-circuited earlier); a run over 20K is approaching the DEGRADED threshold and suggests the agent went too deep on a small number of topics.

**Hit rate:** Over the first 30-day window, expect roughly:
- `RESEARCH-RECOMMENDED` or `LIGHT-CONTEXT-AVAILABLE`: ~40–60% of invocations (the trigger gate should filter out low-signal cases before dispatch)
- `NO-EXTERNAL-SIGNAL`: ~30–40% (the topic was legitimately uncovered in external literature)
- `DEGRADED` or `SCOPE-MISMATCH`: ≤ 10% (indicates either premature invocation or an unusually expensive topic)

**False-positive rate:** A sidecar is a false positive when the EM reads it and concludes the light context was not worth surfacing — i.e., the reviewer would have reached the same conclusions without it. Acceptable rate: ≤ 30% of invocations over the first 30-day window. Higher than 30% suggests the trigger gate is too loose.

**v2-promotion criterion:** If the EM forgets to include the fold-confirmation statement (see review-dispatch Phase 2.7c) ≥ 1 time over the 30-day window, the v2 path activates: create `snippets/external-pattern-check-consumption.md`, create `bin/verify-external-pattern-sync.sh`, add to the snippet-sync tripwire in `coordinator/CLAUDE.md`. This makes consumption structurally enforced rather than relying on EM discipline.

**Retire criterion:** If across the 30-day window ≥ 2 invocations occurred AND in zero of them did the reviewer cite the sidecar OR did the EM dispatch the recommended-next-step research scout, the EM surfaces a retire-recommendation to PM with the dogfood evidence. Retiring is a PM call, not an EM-unilateral action.
