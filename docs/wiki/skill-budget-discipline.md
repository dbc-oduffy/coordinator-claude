# Skill Budget Discipline

> Spec backlinks: `archive/specs/2026-05-06-skill-budget-phases-bcd.md`, `archive/specs/2026-05-06-skill-budget-structural-cleanup.md`.

---
provenance:
  kind: distilled-spec
  source_plans:
    - path: docs/plans/2026-05-06-skill-budget-phases-bcd.md
      last_verbose_sha: 813075af33e4add9d0c1fc5f5c7b8bbc35a1865a
    - path: docs/plans/2026-05-06-skill-budget-structural-cleanup.md
      last_verbose_sha: c7bfce032fdca4437e2bbfa43e1405b4b79f7ebb
    - path: docs/plans/2026-05-06-phase-e-learn-lessons.md
      last_verbose_sha: 400504b33d6b3bb0a61e4ac9eed7d22012b1b346
  distilled_run: 2026-05-08-1032
---

Every loaded skill description is **always in context** — length compounds into aggregate token budget. Skill budget discipline is the practice of keeping the always-on description budget minimal so context remains available for actual work.

---

## Why Skill Budget Matters

The Claude Code harness loads all enabled skill descriptions at every session start, unconditionally. An estimated 88 enabled skills at ~200-600 tokens each would put constant overhead in the 17,000–52,000 token range — this figure is an unvalidated estimate, not a measurement.

**The cap is real, observed in practice, and configurable — this is not in question.** Skill
descriptions compete for a bounded, adaptive listing budget (documented as roughly 1% of the
context window by default, configurable upward), and past that budget not everything is carried.

> **PM first-hand observation, logged 2026-07-27, not reproduced from documentation.** Anthropic's
> tooling has directly flagged a coordinator-claude skill catalog as having too many skills, with
> the stated consequence that only the most-used `n` skills would load, and "raise the cap"
> offered as the remedy. This is a first-hand human observation of product behaviour, clear and
> distinct in the PM's memory — it was never written down at the time, and its absence from the
> written record is exactly what let a later EM treat "not in the docs" as "did not happen" and
> wrongly retract a true claim (see `a129878e`'s commit message for that incident). Logging it
> here closes that gap. **This first-hand flag was a cause of the 2026-05-06/07 super-skill
> consolidation** — see `docs/wiki/super-skill-architecture.md § Skill Consolidation` for the
> causal record alongside that consolidation's already-documented stated causes.

Ordering favours **frequently-invoked** skills, so a
rarely-used skill is the one genuinely at risk under pressure.

> **PM first-hand observation, logged 2026-07-27, not reproduced from documentation (sibling
> surface).** Anthropic's tooling separately flags a `CLAUDE.md` exceeding roughly 40 KB as too
> big. The cap **can be raised** — it is not fixed — but it exists and it fires; this is directly
> observed, not inferred. The PM's operative stance, recorded alongside it: a raisable cap is
> **not an expense account to be spent down to the limit** just because the ceiling can be moved.
> No specific byte threshold beyond "roughly 40 KB" and no mechanism are claimed here — only that
> the flag exists and fires in practice.

The Claude Code 40 KB CLAUDE.md flag is the same shape of constraint as the skill-count cap
above, on a sibling surface.

**The strongest in-repo evidence is the 2026-05-06/07 super-skill consolidation itself**, which
cut the catalog from 30 to 26 user-facing skills in one pass
(`archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md`,
`coordinator/docs/wiki/super-skill-architecture.md § Skill Consolidation`). Read those records
carefully, though: they document the consolidation's stated reasons as folding thin
pass-through skills into their only callers and enforcing a description-character-budget CI gate
— they do not themselves state "too many skills, only the top-`n` load" as the trigger. That
specific causal claim is the first-hand observation above, not something this repo's own spec
traces back to. The two accounts are compatible (a character/count-driven load cap is exactly the
kind of pressure a thin-skill-folding pass would relieve) but are not the same claim, and this wiki
should not conflate them.

**Two things remain genuinely UNSETTLED, and should be treated as open rather than asserted either
way:**

1. **Whether the specific "~60-70 skills" figure was ever a real measured threshold or someone's
   estimate.** It has no traceable source in this repo's docs or specs — grepping the archived
   skill-budget specs and audits turns up character-budget mechanics, not a skill-count number.
   Treat any specific count as unvalidated until a fresh probe pins one down.
2. **Whether an over-budget skill loses only its description or drops from the listing entirely.**
   The documented mechanism (this repo's own reading of Claude Code's skill-listing behavior)
   says descriptions drop before names, so a skill stays name-visible even under pressure — a
   skill never becomes literally invisible, only harder to find by symptom/keyword search instead
   of name recall. But the specific warning Anthropic's tooling surfaced for this repo's skill
   count described the *skill itself* being excluded from what loads, not merely its description
   — that is a stronger claim than "description drops, name survives."

   **Partially settled, not resolved.** A spike
   (`docs/research/spike-verdicts/2026-07-27-boot-context-envelope.md`, corroborated by
   `state/audits/2026-07-27-boot-description-census.md`) observed all 62 skill-listing entries at
   this repo's current catalog size intact by name. The 62 figure is a live-tool-listing
   self-observation made at spike time, not a number the census itself reports — the census
   separately enumerates on-disk source files by a different method and corpus (35 `SKILL.md`
   dirs, 31 agents, 45 commands; no combination of those sums to 62). Its corroboration is of the
   underlying catalog-composition picture, not a reproduction of the 62 count. Truncation, where
   it occurred, was
   character-budget-based and adaptive, trimming descriptions rather than dropping names, so
   discovery degrades gracefully rather than failing outright. That evidence does not refute the
   PM's first-hand account above; it is consistent with it, because the spike observed the
   *current* count and the PM's account describes what tooling flagged at a count large enough to
   trip a warning. Whether the stronger claim — a skill excluded outright, not just
   description-trimmed — ever fires is exactly item 1's open question asked from a different
   angle: it can only bite past a count threshold nobody has pinned down. The two items stay
   coupled until item 1 resolves.

Until item 1 resolves, the practical guidance is unchanged either way: keep descriptions concise
and prune near-zero-invocation skills, because both accounts agree that's what protects budget for
the skills most likely to need to be found.

Key finding from the 2026-05-06 audit: **many skills had zero invocations over 30 days** — they were pure description-budget load with no behavioral value. The audit identified ~30 candidates for removal, demotion, or description trim, with an estimated 6-8K token savings.

---

## Utilization Audit Findings (30-day window)

**Heavy (≥25 invocations/30d):** coordinator:pickup (602), coordinator:handoff (425), coordinator:workstream-complete (366), coordinator:update-docs (66), coordinator:merging-to-main (53), coordinator:workday-start (44), coordinator:mise-en-place (31)

**Zero invocations (methodology skills — passive doctrine burden):** requesting-code-review, receiving-code-review, dispatching-parallel-agents, verification-before-completion, test-driven-development, stuck-detection, systematic-debugging, skill-discovery

(Note: requesting-code-review and skill-discovery have been deleted; only systematic-debugging remains as an active passive-doctrine skill.)

Caveat: cross-machine sessions undercounted 30-50%; passive-doctrine skills may be referenced by agents without explicit invocation.

---

## Phase A Cleanup Actions (commit e40441f)

PM-authorized cleanup:
- Disabled 5 unused official-marketplace plugins globally
- Added skillOverrides to hide 4 builtins, name-only 5 builtins + 3 passive-doctrine skills
  - The four hidden builtins (`review`, `security-review`, `simplify`, `init`) plus `deep-research` (gated on plugin presence) are **install-seeded** — claude-klabauter `coordinator/bin/install-health/seed-skill-overrides.sh` (orchestrator drop-in) → claude-klabauter `coordinator/bin/seed-skill-overrides.py` merges them into `~/.claude/settings.json` idempotently on every `coordinator:install`, superseding the hand-curated Phase-A state. See `docs/wiki/claude-code-platform-gotchas.md` § Bundled-skill collisions.
- Deleted 4 dead coordinator skills (lessons-trim, using-git-worktrees, skill-discovery, inspiration-audit)
- Demoted 3 lifecycle subroutines (tracker-maintenance, handoff-archival, atlas-integrity-check) out of skill surface — /update-docs can still Read them but they don't register as skills
- Removed /update-docs tail-call from /mise-en-place

**Rejected:** /doctor cluster (PM: "bug-sweep is not a doctor mode"); session-end / workday-complete merge (PM: distinct cadences).

---

## Description Budget Hard Limit

The convention: **skills and commands ≤100 bytes**, agents on a computed cap (below), custom via a `description-budget:` frontmatter override. The earlier ≤150 / PM-gated ≤175 tiers are superseded.

**Where the budget binds: `coordinator/tests/test_boot_description_envelope.py`, in this repo's pytest tier.** It covers all three boot-resident description surfaces, parses frontmatter with `yaml.safe_load`, and carries three assertions.

**1. A per-file cap — computed, not flat, for agents.** A skill or command is invoked *by name* (`/plan`), so the name does most of the routing and the description only disambiguates; 100 bytes is generous. An agent is picked out of a flat roster from descriptions alone, with no typed name to go on, so the room it needs is a function of how confusable it actually is. The cap is derived from the roster: a floor, plus an allowance per agent sharing a hyphen-separated name token, plus a persona allowance detected by the mandatory "Personas are Opus-only." clause rather than a hand-kept list. So `enricher` — which collides with nothing — gets 140 B, while `research-worker` — which collides with four other `research-*` agents and three other `*-worker` agents, and must therefore spell out both its tier and its pipeline — gets 260 B. A flat cap taxed the isolated agent and starved the crowded one simultaneously; nobody has to remember the rule because the roster computes it.

**2. A per-surface aggregate byte ratchet.** A per-file cap alone permits every file in a 33-file roster to creep a hundred bytes and calls it compliance. Only a total catches that. The baseline is shrink-only, and the regeneration path refuses to write any value that would loosen it.

**3. A median fill-ratio ceiling — the anti-cut-to-fit assertion.** This is the one worth understanding, because it encodes a behavioural failure rather than a size limit. A bare cap defines success as "under", so 99 bytes scores exactly the same as 40, and the observed behaviour is to shave words until the number passes rather than to write something punchy. The result is a corpus clustered just below the line: every entry technically compliant, none of them good. So the test asserts the shape of the distribution, not only its maximum — **the median file must fill no more than 70% of its own cap**. One entry that genuinely needs its full room is fine; a corpus that has collectively spent its headroom is not. Measuring *fill ratio* rather than raw bytes is what lets this work on the agent surface, where 200 B is disciplined for a crowded `research-*` agent and profligate for `enricher`.

The rule this discharges — "a description should be a tweet, not a paragraph trimmed to tweet length" — previously existed only as an exhortation, and exhortation is exactly what a corpus clustered at 97/100 bytes proves does not work.

**The weekly `check-description-length` advisory is NOT that gate, and never measured coordinator at all.** It runs advisory-only in `/workweek-complete` and scans `$HOME/.claude/plugins/**/SKILL.md`. Because coordinator's plugin source is resolved live from the DoE-claude tree via `--plugin-dir`, that path contains zero coordinator skills — it has been reporting on a handful belonging to an unrelated plugin. It also extracts frontmatter with a line-anchored regex and warns-and-skips multi-line descriptions, so the largest descriptions were precisely the ones it could not see. It retains value only for plugins that genuinely install under `~/.claude/plugins/`; do not cite it as coordinator's enforcement.

The general lesson, which cost a full budget campaign to learn: a validator pointed at a path the artifacts do not occupy reads identically to a passing one. Enforcement is proven by a red run on a deliberately-broken input, never by the validator's existence.

---

## Per-Project Plugin Gating

Skills are disabled globally and re-enabled per-project via settings.json `enabledPlugins` array:
- game-dev, web-dev, data-science, example-game-repo-control, example-game-repo-docs: disabled globally on non-UE-project machines
- coordinator: always enabled globally
- Per-project override: add to project settings.json `enabledPlugins`

On Windows with example-game-repo-flavored plugins, cygpath translation and node-merge fallback are required because plugin paths use MSYS-style separators.

---

## `skillOverrides` Cannot Reach Plugin Skills — Including Every Coordinator Skill

**Read this before planning any work that assumes coordinator skills can be collapsed or hidden via settings. They cannot, in CLI 2.1.220.** This section exists because the assumption is reasonable, the documentation supports it, and it is wrong.

`~/.claude/settings.json` `skillOverrides` maps a skill name to one of `on` / `name-only` / `user-invocable-only` / `off`, documented as *"Per-skill listing overrides keyed by skill name."* It demonstrably works — five bundled skills set `off` are absent from the listing a session receives. The inference that it therefore works on `coordinator:*` skills does not hold, and no amount of key-format guessing fixes it.

The resolver early-returns before ever consulting the setting:

```js
function qFe(e){
  if((e.type==="local-jsx"||e.type==="local")&&uH_.has(e.name)) return ...;
  if(e.type!=="prompt" || e.source==="plugin") return "on";   // <-- every plugin skill, unconditionally
  let t=eo(), r=t.skillOverrides,
      n = r?.[e.name] ?? (e.unqualifiedName!=null ? r?.[e.unqualifiedName] : void 0) ?? "on";
  ...
}
```

Coordinator skills load with `source:"plugin"` (the plugin is resolved via `--plugin-dir`, which does not change the source classification). So they hit `return "on"` and the settings entry is never read. This is not a key-naming problem: neither `coordinator:plan` nor a bare `plan` nor any other spelling reaches the lookup, because the lookup is unreachable. The same `qFe` is what the listing renderer calls to decide whether to emit `- name` or `- name: description`, so `name-only` cannot apply either — the restriction covers rendering and invocation-gating alike.

Empirically confirmed twice before the code was read: setting overrides on both `coordinator:*` and `project-rag:*` entries changed a freshly-booted session's listing not at all.

**The only surviving lever is the aggregate char budget, and it does not select per skill.** `skillListingBudgetFraction` (default `0.01`, a fraction of the context window in chars) and the `SLASH_COMMAND_TOOL_CHAR_BUDGET` env var set a ceiling; when the listing exceeds it, the renderer collapses descriptions to bare names until it fits. Two properties make this a poor substitute for what we wanted:

- **Selection is usage-ranked, not authored.** Surviving descriptions are chosen by a recency-weighted usage score, so which skills keep their descriptions varies per machine and drifts over time. You cannot pin a specific skill open.
- **It is a cliff, not a dial.** Below the threshold nothing collapses; above it, collapse order is out of our hands.

**The `sizing` dependency, recorded here because it outlives whatever mechanism eventually exists.** Coordinator is not a menu system — it has one opinionated spine (`sizing → plan → review → handoff → {session boundary} → pickup → execute-plan → workstream-complete`) whose skills name each other, so exactly one skill has to be discoverable from cold: `sizing`, the lobby, which must match arbitrary unstructured PM wording. Everything downstream is reached by the skill before it or typed by name. **If a future harness version makes per-skill collapsing possible, collapse everything except `sizing` — and do not collapse `sizing` itself.** `plan` currently carries harness trigger phrases under a `description-budget: 260` override, granted because the EM bypassed the skill twice in thirty days; collapsing `plan` is safe only because `sizing` routes to it. Collapse `sizing` too and that bypass regression returns with nothing left to catch it.

**Size the prize before spending on this again.** Collapsing all 80 coordinator entries (35 skills + 45 commands) to name-only saves 6,491 B of an 8,612 B surface — roughly 1,855 tokens, or ~24k tokens across a twelve-agent wave at 13 payers. Real, but an order of magnitude below what dispatch shape recovers (~332k on the same wave — see `agent-dispatch-economics.md § Agent Type Is the Largest Per-Dispatch Cost`). Rank it accordingly.

<!-- spec-backlink: state/handoffs/2026-07-30-boot-payload-collapse-skills-to-name-onl.md item 1; measurement in docs/research/2026-07-30-boot-envelope-controllability.md. -->

---

## Decision Records

| DR | Decision | Status |
|----|----------|--------|
| decision-tree-skill-pattern | Adopt decision-tree pattern over narrative skills for all new super-skills | Accepted 2026-05-06 |
| Phase A cleanup | Disable unused plugins + delete dead skills + demote lifecycle subroutines | Accepted |
| description-budget hard limit | Enforce ≤150/175 char descriptions via a gate | Accepted; relaxed to advisory-only, then found to be measuring no coordinator surface at all. Now bound by the pytest-tier boot-envelope test — see § Description Budget Hard Limit |
| collapse coordinator skills to `name-only` | PM-directed 2026-07-30; **not implementable** — `skillOverrides` cannot reach plugin-sourced skills in CLI 2.1.220. See § `skillOverrides` Cannot Reach Plugin Skills |

---

## Reference

- Super-skill architecture: `docs/wiki/super-skill-architecture.md`
- Per-project plugin gating: `docs/wiki/per-project-plugin-gating.md`
