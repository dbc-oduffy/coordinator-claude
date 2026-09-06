# Subagent Effort Assignment

> Why every agent in `coordinator/agents/` carries an explicit `effort:` value, what each one is
> set to, and the standing ceiling on raising it. The assignment is a deliberate choice recorded
> as data, not an omission left to whatever the session happens to default to.
>
> **The values themselves are not stated here — `coordinator/agent-effort-registry.yaml` holds
> them, and `coordinator/tests/test_agent_effort_registry.py` enforces them.** This page explains
> the reasoning; the registry is the source of truth. A table of per-agent values duplicated into
> prose is a table that goes stale silently, which is the failure this whole mechanism exists to
> end.
>
> spec-backlink: `docs/plans/2026-07-27-claude5-alignment-wave-one.md` § C2 (AC4, AC5a, AC5b)

## The ceiling — standing PM ruling

**`low` and `medium` are the operating range. `high` requires dispensation. Nothing goes beyond
`high`, ever.**

`xhigh` and `max` are not options a frontmatter default may select, and not options the EM may
select at dispatch time either. This is a cost ruling, and it is not re-derivable from a
measurement — do not re-run an A/B against `max` to "check": the answer cannot change the policy,
so the data is unactionable by construction and only spends money. (A session that re-ran the A/B
against `max` anyway, and the PM's response to it, is why this paragraph exists.)

The reason the *default* matters so much: **`high` is already the Sonnet 5 session default.** An
agent with no `effort:` line is not neutral — it is silently running at the level that needs
dispensation. Setting the field is what makes the choice deliberate; that is why every agent carries one
rather than only the ones being moved.

## The field is honoured — verified empirically, 2026-07-27

`effort:` is a documented frontmatter field for subagent definitions (`low|medium|high|xhigh|max`,
"overrides the session effort level"). Documented was never the question — **observed** was.

Two things are worth carrying forward from proving it:

- **The invalid-value oracle proves nothing.** An agent with `effort: banana` loads, appears in the
  dispatchable roster, and dispatches successfully. There is no load-time or dispatch-time
  validation, so silence is consistent with both "read, then silently defaulted" and "never read."
  Don't spend a session on this oracle again.
- **The behavioural A/B is the real instrument, and it is runnable.** Two agent definitions
  differing only in `effort:`, one fixed reasoning-heavy prompt, compare subagent output tokens.
  Measured on the plugin agent-loading path: a ~28x spread between the low and high ends. The field
  is read and it is live.

**Run the A/B at `low` vs `medium`, not `low` vs `max`.** Both ends stay inside the sanctioned
range, and the yes/no signal is what the test is for. Reaching for the extreme buys a bigger margin
and a number nobody is allowed to act on.

### The hot-reload wall, and how to get around it

**Agent definitions are not hot-reloaded.** A newly-written `coordinator/agents/*.md` is not
dispatchable until the next session boot — dispatch returns `Agent type not found` with the file
plainly present on disk. This blocks any in-session probe of a new agent, by the EM or by a
dispatch-capable subagent alike, and it cost three separate failed attempts before being named.

The way through is that **a `claude -p` subprocess is a fresh boot.** Run the probe from a
scratchpad cwd against a throwaway plugin dir (`--plugin-dir`, minimal `.claude-plugin/plugin.json`
plus an `agents/` dir) so no hook fires against the live tree and no probe agent is ever written
into `coordinator/agents/`. Read `modelUsage` out of `--output-format json`: when the probe runs on
Sonnet and the parent on Opus, `modelUsage["claude-sonnet-5"].outputTokens` isolates the subagent's
own output cleanly. This generalizes to any "is this agent-definition field live?" question.

Corollary for probe hygiene: a probe agent must never reach a commit or an install —
`coordinator/agents/` is the live running plugin and percolates to the OSS mirror. The throwaway
plugin dir keeps that structurally impossible rather than relying on a delete-it-afterward note.

## Model and effort are one decision

Setting `model:` and `effort:` via separate passes lets nothing revisit one
when the other changes — promoting an agent's model carries its old effort along unexamined, and
no artifact notices. The registry records the pair together with the band that
justifies it, and the gate fails when frontmatter and registry disagree. The practical effect:
changing a model turns the suite red, and the only route back to green runs through the row where
model, effort, and rationale sit side by side.

**Effort is a property of the band, not of the agent.** Agents are grouped by the shape of the
work they do and the band carries the tier. To change one agent's effort you either move it to a
different band or argue the band — both visible edits. Hand-tuning a single agent's effort is
itself a gate failure, because that is precisely how the assignment drifted before.

## The pre-flight carve-out: overturned for corpus-matching, upheld for discovery

An earlier revision of this page explicitly REJECTED folding the semantic pre-flights into `low`,
on the grounds that their false-negative rate is what the review pipeline pays for. That reasoning
was sound but untested, so it was tested.

**Measurement.** Matched pairs of `sonnet`/`low` against `sonnet`/`medium` on
prior-art-style tasks built to have headroom: a corpus whose rules are worded differently from the
claims, containing a superseded document whose rule was reversed, scope-qualified rules that only
bite under a stated condition, and conflicts visible only by reading two documents together.

- `low` and `medium` both recovered **every** conflict, including **every** composite conflict.
- `low` cost roughly **half** as much and ran in roughly **two-thirds** the wall time.
- The only divergence was on a genuinely ambiguous claim, where `low` was less stable across
  repeats — it gave three different answers in three runs where `medium` gave one.

So the carve-out is **overturned for pre-flights that match a supplied corpus** (prior art,
coverage, documented API behaviour): the tier was not buying the false-negative protection it was
credited with. It is **upheld for the one pre-flight whose corpus is discovered rather than given**
— open-ended web research, where the judgment is in deciding what to go looking for, and where
this measurement does not transfer.

Read the instability finding honestly: `low` is equally accurate on decidable questions and
noisier on genuinely ambiguous ones. That is an argument for keeping judgment-shaped work at
`medium`, not an argument for paying `medium` on matching-shaped work.

## The assignment

Applied with judgment against the C2 buckets, not mechanically. Bands and per-agent rows live in
`coordinator/agent-effort-registry.yaml`; the reasoning for each band is stated inline there.

The bands, in the order they were reasoned about:

| Band | Effort | The work |
|------|--------|----------|
| `retrieval` | `low` | Run a tool or a query, normalize the output. The contract says "no opinions." |
| `scout` | `low` | Breadth-first location. Judged on coverage, not insight. |
| `aggregator` | `low` | Verbatim, no-rewrite assembly. `parallel-review-synthesizer` is the trap here — the name says synthesizer, the contract forbids reasoning about the text, and the contract is what sets the tier. |
| `preflight-matching` | `low` | Semantic matching against a **supplied** corpus. Retiered on the 2026-07-30 measurement above. |
| `preflight-openended` | `medium` | The pre-flight whose corpus is **discovered** — open-ended web research. |
| `apply` | `low` | Applies decisions made upstream and escalates disagreement rather than resolving it. |
| `execution` | `medium` | Writes to the tree against a spec; a miss lands in the repository. |
| `review` | `medium` | Reads a diff and decides what to surface. |
| `deep-specialist` | `medium` | Deep-reads an inventory and challenges peer claims; analysis is the deliverable. |
| `persona` | `medium` | The Opus reviewer personas. Judgment is the whole deliverable. |
| `orchestrator` | `low` | Opus synthesizers and sweeps reconciling many workers into one artifact. |

Which agents sit in which band is the registry's business, not this page's. None above `medium`.

## Changing a level

- **Per-agent default** — edit the frontmatter **and the registry row together**. The frontmatter
  is what the harness reads; the registry is what records the decision. The gate fails if you move
  one without the other, deliberately: that split is the drift this mechanism exists to stop.
- **One exceptional dispatch** — the dispatch-time `effort` override is still available and is the
  right tool for a task that genuinely warrants more. It does not change the default.
- **Anything at `high`** — needs dispensation, per the ceiling above. Record why.

**Hold effort constant per agent rather than varying it per dispatch.** An effort change
invalidates the prompt-cache prefix, so churning the value costs cache re-creation on every flip.

## Negative spec

This wiki does **not** cover context-pressure estimation or the 40/47 bands — see
`context-pressure-estimation.md`. The two mechanisms share an originating plan and
nothing else. Nor does it cover prompt *content* authoring, which is `prompt-authoring.md`; the
only overlap is that wiki's note that `effort` replaced the removed `budget_tokens` lever.
