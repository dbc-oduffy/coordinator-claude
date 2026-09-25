---
name: distill
description: "Distill session artifacts to wiki and decisions; archive specs, drop scratch."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--dry-run] [--no-delete] [--min-convergence=N] [path]"
---

# Distill — Artifact Distillation Pipeline

Extracts knowledge from accumulated session artifacts into wiki/DR entries, trims and archives
canonical specs, deletes scaffolding. Not a disposal route for EM-authored scratch — that's
`bin/cruft-sweep`, `/cruft-sweep`, or `/workstream-complete`'s own `scratch-disposition-per-file`.

Phase mechanics, the Workflow dispatch contract, every gate's evaluation logic, the
PM-gate/dispatch-scope/`state/`-sweep boundaries, and the full Acceptance Criteria all live in
`${CLAUDE_PLUGIN_ROOT}/pipelines/artifact-distillation/PIPELINE.md` — read there, don't re-derive
it. Delete-safety guard schemas live below in this file — the guards gate an irreversible
`git rm`. Rationale and worked evidence behind those calls: the plugin's `distill-residue` wiki
page.

## Execution vehicle

The background **Workflow** is the vehicle unconditionally — scan-wave-journaled → cluster →
one-file-owner synth wave, resumable across rate-limits and compaction. There is no size gate:
a one-artifact run and a 500-artifact run both fire the same Workflow script; the former tiered
split (small-batch single-Sonnet vs. large-batch Workflow-fanout) is retired, not reduced to a
higher threshold. Manual serial `Agent` dispatch is the fallback only for genuinely non-Workflow
work — a single ad-hoc scout or a hand confirmation outside a plan run, never a substitute for
scope size. See `coordinator/docs/wiki/em-operating-model/workflow-orchestration.md` for the general doctrine this instantiates
and `pipelines/artifact-distillation/PIPELINE.md` for this pipeline's own Workflow phase mechanics.

**PM gate applies to deletions only.** Additive knowledge writes (wiki/DR harvest, distillation-log
rows) go direct, no PM checkpoint. Only the irreversible `git rm` at Phase 5 — governed by the
delete-safety guards below — halts for PM/EM judgment.

**Out-of-scope actions for all dispatched agents in this pipeline:** DO NOT run `gh pr create`,
`gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates
GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find
yourself reaching for a merge, STOP and surface the question to the EM in your final reply. The
EM merges via `/merging-to-main`; distill agents do not.

**Announce at start:** "I'm running `/distill` to extract knowledge from [N artifacts / artifacts
in path] into wiki documents."

---

## Fates

| Artifact | Fate |
|---|---|
| Canonical plan/spec, **RIPE only** | Harvest → wiki/DR, log in `state/distillation-log.md` |
| Enriched stubs, reviewer outputs, integrator triage, docs-checker reports | Delete — recoverable via git |
| Wiki entries | Write/update, provenance frontmatter |
| Archived handoffs | **Not a cohort** — never harvested, never deleted here; bounded outlier scan only (pruning is `/update-docs` Phase 8b) |
| Batons | Exhaust, never harvest — see § Baton fate below |

**Reading a plan's outcome.** For a canonical plan/spec carrying a `## Tasks` spine, fold its
outcome from `plan-completeness status <plan-path>` — rows-resolved, chunks-reported, and the
divergence rollup, straight off disk. Do not reconstruct it from `git log` and handoffs; the
ledger is the read path this harvest step consumes, per
`coordinator/docs/wiki/planning/plan-tasks-mutate-cli.md`. A plan predating the spine, or lacking a
`## Tasks` block at all, falls back to the prior git-log/handoff reconstruction — the ledger
answers nothing there.

---

## Baton fate

Batons are a plan's exhaust, never a harvest source — plans are what get wikified. A birth baton
(unpromoted `.git/coordinator-sessions/<sid>/baton.json`) is deleted on a distillation run. A
written baton (continuation, execution, spinoff) survives as cross-reference, keyed on
`deliverable_id`, for an agent working its joined plan — read for how hard delivery actually was
and which items resisted re-derivation — and is deleted with that plan once the plan is
wiki-ified or pruned — keyed on the plan's own disposition, never on the handoff archive. No
baton carries a fate field and no EM decides one. Deletion
mechanism: engine-plane, requested at
`state/memo-outbox/2026-08-21-baton-fate-and-lineage-ruling.md` (C7); rationale and worked detail:
`distill-residue` wiki page.

---

## Arguments

`$ARGUMENTS`, any combination:

- **`--dry-run`** — Phases 0-3d only; deletion-manifest preview, no writes. Additive wiki/DR
  writes are unaffected on a real run either way.
- **`--no-delete`** — applies wiki writes, skips scaffolding deletion and spec trim.
- **`--allow-drop`** — bypasses the negative-loss halt this run after EM eyeball confirms no
  semantic loss; logged to the distillation log's Manual Review section.
- **`--min-convergence=N`** — overrides the Phase 2.5 convergence threshold (default 3).
- **`[path]`** — scopes the inventory to a subdirectory.

```
/distill                          # full repo distillation
/distill --dry-run                # preview only, no writes
/distill --no-delete              # extract wiki content, keep source files in place
```

---

## Delete safety (mandatory; opt-out is `--no-delete`; gates an irreversible `git rm`)

**Aggressive by default.** These guards are the COMPLETE dispositioning-agent-facing eligibility
list — HARD guards only. A dispositioning agent (Phase 3d) MUST NOT invent additional soft
retain-reasons. Conservatism is opt-in via `--no-delete` (skips disposal entirely for the run),
not the default posture. Rationale and worked evidence: `distill-residue` wiki page.

**Scan success-rate gate — disposal is suppressed on a mass-failed harvest, not just an empty
one.** Before Phase 5 emits a deletion manifest, check Phase 1/2's own per-cohort scan
success-rate (plans/handoffs/memos scanned vs. attempted). A coverage-% floor alone is
necessary-not-sufficient — read terminal status off disk per `cleanup-sweep-hazards.md`
§38/§44, then additionally refuse to build a disposal manifest from a wave where the underlying
scan mass-failed, even if the few artifacts that DID scan look individually delete-eligible: a
throttled run where every plan/handoff/memo scan failed must never still produce a sidecar/memo
deletion manifest built from whatever scraps survived. Below the floor (default: any cohort with
<50% of its Phase 1/2 scan attempts succeeding) ⇒ disposal is suppressed for that cohort this run,
surfaced to the EM as a scan-failure report, not a deletion manifest. This composes with, but does
not substitute for, the Workflow's rate-limit resume (which reduces how often a throttle happens
at all) — this gate is defense-in-depth regardless of whether resume ran.

**Archived handoffs are never delete-eligible here.** Handoffs are not a distillation cohort —
`/distill` neither harvests nor deletes any `archive/handoffs/**` path, and the former four-guard
handoff eligibility list is retired with the cohort. Archived-handoff pruning is owned by
`/update-docs` Phase 8b (`pipelines/update-docs/artifact-pruning.md`).

The four guards below survive as the memo eligibility base:
1. **Extraction-artifact present.** A DR or wiki entry cites it via provenance, OR it is
   empirically content-free. A `~/.claude` memory pointer does NOT satisfy this — durable capture
   is in-repo only (`docs/decisions/`, `docs/wiki/`, `state/cross-repo-commitments/`, a canonical
   plan/spec).
2. **`shipped_in:` present.** Missing → surface to PM, do not delete.
3. **Active-reference check.** No live citation across `docs/`, `tasks/`, `archive/specs/`,
   plugin sources, **or any test tree** (provenance-marker tombstones excluded). Test trees are
   named explicitly because a test reads an artifact as a RUNTIME ORACLE, not as a citation: the
   reference is a path string the test opens, so deleting the artifact does not fail the sweep, it
   fails the suite — at an arbitrary later run, with a `FileNotFoundError` naming a path and
   nothing naming distillation. Repointing cannot recover it; there is no file to point at.
4. **Distillation-log row.** ≥8-word domain-prose reason (Phase 5c).

**A cross-repo archive memo is eligible for delete ONLY if all five guards pass** (same 1-4 above,
retargeted to `cross_repo_memo:` provenance and `status: actioned`, plus):
5. **Commitment-closure gate.** Blocked while a linked `state/cross-repo-commitments` entry is
   `status: open` (our record only), OR the memo's disposition is `accepted`/`partial` with an
   absent/unverifiable `realized_by`. Blocked ⇒ BLOCKED — never silently skip.

These guards gate eligibility *judgment* (dispatch-eligible at Phase 3d) — the resulting deletion
at Phase 5 is EM-only.

**Engine-enforced fate guards (apply-time, both classes, mechanical, class-agnostic — in practice
cross-repo-memo-only since `distill_fate` is a cross-repo-memo field).** Re-run by
`apply_disposal` at delete time, never substituted by a shard's own open/closed judgment:
- **Guard 6 — `check_distill_fate`.** `distill_fate: ratification` refuses deletion unless
  `in_repo_capture` resolves on disk and is non-empty. `ephemeral`/`commitment`/absent pass; an
  unrecognized fate value fails closed.
- **Guard 7 — `check_harvest_provenance`.** `distill_fate: commitment` is blocked from deletion
  unless a `docs/wiki/**` or `docs/decisions/**` file cites it (repo-relative path OR bare
  basename). No-op for every non-commitment fate.

**Negative-spec — mechanical re-evaluation must keep re-running at apply time, never stand in for
shard judgment.** A run that split commitment-loop review across three specialist shards had the
shards' own judgment flag 5 open loops; a separate re-run of `evaluate_candidate_detailed` over
the literal guards found 16 more retains the shards missed. `apply_disposal` MUST keep re-running
this mechanical check on every candidate — a shard's careful-but-meaning-based disposition is not
the same fact as a literal guard pass.

---

## § 5d — Link-heal no-rewrite classes

The broad-sweep path-heal executor (Phase 5d) repoints stale in-repo links after archival moves.
**No-rewrite classes — MUST NEVER be rewritten, regardless of how confidently a path resolves:**

1. **Historical logs** — `state/week-changelog/*`, `wsc/*.json` receipts,
   `review-trail/findings/*`. Each is a point-in-time record of what a prior run actually did;
   rewriting its path references retroactively falsifies that record.
2. **Inbox-path provenance** — a path captured to document where an artifact originated, not a
   live reference to be kept resolving.
3. **Bare `source_memo:` basenames** — the recorded basename is itself the point-in-time citation;
   resolving it to a current path destroys what it was pointing at when written.

**The active-ref scope deliberately stops at `docs/`, `tasks/`, `archive/`** (same boundary as the
delete-safety active-reference check above) — link-heal never walks `state/` to "fix" the
no-rewrite classes above, even when a rewrite would technically resolve. Precedent:
`coordinator/docs/wiki/bug-blitz-residue/cleanup-sweep-hazards.md` #45 — an identical point-in-time-record LEAVE class in a
rename context (dated spec/plan filenames are a point-in-time backlink, not a live identity
reference).

---

## Relationship to Other Commands

| Command | When to use |
|---------|-------------|
| `/distill` | Extract knowledge into wiki docs, trim + archive canonical specs, delete scaffolding |
| `/update-docs` Phase 8b | Bulk prune without knowledge extraction, unconditional age-thresholded cleanup |

**Prior-art-checker** consults `docs/wiki/codebase-judgment/` (Phase 2.5 output) on every plan
check — cached Opus-tier judgment at Sonnet cost, zero additional wiring.

---

## Maintenance Checkpoint

**`git.maintenance` hourly tier.** Fires after PIPELINE.md Phase 5's safety commit, advisory,
non-zero reported, run continues:

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" git.maintenance '{"tier":"hourly","repo":"<repo-root>"}'`

Shape W above / Shape A/B POSIX — `snippets/resolve-coordinator-bin.md`. `--repo` flag refused
(`scope='none'`); `repo` goes in the JSON params, not omitted. The op maps `tier=hourly` to
`--task=commit-graph`, never `--schedule=hourly` — no schedule flag appears at this call site.
