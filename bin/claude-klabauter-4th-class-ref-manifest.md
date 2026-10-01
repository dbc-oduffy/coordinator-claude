# Claude-Klabauter 4th-Class State-Reference Manifest

**C2b ground-truth for C3/C4 scripted seam-adoption.**
Generated: 2026-07-03

> **Superseded in part, 2026-08-23.** Every row citing `cockpit-emission.json` as a live output
> path is now historical: the artifact and its producer (`artifact.emit`) were deleted under
> DR-351. The rows are left intact because this file is a dated ground-truth snapshot of a
> completed plan, not a live index — the same reason its `bin/emit-cockpit-snapshot.sh:NNN`
> citations were already marked RETIRED in 2026-07-08 rather than removed.
Plan: docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md
Spec backlink: plan § "Indirect / rev-parse-rooted" 4th-class taxonomy row

This manifest enumerates every instance of the **4th reference class** — shell and script
references to `state/` that are rooted via either (a) root-var indirection
(`ROOT="${CLAUDE_HOME:-$HOME}/.claude"` then `$ROOT/state`) or (b) bare `state/` via
`git rev-parse --show-toplevel`. The C3/C4 literal-pattern repoint scripts are BLIND to
this class; each instance here requires **seam-adoption** (refactor to call
`coordinator_state_root [--central]`) rather than search-and-replace substitution.

Scope searched: `plugins/coordinator-claude/coordinator/{bin,lib,hooks,tests}` and
`tests/cockpit-tc3/`. Test files included (they inherit the same indirection pattern
from the production scripts they call).

Classification key:
- **CENTRAL** — ref resolves to `$CLAUDE_KLABAUTER_ROOT/state` (was `~/.claude/state`) unconditionally;
  route through `coordinator_state_root --central`
- **PER-REPO** — ref resolves to `$GIT_ROOT/state`; route through `coordinator_state_root`
  (which returns `$CLAUDE_KLABAUTER_ROOT` iff git root == meta-repo, else `$GIT_ROOT`)
- **AMBIGUOUS** — cannot be cleanly classified without additional context; note explains why

---

## Class (a) — Root-var indirection

Scripts that capture a `.claude` root into a variable and then reference `$VAR/state`.
The root-capture line AND each state-reference line are recorded.
All instances are CENTRAL (the captured root always resolves to `~/.claude`).

| file:line | matched-code | classification | note |
|---|---|---|---|
| `bin/append-goal-event.sh:23` | `ROOT="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line |
| `bin/append-goal-event.sh:170` | `LOG_DIR="${ROOT}/state"` | CENTRAL | state ref via ROOT |
| `bin/emit-cockpit-snapshot.sh:46` | `ROOT="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | **RETIRED (2026-07-08, DR-208/DR-210):** root-capture line; the bash emitter body these five rows cite no longer exists on disk — it was ported to claude-klabauter's Python `artifact.emit`, now the sole production emitter. `bin/emit-cockpit-snapshot.sh` is a ~66-line fail-loud facade stub; these line numbers do not resolve against current HEAD. Historical citation only — see claude-klabauter's `coordinator_core/ops/emit/` for the equivalent live seam-adoption surface. |
| `bin/emit-cockpit-snapshot.sh:74` | `OUT_FILE="$ROOT/state/cockpit-emission.json"` | CENTRAL | RETIRED — see note above; state ref via ROOT |
| `bin/emit-cockpit-snapshot.sh:88` | `for _f in "$ROOT/state/cockpit-revendor-pending-"*` | CENTRAL | RETIRED — see note above; state ref via ROOT |
| `bin/emit-cockpit-snapshot.sh:1086` | `for _gl in "$ROOT"/state/goals-log.*.jsonl` | CENTRAL | RETIRED — see note above; state ref via ROOT |
| `bin/emit-cockpit-snapshot.sh:1950` | `_SES_HIER_DIR="$ROOT/state"` | CENTRAL | RETIRED — see note above; state ref via ROOT |
| `bin/central-run-due.sh:20` | `CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line |
| `bin/central-run-due.sh:21` | `CONFIG="$CLAUDE_HOME/state/learn-lessons-config.md"` | CENTRAL | state ref via CLAUDE_HOME |
| `bin/central-run-due.sh:86` | `lessons="$root/state/lessons.md"` | AMBIGUOUS | `$root` is an iteration var populated by `learn-lessons-roots.sh` (outputs both meta-repo and sibling roots); not the CLAUDE_HOME capture at line 20; per-repo reads across all configured roots |
| `bin/learn-lessons-roots.sh:22` | `CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line |
| `bin/learn-lessons-roots.sh:111` | `_config="${CLAUDE_HOME}/state/learn-lessons-config.md"` | CENTRAL | state ref via CLAUDE_HOME |
| `bin/cruft-sweep.sh:107` | `HANDOFFS_GLOB="${HOME}/.claude/**/state/handoffs/*.md"` | CENTRAL | **RECLASSIFIED (2026-07-08, C3 of `docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md`):** this row's line number and matched-code are stale — the literal `${HOME}/.claude/**/state/handoffs/*.md` pattern was already seam-adopted by the predecessor plan's own C3 (`docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md`) to `HANDOFFS_GLOB="$(coordinator_state_root)/handoffs/*.md"` (current `bin/cruft-sweep.sh:144`), so no residual literal ref exists to reclassify. More importantly, the CENTRAL classification itself no longer applies to what this row was really guarding against: the folder this manifest entry was worried about reaping is the **install-baton rendezvous**, which as of the 2026-07-08 plan resolves to **settings-home** (`$(coordinator-settings-home)/state/handoffs/`) — a root DISTINCT from both `coordinator_state_root` (per-repo) and `coordinator_state_root --central` (claude-klabauter). `HANDOFFS_GLOB` at `:144` resolves via `coordinator_state_root` (no `--central`) to the CURRENT git root's `state/handoffs/`, which is neither CENTRAL nor the settings-home rendezvous under default invocation — see the C3 forward-guard in `_sweep_orphans()` (Phase C, `bin/cruft-sweep.sh`) for the settings-home-specific reaping exclusion that this row's original CENTRAL framing did not anticipate. |
| `bin/cruft-sweep.sh:108` | `LOG_PATH="${HOME}/.claude/state/cruft-sweep-log.md"` | CENTRAL | **RECLASSIFIED (2026-07-08, C3 of `docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md`):** this row's line number and matched-code are stale — the literal `${HOME}/.claude/state/cruft-sweep-log.md` ref was already seam-adopted by the predecessor plan's own C3 (`docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md`) to `LOG_PATH="$(coordinator_state_root --central)/cruft-sweep-log.md"` (current `bin/cruft-sweep.sh:145`), so no residual literal ref exists to reclassify. |
| `bin/cruft-sweep.sh:109` | `LOCK_DIR="${HOME}/.claude/state/cruft-sweep.lock.d"` | CENTRAL | **RECLASSIFIED (2026-07-08, C3 of `docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md`):** this row's line number and matched-code are stale — the literal `${HOME}/.claude/state/cruft-sweep.lock.d` ref was already seam-adopted by the predecessor plan's own C3 (`docs/plans/2026-07-03-stop-the-rot-claude-klabauter-state-home-placement.md`) to `LOCK_DIR="$(coordinator_state_root --central)/cruft-sweep.lock.d"` (current `bin/cruft-sweep.sh:146`), so no residual literal ref exists to reclassify. |
| `bin/whats-next.sh:34` | `QUEUE_DIR="$HOME/.claude/state/improvement-queue"` | CENTRAL | direct `$HOME/.claude/state` ref; same file has a class-b PER-REPO ref at line 101 |
| `bin/coordinator-queue-append:538` | `base = os.path.join(_claude_home(), output_dir)` | CENTRAL | Python form of root-var indirection; `_claude_home()` uses `CLAUDE_HOME` env var → `~/.claude`; `output_dir` is one of `state/debt-backlog`, `state/bug-backlog`, `state/improvement-queue`, `state/lessons`; only reachable when `queue_scope == "central"` |
| `bin/coordinator-queue-append:540` | `base = os.path.join(os.getcwd(), output_dir)` | AMBIGUOUS | CWD-relative, not root-var-capture or rev-parse rooted; per-repo semantics depend on invocation cwd; schema output_dir includes `state/` prefix (e.g. `state/debt-backlog`) |
| `bin/coordinator-lesson-promote:311` | `return os.path.join(os.getcwd(), "state", "lessons-outbox")` | AMBIGUOUS | CWD-relative default outbox path; not root-var or rev-parse; assumes invoked from meta-repo cwd for central writes; `LESSON_PROMOTE_OUTBOX_ROOT` env var overrides |
| `bin/render-handoff-tracker.js:521` | `path.join(os.homedir(), '.claude', 'state', 'doe-handoff-tracker.md')` | CENTRAL | JS form; direct `$HOME/.claude/state` ref; DoE `--all-repos` mode only |
| `tests/cockpit-tc3/chain-dedup.sh:10` | `ROOT="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line (test harness) |
| `tests/cockpit-tc3/chain-dedup.sh:11` | `EMISSION="$ROOT/state/cockpit-emission.json"` | CENTRAL | state ref via ROOT |
| `tests/cockpit-tc3/full-corpus-run.sh:12` | `ROOT="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line (test harness) |
| `tests/cockpit-tc3/full-corpus-run.sh:34` | `EMISSION="$ROOT/state/cockpit-emission.json"` | CENTRAL | state ref via ROOT |
| `tests/cockpit-tc3/full-corpus-run.sh:173` | `find "$ROOT/state/review-trail"` | CENTRAL | state ref via ROOT |
| `tests/cockpit-tc3/provenance.sh:10` | `ROOT="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line (test harness) |
| `tests/cockpit-tc3/provenance.sh:11` | `EMISSION="$ROOT/state/cockpit-emission.json"` | CENTRAL | state ref via ROOT |
| `tests/cockpit-tc3/rollup-shape.sh:10` | `ROOT="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line (test harness) |
| `tests/cockpit-tc3/rollup-shape.sh:11` | `EMISSION="$ROOT/state/cockpit-emission.json"` | CENTRAL | state ref via ROOT |
| `tests/cockpit-tc3/routine-signals.sh:11` | `ROOT="${CLAUDE_HOME:-$HOME}/.claude"` | CENTRAL | root-capture line (test harness) |
| `tests/cockpit-tc3/routine-signals.sh:12` | `EMISSION="$ROOT/state/cockpit-emission.json"` | CENTRAL | state ref via ROOT |

**Class (a) summary:** 12 unique scripts; 29 total line instances.
CENTRAL: 26 | AMBIGUOUS: 3
Note: `bin/verify-cockpit-wave2.sh` deleted as dead code (no executable caller; 3 rows removed from this manifest — 2026-07-05 C6 disposition).

---

## Class (b) — rev-parse-rooted

Scripts that call `git rev-parse --show-toplevel` to capture a repo root, then reference
`state/` through that variable. All instances are PER-REPO (the state/ resolves to the
current repo at invocation time, which is the meta-repo when run from `~/.claude` but would
be a sibling repo in a consumer context).

| file:line | matched-code | classification | note |
|---|---|---|---|
| `bin/aggregate-chain-loe.sh:107` | `GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line |
| `bin/aggregate-chain-loe.sh:118` | `HANDOFFS_DIR="${GIT_ROOT}/state/handoffs"` | PER-REPO | state ref via GIT_ROOT |
| `bin/check-arch-audit-staleness.sh:43` | `REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line |
| `bin/check-arch-audit-staleness.sh:51` | `LEDGER="$REPO_ROOT/state/health-ledger.md"` | PER-REPO | state ref via REPO_ROOT |
| `bin/check-weekly-staleness.sh:33` | `REPO_ROOT=$(git rev-parse --show-toplevel)` | PER-REPO | rev-parse line |
| `bin/check-weekly-staleness.sh:41` | `HEADER="$REPO_ROOT/state/week-changelog/HEADER.md"` | PER-REPO | state ref via REPO_ROOT |
| `bin/dirty-tree-gate.sh:68` | `REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line |
| `bin/dirty-tree-gate.sh:79` | `HANDOFFS_DIR="$REPO_ROOT/state/handoffs"` | PER-REPO | state ref via REPO_ROOT |
| `bin/list-review-trail-records.sh:43` | `COORDINATOR_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line; variable confusingly named COORDINATOR_ROOT but actually the caller's repo root |
| `bin/list-review-trail-records.sh:85` | `LIVE_DIR="${COORDINATOR_ROOT}/state/review-trail"` | PER-REPO | state ref via COORDINATOR_ROOT |
| `bin/reconcile-completion-commits.sh:115` | `git_root=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line (first call) |
| `bin/reconcile-completion-commits.sh:180` | `git_root=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line (second call in another function) |
| `bin/reconcile-completion-commits.sh:203` | `for _hdir in "${git_root}/state/handoffs" "${git_root}/archive/handoffs"` | PER-REPO | state ref via git_root |
| `bin/regenerate-orientation-cache.sh:48` | `REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"` | PER-REPO | rev-parse line |
| `bin/regenerate-orientation-cache.sh:49` | `CACHE_FILE="$REPO_ROOT/state/orientation_cache.md"` | PER-REPO | state ref via REPO_ROOT |
| `bin/regenerate-orientation-cache.sh:106` | `local d="$REPO_ROOT/state/handoffs"` | PER-REPO | state ref via REPO_ROOT |
| `bin/regenerate-orientation-cache.sh:118` | `local d="$REPO_ROOT/state/handoffs"` | PER-REPO | state ref via REPO_ROOT (second count function) |
| `bin/regenerate-orientation-cache.sh:130` | `local d="$REPO_ROOT/state/handoffs"` | PER-REPO | state ref via REPO_ROOT (third count function) |
| `bin/regenerate-orientation-cache.sh:139` | `local f="$REPO_ROOT/state/bug-backlog.md"` | PER-REPO | state ref via REPO_ROOT |
| `bin/regenerate-orientation-cache.sh:145` | `local f="$REPO_ROOT/state/improvement-queue.md"` | PER-REPO | state ref via REPO_ROOT |
| `bin/render-handoff-tracker.js:67` | `execSync('git rev-parse --show-toplevel', ...)` in `detectRoot()` | PER-REPO | rev-parse line (JS) |
| `bin/render-handoff-tracker.js:544` | `path.join(root, 'state', 'handoff-tracker.md')` | PER-REPO | state ref via root from detectRoot(); per-repo mode only |
| `bin/standup.sh:32` | `REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line |
| `bin/standup.sh:97` | `HANDOFFS_DIR="$REPO_ROOT/state/handoffs"` | PER-REPO | state ref via REPO_ROOT |
| `bin/sweep-shipped-handoffs.sh:56` | `repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line |
| `bin/sweep-shipped-handoffs.sh:61` | `handoffs_dir="${repo_root}/state/handoffs"` | PER-REPO | state ref via repo_root |
| `bin/verify-orientation-cache-sync.sh:31` | `REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"` | PER-REPO | rev-parse line |
| `bin/verify-orientation-cache-sync.sh:32` | `CACHE_FILE="$REPO_ROOT/state/orientation_cache.md"` | PER-REPO | state ref via REPO_ROOT |
| `bin/whats-next.sh:22` | `REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line; same file also has class-a CENTRAL ref at line 34 |
| `bin/whats-next.sh:101` | `HANDOFFS_DIR="$REPO_ROOT/state/handoffs"` | PER-REPO | state ref via REPO_ROOT |
| `bin/workday-complete-backfill-scan.sh:81` | `_top_raw="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line; flows to ROOT at line 93 |
| `bin/workday-complete-backfill-scan.sh:210` | `_changelog="${ROOT}/state/week-changelog/${D}-${_defer_target}.md"` | PER-REPO | state ref via ROOT (set from rev-parse at line 81/93) |
| `bin/workday-complete-step9-append-changelog.sh:127` | `_top_raw="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line; flows to COORDINATOR_ROOT at line 139 |
| `bin/workday-complete-step9-append-changelog.sh:150` | `CHANGELOG_FILE="${COORDINATOR_ROOT}/state/week-changelog/..."` | PER-REPO | state ref via COORDINATOR_ROOT |
| `bin/workday-complete-step9-append-changelog.sh:151` | `HEADER_FILE="${COORDINATOR_ROOT}/state/week-changelog/HEADER.md"` | PER-REPO | state ref via COORDINATOR_ROOT |
| `bin/workday-complete-step9-append-changelog.sh:354` | `HANDOFF_DIR="${COORDINATOR_ROOT}/state/handoffs"` | PER-REPO | state ref via COORDINATOR_ROOT |
| `bin/workday-start-cross-repo-memo-outbox-surface.sh:48` | `git_root=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line |
| `bin/workday-start-cross-repo-memo-outbox-surface.sh:49` | `OUTBOX_DIR="${git_root}/state/memo-outbox"` | PER-REPO | state ref via git_root |
| `hooks/scripts/context-pressure-precompact.sh:94` | `GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line |
| `hooks/scripts/context-pressure-precompact.sh:100` | `ls "${GIT_ROOT}/state/handoffs/"*.md 2>/dev/null` | PER-REPO | state ref via GIT_ROOT |
| `hooks/scripts/project-orientation.sh:18` | `REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line |
| `hooks/scripts/project-orientation.sh:19` | `CACHE="${REPO_ROOT:-.}/state/orientation_cache.md"` | PER-REPO | state ref via REPO_ROOT |
| `hooks/scripts/project-orientation.sh:174` | `SCC_CACHE="${REPO_ROOT:-.}/state/.scc-cache"` | PER-REPO | state ref via REPO_ROOT |
| `hooks/scripts/project-orientation.sh:216` | `HANDOFFS=$(ls "${REPO_ROOT:-.}"/state/handoffs/*.md 2>/dev/null)` | PER-REPO | state ref via REPO_ROOT |
| `hooks/scripts/project-orientation.sh:223` | `LESSONS_DIR="${REPO_ROOT:-.}/state/lessons"` | PER-REPO | state ref via REPO_ROOT |
| `hooks/scripts/runtime-tripwire-advisory.sh:73` | `GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line |
| `hooks/scripts/runtime-tripwire-advisory.sh:182` | `local FIRE_LOG="$GIT_ROOT/state/runtime-tripwire-fire-log.tsv"` | PER-REPO | state ref via GIT_ROOT |
| `hooks/scripts/runtime-tripwire-em-check.sh:76` | `GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"` | PER-REPO | rev-parse line |
| `hooks/scripts/runtime-tripwire-em-check.sh:240` | `FIRE_LOG="$GIT_ROOT/state/runtime-tripwire-fire-log.tsv"` | PER-REPO | state ref via GIT_ROOT |
| `hooks/scripts/session-init.sh:55` | `GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)` | PER-REPO | rev-parse line |
| `hooks/scripts/session-init.sh:283` | `[ -d "${GIT_ROOT}/state/handoffs" ]` | PER-REPO | state ref via GIT_ROOT (condition check) |
| `hooks/scripts/session-init.sh:413` | `git -C "$GIT_ROOT" mv "state/handoffs/${fname}" ...` | PER-REPO | state ref via GIT_ROOT (git -C pattern) |
| `hooks/scripts/session-init.sh:445` | `git ... commit -- state/handoffs/ archive/handoffs/ ...` | PER-REPO | bare state ref in commit scope under GIT_ROOT git -C context; functionally PER-REPO |
| `hooks/scripts/session-init.sh:524` | `git -C "$GIT_ROOT" diff --cached --quiet -- state/handoffs/ ...` | PER-REPO | bare state ref in git -C context; PER-REPO |
| `hooks/scripts/session-init.sh:527` | `git ... commit -- state/handoffs/ archive/handoffs/` | PER-REPO | bare state ref in git -C context; PER-REPO |
| `lib/coordinator-session.sh:34` | `git rev-parse --show-toplevel 2>/dev/null || true` in `_cs_git_root()` | PER-REPO | rev-parse function; git_root callers use this |
| `lib/coordinator-session.sh:1969` | `if [[ -d "${git_root}/state/handoffs" ]]; then` | PER-REPO | state ref via git_root from `_cs_git_root()` |
| `lib/coordinator-session.sh:1971` | `for hfile in "${git_root}/state/handoffs/"*.md; do` | PER-REPO | state ref via git_root from `_cs_git_root()` |

**Class (b) summary:** 20 unique scripts; 62 total line instances.
PER-REPO: 62 | CENTRAL: 0 | AMBIGUOUS: 0

---

## Instance counts

| Sub-class | Unique scripts | Total line instances | CENTRAL | PER-REPO | AMBIGUOUS |
|---|---|---|---|---|---|
| (a) Root-var indirection | 12 | 29 | 26 | 0 | 3 |
| (b) rev-parse-rooted | 20 | 62 | 0 | 62 | 0 |
| **Total** | **27** | **91** | **26** | **62** | **3** |

Note: `bin/whats-next.sh` appears in both sub-classes (has both a class-a CENTRAL ref at
line 34 and a class-b PER-REPO ref at line 101). Count as one unique file but two rows.

---

## Surprises for C3/C4 authors

1. **Scale of class (b)**: 20 scripts with 62 instances substantially exceeds the plan's
   "non-trivial subset" estimate (based on only `list-review-trail-records.sh:43,85` as
   named examples). C4 will need to seam-adopt all 20 scripts.

2. **Python scripts with CWD-relative state/ paths** (`coordinator-queue-append:540`,
   `coordinator-lesson-promote:311`): these are not covered by shell root-var or rev-parse
   patterns but still produce `state/` writes. Classified AMBIGUOUS. C3/C4 authors must
   decide whether these map to the central or per-repo branch of the seam.

3. **`bin/central-run-due.sh:86`**: the `$root` iteration variable is populated by
   `learn-lessons-roots.sh` (which includes both the meta-repo and registered sibling repos).
   This is a PER-REPO read used in a CENTRAL-decision context; the seam-adoption here
   requires the caller to explicitly iterate repo roots rather than routing through
   `coordinator_state_root`.

4. **`bin/workday-complete-step9-append-changelog.sh`** and
   **`bin/workday-complete-backfill-scan.sh`**: both use `COORDINATOR_ROOT` (not `REPO_ROOT`
   or `GIT_ROOT`) as the rev-parse-resolved root. The naming is confusing (suggests
   coordinator plugin root) but it is actually the git repo root of cwd. Seam-adoption
   must use `coordinator_state_root` (default, PER-REPO branch).

5. **(retired 2026-07-19)** `bin/coordinator-handoff-archive.sh:333` is gone — the script
   was deleted in the `handoff.archive_transition` big-bang cutover; the native op resolves
   its own repo root, so this row's PER-REPO/`git -C` seam-adoption concern no longer applies.

6. **`hooks/scripts/project-orientation.sh`**: 4 separate state/ subdirectory refs
   (`orientation_cache.md`, `.scc-cache`, `handoffs/`, `lessons/`) via a single REPO_ROOT
   from rev-parse. All PER-REPO. The seam-adoption simplifies to one `coordinator_state_root`
   call replacing the one `git rev-parse` call.

7. **`lib/coordinator-session.sh`** uses a helper function `_cs_git_root()` rather than
   a top-level rev-parse call. The seam-adoption should replace `_cs_git_root()`-based
   root construction with `coordinator_state_root` in the two call sites at lines 1969/1971.

8. **`tests/cockpit-tc3/*.sh`** (5 test files): all use `ROOT="${CLAUDE_HOME:-$HOME}/.claude"`
   and reference `$ROOT/state/cockpit-emission.json`. These test the production scripts
   that write to central state; after seam-adoption the tests should pass
   `CLAUDE_KLABAUTER_ROOT` instead of relying on `CLAUDE_HOME`.
   **Post-DR-208/DR-210 note (2026-07-08):** the tests exercise `cockpit-emission.json`
   as an output artifact, which is unaffected by the producer-identity change — claude-klabauter's
   `artifact.emit` wrote that file until 2026-08-23, when both it and the file were deleted
   (DR-351) — so the tests below exercise a path that no longer exists at all. The
   `bin/emit-cockpit-snapshot.sh:NNN` citations
   in this manifest's class-(a) table above are stale (retired bash body); this item's
   `$ROOT/state/cockpit-emission.json` output-path reference named a real file at the time and
   names nothing now.
