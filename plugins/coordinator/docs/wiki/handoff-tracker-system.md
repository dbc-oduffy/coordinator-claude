# Handoff Tracker System

> Purpose: Documents the architecture, data model, and operating conventions for the disposable
> markdown handoff tracker rendered by `bin/render-handoff-tracker.js`.
>
> Spec backlink: docs/plans/2026-05-29-handoff-tracker-system.md
>
> Back-citations:
>   - coordinator/CLAUDE.md § Live Queries vs. Scaffolded Indices (why no hand-maintained table)
>   - docs/wiki/workday-workweek-cadence.md "Handoffs are the atom; the week-changelog is the index"
>   - docs/wiki/completion-log-release-loop.md § Phase 2 (canonical archive glob for archive reads)

---

## Architecture

### Query-records as spine — disposable markdown render

The tracker does NOT maintain a hand-written markdown table. That would require agents to keep
the file consistent with the source files it describes — the classic scaffolded-index maintenance
trap documented in coordinator/CLAUDE.md § Live Queries vs. Scaffolded Indices. Instead:

1. `bin/query-records` reads frontmatter from `tasks/handoffs/*.md`, `tasks/handoffs/spinoffs/*.md`,
   and `cross-repo/*.md` on demand.
2. `bin/render-handoff-tracker.js` calls the query engine, formats the results as a markdown table,
   and writes a **disposable** file that is regenerated on every invocation.

The rendered file at `tasks/handoff-tracker.md` is a **snapshot, not a source of truth**. Never
hand-edit it — edits are silently overwritten on the next render.

### Output paths

| Mode | Output path | Trigger |
|------|-------------|---------|
| Per-repo | `<repo-root>/tasks/handoff-tracker.md` | `/session-end`, `/handoff`, `/workday-start` |
| DoE (all repos) | `~/.claude/tasks/doe-handoff-tracker.md` | `/session-start` (coordinator meta-repo), ad-hoc `--all-repos` |

`tasks/handoff-tracker.md` is **lazily created on first render** — no manual scaffolding
needed. The renderer ships with the coordinator plugin and creates the file automatically the
first time any session-boundary skill (session-end, handoff, workday-start) runs.

`doe-handoff-tracker.md` aggregates all repos registered in machine-local `repos.*` keys.
Repos absent on disk are skipped with a note in the output. It uses the same machine-local
path source as `cross-repo-memo`'s receiver-resolution model — not `repo-registry.md`'s
active-block (which is a prior-art lookup aid, not a path source).

---

## Category Taxonomy

The `category` frontmatter field provides coarse routing signal for query-records filters and
the tracker's visual grouping. All values map to the `handoff.yaml` schema enum.

| Value | Meaning |
|-------|---------|
| `roadmap` | Feature work tracked in the roadmap graph (spinoff-roadmap handoffs, sprint items) |
| `infra` | Build system, tooling, plugin, CI, deployment, install-surface work |
| `bug` | Defect investigation and fix workstreams |
| `docs` | Documentation updates, wiki authoring, onboarding content |
| `research` | Deep-research pipelines, experiments, discovery work |
| `refactor` | Code restructuring, cleanup, migration without new behaviour |
| `uncategorized` | Null-object sentinel for legacy handoffs backfilled by the normalizer when no category can be inferred. New handoffs should pick one of the six meaningful values, not this. |

`category` is **optional** in the schema (legacy handoffs without it still pass validation).
When absent, the tracker renders the row without a category badge; `query-records` filters on
`category=X` skip unset entries.

**Spinoff-roadmap clarification:** A `kind: spinoff-roadmap` handoff carries roadmap graph
primitives (`tc_id`, `roadmap_id`, `blocked_by`). It appears in the **daily tracker** as a
handoff row — with those columns rendered — because it IS a handoff (a session-continuity
artifact). The roadmap plan document and sprint alignment reviews stay in the **weekly**
ceremony. The daily/weekly split is by **artifact type** (handoffs/spinoffs/memos vs. plans),
not by strategic-ness. A roadmap spinoff is strategically significant but temporally a handoff.

---

## Workstream Sequence Count Semantics

The tracker renders a `seq` column that shows **N of M in workstream** for handoffs that
belong to a named workstream.

- **"N of M"** — this handoff is the Nth in a chain of M total handoffs sharing the same
  `workstream:` frontmatter value. M is the count of all (active + archived) records in
  that workstream. Useful for gauging how long a chain has run.
- **Standalone row** — when `workstream:` is null or absent, the `seq` column renders `—`.
  No sequence inference is attempted.
- **Archive read is count-only** — `archive/completed/*/*.md` records are read to establish
  M (the total chain depth) but never rendered as tracker rows. The tracker surface shows
  only active/in-flight handoffs; the archive contributes to context only. Archive glob is
  `archive/completed/*/*.md` per completion-log-release-loop.md § Phase 2.

---

## Daily vs. Weekly Split

The renderer queries two artifact types on different cadences to keep the daily view
signal-dense and the weekly view structurally complete.

### Daily tracker — handoffs, spinoffs, cross-repo memos

Queried and rendered by `/session-end`, `/handoff`, `/workday-start`:

- Active `tasks/handoffs/*.md` records (kind: session-handoff, spinoff, spinoff-roadmap, recovery)
- Active `tasks/handoffs/spinoffs/*.md` records (if the spinoffs directory exists)
- Inbound `cross-repo/*.md` memos with `status: pending` or `status: active`

The daily view answers: **"what is in flight right now?"**

### Weekly tracker — plans (via workweek-complete only)

Plan documents (`docs/plans/*.md`) are **out of scope for the daily tracker**. Per
workday-workweek-cadence.md: "Handoffs are the atom; the week-changelog is the index over
them." Plans are structural artifacts, not flight-state — they belong to the weekly gate
review (`/workweek-complete` Step 7), not the per-session snapshot.

---

## Fail-Loud Parse Errors

When the renderer encounters a frontmatter parse error in a handoff file, it emits a
**`PARSE ERROR`** row in the tracker table rather than silently skipping the file. The row
contains the file path and the error message so the operator can fix the source file.

This is by design — a tracker that silently omits malformed handoffs gives a false "clean"
signal on what is in flight. Fail-loud parse errors are preferable to silent gaps.

---

## The Normalizer

`bin/normalize-handoff-frontmatter.js` is a companion tool that backfills `category` and
`summary` on handoffs that predate the schema extension.

Operating rules:
- **Active-only by default** — only processes `tasks/handoffs/` (not the archive).
  Archived handoffs are immutable records; backfilling them changes the historical record
  without benefit.
- **Dry-run is the default** — invoke with `--write` to apply changes. Without `--write`,
  the tool reports what it would change without touching any file.
- **Non-destructive** — only adds missing fields; never overwrites existing values.

### Running ad-hoc

```sh
# Dry-run (preview only):
node ~/.claude/plugins/coordinator/bin/normalize-handoff-frontmatter.js

# Apply:
node ~/.claude/plugins/coordinator/bin/normalize-handoff-frontmatter.js --write

# Against a specific repo root:
node ~/.claude/plugins/coordinator/bin/normalize-handoff-frontmatter.js \
  --root /path/to/repo --write
```

---

## Running the Renderer Ad-Hoc

```sh
# Per-repo (outputs to tasks/handoff-tracker.md in git toplevel):
node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js

# Preview to stdout (no file written):
node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js --stdout

# DoE mode (all repos from machine-local, writes ~/.claude/tasks/doe-handoff-tracker.md):
node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js --all-repos

# Against a specific repo root:
node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js \
  --root /path/to/repo
```

---

## Edit-Resistance — the tracker is a render, not a source

Both tracker files are GENERATED from handoff frontmatter. A hand-edit is overwritten on the
next render and, if committed first, masquerades as source. Two complementary guards make them
edit-resistant — both offer-shaped (overridable by intent), since the next render corrects any
edit anyway:

- **Agent-side (automatic):** the `block-tracker-edit.sh` PreToolUse hook DENIES Claude's
  Write/Edit/MultiEdit/NotebookEdit on `tasks/handoff-tracker.md` and `tasks/doe-handoff-tracker.md`,
  redirecting to "edit the handoff frontmatter and re-run the renderer." Ships with the plugin;
  no per-project setup. Override: `COORDINATOR_OVERRIDE_TRACKER_EDIT=1`. Registry: `coordinator-tripwires.md`
  (`BLOCK-TRACKER-EDIT`). The renderer's own write is a `node` Bash call, not a Write/Edit tool,
  so it is unaffected.
- **Editor-side (per-project):** `ensure-vscode-readonly.sh` merges `files.readonlyInclude`
  globs into `.vscode/settings.json`, so VS Code (and forks honoring that key) open the files
  read-only and refuse to save. Wired into project-onboarding Phase 3f.6; idempotent; skips loudly
  if the file is JSONC. Per-file override: VS Code "Set Active Editor Writeable".

To change what the tracker shows, edit the relevant handoff's frontmatter (`category` / `summary`
/ `deployment_state`) and re-run the renderer.

---

## Negative-Spec

- The tracker IS committed to its own repo (durable, diffable, pushed as crash-insurance —
  like `tasks/orientation_cache.md`); `/session-end`, `/handoff`, and `/workday-start` refresh
  and commit it. It is NOT hand-edited — the renderer owns its content (see § Edit-Resistance).
- The renderer does NOT archive, move, or mutate any handoff or memo file.
- The renderer does NOT glob handoff files directly — it calls `query-records` to benefit
  from `applyConsumedMarker` logic and correct completion-pruning.
- `tasks/handoff-tracker.md` and `~/.claude/tasks/doe-handoff-tracker.md` are NOT published
  to consumer repos via `setup/publish.sh` — they are per-repo session state.
