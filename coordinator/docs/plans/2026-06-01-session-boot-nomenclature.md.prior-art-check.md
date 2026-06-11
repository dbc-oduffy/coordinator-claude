---
title: Prior-Art Check — session-boot-nomenclature
created: 2026-06-01
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-06-01-session-boot-nomenclature.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-01-session-boot-nomenclature.md`
**Verdict:** COMPATIBLE
**Claims checked:** 12
**Conflicts:** 0 | **Compatible-but-relevant:** 5 | **Silent:** 7
**Corpora consulted:** project-wikis (101+ files indexed) | global-wikis (~/.claude/docs/wiki/, 27 files indexed) | lessons.md | improvement-queue

---

No conflicts found.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #1 / #2 / #3 — Session-boot vs /session-start vs SessionStart distinction:** the plan coins "session boot" as a new vocabulary separator between the automatic hook machinery and the PM-invoked skill.
  - **Plan covers:** introduces "session boot" (machinery), `/session-start` (skill), `SessionStart` (literal matcher) as three distinct tokens.
  - **Prior art (`docs/wiki/plugin-session-start-hooks.md` L4 and L8):** "Purpose: Authoring rules for plugin SessionStart hooks — three rules that prevent the silent-skip failure mode detected by `scan-addon-health.sh --red-and-stale`." and "Claude Code executes SessionStart hooks declared in a plugin's `hooks/hooks.json`. When a declared hook command references a script that doesn't exist on disk, Claude Code silently no-ops the command — no error surfaces, no log entry, no indication the hook didn't fire. A botched plugin install that leaves a missing hook script is therefore invisible until the operator notices the expected session-start behavior never fires."
  - **Subtype:** `cite`
  - **Suggested action:** The plan (AC4 / C3) already targets this file for a clarifier. The prior-art passage confirms the file uses `SessionStart` (PascalCase) throughout to mean the literal platform hook — consistent with the plan's three-token taxonomy. The executor should verify on reword that no passage in the file uses "session-start" (hyphen, no slash) as a free-form synonym for the skill — that would be a reclassification site.

- **Claim #1 — "session boot" is already partially in use:** the plan claims to be *coining* "session boot," but prior art shows the term is already present in multiple surfaces.
  - **Plan covers:** "coin 'session boot' as the canonical term" — framed as a new coinage.
  - **Prior art (`docs/wiki/tiered-context-loading.md` L23 and L33):** "| 0 | Boot context | ≤2K tokens, always loaded | `orientation_cache.md`, `CLAUDE.md` (auto-loaded), session memory pointers |" and "Files Tier-0-loaded at every session boot (orientation_cache, MEMORY.md) MUST be bounded."
  - **Prior art (`docs/wiki/implementation-standards-by-domain.md` L14):** "Coordinator CLAUDE.md is read at every session boot."
  - **Prior art (`docs/wiki/learn-lessons-routing.md` L21 and L69):** "CLAUDE.md is load-bearing at every session boot." and "CLAUDE.md loads at every session boot across every project — blast radius is maximum."
  - **Prior art (`docs/wiki/daily-branch-discipline.md` L240):** "Record `session-start-sha` at `/pickup` time (or session boot) to make the scoping mechanical."
  - **Prior art (`docs/wiki/eager-agent-calibration.md` L58):** "A one-line heuristic in `~/.claude/CLAUDE.md` § Implementation Standards — Extensions, visible to the EM at every session boot:"
  - **Prior art (`coordinator/CLAUDE.md` L149 — plan notes this itself):** "CLAUDE.md is load-bearing — read at every session boot."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's "coin" framing is slightly off — "session boot" is already in organic use across at least 6 wiki surfaces with the machinery sense the plan intends. The plan is better described as *formalizing and centralizing* an existing informal convention, not coining it. The executor should update the plan's problem statement or C1 intro to say "establish as the canonical, defined term" rather than "coin" — the term already exists in the right meaning. This is informational; the substance of the work is unchanged.

- **Claim #6 — CONTEXT.md as the glossary anchor for new terms:** the plan proposes adding "session boot" and "ceremony grid" to `~/.claude/CONTEXT.md`.
  - **Plan covers:** C1 — Add two glossary entries to `~/.claude/CONTEXT.md`.
  - **Prior art (`docs/wiki/context-md-convention.md` § Producer / Consumer Split):** "Two skills produce `CONTEXT.md` entries as a side-effect of their natural work: `coordinator:brainstorming` (When the PM resolves a term during design dialogue) and `coordinator:plan` (When the plan introduces a domain term that will recur). **Inline update rule:** When a term is resolved, update `CONTEXT.md` immediately — don't batch. The glossary is most valuable when it's current."
  - **Prior art (`docs/wiki/context-md-convention.md` § Notes on sections):** "**`## Flagged ambiguities`** is optional but valuable. Records the historical confusion that a term resolved — this is institutional memory that prevents regression."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's C1 approach is fully consistent with context-md-convention.md doctrine — this is a `coordinator:plan`-driven term introduction, which is one of the two authorized producer paths. The executor should additionally add a `## Flagged ambiguities` entry recording the `/session-start` vs `SessionStart` conflation being resolved (date 2026-06-01), per the convention wiki's "valuable" note. The CONTEXT.md currently has no "session boot" or "ceremony grid" entries, confirming these are net-new.

- **Claim #5 — Ceremony grid coinage `{session,workday,workweek} × {start,complete}`:** plan proposes defining this as a canonical concept in CONTEXT.md.
  - **Plan covers:** "ceremony grid — the explicit, PM-invoked lifecycle skills form a 2×3 grid: `{session, workday, workweek} × {start, complete}`."
  - **Prior art (`docs/wiki/ceremony-calibration.md` title and opening):** "When to invoke heavyweight ceremony (plan-pipeline, brainstorm, sizing pass, skill extraction, retirement) vs lightweight action...This wiki synthesizes nine recurring patterns into a single calibration vocabulary."
  - **Prior art (`docs/wiki/ceremony-calibration.md` § Negative space):** "**Naming, formatting, file location** — implementation discretion, EM acts."
  - **Subtype:** `cite`
  - **Suggested action:** The `ceremony-calibration.md` wiki uses "ceremony" extensively but with a different sense — it calibrates when to invoke the plan pipeline, not the session-lifecycle grid. There is no conflict, but the plan should note in its CONTEXT.md entry that "ceremony" in the `{session,workday,workweek} × {start,complete}` grid sense is specifically the lifecycle ceremony, distinct from the `ceremony-calibration.md` "ceremony" meaning (heavyweight process weight). The executor should check whether the ceremony-calibration wiki also needs a cross-reference note to avoid the vocabulary collision.

- **Claim #8 — Keep `plugin-session-start-hooks.md` filename unchanged; add clarifier only:** plan explicitly keeps the wiki filename to avoid link-rot churn across its 6 referrers.
  - **Plan covers:** "Do not `git mv` the file." Justified by 6 referrers.
  - **Prior art (`docs/wiki/naming-discipline.md` opening):** "Names are cheap to change once, expensive to change twice, and very expensive to change in anticipation of occupants that never arrive. Refuse speculative umbrella renames... Rename when a second occupant **actually lands**, not when one is hypothesized."
  - **Prior art (`coordinator/CLAUDE.md` § Reviewer-Routed Workers):** "any plan with a `git mv` / path rename / file relocation schedules a post-execution `doc-link-checker` closeout chunk."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's decision to keep the filename is consistent with naming-discipline doctrine. The plan is NOT doing a rename, so no `doc-link-checker` closeout chunk is required — but the executor should verify that the clarifier added in C3 does not itself introduce a new doc-link reference that the checker would need to validate. The naming-discipline reference is informational; the plan's EM-decided no-rename is correct per doctrine.

---

### Silent areas (no prior art found)

- Claim #4 — Front/back asymmetry (no `SessionEnd` platform hook → no "session teardown" coinage needed): no prior art establishing or contradicting this claim. The plan's own investigation of `hooks.json` is the evidence base.
- Claim #7 — CLAUDE.md L7-8 parenthetical reframing (converting a disambiguation scab to a plain statement): no prior art specifically about this passage's history or prescribed treatment. The plan is making a first-mover call.
- Claim #9 — EM-direct execution (not fan-out) for this work: no prior art conflict. The ceremony-calibration.md § Queue-clear classification is COMPATIBLE (vocabulary-classification work is judgment-shaped, consistent with the plan's EM-direct rationale), not a conflict.
- Claim #10 — `/session-end → /session-complete` rename out of scope: no prior art covering this renaming decision itself (the spinoff handoff is the authoritative artifact for that workstream).
- Claim #11 — No machinery behavior changed (byte-identical hooks.json / scripts except rewording): no prior art conflict; this is a constraint, not a claim about prior behavior.
- Claim #12 — Percolation via `setup/publish.sh` noted but not executed: no prior art conflict. The OSS distribution doctrine (`docs/wiki/plugin-extraction-and-distribution.md`) confirms publish.sh is outward-only — consistent with the plan's treatment.

---

### Verdict logic

Zero conflicts found. Five compatible-but-relevant findings: three are informational alignment notes the executor should fold into the execution (the "coinage vs. formalization" framing correction, the CONTEXT.md `## Flagged ambiguities` entry, the "ceremony" vocabulary collision note), and two are confirmatory cites. The plan is internally consistent with prior art on the core claims (file unchanged, CONTEXT.md as glossary anchor, `coordinator:plan` as authorized producer).

**Cost estimate:** ~8K tokens (12 claims × ~5 targeted corpus reads, 3 full wiki reads, lessons + queue scan)
