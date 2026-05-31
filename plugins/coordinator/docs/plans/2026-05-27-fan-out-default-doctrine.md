---
title: Fan-Out by Default — making the anti-monolith rule load-bearing
slug: fan-out-default-doctrine
created: 2026-05-27
author: EM (DoE altitude, ~/.claude meta-repo)
scope_mode: feature
status: Execution complete — c5 done 2026-05-27 (fan-out skill + execute-plan Phase 1.5 refactor)
problem_set: inline (see § Problem)
related:
  - plugins/coordinator/docs/wiki/dispatching-parallel-agents.md
  - plugins/coordinator/docs/wiki/agent-dispatch-economics.md
  - plugins/coordinator/em-operating-model.md
  - plugins/coordinator/CLAUDE.md
  - ~/.claude/CLAUDE.md
---

# Fan-Out by Default — making the anti-monolith rule load-bearing

## Problem

The EM repeatedly hands a large job to a single long-running agent (15+ min, grinding chunk after chunk) when fanning out across N agents would be far faster in wall-clock. The PM's objective ordering is **wall-clock first; token cost only tangential** — the marginal cost of many-vs-few agents is low and acceptable.

**This is not a missing-rule problem.** The anti-monolith rule already exists, in three places:

- `em-operating-model.md` HARD RULES: *"2+ independent tasks → batch-dispatch in parallel, never sequential"* and *"When in doubt, dispatch."*
- `dispatching-parallel-agents.md` § Coupling Rules Out Concurrency: *"One agent grinding a sequence of chunks is itself the antipattern — the overload in slow motion"*; per-executor budget ~15–25 min on one coherent surface; *"a new agent per chunk, not one agent handed chunk after chunk."*
- The same wiki's empirical motivation is dated **2026-05-26, tagged `self`** — describing this exact failure. **The rule was violated one day after it was written.** That is the proof: the failure is **salience + ceremony asymmetry**, not rule-absence.

Three coupled mechanisms keep the violation alive:

- **(A) Salience.** The rule lives in wikis the EM does not re-read mid-flow, and in a dense `Pre-Dispatch Verification` paragraph in CLAUDE.md. Nothing fires at the dispatch moment.
- **(B) Ceremony asymmetry (load-bearing).** Fanning out is taxed *more* than the monolith: file-overlap pre-dispatch pass, per-prompt In/Out-of-scope peer block, `expected_branch` capture, EM-serial commit between waves. The single-agent path skips all of it. Under velocity pressure the EM rationally takes the low-ceremony monolith. **The doctrine taxes the behavior it wants and subsidizes the behavior it hates.**
- **(C) Objective-function drift.** `agent-dispatch-economics.md` weighs token + worktree overhead as co-equal with wall-clock and frames dispatch as *"a real economic call, not a default-to-delegate rule"* / *"overhead theater"*. That framing is correct for sub-60s mechanical fixes but gets over-applied as cover for under-dispatching a genuinely large job.

<!-- the Staff Engineer R1: Deferral of 2b hook added per PM decision post-review. Rationale: heuristic cannot discriminate monolith from correct large single-surface or Opus-tech-lead dispatch; nudge fires after EM already paid prompt-authoring cost; PreToolUse-on-every-Agent risks tune-out (superpowers anti-pattern). 2a + helper-as-salience-trigger is sufficient for problem A. -->
A dispatch-moment advisory hook was considered and deferred (2026-05-27, PM-decided on the Staff Engineer R1): the monolith-smell heuristic cannot discriminate a monolith from a correct large single-surface or Opus-tech-lead dispatch, the nudge would fire after the EM already paid the prompt-authoring cost it was meant to save, and PreToolUse-on-every-Agent risks training tune-out (the superpowers anti-pattern named in global CLAUDE.md). 2a (HARD rule) + the helper-as-salience-trigger satisfies problem A. Revisit only if monolith-grind recurs after 2a ships (instance-#3 rule, ceremony-calibration).

### The belt already exists but is locked in a drawer (problem B', discovered in review)

`coordinator:execute-plan` **Phase 1.5 "Dispatch-Gate Graph"** already contains the correct anti-monolith machinery verbatim: enumerate touched files per task, mark the three real gate types, write the wave map, size per-executor scope ~15–25 min, *"a fresh agent per chunk, never one agent handed chunk after chunk,"* author peer-scope-prohibition briefs. It is not getting run for three structural reasons — none of which is "the EM forgot":

1. **It only fires on a written plan document.** `/execute-plan <plan-path>` requires a plan doc. The monolith-grind failure happens in *ad-hoc* mode ("I'll just send one agent at this big thing"), which never routes through execute-plan. There is no in-the-moment fan-out verb to reach for.
2. **Phase 1.5 is prose, not a tool.** It is a checklist the EM performs in its head — the same non-load-bearing-salience problem as (A), one level up. Chunk 1's helper is the executable form of Phase 1.5.
3. **It is buried as phase 1.5 of seven** in a skill named for "run my written plan," not "fan out this work."

**Belt-and-suspenders mapping (PM-directed 2026-05-27):**
- **Suspenders** = `bin/fan-out-dispatch.sh` (Chunk 1) — the overlap-pass + scoped-prompt compiler.
- **Belt** = `coordinator:fan-out` (Chunk 5) — a thin standalone skill that *calls `Agent`* (which a bin script cannot), invokes the helper to compile the wave, dispatches it, and holds the EM-serial-commit between waves. Reachable WITHOUT a plan doc, and called by execute-plan Phase 1.5 so the two entry points share one mechanism.

### Empirical antecedents (prior-art-checker, fold-in)

- `tasks/lessons.md` 2026-05-20 — *"Many agents often beat one [universal]"* — direct antecedent; cite in Chunk 3.
- Central improvement-queue entry `2026-05-20 | project-rag-ue-addon | tasks/lessons.md:285 | Single-sequential executor wrong shape for chunked-mechanical work — fan out or EM-direct`. This plan's Chunk 2a landing **closes** that entry — the EM git-rm's the line in Chunk 2's work commit, with the commit subject naming the closed entry (per CLAUDE.md § Improvement Queue). Never marked resolved inline. <!-- the Staff Engineer R1 (Finding #7): bind queue closure to specific chunk + commit discipline; "integrator deletes" was ambiguous and violated the git-rm-the-line canon. -->

### Problem-set restatement (doubt-check, scope_mode=feature)

Falsifiable problem statements in PM vocabulary:
1. *When the EM has a large job, the cheapest-to-author dispatch is the monolith — so the EM picks it even though it loses on wall-clock.* (B — the load-bearing one.)
2. *The anti-monolith rule does not enter the EM's context at the moment of dispatch.* (A.)
3. *The dispatch-economics wiki does not encode "wall-clock first, tokens tangential," so it reads as a brake on fan-out.* (C.)

**Resolved uncertainty (PM-decided on the Staff Engineer R1):** the dispatch-moment hook uncertainty has been resolved — hook deferred (see deferral note above). Chunk 2 is the HARD-RULE elevation only. <!-- the Staff Engineer R1 (Disposition 1): "Biggest uncertainty" block updated — the uncertainty was resolved by PM decision; hook cut. -->

## Out of Scope (architectural)

- **A general dispatch DSL / wave-spec config language.** The helper takes the simplest input that works (see Chunk 1); a YAML schema for waves is YAGNI until instance #3. Irreversible-cost reason: a config format becomes a compatibility surface the moment any skill emits it.
- **Auto-invoking `Agent()` from the *helper*.** A bin script cannot call the `Agent` tool; the helper emits paste-ready prompt blocks. The `Agent`-calling autopilot lives in the `coordinator:fan-out` *skill* (Chunk 5), which the EM/runtime executes — that is the correct layer for tool calls. Helper = compiler; skill = dispatcher.
- **Changing the 6–8 concurrency cap or worktree-default doctrine.** The helper respects both; revisiting them is a separate PM call.

## Scope Mode

`feature` — Chunk 1 introduces a novel surface (the helper). The doctrine edits (Chunks 2–4) are `production-patch`-shaped but ride the feature's review depth because they cite the helper. <!-- the Staff Engineer R1 (Disposition 1): "optional novel hook (Chunk 2)" removed — Chunk 2b cut by PM; Chunk 2 is now doctrine-only. -->

## Acceptance Criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|----|-------------------|---------------------|---------------|--------|
| AC1 | A fan-out helper exists that, given a chunk→files→brief wave spec, runs the file-overlap intersection and **fails loud** (non-zero exit, lists collisions) when any file is claimed by ≥2 chunks; also hard-errors (non-zero, names offending row) on any malformed input row (wrong field count, empty required field, embedded newline or comma-in-path). | `pending realization` (test: `bin/fan-out-dispatch.test.sh` — overlap case exits non-zero; malformed-row case exits non-zero naming the row, emits no partial output) <!-- the Staff Engineer R1 (Finding #1 / Disposition 2): malformed-row test added to AC. --> | gate | pending |
| AC2 | On a clean (disjoint) wave spec, the helper emits one paste-ready dispatch block per chunk, each containing: the chunk brief, an In/Out-of-scope peer block naming every peer chunk + its files, the destructive-action prohibition, the disk-first verification preamble, and `expected_branch: <current-branch>`. | `pending realization` (test: `grep:` each required token present once per block) | gate | pending |
| AC3 | The helper prints the 6–8 concurrency cap reminder and the "EM commits serially after the wave; executors do NOT commit" reminder; it does **not** inject any commit step into the emitted executor prompts; when chunk-count > 8, it prints a prominent cap-breach WARNING to **stdout**. | `pending realization` (test: `grep:` absence of commit verbs in emitted blocks; presence of cap reminder on stderr/stdout; >8-chunk spec → cap-breach warning present on stdout) <!-- the Staff Engineer R1 (Finding #5 / Disposition 5): >8-chunk sub-assertion added; stdout specified so it's visible in pasted output, not buried. --> | gate | pending |
| AC4 | The anti-monolith rule is greppable as a HARD RULE from boot surfaces: `em-operating-model.md` HARD RULES block AND coordinator `CLAUDE.md` § Subagent Dispatch, both naming the helper by path. | `pending realization` (test: `grep:` helper path in both files under the rule) | gate | pending |
| AC5 | `agent-dispatch-economics.md`'s § Overview and § The Economics table are re-anchored wall-clock-first (token/worktree overhead demoted to subordinate); the line-50 "overhead theater" smell test is retained verbatim (it was already correctly scoped to sub-60s); § When to EM-Inline is retained in substance. | `pending realization` (test: `cited:` § Overview now leads wall-clock-first AND the co-equal cost table is re-anchored; line-50 smell test retained verbatim; § When to EM-Inline retained in substance) <!-- the Staff Engineer R1 (Finding #3 / Disposition 3): AC5 test cell retargeted to match Chunk 3's revised scope. --> | gate | pending |
| AC6 | Contact-point completeness: the helper is discoverable from `/session-start`, `/workday-start`, `dispatching-parallel-agents.md`, and the global `~/.claude/CLAUDE.md` parallel-dispatch paragraph. | `pending realization` (test: `grep:` helper name in each of the 4 surfaces) | gate | pending |
<!-- the Staff Engineer R1: AC7 removed — Chunk 2b (advisory hook) cut by PM decision. The hook criterion is now moot. -->
| AC8 | The helper runs on a machine that is not the author's: no hardcoded paths, resolves git root and branch dynamically, degrades with a clear error (not silent skip) when run outside a git repo. | `pending realization` (test: `bash:` run from /tmp non-repo → clear non-zero error) | gate | pending |
| AC9 | A standalone `coordinator:fan-out` skill exists, EM-invokable without a plan doc, that invokes `bin/fan-out-dispatch.sh`, dispatches the compiled wave via `Agent` (respecting the 6–8 cap), and holds the EM-serial commit between waves. Carries the skill-scaffold checklist (destructive-action prohibition reference, explicit out-of-scope, discovery-surface integration). | `pending realization` (test: `cited:` SKILL.md has `allowed-tools` incl. Agent + Skill; `grep:` invokes the helper; `grep:` no per-executor commit injected; the skill halts and reports when the helper exits non-zero on overlap and does NOT proceed to Agent dispatch (test: dry-run with an overlapping spec → skill stops, zero Agent calls)) <!-- the Staff Engineer R1 (Finding #7 / Disposition 6): halt-on-non-zero test added — the skill must not dispatch past a helper collision report. --> | gate | pending |
| AC10 | `execute-plan` Phase 1.5 is refactored to invoke the shared mechanism (helper for overlap + `coordinator:fan-out` for dispatch); budget-sizing and non-overlap-gate prose are RETAINED (not deleted) as EM-judgment steps per the responsibility-split table; no duplicated wave-map logic between the two surfaces. | `pending realization` (test: `grep:` Phase 1.5 invokes helper for overlap + fan-out skill for dispatch; `cited:` budget-sizing and non-overlap-gate prose RETAINED as EM-judgment steps per the responsibility-split table) <!-- the Staff Engineer R1 (Finding #4 / Disposition 4): AC10 test cell retargeted to match the responsibility-split table. --> | gate | pending |

## Wave Map (this plan dogfoods fan-out)

```
Wave 0 (predecessor): Chunk 1 — fan-out helper + peer-scope snippet + test
   │  (Chunks 2-5 cite the helper path; it must exist on disk first — contract-change gate)
   ▼
Wave 1 (parallel, disjoint files):
   Chunk 2 — salience: boot-salient HARD RULE elevation<!-- the Staff Engineer R1: "optional PreToolUse advisory hook" removed; 2b cut by PM. -->
   Chunk 3 — agent-dispatch-economics.md rewrite
   Chunk 4 — contact-point wiring + cross-references
   Chunk 5 — coordinator:fan-out skill + execute-plan Phase 1.5 refactor
```

**File-overlap analysis (EM pre-dispatch pass):**

| Chunk | Files touched |
|-------|---------------|
| 1 | `bin/fan-out-dispatch.sh` (new), `bin/fan-out-dispatch.test.sh` (new), `snippets/peer-scope-block.md` (new) |
| 2 | `em-operating-model.md`, `coordinator/CLAUDE.md` (§ Subagent Dispatch) |
<!-- the Staff Engineer R1: hooks/hooks.json, hooks/scripts/nudge-fan-out.sh, docs/wiki/coordinator-tripwires.md dropped — those were Chunk 2b (hook) files. Chunk 2 is now 2a only. -->
| 3 | `docs/wiki/agent-dispatch-economics.md` |
| 4 | `skills/session-start/SKILL.md`, `commands/workday-start.md`, `docs/wiki/dispatching-parallel-agents.md`, `~/.claude/CLAUDE.md`, `docs/wiki/DIRECTORY_GUIDE.md` |
| 5 | `skills/fan-out/SKILL.md` (new), `skills/execute-plan/SKILL.md` |

Pairwise intersection of Wave-1 chunks (2,3,4,5) = ∅. Wave 1 parallelizes. Only gate is Wave 0 → Wave 1 (contract-change: the helper path the doctrine + skill cite must exist). Chunk 4 *names* the `coordinator:fan-out` skill in its cross-references but does not edit `skills/fan-out/SKILL.md` (Chunk 5 owns that file) — citation, not co-write, so no overlap. No output-consumption of helper *runtime* — chunks cite paths, they don't read output — but landing the path first keeps every cross-reference non-dangling.

---

## Chunk 1 — The fan-out helper (load-bearing, problem B) — NOVEL ITEM, full ceremony

**Files:** `bin/fan-out-dispatch.sh` (new), `bin/fan-out-dispatch.test.sh` (new), `snippets/peer-scope-block.md` (new).

**Goal:** collapse the entire fan-out ceremony into one EM-side call, so fanning out is the path of *least* resistance.

**Behaviour:**

1. **Input — simplest that works.** A TSV on stdin (or a `--spec <file>`), one row per chunk:
   ```
   <chunk-id>\t<brief-one-liner-or-@file>\t<comma-separated-file-paths>
   ```
   The `@file` form lets a long brief live in a file the EM already wrote. TSV chosen over YAML deliberately (OOS: no wave-spec DSL). **Parser hard-errors (non-zero exit, names the offending row) on any row not having exactly 3 tab-separated fields, on an empty required field, or on an embedded newline in a field. Briefs are one-liners or `@file` (no embedded tabs); file paths may not contain commas — fail loud, do not mis-split.** <!-- the Staff Engineer R1 (Finding #1 / Disposition 2): fail-loud on malformed input; mis-split on embedded tab or comma-in-path is a silent-corruption class bug. -->
2. **File-overlap intersection.** Compute the pairwise file intersection across chunks. **Detect-then-fail-loud** (per CLAUDE.md § Implementation Standards): any file in ≥2 chunks → exit non-zero, print the colliding file(s) and the chunk-ids, and instruct the EM to merge or sequence those chunks. **Never silently pick.** (AC1)
3. **Branch capture.** `expected_branch=$(git branch --show-current)`; hard-error with remediation if not in a git repo (AC8).
4. **Emit N paste-ready blocks.** For each chunk, print a fenced dispatch prompt containing, composed from `snippets/peer-scope-block.md` + the existing `snippets/text-only-recovery-preamble.md` conventions:
   - the chunk brief;
   - **In-scope** = this chunk's files + expected output;
   - **Out-of-scope — peer work, do NOT touch** = every *other* chunk's id + files, plus the verbatim "if a peer's output appears missing, assume a peer is on it" clause from `dispatching-parallel-agents.md` § Peer-Scope Prohibition;
   - the destructive-action prohibition block;
   - the disk-first verification preamble;
   - `expected_branch: <captured>`.
   (AC2)
5. **Reminders to the EM (stderr, not in executor prompts):** the 6–8 concurrency cap (divide by fan-out if any chunk is itself an orchestrator); "you commit serially after the wave with plain scoped `git add -- <paths>`; executors do NOT commit." No commit verb appears in any emitted block. **If chunk-count > 8, print a prominent WARNING to stdout (not buried in stderr): "N chunks exceeds the 6-8 concurrency cap; a wave this size is a PM call per § Concurrency Budget — use pilot→expand ramp or split into waves."** (AC3) <!-- the Staff Engineer R1 (Finding #5 / Disposition 5): cap-breach warning added — must be on stdout (not stderr) so it's visible in the EM's pasted output. -->

**Test (`bin/fan-out-dispatch.test.sh`):** overlap spec → non-zero + collision listed (AC1); malformed-row spec (wrong field count, empty field, embedded newline) → non-zero exit naming the offending row, no partial output emitted (AC1); clean 3-chunk spec → 3 blocks, each with all required tokens exactly once, peer blocks naming the other two (AC2); no commit verb in blocks + cap reminder present (AC3); run from non-repo dir → clear error (AC8). <!-- the Staff Engineer R1 (Finding #1 / Disposition 2): malformed-row test case added. -->

**Why a snippet for the peer-scope block:** the block currently exists only inlined in `dispatching-parallel-agents.md`. Externalize to `snippets/peer-scope-block.md` (template with `{{peer_chunks}}` placeholder) so the helper and the wiki cite one source. **Decision (the Staff Engineer R1 / Disposition 8): repoint `dispatching-parallel-agents.md` § Peer-Scope Prohibition to `snippets/peer-scope-block.md` (single source). No sync script — the wiki block is human/EM-read and can follow a pointer, unlike the runtime-inlined text-only preamble that `verify-text-only-sync.sh` exists for.** <!-- the Staff Engineer R1 (Finding #9 / Disposition 8): repoint-vs-sync resolved as repoint; sync script explicitly rejected — wiki is human-read and a pointer suffices; the verify-text-only-sync.sh pattern is for runtime-inlined text only. -->

**Ceremony (novel item):** full — this plan, prior-art-check, the Staff Engineer, post-impl code-review.

---

## Chunk 2 — Salience: boot-salient HARD RULE elevation (problem A)

<!-- the Staff Engineer R1 (Disposition 1): Chunk 2b (advisory hook) cut by PM decision. Chunk 2 is now the HARD-RULE elevation only. Files list reduced to em-operating-model.md and coordinator/CLAUDE.md — hooks/hooks.json, hooks/scripts/nudge-fan-out.sh, docs/wiki/coordinator-tripwires.md all dropped. 2a prefix removed; content promoted as the chunk body. -->

**Files:** `em-operating-model.md`, `coordinator/CLAUDE.md` (§ Subagent Dispatch).

- In `em-operating-model.md` HARD RULES, add/elevate: *"A large job is fanned out, or chunked into a sequence of fresh per-chunk agents — never one agent grinding chunk after chunk. To fan out, run `bin/fan-out-dispatch.sh` (it does the overlap pass and emits scoped prompts for you)."*
- In coordinator `CLAUDE.md` § Subagent Dispatch, add the same rule + helper pointer so it is greppable from the boot-loaded CLAUDE.md. (AC4)

---

## Chunk 3 — Objective-function rewrite (problem C)

**Files:** `docs/wiki/agent-dispatch-economics.md`.

**Goal:** re-anchor the decision rule on the PM's real priority ordering — **wall-clock first; token + worktree cost tangential** — without losing the legitimately-correct EM-inline carve-out.

- Rewrite the § Heuristic and § The Economics framing so the table presents token/worktree overhead as **subordinate to wall-clock**, not co-equal. The decision rule becomes: *"Default to dispatch for any non-trivial job; fan out when the job decomposes. EM-inline is the carve-out, not the default — reserved for sub-60s mechanical fixes on a known locus where worktree creation alone exceeds the work."*
- **Keep** § When to EM-Inline verbatim in substance (the sub-60s / known-locus / ≤3-file / already-loaded-context cases are correct).
- The line-50 "overhead theater" smell test is ALREADY correctly scoped to the sub-60s case — KEEP it verbatim. The over-application to re-anchor is (a) the § Overview line *"This is a real economic call, not a default-to-delegate rule"* and (b) the § The Economics table (lines ~20-27) presenting token/worktree overhead as co-equal with wall-clock. Re-anchor those two surfaces to wall-clock-first; do NOT touch the line-50 smell test. (AC5) <!-- the Staff Engineer R1 (Finding #3 / Disposition 3): retargeted — the smell test at line-50 is already correctly scoped; over-application is in § Overview and § The Economics table framing only. Preserves the valid carve-out verbatim per prior-art Claim #3. -->
- Cite the `tasks/lessons.md` 2026-05-20 *"Many agents often beat one [universal]"* antecedent as the empirical basis for the wall-clock-first reframing.
- Add a one-line cross-reference to the new helper, the `coordinator:fan-out` skill, and the anti-monolith HARD RULE.

**Reviewer rationale discrimination:** the rewrite must read differently than the original — if a reviewer couldn't tell the rewrite from the original by its bias, the edit is non-load-bearing. Test: the original answers "should I dispatch?" with "it depends, count the tokens"; the rewrite answers "fan out unless it's a sub-60s mechanical fix."

---

## Chunk 4 — Contact-point wiring + cross-references

**Files:** `skills/session-start/SKILL.md`, `commands/workday-start.md`, `docs/wiki/dispatching-parallel-agents.md`, `~/.claude/CLAUDE.md`, `docs/wiki/DIRECTORY_GUIDE.md`.

Per CLAUDE.md § Adding a Convention to the Coordinator System (conventions decay unless greppable from surfaces agents touch):

- `dispatching-parallel-agents.md`: add a § pointing at `bin/fan-out-dispatch.sh` (compiler) and `coordinator:fan-out` (dispatcher skill) as the canonical way to execute a fan-out wave; repoint the inlined peer-scope block to `snippets/peer-scope-block.md` (single source — no sync script, per Chunk 1 decision). <!-- the Staff Engineer R1 (Finding #9 / Disposition 8): "keep + sync-script" hedge resolved to repoint; Chunk 4 matches Chunk 1's resolved decision. -->
- Global `~/.claude/CLAUDE.md` parallel-dispatch paragraph ("serial work still chunks into a fresh agent per chunk…"): append the helper + `/fan-out` pointer so the boot-loaded global file names the tool.
- `/session-start` and `/workday-start`: one-line mention so the helper + `/fan-out` skill announce themselves in orientation (matches how other bin tools surface).
- `DIRECTORY_GUIDE.md`: index the new snippet.

**Note:** Chunk 4 edits the global `~/.claude/CLAUDE.md`, Chunk 2 edits the coordinator `CLAUDE.md` — different files, no overlap. Chunk 4 *names* `coordinator:fan-out` but Chunk 5 owns `skills/fan-out/SKILL.md` — citation, not co-write. Confirmed in the file-overlap table.

---

## Chunk 5 — `coordinator:fan-out` skill + execute-plan Phase 1.5 refactor (belt, PM-directed)

**Files:** `skills/fan-out/SKILL.md` (new), `skills/execute-plan/SKILL.md`.

**5a — `coordinator:fan-out` standalone skill (the in-the-moment verb):**
- `allowed-tools` includes `Agent`, `Skill`, `Bash`, `Read`, `Edit` — it must call `Agent` (the thing a bin script can't) and `Bash` (to run the helper).
- Procedure: (1) take the EM's chunk→files→brief spec (or build it from the current ad-hoc job); (2) run `bin/fan-out-dispatch.sh` to get the overlap verdict + compiled scoped prompts — **if the helper fails loud on overlap, stop and report the collisions, do not dispatch**; (3) dispatch the compiled wave via `Agent`, respecting the 6–8 concurrency cap (pilot→expand ramp; divide by fanout if any chunk is itself an orchestrator — per `dispatching-parallel-agents.md` § Concurrency Budget); (4) on wave return, the EM performs **one scoped commit** with plain `git add -- <paths>` (executors do NOT commit — per CLAUDE.md § Concurrent-EM Git Operations); (5) repeat for the next wave.
- **Skill-scaffold checklist (per `coordinator:plan` skill-scaffold row):** destructive-action prohibition is injected into every emitted executor prompt by the helper (verify it carries through); explicit out-of-scope list in the skill body; **not** a handoff/spinoff author (no PM-gated continuity artifacts); discovery-surface integration handled by Chunk 4.
- **Not PM-gated** — it is an execution verb (like `/execute-plan`), not a continuity/strategy artifact (like `/spinoff`, `/staff-session`). PM approval of the *work* is the authorization, same as execute-plan.

**5b — execute-plan Phase 1.5 refactor:**

<!-- the Staff Engineer R1 (Finding #4 / Disposition 4): responsibility-split table added so the executor knows exactly what the bin script owns vs. what is retained as EM-judgment prose. Caution added to prevent the executor from deleting budget-sizing or non-overlap-gate prose. -->

**Responsibility split after refactor:**

| Responsibility | Owner after refactor |
|---|---|
| file-overlap pass | helper (`bin/fan-out-dispatch.sh`) |
| scoped-prompt + peer-block emission | helper |
| wave dispatch + EM-serial commit | `coordinator:fan-out` skill |
| output-consumption & contract-change gate discrimination | EM judgment — RETAINED as Phase 1.5 prose |
| per-executor budget sizing (the "how many dispatches" axis) | EM judgment — RETAINED as Phase 1.5 prose |

**Caution:** An executor refactoring Phase 1.5 must NOT delete the budget-sizing or non-overlap-gate prose — those are EM-judgment steps a bin script cannot perform, and the budget-sizing axis is the literal subject of the 2026-05-26 lesson this plan exists to fix.

- Replace the prose "enumerate touched files / mark gates / write wave map / author peer-scope briefs" procedure with an **invocation** of the shared mechanism: run `bin/fan-out-dispatch.sh` for the wave compilation, and where Phase 1.5 dispatches a parallel wave, route through `coordinator:fan-out` so the dispatch logic lives in exactly one place.
- Keep Phase 1.5's *conceptual* explanation (the three gate types, the budget axis) as a one-paragraph rationale with a pointer — the doctrine stays readable, but the *executable* step is the helper/skill invocation, not in-head performance. **No duplicated wave-map logic between execute-plan and `coordinator:fan-out`.** (AC10)

**Ceremony:** Chunk 5 scaffolds a new skill → the `coordinator:plan` skill-scaffold checklist applies (above). Chunk 1 is still the novel *helper*; Chunk 5 is the novel *skill* — both warrant the Staff Engineer's eyes in this single Medium review.

---

## Cross-plan coordination

Scanned `docs/plans/*.md` for the touched file paths and the new abstraction (`fan-out-dispatch`). No live plan cites `agent-dispatch-economics.md`, `dispatching-parallel-agents.md`, the helper path, or `em-operating-model.md` HARD RULES — scanned, no overlapping file scope or seam citations. (Reviewer/coverage-checker to re-confirm against disk at review time.)

## Publish/percolation note

These files ship outward via `setup/publish.sh` (coordinator plugin → OSS publish target). The helper is generic (no holodeck/UE substrate) → ships to OSS coordinator-claude. No depersonalization concern beyond the existing publish pipeline. Flag at `/percolate` time, not in this plan.

## Outcome (session-end 2026-05-27)

Shipped in two commits on `work/striker/2026-05-26to27`: `5156ab30` (Chunk 1 — helper + test + snippet, 52/52 tests) and `55eb7d18` (Wave 1 — Chunks 2–5). Wave 1 was compiled by `bin/fan-out-dispatch.sh` itself (dogfood). All gate-bound ACs verified met except AC7 (intentionally cut). The Staff Engineer R1 APPROVED_WITH_NOTES; all findings integrated. Session-end `code-reviewer` pass on the two commits: see review trail.

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| Chunk 2b (PreToolUse monolith-smell hook) cut entirely | the Staff Engineer R1 + PM: heuristic can't discriminate monolith from a correct large/tech-lead dispatch; nudge fires after authoring cost paid; PreToolUse-on-every-Agent risks tune-out. 2a + helper-as-salience-trigger suffices. | 55eb7d18 |
| Executor trimmed the parallelism-vs-budget orthogonality sentence from coordinator/CLAUDE.md to fit the 39900-byte cap | The `check-claude-md-size.py` hook hard-blocks >39900B; executor reclaimed bytes from load-bearing prose (fight-the-hook). EM restored a compressed orthogonality clause + kept the faithful machine-local condensation as the byte-reclaim. | 55eb7d18 |
| session-start/SKILL.md, the improvement-queue, and dispatching-parallel-agents.md were entangled with a concurrent EM's whoami-spine work | Shared-branch concurrency. Staged only my hunks via `git apply --cached` + broad bleed-check; concurrent EM's hunks left for their commit. | 55eb7d18 |
| Helper input shape: TSV-on-stdin (as planned, no change) | the Staff Engineer confirmed TSV over YAML-DSL is correctly YAGNI-justified. | 5156ab30 |
| AC1 "comma-in-path → fail loud" reconciled to a documented format limitation (not a fail-loud case) | Session-end code-review: comma IS the field-3 delimiter, so a path containing a comma is fundamentally indistinguishable from two paths — undetectable, like a tab in a TSV field. Helper documents it; test asserts the known mis-split. The fail-loud guarantee holds for wrong-field-count / empty-field / embedded-newline. | pending |
