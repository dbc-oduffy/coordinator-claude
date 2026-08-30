---
name: workweek-complete
description: "Weekly release ceremony — validate, docs, release notes, merge."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: ""
---

# Workweek Complete — Weekly Release Ceremony

PM-invoked, release-grade close. Week-changelog is the canonical ledger, never `git log`.

## Step 0.9: Tier-U Grant

Shape W (rung 0, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
`& "$env:COORDINATOR_SETTINGS_HOME\bin\tier-u-grant-cli.exe" grant ceremony "workweek-complete Tier-U consumers (Step 2 plugin-ecosystem run.js, Step 7 parallel-code-review full-tier suite)" --ceremony workweek-complete`
before either consumer fires (wiki: why both need it).

## Step 0.95: Compute the Ceremony Spine

Shape W (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\workweek-complete-brief.exe"`.
Returns `directives[]` (render each `detail` verbatim), `judgment_points[]` (resolve every open
one before its gated directive proceeds; never auto-pick a Tier-3 no-recommendation), `narration`
(surface verbatim).

**Hard-blocking:** UBT pending-record merge, reverse-drift merge, vendored-schema/
version-consistency drift, pcli-04 drift (hand-invoked, Step 5, no directive). Everything else
advisory. Read disposition from each directive's `hard_block` field — halt before Step 7 on a
hard-blocking FAIL; surface the rest without halting.

---

## Step 1: Read Week-Changelog — PM Confirmation Gate

Render enumeration + gap-backfill `detail`s. Past-date synthesized blocks frozen; today's
`-backfill.md` overwritable; human-curated daily blocks sacred. Name any backfilled dates.

Surface: week span, commit count/range, workstreams, blockers, priorities met. Priorities-met:
`state/goals/*.yaml` (`period: week`, ISO-week match) canonical, read `status` directly.
`HEADER.priorities.*.md` fills only gaps, deduped. Neither present → "no priorities were set."

**PM gate:** _"Does this summary match your recollection? Proceed?"_

---

## Step 2: Fast-Tier Validation (blocking)

Resolve `fast_test_cmd` via `cs_resolve_fast_test_cmd`: `COORDINATOR_FAST_TEST_CMD` env var → the
`fast_test_cmd` key → skip-with-notice (unconfigured → skipped, not failed) → `Validation:
0|<non-zero>|skipped`. Non-zero: stop and fix. **Disclose the magnitude, don't just name the
step** — `fast_test_cmd` is still a real test-suite run; source its actual cost from `python
coordinator/tests/_spawn_budget.py` rather than assuming it's cheap because it's "fast-tier."

`node "$CLAUDE_PLUGIN_ROOT/tests/plugin-ecosystem/run.js"` is a second Tier-U invocation — check
`tier-u-grant-cli check` first: exit 0 proceed, exit 1/malformed/missing token halt (fail-closed).

---

## Step 3: Strict Referential-Integrity Gate (blocking)

`lint-frontmatter --strict-refs --json`. `ok: false` → stop and fix. Non-ref `refWarnings` pass.

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
- **Bug backlog:** open P1/P2 ≥10 → ask `/bug-blitz` now or defer.
- **Portability sweep:** handled by Step 7's `code-reviewer-weekly`, not standalone.
- **Initiative-govern sweep:** `coordinator-initiative create`/`attach` per PM confirmation.
  **Negative-spec:** sole to this ceremony — never `/workday-complete`, `/workstream-start`,
  `/workweek-start`.
- **Cruft-sweep:** staleness >21d or >2GB reclaimable → nudge `/cruft-sweep`.
- **Sidecar reap (hand-run):** `reap-stale-subagent-sidecars`; non-zero → surface, don't skip.
- **wsc inline-budget:** `WARN: ... exceeds baseline` → note mechanism inlined not extracted.
- **Weekly KR re-assessment:** EM/PM-confirmed only; also reads `state/kr-suggestions/*.yaml`
  (schema `kr-suggestion.schema.json`), unresolved `kr_id`/`goal_id` surfaced not dropped.
  **Negative-spec:** never auto-sets `status:`.
- **Advisory results:** skill description length, owner-file invariant lint, enabledPlugins
  drift, CVE recheck (manifest changed in 14d only →
  `state/review-findings/<week-starting>-cve/deps.md`), strategic self-description nudge,
  competitor-positioning nudge, atlas drift/arch-audit staleness, human-facing doc health (each
  finding gets its own `judgment_points[]` entry, disposition never auto-picked).
- **Hard-blocking results:** UBT (`sha_range`, escape `COORDINATOR_OVERRIDE_UBT_GATE=1`),
  reverse-drift (`COORDINATOR_OVERRIDE_REVERSE_DRIFT=1`), version/schema-drift. Non-UE repos
  no-op on UBT.
- **pcli-04 drift gate (hand-run):** `workweek-complete-drift-guards pcli-drift-gate` — `0`
  continue, `1` halt before Step 7, `2` cannot-run (never treat as clean).

---

## Step 6: Housekeeping

`scc --no-complexity --no-cocomo --no-duplicates --sort code` (if available) → summary in
`state/code-stats-history.md` under `## YYYY-MM-DD`.

`workweek-complete-drift-guards shellcheck-sweep --repo-root .` — fix mechanical issues, flag
behavior-changing. `... console-flash-guard --target "$HOME/.claude/plugins"` — route through
`spawn-hidden.sh` or `# verify-no-console-flash: allow`. `... multi-event-hook-guard` — fix is
echoing stdin's `hook_event_name`, never hardcoded. All exit 0, advisory, never block merge.

---

## Step 7: Illegal-Path Backstop + Parallel Code-Review Gate

Illegal-path scan (NTFS-illegal chars) on tracked+staged paths; non-zero → halt: rename/remove,
re-commit, re-run. Compute session-keyed trail-scope shard (newest matching `<SID_SHORT>`, else
newest overall).

Read `~/.claude/plugins/coordinator/skills/parallel-code-review/SKILL.md`,
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
(check `archive/release-notes/`, never `git log --contains`).

**Reconcile backstop is KILLED — no step here.** `workweek-complete-close reconcile-sweep` and
`reconcile-completion-commits.py` are both retired in the engine repo's relocation ledger; the
launchers survive and exit 127. The requirement (folding `Session-Id:`-trailer commits into a
pending-release entry's `commits:`) is a live rebuild candidate in the kill-ledger — restore this
backstop only when a successor CLI ships. Until then a missing SHA is caught, if at all, by the
editorial pass below reading the entry corpus.

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

`docs/wiki/versioning-convention.md`, if present, is authority. Fallback: Major = breaking change
in any `Decisions:` field; Minor = new feature/command; Patch = fixes/docs/refactors only.

**This step is the weekly bump for the coordinator-plugin-triple anchor** — `plugin.json`
`.version`, `marketplace.json` `.metadata.version`, and the CHANGELOG's latest `## [X.Y.Z]`
section, the only anchors that exist today. EM proposes the level; PM confirms — the gate below
IS that confirmation, because a release surface is a product call. **Engine anchor row:
named-but-empty here** — a different, per-publish-shaped cadence, not this bump/miss-flag cycle;
fills once claude-klabauter-em's contract converges.

**PM gate:** propose vX.Y.Z with one-line rationale; update release-notes filename and
HEADER.md `Prior week released:`.

**Stamp atomically** in the same commit as the CHANGELOG `[Unreleased] → [X.Y.Z]` stamp:
`coordinator/.claude-plugin/plugin.json` `.version` and `.claude-plugin/marketplace.json`
`.metadata.version` both move to `X.Y.Z`. Run `check-version-consistency` before Step 15 —
non-zero means a surface was missed.

---

## Step 14: Release Publish — Backstop Un-Draft

Catch-all for work reaching main via direct daily-branch commits bypassing `/merge-to-main`'s
tagged-publish leg. Precondition: PM confirmed version at Step 13 (`$VERSION_TAG`).

`gh release view "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude --json isDraft,isLatest`:
already published → skip; draft/none → proceed; tag missing → create it.

**PM gate (irreversible external action):** un-draft via `gh release edit ... --draft=false
--latest`, or create via `gh release create ...` using Step 12's notes file as body.

**Scope:** coordinator-claude only. Deep-research-claude release publishing is owned by the
deep-research-currency-notification spinoff. Claude Prime (`source_is_live`) never tagged — skip
silently on the `~/.claude` meta-repo.

---

## Step 15: `/merge-to-main`

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

Moves daily files + priorities fragments to `archive/week-changelogs/<week-starting>/`,
review-trail JSON to `archive/review-trail/<week-starting>/` (`.gitkeep` and
`.weekly-reviewer-scopes-*.json` shards deleted not archived), rewrites `HEADER.md`, commits +
pushes. Run `workweek-complete-close archive --version vX.Y.Z --merge-sha <merge-sha>`
(`--no-push`/`--no-git` variants exist). **Must run AFTER Step 7 consumes the trail.**

**Multi-week precondition.** Default archive is unbounded by date — destructive if a week was
skipped. Compare block dates in `state/week-changelog/` against HEADER's `**Week starting:**`;
mismatch means multi-week — use `archive --week-only`, one run per week (pair with
`--move-priorities` on the fragment-owning week only; out-of-window blocks stay in place;
`.weekly-reviewer-scopes-*.json` shards are skipped not deleted and accrue).

**Negative spec:** the daily matcher `^\d{4}-\d{2}-\d{2}.*\.md$` also matches
`YYYY-MM-DD-pending-release.md` (Step 12's live editorial corpus) — an unbounded sweep archives
it and the next release draft finds nothing. Check the dated-file list for non-daily entries
first.

Tail: opt-in `workweek_complete_post_command:` hook (advisory, non-blocking); cadence emission
at completion (best-effort).

**Push checkpoint — `push.outstanding`.** Push runs on a cadence, not on every commit, and this
is one of its named checkpoints. Once the commit has landed, call the primitive once and block on
it (~150ms, synchronous — no detach or background wrapper):

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" push.outstanding '{}' --repo "<repo-root>"`

Shape W above (PowerShell host); Shape A/B on a POSIX host — `snippets/resolve-coordinator-bin.md`.
`skipped: push:nothing-outstanding` is the ordinary no-op result, not a failure. The op owns the
branch-gate refusal, the protected-branch policy, the retry ladder, and the LFS-range predicate —
never hand-roll a `git push` beside it.

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
`Tracker`, `Week-changelog`. Each is already recorded by its own commit — `git log`/`git show` is
the record, absence here is not evidence the step was skipped.

---

### What This Does NOT Do

- **Auto-fire.** PM-invoked; `/workday-complete` surfaces the staleness signal.
- **Re-author from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 15 delegates to `/merge-to-main`.
- **Delete release notes or handoffs.** Only daily changelog files are archived.
- **Touch trail records via `/distill` or `/update-docs`/handoff-archival.** Trail JSON is
  archived in Step 18 only.

Relationship to other commands, gate rationale, C-number archaeology, and Tier-U write history:
wiki.
