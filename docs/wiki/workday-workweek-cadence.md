# Workday / Workweek Cadence

> Spec backlink: `archive/specs/` — cadence doctrine distilled from CLAUDE.md § Workday/Workweek Cadence
> and `/workday-complete` + `/workweek-complete` command bodies.

---

## Overview

Daily and weekly are distinct ceremonies, both PM-invoked, staleness-nudged.
**Handoffs are the atom; the week-changelog is the index over them.**
`/workday-complete` synthesises from existing handoffs and the Step 4 daily summary — does not re-author.
`/workweek-complete` reads the index as ground truth, does not reconstruct from `git log`.

---

## Daily ceremony — `/workday-complete`

Sequential steps (each must complete before the next begins):

| Step | Name | Gate | Notes |
|------|------|------|-------|
| 1 | `/validate` (+ UBT preamble) | blocking | UBT preamble: non-UE repos see silent skip |
| 2 | RAG Staleness Nudge | informational | skip if no RAG-index MCP tool is present |
| 3 | Branch Consolidation | blocking on conflict | see conditional-skip note below |
| 4 | Strategic Daily Review | — | writes `archive/daily-summaries/YYYY-MM-DD.md` |
| 5 | Plugin Validation Suite | blocking on hook failures | non-hook failures: report and flag |
| 6 | Completed Archive Audit | — | |
| 7 | Tier Usage Report | — | |
| 8 | Improvement-Queue Depth Nudge | informational | depth ≥5 → notice only; no triage |
| 9 | Append to Week-Changelog | — | commits daily summary + changelog row |
| 10 | Weekly Staleness Check | informational | |
| 11 | Final Summary | — | |

### Step 3 conditional-skip (first conditional in the daily sequence)

Step 3 (branch consolidation) is the only daily step that may legitimately short-circuit: if HEAD already contains `origin/main` (ahead-only state), the rebase sub-step skips with a "no rebase needed" log. This is an EM-judgment skip, not a blocking gate.

The skip fires when `git rev-list --count HEAD..origin/main` is `0` — meaning every commit on `origin/main` is already an ancestor of HEAD. In this state, `git rebase origin/main` would walk back through merge commits and replay them needlessly. The guard avoids that wasted work.

A missing-ref guard precedes the skip: if `origin/main` is not present locally (fresh clone, network issue, renamed remote), the reconcile sub-step logs an informational skip rather than producing an opaque rebase failure.

Step 3 sub-step 0 (`sync-main.py`) MUST run before the rebase/skip check — it fetches `origin/main`, ensuring the rev-list count is computed against a fresh ref.

### Week-changelog `Validation:` schema

The changelog block records:
```
Validation: validate=<exit-code-step-1> plugin-suite=<exit-code-step-5>
```

Both fields are auto-filled from ceremony exit codes; neither is LLM-authored prose. On non-UE repos, the Step 1 UBT preamble is a no-op (script absent), so `validate=` reflects the exit code of the resolved command — the three-step resolver checks `$COORDINATOR_FAST_TEST_CMD` (env var), then `fast_test_cmd:` in `coordinator.local.md`, then skips with notice if neither is configured. The `plugin-suite=` field is present even on non-UE repos (reflects Step 5 node test exit code).

`validate=` enum values:
- `validate=<exit-code>` — the resolved command ran; value is its exit code (e.g. `validate=0`).
- `validate=skipped` — the resolver found no command configured: `$COORDINATOR_FAST_TEST_CMD` was unset and `coordinator.local.md` had no `fast_test_cmd:` key. No test ran. Remediation: set `fast_test_cmd:` in `coordinator.local.md` or export `$COORDINATOR_FAST_TEST_CMD`.
- `validate=not-run` — Step 1 never emitted `RC_VALIDATE` at all: the ceremony did not reach validation (aborted early, Step 9 invoked out-of-band, or a backfill composed without a Step 1 leg). This is the **unset default** and is a ceremony gap, not a configuration state. Distinct from `skipped`, which is a positive emission meaning validation ran and found nothing configured. Do not conflate the two — that collision is what this value exists to break.
- `validate=N/A` — the step was explicitly skipped with PM authorization. Different cause from `skipped`: an authorized skip is a deliberate product call; a `skipped` result is a missing configuration that should be remediated.

**Read-back surface.** `validate=<rc>` above is written into the changelog and, for a time,
had no reader — a red exit code landed in a file nothing consumed. That gap is
closed by a separate, richer record: `state/test-red/<machine>.yaml`, schema at
`coordinator/docs/wiki/test-red-state-schema.md`. That record carries a fingerprinted failing
set (not just an exit code) and a delta vocabulary (`new`/`cleared`/`persistent`) computed
against an acknowledged baseline or the prior run. Two ceremonies consume it: `/workday-start`
(surfaces only on a non-empty delta) and `/workstream-start` (item 6's red predicate advocates
`/bug-blitz` on the same delta). This `Validation:` field and the test-red record are
independent artifacts — this field's own semantics and enum are unchanged by the test-red
record's existence.

---

## Post-ceremony command hook

> Helper: the engine-resident `coordinator/bin/coordinator-ceremony-hook.py`

Any of the four cadence ceremonies (`/workday-start`, `/workday-complete`, `/workweek-start`,
`/workweek-complete`) can run a consumer-repo-declared command at its terminal step, via one
shared generic helper — the engine-resident `coordinator-ceremony-hook.py <canonical-ceremony-name>`. This is the
seam a repo uses to, for example, publish its settled end-of-day state somewhere, without a
bespoke terminal step per ceremony. One helper, called by all four, keeps the four near-identical
bodies from drifting (the parallel-surface footgun).

### Key convention

The helper takes the canonical dashed ceremony name as its sole argument, maps dashes to
underscores, and appends `_post_command` to derive the `coordinator.local.md` frontmatter key it
reads:

| Ceremony | `coordinator.local.md` key |
| --- | --- |
| `/workday-start` | `workday_start_post_command:` |
| `/workday-complete` | `workday_complete_post_command:` |
| `/workweek-start` | `workweek_start_post_command:` |
| `/workweek-complete` | `workweek_complete_post_command:` |

This is the same config surface `fast_test_cmd:` already uses (see § Week-changelog
`Validation:` schema above) — a flat top-level key in the repo's own `coordinator.local.md`.

### Semantics

- **Opt-in.** Key absent or empty → silent no-op: no output, exit 0. The common case; zero
  ceremony noise for repos that declare nothing.
- **Non-fatal / advisory.** The command runs; on non-zero exit the helper emits a `WARN` to
  stderr and still returns 0. A failing hook never fails or blocks the ceremony — the single
  most important invariant of this seam, mirroring the existing `|| echo WARN`-guarded advisory
  steps already present in `/workday-complete` (e.g. cruft-sweep, reconcile, bug-prune).
- **POST / terminal position only.** The hook runs after the ceremony has settled — after Weekly
  Staleness / before Final Summary on `/workday-complete`, after Write Orientation Cache on
  `/workday-start`, before the chain into `/workday-start` on `/workweek-start`, and after Reset
  Week-Changelog / before Final Summary on `/workweek-complete`. There is no PRE-ceremony hook in
  this design.
  <!-- Review: code-reviewer (F2) — clarified execution-vs-rendering timing below for workweek-start,
       where the two "after"s were previously conflated. -->
  **`/workweek-start` execution-vs-rendering split:** the hook *executes* in Step 6.5, before the
  Step 7 chain into `/workday-start` — but its captured `$_HOOK_OUT` line does not *render* until
  the final combined summary, which prints only after the chained `/workday-start` briefing has
  already completed and shown. Do not expect the hook's one-line summary to appear immediately
  after Step 6.5; it appears last, as a trailing line on the combined output.
- **Runs in the repo root**, resolved via `git rev-parse --show-toplevel` (falls back to `cwd`).
  One command per ceremony; a repo needing multiple actions wraps them in its own script.
- **Skipped under `/workday-complete --only`** — a targeted past-date backfill is not a live
  end-of-day settle, so the hook does not run in that mode.

**Output contract.** On stdout, exactly one line when a command was configured and run:

```
Post-<ceremony> hook: ran <redacted-cmd> (exit N)
```

Empty stdout when no command is configured. The calling ceremony's final-summary step emits this
line only when non-empty; all human-readable detail (the command's own stdout/stderr, WARN lines)
streams to stderr, uncaptured.

### Security note

The command is sourced **only** from committed repo config (`coordinator.local.md`) — the repo
owner's own declared command, run with full agent-shell privileges. This is not a shared-branch
injection surface; `coordinator.local.md` is repo-owner-authored config, not an inbound artifact
from an untrusted sender (e.g. a memo or handoff). Unlike `fast_test_cmd`, there is deliberately
**no env-var override** — a per-repo ceremony command has no legitimate env-var source, and an
override would be a subprocess-injectable surface. The helper reuses the same discipline
`fast_test_cmd` resolution already applies:

- `_cs_metachar_warn` flags shell-metacharacter risk on the resolved command before it runs.
- `_cs_redact_for_diag` redacts the command in the summary line and any WARN — a command
  containing a secret (token in a URL, `--password=…`) is never echoed raw.

### Worked example

```yaml
# coordinator.local.md (consumer repo frontmatter)
workday_complete_post_command: "./scripts/publish-state.sh"
```

With this key set, `/workday-complete`'s terminal step runs `./scripts/publish-state.sh` in the repo
root after the ceremony has settled, and the Final Summary includes a line like:

```
Post-workday-complete hook: ran ./scripts/publish-state.sh (exit 0)
```

If the key is absent (the default for most repos), nothing runs and nothing prints.

---

## Weekly ceremony — `/workweek-complete`

PM-invoked, release-grade. Reads the week-changelog as the canonical record — does NOT reconstruct from `git log`. Heavy steps absent from daily live here: `/update-docs`, ShellCheck, improvement-queue triage, skill-description advisory, scc, version bump, merge.

Staleness signal: `check-weekly-staleness.py` (≥5 days AND ≥15 commits since last weekly-reset SHA).

Improvement-queue triage: daily emits depth nudge only (≥5 → notice); weekly triggers action (apply, dispatch executors, delete resolved entries; commit subject names them).

### Step 4d: Skill description length advisory

`check-description-length.py` runs here as **advisory only** — it can never block the ceremony or propagate a non-zero exit. The validator's stdout and rc are captured into the weekly summary via the `set +e` / `_DESC_RC` / `set -e` pattern. A non-zero rc that produces no findings output indicates a script crash — investigate out-of-band. Skills flagged over-budget are follow-up nudges, not blockers.

**Scope caveat — this step does not cover coordinator.** The validator scans the Claude Code meta-repo's plugin-install tree, and coordinator's plugin source resolves live from its doctrine-authoring source tree via `--plugin-dir`, so no coordinator skill appears in its output. Its findings concern whichever other plugins are genuinely installed there. Coordinator's own description budget is bound in the pytest tier by `coordinator/tests/test_boot_description_envelope.py`, which covers agents, skills, and commands; a clean run of this weekly step says nothing about that budget either way.

---

## Weekly ceremony — `/workweek-start`

PM-facing weekly bookend, chains into `/workday-start` at its own close (the week's first session
is also a workday). Bootstraps the week-changelog header on a fresh project.

### `state/week-changelog/` directory conventions

`state/week-changelog/` holds the current week's changelog state. `HEADER.md` is written by
`/workweek-complete` on reset and by `/workweek-start` on re-run — it is the only shared file in
the directory. All other files are per-machine daily blocks (`YYYY-MM-DD-{hostname}.md`) written
by `/workday-complete`, which avoids concurrent-write conflicts.

Priorities are NOT stored inline in HEADER.md. Each `/workweek-start` writer owns its own fragment
file, `HEADER.priorities.<SID_SHORT>.md`, so a second collaborator's `/workweek-start` never
silently overwrites the first's priorities in the same week. Readers merge all fragments on read.

On `/workweek-complete`, the full directory (daily files + fragments + old HEADER) is archived to
`archive/week-changelogs/<week-start>/` before HEADER is rewritten and fragments are cleared.
`check-weekly-staleness.py` reads `HEADER.md` to compute the staleness signal.

### Why the digest/staleness steps are engine-gapped, not hand-derived

`/workweek-start`'s prior-week digest (implemented plans, blockers carried over, priorities met
vs. missed), stalled-workstream detection, and scheduled-recheck surfacing were previously EM
procedures — glob the changelog directory, read every daily file, run `git log --since` per
tracker branch, cross-reference by hand. All three are engine-knowable facts with no producer yet.
The 2026-08-14 corpus-wide grind cut the hand-derivation procedure rather than waiting on the
emission: an EM re-deriving the same digest from raw files every week, forever, is strictly more
expensive than a few weeks of degraded bookkeeping until `orient-assemble` grows a `--cadence week`
digest. See `coordinator/commands/workweek-start.md`'s `<!-- engine-gap: -->` markers for the
specific fields owed.

---

## Relationship Between the Two Ceremonies

## /workweek-complete reads changelog as ground truth — HEADER + daily entries are hard preconditions

`/workweek-complete` reads the week-changelog as ground truth — a missing `HEADER` or absent daily entries for days-with-commits is a precondition failure, not a thing to read past. Backfill before the ceremony; never reconstruct silently inside the skill body. Apply: before invoking `/workweek-complete`, verify `state/week-changelog/current.md` has a `HEADER` section and at least one daily entry per day that had commits.

- `/workday-complete` is a branch wrap, not a release ceremony.
- `/workweek-complete` is the release ceremony; it reads what the daily ceremony wrote.
- Neither ceremony merges to main directly — `/workday-complete` never merges; `/workweek-complete` delegates to `/merge-to-main`.
- ShellCheck, scc, improvement-queue triage, and the skill-description lint are weekly-only; they do not belong in the daily wrap.
