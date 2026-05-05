# 01 — Origin

> What problem this started solving, and what the first version got wrong.

## The problem nobody had named yet

Late 2025, the question wasn't "can an AI write code?" — that question had been answered. The question was "can a person who isn't a working software engineer *manage* the AI doing the work?"

The standard answer at the time was *no* — or rather, it was assumed the answer was *yes for trivial things, no for anything real*. The sales pitch from coding-agent products was "the AI codes for you." The implicit assumption was that the human user was either (a) a developer using AI to go faster, or (b) a non-developer building toy projects.

Neither category fit a real product manager working on a real codebase. A PM:

- can read code and recognize when something looks wrong, but doesn't write it day-to-day
- owns scope and ship decisions, not implementation tradeoffs
- needs to evaluate work, not produce it
- knows that "the AI says it's done" is not a status report

Vanilla Claude Code was already capable of impressive autonomous work. What it didn't have was a doctrine for when to ask, when to act, and how to make engineering state legible to a non-engineer who still cared about quality. That gap was the project's reason for existing.

## What the first version looked like

The earliest version was just a CLAUDE.md file with a few rules. Plan before you act. Don't merge to main without review. Capture lessons. Six commands or so.

It worked OK. It also failed in three predictable ways:

**Failure 1: The model couldn't tell when to stop and ask.** It would interpret ambiguous requests as implementation requests and invent product decisions. Asking "should we add a filter to the dashboard?" would produce a filter — but the filter would have hidden assumptions about permissions, visibility, and defaults that the user hadn't decided. By the time anyone noticed, the implementation had committed to the assumptions.

**Failure 2: Long sessions degraded silently.** The model would lose track of what it was doing around the 50-60% context-fill mark. When this happened, it didn't announce itself — the model just got worse at the thing it was already doing. Plans became less coherent. Earlier decisions got relitigated. Test names started disagreeing with test bodies.

**Failure 3: There was no structural reason to trust completion claims.** The model would say "done." Sometimes done meant *the code compiles*. Sometimes it meant *the agent thinks the code compiles*. Sometimes it meant *I didn't actually run the tests but I'm confident*. There was no protocol to make the gap between belief and verified evidence visible.

## The shape that emerged from those failures

Each failure had a corresponding response that became part of the system:

**For Failure 1 — when to ask:** the EM-PM authority split. Claude is the engineering manager; the user is the product manager. Some decisions are EM discretion, some are PM authority. The list got progressively more explicit over time, eventually landing in the [Challenging the PM](../../plugins/coordinator/CLAUDE.md) and [PM Escalation Triggers](../../plugins/coordinator/CLAUDE.md) doctrine blocks.

**For Failure 2 — context degradation:** the handoff system. Instead of trusting compaction to preserve session state, the system now generates structured handoffs *before* context pressure forces summarization. See [chapter 2](02-handoffs-over-compaction.md).

**For Failure 3 — verified completion:** the verification-before-completion gate, the calibration block on every reviewer, the docs-checker pre-flight, and the ship verdict at merge time. Each layer is a different kind of evidence pressure on the question "is this actually done?"

## What hasn't changed

The thesis hasn't moved: a product manager can manage AI engineering work the way they'd manage a real engineering team — define intent, review plans, control scope, make product decisions, inspect evidence, and decide whether to ship. Implementation has changed; thesis hasn't.

What also hasn't changed: this is a Claude Code plugin, not an alternative to Claude Code. The Claude Code primitives (subagents, hooks, plugins, skills, MCP, plan mode) are load-bearing. This system adds doctrine *on top of* them. Anyone who tries to relitigate that split — make this an alternative orchestration framework, an autonomous coding agent, a PRD pipeline — is rebuilding what already exists in the host runtime, badly.

## The lesson the system was trying to teach itself

Software engineering for humans optimizes for human cognitive limits, high coordination cost, and long feedback loops. Those constraints don't map cleanly to AI execution. Refactors take hours, not sprints. Reviews cost minutes, not meetings. Capacity for first-pass correctness is unusual.

Inheriting human-effort intuitions about scope and effort produces undershoot. Doing a thing thoroughly the first time is not over-engineering when the cycles are cheap and the alternative is shipping work that has to be revisited. That recalibration is the most distinctive thing in the system's operating doctrine, and it took the longest to land.
