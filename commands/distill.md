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
`${CLAUDE_PLUGIN_ROOT}/pipelines/artifact-distillation/PIPELINE.md` — read there, don't
re-derive. Delete-safety guard schemas live below in this file — the guards gate an irreversible
`git rm`. Rationale and worked evidence behind those calls: the plugin's `distill-residue` wiki
page.

**Out-of-scope actions for all dispatched agents in this pipeline:** DO NOT run `gh pr create`,
`gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates
GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find
yourself reaching for a merge, STOP and surface the question to the EM in your final reply. The
EM merges via `/merge-to-main`; distill agents do not.

**Announce at start:** "I'm running `/distill` to extract knowledge from [N artifacts / artifacts
in path] into wiki documents."

---

## Fates

| Artifact | Fate |
|---|---|
| Canonical plan/spec, **RIPE only** | Harvest → wiki/DR, log in `state/distillation-log.md` |
| Enriched stubs, reviewer outputs, integrator triage, docs-checker reports | Delete — recoverable via git |
| Wiki entries | Write/update, provenance frontmatter |
| Archived handoffs | Extract → delete once eligibility guards pass |
| Batons | Exhaust, never harvest — see § Baton fate below |

---

## Baton fate

Batons are a plan's exhaust, never a harvest source — plans are what get wikified. A birth baton
(unpromoted `.git/coordinator-sessions/<sid>/baton.json`) is deleted on a distillation run. A
written baton (continuation, execution, spinoff) survives as cross-reference, keyed on
`deliverable_id`, for an agent working its joined plan — read for how hard delivery actually was
and which items resisted re-derivation — and is deleted with that plan's handoff archive once
the plan is wiki-ified or pruned. No baton carries a fate field and no EM decides one. Deletion
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

**A handoff is eligible for delete in Phase 5 ONLY if all four guards pass:**
1. **Extraction-artifact present.** A DR or wiki entry cites it via `archived_handoff:`
   provenance, OR it is empirically content-free. A `~/.claude` memory pointer does NOT satisfy
   this — durable capture is in-repo only (`docs/decisions/`, `docs/wiki/`,
   `state/cross-repo-commitments/`, a canonical plan/spec).
2. **`shipped_in:` present.** Missing → surface to PM, do not delete.
3. **Active-reference check.** No live citation across `docs/`, `tasks/`, `archive/specs/`,
   plugin sources (provenance-marker tombstones excluded).
4. **Distillation-log row.** ≥8-word domain-prose reason (Phase 5c).

**A cross-repo archive memo is eligible for delete ONLY if all five guards pass** (same 1-4 above,
retargeted to `cross_repo_memo:` provenance and `status: actioned`, plus):
5. **Commitment-closure gate.** Blocked while a linked `state/cross-repo-commitments` entry is
   `status: open` (our record only), OR the memo's disposition is `accepted`/`partial` with an
   absent/unverifiable `realized_by`. Blocked ⇒ surface to PM, retain — never silently skip.

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

## Relationship to Other Commands

| Command | When to use |
|---------|-------------|
| `/distill` | Extract knowledge into wiki docs, trim + archive canonical specs, delete scaffolding |
| `/update-docs` Phase 8b | Bulk prune without knowledge extraction, unconditional age-thresholded cleanup |

**Prior-art-checker** consults `docs/wiki/codebase-judgment/` (Phase 2.5 output) on every plan
check — cached Opus-tier judgment at Sonnet cost, zero additional wiring.
