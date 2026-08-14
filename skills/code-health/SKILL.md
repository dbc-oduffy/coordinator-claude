---
name: code-health
description: "Night-shift code review — dispatch reviewer, apply findings, track."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: (no arguments needed)
---

# Code Health — Night Shift Commit Review

The "night shift colleague." Queries today's completion entries to identify surfaces that saw
recorded work, dispatches a Sonnet reviewer with `--problems-only`, applies findings inline,
defers complex findings to the debt backlog, updates the health ledger, writes a morning-ready
summary. Results wait at the next workstream-start.

**Announce at start:** "I'm using /code-health to review recent commits."

**Run on every committed day, regardless of commit count.** A small commit count is exactly when
a review gets skipped and is exactly where the adjacent-path regression hides — the cost-benefit
is asymmetric. The only valid skip: zero completion entries today AND zero fallback commits (see
Failure Modes).

## Step 1: Identify Surfaces

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --where "created=<YYYY-MM-DD>" --format json
```

Extract file paths / subsystem names from `title`, `description`, `files`. No entries for today:
read `state/health-ledger.md`'s `Last daily check:` date, fall back to
`git log --since="<last-check-date>" --oneline --stat`, update the timestamp, report the fallback,
continue with the commit-based scope.

## Step 2: Diff Scope

`git diff HEAD -- <file1> <file2> ...` over Step 1's surfaces (a directory prefix if Step 1
yielded a subsystem name; `git diff <last-check-commit>..HEAD` on the fallback path). Summarize
which files/systems changed — this drives the reviewer's vocabulary/emphasis in Step 3, not
reviewer selection.

## Step 3: Dispatch the Reviewer

Always the Sonnet `coordinator:code-reviewer`, never a persona — personas are Opus-only, reserved
for the weekly arch pass and explicit architectural decisions; a finding that genuinely needs one
gets flagged for `/workweek-complete` Step 7.5, not escalated here. Tell it what to weight by
dominant change type (UE idioms / component-token-reuse-accessibility / numeric-correctness /
coupling-and-interface-seams) — vocabulary only, never identity.

Dispatch unattended: `coordinator:code-reviewer`, UNNAMED, `run_in_background: true`,
`--problems-only`. Its sidecar is spawn-provisioned (arrives as `sidecar_path:` in its brief) — no
EM pre-scaffold. Read the returned `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings:
<N>` and pass the path to Step 4.

## Step 4: Apply Findings

Dispatch `coordinator:review-integrator` on the on-disk sidecar path (never inline-relayed
findings) plus affected file paths. It applies inline fixes and annotations. Findings needing 3+
interacting files or new abstractions go to Step 5 instead. No findings: skip to Step 6.

## Step 5: Debt Backlog

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-queue-append" --schema debt-backlog
```

One YAML file per finding under `state/debt-backlog/`. Required: `title`, `body` (block scalar:
observation, structural gap, context), `source: daily-health/code-reviewer/{date}`, `risk`,
`proposed_action`, `status: open`, `created`. Stage each: `git add state/debt-backlog/<date>-<slug>.yaml`.

## Step 6: Health Ledger

Create `state/health-ledger.md` from template if absent (header `Last daily check:`/`Last full
audit:`/`Next rotation target:`, then a `## System Index` table: System | Grade | Status | Last
Audited | Open P0/P1/P2 | Lines | Notes). Update `Last daily check` to today. If findings changed
a grade, update that row; a system touched but rowless gets grade `?`.

The health ledger is the single source of truth for grades — `/architecture-audit` also writes
here after weekly audits. Read the existing grade before changing it; don't downgrade a
just-upgraded system absent new P0/P1s.

<!-- engine-gap: field=health_ledger.grade_from_findings producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
Grading anchors, status-trigger definitions, and the reviewer-emphasis-by-change-type mapping
this step and Step 3 apply by eye have no engine producer yet — apply the calibration in the
wiki page for this skill until one lands.

## Step 7: Health Summary

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type health-status --title "Health Summary"
```

Via Edit, fill `health:` (`HEALTHY|WATCH|ACTION|CRITICAL`), `summary:` (one-line), and body
sections `## Systems Graded`, `## Findings Summary`, `## Action Items for Next Session`. Worked
example: wiki.

## Step 8: Commit

```bash
git add state/health-ledger.md "state/health/<YYYY-MM-DD>-health-summary.md"
git commit -m "daily-code-health: review of surfaces from completion entries [date]"
```

Nothing else this run touched. Post-commit hook pushes automatically.

## Failure Modes

| Situation | Action |
|---|---|
| No health ledger on first run | Create from template, use last 24h as scope |
| No completion entries for today | Fall back to `git log --since=<last-check>` scope; report fallback |
| `query-completions` not found | Fall back to git-log scope; note missing binary |
| No new commits since last check (fallback path) | Update timestamp, report, exit — no dispatch |
| Reviewer returns no findings | Skip Steps 4-5, go to Step 6 |
| Debt backlog doesn't exist | Create from template first |
| Complex finding can't be fixed inline | Debt backlog, with severity and effort estimate |
| Git commands fail (no commits, detached HEAD) | Report the error and stop |
| review-integrator unavailable | Log findings into the health summary body manually, note as deferred |

## Cost

1 Sonnet `code-reviewer` dispatch (`--problems-only`) + 1 `review-integrator` dispatch if findings
exist. No persona, no Opus at this cadence.

## Relationship to Other Commands

`/workday-complete` is the primary trigger — let it invoke this rather than running standalone.
`/workstream-start`'s cockpit snapshot and record queries surface `state/health/*.md` at the top
of the next session (nested path, not the stale flat `state/health-summary.md`). `/review-code`'s
full feature-review workflow is a different tool — this dispatches `--problems-only` directly.
`pipelines/daily-code-health/PIPELINE.md` is the pipeline definition this command executes.
