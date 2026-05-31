---
title: Prior-Art Check — fan-out-skill-to-methodology-demotion
created: 2026-05-30
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-05-30-fan-out-skill-to-methodology-demotion.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-fan-out-skill-to-methodology-demotion.md`
**Verdict:** WARN
**Claims checked:** 15
**Conflicts:** 2 | **Compatible-but-relevant:** 5 | **Silent:** 8
**Corpora consulted:** project-wikis (121 files indexed) | global-wikis (same corpus — working directory IS ~/.claude) | lessons.md (not present at coordinator plugin path; global queue consulted) | improvement-queue (~/.claude/tasks/coordinator-improvement-queue.md)

---

### Conflicts (plan contradicts prior art)

- **Claim #6 — Token-economics escape hatch criterion for execute-plan self-execute:** The plan proposes rewriting the escape-hatch criterion from "EM-judgment-heavy / conversation-context-matters" to **token-economics** ("Sonnet ≈ ¼ the tokens of an Opus EM, and faster; self-execute only when articulably cheaper here").
  - **Plan asserts:** "criterion becomes **token-economics** — default dispatch (Sonnet ≈¼ Opus tokens + faster); self-execute only when articulably cheaper here; note that self-execute is the one path that skips the suitability gate, so the bar is high."
  - **Prior art (`docs/wiki/agent-dispatch-economics.md`:53–59 § When to EM-Inline):** "**Fix locus is known and ≤3 files.** No exploration needed; no value in delegation. / **Estimated EM wall-clock is <60s on a >30k-file repo.** Worktree creation alone exceeds the work duration. / **Fix is mechanical** — rename, version bump, single-line tweak, import addition. Judgment value is zero; overhead is not. / **Sub-agent would just re-read what the EM has already loaded.** If the relevant context is already in the EM's window, dispatch adds a re-read cycle for no gain. / **Fix is in a file the EM is already editing.** Mid-edit dispatch mid-session creates a concurrent-edit hazard on the same file."
  - **Prior art (`docs/wiki/agent-dispatch-economics.md`:66, current `skills/execute-plan/SKILL.md`:66):** "When direct in-session execution is the right shape (small plan, EM-judgment-heavy, dispatched-executor overhead exceeds typing) the gate-graph still applies — it sequences Phase 3's tasks even when one executor (the EM) runs them all."
  - **Why this is a conflict:** The existing `§ When to EM-Inline` doctrine lists five concrete criteria (file count, wall-clock, mechanical nature, context loaded, concurrent-edit hazard) that are not the same as "token-economics." The plan's rewrite collapses a multi-criterion checklist into a single economic proxy that is narrower and harder to apply. Specifically, the "context already loaded" and "concurrent-edit hazard" criteria are not captured by token-economics alone. The plan's criterion is partially compatible (wall-clock is the dominant axis in both) but the compression loses load-bearing distinctions.
  - **Candidate directions for EM:**
    - `update-plan` — fold the existing five-criteria vocabulary into the plan's Chunk 2 escape-hatch rewrite instead of replacing it with the token-economics proxy
    - `update-prior-art` — if the five-criteria list is intended to collapse into "articulably cheaper," amend the wiki to reflect that
    - `both` — token-economics is the right framing at the top; the five criteria survive as the operational checklist that grounds "articulably cheaper here"
  - **Lean:** `both` looks most likely — the plan's intent (raise the bar for self-execute, make the criterion legible) is sound; the existing five criteria give it empirical grounding the token-economics proxy alone lacks. Adding "which grounds out to these five cases" preserves both.
  - **Disposition:** applied — the Staff Engineer F2 extended AC5 to assert the five-criterion checklist survives in `agent-dispatch-economics.md` after the (C) rewrite; Chunk 2 already carries the "Do NOT delete" directive; both surfaces now tested.

---

- **Claim #5 — Removing the ad-hoc entry point (no standalone command for ≥2 tasks, no plan doc):** The plan removes the standalone `/fan-out` command and states that ad-hoc parallel work "folds under execution — the EM follows the wiki methodology inline when it has ≥2 independent tasks; no standalone command."
  - **Plan asserts:** "Killing the command removes that entry. **Plan default (per PM 'cited as part of execution'):** ad-hoc parallel work folds under execution — the EM follows the wiki methodology inline when it has ≥2 independent tasks; no standalone command."
  - **Prior art (`docs/plans/2026-05-27-fan-out-default-doctrine.md` § Chunk 5, the 2026-05-27 plan's rationale, explicitly recorded at Problem § Belt-and-suspenders mapping):** "**Belt** = `coordinator:fan-out` (Chunk 5) — a thin standalone skill that *calls `Agent`* (which a bin script cannot), invokes the helper to compile the wave, dispatches it, and holds the EM-serial-commit between waves. **Reachable WITHOUT a plan doc**, and called by execute-plan Phase 1.5 so the two entry points share one mechanism."
  - **Prior art (`docs/plans/2026-05-27-fan-out-default-doctrine.md` § Problem — point 1):** "It only fires on a written plan document. `/execute-plan <plan-path>` requires a plan doc. The monolith-grind failure happens in *ad-hoc* mode ("I'll just send one agent at this big thing"), which never routes through execute-plan. There is no in-the-moment fan-out verb to reach for."
  - **Why this is a conflict:** The 2026-05-27 plan specifically diagnosed the absence of an ad-hoc entry point as one of three structural causes of the monolith-grind failure, and the standalone skill was the explicit fix. The demotion plan removes this fix and replaces it with "follow the wiki methodology inline." The plan acknowledges this in § Open Decision but asserts "Surfaced for review; not a silent choice." The prior art is not just an old constraint — it is the precise causal analysis the new plan is reversing, and the reversal argument (PM: "cited as part of execution") does not directly address the structural cause the 2026-05-27 plan diagnosed. This is a genuine tension: is "follow the wiki methodology inline" sufficient when the prior plan argued the absence of an in-the-moment verb was itself the failure vector?
  - **Candidate directions for EM:**
    - `update-prior-art` — the 2026-05-27 plan's diagnosis was correct then; the PM has since resolved that ad-hoc work folds under execution, which changes the architecture; the prior art should be marked resolved
    - `update-plan` — the plan's § Open Decision should more explicitly address the 2026-05-27 causal argument (not just that the choice was surfaced, but WHY the ad-hoc-verb absence no longer causes the monolith-grind failure it once did)
    - `override-and-document` — the plan already flags this in § Open Decision; make the prior-art reversal explicit there by quoting the 2026-05-27 diagnosis and naming why it is now superseded
    - `PM-input-needed` — the PM decision is referenced ("cited as part of execution") but the specific causal argument from 2026-05-27 is not addressed
  - **Lean:** `override-and-document` with a brief strengthening of the § Open Decision section to explicitly cite why the 2026-05-27 structural-cause argument no longer applies (i.e., the vocabulary-collision problem makes the standalone command actively harmful, outweighing the ad-hoc-entry-point value). The plan has most of this; the connection to the prior plan's specific causal claim just needs a sentence.
  - **Disposition:** applied — the Staff Engineer F0 added explicit ad-hoc firing surface (Phase 1.5 + fan-out-dispatch.sh NOTE:); the Staff Engineer F1 restructured § Open Decision with palliative→root-cause lead argument, acknowledged execute-plan presupposes a plan doc, and named the accepted residual explicitly.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #2 — Deleting the skill (deregistering coordinator:fan-out):** Plan uses `git rm -r skills/fan-out/` as the deregistration mechanism.
  - **Plan covers:** "git rm -r skills/fan-out/ — deregisters `coordinator:fan-out`."
  - **Prior art (`docs/wiki/skill-budget-discipline.md` § Phase A Cleanup Actions):** The skill budget audit framework documents that zero-invocation skills are "pure description-budget load with no behavioral value" — their removal is load-bearing because "every loaded skill description is **always in context**." The plan doesn't cite this framing but the deletion is consistent with it.
  - **Subtype:** `cite`
  - **Suggested action:** The plan's § Problem and § Premise-Pass would be strengthened by noting that removing the skill also recovers description-budget tokens (the fan-out skill's `description-budget: 225` in SKILL.md header). Minor — informational only; the decision is correct either way.

---

- **Claim #3 — Ceremony survival via wiki methodology migration (Step 0.5 suitability gate must survive verbatim in intent):** Plan asserts Step 0.5 (anti-fat-chunk forcing function) is "load-bearing, must survive verbatim in intent."
  - **Plan covers:** "Step 0.5 fan-out suitability gate (the anti-fat-chunk forcing function — load-bearing, must survive verbatim in intent)"
  - **Prior art (`skills/fan-out/SKILL.md` Step 0.5 spec-backlink comment):** "<!-- spec-backlink: 2026-05-29 fan-out-suitability-gate — the EM must confirm each chunk is genuinely one coherent surface BEFORE dispatch, never yeet one executor at N deliverables. The doctrine to fan out already existed; this is the forcing function that makes it fire at dispatch time. -->" and at Step 0.5: "**This is the gate whose absence produced the 2026-05-29 "one agent authors 7 modules" failure.**"
  - **Subtype:** `cite`
  - **Suggested action:** The migration obligation in Chunk 1 correctly identifies the suitability gate as load-bearing. The plan should reference the 2026-05-29 incident in the migration note (it's what makes Step 0.5 non-optional) so the executor knows not to compress it. Currently the incident is cited in SKILL.md but the plan doesn't reference it — the executor may not read SKILL.md before migrating.

---

- **Claim #9 — Organic-ramp operational semantics migration obligation:** Plan states "the organic-ramp *operational* semantics that live in fan-out/SKILL.md Steps 1.5/2 (pilot→expand ramp, soft NOTE not HARD STOP, orchestrator-fanout counting) MUST survive into the migrated wiki methodology."
  - **Plan covers:** Correctly identified as Cross-Plan migration obligation.
  - **Prior art (`docs/wiki/dispatching-parallel-agents.md` § Concurrency Budget, lines 19–37):** The § Concurrency Budget already carries the organic-ramp doctrine in full: "Two surviving hard rules: (a) Ramp, don't pre-batch… (b) Count your own fanout… No fixed numeric cap." The wiki section already contains the canonical doctrine the plan says must survive.
  - **Subtype:** `cite`
  - **Suggested action:** The Chunk 1 executor should check whether the organic-ramp content in SKILL.md Steps 1.5/2 is *already* covered by the existing `§ Concurrency Budget` text in `dispatching-parallel-agents.md`, and migrate only operational procedure that is NOT already there (likely: the per-step "if large wave, consider pilot cohort" dispatch procedure). The plan doesn't distinguish "doctrine already in wiki" from "procedure only in skill" — the executor could double-expand or miss the distinction. Clarify in the Chunk 1 brief.

---

- **Claim #10 — The organic-ramp plan's content has "already landed" to disk:** Plan asserts the organic-ramp plan (status: draft) "content has already landed and there is no live executor."
  - **Plan covers:** "Since its content has already landed and there is no live executor, this plan **supersedes the `fan-out/SKILL.md` file**."
  - **Prior art (`docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md` frontmatter):** `status: draft` — the plan itself carries `status: draft`, and the plan body says "SHIPPED 2026-05-30 (commit 39927cbb)" for the memory-headroom probe but the skill updates (C3) and test updates (C4) show `Status: pending realization` in the AC table for most items. The `dispatching-parallel-agents.md` § Concurrency Budget content is indeed updated (confirmed by reading it). However, C3 (`skills/fan-out/SKILL.md`) shows step 1.5 and step 2 rewrites that the plan mandates — these are what the demotion plan says "already landed."
  - **Subtype:** `cite`
  - **Suggested action:** The Chunk 1 executor should verify by reading `skills/fan-out/SKILL.md` current Steps 1.5 and 2 against the organic-ramp plan's pinned contract (table in § The pinned cap-breach contract) BEFORE migrating — to confirm what is actually there vs. what the demotion plan assumes is there. The demotion plan's premise ("content already landed") needs a targeted read-verification before the migration executor acts on it. If Steps 1.5/2 have NOT landed (organic-ramp C3 unexecuted), the migration obligation changes.

---

- **Claim #15 — EM-inline execution preferred for this ~7-file doctrine work:** Plan applies its own token-economics criterion to decide EM-inline is plausibly cheaper than 3 dispatched executors.
  - **Plan covers:** "this is ~7 files of doctrine wording where cross-file *voice consistency* of the methodology framing matters more than mechanical throughput…"
  - **Prior art (`docs/wiki/agent-dispatch-economics.md` § When to EM-Inline):** "Sub-agent would just re-read what the EM has already loaded. If the relevant context is already in the EM's window, dispatch adds a re-read cycle for no gain." — this criterion directly applies and supports the plan's self-assessment.
  - **Prior art (`docs/wiki/ceremony-calibration.md` § Queue-clear classification):** "Multi-file change touching a shared seam → plan-shaped; the seam is the ceremony trigger." — this is a multi-file change touching a shared seam (methodology anchor); the plan-pipeline was correctly invoked, so the ceremony level is appropriate.
  - **Subtype:** `cite`
  - **Suggested action:** The plan's self-application of the (C) criterion is well-grounded against existing prior art. Informational only — no action needed.

---

### Silent areas (no prior art found)

- Claim #1 — Vocabulary collision between `coordinator:fan-out` and native Claude Code "fan out" concept: no prior art in any corpus about command-name collision with Claude Code native vocabulary.
- Claim #7 — Stance vs. altitude reframing of the execute/fan-out seam: no prior art in any corpus.
- Claim #8 — bin/fan-out-dispatch.sh behavior unchanged by this plan: no prior art in any corpus specifically governing when a bin helper is preserved vs. modified during a skill demotion.
- Claim #11 — Organic-ramp plan's `status: draft` should be flipped (surfaced to PM, OOS): no prior art on stale-status cleanup for plans with already-shipped content.
- Claim #12 — Negative-search claim ("no lessons.md entry argues for standalone fan-out independent of collision rationale"): searched coordinator-improvement-queue.md; no queue entry advocates for the standalone skill. The plan's claim is consistent with the corpus.
- Claim #13 — docs/plans/ files exempted from the no-live-citation AC: no prior art specifically on the scope of this exemption; the 2026-05-27 plan's two `.prior-art-check.md` sidecars not found at the glob path (no prior-art-check sidecars exist at that location), which is consistent with the plan noting "the two `.prior-art-check.md` sidecars reference it descriptively only."
- Claim #14 — Chunk 1 keystone / Chunks 2-3 concurrent authoring with pinned anchor: no prior art conflict; consistent with `dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy (Author vs. verify) which the plan cites.
- Claim #4 — Inline dispatch loop in execute-plan Phase 1.5 (replacing the `coordinator:fan-out` invocation block): the replacement approach is silent in the corpus except for the prior-art conflict surfaced under Claim #5.

---

### Verdict logic

**WARN** — two conflicts surfaced:

1. **Conflict #6 (token-economics escape hatch):** The plan's proposed rewrite of the escape-hatch criterion compresses the existing five-criteria `§ When to EM-Inline` vocabulary into a token-economics proxy. This is substantive but reconcilable — the `both` direction (token-economics as the top-line framing, five criteria as the operational checklist) preserves both surfaces. EM/reviewer call.

2. **Conflict #5 (ad-hoc entry point removal):** The plan removes the specifically-diagnosed structural cause that the 2026-05-27 plan addressed (absence of an in-the-moment verb for ad-hoc work). The reversal has PM backing ("cited as part of execution") but the plan's § Open Decision does not explicitly address the 2026-05-27 causal argument. The prior art is not stale — it is the direct institutional memory for this exact architectural choice. The `override-and-document` direction is the likely landing, but the EM should confirm the PM authorization explicitly covers the structural-cause reasoning, not just the preference for "execution" as the verb.

Neither conflict is load-bearing doctrine (no HARD RULE violated); neither rises to BLOCKED-SURFACE-TO-PM. WARN is the correct verdict. The EM should fold both conflict resolutions before Opus reviewer dispatch.

---

**Cost estimate:** ~9K tokens (15 claims × ~5 corpus reads average; 3 full file reads, 8 partial reads)
