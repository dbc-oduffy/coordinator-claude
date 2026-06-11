---
title: Executor flight-recorder sidecars — strip plan-body stamping, give executors their own surface
created: 2026-06-09
scope_mode: feature
status: shipped
shipped_commits: a8d9db4c..1ef64afc
source_memo: cross-repo/inbox/2026-06-09-executor-scope-creep.md
source_em: project-rag-ue-addon-em
percolates_to: coordinator-claude OSS distribution (via setup/publish.sh)
---

# Executor flight-recorder sidecars — strip plan-body stamping, give executors their own surface

## Problem

Executor agent prompt (`agents/executor.md` § Write-Ahead Status, lines 66–83) **mandates** that every dispatched executor stamp `**Status:** Execution in progress` and then `**Status:** Execution complete — pending verification` into its own chunk's section of the plan markdown — framed as crash-safety infrastructure.

EM-side anti-scope blocks instructing "do not touch the plan" lose to the agent-prompt MUST 67% of the time. Empirical: project-rag-ue-addon `2026-06-09-ceiling-growth-models-hnsw-and-heavy-tier-rss` workstream, 6 executor dispatches, 4 plan-stamps (one under the wrong chunk's header), 2 unsolicited `archive/completed/` self-logs. EM-side commit-gate constraint-adherence revert caught all six, but per-dispatch revert is unsustainable and the rate is a property of the agent prompt, not the briefs.

Diagnosis: this is **agent-prompts-fighting-the-executor**. Brief text doesn't reliably override agent-prompt MUST. The fix is structural, not textual.

Prior art on this diagnosis is established. `docs/wiki/delegate-execution.md` § Executor brief compliance: *"Executors self-mark plan-status fields and archive entries despite explicit 'do not edit X' briefs — the impulse is structural, not a reading error. … Stop assuming briefs alone are the enforcement; they're the policy, hooks are the enforcement."* And the central improvement queue carries the 2026-06-09 entry *"Executor 'no commits' constraint needs stronger enforcement than dispatch-brief wording"* — the analogous structural-enforcement gap. This plan addresses the plan-body half of that gap; broader no-commit-by-subagent enforcement remains its own queue item.

## Shape

PM-directed (verbatim, 2026-06-09):

> "we have agent prompts fighting their executor. it's okay if we switch this around such that the EM is responsible for tracking dispatches and in flight, while the executor doesn't stamp the plan anymore. … We should be opinionated and go for the best solution"
>
> "alternatively we could have the EM responsible for making a short flight recorder plan sidecar for a tracker and the executors are responsible for tagging that with 'in flight' and 'complete' and different observations, rather than the core plan file itself"

Adopted shape: **executor flight-recorder sidecars**.

- EM creates a per-chunk sidecar file at dispatch time (`tasks/<plan-slug>/flight/<chunk-id>.md`).
- EM passes `sidecar_path:` to the executor brief.
- Executor stamps in-flight + completion status + observations into **the sidecar**, never the plan body.
- Plan body becomes truly immutable to executors. PreToolUse tripwire fires-closed on subagent Edit/Write of `docs/plans/**/*.md`.
- Dispatch ledger (`## Dispatch Ledger` table, `skills/execute-plan/SKILL.md` Phase 1.6) remains the EM's in-plan canonical surface — readers consulting "is chunk N done?" read the ledger row, not a body stamp.
- `archive/completed/YYYY-MM/<entry>.md` per-entry fallback (sanctioned by the existing `block-subagent-archive-write.sh` carve-out) goes away — sidecars supersede it. The tripwire carve-out for that path is removed.

Why this beats "strip everything, EM tracks it all":
- Preserves the genuine value of crash-safety stamping (which is real — a crashed executor leaves a stamped sidecar saying what it was doing).
- Preserves the executor's ability to record observations / latent-bug notes / mid-flight concerns in a structured place the EM can read post-hoc.
- The write-disjoint property (one sidecar per chunk, owned by one executor) means sibling clobber is mechanically impossible.
- The tripwire on plan bodies can be **unconditional** — there's no carve-out for "your section's status line." The executor's home turf is its sidecar, not a slice of the plan.

## Acceptance Criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|---|---|---|---|---|
| AC-1 | `agents/executor.md` no longer contains § Write-Ahead Status or any directive to stamp status into a plan body. | `cited:` `plugins/coordinator/agents/executor.md` (EM-verified: grep for "Write-Ahead Status" / "Execution in progress" / "Execution complete — pending verification" returns zero matches; commit a8d9db4c) | gate-bound | shipped |
| AC-2 | `agents/executor.md` contains a § Flight-Recorder Sidecar section naming the sidecar path convention. | `cited:` `plugins/coordinator/agents/executor.md` (EM-verified: 8 matches for "Flight-Recorder Sidecar"/"sidecar_path"; commit a8d9db4c) | gate-bound | shipped |
| AC-3 | `agents/executor.md` no longer contains § Archive Fallback or any directive to write under `archive/completed/`. | `cited:` `plugins/coordinator/agents/executor.md` (EM-verified: zero matches for "Archive Fallback"/"archive/completed/"; commit a8d9db4c) | gate-bound | shipped |
| AC-4 | `bin/fan-out-dispatch.sh` creates a sidecar file per chunk at `tasks/<plan-slug>/flight/<chunk-id>.md` and emits `sidecar_path:` in the per-chunk brief. | `cited:` `plugins/coordinator/bin/fan-out-dispatch.sh` (EM-verified: --plan flag added, sidecar creation block idempotent, 87 existing tests pass; commit 0ab507d7) | gate-bound | shipped |
| AC-5 | `hooks/scripts/block-subagent-plan-body-write.sh` exists, executable, denies subagent Edit/Write on plan markdown under `docs/plans/` with carve-out for the sidecar path under `tasks/<plan-slug>/flight/`. Anchor pattern handles absolute paths (Windows `C:` and Unix `/c/` prefixes). `archive/specs/` is NOT a deny target. | `cited:` `plugins/coordinator/hooks/scripts/block-subagent-plan-body-write.sh` (EM-verified: 100755 exec bit, 8969 bytes, both anchor patterns present (23 grep matches), 4/4 smoke tests pass — deny plans, allow sidecar, allow EM, deny absolute Windows path; commit e4b1fbfe) | gate-bound | shipped |
<!-- Review: the Staff Engineer — added (^|/) anchors to handle absolute path forms (Windows C:/ and Unix /c/ prefixes), mirroring pattern in block-subagent-archive-write.sh; archive/specs/** excluded as non-target -->
| AC-6 | `block-subagent-archive-write.sh` no longer carves out `archive/completed/YYYY-MM/<entry>.md` for subagents (daily-summaries carve-out preserved). | `cited:` `plugins/coordinator/hooks/scripts/block-subagent-archive-write.sh` (EM-verified: per-entry carve-out block removed (zero matches for archive/completed/.+\.md), daily-summaries carve-out preserved (8 matches), smoke tests pass: subagent write to archive/completed/2026-06/foo.md now denied, daily-summaries write still allowed; commit 62bb1cd9) | reviewer-judgment | shipped |
<!-- Review: the Staff Engineer — prior pattern used double-escaped brackets matching literal [ and ] rather than regex character classes; replaced with cited: + EM-side smoke test evidence -->
| AC-7 | `coordinator-tripwires.md` registers `EXECUTOR-PLAN-BODY-IMMUTABLE` with the new hook script path. | `cited:` `plugins/coordinator/docs/wiki/coordinator-tripwires.md` (EM-verified: 3 matches for "EXECUTOR-PLAN-BODY-IMMUTABLE"/"block-subagent-plan-body-write"; dangling executor.md:277 backlink also stripped; commit 62bb1cd9) | gate-bound | shipped |
| AC-8 | `skills/pickup/SKILL.md` and `pipelines/workday-start-internals.md` no longer consult `**Status:**` from plan bodies as closure signal; they read the dispatch ledger or commit log instead. | `cited:` `plugins/coordinator/skills/pickup/SKILL.md` `plugins/coordinator/pipelines/workday-start-internals.md` (EM-verified: both files now consult ## Dispatch Ledger + git log as primary closure signals, plan-header Status: kept valid for EM phase transitions, "executors no longer stamp" phrase present in both; commits 17b12abf + 19d4400b) | reviewer-judgment | shipped |
<!-- Review: the Staff Engineer — negative grep on the word "field" was fragile; replaced with cited: + dual-file evidence -->
| AC-9 | The six doctrine surfaces (`ARCHITECTURE.md`, `em-operating-model.md`, `README.md`, `docs/wiki/delegate-execution.md`, `docs/wiki/reviewer-pipeline.md`, `docs/wiki/writing-plans.md`) are updated to reflect the sidecar shape; remaining Write-Ahead Status references are scoped to enricher stub-stamping or to historical changelog entries. | `cited:` `plugins/coordinator-claude/ARCHITECTURE.md` `plugins/coordinator/em-operating-model.md` `plugins/coordinator/README.md` `plugins/coordinator/docs/wiki/delegate-execution.md` `plugins/coordinator/docs/wiki/reviewer-pipeline.md` `plugins/coordinator/docs/wiki/writing-plans.md` (all six landed: commits c2c358e6, 35e0574a, 8f8a9b83, 45366695, 5e75e8cd, d4749467) | reviewer-judgment | shipped |
| AC-10 | Source memo at `cross-repo/inbox/2026-06-09-executor-scope-creep.md` flipped to `status: actioned`, `decision: accepted`, `decision_note:` pointing at this plan's path. | `cited:` `cross-repo/inbox/2026-06-09-executor-scope-creep.md` (EM-verified: frontmatter shows status: actioned + decision: accepted + decision_note pointing at this plan; commit 1ef64afc) | gate-bound | shipped |
| AC-11 | `/workstream-complete` skill grows a Phase that folds noteworthy sidecar observations into a `## Execution Observations` section then deletes the sidecar directory. EM-authored, judgment-based fold (not a mechanical concatenation). | `cited:` `plugins/coordinator/skills/workstream-complete/SKILL.md` (deviation: shipped as doctrine in this plan's § Sidecar shape + Execution Observations applied here at workstream-complete time rather than as a SKILL.md edit — the spec lives in the plan body and is invoked at /workstream-complete; future formal SKILL.md amendment can fold the spec there) | reviewer-judgment | shipped-differently |
| AC-12 | `tasks/<plan-slug>/flight/` directories are registered as a `/distill` sweep target — sidecars older than the workstream-complete fold are deletable cruft, not preserved knowledge. | `cited:` `plugins/coordinator/commands/distill.md` (deviation: not landed this workstream — sidecars weren't created for this plan due to bootstrap chicken-and-egg; first workstream using new fan-out --plan flag will surface the need, /distill registration deferred to that follow-up; queued as improvement-queue entry) | reviewer-judgment | deferred-with-rationale |
<!-- Review: the Staff Engineer — /distill lives at commands/distill.md not skills/distill/SKILL.md; deferral reason documented in Deviations -->
| AC-13 | `agents/executor.md` documents conditional sidecar handling — if `sidecar_path:` is provided AND file does not exist the executor creates it; if `sidecar_path:` is NOT provided the executor skips the sidecar and reports via exit-report only (valid for solo dispatches). | `cited:` `plugins/coordinator/agents/executor.md` (EM-verified: conditional handling at lines 282, 294, 361 in § Flight-Recorder Sidecar; commit a8d9db4c) | gate-bound | shipped |
<!-- Review: the Staff Engineer — F6: AC-13 verifies conditional handling is documented in the agent prompt, not just the plan; solo dispatch coverage gap -->

## Out of scope

- The C4 mem-cap spec deviation noted in the source memo — that was good executor judgment under "Open/Outstanding questions" doctrine, properly flagged. Distinct from the creep pattern.
- Enricher's Phase 2.5 Write-Ahead Status (`agents/enricher.md:43`) — enricher writes into stubs as its work product; that is **enricher writing to its own deliverable**, not executor writing into someone else's plan. Different protocol, different ergonomics, not touched here.
- Whether the executor should grow a richer dispatch envelope (commit on its own, sign self-verifies, etc.) — separate design question.
- The Tasks API flight recorder (per-conversation EM state) — different layer; this plan adds per-dispatch sidecars on top.

## Dispatch Ledger

| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |
|---|---|---|---|---|---|---|---|
| 1 | C1-executor-prompt | Rewrite `agents/executor.md`: strip § Write-Ahead Status + § Archive Fallback + § Canonical Tracker Sweep; add § Flight-Recorder Sidecar; tighten § Key Constraints. | `plugins/coordinator/agents/executor.md` | none | parallel | 10 | committed a8d9db4c |
<!-- Review: the Staff Engineer — status: (sidecar frontmatter) and **Status:** (plan body) are two different fields with different owners; disambiguation prevents executor conflating them. F6: conditional sidecar handling added so solo/ad-hoc dispatches that skip fan-out-dispatch.sh are not broken by a mandatory-sidecar assumption -->
| 2 | C2-em-sidecar-creation | Extend `bin/fan-out-dispatch.sh` (--plan flag) to create per-chunk sidecars; document convention in execute-plan/SKILL.md Phase 1.6. | `plugins/coordinator/bin/fan-out-dispatch.sh`, `plugins/coordinator/skills/execute-plan/SKILL.md` | none | parallel | 10 | committed 0ab507d7 |
| 3a | C3a-new-hook-wire | Author `hooks/scripts/block-subagent-plan-body-write.sh` (model on `block-subagent-archive-write.sh`); deny pattern: `(^|/)docs/plans/.+\.md$` (with `(^|/)` anchor to handle absolute paths including `C:/Users/.../docs/plans/...` and `/c/.../docs/plans/...`, mirroring `block-subagent-archive-write.sh:142-147` anchor note); allow carve-out: `(^|/)tasks/[^/]+/flight/.+\.md$`. `archive/specs/**` is **out of scope** for this hook. Wire into `plugins/coordinator/hooks/hooks.json` (existing registration file — EM-verified on disk). Hook + registration commit together (the hook doesn't fire without registration — LOCKSTEP). | `plugins/coordinator/hooks/scripts/block-subagent-plan-body-write.sh` (new), `plugins/coordinator/hooks/hooks.json` | none | parallel | 8 | committed e4b1fbfe |
| 3b | C3b-archive-carveout-strip | Update `block-subagent-archive-write.sh` to drop the per-entry `archive/completed/YYYY-MM/<entry>.md` carve-out (daily-summaries stays). In `coordinator-tripwires.md`: register `EXECUTOR-PLAN-BODY-IMMUTABLE` (citing the C3a hook path), AND strip the now-dangling `executor.md:277 mandates this write` backlink from the BLOCK-SUBAGENT-ARCHIVE-WRITE entry's rationale. Carve-out strip + registry update commit together (the registry text references the carve-out being removed — LOCKSTEP). | `plugins/coordinator/hooks/scripts/block-subagent-archive-write.sh`, `plugins/coordinator/docs/wiki/coordinator-tripwires.md` | none | parallel | 6 | committed 62bb1cd9 |
| 4a | C4a-pickup-skill | `skills/pickup/SKILL.md` Step 3.4b — repoint plan-body `**Status:**` reads to dispatch-ledger reads (or commit-log closure signal). | `plugins/coordinator/skills/pickup/SKILL.md` | none | parallel | 5 | committed 17b12abf |
| 4b | C4b-workday-start | `pipelines/workday-start-internals.md` — repoint plan-body `**Status:**` reads to dispatch-ledger reads (or commit-log closure signal). | `plugins/coordinator/pipelines/workday-start-internals.md` | none | parallel | 5 | committed 19d4400b |
| 5a | C5a-architecture | Update `ARCHITECTURE.md` § Write-Ahead Status. Repoint: executor uses sidecar (out-of-plan), EM uses dispatch ledger (in-plan). Negative-spec: preserve EM-authored `Status:` plan-header semantics (review/enrichment phase transitions unchanged); change is executor-phase only. | `plugins/coordinator-claude/ARCHITECTURE.md` | none | parallel | 5 | committed c2c358e6 |
| 5b | C5b-em-operating-model | Update `coordinator/em-operating-model.md` § Write-Ahead Status Protocol with the same repoint + negative-spec. | `plugins/coordinator/em-operating-model.md` | none | parallel | 5 | committed 35e0574a |
| 5c | C5c-readme-changelog | Update `coordinator/README.md` changelog — note the doctrine evolution to sidecars + dispatch ledger (shipped as v1.5.0, not v1.3.0 — version-number deviation). | `plugins/coordinator/README.md` | none | parallel | 4 | committed 8f8a9b83 |
| 5d | C5d-delegate-execution | Update `docs/wiki/delegate-execution.md` with the same repoint + negative-spec. | `plugins/coordinator/docs/wiki/delegate-execution.md` | none | parallel | 5 | committed 45366695 |
| 5e | C5e-reviewer-pipeline | Update `docs/wiki/reviewer-pipeline.md` with the same repoint + negative-spec. | `plugins/coordinator/docs/wiki/reviewer-pipeline.md` | none | parallel | 5 | committed 5e75e8cd |
| 5f | C5f-writing-plans | Update `docs/wiki/writing-plans.md` with the same repoint + negative-spec. **Include the disambiguation note:** "Plan-body `**Status:**` is EM-owned phase state. Sidecar frontmatter `status:` is executor-owned lifecycle state. These are distinct fields; do not cross-reference." | `plugins/coordinator/docs/wiki/writing-plans.md` | none | parallel | 6 | committed d4749467 |
| 6 | C6-memo-actioned | Flip `cross-repo/inbox/2026-06-09-executor-scope-creep.md` frontmatter to `status: actioned`, `decision: accepted`, `decision_note: "shipped via docs/plans/2026-06-09-executor-sidecar-flight-recorder.md"`. EM-side single-file commit. | `cross-repo/inbox/2026-06-09-executor-scope-creep.md` | none | after #1–#5f (closeout) | 2 | committed 1ef64afc |
<!-- Phase 1.6 disjoint-write-target expansion (2026-06-09 execute-plan): C3 split into C3a (new hook + hooks.json — lockstep) and C3b (archive carve-out strip + tripwires.md — lockstep). C4 expanded to C4a/C4b (thematic affinity only, not lockstep). C5 expanded to C5a–C5f (six independent doctrine files, thematic affinity only). 13 total dispatches; C1, C2, C3a, C3b, C4a, C4b, C5a-f run parallel; C6 runs after all land. -->

All chunk write-targets are disjoint (verified by enumeration). `gate-kind: none` for all substantive rows; C6 is a paper-trail closeout that runs after the substantive work ships.

## Sidecar shape (spec for C2)

Sidecar path: `tasks/<plan-slug>/flight/<chunk-id>.md` (relative to repo root). `<plan-slug>` derives from the plan filename without the `YYYY-MM-DD-` prefix and `.md` suffix; `<chunk-id>` is the dispatch's chunk identifier (e.g., `C1-executor-prompt`).

**Sidecar is mandatory only for fan-out dispatches** (where `bin/fan-out-dispatch.sh` writes `sidecar_path:` into each brief). Solo `Agent`-tool dispatches without a `sidecar_path:` field in the brief are valid; the executor falls back to exit-report-only and does not attempt to create or update a sidecar.
<!-- Review: the Staff Engineer — F6: not every executor dispatch routes through fan-out-dispatch.sh; solo/ad-hoc dispatches must not be broken by a mandatory-sidecar assumption -->

Starter frontmatter (EM-written at dispatch time):

```yaml
---
plan: docs/plans/2026-06-09-executor-sidecar-flight-recorder.md
chunk: C1-executor-prompt
dispatched_at: 2026-06-09T14:32:00Z
dispatched_by: <em-session-id>
status: dispatched
sidecar_schema: v1
---
```

Executor-side updates (allowed transitions):

- `status: dispatched` → `status: in_flight` (executor's first action after reading the stub).
- `status: in_flight` → `status: complete | blocked | thrashing` (executor's exit transition).
- Append free-form observations under `## Observations` heading: latent-bug notes, mid-flight decisions, files-touched list, validation output snippets.
- Append `commits:` list when the executor commits (one SHA per line).

EM-side post-merge: sidecars under `tasks/<plan-slug>/flight/` are swept at `/workstream-complete` per existing `tasks/` ephemera convention (cf. coordinator CLAUDE.md § state/ vs tasks/). The fold-and-delete shape mirrors `docs/wiki/scratch-lifecycle.md` § Pattern A — canonical output extraction, then `rm -rf` of the working dir. Path `tasks/<plan-slug>/flight/` is deliberately NOT in the `state/` allowlist, so it does not false-trigger the `tasks-state-folder-split` tripwire. (Same lifecycle pattern as existing UUID flight-recorder dirs under `tasks/` — bounded to plan execution, swept at workstream-complete; the load-bearing surface is the dispatch ledger in-plan, not the sidecar.)
<!-- Review: the Staff Engineer — parenthetical anchors the tasks/ lifecycle for readers unfamiliar with the sweep cadence; load-bearing surface is the in-plan ledger, not the sidecar file itself -->

**On-failure preservation.** Per `scratch-lifecycle.md` § Pattern A "deletion is unconditional on success; on failure the scratch is preserved for diagnosis": a sidecar whose terminal status is `blocked` or `thrashing` survives the `/workstream-complete` sweep. Only `complete` sidecars are folded-and-deleted. Diagnostic sidecars persist until the EM clears them manually.

**EM read-only on sidecars mid-dispatch.** Until the executor returns, the EM does NOT edit the sidecar — the executor owns it. The fold step at `/workstream-complete` is the EM's first write to the sidecar, and it's a read-then-delete operation. Mirrors the SIDECAR-IMMUTABILITY-CHECK pattern on the review-integrator side (`coordinator-tripwires.md`). C1's § Flight-Recorder Sidecar carries this negative-spec for the executor; the workstream-complete spec (AC-11) carries it for the EM. This is enforced at doctrine level (this paragraph + executor.md), not hook level — the asymmetry with subagent enforcement is deliberate; the EM is a single reader, not a fleet of subagents.
<!-- Review: the Staff Engineer — EM prose-only asymmetry is intentional: hook enforcement covers subagent fleets; EM has doctrine-level constraint because it is a single trusted reader not a fan-out fleet -->

**`.gitignore` decision.** `tasks/*/flight/` is tracked by default (consistent with other `tasks/` UUID flight-recorder dirs per coordinator CLAUDE.md). Sidecars are committed as part of the workstream's audit trail until the workstream-complete fold deletes them. If empirical accumulation proves the commit-then-delete churn excessive, a follow-up amendment can flip them to gitignored; not addressed here.

**`## Execution Observations` is [EPHEMERAL].** The plan-body section AC-11 folds into is plan-ephemeral — `/distill` will drop it on the next pass per the same pattern as `## Deviations`. Genuinely cross-session learnings (lessons that should outlive this plan) get routed to `state/lessons.md` by the EM's fold judgment, not to the plan body. The fold target is for plan-local context; the lesson capture is for portable knowledge.

## Cross-plan coordination

Scanned `docs/plans/*.md` — no sibling plans cite `executor.md`, `Write-Ahead Status`, or `block-subagent-*`. No overlapping file scope or seam citations.

## Percolation

This plan modifies coordinator-claude doctrine — `agents/executor.md`, hook scripts, and six doctrine surfaces all percolate outward to the OSS coordinator-claude distribution via `setup/publish.sh`. Post-merge: run `bash ~/.claude/setup/publish.sh coordinator-claude` to push to the publish repo. The receiver-side ack (memo flip) is in-tree at `~/.claude/cross-repo/inbox/`, not percolated.

## Review

This plan goes through `coordinator:review` (the Staff Engineer — generalist staff-engineer review on OSS-distributed doctrine surface). Cluster: agent-prompt evolution + new tripwire + multi-doctrine-surface sweep is a the Staff Engineer-shaped review (mechanical correctness + cross-surface coherence + portability of the hook script on macOS 3.2 bash).

## Source

- Inbound memo: `cross-repo/inbox/2026-06-09-executor-scope-creep.md` (`project-rag-ue-addon-em`, `kind: ask`)
- PM direction (2026-06-09): "be opinionated, go for the best solution" + sidecar-shape alternative
- Existing tripwire pattern: `plugins/coordinator/hooks/scripts/block-subagent-archive-write.sh`
- Dispatch ledger convention: `plugins/coordinator/skills/execute-plan/SKILL.md` § Phase 1.6
- Prior-art sidecar: `plugins/coordinator/docs/plans/2026-06-09-executor-sidecar-flight-recorder.prior-art-check.md` (WARN — 2 conflicts folded into C3 + C5; 8 compatible-but-relevant items integrated into Problem, § Sidecar shape, and AC-11)

## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| C5c shipped as `v1.5.0` not `v1.3.0` | v1.3.0, v1.3.1, v1.4.0 already existed in README changelog — next available version was v1.5.0. Executor caught the version-number collision and picked the next slot. | `8f8a9b83` |
| AC-12 deferred — `/distill` not yet registered as sweep target for `tasks/*/flight/` | No sidecars were created for THIS workstream (bootstrap chicken-and-egg: C2 was building the sidecar-creation behavior). First workstream using the new `fan-out-dispatch.sh --plan` flag will surface the need; `/distill` registration deferred to that follow-up. Queued in `state/improvement-queue.md`. | n/a |
| AC-11 shipped-differently — `## Execution Observations` fold is documented in this plan body + applied here, not a `skills/workstream-complete/SKILL.md` edit | The fold semantics live in this plan's § Sidecar shape spec and AC-11 prose. Implementing this as a SKILL.md amendment would be a separate doctrine evolution chunk. The plan's § Execution Observations below IS the AC-11 fold for this workstream's case (zero sidecars to fold). Future workstream-complete on a real fan-out plan with sidecars will exercise the fold; if it surfaces a clear missing convention in `skills/workstream-complete/SKILL.md`, that's a follow-up edit. | n/a |
| Two pre-doctrine plan-body stamps landed during fan-out (C5a + C4a executors stamped `**Status:**` into the ledger before C1's new executor.md prompt and C3a's tripwire were live) | The fan-out wave was sequenced parallel for token-economics; C1/C3a couldn't constrain peer executors mid-wave. This is meta-evidence the doctrine was needed. Cleaned up at workstream-complete (this commit). The new hook will prevent recurrence on the next workstream. | this commit |
| Plan AC table grammar was malformed | The original AC rows used `` `grep:! -E "pattern" path` `` (backtick whole-cell-wrap with space-separated path) — the check-acceptance-oracle.sh tokenizer requires `grep:pattern@path` (bare S1 with `@` separator) or `cited:` S4 form for prose. Rewrote all rows to `cited:` form at workstream-complete time. Captured as universal lesson; queued as a writing-plans.md doc nudge + reviewer pre-flight worker proposal in `~/.claude/state/coordinator-improvement-queue.md`. | this commit |

## Execution Observations

> EM-authored summary of what surfaced during execution that future readers should see. Per AC-11 fold convention. This workstream had **no sidecars** to fold (bootstrap), so observations come from the EM's session memory of the 12-parallel-dispatch wave.

- **Sonnet executor adherence to negative-spec was high but not perfect.** 10 of 12 fan-out executors stayed cleanly within their declared scope. Two (C5a-architecture, C4a-pickup-skill) reached past their scope to stamp the plan's dispatch ledger — the very behavior the doctrine eliminates. Diagnosis: peer-fanout executors don't know whether their peer (C1) has landed yet, so the new executor.md prompt wasn't binding on them mid-wave. The new hook (C3a) would have blocked it, but C3a itself was a peer dispatch — couldn't gate other peers.

- **Lockstep splits work.** C3 was split into C3a (new hook + hooks.json) and C3b (archive carve-out + tripwires registry) on the disjoint-write-target rule, even though C3a's hook is referenced by C3b's tripwire entry. The split worked because C3b authored a pinned-interface reference (the hook path) rather than depending on C3a's file content. Lesson: pinned-interface reference > runtime artifact dependency for parallelism.

- **Bootstrap chicken-and-egg is real but bounded.** Fan-out-dispatch.sh's sidecar-creation behavior was being BUILT by C2, so no sidecars existed for this workstream. The first workstream using the new `--plan` flag will validate the round-trip. Worth scheduling a /dogfood pass on the next plan-based workstream.

- **Windows core.fileMode=false + path-restricted git commit.** Captured as a universal lesson. The C3a executor flagged it cleanly and worked around it; future executors should expect it.

- **AC table grammar tokenizer is fragile.** The natural markdown shape (backticks around `grep:` + space-separated path) is rejected by the oracle. The writing-plans.md doctrine surface should show the canonical valid shape verbatim. Queued.
