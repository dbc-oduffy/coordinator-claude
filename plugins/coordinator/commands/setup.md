---
description: Set up the coordinator plugin — check prerequisites, verify environment, configure project. Safe to re-run.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive]"
---

# Coordinator Setup

Environment and project setup for the coordinator plugin. Checks prerequisites, verifies configuration, and initializes what's missing. Safe to re-run — skips anything already configured.

If `$ARGUMENTS` contains `--check-only`, report status without making changes.

If `$ARGUMENTS` contains `--non-interactive`, skip all `AskUserQuestion` calls, applying per-site fallback behavior documented in the **D4 Non-Interactive Contract** below.

## D4 Non-Interactive Contract

<!-- spec-backlink: D4 in docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md -->

Each prompt site carries one of three annotations: `skip-with-note` (skip, surface skip in status table), `default-with-warning` (apply documented safe default, surface defaulted value), `fail-loud` (exit non-zero with remediation; used when no safe default exists). Default for any unannotated site is `fail-loud`.

Flag semantics: `--check-only` is a strict superset preventing all mutation regardless of interactivity. `--non-interactive` controls only the prompt fallback — does not affect mutation policy. Both are orthogonal and may be combined.

---

**Scope distinction:** This command sets up the coordinator *environment* (plugins, env vars, tools). For per-project scaffolding (CLAUDE.md, tracker, workstreams), use `/project-onboarding` after this.

---

## Phase 1 — Environment

Run all checks and collect results for the status table.

### 1a. Git repository

```bash
git rev-parse --show-toplevel 2>/dev/null
```

- If not a git repo: warn that branch management, commits, and handoffs require git. Setup continues.
- If a git repo: note the repo root path.

### 1b. Agent Teams env var

```bash
echo "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-not_set}"
```

- If `1`: ready.
- If not set: **required for staff sessions and all research pipelines.** If not `--check-only`, offer to add it:

Read `~/.claude/settings.json`. If an `env` block exists, check for the key. If missing, add it:

```json
"env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }
```

Note: this takes effect on next Claude Code restart.

### 1c. Code statistics tool (scc)

```bash
command -v scc 2>/dev/null || command -v "$HOME/bin/scc" 2>/dev/null || echo "not_found"
```

- If found: ready. Used by the orientation hook for code stats.
- If not found: optional. Note that `scc` provides code statistics in the session orientation. Install from https://github.com/boyter/scc if desired.

### 1d. Deep research plugin

Check if the deep-research plugin is installed:

```bash
ls ~/.claude/plugins/deep-research/commands/web.md 2>/dev/null || \
ls ~/.claude/plugins/cache/*/deep-research/*/commands/web.md 2>/dev/null || \
echo "not_found"
```

- If found: ready. Note which pipelines are available.
- If not found: optional. The deep-research plugin adds multi-agent research pipelines (internet, repo, structured). Available from the plugin marketplace or https://github.com/dbc-oduffy/deep-research-claude.

**If deep-research IS found,** also check:
- Agent Teams env var (already checked above — if missing, flag it as **required** here, not just recommended)
- NotebookLM sub-plugin: check for `notebooklm/.mcp.json` in the deep-research plugin directory. If present, note that Pipeline D (media research) requires the `notebooklm-mcp-cli` package and Google authentication (`nlm login`).

### 1f. Global CLAUDE.md integration

Read `~/.claude/CLAUDE.md` and check if it contains an `@` import of the coordinator doctrine:

```
grep -c "coordinator.*CLAUDE.md" ~/.claude/CLAUDE.md 2>/dev/null || echo "0"
```

- If found: ready — the coordinator operating doctrine is being imported.
- If not found: recommend adding the import. The coordinator CLAUDE.md contains operating norms (session orientation, plan-first workflow, review sequencing, etc.) that improve how Claude works with the coordinator. Suggest adding this line to their global `~/.claude/CLAUDE.md`:
  ```
  @~/.claude/plugins/coordinator/CLAUDE.md
  ```
  Or, if installed from marketplace cache, point to the cache path.

## Phase 2 — Operator identity

### Operator identity capture

Persists the operator's name to `~/.claude/coordinator-identity.yaml` so re-runs skip the prompt. Idempotent.

**Step 1 — Read identity file if present.**

```bash
test -f ~/.claude/coordinator-identity.yaml && echo "exists" || echo "missing"
```

Branch on content:

- **`version: 1` and `operator_name` present** → use stored value; skip prompt. Status: `operator_identity: ready`. Proceed to Step 3.
- **`version:` > 1** → fail-loud: *"coordinator-identity.yaml has schema version {N}, unsupported. Delete the file and re-run /setup, or downgrade coordinator."* Status: `operator_identity: failed (unknown schema version {N})`. Stop phase.
- **`version: 1` but `operator_name` missing (or `version:` absent)** → treat as absent; proceed to Step 2.

If `$ARGUMENTS` contains `--reconfigure`, treat the file as absent regardless.

**Step 2 — Capture identity if absent (or `--reconfigure`).**

<!-- D4 annotation: fail-loud — operator's name is not derivable; no safe default exists. -->

- **Under `--non-interactive`** (i.e., `$ARGUMENTS` contains `--non-interactive`): fail-loud — emit: *"--non-interactive requires ~/.claude/coordinator-identity.yaml to exist (version: 1, operator_name: <string>). Run /setup interactively first to capture the operator name, then re-run with --non-interactive."* Status row: `operator_identity: failed (--non-interactive without identity file)`. Stop this phase.

- **Under interactive (default):** ask via `AskUserQuestion` exactly once:

  > What name should the meta-repo collaboration doctrine address you by? This gets substituted into `~/.claude/CLAUDE.local.md` as the human operator's name (the `PM_NAME` key in the template). Used in framing like *"co-author of the PM-EM working methodology with <name>"*. Use the form you'd like the EM to use when referring to you in doctrine — first name, full name, handle, whatever fits.

  No suggested options — open-ended text input via the user's "Other" affordance.

**Step 3 — Write identity file (skip under `--check-only`).**

If `$ARGUMENTS` contains `--check-only`: emit status row `operator_identity: would write` and skip the write.

Otherwise, write `~/.claude/coordinator-identity.yaml` atomically (write to a temp file, then rename):

```bash
_tmp="$(mktemp ~/.claude/coordinator-identity.yaml.XXXXXX)"
cat > "$_tmp" <<EOF
# ~/.claude/coordinator-identity.yaml — operator-local, NEVER a publish target
version: 1
operator_name: ${OPERATOR_NAME}
EOF
mv "$_tmp" ~/.claude/coordinator-identity.yaml
```

Where `${OPERATOR_NAME}` is the value read from the existing file (Step 1) or captured from the prompt (Step 2). Status row: `operator_identity: ready`.

**Step 4 — Discover working repos.**

The rendered `CLAUDE.local.md` includes a "Your working repos" section. Three-tier discovery (stop at first non-empty):

```bash
WORKING_REPOS=$(bash "${CLAUDE_PLUGIN_ROOT}/coordinator/lib/discover-working-repos.sh")
```

Helper runs Tier A (`~/.claude/projects/` activity record, `X--Foo` → `X:\Foo`) then Tier B (`~/dev`, `~/Projects`, `/x`, etc.). Filters meta-repo, `AppData/Local/Temp`, bare drive roots. Returns up to 20 (A) or 30 (B) candidates.

**Tier C — Ask the operator** (if helper returned empty).

<!-- D4 annotation: default-with-warning — empty list is documented neutral default. -->

Under `--non-interactive`: skip prompt, set `WORKING_REPOS` to placeholder (*"No working repos discovered at install time. Edit this section to list your projects."*), status: `working_repos: defaulted to empty (non-interactive)`.

Under interactive: ask once via `AskUserQuestion`:

> The coordinator setup couldn't find existing code projects on this machine. In which folder do you usually keep code work? (e.g. `~/dev`, `~/Projects`, `C:\code`) — leave blank if you don't have one yet.

If operator names an existing folder, re-probe Tier B inside it. If still empty, record the named folder with a "no repos yet" note.

**Build `WORKING_REPOS` block.** Markdown list with one repo per line: `` - `<path>` — <one-line if README heading readable> ``. Tier A may annotate with `(active recently)` for top 3.

Persist machine-readable copy at `~/.claude/working-repos.yaml` (atomic mv):

```yaml
# generated by /setup; safe to hand-edit
version: 1
discovered_at: <ISO-8601>
discovery_tier: A | B | C
repos:
  - path: <absolute path>
    source: claude-projects-dir | dev-folder-scan | operator-supplied
```

Status: `working_repos: ready (N from tier {A|B|C})`. Under `--check-only`, run Tiers A+B read-only, skip YAML write and Tier C prompt.

**Step 5 — Render `~/.claude/CLAUDE.local.md`.**

Check existence of the rendered file:

```bash
test -f ~/.claude/CLAUDE.local.md && echo "exists" || echo "missing"
```

If `--check-only`: if the file is missing, emit status row `meta_repo_doctrine: would write`; if present, emit `meta_repo_doctrine: ready`. Skip the render.

Otherwise, invoke the render-template helper:

```bash
bash ~/.claude/plugins/coordinator/bin/render-template.sh \
  ~/.claude/plugins/coordinator/templates/CLAUDE.local.md.tmpl \
  -o ~/.claude/CLAUDE.local.md \
  PM_NAME="${OPERATOR_NAME}" \
  WORKING_REPOS="${WORKING_REPOS}"
```

If the helper exits non-zero (e.g., unsubstituted keys in the template), fail-loud with the helper's stderr output.

On success, surface a one-line confirmation: `Meta-repo doctrine installed at ~/.claude/CLAUDE.local.md. Loads when cwd is ~/.claude or below.`

## Phase 3 — Machine-local registry substrate

Lay down the `~/.claude/machine-local/` substrate and the `bin/{machine-local, claude-home}` resolvers. Idempotent — safe to re-run; never overwrites a live `registry.toml`, `registry.local.toml`, or operator-customized file.

**Sources of truth:**
- `coordinator/templates/machine-local/` — tracked files (README, .gitignore, both `.example` registries)
- `coordinator/templates/bin/` — `machine-local` family + `python3.cmd` shim
- `coordinator/lib/claude-home/` — load-bearing `claude-home` module (`lib/<module>/` shape signals "cross-repo contract surface, do not customize"); see `coordinator/lib/claude-home/README.md`

Skip mutations under `--check-only`. Under `--non-interactive`, run all mechanical work but skip Step 3's seed prompt. (Step 5 and Step 6: under `--check-only`, emit status rows but skip all mutations.)

### Step 1 — Run install-substrate helper

The mechanical work — directory creation, tracked-file install, bin/ resolver install, Windows PATH integration, Windows Python-resolution health check — is encapsulated in `coordinator/lib/install-substrate.sh`. Invoke it:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/coordinator/lib/install-substrate.sh"
```

Helper behavior:
- **Fails-loud and halts setup** if any source-of-truth directory is missing — hard precondition for downstream skills (project-rag, holodeck, deep-research all shell out to `bin/machine-local`). Writes `Phase 3 FATAL:` to stderr and exits non-zero. Skill renders Phase 7 status: `machine_local_substrate: FATAL (templates missing)`.
- Honors `CLAUDE_HOME` (`docs/wiki/machine-local-registry.md § 4a`).
- Preserves operator-customized files with one-line notices; louder notice on `claude-home` artifacts (cross-repo contract surface).
- Skips Windows PATH + AppX checks on non-Windows; honors `COORDINATOR_NON_INTERACTIVE=1` to suppress consent prompts.

Seven installed bin/ artifacts:

| Live file | Source-of-truth |
|---|---|
| `~/.claude/bin/{machine-local, _machine_local.py, machine-local.cmd}` | `coordinator/templates/bin/` |
| `~/.claude/bin/{claude-home, _claude_home.py, claude-home.cmd}` | `coordinator/lib/claude-home/` |
| `~/.claude/bin/python3.cmd` | `coordinator/templates/bin/` |

The three `.cmd` files are Windows shims that prevent the "Select an app to open" picker on extensionless scripts and `python3`. Harmless on Linux/macOS. Rationale: `coordinator/docs/wiki/windows-cmd-shims.md`. The Windows-branch Python-resolution health check catches orphan AppX stubs, Store-alias-on-PATH, and no-Python; only orphan-stub deletion is mutating and requires `[y/N]` consent.

### Step 2 — Never overwrite live registry files

If `~/.claude/machine-local/registry.toml` or `~/.claude/machine-local/registry.local.toml` exists, leave both untouched regardless of `.example` updates. Same rule for any `<concern>.toml` and `<concern>.local.toml`. The operator's machine-local values are theirs.

### Step 3 — Optional seed prompt (declinable, interactive only)

<!-- D4 annotation (seed prompt): skip-with-note — seed is elective; --non-interactive skips it and notes that the operator should copy .example → real by hand. -->

**Skip entirely** if either `~/.claude/machine-local/registry.toml` or `registry.local.toml` already exists (idempotency).

Under `--non-interactive`: skip; emit status row `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`.

Under interactive, ask once via `AskUserQuestion`:

> Would you like to seed the registry with the four most common `repos.*` keys (coordinator, project-rag, project-rag-ue-addon, claude-unreal-holodeck)? Key declarations go to `registry.toml` (shared, tracked); per-machine path values to `registry.local.toml` (gitignored). Single-machine operators may put everything in `registry.toml`. [Y/n]

**On Y:** Ask for each key's path value inline (blank = skip). Then write via script:

1. Write `registry.toml` with key declarations (empty-string values + `schema = 1`) using a plain atomic write — these are shared declarations, not machine-specific.
2. For each non-blank path value, write to `registry.local.toml` via `machine-local set`:

```bash
machine-local set repos.coordinator_claude     "${PATH_VALUE}"
machine-local set repos.project_rag            "${PATH_VALUE}"
machine-local set repos.project_rag_ue_addon   "${PATH_VALUE}"
machine-local set repos.claude_unreal_holodeck "${PATH_VALUE}"
```

**Do NOT write paths to `registry.local.toml` by hand-editing or heredoc.** `machine-local set` is atomic, idempotent, and sets the example for every future script that needs to populate the registry.

**On N:** leave both absent.

### Step 4 — Test surface (expected behavior; do not actually run setup)

- **Fresh install:** directory, all tracked files, all 7 bin/ artifacts present after Step 1. Seed prompt fires interactively.
- **Re-run on populated install:** no overwrites, no prompts.
- **`--non-interactive`:** substrate laid down, no seed prompt, no `registry.toml`, no `registry.local.toml`.
- **Operator-modified file:** preserved; one-line notice; no overwrite.

**See:** `docs/wiki/machine-local-registry.md` (substrate doctrine + § 4a CLAUDE_HOME resolver), `coordinator/lib/install-substrate.sh` (mechanical contract), `coordinator/lib/claude-home/README.md` (claude-home module), `docs/wiki/coordinator-doctor.md` (post-install probes).

### Step 5 — Register coordinator plugin in `plugin.mirrors` (idempotent)

<!-- spec-backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 / AC-7 -->

Coordinator's live install IS the canonical source — `~/.claude/` itself. No inward propagation step is needed; edits flow outward via `publish.sh`. Register this in `registry.local.toml::plugin.mirrors` so `bin/check-plugin-drift.sh` surfaces it as `n/a-by-design`.

Run under `--non-interactive`. Pass `--check-only` when `$ARGUMENTS` contains it.

```bash
_mirror_flag=""
[[ "${ARGUMENTS:-}" == *"--check-only"* ]] && _mirror_flag="--check-only"
bash "${CLAUDE_PLUGIN_ROOT}/coordinator/lib/register-coordinator-mirror.sh" $_mirror_flag
```

The helper is idempotent and atomic (Python `os.replace` on a .tmp.<pid> file) — safe under concurrent `/coordinator:setup` invocations. Spec: `docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 / AC-7`.

Add a `Coordinator plugin.mirrors` row to the Phase 7 status table.

---

### Step 6 — Install `coordinator_whoami` package (idempotent)

<!-- spec-backlink: docs/plans/2026-05-21-whoami-first-class-substrate.md § Chunk 1 / AC-1, AC-2, AC-3, AC-15 -->
<!-- D4: default-with-warning — no prompt site; install fires mechanically under --non-interactive same as interactive. -->

Probe whether the package is already importable:

```bash
python3 -c "import coordinator_whoami" 2>/dev/null
```

- **Import succeeds:** status row `coordinator_whoami: ready`. No mutation.
- **Import fails, `--check-only`:** status `coordinator_whoami: would write`. Exit step.
- **Import fails, otherwise:** run editable install:

```bash
python3 -m pip install -e "${CLAUDE_PLUGIN_ROOT}/coordinator/whoami/"
```

On exit 0: `coordinator_whoami: ready`. On non-zero: `coordinator_whoami: failed` (log pip stderr tail separately; do NOT halt the chain — this isn't a hard precondition like Step 1). Add row to Phase 7 table. Post-install probe P-5 in `docs/wiki/coordinator-doctor.md`.

---

## Phase 4 — Meta-repo doctrine

### `~/.claude` git tracking

The meta-repo doctrine, plugins, and accumulated wikis benefit from version control — `git log` becomes the audit trail for how the operator's working methodology evolved. Check whether `~/.claude` is a git repo:

```bash
git -C ~/.claude rev-parse --show-toplevel 2>/dev/null || echo "not_a_repo"
```

- **Repo:** ready. If no remote (`git -C ~/.claude remote -v`), suggest: *"Consider configuring a private remote so history survives machine loss."*
- **Not a repo, not `--check-only`:** offer to initialize.

  <!-- D4: default-with-warning — defaults to Skip under --non-interactive. Status: `claude_git_tracking: skipped (non-interactive default)`. -->

  Under `--non-interactive`: skip prompt, apply **Skip**, status `claude_git_tracking: skipped (non-interactive default)`.

  Under interactive: ask via `AskUserQuestion`:

  > Your `~/.claude` directory isn't currently git-tracked. The coordinator setup recommends version-controlling this environment so the evolution of your doctrine, plugins, and wikis is auditable. Initialize a git repo at `~/.claude`?

  Options: **Initialize (Recommended)** — runs `git init ~/.claude`, creates a starter `.gitignore` from `templates/dotgitignore.tmpl` if present, commits a `chore: initialize Claude Central` baseline. **Skip** — re-ask next run. Do NOT push to a remote — that's the user's decision.

- **Not a repo, `--check-only`:** report `not_a_repo`.

---

## Phase 5 — Project-local

### coordinator.local.md

Check if `coordinator.local.md` exists at the repo root:

```bash
test -f coordinator.local.md && echo "exists" || echo "missing"
```

**If exists:** report current `project_type` (and `project_subtypes` if present). On legacy values (`unreal`, `meta`, bare `web`), emit:

> ⚠ Legacy project_type detected: `{value}`. Migrate: `project_type: game-dev` + `project_subtypes: [unreal]` (or `general` for `meta`, `web-dev` for `web`). Edit manually — this command does not auto-rewrite.

**If missing and not `--check-only`:**

<!-- D4: fail-loud on project_type (wrong type silently mis-routes); default-with-warning on subtypes. -->

Under `--non-interactive`: fail-loud — *"--non-interactive cannot create coordinator.local.md: project_type requires operator input (no safe default). Create manually with `project_type: general` and re-run."* Stop phase.

Under interactive: ask via `AskUserQuestion`:

> What type of project is this? Controls which domain specialists route.
>
> - **general** — Software (the Staff Engineer for code review)
> - **game-dev** — Game (adds the Game Dev Reviewer + game-dev agents)
> - **web-dev** — Web (adds the Front-End Reviewer + the UX Reviewer)
> - **data-science** — ML/data (adds the Data Science Reviewer)

Then ask for subtypes (free-form advisory tags; empty default; under `--non-interactive` skip and apply empty default, status `coordinator_local_md: created (project_subtypes defaulted to empty, non-interactive)`):

> Any subtypes? Free-form advisory tags — no validation. Examples: `unreal` under game-dev; `react`, `nextjs` under web-dev. Comma-separated, or blank.

Write `coordinator.local.md`:

```markdown
---
project_type: {type}
project_subtypes: [{subtype1}, {subtype2}]   # omit field when blank
---
```

---

## Phase 6 — Optional

### Persona Customization

<!-- D4: default-with-warning — Keep defaults is canonical baseline. -->

Under `--non-interactive` or `--check-only`: apply **Keep defaults**, status `persona_customization: skipped (non-interactive default: keep defaults)`.

Under interactive:

> The coordinator includes named reviewer personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering). Customize their names? **Keep defaults** / **Customize**

If customize: no `rename-personas.sh` helper currently ships — hand-edit persona names across agent files and prompts/skills referencing them. Canonical persona-to-role vocabulary in `NAME_TO_ROLE` table at `plugins/coordinator/bin/depersonalize-for-publish.sh` (exclude that file from search-replace to avoid self-corruption). One-time cosmetic choice; automation queued.

---

### Percolation Setup (if applicable)

Detect whether this repo is a *source* repo for percolation — i.e., a repo that publishes plugin content to a separate publish-repo target.

```bash
test -f setup/publish.sh && echo "percolation_source" || echo "not_applicable"
```

**If `setup/publish.sh` is absent:** skip this phase silently. This repo is not a percolation source.

**If `setup/publish.sh` is present:** check whether any publish targets are registered:

```bash
bash -c '
  [[ -f setup/publish-targets.sh ]] || { echo "MISSING_TARGETS"; exit 0; }
  source setup/publish-targets.sh
  echo "TARGET_COUNT:${#TARGETS[@]}"
'
```

- **`MISSING_TARGETS` or `TARGET_COUNT:0`:** No targets registered. Walk `docs/wiki/percolate-setup.md` (plugin-relative path) inline — specifically Steps 1 and 2 to register a target, then Steps 3–4 to scaffold `.percolate-ignore` and hook directories. This is an interactive procedure; do not skip.
- **Targets registered and all configured** (each target has a `.percolate-ignore` and hook dirs): report status in the summary table as `Percolation: N target(s) configured`.
- **Targets registered but partially configured** (missing `.percolate-ignore` or hook dirs on any target): surface the gap and offer to run the setup procedure for the unconfigured target(s).

If `--check-only`, report the percolation state in the summary table without creating anything.

Add a `Percolation` row to the status table in Phase 7.

---

## Phase 7 — Status Report

Present a summary table:

```
## Coordinator Setup

| Check                       | Status |
|-----------------------------|--------|
| Git repository              | ... |
| Agent Teams env var         | ... |
| Code stats (scc)            | ... (optional) |
| Deep research plugin        | ... (optional) |
| NotebookLM (Pipeline D)     | ... (optional) |
| Global CLAUDE.md import     | ... |
| Operator identity           | ... (`ready` / `would write` / `failed (...)`) |
| Working repos               | ... (`ready (N from tier A\|B\|C)` / `defaulted to empty`) |
| Meta-repo CLAUDE.local.md   | ... |
| Machine-local directory     | ... (`ready` / `created` / `FATAL`) |
| Machine-local tracked files | ... (`ready (4/4)` / `partial (N/4: <missing>)` / `customized (<file> preserved)` / `FATAL`) |
| bin/ resolvers              | ... (`ready (7/7)` / `partial (N/7: <missing>)` / `FATAL`) — `machine-local` (registry reader) + `claude-home` (path resolver) + `python3.cmd` shim, plus three `.cmd` Windows shims |
| Windows PATH + Python shims | ... (n/a non-Windows / `ready` / `PATH-added, restart shells` / `WARNING: <stub\|alias\|no-python>`) |
| Registry seed               | ... (`seeded (Y)` / `declined (N)` / `skipped (non-interactive)` / `pre-existing`) |
| Coordinator plugin.mirrors  | ... (`ready` / `would write` / `skipped (--check-only)`) |
| `~/.claude` git tracking    | ... |
| coordinator.local.md        | ... |
| Percolation                 | ... (n/a if not a percolation source) |
| Non-interactive contract    | ... (`not_invoked` / `applied (skipped: N, defaulted: M, failed: 0)`) |
| Render template helper      | ... (`ready` / `missing`) |
| Project scaffolding         | Run `/project-onboarding` — it owns lazy directory creation, lessons file, and tracker |

### Available commands

- `/session-start` — Orient session, load context, choose work
- `/session-end` — Wrap up, capture lessons
- `/handoff` — Save state for next session
- `/review` (plans) and `/review-code` (diffs) — Self-contained review skills with inline routing; shared phases in `docs/wiki/reviewer-pipeline.md`
- `/update-docs` — Refresh project documentation, maintain docs/README.md index
- `/distill` — Extract knowledge from session artifacts into wiki guides
- `/project-onboarding` — Full project scaffolding (CLAUDE.md, tracker, docs/README.md, wiki structure)
- `/percolate` — Publish to a registered target; first-run setup walks `docs/wiki/percolate-setup.md` automatically (also walked by `/setup` percolation phase)
```

### Plugin-bundled doctrine wikis

After install, the plugin ships doctrine as wiki guides at `<plugin-install-path>/docs/wiki/`. Skim a few: `delegate-execution.md`, `receiving-code-review.md`, `daily-branch-discipline.md`, `tiered-context-loading.md`. These travel with the plugin install.

If any **required** items are missing (git), note prominently. If recommended items (Agent Teams, CLAUDE.md import) are missing, list concrete next steps.

**Hard-precondition rows.** The four Machine-local rows are non-optional: `FATAL` means Phase 3 halted (table partial; downstream skills won't function). `Registry seed` is informational only.

End with: _"`/setup` is environment-only. Run `/project-onboarding` to scaffold a new project (CLAUDE.md, tracker, sessions directory, lessons file). Then run `/session-start` to begin work."_ If `--check-only`, show the table but note what *would* be created/configured without the flag.
