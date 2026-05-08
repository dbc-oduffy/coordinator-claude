---
description: Repo-wide documentation maintenance and sync
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--no-distill]"
---

# Update Documentation — Repo-Wide Maintenance

Ensure all documentation reflects the current state of the codebase.

## Instructions

When invoked, systematically update all documentation artifacts to match reality. This is a **repo-wide maintenance operation**, not scoped to any single session or agent. It syncs docs with the codebase as it currently exists, regardless of which agent(s) made the changes. This prevents documentation drift — the #1 cause of wasted context in LLM-driven development.

**Arguments:**
- `--no-distill` — Skip the artifact distillation check (Phase 12). Use when calling from overnight/unattended workflows (mise-en-place hibernate mode) or when you just want a fast doc sync.

**Execution model:** Phases 1–11d are mechanical maintenance work. Dispatch them to a **Sonnet agent** via the Agent tool (`model: "sonnet"`). The coordinator (you) handles Phase 0 (branch guard), Phase 12 (distillation check), Phase 13 (report), Phase 14 (registry refresh — cwd-gated to `~/.claude`), and any escalations. When the Sonnet agent encounters a skill invocation stub (Phases 5, 6, 8, 11), it executes that skill's content directly — it does not bounce back to the coordinator.

**Out-of-scope actions for the doc-maintenance agent:** DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find yourself reaching for a merge, STOP and surface the question to the EM in your final reply. The EM merges via `/merge-to-main`; the doc-maintenance agent does not.

### What This Does

1. **Detects** project tracker and flags if missing (escalates to PM)
2. **Refreshes** source indexes / directory docs if source files changed
3. **Updates** plan documents to reflect completed/changed work
4. **Syncs** MEMORY.md with new patterns, decisions, or status changes
5. **Maintains** the unified project tracker (inlined; was `tracker-maintenance` skill — see `pipelines/update-docs/`) — marks completion, archives shipped work, updates dependencies
6. **Processes** lessons files (inlined via `/learn-lessons --mode=local`)
7. **Updates** CLAUDE.md if architecture or conventions changed (rare)
8. **Archives** old handoffs (inlined; see `pipelines/update-docs/`)
9. **Commits** all doc changes and verifies remote sync
9b. **Regenerates repomap** (RAG-gated: primary when no RAG, fallback when RAG stale, skipped when RAG fresh)
10. **Refreshes** orientation cache if present
10b. **Logs repomap audit value** (when RAG present and repomap generated as fallback)
11. **Checks** changed files against architecture atlas — narrative-drift mode on RAG repos, hybrid mode on non-RAG repos (inlined; see `pipelines/update-docs/`)
11b. **Verifies snippet sync** (runs every `plugins/*/bin/verify-*-sync.sh`; surfaces diff to PM on failure)
11d. **Sweeps frontmatter-schema drift** (runs `bin/lint-frontmatter.sh --json`; surfaces count + top violators)
12. **Distills** accumulated artifacts into wiki guides if thresholds are met (`/distill` pipeline, conditional)
13. **Reports** summary of all phases
14. **Refreshes** the cross-repo registry (cwd-gated: only fires when invoked from `~/.claude`)

### Execution Workflow

#### Phase 0: Quick-Save Before Docs

1. **Branch guard:** If on `main`, create a work branch (`work/{machine}/{date}`) and switch. Never commit to main directly.
2. `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "pre-docs quick-save"`
3. If nothing to commit, move on
4. Do not push yet — push happens in Phase 9

#### Phase 1: Detect Current State (Silent)

1. **Project tracker check:**
   - Look for `docs/project-tracker.md`
   - If it does NOT exist: **set a `tracker_missing` flag** and include this in your output: `"ESCALATION: No project tracker found at docs/project-tracker.md. This needs a PM + EM conversation to establish workstreams before the tracker can be maintained. Skipping Phase 5."`
   - If it exists: read it and note current workstream count, any `[x]` items, and dependency markers
   - Also check for `archive/completed/` directory — create it if missing

2. **Source file inventory:**
   - Compare actual source files against any directory index / source map docs
   - Identify: files present but undocumented, files documented but missing, renamed files
   - Were any new directories created?

3. **Plan document status:**
   - Check plan doc locations in this order:
     1. `tasks/<feature>/todo.md` — feature-scoped plans (active work)
     2. `docs/plans/` — **canonical location** for approved plans and historical reference
     3. `~/.claude/plans/` — plan-mode working directory (approved plans should be copied to `docs/plans/`)
     4. `tasks/plans/` — session handoff plans (temporary)
   - Any plans in `~/.claude/plans/` that have been approved and should be copied to `docs/plans/`?
   - Any plans with items that appear completed in code?
   - Any plans marked in-progress that are now done?

4. **Recent git context** (supplementary — shows what's happened since last push/docs update):
   ```
   git log --oneline -15
   git log --oneline origin/HEAD..HEAD 2>/dev/null  # committed but not pushed
   ```

#### Phase 2: Update Source Indexes (or Create Them)

**If no DIRECTORY.md (or equivalent source index) exists at all**, create one using subagents. Each agent handles one top-level source directory:

1. Identify the project's source root(s) (e.g., `src/`, `Source/`, `lib/`, `app/`, `packages/`)
2. For each top-level directory, dispatch a subagent with this prompt:
   > Catalog all source files in `[directory]`. For each file, document:
   > - File name and path
   > - Primary class/module/component it defines
   > - One-line purpose
   > - Key exports or APIs (2-3 most important)
   > - Dependencies on other directories in this project
   >
   > Write a `DIRECTORY.md` in `[directory]/` with this information. Use a table or structured list. Include a file count and "Last refreshed: YYYY-MM-DD" timestamp.
3. After all agents complete, write a top-level `DIRECTORY.md` (at the source root) that:
   - Lists each directory with a one-line summary
   - Shows file counts per directory
   - Maps cross-directory dependency chains
   - Includes a "Last refreshed" timestamp

**Adapt to project conventions:** If the project uses a different index structure, match it. Default location: `DIRECTORY.md` at the project root.

**If a DIRECTORY.md already exists**, update it:

1. Compare actual source files against the documented index
2. Add entries for new files, remove entries for deleted files
3. Update any file counts, timestamps, or dependency references
4. If new directories were created, create per-directory indexes for them

**If no source files changed and indexes exist, skip this phase entirely.**

#### Phase 2b: Maintain `docs/README.md`

**If `docs/README.md` does not exist:** Create it now. Include:
- A **Wikis and Guides** section: table of all guides in `docs/wiki/` (read from `DIRECTORY_GUIDE.md` or glob `docs/wiki/*.md`)
- A **Plans** section: pointer to `docs/plans/` with count and recent list (`docs/plans/` is the canonical home; copy approved `~/.claude/plans/` items here)
- A **Research** section: pointer to `docs/research/` with highlights of recent files (glob by date, list top 5–10 most recent)
- A **Design Specifications** section: table of specs (check `docs/specs/`, `docs/superpowers/specs/`, or project-specific locations)
- A **Reference Documentation** section: table of top-level `docs/*.md` files (project-tracker, ci-pipeline, git-workflow, etc.)
- Footer: `*Last updated: YYYY-MM-DD. Maintained by /update-docs.*`

**If `docs/README.md` already exists:** Update it:
1. Sync the Wikis and Guides table against `docs/wiki/DIRECTORY_GUIDE.md` — add new guides, remove deleted ones, update summaries
2. Sync the Plans section — list new plans in `docs/plans/`, remove deleted ones; copy any approved `~/.claude/plans/` items not yet in `docs/plans/`
3. Update the Research highlights — add new `docs/research/*.md` files since the footer timestamp
4. Sync the Design Specifications table — add new specs, update status if implementation is complete
5. Update the footer timestamp

**Include `docs/README.md` in the Phase 9 commit.**

#### Phase 3: Update Plan Documents

For each plan doc related to current codebase state: read it, update status markers (checkbox completion, phase status), note completion date if fully done, and document deviations.

#### Phase 4: Update Memory

**MEMORY.md is a pointer index, not a state mirror.** Cross-session pointers — PM decisions, behavioral feedback, external-system pointers, project-context not derivable from code. NEVER phase status, file catalogs, completion logs, architectural decisions inline, or system health stats.

Read the project's MEMORY.md (at `~/.claude/projects/<project-key>/memory/MEMORY.md`) and update only if a new entry fits one of these shapes:

1. **PM decision pointer** — link to `project_<topic>.md` capturing a product/scope call not derivable from code
2. **Behavioral feedback for the assistant** — `feedback_<topic>.md` correcting or confirming a working pattern
3. **External-system pointer** — links to other repos, MCP server registrations, data dirs, dashboards
4. **Project-context pointer** — repo conventions, sister-repo paths, top-level strategic framing not in CLAUDE.md

**Do NOT add to MEMORY.md** (these are violations regardless of how they're phrased):

- **Phase/milestone status** ("Phase 2 Complete on 2026-04-XX") → belongs in `git log`, plan archives, `CHANGELOG.md`, `docs/project-tracker.md`
- **Completion logs** ("X shipped on date Y, commits Z, W") → git log is authoritative
- **Key Files tables** mirroring `DIRECTORY.md` / `docs/README.md` → those are the source of truth
- **Architectural decisions inline** ("C++ drives logic, BP drives pixels") → DR or wiki, with a one-line MEMORY.md pointer if cross-cutting
- **System health stats** ("789 tests passing, 27 systems in atlas") → CI / atlas / debt-backlog are authoritative; counts rot
- **Active priorities / task lists** → `tasks/`, project tracker
- **Information that duplicates CLAUDE.md or coordinator universal doctrine** — pointer is fine, restated rule is bloat
- **Session-specific details** — what was discussed, temporary state
- **Speculative conclusions** from reading a single file

**Periodic hygiene:** When MEMORY.md exceeds ~80 lines or contains tables, audit it — promote architectural facts to wiki/DRs, delete completion logs, replace state-mirror tables with pointers. Lessons-style content (behavior corrections, anti-patterns) routes via `/learn-lessons` to `tasks/lessons.md`, not here.

#### Phase 5: Maintain Project Tracker + Archive Completed Work

**If `tracker_missing` flag was set in Phase 1, skip this phase.**

Inline the tracker-maintenance routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/tracker-maintenance.md` and follow all steps exactly.

#### Phase 6: Trim Lessons Files

Invoke `/learn-lessons --mode=local` directly.

#### Phase 7: Update CLAUDE.md (Rare)

Only update CLAUDE.md if:
- Source architecture section no longer matches reality
- New critical rules were established that apply project-wide
- Build system or workflow changed

**This should be rare** — most updates are to indexes and plan docs.

#### Phase 8: Archive Old Handoffs

Inline the handoff-archival routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/handoff-archival.md` and follow all steps exactly.

#### Phase 8b: Prune Accumulated Artifacts

Inline the artifact-pruning routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/artifact-pruning.md` and follow all steps exactly. Conservative thresholds make most runs no-ops; the safety commit makes any deletion `git revert`-able.

#### Phase 9: Commit + Verify Remote

1. `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "docs maintenance"`
   (The post-commit hook will auto-push on work/feature branches.)
2. **Verify remote is synced:** `git log origin/$(git branch --show-current)..HEAD 2>/dev/null`
   If unpushed commits remain, push explicitly.
3. If push fails, **warn the PM explicitly**

**Note:** Pushes to the current branch only. Getting to main is the caller's responsibility (`/workday-complete` or `/merge-to-main`). If on main here, Phase 0 failed.

#### Detection-Gating Contract — RAG_PRESENT

All "when RAG present" gates in this command use the same detection mechanism: check whether any MCP tool matching `mcp__*project-rag*` (case-insensitive substring) is available in the current session. A positive match sets the logical `RAG_PRESENT` flag for this run. Future maintainers: the same detection is used by `coordinator/hooks/project-rag-detect.*` (W1 hook) — keep them in sync.

**Three-tier repomap behavior (applies to Phase 9b and Phase 10b):**
- **RAG absent (`!RAG_PRESENT`):** repomap retains its primary role — generate/refresh unconditionally.
- **RAG present + stale or uninitialized:** repomap available as a fast stopgap. Generate as fallback, emit audit log entry (Phase 10b). EM chooses repomap-vs-reindex per session based on time budget.
- **RAG present + fresh:** skip repomap generation entirely.

#### Phase 9b: Repomap Regeneration (RAG-gated)

**Three-tier logic:**
- `!RAG_PRESENT`: run `/generate-repomap` as today (unconditional). Repomap is primary.
- `RAG_PRESENT` + stale/uninitialized: run `/generate-repomap` as fallback stopgap. Note in Phase 13 report: "Repomap: generated as RAG-fallback (RAG stale)."
- `RAG_PRESENT` + fresh: skip. Note in Phase 13 report: "Repomap: skipped (RAG present + fresh)."

#### Phase 10: Refresh Orientation Cache

If `tasks/orientation_cache.md` exists, **always do a full refresh in this phase — never skip on grounds of "looks roughly current."** Stale orientation poisons every subsequent session-start:
1. Re-derive cache content from the docs just updated (repomap, DIRECTORY, health files)
2. Update `generated_at` and `git_head_at_generation` to current HEAD
3. **Ensure a "Key Documentation" section is present** pointing to `docs/README.md`:
   ```
   ## Key Documentation
   - **Master docs index:** [`docs/README.md`](../docs/README.md) — wikis, research, specs, reference
   - **Wiki guides:** [`docs/wiki/`](../docs/wiki/) — [N] living guides with embedded decision records
   - **Research outputs:** [`docs/research/`](../docs/research/) — [N] timestamped research files
   ```
4. Include in the Phase 9 commit (or amend if already committed)

If no cache exists: skip. Project hasn't run `/workday-start` yet.

#### Phase 10b: Repomap Audit Log (when RAG present and repomap was generated as fallback)

**Only execute when:** RAG present AND repomap generated as fallback this run (stale/uninitialized, not fresh).

Emit a single log entry to `tasks/repomap-audit.log` (create if absent, append-only):

```
YYYY-MM-DD | repomap_unique_value: yes|no | <brief justification — what did repomap reveal that RAG could not?>
```

After **two consecutive `no` entries**, surface a recommendation to PM: "Repomap has provided no unique value over two consecutive runs on this repo. Consider retiring it here — project-RAG covers the same surface. No auto-action taken."

Do NOT retire the repomap automatically. The PM decides.

#### Phase 11: Architecture Atlas Integrity Check

Inline the atlas-integrity-check routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/atlas-integrity-check.md` and follow all steps exactly.

**RAG-gating note:** When `RAG_PRESENT`, the atlas-integrity-check skill has been repurposed toward narrative-drift detection (not file-coverage enumeration). The skill handles this internally based on RAG state — no special flag needed here.

**Atlas freshness check (when RAG present):** If project-RAG staleness banner was emitted at session start (W1 hook), surface it again in the Phase 13 report: *"Project-RAG staleness: [fresh/stale/uninitialized] — consider reindexing before next heavy investigation session."*

**Quarterly atlas re-read reminder (the Data Science Reviewer F7 — narrative drift mitigation):** Check `tasks/architecture-atlas/systems-index.md` for `last_mapped`. If any system's `last_mapped` is >90 days ago, note in Phase 13: *"Atlas drift risk: system [X] last mapped [date] — schedule a quarterly re-read sweep."* Informational only — no auto-audit.

#### Phase 11b: Snippet Sync Check

Run every snippet-sync verifier across all installed plugins. The glob covers current verifiers (preamble, calibration, docs-checker, prior-art, text-only, default-routing) and any future ones added under the same `bin/verify-*-sync.sh` convention.

```bash
set +e
fail=0
for verifier in ~/.claude/plugins/*/*/bin/verify-*-sync.sh; do
  [ -x "$verifier" ] || continue
  echo "=== $verifier ==="
  "$verifier" || fail=1
done
exit $fail
```

**If any verifier exits non-zero:** Surface to PM with the offending verifier name + diff output — do NOT auto-fix. Investigate which consumer drifted from its canonical snippet.

**If all verifiers exit 0:** Note in Phase 13 report: "Snippet sync: all N verifiers in sync."

#### Phase 11g: Plugin-bundled wiki sync

Mirror dev-side wiki files cited from plugin files into the plugin-bundled `docs/wiki/` so marketplace consumers can resolve them. Source-of-truth is `~/.claude/docs/wiki/`; sync target is `plugins/coordinator-claude/coordinator/docs/wiki/`. Wiki names are auto-discovered by grepping plugin files for `docs/wiki/<name>.md` references.

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/sync-plugin-wiki.sh
```

**If the script reports synced files:** include the updated/created files under `plugins/coordinator-claude/coordinator/docs/wiki/` in the Phase 9 commit. Log in the Phase 13 report: "Plugin-bundled wiki: N file(s) synced."

**If the script reports WARN:** a wiki name is referenced but absent from dev-side. Doc-link health (Phase 11e) handles broken links separately — don't auto-fix here. Log the warning count in the Phase 13 report.

#### Phase 11c: Query Callout Refresh

Run the query callout refresh helper to regenerate any `<!-- BEGIN query: ... -->` blocks in tracked markdown files:

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/refresh-queries.sh
```

**If the script reports changes:** include the updated files in the Phase 9 commit (or a follow-up commit in this phase). Log in the Phase 13 report: "Query callouts: N file(s) updated."

**If the script exits non-zero** (parse error or query failure): surface the error to PM with the stderr output. Do NOT abort the rest of `/update-docs` — log the failure and continue.

**If the script reports no changes:** note in the Phase 13 report: "Query callouts: up to date."

#### Phase 11d: Frontmatter Schema Drift Sweep

The W1 PreToolUse validator runs in WARN mode — violations do NOT block writes. This phase surfaces accumulated drift counts at every `/update-docs` run.

Run the lint:

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/lint-frontmatter.sh --json
```

Parse the JSON. Three behaviors:

1. **`ok: true` (zero violations):** Note in Phase 13 report: *"Frontmatter schema drift: 0 violations."*
2. **`ok: false` with N violations:**
   - Group by schema. Identify the top 3 most-violated schemas with their counts.
   - List up to 5 specific offending files (path + schema name) in the Phase 13 report.
   - Total count goes in the report headline; full JSON output is logged below the bullet.
   - Phase 13 wording: *"Frontmatter schema drift: N violations across S schema(s). Top: [schema A] (count), [schema B] (count). Files: [path1, path2, ...]. WARN-mode validator did not block these writes — fix-forward at the listed paths."*
3. **Non-zero exit other than 1:** Note "frontmatter drift sweep: errored, stderr attached" in the Phase 13 report and continue. Do NOT abort the rest of `/update-docs`.

**Do not auto-fix.** This phase reports only — violations may encode intentional decisions (predating the schema, field deprecation in flight). Escalation path: ≥2 consecutive non-zero runs → lift schema default to STRICT (`COORDINATOR_SCHEMA_STRICT=1`) or open a bulk-fix debt entry. **Exception:** tradeoff-free correctness fixes on records authored this session (typo, missing required field) may be fixed inline before the Phase 9 commit.

#### Phase 11e: Doc-link health check (plugin assets)

Dispatch the `doc-link-checker` agent with the following prompt. The agent returns a `DONE: <actual-path>` reply.

After the worker returns, read the report and surface counts in the Phase 13 rollup:
- Broken-link count (rows with `status: broken`)
- Anchor-missing count (rows with `status: anchor-missing`)
- Report path (so PM can read findings)
- Skip-cap notice if external-URL cap was hit

If the dispatch returns zero broken/anchor-missing items: report "Plugin doc-link health: clean."

The phase does NOT halt `/update-docs` on findings. Findings are informational; remediation is a separate workstream (queue entry or session-bound fix).

**Dispatch prompt for doc-link-checker:**

```
Tier 1-3 attempted: tier 1 (architecture atlas / wiki) and tier 2 (project-RAG / query-records) do not validate markdown link health; tier 3 (grep) cannot resolve anchor existence; insufficient because mechanical link validation across 150+ plugin assets requires a worker with rate-limited WebFetch and anchor-resolution logic.

You are the doc-link-checker. Your scope for this dispatch:

Scope path: `plugins/`
File filter: `{skills,agents,commands}/*.md` (all 7 plugins; recursive into plugin subdirectories)

Validate every internal markdown link (file existence + anchor existence) and every external URL (HEAD with redirect-follow, 1s sleep between requests, 100-URL cap). Use your standard output contract.

Write the report to your default path: `tasks/doc-link-check-<timestamp>.md` (substitute your own timestamp; do NOT use the literal string "<timestamp>").

DO NOT run `gh pr merge`, `gh pr create` against main, or `git push origin main`.

Reply with `DONE: <path>` ONLY after you have confirmed the file exists at the path above (use Read or Bash `ls` to verify). If you find yourself about to summarize the deliverable inline in your reply, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.
```

#### Phase 11f: Parallel-review lens-orthogonality check

Asserts the four reviewers in the parallel-code-review skill's lens-domain manifest exist as agent files and have non-overlapping `lens_domain` values.

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/verify-parallel-review-lens-orthogonality.sh
```

**On non-zero exit:** Surface the diagnostic to PM — do NOT auto-fix. A collision means the parallel-review carve-out's preconditions no longer hold (`coordinator/CLAUDE.md` § Review Sequencing). Fix: rename the colliding lens domain or remove the reviewer from the parallel pool.

**On zero exit:** Report "Parallel-review lens-orthogonality: clean."

This phase is informational like 11e; does NOT halt `/update-docs`.

#### Phase 11h: Super-skill anchor-link check

Walks every super-skill SKILL.md and verifies each `CLAUDE.md § <section>` citation resolves against a heading in project-level `coordinator/CLAUDE.md`. Global citations (`~/.claude/CLAUDE.md` or "global" on the same line) are recorded as QUALIFIED and not failed.

```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/verify-skill-anchor-links.sh
```

**On non-zero exit (DEAD anchors found):** Surface to PM — do NOT auto-fix. Fix: lift the cited content into project-level `coordinator/CLAUDE.md` as a stub bullet, or qualify the citation as global.

**On zero exit:** Report "Super-skill anchor links: clean (N total, K qualified-global)."

This phase is informational like 11e/11f; does NOT halt `/update-docs`.

#### Phase 11i: Prune resolved-state bloat from queues

Spec backlink: `docs/plans/2026-05-07-prune-resolved-state-bloat.md § S5`

Strip resolved-state bloat (resolved entries and `## Processed` / `## Resolved*` sections) from the three queue files. Belt-and-suspenders in case legacy writes drift back to the resolved pattern.

```bash
for queue in tasks/coordinator-improvement-queue.md tasks/improvement-queue.md tasks/bug-backlog.md; do
  [[ -f "$queue" ]] || continue
  before=$(wc -l < "$queue")
  ~/.claude/plugins/coordinator-claude/coordinator/bin/prune-resolved-queue-entries.sh "$queue"
  after=$(wc -l < "$queue")
  echo "Pruned $((before - after)) lines from $queue"
done
```

**On non-zero exit:** Surface the file path and line from the pruner's error output to the PM — do NOT skip. The pruner fails loud on unexpected structure and must not be bypassed.

**On zero exit with lines pruned:** Include the diff in the docs-maintenance commit (or a separate `chore(queues): prune resolved-state bloat` commit if large). Report pruned counts in the summary.

**On zero exit with no lines pruned:** Note in the report: "Queue prune: clean (no resolved bloat found)."

#### Phase 12: Artifact Distillation (Conditional)

**Skip this phase if `--no-distill` was passed.**

Check whether accumulated artifacts warrant distillation into wiki documents:

1. **Count artifacts:**
   ```bash
   # Count across distillation source directories
   PLANS=$(find docs/plans/ -name "*.md" 2>/dev/null | wc -l)
   HANDOFFS=$(find archive/handoffs/ -name "*.md" 2>/dev/null | wc -l)
   COMPLETED=$(find archive/completed/ -name "*.md" 2>/dev/null | wc -l)
   TASKS=$(find tasks/ -mindepth 2 -name "*.md" -not -path "tasks/architecture-atlas/*" -not -name "lessons.md" -not -name "health-ledger.md" -not -name "bug-backlog.md" -not -name "debt-backlog.md" 2>/dev/null | wc -l)
   TOTAL=$((PLANS + HANDOFFS + COMPLETED + TASKS))
   ```

2. **Check recency + threshold — fire if EITHER:** total count ≥ 50; OR last distillation >14 days ago (read from `docs/wiki/.distill-log.md`); OR no log exists and count ≥ 20.

3. **If threshold met:** Announce to PM: *"Artifact count is [N] / last distillation was [N] days ago. Chaining into `/distill`."* Then invoke `/distill` via the Skill tool. `/distill` Phase 4 is the PM approval checkpoint.

4. **If threshold not met:** Note in report: "Distillation: not needed (N artifacts, last run M days ago)."

#### Phase 13: Report

Present a concise `## Documentation Update Summary`. Emit one `### <section>` heading per row below, followed by a single status line drawn from the bracketed options.

| Section heading | Status template |
|---|---|
| Project Tracker | `[Maintained — N items archived, M remaining / No tracker found — NEEDS PM+EM SETUP / No changes needed]`; append active workstream count + any dependency/dead-reference notes |
| Source Indexes | `[Created from scratch (N directories, M files) / Updated — N files added, M removed / No changes needed]` |
| Plan Documents | one line per file: `[file]: [what was updated]` |
| Memory | `[Updated / No changes needed] — [what changed]` |
| Lessons | `[Trimmed N entries / Merged M / No changes needed]` |
| CLAUDE.md | `[Updated / No changes needed]` |
| Handoffs Archived | `[N moved from tasks/handoffs/ → archive/handoffs/ / No handoffs to clean up]` |
| Artifact Pruning (Phase 8b) | `[Pruned N plans, M archived handoffs, K task dirs (safety commit <sha>) / Nothing crossed threshold — no-op]` |
| Plugin Doc-Link Health | `[Clean / N broken, M anchor-missing — see <report-path> / Skipped — N external URLs over 100-cap]` |
| Completion Archive | `[N items archived to archive/completed/YYYY-MM.md / No completed items]`; second line for ad-hoc git-log captures |
| Architecture Atlas | `[Narrative-drift findings: N suggestions / No drift detected / Skipped — atlas not found]`; append RAG-staleness line and quarterly drift-risk note if triggered |
| Repomap | `[Generated (primary — no RAG) / Generated as RAG-fallback (RAG stale) / Skipped (RAG present + fresh)]`; append audit-log line if applicable |
| Preamble Sync | `[In sync / FAILED — diff surfaced to PM / Script not found (W2 not deployed)]` |
| Query Callouts | `[Up to date / N file(s) updated / Error — stderr surfaced to PM / Script not found (W2 not deployed)]` |
| Frontmatter Schema Drift | `[0 violations / N violations across S schema(s) — top: schema A (count), schema B (count); offending files: path1, path2 … / Script not found (W1 not deployed)]` |
| Distillation | `[Ran /distill — N guides created/updated, M artifacts deleted / Not needed (N artifacts, last run M days ago) / Skipped (--no-distill)]` |
| Pushed to Remote | `[yes — branch name / no — reason]` |
| Cross-Repo Registry (Phase 14, central-only) | `[N candidates surfaced for tagging / All known repos verified / N entries marked unreachable / Skipped — not running from ~/.claude]` |

**Flag to PM:** Explicitly note the push so they can verify nothing breaks for other consumers.

#### Phase 14: Cross-Repo Registry Refresh (cwd-gated, EM-only)

**Skip this phase entirely if `pwd` does not resolve to `~/.claude` (i.e., `$HOME/.claude` or `c:/users/oduffy/.claude` on Windows).** This phase exists for the central coordinator repo only — per-project `/update-docs` runs are no-ops here. Skip with one-line log: *"Phase 14: skipped — not running from ~/.claude."*

**This phase is EM-only.** The doc-maintenance Sonnet agent does NOT execute Phase 14 (same pattern as Phase 12). The EM runs it inline after the agent reports back. If the agent reaches Phase 14 in error, it logs `"Phase 14 is EM-only — deferring to coordinator"` and exits.

**Purpose:** Maintain `~/.claude/tasks/repo-registry.md` — the cross-repo inventory powering peer-repo prior-art lookup. Schema and conventions: [`docs/wiki/repo-registry.md`](../../../docs/wiki/repo-registry.md).

**Steps:**

1. **Decode Claude Code invocation history.** Run `${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh`. Output is tab-separated `shortname<TAB>candidate-path<TAB>encoded-dir`. The decoder is heuristic; treat output as candidates, not authoritative paths.

2. **Diff against active registry block.** Read the `<!-- BEGIN repo-registry --> ... <!-- END repo-registry -->` block in `~/.claude/tasks/repo-registry.md`. For each decoded candidate:
   - **Already in active block (by `shortname`)** → no-op for this candidate.
   - **Not in active block** → append to `<!-- BEGIN repo-registry-candidates --> ... <!-- END repo-registry-candidates -->` block with `status: needs-pm-review`, `goals: []`, `stack_tags: []`, `relationships: []`, `last_verified: <today>`. Skip if already in candidates block.

3. **Staleness check on existing entries.** For each repo in the active block:
   - `ls "${path}"` (or equivalent reachability check). If reachable → update `last_verified: <today>`.
   - If unreachable → flip `status: unreachable` (do NOT delete; repo may be on a disconnected drive).
   - If currently `unreachable` and now reachable → flip back to `active` and log the transition.

4. **Surface counts to PM.** End-of-phase output (count-only, no per-entry detail):
   - `N candidates surfaced for tagging` (if any new candidates)
   - `M entries marked unreachable` (if any flipped to unreachable this run)
   - `K entries restored to active` (if any flipped back from unreachable)
   - `R entries refreshed last_verified`

5. **Commit.** Include `~/.claude/tasks/repo-registry.md` in the EM-side Phase 9 commit. Use `coordinator-safe-commit "registry refresh: N candidates, M unreachable"` or explicit-path staging.

**Failure modes:** Decoder returns zero candidates → log warning, proceed to staleness check. Registry file missing → create from template (Schema heading + empty active + empty candidates blocks); log `"Phase 14: registry file created from scratch"`. Sentinel block malformed → surface to PM, do NOT auto-repair.

**Out of scope for V1:** auto-promoting candidates, inferring stack tags from manifest files, or pruning dormant entries (PM curates and judges in `/workweek-complete`).

### Style Guidelines

- **Match existing style** — don't reformulate, just update
- **Be precise** — file paths, class names, line numbers where relevant
- **Be concise** — bullet points, not paragraphs
- **Preserve structure** — don't reorganize documents, just update content
- **Timestamp everything** — dates on refreshes, completion markers on plans

### When to Invoke

- **Periodically** — when docs have drifted from reality (not necessarily every session)
- **After major feature implementation** — when significant code was written by one or more agents
- **Before starting a new phase** — to ensure docs reflect the starting state
- **Explicitly** — when you want repo-wide maintenance. `/session-end` and `/handoff` now do lightweight orientation patches (cache, tracker, action items, plan docs) for what the session touched — but `/update-docs` is still the heavyweight pass that re-derives everything, trims lessons, archives handoffs, and runs integrity checks.
