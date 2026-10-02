Part of [`PIPELINE.md`](PIPELINE.md); phases still run in its strict sequence.

## Cross-Repo Archive Specialist Branch (Sonnet, parallel to Phase 1/1.5)

**Model:** Sonnet. **Dispatch:** Single agent (or sharded by chronological window on large
cohorts — see prompt template). **Runs:** parallel to Phase 1/1.5, on a disjoint input
cohort (`cross-repo/archive/*.md`, closed `status: actioned` memos only — excluded from
the generic Phase 0 candidate list, per § Phase 0 step 1 above).

**Why a dedicated branch, not the generic Haiku nugget-scanner + topic-Sonnet path:**
Cross-repo memos carry commitment-closure state (does a linked sibling-repo promise
remain open?) and occasional boundary-ratification content (rare cross-team
architecture decisions) that a fragment-level Haiku nugget pass is poorly suited to
judge — both require reading the memo whole, not as extracted nuggets, for any memo
the EM hasn't already labeled at action time (see the specialist prompt's frontmatter
fast-path for `distill_fate:`-stamped memos, which skip the full-body read). Routing
this cohort through the generic path risks silently deleting a memo whose sibling
commitment is still open, or reducing a genuine boundary-ratification decision to an
`[EPHEMERAL]` nugget. AC6.

**[engine-reliant] `memo.triage` pre-filter (run BEFORE the Sonnet specialist dispatch).**
Per the C8 contract (`docs/contracts/distill-engine-scripts.md` § 1), dispatch the engine repo's
`memo.triage` COMPUTE_ONLY op (`coordinator_core/ops/memo_triage.py`, registered as
`memo.triage`) over the `cross-repo/archive/*.md` cohort before this branch's Sonnet agent
runs. The op returns `{promote: [...], disqualified: [...], candidates: [...], counts: {...}}`
— a deterministic pre-filter, not a final promotion decision. **Judgment stays here, not in
the op:** the Sonnet specialist's commitment-closure + boundary-ratification lens still runs
over the op's `promote` set (the small candidate list), replacing the pre-rebuild behavior of
feeding the ENTIRE memo corpus to Sonnet for classification — this is the dominant cost this
rebuild eliminates (findings #1–#5, #8: the 2026-07-12 dogfood run fed all 257 memos to
Sonnet). Entries in `disqualified` are excluded from the specialist's input cohort entirely
(already-captured or scored below the pre-filter threshold) unless the coordinator has reason
to override for a specific memo. **Observability (#9):** read `counts.promote` /
`counts.total` from the op's output — warn if the ratio exceeds 20% (a wide-net promote set
defeats the point of the pre-filter; the op itself only emits the counts, the caller computes
and warns from the ratio). **Fail-loud on malformed op output:** if the op's stdout is
missing any of `promote`/`disqualified`/`counts.promote`/`counts.total`, treat as
op-unavailable and fall back to the agentic path — do not attempt the ratio computation
against a malformed response. **Agentic-path fallback if the engine repo declines / the op is
unavailable:** revert to feeding the full `cross-repo/archive/*.md` cohort directly to the
Sonnet specialist below with no pre-filter — degraded (the full per-memo LLM cost findings
#1–#5/#8 diagnose), not broken.

**Lens:** commitment-closure + boundary-ratification. Full procedure, dispatch prompt,
output schema, sharding rule, and out-of-scope list:
`agent-prompts/cross-repo-archive-specialist.md`.

**Inherits** the pipeline-wide "Out-of-scope actions for all dispatched agents" block
(`commands/distill.md` § top-of-file) — no destructive `gh`/git actions. The specialist
prompt adds branch-specific out-of-scope items (no direct wiki/DR writes, no memo
deletion, no commitment-ledger mutation, no `cross-repo/inbox/` reads) on top of that
inherited floor.

**Native op backing the read-scope partition:** the mechanical split between the
unlabeled-residue partition (what this branch's Sonnet specialists should read) and the
labeled partition (mechanical log-append eligible) is computed by the engine repo's `memo.fate_partition`
op (`coordinator_core/ops/memo_fate_partition.py`, `@register_op("memo.fate_partition")`) —
partitions on `distill_fate:`/`in_repo_capture:` plus a capture-target existence check. Cite
this op name when describing why the specialist reads only one partition.

**Convergence with the main pipeline:** the specialist's `cross_repo_dispositions:`
scratch output is consumed by Phase 3d (deletion manifest — `ROUTINE` entries become
synthetic `deletions:` rows; `COMMITMENT_OPEN` entries are excluded) and, for any
`BOUNDARY_RATIFICATION` draft, by Phase 3c/Phase 5 apply-agents the same way a Phase 2
new-guide/DR output is consumed. No Phase 2.5/2.7-QG/3a participation — this branch
does not produce nuggets or dispositions in the Phase 2 shape, so the contradiction-
detection and coverage-gate machinery built for that shape does not apply to it.

**Scratch verification:** Verify the specialist's scratch file(s) exist before Phase 3c/3d
proceed to consume `cross_repo_dispositions:` output.

**Drop protection is two-layered:** the specialist's own mandatory self set-diff
(assigned memos vs. `cross_repo_dispositions:` keys, `assigned_count` echoed in
frontmatter — see `agent-prompts/cross-repo-archive-specialist.md` § Output schema) is
the first line; the coordinator's dispatched-vs-classified set-diff at consumption time
remains the backstop, not the sole guard.

---

## Baton Fate — routing note

Batons (`.git/coordinator-sessions/<sid>/baton.json` and written continuation/execution/spinoff
batons) are never a Phase 0-8 harvest input — plans are what get wikified, batons are a plan's
exhaust. A birth (unpromoted) baton is deleted on a distillation run without entering any scan
batch. A written baton survives as cross-reference for an agent working its joined plan (joined
on `deliverable_id`) and is deleted with that plan once the plan is wiki-ified or
pruned — keyed on the plan's own Phase 5 disposition, never on the handoff archive (which this
pipeline no longer disposes of at all). No baton
carries a fate field; no phase in this pipeline decides one. The deletion mechanism itself is
engine-plane and pending, requested at
`state/memo-outbox/2026-08-21-baton-fate-and-lineage-ruling.md` (C7) — this pipeline states the
fate as present-tense truth regardless of that ask's outcome. Rationale: `distill-residue` wiki
page.

---

## Phase 1 Scout Output Schema

Phase 1 Haiku agents must emit a fenced YAML block for each classification group (EPHEMERAL clusters, ALREADY_CAPTURED clusters) — specifically, the first fenced YAML block occurring after the H2 heading and before the next H2 heading (or EOF). Phase 5 reads this YAML block when expanding `deletion_groups:` entries — the YAML block is authoritative; the surrounding Markdown prose is human-readable documentation only.

**H2 heading format:** The heading text must exactly match the `section_anchor:` value declared in the corresponding `deletion_groups:` entry in the Phase 3d manifest. Example:

```
## EPHEMERAL — reviewer outputs (state/review-trail/2026-05)
```

**Fenced YAML block (mandatory, immediately under the H2 heading):**

```yaml
artifact_paths:
  - state/review-trail/2026-05/2026-05-01-foo.md
  - state/review-trail/2026-05/2026-05-02-bar.md
description: "Reviewer outputs from 2026-05 sprint — already integrated, no lasting knowledge."
```

**Schema:**
- `artifact_paths:` — required. Ordered list of file paths (relative to repo root) belonging to this group. Phase 5 iterates this list to build synthetic `deletions:` rows. The `count:` field in the `deletion_groups:` entry must equal `len(artifact_paths)` — mismatch causes Phase 5 to abort.
- `description:` — optional. Human-readable summary of the group for PM review and distillation log. Not consumed programmatically.

**Invariant (AC16):** Every group section in a Phase 1 scout output that is cited by a `deletion_groups:` entry MUST have this fenced YAML block. Missing YAML block → Phase 5 `deletion_groups:` expansion aborts for that group with a named error.
