# Tiered Context Loading

> Spec backlink: `docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md` §W3

The EM's context window is the scarcest resource in any session. Every token consumed by exploratory lookup is a token unavailable for reasoning, reviewing, or holding the plan. Tiered context loading is the discipline that prevents that burn — not by refusing to look things up, but by requiring the cheapest adequate lookup to run before the expensive one.

---

## 1. Why Tiers Exist

The existing "Codebase Investigation" section in `coordinator/CLAUDE.md` described an investigation funnel informally — orientation cache, then wiki/atlas, then project-RAG, then grep, then scout — but never named the tiers or made the escalation order a hard requirement. The cost of skipping to a Sonnet scout when a Grep call would have answered the question is real: the scout takes up an Agent dispatch, pulls minutes of wall time, consumes a subagent context, and usually returns more context than needed — inflating the EM's window with noise.

**The goal of this doctrine is not to name what we do. It is to make the escalation order visible and measurable so that violations are detectable.**

Two behavioral levers operationalize this:

1. **Tier-4 rationale rule** — every Agent dispatch for investigation must include a one-line preamble stating what tiers 1–3 returned and why they were insufficient.
2. **Session-end telemetry** — a PostToolUse hook counts tool calls by tier; `/session-end` emits a per-session report. Trends across sessions reveal whether the doctrine is followed or drifting.

---

## 2. The Five Tiers

| Tier | Name | Budget | Surfaces |
|------|------|--------|----------|
| 0 | Boot context | ≤2K tokens, always loaded | `orientation_cache.md`, `lessons.md`, `CLAUDE.md` (auto-loaded), session memory pointers |
| 1 | Curated narrative | ≤8K tokens per fetch, on demand | `docs/wiki/`, `tasks/architecture-atlas/`, `docs/decisions/`, `docs/project-tracker.md` |
| 2 | Structured query | ≤2K tokens per query | `bin/query-records`, `mcp__*project-rag*__*`, `/workday-start` freshness table |
| 3 | Targeted code/grep | ≤4K tokens per call | `Read` of a known path, `Grep` for a specific symbol, `Glob` for discovery |
| 4 | Sonnet scout | Offloaded to subagent | `Explore`, `general-purpose` Sonnet, `deep-research:repo`, `feature-dev:code-explorer` |

**Tier 0 — Boot context** is always present before the first tool call. It costs nothing at investigation time because it was loaded at session start: `orientation_cache.md` gives the project's current state, `lessons.md` records accumulated gotchas, and session memory pointers anchor any cross-session continuity. Boot context is not a lookup tier; it is the baseline from which escalation begins.

**Tier 1 — Curated narrative** contains human-authored and distilled documents that describe how subsystems work at a level above code: wiki guides, architecture atlas pages, decision records. These are the product of previous investigation cycles — they exist precisely so future sessions don't have to re-derive the same structural knowledge from grep. A tier-1 read of `tasks/architecture-atlas/systems/auth.md` is almost always more informative than ten tier-3 Greps across the same system.

**Tier 2 — Structured query** returns precise, bounded answers from indexed data. Project-RAG tools answer symbol-shaped and subsystem-shaped questions in a single call with ≤2K tokens. `bin/query-records` answers schema-conformant queries against frontmatter records. Tier 2 is fast and narrow; its failure mode is returning nothing rather than returning wrong information.

**Tier 3 — Targeted code/grep** is direct inspection: reading a specific file, grepping for a symbol by name, globbing for a pattern. It is powerful and accurate but expensive in proportion to the answer size — a Grep on a large codebase can return hundreds of lines of context. Tier 3 is appropriate when you know where to look; it is not appropriate as a substitute for tier 1 or tier 2 when curated knowledge covers the question.

**Tier 4 — Sonnet scout** offloads open-ended investigation to a subagent. This is the correct choice when tiers 0–3 genuinely returned nothing useful and the question requires reasoning across multiple files or dynamic discovery. Tier-4 dispatches are the most expensive lookup in the funnel: they consume subagent context, take wall time, and return unstructured output that the EM must parse. They are not a default; they are a last resort.

---

## 3. Escalation Rules

**Start at tier 0. Escalate one tier at a time. Never skip.**

The most common violation is skip-to-scout: dispatching a tier-4 Explore or general-purpose agent when tier 2 or tier 3 would have answered the question. The second most common is premature-grep: jumping to tier 3 before checking whether tier 1 or tier 2 covers the topic.

### Worked Example A — "Where is X defined?"

This is a symbol-shaped question. Correct escalation:

1. **Tier 0 check:** Is the symbol mentioned in `orientation_cache.md` or `lessons.md`? If the answer is there, done.
2. **Tier 2:** Call `project_cpp_symbol` or `project_semantic_search` if project-RAG tools are available. A clean hit returns file + line in one call. Done.
3. **Tier 3:** If RAG is unavailable or returns nothing, `Grep` for the symbol name across relevant directories. Read the matching file for context. Done.
4. **Tier 4 only if:** tier 3 returned nothing (symbol doesn't exist, is generated, or lives in a location grep didn't cover) AND the question can't be answered without cross-file reasoning. Dispatch preamble required (see §7).

This question should almost never reach tier 4.

### Worked Example B — "How does subsystem X work?"

This is a subsystem-shaped question. Correct escalation:

1. **Tier 0 check:** Is there an orientation note or lesson about this subsystem?
2. **Tier 1:** Read the relevant architecture atlas page (`tasks/architecture-atlas/systems/<subsystem>.md`) or the corresponding wiki guide (`docs/wiki/<subsystem>.md`) if it exists. A good tier-1 read answers subsystem questions comprehensively without any code inspection. Done in most cases.
3. **Tier 2:** If the wiki/atlas doesn't cover the question, call `project_subsystem_profile` to get a structural summary. Done.
4. **Tier 4:** If tiers 1–3 return nothing (the subsystem is new, undocumented, or the atlas is known stale), dispatch a scout with the rationale preamble. The scout's job is to produce a tier-1 artifact (e.g., a new atlas page) so this question doesn't hit tier 4 again next session.

---

## 4. Skipping Rules

Not every lookup requires climbing from tier 0. Skipping is correct in these cases:

- **Known path, direct read:** If you already know the exact file path from context, go straight to `Read` (tier 3). Consulting tier 1 or tier 2 first would be redundant overhead.
- **Single-fact confirmation:** If you need to confirm one specific fact — a function signature, a config value — and you know roughly where it lives, tier 3 directly is correct.
- **Repeat lookup with cached answer:** If you answered this question earlier in the session and the answer is still in context, use the cached answer. Do not re-run any tier.
- **Tier 1 explicitly covers the topic:** If `orientation_cache.md` (tier 0) says "see `tasks/architecture-atlas/systems/auth.md`," jump to that file (tier 1) directly — no tier 2 needed.

The guiding test: **could a cheaper tier have answered this question?** If yes and you skipped it, that is a violation regardless of whether the answer you got was correct.

---

## 5. Tier–Tool Mapping

| Tier | Claude Code Tools |
|------|-------------------|
| 0 | Auto-loaded at session start — no tool call needed |
| 1 | `Read` of wiki, atlas, decisions, or tracker paths |
| 2 | `mcp__*project-rag*__*` tools; `Bash` invoking `bin/query-records` or `bin/lint-frontmatter` |
| 3 | `Read` of any other path; `Grep`; `Glob` |
| 4 | `Agent` with `subagent_type` in {`Explore`, `general-purpose`, `deep-research:*`, `feature-dev:code-explorer`} |

Note: `Bash` calls that are not `bin/query-records` or RAG-adjacent fall outside the tier classification and are not tracked. Telemetry ignores them.

---

## 6. Failure Modes

**Skip-to-scout (most common).** Dispatching a tier-4 agent when tier 2 or tier 3 would have answered the question. Symptoms: scout returns a brief that could have come from a single Grep; tier-usage report shows tier4 >> tier2+tier3; dispatch prompt contains no rationale preamble. Fix: run the tier-4 rationale rule check before every Agent dispatch.

**Redundant tier.** Re-running a tier after it already returned a clean answer. The most common variant is re-grepping after a tier-2 RAG call returned the symbol location. Wastes tokens without adding information.

**Premature grep.** Jumping to tier 3 before checking whether tier 1 or tier 2 covers the topic. Symptoms: Grep is the first non-tier-0 tool call in the session; wiki/atlas are never consulted; questions like "how does X work" are answered by grep aggregation rather than structured knowledge. Fix: make tier-1 reads the default first step for any subsystem question.

**Stale tier-1 bypass.** Skipping tier 1 because the wiki/atlas is "probably stale." Stale RAG and stale atlas still cover the structural skeleton; grep covers none of it. Use the stale artifact first, then fill gaps with tier 3. Staleness is a signal to update the artifact after the session, not a reason to skip it during.

---

## 7. Tier-4 Rationale Rule

Every `Agent` dispatch where `subagent_type` is in `{Explore, general-purpose, deep-research:*, feature-dev:code-explorer}` **must** include the following preamble as the first line of the dispatch prompt:

```
Tier 1-3 attempted: <what each returned>; insufficient because <reason>.
```

Examples:

```
Tier 1-3 attempted: atlas has no page for the payments subsystem, RAG returned no matches for PaymentProcessor, grep found 0 results in src/payments/; insufficient because the module may live under a non-obvious path.
```

```
Tier 1-3 attempted: wiki guide covers auth at a high level, RAG symbol search returned AuthManager:line 42, Read confirmed it's a thin wrapper; insufficient because the actual auth logic is in the middleware chain and the atlas doesn't map it.
```

The rationale preamble does three things: it forces the EM to verify that tiers 1–3 were actually tried (not assumed to return nothing), it gives the scout useful negative context (what was already checked), and it produces a visible artifact that Patrik and the review-integrator can flag if the rationale is implausible.

Dispatches missing the preamble are flagged as `rationale_present: false` by the telemetry hook (see §8).

---

## 8. Telemetry

`~/.claude/plugins/coordinator-claude/coordinator/hooks/scripts/track-tier-usage.sh` runs as a PostToolUse hook on every tool call matching `Read|Grep|Glob|Bash|Agent|mcp__.*`. It classifies each call into a tier and increments per-session counters persisted to:

```
~/.claude/projects/<project-slug>/tier-usage/<session_id>.json
```

JSON shape:
```json
{
  "session_id": "...",
  "started_at": "ISO-date",
  "counts": { "tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0 },
  "tier4_dispatches": [
    { "ts": "...", "subagent_type": "...", "rationale_present": true }
  ]
}
```

At `/session-end` and `/workday-complete`, the session's tier-usage JSON is read and a one-line report is emitted before the wrap-up:

```
Tier usage this session: tier1=N tier2=N tier3=N tier4=N (X tier-4 missing rationale)
```

This report is the data that prevents W3 from being ceremonial. If after several sessions the counters show tier4 >> tier2+tier3 or consistent missing-rationale counts, the doctrine is not being followed — revise the enforcement, not the doctrine.
