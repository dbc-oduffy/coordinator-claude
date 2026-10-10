---
name: workweek-complete
description: "Weekly release ceremony — validate, docs, release notes, merge."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: ""
disable-model-invocation: true
---

# Workweek Complete — Weekly Release Ceremony

PM-invoked, release-grade close. Week-changelog is the canonical ledger.

## Step 0.95: Compute the Ceremony Spine

Shape W (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\workweek-complete-brief.exe"`.
Returns `directives[]` (render each `detail` verbatim), `judgment_points[]` (resolve every open
one before its gated directive proceeds; never auto-pick a Tier-3 no-recommendation), `narration`
(surface verbatim).

**Hard-blocking:** reverse-drift merge, version-consistency drift, pcli-04 drift
(hand-invoked, Step 5, no directive). Everything else advisory. Read disposition from each
directive's `hard_block` field — halt before Step 7 on a hard-blocking FAIL; surface the rest
without halting.

**Vendored-schema drift is advisory, and its absence from the set above is a ruling.** The
`schema-drift-gate` verdict covers the ENGINE's vendored `coordinator_core/frontmatter/schemas/`,
which a consuming repo cannot re-vendor. Surface DRIFT with the owning repo named and proceed.

**UBT pending-record merge is NOT in that set, and its absence is a ruling.** UBT freshness is
Example-game-repo's requirement, discharged by example-game-repo's own ceremonies. Do not re-add the gate or
compensating EM prose for it.
<!-- guard-allow: directive-ids-are-engine-current d_step4c_ubt_pending_merge_gate is named here as history: the engine repo drained it at f88ae3bddf and this text exists to say the gate is dead. -->
Until the engine drain publishes, the mirror still emits `d_step4c_ubt_pending_merge_gate` (`4c`),
which exits 1 with `ModuleNotFoundError: ... scan_unresolved_ubt_records`. That is a dead gate, not
a release blocker; proceed and hand-derive no UBT verdict.

---

## Step 1: Read Week-Changelog — PM Confirmation Gate

Render enumeration + gap-backfill `detail`s. Past-date synthesized blocks frozen; today's
`-backfill.md` overwritable; human-curated daily blocks sacred. Name any backfilled dates.

Surface: week span, commit count/range, workstreams, blockers, priorities met. Priorities-met:
`state/goals/*.yaml` (`period: week`, ISO-week match) canonical, read `status` directly.
`HEADER.priorities.*.md` fills only gaps, deduped. Neither present → "no priorities were set."

**Three states — achieved / missed / never-assessed,** produced by
`python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/bin/goal-assessment-staleness.py"`: an unread instrument, not a missed goal.
Own line, never inside the achieved/missed counts. Tripwire:
`AN-UNSTAMPED-GOAL-IS-NEVER-ASSESSED-NOT-MISSED`. Exit 2 ("could not read the goals
directory/artifacts") is unknown, not clean — surface it as such, never as "no never-assessed
goals."

For each never-assessed goal, render per-KR status plus evidence candidates via
`python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/bin/goal-kr-evidence.py" --json`.
Own line, never folded into the achieved/missed counts — same tripwire above still governs.

**PM gate:** _"Does this summary match your recollection? Proceed?"_

---

## Step 2: Fast-Tier Validation (blocking)

Resolve `fast_test_cmd` via `cs_resolve_fast_test_cmd`: `COORDINATOR_FAST_TEST_CMD` env var → the
`fast_test_cmd` key → skip-with-notice (unconfigured → skipped, not failed) → `Validation:
0|<non-zero>|skipped`. Non-zero: stop and fix. **Disclose the magnitude, don't just name the
step** — `fast_test_cmd` is still a real test-suite run; source its actual cost from `python
coordinator/tests/_spawn_budget.py` rather than assuming it's cheap because it's "fast-tier."

`node "$CLAUDE_PLUGIN_ROOT/tests/plugin-ecosystem/run.js"` is a second Tier-U invocation.

---

## Step 3: Strict Referential-Integrity Gate (blocking)

`ok: false` → stop and fix. Non-ref `refWarnings` pass.

**Partitioned waiver — the only route past a red. THERE IS NO FLAG:** the gate keeps reading `ok: false` and you report it red. Record a waiver only when every remaining failure is one conceded upstream class proven from `--json` (never a summary), honest-fix errors are fixed first with both counts stated, and the reason is recorded where a reader meets it. Tripwire: `CARRY-IT-RED-WHEN-THE-GATES-OWNER-HAS-CONCEDED-THE-DEFECT`.

---

## Step 4: Run `/update-docs`

Full multi-phase docs sweep; commits and pushes to the current branch. Wait for completion.

---

## Step 5: Improvement-Queue, Tripwire, Initiative, and Guard-Sweep Triage

Resolve from the spine's directives in one pass; advisory rows never block:

- **Tripwire fire-log:** ≥50% `em-side` or any `agentId` ≥3 → nudge dispatch-size recalibration.
- **Improvement queue:** `[recurring: ≥3]` first, one executor per target, delete resolved
  (never annotate); >15 → `/staff-session`-style sweep.
- **Prior-art sidecar scan:** dispositioned `override-and-document`/`update-prior-art`/`both`;
  wiki cited ≥3× → revision candidate.
- **Audience-mismatch (hand-run):** `coordinator_core.ops.audience_mismatch_scan --root .`.
  ≥3-cluster on one gap → route via `coordinator/skills/review/SKILL.md` § A.3 — Sequencing.
- **The register stall check:** `coordinator-invoke requirement_register.stall_report '{"today":"<YYYY-MM-DD>"}'`;
  render stale rows, stuck plans, unclaimed rows as a "Register stall check" section (omit when empty or op absent). Advisory.
- **Bug backlog:** open P1/P2 ≥10 → ask `/bug-blitz` now or defer.
- **Portability sweep:** handled by Step 7's `code-reviewer-weekly`, not standalone.
- **Initiative-govern sweep:** `coordinator-initiative create`/`attach` per PM confirmation.
  **Negative-spec:** sole to this ceremony — never `/workday-complete`, `/workstream-start`,
  `/workweek-start`.
- **Cruft-sweep:** harness/orphan-class staleness >21d or >2GB reclaimable → nudge `/cruft-sweep`
  (repo `scratch/` is not this class; Step 6 purges it).
- **Strategic self-description staleness (named line item, not an advisory):** newest
  `state/strategic/self-description.yaml` `version_highlights[].date` older than 14d → run
  `coordinator:strategic-self-description-refresh` this ceremony (it carries its own human ratify
  gate). Missing file in a repo that has adopted the standard reads as stale. **Negative-spec:** a
  disposition of "skip" is recorded with a reason on the spine — never silently dropped or folded
  into the advisory bucket. Standard: `coordinator/docs/wiki/skills-corpus/strategic-self-description-standard.md`;
  onboarding is `coordinator/skills/repo-setup/SKILL.md`'s.
- **Sidecar reap (hand-run):** `reap-stale-subagent-sidecars`; non-zero → surface.
- **wsc inline-budget:** `WARN: ... exceeds baseline` → mechanism inlined not extracted.
- **Weekly KR re-assessment:** `& "$env:COORDINATOR_SETTINGS_HOME\bin\reassess-goal-krs.exe"`
  (Shape W); also reads `state/kr-suggestions/*.yaml`, unresolved `kr_id`/`goal_id` surfaced not
  dropped. EM/PM-confirmed only; apply via
  `& "$env:COORDINATOR_SETTINGS_HOME\bin\set-goal-kr-status.exe"`, never a hand-edit.
  **Negative-spec:** neither auto-sets `status:` — why Step 1's never-assessed line exists; only
  writer is human.
- **Advisory results:** skill description length, owner-file invariant lint, enabledPlugins
  drift, CVE recheck (manifest changed in 14d only →
  `state/review-findings/<week-starting>-cve/deps.md`), competitor-positioning nudge, atlas
  drift/arch-audit staleness, human-facing doc health (each
  finding gets its own `judgment_points[]` entry, disposition never auto-picked).
- **Hard-blocking results:** reverse-drift (`COORDINATOR_OVERRIDE_REVERSE_DRIFT=1`),
  version-consistency. Neither vendored-schema drift nor UBT is a member — see § Step 0.95. A `4c` directive still arriving
  from an unpublished mirror exits 1 on `ModuleNotFoundError`; that is the dead gate, not a
  finding.
- **pcli-04 drift gate (hand-run):** `workweek-complete-drift-guards pcli-drift-gate` — `0`
  continue, `1` halt before Step 7, `2` cannot-run (never treat as clean).

---

## Step 6: Housekeeping

`scc --no-complexity --no-cocomo --no-duplicates --sort code` (if available) → summary in
`state/code-stats-history.md` under `## YYYY-MM-DD`.

`... verify-no-console-flash --target "$HOME/.claude/plugins"` — route through
`spawn-hidden.sh` or `# verify-no-console-flash: allow`.
`... check-multi-event-hook-hardcoded-event` — fix is
echoing stdin's `hook_event_name`, never hardcoded. Both exit 0, advisory, never block merge.

**Scratch purge + hold nag.** `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" fleet.scratch_hygiene '{"repo_root":"<repo-root>","cadence":"workweek_complete","apply":false}'`
(Shape per `resolve-coordinator-bin.md`). Dry-run first; re-run with `"apply":true` only when the summary's `capabilities` includes
`hold_pending_marker`, else report the plan. Render `hold-nag` records (incl.
`skipped-hold-pending`) as a "Scratch-hold" section; exit 1 is a report section. The nag deletes
nothing. Op absent or erroring → report "fleet.scratch_hygiene not yet available" and continue;
never abort, never delete by hand.

---

## Step 7: Illegal-Path Backstop + Parallel Code-Review Gate

Illegal-path scan (NTFS-illegal chars) on tracked+staged paths; non-zero → halt: rename/remove,
re-commit, re-run. Compute session-keyed trail-scope shard (newest matching `<SID_SHORT>`, else
newest overall).

Read `${CLAUDE_PLUGIN_ROOT}/skills/parallel-code-review/SKILL.md`,
execute against the shard. The Staff Engineer NOT in this gate — see Step 8.

- **BLOCKED:** halt before Step 10; surface verdict + findings-dir path.
- **WARN / OK:** proceed; verdict line goes into release notes (Step 12).

Skip rules (full detail in skill body): <10 lines/internal-only skip; doc-only week skips
code-semantics; plan-only week skips entirely; `--force` passes through.
**Already-reviewed-span (EM-judgment):** a large catch-up span already verdicted at
`/workstream-complete` may skip the chunk gate (record `incrementally-reviewed`) or narrow to
the un-reviewed subset.

---

## Step 8: the Staff Engineer Layer-2 — Architecture Pass (advisory, does NOT gate merge)

Skip if `arch_tier_candidates`, `convergent_findings`, seam-file set, and the daily
strategic-observer (DSR) trail's `for-weekly-arch-review` flags are all empty.

**EM-discretion:** on a large already-reviewed span, seam-file count alone must NOT auto-fire.
Default OFF.

Otherwise dispatch the Staff Engineer (`coordinator:staff-eng`, Opus) with changelog digest,
`arch_tier_candidates`/`convergent_findings`, `staff_eng_seam_files` (Step 7's shard), the DSR trail.
The Staff Engineer produces candidates only; EM routes: trivial → immediate executor; mid-size → bundled
spinoff; large/structural → standalone spinoff or `/plan`. Surface with the release-notes draft
(Step 12).

---

## Step 9: Architecture Audit Fold + Atlas Drift Walk

**Staleness:** `STALE` (>10d or never targeted-audited) → auto-fold a targeted-on-diff audit,
scoped to diff-touched systems. `FRESH` → no fold (EM may still trigger on heavy churn).
`UNKNOWN` → note. Never edits code — findings become spinoff candidates.

**Atlas drift walk:** `DRIFT`/`MISSING` folds into the staleness pass. `ERROR`/`MALFORMED` →
helper issue, never FRESH. `STALE` (>30d) → EM-judgment: ratify current (no-op commit) or
schedule `/architecture-audit` — never auto-dispatches.

---

## Step 10: Retired, no-op — placeholder keeps numbering stable.

---

## Step 11: LoE High-Water Check — MANDATORY Before Step 12

Union four `query-completions` sets: chain-terminal `chain_loe.tshirt=XL`, same for `XXL`,
single-session `loe.tshirt=XL AND chain_terminal=true`, same for `XXL`.

**NEGATIVE SPEC:** never collapse into `chain_loe.tshirt in (XL, XXL)` — `in (...)` matches only
a dotless field; a dotted field with `in` is a hard parse failure (exit 1), taking this mandatory
gate down. One `=` query per notch, unioned.

Surface each entry's title, chain slug, sessions/tshirt, date span. Zero → note explicitly. No PM
gate; PM may promote an entry to Highlights at Step 12.

---

## Step 12: Editorial Bucketing + Release Notes Draft — PM Review Gate

`mkdir -p state/week-changelog/`. Query `pending-release` entries since HEADER's week-start. Zero
→ empty-week note.

**Main-membership is not "already announced."** An entry already on `origin/main` is the
catch-up target, not a double-count risk — what matters is coverage in a *prior* release's notes
(check `archive/release-notes/`).

**Reconcile backstop is KILLED — no step here.** `workweek-complete-close reconcile-sweep` and
`reconcile-completion-commits.py` are retired; their launchers survive and exit 127. Folding
`Session-Id:`-trailer commits into an entry's `commits:` is now unbacked — a missing SHA is caught,
if at all, by the editorial pass below. Restore only when a successor CLI ships.

**Editorial bucketing:** dispatch a Sonnet worker with the entry corpus; writes
`state/week-changelog/YYYY-MM-DD-pending-release.md`. Bucket by `nature`+`loe.tshirt`: roadmap
L/XL/XXL → Highlights; roadmap S/M → Notable; roadmap XS → Other; user-visible bugfix (any) or
bugfix XL → Notable; bugfix S/M/L → Other; tech-debt/infra non-XL → Other; tech-debt/infra XL →
Notable (EM call, override stated). Empty buckets: `_none this week_`; ≥5 similar Other-only
entries collapse to "... and assorted fixes" (EM override permitted on any row — state explicitly
in the dispatch). Each entry cites its source file. Step 7's verdict goes verbatim under
`_Code-review gate verdict:_`. Verify the file exists and is non-trivial before proceeding.

Read the pending-release file, write `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md` as a thin
formatting wrapper — do NOT re-author. Version is a placeholder until Step 13.

**PM gate:** present draft path and bucket counts; wait for review; update both files for any
reclassifications.

---

## Step 13: Version Bump — PM Confirmation Gate

`coordinator/docs/wiki/install-playbook-rationale/versioning-convention.md`, if present, is authority. Fallback: Major = breaking change
in any `Decisions:` field; Minor = new feature/command; Patch = fixes/docs/refactors only.

**This step is the weekly bump for the coordinator-plugin-triple anchor** — `plugin.json`
`.version`, `marketplace.json` `.metadata.version`, and the CHANGELOG's latest `## [X.Y.Z]`
section. EM proposes the level; the gate below is PM's confirmation. The engine is not an anchor
here — it bumps per-publish (`coordinator/docs/wiki/release-and-distribution/release-cadence-and-currency-notification.md`
§ Engine anchor), never on this weekly clock.

**PM gate:** propose vX.Y.Z with one-line rationale; update release-notes filename and
HEADER.md `Prior week released:`.

**Stamp atomically** in the same commit as the CHANGELOG `[Unreleased] → [X.Y.Z]` stamp:
`coordinator/.claude-plugin/plugin.json` `.version` and `.claude-plugin/marketplace.json`
`.metadata.version` both move to `X.Y.Z`. No CHANGELOG in the repo: the anchor pair is the whole
stamp, not a missed surface.

**`check-version-consistency --root <dir holding .claude-plugin/>` before Step 15** — `coordinator/`
in the source repo, repo root in the mirror. **Omitting `--root` exits 0 having checked nothing**
(it prints `could not locate ...`, then skips). Confirm the OK line names a version; the exit code
alone does not.

---

## Step 14: Release Publish — Backstop Un-Draft

Catch-all for work reaching main via direct daily-branch commits bypassing `/merging-to-main`'s
tagged-publish leg. Precondition: PM confirmed version at Step 13 (`$VERSION_TAG`).

`gh release view "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude --json isDraft,isLatest`:
already published → skip; draft/none → proceed; tag missing → create it.

**PM gate (irreversible external action):** un-draft via `gh release edit ... --draft=false
--latest`, or create via `gh release create ...` using Step 12's notes file as body.

**Scope:** coordinator-claude only. Deep-research-claude release publishing is owned by the
deep-research-currency-notification spinoff. Claude Prime (`source_is_live`) never tagged — skip
silently on the `~/.claude` meta-repo.

---

## Step 15: `/merging-to-main`

Invoke only after PM has confirmed release notes (Step 12) and version (Step 13). Do NOT inline
merge logic.

---

## Step 16: Health Survey

Run the full health survey if available; record output in `state/health-ledger.md` under today's
date.

---

## Step 17: Auto-Memory Drain (blocking gate)

Auto-memory is ephemeral — drains to zero every close.

Shape W (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\check-auto-memory-drained.exe" --root .`

Exit 0 → Step 18. Exit 1 → prints every residual path attributed to this closing session. For
EACH: **PROMOTE** (write to its durable home — doctrine, wiki, `docs/decisions/`,
`state/lessons/` via `/learn-lessons`, orientation cache — note target path) or **DROP** (say so
explicitly). Silence is not a disposition.

Delete every named file, re-run to confirm exit 0. Record the disposition list in Step 19 under
**Auto-memory drain**.

**First invocation exits 0 immediately, or `SKIPPED`:** omit the summary line. **If the gate ever
printed residue this run, even once:** the disposition list is mandatory even though the store is
now empty.

Residue is row-granular to this session only — never the whole store, never a peer's rows.

---

## Step 18: Archive + Reset Week-Changelog

Moves daily files + priorities fragments to `archive/week-changelogs/<week-starting>/` (which must
end up holding one `WEEK-SUMMARY.md` in the rollup-frontmatter shape —
`coordinator/docs/wiki/ceremony-calibration/daily-summary-procedure.md` § Rollup Frontmatter Standard),
review-trail JSON to `archive/review-trail/<week-starting>/` (`.gitkeep` and
`.weekly-reviewer-scopes-*.json` shards deleted not archived), rewrites `HEADER.md`, commits +
pushes. Run `workweek-complete-close archive --version vX.Y.Z --merge-sha <merge-sha>`
(`--no-push`/`--no-git` variants exist). **Must run AFTER Step 7 consumes the trail.**

**Multi-week precondition.** Default archive is unbounded by date — destructive if a week was
skipped. Compare block dates in `state/week-changelog/` against HEADER's `**Week starting:**`;
mismatch means multi-week — use `archive --week-only`, one run per week (pair with
`--move-priorities` on the fragment-owning week only; out-of-window blocks stay in place;
`.weekly-reviewer-scopes-*.json` shards are skipped not deleted and accrue). Under
`--week-only`, the `HEADER.md` rewrite is conditional on `derive_week_start(HEADER.md) ==
week_starting` — inert at a genuine live boundary but silently skipped if HEADER still carries
the "(not yet set …)" sentinel; treat that as known behavior, not something this step branches
on.

**Negative spec:** the daily matcher `^\d{4}-\d{2}-\d{2}.*\.md$` also matches
`YYYY-MM-DD-pending-release.md` (Step 12's live editorial corpus) — an unbounded sweep archives
it and the next release draft finds nothing; concretely, `state/week-changelog/2026-07-20-pending-release.md`
is the live accumulator this matches today. Check the dated-file list for non-daily entries
first.

Tail: opt-in `workweek_complete_post_command:` hook (advisory, non-blocking); cadence emission
at completion (best-effort).

**Push checkpoint — `push.outstanding`.** A backstop for anything the per-commit auto-push hook
missed. Fire the primitive and move on — do not block on it, detach it, or wrap it; branch-gate,
protected-branch policy, retry ladder and LFS-range predicate belong to the op, never a hand-rolled
`git push`. An empty reconcile read is not proof the call failed — wait, then read again.

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" push.outstanding '{}' --repo "<repo-root>"`

Shape W above (PowerShell host); Shape A/B on a POSIX host — `snippets/resolve-coordinator-bin.md`.
`skipped: push:nothing-outstanding` is the ordinary no-op result, not a failure.

**Maintenance checkpoint — `git.maintenance` weekly tier.** Advisory, non-zero reported, ceremony
continues:

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" git.maintenance '{"tier":"weekly","repo":"<repo-root>"}'`

Shape W above / Shape A/B POSIX — `snippets/resolve-coordinator-bin.md`. `--repo` flag refused
(`scope='none'`); `repo` goes in the JSON params, not omitted. One call, one tier — the op prunes,
runs the weekly schedule (superset of daily+hourly), then sweeps orphan packs, in that order
internally; never sequence prune and maintenance as separate call-site steps.

---

## Step 19: Final Summary

**Report by exception.** Four lines always; everything else only when not clean — ≤200-word
budget from global `CLAUDE.md § Communication Style`.

```
## Workweek Complete

**Shipped:** N workstreams — one-line characterization
**Version:** vX.Y.Z
**Merged to main:** [yes — PR #N / blocked: reason]
**Next:** run /workweek-start to set priorities for the new week
```

Append a line only when its condition holds:

| Line | Include only when |
|---|---|
| `**Validation:**` | failures occurred |
| `**ShellCheck:**` | the sweep found/fixed N issues |
| `**Code-review gate:**` | BLOCKED or WARN, or findings fixed |
| `**Arch pass (Step 8):**` | N ≥ 1 arch-tier candidates surfaced |
| `**Arch audit fold (Step 9):**` | Step 9 folded a stale targeted audit |
| `**Improvement queue:**` | K ≥ 1 entries processed |
| `**Bug backlog:**` | N ≥ 1 open P1/P2 items, or `/bug-blitz` proposed/deferred |
| `**Auto-memory drain:**` | drain gate printed residue at any point — full `path -> PROMOTE(target)/DROP` list |
| `**Post-ceremony hook:**` | the tail hook produced output |

**Negative-spec — gone, do not restore:** `Week`, `Release notes`, `Docs updated`, `Code stats`,
`Tracker`, `Week-changelog`. Each is already recorded by its own commit; absence here is not
evidence the step was skipped.

---

### What This Does NOT Do

- **Auto-fire.** PM-invoked; `/workday-complete` surfaces the staleness signal.
- **Re-author from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 15 delegates to `/merging-to-main`.
- **Delete release notes or handoffs.** Only daily changelog files are archived.
- **Touch trail records via `/distill` or `/update-docs`/handoff-archival.** Trail JSON is
  archived in Step 18 only.

Relationship to other commands, gate rationale, C-number archaeology, and Tier-U write history:
wiki.
