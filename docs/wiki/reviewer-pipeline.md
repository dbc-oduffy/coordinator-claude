---
name: reviewer-pipeline
spec_backlink: archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md
status: active
---

<!-- Purpose: Canonical home for the shared reviewer pipeline phases used by both /review (plan-shaped) and /review-code (code-shaped). Carries Phases 2.5, 2.7, 2.7b, 2.7c, 2.8, 3.5, 3.7, 4, and 5 verbatim from the former review-dispatch skill. Does NOT carry the routing table (lives in each skill's Branch A.2) or the sequential-dispatch HARD RULE (lives in each skill's Branch A.3). -->

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-05/2026-05-06-parallel-code-review-weekly-gate.md, archive/specs/2026-05/2026-05-08-session-end-review-and-marker-trail.md, archive/specs/2026-05/2026-05-08-session-end-review-doctrine-recalibration.md, archive/specs/2026-05/2026-05-18-code-reviewer-agent.md, archive/specs/2026-05/2026-05-28-archive-aware-review-oracle-and-audit-skill.md, archive/specs/2026-03/2026-03-08-agent-hierarchy-design.md, archive/specs/2026-03/2026-03-16-structured-review-output.md, archive/specs/2026-04/2026-04-29-claude-setup-borrows.md, archive/specs/2026-04/2026-04-29-reviewer-routed-workers.md, archive/specs/2026-05/2026-05-03-docs-checker-default-pre-flight.md, archive/specs/2026-05/2026-05-04-reviewer-premise-challenge.md, archive/specs/2026-06/2026-06-30-chain-review-coverage-dag-consumer.md -->

# Reviewer Pipeline — Shared Phases Reference

This wiki is the single authoritative source for the phases that run identically for plan reviews (`/review`) and code reviews (`/review-code`). Both skills reference these phases inline — they are not optional. Walk them in order as directed by the invoking skill.

<!-- distilled: run 2026-08-06-14h38; source nugget: c7-025 -->
**Skill consolidation note.** `/review` and `/review-code` are a single skill, internally `--surface`-branched (plan-shaped vs code-shaped). The phase content this wiki hosts applies identically to both surfaces; only the invoking-skill packaging differs, not the phase numbering or content described above.

**Scope boundary:** This wiki carries numbered phases with their inline framing prose (rationale paragraphs, EM Decision Step tables, On-failure clauses, write-ahead status). It does NOT carry:
- The reviewer routing table — lives in each skill's Branch A.2.
- The sequential-dispatch HARD RULE — lives in each skill's Branch A.3.

---

## Phase 2.4: Comprehensiveness Auditor (Sonnet, DRAFT — not yet wired)

> **Status: DRAFT.** PM has approved the concept; the implementation has not landed yet. The design below is the spec for a follow-up session to pick up and wire — standard `/plan` + reviewer chain applies. Not staff-session-gated; this is a normal new-skill scaffold, not an architectural decision.

**Problem this targets.** docs-checker and prior-art-checker both work on what IS in the plan. The Staff Engineer reasons from the plan's claims forward. None of them is structurally well-positioned to ask *what's missing* — the plan didn't write about X, so no reviewer's grep over the plan body surfaces X. The empirical failure shape: plans pass docs-check + prior-art + the Staff Engineer review with no findings, then the executor returns BLOCKED on a substrate gap that any senior engineer would have flagged at draft time ("you didn't say anything about the rollback path", "this plan doesn't address the consumer migration"). The gap is a missing-coverage problem, not a wrong-claim problem.

**Why a Sonnet mechanical auditor, not an Opus reviewer:** The work is enumerative — walk a checklist of canonical coverage areas (rollback, migration, observability, security boundary, error paths, test surface, concurrency, performance, accessibility, docs/changelog impact), grep the plan body for evidence of each area being addressed, emit a sidecar listing which areas are silent. This is mechanical pattern-matching, not architectural judgment; Sonnet at low temperature is the right altitude. Opus reviewers can then use the gap-list as input rather than re-deriving it.

**Sequencing — between plan-draft and prior-art-check:**

```
plan.write → comprehensiveness-auditor (Sonnet) → docs-checker (Sonnet) → prior-art-checker (Sonnet) → Opus reviewer → integrator
```

The auditor runs BEFORE docs-checker and prior-art-checker because gap findings often reshape the plan body (the EM adds a Rollback section, a Migration section), which means docs-checker and prior-art-checker should run on the AMENDED body, not the original. Running comprehensiveness-auditor last (post-Opus) is the wrong shape — it would force a second Opus pass after gap-fill.

**Coverage checklist (initial draft — to be tuned empirically):**

| Area | Trigger | What "addressed" looks like |
|------|---------|----------------------------|
| Rollback | Plan changes shipped behavior, contract, or schema | Section names a revert/disable path, names what state survives the rollback |
| Migration | Plan changes a producer-consumer contract or persisted format | Section addresses existing data / existing consumers / version-aware logic |
| Observability | Plan ships a new code path, hook, or background process | Section names log/metric/trace surface OR explicitly notes "no observability needed and why" |
| Security boundary | Plan reads/writes external input, executes shell, or crosses a privilege boundary | Section names the validation surface OR explicitly notes "trusted internal path" with grep evidence |
| Error paths | Plan adds error-prone surface (I/O, network, parse, exec) | Section names each failure mode + handling shape |
| Test surface | Any code change | Section names test files OR documents "no test, because <reason>" |
| Concurrency | Plan touches shared state, files appended by multiple actors, async dispatch | Section addresses lock/order/idempotency strategy |
| Docs impact | Plan changes user-visible behavior or operator-visible interface | Section names doc files to update OR notes none-needed |

**Output sidecar:** `state/review-findings/{timestamp}-comprehensiveness.md` with a Silent / Addressed / N/A verdict per area + evidence quote (file:line within plan). Empty Silent column = green light. Non-empty Silent column blocks dispatch of downstream reviewers until EM either fills the gaps or annotates each as N/A with rationale.

**Failure modes to watch for** (when this phase ships, calibrate against these):

1. **False-positive Silent on N/A areas.** A trivial single-file fix doesn't need a Rollback section. The auditor must NOT block trivial work; tune the area-trigger column to fire only when the plan's scope mode (prototype / production-patch / feature / architecture / spike — see writing-plans.md) justifies the check.
2. **Coverage checklist becomes ceremony.** If every plan ships with an empty Observability section just to clear the gate, the section is decorative. Calibrate the trigger so the area only surfaces on genuine scope; null-result audit at 4-week cadence to retire areas that never fire on real plans.
3. **Auditor competes with the Staff Engineer.** If the auditor surfaces gaps that the Staff Engineer would have surfaced anyway, it's pure overhead. Calibrate by tracking which gaps the Staff Engineer flags that the auditor DIDN'T pre-surface — those are the ones the auditor needs to learn; ones the Staff Engineer never flags are the ones the auditor over-surfaces.

**Open design questions (PM input pending):**

- Should this run on plan-mode `coordinator:plan` exit, or only when the plan is `architecture` / `feature` scope? Default proposal: only on `feature` and `architecture` (skip for `prototype`, `production-patch`, `spike`).
- Should Silent areas auto-amend the plan body with `## TODO: <area> coverage` stubs, or just emit the sidecar and let the EM author? Default proposal: sidecar-only, EM authors — auto-amend invites ceremony.
- Cumulative-effect: this adds a 4th pre-flight to the plan→review pipeline. Combined with docs-check + prior-art + external-pattern, the pre-review chain is now ~2-3 minutes of Sonnet dispatch. Acceptable cost vs. expected Opus-reviewer savings? Empirical calibration after first 10 dispatches.

Lesson source: `project-rag/state/lessons.md` (comprehensiveness-auditor between plan-draft and prior-art-check).

---

## Phase 2.5: Write-Ahead Status Update

Before dispatching reviewers, mark the artifact's review status. If the artifact has a status header (plan doc, stub doc), update it:

```
**Status:** Under review by [Reviewer Name] (review started YYYY-MM-DD HH:MM)
```

If the artifact is code (no status header), note the review in the tracker or plan doc that references this work. The point is: if a crash happens mid-review, there's a breadcrumb showing what was being reviewed and by whom.

**This phase is EM-side only.** Phase 2.5 updates the plan body or tracker — not any executor-owned surface. Reviewers and enrichers continue to write status into their own work-product stubs as before.

> **Note: executor-phase in-flight state lives in a sidecar.** Executors do not stamp `**Status:**` into plan bodies. Per-chunk executor in-flight state lives in a sidecar at `tasks/<plan-slug>/flight/<chunk-id>.md`. The reviewer pipeline's Phase 2.5 is unrelated to that — it governs the EM-side tracker/stub write-ahead.
>
> **Disambiguation:** Plan-body `**Status:**` is EM-owned phase state. Sidecar frontmatter `status:` is executor-owned lifecycle state. These are distinct fields; do not cross-reference.
>
> Cross-references: `docs/plans/2026-06-09-executor-sidecar-flight-recorder.md`, `agents/executor.md § Flight-Recorder Sidecar`.

---

## Phase 2.7: API Verification (docs-checker pre-flight)

Before dispatching expensive Opus reviewers, decide whether to run the **docs-checker** agent (Sonnet) as a suggested pre-flight. docs-checker verifies external API references and applies AUTO-FIX-class corrections inline — reviewers receive a pre-verified artifact and can skip mechanical lookups entirely.

**EM Decision Step — consult the table below before dispatching:**

_Last calibrated: 2026-05-03 against Claude Opus 4.7 (1M context) training distribution. Re-evaluate when the underlying model changes._

| Language / Domain | Default | EM discretion |
|---|---|---|
| **C++ (Unreal Engine, native libraries)** | **Always run.** UE's API surface drifts every release; signatures and module/`.Build.cs` boundaries are easy to hallucinate. | None — run it. |
| **C++ (non-UE)** | Run unless trivially small. | Skip only when the artifact cites ≤3 stdlib calls and nothing else. |
| **C# (Unity, .NET)** | EM discretion, bias toward running for Unity package version drift and recent .NET preview features. | Skip for trivial scripts touching only well-known BCL APIs. |
| **Python** | EM discretion. | Run when the artifact pins library versions or uses uncommon SDKs (Stripe, Anthropic SDK new features, ML libraries). Skip for stdlib-only scripts. |
| **TypeScript / JavaScript** | EM discretion. | Run when SDK signatures matter (Anthropic, Stripe, AWS SDK v3 vs v2). Skip for routine React/Node code in the training distribution. |
| **Go, Rust, Swift** | EM discretion. | Bias toward running — fewer training tokens than Python/TS. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — nothing to mechanically verify. |
| **Plans citing in-repo symbols only** | Skip docs-checker (use project-RAG instead). | None — docs-checker is for external APIs. |

**Heuristic, not law.** The EM applies judgment: scale (1-page stub vs 30-page spec), complexity (3 API calls vs 50), distance from training (UE 5.6 features vs `Array.prototype.map`). When in doubt, run it — it's cheap. **Skip is silent — no flag needed, no justification required.**

**In practice:**
- **C++/UE artifacts:** run docs-checker.
- **Other languages:** EM judgment — bias toward running for unfamiliar SDKs and pinned versions; skip for routine in-distribution code.
- **Pure prose artifacts:** skip — nothing to verify.

**Dispatch:**
1. Dispatch `docs-checker` agent with the artifact path
2. docs-checker applies AUTO-FIX-class corrections inline and writes all edits as a single git-revertible commit
3. docs-checker emits `state/review-findings/{timestamp}-docs-checker-edits.md` (changelog sidecar) and `state/review-findings/{timestamp}-docs-checker.md` (verification report)
4. EM reads the edits sidecar (if any) and includes the following verbatim in the Opus reviewer's dispatch prompt:

   > A docs-checker pre-flight ran on this artifact. AUTO-FIX corrections were applied inline — see [edits sidecar path] for the changelog. UNVERIFIED claims are listed in [report path] for your verification. VERIFIED claims do not need re-checking; focus your review on architecture, approach, and design.

**EM spot-check obligation (mandatory):** After the Opus reviewer completes, the EM diffs the docs-checker commit against the pre-edit artifact for any auto-fix the Opus reviewer did not explicitly endorse. This spot-check is mandatory and time-bounded — read the changelog AND run the diff before marking the review stage done. Rollback is `git revert <docs-checker-commit-sha>` — one command.

**On docs-checker failure:** Proceed to Phase 2.8 and Phase 3 without the report. Reviewers fall back to their own verification. This phase is additive, not blocking.

**Phase 2.8 integrator note:** The review-integrator does NOT review docs-checker auto-fixes — those are pre-applied before the Opus reviewer sees the artifact. The integrator continues to handle Opus reviewer findings as today. The docs-checker changelog is part of the review record archived alongside the review findings.

### docs-checker AUTO-FIX scope, cap, and changelog schema

<!-- src: plan02-033, plan02-034, plan02-035, plan02-036, plan02-037, plan02-038, plan02-040, plan02-041 -->

**AUTO-FIX allowlist is narrow — artifact text only:** wrong API/method/header/signature/enum/module-placement claims. Hard prohibitions: prose, design-rationale, comments, structural changes, "legacy+new coexist" patterns, and Motivation/Decision/Risks sections. docs-checker corrects factual API claims, never argues with the plan's reasoning.

**Scope constraint — edits the artifact under review ONLY, never the referenced files.** If a plan cites the wrong header for a symbol, docs-checker corrects the citation in the plan/stub, not the `.cpp`/`.h` it's citing. This constraint is load-bearing for the integrator-bypass design: docs-checker's blast radius is provably confined to the one artifact the reviewer is about to read.

**Edit-budget cap:** `max(10, claims_count / 3)` edits per artifact. Beyond the cap, remaining INCORRECT items report as findings instead of auto-applying — this bounds blast radius if the verification source itself turns out to be inconsistent, and mitigates oscillation risk from giving a pre-flight agent inline-edit authority.

**Changelog sidecar schema** (`state/review-findings/{timestamp}-docs-checker-edits.md`, YAML per edit): `file`, `line_before`/`line_after`, `content_before`/`content_after`, `source` (tool/query/result_id), `claim_id`, `confidence` (high/medium). This is what the EM's mandatory spot-check (above) reads against the diff.

**Reviewer awareness:** the sentinel snippet `snippets/docs-checker-consumption.md` is synced to every reviewer that may see a pre-verified artifact (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, example-game-repo-the Game Dev Reviewer) — it explains how to read `VERIFIED`/`AUTO-FIXED`/`UNVERIFIED`/`INCORRECT` markers so reviewers don't re-verify what docs-checker already settled.

---

## Phase 2.7b: Prior-Art Verification (prior-art-checker pre-flight)

**The prior-art-checker is a recall pre-flight, not a reviewer. It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed by all downstream reviewers.**

Before dispatching expensive Opus reviewers, decide whether to run the **prior-art-checker** agent (Sonnet) as a suggested pre-flight. While docs-checker verifies factual claims about external APIs, prior-art-checker cross-references the plan's claims against **what we've already learned** — the full corpus is enumerated in `agents/prior-art-checker.md` § Bootstrap: corpus inventory (that file is the source of truth for the corpus list; not restated here). Reviewers receive a sidecar showing where the plan conflicts with prior art, where it should cite established patterns, and where it touches unprecedented ground.

**EM Decision Step — when to run:**

| Artifact type | Default | EM discretion |
|---|---|---|
| **Plan documents** (`docs/plans/*.md`, `~/.claude/plans/*.md`) | **Run by default.** Plans are the artifact this agent was designed for. | Skip only when the plan is a single-file mechanical bug-fix with no architectural decision. |
| **Enriched stubs with architectural decisions** | Run if any chunk introduces a new pattern, new agent, new convention, or modifies cross-cutting doctrine. | Skip for stubs that are purely mechanical execution of a previously-checked plan. |
| **Code review (no plan artifact)** | Skip. | Run when a PR/diff lacks a plan but introduces a new pattern or convention worth checking against doctrine. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — no claim surface to cross-reference. |
| **Trivial single-file edits** | Skip. | None — overhead exceeds the benefit. |

**Heuristic, not law.** When the plan reverses a prior decision, ALWAYS run — that is exactly the case where prior art most matters (per `coordinator/docs/wiki/pre-dispatch-verification.md` § Plan-Time Verification Checklist, "Premise-pass before regenerating torn-down structure"; `coordinator/CLAUDE.md` retired). When in doubt, run it; the agent is cheap and the alternative is silent doctrine decay.

**Skip is silent.** No flag needed, no justification required. EM judgment.

**Dispatch:**
1. Dispatch `prior-art-checker` agent with the plan path.
2. prior-art-checker reads project wikis, global wikis, lessons, and the improvement queue; cross-references the plan; writes a sidecar at the plan-derivable `state/plan-sidecars/<plan-stem>.prior-art-check.md` home (D0).
3. Sidecar verdict is `COMPATIBLE`, `WARN`, or `BLOCKED-SURFACE-TO-PM`.
4. **EM reads the sidecar before dispatching the Opus reviewer.** This step is mandatory — the verdict determines whether to proceed or escalate to PM. It does NOT require EM pre-disposition of Conflicts; the Opus reviewer's judgment is the primary input on direction-of-correction (per `snippets/prior-art-check-consumption.md` and `docs/wiki/prior-art-checker.md § Bidirectional resolution`).
   - **COMPATIBLE:** include the sidecar path in the Opus reviewer's dispatch prompt and proceed.
   - **WARN:** include the sidecar in the Opus reviewer's dispatch prompt and proceed. The reviewer recommends a direction-of-correction per Conflict (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`). EM pre-disposition in the dispatch brief is OPTIONAL — use it when the right direction is mechanically obvious (e.g., a Conflict against load-bearing doctrine that's already settled), and leave it for the reviewer when the call is architectural. A reviewer recommendation contrary to an EM pre-disposition escalates as ASK in the integrator pass (see `agents/review-integrator.md § Prior-Art Conflict Resolution`).
   - **BLOCKED-SURFACE-TO-PM:** STOP. Surface to PM with the sidecar quote(s). Do NOT dispatch the Opus reviewer until PM has decided fold-in or authorized override.
5. Include the following verbatim in the Opus reviewer's dispatch prompt:

   > A prior-art-check pre-flight ran on this plan. Sidecar: [path]. Verdict: [verdict]. The sidecar is unintegrated — your judgment is the primary input on direction-of-correction per Conflict. Recommend `update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed` per Conflict with one-sentence reasoning. Use the Compatible-but-relevant section to identify wikis the plan should cite; flag missing citations as findings if they would aid maintainability. (Any EM pre-disposition appears in this dispatch brief; if your judgment differs, say so — the integrator will escalate as ASK.)

**On prior-art-checker failure:** Proceed to Phase 2.8 and Phase 3 without the sidecar. Reviewers fall back to their own doctrine recall (which is the pre-2026-05-06 baseline). This phase is additive, not blocking.

**The prior-art-checker is a feedback loop on wiki quality.** Repeated false-positive conflicts on a wiki entry are signal — surface to PM as a candidate for wiki revision (the wiki may be outdated, vague, or wrong). This is the recall side of the capture-recall loop; without it, captured wikis decay silently.

**Fleet-capability-index input (cross-repo capability lens).** The prior-art-checker dispatch may optionally carry a `fleet_capability_index:` input — the path to the claude-klabauter-aggregated, persisted fleet-capability index, resolved and TTL-checked by the SKILL at dispatch time. When present, the Platform-capability bucket ("consume, don't rebuild") is consumed by the checker alongside the other buckets in the same pre-flight pass. Failure to resolve/read the index is additive and non-blocking — the checker proceeds without the bucket, matching the existing Phase 2.7b failure posture above. See `docs/wiki/prior-art-checker.md § Cross-repo capability lens` for the substrate and matching rationale.

**Phase 2.7b integrator note:** The review-integrator processes prior-art-side edits AFTER the Opus reviewer pass, per the direction-of-correction the reviewer (and optionally the EM) named. No integrator pass runs *between* the prior-art-checker and the first named reviewer — pre-flight sidecars are not a sequential reviewer. See `agents/review-integrator.md § Prior-Art Conflict Resolution` for the integrator's authority on wiki/registry/lessons edits. The prior-art-check sidecar is archived alongside the review findings. Note: this contract applies to prior-art-checker WARN (Conflicts with five valid directions, passing through the reviewer unintegrated); plan-coverage-checker INCOMPLETE has a different contract — see Phase 2.7d.

---

## Phase 2.7d: Plan Coverage Verification (plan-coverage-checker pre-flight)

**The plan-coverage-checker is a completeness pre-flight, not a reviewer. It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed by all downstream reviewers.**

**Trigger (skill-internal — no EM opt-out):**

| Plan shape | Run? | Why |
|---|---|---|
| Plan contains an audit/findings/issues table with ≥5 items | **Run.** | The oracle exists; coverage is checkable; the empirical 36/9/4 case lives here. |
| Plan contains an audit table with 1–4 items | Run. | Cheap. False-skip cost is higher than false-run cost. |
| Plan contains no audit/findings table (pure greenfield design) | Skip silently. | Agent would emit `SCOPE-MISMATCH`; no point spending the dispatch. |
| Plan is single-file mechanical fix (no design content) | Skip silently. | Same as prior-art-checker triviality skip. |
| Plan is a doc redesign / wiki rewrite | Skip silently. | No fix-slate shape. |

**Dispatch:**
1. Dispatch `plan-coverage-checker` agent with the plan path.
2. Agent parses oracle + slate, runs three lenses, writes sidecar at the plan-derivable `state/plan-sidecars/<plan-stem>.plan-coverage-check.md` home (D0).
3. EM reads sidecar before dispatching the Opus reviewer.
   - **COMPLETE:** include sidecar path in Opus reviewer dispatch and proceed.
   - **INCOMPLETE:** fold findings into the plan BEFORE Opus reviewer dispatch. Missed items added to slate or OOS with architectural reason. Weak-OOS rewritten or promoted to slate. Substrate-drift amended.
   - **BLOCKED-SURFACE-TO-PM:** STOP. Surface to PM with verbatim findings.
   - **SCOPE-MISMATCH / DEGRADED:** proceed; no fold needed.
4. Include verbatim in Opus reviewer dispatch prompt:

   > A plan-coverage-check pre-flight ran on this plan. Sidecar: [path]. Verdict: [verdict]. If INCOMPLETE, the EM has folded findings into the plan body — review the amended version. The sidecar is included as audit trail; coverage gaps are not yours to re-litigate, but if you spot a NEW gap the lens missed, flag it.

**On plan-coverage-checker failure:** Proceed without the sidecar. Phase is additive, not blocking.

**Doctrine note — divergence from Phase 2.7b sidecar contract.** The Phase 2.7b note that "the Opus reviewer's judgment is what we want shaping direction-of-correction" applies to **prior-art Conflicts**, which have five valid directions (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`). It does NOT apply to plan-coverage-check Missed findings, which have three valid EM-mechanical resolutions: (1) add-to-slate, (2) architectural-OOS, (3) oracle-was-wrong (amend the audit table with explanatory note). None of these three require reviewer judgment. The mechanical nature of a missed audit item makes pre-fold the correct posture; reviewer judgment adds no value on a question the EM can resolve mechanically. Same shape for substrate-drift (amend or explain). This is the architectural distinction between recall (prior art) and coverage (this lens). Note: this contract applies to prior-art-checker WARN, not to all pre-flight findings.

**Phase 2.7b and 2.7d run in parallel** when the plan triggers both. They are independent — neither reads the other's sidecar. **Phase 2.7c still gates on 2.7b completion (unchanged from existing doctrine)** — external-pattern-checker reads the prior-art sidecar as input. So the runtime shape is: (2.7b ∥ 2.7d) → 2.7c → 2.8 → named reviewer. The EM consumes all available sidecars before dispatching the named Opus reviewer.

---

## Phase 2.7c: External Pattern Verification (external-pattern-checker, opt-in)

**The external-pattern-checker is a triage pre-flight, not a reviewer. It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed as ad-hoc context in the Opus reviewer's dispatch prompt.**

Before dispatching expensive Opus reviewers, decide whether to run the **external-pattern-checker** agent (Sonnet) as an opt-in pre-flight. Where docs-checker verifies facts and prior-art-checker recalls internal doctrine, external-pattern-checker asks a different question: *"Is there enough external signal on this topic that we should dispatch deeper research before the Opus reviewer sees this plan?"*

**This phase is opt-in only and is skipped silently for ~95% of plans.** There is no default-on behavior.

**EM Decision Step — the two-condition trigger gate:**

| Condition | Requirement |
|---|---|
| **A** | prior-art-checker returned `Silent` on ≥ 1 **architecturally-loaded** claim — meaning the claim involves a new abstraction, protocol, or doctrine surface (not a constant bump, test fix, or rename) |
| **B** | The plan is `scope_mode: architecture` or `scope_mode: feature` AND the topic is one the project has struggled with, evidenced by ≥ 2 entries in `state/lessons/` or the central structured queue (`state/improvement-queue/`, `queue_scope: central`) sharing a noun-phrase from the plan's central abstractions, OR ≥ 1 archived handoff in `archive/handoffs/` whose body matches the same noun-phrase AND contains "reverted" / "abandoned" / "rolled back" |

**Both A and B must hold.** If either condition is absent, skip this phase silently — no flag, no justification. PM can also authorize a direct invocation ("run external-pattern-check on this plan") which bypasses the gate.

**This phase always runs AFTER Phase 2.7b (prior-art-checker).** It reads the prior-art sidecar as input; dispatching it before prior-art-checker runs produces an automatic SCOPE-MISMATCH abstain.

**Dispatch (when both conditions hold):**
1. Dispatch `external-pattern-checker` agent with the plan path. The EM does NOT pass the prior-art sidecar path as an argument — external-pattern-checker DERIVES it itself from the plan-stem convention (`state/plan-sidecars/<plan-stem>.prior-art-check.md`, D0), the same convention its own output home follows. This is the load-bearing proof that the plan-derivable convention closes the coupling gap that a passed-argument would have papered over.
2. The agent locates and reads the prior-art sidecar via that derivation, identifies architecturally-loaded Silent claims, runs ≤ 2 WebSearch + ≤ 5 WebFetch, and writes a sidecar at the plan-derivable `state/plan-sidecars/<plan-stem>.external-pattern.md` home (D0).
3. Sidecar verdict is `RESEARCH-RECOMMENDED`, `LIGHT-CONTEXT-AVAILABLE`, `NO-EXTERNAL-SIGNAL`, `DEGRADED`, or `SCOPE-MISMATCH`.
4. **EM reads the sidecar before dispatching the Opus reviewer.** The verdict determines next steps:
   - **RESEARCH-RECOMMENDED:** EM dispatches the recommended `general-purpose` web scout or `/deep-research` as a separate decision before the Opus review. Include the sidecar path in the Opus reviewer prompt.
   - **LIGHT-CONTEXT-AVAILABLE or CAUTIONARY-NOTE:** Fold the relevant `Light Context Surfaced` / `Cautionary Note` sections as a one-paragraph briefing into the Opus reviewer dispatch prompt.
   - **NO-EXTERNAL-SIGNAL:** Proceed to Phase 2.8. No fold-in needed.
   - **DEGRADED:** Treat as no signal — proceed as if the phase did not run.
   - **SCOPE-MISMATCH:** The trigger conditions were not met (the agent determined this itself). Note the reason and proceed.

**Mandatory fold-confirmation (auditable consumption — per plan disposition D1):**

In the same dispatch turn where you proceed to Phase 2.8 / Phase 3, you MUST include verbatim either:

> (a) A one-paragraph briefing copied from the sidecar's `Light Context Surfaced` / `Cautionary Note` buckets (included in the Opus reviewer's dispatch prompt), OR
> (b) "external-pattern-check ran; no fold needed (verdict: NO-EXTERNAL-SIGNAL)."

This makes consumption auditable. Silent omission of the sidecar with no confirmation is not permitted.

**On external-pattern-checker failure:** Proceed to Phase 2.8 and Phase 3 without the sidecar. This phase is additive, not blocking.

**Note on vocabulary:** external-pattern-checker uses its own bucket vocabulary (`Signal Worth Deeper Research`, `Light Context Surfaced`, `Cautionary Note`, `No External Signal`). These are distinct from prior-art-checker's vocabulary (`Conflicts`, `Compatible-but-relevant`, `Silent`). Do not conflate them in reviewer prompts or EM notes. Full doctrine: `docs/wiki/external-pattern-checker.md`.

---

## Phase 2.8: Pre-Review Artifact Verification (Haiku, optional)

Before dispatching an expensive Opus reviewer, dispatch a **Haiku agent** to verify the artifact is well-formed and worth reviewing. This catches broken artifacts before they waste the most expensive tokens in the system.

**When to run:** When the artifact is code or enriched stubs (not plans or docs — those are cheap to review regardless).

**Haiku checks:**
1. **Compilable/parseable** — does the code compile, typecheck, or lint clean? Run the project's validation command.
2. **Enrichment complete** — are all placeholder/TODO markers in enriched stubs filled? (`grep -r 'TODO\|PLACEHOLDER\|TBD\|\[UNKNOWN\]'`)
3. **Non-trivial** — is the artifact non-empty and substantive? (not a stub with only headers)

**On failure:** Report to coordinator with the specific issue. Do NOT dispatch the Opus reviewer. Fix the artifact first (or re-dispatch enrichment), then retry.

**On pass:** Proceed to Phase 3.

**Why Haiku:** Running `tsc --noEmit`, `grep`, and checking file sizes is mechanical work. A failed pre-flight saves 1 full Opus reviewer dispatch — the highest per-agent cost in the system.

---

## Phase 3.5: Parse and Render Structured Output

After each reviewer completes:

1. **Parse the JSON block** from the reviewer's output. Look for a fenced ` ```json ` block containing a `ReviewOutput` object with `reviewer`, `verdict`, `summary`, and `findings` fields.

2. **If valid JSON found:**
   - Render findings as a Markdown table for human reading:
     ```
     | # | File | Lines | Severity | Category | Finding |
     |---|------|-------|----------|----------|---------|
     | 0 | path/to/file.ts | 42-48 | critical | correctness | Description |
     ```
   - Write raw JSON to disk at: `state/review-findings/{timestamp}-{reviewer}.json`
     Create `state/review-findings/` directory if it doesn't exist.
   - Report: "Structured output parsed: N findings (X critical, Y major, Z minor, W nitpick)"

3. **If valid JSON but with field drift, normalize before rendering:**
   - Severity: map `"high"` → `"major"`, `"moderate"/"medium"` → `"minor"`, `"low"` → `"nitpick"`
   - Verdict: normalize to ALL_CAPS_UNDERSCORES (e.g., `"request_changes"` → `"REQUIRES_CHANGES"`)
   - Field names: map `"description"/"detail"` → `"finding"`, `"recommendation"` → `"suggested_fix"`, `"line"` → `"line_start"`
   - Category: strip underscores/verbose suffixes (e.g., `"trust_and_transparency"` → `"trust"`, `"cognitive_flow"` → `"cognitive-load"`)
   - Log: "Normalized N fields in reviewer output" (for tracking compliance improvement over time)

4. **If no valid JSON found (reviewer output is prose):**
   - Log a warning: "Reviewer returned prose output, not structured JSON. Proceeding with prose."
   - Continue with the prose findings as before.
   - Note in the Phase 5 report that this reviewer needs structured output enforcement on re-review.

5. **Apply `--problems-only` filter** (if flag was set):
   - Filter the rendered findings table to `severity != "nitpick"`. Findings missing a `severity` field are treated as `minor` and included.
   - Nitpicks are still present in the JSON file written to disk (audit trail)
   - Nitpicks are NOT auto-applied to the artifact
   - Only findings with severity ∈ {critical, major, minor} are included in the "apply all" list

### Structured Output Schemas — ReviewFinding / UXReviewerFinding / ZoliOutput

<!-- src: plan01-020 -->

All reviewer output is wrapped in a `ReviewOutput` envelope: `reviewer`, `verdict`, `summary`, `findings[]`. Three finding shapes exist depending on reviewer type:

- **`ReviewFinding`** (code reviewers — the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, domain reviewers): `file`, `line_start`/`line_end`, `severity`, `category`, `finding`, `suggested_fix`.
- **`UXReviewerFinding`** (UX reviewer): `flow`, `step`, `file`/`line` (optional — UX findings aren't always code-anchored), `severity`, `category`, `finding`, `suggested_fix`.
- **`ZoliOutput`** (backstop/DoE-tier dispatches): `subject`, `conservative_stance`, `ambition_challenge`, `tension_level`, `ai_capacity_argument`, `suggested_approach`, `common_ground`, `decision_needed`. The Director of Engineering's output is structurally a tension record, not a findings list — their job is to name the seize-the-moment-vs-defer tradeoff explicitly, not to enumerate line-level defects.

These schemas are what Phase 3.5's JSON-block parser expects; the field-drift normalization table in Phase 3.5 step 3 exists precisely because reviewers occasionally emit near-miss field names against this canonical shape.

**Sidecar-path note — integrator intake vs. human/audit artifact.** The JSON written to `state/review-findings/{timestamp}-{reviewer}.json` (step 2 above) is a **human/audit artifact and is NOT the intake path for the review-integrator**. The integrator reads from the reviewer-scaffolded on-disk sidecar. Spec backlink: `cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md`.

All findings-producing reviewers persist to the DR-091 `state/subagent-share/<session>/<provision_key>.md` home by default — no EM pre-scaffold in the common case, no claim marker:

- **Sonnet `code-reviewer`** (the one reviewer — no `-selfpersist` variant): writes to its DR-091-provisioned sidecar — pre-provisioned by the dispatching EM in the common case, self-scaffolded into that same home via `coordinator-doc-new --type review-findings` only when no path arrived pre-provisioned — edits the `<!-- FINDINGS -->` sentinel with its findings, and returns: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N> | executed: <yes|no>`. The EM reads the returned path.

- **Persona reviewers** (the Staff Engineer, the Director of Engineering, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Game Dev Reviewer): are dual-use (advisory OR sidecar-review). When dispatched for a review that feeds an integrator, the invoking skill injects the DR-091 provisioned `state/subagent-share/<session>/<provision_key>.md` path into the dispatch brief — claude-klabauter's `provision_report` engine has already created the sidecar at spawn — and the persona writes its findings into that path and returns the same pointer line. No sentinel-append self-scaffold, no EM pre-scaffold, no claim marker. The review-integrator intake fails loud (BLOCKED) if the returned sidecar is a trivial/unfilled scaffold — the intake fill-guard, not a per-dispatch-site check.

**No inline return is a valid reviewer mode.** An EM walking Phases 3.5 and 3.7 never hands the integrator an inline finding list — the on-disk sidecar is the integrator's intake contract (`agents/review-integrator.md § Intake precondition`). If a reviewer returns inline, re-dispatch it — do not transcribe.

---

## Phase 3.7: Review Integration (replaces manual feedback application)

After each reviewer completes (and Phase 3.5 runs):

> **Sidecar pre-condition.** The reviewer writes to its DR-091-provisioned sidecar at `state/subagent-share/<session>/<provision_key>.md` and returns a pointer line. Phase 3.5's `state/review-findings/{timestamp}-{reviewer}.json` is a human/audit render, NOT the integrator intake. See Phase 3.5 § Sidecar-path note for the full contract.

1. Dispatch the review-integrator agent with:
   - The **on-disk sidecar path** returned by the reviewer in its pointer line (`DONE: <sidecar-path> | verdict: … | findings: …`). Never an inline finding list; the integrator hard-stops on inline-relayed findings (`agents/review-integrator.md § Intake precondition`).
   - The artifact path(s)
   - The reviewer name (for annotation attribution)
2. Review-integrator applies all findings, annotates changes, returns completion report
3. EM reviews:
   - Escalation list (usually 0 items) — resolve any disagreements
   - Spot-check the diff (verify integrator applied findings correctly)
   - If escalations exist: EM resolves directly or escalates to PM

**Reviewer 2 (Generalist) — if routing calls for one:**

4. Dispatch Reviewer 2 with the EVOLVED artifact (post-review-integrator changes)
5. Reviewer 2 catches novel issues AND regressions from the integration pass
6. Dispatch review-integrator again for Reviewer 2's findings (same Phase 3.7 protocol)

---

## Phase 4: Backstop Handling

This phase applies when the primary reviewer (the Staff Engineer or a domain reviewer) has run and the chain calls for a backstop pass. It does NOT apply when the Director of Engineering was the standalone primary reviewer — in that case, those findings flow through the normal integrator path (Phase 3.7) and Phase 4 is a no-op.

When effort level is High AND a primary reviewer (not standalone the Director of Engineering) ran:
1. Verify that the reviewer invoked their backstop partner (the Director of Engineering for the Staff Engineer; the Staff Engineer for domain reviewers; the UX Reviewer for the Front-End Reviewer; the Staff Engineer for the UX Reviewer)
2. If the backstop was not invoked, prompt the reviewer to do so OR dispatch the backstop directly, describing the ambition-backstop posture in the brief's prose — never as a `mode` argument, which is the harness `Agent` tool's own parameter and errors the dispatch (see `routing.md` § the Director of Engineering Standalone vs. Backstop)
3. If the backstop disagreed: both perspectives are surfaced to Coordinator/PM per the routing.md reconciliation protocol

When effort level is Medium:
- Backstop invocation is at the reviewer's (or EM's) discretion
- No verification needed

**When the Director of Engineering ran as standalone primary, skip Phase 4 entirely.** the Director of Engineering standalone is a peer-to-the Staff Engineer review with cross-team authority — there is no further backstop above the DoE chair. The Director of Engineering is the terminal backstop in the system; nothing wraps it.

---

## Phase 5: Report

Summarize the review with a **triage table** — every finding must have an explicit disposition:

| # | Finding | Severity | Disposition | Reasoning |
|---|---------|----------|-------------|-----------|
| 0 | [summary] | critical | Applied | [what changed] |
| 1 | [summary] | minor | Dismissed | [why — PM input needed / disagree] |

Dispositions: **Applied** (fix implemented), **Captured** (deferred to backlog — state where), **Dismissed** (with reasoning).

Then summarize:
- Who reviewed, at what effort level
- Disposition counts: N applied, N captured, N dismissed
- What was escalated to PM (if anything)
- Verdict: Ready for execution / Needs PM decision / Needs rework

**Post-review synthesis:** If 2+ reviewers ran, produce a synthesis note per the routing rules. This cross-references coverage declarations and flags reinforcing findings, conflicts, and gaps. The synthesis is the coordinator's judgment — no additional agent dispatch.

---

## Composition Patterns for Major Surface Additions

The numbered phases above describe a single review pass. For substrate-blind spec→impl chains, parallel-enriched cohorts, and architecturally-loaded plan stubs, composition matters as much as any single reviewer's depth. The patterns below name the recipes that have caught real bugs the single-pass shapes missed.

### Five-layer review topology

For major surface additions where the spec author was substrate-blind (no on-disk grep, no per-file Read), a single Opus reviewer is not enough — orthogonal lenses catch different error classes. The full topology:

1. **Plan-author negative-search** (W1, `coordinator:plan` skill (pre-flight negative-search is Branch B)). Prohibitions and prior reversals surfaced before reviewer dispatch.
2. **docs-checker pre-flight** (Phase 2.7). External-API claim verification, AUTO-FIX inline.
3a. **prior-art-checker pre-flight** (Phase 2.7b). Doctrine-recall against wikis + lessons + queue.
3b. **plan-coverage-checker pre-flight** (Phase 2.7d). Oracle-vs-slate completeness, hedge detection, in-repo substrate drift. Skill-internal trigger — runs unconditionally on plans with oracle tables. Runs in parallel with layer 3a (prior-art-checker).
4. **the Staff Engineer Pass 0 premise review** (W3). Plan-level premise validity; `clean | needs-justification | refuted`.
5. **Domain reviewer (the Game Dev Reviewer for game-dev / the Data Science Reviewer for data / etc.) + enricher callsite read** (Phase 3). Existing-codebase pattern check + on-disk callsite reality.

<!-- Review: code-reviewer — plan-coverage-checker (Phase 2.7d) was absent from the five-layer topology list; added as 3b parallel to prior-art-checker, matching the (2.7b ∥ 2.7d) runtime shape documented in Phase 2.7d. -->

Use the full five-layer recipe when the plan introduces a new cross-cutting abstraction, new doctrine surface, or the spec author flagged substrate-blind framing. Skip layers only with explicit rationale recorded in the dispatch trail. Specialist-worker lenses (test-evidence-parser, security-audit-worker, dep-cve-auditor, doc-link-checker) ride alongside layer 5 as routine, not opt-in — they catch what generalist Opus reviewer lenses miss.

### the Staff Engineer Pass 0 — premise-challenge protocol (layer 4 detail)

<!-- src: plan02-046, plan02-047, plan02-048, plan02-049, plan02-050 -->

Pass 0 runs before the Staff Engineer's normal 4-pass review and answers one question: does this plan's premise contradict an explicit, greppable prior decision without engaging the original argument? It emits three fields:

- `premise_review`: `clean` / `needs-justification` / `refuted`.
- `alternatives_considered`: a **flat list, 0-3 items, no ranking or comparison**, each carrying a "not deep" disclaimer — Pass 0 is a backstop that surfaces the absence of alternatives-search, not a substitute for one.
- `planning_quality`: one sentence, emitted only when structural signals are present (zero alternatives considered, no negative-search performed, single-source citation).

**Four hard guardrails** keep Pass 0 from mission-creeping into a second planning pass: it does NOT investigate alternatives in depth, does NOT pick a winner among them, does NOT run planning itself (it is a backstop, not a substitute), and does NOT rank or compare — the list stays flat.

**`REJECTED` verdict.** When `premise_review: refuted`, the Staff Engineer may return verdict `REJECTED`. This is **advisory only** — the review-integrator surfaces it to the EM for routing, never applies it as a blocking gate on its own authority. The EM may override a `REJECTED` verdict **iff the PM explicitly agrees**, and the override must be recorded verbatim: `"PM-overridden REJECT. PM said: <verbatim quote>. Reasoning: <reasoning>."` A paraphrase is not a valid override — proceeding without the verbatim PM quote is a doctrine violation, same class as any other silent-override anti-pattern.

### Architectural review chain — the Staff Engineer, the Game Dev Reviewer, enricher catch different bugs

Within the layer-5 envelope, the three roles divide the work:

- **the Staff Engineer catches structural problems.** Plan coherence, missing seams, architectural inversions, premise refutation.
- **the Game Dev Reviewer (or domain-equivalent) catches existing-codebase-pattern violations.** "We don't do it that way here" — patterns the plan invented when the codebase already had a convention.
- **The enricher catches callsite reality.** What the code actually does at the consumer end — function envelopes, reachability, guard conditions the plan paraphrased.

All three are needed on architecturally-loaded stubs. Dropping any one of them produces a known failure class.

### Sequential two-reviewer on architecturally-loaded stubs

For plan stubs that are architecturally-loaded but not full-spec scope, the minimum viable shape is **sequential two-reviewer (generalist the Staff Engineer + domain reviewer)** plus the layer-2/2.7b pre-flights. Single-pass review on this surface has a documented miss rate — the second lens routinely surfaces issues the first missed at lower cost than fixing the bug in execution. Sequential, not parallel: integrate Reviewer 1's findings before dispatching Reviewer 2 (the merge-gate parallel carve-out in CLAUDE.md does not apply to plan/stub review).

### Two-pipeline review on shared artifacts: per-stub + per-cohort + docs-check

When a cohort of stubs is enriched in parallel from a shared spec, **two pipelines on the same artifacts** beats picking one lens:

- **Per-stub depth:** the Staff Engineer (or domain reviewer) on each stub independently. Catches local correctness, premise validity, structural soundness.
- **Per-cohort coherence:** one reviewer across the whole cohort. Catches contradictions between stubs, shared-API gaps, sibling-surface drift, cross-stub seam violations.
- **docs-check pre-flight:** every external-API claim verified across the cohort, once.

Composition beats picking one. The per-cohort lens routinely re-edits stubs that the per-stub lens already marked "complete" — that is the value, not a defect. Stub completion is conditional on cohort settle, never on per-stub verdict alone. Integrator sweeps cohort-wide findings back across already-applied stubs before declaring the wave done.

### Reviewers false-positive on import-fallback seams

A common false positive: reviewers flag `try: import X / except ImportError: ...` patterns as bugs or anti-patterns without reading both arms. The except-arm is usually a deliberate graceful-degradation seam — a fallback to a vendored module, a stub for optional dependency, or a runtime-detected capability. Flagging the seam as a bug inverts the intent.

**EM disposition discipline:** when a reviewer flags an `ImportError` fallback, **read both arms** before applying. If the except-arm is a structural seam (not error-swallowing), dismiss the finding with a one-line reasoning ("intentional fallback for optional X"). Same shape for try/except `ModuleNotFoundError`, `AttributeError` on capability probes, and platform-conditional imports.

The integrator does not auto-apply import-fallback findings — they always land in the EM disposition table.

---

## Parallel Code Review Gate (merge boundary only)

The `coordinator:parallel-code-review` skill is the merge-gate ceremony, wired into
`/merging-to-main` Step 1.54. It is **NOT** a mid-implementation review tool and must
refuse invocation from any context other than merge. The parallel exception to the
sequential-dispatch HARD RULE lives here — frozen diff at merge boundary means no
integration occurs between reviewers, so parallel-blind + synthesizer is the correct shape.
<!-- src: plan04-009 -->

**Why parallel-with-carve-out, not one of the alternatives.** Three shapes were considered
and rejected before landing on the carve-out: (1) *sequential, no carve-out* — rejected, it
loses convergence-as-confidence (independent entry points agreeing is the signal; sequential
integration between reviewers erases the independence); (2) *Opus-only, no mechanical workers* —
rejected, it loses the orthogonal-lens guarantee the mechanical workers provide (security/deps/tests
are lenses no generalist Opus reviewer reliably re-derives); (3) *workers first, then the Staff Engineer* —
rejected, it makes the Staff Engineer's Layer-2 pass dependent on worker output, which defeats the
independence that makes convergence meaningful in the first place. The chosen shape — parallel
dispatch with the merge-gate carve-out — is the only one of the three that preserves independent
entry points delivering convergence-as-confidence. <!-- src: plan04-010 -->

### Dispatch graph (as of 2026-05-23)

**Step A (sequential):** Freeze the week's diff via `coordinator/bin/freeze-review-diff.py
--range origin/main...HEAD --slice-id weekly-<TS>`, which writes
`state/review-trail/diffs/<slice-id>.{diff,head.sha}` and prints the `.diff` path. There is no
`$FINDINGS_DIR` mirror — `workflows/review-wave.mjs` derives the `.head.sha` sibling from the
printed `.diff` path and passes both paths explicitly into the synthesizer dispatch as
`DIFF_PATH`/`HEAD_SHA_PATH`. Run Step 7 prelude (external to skill body) to compute seam-first
chunks and write `state/review-trail/.weekly-reviewer-scopes.json`.

**Step B (parallel — single Agent batch):**
- N × `code-reviewer-weekly` (Sonnet variant, Write-capable for findings files only):
  one instance per seam-first chunk of narrowed scope. Seam-first chunking is a **hard
  constraint** — non-negotiable. Each cross_segment_seam file plus the union of hunks
  touching it forms an atomic nucleus assigned whole to ONE chunk; only non-seam
  co-touching files may spill if nucleus exceeds size target.
- `security-audit-worker` (Sonnet): semgrep/bandit/gitleaks, full week diff always.
- `dep-cve-auditor` (Sonnet): language CVE feed, full week diff always.
- `test-evidence-parser` (Sonnet): classifies captured test failures — `tools: ["Read", "Edit"]`, executes nothing. It reads output someone else produced: the EM's own run, or a `test-runner` dispatch. Full week diff always.

The three mechanical workers ALWAYS run on the full week diff. They are never scoped down
by the trail — workstream-complete reviews do not invoke them, so "trail-covered" ≠ "mechanically
covered."

**Step C (sequential — after all workers return):**
Synthesizer (Sonnet) reads N chunk-reviewer files + 3 specialist files from disk. Per the
no-rewrite contract: every finding appears verbatim (quote or omit, never paraphrase).
Output JSON:
```json
{
  "verdict": "BLOCKED|WARN|OK",
  "convergent_findings": [],
  "per_reviewer_findings": {"chunk-1": "...", "chunk-2": "...", "security": "...", "deps": "...", "tests": "..."},
  "arch_tier_candidates": [],
  "requires_em_resolution": []
}
```
`arch_tier_candidates` collects verbatim `escalate_to_architecture` flags from chunk-reviewers.
Convergence fires across chunk-reviewer × specialist (different lens domains) or when ≥2
chunks independently flag the same seam file.

**Step D (gate):**
- `BLOCKED` → halts merge.
- `WARN` → proceeds with warning in PR body.
- `OK` → proceeds silently. Subvariant: `OK (the Staff Engineer trail-covered, mechanical clean)` when
  chunk-reviewer scope was empty and mechanical workers found nothing.

PR body line: `**Code-review gate:** [BLOCKED | WARN | OK] — convergent: N — code-review: <chunk-count> — security: <count> — deps: <count> — tests: <pass/fail/flake>`

**Step 7.5 (post-gate, sequential):** the Staff Engineer Layer-2 architecture-altitude pass. Input:
(i) week's changelog digest, (ii) synthesizer's `arch_tier_candidates`, (iii) synthesizer's
`convergent_findings`, (iv) seam-file set. Output: tech-debt / refactor-consolidate / YAGNI
recommendations, packaged as spinoff candidates. The Staff Engineer Layer-2 NEVER blocks merge — it
surfaces to PM as recommendations only.

### Skip rules

| Condition | Action |
|---|---|
| Diff <10 lines OR touches only `tasks/`, `tmp/`, `archive/`, `docs/wiki/` | Skip entirely |
| Doc-only diff | Skip chunk-reviewers; run mechanical workers |
| Plan/spec-only diff | Run chunk-reviewers; skip mechanical workers |
| Force flag | Run all regardless |

### agent/code-reviewer-weekly.md — thin variant

The base `code-reviewer.md` is read-only. The weekly variant authorizes exactly one Write
target: the assigned findings path (`$FINDINGS_DIR/chunk-<k>.md`). The base read-only
contract is intentionally preserved — adding Write to the base would grant Write to
workstream-complete dispatches (explicitly out-of-scope). Any extension of the weekly variant's
Write surface requires EM explicit scope-check on return via `git --no-optional-locks status`.

### Cost envelope (per merge gate invocation)

| Worker | Token range |
|---|---|
| docs-checker (conditional, Sonnet) | 5–15K |
| N × code-reviewer-weekly (Sonnet, per chunk) | ~5–30K each |
| security-audit-worker (Sonnet) | 10–30K |
| dep-cve-auditor (Sonnet) | 10–25K |
| test-evidence-parser (Sonnet) | 5–30K |
| synthesizer (Sonnet, in/out) | 15–40K / 3–8K |

Total: ~75–200K tokens. Expected frequency: 1–3× per active day. This is the justified
cost — multi-lens mechanical sweep at merge is the gate that workstream-complete reviews and
plan-time reviews do not substitute for.

## Reviewer Elevation Past Charter

*project-rag.* The PM may elevate a reviewer past their default charter for a specific dispatch — e.g. invoking the Director of Engineering not as ambition-backstop (their default) but as standalone DoE for an architectural call; invoking the Staff Engineer with cross-repo authority they do not carry by default. Elevation must be **verbatim in the brief** — the reviewer's default charter is what they pattern-match against without explicit elevation, and pattern-match will silently win over implicit elevation.

**Required form:**

> *"You are dispatched in elevated mode: [DoE / cross-repo authority / prior-art-override / other]. This dispatch grants [specific authority]. Your default charter ([brief restatement]) does NOT apply for this artifact."*

Without the verbatim elevation, the reviewer falls back to default charter — even if the dispatching EM verbally framed the dispatch as elevated. The brief is the contract; chat context is not.

**Authorization gate.** Elevation past charter is **PM-only**. The EM may surface elevation candidates (*"this artifact would benefit from DoE-tier the Director of Engineering, not ambition-backstop"*) but must wait for PM authorization before dispatching the elevated brief. EM-initiated elevation creates a doctrine hole where any EM can promote any reviewer to any charter ad hoc.

**Companion:** `prior-art-checker.md § Prior-art mutability` — for one specific elevated authority (DoE-override of prior-art-checker findings).

## Problems-Only Mode

When `--problems-only` is specified at invocation, append to the reviewer prompt:

> Return only findings that identify problems, bugs, security issues, or correctness concerns. Do not include praise, compliments, or suggestions for optional improvements. Nitpick-severity findings should still be included in your JSON output but will be filtered from the rendered summary.

Three explicit behaviors:
1. Nitpicks are written to the JSON file for audit trail
2. Nitpicks are omitted from the rendered Markdown table
3. Nitpicks are NOT auto-applied to the artifact

The filter criterion is `severity != "nitpick"` — not prose-based filtering. Applied in Phase 3.5 step 5.

## Reviewer Altitude Rules

These rules are cross-cutting tripwires that apply regardless of which pipeline phase you are in.

**1. Personas are Opus-only.** the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering carry `model: opus` in
their agent frontmatter. Dispatching a persona at Sonnet altitude (via `model: "sonnet"` override)
is a **doctrine violation** — persona prompt complexity is calibrated for Opus judgment;
Sonnet yields a "Sonnet-flavored the Staff Engineer" without the payoff. → `agents/code-reviewer.md`.

**2. Sonnet-tier code review uses `code-reviewer`, not a persona at Sonnet.** The dedicated agent
at `agents/code-reviewer.md` is the correct tool for workstream-complete review, handoff review, mid-session
quick review, and all code-output review contexts. Read-only tool surface (no Edit/Write);
OK/WARN/BLOCKED verdict enum where BLOCKED is advisory (EM retains shipping authority).

**3. Plan review altitude is binary: named Opus persona OR skip.** There is no Sonnet plan
reviewer. `code-reviewer` is the diff reviewer, scoped to weak tests / dead code / naming /
correctness on a frozen diff — not architectural judgment on a plan body. If a plan is worth
reviewing, dispatch the appropriate Opus persona; if it's not worth that ceremony, skip review
and let `code-reviewer` catch issues on the diff at `/workstream-complete`. Triage happens at
plan-time (plan-or-just-do-it), not at review-time (review-or-downgrade).

**4. Parallel dispatch exception is merge-gate-only.** The carve-out from the sequential-dispatch
HARD RULE applies exactly when: (a) artifact is a frozen diff at a merge boundary, (b) all
reviewers are orthogonal lenses, (c) a synthesizer with strict no-rewrite contract assesses
combined output. Plan/stub/doc review remains sequential. The exception sentence names all
three conditions to prevent scope creep.

**5. code-reviewer lens hardening is cumulative, not a fixed prompt.** Defect classes that
escaped review get named explicitly in `agents/code-reviewer.md` as they're discovered — e.g.
slash-command-extraction path bugs and slug path-injection were both added as named defect
classes after a 2026-05 cleanup wave surfaced them escaping review. Treat "the reviewer missed
X" as a signal to add X as a named lens, not just a one-off fix. <!-- src: plan11-045, plan11-049 -->

**6. `coordinator:review` routing calibration is not one-size.** A single-domain refactor does
not always need two Opus passes — sequential two-reviewer is a floor for architecturally-loaded
stubs (see § Sequential two-reviewer below), not a blanket default for every diff. Pre-flight
re-runs on amended plans are delta-scoped — re-run docs-checker / prior-art-checker / plan-coverage-checker
against what changed, not the whole plan again. <!-- src: plan11-047 -->

**7. Finding-confidence routing (borrowed pattern, cross-reviewer).** Where a reviewer or
pre-flight worker attaches a confidence score to a finding, route on it: confidence 10 =
doctrine contradiction (verbatim, greppable), 8-9 = high (near-certain), 6-7 = substantive
(worth surfacing, EM discretion), 5 = judgment call, <5 = speculative (relegate to a low-confidence
appendix, don't fold inline). AUTO-FIX-class authority (docs-checker) is reserved for the
high-confidence band; anything below routes to ASK / EM disposition rather than auto-applying.
<!-- src: plan02-002 -->

**the Director of Engineering's persona framing (elevation context).** the Director of Engineering's default challenge is not a generic
"be more ambitious" nudge — it's a named tension: *"We have AI capacity to do this properly.
Should we?"* — refactor-vs-patch, seize-the-moment-vs-defer. Elevating the Director of Engineering past ambition-backstop
(see § Reviewer Elevation Past Charter above) is asking them to hold that tension as primary
DoE judgment rather than as a counter-voice to the Staff Engineer. <!-- src: plan01-004 -->

**No new persona names.** The roster is closed at six (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering).
Proposals to add named personas for narrower judgment surfaces are rejected by default — workers
(unnamed Sonnet agents with tight tool surfaces) are the correct answer to "we need mechanical
leverage on a new surface"; a new persona is warranted only when the surface genuinely needs
*judgment*, not enumeration. <!-- src: plan02-016 -->

## Why Each Layer Is Load-Bearing — Pre-flights and Persona Are Not Substitutes

**Pre-flight workers (coverage-checker, prior-art-checker, docs-checker) and the Staff Engineer plan review catch different defect classes; both pay off even when the plan looks ready.** Empirical evidence from a high-confidence, the Director of Engineering-grounded plan (v12):

- **Plan-coverage-checker** caught one BLOCKING drift (cited helper symbol `_get_graph_db_conn()` did not exist) + 2 appetite hedges.
- **Prior-art-checker** caught a bump-rule wiki contradiction (additive-defaulted fields don't mandate a bump per Z-AMEND-1 carve-out 2 — the plan said "mechanically bumps").
- **Docs-checker** auto-fixed 4 line-number/symbol drifts.
- **the Staff Engineer** (post-pre-flights) added 1 major + 5 minor findings, including the closure-capture-footgun module-level-helper refactor and the `check-shipped-on-main.py` verifiable predicate replacing honor-system sequencing.

Every layer was load-bearing on a plan that had already passed EM confidence + external review. Skipping any one would have shipped a defect. The layers are non-overlapping — each catches a class the others don't scan for. (Source: project-rag v12 plan.) [universal]

## Author-Confidence Is the Failure Mode the Pre-Flight Chain Exists to Catch

**Pre-flight pre-review pipeline catches author-confidence-inflated fabrications that the author cannot catch in self-review.**

The author pattern-matches their own draft: if a citation FEELS like it should exist, it gets cited. Only a fresh agent with grep tools verifying against actual disk catches the fabrication. Two documented failure modes from the same plan:

- A doctrine citation asserted ">40 actions per verb" as a ceiling rule — caught by prior-art-checker (the wiki has counts but no such ceiling rule; the constraint felt load-bearing so it was authored in).
- A UE macro family was cited as the Effects module registration seam — caught by docs-checker (the actual seam was `Core.RegisterHandler(TEXT("..."), ...)` from EffectsModule.cpp; the macro family is Core-only and the plan invented its own seam).

Neither lens-of-author (re-reading the draft) would have caught either; only a fresh agent with grep tools verifying against actual disk caught both.

**How to apply:** treat the pre-flight chain (docs-checker + prior-art-checker + plan-coverage-checker) as the floor on any plan that cites doctrine, prior-art, or in-repo conventions. **Skipping "because the plan feels well-grounded" is the anti-signal** — author-confidence is the failure mode the chain exists to catch, and confident-feeling plans are exactly where the fabrication hides best.

*Source: example-game-repo (niagara-extensions-suite plan pre-flights).* [universal]

## the Staff Engineer / the Game Dev Reviewer / enricher role differentiation — each catches a different defect class

**The architectural review chain — the Staff Engineer catches structure, the Game Dev Reviewer catches existing-codebase patterns, enricher catches callsite reality — is not interchangeable. All three are needed for cross-module refactors.**
**Why:** A plan that survives the Staff Engineer's architectural review can still hide (a) duplication of an existing project pattern the Staff Engineer can't see from the diff (the Game Dev Reviewer territory), and (b) callsite-level multi-tenancy bugs that look correct in spec but break adjacent functionality (enricher territory). In one case, a CRITICAL spec bug (multi-tenancy) and a design-duplication smell (existing registry pattern) both survived two the Staff Engineer passes.
**How to apply:** for architecturally-loaded stubs with real stakes, run the full chain — the Staff Engineer → integrator → the Game Dev Reviewer → integrator → enricher → integrator → the Staff Engineer. Each layer targets a qualitatively different class of defect; skipping any layer leaves that class uncovered.

*Source: example-game-repo `state/lessons/` (example-game-repo-L117).*

---

## Session-End and Chain-End Review Scale

<!-- src: plan06-045, plan06-046, plan06-047, plan06-049, plan06-050 -->

At session end (via `/handoff` or `/workstream-complete`), three review scales apply — the EM picks based on diff shape, not ceremony:

| Scale | Trigger |
|---|---|
| **None** | Trivial, doc-only, <50 LOC |
| **Sonnet** (`code-reviewer`) | Executor-authored OR >50 LOC OR shared schema touched |
| **Sonnet + the Staff Engineer** | Chain-end AND (complex OR >500 LOC OR public API OR ≥3 segments) |

**Chain-end detection.** A session is chain-end when it was opened via `/pickup` and ends WITHOUT `/handoff` or `/spinoff` — i.e. it's the terminal link, not a checkpoint. Chain-end review scope is the **full chain diff since the last main merge**, not just the current session's segment — the point is to catch integration-seam mismatches across the whole chain, not re-review what a prior session's `code-reviewer` already covered.

**Review-trail record.** Every completed review writes `state/review-trail/YYYY-MM-DD-HHMMSS-session-id.json` (never overwritten) with fields: `sha_range`, `reviewer`, `scope`, `verdict`, `diff_loc`, `session_id`. This is the substrate the archive-aware readers (below) and the plan-delivery-audit skill consume.

**`/workweek-complete` Step 7 prelude.** Before the weekly merge-gate (§ Parallel Code Review Gate below) dispatches, Step 7's prelude reads the trail, computes unreviewed SHAs and cross-segment seams (files touched in ≥2 segments), and scopes the Staff Engineer's advisory pass to `unreviewed ∪ seams` — mechanical workers (security/deps/tests) still run the full week diff regardless.

**Anti-ceremony-bias tripwire.** *"If Sonnet-only feels like ceremony, escalate. The Staff Engineer is one dispatch. Redundant review costs one call. Unreviewed risk shipping costs hours debugging."* The asymmetry is deliberate — under-reviewing is the expensive failure mode, not over-reviewing.

---

## Plan-Time vs. Post-Implementation Review Are Complementary

<!-- src: plan07-001, plan07-002, plan07-004 -->

Plan-time review (prior-art-checker + the Staff Engineer, per the pre-flight chain above) and post-implementation session-end review (`code-reviewer`, § Session-End and Chain-End Review Scale above) are **complementary, not substitutional** — they catch different defect classes and neither one's presence licenses skipping the other:

- **Plan-time review** catches architectural shape, prior-art conflicts, substrate verification — questions answerable from the plan body and the codebase-as-it-currently-is.
- **Post-implementation review** catches what executors actually did versus what the plan said, integration-seam mismatches between chunks, scope creep, and executor cleverness that technically satisfies the letter of the stub while drifting from its intent.

**EM waive authority.** The EM retains authority to waive session-end review on genuinely trivial diffs (a mechanical typo fix, a single-file rename) — this is a `Sonnet` → `None` downgrade, not a doctrine bypass. The test for whether a waive is legitimate is the four-point shape, not a line-count threshold: (1) does plan-time/post-implementation complementarity still hold without this review (i.e. was there no plan-time review to begin with, making post-implementation the only lens)? (2) is this diff mechanical enough that mechanical gates (lint, typecheck, tests) substitute for a review lens? (3) does skipping pass the symmetric anti-ceremony test above (redundant review costs one call; unreviewed risk costs hours)? (4) is the waive rationalized by wrap-up pressure ("we're basically done, let's not bother") — if so, it's not legitimate.

**PM-only waive applies to plan-review cadence, not session-end Sonnet review.** Session-end review is EM-judgment-shaped per the diff-shape table above: EM waive authority on row-`None` trivial diffs stands, gated by the four-point test, not a PM ask.

---

## Archive-Aware Review-Trail Readers and Plan-Delivery Audit

<!-- src: plan12-022, plan12-023, plan12-024, plan12-025, plan12-026, plan12-027 -->

**The archival problem.** `/workweek-complete` Step 13 moves `state/review-trail/*.json` into `archive/review-trail/` on a weekly cadence. Any review-trail reader that globs `state/review-trail/**` only — and not `archive/review-trail/**` too — systematically **under-counts** review coverage for any shipped work older than the current week: an audit that only reads the live directory will conclude "most shipped work is unreviewed" when the reviewed work has simply rolled into `archive/`.

**Fix — every review-trail reader in the coordinator plugin globs both directories.** This is a standing requirement, not a one-off patch: `state/review-trail/**` AND `archive/review-trail/**`.

**No lister CLI exists.** The per-commit review-trail writer/lister family is retired with no
launcher of any kind, replaced by a binary review receipt. Every reader walks both trees directly:
union `state/review-trail/**` and `archive/review-trail/**`, **sorted by basename (not full path)
ascending** — this matters because week-subdirectory ordering can invert
(`week-2026-05-25/2026-05-19.json` sorts after `week-2026-05-18/2026-05-20.json` on a full-path
sort, which is chronologically backwards). Absent directories contribute nothing and are not an
error. The records found this way are complete only up to the retirement point — nothing writes a
new trail record after it, so this walk answers nothing about recent commits' review coverage.

**`coordinator:plan-delivery-audit` skill — three-oracle audit.** Codifies an empirically-proven audit pattern as a first-class skill:

1. **Plan-claim oracle** — the plan's own `Status:`/AC status fields (a claim, not evidence).
2. **Code-reality oracle** — run typed-prefix tests (grep/cited/bats/pytest) against `HEAD`.
3. **Review oracle (archive-aware)** — range-membership check: `git merge-base --is-ancestor C B && ! git merge-base --is-ancestor C A`, walked directly across `state/review-trail/**` AND `archive/review-trail/**` (no lister CLI survives — see above).

**Five delivery buckets** the audit sorts every plan into: **DELIVERED+REVIEWED** (claim=shipped, code green, review covers the range), **DELIVERED-UNREVIEWED** (claim=shipped, code green, no covering review record), **PARTIAL** (claim=shipped, code partially failing), **IN-FLIGHT** (claim not yet shipped), **ABANDONED** (claim=abandoned/superseded).

---

## Chain Review Coverage — DAG-Aware Completeness at Chain-Terminal `/workstream-complete`

<!-- src: plan30-003, plan30-004, plan30-005, plan30-006, plan30-010, plan30-012, plan30-013, plan30-014, plan30-016, plan30-017, plan30-020, plan31-001, plan31-002, plan31-004, plan31-005 -->

This generalizes the chain-end review scope rule (§ Session-End and Chain-End Review Scale above) from a single linear chain to the full handoff DAG — additional-predecessor fan-in and spinoff fan-out edges included. PM-authorized reopening of a DAG-aware review-scope idea that an earlier reshape had dropped, per the PM's completeness rule.

**The completeness rule.** At a chain-terminal `/workstream-complete`, the closing session must review-cover an ancestor handoff **iff that ancestor has no live descendant outside the chain being closed**. If the ancestor still has another live descendant elsewhere in the DAG, the closing session reviews only its own segment and skips that ancestor — the *last* child to close the ancestor's subtree is the one that reviews it. This prevents both double-review (every closing session re-reviewing shared ancestors) and silent gaps (no session ever owning a shared ancestor).

**One predicate serves both archival and review.** The completeness predicate IS the same one backing the archival guard (`handoff-has-live-children.py`, the `referencedBy`/C0 check) — "no live children remain" is simultaneously the condition under which a node is archived AND the condition under which the closing session owns its review. Archival and review-obligation co-occur structurally; there is one predicate, not two.

**Edge-kinds used in the walk: `predecessor` and `additional_predecessors` only — `forked_from` is explicitly excluded.** `forked_from` is lineage/render-only (not LoE-aggregated, per Handoff Lineage doctrine) — a spinoff's closing session reviews its own commits from the branch point forward, not the parent branch's history. Review-obligation follows the same continuation-only treatment as LoE-aggregation.

**Attribution key: `git log --follow --diff-filter=A ... | tail -1` trailer, never `authoring_session` frontmatter.** `authoring_session` is absent on ordinary session-handoffs and, when populated on spinoffs, holds free-text prose or a path — never a session-id UUID — so it cannot serve as an attribution key.

**Archived-ancestor attribution pitfall — `--follow` is load-bearing.** For a chain-intermediate ancestor (the normal state of an ancestor being reviewed at a terminal close), the handoff file has already moved into `archive/handoffs/`. Without `--follow`, `git log --diff-filter=A` on the archived path resolves to the **archival/move commit**, whose trailer names the *archiving* session — not the *authoring* session. Because the archiving session has real commits, neither the vacuous-match guard nor the null-attribution guard catches this silently-wrong attribution; it must be caught structurally, by always resolving through `--follow` back to the original add-commit. This was the single critical finding on the r4 review pass and was closed before r5 approval — verified against a real archived handoff: `--follow --diff-filter=A | tail -1` correctly resolves to the authoring commit (22-commit session) rather than the 1-commit archival move.

**Coverable-ancestor walk is a bottom-up fixpoint, not a flat ancestor set.** A node enters the closing session's exclusion set only once it is *itself* determined coverable — this is the load-bearing invariant. Using the flat `walkForward` ancestor set directly as the exclusion set is wrong: on a diamond `A→B→{C,F}` with `F` live, closing `C` naively via the flat set would wrongly mark `A` coverable (because `A` has a live descendant `F` via `B`, but the flat set doesn't propagate that). The correct computation propagates bottom-up: `B` fails (has live descendant `F`), therefore `A` fails too (its only descendant path to liveness runs through the now-failed `B`); only `C` is covered.

**Dual-consumer exit-code contract for `handoff-has-live-children.py`.** The primitive distinguishes three outcomes: exit 1 = genuinely childless, exit 0 = has live children, exit 2 = internal error/indeterminate. Archival callers treat `{0, 2}` identically as do-not-archive (conservative, unchanged). The coverage consumer diverges: exit 0 → skip (someone else owns it), exit 2 → `INDETERMINATE` → **fail the verdict** rather than silently defaulting either direction.

**Segment-derivation failure posture — never silently report COVERED.** Three cases: (1) add-commit carries a Session-Id trailer → derive the segment via `git log --all --grep` (merge-boundary-robust, vacuous-match guarded); (2) add-commit has NO Session-Id trailer → the gate MUST fail the verdict (`INDETERMINATE`), not guess; (3) the closing session's own handoff → segment is the closing session's own active Session-Id. The operative rule across all three: ambiguity fails loud, it never resolves to a silent `COVERED`.

**Known architectural residual — concurrent-both-terminal-close race.** If two sessions both close terminal branches of the same ancestor concurrently, both may observe the other's child as still-live and both skip review — the ancestor merges unreviewed. The proper fix is a review-claim-lock on the ancestor path (analogous to `cs_claim_handoff`). This is explicitly out of scope for the DAG-consumer plan and recorded in `state/debt-backlog/` at execute-plan time rather than solved inline — a known, accepted gap, not an oversight.

---
