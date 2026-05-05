# PM-Native Positioning & Doctrine Plan

**Date:** 2026-05-05
**Status:** Drafted, awaiting PM review
**Source:** `coordinator_claude_deep_recommendations.md` (external review, 2026-05-05) — triaged with skepticism, not adopted wholesale.

## Premise

External review proposed 30 recommendations for the coordinator-claude **publish repo**. The strongest insight is positional: this project is more accurately described as a *PM-native engineering-management operating system* than as "a Claude Code productivity framework." That framing already lives in our README in seed form but isn't fully operationalized.

The weakest parts of the external review:

- **Misframes the competitive set.** Lists Claude Code itself as a peer to differentiate against. We are a plugin *for* Claude Code; the framing should be "what does this plugin add on top of vanilla Claude Code," not "how do we beat Claude Code."
- **Artifact reflex.** Proposes 11+ new artifact types (Acceptance Contract, Evidence Ledger, Demo Contract, Ship Recommendation, Decision Log, Confidence Budget, Tool Risk, PM Architecture Brief, Coordinator Trace, DoR, DoD). Each is plausible alone; cumulatively this is process theater that contradicts our own doctrine ("don't add structure beyond what the task requires"). Several duplicate things we already have (`docs/decisions/`, handoffs, lessons, release notes).
- **Command explosion.** Proposes 11 new slash commands while warning against command explosion. We resist.
- **Misses asymmetry of public vs. private.** "Evidence ledger" maps to two different things: in our private working repo, the git tree + plans + handoffs *are* the evidence. In the publish repo, "evidence" means **public proof points** — demonstrations that the model works for outside readers evaluating whether to adopt it. Treat these as separate problems.

## What we adopt, in priority order

### Phase 0 — Positioning sharpening (1 session, today-eligible)

The single highest-leverage change. Pure prose; no machinery.

0.1. **README rewrite around PM-native thesis.** Reframe lede from "runs your projects like a real dev team" to something closer to *"a PM-native operating layer for AI engineering work — turn product intent into scoped plans, delegated implementation, and ship/no-ship decisions, without becoming the engineer."* Preserve all existing content; reorganize around the thesis. Keep the routine narrative (session start → planning → building → reviewing → handoff → wrap-up) since that's the strongest part of the current README.

0.2. **Add a "What this is *not*" section** to the README to head off miscategorization (we are not another agent framework, not a PRD-to-code pipeline, not an autonomous coding agent — we are a decision-architecture plugin layered on top of Claude Code).

0.3. **Reorganize the command tables around flows, not inventory.** Five flows: build a feature, fix a bug, resume work, autonomous sprint, architecture change. Commands appear inside flows. The existing exhaustive table moves to a collapsed appendix.

**Out of scope for Phase 0:** new artifacts, new commands, new doctrine. Just words.

### Phase 1 — Evolution-history doc set (1–2 sessions)

This is the publish-repo answer to "evidence ledger." External readers evaluating whether to adopt this need to see *that the model has been pressure-tested and evolved from real failures*, not just that it's well-designed in the abstract. We already have most of the raw material in `docs/research/`; what's missing is curated narrative.

1.1. **`docs/evolution/README.md`** — index over the evolution history. One-paragraph framing per chapter.

1.2. **`docs/evolution/01-origin.md`** — what problem this started solving, what the first version looked like, what failed early.

1.3. **`docs/evolution/02-handoffs-over-compaction.md`** — pulls from `2026-03-21-handoff-artifacts-vs-compaction.md`. Frames the handoff doctrine as evolved from observed compaction loss.

1.4. **`docs/evolution/03-personas-as-ergonomics.md`** — pulls from `2026-03-26-persona-experiment-results.md`. The honest version: detailed personas didn't improve recall and increased false positives in some conditions. Calibration block + AUTO-FIX/ASK is what actually moves the needle. This chapter is a *credibility-building* document precisely because it documents a negative result we ran on ourselves.

1.5. **`docs/evolution/04-investigation-funnel.md`** — tiered context loading, project-RAG step 1.5, why we built it, what we learned about Sonnet scout overuse.

1.6. **`docs/evolution/05-failure-modes.md`** — the failure-mode taxonomy from external review #21 (false completion, silent scope expansion, test theater, review laundering, etc.). This one we adopt because it generalizes our scattered "TEXT ONLY hallucination," "Edit atomic-write crash," "scout disk-first verification" lessons into a public-facing reference. Each failure mode: detection signals, prevention, recovery.

1.7. **`docs/evolution/06-what-we-rejected.md`** — counter-examples. Things we tried that didn't work, things external reviewers proposed that we declined and why. Includes this plan's "Skip explicitly" list. Demonstrates the project has taste, not just enthusiasm.

**Why this matters:** the publish repo's competitive moat isn't features — peers will replicate features. It's *demonstrated evolutionary discipline*. An evolution doc set is the most honest possible "evidence ledger" for a public artifact.

### Phase 2 — Targeted doctrine additions (1 session)

These are real changes to plugin doctrine, not just docs. All fold into existing surfaces — no new commands, no new persistent artifact types.

2.1. **Challenge-the-PM doctrine line.** Sharpen `plugins/coordinator/CLAUDE.md` and the project-template `CLAUDE.md` with explicit pushback triggers (request doesn't serve stated objective; change is larger than PM realizes; request hides a product decision; cheaper experiment available; scope expanding mid-stream; acceptance criteria missing or unverifiable; PM asking to ship despite insufficient evidence).

2.2. **PM escalation trigger list.** Doctrine block enumerating ask-vs-don't-ask cases. Lives next to the existing First Officer Doctrine section. ~30 lines.

2.3. **Scope modes as doctrine, not commands.** Five modes: prototype, production-patch, feature, architecture, spike. Each with rules and an "evidence bar." Cited from `plugins/coordinator/skills/writing-plans/`. No `/set-scope-mode` command — the mode is a header field in the plan, not a session state.

2.4. **Acceptance-criteria section in plan template.** Add to `plugins/coordinator/skills/writing-plans/`. Plans already exist; adding "Acceptance criteria" + "Non-goals" sections is the cheapest path. Reviewers check against them.

2.5. **Definition of Ready / Definition of Done as checklists folded into existing skills**, not new gate skills. DoR → `writing-plans`. DoD → `verification-before-completion` (already exists). One markdown checklist each.

### Phase 3 — Product-risk reviewer (1–2 sessions)

3.1. **New persona: product-risk reviewer.** This is genuinely additive — Patrik (staff eng), Sid (UE), Camelia (data sci), Palí (front-end), Fru (UX) cover code/UE/data/FE/UX, but none own *"does this solve the user problem and is it safe to ship to a real user?"* That's a real gap. Reviewer answers: fit-to-intent, UX clarity for non-trivial behavior changes, edge cases with product impact, support burden, trust/safety/privacy implications, scope discipline (over/under/drift), launch readiness verdict.

3.2. **Integrate into existing review pipeline.** Runs after technical reviewer when work is user-visible. Routed via `/review-dispatch`. Carries the synced calibration block like other reviewers.

3.3. **Publish-repo dogfooding note.** First several invocations on real work get captured (lightly) into the evolution doc set as a calibration record.

### Phase 4 — Ship-recommendation polish (light, opportunistic)

4.1. **`/merge-to-main` adds an explicit ship verdict** — ship / ship-behind-flag / hold / split — with one-line rationale. Already partially present in release notes; formalize the verdict slot. No new command.

4.2. **PR description template addition: "Demo path" section.** What this demonstrates, setup, steps, expected behavior, known limitations. Lives in the PR template, not as a separate artifact file. For user-visible work only.

## Explicitly rejected (with reasons)

These appear in the external review and we are *not* adopting:

- **Evidence Ledger as a separate persistent artifact.** Handoffs + PR descriptions + release notes already cover this for working sessions. For the publish repo, the evolution doc set (Phase 1) is the better answer.
- **Decision Log separate from handoffs.** We have `docs/decisions/`. Don't duplicate.
- **PM-altitude / engineer-altitude commands.** Communication style, not a feature. At most a one-line doctrine note. No `/pm-altitude` command.
- **Coordinator Trace artifact.** YAGNI. Revisit if users actually report inability to understand why Claude routed a task.
- **Tool/Automation Risk artifact** for every plugin/MCP/hook. Speculative bookkeeping. Real tool risk surfaces during use; surface then.
- **Session Metrics dashboard.** YAGNI without a measurement question.
- **Multi-project portfolio view.** Speculative. Out of scope for an open-source plugin.
- **Reviewer Contract template per reviewer.** Reviewers are already structured artifacts. Adding a meta-template per reviewer is overhead.
- **Task Economics artifact per task.** The classification (complexity, blast radius, reversibility, etc.) is already implicit in scope-mode selection. Don't write it twice.
- **Worktree Parallel Work Plan template.** Already covered by `coordinator:using-git-worktrees` skill.
- **Confidence Budget artifact.** Calibration block already covers this for reviewers; for the EM, "say what you know vs. infer" is a doctrine line, not a template.
- **PM Architecture Brief as a separate doc.** The architecture atlas already exists. Reframing it for "PM altitude" is a Phase 0 README concern, not a new artifact.
- **All 11 proposed slash commands.** Command explosion. Phase 2 folds the real value into existing skills/templates.

## Sequencing & approval gates

| Phase | Effort | Requires PM approval before? | Notes |
|-------|--------|------------------------------|-------|
| 0     | 1 session | No — pure positioning, EM remit | Land first; everything else benefits from the sharpened thesis |
| 1     | 1–2 sessions | Yes (chapter outline before drafting) | Highest narrative-risk phase; outline-then-draft |
| 2     | 1 session | No — doctrine extension within existing patterns | Lands after Phase 0 |
| 3     | 1–2 sessions | Yes (persona scope before authoring) | New persona = real surface area; PM should sign off on remit |
| 4     | <1 session | No — opportunistic during a real merge | No need to schedule |

## Open questions for PM

1. **Phase 1 voice.** Evolution docs can read as "war stories" (informal, character-driven) or as "engineering changelog" (clinical, dispassionate). Recommend war-stories voice — matches the project's existing tone in research artifacts and is more memorable. Confirm?
2. **Product-risk reviewer naming.** Existing personas have names (Patrik, Sid, Camelia, Palí, Fru, Zolí). Do we name this one? If yes, what role/personality fits — a Director of Product? A senior PM? Recommend a senior PM character so the dynamic is "PM-reviewer cross-checks PM-user," which is genuinely useful.
3. **Phase 0 scope.** Tempting to also rewrite `docs/architecture.md` and `docs/getting-started.md` while we're in there. Recommend deferring — README change is the keystone; downstream doc rewrites are easier once it lands.

## What we're not solving here

Plenty of the external review's structural critique is fair but downstream of positioning. Once Phase 0 lands and the thesis is sharp, decisions like "should the evidence ledger be a thing" answer themselves. Get the framing right; let the artifacts follow.
