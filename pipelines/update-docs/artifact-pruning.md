---
name: update-docs/artifact-pruning
description: "Bulk-prune accumulated session artifacts (plans/, archive/handoffs/, stale task dirs). Inlined by /update-docs Phase 8b."
version: 1.1.0
---

# Artifact Pruning Pipeline

> **Inlined by `/update-docs` Phase 8b.** Not invoked standalone — `/update-docs` is the only caller. Replaces the former `coordinator:artifact-consolidation` skill.

> **This is age-archival, not knowledge-archival.** Two lifecycles wear the word "archive": **knowledge-archival** (`/distill` — trim a ripe plan to its canonical skeleton and move it to `archive/specs/YYYY-MM/` *after* extracting its knowledge into wiki/DR) and **age-archival** (this pipeline — time-thresholded janitorial pruning of aged, non-knowledge-bearing artifacts; no extraction). This pipeline owns the latter only. Boundary doctrine: `commands/distill.md` § Relationship to Other Commands.

> **Negative-spec — consumed markers:** This pipeline moves and deletes files. It does NOT write `<!-- consumed: YYYY-MM-DD -->` markers — that's `/pickup`'s exclusive responsibility. Active handoffs in `state/handoffs/` are outside this pipeline's scope; chain-aware archival of those is `pipelines/update-docs/handoff-archival.md`'s job (Phase 8), which runs immediately before this pipeline.

## When This Runs

Every `/update-docs` invocation, after Phase 8 (handoff archival) completes. Conservative thresholds make most runs no-ops — the pipeline only deletes when accumulated artifacts cross the threshold lines below. `/update-docs` is itself PM-invoked, and the safety commit (Step 1 below) makes any deletion `git revert`-able as a single operation.

## Scope

| Directory | What accumulates | Pruning rule |
|-----------|-----------------|--------------|
| `docs/plans/` | Session plan files (`*.md`) | Delete plans older than 14 days with no open references, subject to the ripeness-safety guard below. **Ordering hazard (mirror of the `cross-repo/archive/` 90d floor):** this 14d floor age-DELETES plans — it does not knowledge-archive them. If a plan is RIPE-but-unharvested (delivered, but `/distill` has not yet trimmed→archived it to `archive/specs/`), deleting it here loses the wiki/DR promotion (git history survives, but the extraction never runs). The floor MUST exceed the `/distill` cadence; if `/distill` runs less often than every 14d, raise this floor proportionally — same cadence-exceeds-floor anchor as the cross-repo memo row. Knowledge-archival is `/distill`'s job and runs upstream of this deletion. **Ripeness-safety guard:** a plan in `docs/plans/` is ONLY eligible for age-deletion when BOTH conditions hold: (a) its frontmatter `status:` is terminal-abandoned (`superseded`, `abandoned`, or `cancelled`) OR a trimmed copy already exists under `archive/specs/**` (i.e. `/distill` has already knowledge-archived it — see `commands/distill.md` § Relationship to Other Commands); AND (b) it is not referenced by any active handoff, task file, or `MEMORY.md` entry. NEVER age-delete a plan whose `status:` is `implemented`/`shipped` but which has no counterpart under `archive/specs/**` (ripe-unharvested — that extraction is `/distill`'s job, not this pipeline's). NEVER age-delete a plan with `status:` `draft`, `in-progress`, or `reviewed` (in-flight). When `status:` is absent or unrecognised, treat as in-flight (KEEP). |
| `archive/handoffs/` | Consumed handoff files | **Exemption (checked first):** an archived handoff whose frontmatter carries `kind: spinoff-roadmap` is NEVER pruned, regardless of age or rank — see rationale in Step 1 below. Otherwise, keep the 10 most recent by filename timestamp; delete the rest **unless still referenced** — see the referrer guard below. **Month-subfolder transition:** files are migrating from flat `archive/handoffs/*.md` to month-subfolders `archive/handoffs/YYYY-MM/<file>.md` (matching the `archive/specs/YYYY-MM/` convention). Enumerate BOTH `archive/handoffs/*.md` AND `archive/handoffs/*/*.md` to cover files in either layout during the transition. Select the 10 most recent across the combined set; delete the rest individually (not `git rm -r`). **Referrer guard (mirrors the plans row):** a count/age rule alone silently breaks lineage. Plans carry `predecessor_handoff:` and handoffs carry `predecessor:` pointing at handoffs that were correct when written; archival then moves the target and this prune deletes it, leaving a dangling pointer no reader can distinguish from "never existed". Skip deletion when the file's **basename** appears in an ancestry field of any live plan or handoff: `predecessor_handoff:` (plans), or `predecessor:`, `additional_predecessors:`, `forked_from:`, `continued_into:` (handoffs). Basename, not path — `predecessor_handoff:` is conventionally a repo-relative path and the rest are bare basenames, so a path-match catches only some. Separately, `blocked_by:` is a roadmap dependency-graph edge, not ancestry, and is **not** basename-matched — it holds identifier values, never filenames. Do NOT re-derive that resolution here: dispatch the `handoff.blocked_by_dependents` op (Step 1 carries the invocation) and honour its tri-state. Measured: three such sweeps broke 21 of 25 `predecessor_handoff:` links; the rot is monotonic — each sweep breaks more, none are repaired. Measured: the missing `blocked_by:` edge and the missing `spinoff-roadmap` exemption together killed two of three live roadmaps — the referrer guard alone cannot close this because the roadmap audit asserts an equal stub *count*, not just edge-reachability. |
| `tasks/*/` | Feature task directories | Delete dirs where all `todo.md` items are `[x]` AND the feature branch is merged or deleted |
| `state/handoffs/` | Active handoffs | **Out of scope** — `pipelines/update-docs/handoff-archival.md` (Phase 8) handles these |
| `state/subagent-share/<session-id>/*.md` | doc-link-checker (and other `run-report`-typed) sidecars | **Out of scope** — Phase 12's doc-link-checker report now lands in an EM-provisioned sidecar under this tree, not `tasks/`. `state/subagent-share/` is a tracked-deliverable record surface with its own typed, liveness-and-age-floor-gated reaper (`bin/reap-stale-subagent-sidecars.py`, run by `/distill` Phase 5), not a `status:`/count sweep — this pipeline does not touch it. |
| `cross-repo/archive/` | Closed `actioned` memos swept here after the receiver has acted | Delete memos with `status: actioned` older than **90 days** — 90d is chosen as ≥3× the expected `/distill` cadence so this janitorial sweep never deletes un-mined evergreen content before `/distill` has had a chance to run; if the `/distill` cadence lengthens past 30d, raise this floor proportionally. **Ordering hazard:** this 90d floor MUST exceed the max distill-run interval — if update-docs deletes a >90d actioned memo that `/distill` never mined, any evergreen content is lost (git history survives, but the promotion job never ran). The cadence-exceeds-floor anchor is what closes this hazard. |

## Steps

### Step 1: Inventory

<!-- Review: review-integrator/overengineering-reviewer — invocation shape lives once at
     detect-current-state.md § The updatedocs.gates invocation. -->

**Detect first.** `updatedocs.gates` (`detect-current-state.md § The updatedocs.gates invocation`
for the call shape) — `plans-prune-candidates` and
`archive-memo-prune-candidates` emit candidate sets for the `docs/plans/` and `cross-repo/archive/`
rows. Both detect only: neither moves or deletes anything, and every guard in this file still runs
here. Their verdict is three-state — `prunable` / `retained` / `indeterminate` — and a record with
no `status:` key is `indeterminate` regardless of age, never silently retained; `indeterminate`
maps to this pipeline's KEEP, same as the ripeness guard's absent-`status:` rule. A gate reading
`unavailable` is "not checked", never "clean": classify that row by hand below.

1. **Count and classify:**
   - **Plans (`docs/plans/*.md`):**
     - PRUNE if ALL of the following hold: (1) file is older than 14 days; (2) not referenced by any active handoff, task file, or `MEMORY.md` entry (grep the filename across `state/handoffs/`, `tasks/`, and `MEMORY.md`); AND (3) the ripeness-safety guard passes — `status:` is `superseded`/`abandoned`/`cancelled` OR a trimmed copy exists under `archive/specs/**`. Plans with `status:` `implemented`/`shipped` that have no `archive/specs/**` counterpart are ripe-but-unharvested (KEEP; `/distill`'s job). Plans with `status:` `draft`/`in-progress`/`reviewed` or absent/unrecognised are in-flight (KEEP).
     - KEEP otherwise.
   - **Archived handoffs (`archive/handoffs/*.md` and `archive/handoffs/*/*.md`):**
     - Enumerate BOTH globs to cover flat files and month-subfoldered files during the ongoing migration to `archive/handoffs/YYYY-MM/` layout.
     - **KEEP unconditionally if frontmatter `kind` is `roadmap-baton` OR `spinoff-roadmap`** — check this before applying the count/age rule below. Roadmap stubs are graph nodes with a standing referential obligation to an audit (claude-klabauter `coordinator_core/roadmap/audit.py`) that runs long after they ship, unlike ordinary consumed handoffs whose context genuinely does live on in successors. That obligation is set-shaped, not edge-shaped: the audit asserts an equal count of live+archived stubs per `roadmap_id`, so a stub with no inbound referrer at all is still load-bearing and the referrer guard below cannot see it. The exempt set is bounded (a few dozen stubs across all roadmaps), so retention cost is near-zero against a deletion cost of a permanently dispatch-blocked roadmap.

       **Both names, never one** — `roadmap-baton` is live, `spinoff-roadmap` retired, and the archived corpus keeps whichever a record was written under (`coordinator/artifact-shape-contract/DECISIONS.md:42`). Resolve the pair via `kind_values_for_canonical('roadmap-baton')` where a programmatic gate is available, never a bare literal. Scoped to this canonical only — do NOT extend to `goal-seed`/`spinoff-goal`, `roadmap-seed`/`spinoff-roadmap-creator`, or any other kind.
     - KEEP the 10 most recent across the combined set by filename timestamp.
     - KEEP any older file still referenced by lineage — grep its **basename** across `docs/plans/*.md` (`predecessor_handoff:`) and `state/handoffs/*.md` (`predecessor:`, `additional_predecessors:`, `forked_from:`, `continued_into:`). A hit in any of those fields is a live referrer; do not delete regardless of age or rank.
     - Separately, check `blocked_by:` — this field is a roadmap dependency-graph edge, not lineage-ancestry, and is matched differently: it holds identifier values, never basenames. **Dispatch the op; do not re-derive the algorithm.** `handoff.blocked_by_dependents` (claude-klabauter, registered `43710cfa732d`, scope class `common_dir` — the same wrapper shape as `handoff.has_live_children`) is the tested, corpus-complete, scan-error-aware resolver for this predicate. It resolves the candidate's own identifiers (`stub_id` / `id` / `handoff_id`) and reports which LIVE handoffs list any of them in `blocked_by:`:

       Resolve the engine root FIRST, out of band: `REPO_CLAUDE_KLABAUTER` or `CLAUDE_KLABAUTER_ROOT` if either is set, else `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_engine_root.py"`. **If it resolves to nothing, or to a path that is not a directory, STOP this rule and KEEP every remaining candidate** — an unresolvable engine is the `indeterminate` case below arriving one layer earlier, and it fails closed for the same reason. With the root resolved, run this from inside it:

       ```bash
       python3 -m coordinator_core.invoke handoff.blocked_by_dependents "{\"candidate\": \"<abs-path-of-candidate>\"}" --repo "<abs-path-of-this-repo-root>"
       ```

       Honour the tri-state under `.result.state`, which is three answers and not two:
       - `dependents` — a live handoff depends on this file. **KEEP**, regardless of age or rank.
       - `none` — no live dependent. No bar to deletion from this check; the other rules still apply.
       - `indeterminate` — **the resolver could not look.** KEEP. This is fail-closed by design and must never be collapsed to `none`: a partial corpus scan that read as "no dependents" would delete exactly the file the check exists to protect. `.result.scan_errors` / `.result.error` carry why. Claude-Klabauter pins this at the op boundary, not merely inside the resolver, with `test_scan_error_surfaces_as_indeterminate_not_none_across_op_boundary` — a future edit that flattens the tri-state has to delete a test whose name says what it protects.

       **A candidate with no resolvable identifier returns `indeterminate`, not `none`** — so any archived handoff carrying no `stub_id:`/`id:`/`handoff_id:` frontmatter is retained rather than checked-and-cleared. This is deliberate conservatism at near-zero *safety* cost, not near-zero retention cost: current-format roadmap-stub records (`roadmap-baton`, or `spinoff-roadmap` under the retired name) reliably carry an identifier, but ordinary `kind: session-handoff` records occasionally do not (measured: 2 of 134 live handoffs in this repo, both current-format, dated 2026-07-28) — so the residue is ongoing, not legacy-only, and is not demonstrably shrinking. It costs nothing to the protection this check exists to provide, because `blocked_by:` protection only matters for roadmap-stub records (see below) and those do carry identifiers; the cost is purely retention of a small number of ordinary handoffs that would otherwise have pruned. It is a real behaviour change from the prose algorithm this replaced, which skipped the check for those files and let them prune.

       This check is a **subordinate backstop, not the primary protection**: `blocked_by:` appears only on roadmap-stub records, and those are already unconditionally exempt from pruning above (the exemption is what actually closes the failure) — this dependents check is defence-in-depth against a roadmap stub that somehow reaches the count/age rule despite that exemption.

       **Cost note:** each `blocked_by:` check is a fresh `python3 -m coordinator_core.invoke` process spawn (cold interpreter + package import), run once per archived-handoff candidate beyond the top-10-by-recency set — no batched form exists (`candidate` takes one path, not a list). On a repo with a large `archive/handoffs/` backlog (309 files in this repo alone) this is N cold spawns during Phase 8b, and per this repo's own runtime-conventions doctrine (`CLAUDE.md` § Runtime conventions), process spawns are cheap on some hosts and brutally expensive on others. Not a correctness concern — KEEP-by-default degrades safely — but a known, named cost. If it is ever measured as a bottleneck, the fix is a batched `candidates: [...]` param on the op.
     - PRUNE the rest — they've been consumed, nothing points at them, and their context lives in successor handoffs.
     - Measured: the missing `blocked_by:` referrer check and the missing `spinoff-roadmap` exemption together deleted two of three live roadmaps' archived stubs, breaking both the dependency-order audit (unresolved `blocked_by:` edges) and the stub-count audit (missing count no referrer check could have caught).
   - **doc-link-checker reports:** out of scope — see the `state/subagent-share/` row in the Scope table above. Nothing in `tasks/` classifies here; do not inventory `tasks/doc-link-check-*.md`, it is never written.
   - **Feature task directories (`tasks/<feature>/`):**
     - PRUNE if `todo.md` exists and all items are `[x]`, AND no `lessons.md` with unmerged entries, AND the feature branch (if identifiable from the dir name) is merged or deleted.
     - KEEP if any `[ ]` items remain or unmerged lessons present.
     - **Never delete:** `state/lessons/` (global, structured-YAML dir store), `state/health-ledger.md`, `state/bug-backlog/` (structured-YAML dir store), `state/debt-backlog/` (structured-YAML dir store), `docs/architecture/`, `state/improvement-queue/` (structured-YAML dir store), `state/handoffs/` (active), `state/week-changelog/`.
   - **Cross-repo archive memos (`cross-repo/archive/*.md`):**
     - PRUNE if `status: actioned` AND file mtime > 90 days. Parse `status:` from YAML frontmatter; do NOT prune memos lacking a `status:` field (treat as open/unknown).
     - KEEP if `status:` is absent, `open`, or any value other than `actioned`, regardless of age — these are not yet closed channel traffic.
     - KEEP if `status: actioned` AND mtime ≤ 90 days — `/distill` should have a chance to mine them first.
     - **`cross-repo/archive/` is NOT on the never-delete list** — age-based pruning of actioned memos here is safe and intentional. The 90d floor is the guard against premature deletion before `/distill` runs (see Scope table rationale above).

2. **If nothing classifies as PRUNE,** record `prune_count: 0` for the Phase 13 summary and exit this pipeline.

### Step 2: Safety Commit

Before any deletions, snapshot current state:

```bash
CLAUDE_INVOKING_COMMAND=update-docs "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --blanket "pre-prune checkpoint (update-docs Phase 8b)"
```

This makes the entire prune operation revertible as a single `git revert`.

### Step 3: Delete

Use `git rm` so deletions appear in git history:
- Plans: `git rm docs/plans/<file>`
- Archived handoffs: `git rm archive/handoffs/<file>` or `git rm archive/handoffs/<YYYY-MM>/<file>` depending on layout — individual files, not `git rm -r`
- Feature task dirs: `git rm -r tasks/<feature>/`
- Cross-repo archive memos: `git rm cross-repo/archive/<file>` (individual files, NOT `git rm -r cross-repo/archive/` — the directory and its README must survive)

Remove any empty directories left behind on the filesystem.

### Step 4: Commit

```bash
CLAUDE_INVOKING_COMMAND=update-docs "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --blanket "artifact pruning: pruned N plans, N handoffs, N task dirs (update-docs Phase 8b)"
```

### Step 5: Record Counts

Pass `pruned_plans`, `pruned_archived_handoffs`, `pruned_task_dirs`, and the safety-commit SHA to the Phase 13 summary.

## Tuning

The defaults (14-day plan retention, 10 archived handoffs) live in this pipeline file. Override by editing this file — there is no flag interface, because this pipeline runs unconditionally as part of `/update-docs`. Repos with materially different cadence should fork this file rather than thread tuning flags through `/update-docs`.

## Notes

- The safety commit ensures `git revert <safety-sha>` undoes the entire prune in one step.
- For repos with 200k+ artifacts, present counts and disk-reclaimed size in the summary, not per-file lists.
- Never delete the architecture atlas, global tracking files, or active handoffs. When in doubt, keep.
- For `distill`-then-delete (extract knowledge into wiki before deleting source), use `/distill` instead — it runs upstream of this pipeline conceptually. This pipeline prunes raw scaffolding only.
