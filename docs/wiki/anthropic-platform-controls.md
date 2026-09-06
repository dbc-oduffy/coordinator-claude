---
title: "Anthropic platform controls — what reaches a Claude Code plugin"
created: 2026-07-27
status: active
spec_backlink: state/reference/anthropic-docs/_verify-harness-capabilities.md
---

# Anthropic Platform Controls — What Reaches a Claude Code Plugin

> Distills the archived Anthropic platform docs (`state/reference/anthropic-docs/*.md`, 96
> pages) plus the second-pass mining sidecars under `_mine/`. The recurring shape: most of this
> documentation describes **raw Messages-API request/response fields** — `tools=[...]`,
> `cache_control`, `output_config`, `thinking: {...}`, `context_management`. Claude Code already
> is such an API client, fully assembled, running its own agentic loop. A coordinator plugin
> author (skill/hook/agent/command under `coordinator/`) never constructs that request — so a
> capability documented at the API level is reachable **only if the harness re-exposes it** as a
> frontmatter field, a hook event, a settings.json knob, or a CLI flag. Absent that re-exposure,
> "documented" and "reachable" are different claims, and this file keeps them separate on
> purpose. Ground truth for reachability: `state/reference/anthropic-docs/_verify-harness-capabilities.md`,
> verified against the installed **Claude Code 2.1.220** build.

## Context — windows, compaction, editing, counting

**Real numbers** (`context-windows.md`): context window is up to **1M tokens** on Opus 5,
Sonnet 5, and siblings (200k on older Sonnet 4.5-class models); a single 1M-window request can
emit up to 128k output tokens. Everything in the request counts — system prompt, every message,
tool definitions, tool results, and thinking tokens. Context awareness (`<budget:token_budget>`
tags auto-injected into the model's own system prompt and after every tool call, on every model
in our fleet except the Opus personas) is real, automatic, and **has no caller-facing lever at
all** — nothing to enable, disable, or read from plugin code (`_mine/context-effort-thinking.md`
item 4).

- **Compaction** (`compaction.md`, `context_management.compact_20260112`) and **context editing**
  (`context-editing.md`, `clear_tool_uses_20250919`/`clear_thinking_20251015`) are both
  `context_management` fields on `messages.create`. Whether Claude Code's own harness invokes
  these internally is **UNCONFIRMED** — `_verify-harness-capabilities.md` has no section on
  `context_management` at all. Inferred-NO for plugin *access* to the config (Claude Code
  abstracts request construction away entirely, same pattern as every item below), but that's an
  inference, not a settled fact (`_mine/context-effort-thinking.md` item 3).
- **What we actually have:** `PreCompact` hook (registered — `context-pressure-precompact.py`)
  fires before compaction; `PostCompact` **exists, is documented, and is unused** — we currently
  infer compaction happened from a byte-size sentinel written pre-compaction rather than
  confirming completion via `PostCompact`. Genuine gap, not a documentation curiosity.
- **Token counting**: `POST /v1/messages/count_tokens` is free, rate-limited only. Already
  adopted (`claude-klabauter` commit `4dc5d518`, per the claude5-alignment plan's C1) — nothing
  further to mine here.
- **Coordinator takeaway:** our context-pressure hooks (`postuse_advisory_dispatch.py`, the
  sidecar read) are not a redundant layer on top of a native mechanism we could instead
  just read — they are the *only* signal this harness gives an operator. `context-pressure-estimation.md`
  should describe itself that way, not hedge as if a native surface might already be doing the
  job where we could just tap in.

## Effort and thinking

**What `effort` actually controls** (`effort.md`): a single dial from `low` → `medium` → `high`
(default) → `xhigh` → `max`, affecting **all** token spend — text, tool calls, and thinking
together, not thinking alone. It is a behavioral signal, not a strict budget (Claude still thinks
on hard problems at `low`, just less). Anthropic's own reference explicitly recommends `low`
**for subagent-shaped work** — "simpler tasks that need the best speed and lowest costs, such as
subagents." Claude Sonnet 5 defaults to `high` effort "on the Claude API **and Claude Code**"
(`effort.md`, confirmed textually — this line is evidence for, not proof of, subagent-frontmatter
reachability specifically; see below).

- **Reachability:** `effort` is a documented `coordinator/agents/*.md` frontmatter field on the
  installed 2.1.220 build (alongside `disallowedTools`, `permissionMode`, `maxTurns`, `skills`,
  `mcpServers`, `hooks`, `memory`, `background`, `isolation`, `initialPrompt` — 11 documented
  optional fields total). **We use zero of them** across 31 agent files; only `tools`, `model`,
  `color` are populated (`_verify-harness-capabilities.md` § 2, § 4). "Documented in schema" is
  not "observed in effect" — nobody has yet empirically confirmed the plugin agent-loading path
  actually honours a frontmatter `effort:` value (that's the open AC4 blocker on
  `docs/plans/2026-07-27-claude5-alignment-wave-one.md` C2; the `effort.md` line above narrows,
  but doesn't close, that gap).
- **Prompt-level thinking steering is reachable *today*, independent of the frontmatter gate.**
  `thinking-steering-and-cost.md` documents three levers in priority order: `effort` (frontmatter,
  gated per above) > system-prompt phrasing ("Extended thinking adds latency... When in doubt,
  respond directly" to suppress; "This task involves multistep reasoning. Think carefully" to
  encourage) > per-message phrasing. Lever 2 is plain prose in an agent's prompt **body** — a
  different edit surface from frontmatter, needs no empirical verification, and is available now.
  Coordinator takeaway: scout/mechanical-parser agents can get a "skip thinking on simple inputs"
  nudge, and reviewer/orchestrator agents a "think carefully" nudge, in-band, without waiting on
  the `effort:` rollout.
- **Task budgets** (`task-budgets.md`) — an advisory running-countdown token budget for a whole
  agentic loop — are **beta, header-gated (`task-budgets-2026-03-13`), and NOT listed as
  supported for Claude Sonnet 5** (only Opus 5/4.8/4.7, Fable 5, Mythos 5). Even where supported,
  it is a `messages.create` request field with no Claude Code exposure. **API-only. Not
  reachable.**
- **Manual `extended-thinking.md` budgets are N/A for our fleet.** Sonnet 5 and Opus 5 use
  adaptive thinking (manual `budget_tokens` is a 400 error); Haiku 4.5 has no thinking lever
  worth chasing. This is a legacy page for pre-4.6-class callers.
- **Existing doctrine this discharges/contradicts:** the `subagents-sonnet-unless-pm-approves-opus`
  memory lesson already picks the right model tier by hand; `effort: low` on Sonnet subagents is
  the *complementary*, currently-unused lever for the same economics goal, once AC4 resolves.
  `agent-dispatch-economics.md`'s dispatch-vs-inline calculus is unaffected — effort tunes a
  dispatched agent's cost, it doesn't change whether dispatch is the right shape.

## Tool use — parallel calls, tool search, the runner loop, streaming

**Structural finding, stated once so it isn't re-litigated:** every page in this family —
`parallel-tool-use.md`, `tool-search-tool.md`, `tool-runner.md`, `fine-grained-tool-streaming.md`,
`bash-tool.md`, `code-execution-tool.md`, `handling-stop-reasons.md`, `implement-tool-use.md` —
describes **building your own agent harness on the raw SDK**: constructing a `tools` array,
setting `tool_choice`, matching `tool_result` to `tool_use_id`, running a `while stop_reason ==
"tool_use"` loop. Claude Code is exactly such a harness, already built, already running that
loop. A plugin author's actual surface is `tools:`/`model:`/`color:` in agent frontmatter (a
name-allowlist), never an API `tools` array. This makes the family's remaining API-level detail
*structurally* unreachable, not merely currently-unused (`_mine/tool-use.md`).

- **Parallel tool use**: the API doesn't prescribe call ordering; Claude Code's own tool-call
  batching and the `tool_use_id`-matching discipline are internal to the harness. Nothing for a
  plugin to configure.
- **Tool search tool** (`tool-search-tool.md`): Anthropic's own adoption threshold is inconsistent
  across its docs — `manage-tool-context.md` says "roughly 20 tools," `tool-search-tool.md` says
  "10 or more" — flagged as a minor cross-doc discrepancy, not chased further. **This is the same
  problem the `ToolSearch` tool visible in this very session's tool list solves** (deferred-tool
  schemas, fetched on demand by name/keyword query) — but that mechanism is Claude Code's own
  native harness feature, not the Anthropic API's `tool_search_tool_20260118` server tool. Same
  *shape*, different *layer*: ours is already live and free; the API one is unreachable from a
  plugin regardless.
- **Bash tool / code execution tool**: API server-tool types (`bash_20250124`,
  `code_execution_...`) for a raw Messages-API client. Claude Code ships its own native `Bash`
  tool and file-edit tools already — a plugin's `tools:` allowlist names *harness* tools, never
  attaches an API-schema tool type. **Not reachable, and not needed** — we already have the
  native equivalent.
- **Tool runner (SDK)**, **fine-grained tool streaming** (`eager_input_streaming`): both are
  request-construction/response-parsing conveniences for a raw SDK caller. No plugin surface.
- **Coordinator takeaway:** nothing in this family is an unadopted opportunity. The fan-out
  dispatch machinery (`fan-out-dispatch.py` → `Agent` → EM-serial commit,
  `docs/wiki/dispatching-parallel-agents.md`) already *is* our answer to "run many tool-using
  agents" — it doesn't need, and can't use, the API-level parallel-tool-use or tool-runner
  mechanics, because those operate one level below the abstraction Claude Code hands us.

## Structured outputs

**What constrained decoding guarantees:** `output_config.format` (JSON outputs) and `strict:
true` (tool inputs) are Messages-API parameters backed by compiled-grammar constrained decoding —
Anthropic's guarantee is schema-*shape* conformance (valid JSON matching the schema), not
semantic correctness of the values inside it.

**What it does NOT reach:** `_verify-harness-capabilities.md` § 2's full 14-field frontmatter
census — `tools`, `model`, `color`, `disallowedTools`, `permissionMode`, `maxTurns`, `skills`,
`mcpServers`, `hooks`, `memory`, `background`, `effort`, `isolation`, `initialPrompt` — contains
no `schema`, `output_config`, or `strict` field, and the `Agent`/Task dispatch call itself takes
a prompt and a subagent type, never a JSON Schema. Cross-checked directly against
`coordinator/agents/{code-reviewer,plan-coverage-checker,coverage-auditor,parallel-review-synthesizer}.md`
frontmatter: `name`, `description`, `model`, `color`, `tools`, `access-mode` only. **Settled NO**
for the dispatch path that carries ~30 of coordinator's ~31 agents (`_mine/structured-outputs.md`).

- **Why this matters here, specifically:** coordinator's entire review/findings pipeline —
  `ReportFindings`, sidecar YAML/JSON, `claims.json`-shaped contracts — parses **agent-generated
  prose defensively**, because there is no constrained-decoding guarantee backing any of it. This
  confirms (doesn't just excuse) the existing defensive-parsing posture: it is the correct
  response to a real absence, not caution left over from an earlier, less-capable harness. Do not
  read a future SDK/harness upgrade as license to relax it without re-checking this census first.
- **`ReportFindings`** (the typed tool this very agent has access to) is the closest thing
  coordinator has to schema-constrained output today, and it works by a different mechanism
  entirely — a harness-defined tool with its own JSON-Schema-shaped parameters, invoked the same
  way any tool call is, not `output_config.format` on a raw completion. Don't conflate the two.

## Caching and batching

**What caches, what invalidates it** (`prompt-caching.md`): `cache_control` marks a breakpoint;
default TTL 5 minutes (1-hour available at 2x base input price). Lookback window is **20 blocks**
— the system checks at most 20 positions back from a breakpoint for a matching prior write; miss
the window and there's no hit even if the content is byte-identical to something cached earlier.
Up to 4 explicit breakpoint slots per request; automatic caching claims one if unused.

**Batch processing** (`batch-processing.md`): up to 100,000 requests or 256MB per batch, **50%**
price cut, most batches finish inside an hour, hard 24-hour expiry, results as `.jsonl`. Server
tools (web search, code exec, MCP connectors) run inside the batch worker's own agentic loop —
**client-side tools do not**: a batched request declaring `tools` still returns `tool_use` blocks
the *caller* must execute and feed back as a new batch request. There is no Task-tool-style
Read/Grep/Bash runtime inside a batch worker.

- **Reachability, both:** neither is exposed to a Claude Code plugin. Caching/streaming/`system`/
  `tools`-array construction is Messages-API request plumbing Claude Code assembles internally
  and never hands to hooks/skills/agents. Batch requires a live `ANTHROPIC_API_KEY` this
  environment doesn't have, and — even with one — building fan-out on Batch means
  reimplementing the tool-execution loop Claude Code already gives us for free, i.e. a second
  harness, not a cost optimization (`_mine/caching-batch-models.md`).
- **Coordinator takeaway — do NOT chase Batch as a fan-out-dispatch replacement.** It looks
  attractive on a skim ("bulk content generation," "large-scale evaluations" — exactly our
  scout-wave shape) and is a dead end for that use once you check the tool-execution gap. Settled
  here so it isn't re-proposed.
- **One live, unadopted lever, unrelated to either doc's headline:** `PostToolBatch` — a
  documented hook event (batches hook firings once per tool-call batch instead of once per call)
  — is **registered nowhere** in `coordinator/hooks/hooks.json` (0 of 7 registered events cover
  it; see `_verify-harness-capabilities.md` § 5's full 29-event table). Worth a look against the
  P0 bash-kill campaign's fork/exec-tax concern — batching hook firings could cut process spawns
  on tool-heavy waves. Not evaluated further here; flagged for whoever next touches hook
  registration.

## Evals

`develop-tests.md`'s prescribed recipe: define measurable success criteria per behavior → build
test cases against real task distribution (edge cases included) → grade automatically — exact
match for categorical outputs, LLM-based grading (Likert/binary/ordinal) for judgment-shaped ones
→ prioritize volume of cheap-graded cases over a few hand-graded ones.

- **We already have one narrow instance of this pattern**: `coordinator/skills/eval-output/SKILL.md`
  dispatches a single Sonnet agent against a fixed 5-criteria rubric to score a research output —
  explicitly citing the same doc's finding that "a single LLM call with a single prompt was most
  consistent." It is manual, on-demand, one-shot, and scoped to one artifact type (research
  output) — not a tracked fixture set, not run in CI, not applied to any of the 31 agents or
  ~40+ skills coordinator changes on judgement alone.
- **Reachability is PARTIAL, split cleanly in two:** the *structural* half (does a prompt file
  have the right frontmatter shape, does a skill reference a file that exists) is CI-reachable —
  ordinary `pytest` under `coordinator/tests/`. The *behavioral* half (did this prompt edit
  actually help or hurt) requires a live dispatch — `Agent`/Task inside an EM turn, or a
  scheduled routine (`schedule` skill / `CronCreate`) — and can never be a commit-blocking
  pytest gate, because pytest cannot itself invoke a subagent and grade its output.
  (`_mine/evals.md`)
- **Coordinator takeaway:** the `eval-output` pattern is the right shape to generalize into a
  golden-fixture regression harness for coordinator's own agent/skill prompts — closing the real
  gap that "we change prompts on judgement alone, with no regression net on *behaviour*, only on
  code" names. Sizeable (L) — picking an initial slice of agents/skills, not all 31 at once — not
  proposed as work here, only named as the documented-correct recipe if/when it's picked up.

## Summary table — reachable vs. not, from a Claude Code plugin

| Capability | Reachable? | Where the answer comes from |
|---|---|---|
| Context window sizes, thinking-token accounting | N/A (automatic, no lever) | `context-windows.md` |
| `context_management` (compaction/editing config) | UNCONFIRMED, inferred NO | `_verify-harness-capabilities.md` (silent) |
| `PostCompact` hook | YES, documented, **unused** | `_verify-harness-capabilities.md` § 5 |
| Token counting API | YES, already adopted | `4dc5d518` |
| `effort:` subagent frontmatter | Documented field, **unverified in effect, unused (0/31)** | `_verify-harness-capabilities.md` § 2/4 |
| Prompt-body thinking-steering phrasing | YES, live now | `thinking-steering-and-cost.md` |
| Task budgets | NO — beta, not on Sonnet 5, API-only | `task-budgets.md` |
| Parallel tool use / tool runner / fine-grained streaming | NO — SDK request plumbing | `_mine/tool-use.md` |
| Tool search (API server tool) | NO — but native `ToolSearch` harness equivalent already live | `_mine/tool-use.md` |
| Bash / code-execution API tool types | NO — native `Bash`/edit tools already cover it | `_mine/tool-use.md` |
| `output_config.format` / `strict` structured outputs | NO for `Agent`/Task dispatch (~30/31 agents) | `_mine/structured-outputs.md` |
| Prompt caching (`cache_control`) | NO — Claude Code owns it internally | `_mine/caching-batch-models.md` |
| Batch API | NO — no tool-execution loop inside a batch worker; no API key here | `_mine/caching-batch-models.md` |
| `PostToolBatch` hook | YES, documented, **unused**, worth investigating | `_verify-harness-capabilities.md` § 5 |
| LLM-judge evals (behavioral) | PARTIAL — dispatch-reachable, not pytest-reachable | `_mine/evals.md`, `eval-output` skill |

**Reading this table cold:** if a row says NO with "SDK request plumbing" or "Messages-API
field" as the reason, that verdict will not change without a harness upgrade that re-exposes the
field — don't re-propose adoption without checking whether `_verify-harness-capabilities.md` has
been re-run against a newer build first.
