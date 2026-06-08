---
name: repo-setup
description: "First-time repo setup (default: single-repo), or `--batch` for fleet setup over working-repos.yaml. Consolidates /project-onboarding and /bootstrap-repos into one surface."
description-budget: 175
version: 1.0.0
---

# Repo Setup

## When to Use

- Starting work in a new project repository for the first time
- `/update-docs` reports `tracker_missing` — the project lacks coordination infrastructure
- PM asks to set up project tracking in an existing repo
- **Marketplace first-run** — new coordinator plugin user setting up their first project

## Flag contract

- **Default (no flag) — single-repo interactive.** Runs from inside one repo's cwd. PM-present; asks the 3 cold questions when needed; full Phase 1 → Phase 4 flow as documented below.
- **`--batch` — fleet non-interactive.** Reads `~/.claude/working-repos.yaml` and loops the single-repo flow per repo. Phase-2 cold-asks substituted by detected defaults (Phase 1 marker scan + Phase 1.5 substrate) OR skipped via lazy-creation discipline when the target artifact already exists. See § Batch Mode below.
- **`--check-only` and `--non-interactive` are batch-mode-only.** If passed to the default single-repo mode (without `--batch`), the skill exits with the one-line remediation: `"--check-only and --non-interactive are only valid with --batch; for non-interactive single-repo setup, set coordinator.local.md first and re-run /repo-setup."` This is the AC12 binding from `docs/plans/2026-06-08-repo-setup-consolidation.md`. Per `docs/wiki/coordinator-tripwires.md` § Detect-then-fail-loud — never silently pick a meaning for an ambiguous flag combination.

## Batch Mode (--batch)

Batch mode runs fleet-wide setup non-interactively. Intended for PM use from `~/.claude` against all repos in the fleet.

**Driver:** delegates to `lib/bootstrap-orchestrate.sh` for the per-repo loop (repointed to drive this consolidated skill in non-interactive mode — see C3a commit).

**Per-repo flow:**

1. Reads `~/.claude/working-repos.yaml`, normalizes paths, filters to repos on disk (repos not on disk are counted as `not-on-disk` in the summary table and skipped).
2. For each on-disk repo: dispatches the single-repo phases (Phase 1, 1.5, 3, 3g, 4) in non-interactive mode.
3. **SKIPS Phase 2 cold-asks.** Cold-asks are substituted by detected defaults from Phase 1's marker scan + Phase 1.5 substrate profile. When the target artifact already exists (e.g. `CLAUDE.md` present), lazy-creation discipline applies — no overwrite, no re-ask.

**Idempotency:** a re-run on a fully-bootstrapped fleet (all repos have `docs/coordinator-currency.yaml` matching current schema) exits 0 with per-repo "already current" rows and zero writes. The currency stamp is the load-bearing idempotency primitive — already-current stamps short-circuit Phase 3/3g for that repo.

**Hook-respect:** target-repo commit hooks run normally (no `--no-verify`); a hook failure surfaces the repo as failed and the overall run exits non-zero.

**Summary table** printed at end of run (columns: repo path / status / writes):

| Repo | Status | Notes |
|------|--------|-------|
| `/x/some-repo` | succeeded | currency stamp updated |
| `/x/other-repo` | already current | 0 writes |
| `/x/missing-repo` | not-on-disk | skipped |
| `/x/hook-fail-repo` | failed | post-commit hook exited non-zero |

Overall exit code: 0 if all on-disk repos succeeded or were already current; non-zero if any failed.

AC4, AC6, AC10 bind this section. AC9 binds the lib/detect-onboarding-offer.sh emitting `/repo-setup` (single-repo form, no flags) — never `/repo-setup --batch` in the per-repo offer (batch mode is PM-from-~/.claude, not per-repo), and never with a `--refresh` flag (the command is idempotent; re-running `/repo-setup` on a stale repo re-stamps currency).

## Prerequisites

- You are in the project's working directory (not `~/.claude`)
- PM is available for 3 questions (Step 2)

## Phases

### Phase 1: DETECT — Survey Existing State

Before scaffolding, check what already exists. **Never overwrite existing files.**

Check for each of these and record status (exists / missing / incomplete):

```
├── CLAUDE.md                           — project conventions
├── docs/README.md                      — documentation index (wikis, research, specs, reference)
├── docs/project-tracker.md             — workstream tracking
├── docs/wiki/                          — wiki guides (LAZY — created by coordinator:distill on first guide extraction)
├── docs/wiki/DIRECTORY_GUIDE.md        — guide index with decision record mapping
├── docs/plans/                         — implementation plans (LAZY — created when first plan is copied from ~/.claude/plans/)
├── docs/research/                      — research outputs (LAZY — created by deep-research:research on first run)
├── state/lessons.md                    — engineering patterns (LAZY — created by coordinator:workstream-complete on first lesson)
├── archive/completed/                  — completion archive (LAZY — created by coordinator:workstream-complete on first completion)
├── state/handoffs/                     — session continuity (LAZY — created by coordinator:handoff on first handoff)
├── CONTEXT.md                          — domain glossary (LAZY — never scaffold; produced when first term is resolved)
├── DIRECTORY.md                        — source index
└── .gitignore                          — check for .claude/settings.local.json entry
```

**If `docs/project-tracker.md` already exists:** This skill becomes a health check — verify the format matches the standard template, flag deviations, and skip to Phase 4 (REPORT).

**Global detection:** Check if `~/.claude/CLAUDE.md` exists. If yes, the generated CLAUDE.md will include an "extends global" reference. If not, the template is fully self-contained — no dependency on global config.

**Repo classification (PM ask):** Check if `.gitignore` excludes session infrastructure directories (`tasks/`, `archive/`, `state/handoffs/`). Capture this as a hint string — do not make a decision from it:

- 2+ of these are gitignored → hint = `_(detected: 2+ of 3 session dirs gitignored — looks like a distribution repo)_`
- Fewer or none gitignored → hint = `_(detected: standard working-tree layout)_`

Always ask the PM:

> **Is this repo:**
> - **(a) a working repo** — for active development, with session artifacts tracked
> - **(b) a published artifact / template** — distributed for downstream consumers; no session infrastructure
> - **(c) both** — a working repo that publishes itself as the artifact
>
> _(detected: {hint})_

**Branch on the PM's answer:**

- **(a)** → proceed to Phase 1.5 / Phase 2 unchanged. No injection.
- **(b)** → STOP. Do not proceed to Phase 2. Report:
  > _"You answered (b) — distribution repo. Onboarding infrastructure doesn't belong here. Track work on this repo from your parent project's tracker instead."_
- **(c)** → proceed exactly like (a), AND inject a one-line note in the generated CLAUDE.md (Phase 3a) and the generated tracker (Phase 3b):
  > _"This repo is published as its own working artifact — consumers see the full directory shape including `tasks/` and `archive/`."_

Report what exists and what needs to be created before proceeding.

**Project type short-circuit:** Check if `coordinator.local.md` exists at the repo root:

```bash
test -f coordinator.local.md && echo "exists" || echo "missing"
```

If it exists, read it and capture `project_type` and `project_subtypes` (if present). Emit a one-line confirmation:

> Project type: {type}{ +subtypes: [{subtypes}] if any}. From coordinator.local.md — skipping Phase 2 question 2.

If `coordinator.local.md`'s `project_type` differs from the `detected_type` derived from the marker scan, append this one-line challenge immediately after the confirmation (PM remains authoritative — this is informational only, not a re-ask):

> *`coordinator.local.md` says `{type}` but detected stack is mostly `{detected_type}` — keeping the file value (PM authoritative). If wrong, edit `coordinator.local.md` and re-run.*

If `coordinator.local.md` is missing, proceed to Phase 2 question 2 (cold-ask) as normal.

Also check for legacy values in the file: if `project_type` is `unreal`, `meta`, or bare `web`, emit a one-line warning with the migration hint (e.g. `unreal` → `project_type: game-dev` + `project_subtypes: [unreal]`). Do not auto-rewrite.

**Runtime marker scan:** Run `bash "$HOME/.claude/plugins/coordinator/bin/detect-project-runtime.sh"` and capture the output. Show to PM in Phase 2 above question 2 as `_(detected stack: <one-line summary>)_`. PM's answer is authoritative; detection is sanity-check only. Output is advisory stdout — no skill/agent/hook reads it programmatically (adding a consumer requires a separate plan per `archive/specs/2026-05-06-detect-project-runtime.md`).

**Derived type from markers:** Once the marker scan returns, derive a `detected_type` (and `detected_subtypes` if applicable) using these rules, in priority order:

- `*.uplugin` or `*.uproject` present → `detected_type: game-dev`, `detected_subtypes: [unreal]`
- `package.json` + any of `next.config.js`, `vite.config.*`, `nuxt.config.*`, `svelte.config.*`, `remix.config.*` present → `detected_type: web-dev`
- `requirements.txt` or `pyproject.toml` present (and no UE markers) → `detected_type: data-science`
- `Cargo.toml`, `go.mod`, or none of the above → `detected_type: general`

Capture these as part of the Phase 1 profile. If `coordinator.local.md` already exists and its `project_type` differs from `detected_type`, emit a one-line challenge inline in the Phase 1 report (see **Project type short-circuit** block above for the exact wording).

### Phase 1.5: INVESTIGATE — Read substrate, draft proposals

Skip when Phase 1 found a genuinely empty repo (no README, no CONTRIBUTING, no top-level manifest).

**Substrate-first onboarding.** Read the project's accumulated institutional memory before asking the PM cold: `README.md`, `CLAUDE.md`, `state/lessons.md`, `state/improvement-queue.md` if present (1.5a); most-recent 5 handoffs for stack/tooling clues if `state/handoffs/` exists (1.5b); sibling `CLAUDE.md` files for stack-shared conventions via `~/.claude/state/repo-registry.md` `stack_tags` (1.5c). Output: a 5–10 line substrate snapshot. Cold-ask is the fallback when substrate is empty.

**Roadmap orientation (run immediately after the substrate snapshot):** Query the completed archive for recent roadmap items — especially valuable when joining cold.

```bash
"$HOME/.claude/plugins/coordinator/bin/query-records.sh" --type completion --since "90d" --where "nature=roadmap" \
  --sort "-loe.tshirt" --limit 10 --format markdown-list
```

Render under `#### Recent roadmap (last 90d, top-10 by size)` in the Phase 4 REPORT (count-always per `docs/wiki/orientation-surfacing-doctrine.md`; `(none)` is expected on new repos). Otherwise:

1. Read top-level `README.md` / `README.rst` / `README.txt` if present.
2. Read `CONTRIBUTING.md` if present.
3. Read top-level manifests: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `*.uplugin`, `*.uproject`, etc. — whichever exist.
4. Skim recent commit subjects: `git log --oneline -20`.

Draft proposals from what you read:

- **Project name** — from README H1 or repo directory name.
- **Project type + subtypes** — from manifest signals + README role description, reconciled with Phase 1 runtime-marker output. If proposal differs from `detected_type`, surface both with proposal winning and emit:

  > *Detected stack suggests `{detected_type}`. README/manifests suggest `{proposed_type}`. Going with `{proposed_type}` — confirm or override.*
- **Initial workstreams (1-3)** — derived from README "what this does" + recent commit subjects + any "Roadmap" / "TODO" / "Status" sections. If the repo names sibling repos (path on disk, GitHub URL, or "split" / "addon" / "upstream" / "downstream" language), capture each as `peer_repo_candidates`.

Present proposals to the PM for ratification:

> Before I scaffold, here's what I found:
>
> **Project name:** {proposed}
> **Project type:** {proposed}{, subtypes: [...] if any}
> **Workstreams (proposed):**
> 1. {WS1} — {2-3 deliverables}
> 2. {WS2} — {...}
>
> **Sibling repos referenced:** {list with file:line citations from README/CONTRIBUTING}
>
> Ratify, correct, or say "go cold" to skip this and ask from scratch.

On ratification: skip Phase 2's name + workstreams questions; only ask if PM corrected something or said "go cold."

On peer-repo presence: ask once whether to dispatch parallel Explore scouts (recommended). If yes, dispatch each with: *"Read README, CONTRIBUTING, and recent commits. Identify shared schemas, integration contracts, and shipped vs in-flight work relevant to {this repo's name}. Reply with file:line citations."* Wait for results before drafting tracker workstreams.

### Phase 2: ASK — PM Input

**Skip questions Phase 1.5 already ratified. Phase 1.5 may have already pinned project name and/or workstreams; only ask the questions whose answers are still missing.** **If `coordinator.local.md` was found in Phase 1**, skip question 2 — project type already pinned. Ask:

> **1. Project name** — short name (e.g., "Geneva MVP", "DroneSim")
> **2. Initial workstreams** (1-3) — name, 2-3 deliverables, optional deps/blockers. Say "stubs" for placeholders.

**If `coordinator.local.md` was NOT found** (cold-ask path), present all three:

> **1. Project name** — short name (e.g., "Geneva MVP", "DroneSim")
> _(detected stack: <one-line summary>)_
> **2. Project type:**
>    - `game-dev` — Game development (adds the Game Dev Reviewer reviewer, game-dev domain agents)
>    - `web-dev` — Web frameworks (adds the Front-End Reviewer for front-end review, the UX Reviewer for UX)
>    - `data-science` — Notebooks, pipelines (adds the Data Science Reviewer reviewer)
>    - `general` — Standard conventions only
> **3. Initial workstreams** (1-3) — name, 2-3 deliverables, optional deps/blockers. Say "stubs" for placeholders.

Wait for PM response before proceeding.

### Phase 3: GENERATE — Create Missing Files

Create only what's missing. Use the templates in this skill's `templates/` directory as the base.

#### Lazy-creation discipline

Only scaffold files that have **meaningful day-1 content**. A placeholder header trains agents to ignore the directory; empty scaffolding has zero signal value. Create files and directories only when there is a real artifact to write.

**Audit verdict — Phase 3 scaffold items:**

| Item | Verdict | Reasoning |
|------|---------|-----------|
| `CLAUDE.md` | EAGER | Project conventions apply immediately; filled in Phase 2 |
| `docs/project-tracker.md` | EAGER | Workstreams established in Phase 2; real content on day 1 |
| `docs/README.md` | EAGER | Structural index with project name, pointers to plans/research/wikis |
| `.gitignore` entry | EAGER | Prevents accidental credential commits from first commit onwards |
| Post-commit hook | EAGER | Auto-push crash insurance is needed from the very first commit |
| `cross-repo/` dir | EAGER (contract-bearing) | Inbound cross-repo memo channel — sibling EMs address this repo's `cross-repo/` by name; must exist before any memo arrives. Scaffolded with `README.md` (real content, not `.gitkeep`) by `scaffold-canonical-structure.sh`. Schema: `cross-repo-memo`. Source of truth: `canonical-structure.yaml`; plan: `docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Lazy-vs-eager reconciliation`. |
| `state/lessons.md` | LAZY | Header + comment only; no lessons exist until first session runs |
| `state/handoffs/` dir | LAZY | No handoffs until first session ends via `/handoff` |
| `state/handoff-tracker.md` | LAZY (render) | Per-repo handoff tracker. **Never scaffold manually** — lazily created on first render by `bin/render-handoff-tracker.js`. Edit-resistance: two layers (agent hook + editor guard, both wired automatically). → `docs/wiki/handoff-tracker-system.md` § Edit-Resistance |
| `archive/completed/` dir | LAZY | No completed work until first work item ships |
| `docs/wiki/` dir | LAZY | Wiki guides come from `/distill` after artifacts accumulate |
| `docs/plans/` dir | LAZY | Plans come from plan mode; none exist on day 1 |
| `docs/research/` dir | LAZY | Research outputs come from `/deep-research` pipelines |
| `state/review-trail/` dir | LAZY | Review records written by `/workstream-complete` and `/handoff` |

LAZY items are NOT created here. Each has a designated "create on first use" owner noted in its section below.

#### 3a. CLAUDE.md (if missing)

Use `templates/CLAUDE.md.template` via `render-template.sh`. Construct three substitution values before calling the helper:

1. **`GLOBAL_EXTENDS_LINE`** — `Extends global \`~/.claude/CLAUDE.md\`.` if that file exists; else `""`.
2. **`PROJECT_TYPE_BLOCK`** — concatenated per-type convention section bodies (one per selected type, blank line between). Full block bodies for `game-dev`, `web-dev`, `data-science`, and multi-type rules: → [`docs/wiki/repo-setup-claude-md-render.md`](../../docs/wiki/repo-setup-claude-md-render.md). `general` type: empty string.
3. **Render helper call + runtime conventions population:** → same wiki § Render Helper Call and § Runtime Conventions Section.

Use absolute `$HOME`-anchored paths. Leave `<!-- Fill in -->` comments as-is.

#### 3b. docs/project-tracker.md (if missing)

Use `templates/tracker.md.template`:

1. Replace `[PROJECT_NAME]`, `[DATE]` (today), `[YEAR]`, `[MONTH]`
2. Replace `[WORKSTREAMS]` with formatted workstream blocks from PM input:

For each workstream the PM provided:
```markdown
### N. [Workstream Name]
**Status:** Ready
**Specs:** <!-- link when spec is written -->

- [ ] [Deliverable 1]
- [ ] [Deliverable 2]
- [ ] [Deliverable 3]
```

If PM said "stubs": create one placeholder workstream:
```markdown
### 1. [Define workstreams]
**Status:** Ready

- [ ] _PM: Define initial workstreams and deliverables_
```

#### 3c. state/lessons.md — SKIP (lazy)

Do NOT create this file during onboarding — no meaningful day-1 content. Created by `coordinator:workstream-complete` on first lesson capture.

#### 3d. docs/README.md (if missing)

Create `docs/README.md` — the documentation index maintained by `/update-docs`. Structure:

```markdown
# [Project Name] — Documentation Index

Central entry point for all project documentation. Maintained by `/update-docs`.

---

## Wikis and Guides
→ **[`docs/wiki/DIRECTORY_GUIDE.md`](guides/DIRECTORY_GUIDE.md)** — full guide index
_No guides yet. Created by `/distill` as knowledge accumulates._

---

## Plans
→ [`docs/plans/`](plans/) — plans start in `~/.claude/plans/`, copied here on approval.

---

## Research
→ [`docs/research/`](research/) — `/deep-research` outputs; key findings extracted by `/distill`.

---

## Reference Documentation
| Doc | Purpose |
|-----|---------|
| [project-tracker.md](project-tracker.md) | Active workstreams and priorities |

---
*Last updated: [DATE]. Maintained by `/update-docs`.*
```

Replace `[Project Name]` and `[DATE]` with the appropriate values.

#### 3e. Directories

Only create directories with real day-1 content or referenced by files being written in this phase:

```bash
mkdir -p docs   # for project-tracker.md (3b) and README.md (3d)
```

**Scaffold contract-bearing directories and the full `state/` skeleton** by invoking `scaffold-canonical-structure.sh`. This is idempotent — safe to re-run; never clobbers existing content:

```bash
# Resolve scaffold script from the coordinator plugin location, not cwd.
_scaffold_script="$HOME/.claude/plugins/coordinator/bin/scaffold-canonical-structure.sh"
# Pass --root explicitly so the scaffold targets the project repo, not the coordinator plugin root.
bash "$_scaffold_script" --root "$(pwd)"
```

The script reads `canonical-structure.yaml` and for every `creation: eager` directory entry either:
- Creates the directory with a `README.md` (for contract-bearing dirs with `readme:` content, e.g. `cross-repo/inbox/`)
- Creates the directory with a `.gitkeep` sentinel (for `gitkeep: true` dirs — the full `state/` subdirectory skeleton and `tasks/`)

The full skeleton produced on a fresh repo:

```
state/
  handoffs/.gitkeep
  review-trail/.gitkeep
  week-changelog/.gitkeep
  memos/.gitkeep
  cross-repo-declarations/.gitkeep
  cross-repo-outbound/.gitkeep
  reviews/.gitkeep
  review-findings/.gitkeep
  roadmap/.gitkeep
  audits/.gitkeep
  recovery/.gitkeep
  scratch/deep-architecture-survey/.gitkeep
  scratch/bug-blitz/.gitkeep
  scratch/artifact-distillation/.gitkeep
tasks/
  .gitkeep
cross-repo/
  inbox/README.md   (schema-documenting; inbound memo channel)
```

**Idempotence:** re-running on a repo where these directories already have populated content is a no-op — the `.gitkeep` check skips dirs that contain any real files.

**Tracker files are NOT pre-created** (`state/lessons.md`, `state/orientation_cache.md`, `state/handoff-tracker.md`, etc.) — they are written lazily by their owning skills on first use (see table above). Pre-creating empty tracker files trains agents to ignore the directory; empty scaffolding has zero signal value.

#### 3f. .gitignore handling

Ensure `.gitignore` contains the canonical block (per `docs/wiki/gitignore-policy.md`):

```
# Machine-specific Claude settings (do not commit)
.claude/settings.local.json

# Scratch — transient agent output, investigation notes, workstream byproduct.
# `scratch/` matches at any depth (top-level scratch/, tasks/scratch/, etc.)
scratch/
tasks/_*.log
```

Procedure:

1. **If `.gitignore` doesn't exist:** Create it with the canonical block above.
2. **If `.gitignore` exists but is missing any of the three rules:** Append only the missing rules under a single comment header (`# Coordinator universal — scratch + machine-local settings`).
3. **If all three rules are present:** Skip silently.

**Warning checks:**

- If `.gitignore` ignores all of `.claude/` (`.claude/` or `.claude/*`), warn: only `.claude/settings.local.json` needs ignoring.
- If tracked content exists under `scratch/` or `tasks/_*.log`, surface count and offer `git rm --cached -r` cleanup (confirm with PM first — don't auto-untrack).

#### 3f.5. Auto-push post-commit hook

Check for `.git/hooks/post-commit`. If absent, install one that delegates to the canonical helper (SSH remotes on Windows → PowerShell; HTTPS → git directly):

```bash
cat > .git/hooks/post-commit <<'HOOK'
#!/bin/bash
# Auto-push to remote on work/* or feature/* branches — crash insurance.
# Delegates to coordinator-auto-push helper.
exec "$HOME/.claude/plugins/coordinator/bin/coordinator-auto-push"
HOOK
chmod +x .git/hooks/post-commit
```

If the repo already has a post-commit hook (e.g. Git LFS prefix), preserve the existing block(s) and append the helper invocation backgrounded:

```bash
# === Auto-push (crash insurance) ===
( "$HOME/.claude/plugins/coordinator/bin/coordinator-auto-push" ) &
exit 0
```

Skip if a custom auto-push hook already exists and the PM has signed off on it.

Then harden this repo's git config against two concurrent-EM Git-for-Windows failure modes (see `docs/wiki/concurrent-em-hazards.md` § H21–H22): `gc.autoDetach false` so git's auto-maintenance runs synchronously instead of detaching into a background process that can orphan the index lock, and `core.checkStat minimal` so the index comparison ignores the NTFS-unstable `ctime/ino/dev` fields that cause a phantom-dirty tree under concurrent index rewrites:

```bash
"$HOME/.claude/plugins/coordinator/bin/coordinator-configure-git"
```

Idempotent — safe to re-run; a no-op if already hardened.

#### 3f.6. VS Code read-only guard for generated trackers

Mark the generated handoff tracker renders read-only in VS Code (and forks that
honor `files.readonlyInclude`) so a human does not accidentally hand-edit a file
the renderer overwrites. This is the editor-side complement to the agent-side
guard (the `block-tracker-edit.sh` PreToolUse hook, which ships with the plugin
and needs no per-project setup). Idempotent — merges two globs into
`.vscode/settings.json` without clobbering existing settings:

```bash
bash "$HOME/.claude/plugins/coordinator/bin/ensure-vscode-readonly.sh" --root "$(pwd)"
```

The helper skips loudly if `jq` is absent or `.vscode/settings.json` is JSONC
(comments/trailing commas) — in that case the report should note the two keys to
add by hand (`files.readonlyInclude` → `"**/state/handoff-tracker.md": true`,
`"**/state/doe-handoff-tracker.md": true`). Offer-shaped, not a hard lock: a user
can still override per-file via VS Code's "Set Active Editor Writeable".

#### 3g. DIRECTORY.md

Do NOT create this file directly — requires source file analysis handled by `/update-docs` Phase 2. Note in the report that the PM should run `/update-docs`.

### Phase 3g. Currency stamp (ALWAYS — idempotent)

<!-- spec-backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1 -->

Record which `COORDINATOR_SCHEMA_VERSION` this project was onboarded against. Idempotent —
safe to re-run; overwrites only when the schema version has been bumped since the last stamp.

Skip for distribution repos (answer (b) from Phase 1). Apply for working repos ((a) and (c)).

Resolve `CLAUDE_PLUGIN_ROOT` as the coordinator plugin root (e.g. `~/.claude/plugins/coordinator-claude/coordinator`):

```bash
source "${CLAUDE_PLUGIN_ROOT}/lib/coordinator-currency.sh"
coordinator_currency_write "$(pwd)" "${CLAUDE_PLUGIN_ROOT}"
```

If the write succeeds: add `docs/coordinator-currency.yaml` to the **Created** list (or **Already Existed** if idempotent no-op). If it fails with a clear error, add a **Needs Attention** warning — the stamp is non-fatal for onboarding but required for the drift probe.

---

### Phase 4: REPORT

If Phase 1.5 dispatched peer-repo scouts, ensure the tracker's workstream blocks include `file:line` citations from the scout reports.

Present what was done:

```
## Onboarding Complete — [Project Name]

### Created
- [list each file/directory created]

### Already Existed (untouched)
- [list each file that was skipped]

### Needs Attention
- [any warnings — .gitignore issues, incomplete CLAUDE.md sections to fill in]

### Recent Roadmap (last 90d, top-10 by size)
_(Results from Phase 1.5 roadmap orientation query — one bullet per row. Render "(none)" when the query returns zero rows. Heading always present — count-always per orientation-surfacing-doctrine.)_

### Next Steps
0. **Your `~/.claude` is the surface you evolve** — it is a git-tracked repo that IS your live coordinator install. Customize it (CLAUDE.md, lessons, wiki), commit, and push. Never edit the upstream `coordinator-claude` source clone; changes there are overwritten on the next publish/refresh.
1. **Fill in CLAUDE.md** — the `<!-- Fill in -->` sections need project-specific details
2. **Run `/update-docs`** — generates DIRECTORY.md source index, refreshes docs/README.md, and creates orientation cache
3. **Run `/workstream-start`** — verifies everything is wired up correctly
4. **Introspect coordinator / plugin bindings** — run the envelope-branch check below to verify the coordinator sees this project correctly.

   ```sh
   # Compact JSON output — pipe through python -m json.tool if you want pretty-print.
   # No --json flag needed — default output is compact JSON.
   python3 -m coordinator_whoami.project_rag        # POSIX / macOS
   py -3   -m coordinator_whoami.project_rag        # Windows Git Bash / PowerShell
   ```

   Parse `binding.kind` and `binding.target` from the JSON envelope (`cross-plugin-whoami-contract.md §Operator wiring`):

   - **`binding.kind == "bound"` AND `binding.target` matches cwd:** emit `Coordinator binding healthy: project-rag is bound to <binding.target>.`
   - **`binding.kind == "bound"` AND `binding.target` does NOT match cwd:** emit a mismatch block:
     ```
     Binding mismatch:
       envelope binding.target : <binding.target>
       expected (cwd)          : <cwd>
     Run /project-rag:setup to re-register this project root.
     ```
   - **`binding.kind == "unbound"`:** emit:
     `project-rag is not bound to this project. Run /project-rag:setup to register this project root.`
   - **Import fails (`ModuleNotFoundError`) OR the command exits non-zero:** emit:
     `coordinator_whoami is not installed. Run /coordinator:setup to install the introspection package.`

   Full probe suite: [`docs/wiki/coordinator-doctor.md`](../docs/wiki/coordinator-doctor.md).
5. **If `machine-local get repos.*` fails** — the machine-local registry is not yet bootstrapped for this project. See [`coordinator-doctor.md`](../docs/wiki/coordinator-doctor.md) probes P-1 through P-4 to bootstrap the registry.

### Documentation System
The documentation index is live at `docs/README.md`. Subdirectories are created lazily as artifacts accumulate:
- **`docs/wiki/`** — created by `/distill` when first guide is extracted
- **`docs/plans/`** — created when first plan is written in plan mode
- **`docs/research/`** — created by `/deep-research` on first run
- `/update-docs` maintains docs/README.md; `/distill` creates wiki guides from session artifacts
```

## Coordinator Conventions — Discovery Summary

When a new project is onboarded, surface these convention introductions so the EM has them at hand from day one. These are one-line pointers; the canonical docs hold the full mechanics.

- **Acceptance oracle (outer-loop):** Non-trivial reviewed plans declare bindable acceptance criteria gated at `/workstream-complete` Step 3.8. See `docs/wiki/writing-plans.md` § Acceptance Oracle.

## Onboarding Bug Fixes — Three-Layer Rule

Any onboarding bug fix that doesn't ship all three layers will recur:

**Layer 1 — Prevention:** Fix the install/setup script so future runs don't hit the failure.

**Layer 2 — Reactive repair:** A targeted recovery path for users who already hit the failure and won't re-run the full installer. Valid shapes: a `doctor`-style script (`--fix` flag), or an idempotent slash command safe to re-run against broken state. What matters is the ability to recover without a clean-slate install.

**Layer 3 — Searchable docs:** A row in the troubleshooting table keyed on the **literal error text** the user would see.

```markdown
| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'coordinator_whoami'` | coordinator-whoami package was not installed | Run `/coordinator:setup` to install the introspection package |
```

Layer 2 recovery: doctor probe P-5 in [coordinator-doctor.md](../../docs/wiki/coordinator-doctor.md).

**When onboarding flags a new failure:** Verify all three layers exist before closing — missing layers are part of the same fix, not a follow-up task.

## Notes

- This skill creates the **skeleton**; `/update-docs` handles ongoing tracker maintenance. Tracker format matches the tracker-maintenance skill for consistency.
- Handoffs live at `state/handoffs/` (git-tracked); `settings.local.json` in `.gitignore`.
- **Template architecture:** One base CLAUDE.md template with conditional blocks per project type — NOT 4 separate files (stays under 12-file ceiling). Works standalone for marketplace users; DETECT phase adds "extends global" reference if `~/.claude/CLAUDE.md` exists.
