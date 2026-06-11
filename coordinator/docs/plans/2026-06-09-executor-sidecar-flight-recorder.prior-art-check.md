---
title: Prior-Art Check — executor-sidecar-flight-recorder
created: 2026-06-09
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-06-09-executor-sidecar-flight-recorder.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-09-executor-sidecar-flight-recorder.md`
**Verdict:** WARN
**Claims checked:** 14
**Conflicts:** 2 | **Compatible-but-relevant:** 8 | **Silent:** 4
**Corpora consulted:** project-wikis (43 files indexed) | global-wikis (n/a — project IS ~/.claude; same corpus) | lessons.md | improvement-queue

---

### Conflicts (plan contradicts prior art)

- **Claim #1 — archive/completed carve-out removal without BLOCK-COMPLETION-MONOLITH-WRITE update:**
  The plan asserts (AC-6, C3 dispatch) that `block-subagent-archive-write.sh` should drop the `archive/completed/YYYY-MM/<entry>.md` carve-out for executors, and that C3 also updates `block-subagent-archive-write.sh` only. The plan does NOT list updating `agents/executor.md` § Archive Fallback as a write-target for C1 (C1 strips § Write-Ahead Status and § Archive Fallback per the brief). But `docs/wiki/coordinator-tripwires.md` describes two *separately-scoped* runtime blocks:
  - **Plan asserts:** removing the per-entry carve-out from `block-subagent-archive-write.sh` is the complete closure of the archive-write path.
  - **Prior art (`plugins/coordinator/docs/wiki/coordinator-tripwires.md`, BLOCK-SUBAGENT-ARCHIVE-WRITE entry, lines 103–118):**
    > "Script: `hooks/scripts/block-subagent-archive-write.sh`. … Sanctioned per-entry fallback shape `archive/completed/YYYY-MM/<entry>.md` (executor.md § Archive Fallback). EM writes to archive/ (no agent_id) are always allowed."
  
    And separately (BLOCK-COMPLETION-MONOLITH-WRITE entry):
    > "executor.md § Archive Fallback" is also cited as the prose instruction layer: "executors under wrap-up pressure repeatedly self-log completion into archive/; this hook is the fail-closed backstop for the agents/executor.md § Key Constraints … 'Does NOT write anywhere under archive/ on its own initiative' baseline rule."
  - **Why this is a conflict:** The tripwires entry makes clear that `executor.md § Archive Fallback` is the *instruction layer* and the hook is the *enforcement layer* — they are a two-part pairing. The plan removes the instruction layer (§ Archive Fallback) in C1 and removes the hook's carve-out in C3, which is consistent. However, C3's write-files list in the dispatch ledger does NOT include `coordinator-tripwires.md` update for the BLOCK-SUBAGENT-ARCHIVE-WRITE entry — the tripwires entry references `executor.md § Archive Fallback` by name (line 19: "executor.md:277 mandates this write") and that backlink will become a dangling doctrine reference when § Archive Fallback is stripped in C1. The C5 doctrine sweep covers `coordinator-tripwires.md` only via AC-7 (registers the NEW hook), not via updating the OLD BLOCK-SUBAGENT-ARCHIVE-WRITE entry.
  - **Candidate directions for EM:**
    - `update-plan` — add updating the BLOCK-SUBAGENT-ARCHIVE-WRITE entry in `coordinator-tripwires.md` to C3 or C5 write-targets (strip the `executor.md:277` backlink reference from the entry's rationale prose)
    - `both` — the tripwires entry should also note the handoff from per-entry fallback to sidecar model; worth a one-line amendment in the same commit as C3
  - **Lean:** `update-plan` is likely sufficient — the C5 doctrine sweep already owns `coordinator-tripwires.md`, so this is a scope gap in C5, not a new chunk.

---

- **Claim #2 — plan body's `Status:` field cited in `writing-plans.md` as part of the write-ahead protocol:**
  The plan proposes stripping `**Status:**` from executor behavior, but `docs/wiki/writing-plans.md` (§ Plan Document Header) explicitly declares `Status:` as part of a mandatory plan document protocol that executors must maintain.
  - **Plan asserts:** "plan body becomes truly immutable to executors" and AC-8 strips `**Status:**` reads from `skills/pickup/SKILL.md` and `pipelines/workday-start-internals.md`.
  - **Prior art (`plugins/coordinator/docs/wiki/writing-plans.md`, lines 321–323):**
    > "The `Status:` field is part of the write-ahead protocol — it gets updated at every phase transition (review, enrichment, execution) so that crashed sessions leave unambiguous state. See ARCHITECTURE.md § 'The Write-Ahead Status Protocol' for the full state machine."
  - **Why this is a conflict:** `writing-plans.md` describes `Status:` as a mandatory cross-phase signal covering *review*, *enrichment*, and *execution* — not just executor-phase. The plan's out-of-scope note correctly excludes enricher stub-stamping from the change, but `ARCHITECTURE.md § Write-Ahead Status Protocol` and `writing-plans.md` both describe `Status:` as a plan-header field maintained by the EM across all phases. The plan's C5 doctrine sweep lists `writing-plans.md` as a write-target (AC-9), so the plan is aware this needs updating. The conflict is that the plan must ensure the `writing-plans.md` update is precise: preserve the *EM-authored* `Status:` header semantics (review/enrichment phases) while removing the *executor-stamped* status mechanics. The current plan language in C5 ("repoint the protocol semantics: executor uses sidecar…") may be underspecified for a reviewer — it could be read as stripping the entire `Status:` field from the plan header doc.
  - **Candidate directions for EM:**
    - `update-plan` — add a negative-spec in C5 brief: "preserve the plan-header `Status:` field semantics for EM-authored phase transitions (review, enrichment); the change is executor-phase only; the write-ahead protocol for EM-owned status transitions is unchanged"
    - `update-prior-art` — if the intent IS to also strip the plan-header `Status:` field entirely (replacing it with commit log), that is a larger scope change that the plan's Out of Scope section does not acknowledge; surface to EM for scoping decision
  - **Lean:** `update-plan` — the plan's Out of Scope section explicitly preserves enricher stub-stamping, strongly implying EM-authored status transitions are also preserved; C5 brief just needs the negative-spec stated.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #3 — executor freelance-edits plan body are structural, not instructional:**
  - **Plan covers:** "Brief text doesn't reliably override agent-prompt MUST. The fix is structural, not textual." (§ Problem, line 19)
  - **Prior art (`plugins/coordinator/docs/wiki/delegate-execution.md`, § Executor brief compliance, lines 350–356):**
    > "Executors self-mark plan-status fields and archive entries despite explicit 'do not edit X' briefs — the impulse is structural, not a reading error. … gate Status edits via schema-validation hook + frontmatter enum (catches invalid values mid-write), or move plan-status into a derived view computed from the archive log. Stop assuming briefs alone are the enforcement; they're the policy, hooks are the enforcement."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's Problem section would be strengthened by citing this established prior (the diagnosis was already captured and promoted). Informational — not a blocker.

- **Claim #4 — `tasks/` is the right home for executor sidecars:**
  - **Plan covers:** sidecar at `tasks/<plan-slug>/flight/<chunk-id>.md`, cleaned up at `/workstream-complete`.
  - **Prior art (`plugins/coordinator/CLAUDE.md`, § state/ vs tasks/):**
    > "`tasks/` holds UUID flight-recorder dirs + dated reports + loose scratch. `/distill` and `/update-docs` sweep here aggressively. Writing a load-bearing surface (any allowlist name) under `tasks/` is a tripwire — see `docs/wiki/coordinator-tripwires.md` § tasks-state-folder-split."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's sidecar path is consistent with `tasks/` ephemera doctrine. The plan should add a note in the sidecar spec (§ Sidecar shape) or § Percolation clarifying that `tasks/<plan-slug>/flight/` is NOT in the `state/` allowlist and will not false-trigger the `tasks-state-folder-split` tripwire. Informational — sidecars at this path are correctly ephemeral.

- **Claim #5 — scratch lifecycle: fold-and-delete at workstream-complete (AC-11):**
  - **Plan covers:** AC-11 directs EM to fold noteworthy sidecar observations into `## Execution Observations` in the plan body at `/workstream-complete`, then delete the sidecar directory.
  - **Prior art (`plugins/coordinator/docs/wiki/scratch-lifecycle.md`, § Pattern A, lines 9–17):**
    > "Phase N (final, after canonical outputs are committed): `rm -rf tasks/scratch/<skill>/<run-id>/` … The skill's last act is to delete its own working directory. Canonical outputs (the wiki edits, the queue closures, the archive entries, the doc updates) are already committed; the scratch was load-bearing only during the run. Deletion is unconditional on success; on failure the scratch is preserved for diagnosis."
  - **Subtype:** `cite`
  - **Suggested action:** AC-11's fold-and-delete shape is directly compatible with Pattern A. The plan should reference `scratch-lifecycle.md` Pattern A in the workstream-complete phase spec (AC-11 criterion prose) to anchor the cleanup contract. The `scratch-lifecycle.md` pattern also establishes "on failure, scratch is preserved for diagnosis" — worth mirroring in the sidecar spec (e.g. a `status: thrashing` sidecar should survive past workstream-complete for diagnosis).

- **Claim #6 — dispatch ledger is the canonical EM-side in-plan surface:**
  - **Plan covers:** "Dispatch ledger (`## Dispatch Ledger` table, `skills/execute-plan/SKILL.md` Phase 1.6) remains the EM's in-plan canonical surface."
  - **Prior art (`plugins/coordinator/skills/execute-plan/SKILL.md`, Phase 1.6 spec-backlink comment, lines 72–76):**
    > "spec-backlink: this skill's 2026-05-30 failure — gate graph correctly produced 4 chunks … EM narrated 'delegate the chunker to a focused executor' then dispatched '3b + 3a + 2' as ONE 23-minute executor. The prose rule in Phase 1.5 ('can't parallelize ≠ one dispatch') was present and ignored; this ledger converts it into a mechanical artifact where the bundle is malformed on its face."
  
    And `state/coordinator-improvement-queue.md` (2026-05-31, ledger-granularity entry):
    > "ledger sub-chunks that collapse to one agent are theater — ledger granularity must equal dispatch granularity | proposed target: skills/execute-plan Phase 1.6"
  - **Subtype:** `cite`
  - **Suggested action:** The plan is correctly building on established doctrine. Worth citing Phase 1.6's existing canonical status explicitly in C2's brief so the executor adds the sidecar convention as an *extension* to the existing ledger schema, not a competing surface.

- **Claim #7 — executor "no-commit" structural enforcement, not prose:**
  - **Plan covers:** hook-based unconditional tripwire on plan body writes (PreToolUse), replacing prose prohibition.
  - **Prior art (`plugins/coordinator/docs/wiki/delegate-execution.md`, § No-commit briefs need structural enforcement, lines 359–365):**
    > "Executors ignore explicit no-commit constraints under chunk-mode — 'DO NOT commit' in a brief will be overridden by the executor's chunk-completion convention. … either enforce no-commit via `settings.json` deny on `git commit`, or accept that committers will commit and use an EM-side review/amend pattern after the executor returns. Prose alone is not binding against a structural prior."

    And `state/coordinator-improvement-queue.md` (2026-06-09, executor no-commits entry):
    > "Executor 'no commits' constraint needs stronger enforcement than dispatch-brief wording — eager executors commit anyway; recurring class of EM-serial-commit-bypass. | proposed target: coordinator-safe-commit --expected-owner em-only flag, OR pre-commit hook fail-under-executor-identity, OR coordinator:executor agent prompt destructive-action-style hard prohibition + structural withholding of git via mode flag"
  - **Subtype:** `cite`
  - **Suggested action:** The plan's PreToolUse hook on plan bodies is exactly the "structural enforcement" shape the prior art calls for. The improvement queue entry proposes `coordinator-safe-commit --expected-owner em-only` as an additional shape — the plan author should note in the plan whether the new `block-subagent-plan-body-write.sh` hook is intended as the complete structural fix for plan-body writes specifically, while the broader "no commits" enforcement remains a separate improvement-queue item.

- **Claim #8 — fan-out-dispatch.sh must create sidecar files (C2):**
  - **Plan covers:** C2 extends `bin/fan-out-dispatch.sh` to create `tasks/<plan-slug>/flight/<chunk-id>.md` per chunk.
  - **Prior art (`plugins/coordinator/docs/wiki/scratch-lifecycle.md`, § Where this surfaces, lines 44–52):**
    > "The skill-author convention: name the scratch path under `tasks/scratch/<skill>/<run-id>/` so a single `.gitignore` rule and a single cleanup convention cover them all."
  - **Subtype:** `cite`
  - **Suggested action:** The plan uses `tasks/<plan-slug>/flight/` rather than `tasks/scratch/<skill>/`. This is a deliberate divergence — flight sidecars are plan-scoped, not skill-scoped — but it should be noted in C2's brief so the executor doesn't normalize to the `scratch/` convention. The path also needs a `.gitignore` consideration: are `tasks/*/flight/` dirs tracked? The scratch-lifecycle wiki suggests they should be gitignored or auto-cleaned. AC-12 covers distill sweep targeting but the plan doesn't address `.gitignore` for the new path — worth a note in C2.

- **Claim #9 — sidecar immutability pattern (existing SIDECAR-IMMUTABILITY-CHECK tripwire):**
  - **Plan covers:** sidecars are the executor's write surface; the executor MUST NOT touch plan bodies.
  - **Prior art (`plugins/coordinator/docs/wiki/coordinator-tripwires.md`, SIDECAR-IMMUTABILITY-CHECK entry, lines 100–102):**
    > "The review-integrator's baseline prompt carries a `## Sidecar Immutability` section that prohibits the integrator from writing back to or modifying any sidecar file it reads. Per-dispatch 'DO NOT touch sidecars' instructions compete with the baseline prompt and lose under context pressure — the constraint must live in the baseline prompt itself, not only in the dispatch brief."
  - **Subtype:** `cite`
  - **Suggested action:** The existing SIDECAR-IMMUTABILITY-CHECK applies to review-integrators, not executors. The plan introduces an analogous concept (executor owns its sidecar; EM is read-only on sidecars mid-dispatch). C1's new `agents/executor.md` § Flight-Recorder Sidecar section should include an explicit negative-spec: "the EM does NOT edit the sidecar during execution — the executor owns it until workstream-complete fold." This mirrors the integrator's immutability doctrine and prevents EM overwriting an in-flight executor's status record. Not a blocker; informational to the Staff Engineer.

- **Claim #10 — workstream-complete fold of executor observations (AC-11) — scratch-surface→fold+delete precedent:**
  - **Plan covers:** AC-11 describes EM-authored fold of executor observations into `## Execution Observations` appended to the plan body at `/workstream-complete`.
  - **Prior art (`plugins/coordinator/docs/wiki/scratch-lifecycle.md`, § When scratch IS useful post-ship, lines 37–43):**
    > "Two narrow cases: 1. Diagnostic artifacts for a failed run … 2. Cross-session ledgers that the skill itself reads on next run. … Anything that is neither of those is post-ship noise."
    
    And (§ Anti-patterns):
    > "Leaving scratch around 'in case it's useful.' It almost never is. The conclusions that were useful are already in the canonical outputs. The notes that led to those conclusions are not load-bearing once the conclusion has shipped."
  - **Subtype:** `cite`
  - **Suggested action:** AC-11's "fold genuinely-noteworthy observations" is compatible with scratch-lifecycle Pattern A — the fold IS the canonical output extraction step. But the scratch-lifecycle wiki raises a useful question for the plan author: if the sidecar observations are truly noteworthy, where do they land? `## Execution Observations` in the plan body is a plan-ephemeral section (`/distill` drops it as `[EPHEMERAL]` alongside `## Deviations`). If an observation is noteworthy enough to fold, it may warrant a wiki or lesson capture rather than a plan-body append. Suggest the C5 or AC-11 implementation brief note that `## Execution Observations` is `[EPHEMERAL]` and encourage routing genuinely cross-session learnings to `state/lessons.md` instead.

---

### Silent areas (no prior art found)

- **Claim #11 — `tasks/<plan-slug>/flight/` as a specifically-named subfolder convention:** no prior art in any corpus. `flight/` as a subdirectory name under a plan-scoped tasks path is novel; the closest prior art is `tasks/scratch/<skill>/<run-id>/` but the plan uses a different path shape. Silent.

- **Claim #12 — sidecar frontmatter schema (v1) with `status: dispatched | in_flight | complete | blocked | thrashing` transitions:** no prior art in any corpus. The status enum mirrors executor report verbs but the frontmatter schema for a per-chunk flight sidecar is novel. Silent.

- **Claim #13 — removing `tasks/<plan-slug>/flight/` as a distill sweep target (AC-12):** no prior art in any corpus on distill specifically registering per-plan sidecar directories as sweep targets. The `scratch-lifecycle.md` wiki covers the pattern generically but not a distill-skill registration mechanism. Silent.

- **Claim #14 — `sidecar_path:` field injected by fan-out-dispatch.sh into executor briefs:** no prior art in any corpus. The fan-out brief envelope extension with a `sidecar_path:` key is novel. Silent.

---

### Verdict logic

**WARN** — Two conflicts surfaced. Both are plan-completeness issues (a dangling backlink in `coordinator-tripwires.md` when § Archive Fallback is stripped; and a precision gap in C5 around what exactly gets updated in `writing-plans.md` for the `Status:` field). Neither conflict blocks execution if the EM adds the two targeted amendments to the plan before dispatching:

1. **Conflict #1 (BLOCK-SUBAGENT-ARCHIVE-WRITE backlink):** Add `coordinator-tripwires.md` BLOCK-SUBAGENT-ARCHIVE-WRITE entry amendment to C3 or C5 write-targets — specifically strip the `executor.md:277 mandates this write` backlink from that entry's rationale.

2. **Conflict #2 (writing-plans.md Status: precision):** Add a negative-spec to C5 brief: preserve the EM-authored `Status:` plan-header semantics (review, enrichment transitions); the change is executor-phase only.

The eight compatible-but-relevant items are informational for the Staff Engineer's review. Items #5 (scratch-lifecycle alignment), #8 (gitignore for `tasks/*/flight/`), and #9 (sidecar immutability EM-side negative-spec) are worth a look in review.

---

**Cost estimate:** ~9,200 tokens (14 claims × ~3 corpus reads average, with 6 full-document reads on key sources)
