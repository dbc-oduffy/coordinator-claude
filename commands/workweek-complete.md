---
name: workweek-complete
description: "Weekly release ceremony — validate, docs, release notes, merge."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: ""
---

# Workweek Complete — Weekly Release Ceremony

PM-invoked, release-grade close. Reads the week-changelog as the canonical record of what shipped — does NOT reconstruct the week from `git log`. Heavy steps dropped from `/workday-complete` live here: `/update-docs`, ShellCheck, improvement-queue triage, scc, version bump, and merge.

**Design contract:** the week-changelog is the ledger. The weekly ceremony reads it, validates against it, and archives it. Release notes are drafted from it, not re-derived.

## Step 0.9: Tier-U Grant (Implicit Ceremony Grant — Written)

`/workweek-complete` holds an implicit Tier-U grant — one of the three ceremonies (alongside `/workday-complete` and `/merge-to-main`) authorized to run the full, unscoped test suite without a fresh ask each time, because each is already a deliberate full-repo gate. Write the token here, before either downstream consumer fires: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" grant ceremony "workweek-complete Tier-U consumers (Step 2 plugin-ecosystem run.js, Step 8 parallel-code-review full-tier suite)" --ceremony workweek-complete`.

**Correction to a prior version of this note.** This step used to write no token, on the stated grounds that the ceremony's only test invocation (Step 2) is Tier F. That premise was found false during a Tier-U enforcement sweep: (1) Step 2's own `node "$CLAUDE_PLUGIN_ROOT/tests/plugin-ecosystem/run.js"` is an unscoped runner invocation — Tier U regardless of how it is reached, independent of the separate `fast_test_cmd` resolution in that same step; and (2) Step 8 dispatches `/parallel-code-review`, whose Test-Output Capture step runs the full suite (`coordinator_resolve_validation_cmd.py --full`) and now gates that run on a live `tier-u-grant-cli check` (`skills/parallel-code-review/SKILL.md` § Test-Output Capture). Both consumers need this ceremony's grant to be live before they fire. `/merge-to-main` at Step 16 still writes its own separate grant at its own open — that is unaffected by this write and remains correct on its own terms. Do not remove this write again without re-verifying both Step 2 and Step 8's call sites first.

---

## Step 0.95: Compute the Ceremony Spine

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-complete-brief"`.

The assembler computes the whole mechanical spine of this ceremony in one read-only pass —
week-changelog enumeration + gap backfill, fast-test-cmd resolution, referential-integrity lint,
the runtime-tripwire/improvement-queue/initiative/cruft-sweep/wsc-budget/goal-KR counts, the
Step 4b–4k guard-sweep battery, the illegal-path backstop, the weekly trail-scope compute, the
architecture-audit staleness + atlas-drift-walk reads, the version-consistency check, and the
archive/reset — and returns one decision object:

- **`directives[]`** — each names an existing CLI and is either unconditional (`depends_on: null`,
  execute as you reach it) or gated on a `judgment_points[]` disposition. Render each `detail`
  into the step it belongs to below rather than re-deriving the finding by hand.
- **`judgment_points[]`** — the genuine EM/PM calls the assembler cannot resolve for you. Each
  carries `question`, `dispositions[]`, and (Tier-2 only) a `recommendation` + `rationale` —
  resolve every open one before its gated directive(s) proceed; never auto-pick a disposition for
  a Tier-3 (no-recommendation) point.
- **`narration`** — surface verbatim where noted below. Covers `scc`, `node run.js`, and
  `gh release`, which have no consumes-manifest project script and are never `directives[]`
  entries.

**Guard-sweep hard-block set (AC9 census, not the emitted `hard_block` flag alone).** Three of
the ten former Step 4b–4k lettered gates are hard-blocking — UBT pending-record merge, the
reverse-drift merge gate, and the vendored-schema/version-consistency drift gate — the remaining
seven are advisory-only and never halt. Halt before Step 8 on any FAIL among the hard-blocking
three; surface the rest without halting. **Known gap:** the assembler's own `hard_block` field on
the guard-sweep directive does not yet mark the UBT check `true` — treat UBT failures as
hard-blocking per this paragraph regardless of what the emitted flag says until that's fixed
upstream.

What follows is the residue the assembler does not compute: the PM gates, the dispatch-worthy
judgment calls, the skill-shaped steps (`/update-docs`, the parallel code-review gate, the Staff Engineer's
architecture pass, editorial bucketing, `/merge-to-main`), and the two items outside the C4
consumes-manifest (Subagent-share Sidecar Reap, the diff-scoped portability sweep) that still run
by hand.

---

## Step 1: Read Week-Changelog — PM Confirmation Gate

`directives[]` cover the enumeration (`d_step1a_list_changelog`) and gap-backfill
(`d_step1b_backfill_changelog_gaps`) — render each `detail` here. Past-date synthesized blocks
stay frozen; today's `-backfill.md` is overwritable by design (commits land throughout the day).
Human-curated daily blocks (no `-backfill` suffix) are always sacred. Name any backfilled dates
in the summary below so the PM can amend before release-notes drafting.

Surface to PM:

```
Week covers: D days (YYYY-MM-DD to YYYY-MM-DD)
Commits: N (range: <oldest-sha>..<newest-sha>)
Implemented workstreams: <list from Plans touched: implemented fields>
Blockers: <list or "none">
Priorities met: <from period=week goal .yaml artifacts' status, dual-sourced with legacy HEADER.priorities.*.md fragments as fallback>
```

**Priorities-met computation (goal-artifact CANONICAL, fragment FALLBACK).** Glob
`state/goals/*.yaml`, keep `period: week` artifacts matching the closing week's ISO-week, and read
`status` directly — no freeform-text parsing. Fall back to `state/week-changelog/HEADER.priorities.*.md`
fragments only for a priority no goal artifact already represents — dedup by priority
text/identity, never double-count the same priority from both sources. No fragments and no goal
artifacts → report "no priorities were set this week." Don't drop a fragment as duplicative
across writers — the dedup rule is cross-source, not cross-fragment.

**`jp_step1c_pm_recollection_match`** (Tier-3, your-call — no recommendation; reason:
pm-authority). Ask: _"Does this summary match your recollection? Proceed with release ceremony?"_
This is the single explicit PM gate before the irreversible steps — **wait for confirmation
before continuing.**

---

## Step 2: Fast-Tier Validation (blocking)

`d_step2_resolve_validation_cmd` resolves the configured `fast_test_cmd` (rc 0 = resolved, rc 2 =
none configured — treat as skipped, not failed). Run the resolved command in a `bash -c` sandbox
and capture its exit code.

**The plugin-ecosystem contract suite is a Tier-U invocation, not Tier F, and is gated
separately.** `node "$CLAUDE_PLUGIN_ROOT/tests/plugin-ecosystem/run.js"` names no test file,
directory, or node-id — an unscoped runner invocation is Tier U under the disjunctive
definition of that tier regardless of how it is reached, independent of the `fast_test_cmd` run above. Before
firing it, re-confirm the Step 0.9 grant is still live rather than trusting that step having run
earlier in this same ceremony: run
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" check`.
Exit 0 — proceed and run the suite. Exit 1 (ungranted) — halt before this invocation and surface
to the PM; a token absent or malformed reads as ungranted, never granted (fail-closed). The
`fast_test_cmd` run above is also a grant-gated invocation now — it is already covered by the
Step 0.9 token written before either consumer fires, so no separate grant check is needed here.

Capture exit codes — they populate `Validation:` in the changelog block:
- **`Validation: 0`** — fast-tier passed; plugin ecosystem check passed.
- **`Validation: <non-zero>`** — configured fast-test command failed. Stop and fix before proceeding.
- **`Validation: skipped`** — no `fast_test_cmd` configured. Proceed with awareness that fast-tier
  was not run.

Any blocking failure → stop and report. Fix before proceeding.

> Tier F (`fast_test_cmd`) cadence gate — cap parallelism at ~50% cores. Tier F is grant-gated
> here too, covered by the Step 0.9 token rather than a separate check. The plugin-ecosystem
> `node run.js` invocation above is the ceremony's first of two Tier-U consumers — see Step 0.9;
> the second is Step 8's `/parallel-code-review` full-tier run.

---

## Step 3: Strict Referential-Integrity Gate (blocking)

`d_step2_5_lint_frontmatter` runs `lint-frontmatter --strict-refs --json` — the one place a
dangling `predecessor_id`/`origin_handoff_id` or a path/ID divergence escalates from `/validate`'s
soft-warn to a blocking error. `ok: true` (empty `violations`) passes even with non-ref
`refWarnings` present. `ok: false` → stop and fix before proceeding.

---

## Step 4: Run `/update-docs`

Full multi-phase docs sweep. Commits and pushes to the current branch. Wait for completion.

---

## Step 5: Improvement-Queue, Tripwire, Initiative, and Guard-Sweep Triage

`d_step3_5_advisories` and the Step-4-counts directives (`d_step4_counts_query_records`,
`d_step4_counts_initiative_candidates`, `d_step4_counts_coordinator_initiative`,
`d_step4_counts_cruft_sweep`, `d_step4_counts_wsc_budget`, `d_step4_counts_goal_krs`) and the
guard-sweep directives (`d_step4b_4k_drift_guards`, `d_step4b_4k_reverse_drift`,
`d_step4b_4k_version_consistency`, `d_step4b_4k_competitor_positioning`,
`d_step4b_4k_atlas_watch_drift`, `d_step4b_4k_arch_audit_staleness`), plus the human-facing
doc-health guard-sweep directive (staleness + content verification), resolve everything below in
one pass — render each `detail` under its heading rather than re-running the underlying CLI by
hand. The doc-health directive is computed by the Step 0.95 spine before Step 4 runs, but — like
every other 4b–4k gate — its disposition happens here at Step 5, not as input to Step 4's
`/update-docs` pass: this doc class (root `README.md`, `INSTALL.md`, `CONTEXT.md`,
`CONTRIBUTING.md`, plugin-root READMEs) is precisely what `/update-docs` does not cover, so
there is no pass for it to inform.

**Runtime-tripwire fire-log.** If `em-side` fires dominate (≥50% of entries) or any `agentId`
fires ≥3 times, surface to PM: _"Tripwire fire-log shows N recurring dispatches — consider
recalibrating `SONNET_MAX_MINUTES` or the dispatch-size ceiling."_

**`jp_step4_triage_dispatch`** (Tier-2, recommendation: `dispatch`; skip only when there's nothing
new). If dispatching: prioritize `[recurring: ≥3]` entries first, dispatch a small executor per
`proposed target`, delete resolved entries (never annotate), commit naming closed entries, and
route a >15-entry backlog through a `/staff-session`-style sweep — consider running that sweep as
a background `Workflow` (you should) so N executors' conclusions stay off your context.

**Write-time discipline:** new queue entries are a single main line — no sub-lines, no
closure-log sections; the pruner strips them.

**Prior-art sidecar scan.** Scan recent `state/plan-sidecars/*.prior-art-check*.md` sidecars for
Conflicts dispositioned `override-and-document`/`update-prior-art`/`both`. A wiki cited ≥3 times
is a revision candidate — surface to PM. Full doctrine: `docs/wiki/prior-art-checker.md` §
"Bidirectional resolution".

**Audience-mismatch cadence gate (not consumes-manifest — runs by hand).** Run
`python3 -m coordinator_core.ops.audience_mismatch_scan --root .` (claude-klabauter). Reads recent
`state/subagent-share/` run-report sidecars' `## Exit interview` → "What did you have to work out
that the brief could have told you?" answers (the channel every dispatched agent already fills,
enforced present-in-sidecar by `test_review_integrator_fill_guard.py`) and clusters near-duplicate
answers across independent dispatches. A cluster of ≥3 sidecars naming the same doctrine-shaped gap
prints a `[audience-mismatch] ...` nudge — treat it as a Step-5-shaped triage item: route it back
to the classification pass named in `coordinator/snippets/em-operating-doctrine.md` § How to
Review What Came Back ("a recurring 'what should the brief have told you?' naming an EM-only
rule is a mis-routing signal") — which rule was missing from the dispatched agent's context, and
does it belong in the always-on file or the EM channel. Silent output → no recurring gap this cadence; nothing to
action.

**Bug-backlog depth.** The `query-records` directive's open P1/P2 count governs this: ≥10 → ask
PM _"Bug backlog has N open P1/P2 items — run /bug-blitz now or defer?"_; otherwise note in
summary; `state/bug-backlog/` absent or empty → skip silently.

**Portability sweep.** Path-portability findings on the week's diff surface to the PM (never
blocking) via Step 8's parallel-code-review gate, which dispatches `code-reviewer-weekly`
(delegating to `code-reviewer.md`'s always-on **Cross-platform portability lens** and
**Path-shape hazard lens** — separator mismatches, foreign-platform paths, and hardcoded
sibling-repo paths bypassing the settings-home registry) against the week's diff against
`origin/main` as a structural part of every weekly gate run — not a standalone hand-run step.

**Initiative-govern sweep.** Surface for each candidate cluster the detector returns: label, item
count, representative items. Prompt: _"Confirmed initiatives to name? Run
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-initiative" create` for new ones, `... attach <artifact-path> <id>` to link existing items."_
No candidates → note the unattached count and continue. **Negative-spec — sole ritual home.** This
sweep MUST NOT be added to `/workday-complete`, `/workstream-start`, or `/workweek-start`; the
detector is read-only, the human authors the cut.

**Cruft-sweep verification.** Staleness >21 days OR dry-run >2 GB reclaimable → one-line note:
_"Cruft-sweep cadence drift — N days since last run, X MB reclaimable. Invoke `/cruft-sweep` to
action."_

**Subagent-share sidecar reap (not consumes-manifest — runs by hand).** Named exception to
`state/`'s never-swept posture — canonical three-clause definition lives at
`coordinator/commands/distill.md § tasks/ vs state/ — aggressive sweep boundary`. Run
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/reap-stale-subagent-sidecars"`.
Non-zero exit → surface the error, do NOT skip. Zero exit with sidecars reaped → include the
`git rm` deletions in the weekly maintenance commit and note the reaped count. Zero exit with
nothing reaped → note "clean (nothing stale)."

**Workstream-complete inline-budget advisory.** `WARN: ... exceeds baseline` → one-line note:
_"workstream-complete inline-budget drift — new mechanism inlined instead of extracted to a
`bin/wsc-*.sh` script."_

**Weekly KR re-assessment (advisory, non-blocking).** `d_step4_counts_goal_krs` reads existing
signal only (completions, handoffs, week-changelog HEADER) — no new instrumentation. That clause
bars *this system standing up instrumentation of its own*; it is a coupling constraint, not a rule
about where signal originates (`docs/problems/2026-07-06-goal-setting-per-repo-okr-legibility-sys.md`
OOS #1: folding the instrumentation build in "would couple the legibility system to an
instrumentation build it doesn't need in order to be useful"). A signal the running repo already
produces for its own reasons is not barred by it; a signal this step would require someone to build
in order to run is. Review the
proposed per-KR statuses and any `*** maybe-not-a-goal — no perceptible movement this week` flags
as EM/PM-confirmation proposals; the live `status` field is never auto-overwritten. No
`state/goals/` directory → skip. **Negative-spec:** this step MUST NOT auto-set `status:` fields.

The step also reads one optional, generalized local source: `state/kr-suggestions/*.yaml`
(`coordinator/schemas/kr-suggestion.schema.json`) — any producer resident in the running repo may
emit a suggested KR-shift, anchored on `key_results[].id` and carrying rationale + provenance
(source record, span, timestamp), for presentation alongside this step's own proposals. This is
existing local signal under the clause above, not new instrumentation the ceremony stands up — no
directory present → skip cleanly, exactly like a missing `state/goals/`. Same posture as every
other proposal here: advisory, EM/PM-confirmed, no auto-apply path at any confidence level, ever.
A suggestion whose `kr_id` doesn't resolve against the target goal is surfaced to the human, never
dropped silently — and so is one whose `goal_id` matches no goal at all, or one that resolves
cleanly onto a goal that has since gone non-active: three distinctly-worded not-presented lines,
never a silent drop.

**Guard-sweep results (advisory eight).** Skill description length, owner-file invariant lint,
enabledPlugins drift, CVE recheck, strategic self-description refresh nudge, competitor-positioning
nudge, the atlas drift walk / arch-audit staleness read, and human-facing doc health never block —
note each finding in the weekly summary and move on. CVE recheck dispatches `dep-cve-auditor`
(Sonnet) only when a tracked manifest changed in the last 14 days — output to
`state/review-findings/<week-starting>-cve/deps.md`. Strategic self-description nudge: if
`state/strategic/self-description.yaml` is stale relative to `git log --since="7 days ago"`,
prompt to run `coordinator:strategic-self-description-refresh`; absent → note that `/repo-setup`
scaffolds a skeleton. Competitor-positioning nudge fires only on an absent-or-empty
`competitors[]` — never re-nudge a repo that already has data, even if the freshness nudge above
separately flags it as stale.

**Human-facing doc health (staleness + content verification).** Advisory, never blocking — but
unlike the other seven advisory rows, each doc with a finding is also gated through a paired
`judgment_points[]` entry (one per doc with findings, not per finding — see
`docs/wiki/human-facing-doc-freshness.md`), requiring an explicit recorded per-doc disposition
before its gated follow-on directive can proceed; no disposition is ever auto-picked. Staleness
findings carry commits-since/days-since/last-touch evidence per doc; content-verification
findings carry the citation and why it failed to resolve. Detector entrypoints:
`claude-klabauter:coordinator/bin/workweek-complete-doc-staleness.py` (staleness) and
`claude-klabauter:coordinator/bin/workweek-complete-doc-verify.py` (content verification), each
with a `.cmd` sibling for Windows.

**Guard-sweep results (hard-blocking three).** UBT pending-record merge, reverse-drift, and
version-consistency/schema-drift — see § Step 0.95's hard-block-set paragraph. On a FAIL: halt
and surface before Step 8; UBT names `sha_range` and the `COORDINATOR_OVERRIDE_UBT_GATE=1`
escape; reverse-drift names `COORDINATOR_OVERRIDE_REVERSE_DRIFT=1`; version-consistency/schema-drift
names the drifted schema and direction (we-ahead/we-behind/both) or `COORDINATOR_OVERRIDE_UBT_GATE`-
class remediation per its own stderr. Non-UE repos no-op silently on the UBT check.

---

## Step 6: scc Snapshot

Not consumes-manifest (`scc` is third-party — see `narration`). If `scc` is available, run
`scc --no-complexity --no-cocomo --no-duplicates --sort code` and record the compact summary
(total lines, top 5 languages) in `state/code-stats-history.md` under a `## YYYY-MM-DD` heading.
Not available → note _"scc not available — install for weekly code stats."_

---

## Step 7: ShellCheck Sweep + Console-Flash + Multi-Event-Hook Guards

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-complete-drift-guards" shellcheck-sweep --repo-root .`. Issues found → report and fix straightforward mechanical
ones, flag behavior-changing items for PM review. Clean → _"ShellCheck: all .sh files clean."_ Not
installed → note.

Then the spawn-suppression guard: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-complete-drift-guards" console-flash-guard --target "$HOME/.claude/plugins"`.
Same report-and-offer shape; route bare spawns through claude-klabauter `coordinator/lib/spawn-hidden.sh`
or add `# verify-no-console-flash: allow`. Clean → _"Console-flash guard: OK"_.

Then the `hookEventName` guard: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-complete-drift-guards" multi-event-hook-guard`. Fix is to echo the stdin payload's
`hook_event_name` rather than a hardcoded literal — see `runtime-tripwire-em-check.py::_hook_event_name`.
Clean → _"Multi-event hookEventName guard: OK"_.

All three always exit 0 and are advisory — none block merge.

---

## Step 8: Illegal-Path Backstop + Parallel Code-Review Gate

`d_step5_7_illegal_path_backstop` scans all tracked and staged paths for NTFS-illegal characters
before the parallel code-review. Non-zero → halt: rename or remove the offending path, re-commit,
then re-run `/workweek-complete`.

`d_step7_6_trail_scope` computes and writes the session-keyed scope shard
(`state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json`). Select the newest
shard whose `<SID_SHORT>` matches this session's own id, falling back to the newest shard overall.

Read `~/.claude/plugins/coordinator/skills/parallel-code-review/SKILL.md` and
execute its steps against the selected shard. The Staff Engineer is NOT in this gate — see Step 9.

- **BLOCKED:** halt before Step 11; surface verdict line + findings-dir path to PM.
- **WARN:** include verdict line in the release-notes draft (Step 13); proceed.
- **OK:** proceed; verdict line goes into the release-notes draft for the record.

**Skip rules** (full detail in skill body): <10 lines or internal-only → skip; doc-only week →
skip code-semantics chunks; plan-only week → skip entirely; `--force` passes through.
**Already-reviewed-span (Rule 5, EM-judgment):** on a large catch-up span already verdicted at
`/workstream-complete` time, the EM may skip the chunk gate (record `incrementally-reviewed`,
naming this week's `state/review-trail/*.json` records as evidence) or narrow it to the
un-reviewed commit subset. Deliberate EM call, not auto-fired.

---

## Step 9: the Staff Engineer Layer-2 — Architecture Pass (advisory, does NOT gate merge)

Skip (note "no arch-tier signal this week") if `arch_tier_candidates` empty AND
`convergent_findings` empty AND seam-file set empty AND the daily strategic-observer trail carries
no `for-weekly-arch-review` flags.

**`jp_step7_5_staff_eng_fire_discretion`** (Tier-2, no fixed recommendation — genuinely EM-discretion).
On a large already-reviewed span (Step 8's Rule 5 condition), the seam-file trigger alone MUST NOT
auto-fire this pass — seam count scales with span size, not architectural risk. Default OFF on
such a span; fire only when cross-workstream drift is genuinely plausible.

Otherwise dispatch the Staff Engineer (`coordinator:staff-eng`, Opus) with: changelog digest,
`arch_tier_candidates`/`convergent_findings` from `$FINDINGS_DIR/synthesis.json`,
`staff_eng_seam_files` from Step 8's scope shard, and the DSR trail. Inputs 2/3 are omitted when
Step 8 took the Rule 5 skip. The Staff Engineer produces candidates only — EM routes them down the disposition
ladder (trivial → immediate executor; mid-size → bundled spinoff candidate; large/structural →
standalone spinoff or `/plan`). Surface alongside the release-notes draft (Step 13).

---

## Step 10: Architecture Audit Fold + Atlas Drift Walk

`d_step4b_4k_arch_audit_staleness` and `d_step4b_4k_atlas_watch_drift` resolve both reads.

**Staleness fold.** `STALE` (>10 days or never targeted-audited) → auto-fold a targeted-on-diff
audit: read `${CLAUDE_PLUGIN_ROOT}/skills/architecture-audit/SKILL.md` scoped to diff-touched
systems. `FRESH` → no fold (EM may still trigger on heavy churn). `UNKNOWN` → note, move on. Never
edits code — packages findings as spinoff candidates. Surface alongside Step 9's candidates.
FRESH-and-no-churn → note "fresh (Last targeted audit within 10d) — no fold."

**Atlas drift walk.** `DRIFT`/`MISSING` → folds into the staleness pass above. `ERROR`/`MALFORMED`
→ helper-script issue for author attention, never treated as FRESH. `STALE` (>30d) → EM-judgment:
ratify current (`atlas-current-as-of:<date>` no-op commit token) or schedule `/architecture-audit`.
Never auto-dispatches a refresh — the surface IS the gate. Note: _"Atlas drift walk: N DRIFT, N
STALE, N ERROR — [folded / surfaced for EM judgment]."_

---

## Step 11: Tracker Reconciliation

Read `docs/project-tracker.md` (if it exists). For each workstream in the week's `Plans touched:
implemented` fields, verify tracker status reflects completion; fix in place. Report: _"Tracker
reconciliation: N workstreams updated."_

---

## Step 12: LoE High-Water Check — MANDATORY Before Step 13

`d_step6_query_completions` resolves the chain-terminal XL query
(`--where "chain_terminal=true" --where "chain_loe.tshirt=XL"`) plus the single-session XL query
(`--where "loe.tshirt=XL AND chain_terminal=true"`, no `chain_loe`) — union both sets.

**`jp_step8_5_loe_high_water`** (Tier-2, no fixed recommendation). For each entry surface `title`,
`chain` slug, `chain_loe.sessions`/`chain_loe.tshirt` (or `loe.tshirt`), date span:

```
**XL chain-terminal entries this week:**
- "<title>" — chain: <chain-slug>, <N sessions>, <date-start> to <date-end> [chain-level XL]
- "<title>" — single-session XL, <date>
```

Zero entries → note explicitly _"No XL chain-terminal entries this week."_ — never silently omit.
No PM gate required; PM may promote an entry to Highlights at Step 13.

---

## Step 13: Editorial Bucketing + Release Notes Draft — PM Review Gate

`mkdir -p state/week-changelog/`. Derive the week-start date from `state/week-changelog/HEADER.md`
(`**Week starting:**` line) and query
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --since "<week-start>" --where "status=pending-release" --format json --limit 1000`. Zero entries →
skip to the empty-week note below.

**Main-membership is not the "already announced" signal.** A returned `pending-release` entry
already on `origin/main` is the catch-up target for this release, not a double-count risk —
`main` routinely runs ahead of the changelog. The double-count check that matters: whether an
entry was already covered in a *prior* release's notes — check `archive/release-notes/`, not
`git log --contains`.

**Detect-only reconcile pass (pre-release backstop).** Before handing the corpus to the editorial
worker, run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-complete-close" reconcile-sweep`. Advisory — does NOT hard-fail on unaccounted commits. Any warning →
fold the missing SHAs via `reconcile-completion-commits.py --append` before dispatching the
editorial worker.

**`jp_step9_editorial_bucketing`** (Tier-2, no fixed recommendation). Dispatch a Sonnet worker with
the entry corpus; it assigns each entry to a bucket and writes
`state/week-changelog/YYYY-MM-DD-pending-release.md`. Default bucket rules (primary key `nature`,
refined by `loe.tshirt`):

| nature | tshirt | Bucket |
|--------|--------|--------|
| roadmap | L, XL | **Highlights** |
| roadmap | S, M | **Notable** |
| roadmap | XS | **Other** |
| bugfix (user-visible) | any | **Notable** |
| bugfix | XL | **Notable** |
| bugfix | S, M, L | **Other** |
| tech-debt / infra | non-XL | **Other** |
| tech-debt / infra | XL | **Notable** (EM call) |

EM override permitted — state explicitly in the dispatch. Empty buckets read `_none this week_`;
long tails (≥5 similar entries, Other only) collapse to "... and assorted fixes". Each entry cites
its source file. Step 8's WARN verdict (or Rule-5 `incrementally-reviewed` + trail-record
evidence) goes verbatim under `_Code-review gate verdict:_`. Verify the file exists and is
non-trivial before proceeding.

Read the pending-release file and write `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md` as a thin
formatting wrapper — do NOT re-author. Version is a placeholder until Step 14 confirms it.

**`jp_step9_pm_release_notes_gate`** (Tier-3, your-call — no recommendation; reason: pm-authority).
Present: _"Release notes drafted at `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md`. Bucketed: N
Highlights, N Notable, N Other. Does this capture the week accurately?"_ **Wait for PM review.**
Update both files to reflect any reclassifications.

---

## Step 14: Version Bump — PM Confirmation Gate

**Consumer convention takes precedence.** If `docs/wiki/versioning-convention.md` exists, it is
the authority for which number/artifact is canonical and how to bump it. The semver heuristic
below is the fallback: **Major** — breaking change in any `Decisions:` field. **Minor** — new
feature/command shipped. **Patch** — fixes, docs, refactors only. Either way, one bump
consolidates the delta since the last user-visible release.

**`jp_step10_semver_judgment`** (Tier-2, no fixed recommendation). Present: _"Proposed: vX.Y.Z
(rationale: [one line]). Confirm or adjust."_ **Wait for PM confirmation.** Update the
release-notes filename and HEADER.md `Prior week released:` to the confirmed version.

**Stamp version surfaces atomically.** In the same commit that stamps the CHANGELOG
`[Unreleased] → [X.Y.Z] — <date>` (Step 13): `coordinator/.claude-plugin/plugin.json` `.version`
and `.claude-plugin/marketplace.json` `.metadata.version` both move to `X.Y.Z`.
`d_step4b_4k_version_consistency` then gates: run
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-version-consistency"`
before Step 16 — non-zero means a surface was missed; fix it before proceeding.

---

## Step 15: Release Publish — Backstop Un-Draft


Catch-all for non-trivial work that reached main via direct daily-branch commits that bypassed
`/merge-to-main`'s per-merge tagged-publish leg. Precondition: PM confirmed the version at Step 14
(`$VERSION_TAG` set, e.g. `v2.7.0`).

Verify via `gh release view "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude --json isDraft,isLatest`:
`isDraft=false, isLatest=true` → already published, note and skip. Draft exists or no release for
the tag → proceed. Tag doesn't exist → create it.

**`jp_step10_5_gh_release_publish`** (Tier-3, your-call — no recommendation; reason:
irreversible-external-action). Un-draft via
`gh release edit "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude --draft=false --latest`, or
create via `gh release create "$VERSION_TAG" --repo dbc-oduffy/coordinator-claude --title "$VERSION_TAG" --notes-file "archive/release-notes/<date>-$VERSION_TAG.md" --latest` using the
Step 13 release-notes file as the body.

**Scope:** coordinator-claude only. Deep-research-claude release publishing is owned by the
deep-research-currency-notification spinoff. **Claude Prime
(`source_is_live`) is never tagged** — skip silently when the active repo is the `~/.claude`
meta-repo. Surface to PM: _"Release $VERSION_TAG published on coordinator-claude (or already
published — no action)."_

---

## Step 16: `/merge-to-main`

Invoke `/merge-to-main` only after PM has confirmed release notes (Step 13) and version
(Step 14). Do NOT inline merge logic — the skill handles the pre-merge test suite, PR creation,
and merge.

---

## Step 17: Health Survey

Run the full health survey if available. Record output in `state/health-ledger.md` under today's
date.

---

## Step 17b: Auto-Memory Drain (blocking gate, no consumes-manifest CLI)

Auto-memory is ephemeral by definition — this ceremony drains it to zero every close. Run:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-auto-memory-drained" --root .
```

Exit 0: nothing under the auto-memory store — skip to Step 18. Exit 1: it prints every residual
`*.md` path (index and/or sibling body files) to stderr. For EACH one, resolve exactly one
disposition — silence is not a disposition:

- **PROMOTE** — write the fact to its durable home (doctrine, wiki, `docs/decisions/`,
  `state/lessons/` via `/learn-lessons`, or the orientation cache — per C1's channel contract) and
  note the target path. This is a real authoring act: most memory rows are private shorthand that
  will not survive a reader who lacks the session, so restate the claim in the destination's own
  voice rather than copying the row verbatim.
- **DROP** — say so explicitly.

Then delete every file the gate named (the gate itself never mutates — it only detects residue)
and re-run the command above to confirm exit 0. Record the full disposition list — path,
PROMOTE/DROP, and target path for each PROMOTE — in Step 19's final summary under **Auto-memory
drain**; the memory dir carries no git history, so this ceremony's own output is the only record
of what was destroyed.

**On the first gate invocation this ceremony exiting 0 immediately (no residue ever printed):**
the store was empty from the start — omit the `**Auto-memory drain:**` line entirely.
**If the gate ever printed residue this run, even once:** the disposition list is mandatory in
the final summary — even though the store is empty by the time you write it. Omitting the line
at that point would erase the only record of what was destroyed.

ZERO MEANS THE DIRECTORY, NOT THE INDEX — a drained `MEMORY.md` with surviving sibling body files
still fails the gate and is not done. This complements the write-time size cap on the auto-memory
store (a spatial bound), not a duplicate of it (a temporal bound); neither supersedes the other.

---

## Step 18: Archive + Reset Week-Changelog

`d_step13_archive_close` resolves the whole archive/reset — moves the daily files + priorities
fragments to `archive/week-changelogs/<week-starting>/`, moves review-trail JSON to
`archive/review-trail/<week-starting>/` (excluding `.gitkeep` and any
`.weekly-reviewer-scopes-*.json` shard, which is deleted, not archived), rewrites `HEADER.md`, and
commits + pushes. Run
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-complete-close" archive --version vX.Y.Z --merge-sha <merge-sha>` (`--no-push` to commit without pushing,
`--no-git` for file moves only). **Archival ordering matters:** must run AFTER Step 8 consumes the
trail.

### Multi-week precondition

The default archive is **unbounded by date** — every dated block goes to the single
`<week-starting>` destination. Correct at a real week boundary; destructive when a week was skipped,
collapsing several weeks into one directory under one week's label.

Before archiving, compare the block dates in `state/week-changelog/` against `**Week starting:**` in
its `HEADER.md`. Dates outside that week mean multi-week — do not use the default path.

**Multi-week: archive one week at a time** via `archive --week-only`, which window-filters the
sweep. Two traps:

1. `--week-only` alone strands the priorities fragments — their sweep is gated on
   `not week_only or move_priorities`. Pair it with `--move-priorities` on the **fragment-owning
   week only**.
2. Out-of-window blocks are left in place, not archived. N weeks need N runs.

`.weekly-reviewer-scopes-*.json` shards are skipped rather than deleted under `--week-only` (a shard
cannot be attributed to a week, so it fails safe) and will accrue.

**Negative spec — the daily matcher `^\d{4}-\d{2}-\d{2}.*\.md$` is broader than daily-block naming,
so `YYYY-MM-DD-pending-release.md` matches it.** That file is Step 13's editorial corpus and the
input both Step 13 and `merging-to-main` read. An unbounded sweep archives it, and the next release
draft finds nothing in the live directory. Check the dated-file list for non-daily entries before
running.

This guard is prose, and prose is a weak discharge. The durable fix is a driver that enumerates the
weeks and runs each scoped pass with fragment-ownership computed rather than remembered — that
belongs to whichever engine provides `workweek-complete-close`, not to this command.

The tail directives close the ceremony:

- `d_step13_5_post_command_hook` — the repo's own opt-in `workweek_complete_post_command:`
  (declared in `coordinator.local.md`), via the shared `coordinator-ceremony-hook.py` helper.
  Advisory, non-blocking — a failing or unconfigured hook never fails the ceremony; a non-zero
  here means the helper itself couldn't be found/exec'd.
- `d_step13_6_emit_cadence` — fires at ceremony completion so the emitted snapshot reflects
  settled state. Best-effort per AC5 — a no-seam machine or transport hiccup is a note, not a
  blocker.

---

## Step 19: Final Summary

**Report by exception.** Four lines always; everything else appears only when it is *not*
clean. A ceremony summary is still an EM→PM reply and still owes the ≤200-word budget from
global `CLAUDE.md § Communication Style` — a fixed block of all-clean status lines spends that
budget on facts the PM can read off the commit, then gets measured as a verbosity violation by
the Stop-hook altitude check. Print what needs a reader, not what needs a checkbox.

```
## Workweek Complete

**Shipped:** N workstreams — one-line characterization (name only the workstreams that fit in that line)
**Version:** vX.Y.Z
**Merged to main:** [yes — PR #N / blocked: reason]
**Next:** run /workweek-start to set priorities for the new week
```

Then append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Validation:**` | failures occurred — describe them (silent when all validation passed) |
| `**ShellCheck:**` | the sweep found/fixed N issues (silent when clean) |
| `**Code-review gate:**` | verdict is BLOCKED or WARN, or findings were fixed — [BLOCKED\|WARN] — convergent: N — code-semantics (N chunks) / security / deps / tests summary (silent when OK/not-run) |
| `**Arch pass (Step 9):**` | N ≥ 1 arch-tier candidates surfaced this week |
| `**Arch audit fold (Step 10):**` | Step 10 folded a stale targeted audit this run |
| `**Improvement queue:**` | K ≥ 1 entries processed |
| `**Bug backlog:**` | N ≥ 1 open P1/P2 items, or `/bug-blitz` was proposed/deferred |
| `**Auto-memory drain:**` | the drain gate printed residue at any point this run — full `path -> PROMOTE(target)/DROP` list, one per line, mandatory even though the store is now empty |
| `**Post-ceremony hook:**` | the tail hook produced output, e.g. "ran `<redacted-cmd>` (exit 0)" |

**Negative-spec — these are gone, do not restore them.** `Week`, `Release notes`, `Docs
updated`, `Code stats`, `Tracker`, and `Week-changelog` are no longer printed at all. Each was a
count, date range, or file path the ceremony's own commit already records: the week span and
commit count are derivable from `git log`; the release-notes path is written by the commit that
drafts it (Step 12); `/update-docs` completion, `scc` output, and tracker-row counts are
recorded by their own commits; the week-changelog archive path is recorded by Step 18's own
commit. None of these carried a PM decision. Their absence is not a signal the step was skipped
— the directives still run, and `git show`/`git log` is their record. A future reader must not
re-add them "for completeness": completeness of the *ceremony* is the assembler's job,
completeness of the *report* is not the same thing.

---

### What This Does NOT Do

- **Auto-fire.** PM-invoked; `/workday-complete` surfaces the staleness signal.
- **Re-author from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 16 delegates to `/merge-to-main`.
- **Delete release notes or handoffs.** Only daily changelog files are archived.
- **Touch trail records via `/distill` or `/update-docs`/handoff-archival.** Trail JSON is
  archived in Step 18 only.

### Relationship to Other Commands

- **`/workday-complete`** — daily wrap; feeds the changelog this command reads.
- **`/workweek-start`** — weekly orient; detects Step 18's HEADER reset and re-inits.
- **`/merge-to-main`** — invoked in Step 16.
- **`/update-docs`** — invoked in Step 4.
- **`check-weekly-staleness.py`** — staleness nudge used by `/workday-complete`.
- **`check-arch-audit-staleness.py`** — reads `Last targeted audit` clock; consumed by Step 10
  (STALE >10 days → auto-fold).
- **`/architecture-audit`** — folded in by Step 10 when stale; writes `Last targeted audit`.
- **`/architecture-survey`** — full breadth survey (PM-invoked only); writes `Last full audit`.

---

## Computed-conversion manifest (C4 census — precedes the C6 rewrite)


This section is preparatory census output for the `workweek_complete` assembler (C5), landed
before the evergreen rewrite above (C6). It records the manifest the assembler orchestrates and
the guard-sweep hard-block/advisory census the rewrite's § Step 0.95/Step 5 render against.

### Consumes-manifest

Every existing coordinator_core capability / atomic CLI the `workweek_complete` assembler
orchestrates — C5 imports these, none get reimplemented:

`list-week-changelog`, `backfill-week-changelog-gaps`, `coordinator-resolve-validation-cmd`,
`lint-frontmatter`, `workweek-complete-advisories`, `query-records`,
`detect-initiative-candidates`, `coordinator-initiative`, `cruft-sweep`,
`check-wsc-inline-budget`, `reassess-goal-krs`, `workweek-complete-drift-guards`,
`workweek-complete-reverse-drift-gate`, `check-competitor-positioning-nudge`,
`check-no-illegal-paths`, `workweek-trail-scope`, `check-arch-audit-staleness`,
`check-atlas-watch-drift`, `query-completions`, `workweek-complete-close`,
`check-version-consistency`, `coordinator-ceremony-hook`, `emit-cadence`, `scc`, `node run.js`,
`gh release`.

Contract↔emission test (skeleton, red until C5 lands) is authored in claude-klabauter —
`coordinator_core/tests/test_workweek_complete_contract.py` — out of this repo's write scope; not
delivered by this section.

### Step 4b–4k guard-sweep census

Steps 4b–4k are ten lettered advisory/drift gates that collapse to ONE "guard sweep" MECHANICAL
block returning a JSON verdict array. Hard-blocking vs advisory granularity, confirmed against
current step bodies:

| Step | Gate | Disposition |
|------|------|--------------|
| 4b | Install OOM reproducer freshness | Advisory (blocking only in the narrow sub-case where the reproducer itself runs and fails) |
| 4c | UBT pending-record merge gate | **Hard-blocking** |
| 4d | Skill description-length | Advisory |
| 4e | Owner-file invariant lint | Advisory |
| 4f | enabledPlugins drift audit | Advisory |
| 4g | Reverse-drift merge gate | **Hard-blocking** |
| 4h | CVE recheck (change-aware) | Advisory |
| 4i | Strategic self-description refresh nudge | Advisory |
| 4j | Competitive positioning nudge | Advisory |
| 4k | Vendored-schema drift gate | **Hard-blocking** |
| — (new, no 4b–4k letter) | Human-facing doc health (staleness + content verification — doctrine: `docs/wiki/human-facing-doc-freshness.md`) | Advisory — non-blocking, but paired with a per-doc `judgment_points[]` entry requiring an explicit recorded disposition (never auto-resolved) |

The rewritten (C6) body preserves this granularity — the assembler returns one verdict array, and
the three hard-blocking rows (4c, 4g, 4k) still halt the ceremony while the eight advisory rows
never do (the seven original 4b–4k advisory rows plus the human-facing doc-health row — no new
class, no binary-split rewrite). **C6 note:**
the assembler's own emitted `hard_block` field does not currently mark the 4c/UBT directive `true`
(a gap surfaced during C6, not corrected here — see § Step 0.95) — the rewrite's guidance follows
this table, not the field, until that's fixed upstream in claude-klabauter.

### Axis-3 consolidation disposition (the Staff Engineer F6)

A survey of consolidation candidates for the cluster rebuild, enumerated by baton
(B7/B8/B9/B10), named none of `workweek-complete` or its surfaces. The B1 cluster row itself already directs the two
consolidations that touch this file — share the cadence session-state resolver (backend-dedup,
C5) and fold `/autonomous`'s sentinel toggle into a shared assembler verb (C7) — both already
assigned to their respective chunks. **Disposition: keep-with-reason** — no further merge/fold
candidate found naming this surface beyond what the B1 row and C5/C7 already carry.

### Shared-tail resolution (the Staff Engineer F2, AC9)

C4's preliminary characterization found the Step 13.5/13.6 tail NOT byte-identical to
`workday-complete.md`'s Step 10.5/10.6 tail (differing invocation shape, a `--only-mode` skip with
no workweek analog, differing exit-code granularity). C5's own AC9 identity check, run once both
real shapes existed, reached the opposite conclusion once workweek's `hard_block` bookkeeping (a
uniform post-build pass applied to every directive, tail included) was excluded from the
comparison — every load-bearing field (both CLIs, empty args, `depends_on=None`) matched. Both
assemblers now consume the shared `coordinator_core.ceremony_common.tail.build_ceremony_close_tail`.
This section's earlier "not byte-identical" verdict is superseded by C5's own finding, not a
contradiction to resolve — C4 measured a partial input, C5 measured both complete shapes.
