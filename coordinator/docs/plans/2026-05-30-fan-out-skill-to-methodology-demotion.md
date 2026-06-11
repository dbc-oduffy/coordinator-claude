---
title: Demote coordinator:fan-out from skill to methodology
slug: fan-out-skill-to-methodology-demotion
status: consumed
shipped_in: 58234b9c
scope_mode: production-patch
created: 2026-05-30
author: striker EM
reverses: docs/plans/2026-05-27-fan-out-default-doctrine.md § Chunk 5 (coordinator:fan-out standalone skill)
---

# Demote `coordinator:fan-out` from Skill to Methodology

## Problem

`coordinator:fan-out` was shipped 2026-05-27 as a standalone invokable skill — the
"in-the-moment fan-out verb." Since then, **"fan out" has become native Claude Code
vocabulary** (a core dispatch concept). The verb now collides: a PM or EM saying "fan out X"
may trip ambient Claude Code behavior rather than our disciplined skill (overlap pass →
suitability gate → scoped prompts → EM-serial commit). Meanwhile "execute" is the PM's
natural, collision-free handle for the same intent, and execution *already* owns the
restructure-for-fan-out judgment (`execute-plan` Phase 1.5).

The fix: **demote the skill to a methodology** owned by execution. The disciplined ceremony
survives (it moves into `execute-plan` + the canonical wiki); only the colliding standalone
`/fan-out` command disappears.

This is three coupled doctrine changes:

- **(A) Re-name the seam as STANCE, not altitude.** Today the execute-plan/fan-out relationship
  is framed as altitude (plan-aware orchestrator vs. ad-hoc verb). Reframe it as stance:
  **execute = restructure-then-dispatch (judgment); fan-out = the dispatch methodology execution
  follows.** Makes the seam's purpose legible.
- **(B) Consolidate the PM-facing verb on "execute"; demote the skill.** Migrate the
  `skills/fan-out/SKILL.md` operational body into the canonical wiki methodology
  (`dispatching-parallel-agents.md § Executing a Fan-Out Wave`), delete the skill dir
  (auto-deregisters `coordinator:fan-out` and stops it shipping to OSS), and repoint every
  citation. Ad-hoc parallel work (≥2 tasks, no plan) folds under execution / follows the
  methodology inline — **no standalone command.**
- **(C) Keep `execute-plan`'s self-execute escape hatch, but rewrite its criterion** from the
  fuzzy "EM-judgment-heavy / conversation-context-matters" to **token-economics**: default to
  dispatch (Sonnet ≈ ¼ the tokens of an Opus EM, and faster); self-execute only when the EM can
  articulate why it is genuinely cheaper *here*. Since that is rarely true, the bar is high —
  and this closes the one route that skips the suitability gate.

## Premise-Pass — What We're Reversing and Why It Stays Coherent

The 2026-05-27 decision made fan-out a *standalone skill* for one concrete reason: **a bin
script (`fan-out-dispatch.sh`) cannot call the `Agent` tool**, so the dispatch autopilot had to
live in an executable layer, and a skill was that layer (reachable ad-hoc *and* from
execute-plan Phase 1.5 — "one mechanism, two entry points").

The demotion **preserves that rationale rather than fighting it**: the `Agent`-dispatch steps
move *into* `execute-plan` (still an executable layer) plus the wiki methodology that both
execute-plan and ad-hoc callers follow. The compiler (`fan-out-dispatch.sh`) is untouched —
it was always the suspenders; the skill was the belt, and the belt's function relocates rather
than vanishes. **What we lose is only the standalone `/fan-out` *command*** — which is exactly
the Claude-Code vocabulary collision this change exists to remove.

Negative-search (reverses-prior-teardown): the 2026-05-27 plan + its prior-art-check are the
only prior art; both are cited here. No lessons.md entry argues *for* a standalone fan-out
command independent of the collision rationale.

## Substrate — Contact Map (grep-verified 2026-05-30)

**Repoint (skill-invocation references — 7 surfaces):**

| # | File | Current | Action |
|---|---|---|---|
| 1 | `skills/fan-out/SKILL.md` | the skill itself | **migrate body → wiki, delete dir** (deregisters `/fan-out`) |
| 2 | `skills/execute-plan/SKILL.md` (Phase 1.5 `:61`, escape hatch `:66`, Relationship §) | invokes `coordinator:fan-out`; fuzzy escape-hatch criterion | inline the dispatch loop + cite wiki methodology; rewrite (C) criterion; add (A) stance framing |
| 3 | `docs/wiki/dispatching-parallel-agents.md` (`:191-200`) | § Executing a Fan-Out Wave names the "dispatcher skill" | **host the migrated methodology**; rewrite the `:196` bullet from skill → methodology |
| 4 | `docs/wiki/agent-dispatch-economics.md` (`:26`, `:108`) | "use `coordinator:fan-out` skill" | repoint to methodology/helper |
| 5 | `skills/session-start/SKILL.md` (`:294`) | "`coordinator:fan-out` skill (end-to-end dispatch verb)" | repoint to methodology |
| 6 | `commands/workday-start.md` (`:470`) | "`/fan-out` skill (dispatcher)" | repoint to methodology |
| 7 | global `~/.claude/CLAUDE.md` (`:53`) | "invoke the `coordinator:fan-out` skill" | repoint to methodology; add (A) stance one-liner |

**NOT touched:**
- `bin/fan-out-dispatch.sh` + `.test.sh` + `capture-fan-out-threshold.sh` — the *compiler* stays (it is the methodology's mechanical core, not a skill). The references *inside* the helper to `skills/fan-out/SKILL.md Step 0.5` (the suitability gate) DO need repointing to the new methodology anchor — see Chunk 1.
- `coordinator/CLAUDE.md` — its "fan-out" hits are helper/concept references, no skill invocation.
- Historical plan docs (`2026-05-27-fan-out-default-doctrine.md`, `2026-05-30-organic-ramp-concurrency-doctrine.md` + sidecars) — archival records; not retro-edited.

## Cross-Plan Coordination

- **`docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md`** (`status: draft`, but content
  shipped to disk): edits the same `skills/fan-out/SKILL.md` (Step 1.5 ramp-reminder, Step 2
  organic ramp), `dispatching-parallel-agents.md` (§ Concurrency Budget), and
  `bin/fan-out-dispatch.sh` (threshold). Since its content has already landed and there is no
  live executor, this plan **supersedes the `fan-out/SKILL.md` file** (deleting it). **Migration
  obligation:** the organic-ramp *operational* semantics that live in fan-out/SKILL.md Steps
  1.5/2 (pilot→expand ramp, soft NOTE not HARD STOP, orchestrator-fanout counting) MUST survive
  into the migrated wiki methodology — they are not lost by deleting the SKILL.md, but the
  *procedure* (not just the § Concurrency Budget doctrine the wiki already carries) must be
  carried over. **Side flag (not in scope):** that plan's `status: draft` is stale and should be
  flipped to `consumed`/`shipped_in:` — surface to PM, do not edit as part of this plan.
- No other `docs/plans/*.md` cite `coordinator:fan-out` as a live dependency (the two
  `.prior-art-check.md` sidecars reference it descriptively only).

## Open Decision (surfaced to PM, default carried in plan)

**Ad-hoc entry point.** The 2026-05-27 skill was deliberately reachable ad-hoc (≥2 tasks, no
plan doc). Killing the command removes that entry. **Plan default (per PM "cited as part of
execution"):** ad-hoc parallel work folds under execution — the EM follows the wiki methodology
inline when it has ≥2 independent tasks; no standalone command. Surfaced for review; not a
silent choice.

**There is NO skill-less ad-hoc path: the forcing function still fires on both routes.** For
ad-hoc parallel work of ≥2 tasks, the methodology lives in `execute-plan` Phase 1.5's inline
methodology (which carries the migrated Step 0.5 suitability gate) — this is the primary
execution path. For any path where no plan doc exists and an EM reaches for `fan-out-dispatch.sh`
directly, the mechanical fat-chunk `NOTE:` in `fan-out-dispatch.sh` (≥4 files → fires) is the
executed backstop. The HARD STOP does not disappear; it relocates. Readers who wonder "where does
the suitability gate fire for no-plan-doc work?" have a precise answer: Phase 1.5 (plan-path) and
the NOTE: (direct-sh path). There is no gap.

<!-- Review: the Staff Engineer F0 — make explicit that the ad-hoc firing surface is Phase 1.5 + the fan-out-dispatch.sh NOTE:; don't leave readers to infer where HARD STOP lands for the no-plan-doc path -->

**Engaging the 2026-05-27 causal argument (prior-art Conflict #5).** The fan-out-default plan
diagnosed the *absence of an in-the-moment ad-hoc verb* as one of three structural causes of the
monolith-grind failure (EM defaults to one-agent-many-chunks when fanning out has higher ceremony
than grinding). Removing the `/fan-out` command could appear to re-open that failure. It does not.

The lead argument: the standalone `/fan-out` command was a **palliative** for the monolith-grind
*symptom* — it gave the EM a low-friction verb to reach for. Consolidating on "execute" with the
methodology inline is the **root-cause** fix: it creates a low-friction path *to the disciplined
ceremony* while also removing the palliative's now-toxic side effect (the vocabulary collision
between `/fan-out` and native Claude Code "fan out" dispatch behavior). The 2026-05-27 plan added
a palliative because there was no root-cause path yet; this plan adds the root-cause path and
retires the palliative.

The three-surfaces reconciliation supports this: the anti-monolith fix is preserved on three
surviving surfaces, not by the command:
(1) the dispatch methodology stays **inline in `execute-plan`** and the canonical wiki — the
ceremony is still one EM-side call (`fan-out-dispatch.sh`), not hand-authored prompts;
(2) the **anti-monolith HARD RULE** remains in `em-operating-model.md` / `coordinator/CLAUDE.md`
/ global CLAUDE.md, unchanged; (3) **"execute" is a lower-friction verb than `/fan-out` ever
was** — it is the PM's natural word and collision-free, so the path of least resistance still
leads to the disciplined ceremony. What 2026-05-27 actually fixed was "no easy verb → grind";
this plan keeps an easy verb (execute) and the one-call helper, and removes only the *colliding*
command. The harm being traded away (vocabulary collision sending "fan out X" to ambient Claude
Code instead of our ceremony) did not exist on 2026-05-27.

The acknowledged residual: "execute" presupposes a plan doc (it is `execute-plan`), so it
addresses PLANNED-work grind more directly than ad-hoc-no-plan grind. We accept a small
residual regression on the ad-hoc-no-plan path in exchange for removing the collision. This
is backstopped by Phase 1.5 + the mechanical NOTE: as described above (see preceding paragraph).

<!-- Review: the Staff Engineer F1 — tighten rebuttal: (a) lead with palliative→root-cause framing (the PM's sharper framing), (b) acknowledge "execute" is execute-plan and presupposes a plan doc, (c) name the accepted residual explicitly, (d) place three-surfaces reasoning as supporting, not primary -->

## Chunks

### Chunk 1 — Methodology home + skill deletion (keystone) — `docs/wiki/dispatching-parallel-agents.md`, `skills/fan-out/`, `bin/fan-out-dispatch.sh` (anchor refs only)

The serial keystone — establishes the methodology anchor every other chunk cites.

- **Read the current `skills/fan-out/SKILL.md` Steps 1.5/2 on disk before migrating** (prior-art
  Claim #10): trust disk, not this plan's claim about what the organic-ramp work landed. Confirm
  the live ramp semantics, then migrate them. **Hard gate:** before proceeding to `git rm -r
  skills/fan-out/`, also read `docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md` AC
  table and check for any rows touching its C3 (skills/fan-out/SKILL.md edits) that are still
  `status: pending realization`. If such rows exist, migrate the INTENDED final shape from the
  AC table, not merely the current-disk state — the organic-ramp plan's intended content is the
  migration source, not a partially-executed snapshot. Confirm which shape you are migrating and
  state it in your work notes before deleting the skill dir.

<!-- Review: the Staff Engineer F4 — read-before-migrate is a hard gate: check the organic-ramp plan's AC table for pending-realization C3 rows before git rm; migrate intended final shape if any pending edits exist, not just current disk -->
- **Distinguish doctrine-already-in-wiki from procedure-only-in-skill** (prior-art Claim #9): the
  wiki's `§ Concurrency Budget` ALREADY carries the organic-ramp *doctrine* (LARGE_WAVE_THRESHOLD,
  headroom probe, no-fixed-cap). Do NOT re-expand that. Migrate only the *operational procedure*
  from the SKILL.md (Steps 1.5/2) that the wiki does not yet carry — avoid double-stating.
- Expand `§ Executing a Fan-Out Wave — The Canonical Mechanism` to carry the migrated
  *operational* body from `skills/fan-out/SKILL.md`: Step 0 wave-spec, **Step 0.5 fan-out
  suitability gate** (the anti-fat-chunk forcing function — load-bearing, must survive verbatim
  in intent, must retain STOP-and-re-chunk *forcing-function* framing not merely topic
  mention), overlap pass, **organic-ramp** (pilot→expand, soft NOTE, orchestrator counting —
  per Cross-Plan migration obligation), dispatch with `acceptEdits`, **EM-serial commit**, and
  next-wave gate. Frame it as *the methodology execution follows*, not a skill.
- **Migrate the 2026-05-29 "one agent authors 7 modules" incident anchor alongside the gate
  text** (per prior-art Claim #3): the incident citation is what makes Step 0.5 non-optional to
  a future reader — the gate looks advisory without it. The source is the spec-backlink comment
  in `skills/fan-out/SKILL.md` Step 0.5: "**This is the gate whose absence produced the
  2026-05-29 'one agent authors 7 modules' failure.**" Carry that or equivalent language into
  the wiki methodology.

<!-- Review: the Staff Engineer F3 — AC3/AC8: assert migrated gate retains HARD-STOP framing; Chunk 1: carry the 2026-05-29 incident anchor alongside the gate — incident citation is what signals non-optionality to a future reader -->
- **Repoint the narrative citation at `dispatching-parallel-agents.md:127`** (coverage SD-1): the
  § Read-Overlap Is NOT Write-Overlap empirical block cites "`skills/fan-out/SKILL.md` Step 0.5"
  as a live path — repoint it to the new in-wiki methodology anchor. Same file Chunk 1 already
  edits; two-line edit. (Without this, `git rm -r skills/fan-out/` leaves a dead reference that
  AC2's grep would flag post-execution.)
- Rewrite the `:196` bullet: delete "`coordinator:fan-out` (dispatcher skill)"; replace with the
  methodology statement (the EM, from `execute-plan` or ad-hoc, runs `fan-out-dispatch.sh` then
  dispatches via `Agent` and holds the EM-serial commit — these steps, here).
- Repoint the in-helper anchor: `bin/fan-out-dispatch.sh` lines that cite
  `skills/fan-out/SKILL.md Step 0.5` → the wiki methodology anchor. (Comment-string edits only;
  no logic change.)
- `git rm -r skills/fan-out/` — deregisters `coordinator:fan-out`.
- **Test surface:** `grep:` no surviving reference to `skills/fan-out/SKILL.md` outside historical
  plans; `bash bin/fan-out-dispatch.test.sh` exits 0 (the helper's suitability NOTE text may
  reference the new anchor but its behavior is unchanged).

### Chunk 2 — `execute-plan` rewrite — `skills/execute-plan/SKILL.md`

- Phase 1.5: replace the ```coordinator:fan-out``` invocation block with the inline dispatch
  loop, citing the Chunk-1 wiki methodology as the canonical reference. Preserve the EM-judgment
  steps (gate-type discrimination, budget-sizing) that already live here.
- Rewrite the (C) escape-hatch paragraph (`:66`) and the Relationship-to-other-commands row:
  criterion becomes **token-economics** — default dispatch (Sonnet ≈¼ Opus tokens + faster);
  self-execute only when articulably cheaper here; note that self-execute is the one path that
  skips the suitability gate, so the bar is high. **Do NOT delete the existing five-criterion
  `When to EM-Inline` checklist in `agent-dispatch-economics.md`** (fix-locus known ≤3 files /
  <60s on >30k-file repo / mechanical / context-already-loaded / mid-edit-hazard) — per prior-art
  Conflict #6, token-economics is the **top-line** criterion and those five remain the
  **operational checklist that grounds "articulably cheaper here."** Top-line + checklist, not a
  collapse.
- Add the **(A) stance framing**: execute = restructure-then-dispatch; fan-out = the dispatch
  methodology. Replace altitude language in the Relationship section.
- **Test surface:** `grep:` no `coordinator:fan-out` invocation remains; `grep:` the
  token-economics criterion phrase is present; `grep:` stance framing present.

### Chunk 3 — Pointer repoints — `docs/wiki/agent-dispatch-economics.md`, `skills/session-start/SKILL.md`, `commands/workday-start.md`, global `~/.claude/CLAUDE.md`

Four independent one-line pointer edits (disjoint files, read-only on Chunk 1's anchor — pinned).

- `agent-dispatch-economics.md:26,108` — "use `coordinator:fan-out` skill" → methodology/helper.
- `session-start/SKILL.md:294` — drop "skill"; point at the methodology.
- `workday-start.md:470` — drop "`/fan-out` skill"; point at the methodology.
- global `~/.claude/CLAUDE.md:53` — drop "invoke the `coordinator:fan-out` skill"; point at the
  methodology + add the (A) stance one-liner.
- **Verb hygiene (applies to all four files):** when repointing the skill references in
  `~/.claude/CLAUDE.md:53`, `session-start/SKILL.md:294`, and `workday-start.md:470`, change the
  VERB too — "invoke the skill" → "follow the methodology" / "run the helper". Methodologies are
  followed; skills are invoked. Do not leave a dangling "invoke" paired with a wiki-section noun.
  The verb shape signals whether the referent is executable (skill) or procedural (methodology)
  — this distinction is intentional and load-bearing for routing.

<!-- Review: the Staff Engineer F5 — verb hygiene: "invoke" → "follow the methodology" / "run the helper" when repointing; don't leave "invoke" with a wiki-section noun -->

- **Test surface:** `grep:` zero `coordinator:fan-out` / `/fan-out` skill references survive in
  these four files; `grep:` no "invoke" verb paired with a methodology/wiki-section noun in the
  repointed lines.

## Dispatch Shape

Chunk 1 is the keystone (defines the anchor Chunks 2-3 cite); its methodology anchor name is
**pinned** here (`§ Executing a Fan-Out Wave — The Canonical Mechanism`, existing), so Chunks 2-3
can be *authored* concurrently with Chunk 1 and *verified* after it lands.

**Execution-mode note (applying the (C) criterion to this very work):** this is ~7 files of
doctrine wording where cross-file *voice consistency* of the methodology framing matters more
than mechanical throughput, and the total is small. Per the token-economics criterion, EM-inline
is plausibly cheaper here than dispatching 3 Sonnet executors who each need the full framing
context and may drift in voice — the EM will make and state that call at execution time (post-
review). This is itself a dogfood of criterion (C).

## Acceptance Criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|---|---|---|---|---|
| AC1 | `coordinator:fan-out` no longer exists as an invokable skill | `grep:` no `skills/fan-out/` dir; skill absent from registry | gate | pending realization |
| AC2 | No live citation references the skill (historical plans exempt) | `grep:` `coordinator:fan-out\|/fan-out` skill refs absent outside `docs/plans/` | gate | pending realization |
| AC3 | The disciplined ceremony survives in the wiki methodology; the suitability gate retains STOP-and-re-chunk *forcing-function* framing (not just topic mention), and the 2026-05-29 "one agent authors 7 modules" incident anchor is present alongside the gate text | `cited:` § Executing a Fan-Out Wave carries suitability gate + ramp + EM-serial commit; gate language uses STOP/HARD-STOP framing, not merely describes the topic; incident citation present | gate | pending realization |
| AC4 | `execute-plan` Phase 1.5 dispatches via the inline methodology, not a skill call | `grep:` no `coordinator:fan-out` in execute-plan; methodology cited | gate | pending realization |
| AC5 | (C) escape-hatch criterion is token-economics, not "EM-judgment-heavy"; the five-criterion `When to EM-Inline` checklist (fix-locus ≤3 files / <60s / mechanical / context-already-loaded / mid-edit-hazard) is STILL PRESENT in `agent-dispatch-economics.md` after the (C) rewrite | `grep:` token-economics phrasing present; old phrasing gone; `grep:` all five `When to EM-Inline` criteria present in `agent-dispatch-economics.md` | gate | pending realization |
| AC6 | (A) stance framing present at the execute-plan seam + global CLAUDE.md | `cited:` "restructure-then-dispatch" / methodology framing present | gate | pending realization |
| AC7 | `fan-out-dispatch.sh` behavior unchanged; tests green | `bash:` `bash bin/fan-out-dispatch.test.sh` exits 0 | gate | pending realization |
| AC8 | Organic-ramp operational semantics preserved in migration | `cited:` pilot→expand ramp + soft-NOTE present in wiki methodology | gate | pending realization |

## Out of Scope

- Renaming `execute-plan` to `execute` (verb consolidation is via demotion + doctrine, not a
  command rename this pass — surface separately if the PM wants the literal rename).
- Flipping the organic-ramp plan's stale `status: draft` (surfaced to PM).
- Any change to `fan-out-dispatch.sh` logic (compiler stays).

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| None material — execution matched the amended plan | Pre-flight findings (coverage SD-1, prior-art Conflicts #5/#6, the Staff Engineer F0–F5) were folded into the plan *before* execution, so the shipped diff matched the amended forecast. Contact-map refinement (coordinator/CLAUDE.md carries no skill refs; global CLAUDE.md:53 does) happened at substrate-verification time and was already in the committed plan. EM-inline execution dispatched as the Dispatch Shape forecast. | 58234b9c |

All ALLOWLIST sections (Decisions, the (A)/(B)/(C) changes, AC table) shipped as specified — no `SHIPPED: … (was: …)` annotations required.
