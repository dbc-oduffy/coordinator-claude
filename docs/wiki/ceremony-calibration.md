# Ceremony Calibration

> When to invoke heavyweight ceremony (plan-pipeline, brainstorm, sizing pass, skill extraction, retirement) vs lightweight action (direct dispatch, in-place patch, demote-don't-retire, wait-for-instance-3). The pipeline (enrichment → review → execution → integration) is cheap relative to shipping broken work, but applying it to *every* decision is its own waste. Calibrate process weight to actual decision weight.

This wiki synthesizes nine recurring patterns into a single calibration vocabulary. None of the rules are novel; the leverage is in having one place to point when a sibling EM (or a future you) is choosing process weight.

## TL;DR — the calibration axis

For any candidate action, three questions decide the ceremony level:

1. **Is the decision novel, or a surgical follow-up to a decision already made?** Novel → ceremony. Surgical → direct dispatch.
2. **Does the entry have an established occupancy pattern, or is it instance #1?** Pattern with ≥3 instances → extract / promote / refactor. Single instance → wait.
3. **Is the framing concrete enough to enter the plan-write pipeline, or vague enough to need brainstorming first?** Concrete → plan. Vague → brainstorm.

The default failure mode is over-ceremony on surgical work and under-ceremony on novel work — both produce drag, both are visible in retrospect, neither is visible at decision time without this rubric.

## Plan-vs-direct-dispatch

**Plans default to decisions, not questions.** Reviewer-questions in a plan body indicate undelegated decisions the plan author had context to make. If the plan reads "should X or Y?", the plan isn't done — answer it. The decision-tree skill (`coordinator:plan` Branch C) codifies this: questions in the plan body are a doctrine violation, not a feature.

**Cluster execution = full ceremony on the novel item, direct dispatch on surgical follow-ups** with explicit file-scope partitioning. The first item in a cluster typically introduces the pattern; subsequent items apply it to adjacent files. Running the full enrichment pipeline on the novel item earns the ceremony; running it on the follow-ups doesn't — direct dispatch with the file-scope partitioning declared up front is sufficient. Failure mode: re-running ceremony on follow-ups buries genuinely novel reviews under serial process noise.

## Queue-clear classification — by edit-shape, not ceremony default

Clearing a backlog of queued items (improvement-queue entries, lesson folds, small fixes) tempts a uniform ceremony default — "everything goes through plan-and-review." Most queue items don't need it. Classify each item by its **actual edit-shape**, and route the ceremony to the shape:

- **Wiki append / single paragraph of doctrine** → direct edit, no plan, no review. The fold-target is named in the queue entry.
- **Single-paragraph code change / single-file fix** → direct dispatch or EM-inline per `agent-dispatch-economics.md`.
- **Multi-file change touching a shared seam** → plan-shaped; the seam is the ceremony trigger.
- **A genuine design call** (new abstraction, public-surface change) → full plan-pipeline.

The failure mode is applying the heaviest shape uniformly because "queue-clear" feels like a batch operation that wants one process. It isn't — it's N independent items of N different shapes. Classify first, then route per item. This is the queue-clear instance of the calibration axis (§ TL;DR): ceremony tracks the edit-shape of each item, not the framing of the batch.

## Defuse-vs-spinoff — when a "small fix" hides a product/architectural fork

A queue/handoff item framed as a "small fix" can conceal a product decision or an architectural fork — the conflicting ground-truth surfaces only once the EM starts coding. **Before dispatching a small-fix into an execution path, check whether the fix presupposes a decision that isn't actually settled.** When two sources of truth disagree about the desired end-state (the bug report wants X, the architecture implies not-X), that is a fork to *defuse* (surface to PM / route through `/shape` or `coordinator:plan`), not a fix to *code*. Never dispatch an executor onto a path whose ground-truth is internally contradictory — the executor will pick one side silently and ship a decision nobody made. Tell: the "fix" requires the executor to decide *which behaviour is correct*, not just *how to implement the agreed behaviour*. This is the calibration axis (§ TL;DR) applied to disguised forks — a product-decision wearing a small-fix costume earns ceremony, not direct dispatch.

## Cross-repo memo ceremony — the receiver calibrates magnitude

When you accept an inbound cross-repo memo-ask, the ceremony it earns is the **receiver's** call, not a sender-declared field — magnitude is not knowable to the sender. **Default to mechanical-direct** (do the work, commit both sides where authorized, action the memo — no plan, no round-trip); **escalate to a plan only on a named weighty signal** per § TL;DR (novel decision / instance-#1 with downstream occupancy / vague framing). A plainly-worded ask is not therefore a weighty one: the sender states work plainly (the presume-action authoring rule), the receiver decides how big a deal it is — complementary halves, not one knob. This is the cross-repo-memo instance of the calibration axis; the canonical procedure lives in your cross-repo communication doctrine's "picking up a memo" guidance (adjudicate-and-own includes ceremony). Keep it distinct from the **channel** axis — *whether to use the memo channel at all*, a separate governance question keyed to change-class (a narrow direct-commit exception exists for break-glass cases; everyday code/install/contract work routes via memo+relay): channel and ceremony are orthogonal, not nested. Conflating them is the over-ceremony failure mode this entry exists to prevent.

## Vague-vs-concrete framing

**`/brainstorming` is for vague requirements, not well-scoped follow-ups.** When the PM says "build X and the way is clear," skip brainstorm — go straight to plan. When the PM says "we should probably do something about Y" with multiple plausible shapes, brainstorm. The signal is whether the action's *shape* is contested, not whether it's hard. Hard-but-clear → plan. Easy-but-shape-unknown → brainstorm.

**PM-set axiom collapses brainstorm into plan.** When the PM has fixed the axiom (chosen the architectural direction, named the constraint, set the policy), residual ambiguity is classification-shaped — "which existing surfaces fall under this axiom, with what disposition?" That is plan-shaped work, not brainstorm-shaped. Brainstorm exists to *generate* shape options; once the PM has picked one, generating more is regression. Skip to plan and let the plan-pipeline handle the per-surface classifications under the fixed axiom.

## Pattern-extraction calibration

**Wait for instance #3 before extracting a pattern into a skill.** One-off looks like noise. Two might be coincidence. Three is a pattern. The cost of premature extraction is a skill that codifies the wrong invariant — and once codified, the wrong invariant is harder to correct than the original ad-hoc behavior. Hold instance-#1 and instance-#2 as separate entries under `state/lessons/`, cross-referenced so the recurrence is visible; promote on the third surfacing.


**Fight-the-hook is an anti-pattern** — strip once, commit, file a paper-trail bug, surface to PM.

**Codify a stable pattern before running new instances under it, never before** — demote-don't-retire (see § Demote-don't-retire below) is the corollary once a pattern is codified and later goes stale.

**Inventory existing piggybacks and vendored copies BEFORE applying the rule — they count as instance #2+ in disguise.** The wait-for-#3 count is wrong if it only counts *clean* instances. A convenience-coupling, a vendored copy, or a piggyback on an unrelated primitive (e.g. one plugin borrowing another's introspection call because no contract existed) is a *disguised* instance of the same need — it is the empirical proof the abstraction is overdue, not a separate one-off. Before reaching for "only one instance, wait," grep for the disguised forms: vendored/copied implementations, piggybacks on adjacent primitives, and inline re-implementations. Counting those in often moves a perceived instance-#1 to instance-#2-or-#3, and mis-applying the wait-rule to a piggyback case delays the abstraction and entrenches the wrong shape. (Connects to the misshapen-instance #2 override shape below — a misshapen piggyback IS the second instance.)

**Exception — low-invariant-risk + high-magnitude (instance-#1 promotion justified).** The wait-for-#3 rule exists to prevent codifying the wrong invariant. That risk is substantially lower when (a) the invariant being codified is mechanical and low-misclassification-risk (the invariant is a structural cross-ref, not a judgment call), AND (b) the motivating incident magnitude is qualitatively distinct from typical near-miss noise — e.g., 36-of-50 items missed in a single artifact versus 1–2 items in a near-miss. When both conditions hold, the wait-for-#3 gate re-instantiates the EM-confidence failure mode the agent exists to prevent: the EM would judge each near-miss as "still not enough evidence," and the structural gap persists until the third incident. Instance-#1 promotion is warranted; override must be documented with explicit rationale at the extraction site. (the Staff Engineer review, Conflict #15 update-prior-art follow-up.)

**Second valid override shape — prospective-demand (instance-#1 with instances #2 and #3 named, structurally dependent, same producer surface):**
The retrospective-magnitude argument above is not the only valid exception shape. The prospective-demand argument substitutes for the retrospective-magnitude argument when:
- **(i)** The named instances are not speculative — they live in handoff items, plans, or active workstreams, not in hypothetical future demand.
- **(ii)** The structural dependence is on the **same producer surface**, making the duplicate cost concrete: three consumers of the same primitive with divergent implementations means bugs in one don't fix the others.

When both (i) and (ii) hold AND condition (a) is satisfied (mechanical, low-misclassification-risk invariant), instance-#1 promotion is warranted on prospective-demand grounds. The override must be documented with explicit criterion-match at the extraction site, naming (a) the mechanical nature of the invariant and (b) the three named instances with their source artifacts.

The key distinction from appetite-based override: prospective-demand requires the instances to be concretely named (not "probably more later") and structurally dependent on the same surface (not "similar category of need"). Speculative demand ("there might be more") does not qualify.

**Third valid override shape — misshapen-instance #2 (two instances where the second is wrong-shaped because the abstraction never existed):**
**Worked example — when the rule does NOT apply.** The rule prevents premature abstraction when you have one instance and might guess wrong about the second. It does NOT apply when you already have **two** instances and one of them is in active **wrong-shape arrangement** because the abstraction never existed (e.g., one plugin piggybacking on a sibling plugin's introspection call for cross-plugin identity lookup — instance #2 misshapen specifically because there was no contract for it to conform to). In that case the abstraction is *retroactively justified*: extracting closes a doctrine gap that the wrong-shape arrangement is the empirical proof of. The "wait for #3" rule is about *information* — three instances let you infer the right shape; two instances + a misshapen arrangement give you the same information. Distinct from the prospective-demand override (second valid override shape in this same section): that one argues from concretely-named future instances structurally dependent on the same producer surface; this one argues from an existing misshapen arrangement that is itself the evidence the abstraction is overdue.

**Null-result audits fold the rule into the producer skill, not just the report.** When an audit finds "this didn't happen because X," the producer-side surface (the skill that should have made X happen) is where the rule belongs — the audit report itself is read once and dies. Audit reports without producer-side fixes are observation theater.

## Retirement calibration

**Demote-don't-retire beats empirical retirement criteria for legacy surfaces.** Three-tier gating — *active* / *demoted* / *retired* — terminates the deprecation question without indefinite limbo. Empirical retirement criteria ("when usage drops below N") sound disciplined but trap the surface in perpetual review-cycle limbo when usage is non-zero but minor. Demote first, retire later, never leave open-ended.

**Pair with: calibrate deprecation-cycle posture to consumer count, not general best-practice.** At two consumers, direct ship. The general "deprecation cycle" rubric is for surfaces with diffuse external consumers; in-tree surfaces with N≤2 known consumers can be migrated in one commit. Don't import enterprise deprecation pacing into a setup where the consumers are visible in `git grep`.

### Deprecation-cycle calibration — ask consumer count first

Deprecation cycles, opt-in flags, and gradual-rollout windows assume *thousands* of consumers. At that scale the machinery protects a real population. At **two consumers**, the same machinery is ceremony for ceremony's sake; the version of "respect users' time" that does apply is "fix the underlying behavior cleanly so they're not debugging silent degradation later."

When facing a *(a) direct ship / (b) opt-in for one cycle / (c) opt-out indefinitely* decision, the **first question** is "how many consumers?" — not "what's the right posture?". The posture follows from the consumer-count answer:

- **N ≤ 2 (visible in `git grep`):** direct ship. Migrate the consumers in the same commit if needed. No flag, no cycle, no doc note about deprecation — the consumers are inline with the change.
- **N small (≤10, all in-org):** direct ship with a release note. Optional opt-out flag *only* if the change has a known-bad failure mode you can't fix forward (rare).
- **N large (diffuse / external):** standard deprecation cycle applies — flag, doc, cycle window, telemetry on usage of the deprecated path.

The failure mode is importing enterprise-grade deprecation pacing into a two-consumer setup. The ceremony costs real session time and produces no signal. Verify consumer count by grep before reaching for the deprecation rubric.

## Authorial-latitude conventions

**Bind sub-disciplines at the latitude site, not in separate stanzas.** When a convention says "executor decides X but must follow Y," the Y constraints belong on the same line as the X latitude — separating them lets executors read the latitude and miss the binding. Pattern: "Authorial latitude on phrasing; vocabulary stays disciplined per `CONTEXT.md`" beats "Authorial latitude on phrasing." (later) "Vocabulary stays disciplined." A sub-discipline two stanzas away from the freedom it constrains is an unenforced rule.

## Sizing-pass calibration (deep-research)

**Sizing pass before deep research:** parallel Sonnet sizing scouts (~30 min each) decide per-repo depth before committing Pipeline B. The sizing pass is itself a calibration step — it answers "is this worth the full pipeline, or does a stub-and-prod read suffice?" Skipping it commits the heavyweight pipeline on every entry, which is the same failure mode as running plan-ceremony on surgical follow-ups: ceremony applied uniformly is ceremony wasted.

**Asymmetric defaults + override conditions in scope.md produce sharper synthesis than balanced surveys.** Declare per-layer defaults explicitly: "Layer 1 = exhaustive, Layer 2 = targeted, Layer 3 = bypass unless trigger Z fires." Balanced surveys produce balanced (= mediocre) synthesis because every layer gets equal attention regardless of relevance. The asymmetry is the signal.

## Small-workstream framing is not a discount lens

"Mostly lift," "small," "mechanical substitution" — these describe effort, not integration complexity. Hidden complexity clusters at substitution seams, integration boundaries between workstreams, and concurrent-EM bleed-through (invisible to per-workstream review by construction). The doctrine table fires on "any executor dispatched OR shared schema seam touched," not LoC threshold. When a workstream feels small or mechanical, that is the signal to look harder at the seams — not less hard. (Surfaced by an 80%-lift workstream that had 6 Sonnet findings invisible to per-W' mechanical gates.)

Small framing is not a discount lens on review doctrine. A workstream may be small in line-count but lift-heavy (touches a load-bearing constant, refactors a hot seam) — review depth tracks lift, not size. Default sequential review still applies.

## Inline triage as scout-failure fallback

Inline triage by the EM is a legitimate fallback when a classification scout fails (1M-tail-error, TEXT-ONLY hallucination), provided the EM applies the same bucket schema the scout would have used AND records the inline-vs-dispatched decision. Don't redispatch over a partial scout result if disciplined inline finish is cheaper.

## Workstream-complete-as-defer is hedging in disguise

Mid-session offering to defer non-blocking work to a future session — "want me to workstream-complete and pick this up next time?" — is the anti-ambition tell. When findings are applicable now, apply them; reserve `/workstream-complete` for genuine completion or PM redirect. The "we could do less" framing rationalizes the heaviest ceremony available (close out, write a handoff, restart) for what's actually a tradeoff between two minutes of work and an hour of context-loss next time. Default: keep going. Only invoke `/workstream-complete` when it's the *cheapest* remaining action, not the easiest *to ask permission for*.

## Phase deferral beats redundant smoke-spend

When a phase's smoke-test would re-prove something a sibling phase already proved, defer the phase with documented rationale (`# DEFERRED: redundant with Phase 3 smoke`) rather than running it for completeness. Redundant smoke-spend is a workflow tax with no signal gain — the deferral note carries the audit trail; the re-run carries nothing the previous phase didn't.

## Pipeline structure — EM owns dispatch, subagents are leaves

The coordinator pipeline (architecture-audit, distill, bug-sweep, learn-lessons) MUST follow a
structural rule: subagents dispatched into a phase cannot fan out further. Once a subagent is in
flight, it cannot dispatch additional subagents to parallelize its own work.

**Why this matters:** Phase 3 of /distill timed out repeatedly (Phase 5 had the same problem in
2026-04) when a single Opus monolith tried to do cross-reference assembly, contradiction detection,
decision-record dedup, DIRECTORY_GUIDE.md assembly, and deletion manifest generation serially in
one agent call. The EM owns the fan-out; the subagents are the leaves.

**Pattern:** EM-orchestrated Sonnet fan-out, Opus retained only as opt-in escalation for genuine
contradictions that Sonnet sub-phases surface and cannot resolve. When Phase 3a (contradiction
detection) reports zero unresolvable contradictions, Opus is never dispatched.

**Anti-pattern:** A monolith Phase 3 that "does everything" is both an output-timeout risk and a
correctness risk — when Opus handles cross-reference assembly AND dedup AND deletion manifest in
one context window, it drops edge cases at the seam between tasks.

**Distill rubric carve-out — delete-default for cross-repo memos.** The `/distill` trim+archive rubric (allowlist stays in place, denylist archives to `archive/`) applies to canonical specs and evergreen docs. Exception: cross-repo memos (`cross-repo/`) are DELETED-after-extraction by default — their value is fully captured in the distillation output, and retention in `archive/` compounds file-count without benefit. Archived handoffs are **outside every distillation cohort** — `/distill` neither harvests nor deletes them; their pruning is `/update-docs` Phase 8b. This carve-out does NOT apply to decision records, plans, or research outputs, which follow the trim+archive default.

## Daily-ceremony gate discipline

Daily ceremony gates (gates in /workday-complete, /workday-start) MUST test TODAY'S WORK — the
diff, the commits, the branch state. Machine-configuration diagnostics and pre-publish style
lints do not belong in daily-ceremony gates.

`/workstream-complete` is deliberately excluded from this enumeration: it is work-boxed, not
daily-cadence (see § The ceremony grid below) — it fires per workstream, which may happen several
times in a day or not for a week. Its gates test *the workstream's* work, not today's diff; holding
it to a daily-cadence gate would be a category error even though it is, like the two ceremonies
above, a session terminator (§ Session terminators).

**Wrong-cadence blocking validators anti-pattern:** A validator added under "while we're here,
also check X" framing — when X is a machine-config diagnostic or a cross-repo UE override check —
turns into a chronic daily blocker with no signal gain. When it breaks silently (grep no-match
kills the loop under `set -euo pipefail`), it becomes gate-as-theater. (Motivating case:
/workday-complete Step 0a/0b burned ~20 minutes, had hardcoded peer-dir paths that had rotted, and
one was broken under pipefail — all blocking daily wrap-up for work unrelated to what they checked.)

**Placement rule:**
- Machine-config diagnostics → standalone manual helpers, never auto-fired by ceremony
- Pre-publish style lints → weekly or PR cadence, advisory-only
- Cross-repo path-drift checks → /workday-start advisory section or standalone doctor

## Negative space — what doesn't earn ceremony

- **Naming, formatting, file location** — implementation discretion, EM acts.
- **Tradeoff-free reviewer fixes** — apply via integrator, surface to PM only on real tradeoffs (`global-doctrine/CLAUDE.md` § Flag Severity, "Reviewer findings — apply, don't ratify").
- **Tool choice within an established pattern** — direct dispatch unless cost/risk shifts materially.
- **Whether to commit/branch/stash** — never ask.

## Shared-Evidence-Axes Sizing Pass

Linear-run verification budgets — "we'll spend N sessions of verification across this multi-handoff chain" — collapse when **shared evidence axes are identified first**. Before sizing a multi-session handoff chain, enumerate the shared evidence: test files exercised by multiple handoffs, build artifacts referenced by multiple stubs, schema columns multiple parsers consume, config values multiple subsystems read. Each shared axis can be verified once and reused across the dependent handoffs; without enumeration, each session re-verifies the same evidence and the budget inflates by the dependency factor.

**Sizing-pass procedure** (run during `coordinator:roadmap-planning` Phase 2 or before authoring a multi-session plan): (1) list every handoff / stub in the chain; (2) for each, list the evidence it asserts on (files, commits, schema state, build artifacts); (3) compute set-union; (4) re-cost the chain assuming each shared-axis verification runs *once*, not per-handoff. The gap between linear-cost and shared-axis-cost is the room the sizing pass buys back.

## Reviewer-dispatch calibration

Reviewer auto-dispatch surfaces accumulate triggers; calibrate against who actually applies the lens. Demote auto-dispatch hooks for reviewers whose lens is PM-owned (e.g., vp-product when PM is Head of Product) to explicit-ask only.

## Tier/Cost Rule Changes Leave Landmines in Pre-Existing Dispatch Sites

*Source: self.*

When a tier or cost rule changes — e.g., Opus-only becomes the strict gate for persona dispatches — existing dispatch sites that named the old tier continue to run silently at the wrong tier until manually reconciled. The rule is updated; the call sites lag.

**Rule.** Any tier/cost rule change must be paired with a grep across every dispatch site and a reconciliation pass. Reserve the expensive tier for low-frequency gates; recurring or pipeline passes get the cheaper worker. Failure to sweep leaves a class of dispatch violations that pass silently in all existing invocations.

## Handoff-Named Followup Scripts Need an Exists-Check Before Depending On Them

A handoff that names a followup script ("run `promote-x-to-y.sh` next session") assumes that script was authored in the prior session. Deferred scripts that were planned but never materialized produce a silent gap: the succeeding session treats the script as present, wastes investigation time, or fabricates its absence as an environmental problem.

**Rule.** At pickup, before depending on any script named in the handoff, verify it exists (`ls <path>` or `Glob`). If absent, surface the gap to PM rather than assuming it will materialize. Followup-script promises are not completed work.

## State the Stakes-vs-Ceremony Proportion Before Executing a Picked-Up Spinoff

A spinoff handoff names a workstream but rarely names the cost/risk profile of its pickup ceremony. Before executing, the picking-up EM must state — for themselves, not for the PM — the stakes-vs-ceremony proportion: Is this a high-stakes architectural seam that warrants the full enrichment → review → execute pipeline? Or is it a low-stakes doc/config change where direct dispatch is the correct weight?

**Rule.** At pickup of any spinoff, before opening the plan-pipeline, write (or state internally) one sentence: *"This workstream is [stakes level] because [reason]; the appropriate ceremony is [pipeline / direct dispatch / inline]."* Without that sentence, the EM defaults to whatever the handoff's narrative tone implies — which is routinely over-ceremony on small spinoffs and under-ceremony on high-risk ones. Composes with § Queue-clear classification: the spinoff is a queued workstream; classify by edit-shape, then route.

## Try empirical cuts before debating a budget target

When the PM questions a budget ceiling at pickup ("is N really the right limit? where does that number come from?"), the cheap move is to *cut first and measure*, not to open a debate about whether the target is correctly sourced. Empirical cuts answer the question the debate is circling: if the cuts land without hurting the artifact, the ceiling was achievable and the sourcing question is moot; if the cuts start to hurt, *that* is the real evidence to bring to a budget discussion. Debating "the rule isn't sourced" in the abstract is theoretical resistance — it produces no signal and defers the actual work.

**Rule.** A questioned budget/ceiling at pickup is a cue to attempt the cuts, not to litigate the number. Cut to the target, observe whether anything load-bearing breaks, and surface to the PM *only* if the cuts hurt — with the specific hurt as the evidence. Theoretical "this rule isn't sourced" does not, on its own, qualify as resistance worth a round-trip; it qualifies as a reason to gather the empirical answer first. This is the ceremony-calibration axis applied to budget questions: cutting is the cheap direct action, debating-the-target is the over-ceremony failure mode. Composes with `coordinator/snippets/em-operating-doctrine.md` § How to Decide — the empirical cut *is* the verification you do before asking.

## Companion doctrine

- `docs/wiki/writing-plans.md` — plan-pipeline mechanics
- This wiki's own § Pattern-extraction calibration — instance-#3 rule, lessons cadence
- `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off — plan-skill invocation discipline
- `coordinator/snippets/em-operating-doctrine.md` § How to Decide — what to ask vs what to act on

## Platform Vocabulary vs Local Coinage

**Use Claude Code platform tokens exactly; do not invent local synonyms.**

Claude Code defines 30 PascalCase hook identifiers — `SessionStart`, `SessionEnd`,
`Stop`, `Setup`, `PreCompact`, `SubagentStart`, etc. These are platform tokens, not
free vocabulary. Refer to the machinery by the platform token (`SessionStart` hook);
the spaced phrase "session start" is fine in temporal prose, but never as a skill
name or event identifier.

**Renaming dissolves collisions at their source.** When a coordinator surface
collides with a platform token, the right move is to rename the coordinator surface
off the colliding word — not to coin a new bridge term ("session boot", etc.) and
hope the glossary catches every confabulation.

**The ceremony grid:**

| Axis | Boxing | start | complete |
|---|---|---|---|
| `workstream` | work-boxed | `/workstream-start` | `/workstream-complete` |
| `workday` | time-boxed | `/workday-start` | `/workday-complete` |
| `workweek` | time-boxed | `/workweek-start` | `/workweek-complete` |

**Time-boxed vs work-boxed — not a magnitude ordering.** `workday` and `workweek` fire on a
calendar; `workstream` fires when a unit of work finishes, which may happen several times a day or
not for a week. The shared `work*` prefix invites reading these three as points on one scale
(stream < day < week, small to large) — they are not. `/workstream-complete` is the lightest of
the three in step count, but that is incidental to the axis, not derived from it: it is
work-boxed, full stop, and must not be sized or gated as a smaller version of the time-boxed pair.

**Session terminators.** `/workstream-complete`, `/handoff`, `/workday-complete`, and `quick-wrap`
are the four *session terminators* — the canonical term for this set
(`coordinator/commands/workday-complete.md:101`). A ceremony is a session terminator if it ends a
session and carries a dirty-tree gate — the criterion is *engaging* the dirty tree at session
close, not the specific stop/prompt shape the other three use. `quick-wrap` earns membership via
its Step 1 `session.safe_commit_offer` dial, which computes and commits the session's safe pathspec: the
mechanism differs (auto-commit vs. stop/prompt-then-proceed), but the tree state it acts on and
the point in the session it acts at are the same — it engages whatever is dirty in the session's
own touch-list at close, exactly where the other three terminators' gates fire. That shared
engagement point is what the membership criterion below tests, not sameness of mechanism.
Membership is about ending a session, not about cadence, so it cuts across the time-boxed/work-boxed axis
above (`/workstream-complete` is work-boxed and still a session terminator; `/workweek-complete` is
time-boxed and not one — it does not end a single session's work). Do not use "session terminator"
as a synonym for "daily ceremony" or for the heavy validate/consolidate/merge shape — see
§ Daily-ceremony gate discipline above for why conflating the two misroutes `/workstream-complete`.

A prior unified rename swept `/session-start → /workstream-start` and
`/session-end → /workstream-complete` for exactly this reason: `SessionStart` is a
platform hook identifier; the prior skill names were colliding with platform
vocabulary. An interim "session boot" coinage was reverted as
soon as the collision shape was named.
