---
title: Plan Coverage Check — fan-out-skill-to-methodology-demotion
created: 2026-05-30
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-05-30-fan-out-skill-to-methodology-demotion.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-fan-out-skill-to-methodology-demotion.md`
**Verdict:** INCOMPLETE
**Oracle items:** 7 (source: `## Substrate — Contact Map` table, "Repoint" rows #1–#7)
**Slate items:** 3 chunks (Chunk 1 keystone, Chunk 2 execute-plan, Chunk 3 pointer repoints)
**Missed:** 0 | **Ambiguous:** 0 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 1

---

### Missed audit items (no slate entry, no architectural OOS)

None.

---

### Ambiguous audit items (signal-partial — informational only)

None.

---

### Weak OOS / hedges (appetite-based deferrals)

None found. Both OOS items assessed:

- **"Renaming `execute-plan` to `execute`"** — OOS because this plan's scope is demotion via doctrine, not a command rename; the plan states "surface separately if the PM wants the literal rename." This is architectural: it is a separate user-visible command rename with distinct blast-radius, not appetite-based hedging. OOS-ARCHITECTURAL.
- **"Flipping the organic-ramp plan's stale `status: draft`"** — OOS because it is a foreign plan's frontmatter; the plan correctly flags it to PM rather than editing it unilaterally. The reason is a blast-radius/ownership boundary, not appetite. OOS-ARCHITECTURAL.

No hedge tokens fired for items that warrant findings.

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

#### SD-1: `dispatching-parallel-agents.md:127` — uncovered live path reference to the deleted skill

**Plan citation (NOT-touched list and Chunk 1 scope):**

> `bin/fan-out-dispatch.sh` + `.test.sh` + `capture-fan-out-threshold.sh` — [...] The references *inside* the helper to `skills/fan-out/SKILL.md Step 0.5` (the suitability gate) DO need repointing to the new methodology anchor — see Chunk 1.

Chunk 1 names two repoint targets: the `:196` bullet in `dispatching-parallel-agents.md` and the comment strings in `bin/fan-out-dispatch.sh`. It does NOT name `dispatching-parallel-agents.md:127`.

**Current disk state** — `dispatching-parallel-agents.md` line 127 contains:

> "a per-chunk fan-out-suitability gate at both plan-authoring time (`skills/plan/SKILL.md` Branch C) and fan-out-dispatch time (`skills/fan-out/SKILL.md` Step 0.5), plus a mechanical fat-chunk NOTE in `fan-out-dispatch.sh`."

This is a live narrative citation to `skills/fan-out/SKILL.md Step 0.5` inside the wiki file that is NOT a historical plan. After `git rm -r skills/fan-out/`, this reference becomes a dead path.

**The plan's own test surface makes this a testable failure:** Chunk 1's test surface reads:

> `grep:` no surviving reference to `skills/fan-out/SKILL.md` outside historical plans

`dispatching-parallel-agents.md` is a live wiki, not a historical plan. The test as written would flag this line — but Chunk 1's work instructions do not include editing it.

**Contact map scope note:** The plan frames the contact map as "skill-invocation references." Line 127 is a narrative citation, not a skill invocation — but it will produce a dead link after deletion. This is outside the plan's explicit scope framing but inside the scope of its own AC test ("no surviving reference to `skills/fan-out/SKILL.md` outside historical plans").

**Suggested action:** add-to-slate — Chunk 1 should include repointing `dispatching-parallel-agents.md:127` from `skills/fan-out/SKILL.md Step 0.5` to the new wiki methodology anchor (same file, same chunk, two-line edit). Alternatively, amend oracle with explanatory note if the plan author considers narrative citations out of scope and is willing to weaken the Chunk 1 test surface accordingly.

**Disposition:** applied — the plan already carries SD-1 as an explicit bullet in Chunk 1 ("Repoint the narrative citation at `dispatching-parallel-agents.md:127`..."), added during pre-integration. This finding was already folded before the Staff Engineer's review; confirmed present in the plan text.

---

### Coverage cross-reference (all 7 oracle items)

| # | Oracle item | Chunk | Signal | Verdict |
|---|---|---|---|---|
| 1 | `skills/fan-out/SKILL.md` — migrate body → wiki, delete dir | Chunk 1 | shared file-path (`skills/fan-out/`) | MATCHED |
| 2 | `skills/execute-plan/SKILL.md` (Phase 1.5 `:61`, escape hatch `:66`, Relationship §) | Chunk 2 | shared file-path + shared symbol (`coordinator:fan-out`) | MATCHED |
| 3 | `docs/wiki/dispatching-parallel-agents.md` (`:191-200`) — host methodology, rewrite `:196` | Chunk 1 | shared file-path + shared line range | MATCHED |
| 4 | `docs/wiki/agent-dispatch-economics.md` (`:26`, `:108`) | Chunk 3 | shared file-path + shared symbol (`coordinator:fan-out`) | MATCHED |
| 5 | `skills/session-start/SKILL.md` (`:294`) | Chunk 3 | shared file-path + shared line number | MATCHED |
| 6 | `commands/workday-start.md` (`:470`) | Chunk 3 | shared file-path + shared line number | MATCHED |
| 7 | global `~/.claude/CLAUDE.md` (`:53`) | Chunk 3 | shared file-path + shared line number | MATCHED |

---

### Substrate verification — cited line numbers against disk

All 7 files confirmed to exist on disk.

| Citation | Disk state | Result |
|---|---|---|
| `dispatching-parallel-agents.md:191-200` — § Executing a Fan-Out Wave | Line 191: section heading confirmed; line 196: "`coordinator:fan-out` (dispatcher skill)" bullet confirmed | VERIFIED |
| `agent-dispatch-economics.md:26` — "use `coordinator:fan-out` skill" | Line 26: "use `coordinator:fan-out` skill to dispatch the compiled wave via `Agent`" — confirmed | VERIFIED |
| `agent-dispatch-economics.md:108` — skill reference in Related section | Line 108: "→ `coordinator:fan-out` skill — standalone fan-out verb" — confirmed | VERIFIED |
| `session-start/SKILL.md:294` — "`coordinator:fan-out` skill (end-to-end dispatch verb)" | Line 294: "`coordinator:fan-out` skill (end-to-end dispatch verb)" — confirmed | VERIFIED |
| `workday-start.md:470` — "`/fan-out` skill (dispatcher)" | Line 470: "`/fan-out` skill (dispatcher — end-to-end wave execution)" — confirmed | VERIFIED |
| `~/.claude/CLAUDE.md:53` — "invoke the `coordinator:fan-out` skill" | Line 53: "invoke the `coordinator:fan-out` skill (end-to-end verb — overlap pass + dispatch + EM-serial commit)" — confirmed | VERIFIED |
| `skills/execute-plan/SKILL.md:61` — `coordinator:fan-out` invocation | Line 61: `coordinator:fan-out` (bare invocation block) — confirmed | VERIFIED |
| `skills/execute-plan/SKILL.md:66` — escape hatch criterion | Line 66: "skip the `coordinator:fan-out` invocation" — confirmed | VERIFIED |

---

### NOT-touched claims verified

**`coordinator/CLAUDE.md` — "fan-out hits are helper/concept references, no skill invocation":**
Grep of `coordinator/CLAUDE.md` for `coordinator:fan-out` and `/fan-out`: **zero matches**. Claim VERIFIED.

---

### Extra contact points check — live references not in the contact map

Grep of the full plugin tree (non-plan, non-sidecar `.md` files and `.sh` files) for `coordinator:fan-out`, `/fan-out skill`, and `skills/fan-out/SKILL`:

**Live non-plan files with hits:**

| File | Line | Content | In contact map? |
|---|---|---|---|
| `docs/wiki/dispatching-parallel-agents.md` | 127 | `skills/fan-out/SKILL.md Step 0.5` (narrative citation) | NO — contact map lists only `:191-200` |
| `docs/wiki/dispatching-parallel-agents.md` | 196 | `coordinator:fan-out` skill invocation bullet | YES — oracle item #3 |
| `docs/wiki/agent-dispatch-economics.md` | 26, 108 | `coordinator:fan-out` skill | YES — oracle item #4 |
| `skills/session-start/SKILL.md` | 294 | `coordinator:fan-out` skill | YES — oracle item #5 |
| `commands/workday-start.md` | 470 | `/fan-out` skill | YES — oracle item #6 |
| `skills/fan-out/SKILL.md` | (whole file) | the skill itself | YES — oracle item #1 |
| `skills/execute-plan/SKILL.md` | 61, 66 | `coordinator:fan-out` | YES — oracle item #2 |
| `bin/fan-out-dispatch.sh` | 378, 392 | `skills/fan-out/SKILL.md Step 0.5` (comment strings) | YES — NOT-touched list, Chunk 1 explicitly covers |
| `~/.claude/CLAUDE.md` | 53 | `coordinator:fan-out` skill | YES — oracle item #7 |

**One unmapped live reference:** `dispatching-parallel-agents.md:127` — reported as SD-1 above.

No other unmapped live skill-invocation or path references found.

---

### Verdict logic

**INCOMPLETE.** One substrate-drift finding (SD-1): `dispatching-parallel-agents.md:127` contains a live path citation (`skills/fan-out/SKILL.md Step 0.5`) that will become a dead reference after `git rm -r skills/fan-out/`, and is not covered by any chunk. The plan's own test surface (Chunk 1: "grep: no surviving reference to `skills/fan-out/SKILL.md` outside historical plans") would fail against this line post-execution. EM must fold before dispatch: either add the `:127` repoint to Chunk 1's work instructions, or explicitly declare narrative citations out of scope and weaken the Chunk 1 test surface accordingly.

All 7 oracle items are MATCHED to chunks. Zero missed, zero ambiguous, zero weak-OOS, zero hedges. The sole finding is the uncovered dead-path reference.

**Cost estimate:** ~8K tokens (7 oracle items × line verification + 1 full-tree grep + 9 file reads)
