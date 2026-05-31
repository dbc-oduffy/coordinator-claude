# Phase 2.5 — Judgment Mining (full procedure)

> Referenced by `PIPELINE.md` § Phase 2.5. Spec backlinks: `docs/plans/2026-05-07-codebase-judgment-mining.md` § D1, D2, D5–D8.

**Model:** Sonnet. **Dispatch:** one agent per topic-cluster, all simultaneously. Coordinator owns fan-out; no nested sub-agents.

**Strict-sequencing gate:** All Phase 2 topic-cluster agents MUST complete and their scratch files verified before Phase 2.5 begins. Phase 2.5 MUST complete before Phase 3a dispatches.

## Input corpus

Per plan in the run's scope, the coordinator collects:

- **Live sidecars** — `<plan>.{patrik,sid,camelia,palí,fru}-rN.md` files on disk at Phase 2.5 start. Pre-annotated with `disposition:` fields by the review-integrator (D7) before Phase 5 deletes them.
- **Historical sidecars via `git show`** — when an existing `docs/wiki/codebase-judgment/<topic>.md` entry lists `source_findings[*].sha`, those SHAs resolve via `git show <sha>:<sidecar-path>`. Used ONLY during initial topic-cluster creation, not during the update path (D8).

**SHA-resolution + Phase 5 timing:** sidecars are deleted by Phase 5; the `source_findings[*].sha` field captures the sidecar's git SHA so `git show` resolves after deletion. The strict-sequencing gate above ensures Phase 2.5 runs before the same run's Phase 5.

## Finding eligibility

Only architectural reviewer findings count for convergence. **Ineligible:**

- Mechanical (newline, indent, formatting)
- docs-checker-class (wrong import, stale signature, incorrect function name)
- `disposition: escalated-disagree` — actively rejected by integrator; including would let rejected verdicts accumulate

**Eligible:** architectural recommendations, pattern requirements, anti-pattern prohibitions, recurring design constraints.

## Shape-matching

Two findings shape-match iff:

1. **Claim-topic equivalence (semantic, not lexical)** — same codebase concept (e.g. "scoped staging" ≡ "git add scoping").
2. **Verdict-direction polarity matches** — both `forbid` / `require` / `prefer` / `avoid`.

Worked examples in `agent-prompts.md` Phase 2.5 template.

## Update path (existing entries)

When `docs/wiki/codebase-judgment/<topic>.md` exists:

- A single new live finding that shape-matches the topic key increments `convergence_count` by 1 and appends to `source_findings`.
- Do NOT re-`git show` prior SHAs for re-shape-matching — the existing topic key is the join. Re-mining is wasteful and creates churn risk if heuristics evolve.
- The update path fires on a single matching finding (threshold already met at prior promotion).

## Convergence threshold

`MIN_CONVERGENCE` defaults to 3. Override via `/distill --min-convergence=N`. Phase 2.5 emits a proposal only when:

- **New topic:** finding cluster reaches `convergence_count >= MIN_CONVERGENCE` across distinct plans (one finding per plan max).
- **Existing topic:** any single new shape-matching finding triggers an update.

## Output

**Path:** `tasks/scratch/artifact-distillation/{run-id}/judgment-proposals.md` (all agents append; coordinator merges).

**Format per proposal:**

```markdown
## Proposal: <topic-slug>

**Topic:** <claim-topic noun>
**Verdict direction:** forbid | require | prefer | avoid
**Convergence count:** N
**Action:** new-entry | increment-existing

### Source findings

| Sidecar | Plan | Reviewer | Finding ID | SHA |
|---------|------|----------|------------|-----|

### Proposed wiki content

<!-- Full proposed `docs/wiki/codebase-judgment/<topic-slug>.md` body for new entries,
     or a one-line increment note for existing entries. -->

---
```

## Frontmatter schema for promoted entries

Each new `docs/wiki/codebase-judgment/<topic>.md` carries (D5):

```yaml
---
judgment_provenance:
  kind: codebase-judgment
  convergence_count: N
  source_findings:
    - sidecar: <path>
      plan: <plan-path>
      reviewer: patrik | sid | camelia | palí | fru
      finding_id: <id-or-line-ref>
      sha: <git-sha-of-sidecar>
  promoted: <YYYY-MM-DD>
  last_refreshed: <YYYY-MM-DD>
---
```

**Key is `judgment_provenance:`** — NOT `provenance:` (that key is taken by Phase 5b's archived-spec schema with an incompatible list-of-objects shape).

## Dispatch

Open `agent-prompts.md`. Copy the **Phase 2.5: Judgment Mining Prompt** verbatim. Fill: `[TOPIC_CLUSTER]`, `[VERDICT_DIRECTION]`, `[LIVE_SIDECAR_PATHS]`, `[EXISTING_JUDGMENT_ENTRY]` (full path + content if present, else `"NONE"`), `[MIN_CONVERGENCE]`, `[RUN_ID]`, `[SCRATCH_PATH]`. Each agent uses Read, Write, Glob, Bash (for `git show` SHA resolution). Dispatch with `run_in_background: true`.

**Scratch verification:** Before Phase 3a/3b/3d, verify the proposals file exists. Zero proposals → create an empty file with `## No proposals — corpus below threshold` so downstream phases have a known-good input.
