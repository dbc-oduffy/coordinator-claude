# Convention — `CONTEXT.md` Domain Glossary

> **Source:** Adopted from mattpocock's `CONTEXT.md` pattern (audit: `docs/wiki/opensource/2026-04-29-mattpocock-skills-audit.md` § High-value borrows #1). Adapted for the coordinator-claude system with the producer/consumer split as load-bearing doctrine.

---

## Why This Matters

The coordinator system has excellent "where does X live" coverage — atlas, repomap, DIRECTORY guides. What it lacked was "what does the team mean when they say Z." That gap shows up concretely: handoffs use "plugin" to mean skill, commits mix "command" and "agent," and the next session relitigates the same terminology question because no written authority existed.

`CONTEXT.md` is that authority. It is not a wiki page (those are structural/how-to). It is not a design record (those capture decisions). It is the vocabulary layer: the canonical term, one sentence of meaning, and the list of terms that caused confusion before this one was established.

The load-bearing detail that distinguishes a glossary from a word list is the `_Avoid_:` synonym line. A term without `_Avoid_:` is either genuinely clean (no corpus overloads) or hasn't been calibrated yet. A term with a populated `_Avoid_:` list is the result of real confusion being resolved. That resolution is what makes the file worth reading.

---

## Format Specification

```markdown
# CONTEXT — <Project Name>

> Domain glossary. The team's canonical terms.
> Lazy: only contains terms that have actually come up in real work.

## Terms

**<Canonical term>** — one-sentence definition.
_Avoid_: <synonym1>, <synonym2>, <synonym3>.

**<Canonical term>** — one-sentence definition.
_Avoid_: <synonym>.

## Relationships

- A <term> has 0..N <other-term>.
- A <term> belongs to exactly one <other-term>.

## Example dialogue

> Dev: "When the <term> fires, does it go through <other-term>?"
> Domain expert: "Only if the <term> is <state> — otherwise it short-circuits."

## Flagged ambiguities

- YYYY-MM-DD: "<word>" was used to mean both <X> and <Y>. Resolved: <word> now means <X>; for <Y> we say <new-term>.
```

### Notes on sections

- **`## Terms`** is required. Every `CONTEXT.md` must have it.
- **`## Relationships`** is optional. Add when terms have structural relationships that matter for correctness (e.g., "A Plugin contains 0..N Skills").
- **`## Example dialogue`** is optional. Useful when the term has subtle usage context that a definition alone doesn't convey.
- **`## Flagged ambiguities`** is optional but valuable. Records the historical confusion that a term resolved — this is institutional memory that prevents regression.

### The `_Avoid_:` line

Include `_Avoid_:` when ≥1 synonym appears in the corpus (handoffs, lessons, skills, recent commits) used to mean the canonical term. The **operational test**: grep the corpus for the candidate synonym — if it appears being used to mean this canonical concept, list it. If no such usage exists at term-creation time, omit `_Avoid_:` entirely; future sessions may add it when an overload appears.

Do NOT populate `_Avoid_:` with theoretical synonyms. A list of synonyms nobody uses is theatre, not documentation. The convergence test is the gate.

---

## Producer / Consumer Split

This split is the load-bearing doctrine. Violating it is how the "read CONTEXT.md everywhere" cargo-cult starts.

### Producers — create and update entries

Two skills produce `CONTEXT.md` entries as a side-effect of their natural work:

| Skill | When it produces |
|---|---|
| `coordinator:brainstorming` | When the PM resolves a term during design dialogue |
| `coordinator:plan` | When the plan introduces a domain term that will recur |

**Lazy-creation rule:** Neither skill scaffolds an empty `CONTEXT.md`. Creation happens on the first real term being resolved. If no term has been resolved yet in a session, the file should not exist (or should not be extended with empty/placeholder entries).

**Inline update rule:** When a term is resolved, update `CONTEXT.md` immediately — don't batch. The glossary is most valuable when it's current.

### Consumers — read entries, do not write

Skills that read `CONTEXT.md` for orientation use canonical terms in their output, but do NOT write entries. Writing is the producers' job.

Current consumers (this plan, v1):
- `coordinator:brainstorming` (reads before first PM question, if present)
- `coordinator:plan` (reads before file-mapping, if present)
- `/architecture-survey` synthesizer (reads if present; flags glossary candidates without writing)

Future consumer rollout (follow-up plan): `docs/wiki/systematic-debugging.md` (formerly the systematic-debugging skill, demoted 2026-05-06), `coordinator:debt-triage`, `coordinator:review-code`, and others. Do not add "read CONTEXT.md" to additional skills/wikis without a plan that explicitly authorizes the addition — that's how cargo-cult expansion starts.

### ADR-0001 — Silence on Absence

The single most important rule for consumers: **if `CONTEXT.md` is absent, proceed silently.** Do not flag its absence. Do not suggest creating it. Do not scaffold an empty file. Do not add a meta-finding to your output saying "CONTEXT.md was not found."

This mirrors Matt's ADR-0001 discipline. The file's absence means no terms have been resolved yet in real work. That is a valid state, not a gap. Flagging absence is the first step toward cargo-cult expansion.

---

## Lazy-Creation Discipline

This is a load-bearing rule, not a style preference. The coordinator system already has scaffold bloat. `CONTEXT.md` earns its keep only if it contains real terms from real work — not a pre-populated vocabulary dump.

**When to create:** First time a term is resolved during a brainstorming or writing-plans session that would clearly recur in future sessions. The signal is: "I'm about to write this term in the plan, and if I don't record the canonical form, the next session will use the wrong synonym."

**When NOT to create:**
- Project onboarding (even if the project is terminology-heavy)
- Start of a session before any dialogue has happened
- Any time the only reason to create it is "it would be nice to have"

**Cap on seed size:** The POC seed for this repo is ~14 terms. That's enough to demonstrate the format and resolve the historical plugin/skill/command/agent conflation. Full vocabulary inventory is cargo-cult expansion. If you find yourself wanting to add 20+ terms at once, that's a signal you're building a glossary for its own sake rather than resolving real overloads.

---

## Multi-Context Variant (Specified, Not Wired)

For repos with strongly bounded contexts (e.g., a monorepo where "deployment" means something different in the frontend context vs. the infrastructure context), the multi-context variant is:

1. Root holds `CONTEXT-MAP.md` with pointers to per-context glossaries
2. Each bounded context has its own `<subdir>/CONTEXT.md`
3. Skills detect by presence of `CONTEXT-MAP.md` (no `CONTEXT.md` at root)

This variant is documented here so a future session has a paved path. No skill code exists for it today (2026-04-29). Do not implement it until a real multi-context repo demonstrates the need.

---

## Reference

- Proof-of-concept: `~/.claude/CONTEXT.md` (the coordinator-claude repo's own glossary)
- Coordinator doctrine: `plugins/coordinator-claude/coordinator/CLAUDE.md` § Documentation and Knowledge System
- Inspiration audit: `docs/wiki/opensource/2026-04-29-mattpocock-skills-audit.md` § High-value borrows #1
- Producer skills: `coordinator:brainstorming`, `coordinator:plan`
