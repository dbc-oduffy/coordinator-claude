---
description: Weekly release ceremony — validate, update docs, cut release notes, version bump, merge to main, archive
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: ""
---

# Workweek Complete — Weekly Release Ceremony

PM-invoked, release-grade close. Reads the week-changelog as the canonical record of what shipped — does NOT reconstruct the week from `git log`. Heavy steps dropped from `/workday-complete` live here: `/update-docs`, ShellCheck, improvement-queue triage, scc, version bump, and merge.

**Design contract:** the week-changelog is the ledger. The weekly ceremony reads it, validates against it, and archives it. Release notes are drafted from it, not re-derived.

---

## Step 1: Read Week-Changelog — PM Confirmation Gate

Glob `tasks/week-changelog/*.md` (daily files, sorted by filename). Read HEADER.md and all daily files.

Surface to PM:

```
Week covers: D days (YYYY-MM-DD to YYYY-MM-DD)
Commits: N (range: <oldest-sha>..<newest-sha>)
Shipped workstreams: <list from Plans touched: shipped fields>
Blockers: <list or "none">
Priorities met: <from HEADER.md priorities vs. shipped plans>
```

Ask: _"Does this summary match your recollection? Proceed with release ceremony?"_

**Wait for PM confirmation before continuing.** This is the single explicit PM gate before the irreversible steps.

---

## Step 2: Full Validation (blocking)

Run the complete validation stack:

```bash
python .github/scripts/run-all-checks.py
node --test ~/.claude/tests/plugins/run.js
```

Any blocking failure → stop and report. Fix before proceeding. Do not proceed to Step 3 on a failing validation.

---

## Step 3: Run `/update-docs`

Full multi-phase docs sweep. Commits and pushes to the current branch.

Wait for completion before proceeding.

---

## Step 4: Improvement-Queue Triage

Read `~/.claude/tasks/coordinator-improvement-queue.md`. For each `- ` entry in `## Active queue`,
parse the following fields:
- **Main line:** `- YYYY-MM-DD | <source-repo> | <source-file>:<line> | <summary> | proposed target: <target>`
- **`recurring:` field** (sub-line, indented two spaces): integer count of recurrence increments.
- **`resolution:` field** (sub-line, indented two spaces): one of `pending`, `in_progress`, `resolved <date> <commit>`.

Note the oldest entry date and total active count.

**Triage triggers (any condition):**
- ≥ 5 active entries, OR
- Oldest entry is > 14 days ago, OR
- Any entry has `recurring: ≥3` AND `resolution: pending` (recurring-without-action threshold).

If triggered:
1. Read the queue entries.
2. **Prioritize recurring-without-action items first** (any with `recurring: ≥3` and `resolution: pending`).
3. For each prioritized entry, dispatch a small executor per the `proposed target` field.
4. Verify applied entries; delete the resolved entries from the queue.
5. Commit subject names each closed entry (`workweek triage: closed <id-or-summary>, <id-or-summary>`).
6. If > 15 total entries to triage, treat as a `/staff-session`-style multi-executor sweep.

If not triggered: note in summary — _"Improvement queue: K entries, oldest YYYY-MM-DD — no triage needed."_

**Parser tolerance (the Staff Engineer F15):** The parser MUST treat absent `recurring:` as `0` and absent `resolution:` as `pending`. This handles both pre-migration entries (when the migration was skipped due to absent PM gate) AND new entries appended without the sub-lines (defensive). The triage threshold "`recurring: ≥3 AND resolution: pending`" applies to entries with explicit values; entries without sub-lines effectively count as `recurring: 0, resolution: pending` and never trigger the threshold. This is correct semantics — entries the migration didn't touch shouldn't trigger triage on their own.

**Write-time discipline (the Staff Engineer F6):** When appending a NEW entry to either queue (central or per-project), ALWAYS write three lines: the main entry, then `  recurring: 0`, then `  resolution: pending` (two-space indent). This applies to both `~/.claude/tasks/coordinator-improvement-queue.md` and per-project `tasks/improvement-queue.md`.

**Prior-art sidecar scan (judgment-based):** While reading the improvement queue, also scan recent `docs/plans/**/*.prior-art-check*.md` sidecars for Conflicts dispositioned as "override." Any wiki cited ≥3 times in override dispositions is a candidate for revision — surface to PM. Full doctrine: `docs/wiki/prior-art-checker.md` § "False-positive arbitration."

**Bug-backlog depth check:** Read `tasks/bug-backlog.md` if it exists. Count open items in P1 and P2 tables (exclude the `## Resolved` section and any resolved/closed rows). If the open count is ≥10, propose running `/bug-blitz` as part of this triage session — surface the count and ask PM: _"Bug backlog has N open P1/P2 items — run /bug-blitz now or defer?"_ If not triggered: note in summary — _"Bug backlog: N open P1/P2 items — no blitz needed."_ If the file is absent: skip silently.

---

## Step 4b: Install OOM Reproducer Freshness Check

If `bin/check-install-reproducer-fresh.sh` exists in the repo root:

```bash
bash bin/check-install-reproducer-fresh.sh
```

- **Exit 0 (marker fresh, < 24h):** Print notice; no test run; proceed to Step 5.
- **Exit 0 (test ran and passed):** Print pass notice; proceed to Step 5.
- **Exit 1 (test failed):** Halt and report. Do NOT proceed to Step 5 (scc), Step 6 (ShellCheck), or beyond until either the OOM reproducer passes or PM grants `--force` bypass.

This check is informational when the marker is fresh; it is a **blocking gate** only when the test is actually run and fails.

---

## Step 5: scc Snapshot

If `scc` is available (`which scc` or `~/bin/scc`):
```bash
scc --no-complexity --no-cocomo --no-duplicates --sort code
```

Record the compact summary (total lines, top 5 languages) in `tasks/code-stats-history.md` under a `## YYYY-MM-DD` heading (append; create the file if it doesn't exist). Weekly trend is the signal; daily delta is noise.

If `scc` is not installed: note in summary — _"scc not available — install for weekly code stats."_

---

## Step 6: ShellCheck Sweep

```bash
git ls-files '*.sh' | while read -r f; do
  tr -d '\r' < "$f" | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|$f:|g"
done
```

- **Issues found:** report and offer to fix. Most findings are quick mechanical fixes; fix what's straightforward, flag behavior-changing items for PM review.
- **Clean:** report _"ShellCheck: all .sh files clean."_
- **Not installed:** note in summary.

---

## Step 7: Parallel Code-Review Gate

### Step 7 prelude — trail-reading and scope computation

Before invoking `parallel-code-review`, compute the Staff Engineer's narrowed scope from the session-end review trail. The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) ALWAYS see the full week diff — only the Staff Engineer's lens narrows.

```bash
# Review: the Staff Engineer — WEEK_START parsing must be fail-loud; date -d is GNU-specific and
# the old silent fallback to today violated the detect-then-silently-pick footgun rule.
HEADER_FILE="tasks/week-changelog/HEADER.md"
if [[ ! -f "$HEADER_FILE" ]]; then
  echo "ERROR: $HEADER_FILE not found — run /workweek-start to initialise." >&2
  exit 1
fi
WEEK_START=$(grep -E '^\*\*Week starting:\*\*' "$HEADER_FILE" | sed -E 's/^\*\*Week starting:\*\* +([0-9]{4}-[0-9]{2}-[0-9]{2}).*/\1/' | head -1)
if [[ -z "$WEEK_START" || ! "$WEEK_START" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: cannot parse 'Week starting:' YYYY-MM-DD from $HEADER_FILE" >&2
  exit 1
fi
TODAY=$(date -u +%Y-%m-%d)
export WEEK_START TODAY

# 1. Glob all trail records; filter by date-prefix in the Python block below.
# (find -newermt requires GNU date arithmetic; filename-prefix comparison is portable.)
TRAIL_FILES=$(find tasks/review-trail -maxdepth 1 -name "*.json" -type f 2>/dev/null | sort)
export TRAIL_FILES

# 2-7. Compute scope in Python: set subtraction, cross-segment seam detection,
#      and JSON output — all fail-loud on any subprocess error.
# Review: the Staff Engineer — pseudocode steps 4-6 replaced with runnable Python block that
# performs real set subtraction and pairwise seam intersection, then writes the
# actual scope JSON (previously emitted literal placeholder "<patrik_scope_sha_list>").
python3 - <<'PYEOF'
import json, os, subprocess, sys

week_start = os.environ.get("WEEK_START", "")
today      = os.environ.get("TODAY", "")
trail_env  = os.environ.get("TRAIL_FILES", "")

if not week_start or not today:
    print("ERROR: WEEK_START and TODAY must be set before invoking this block", file=sys.stderr)
    sys.exit(1)

# ---- (a) Load trail records for this week (filename-prefix range filter) ------
trail_files = [f.strip() for f in trail_env.split("\n") if f.strip() and f.strip().endswith(".json")]
# Keep only files whose date prefix falls within [WEEK_START, TODAY] (inclusive).
week_records = []
for f in trail_files:
    basename = os.path.basename(f)
    date_prefix = basename[:10]  # "YYYY-MM-DD"
    if week_start <= date_prefix <= today:
        try:
            with open(f) as fh:
                rec = json.load(fh)
            week_records.append(rec)
        except Exception as e:
            print(f"ERROR: could not parse trail record {f}: {e}", file=sys.stderr)
            sys.exit(1)

# ---- (b) Expand each trail record to its SHA list and file-touch set -----------
def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if result.returncode != 0:
        print(f"ERROR: command failed: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()

segment_shas   = []   # list of sets, one per segment
segment_files  = []   # list of sets, one per segment

for rec in week_records:
    sha_range = rec.get("sha_range", "")
    if not sha_range or ".." not in sha_range:
        print(f"ERROR: trail record has invalid sha_range: {sha_range!r}", file=sys.stderr)
        sys.exit(1)
    shas_out   = run(["git", "rev-list", sha_range])
    files_out  = run(["git", "diff", "--name-only", sha_range])
    shas_set   = set(shas_out.splitlines()) if shas_out else set()
    files_set  = set(files_out.splitlines()) if files_out else set()
    segment_shas.append(shas_set)
    segment_files.append(files_set)

# ---- (c) reviewed_set = union of all segment SHA sets -------------------------
reviewed_set = set()
for s in segment_shas:
    reviewed_set |= s

# ---- (d) weekly_diff_shas = commits on HEAD not yet on origin/main ------------
weekly_raw = run(["git", "log", "origin/main..HEAD", "--format=%H"])
weekly_diff_shas = set(weekly_raw.splitlines()) if weekly_raw else set()

# ---- (e) unreviewed_set = weekly_diff_shas - reviewed_set ---------------------
unreviewed_set = weekly_diff_shas - reviewed_set

# ---- (f) cross_segment_seams = files touched by ≥2 distinct segments ----------
cross_segment_seams = set()
for i in range(len(segment_files)):
    for j in range(i + 1, len(segment_files)):
        cross_segment_seams |= segment_files[i] & segment_files[j]

# ---- (g) patrik_scope = unreviewed_set ∪ seam SHAs (deduped list) -------------
# For file seams we include the SHAs from any segment that touched those files.
seam_shas = set()
for k, fset in enumerate(segment_files):
    if fset & cross_segment_seams:
        seam_shas |= segment_shas[k]

patrik_shas  = sorted(unreviewed_set | seam_shas)
seam_files   = sorted(cross_segment_seams)

# ---- (h) Write the scope file --------------------------------------------------
scope_path = "tasks/review-trail/.weekly-reviewer-scopes.json"
scope_obj  = {
    "patrik":           patrik_shas,
    "patrik_seam_files": seam_files,
    "mechanical_workers": "full"
}
try:
    with open(scope_path, "w") as fh:
        json.dump(scope_obj, fh, indent=2)
except Exception as e:
    print(f"ERROR: could not write {scope_path}: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Scope written: {len(patrik_shas)} patrik SHA(s), {len(seam_files)} seam file(s) → {scope_path}")
PYEOF
```

**Cross-segment-seam definition:** A *segment* is the sha-range of one trail record (one session-end review). `cross_segment_seams` is the set of file paths that appear in the diff of ≥2 distinct segments — computed by taking the union of files-touched per record and intersecting pairwise. The file-touch set per segment is derived from `git diff --name-only <sha-range>`.

---

After ShellCheck (Step 6) and before Tracker Reconciliation (Step 8), run the parallel code-review gate on the week's diff against `origin/main`.

Read `~/.claude/plugins/coordinator-claude/coordinator/skills/parallel-code-review/SKILL.md` and execute its steps. The skill snapshots the diff, dispatches four orthogonal reviewers (the Staff Engineer + security-audit-worker + dep-cve-auditor + test-evidence-parser) in parallel into a no-rewrite synthesizer, and emits a structured `BLOCKED | WARN | OK` verdict. The brief that invokes parallel-code-review references `tasks/review-trail/.weekly-reviewer-scopes.json` so the no-rewrite synthesizer narrates 'the Staff Engineer scoped to gap+seams; mechanical workers full diff' in the BLOCKED|WARN|OK verdict.

- **BLOCKED:** halt before Step 8 (Tracker Reconciliation) and Step 9 (Release Notes). Surface verdict line and findings-dir path to PM. Do NOT proceed to release notes or merge until either the issue is fixed and the gate is re-run, or `--force` bypass is granted.
- **WARN:** include the verdict line in the release-notes draft (Step 9); proceed.
- **OK:** proceed silently; verdict line still goes into the release-notes draft for the record.
- **OK (patrik trail-covered, mechanical clean):** when the trail covers all weekly the Staff Engineer-tier scope AND no findings from any worker. Informational subvariant of OK; the dispatch still ran.

**Skip rules** (full detail in the skill body): skip entirely on <10 lines or internal-only paths; skip the Staff Engineer on doc-only weeks; skip the entire gate on plan-only weeks; `--force` escape passes through from `/workweek-complete --force`.

**Plan:** `docs/plans/2026-05-06-parallel-code-review-weekly-gate.md`.

---

## Step 8: Tracker Reconciliation

Read `docs/project-tracker.md` (if it exists). For each workstream that appears in the week's `Plans touched: shipped` fields, verify the tracker status is updated to reflect completion. Fix in place.

Report: _"Tracker reconciliation: N workstreams updated."_

---

## Step 9: Draft Release Notes — PM Review Gate

Draft release notes from two sources (do NOT re-author — surface and organise):
1. The week-changelog daily files: `Scope:`, `Decisions:`, `Plans touched: shipped` fields.
2. `archive/completed/YYYY-MM.md`: entries under the week's date range.

Write the draft to `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md` (use today's date; version is a placeholder until Step 10 confirms it).

Present the draft to PM: _"Release notes drafted. Does this capture the week accurately?"_

**Wait for PM review.** The PM may request edits before proceeding.

---

## Step 10: Version Bump — PM Confirmation Gate

Propose a semver increment based on changelog content:
- **Major:** breaking change noted in any `Decisions:` field.
- **Minor:** new feature or new command shipped (`Plans touched: shipped` with new commands/skills).
- **Patch:** fixes, doc updates, refactors only.

Present to PM: _"Proposed: vX.Y.Z (rationale: [one line]). Confirm or adjust."_

**Wait for PM confirmation.** Update the release-notes filename and HEADER.md `Prior week released:` value to the confirmed version.

---

## Step 11: `/merge-to-main`

Invoke `/merge-to-main` only after PM has confirmed release notes (Step 9) and version (Step 10). Do NOT inline merge logic — the skill handles pre-merge test suite, PR creation, and merge.

---

## Step 12: Health Survey

Run the full health survey if available (e.g., `/health` or equivalent). Record output in `tasks/health-ledger.md` under today's date.

---

## Step 13: Reset Week-Changelog

Archive and reset the week's state:

1. Determine the current `Week starting:` date from HEADER.md — this is the archive path key.
2. Create `archive/week-changelogs/<week-starting>/`.
3. Move all daily files (`tasks/week-changelog/YYYY-MM-DD-*.md`) to the archive path. HEADER.md is NOT moved — it gets rewritten in place.
4. Create `archive/review-trail/<week-starting>/` and move `tasks/review-trail/*.json` (excluding `.gitkeep` and `.weekly-reviewer-scopes.json`) into it. The `.gitkeep` stays in `tasks/review-trail/` so the directory remains tracked. The transient `.weekly-reviewer-scopes.json` (written by Step 7's prelude) is deleted, not archived — it is regenerated each week.

   > **Archival ordering matters:** this MUST happen AFTER Step 7 has consumed the trail (otherwise Step 7 reads an empty trail on the week it runs). Step 13 is correctly downstream — Step 7 runs at line ~135 of this file; Step 13 archives at the end.

5. Write a fresh HEADER.md with the released version and a cleared `Last /workweek-start:` line:

```markdown
# Week Changelog

<!-- Directory convention: [see HEADER.md comment block] -->

**Week starting:** (not yet set — run /workweek-start to initialise)
**Prior week released:** vX.Y.Z (commit <merge-sha>, YYYY-MM-DD)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):**
- [ ] (run /workweek-start to set priorities)
```

6. Commit everything:
```bash
git add -- tasks/week-changelog/ archive/week-changelogs/<week-starting>/ \
           tasks/review-trail/ archive/review-trail/<week-starting>/
git commit -m "chore(workweek-complete): archive week <week-starting>, reset changelog + review-trail vX.Y.Z"
git push origin $(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)
```

---

## Step 14: Final Summary

```
## Workweek Complete

**Week:** YYYY-MM-DD to YYYY-MM-DD (D days, N commits)
**Shipped:** [list of shipped workstreams]
**Version:** vX.Y.Z
**Release notes:** archive/release-notes/YYYY-MM-DD-vX.Y.Z.md
**Validation:** [pass / failures described]
**Docs updated:** [/update-docs completed]
**Improvement queue:** [K entries processed / no triage needed]
**Bug backlog:** [N open P1/P2 items — /bug-blitz proposed/deferred/not needed / file absent]
**Code stats:** [summary or "scc not available"]
**ShellCheck:** [clean / N issues fixed]
**Code-review gate:** [BLOCKED|WARN|OK] — convergent: N — patrik / security / deps / tests summary
**Tracker:** [N workstreams updated]
**Merged to main:** [yes — PR #N / blocked: reason]
**Week-changelog:** archived to archive/week-changelogs/<week-starting>/, HEADER.md reset
**Next:** run /workweek-start to set priorities for the new week
```

---

### What This Does NOT Do

- **Auto-fire.** This is PM-invoked. `/workday-complete` surfaces the staleness signal.
- **Re-author the week from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 11 delegates to `/merge-to-main` which handles the PR.
- **Delete release notes or handoffs.** Only daily changelog files are archived; release artifacts stay.
- **`/distill` and `/update-docs/handoff-archival` do not touch trail records.** Trail records follow the week-changelog lifecycle (archived here in Step 13), not the handoff lifecycle. They are per-session JSON files written by `coordinator-write-review-trail.sh` and consumed by Step 7's prelude — never by handoff archival.

### Relationship to Other Commands

- **`/workday-complete`** — daily wrap; feeds the changelog this command reads.
- **`/workweek-start`** — weekly orient; detects the HEADER reset done in Step 13 and re-inits cleanly.
- **`/merge-to-main`** — invoked in Step 11; not duplicated.
- **Artifact pruning** — formerly Step 12 (`coordinator:artifact-consolidation`); absorbed into `/update-docs` Phase 8b 2026-05-06. Step 3's `/update-docs` invocation now handles it.
- **`/update-docs`** — invoked in Step 3; not duplicated.
- **`bin/check-weekly-staleness.sh`** — the informational script surfaced by `/workday-complete` to nudge PM toward this command.
