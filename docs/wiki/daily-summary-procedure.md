---
name: daily-summary-procedure
status: active
spec_backlink: archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md
---

# Daily Summary Procedure

> Reference wiki for `/workday-complete` Step 4. Heavy-weight artifacts extracted here to keep the
> command body under 200 lines. Step 4 walks these sections inline — do not skip them.
>
> Spec backlink: `archive/specs/2026-05/2026-05-09-skill-consolidation-pass.md` § T1

---

## Daily Reviewer — Sonnet Observer, No Persona Routing

The daily strategic review is dispatched as an **unnamed Sonnet worker** (`general-purpose`,
`model: "sonnet"`). There is **no domain→persona routing** at daily cadence — that was the old
shape and it was wrong. Personas (the Game Dev Reviewer / the Front-End Reviewer / the Data Science Reviewer / the Staff Engineer) are Opus-only; routing a *daily*
ceremony to one puts Opus persona-judgment on the cheapest, most frequent gate we have. The fix
mirrors Sonnet-tier code review moving off personas onto `code-reviewer`.

**Role: observer, not judge.** The daily worker leaves a **paper trail for future-the Staff Engineer** —
alignment notes, debt candidates, architectural-risk *flags*. It renders no final architectural
verdict. The **weekly** Opus the Staff Engineer arch pass (`/workweek-complete` Step 7.5) consumes the week's
accumulated daily trail (the `## Strategic Review (Sonnet daily observer)` sections + DSR rows
tagged `for-weekly-arch-review`) and adjudicates. Domain still matters only for *vocabulary* — a
UE-heavy day's observer should speak UE — but the dispatch is one Sonnet worker regardless, never
a named persona.

---

## Sonnet Analyst Prompt Template

Use this verbatim when dispatching the Phase 4b analyst agent
(`model: "sonnet"`, `run_in_background: true`).

---

**Analyst instructions:**

1. **Read** `tasks/daily-review-scratch/inventory.md` (the Step 4a output).

2. **Extract baseline:** Parse the `> Baseline:` header line from the inventory to get the commit
   hash and timestamp. Example:
   ```bash
   BASELINE=$(grep '^> Baseline:' tasks/daily-review-scratch/inventory.md \
     | sed 's/^> Baseline: //' | awk '{print $1}')
   ```

3. **Read the actual diffs** for architectural understanding:
   ```bash
   git diff <baseline>..HEAD
   ```
   If the diff exceeds ~3000 lines, focus on the files with the most changes (from the inventory's
   file change table). Use `git diff <baseline>..HEAD -- <path>` for targeted reads.

4. **Read commit messages in full** for context on intent:
   ```bash
   git log --since="<baseline>" --format="%H%n%s%n%b%n---"
   ```

5. **Read plan docs** referenced in the inventory (if any) for context on what was being built
   and why.

6. **Write the daily summary** to `archive/daily-summaries/YYYY-MM-DD-<machine>.md` (per-machine naming — mirrors `state/week-changelog/<date>-<machine>.md`):

   Before writing, compute the required coverage anchor values from git — do NOT hand-type these:
   ```bash
   # Full 40-char SHA of the newest commit in today's window (same date bounds step9 uses).
   # YESTERDAY and TODAY are YYYY-MM-DD strings for the previous and current calendar day.
   COVERED_TIP_SHA="$(git log --no-merges --format=%H \
     --after="${YESTERDAY}T23:59:59Z" --before="${TODAY}T23:59:59Z" | head -1)"
   [[ -z "${COVERED_TIP_SHA}" ]] && COVERED_TIP_SHA="none"

   # Machine name — uses the canonical cs_compute_machine resolver.
   # Resolution order: $COORDINATOR_MACHINE → machine-local registry coordinator.machine_slug
   # → $COMPUTERNAME → hostname. Always lowercased. COORDINATOR_MACHINE overrides for tests.
   # POSIX-host form (this is the cc-root-source-guard.md SSOT preamble, not a coordinator-CLI
   # invocation); a PowerShell host resolves the trusted root by its own PowerShell-native path.
   _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
   _cc_doe="$(cat "${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root" 2>/dev/null || true)"
   if [ -z "$_cc_doe" ]; then
     _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
   fi
   _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
   _cc_trusted=0
   case "$_cc_root" in
     "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
   esac
   [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
   case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
   [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
   [ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
   [ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
   # cs_compute_machine is natively imported from coordinator_core.machine_resolver
   # (de-bash campaign, unit "daily-branch" — coordinator-daily-branch.sh is retired).
   _cc_machine_py="python3"; command -v python3 >/dev/null 2>&1 || _cc_machine_py="python"
   COVERED_MACHINE="$("$_cc_machine_py" -c '
import sys
sys.path.insert(0, "'"${_cc_root}"'/hooks/scripts")
from _engine_root import resolve_claude_klabauter_root
mr = resolve_claude_klabauter_root()
if mr not in sys.path:
    sys.path.insert(0, mr)
from coordinator_core.machine_resolver import compute_machine
print(compute_machine())
')"
   ```

   ```markdown
   # Daily Summary — YYYY-MM-DD

   > Generated: YYYY-MM-DD HH:MM by /workday-complete Step 4
   > Baseline: <commit-hash> (<date>)
   > Commits: N | Files changed: M
   covered_tip_sha: <40-char SHA from git command above, or "none" if no commits>
   covered_machine: <machine>

   ## Work Completed
   - **[Feature/system]** — [what changed and why] | commits: [hashes]
   - ...

   ## Systems Affected
   | System | Files Changed | Lines +/- | Nature of Change |
   |--------|--------------|-----------|-----------------|
   | ...    | ...          | ...       | ...             |

   ## Architectural Decisions (Explicit & Implicit)
   - [Decision description — e.g., "Player pawn hardcoded as drone class"]
     - **Rationale:** [why this was done, from commit messages/plan docs]
     - **Risk:** [what this locks in or limits]
   - ...

   _Strategic Review section will be appended by the reviewer agent._
   ```

   **Coverage anchor (required):** `covered_tip_sha` is the completeness anchor a downstream
   backfill scan reads to detect under-covered days. A summary MISSING this field on a day that
   has committed work is treated as a GAP (fail-loud) by the scan — never as "unknown → pass".
   Always derive from the git command above; never hand-type the SHA.

   **Anchor semantics — content-true tip, not actual tip (this is the whole ballgame):**
   `covered_tip_sha` MUST be the newest commit the summary's **content actually describes** (the
   *content-true tip*), NEVER blindly the day's actual/descendant tip. A summary whose prose stops
   mid-day but is anchored to the actual tip is certified complete by the scan even though dozens of
   later commits are absent — the scan trusts the anchor, not the prose. Mechanical anchor injection
   (Phase A0) is therefore safe ONLY for already-complete summaries; for partial summaries, anchor to
   the content-true tip (which correctly re-flags the gap) or route the date to a Phase A
   content-assembly analyst. The analyst must set `covered_tip_sha` to the tip of the range its prose
   actually covers — not the session-end tip if writing stopped mid-day. → See
   `## Coverage Anchor Semantics and Phase A0 Backfill Deductions` below.

   **Machine-defer convention (optional):** When a summary covers a day where work was actually
   done on a different machine, add `defers_to: <machine-slug>` at line start in the summary
   body (no `>` blockquote prefix — the backfill scan reads this field with a line-anchor grep):

   ```
   defers_to: machine-a
   ```

   This declares that `state/week-changelog/<date>-machine-a.md` covers this machine's work for
   the day. **The backfill scan enforces the pointer:** if `state/week-changelog/<date>-<target>.md`
   does not exist on disk, the scan emits `DANGLING-DEFER: <date> <this-machine> -> <target>` to
   stderr and a `DANGLING-DEFER` TSV row to stdout — it never silently trusts a defer whose
   changelog target is absent. This guard exists to prevent the failure mode where
   a machine-b summary deferred to machine-a's own changelog that had not been written.

   **Create `archive/daily-summaries/` directory if it doesn't exist.**

7. **The "Architectural Decisions" section is the key value-add.** Don't just list what changed —
   identify decisions that were made (even implicitly) and their consequences. Examples:
   - "Added a direct dependency from module A to module B" — coupling risk
   - "Used a concrete class where an interface would allow future flexibility" — extensibility risk
   - "Hardcoded a configuration value that may need to vary" — flexibility risk
   - "Chose approach X over Y" — tradeoff documentation

---

## Coverage Anchor Semantics and Phase A0 Backfill Deductions

> Spec backlinks: `cross-repo/inbox/2026-07-02-workday-backfill-covered-tip.md` (Finding 2 —
> content-true-tip doctrine) and
> `cross-repo/inbox/2026-07-02-backfill-scan-legacy-anchor-migration.md` (descendant-tip
> machine-row deduction). Canonicalized in `docs/plans/2026-07-02-backfill-anchor-injection-contract.md`.

### Anchor-semantics doctrine

`covered_tip_sha` MUST be the newest commit the summary's **content actually describes** (the
*content-true tip*), NEVER blindly the day's actual tip or the scan's `actual_tip` column value.
This is the whole ballgame: the backfill scan trusts the anchor, not the prose. A summary anchored
to a tip beyond its content silently certifies that uncovered work has been recorded — the gap
detector is defeated, not satisfied.

**Mechanical injection (Phase A0)** is safe only for a summary whose content already covers the
full day's commit range. For partial summaries (prose stops mid-day), anchor to the content-true
tip instead — this correctly re-flags the gap on the next scan — or route the date to a Phase A
content-assembly analyst. The analyst assembles from existing completion entries (authored truth,
not re-derivation) before a mechanically-correct anchor is set.

### Phase A0 content-completeness guard

Before mechanically injecting an anchor into a pre-existing summary, run a cheap heuristic to
check whether the prose is plausibly complete for the day's commit range (defense in depth):

- Count completion entries for the date: `query-completions --where created=<date>` (or
  `bin/query-records` equivalent).
- Count `## Work Completed` bullets in the summary file.
- **Large mismatch** (e.g. completion entries ≥ 2× Work-Completed bullets AND entries ≥ 3) →
  **CONTENT-GAP**: do NOT inject a masking anchor. Surface the date as requiring content-assembly
  (Phase A analyst). Log the entry count and bullet count for auditability.
- **Commit-density signal** (complement to the completion-count heuristic): count commits dated
  to `<date>` reachable from the tip SHA (`git log <tip> --since="<date> 00:00:00"
  --until="<date> 23:59:59"`), then count distinct commit SHAs cited in the summary that resolve
  and are ancestors of the tip. **Cited count < 50% of range count (range ≥ 3)** → **CONTENT-GAP**
  (exit 30). A **morning-run/tail-wrap/spilled-past-midnight note** in the summary body is a
  corroborating near-certain gap signal when the range is large (≥ 10 commits; exit 30
  independently). The `# Daily Summary` H1 match is case-insensitive.

The injection script exits 30 on CONTENT-GAP; the Step 3.5 caller routes that date to the
content-assembly path, not the re-derivation path.

### Descendant-tip machine-row deduction

After branch consolidation, multiple machine branches (`work/machine-a/*`, `work/machine-b/*`) share
the same commit ancestry — `git log` on each branch-glob walks identical commits. The backfill scan
then emits duplicate gap rows (one per machine) for the same date.

One anchor in the shared flat `archive/daily-summaries/YYYY-MM-DD.md` closes **every machine row**
for that date. The deduction:

- **Machine that owns the descendant tip:** `recorded == actual` → covered.
- **Machines with an older tip:** the recorded (descendant) SHA is NOT an ancestor of their older
  tip → `merge-base --is-ancestor` is false → the scan treats the branch as diverged → **not a gap**.

Phase A0 therefore injects the **descendant tip** (the `actual_tip` value that is a descendant of
/ equal to all other machines' tips for that date), not any individual machine's tip. Do NOT
manufacture per-machine `YYYY-MM-DD-<machine>.md` duplicates for days covered by a legacy flat
summary — the flat file is canonical; the machine axis collapses post-consolidation.

---

## Daily Strategic Observer Prompt Template

Dispatch in **parallel with the analyst** (both background, `run_in_background: true`), as an
**unnamed Sonnet worker** (`general-purpose`, `model: "sonnet"`) — **never a named persona** (see
§ Daily Reviewer above for why). The worker is an **observer leaving a paper trail for
future-the Staff Engineer**, not a judge. It flags candidates; the weekly Opus the Staff Engineer arch pass adjudicates.

> **Parallel-pattern constraint:** the observer reads the same inputs as the analyst
> (`tasks/daily-review-scratch/inventory.md`, `completions-today.json`, `git diff`) — it does NOT
> read the analyst's output prose. The analyst summary is being written concurrently and is not
> available. If a future revision of this step needs the analyst's "Architectural Decisions" section
> (or any other analyst-authored prose) as input, the sidecar/parallel pattern breaks and must
> revert to serial dispatch. This constraint is also documented at the dispatch site in
> `commands/workday-complete.md` § Step 4c.

---

**Daily observer instructions:**

You are an unnamed Sonnet strategic observer for the daily wrap. Read the work summary and project
strategic documents and leave a **paper trail** — alignment notes, debt candidates, and
architectural-risk *flags* for the weekly Opus arch pass to adjudicate. **Render no final
architectural verdict** and do **not** claim a persona identity. **This is NOT a code review** — no
inline code fixes.

1. **Read** `tasks/daily-review-scratch/inventory.md` (the Step 4a output) and
   `tasks/daily-review-scratch/completions-today.json` to understand today's work. Also read the
   git diff for architectural context:
   ```bash
   BASELINE=$(grep '^> Baseline:' tasks/daily-review-scratch/inventory.md \
     | sed 's/^> Baseline: //' | awk '{print $1}')
   git diff "$BASELINE"..HEAD
   ```
   (The analyst summary is being written concurrently and is not yet available.)

2. **Read project strategic documents** (check each, skip silently if missing):
   - `ROADMAP.md`, `docs/roadmap.md`, or `docs/ROADMAP.md`
   - `VISION.md` or `docs/vision.md`
   - `state/workstreams/` (query directly — the rendered `docs/project-tracker.md` view is retired)

3. **Assess** today's work against the strategic direction. Focus on:
   - **Alignment:** Does today's work advance the roadmap? Does anything conflict?
   - **Lock-in:** Do any decisions create accidental constraints that the roadmap/vision would
     want to avoid?
   - **Bridging opportunities:** Are there low-cost opportunities to make today's code more ready
     for planned future capabilities?
   - **Debt patterns:** Is technical debt accumulating in a direction that should be documented?

   **A negative claim about a sibling repo is read there or not made.** "No fix has landed", "no
   guard shipped", "still unguarded" — absence in THIS repo's history is not absence. Resolve the
   sibling (`machine-local get repos.<key>`) and search it (`git -C <path> log --grep`), or write
   the finding without the negative. Nothing denies read access to a sibling checkout; an
   unchecked cross-repo negative sends a peer team chasing a bug they already closed.

4. **Write** findings to the sidecar file `archive/daily-summaries/YYYY-MM-DD-<machine>.observer.md` as a
   new section (`/workday-complete` Step 4d will concatenate this into the main daily summary once
   both agents complete — do not write to or append the main summary file directly):

   ```markdown
   ## Strategic Review (Sonnet daily observer)

   > Observer read: [list which strategic docs were found and read]

   ### Alignment Assessment
   - [Where today's work advances the roadmap]
   - [Where today's work diverges or creates friction]

   ### Technical Debt Identified
   - [Debt item — what, why it matters, suggested future action]
   - ...

   ### Architectural-Risk Flags (for future-the Staff Engineer / weekly arch pass)
   - [Candidate concern — flagged, NOT adjudicated. State what to look at and why it might matter.]
   - ...

   ### Bridging Opportunities
   - [Things that could be done to better connect current state to vision]
   - ...
   ```

   If no strategic docs exist, note that and focus purely on architectural principles
   (SOLID, coupling, extensibility).

5. **Debt backlog entries:** For any finding that warrants tracking, write a per-entry YAML file
   via `coordinator-queue-append --schema debt-backlog`. Do NOT append to a markdown file.
   Required fields:
   - **`title`** — one-line noun-phrase summary of the finding
   - **`body`** — multi-line prose: what was observed, the structural gap, context (`body: |` block scalar)
   - **`source`** — `workday-complete/step4/sonnet-observer/{date}`
   - **`risk`** — consequence of leaving the debt unaddressed
   - **`proposed_action`** — what the EM or a future executor should do about it
   - **`status`** — `open`
   - **`created`** — today's date (YYYY-MM-DD)
   - **`tags: [weekly-arch-review]`** — for any architectural-risk flag, so the weekly the Staff Engineer arch pass
     (`/workweek-complete` Step 7.5) picks it up as accumulated daily signal.

   This produces `state/debt-backlog/<date>-<slug>.yaml`. See `docs/wiki/debt-backlog-schema.md`
   for the full field reference and an example entry.

---

## Health Ledger Entry Schema

After the reviewer agent completes, update `state/health-ledger.md`:

1. If it doesn't exist, create it with this shape (two audit clocks above a per-system table —
   the schema established by the weekly-gate/arch-survey restructure; do **not**
   conflate the clocks):
   ```markdown
   # Health Ledger

   **Last full audit:** (none — run /architecture-survey)
   **Last targeted audit:** <date or none>
   **Next rotation target:** <system>

   | System | Grade | Last Audited | Notes |
   |--------|-------|-------------|-------|
   ```

2. If a system was touched by today's commits but has no row yet, add it with grade `?` (unaudited).

3. Do **NOT** update grades or the two audit clocks from the daily wrap. `Last full audit` is written
   only by a PM-invoked `/architecture-survey`; `Last targeted audit` only by `/architecture-audit`.
   The daily Sonnet observer renders no grades — it flags candidates as debt-backlog YAML entries
   (`state/debt-backlog/<date>-<slug>.yaml`) with `tags: [weekly-arch-review]` for the weekly
   the Staff Engineer arch pass to adjudicate. Grade changes are an audit output, never a daily-wrap side effect.

---

## Debt Backlog Entry Format (Daily Observer)

Entries added by the daily strategic reviewer are per-entry YAML files produced by
`coordinator-queue-append --schema debt-backlog`. The filename is the canonical identity handle:

```
state/debt-backlog/<YYYY-MM-DD>-<slug>.yaml
```

The pre-tc-2 DSR-{YYYY-MM-DD}-{N} ID prefix and markdown table row format are retired.
See `docs/wiki/debt-backlog-schema.md` for the full field reference and a complete example entry.
Historical DSR-prefixed references in entry bodies (e.g. in `evidence:` prose) are tolerated;
the `id:` field itself is dropped (filename is the identity key).

---

## Source Discipline — Residue First, Never `git log`

The primary source for a daily summary or a weekly digest is the residue `/workstream-complete`
leaves: completion entries under `archive/completed/`, plus lessons, handoffs, and the
review-trail. **`git log` is fallback detail for a thinly-named unit, not the spine.** Weekly
agents run *after* the dailies and read them rather than re-deriving from commits.

A completion entry is a unit of work the session that did it declared complete — already
theme-shaped, carrying a title, `nature`, t-shirt LoE, its own commit list, and a narrative body.
Commit-first grouping asks an analyst to reconstruct all of that from scratch, and it is both
costlier and lossy.

Measured on the 2026-07-28 → 2026-08-05 backfill: roughly 350 commits/day against
roughly 10 completion entries/day, and commit-first analysts missed **30% of declared work units
(23 of 75)** — concentrated on exactly the high-commit days where the loss is least visible. A
residue-first second pass closed it to 75/75. Dailies feed release notes, so a dropped entry
becomes a dropped release-note line.

**Brief analysts to read their day's completion entries first and cover every one**, then verify
coverage mechanically: query the entries for the span and assert each is traceable in the output.
This is a step, not a spot-check — sub-agents report success either way. The same backfill had a
bucketing worker silently drop an entry and report success, and the gap-fill agents did the same;
only the mechanical assertion caught either.

---

## Failure Mode Table

| Situation | Action |
|---|---|
| No commits since baseline | Write a minimal daily summary noting "no work today"; skip analyst and reviewer dispatch |
| `standup.py` exits non-zero | Fall back: EM runs git commands directly, writes inventory manually; proceed to analyst dispatch |
| Analyst dispatch fails | Fall back: EM writes a minimal work summary from the inventory; proceed to reviewer dispatch |
| Reviewer dispatch fails | Skip reviewer, note "strategic review skipped" in the daily summary |
| No strategic docs exist | Reviewer focuses on pure architectural principles instead of roadmap alignment |
| No debt entries to write | Skip Step 5; `coordinator-queue-append` creates the entry file; `state/debt-backlog/` directory must exist |

---

## Skip Condition

The only valid skip: **zero new commits today AND no agent-driven changes outside commits.**
Anything else — one commit, one file — run the review. The strongest predictor of a review
that surfaces regressions is a small commit count, not a large one.
