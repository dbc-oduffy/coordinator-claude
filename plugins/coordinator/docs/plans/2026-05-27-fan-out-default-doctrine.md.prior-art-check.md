---
title: Prior-Art Check — fan-out-default-doctrine
created: 2026-05-27
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-05-27-fan-out-default-doctrine.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-27-fan-out-default-doctrine.md`
**Verdict:** COMPATIBLE
**Claims checked:** 15
**Conflicts:** 0 | **Compatible-but-relevant:** 5 | **Silent:** 10
**Corpora consulted:** project-wikis (88 files indexed under `plugins/coordinator/docs/wiki/`) | global-wikis (22 files indexed under `~/.claude/docs/wiki/`) | lessons.md | improvement-queue (`~/.claude/tasks/coordinator-improvement-queue.md`)

---

### Conflicts (plan contradicts prior art)

No conflicts found.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #1 — Pre-existing HARD RULE in `em-operating-model.md`:** The plan asserts that `"2+ independent tasks → batch-dispatch in parallel, never sequential"` already exists as a HARD RULE in `em-operating-model.md`. Verified: the rule is present exactly as quoted at the HARD RULES block, lines 22–23.
  - **Plan covers:** The plan's central premise is that this rule exists and is being elevated, not invented.
  - **Prior art (`plugins/coordinator/em-operating-model.md`, lines 18–23):** "## HARD RULES\n- Once a goal is set, IMMEDIATELY create a task list (TaskCreate) before any work.\n[...]\n- 2+ independent tasks → batch-dispatch in parallel, never sequential"
  - **Subtype:** `cite`
  - **Suggested action:** Confirmed — the rule exists verbatim. Chunk 2a's "add/elevate" framing is accurate; the rule is already there but not yet pointing at the helper. No plan correction needed; confirmation strengthens the plan's premise.

- **Claim #2 — Pre-existing anti-monolith rule in `dispatching-parallel-agents.md`:** The plan asserts that `"One agent grinding a sequence of chunks is itself the antipattern — the overload in slow motion"` and `"a new agent per chunk, not one agent handed chunk after chunk"` already exist in § Coupling Rules Out Concurrency. Verified: both quoted passages are present at lines 128 and 127 respectively, tagged with empirical motivation dated 2026-05-26.
  - **Plan covers:** The plan names this as existing prior art the rule was violated against one day after writing.
  - **Prior art (`plugins/coordinator/docs/wiki/dispatching-parallel-agents.md`, lines 124–136):** "**'Can't parallelize' ≠ 'must be one dispatch.'** Coupling removes *concurrency*; it does not remove *decomposition*. [...] **a new agent per chunk, not one agent handed chunk after chunk.** [...] **One agent grinding a sequence of chunks is itself the antipattern — the overload in slow motion.**"
  - **Subtype:** `cite`
  - **Suggested action:** Confirmed — both passages are present verbatim. The Chunk 4 contact-point wiring to `dispatching-parallel-agents.md` is appropriate; the wiki already encodes the rule but lacks the helper pointer.

- **Claim #3 — `agent-dispatch-economics.md` "overhead theater" framing:** The plan identifies this as the source of objective-function drift (problem C) and proposes a rewrite. The existing text is verified as stated.
  - **Plan covers:** Chunk 3 rewrites `agent-dispatch-economics.md` to anchor wall-clock-first, retaining the sub-60s EM-inline carve-out, and removes "overhead theater" as a general caution.
  - **Prior art (`plugins/coordinator/docs/wiki/agent-dispatch-economics.md`, lines 10–11, 50):** "This is a real economic call, not a default-to-delegate rule." [...] "A useful smell test: if the EM's dispatch prompt would be 'read file X, change line Y, report back' — and the EM already has file X in context — the dispatch is overhead theater, not delegation."
  - **Subtype:** `cite`
  - **Suggested action:** The "overhead theater" phrase currently lives under § Heuristic and is correctly scoped to the sub-60s mechanical case in the existing text, but the § Overview framing ("real economic call, not a default-to-delegate rule") is unqualified and supports the plan's diagnosis. The plan's rewrite intent is compatible with the existing carve-out content; the rewrite must preserve the `§ When to EM-Inline` block verbatim in substance (per AC5). The plan correctly notes this. No conflict; cite for Chunk 3 reviewers.

- **Claim #4 — lessons.md "Many agents often beat one" entry:** Directly confirms the under-parallelization failure mode the plan diagnoses.
  - **Plan covers:** Problem statement A (salience failure) and the empirical motivation for the rule.
  - **Prior art (`tasks/lessons.md`, line 85 in prior-art-checker's read window — "Many agents often beat one — don't overload a single Sonnet when the work decomposes [universal]" 2026-05-20):** "Dispatched one Sonnet `general-purpose` scout to do an enumeration spanning ~10 independent chunks [...] Crashed at ~35min / 43 tool uses with a socket-disconnect; only 1 of 10 deliverables landed. PM correction: should have dispatched N parallel Sonnets at the natural decomposition unit, not one scout to do everything. [...] Default bias: when the dispatch brief contains 'for each X, do Y' with X≥3 independent items, the right shape is N agents, not one. Anti-pattern signature: one `Agent` dispatch whose prompt enumerates ≥3 independent targets and asks for one combined deliverable."
  - **Subtype:** `cite`
  - **Suggested action:** This lesson is a direct empirical antecedent to the plan. The plan should cite it in its Problem section or at minimum the Chunk 2a rationale. Improvement-queue entry `2026-05-20 | project-rag-ue-addon | tasks/lessons.md:285 | Single-sequential executor wrong shape for chunked-mechanical work — fan out or EM-direct | proposed target: coordinator/CLAUDE.md § Executor Dispatch Mode or docs/wiki/writing-plans.md § Dispatch shape` is also directly relevant — this plan likely resolves that queue entry. The plan does not name it; the integrator should confirm closure at landing time.

- **Claim #5 — No existing fan-out helper / dispatch-prompt emitter under `bin/` or `snippets/`:** The plan states the EM pre-checked and found none. Verified independently by full glob of `bin/` and `snippets/`.
  - **Plan covers:** Claim that `bin/fan-out-dispatch.sh` is genuinely new (no duplicate).
  - **Prior art (`plugins/coordinator/bin/` and `snippets/`):** Full glob confirms: 80+ bin scripts present; none named `fan-out*`, `dispatch-emit*`, `wave-dispatch*`, `parallel-dispatch*`, or similar. Snippets directory contains 9 files; none is a fan-out or peer-scope block emitter. `snippets/text-only-recovery-preamble.md` is cited by the plan as a pattern to follow — it exists.
  - **Subtype:** `cite`
  - **Suggested action:** No duplication risk confirmed. Plan's no-duplicate claim is accurate. `snippets/text-only-recovery-preamble.md` exists at the expected path, confirming the plan's Chunk 1 reference is valid.

---

### Silent areas (no prior art found)

- Claim #6 — `snippets/peer-scope-block.md` as a new externalized template: no prior art on snippet-sync patterns beyond the existing `verify-text-only-sync.sh` model cited by the plan. The plan's reference to that model is the right anchor; no additional prior art surfaced.
- Claim #7 — Chunk 2b: new optional PreToolUse `Agent` advisory hook with monolith-smell heuristic: no prior art on `Agent`-matcher hooks in `hooks/hooks.json` or `hooks/scripts/`. Confirmed: existing hooks target `Write`, `Edit`, `MultiEdit`, `Bash` matchers per the lessons.md entry about block-unauthorized-handoff.sh. No `Agent`-matcher hook is currently registered. The hook-best-practices.md wiki exists but contains no Agent-matcher precedent.
- Claim #8 — Wall-clock-first / tokens-tangential as the PM's priority ordering: no prior art document explicitly states this priority ordering. The plan is establishing it. Not a conflict — it is an un-codified PM preference the plan is making load-bearing for the first time.
- Claim #9 — TSV input format for the helper (over YAML): no prior art on dispatch-helper input formats. YAGNI justification stands.
- Claim #10 — Helper degrades with clear error outside git repo: no prior art. AC8 is novel engineering constraint.
- Claim #11 — `bin/verify-peer-scope-sync.sh` (conditional, if wiki keeps a copy of peer-scope block): no existing peer-scope sync script; the pattern mirrors `verify-text-only-sync.sh` which does exist. Reviewer decision on repoint-vs-sync is correctly flagged in the plan.
- Claim #12 — Helper ships to OSS coordinator-claude: no prior art on per-helper OSS eligibility checks. The plan notes it is generic (no holodeck/UE substrate). OSS distribution doctrine (`CLAUDE.local.md` § Editorial principle) is satisfied; no conflict.
- Claim #13 — Contact-point wiring to `/session-start` and `/workday-start`: no prior art on how other bin tools surface in orientation. The plan asserts this is the established pattern without citing which tool was first; no conflict found.
- Claim #14 — Wave 0 → Wave 1 gate is contract-change (helper path must exist before doctrine cites it): no prior art conflicts. The plan's file-overlap analysis is correct per the dispatching-parallel-agents.md § Dispatch-Gate Taxonomy — "Output-consumption" and "Contract-change dependency" are the two real gates cited.
- Claim #15 — No live plan conflicts with touched file paths: no prior art found in `docs/plans/*.md` that cites the touched files. The plan self-reports this scan; no independent hits found during corpus search.

---

### Verdict logic

**COMPATIBLE** — zero conflicts. The plan's central premise (the rule already exists; this plan makes it load-bearing) is confirmed by direct reading of the cited files. The anti-monolith rule exists verbatim in `em-operating-model.md` HARD RULES and in `dispatching-parallel-agents.md` § Coupling Rules Out Concurrency exactly as quoted. No `fan-out-dispatch.sh` or peer-scope snippet exists under `bin/` or `snippets/` — the Chunk 1 deliverable is genuinely new. The `agent-dispatch-economics.md` framing the plan proposes to correct exists as diagnosed. Five compatible-but-relevant items are informational; none requires plan changes before review dispatch.

**Improvement-queue closure note (for integrator):** The central improvement queue entry `2026-05-20 | project-rag-ue-addon | tasks/lessons.md:285 | Single-sequential executor wrong shape for chunked-mechanical work — fan out or EM-direct | proposed target: coordinator/CLAUDE.md § Executor Dispatch Mode or docs/wiki/writing-plans.md § Dispatch shape` is likely resolved by this plan's Chunk 2a landing. The integrator should confirm and delete that entry in the same commit.

**Cost estimate:** ~6K tokens (15 claims × 5 corpus reads per claim average; 3 full-file reads of large wikis, 2 glob inventories, 1 lessons.md read, 1 improvement-queue read)
