# 06 — What We Rejected

> Choices we declined — including from external review — and the reasoning. Taste, not just enthusiasm.

This chapter exists because most projects publicly describe what they *did*. The interesting question is also what they *didn't* do, and whether they had a coherent reason for not doing it. Below are choices that were proposed (by external review, by ourselves at earlier stages, or by the seductive pull of "more is better") and declined.

The pattern across most of these: each individual proposal is plausible. Cumulatively, adopting them all would produce process theater that contradicts the system's own doctrine ("don't add structure beyond what the task requires"). The skill is in *seeing* the cumulative effect when each piece looks reasonable in isolation.

---

## Rejected: Evidence Ledger as a separate persistent artifact

**The proposal.** Every meaningful change gets a structured `Evidence Ledger` artifact: implementation summary, verification table, review findings table, unverified claims, residual risks, PM acceptance decision. Persisted to disk per-feature.

**Why we declined.** The pieces already exist in surfaces that *work*. Handoffs carry session state. PR descriptions carry release notes and ship verdicts. `docs/decisions/` carries decision records. Adding a third place that must stay in sync with the others is the kind of bookkeeping that decays fastest — and silently. A ledger that drifts from the actual git history is worse than no ledger.

**What we did instead.** Strengthened the existing surfaces. The merging-to-main skill now produces a ship verdict, a YK verdict, and a demo path inline in the PR body. The verification-before-completion gate names what evidence must exist before "done" is claimed. Evidence is distributed across the surfaces that already exist and stay current.

**For the publish repo specifically:** the [evolution doc set](README.md) is the externally-facing version of "evidence." Outside readers evaluating the system don't need a per-feature ledger — they need to see that the model has been pressure-tested and learns from failure. The evolution chapters do that.

---

## Rejected: A separate Decision Log

**The proposal.** Decisions are durable; handoffs are temporal. They should be separate artifacts: a Decision Log per feature with rationale, alternatives considered, consequences, revisit triggers.

**Why we declined.** `docs/decisions/` already exists. Wiki guides embed their own DRs. Adding a third location for "durable decisions" duplicates infrastructure and creates drift surface. The proposal is well-intentioned but doesn't notice the existing infrastructure.

**What we did instead.** Reinforced the existing pattern. Wiki guides remain the home of distilled decisions; `docs/decisions/` carries free-standing DRs; handoffs preserve session-scoped decisions and chain forward.

---

## Rejected: PM-altitude / engineer-altitude commands

**The proposal.** `/pm-altitude` and `/engineer-altitude` slash commands let the user explicitly toggle the level of detail in EM responses.

**Why we declined.** This is communication style, not a feature. The EM should already match response detail to context — long diffs and file-by-file narration when the user is debugging, terse summaries when the user is reviewing direction. Encoding this as a command implies the EM can't infer it; better to fix the inference than add commands to override it.

**What we did instead.** A doctrine line in tone-and-style: respond at the altitude the conversation is operating at. If the user asks "what changed?", a one-paragraph answer; if they ask "walk me through this implementation," a longer one. The reverse-direction signal — *"give me the engineering view"* — works as natural language; no command is needed.

The publish repo aspiration to support a fully non-technical PM (described as future work in the README's "What This Is *Not*" section) might eventually require explicit altitude controls. That's a roadmap item, not current work, and adding the command before the rest of the higher-altitude infrastructure exists would be premature.

---

## Rejected: Session metrics dashboard

**The proposal.** Track per-session metrics — work items completed, review findings, scope expansions, acceptance criteria satisfied, PM decisions requested, agents dispatched, rework loops. Visualize over time.

**Why we declined.** YAGNI without a measurement question. Metrics are valuable when you have a specific hypothesis they would test or a specific decision they would inform. We don't currently. Adding measurement infrastructure for its own sake produces dashboards that nobody reads and data that nobody asks questions of.

**What we'd revisit.** If we wanted to test a specific claim — "personas improve review precision," "tier-4 escalations drop after rationale-rule introduction," "compaction-driven loss decreases with handoff cadence" — we'd build the measurement *for that question*. Each persona experiment, the named-persona research, the handoff vs. compaction survey were all built this way. They started with a question; they ended with data; they didn't start with a dashboard.

---

## Rejected: Multi-project portfolio view

**The proposal.** A view across multiple projects — current state, blockers, recent activity — for users running coordinator-claude in multiple repos.

**Why we declined.** Speculative for an open-source plugin. The deployment shape is "one user, one project at a time, in their own Claude Code window." A portfolio view assumes shared infrastructure that doesn't exist and doesn't have a current shape worth designing for.

**What we'd revisit.** If the user base shifts to teams or to single users running 5+ projects in parallel, the question becomes real. Until then, it's a speculative addition that would carry maintenance cost.

---

## Rejected: Per-task "Task Economics" artifact

**The proposal.** Every task gets a classification artifact — complexity, blast radius, reversibility, uncertainty, product judgment required, technical judgment required, recommended workflow, rationale.

**Why we declined.** The classification is already implicit in scope-mode selection ([writing-plans](../../plugins/coordinator/skills/writing-plans/SKILL.md)). Production-patch mode encodes "low blast radius, high reversibility, minimal technical judgment, scope discipline matters." Architecture mode encodes the opposite. Writing the classification *twice* — once as the scope mode, once as the Task Economics block — duplicates the decision without adding signal.

**What we did instead.** Made scope mode a required header field with explicit rules per mode. The mode is the classification; we don't need a parallel taxonomy.

---

## Rejected: Reviewer Contract template per reviewer

**The proposal.** Each reviewer gets a meta-template — review lens, non-goals, evidence standard, false-positive control, output format. Synced across reviewers.

**Why we declined.** Reviewers are already structured artifacts. Each carries (1) a frontmatter description naming scope, (2) a domain focus section naming what's in/out, (3) a synced calibration block (already template-driven from `snippets/reviewer-calibration.md`), (4) a JSON output spec. Adding a meta-template above the existing structure adds overhead without adding constraint.

---

## Rejected: PM Architecture Brief as a separate artifact

**The proposal.** A PM-readable architecture summary — different from the engineer-facing architecture atlas — that gives PMs enough understanding to make tradeoffs.

**Why we declined.** The architecture atlas already exists and the wiki guides translate it into narrative. The proposal's actual gap is *positioning* — "the existing atlas is too dense for someone who isn't reading code daily." That's a writing problem in the existing artifact, not a need for a parallel artifact. We addressed it by sharpening the README's framing of when to read the atlas vs. when to read wiki guides; if specific atlas pages need a PM-altitude rewrite, that's a per-page edit.

---

## Rejected: Coordinator Trace artifact

**The proposal.** Every coordinator decision gets a trace — user request interpretation, scope mode selected, why not direct implementation, agents dispatched, artifacts consulted, reviews required, PM decisions requested, confidence.

**Why we declined.** YAGNI without a specific user need. If the question is "I don't understand why Claude routed this work the way it did," the answer is to ask Claude — and the answer should be available in plain English. Pre-emptively persisting a trace for every decision is overhead in service of a question nobody is currently asking.

**What we'd revisit.** If users started reporting a specific class of confusion — "I can't tell why the EM dispatched X instead of Y" — we'd build the trace for that specific question. The premature general-purpose trace would have buried that signal in noise.

---

## Rejected: Tool/Automation Risk artifact for every plugin/MCP/hook

**The proposal.** Each tool gets a risk artifact — name, access level, risks, mitigations, PM relevance.

**Why we declined.** The proposal scales with the *count* of tools, not the *risk* of tools. Most tools (Read, Grep, Glob, basic MCP verbs) carry near-zero risk and don't deserve an artifact. Real risk surfaces at use time — when a tool is doing something with credentials, network, or external write access — and that's when the question gets asked and answered. Pre-emptively artifacting low-risk tools clutters the surface and trains readers to ignore the artifact when something risky shows up.

**What we did instead.** Trust the existing review process. When a tool with substantive risk appears in a dispatch (a new MCP server with network access; a hook with write access to shared infra), the review flag goes up at that point. The general-purpose risk artifact would have caught the same cases later, with more overhead.

---

## Rejected: 11 new slash commands proposed by external review

**The proposal.** `/pm-cockpit`, `/define-acceptance`, `/set-scope-mode`, `/product-risk-review`, `/evidence-ledger`, `/demo-contract`, `/ship-recommendation`, `/decision-log`, `/pm-altitude`, `/engineer-altitude`, `/challenge`.

**Why we declined.** The external review proposed these commands while *simultaneously* warning against command explosion — and didn't notice the contradiction. Each command alone is plausible; eleven together is a different system. The point of having a small command surface is that users remember what's available; expanding the surface defeats the property.

**What we did instead.** Folded the real value into existing surfaces. Acceptance criteria → `writing-plans` skill (header field). Scope mode → `writing-plans` skill (header field). Product-risk review → YK reviewer dispatched from `merging-to-main`. Demo contract → `merging-to-main` Step 1.56. Ship recommendation → `merging-to-main` Step 1.57. Challenge → "Challenging the PM" doctrine block in `coordinator/CLAUDE.md`. Evidence ledger, decision log, PM cockpit, altitude commands → declined per their own sections above.

The cumulative effect: zero new commands, real value captured.

---

## What this list teaches

These rejections share a pattern. The proposal is plausible, the implementation is feasible, the underlying motivation is real — and adopting the proposal would be a mistake. Each rejected idea would have generated more *artifacts*, more *commands*, more *checkpoints*, more *bookkeeping*. Each piece would have been small. Cumulatively they would have produced a system that contradicts its own doctrine — process theater dressed as rigor.

The skill being practiced here is *seeing the cumulative effect when each individual piece looks reasonable*. It's a different skill from "evaluate this proposal on its merits." The system stays light because we keep declining individually-plausible proposals that would collectively make it heavy.

If this chapter ever reads as too short, that's a worry signal: it means we may have started accepting proposals we should have declined. The chapter should grow proportionally to the system, not stay frozen.
