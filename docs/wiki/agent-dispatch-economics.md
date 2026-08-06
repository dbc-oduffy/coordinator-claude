---
title: Agent Dispatch Economics
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Agent Dispatch Economics

> When to dispatch a sub-agent vs. do work EM-inline. Default: dispatch for any non-trivial job; fan out when the job decomposes. EM-inline is the carve-out, not the default.


## Overview

**Wall-clock is the primary objective. Token cost and dispatch bootstrap overhead are subordinate.**

Sub-agent dispatch has fixed costs: prompt-bootstrap tokens and context-loading time for the sub-agent's system prompt re-read. These costs are real and are worth accounting for on sub-60s mechanical fixes where bootstrap alone would exceed the work duration. Outside that narrow carve-out, the default is to dispatch — and when the work decomposes into independent chunks, to fan out across N agents.

Per-agent git worktree isolation is structurally banned fleet-wide and blocked at dispatch (see § Per-Agent Worktrees Are Blocked at Dispatch, Not Mitigated below) — it degrades badly on Windows (the primary machine and audience) and doesn't scale to a concurrent agentic fleet. The data point that first surfaced worktree-creation cost as a dispatch tax — a large repo where each dispatch added tens of seconds of worktree-creation overhead before the sub-agent's first tool call, turning a 20-second EM-typed rename into a 90-second round-trip when dispatched — is why the ban exists, not a live cost the table below still needs to weigh: dispatch on this repo runs against the shared tree, and worktree creation is no longer part of the round-trip at all. The lesson that data point taught still holds in weakened form: **sub-60s mechanical fixes on known loci warrant EM-inline**, driven now by bootstrap-and-context-load cost rather than worktree creation.

Empirical antecedent: *"Many agents often beat one — don't overload a single Sonnet when the work decomposes [universal]."* A cross-repo slow-test sweep dispatched as one agent grinding ~10 independent chunks crashed at 35 min / 43 tool uses; only 1 of 10 deliverables landed. The correct shape was N parallel agents at the natural decomposition unit. Independent chunks have zero cross-chunk data dependency; coordination cost is zero; wall-clock is N× faster; failure blast-radius is contained per-chunk; the PM gets partial results immediately as each agent lands.

<!-- negative-spec: The co-equal cost framing ("token + worktree overhead as co-equal with wall-clock") that appeared in the 2026-05-18 draft of this file was incorrect as a general rule. It is valid only for sub-60s mechanical fixes on known loci. The § Overview previously read "This is a real economic call, not a default-to-delegate rule" — that framing caused over-application as cover for under-dispatching genuinely large jobs. Reanchored 2026-05-27. -->

**Anti-monolith HARD RULE** (see `coordinator/snippets/em-operating-doctrine.md` § How to Dispatch, "Fan-out is the default dispatch shape"): a large job is fanned out, or chunked into a sequence of fresh per-chunk agents — never one agent grinding chunk after chunk. To fan out, run your fleet's fan-out dispatch helper (overlap pass + scoped-prompt compiler), then follow the fan-out methodology (`dispatching-parallel-agents.md` § Executing a Fan-Out Wave) to dispatch the compiled wave via `Agent` (which a bin script cannot call directly) and hold the EM-serial commit.

## The Economics

Wall-clock cost is the primary axis. Token and dispatch bootstrap overhead are subordinate — they matter only when bootstrap alone would dominate the work being done. Per-agent worktree creation is not part of this axis at all on this fleet: worktree isolation is blocked at dispatch (§ Per-Agent Worktrees Are Blocked at Dispatch, Not Mitigated), so every dispatch runs against the shared tree. The table below retains a worktree-creation column for the repo sizes where the ban does not apply — an EM-authorized isolated dispatch under the PM-permission override — but the default row every EM reads is the shared-tree one.

| Repo size | Worktree creation (override-only) | Dispatch fixed cost (shared tree, default) | EM-inline cost |
|---|---|---|---|
| <5k files | <1s | ~3s overhead | typing + read tokens |
| 10k–30k files | 5–15s | 8–20s overhead | typing + read tokens |
| 30k–60k files | 30–60s | 35–65s overhead | typing + read tokens |
| 60k+ files | 60s+ | 65s+ overhead | typing + read tokens |

**Reading the table correctly:** the dispatch-fixed-cost column is the one that governs ordinary dispatch decisions — it reflects prompt-bootstrap and context-loading, not worktree creation, because worktree creation doesn't happen on the default path. A fix the EM can type in 20s is legitimately EM-inline — dispatching it doubles wall-clock for no gain. A multi-file refactor that takes an executor 5 minutes is still a dispatch regardless of bootstrap cost: 5 min + tens of seconds of overhead vs. EM-inline serial is not a close call, and the EM keeps its context window for other work in parallel. The worktree-creation column matters only inside the override path, and even there it is the same brake it always was — a reason to keep isolated dispatch rare, not a reason to lean on it.

**When the job decomposes:** N parallel executors at the natural chunk boundary beat one executor grinding serially on wall-clock *every time*, for any N ≥ 2 with independent chunks. Dispatch bootstrap overhead is paid once per chunk, not once per job; the wall-clock gain from parallelism dwarfs the overhead for any non-trivial chunk size. Because the shared tree carries no per-chunk worktree cost, the coordination burden that overhead used to absorb now falls entirely on keeping each executor's scope disjoint from its siblings' — see § Per-Agent Worktrees Are Blocked at Dispatch, Not Mitigated.

**File count is not effort.** A probe that returns a large inventory of affected documents or files does not, by itself, raise the size estimate. If the scopes are disjoint — no item reads or writes what another item touches — the job is one dispatch per document in a single parallel wave, mechanical fan-out, not N units of sequential effort. The failure mode is specific: a substrate probe naturally returns a count, and a count is easy to mistake for an effort measure. Before letting a count move a size classification, ask "do these scopes interact?" — if they don't, the count changes the wave's width, not the estimate, and the irreducible engineering content (the guard, the seam, the mechanism shared across the documents) is what actually sets the size.

### Exploration Tax — The Hidden Per-Dispatch Fixed Cost

The dispatch bootstrap overhead in the table above is not the only fixed cost a dispatcher pays. On chunks that touch **unfamiliar code**, every fresh executor also pays an **exploration tax** — the time spent reading, understanding, and mentally modelling the substrate before writing a single line. Unlike bootstrap, this tax scales with the read-set complexity, not the repo size.

**The tax is per-dispatch.** When a plan's chunks share an expensive, unfamiliar read-surface, splitting the work smaller multiplies the tax (N × the tax per chunk), inverting the small-remit-and-many rule rather than benefiting from it — executors spend their entire budgets re-exploring and never write.

**The § When to EM-Inline checklist's first criterion** — "fix locus is known and ≤3 files — no exploration needed" — implicitly recognises this: if exploration is required, the EM-inline shape is already disqualified. The Shared-Expensive-Substrate (SES) gate extends this logic in the *opposite* direction: when exploration is both shared across chunks and genuinely expensive, the correct shape is to **enrich-once before dispatch** — pay the exploration tax once in a single enricher pass, hand per-chunk executors pinned specs, and let them *only type* (near-zero exploration tax per executor). The SES predicate definition and firing conditions are canonical in `dispatching-parallel-agents.md § Shared-Expensive-Substrate`; cross-reference it, do not redefine the predicate here.

**Brief-authoring implication:** even when SES does not fire, a "go read" dispatch brief — one that instructs executors to *"read plan §X and all the source files"* rather than pinning the spec inline — is an instruction to spend budget exploring. The discipline is: **pin the spec**, never go-read. → `dispatching-parallel-agents.md § Pin the Spec, Never Go-Read` for the brief-authoring rule that makes enrich-once products consumable by per-chunk executors (co-pillar: `delegate-execution.md § Briefing Concreteness`).


## When to Dispatch

- **Work is independently verifiable.** A scout returns a structured deliverable the EM reads; concurrency is real leverage.
- **Work spans contexts the EM hasn't loaded.** Sub-agent loads a directory's worth of code the EM doesn't need to hold in its own context window.
- **Work is parallel-shaped.** N independent edits to N different files; sequential EM would gate each behind the last.
- **Work needs persona judgment.** the Staff Engineer / the Game Dev Reviewer / the Data Science Reviewer / the UX Reviewer bring framing, calibration, and review lens the EM doesn't have.
- **Work would blow EM context.** Reading 50k tokens of code to make a small edit is sub-agent shape — the sub-agent reads, acts, and reports a summary.
- **Work is long-running and the EM needs to continue.** Background dispatch with disk-based signaling lets the EM make progress while the sub-agent works.
- **Work decomposes into ≥2 independent chunks.** Fan out — don't hand a multi-chunk job to one agent. See anti-monolith HARD RULE above.
- **Work is broad fact-finding.** A "let's find out the context" sweep across files the EM hasn't loaded returns a conclusion, not file dumps — see § Fact-Finding below.

## When to EM-Inline

**All of the following criteria must hold — this is a conjunctive checklist, not a menu.** Satisfying one or two (e.g. estimated wall-clock alone) is insufficient to qualify for the inline carve-out; every criterion below must be true simultaneously before EM-inline is the correct shape.

- **Fix locus is known and ≤3 files.** No exploration needed; no value in delegation.
- **Estimated EM wall-clock is <60s on a >30k-file repo.** Dispatch bootstrap and context-load alone can exceed the work duration at this size.
- **Fix is mechanical** — rename, version bump, single-line tweak, import addition. Judgment value is zero; overhead is not.
- **Sub-agent would just re-read what the EM has already loaded.** If the relevant context is already in the EM's window, dispatch adds a re-read cycle for no gain.
- **Fix is in a file the EM is already editing.** Mid-edit dispatch mid-session creates a concurrent-edit hazard on the same file.

### Wave-Map `inline (EM)` — Not a Binding Re-Decision

A plan's wave-map `inline (EM)` row is **not a binding re-decision** — it is the plan-author's at-write-time estimate. At dispatch time the EM re-decides against this checklist; acknowledging a conflict (e.g. an improvement-queue entry favouring dispatch) and self-executing anyway is performative, not a waiver. → `dispatching-parallel-agents.md` § Inline-EM Dispatch Classification Is EM-at-Plan-Write-Time Judgment — Re-Decide at Dispatch Time is the canonical statement of this rule; cross-cite it, do not author a divergent version here.

## Fact-Finding — Broad Sweeps Default to a Sonnet Agent

Fact-finding is not one class of work, and the economics split cleanly on breadth:

- **Broad fact-finding → dispatch (default).** "Hmm, let's find out the context," multi-file sweeps, unknown-location hunts, "does X exist anywhere," "how is Y wired." Send it to an unnamed `Explore` agent — **not** `general-purpose`, which is not interchangeable with it (§ Agent Type Is the Largest Per-Dispatch Cost); the EM reads back the **conclusion**, never the file dumps. The primary reason is **context hygiene, not token cost**: the EM's context window is the scarce resource, and an Opus EM reading a sweep inline spends judgment-context on grep output it will never need again. Sonnet is also cheaper per token and, being parallel, faster on breadth. This is the same instinct as *"Your delegates have capabilities you cannot see"* and the fan-out-is-default rule — delegate down, keep the EM's window for judgment.
- **Single targeted lookup → EM-inline.** A known file / symbol / value the EM can Read or Grep in one call stays inline. The spawn round-trip (prompt-bootstrap, sub-agent context load, return-synthesis) would cost more tokens *and* more wall-clock than the read itself. Delegating a one-liner is overhead theater — the exact anti-pattern the § When-to-EM-Inline checklist guards.

**The reflex before reading files:** *"single known target, or a sweep?"* Sweep → delegate. This is directional, not absolute — it does not license spawning an agent for every `grep`, only for the "let's find out" ones.

## Agent Type Is the Largest Per-Dispatch Cost


The sections above cost dispatch in wall-clock, which remains the primary axis. This section is about the other axis, and it settles a question this wiki previously got wrong by treating `Explore` and `general-purpose` as interchangeable Sonnet scouts.

**`Explore` and `Plan` skip the always-on doctrine corpus. Nothing else does.** They receive neither repo nor global `CLAUDE.md`, neither the memory index nor the git-status block. The harness documents that there is no frontmatter field and no per-agent setting to change which agents skip them — so this is a choice made at dispatch, once, and never afterwards.

Measured first-request input, before the lazy roster/MCP delta that every tier pays equally on its first tool call:

| Dispatch | Tokens at boot |
|---|---:|
| `Explore`, unnamed | **17,566** |
| `general-purpose`, unnamed | 45,258–46,336 |
| `coordinator:executor`, unnamed | 54,982 |

Two consequences that invert the standing intuition:

1. **A coordinator persona agent is the *most* expensive tier, not the leanest.** It carries the full doctrine corpus *plus* its own long agent body. Reaching for `coordinator:executor` because it is "purpose-built" costs ~9.6k tokens more than `general-purpose` for the privilege.
2. **At wave scale the agent-type choice dominates anything you can recover by shortening prompts.** Twelve `general-purpose` subagents cost ~543k tokens at boot and ~730k once each has made its first tool call; twelve unnamed `Explore` scouts cost ~211k and ~397k. That ~332k difference exceeds what a full pass of trimming every agent, skill, and command description recovers — dispatch shape is the bigger lever, by a wide margin.

**The default that follows:** read-only investigation dispatches as an unnamed `Explore`. **The boundary that limits it:** the cheap tier is read-only by construction — `Explore` and `Plan` carry no `Edit`/`Write`, and there is no cheap tier that writes. Work that edits files pays the full tier, and that is the *only* reason to leave the cheap tier.

**A replay against real dispatch prompts bounds how often a read-only-tier offer would even apply.** Checking 516 real `general-purpose` dispatch prompts for a read-only-shaped predicate — a find/locate/search/survey signal present, with no write-shaped instruction anywhere in the prompt — found it fired on 32 of them, about 6.2%. Ground truth for which of those dispatches actually went on to write could not be reconstructed from the same batch, so the number bounds how *often* such an offer would surface, not how often it would be *wrong*. That is the reason a read-only-tier nudge belongs at the offer register rather than a block: when a detector's error rate cannot itself be measured, the right response is to lower the consequence of the detector being wrong, not to harden the signal into something that blocks on it.

### Naming an `Explore`/`Plan` Dispatch Destroys Both the Saving and the Read-Only Guarantee

Passing `name:` makes a dispatch an addressable teammate. On a **built-in** agent type that is not an annotation — it is a different spawn path that **discards the built-in agent definition altogether**. Confirmed from the CLI implementation, not inferred from the token counts:

- The predicate that strips CLAUDE.md from a subagent tests `agentDefinition.omitClaudeMd`; the predicate that strips git status tests `agentType === "Explore" || agentType === "Plan"`. Both `Explore` and `Plan` carry `omitClaudeMd: true` and `source: "built-in"`.
- A named dispatch routes to the teammate spawn, which looks the definition up and then keeps it only if `source !== "built-in" && source !== "plugin"`. For `Explore`/`Plan` that test fails, so **no definition is passed on**.
- A synthetic definition is fabricated in its place: `agentType` becomes your `name:` string, there is no `omitClaudeMd`, the system prompt is the **main-loop** builder, and `tools` falls back to `["*"]`.

Three consequences follow, and the second is the one that matters most:

1. **Cost.** The same `Explore` costs ~17,566 tokens unnamed and ~48,568 named. Naming does not shrink the saving; it deletes it. Every named dispatch converges on the same base envelope regardless of type.
2. **A named `Explore` is not read-only.** Its `Edit`/`Write` denial lives in the definition that naming throws away, along with `disallowedTools`. An agent dispatched as a read-only scout can modify the working tree. Do not rely on agent type as a write barrier once a dispatch is named.
3. **The penalty is type-dependent.** `general-purpose` (45,258 → 48,872) and `coordinator:executor` (54,982 → 57,705) barely move — their definitions are not `built-in`, survive the filter, and were already paying for the corpus. The ~31k figure is specific to the cheap tier.

Caveat on scope: this is the in-process teammate path, which is the one an in-session `Agent` dispatch exercises. A split-pane/tmux teammate spawns a separate `claude` process and composes its prompt differently.

### The Roster/MCP Delta Is Paid Only by Subagents That Can Dispatch

A separate measured mechanism, easy to mistake for the above: the 42-entry agent roster and every connected MCP server's instruction block — ~39,654 B, ~15,547 tokens — are **not** in a dispatched subagent's initial context. They arrive attached to the result of its **first tool call**, any tool call. A `general-purpose` probe making exactly one `Bash: echo hi` saw its input jump 45,258 → 60,805 tokens for a two-byte tool result.

**But it is not delivered to every subagent — it tracks whether the subagent holds the `Agent` tool**, i.e. whether it can dispatch at all. Measured first-tool-call deltas: `Explore` unnamed **+803** (n=3), `coordinator:test-evidence-parser` **+1,421**, named `Explore` (`tools:["*"]`) **+9,091** (n=3), `general-purpose` **+15,547**. The `test-evidence-parser` cell is the decisive one — it carries the full doctrine corpus and makes a real tool call, and differs from `general-purpose` essentially only in its tool grant.

Two consequences:

- **The multiplier is small in practice.** Almost no coordinator agent holds the `Agent` tool, so a twelve-agent coordinator fan-out pays the roster roughly **once**, not thirteen times. Do not cost agent-`description:` bytes as a wave-scale ×N saving — the durable arguments for short descriptions are the 1024-char truncation cliff and routing quality, not this delta.
- **It does not change the `Explore`-by-default call above**, and it slightly strengthens it: the cheap tier avoids this delta as well as the corpus.

It also explains why two honest probes can contradict each other about whether the roster is present: the answer depends on whether the probe used a tool before answering **and** on whether its agent type can dispatch. The injection writes **no attachment record**, so transcript absence is not evidence of non-delivery.

### The Auto-Memory Index Rides the CLAUDE.md Corpus, and Cannot Be Scoped to the Main Session

The harness auto-memory index (`MEMORY.md`, the one-line-per-fact file the model maintains across conversations) is not delivered as its own attachment — it is loaded as a CLAUDE.md-family entry and rendered into the same `claudeMd` string as the repo and global doctrine. Two consequences:

- **Every doctrine-carrying subagent pays it**, not just the main session — one more reason the index deserves the same byte discipline as a prompt surface. `Explore` and `Plan` escape it for the same reason they escape CLAUDE.md, and by the same single flag.
- **It cannot be suppressed for subagents alone.** The only predicate that strips it from a dispatched agent is the built-in corpus-skipping flag, which is not settable from agent frontmatter, agent JSON, or the dispatch call — the loaders build their agent records from closed field lists and silently drop unknown keys. Every other control (`autoMemoryEnabled: false`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`, blanking the index content via env) is session-wide and takes the main session's memory down with it.

So the lever that exists is **curation, not configuration**: keep the index to genuinely non-derivable operating memory. Anything restating always-on doctrine, or already enforced by a hook, guard, schema, or test, is paid once per agent per wave to tell the reader something it was going to be told anyway.

## Heuristic

> Fan out when the job decomposes. Dispatch when the sub-agent brings something the EM doesn't have: context, concurrency, judgment, or isolation from a large read. EM-inline only when the fix is small, the locus is already known, and the work fits inside the dispatch-bootstrap-overhead window.

A useful smell test: if the EM's dispatch prompt would be "read file X, change line Y, report back" — and the EM already has file X in context — the dispatch is overhead theater, not delegation.

## Per-Agent Worktrees Are Blocked at Dispatch, Not Mitigated

Per-agent git worktrees are structurally banned across the fleet: they degrade badly on the primary machine and audience (Windows) and don't scale to a concurrent agentic fleet where many sessions share one working tree. `isolation: "worktree"` dispatch is blocked before it can pay the creation cost described in the table above — there is no sweep, throttle, or settings toggle to reach for, because the dispatch itself doesn't happen. An override exists for the rare case that genuinely needs isolation, but it requires explicit PM permission routed through the EM — it is not a default any EM reaches for unilaterally.

The economics that still bite are the ones the ban doesn't touch: **shared-tree dispatch with disjoint scopes, and EM-serial commits.** Every sub-agent operates on the same working tree as its siblings and the EM. That buys back the worktree-creation cost entirely, but it moves the coordination burden onto scope discipline instead — parallel dispatches must have non-overlapping file lists (see `dispatching-parallel-agents.md` § Peer-Scope Prohibition), and only the EM commits, serially, after a wave closes, because a shared index means a stray `git add -A` or unscoped `git commit` from one sub-agent can sweep up a sibling's uncommitted edits. The fixed cost that used to be "worktree creation seconds" is now "scope-planning discipline at fan-out time" — cheaper in wall-clock, but it shifts the failure mode from slow to wrong if scopes aren't kept disjoint.

## Cluster Execution — Full Ceremony on the Novel Item, Direct Dispatch on the Rest

*coordinator-claude.* When a cluster of related fixes shares a single architectural shape (one novel pattern + N surgical follow-ups that mirror it), front-load the review ceremony on the novel item and direct-dispatch the surgical follow-ups against the established pattern. Full plan-review + prior-art-check + post-impl code-review on every cluster member is ceremony inflation — the second through Nth instances re-verify the same pattern with diminishing return.

**Rule:**
- **Item 1 (the novel one):** full ceremony — plan, prior-art-check, the Staff Engineer, post-impl review.
- **Items 2..N (surgical follow-ups of the same shape):** direct executor dispatch with the item-1 spec as reference. EM spot-check post-commit.

Tell for cluster shape: each item edits a different file, the *shape* of the edit is the same, and the only judgment in items 2..N is "apply the item-1 pattern to this file's specifics." When you find yourself drafting the same plan body N times with the file path changed, that's the tell — promote item 1 to canonical and direct-dispatch the rest.

## Run-Cost Calibration — Budget for Longest-Reasonable-Success, Build a Short Repro Before the Long One

Three facets of the same discipline: the wall-clock budget for a dispatched run, and the loop you iterate inside it, must be sized against the *actual* cost of the run, not a worst-case imagination or the convenience of re-firing the whole thing.

**Budget for "longest reasonable success," not "worst-case imagined."** A diagnostic or e2e run's timeout should be set from the longest a *successful* run plausibly takes — not the catastrophic upper bound your anxiety reaches for. Over-budgeting wastes the EM's polling window (a run that would have failed at 90s is given 10 minutes before the EM looks); a too-tight budget kills legitimate slow-but-succeeding runs. Estimate the success-path duration, add headroom, and treat overrun as signal (it hung) rather than as a margin you padded to avoid thinking.

**Build a 60s repro before re-firing a 30-min job.** When a long-running pipeline fails, the temptation is to tweak one thing and re-fire the whole 30-minute job. The short-loop discipline: extract the failing stage into a sub-minute reproducer first, iterate against *that* until green, then re-fire the full job once. The repro-construction cost is paid back on the second iteration — and most long-pipeline failures need 3-5 iterations to resolve. Re-firing the full job per iteration is the single most expensive iteration shape available.

**The harness Bash 5-minute timeout is hostile to long-running e2e — three workarounds.** The Bash tool caps at a hard timeout (default 2 min, max 10 min); genuinely long e2e runs (full index build, cold-cache install verification) exceed it. Do not paper over this by splitting the *test* into artificially small pieces that no longer exercise the integration. The three legitimate shapes:

1. **PM-manual** — hand the PM the exact command to run in a real terminal with no timeout; the EM consumes the result. Right when the run is genuinely one indivisible long operation.
2. **Warm-cache splits** — run the expensive setup phase once (priming the cache), then the EM's repeated verification runs hit warm cache and fit the budget. Right when the cost is front-loaded setup, not the assertion.
3. **Passive sibling verification** — a sibling process (daemon, watcher, already-running server) does the long work; the EM polls its status artifact rather than blocking on it. Right when the long work is someone else's to own (see `dispatching-parallel-agents.md` § Long-Running Dispatched Process for the status-file/heartbeat protocol).

## Related

- → `docs/wiki/dispatching-parallel-agents.md` — when parallel-shape is appropriate; Coupling Rules Out Concurrency; Peer-Scope Prohibition
- → `docs/wiki/delegate-execution.md` — EM-vs-executor altitude
- → `agent-worktree-sweep.py` — reaps orphan worktree directories; only relevant to the rare PM-authorized isolated-dispatch override, since the shared-tree default creates no worktrees to orphan
- → your fleet's fan-out dispatch helper — overlap pass + scoped-prompt compiler (run this to fan out a wave)
- → `dispatching-parallel-agents.md` § Executing a Fan-Out Wave — the fan-out methodology execution follows; runs the helper, dispatches the compiled wave via `Agent`, holds EM-serial commit between waves (not a skill — a slash-command alias for this was retired, vocabulary collision with native Claude Code)
- → anti-monolith HARD RULE — a large job is fanned out or chunked per-fresh-agent, never one agent grinding chunk after chunk
- → "Many agents often beat one [universal]" — empirical antecedent for fanning out over grinding one agent through independent chunks serially
- → `skills/pickup/SKILL.md` (handoff Step 6 + memo M3 Accept) and `skills/workstream-start/SKILL.md` (§ Engage + § Load task context) route grabbed-baton work through dispatch-by-default — "run" = dispatch an executor, not type it yourself.
