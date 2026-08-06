---
name: update-docs
description: "Sync all documentation artifacts to the current codebase state."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--no-distill]"
---

# Update Documentation — Repo-Wide Maintenance

## Instructions

Repo-wide maintenance — syncs all documentation artifacts to match the current codebase state, regardless of which agent(s) made the changes.

**Arguments:** `--no-distill` — skip Phase 13 distillation check (use for overnight/unattended runs).

**Execution model:** Dispatch Phases 1–11d to a **Sonnet doc-maintenance agent** (`model: "sonnet"`), **dispatched UNNAMED** — you do not need mid-flight contact with it, and a named teammate's report is not delivered to the dispatcher (a named dispatch becomes an Agent-teams teammate; recovering from that costs a corrective `SendMessage` round trip plus stray idle notifications after stand-down). The coordinator (EM) handles Phase 0, **Phase 12 (Agent dispatch — EM only)**, Phases 11f / 11g / 11h / 11h2 / 11i, and Phases 13 / 14 / 15, plus any escalations. When the Sonnet agent encounters a skill invocation stub (Phases 5, 6, 8, 11), it executes that skill's content directly.

> **EM/subagent boundary — read this before dispatching the Sonnet agent.** The Sonnet doc-maintenance agent's scope ENDS at Phase 11d. It MUST NOT attempt Phase 12: subagents cannot dispatch other subagents via `Agent`, and a Sonnet worker reaching for `doc-link-checker` will fail. Phase 12 is structurally EM-led and is the explicit hand-back point — when the Sonnet agent returns, the EM resumes execution at Phase 12 and runs everything from there onward (the 11f / 11g / 11h* / 11i bash checks plus the Phase 13+ tail).

**Out-of-scope actions for the doc-maintenance agent:** DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, or any `gh` command mutating GitHub state beyond pushing the current branch. DO NOT commit to `main`. If you find yourself reaching for a merge, STOP and surface to the EM. The EM merges via `/merge-to-main`.

### Pre-flight: Fresh-Repo Precondition Probe

Before running any phase, probe whether the repo has accumulated anything worth maintaining. If ALL THREE axes below indicate a freshly-scaffolded repo with no doc-relevant activity, emit the no-op-loud message and EXIT — do NOT dispatch the doc-maintenance agent against empty inputs.

Applies the **produce-not-prescribe** principle (`docs/wiki/produce-not-prescribe.md`): `/update-docs` adds-to the substrate `/coordinator:repo-setup` produced; it does not re-create from scratch on a fresh repo.

**Threshold (conjunctive AND — all three must be true for the no-op to fire):**

Run the probe: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/update-docs-probes" fresh-scaffold-probe`

The CLI owns the cwd guard (falls through silently if neither `CLAUDE.md` nor `.git/HEAD` is present at repo root) and the 3-axis AND (source-file surface via `DIRECTORY.md`/`docs/DIRECTORY.md`, completed-work archive, distillable `tasks/*.md`). **Exit 0** means all three axes fired — the no-op-loud message is already on stdout; relay it verbatim and EXIT before dispatching the doc-maintenance agent. **Exit 1** means at least one axis has real content (or the cwd guard fired) — nothing is printed; fall through to the normal pipeline.

**Bias:** false-negative-NEVER. If even ONE axis suggests maintenance is due, the probe falls through and the full pipeline runs.

#### Phase 0: Quick-Save Before Docs

1. **Branch guard:** If on `main`, create a work branch (`work/{machine}/{date}`) and switch. Never commit to main directly.
2. Run `CLAUDE_INVOKING_COMMAND=update-docs "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --blanket "pre-docs quick-save"`
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

4. **Recent git context** (supplementary — shows what's happened since last push/docs update).
   Recent commit history:
   ```bash
   git log --oneline -15
   ```
   Commits made but not yet pushed:
   ```bash
   git log --oneline origin/HEAD..HEAD 2>/dev/null
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

   This is a clean fit for a background `Workflow` — one directory-scout per top-level source dir, all running in one context-cheap wave instead of holding N agent-dumps in your own context. Worth stamping with `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type workflow` if there are more than a couple of directories.
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

**Hygiene is enforced, not advisory.** A write-time guard caps `MEMORY.md` (≤2,000 B, ≤20 index rows, ≤100 chars/row) and each sibling body file (≤1,500 B) — a write that would exceed any of these is denied outright, not merely flagged. Separately, every closure ceremony (`/workday-complete`, `/workweek-complete`, `/workstream-complete`, `/merging-to-main`) runs a blocking drain gate that fails while any `*.md` survives under the auto-memory store at all — the size cap bounds a single day, the drain bounds how long anything persists between closes, and the two are complementary rather than either superseding the other. Lessons-style content (behavior corrections, anti-patterns) routes via `/learn-lessons` to `state/lessons/` (one per-entry YAML file), not here.

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

**`state/`** is load-bearing session substrate (queues, trackers, ledgers, handoffs, recheck markers, etc.). **`/update-docs` never archives, prunes, or deletes any path under `state/`.** Only surgical named sweeps apply (e.g., Phase 11i queue pruner on named queue files; Phase 11j `state/subagent-share/` sidecar reaper, liveness-and-age-floor gated per its own named exception; Phase 10 orientation-cache regenerator on its own schema).

**`tasks/`** is the aggressive sweep target: UUID flight-recorder dirs, dated reports, dated topic dirs, and loose scratch. Phases 8b and 13 may archive or delete from `tasks/` under the thresholds defined in their respective sub-routines. Specific rules:

- **Dated reports** (`*-YYYY-MM-DD*.md`) older than 14 days → eligible for archival after active-reference check.
- **Dated topic directories** (`<topic>-YYYY-MM-DD/`) with no recent git activity → eligible for archival after active-reference check.
- **Loose scratch files** (`tasks/scratch/*.{py,log,txt,sh}`) older than 7 days → eligible for deletion (no active-reference check required).
- **UUID flight-recorder dirs** — managed by the Tasks API; `/update-docs` does **NOT** touch them.
- **Frontmatter `status: superseded` or `status: archived`** on any `tasks/*.md` → archive immediately regardless of age.

**Hard constraint — `state/scratch/<managed-namespace>/`** (deep-architecture-survey, bug-blitz, artifact-distillation): sustained cross-session work products protected by the `state/` no-touch rule. Only loose `tasks/scratch/*` files are fair game.

#### Phase 8b: Prune Accumulated Artifacts

Inline the artifact-pruning routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/artifact-pruning.md` and follow all steps exactly. Conservative thresholds make most runs no-ops; the safety commit makes any deletion `git revert`-able. **The `git rm` leg is EM-scope**, same as the Phase 9 commit below — the doc-maintenance agent identifies and stages nothing; it inventories the prune candidates for the report and leaves deletion to the EM at hand-back. A subagent-scope `git rm` will be blocked by the same guard that blocks Phase 9's commit.

#### Phase 9: Commit + Verify Remote

> **EM-scope, same as Phase 12 — the doc-maintenance agent MUST NOT run this.** Subagents cannot commit; the caller-identity guard blocks it with no cooperative override, correctly, per "only the EM or `git-commit-agent` commits." The doc-maintenance agent's job through Phase 11d is to leave every file written and nothing committed — the EM performs Phase 9 itself as the first action after the Sonnet agent hands back, before dispatching Phase 12. See the full step under "EM resumes here" below; this heading exists here only to hold the phase number in sequence.

**Note:** Pushes to the current branch only — getting to main is the caller's responsibility (`/workday-complete` or `/merge-to-main`). If on main here, Phase 0 failed.

#### Detection-Gating Contract — RAG_PRESENT

All "when RAG present" gates in this command use the same detection mechanism: check whether any MCP tool matching `mcp__*project-rag*` (case-insensitive substring) is available in the current session. A positive match sets the logical `RAG_PRESENT` flag for this run. Future maintainers: the same detection is used by `coordinator/hooks/project-rag-detect.*` (W1 hook) — keep them in sync.

**Three-tier repomap behavior (applies to Phase 9b and Phase 10b):**
- **RAG absent:** generate unconditionally.
- **RAG present + stale or uninitialized:** generate as fallback stopgap; emit audit log entry (Phase 10b).
- **RAG present + fresh:** skip entirely.

#### Phase 9b: Repomap Regeneration (RAG-gated)

Gate via `check-rag-state.py`, then invoke `generate-repomap.py`. Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/update-docs-probes" repomap-gate`

The CLI resolves `check-rag-state.py`, applies the three-tier case (fresh → skip; absent → generate unconditionally; stale/unknown → generate as fallback), and prints the matching Phase 14 note (skip note, or the RAG-fallback note, or a stderr warning if `generate-repomap.py` is unresolvable). Exit 0 covers the skip/success/missing-generator cases; exit 1 means the generator ran and failed.

#### Phase 10: Refresh Orientation Cache

If `state/orientation_cache.md` exists, regenerate it from spec via the shared routine. **Do not author the cache directly here. Do not patch sections. Do not re-derive content section-by-section.** The schema (`pipelines/workday-start-internals.md` § 5.5) is owned by `regenerate-orientation-cache`; this phase's job is to invoke that routine in ceremony mode (which clears the mid-session pinboard and discards any out-of-schema sections present in the file): `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/regenerate-orientation-cache" --invoker update-docs`

This phase is **where bloat dies.** Any section accreted outside `## Pinboard` is discarded — only schema-conformant sections regenerate. The verifier (Phase 11b) catches any drift introduced after this phase.

Include the regenerated cache in the Phase 9 commit (or amend if already committed).

If no cache exists: skip. Project hasn't run `/workday-start` yet.

#### Phase 10b: Repomap Audit Log (when RAG present and repomap was generated as fallback)

**Only execute when:** RAG present AND repomap generated as fallback this run (stale/uninitialized, not fresh).

Emit a single log entry to `state/repomap-audit.log` (create if absent, append-only):

```
YYYY-MM-DD | repomap_unique_value: yes|no | <brief justification — what did repomap reveal that RAG could not?>
```

After **two consecutive `no` entries**, surface to PM: "Repomap has provided no unique value over two consecutive runs. Consider retiring it — project-RAG covers the same surface. No auto-action taken." PM decides; do NOT retire automatically.

#### Phase 11: Architecture Atlas Integrity Check

Inline the atlas-integrity-check routine. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/atlas-integrity-check.md` and follow all steps exactly.

**Atlas freshness check (when RAG present):** If project-RAG staleness banner was emitted at session start (W1 hook), surface it in the Phase 14 report: *"Project-RAG staleness: [fresh/stale/uninitialized] — consider reindexing before next heavy investigation session."*

**Quarterly atlas re-read reminder (the Data Science Reviewer F7 — narrative drift mitigation):** Check `docs/architecture/systems-index.md` for `last_mapped`. If any system's `last_mapped` is >90 days ago, note in Phase 14: *"Atlas drift risk: system [X] last mapped [date] — schedule a quarterly re-read sweep."* Informational only — no auto-audit.

#### Phase 11b: Snippet Sync Check — retired, no-op

Retired: `snippet-sync-sweep retired — no-op` (used to run every `bin/verify-*-sync.sh` snippet-sync verifier across installed plugins). Kept as a numbered placeholder so downstream phase numbers don't shift.

#### Phase 11g: Plugin-bundled wiki validate

Verifies no plugin-cited wiki has a dev-side mirror at `~/.claude/docs/wiki/`. Plugin-doctrine wikis live ONLY at `plugins/coordinator/docs/wiki/<name>.md`.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/sync-plugin-wiki"`

**If the script exits 0:** log in the Phase 14 report: "Plugin-bundled wiki: clean (N validated)."

**If the script exits 5:** a dev-side mirror exists. Output names both paths and remediation steps. Resolve before proceeding (override with `COORDINATOR_OVERRIDE_WIKI_MIRROR=1` only for wikis genuinely not belonging in the plugin tree).

**If the script reports WARN (missing-bundled):** a wiki name is referenced but absent from the bundled tree. Doc-link health (Phase 12) handles broken links separately — don't auto-fix here. Log the warning count in the Phase 14 report.

#### Phase 11c: Query Callout Refresh

Regenerate `<!-- BEGIN query: ... -->` blocks in tracked markdown files: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/refresh-queries"`

**If the script reports changes:** include the updated files in the Phase 9 commit (or a follow-up commit in this phase). No separate Phase 14 line — folds into the always-print `**Synced:**` rollup (Phase 14 § Negative-spec: `Preamble Sync, Query Callouts` is dropped outright).

**If the script exits non-zero** (parse error or query failure): surface the error to PM. Do NOT abort the rest of `/update-docs` — log the failure and continue.

**If the script reports no changes:** no Phase 14 line — folds into the always-print `**Synced:**` rollup.

#### Phase 11d: Frontmatter Schema Drift Sweep

The W1 PreToolUse validator runs in WARN mode — violations do NOT block writes. This phase surfaces accumulated drift counts at every `/update-docs` run: run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/lint-frontmatter" --json`.

**Native op replacement:** the underlying validation now also lives at
`coordinator_core/frontmatter/schema_cli.py`, `@register_op("schema.validate")` — a native
Python frontmatter validation seam needing no Node runtime. `schema.validate` is the op-surface
replacement to cite here, not a guaranteed 1:1 CLI swap for `lint-frontmatter.js` (which still
exists in `coordinator/bin/` as a legacy artifact); if this step needs a specific check
`schema.validate` doesn't yet cover, diff the two and flag back to claude-klabauter-em.

Parse the JSON. Three behaviors:

1. **`ok: true` (zero violations):** No Phase 14 line — the `**Frontmatter Schema Drift:**` exception line is omitted at 0 violations.
2. **`ok: false` with N violations:**
   - Group by schema. Identify the top 3 most-violated schemas with their counts.
   - List up to 5 specific offending files (path + schema name) in the Phase 14 report.
   - Total count goes in the report headline; full JSON output is logged below the bullet.
   - Phase 14 wording: *"Frontmatter schema drift: N violations across S schema(s). Top: [schema A] (count), [schema B] (count). Files: [path1, path2, ...]. WARN-mode validator did not block these writes — fix-forward at the listed paths."*
3. **Non-zero exit other than 1:** Note "frontmatter drift sweep: errored, stderr attached" in the Phase 14 report and continue. Do NOT abort the rest of `/update-docs`.

**Do not auto-fix.** This phase reports only — violations may encode intentional decisions (predating the schema, field deprecation in flight). Escalation path: ≥2 consecutive non-zero runs → lift schema default to STRICT (`COORDINATOR_SCHEMA_STRICT=1`) or open a bulk-fix debt entry. **Exception:** tradeoff-free correctness fixes on records authored this session (typo, missing required field) may be fixed inline before the Phase 9 commit.

---

### ── EM resumes here (Sonnet doc-maintenance agent has returned) ──

The EM owns every phase below. Phase 12 exists at this seam *specifically because* it requires `Agent` dispatch, which only the EM can perform — and Phase 9's commit exists at this seam *specifically because* only the EM can commit. Run Phase 9 first, before Phase 12.

#### Phase 9 (executed here): Commit + Verify Remote

1. Run `CLAUDE_INVOKING_COMMAND=update-docs "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --blanket "docs maintenance"`
   (The post-commit hook will auto-push on work/feature branches.) This is the "Phase 9 commit" every phase from 9b through 11d refers to — it captures everything they wrote, since none of them committed on their own.
2. **Verify remote is synced:** `git log origin/$(git branch --show-current)..HEAD 2>/dev/null`
   If unpushed commits remain, push explicitly.
3. If push fails, **warn the PM explicitly**

#### Phase 12: Doc-link health check (plugin assets) — EM-LED

> **EM-only phase. The Sonnet doc-maintenance agent MUST NOT execute this — subagents cannot dispatch other subagents.** If you are the Sonnet doc-maintenance agent reading this: STOP at the end of Phase 11d and return to the EM. The EM dispatches `doc-link-checker` here, then runs Phases 11f through 11j (mechanical bash) and the Phase 13+ tail itself.

After the worker returns, read the report and surface counts in the Phase 14 rollup:
- Broken-link count (rows with `status: broken`)
- Anchor-missing count (rows with `status: anchor-missing`)
- Report path (so PM can read findings)
- Skip-cap notice if external-URL cap was hit

If the dispatch returns zero broken/anchor-missing items: report "Plugin doc-link health: clean."

The phase does NOT halt `/update-docs` on findings. Findings are informational; remediation is a separate workstream (queue entry or session-bound fix).

**Scope-path resolution (cwd-gated — do NOT hardcode `plugins/`).** The `plugins/` scope path below is a `~/.claude`-authoring assumption that does not hold in a consumer repo (no `plugins/` directory exists there). Resolve the scope path relative to the invoking repo before filling in the dispatch prompt:
- If the invoking repo root contains a top-level `plugins/` directory (the coordinator-plugin-authoring shape — DoE-claude or a `~/.claude` install), scope to `plugins/`.
- Otherwise (a consumer repo with no `plugins/` tree), scope to the invoking repo's own doc surface — e.g. the repo root, or its `docs/` + `coordinator.local.md`-declared doc paths if narrower scoping is warranted. Substitute the resolved path for `plugins/` in the dispatch prompt below.

**Pre-count gate — cheap check before paying for the worker.** Before dispatching, count occurrences of `[text](url)`-shaped markdown links across the resolved scope path's `{skills,agents,commands}/*.md` file filter. Below a low single-digit-per-file threshold (a handful of total hits across the whole scope), the corpus is not link-authoring in this form — this repo's house convention is prose-cited paths and `<path> § <section>` citations, already checked by the cheaper Phase 11h anchor-link check — so **skip the dispatch and report the skip**: "Plugin doc-link health: skipped — pre-count found N markdown-link occurrence(s) across the scope, below dispatch threshold; citations checked by Phase 11h instead." This is a gate, not a deletion — a consumer repo whose pre-count clears the threshold still gets the full worker dispatch below.

**Sidecar provisioning (EM's step, dispatch path only — never on the pre-count-gate skip path above).** `doc-link-checker` carries `Edit` but not `Write`/`Bash`-redirect for its deliverable (`agents/doc-link-checker.md` § Tools Policy, § DONE-After-Write Protocol) — its report lands via a single `Edit` into a pre-provisioned sidecar, never a self-authored `tasks/` path. Dispatching it via `Agent` auto-provisions `state/subagent-share/<session-id>/<provision_key>.md` at spawn and injects it into the brief as `sidecar_path:` (`subagent-sandbox-policy.yaml` — `coordinator:doc-link-checker` carries `provisioned-scaffold-precedence`); confirm the path landed in the brief before filling in the dispatch prompt below. This is why the report target below is "your provisioned sidecar," never a literal path the EM invents — inventing one here would silently regress to the same Write-shaped contradiction this seam exists to prevent.

**Dispatch prompt for doc-link-checker (only when the pre-count gate does not skip):**

```
Tier 1-3 attempted: tier 1 (architecture atlas / wiki) and tier 2 (project-RAG / query-records) do not validate markdown link health; tier 3 (grep) cannot resolve anchor existence; insufficient because mechanical link validation across 150+ plugin assets requires a worker with rate-limited WebFetch and anchor-resolution logic.

You are the doc-link-checker. Your scope for this dispatch:

Scope path: `<resolved scope path — see "Scope-path resolution" above; `plugins/` only when that directory exists at the invoking repo root, otherwise the invoking repo's own doc surface>`
File filter: `{skills,agents,commands}/*.md` (all plugins under the resolved scope path; recursive into plugin subdirectories)

Validate every internal markdown link (file existence + anchor existence) and every external URL (HEAD with redirect-follow, 1s sleep between requests, 100-URL cap). Use your standard output contract.

Edit your provisioned sidecar (the `sidecar_path:` in this brief) with the Structured Output Contract body, per your own DONE-After-Write Protocol. Never Write or Bash a report file yourself.

DO NOT run `gh pr merge`, `gh pr create` against main, or `git push origin main`.

Reply with `DONE: <path>` ONLY after your single `Edit` has landed in the provisioned sidecar. If you find yourself about to summarize the deliverable inline in your reply, STOP — the coordinator reads from disk, not chat. Inline summary without a written file counts as task failure.
```

#### Phase 11f: Parallel-review lens-orthogonality check

Asserts the four reviewers in the parallel-code-review skill's lens-domain manifest exist as agent files and have non-overlapping `lens_domain` values. Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/verify-parallel-review-lens-orthogonality"`

**On non-zero exit:** Surface the diagnostic to PM — do NOT auto-fix. A collision means the parallel-review carve-out's preconditions no longer hold (`coordinator/snippets/em-operating-doctrine.md` § How to Review What Came Back). Fix: rename the colliding lens domain or remove the reviewer from the parallel pool.

**On zero exit:** Report "Parallel-review lens-orthogonality: clean." Informational — does NOT halt `/update-docs`.

#### Phase 11h: Super-skill anchor-link check

Checks each `<path>.md § <section>` citation in the super-skill SKILL.md files against the headings of the file it names. Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/verify-skill-anchor-links"`

- **exit 0** — clean. Report "Super-skill anchor links: clean (N total, K qualified, U unresolved)." U is non-fatal by design but must be surfaced, not folded into "clean". Does NOT halt.
- **exit 1** — DEAD anchors. Surface to PM, do NOT auto-fix: repoint the citation, lift the section into the named file, or qualify it as global.
- **exit 2** — could not check; stderr names why. Surface as **coverage you do not have**, never as a finding or a clean run.

**Never collapse 1 into 2.** "Found nothing" and "looked at nothing" are different verdicts, and reading the second as the first is what let this gate no-op silently for a week in July 2026.

Exit 2 needs a *present and broken* `coordinator/doctrine-surfaces.json` (or an unresolvable root). **An absent manifest is NOT exit 2** — it is the normal mode, exiting 0/1 with alias citations recorded QUALIFIED. The manifest is a coverage upgrade, not a dependency; treating its absence as failure reintroduces the same incident from the other side.

#### Phase 11h2: Cross-reference coverage sweep

Walks the coordinator-claude plugin tree, extracts every `<plugin>:<name>` reference, `subagent_type:` assignment, and worker bullet under `## Worker Dispatch Recommendations` headers, and verifies each resolves to a real skill/agent/command on disk. External prefixes (`example-game-repo-control:*`, `superpowers:*`, etc.) are skipped.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/verify-coverage" --sweep-root "$(pwd)"`.

**cwd-gated by design.** `--sweep-root "$(pwd)"` scopes the reference sweep to the invoking repo's own doc surface, not the coordinator plugin tree (`--root` above stays the plugin tree — that's where skills/agents/commands are discovered from). Without this gate, a consumer repo running `/update-docs` walks DoE-claude's entire tree and HALTs on that repo's unrelated archival drift — a defect confirmed independently by two consumer repos (market-intel, claude-klabauter). `verify-coverage` also excludes `archive/` from the sweep by default now (joins `dist/`, `review-trail/`) — archived docs are historical records, not live dispatch references.

The script exits non-zero on any orphan reference. **This phase HALTS `/update-docs` on orphans** — retarget to the real artifact, add to `REF_ALLOWLIST` in claude-klabauter's `coordinator_core/ops/verify_coverage.py` with a rationale, or create the missing artifact.

**On orphans:** Report `Cross-reference coverage: N orphan(s) — /update-docs HALTED.` and stop. **On zero orphans:** Report "Cross-reference coverage: clean."

#### Phase 11i: Prune resolved-state bloat from queues

Aggressively strip resolved-state bloat and schema ceremony from the three queue files:
- Closure-log sections: `## Processed` / `## Resolved*` / `## History` / `## Closed` / `## Done` / `## Archive` / `## Closeout` — entire body stripped to next `##` heading.
- Entry-shape closure annotations (queue files only): any entry whose `resolution:` is not `pending`/`in_progress`, or which carries a `**Closeout:**` sub-line — entire entry deleted.
- Trivial schema ceremony (queue files only): `  recurring: 0`, `  resolution: pending`, `  resolution: in_progress` sub-lines — stripped, main line preserved.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/update-docs-probes" queue-prune-sweep`

**On non-zero exit:** Surface the file path and error output to the PM — do NOT skip. The pruner fails loud on unexpected structure and must not be bypassed.

**On zero exit with lines pruned:** Include the diff in the docs-maintenance commit (or a separate `chore(queues): prune resolved-state bloat` commit if large). Report pruned counts in the summary.

**On zero exit with no lines pruned:** Note in the report: "Queue prune: clean (no resolved bloat found)."

#### Phase 11j: Reap stale subagent-share sidecars

Named exception to `state/`'s never-swept posture (see § tasks/ vs state/ above): `state/subagent-share/<session-id>/*.md` sidecars of every identity-typed kind (run-report, review-findings, staff-eng-review, assessment/prior-art-checker/docs-checker/plan-coverage-checker spawns) are tracked deliverable docs, not ephemera, so a "cadence sweep of a known folder" gate on `status:` alone is wrong. Reap gate is **session liveness AND an age floor, plus a status carve-out — never `status:` in isolation** — same op and same guard `/workweek-complete` invokes; canonical full three-clause definition lives at `coordinator/commands/distill.md` § tasks/ vs state/ — aggressive sweep boundary (named exception) — read that, not a re-derivation here.

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/reap-stale-subagent-sidecars"`

**On non-zero exit:** Surface the file path and error output to the PM — do NOT skip.

**On zero exit with sidecars reaped:** Include the `git rm` deletions in the docs-maintenance commit (or a separate `chore(subagent-share): reap stale sidecars` commit). Report the reaped count in the Phase 14 summary.

**On zero exit with nothing reaped:** Note in the report: "Subagent-share sidecar reap: clean (nothing stale)."

#### Phase 13: Artifact Distillation (Conditional)

**Skip this phase if `--no-distill` was passed.**

Check whether accumulated artifacts warrant distillation into wiki documents:

1. **Count artifacts + check threshold:** run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/update-docs-probes" distill-threshold`

   The CLI counts artifacts across the distillation source directories (`docs/plans/`, `archive/handoffs/`, `archive/completed/`, `tasks/` at mindepth 2 — `state/` excluded by scope) and applies the fire/no-fire threshold — **fire if EITHER:** total count ≥ 50; OR last distillation >14 days ago (read from `state/distillation-log.md` — the canonical log per `schemas/distillation-log.schema.md § Path`; the formerly-cited `docs/wiki/.distill-log.md` never existed on disk); OR no log exists and count ≥ 20. Exit 1 means the threshold fired; exit 0 means not needed. The printed line already carries the count/reason.

   **Native op backing this cadence check:** `update-docs-probes distill-threshold` reads the
   same freshness signal claude-klabauter's `distill.curation_status --emit` op emits
   (`coordinator_core/ops/distill_curation_status.py`, `@register_op("distill.curation_status")`)
   — this is the op that killed the fictional `docs/wiki/.distill-log.md` read referenced above.
   Cite `distill.curation_status` (not a hand-rolled freshness read) when describing what this
   step consumes.

2. **If threshold met (exit 1):** Announce to PM: *"Artifact count is [N] / last distillation was [N] days ago. Chaining into `/distill`."* Then invoke `/distill` via the Skill tool. `/distill` Phase 4 is the PM approval checkpoint.

3. **If threshold not met:** Note in report: "Distillation: not needed (N artifacts, last run M days ago)."

#### Phase 14: Report

**Report by exception.** A ceremony summary is still an EM→PM reply and still owes the ≤200-word budget from global `CLAUDE.md § Communication Style` — a fixed block of 17 per-item status lines spends that budget on facts the PM can read off the commit, then gets measured as a verbosity violation by the Stop-hook altitude check. Print what needs a reader, not what needs a checkbox.

```
## Documentation Update Summary

**Synced:** [N] doc(s) updated (tracker, indexes, plans, memory, lessons, CLAUDE.md, handoffs, artifact pruning, completion archive, repomap, preamble/callout sync) — see commit for detail
**Pushed:** yes (branch) / no (reason)
```

Then append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Plugin Doc-Link Health:**` | N broken link(s) found (name the path(s)), or the check was skipped (cap) — omit when clean |
| `**Architecture Atlas:**` | drift findings, a RAG-staleness banner, or a quarterly drift-risk note fired this run — omit when clean |
| `**Frontmatter Schema Drift:**` | N ≥ 1 violations found (include top offenders per schema, per Phase 11d wording) or the sweep errored — omit at 0 violations |
| `**Distillation:**` | the threshold fired and `/distill` was chained — omit when "not needed" |
| `**Cross-Repo Registry:**` | N candidate(s) unreachable, or the phase was skipped (cwd-gated out) — omit when all verified |

**Negative-spec — these are gone, do not restore them.** `Project Tracker`, `Source Indexes`, `Plan Documents`, `Memory`, `Lessons`, `CLAUDE.md`, `Handoffs Archived`, `Artifact Pruning (Phase 8b)`, `Completion Archive`, `Repomap`, and `Preamble Sync, Query Callouts` are no longer printed as their own lines at all. Each was a count or a file list of work the ceremony's own commit already records, with no PM decision attached; their absence is not a signal the corresponding phase was skipped — the phases still run, and `git show` is their record. A future reader must not re-add them "for completeness": completeness of the *ceremony* is the assembler's job, completeness of the *report* is not the same thing.

#### Phase 15: Cross-Repo Registry Refresh (cwd-gated, EM-only)

**Skip if `pwd` is not `~/.claude`.** Per-project runs skip with: *"Phase 15: skipped — not running from ~/.claude."* **EM-only** — the Sonnet agent does NOT execute this phase; if it reaches Phase 15, it logs `"Phase 15 is EM-only — deferring to coordinator"` and exits.

Read `${CLAUDE_PLUGIN_ROOT}/pipelines/update-docs/cross-repo-registry-refresh.md` and follow all steps exactly.
