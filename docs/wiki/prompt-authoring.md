---
title: Prompt authoring for agent/persona prompts
created: 2026-07-27
type: doctrine
related:
  - coordinator/agents/executor.md
  - coordinator/agents/code-reviewer.md
  - coordinator/docs/wiki/dispatching-parallel-agents.md  (§ Agent Definitions — Durable Doctrine Lives There, Not in the Brief — WHEN/HOW to dispatch)
  - coordinator/docs/wiki/eager-agent-calibration.md  (executor-facing calibration prose, a sibling concern)
  - coordinator/docs/wiki/writing-skills.md  (SKILL.md authoring — a distinct surface, see § Scope below)
---

# Prompt Authoring for Agent/Persona Prompts

<!-- spec-backlink: state/reference/anthropic-docs/_survey-prompt-shape.md (empirical survey of the 31 coordinator/agents/*.md files this wiki is grounded in) -->

This wiki governs how `coordinator/agents/*.md` persona/agent prompts are written: what belongs
in the agent definition versus the per-dispatch brief, which pieces of Anthropic's current
model-behavior guidance apply to our fleet and how to keep that guidance from rotting silently,
when a worked `<example>` earns its tokens against a declarative rule, and what a prompt should
never contain. It closes a real gap: 31 agent prompts (largest 485 lines) exist today, authored
by accumulated convention, with no canonical reference for the choices that convention encodes.

**Scope.** This is about agent/persona prompt *text* — the file the dispatched agent reads as its
identity and doctrine. It is not about *when* or *how* to dispatch (`dispatching-parallel-agents.md`
owns that), and it is not about SKILL.md authoring (`writing-skills.md` owns that — skills are
read by the EM's own session, agent prompts are read by a spawned subagent with no other context).
It is also not a style guide: heading case, bullet glyphs, and section ordering are not covered
here — the value below is model-behavior facts and the definition-vs-brief boundary, not
formatting taste.

## The Agent-Prompt vs Dispatch-Brief Boundary

Two surfaces carry text to a dispatched agent, and conflating them is the most common authoring
mistake:

- **Agent definitions** (`coordinator/agents/*.md`) load on **every** dispatch of that agent type.
  They are durable, version-controlled, and shared across however many times that role is ever
  invoked. This is where identity, standing invariants, and doctrine the role must always carry
  belong — write it once here rather than retyping it into every brief.
- **Dispatch briefs** are EM-authored, ad hoc, and per-invocation. They carry the delta: which
  files are in scope, what this specific task is, which peer chunks are out-of-scope, and the
  go-ahead. Everything the agent definition already states should not be restated in the brief.

**The operational test:** would this sentence be true on *every* dispatch of this agent, or only
on *this* one? "Always confined to a two-tier Bash allowlist" is a definition fact — true on every
`code-reviewer` dispatch, so it lives in `agents/code-reviewer.md`. "Review `coordinator/hooks/scripts/foo.py`
and its test" is a brief fact — true only of this dispatch, so it never belongs in the definition.

**Tell you're on the wrong side of the boundary:**
- If you find yourself retyping the same paragraph into every brief for a given agent type, that
  paragraph belongs in the definition, not the brief.
- If a definition file names a specific file path, a specific chunk ID, or "this diff" instead of
  "the diff" — it has drifted brief content into the durable file, and the next dispatch of that
  agent inherits stale specifics it should never have seen.
- **The artifact is the interface, not the paraphrase.** Where content already lives on disk (a
  plan chunk, a sidecar, a disposition table), the brief passes the *path* to it — never a
  retyped summary. An EM that paraphrases a sidecar into a brief has made itself the transport,
  and the agent re-derives from the paraphrase instead of reading the source. See
  `dispatching-parallel-agents.md § Agent Definitions — Durable Doctrine Lives There, Not in the Brief`
  for the fuller treatment (including the third, dispatch-time-injected lane via
  `contract_blocks:`) — this wiki names the boundary test; that wiki names the mechanics.

## Model-Specific Guidance — Explicitly Marked Volatile

The items below **reverse** advice that was universal until recently, based on measured model
behavior at time of writing (Claude Opus 5 / Claude Sonnet 5). Model behavior is not a stable
foundation to build doctrine on — each item below carries the model/version it is true of and the
observation that would invalidate it. **Do not silently propagate these into an agent prompt
without the same volatility framing** — an unqualified "never tell it to verify its work" reads as
timeless doctrine to a future author who has no way to know it was Opus-5-conditional.

### Opus 5 self-verifies and self-corrects unprompted

Opus 5 catches and fixes its own mistakes without being told to, and an explicit "verify your
work" / "double-check your answer" / "use a subagent to verify" instruction now causes measured
**over-verification** — wasted tokens with no quality gain — rather than the safety net that
instruction used to buy on older models.

- **True of:** Claude Opus 5, per Anthropic's own prompting guide for that model.
- **Invalidated by:** a future model generation regressing on self-correction (an eval showing
  Opus-tier output shipping uncorrected errors would be the signal to re-add verification
  language), or a coordinator persona's own review finding this class of drift live in practice.
- **What to do instead:** if a task genuinely needs a distinct verification *pass* (not a
  self-check), that pass is a structural step — a downstream reviewer, an integrator, a test run —
  not a sentence asking the same model to re-check itself.

### Opus 5 expands scope and over-delegates to subagents

Opus 5 both widens task scope on its own initiative (adding unrequested steps, applying its own
judgment about what the task "should" be) and reaches for subagent delegation more readily than
prior models, including — unhelpfully — delegating to *verify its own work*.

- **True of:** Claude Opus 5.
- **Invalidated by:** a future model showing narrower default scope or delegation restraint.
- **What to do instead:** an Opus-pinned agent definition (`eng-director.md`, `staff-eng.md`, and
  the other Opus-tier personas) should state scope discipline explicitly — "deliver what was
  asked, at the scope intended; stop short of actions clearly beyond what was asked" — and cap
  delegation to genuinely independent, parallelizable work, never to self-verification. This is
  the model-behavior grounding for the existing `agent-dispatch-economics.md` /
  `dispatching-parallel-agents.md` dispatch-economy doctrine; it does not replace that doctrine, it
  explains why Opus needs the explicit cap where a Sonnet worker may not.

### Sonnet 5 has adaptive thinking on by default; manual thinking budgets 400 error

Sonnet 5 runs with adaptive thinking on for any request that doesn't set a `thinking` field — a
change from Sonnet 4.6, where the same request ran with no thinking. Passing a manual/extended
thinking budget (`thinking: {type: "enabled", budget_tokens: N}`) is **removed** on Sonnet 5 and
returns an API 400 error; the replacement lever is `effort`, not a token budget.

- **True of:** Claude Sonnet 5 (API-level change, not just a stylistic recommendation).
- **Invalidated by:** an API surface change reintroducing manual budgets, or a docs update to
  Anthropic's Sonnet 5 migration guide.
- **What to do instead:** an agent prompt authored for the coordinator fleet should never encode a
  `budget_tokens` value — the replacement lever is `effort`. Frontmatter `effort:` on the agent
  definition is the durable per-agent default locus (see
  `docs/plans/2026-07-27-claude5-alignment-wave-one.md` chunk C2) — no agent defaults to `high`;
  mechanical workers get `low`, executors/review-integrator/code-reviewer/Opus personas get
  `medium`. Dispatch-time `effort` remains the override for the exceptional task that genuinely
  warrants raising it, not the primary locus. The per-agent assignment, the empirical confirmation
  that the field is honoured, and the standing ceiling (`high` needs dispensation, nothing beyond
  it) are in `subagent-effort-assignment.md`.

### Prefilled assistant turns are removed fleet-wide

Prefilling the start of an assistant turn to force format, suppress a preamble, or steer a
refusal is a **removed technique** starting Claude 4.6/Mythos Preview. Any inherited prompt pattern
that relies on a prefilled assistant-turn opener needs a named replacement, not a retained prefill.

- **True of:** all current-generation Claude models (Opus 5, Sonnet 5, and the 4.6 generation
  onward) — this is the broadest-scoped item in this section, not model-specific in the way the
  other three are.
- **Invalidated by:** Anthropic reintroducing prefill support in a future API generation.
- **What to do instead:** Anthropic names four replacements depending on what the prefill was
  doing — Structured Outputs for format control, an explicit no-preamble instruction for preamble
  suppression, refusal-handling without prefill, and moving continuations into the user turn or
  hydrating context via tools instead of prefill. None of the 31 coordinator agent prompts surveyed
  currently rely on prefill, so this item is a standing constraint on future authors, not a
  retrofit.

### Why volatility framing is mandatory, not optional, here

Every claim above will eventually be wrong about *some* future model. The framing
(model/version + invalidation trigger) is what lets a future author tell the difference between
"this was always true" and "this was true of Opus 5, check before reusing it." An agent prompt
that bakes in unqualified Opus-5-specific behavior claims — rather than citing this wiki or the
source doc — creates exactly the kind of undated assumption `no-ruling-dates-in-skill-surfaces`
warns against, inverted: dates belong in provenance comments, not in the doctrine body, but the
*model this claim is conditioned on* is not optional metadata — omitting it turns a conditional
fact into an unconditional one.

## When Examples Earn Their Tokens

The survey found `<example>` blocks in exactly 10 of the 31 agent prompts, and — tellingly —
**in none of the 9 largest procedural agents** (`review-integrator`, `executor`, `eng-director`,
`prior-art-checker`, `code-reviewer`, `parallel-review-synthesizer`, `plan-coverage-checker`,
`docs-checker`, `enricher`). Where examples do appear, they cluster in the research/repo pipeline
agents (`research-scout`, `research-specialist`, `research-synthesizer`, `research-worker`,
`research-sweep`, `repo-scout`, `repo-specialist`, `structured-synthesizer`,
`notebooklm-research-scout`, `coverage-auditor`) — each carrying exactly one example block, which
is the harness's own Agent-tool `<example>…</example>` frontmatter convention rather than a
few-shot library.

**The rule this data supports:** an example earns its tokens when the desired *shape of output*
is hard to state declaratively but easy to recognize once shown — a narrative style, a
communication cadence, a worked input/output pair for a format the model must reproduce exactly.
It does not earn its tokens when the task is procedural: a numbered sequence of steps, a decision
tree, a set of invariants to hold. The 9 largest agents in this fleet are procedural — their size
comes from section count (executor carries 20 `##`/`###` sections; review-integrator carries 24),
not from illustrative material — and a declarative rule ("verdict is exactly one of OK/WARN/BLOCKED,
use BLOCKED when you mean it") states the same content an example would, at a fraction of the
token cost, with none of the risk of the model over-fitting to the example's surface details
instead of the underlying rule.

**Ask before adding an `<example>` block to a procedural agent:** could this be a declarative
sentence instead? If yes, write the sentence — you are looking at the failure mode the 9 largest
agents in this fleet already avoid. Reserve examples for: format-reproduction tasks (a commit
message shape, a specific report template), communication-cadence calibration (narration style,
tone), or genuinely ambiguous category boundaries a rule can't cleanly state (what counts as a
P0 vs P1 finding is closer to declarative-rule territory; what a "warm, collaborative tone" sounds
like is closer to example territory).

## Length Discipline

There is no fixed line-count ceiling in this fleet, and this wiki does not invent one. The survey
data: the largest agent prompt (`review-integrator.md`) runs 485 lines; the next three
(`executor.md`, `eng-director.md`, `research-sweep.md`) run 462, 451, and 369. All four are
structured entirely with markdown `##`/`###` headers — none of the three largest use any
`<role>`/`<instructions>`/`<context>` XML-wrapper convention, and the only literal `<tag>` usage
anywhere in agent bodies is the narrow `<exit-status>` structured-output convention in
`executor.md`. Size in this fleet tracks **procedural section count**, not padding: the largest
files are the ones with the most distinct doctrine surfaces to cover (dispatch discipline, commit
discipline, sidecar contract, guard-encounter protocol, and so on), each a load-bearing section a
prior incident motivated.

**The discipline this data supports is proportionality, not a cap.** Ask, for each section: does
this section state something true on every dispatch of this role that the agent needs to act
correctly, or is it explaining something the model already knows? The Anthropic skill-authoring
default — "assume Claude is already very smart; challenge each paragraph with 'does this
justify its token cost?'" — applies here even though this is an agent prompt and not a SKILL.md:
a section that restates general competence (how to read a diff, what a bug is) costs tokens on
every dispatch of that role for the lifetime of the file. A section that encodes a hard-won,
non-obvious invariant (the guard-denial stop-signal contract, the exact verdict enum, the sidecar
provisioning path) earns its place regardless of length, because omitting it reproduces the
incident that motivated it.

**Tell you're padding rather than encoding an invariant:** the section restates something any
capable model already knows without coordinator-specific framing (what a docstring is, what "be
thorough" means in the abstract), or the section could be deleted without any prior incident
recurring. Tell you're rightly long: every paragraph traces to a `Spec backlink:` — a real prior
failure the file exists to prevent from happening twice.

## What a Prompt Should NOT Contain

Adapted from Anthropic's skill-authoring guidance to this repo's actual surfaces — these are
concrete failure modes seen in the agent-prompt corpus and its cousins, not abstract hygiene:

- **Time-sensitive information.** No "as of [date]" behavior claims or "before/after [date] do X"
  branches baked into agent-prompt prose. Model behavior, API surfaces, and harness capabilities
  drift; a dated claim in the doctrine body goes stale silently. Provenance (when a section was
  authored, what incident motivated it) belongs in a spec-backlink comment, never in the prose a
  future dispatch reads as current instruction — see `no-ruling-dates-in-skill-surfaces` (memory
  note) and the model-volatility framing above for the one place a version *is* load-bearing
  content rather than a changelog artifact.
- **Magic numbers.** A bare threshold, retry count, or timeout with no stated reason forces every
  future reader to guess whether the number is load-bearing or arbitrary. If a number must appear,
  say why: "3 retries, because most intermittent failures resolve by the second" is authorable;
  "RETRIES = 3" alone is not (Anthropic's own skill-authoring guide calls this "voodoo constants,"
  Ousterhout's law).
- **Absolute or Windows-style paths.** No `/Users/...`, no `C:\...`, no backslash path separators <!-- foreign-path-ok: illustrating the forbidden shape itself, not asserting a location -->
  anywhere in an agent prompt body. This fleet runs cross-platform by design (Windows is the
  primary machine); a hardcoded path in a durable, every-dispatch-loaded file is exactly the
  install-surface-completeness failure this repo's own doctrine already names for code — the same
  discipline applies to the prompt text itself.
- **Over-explaining.** Don't narrate what a well-known concept is (what git is, what a docstring
  does, what "be thorough" means) — assume the model already knows. Every paragraph should answer
  "does Claude really need this told to it, or is this something a comparably capable model
  already has?" A paragraph that would be equally true and equally useful in a generic prompting
  guide with no coordinator context is a paragraph to cut from an agent prompt — coordinator-doctrine
  value comes from what only *this* codebase's conventions and incident history can teach.
- **Too many options presented as equally valid.** "You can use approach A, or B, or C, or…" is
  confusing where a default-with-escape-hatch would do: state the default action plainly, and name
  the one alternative that applies when the default doesn't fit. Anthropic's own skill guidance
  calls this out directly; agent prompts are no exception — an agent facing three equally-weighted
  options at the moment it needs to act is an agent that hesitates or guesses wrong.
- **Point-of-view drift.** An agent prompt speaks to the agent in second person ("you are…", "you
  read…") consistently throughout, per the house convention visible in every surveyed agent file
  (`code-reviewer.md`: "You are the **code-reviewer**. You read code diffs…"). Slipping into third
  person ("the agent should…") or first person ("I will now…") mid-file reads as a description of
  the role rather than an address to the role performing it, and Anthropic's own skill-description
  guidance flags exactly this drift as a discovery/clarity hazard in the adjacent SKILL.md surface —
  the same discipline holds here.

## What This Does Not Cover

- **SKILL.md authoring conventions** (name/description constraints, progressive disclosure,
  when to split into reference files) — `writing-skills.md` owns that surface. Skills are read by
  the EM's own session with full CLAUDE.md context already loaded; agent prompts are read by a
  freshly-spawned subagent with *no* other context, which is why an agent prompt must be fully
  self-contained in a way a skill need not be.
- **Dispatch mechanics** (fan-out sizing, concurrency budgets, background-by-default,
  shared-tree scoped-dispatch discipline) — `dispatching-parallel-agents.md` owns the WHEN/HOW of dispatch; this
  wiki owns the HOW of the prompt text itself. The two compose: a well-authored agent definition
  still needs a well-formed dispatch brief riding on top of it.
- **Editing the 31 existing agent prompts.** This wiki is doctrine only — it does not propose or
  make changes to any file under `coordinator/agents/`. Applying this doctrine to the existing
  corpus is separate, deliberately-scoped work.
