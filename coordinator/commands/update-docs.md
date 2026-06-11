---
name: update-docs
description: Repo-wide documentation maintenance and sync
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--no-distill]"
---

# Update Documentation — Repo-Wide Maintenance

Ensure all documentation reflects the current state of the codebase.

## Instructions

Repo-wide maintenance — syncs all documentation artifacts to match the current codebase state, regardless of which agent(s) made the changes.

**Arguments:** `--no-distill` — skip Phase 13 distillation check (use for overnight/unattended runs).

**Execution model:** Dispatch Phases 1–11d to a **Sonnet doc-maintenance agent** (`model: "sonnet"`). The coordinator (EM) handles Phase 0, **Phase 12 (Agent dispatch — EM only)**, Phases 11f / 11g / 11h / 11h2 / 11i, and Phases 13 / 14 / 15, plus any escalations. When the Sonnet agent encounters a skill invocation stub (Phases 5, 6, 8, 11), it executes that skill's content directly.

> **EM/subagent boundary — read this before dispatching the Sonnet agent.** The Sonnet doc-maintenance agent's scope ENDS at Phase 11d. It MUST NOT attempt Phase 12: subagents cannot dispatch other subagents via `Agent`, and a Sonnet worker reaching for `doc-link-checker` will fail. Phase 12 is structurally EM-led and is the explicit hand-back point — when the Sonnet agent returns, the EM resumes execution at Phase 12 and runs everything from there onward (the 11f / 11g / 11h* / 11i bash checks plus the Phase 13+ tail).

**Out-of-scope actions for the doc-maintenance agent:** DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, or any `gh` command mutating GitHub state beyond pushing the current branch. DO NOT commit to `main`. If you find yourself reaching for a merge, STOP and surface to the EM. The EM merges via `/merge-to-main`.

### Execution Workflow

Phases below are the source of truth — the headings enumerate everything this command does. No separate "what this does" list (it drifts).

### Pre-flight: Fresh-Repo Precondition Probe

Before running any phase, probe whether the repo has accumulated anything worth maintaining. If ALL THREE axes below indicate a freshly-scaffolded repo with no doc-relevant activity, emit the no-op-loud message and EXIT — do NOT dispatch the doc-maintenance agent against empty inputs.

This is the **produce-not-prescribe** principle (`docs/wiki/produce-not-prescribe.md`) applied as a downstream self-gate: `/coordinator:repo-setup` produces the minimum-viable substrate (orientation_cache.md, project-tracker.md, README.md, CLAUDE.md); `/update-docs` adds-to those artifacts once content accumulates, rather than re-creating from scratch on a fresh repo.

**Threshold (conjunctive AND — all three must be true for the no-op to fire):**

```bash
# Axis 1 — source-file surface: DIRECTORY.md does not yet exist (no source indexed)
axis1=0
[ ! -f docs/DIRECTORY.md ] && axis1=1

# Axis 2 — completed-work archive: empty
axis2=0
if [ ! -d archive/completed ] || [ -z "$(ls -A archive/completed 2>/dev/null)" ]; then
  axis2=1
fi

# Axis 3 — distillable artifacts in tasks/: none
axis3=0
if [ ! -d tasks ] || [ -z "$(find tasks -name '*.md' -type f 2>/dev/null)" ]; then
  axis3=1
fi

if [ "$axis1" -eq 1 ] && [ "$axis2" -eq 1 ] && [ "$axis3" -eq 1 ]; then
  cat <<'EOF'
Nothing material to update — the repo is freshly-scaffolded (no DIRECTORY.md, no completed work, no distillable artifacts in tasks/). /coordinator:repo-setup already produced the minimum-viable substrate (orientation_cache.md, project-tracker.md, README.md, CLAUDE.md). Re-run /update-docs after the first workstream lands real content.

Doctrine: docs/wiki/produce-not-prescribe.md — setup-class skills produce minimum-viable downstream artifacts; downstream skills add-to them as content accumulates.
EOF
  exit 0
fi
```

**Portability note (per DR-148):** Execution target is **bash ≥ 4 + BSD coreutils**. The probe uses portable idioms only — no `grep -P`, no `realpath`, no GNU-only `find` flags. `find tasks -name '*.md' -type f` is portable across BSD and GNU `find`; `ls -A` is portable. Verify with `bash -n` before committing — see `docs/wiki/cross-platform-shell-portability.md` for the BSD coreutils-axis specifics.

**Bias:** false-negative-NEVER. The conjunctive AND means if even ONE axis suggests real maintenance is due, the probe falls through and the full pipeline runs. Better to run a no-op pipeline than silently skip real work.

#### Phase 0: Quick-Save Before Docs

1. **Branch guard:** If on `main`, create a work branch (`work/{machine}/{date}`) and switch. Never commit to main directly.
2. `CLAUDE_INVOKING_COMMAND=update-docs ~/.claude/plugins/coordinator/bin/coordinator-safe-commit --blanket "pre-docs quick-save"`
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

**MEMORY.md is a pointer index, not a state mirror.** Update only when a new entry fits one of: PM decision pointer (`project_<topic>.md`), behavioral feedback (`feedback_<topic>.md`), external-system pointer (other repos, MCP registrations, dashboards), or project-context pointer (repo conventions, sister-repo paths).

**Do NOT add:** phase/milestone status → `git log` / tracker; completion logs → git log; key-files tables → DIRECTORY.md; architectural decisions inline → DR or wiki; system health stats → CI / atlas; active priorities → `tasks/`; anything that duplicates CLAUDE.md; session-specific details; speculative conclusions from one file.

**Periodic hygiene:** When MEMORY.md exceeds ~80 lines or contains tables, audit it — promote architectural facts to wiki/DRs, delete completion logs, replace state-mirror tables with pointers. Lessons-style content (behavior corrections, anti-patterns) routes via `/learn-lessons` to `state/lessons.md`, not here.

#### Phase 5: Maintain Project Tracker + Archive Completed Work

**If `tracker_missing` flag was set in Phase 1, skip this phase.**

Inline the tracker-maintenance routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/tracker-maintenance.md` and follow all steps exactly.

#### Phase 6: Trim Lessons Files

Invoke `/learn-lessons --mode=local` directly.

#### Phase 7: Update CLAUDE.md (Rare)

Only if source architecture no longer matches reality, new project-wide rules were established, or build system changed. **This should be rare.**

#### Phase 8: Archive Old Handoffs

Inline the handoff-archival routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/handoff-archival.md` and follow all steps exactly.

#### tasks/ vs state/ — sweep scope for Phases 8b and 13

Spec backlink: `docs/plans/2026-06-08-tasks-state-folder-split.md` § C5.

**`state/`** is load-bearing session substrate (queues, trackers, ledgers, handoffs, recheck markers, etc.). **`/update-docs` never archives, prunes, or deletes any path under `state/`.** Sweeps of `state/` surfaces are surgical and named — `coordinator:learn-lessons` writes `state/lessons.md`; Phase 11i's queue pruner operates on named queue files only; the orientation-cache regenerator (Phase 10) runs its own schema-governed replacement. No blanket sweep ever touches `state/`.

**`tasks/`** is the aggressive sweep target: UUID flight-recorder dirs, dated reports, dated topic dirs, and loose scratch. Phases 8b and 13 may archive or delete from `tasks/` under the thresholds defined in their respective sub-routines. Specific rules:

- **Dated reports** (`*-YYYY-MM-DD*.md`) older than 14 days → eligible for archival after active-reference check.
- **Dated topic directories** (`<topic>-YYYY-MM-DD/`) with no recent git activity → eligible for archival after active-reference check.
- **Loose scratch files** (`tasks/scratch/*.{py,log,txt,sh}`) older than 7 days → eligible for deletion (no active-reference check required).
- **UUID flight-recorder dirs** — managed by the Tasks API; `/update-docs` does **NOT** touch them.
- **Frontmatter `status: superseded` or `status: archived`** on any `tasks/*.md` → archive immediately regardless of age.

**Hard constraint — `state/scratch/<managed-namespace>/`** (deep-architecture-survey, bug-blitz, artifact-distillation): these roots are sustained cross-session work products, not ephemera. They are protected by the `state/` no-touch rule above. Only loose `tasks/scratch/*` files are fair game; the managed-namespace roots under `state/scratch/` are never swept.

#### Phase 8b: Prune Accumulated Artifacts

Inline the artifact-pruning routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/artifact-pruning.md` and follow all steps exactly. Conservative thresholds make most runs no-ops; the safety commit makes any deletion `git revert`-able.

#### Phase 9: Commit + Verify Remote

1. `CLAUDE_INVOKING_COMMAND=update-docs ~/.claude/plugins/coordinator/bin/coordinator-safe-commit --blanket "docs maintenance"`
   (The post-commit hook will auto-push on work/feature branches.)
2. **Verify remote is synced:** `git log origin/$(git branch --show-current)..HEAD 2>/dev/null`
   If unpushed commits remain, push explicitly.
3. If push fails, **warn the PM explicitly**

**Note:** Pushes to the current branch only. Getting to main is the caller's responsibility (`/workday-complete` or `/merge-to-main`). If on main here, Phase 0 failed.

#### Detection-Gating Contract — RAG_PRESENT

All "when RAG present" gates in this command use the same detection mechanism: check whether any MCP tool matching `mcp__*project-rag*` (case-insensitive substring) is available in the current session. A positive match sets the logical `RAG_PRESENT` flag for this run. Future maintainers: the same detection is used by `coordinator/hooks/project-rag-detect.*` (W1 hook) — keep them in sync.

**Three-tier repomap behavior (applies to Phase 9b and Phase 10b):** See `docs/wiki/repomap-rag-gating.md` for the full gating doctrine. Summary:
- **RAG absent:** repomap retains its primary role — generate unconditionally.
- **RAG present + stale or uninitialized:** generate as fallback stopgap; emit audit log entry (Phase 10b).
- **RAG present + fresh:** skip repomap generation entirely.

#### Phase 9b: Repomap Regeneration (RAG-gated)

Gate via `check-rag-state.sh`, then invoke `generate-repomap.sh`. Full gating pattern in `docs/wiki/repomap-rag-gating.md § Caller Pattern`.

```bash
RAG_STATE=$(bash "${CLAUDE_PLUGIN_ROOT}/bin/check-rag-state.sh" 2>/dev/null || echo "unknown")
case "$RAG_STATE" in
  fresh)
    # Note in Phase 14 report: "Repomap: skipped (RAG present + fresh)."
    ;;
  absent|stale|unknown)
    bash "${CLAUDE_PLUGIN_ROOT}/bin/generate-repomap.sh"
    if [ "$RAG_STATE" != "absent" ]; then
      # Note in Phase 14 report: "Repomap: generated as RAG-fallback (RAG state: ${RAG_STATE})."
    fi
    ;;
esac
```

#### Phase 10: Refresh Orientation Cache

If `state/orientation_cache.md` exists, regenerate it from spec via the shared routine. **Do not author the cache directly here. Do not patch sections. Do not re-derive content section-by-section.** The schema (`pipelines/workday-start-internals.md` § 5.5) is owned by `regenerate-orientation-cache.sh`; this phase's job is to invoke that routine in ceremony mode (which clears the mid-session pinboard and discards any out-of-schema sections present in the file):

```bash
bash ~/.claude/plugins/coordinator/bin/regenerate-orientation-cache.sh --invoker update-docs
```

This phase is **where bloat dies.** Any section accreted by a mid-session writer outside `## Pinboard` (a `## Recent Work` paragraph, a `## Health Snapshot` from an older schema, a `## Key Documentation` block) is discarded — only schema-conformant sections regenerate. The verifier (Phase 11b) catches any drift introduced after this phase.

Include the regenerated cache in the Phase 9 commit (or amend if already committed).

If no cache exists: skip. Project hasn't run `/workday-start` yet.

#### Phase 10b: Repomap Audit Log (when RAG present and repomap was generated as fallback)

**Only execute when:** RAG present AND repomap generated as fallback this run (stale/uninitialized, not fresh).

Emit a single log entry to `state/repomap-audit.log` (create if absent, append-only — load-bearing append-log, lives under `state/` per the tasks-state-folder-split):

```
YYYY-MM-DD | repomap_unique_value: yes|no | <brief justification — what did repomap reveal that RAG could not?>
```

After **two consecutive `no` entries**, surface to PM: "Repomap has provided no unique value over two consecutive runs. Consider retiring it — project-RAG covers the same surface. No auto-action taken." PM decides; do NOT retire automatically.

#### Phase 11: Architecture Atlas Integrity Check

Inline the atlas-integrity-check routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/atlas-integrity-check.md` and follow all steps exactly.

**Atlas freshness check (when RAG present):** If project-RAG staleness banner was emitted at session start (W1 hook), surface it in the Phase 14 report: *"Project-RAG staleness: [fresh/stale/uninitialized] — consider reindexing before next heavy investigation session."*

**Quarterly atlas re-read reminder (the Data Science Reviewer F7 — narrative drift mitigation):** Check `docs/architecture/systems-index.md` for `last_mapped`. If any system's `last_mapped` is >90 days ago, note in Phase 14: *"Atlas drift risk: system [X] last mapped [date] — schedule a quarterly re-read sweep."* Informational only — no auto-audit.

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

**If all verifiers exit 0:** Note in Phase 14 report: "Snippet sync: all N verifiers in sync."

#### Phase 11g: Plugin-bundled wiki validate

> Spec backlink: `docs/plans/2026-05-15-plugin-wiki-write-direction-trap.md` § Phase 4
> Semantics changed 2026-05-15 (Option B): no longer syncs dev-side → bundled; now verifies no plugin-cited wiki has a dev-side mirror.

Verify that no plugin-doctrine wiki has a dev-side mirror at `~/.claude/docs/wiki/`. Plugin-doctrine wikis live ONLY at `plugins/coordinator/docs/wiki/<name>.md` — dev-side mirrors re-introduce the write-direction trap. Wiki names are auto-discovered by grepping plugin files for `docs/wiki/<name>.md` references.

```bash
~/.claude/plugins/coordinator/bin/sync-plugin-wiki.sh
```

**If the script exits 0:** log in the Phase 14 report: "Plugin-bundled wiki: clean (N validated)."

**If the script exits 5:** a dev-side mirror exists for a plugin-doctrine wiki. Output names both paths and remediation steps. Resolve before proceeding (override with `COORDINATOR_OVERRIDE_WIKI_MIRROR=1` only for wikis genuinely not belonging in the plugin tree).

**If the script reports WARN (missing-bundled):** a wiki name is referenced but absent from the bundled tree. Doc-link health (Phase 12) handles broken links separately — don't auto-fix here. Log the warning count in the Phase 14 report.

#### Phase 11c: Query Callout Refresh

Run the query callout refresh helper to regenerate any `<!-- BEGIN query: ... -->` blocks in tracked markdown files:

```bash
~/.claude/plugins/coordinator/bin/refresh-queries.sh
```

**If the script reports changes:** include the updated files in the Phase 9 commit (or a follow-up commit in this phase). Log in the Phase 14 report: "Query callouts: N file(s) updated."

**If the script exits non-zero** (parse error or query failure): surface the error to PM with the stderr output. Do NOT abort the rest of `/update-docs` — log the failure and continue.

**If the script reports no changes:** note in the Phase 14 report: "Query callouts: up to date."

#### Phase 11d: Frontmatter Schema Drift Sweep

The W1 PreToolUse validator runs in WARN mode — violations do NOT block writes. This phase surfaces accumulated drift counts at every `/update-docs` run.

Run the lint:

```bash
~/.claude/plugins/coordinator/bin/lint-frontmatter.sh --json
```

Parse the JSON. Three behaviors:

1. **`ok: true` (zero violations):** Note in Phase 14 report: *"Frontmatter schema drift: 0 violations."*
2. **`ok: false` with N violations:**
   - Group by schema. Identify the top 3 most-violated schemas with their counts.
   - List up to 5 specific offending files (path + schema name) in the Phase 14 report.
   - Total count goes in the report headline; full JSON output is logged below the bullet.
   - Phase 14 wording: *"Frontmatter schema drift: N violations across S schema(s). Top: [schema A] (count), [schema B] (count). Files: [path1, path2, ...]. WARN-mode validator did not block these writes — fix-forward at the listed paths."*
3. **Non-zero exit other than 1:** Note "frontmatter drift sweep: errored, stderr attached" in the Phase 14 report and continue. Do NOT abort the rest of `/update-docs`.

**Do not auto-fix.** This phase reports only — violations may encode intentional decisions (predating the schema, field deprecation in flight). Escalation path: ≥2 consecutive non-zero runs → lift schema default to STRICT (`COORDINATOR_SCHEMA_STRICT=1`) or open a bulk-fix debt entry. **Exception:** tradeoff-free correctness fixes on records authored this session (typo, missing required field) may be fixed inline before the Phase 9 commit.

---

### ── EM resumes here (Sonnet doc-maintenance agent has returned) ──

The Sonnet agent's Phase 1–11d work is complete. The EM owns every phase below. The first one (11e) exists at this seam *specifically because* it requires `Agent` dispatch, which only the EM can perform.

#### Phase 12: Doc-link health check (plugin assets) — EM-LED

> **EM-only phase. The Sonnet doc-maintenance agent MUST NOT execute this — subagents cannot dispatch other subagents.** If you are the Sonnet doc-maintenance agent reading this: STOP at the end of Phase 11d and return to the EM. The EM dispatches `doc-link-checker` here, then runs Phases 11f through 11i (mechanical bash) and the Phase 13+ tail itself.

The EM dispatches the `doc-link-checker` agent with the prompt below. The agent returns a `DONE: <actual-path>` reply.

After the worker returns, read the report and surface counts in the Phase 14 rollup:
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
~/.claude/plugins/coordinator/bin/verify-parallel-review-lens-orthogonality.sh
```

**On non-zero exit:** Surface the diagnostic to PM — do NOT auto-fix. A collision means the parallel-review carve-out's preconditions no longer hold (`coordinator/CLAUDE.md` § Review Sequencing). Fix: rename the colliding lens domain or remove the reviewer from the parallel pool.

**On zero exit:** Report "Parallel-review lens-orthogonality: clean."

This phase is informational like 11e; does NOT halt `/update-docs`.

#### Phase 11h: Super-skill anchor-link check

Walks every super-skill SKILL.md and verifies each `CLAUDE.md § <section>` citation resolves against a heading in project-level `coordinator/CLAUDE.md`. Global citations (`~/.claude/CLAUDE.md` or "global" on the same line) are recorded as QUALIFIED and not failed.

```bash
~/.claude/plugins/coordinator/bin/verify-skill-anchor-links.sh
```

**On non-zero exit (DEAD anchors found):** Surface to PM — do NOT auto-fix. Fix: lift the cited content into project-level `coordinator/CLAUDE.md` as a stub bullet, or qualify the citation as global.

**On zero exit:** Report "Super-skill anchor links: clean (N total, K qualified-global)."

This phase is informational like 11e/11f; does NOT halt `/update-docs`.

#### Phase 11h2: Cross-reference coverage sweep

Walks the coordinator-claude plugin tree, extracts every `<plugin>:<name>` reference, `subagent_type:` assignment, and worker bullet under `## Worker Dispatch Recommendations` headers, and verifies each resolves to a real skill/agent/command on disk. External prefixes (`holodeck-control:*`, `superpowers:*`, etc.) are skipped.

```bash
node ~/.claude/plugins/coordinator/bin/verify-coverage.js
```

The script exits non-zero on any orphan reference. This phase HALTS `/update-docs` until orphans are resolved — retarget to the real artifact, add to `REF_ALLOWLIST` in `bin/verify-coverage.js` with a rationale, or create the missing artifact.

**On orphans:** Report `Cross-reference coverage: N orphan(s) — /update-docs HALTED. Resolve before re-running.` and stop.

**On zero orphans:** Report "Cross-reference coverage: clean."

#### Phase 11i: Prune resolved-state bloat from queues

Spec backlinks: `docs/plans/2026-05-07-prune-resolved-state-bloat.md § S5`; `docs/decisions/DR-056-queue-delete-on-resolution.md` (amended 2026-05-17).

Aggressively strip resolved-state bloat and schema ceremony from the three queue files:
- Closure-log sections: `## Processed` / `## Resolved*` / `## History` / `## Closed` / `## Done` / `## Archive` / `## Closeout` — entire body stripped to next `##` heading.
- Entry-shape closure annotations (queue files only): any entry whose `resolution:` is not `pending`/`in_progress`, or which carries a `**Closeout:**` sub-line — entire entry deleted.
- Trivial schema ceremony (queue files only): `  recurring: 0`, `  resolution: pending`, `  resolution: in_progress` sub-lines — stripped, main line preserved.

This is belt-and-suspenders. The write-time discipline (main-line-only entries; delete on resolution) lives in `learn-lessons` and `workweek-complete`; the pruner is the structural backstop that catches drift regardless of writer.

```bash
for queue in state/coordinator-improvement-queue.md state/improvement-queue.md state/bug-backlog.md; do
  [[ -f "$queue" ]] || continue
  before=$(wc -l < "$queue")
  ~/.claude/plugins/coordinator/bin/prune-resolved-queue-entries.sh "$queue"
  after=$(wc -l < "$queue")
  echo "Pruned $((before - after)) lines from $queue"
done
```

**On non-zero exit:** Surface the file path and line from the pruner's error output to the PM — do NOT skip. The pruner fails loud on unexpected structure and must not be bypassed.

**On zero exit with lines pruned:** Include the diff in the docs-maintenance commit (or a separate `chore(queues): prune resolved-state bloat` commit if large). Report pruned counts in the summary.

**On zero exit with no lines pruned:** Note in the report: "Queue prune: clean (no resolved bloat found)."

#### Phase 13: Artifact Distillation (Conditional)

**Skip this phase if `--no-distill` was passed.**

Check whether accumulated artifacts warrant distillation into wiki documents:

1. **Count artifacts:**
   ```bash
   # Count across distillation source directories
   PLANS=$(find docs/plans/ -name "*.md" 2>/dev/null | wc -l)
   HANDOFFS=$(find archive/handoffs/ -name "*.md" 2>/dev/null | wc -l)
   COMPLETED=$(find archive/completed/ -name "*.md" 2>/dev/null | wc -l)
   # state/ is excluded by directory scope. The previous -not -name filters for
   # lessons.md / health-ledger.md / bug-backlog.md / debt-backlog.md were dropped
   # per the tasks-state-folder-split (those files now live under state/).
   TASKS=$(find tasks/ -mindepth 2 -name "*.md" 2>/dev/null | wc -l)
   TOTAL=$((PLANS + HANDOFFS + COMPLETED + TASKS))
   ```

2. **Check recency + threshold — fire if EITHER:** total count ≥ 50; OR last distillation >14 days ago (read from `docs/wiki/.distill-log.md`); OR no log exists and count ≥ 20.

3. **If threshold met:** Announce to PM: *"Artifact count is [N] / last distillation was [N] days ago. Chaining into `/distill`."* Then invoke `/distill` via the Skill tool. `/distill` Phase 4 is the PM approval checkpoint.

4. **If threshold not met:** Note in report: "Distillation: not needed (N artifacts, last run M days ago)."

#### Phase 14: Report

Present a concise `## Documentation Update Summary` with one `### <section>` heading per item below, status line drawn from the phase's own success/skip/failure outputs.

- **Project Tracker** — maintained / no tracker / no changes; include workstream count + dependency notes
- **Source Indexes** — created / updated / no changes
- **Plan Documents** — one line per file
- **Memory** — updated / no changes (note what changed)
- **Lessons** — trimmed N / merged M / no changes
- **CLAUDE.md** — updated / no changes
- **Handoffs Archived** — N moved / no cleanup
- **Artifact Pruning (Phase 8b)** — N plans, M handoffs, K dirs (safety commit SHA) / no-op
- **Plugin Doc-Link Health** — clean / N broken (path) / skipped (cap)
- **Completion Archive** — N archived to YYYY-MM.md / none
- **Architecture Atlas** — drift findings / clean / skipped; append RAG-staleness + quarterly drift-risk notes
- **Repomap** — generated (primary) / fallback / skipped (RAG fresh); append audit-log line
- **Preamble Sync, Query Callouts** — in-sync / N updated / failed
- **Frontmatter Schema Drift** — 0 / N across S schemas with top offenders
- **Distillation** — ran (N guides, M deleted) / not needed / skipped
- **Pushed to Remote** — yes (branch) / no (reason)
- **Cross-Repo Registry (Phase 15)** — N candidates / all verified / N unreachable / skipped

#### Phase 15: Cross-Repo Registry Refresh (cwd-gated, EM-only)

**Skip if `pwd` is not `~/.claude`.** Per-project runs skip with: *"Phase 15: skipped — not running from ~/.claude."* **EM-only** — the Sonnet agent does NOT execute this phase; if it reaches Phase 15, it logs `"Phase 15 is EM-only — deferring to coordinator"` and exits.

Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/cross-repo-registry-refresh.md` and follow all steps exactly.
