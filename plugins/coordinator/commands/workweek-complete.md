---
name: workweek-complete
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
Implemented workstreams: <list from Plans touched: implemented fields>
Blockers: <list or "none">
Priorities met: <from HEADER.md priorities vs. implemented plans>
```

Ask: _"Does this summary match your recollection? Proceed with release ceremony?"_

**Wait for PM confirmation before continuing.** This is the single explicit PM gate before the irreversible steps.

---

## Step 2: Full Validation (blocking)

Run the complete validation stack:

```bash
_LIB="$HOME/.claude/plugins/coordinator/lib/coordinator-resolve-validation-cmd.sh"
_RESOLVE_TMP=$(mktemp)
trap 'rm -f "$_RESOLVE_TMP"' EXIT

if [[ -f "$_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$_LIB"
  CMD=$(cs_resolve_fast_test_cmd 2>"$_RESOLVE_TMP")
  RC_RESOLVE=$?
else
  echo "WARN: resolver lib not found at $_LIB — skipping fast-test gate" >&2
  RC_RESOLVE=2
  CMD=""
fi

if [[ $RC_RESOLVE -eq 0 ]]; then
  # bash -c (child-shell sandbox) — matches workday-complete and skills/validate/SKILL.md;
  # prevents assignment-injection clobber of caller state via the resolved command.
  bash -c "$CMD"
  RC_CMD=$?
  # Validation: $RC_CMD  (0 = pass, non-zero = fail)
elif [[ $RC_RESOLVE -eq 2 ]]; then
  # Validation: skipped  (no fast_test_cmd configured — see stderr for remediation)
  RC_CMD=0
  [[ -s "$_RESOLVE_TMP" ]] && cat "$_RESOLVE_TMP" >&2
fi

node --test ~/.claude/plugins/coordinator/tests/plugin-ecosystem/run.js
```

Capture exit codes — they populate `Validation:` in the changelog block:
- **`Validation: 0`** — fast-tier passed; plugin ecosystem check passed.
- **`Validation: <non-zero>`** — configured fast-test command failed. Stop and fix before proceeding.
- **`Validation: skipped`** — no `fast_test_cmd` configured in `coordinator.local.md` and `$COORDINATOR_FAST_TEST_CMD` is unset. Set one or the other; proceed with awareness that fast-tier was not run.

Any blocking failure → stop and report. Fix before proceeding. Do not proceed to Step 3 on a failing validation.

---

## Step 3: Run `/update-docs`

Full multi-phase docs sweep. Commits and pushes to the current branch.

Wait for completion before proceeding.

---

## Step 4: Improvement-Queue Triage

Read `~/.claude/tasks/coordinator-improvement-queue.md`. Note oldest entry date and total active count.

**Triage triggers (any):** ≥5 active entries; oldest >14 days ago; any `[recurring: ≥3]`.

If triggered: (1) read entries, (2) prioritize `[recurring: ≥3]` first, (3) dispatch small executor per `proposed target`, (4) delete resolved entries (do NOT annotate), (5) commit naming closed entries, (6) >15 entries → `/staff-session`-style sweep.

If not triggered: note _"Improvement queue: K entries, oldest YYYY-MM-DD — no triage needed."_

**Write-time discipline (DR-056):** Append NEW entries as a single main line — no sub-lines, no closure-log sections (`## History`, `## Resolved`, `## Done`, etc.) — the pruner strips them.

**Prior-art sidecar scan (judgment-based):** Scan recent `docs/plans/**/*.prior-art-check*.md` sidecars for Conflicts dispositioned as `override-and-document`, `update-prior-art`, or `both`. Any wiki cited ≥3 times is a revision candidate — surface to PM. Full doctrine: `docs/wiki/prior-art-checker.md` § "Bidirectional resolution".

**Bug-backlog depth check:** Read `tasks/bug-backlog.md` if it exists. Count open P1/P2 items. If ≥10 open, ask PM: _"Bug backlog has N open P1/P2 items — run /bug-blitz now or defer?"_ Otherwise note in summary. If absent: skip silently.

---

## Step 4b: Install OOM Reproducer Freshness Check

If `bin/check-install-reproducer-fresh.sh` exists in the repo root:

```bash
bash bin/check-install-reproducer-fresh.sh
```

- **Exit 0 (marker fresh, <24h):** notice; proceed.
- **Exit 0 (test ran and passed):** proceed.
- **Exit 1 (test failed):** halt and report; do NOT proceed to Step 5+ until fixed or PM grants `--force`.

Informational when fresh; **blocking gate** only when the test runs and fails.

---

## Step 4c: UBT Pending-Record Merge Gate (UE plugin work only)

Scan for `*.ubt-compile.pending.json` records in `tasks/review-trail/` with no `.resolved.json` sibling:

```bash
UNRESOLVED=$(find tasks/review-trail -maxdepth 1 -name "*.ubt-compile.pending.json" -type f 2>/dev/null | while read -r f; do
  base="${f%.pending.json}"; [[ ! -f "${base}.resolved.json" ]] && echo "$f"
done)
```

Passes silently when none found. If unresolved: halt and emit `sha_range` values — _"run /workday-complete on the affected day(s) or override with `COORDINATOR_OVERRIDE_UBT_GATE=1`."_ Non-UE repos no-op silently.

---

## Step 4d: Skill Description Length Advisory

```bash
set +e
_DESC_OUT=$(${CLAUDE_PLUGIN_ROOT}/bin/check-description-length.sh 2>&1); _DESC_RC=$?
set -e
echo "---"; echo "description-length advisory (rc=$_DESC_RC):"; echo "$_DESC_OUT"; echo "---"
```

Informational — never blocks. Note over-budget skills in the weekly summary; address next session.

---

## Step 4e: Owner-File Invariant Lint Advisory

Presence-detected. Applies only when `scripts/lint-owner-file-invariants.py` exists — repos without the §1a convention (`docs/wiki/rag-bait-conventions.md` §1a) pass silently.

```bash
if [[ -f scripts/lint-owner-file-invariants.py ]]; then
  set +e
  _LINT_OUT=$(python scripts/lint-owner-file-invariants.py 2>&1); _LINT_RC=$?
  set -e
  echo "---"; echo "owner-file-invariant advisory (rc=$_LINT_RC):"; echo "$_LINT_OUT"; echo "---"
fi
```

Informational. Non-zero rc means a file in `scripts/owner_files.yaml` lost its `Invariant —` marker. Note in weekly summary; address next session. Cadence doctrine: `docs/wiki/workday-workweek-cadence.md` lines 56–75.

---

## Step 4f: enabledPlugins Drift Audit Advisory

Per-repo advisory — audits current repo's `enabledPlugins` against `project_type` / `stack_tags` from `.claude/coordinator.local.md` or `~/.claude/tasks/repo-registry.md`.

```bash
set +e
if [[ -f .claude/settings.json ]]; then
  _EP_OUT=$(${CLAUDE_PLUGIN_ROOT}/bin/audit-enabled-plugins.sh 2>&1); _EP_RC=$?
else
  _EP_OUT="(no .claude/settings.json — skipped)"; _EP_RC=0
fi
set -e
echo "---"; echo "enabledPlugins drift advisory (rc=$_EP_RC):"; echo "$_EP_OUT"; echo "---"
```

Advisory only — never blocks. `project_type: meta` short-circuits (all plugins intentional). When drift is reported, full uninstall requires removing the entry from `.claude/settings.json`, from `~/.claude/plugins/installed_plugins.json`, and from `~/.claude/plugins/cache/<marketplace>/<plugin>/` — EM surfaces the recipe, PM authorizes.

---

## Step 4g: Reverse-Drift Merge Gate (copy_install plugins only)

Blocking gate for plugins whose live install is a copy of source (`copy_install` in `plugin.mirrors`). The forward-SHA `check-plugin-drift.sh` is structurally blind to a live install that was hand-edited *after* the last install — each plugin's registered `reverse_drift_cmd` closes that direction by digest-comparing live against source.

Detection is delegated to the per-plugin `reverse_drift_cmd` registered in `plugin.mirrors.<name>` and discovered through the machine-local registry — so the gate fires from any cwd, not only the holodeck source repo. The reader script is referenced by its **authoritative absolute path**; a cwd-relative `bin/...` path would reproduce the exact silent-no-op bug this gate's 2026-05-28 rework fixed (DR-146). Never shorten it.

```bash
# Discover registered reverse-drift commands via the machine-local registry.
# Absolute path is load-bearing — see DR-146 and docs/wiki/machine-local-registry.md § reverse_drift_cmd.
# `|| REVDRIFT_RC=$?` (not a bare `RC=$?` on the next line) so a non-zero rc is captured
# even if this block is paste-run under `set -e` — otherwise the shell aborts on the
# assignment before rc is read, and the fail-loud branches below never fire.
REVDRIFT_RC=0
REVDRIFT_ROWS="$(~/.claude/plugins/coordinator/bin/list-reverse-drift-cmds.sh)" || REVDRIFT_RC=$?

if [[ $REVDRIFT_RC -eq 3 ]]; then
  # copy_install plugins ARE registered but none carry a reverse_drift_cmd: the gate is blind.
  echo "Reverse-drift gate MISCONFIGURED — copy_install plugins exist but none have a reverse_drift_cmd. Register with: machine-local set plugin.mirrors.<name>.reverse_drift_cmd '<invocation>'. See docs/wiki/machine-local-registry.md § reverse_drift_cmd."
  [[ "${COORDINATOR_OVERRIDE_REVERSE_DRIFT:-0}" == "1" ]] || exit 1
elif [[ $REVDRIFT_RC -ne 0 ]]; then
  echo "Reverse-drift gate: could not read the registry (rc=$REVDRIFT_RC). Investigate before merging."
  [[ "${COORDINATOR_OVERRIDE_REVERSE_DRIFT:-0}" == "1" ]] || exit 1
else
  # rc==0: run each registered command from its source_path. Empty rows = no
  # copy_install plugins on this machine = genuinely N/A (clean pass).
  REVERSE_DRIFT_FAIL=0
  while IFS='|' read -r PLUGIN SRC CMD; do
    [[ -z "$PLUGIN" ]] && continue
    # bash -euo pipefail -c (not plain bash -c) so a pipeline failure inside the
    # registered reverse_drift_cmd fails-fast rather than being masked — matches the
    # hardened refresh_cmd invocation (refresh-plugin-live-install.sh:393, code-reviewer F7).
    if ! ( cd "$SRC" && bash -euo pipefail -c "$CMD" ); then
      REVERSE_DRIFT_FAIL=1
    fi
  done <<< "$REVDRIFT_ROWS"
  if [[ $REVERSE_DRIFT_FAIL -ne 0 ]]; then
    echo "Reverse-drift gate FAILED. Remediation: run \`holodeck_recover --step reverse-drift\` to back-propagate live→source, or override with COORDINATOR_OVERRIDE_REVERSE_DRIFT=1."
    [[ "${COORDINATOR_OVERRIDE_REVERSE_DRIFT:-0}" == "1" ]] || exit 1
  fi
fi
```

Do NOT proceed to Step 5 until the gate passes or PM grants override. Note `reverse_drift_cmd` is registry-supplied and shell-evaluated once by `bash -c` — operators MUST single-quote the value in `registry.local.toml` (same idiom as `refresh_cmd`). Detection logic remains holodeck-owned (`X:/claude-unreal-holodeck/bin/check-reverse-drift.sh`; `docs/plans/2026-05-26-game-dev-ownership-and-bidirectional-install-drift.md` AC7); this gate only routes to it via the registry.

---

## Step 5: scc Snapshot

If `scc` is available (`which scc` or `~/bin/scc`):
```bash
scc --no-complexity --no-cocomo --no-duplicates --sort code
```

Record the compact summary (total lines, top 5 languages) in `tasks/code-stats-history.md` under a `## YYYY-MM-DD` heading (append; create the file if it doesn't exist). Weekly trend is the signal; daily delta is noise.

If `scc` is not installed: note in summary — _"scc not available — install for weekly code stats."_

---

## Step 6: ShellCheck Sweep + Console-Flash Guard

```bash
git ls-files '*.sh' | while read -r f; do
  tr -d '\r' < "$f" | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|$f:|g"
done
```

- **Issues found:** report and offer to fix. Most findings are quick mechanical fixes; fix what's straightforward, flag behavior-changing items for PM review.
- **Clean:** report _"ShellCheck: all .sh files clean."_
- **Not installed:** note in summary.

**Console-flash guard (CONSOLE-FLASH-GUARD):** After ShellCheck, run the spawn-suppression guard:

```bash
# Runs from the coordinator plugin root regardless of cwd.
_GUARD="${CLAUDE_PLUGIN_ROOT}/bin/verify-no-console-flash.sh"
if [[ -f "$_GUARD" ]]; then
  bash "$_GUARD" "$HOME/.claude/plugins"
  _FLASH_RC=$?
  if [[ $_FLASH_RC -ne 0 ]]; then
    echo "Console-flash guard: UNSUPPRESSED spawns found (see above). Fix before merging."
  else
    echo "Console-flash guard: OK"
  fi
else
  echo "Console-flash guard: guard not found at $_GUARD — install or check CLAUDE_PLUGIN_ROOT"
fi
```

- **Issues found:** report and offer to fix; same offer-and-fix shape as ShellCheck. Route bare python/node/powershell spawns through `lib/spawn-hidden.sh` or add `# verify-no-console-flash: allow` if the spawn is verifiably not on the Windows hot-path.
- **Clean:** report _"Console-flash guard: OK"_.
- **Guard missing:** note in summary — install or check `$CLAUDE_PLUGIN_ROOT`.

<!-- spec: CONSOLE-FLASH-GUARD; see docs/wiki/coordinator-tripwires.md § Console-window flash and docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 4 -->

---

## Step 7: Parallel Code-Review Gate

> Architecture and rationale: `docs/wiki/weekly-gate-architecture.md § Step 7`.

**Compute scope.** Run the trail helper (fail-loud; reads `tasks/week-changelog/HEADER.md`, globs `tasks/review-trail/*.json`, writes `tasks/review-trail/.weekly-reviewer-scopes.json`):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/workweek-trail-scope.sh"
```

**Run gate.** After ShellCheck (Step 6) and before Tracker Reconciliation (Step 8), read `~/.claude/plugins/coordinator/skills/parallel-code-review/SKILL.md` and execute its steps. The brief references `tasks/review-trail/.weekly-reviewer-scopes.json`. The Staff Engineer is NOT in this gate — see Step 7.5.

- **BLOCKED:** halt before Step 8 and Step 9; surface verdict line + findings-dir path to PM. Do not proceed until fixed or `--force` granted.
- **WARN:** include verdict line in release-notes draft (Step 9); proceed.
- **OK:** proceed; verdict line goes into release-notes draft for the record.

**Skip rules** (full detail in skill body): <10 lines or internal-only → skip entirely; doc-only week → skip code-semantics chunks (mechanical workers still run); plan-only week → skip entire gate; `--force` passes through.

---

## Step 7.5: the Staff Engineer Layer-2 — Architecture Pass (advisory, does NOT gate merge)

> Architecture and rationale: `docs/wiki/weekly-gate-architecture.md § Step 7.5`. Disposition ladder and accepted-loss reasoning are documented there.

**Run condition:** skip (note "no arch-tier signal this week") if ALL of: `arch_tier_candidates` empty AND `convergent_findings` empty AND seam-file set empty AND daily strategic-observer trail carries no `for-weekly-arch-review` flags.

**Otherwise** dispatch the Staff Engineer (`coordinator:staff-eng`, Opus) with five inputs: (1) changelog digest, (2) `arch_tier_candidates` from `$FINDINGS_DIR/synthesis.json`, (3) `convergent_findings` from `synthesis.json`, (4) `patrik_seam_files` from `tasks/review-trail/.weekly-reviewer-scopes.json`, (5) daily strategic-observer trail (`archive/daily-summaries/*.md` DSR rows tagged `for-weekly-arch-review`).

The Staff Engineer produces candidates only — never auto-authors spinoffs. EM routes candidates down the disposition ladder (trivial+non-structural → immediate executor; mid-size cluster → bundled spinoff candidate; large/structural → standalone spinoff or `/plan`).

**Surface the Staff Engineer's spinoff candidates to PM alongside the release-notes draft (Step 9).**

---

## Step 7.6: Architecture Audit Staleness Fold

> Architecture and rationale: `docs/wiki/weekly-gate-architecture.md § Step 7.6`. Scope (DECISION D6) and disposition ladder documented there.

**Run the staleness check:**
```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/check-arch-audit-staleness.sh"
```

- `STALE` (>10 days or never targeted-audited) → auto-fold a targeted-on-diff audit: read `${CLAUDE_PLUGIN_ROOT}/skills/architecture-audit/SKILL.md` and run it scoped to diff-touched systems only.
- `FRESH` → no fold (EM may still trigger on heavy multi-system churn).
- `UNKNOWN` → do NOT auto-fold; note and move on.

The folded audit never edits code — packages findings as spinoff candidates; writes only `Last targeted audit` clock + atlas metadata. Surface candidates alongside the Staff Engineer's Step 7.5 candidates and the release-notes draft (Step 9). Does NOT block merge.

If skipped (FRESH and no EM churn trigger): note _"Architecture audit: fresh (Last targeted audit within 10d) — no fold."_ in the summary.

---

## Step 8: Tracker Reconciliation

Read `docs/project-tracker.md` (if it exists). For each workstream that appears in the week's `Plans touched: implemented` fields, verify the tracker status is updated to reflect completion. Fix in place.

Report: _"Tracker reconciliation: N workstreams updated."_

---

## Step 8.5: LoE High-Water Check — MANDATORY Before Step 9

> **MANDATORY.** Do NOT proceed to Step 9 without completing it. Surfaces XL chain-terminal completion entries so large chains are explicitly acknowledged in the weekly summary, not silently folded into Other bucket prose.

### 8.5.1 Query chain-terminal XL entries

```bash
bin/query-completions --since "7d" \
  --where "chain_terminal=true" \
  --where "chain_loe.tshirt=XL" \
  --format json
```

Run a second time with `--where "loe.tshirt=XL AND chain_terminal=true"` to surface single-session XL entries (no `chain_loe`). Union both result sets in the PM summary.

### 8.5.2 Surface to PM

For each returned entry include: `title`, `chain` slug, `chain_loe.sessions`, `chain_loe.tshirt` (or `loe.tshirt` for single-session XL), date span. Format:

```
**XL chain-terminal entries this week:**
- "<title>" — chain: <chain-slug>, <N sessions>, <date-start> to <date-end> [chain-level XL]
- "<title>" — single-session XL, <date>
```

**If zero entries:** note explicitly _"No XL chain-terminal entries this week."_ — do NOT silently omit (absence is indistinguishable from a skipped step).

No PM gate required — informational surfacing only. PM may promote an XL entry to Highlights in Step 9 editorial bucketing.

---

## Step 9: Editorial Bucketing + Release Notes Draft — PM Review Gate

### 9.0 Ensure output directory exists

```bash
mkdir -p tasks/week-changelog/
```

### 9.1 Query the week's completion entries

```bash
"$HOME/.claude/plugins/coordinator/bin/query-completions.sh" --since "7d" --where "status=pending-release" --format json
```

Zero entries → skip to Step 9.4 with an empty-week note.

### 9.2 Dispatch Sonnet editorial worker

Dispatch a Sonnet worker with the entry corpus. Worker assigns each entry to one bucket, writes `tasks/week-changelog/YYYY-MM-DD-pending-release.md`.

**Default bucket rules** (primary key: `nature`; refined by `loe.tshirt` when present):

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

EM override permitted — state explicitly in the dispatch. **Worker output format:**

```markdown
# Pending Release — YYYY-MM-DD

_Source entries queried: N_
_Code-review gate verdict: [OK | WARN <verdict-line> | not-run]_

## Highlights
- <summary> — [source](relative/path/to/per-entry-file.md)

## Notable
- <summary> — [source](relative/path/to/per-entry-file.md)

## Other
- <summary> — [source](relative/path/to/per-entry-file.md)
- ... and assorted fixes  _(collapse long tails ≥5 similar entries; not for Highlights/Notable)_
```

Empty buckets: `## Heading` with `_none this week_`. Each entry cites its source file. WARN verdict from Step 7 goes verbatim under `_Code-review gate verdict:_`. Verify file exists and is non-trivial before proceeding.

### 9.4 Draft release notes as thin wrapper

Read pending-release file. Write `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md` — do NOT re-author; format for the reader:

```markdown
# Release Notes — vX.Y.Z (YYYY-MM-DD)

## Highlights
<paste Highlights bucket, reformatted for prose if desired>

## Notable Changes
<paste Notable bucket>

## Other Changes
<paste Other bucket>

---
_Code-review gate: [verdict]_
```

Version is a placeholder until Step 10 confirms it.

Present to PM: _"Release notes drafted at `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md`. Bucketed: N Highlights, N Notable, N Other. Does this capture the week accurately?"_

**Wait for PM review.** Update both files to reflect any reclassifications.

---

## Step 10: Version Bump — PM Confirmation Gate

**Consumer convention takes precedence.** If the repo has `docs/wiki/versioning-convention.md`, that doc is the authority for *which* number/artifact is the canonical product version and *how* to bump it — read it first and follow it. The repo-agnostic semver heuristic below is the fallback for repos with no convention doc. (A repo with multiple version namespaces — pyproject, package.json, `.uplugin`, git tags — should not have its scheme guessed here; the convention doc exists precisely to name the one that ships.)

Fallback heuristic (no convention doc present) — propose a semver increment based on changelog content:
- **Major:** breaking change noted in any `Decisions:` field.
- **Minor:** new feature or new command shipped (`Plans touched: implemented` with new commands/skills).
- **Patch:** fixes, doc updates, refactors only.

Either way the governing principle is the same: a version bump communicates user-noticeable change — consolidate the delta since the last user-visible release into ONE bump.

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
4. Create `archive/review-trail/<week-starting>/` and move `tasks/review-trail/*.json` (excluding `.gitkeep` and `.weekly-reviewer-scopes.json`) into it. `.gitkeep` stays so the dir remains tracked; transient `.weekly-reviewer-scopes.json` is deleted, not archived. **Archival ordering matters:** must run AFTER Step 7 consumes the trail (Step 13 is correctly downstream).

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
git push origin $(~/.claude/plugins/coordinator/bin/coordinator-current-branch)
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
**Code-review gate:** [BLOCKED|WARN|OK] — convergent: N — code-semantics (N chunks) / security / deps / tests summary
**Arch pass (Step 7.5):** [N arch-tier candidates surfaced / no arch-tier signal this week]
**Arch audit fold (Step 7.6):** [folded targeted-on-diff audit — N spinoff candidates surfaced / fresh — no fold / staleness UNKNOWN]
**Tracker:** [N workstreams updated]
**Merged to main:** [yes — PR #N / blocked: reason]
**Week-changelog:** archived to archive/week-changelogs/<week-starting>/, HEADER.md reset
**Next:** run /workweek-start to set priorities for the new week
```

---

### What This Does NOT Do

- **Auto-fire.** PM-invoked; `/workday-complete` surfaces the staleness signal.
- **Re-author from git log.** The week-changelog is the canonical record.
- **Push directly to main.** Step 11 delegates to `/merge-to-main`.
- **Delete release notes or handoffs.** Only daily changelog files are archived.
- **Touch trail records via `/distill` or `/update-docs/handoff-archival`.** Trail JSON is archived in Step 13 only — never by handoff archival.

### Relationship to Other Commands

- **`/workday-complete`** — daily wrap; feeds the changelog this command reads.
- **`/workweek-start`** — weekly orient; detects Step 13's HEADER reset and re-inits.
- **`/merge-to-main`** — invoked in Step 11.
- **`/update-docs`** — invoked in Step 3.
- **`check-weekly-staleness.sh`** — staleness nudge used by `/workday-complete`.
- **`check-arch-audit-staleness.sh`** — reads `Last targeted audit` clock; consumed by Step 7.6 (STALE >10 days → auto-fold).
- **`/architecture-audit`** — folded in by Step 7.6 when stale; writes `Last targeted audit`.
- **`/architecture-survey`** — full breadth survey (PM-invoked only); writes `Last full audit`.
