# Tiered Context Loading

The EM's context window is the scarcest resource in any session. Every token consumed by exploratory lookup is a token unavailable for reasoning, reviewing, or holding the plan. Tiered context loading is the discipline that prevents that burn — not by refusing to look things up, but by requiring the cheapest adequate lookup to run before the expensive one.

---

## 1. Why Tiers Exist

Coordinator doctrine has long described an investigation funnel informally — orientation cache,
then wiki/atlas, then project-RAG, then grep, then scout — but never named the tiers or made the
escalation order a hard requirement. The cost of skipping to a Sonnet scout when a grep call (via Bash) would have answered the question is real: the scout takes up an Agent dispatch, pulls minutes of wall time, consumes a subagent context, and usually returns more context than needed — inflating the EM's window with noise.

**The goal of this doctrine is not to name what we do. It is to make the escalation order visible and measurable so that violations are detectable.**

The behavioral lever is the **tier-4 rationale rule**: every Agent dispatch for investigation must include a one-line preamble stating what tiers 1–3 returned and why they were insufficient. (An earlier telemetry hook counted tier usage per session across roughly a thousand sessions before it was removed for measuring the wrong agent population — see §7 for what the measurement got wrong.)

---

## 2. The Five Tiers

| Tier | Name | Budget | Surfaces |
|------|------|--------|----------|
| 0 | Boot context | always loaded, ~9.9K + ~7.1K tokens measured (was claimed ≤2K — corrected, see below) | `orientation_cache.md`, `CLAUDE.md` (auto-loaded), session memory pointers |
| 1 | Curated narrative | ≤8K tokens per fetch, on demand | `docs/wiki/`, `docs/architecture/`, `docs/decisions/` |
| 2 | Structured query | ≤2K tokens per query | `bin/query-records`, `mcp__*project-rag*__*`, `/workday-start` freshness table |
| 3 | Targeted code/grep | ≤4K tokens per call | `Read` of a known path, `grep` (via Bash) for a specific symbol, `find` (via Bash) for discovery |
| 4 | Sonnet scout | Offloaded to subagent | `Explore`, `general-purpose` Sonnet, `coordinator:repo-scout`, `feature-dev:code-explorer` |

**Tier 0 — Boot context** is always present before the first tool call. It costs nothing at investigation-*decision* time because it was loaded at session start: `orientation_cache.md` gives the project's current state and session memory pointers anchor any cross-session continuity. Boot context is not a lookup tier; it is the baseline from which escalation begins.

**The imperative form of the Tier 0 rule: silently read `state/orientation_cache.md` before your first tool call.** In many installs that read is mechanized — a SessionStart hook injects the file's contents into context before you act, so by the time you see this doctrine the read has already happened — but the underlying obligation is the EM's, not the hook's: if a session ever lacks the hook (a stripped-down harness, a future refactor that drops it), the fallback is to read the file yourself, silently, before any other tool call, not to skip orientation because no automation did it for you. **Do not pair this with also scanning `state/lessons/` at boot** — that queue is NOT Tier 0; see the negative-spec below (`**state/lessons/ is NOT Tier 0.**`) for why and what to reach for instead.

**Correction — the "≤2K tokens" budget above was wrong, not a typo.** This table
originally claimed Tier 0 fit in ≤2K tokens. Actually measuring the always-loaded doctrine
surfaces on a maximalist install found the always-on CLAUDE.md-class surfaces running to roughly
9-10K tokens plus another 7K tokens from the user-level CLAUDE.md — 3.5x-5x the number this file
used to assert. The figures are heuristic-derived (a ~4-chars/token approximation) — directional,
not exact tokenizer parity; do not treat them as more precise than that. **They are also a
snapshot of a moving target, not a constant to hardcode against** — the always-loaded doctrine
surface was, at the time of this correction, under active restructuring, and has since split by
audience into an all-agents surface and an EM-only channel. A future reader relying on this
section should re-run the oracle against the current always-loaded surfaces rather than trust
either historical number above as current.

**What changed and what didn't.** The correction is to the *budget claim* only — Tier 0 keeps its
placement and its ordering semantics (cheapest-first, zero escalation cost, always loaded before
the first tool call) unchanged, because that placement was never wrong: these files structurally
*are* always-on with no lookup cost at decision time. It was the "≤2K" figure describing their
size that was aspirational rather than measured.

**`state/lessons/` is NOT Tier 0.** It is a capture queue processed by `/learn-lessons` (queue → wiki promotion); load-bearing lessons live in `docs/wiki/` and are surfaced on demand by the prior-art-checker pre-flight when relevant to a plan. Reading the queue on every boot is wasteful — most entries are future work for `/learn-lessons`, not in-the-moment guidance. The EM does NOT read the queue directly as a Tier-2 lookup either; the prior-art-checker is the mechanism. If you find yourself reaching for the lessons queue during planning, run prior-art-checker (which reads it for you and surfaces relevant entries) — or invoke `/learn-lessons`, the only skill that consumes the raw queue end-to-end.



Files Tier-0-loaded at every session start (orientation_cache, MEMORY.md) MUST be bounded. Unbounded accumulators silently inflate boot context.

- **`orientation_cache.md`** is regenerated from a fixed schema by `regenerate-orientation-cache` and verified by `verify-orientation-cache-sync.py`. **Hard ceiling: 35 lines.** The schema permits only seven sections (`Project`, `Trust caveats`, `Counters`, `Active workstreams`, `Rechecks due ≤7 days`, `Branch`, `Pinboard`); all are either static, derived-from-disk, or absent. **No free-form prose anywhere.** Schema drift fails the verifier at `/update-docs` Phase 11b. Writer tiers: ceremony writers (`/workday-start`, `/update-docs`) own full regen; mid-session writers (`/workstream-complete`, `/handoff`) may only write a single line to `## Pinboard` (one-slot, overwrite-or-omit, auto-cleared on next ceremony). The `## Trust caveats` section is filesystem-detector-driven (e.g. presence of any `*.uproject` in repo triggers a UE training-data-trust warning instructing the EM and its delegates to verify via `mcp__project-rag__*` or dispatch the Game Dev Reviewer) — content is owned by the routine, not the writer.
- **MEMORY.md** trims via auto-memory consolidation.

Quarterly verify file sizes.

**Tier 1 — Curated narrative** contains human-authored and distilled documents that describe how subsystems work at a level above code: wiki guides, architecture atlas pages, decision records. These are the product of previous investigation cycles — they exist precisely so future sessions don't have to re-derive the same structural knowledge from grep. A tier-1 read of `docs/architecture/systems/auth.md` is almost always more informative than ten tier-3 greps across the same system.

**Documentation index pointers.** Tier 1's surfaces have known maintainers and known indexes — know which pointer answers which question before falling through to tier 2/3: `docs/README.md` is the master index, maintained by `/update-docs`; `docs/wiki/` is distilled by `/distill`, indexed by `DIRECTORY_GUIDE.md`; `docs/plans/` is the canonical plan location; `docs/research/` holds `/deep-research` (deep-research pipeline) output; `CONTEXT.md` is the domain glossary — canonical vocabulary, project-coined synonyms forbidden. Reach for the index before re-deriving structural knowledge that a maintained pointer already answers.

**Tier 2 — Structured query** returns precise, bounded answers from indexed data. Project-RAG tools answer symbol-shaped and subsystem-shaped questions in a single call with ≤2K tokens. `bin/query-records` answers schema-conformant queries against frontmatter records. Tier 2 is fast and narrow; its failure mode is returning nothing rather than returning wrong information.

**Tier 3 — Targeted code/grep** is direct inspection: reading a specific file, grepping for a symbol by name, globbing for a pattern. It is powerful and accurate but expensive in proportion to the answer size — a grep call on a large codebase can return hundreds of lines of context. Tier 3 is appropriate when you know where to look; it is not appropriate as a substitute for tier 1 or tier 2 when curated knowledge covers the question.

**Tier 4 — Sonnet scout** offloads open-ended investigation to a subagent. This is the correct choice when tiers 0–3 genuinely returned nothing useful and the question requires reasoning across multiple files or dynamic discovery. Tier-4 dispatches are the most expensive lookup in the funnel: they consume subagent context, take wall time, and return unstructured output that the EM must parse. They are not a default; they are a last resort.

---

## 3. Escalation Rules

**Start at tier 0. Escalate one tier at a time. Never skip.**

The most common violation is skip-to-scout: dispatching a tier-4 Explore or general-purpose agent when tier 2 or tier 3 would have answered the question. The second most common is premature-grep: jumping to tier 3 before checking whether tier 1 or tier 2 covers the topic.

### Worked Example A — "Where is X defined?"

This is a symbol-shaped question. Correct escalation:

1. **Tier 0 check:** Is the symbol mentioned in `orientation_cache.md`? If the answer is there, done.
2. **Tier 2:** Call `project_cpp_symbol` or `project_semantic_search` if project-RAG tools are available. A clean hit returns file + line in one call. Done.
3. **Tier 3:** If RAG is unavailable or returns nothing, `grep` (via Bash) for the symbol name across relevant directories. Read the matching file for context. Done.
4. **Tier 4 only if:** tier 3 returned nothing (symbol doesn't exist, is generated, or lives in a location grep didn't cover) AND the question can't be answered without cross-file reasoning. Dispatch preamble required (see §7).

This question should almost never reach tier 4.

### Worked Example B — "How does subsystem X work?"

This is a subsystem-shaped question. Correct escalation:

1. **Tier 0 check:** Is there an orientation note about this subsystem in `orientation_cache.md`?
2. **Tier 1:** Read the relevant architecture atlas page (`docs/architecture/systems/<subsystem>.md`) or the corresponding wiki guide (`docs/wiki/<subsystem>.md`) if it exists. A good tier-1 read answers subsystem questions comprehensively without any code inspection. Done in most cases.
3. **Tier 2:** If the wiki/atlas doesn't cover the question, call `project_subsystem_profile` to get a structural summary. Done.
4. **Tier 4:** If tiers 1–3 return nothing (the subsystem is new, undocumented, or the atlas is known stale), dispatch a scout with the rationale preamble. The scout's job is to produce a tier-1 artifact (e.g., a new atlas page) so this question doesn't hit tier 4 again next session.

---

## 4. Skipping Rules

Not every lookup requires climbing from tier 0. Skipping is correct in these cases:

- **Known path, direct read:** If you already know the exact file path from context, go straight to `Read` (tier 3). Consulting tier 1 or tier 2 first would be redundant overhead.
- **Single-fact confirmation:** If you need to confirm one specific fact — a function signature, a config value — and you know roughly where it lives, tier 3 directly is correct.
- **Repeat lookup with cached answer:** If you answered this question earlier in the session and the answer is still in context, use the cached answer. Do not re-run any tier.
- **Tier 1 explicitly covers the topic:** If `orientation_cache.md` (tier 0) says "see `docs/architecture/systems/auth.md`," jump to that file (tier 1) directly — no tier 2 needed.

The guiding test: **could a cheaper tier have answered this question?** If yes and you skipped it, that is a violation regardless of whether the answer you got was correct.

---

## 5. Tier–Tool Mapping

| Tier | Claude Code Tools |
|------|-------------------|
| 0 | Auto-loaded at session start — no tool call needed |
| 1 | `Read` of wiki, atlas, decisions, or tracker paths |
| 2 | `mcp__*project-rag*__*` tools; `Bash` invoking `bin/query-records` or `bin/lint-frontmatter` |
| 3 | `Read` of any other path; `grep` via `Bash`; `find` via `Bash` |
| 4 | `Agent` with `subagent_type` in {`Explore`, `general-purpose`, `coordinator:research-*`, `feature-dev:code-explorer`} |

Note: `Bash` calls that are not `bin/query-records` or RAG-adjacent fall outside the tier classification and don't count toward escalation accounting.

---

## 6. Failure Modes

**Skip-to-scout (most common).** Dispatching a tier-4 agent when tier 2 or tier 3 would have answered the question. Symptoms: scout returns a brief that could have come from a single grep call; dispatch prompt contains no rationale preamble. Fix: run the tier-4 rationale rule check before every Agent dispatch.

**Redundant tier.** Re-running a tier after it already returned a clean answer. The most common variant is re-grepping after a tier-2 RAG call returned the symbol location. Wastes tokens without adding information.

**Premature grep.** Jumping to tier 3 before checking whether tier 1 or tier 2 covers the topic. Symptoms: a grep call is the first non-tier-0 tool call in the session; wiki/atlas are never consulted; questions like "how does X work" are answered by grep aggregation rather than structured knowledge. Fix: make tier-1 reads the default first step for any subsystem question.

**Stale tier-1 bypass.** Skipping tier 1 because the wiki/atlas is "probably stale." Stale RAG and stale atlas still cover the structural skeleton; grep covers none of it. Use the stale artifact first, then fill gaps with tier 3. Staleness is a signal to update the artifact after the session, not a reason to skip it during.

**Investigation funnel.** Build error stream is the contract (compat docs under-report drift 2-3×). Grep every writer of a path before codifying its role; runtime contract change → grep every assertion. **Spec backlinks outlive their cited spec** — confirm the file exists (check `archive/`) before quoting.

---

## 7. Tier-4 Rationale Rule

Every `Agent` dispatch where `subagent_type` is in `{Explore, general-purpose, coordinator:research-*, feature-dev:code-explorer}` **must** include the following preamble as the first line of the dispatch prompt:

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

The rationale preamble does three things: it forces the EM to verify that tiers 1–3 were actually tried (not assumed to return nothing), it gives the scout useful negative context (what was already checked), and it produces a visible artifact that the Staff Engineer and the review-integrator can flag if the rationale is implausible.

The rationale preamble is a writing discipline, not an enforced gate — no hook blocks dispatch when it is missing. The earlier telemetry attempt tried to measure compliance via regex on dispatch prompts and conflated investigation scouts with the rest of the `Agent` tool surface — a mismeasurement of the wrong agent population, not a compliance signal worth trusting. Future enforcement should either block dispatch on a missing preamble or not exist as compliance theater.

---

## 8. Scout Deliverable Format — Surface Premises as Questions

Tier-4 scouts that recommend "defer X" or "skip Y for now" are emitting hypotheses about scope, not verdicts. The dispatch brief MUST require the scout to surface each defer with its unverified premise inline:

```
## Recommendations
- Defer migration of `<module>` assuming the consumer count is ≤2 (UNVERIFIED — confirm with `grep`).
- Skip validation of `<surface>` assuming sibling repo X owns the contract (UNVERIFIED — check repo-registry).
```

Without premise-naming, defers age into mystery cuts: the next session re-investigates from zero because nothing in the artifact says *why* the cut was safe. Premise-named defers either resolve (premise confirmed, defer ratified) or escalate (premise falsified, work folded back in). Either way the cycle closes.

The pattern composes with the Tier-4 rationale rule in §7 — the rationale preamble explains why tiers 1–3 were insufficient *for the question*; the premise-naming requirement explains the unverified assumptions *in the answer*.

---

## 9. Quarantine-Read Mechanics for Tier-4 Briefs

When a scout dispatch deliberately restricts the read surface — "investigate <feature> but DO NOT load <other-file>", or "summarize section N of a long artifact" — the brief must specify *how* the scope restriction works at the tool level, not just state it as a "skip" instruction:

- **Section-scoped reads use `Read` with `offset:` + `limit:`** to load only the relevant slice. Telling the scout "ignore the rest of the file" without `offset`/`limit` invites accidental full-file reads that blow the scout's context budget and contaminate the analysis with off-topic content.
- **Post-write scan pattern.** When the scope restriction is "do not touch file X," a post-`DONE` `git status --porcelain -- <restricted-paths>` is what surfaces a modification as a quarantine event (see `scout-and-dispatch-discipline.md` § Scout output discipline).
- **Quarantine reads of contaminated output.** When inspecting a rogue subagent's quarantined output (see scout-and-dispatch-discipline § Quarantine rogue subagent output), use `Read` with `offset`/`limit` over the quarantined copy — do not pipe through `cat` or load the whole rogue file into EM context. The whole point of quarantine is to keep the contamination off the EM's reasoning surface.

Without explicit mechanics, "skip this file" instructions decay into trust-the-scout and produce the contamination they were meant to prevent.

---

## 10. Existing Logs Often Answer "Add A Probe" Questions Without A Rebuild

Before drafting a plan that adds a diagnostic probe / log line / counter to investigate a question, Tier-0/1 should grep existing logs first. Build systems (UE's `UnrealBuildTool`, MSBuild, Cargo) and runtime daemons routinely already emit the data the probe would gather — verbose-log flags, `--diagnostics`, profiler outputs, crash dumps, structured event logs. A 30-second grep over the latest log file answers many probe-shaped questions without authoring a single line of new instrumentation.

**Heuristic:** when the question is "why did X happen / what value did Y take / which path was taken at branch Z," check `Saved/Logs/`, `target/debug-logs/`, `.cache/`, the tool's own home-config logs directory, or the equivalent for the tooling in play *before* planning instrumentation. Rebuilds-for-instrumentation are time-expensive (a live-editor rebuild can crash the session entirely for some toolchains; native builds churn caches); the log-grep alternative is free. Add the rebuild path only after the existing logs are confirmed silent on the question.

---

## Procedural-Overrides-Declarative Comprehension Trap

In agent comprehension, procedural-overrides-declarative when the two disagree — declarative doctrine (CLAUDE.md, wiki rule) loses to procedural surface context (a step-by-step script, a skill body) in practice. Verify procedural surfaces against declarative doctrine before trusting what the procedural surface narrates. Apply: when a procedural surface (skill step, hook script, install procedure) conflicts with declarative doctrine (CLAUDE.md rule, wiki principle), treat the procedural surface as drift and resolve it explicitly — don't silently adopt the procedural behavior. (doe_escalation: the doctrine owner should assess whether procedural-surface validation belongs as a tip in CLAUDE.md § Verification Before Done.)

## 11. The meta-repo's `projects/` directory is the canonical per-folder activity record

When a skill or audit needs **cross-project recency** ("which repos has the operator touched lately / in what order"), `${CLAUDE_HOME:-$HOME}/.claude/projects/` is the canonical source — consult it before falling back to heuristic dev-folder scans (globbing drive letters, walking guessed dev directories, `git log` across guessed paths). The directory holds one subdirectory per project Claude Code has run in; the subdirectory **name is the project's filesystem path with separators encoded** — every separator, and a Windows drive colon, collapses to `-`, so a drive-rooted path under a user's home encodes to a name of the form `<drive>--Users-<user>-<repo>`, and its **mtime ≈ last-activity recency** for that project. A single `ls -dt "${CLAUDE_HOME:-$HOME}/.claude/projects/"*/` gives a recency-ranked list of every folder the operator has actually worked in — far more reliable than guessing which dev folders are "active" by scanning the filesystem. This is a Tier-0/Tier-3 lookup (a known path, direct read), not a scout dispatch. Decode the path-as-name to recover the real project root.
