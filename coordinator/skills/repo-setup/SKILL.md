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
- **Creating a NEW repo from scratch** (not onboarding an existing folder)? → use `coordinator:new-project`, which creates + scaffolds a stack + delegates the onboarding half back to this skill.

**Setup is sufficient — downstream skills add-to, never create-from-scratch.** This skill produces minimum-viable versions of all coordinator artifacts the operator will rely on (`state/orientation_cache.md`, `docs/project-tracker.md`, `docs/README.md`, `CLAUDE.md`). Downstream skills (`/update-docs`, `/workstream-start`) add to these artifacts as content accumulates, and they self-gate when invoked against fresh substrate. → [`docs/wiki/produce-not-prescribe.md`](../../docs/wiki/produce-not-prescribe.md) for the underlying principle. (`/workday-start` is the morning cadence skill — it runs unconditionally as part of session orientation, so the produce-not-prescribe / self-gate axis does not apply to it.)

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

**coordinator_whoami availability (install-surface-completeness):**

The Phase 4 binding probe (`python3 -m coordinator_whoami.project_rag`) requires the `coordinator_whoami` package. On a fresh machine where this is the first onboarded repo, the package is not yet installed. Probe and install idempotently — owning the binding-probe contract this skill advertises rather than punting to a separate meta-package command.

```bash
if python3 -c "import coordinator_whoami" 2>/dev/null; then
  whoami_status="ready"
elif [ "${CHECK_ONLY:-0}" = "1" ]; then
  whoami_status="would-install"
else
  if pip_stderr=$(python3 -m pip install -e "${CLAUDE_PLUGIN_ROOT}/whoami/" 2>&1 >/dev/null); then
    whoami_status="installed"
  else
    whoami_status="failed"
  fi
fi
```

Record `coordinator_whoami: <whoami_status>` in the Phase 4 status table.

- **`ready`:** package was already importable — no mutation.
- **`installed`:** `pip install -e` succeeded; binding probe will work in Phase 4.
- **`would-install`:** `--check-only` is set; package missing; no mutation. Reported in status table.
- **`failed`:** pip itself errored (no Python, no pip, or pip exit non-zero). Do NOT halt the skill — Phase 4's existing `ModuleNotFoundError` fallback (`Run /coordinator:install to install the introspection package.`) remains the last-resort signal. Log pip stderr (captured in `pip_stderr`) to the status table notes.

Idempotent: re-running the skill on an already-bootstrapped repo short-circuits at the `import` probe with no pip invocation.

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
| `state/orientation_cache.md` | EAGER | Project name, type, workstreams, sibling-repo refs all ratified in Phase 2 — meaningful day-1 content exists. Applies the lazy-creation rule at `:235-238`, not a reversal. |
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

After `render-template.sh` returns successfully, set `_PHASE_3A_RENDERED_CLAUDE_MD=true` so Phase 4 item 1 can fire its conditional. (When CLAUDE.md exists before Phase 3a and is left untouched, the flag stays unset and Phase 4 item 1 is suppressed — the intended behavior for bespoke CLAUDE.md.)

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

Render `templates/README.md.template` via `render-template.sh`, substituting `[PROJECT_NAME]` and `[DATE]`.

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

Reads `canonical-structure.yaml` (source of truth for the skeleton). For each `creation: eager` entry: contract-bearing dirs get a `README.md` (schema-documenting, e.g. `cross-repo/inbox/`); `gitkeep: true` dirs get a `.gitkeep` sentinel (full `state/` subdir skeleton + `tasks/`). Idempotent — `.gitkeep` skips dirs containing real files.

**Most tracker files are NOT pre-created** (`state/lessons.md`, `state/handoff-tracker.md`, etc.) — they are written lazily by their owning skills on first use (see table above). Pre-creating empty tracker files trains agents to ignore the directory; empty scaffolding has zero signal value. **Exception — `state/orientation_cache.md`** is now eagerly seeded by Phase 3h below: PM has just ratified project name, type, and workstreams in Phase 2, so meaningful day-1 content exists. See `docs/wiki/produce-not-prescribe.md` for the underlying principle.

#### 3f. .gitignore handling

Ensure `.gitignore` contains the canonical block (per `docs/wiki/gitignore-policy.md`):

```
# Machine-specific Claude settings (do not commit)
.claude/settings.local.json

# Scratch — transient agent output, investigation notes, workstream byproduct.
# `scratch/` matches at any depth (top-level scratch/, tasks/scratch/, etc.)
scratch/
tasks/_*.log

# Per-session transient markers (produce-not-prescribe sentinel — consumed by /workstream-start)
state/.repo-setup-*
```

Procedure:

1. **If `.gitignore` doesn't exist:** Create it with the canonical block above.
2. **If `.gitignore` exists but is missing any of the three rules:** Append only the missing rules under a single comment header (`# Coordinator universal — scratch + machine-local settings`).
3. **If all three rules are present:** Skip silently.

**Warning checks:**

- If `.gitignore` ignores all of `.claude/` (`.claude/` or `.claude/*`), warn: only `.claude/settings.local.json` needs ignoring.
- If tracked content exists under `scratch/` or `tasks/_*.log`, surface count and offer `git rm --cached -r` cleanup (confirm with PM first — don't auto-untrack).

#### 3f.5. Auto-push post-commit hook

Delegate to the canonical idempotent self-heal helper — it handles install (hook absent), repair (hook present but not routed), and exec-bit fix (hook present but `chmod -x`) in one place:

```bash
"$HOME/.claude/plugins/coordinator/bin/coordinator-ensure-post-commit-hook"
```

Idempotent and near-zero cost when already installed (one stat + one grep). The same helper runs from `session-init.sh` on every session boot, so any repo that pre-dated the doctrine, had its `.git/hooks/` wiped, or was cloned without `/repo-setup` ever being run, is self-healed on the next opened Claude Code session. The 2026-06-11 silent-failure spinoff (`state/handoffs/2026-06-11_145955_auto-push-silent-failure-email-privacy.md`) is the empirical basis for the install-time-only → self-healing shift.

Skip if a custom auto-push hook already exists and the PM has signed off on it.

#### 3f.5.6. Session-Id trailer prepare-commit-msg hook

Delegate to the same idempotent self-heal pattern as 3f.5 — installs the `prepare-commit-msg` hook that injects a `Session-Id: <id>` git trailer on every commit (resolution-order: `CLAUDE_SESSION_ID` → `CLAUDE_CODE_SESSION_ID` → `.git/coordinator-sessions/.current-session-id`). The trailer is the substrate `~/.claude/plugins/coordinator/bin/review-brightline-gate.sh --session-id` filters on so the brightline gate fires on this session's commits, not the whole shared-branch diff:

```bash
"$HOME/.claude/plugins/coordinator/bin/coordinator-ensure-prepare-commit-msg-hook"
```

Idempotent; silent no-op when no session-id resolves (legitimate non-coordinator commits stay unaffected). The same helper runs from `session-init.sh` for self-healing. Empirical basis for the install-surface completion: `docs/plans/2026-06-15-brightline-session-scope-fix.md` § Problem.

#### 3f.7. Concurrent-EM git config hardening

Harden this repo's git config against two concurrent-EM Git-for-Windows failure modes (see `docs/wiki/concurrent-em-hazards.md` § H21–H22): `gc.autoDetach false` so git's auto-maintenance runs synchronously instead of detaching into a background process that can orphan the index lock, and `core.checkStat minimal` so the index comparison ignores the NTFS-unstable `ctime/ino/dev` fields that cause a phantom-dirty tree under concurrent index rewrites:

```bash
"$HOME/.claude/plugins/coordinator/bin/coordinator-configure-git"
```

Idempotent — safe to re-run; a no-op if already hardened.

#### 3f.5.5. Meta-repo pre-commit exec-bit gate (conditional)

```bash
"$HOME/.claude/plugins/coordinator/bin/install-meta-repo-precommit-hook.sh" "$HOME/.claude"
```

Idempotent. Pass `"$HOME/.claude"` explicitly so the install is cwd-independent — without the arg the installer derives the repo root from cwd, which is the consumer *project* repo during `/repo-setup`, so the gate would silently never land in the meta-repo (the 2026-06-24 gap). The helper still internally gates on `canon(repo-root) == canon($HOME/.claude)` — installs the pre-commit gate only in the meta-repo itself, no-ops in consumer repos. If an existing `pre-commit` hook is present without the gate marker, the installer appends the invocation instead of clobbering it.

**Why this is conditional.** The helper scans `~/.claude/plugins/*` for exec-bit drift on `.sh` files — a meta-repo concern. Consumer-repo commits don't touch that tree; installing the hook in a consumer repo would fire the helper on every commit only to have it immediately exit 0. The `/workday-complete` Step 5 gate remains the meta-repo's end-of-day backstop; this hook is the earlier-cadence catch.

**Override:** `COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT=1 git commit ...` bypasses the gate for emergency commits.

**Spec backlink:** `cross-repo/inbox/2026-06-08-exec-bit-drift-runtime-tripwire-tests.md`.

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

Do NOT create this file directly — requires source file analysis handled by `/update-docs` Phase 2. Do NOT add a prescription to the Phase 4 REPORT telling the PM to run `/update-docs` — the precondition probe self-gates and will run when DIRECTORY.md analysis is warranted. → `docs/wiki/produce-not-prescribe.md`.

### Phase 3i. Currency stamp (ALWAYS — idempotent)

<!-- spec-backlink: archive/specs/2026-05/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1 -->

Record which `COORDINATOR_SCHEMA_VERSION` this project was onboarded against. Idempotent —
safe to re-run; overwrites only when the schema version has been bumped since the last stamp.

Skip for distribution repos (answer (b) from Phase 1). Apply for working repos ((a) and (c)).

Resolve `CLAUDE_PLUGIN_ROOT` as the coordinator plugin root (e.g. `~/.claude/plugins/coordinator-claude/coordinator`):

```bash
source "${CLAUDE_PLUGIN_ROOT}/lib/coordinator-currency.sh"
coordinator_currency_write "$(pwd)" "${CLAUDE_PLUGIN_ROOT}"
```

If the write succeeds: add `docs/coordinator-currency.yaml` to the **Created** list (or **Already Existed** if idempotent no-op). If it fails with a clear error, add a **Needs Attention** warning — the stamp is non-fatal for onboarding but required for the drift probe.

#### 3h. state/orientation_cache.md (if missing)

Authority for this eager seed: the lazy-creation rule at `:235-238` — *"Only scaffold files that have meaningful day-1 content."* PM input from Phase 2 (project name, type, initial workstreams, sibling-repo refs) is *exactly* the meaningful day-1 content that licenses an eager seed. This is the produce-not-prescribe principle (→ `docs/wiki/produce-not-prescribe.md`) applied to the orientation surface: setup has the maximum-possible context for this project, so setup writes the cache rather than punting to `/update-docs` Phase 13 against an empty repo.

Render to `state/orientation_cache.md` with the project context just gathered:

```markdown
# Orientation Cache

## Project
[PROJECT_NAME] — [PROJECT_TYPE] project. [ONE-LINE_PURPOSE_FROM_PM_OR_DETECTED_STACK].

## Active workstreams
[WORKSTREAM_LIST — name + 2-3 deliverables each, from Phase 2 PM input]

## State
- **Handoffs:** none yet (created by `/handoff` when first session ends mid-stream).
- **Lessons:** none captured yet (`state/lessons.md` lazily created on first capture).
- **Last weekly reset:** N/A (no weeks closed yet).

## Pinboard
[empty — populated by future workday-start / workstream-start runs]
```

Substitute the bracketed tokens from Phase 1.5 / Phase 2 ratified inputs. Leave `## Pinboard` empty (intentional — populated later). Future `/update-docs` Phase 13 reads this cache and updates it rather than overwriting from scratch.

---

### Phase 3j. Extended substrate seeds (ALWAYS — idempotent)

<!-- spec-backlink: docs/plans/2026-06-23-setup-time-substrate-completeness.md § C1 -->

Wire in the four substrate seeds that complete the coordinator machinery for this repo. Each helper is idempotent and fail-loud on ambiguity — safe to re-run; skips cleanly when the artifact already exists or the condition doesn't apply.

Resolve `_PLUGIN_ROOT` as the coordinator plugin root (e.g. `~/.claude/plugins/coordinator-claude/coordinator`). Run each helper as a **subprocess** (`bash <path>`), **not** `source` — every helper is fail-loud and calls `exit` on ambiguity, so sourcing would terminate the repo-setup shell (and `setup-rag-decision.sh` is `$0`-guarded, so sourcing it bare silently no-ops the decision block); the subprocess form isolates each exit, and `bash <path>` is robust to the exec-bit being stripped on checkout (DR-151). The target repo root is passed explicitly as `"$(pwd)"` (required by the test-command detector; defaulted to cwd by the others). Run in sequence:

**1. Test-command detection** — detect the stack's test command and write `fast_test_cmd` / `full_test_cmd` into `coordinator.local.md`:

```bash
bash "${_PLUGIN_ROOT}/lib/setup-detect-test-cmd.sh" --root "$(pwd)"
```

Detects `package.json` test scripts, `pyproject.toml`/`pytest.ini`, `Cargo.toml`. Presents candidates for operator confirmation (or accepts `--non-interactive` pre-set). Fails loud when multiple ambiguous candidates are found — never silent-picks. Writes both keys as flat top-level entries in `coordinator.local.md` (the shape `cs_resolve_fast_test_cmd` / `cs_resolve_full_test_cmd` already reads). Skip if both keys are already present.

**2. Health ledger seed** — seed `state/health-ledger.md` from the daily-summary schema:

```bash
bash "${_PLUGIN_ROOT}/lib/setup-seed-health-ledger.sh" "$(pwd)"
```

Seeds every system row at grade `?` (never fabricates grades). Idempotent — skips if `state/health-ledger.md` already exists. Reference shape: this repo's own `state/health-ledger.md`.

**3. RAG-index decision** — resolve the three-branch RAG-index decision tree and write the outcome into the repo `CLAUDE.md`:

```bash
bash "${_PLUGIN_ROOT}/lib/setup-rag-decision.sh" --root "$(pwd)"
```

Branch logic (do not write a dead offer for non-UE repos):
- UE repo + project-rag daemon present → offer to index.
- Non-UE repo (any daemon state) → tripwire path (upstream `.uproject`-abstention defect blocks non-UE indexing; cite the memo).
- No daemon → tripwire path.

Tripwire branches write `un-indexed; use Tier-3 (Read/Grep/Glob)` into the repo `CLAUDE.md`.

**4. fnm pin-resolution** — ensure the repo's pinned Node version is installed via machine-level fnm:

```bash
bash "${_PLUGIN_ROOT}/lib/setup-fnm-pin.sh" "$(pwd)"
```

Acts only when `.node-version` or `.nvmrc` is present; pure no-op when neither exists. When a pin file is found: checks whether the `fnm` binary is installed; if present, runs `fnm install <pinned>` and emits `eval "$(fnm env)"` / PATH guidance for no-version-manager shells; if absent, fails loud: `"fnm not installed — run coordinator:install to install the Node toolchain manager, then re-run repo-setup."` **repo-setup MUST NOT install the fnm binary** — binary install is machine-level only (per `coordinator:install` Phase 3).

Record outcomes in the Phase 4 REPORT under `### Created` or `### Already Existed` as appropriate. Any fail-loud exit from a helper surfaces under `### Needs Attention` with the helper's remediation text verbatim.

**`coordinator:new-project` inherits all four seeds via its Phase-4 delegation to `coordinator:repo-setup` — no re-implementation in `new-project` is needed or permitted.**

---

### Phase 4: REPORT

If Phase 1.5 dispatched peer-repo scouts, ensure the tracker's workstream blocks include `file:line` citations from the scout reports.

**`coordinator_whoami` status row.** Emit a one-line status row based on `whoami_status` from Phase 1 (vocabulary: `coordinator_whoami: ready | installed | would-install | failed`). Route by value: `ready` → `### Already Existed`; `installed` → `### Created`; `would-install` or `failed` → `### Needs Attention` (include `pip_stderr` for `failed`).

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

### What's next

Setup left this repo with `state/orientation_cache.md`, `docs/project-tracker.md`, `docs/README.md`, and `CLAUDE.md` — minimum-viable versions of all coordinator artifacts. The standard coordinator skills (`/update-docs`, `/workstream-start`, `/workday-start`, `/workstream-complete`) will keep these in sync as the project accumulates work — invoke them when there's something to maintain. Both `/update-docs` and `/workstream-start` self-gate on fresh substrate and will emit a one-liner rather than running an empty pipeline (→ `docs/wiki/produce-not-prescribe.md` for the underlying principle).

Two things worth flagging before you dive in:

0. **Your `~/.claude` is the surface you evolve** — it is a git-tracked repo that IS your live coordinator install. Customize it (CLAUDE.md, lessons, wiki), commit, and push. Never edit the upstream `coordinator-claude` source clone; changes there are overwritten on the next publish/refresh.

1. **Fill in CLAUDE.md** *(only if Phase 3a rendered the template this session — skip if CLAUDE.md was authored bespoke)* — the `<!-- Fill in -->` sections need project-specific details. Skip silently if `_PHASE_3A_RENDERED_CLAUDE_MD=true` was not set.

To verify the install: `python3 -m coordinator_whoami.project_rag`.

To start your first workstream now, just describe what you want to do — the EM has full context from the setup conversation.

### Verify the coordinator binding

Run the envelope-branch check below to verify the coordinator sees this project correctly.

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
     `coordinator_whoami is not installed. Run /coordinator:install to install the introspection package.`

   Full probe suite: [`docs/wiki/coordinator-doctor.md`](../docs/wiki/coordinator-doctor.md).

**If `machine-local get repos.*` fails** — the machine-local registry is not yet bootstrapped for this project. See [`coordinator-doctor.md`](../docs/wiki/coordinator-doctor.md) probes P-1 through P-4 to bootstrap the registry.

### Documentation System
The documentation index is live at `docs/README.md`. Subdirectories are created lazily as artifacts accumulate:
- **`docs/wiki/`** — created by `/distill` when first guide is extracted
- **`docs/plans/`** — created when first plan is written in plan mode
- **`docs/research/`** — created by `/deep-research` on first run
- `/update-docs` maintains docs/README.md; `/distill` creates wiki guides from session artifacts
```

### Sentinel — signal that setup just ran

As the final action of `/coordinator:repo-setup`, write a session-scoped sentinel so `/workstream-start` (if invoked in this same session) detects that setup just ran and emits the produce-not-prescribe one-liner instead of re-orienting:

```bash
mkdir -p state
touch state/.repo-setup-just-ran
```

The sentinel is single-shot: `/workstream-start`'s Preflight consumes it on first read (`rm -f`). It MUST be gitignored — see Phase 3f for the `.gitignore` line. Per-machine transient marker, never committed.

## Optional Tripwire Installs

After Phase 3 scaffolding completes, offer to install coordinator-standard tripwire tests into the consuming repo's test suite. Each tripwire is a copyable template — copy, customize the allowlist, and wire into CI.

### Windows console-subprocess tripwire (offer always on Windows-operator repos)

Offer this tripwire when the consuming repo includes shell scripts that may run on
Windows operator machines (any `*.sh` in the repo root or a `scripts/` / `bin/` subtree
is a reliable signal).

**What it catches:** bare `python -c`, `python3 -c`, `python.exe -c`, `powershell.exe`,
and PowerShell `& python` invocations in `*.sh` files — shapes that pop a
focus-stealing console window on Windows when spawned from the headless Bash-tool
parent process.

**Canonical suppression markers (two forms, honored identically by all layers):**
- `# popup-intentional-last-resort` — the popup occurs and is accepted (pythonw fallback or genuine console need).
- `# popup-safe-env-suppressed` — the popup is suppressed at this site by env-var means and is therefore safe.

Place the applicable marker on the same line as the bare call (shell/Python comment form). When inside an embedded interpreter string (`python -c "..."`) place the marker on the surrounding SHELL line, outside the string — the marker inside a Python string argument is parsed by Python at runtime, not by the tripwire regex. The retired form `# noqa: bare-subprocess-windows` is NOT honoured; do not use it.

**Install steps:**

```bash
# 1. Copy the template into the consuming repo
cp "$HOME/.claude/plugins/coordinator/tests/templates/test_no_bare_console_subprocess.py" \
   tests/test_no_bare_console_subprocess.py

# 2. Customize the allowlist at the top of the copied file:
#    PREFIXES  — subtree paths that are known-safe (e.g. "vendor/", "tests/fixtures/")
#    EXACT_FILES — individual files allowed to use bare calls (e.g. the safe-path wrapper itself)

# 3. Verify it runs and reports nothing unexpected:
python3 tests/test_no_bare_console_subprocess.py
# or:
pytest tests/test_no_bare_console_subprocess.py

# 4. Add the appropriate suppression marker to any remaining bare calls in files NOT
#    covered by the allowlist:
#    - `# popup-intentional-last-resort`  if the popup is accepted (last-resort / pythonw fallback)
#    - `# popup-safe-env-suppressed`      if the popup is already suppressed by env-var means
```

**Template path:** `~/.claude/plugins/coordinator/tests/templates/test_no_bare_console_subprocess.py`

Offer the install when the PM has not already done so (check for the file in the
consuming repo's test tree). If the PM declines, note it in the Phase 4 REPORT under
`### Needs Attention` with a one-line pointer to the template path.

## Coordinator Conventions — Discovery Summary

When a new project is onboarded, surface these convention introductions so the EM has them at hand from day one. These are one-line pointers; the canonical docs hold the full mechanics.

- **Acceptance oracle (outer-loop):** Non-trivial reviewed plans declare bindable acceptance criteria gated at `/workstream-complete` Step 3.8. See `docs/wiki/writing-plans.md` § Acceptance Oracle.
- **Extended substrate (Phase 3j):** setup now seeds `fast_test_cmd`/`full_test_cmd` in `coordinator.local.md`, `state/health-ledger.md` (grade `?` baseline), the RAG-index decision (index-offer or `un-indexed` tripwire in `CLAUDE.md`), and the fnm Node-version pin if `.node-version`/`.nvmrc` is present. These remove the silent-skip gaps in `/workday-complete` Step 1 and Step 4d and the Node toolchain mismatch on repos with a pinned version. → `docs/plans/2026-06-23-setup-time-substrate-completeness.md`.

## Onboarding Bug Fixes — Three-Layer Rule

Any onboarding bug fix without all three layers recurs: **(1) Prevention** — fix the install script; **(2) Reactive repair** — `doctor`-style recovery or idempotent re-run path for users who already hit it; **(3) Searchable docs** — a troubleshooting table row keyed on the literal error text. New failures: verify all three layers before closing. → `docs/wiki/post-install-onboarding-pattern.md`; doctor probe P-5 in `docs/wiki/coordinator-doctor.md`.

## Notes

- This skill creates the **skeleton**; `/update-docs` handles ongoing tracker maintenance. Tracker format matches the tracker-maintenance skill for consistency.
- Handoffs live at `state/handoffs/` (git-tracked); `settings.local.json` in `.gitignore`.
- **Template architecture:** One base CLAUDE.md template with conditional blocks per project type — NOT 4 separate files (stays under 12-file ceiling). Works standalone for marketplace users; DETECT phase adds "extends global" reference if `~/.claude/CLAUDE.md` exists.
