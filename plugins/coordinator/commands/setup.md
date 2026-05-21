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

Each prompt site in this skill carries one of three annotations:

- **`skip-with-note`** — Skip the prompt entirely; surface the skip in the status table. No side effect.
- **`default-with-warning`** — Apply the documented safe default without prompting; surface the defaulted value in the status table.
- **`fail-loud`** — Exit non-zero immediately with a remediation message. Used when no safe default exists.

**Default for any unannotated site is `fail-loud`.**

Flag semantics:
- `--check-only` is a **strict superset**: it prevents all mutation regardless of interactivity. Applies with or without `--non-interactive`.
- `--non-interactive` controls **only the prompt fallback** — it does not affect mutation policy. A site that writes under interactive mode still writes under `--non-interactive` (unless `--check-only` is also set).
- Both flags are **orthogonal** and may be combined: `--check-only --non-interactive` runs a fully read-only, non-prompting check.

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

The coordinator setup persists the operator's name to `~/.claude/coordinator-identity.yaml` so that downstream phases and re-runs can read it without re-prompting. This phase is idempotent: if the identity file already exists with a matching schema, it skips the prompt silently.

**Step 1 — Read identity file if present.**

```bash
test -f ~/.claude/coordinator-identity.yaml && echo "exists" || echo "missing"
```

If the file exists, read it and branch on its content:

- **`version: 1` and `operator_name` present** → use the stored `operator_name` value; skip the `AskUserQuestion`. Status row: `operator_identity: ready`. Proceed to Step 3 (render CLAUDE.local.md).
- **`version:` present and higher than 1** → fail-loud: emit an error message — *"coordinator-identity.yaml has schema version {N}, which this installer does not know how to read. Either downgrade to a coordinator version that supports v{N}, or delete ~/.claude/coordinator-identity.yaml and re-run /setup to recapture."* Status row: `operator_identity: failed (unknown schema version {N})`. Stop this phase.
- **`version: 1` present but `operator_name` missing (or `version:` absent entirely)** → migrate silently: treat as if the file is absent and proceed to Step 2. (Today there are no v0 consumers, so this branch is a no-op placeholder for future schema migration.)

If `$ARGUMENTS` contains `--reconfigure`, treat the file as absent regardless of its content — re-prompt even when the identity file is valid.

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

The rendered `CLAUDE.local.md` includes a "Your working repos" section so the EM (operating as DoE in the meta-repo) knows which sibling projects exist. Three-tier discovery (stop at first non-empty), encapsulated in a helper:

```bash
WORKING_REPOS=$(bash "${CLAUDE_PLUGIN_ROOT}/coordinator/lib/discover-working-repos.sh")
```

The helper runs **Tier A** (`~/.claude/projects/` activity record — path-encoded directory names, `X--Foo` → `X:\Foo`) then **Tier B** (common dev-folder layouts: `~/dev`, `~/Projects`, `/x`, etc.) and stops at first non-empty result. Filters meta-repo, `AppData/Local/Temp`, bare drive roots. Returns up to 20 (Tier A) or 30 (Tier B) candidates.

**Tier C — Ask the operator** (if helper returned empty). Operator is likely new to coding or keeps work somewhere non-standard.

<!-- D4 annotation: default-with-warning — empty list is the documented neutral default. Under --non-interactive, skip the prompt, emit status row: working_repos: defaulted to empty (non-interactive). The CLAUDE.local.md gets a placeholder note that the operator can fill in later. -->

Under `--non-interactive`: skip the prompt, set `WORKING_REPOS` to a placeholder paragraph (*"No working repos discovered at install time. Edit this section to list your projects."*), emit status row `working_repos: defaulted to empty (non-interactive)`.

Under interactive (default), ask once via `AskUserQuestion`:

> The coordinator setup couldn't find existing code projects on this machine. In which folder do you usually keep code work? (e.g. `~/dev`, `~/Projects`, `C:\code`) — leave blank if you don't have one yet.

If the operator names a folder that exists, re-probe Tier B inside it. If still empty (or blank reply), record the named folder (or `~/dev` as a forward-looking suggestion) as the working area with a one-line "no repos yet" note.

**Build the `WORKING_REPOS` block.** Format the discovered list as a markdown bulleted list with one repo per line:

```
- `<path>` — <one-line if a README's first heading is readable, else blank>
```

For Tier A results, optionally annotate with relative mtime (`(active recently)` for top 3). For empty / unknown, fall back to the placeholder paragraph.

Persist a machine-readable copy at `~/.claude/working-repos.yaml` (idempotent, atomic mv) so future doctrine/skills can re-read without re-discovering:

```yaml
# ~/.claude/working-repos.yaml — generated by /setup; safe to hand-edit
version: 1
discovered_at: <ISO-8601>
discovery_tier: A | B | C
repos:
  - path: <absolute path>
    source: claude-projects-dir | dev-folder-scan | operator-supplied
```

Status row: `working_repos: ready (N from tier {A|B|C})`.

If `--check-only`, run Tiers A and B (read-only), report what *would* be written, but skip both the YAML write and the AskUserQuestion in Tier C.

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

Skip under `--check-only`. Under `--non-interactive`, run all mechanical work but skip Step 3's seed prompt.

### Step 1 — Run install-substrate helper

The mechanical work — directory creation, tracked-file install, bin/ resolver install, Windows PATH integration, Windows Python-resolution health check — is encapsulated in `coordinator/lib/install-substrate.sh`. Invoke it:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/coordinator/lib/install-substrate.sh"
```

The helper:

- **Fails-loud and halts the entire setup chain** if any source-of-truth directory is missing — this is a hard precondition for downstream skills (project-rag, holodeck, deep-research all shell out to `bin/machine-local`); silently skipping leaves the operator with a broken-and-undiagnosable install. The helper writes `Phase 3 FATAL:` to stderr (naming the missing path and remediation paths: reinstall plugin, verify `CLAUDE_PLUGIN_ROOT`, confirm meta-repo working tree) and exits non-zero. The skill catches the non-zero exit and renders the Phase 7 status row: `machine_local_substrate: FATAL (templates missing)`.
- **Honors `CLAUDE_HOME`** (same precedence as `bin/claude-home` — see `docs/wiki/machine-local-registry.md § 4a`) so test sandboxes and CI redirect cleanly.
- **Preserves operator-customized files** with one-line notices; for `claude-home` artifacts, the notice is louder (cross-repo contract surface — customization is anti-doctrine).
- **Skips Windows PATH + AppX checks** on non-Windows operators; honors `COORDINATOR_NON_INTERACTIVE=1` to suppress the AppX-stub deletion consent prompt.

The seven installed bin/ artifacts and their sources:

| Live file | Source-of-truth |
|---|---|
| `~/.claude/bin/{machine-local, _machine_local.py, machine-local.cmd}` | `coordinator/templates/bin/` |
| `~/.claude/bin/{claude-home, _claude_home.py, claude-home.cmd}` | `coordinator/lib/claude-home/` |
| `~/.claude/bin/python3.cmd` | `coordinator/templates/bin/` |

The three `.cmd` files are Windows shims for the extensionless scripts and the `python3` name; they prevent the "Select an app to open" picker when Windows `ShellExecute` falls back to file-association lookup. Harmless on Linux/macOS (unused). Rationale: `coordinator/docs/wiki/windows-cmd-shims.md`.

**Windows Python-resolution health** (Step 1's Windows branch) catches three configurations that defeat the shims: orphan AppX stubs (zero-byte reparse-points from uninstalled Store Python), Store-alias-on-PATH (Get-Command resolving under `WindowsApps`), and no-Python-at-all. The helper surfaces remediation; only the orphan-stub deletion is mutating, and it requires explicit `[y/N]` consent on a TTY.

### Step 2 — Never overwrite live registry files

If `~/.claude/machine-local/registry.toml` or `~/.claude/machine-local/registry.local.toml` exists, leave both untouched regardless of `.example` updates. Same rule for any `<concern>.toml` and `<concern>.local.toml`. The operator's machine-local values are theirs.

### Step 3 — Optional seed prompt (declinable, interactive only)

<!-- D4 annotation (seed prompt): skip-with-note — seed is elective; --non-interactive skips it and notes that the operator should copy .example → real by hand. -->

**Skip entirely** if either `~/.claude/machine-local/registry.toml` or `registry.local.toml` already exists (idempotency).

Under `--non-interactive`: skip; emit status row `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`.

Under interactive, ask once via `AskUserQuestion`:

> Would you like to seed the registry with the four most common `repos.*` keys (coordinator, project-rag, project-rag-ue-addon, claude-unreal-holodeck)? Key declarations go to `registry.toml` (shared, tracked); per-machine path values to `registry.local.toml` (gitignored). Single-machine operators may put everything in `registry.toml`. [Y/n]

**On Y:** write `registry.toml` with the four keys + `schema = 1`, and `registry.local.toml` with the operator's typed paths (asked inline per key; blank allowed). **On N:** leave both absent.

### Step 4 — Test surface (expected behavior; do not actually run setup)

- **Fresh install:** directory, all tracked files, all 7 bin/ artifacts present after Step 1. Seed prompt fires interactively.
- **Re-run on populated install:** no overwrites, no prompts.
- **`--non-interactive`:** substrate laid down, no seed prompt, no `registry.toml`, no `registry.local.toml`.
- **Operator-modified file:** preserved; one-line notice; no overwrite.

**See:** `docs/wiki/machine-local-registry.md` (substrate doctrine + § 4a CLAUDE_HOME resolver), `coordinator/lib/install-substrate.sh` (mechanical contract), `coordinator/lib/claude-home/README.md` (claude-home module), `docs/wiki/coordinator-doctor.md` (post-install probes).

### Step 5 — Register coordinator plugin in `plugin.mirrors` (idempotent)

<!-- spec-backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 / AC-7 -->

The coordinator plugin's live install IS the canonical source — `~/.claude/` itself. No inward propagation step is needed; edits flow outward via `publish.sh`. Register this structural fact in `registry.local.toml` under `plugin.mirrors` so the drift probe (`bin/check-plugin-drift.sh`) can surface it as `n/a-by-design` rather than treating it as an unchecked entry.

Skip if `--check-only`. Run under `--non-interactive`.

**Idempotency check:** before writing, check whether the section already exists.

```bash
_reg="$(claude-home machine-local)/registry.local.toml"
if [ -f "$_reg" ] && grep -q '\[plugin\.mirrors\.coordinator-claude\]' "$_reg" 2>/dev/null; then
  echo "plugin.mirrors.coordinator-claude already registered — skipping."
else
  # Resolve coordinator live_path via claude-home
  _coordinator_live="$(claude-home plugins)/coordinator-claude/coordinator"

  # Append the section (atomic: write to tmp, append content, mv into place is not safe for append;
  # use a direct append after idempotency confirmed above)
  cat >> "$_reg" <<TOML

[plugin.mirrors.coordinator-claude]
# Live install IS canonical source — registered automatically by /coordinator:setup
# Drift probe and refresh script treat this as n/a-by-design; no git/venv legs to check.
propagation_mode = "source_is_live"
live_path = "${_coordinator_live}"
TOML

  echo "Coordinator plugin registered (source_is_live mode). Drift probe will skip it as n/a-by-design."
fi
```

If `registry.local.toml` does not yet exist at this point (operator declined seed in Step 3), create it with minimal TOML boilerplate before appending:

```bash
_reg="$(claude-home machine-local)/registry.local.toml"
if [ ! -f "$_reg" ]; then
  printf 'schema = 1\n' > "$_reg"
fi
```

Run this creation guard before the idempotency check above, so the grep is always against an existing file.

**`--check-only` behavior:** if the section is absent, emit status row `coordinator_plugin_mirrors: would write`; if present, emit `coordinator_plugin_mirrors: ready`.

Add a `Coordinator plugin.mirrors` row to the Phase 7 status table.

---

### Step 6 — Install `coordinator_whoami` package (idempotent)

<!-- spec-backlink: docs/plans/2026-05-21-whoami-first-class-substrate.md § Chunk 1 / AC-1, AC-2, AC-3, AC-15 -->

<!-- D4 annotation (coordinator_whoami install): default-with-warning — no prompt site; install fires mechanically. Under --non-interactive: same as interactive default (no prompt was ever asked). Status row is `failed` on non-zero pip exit; chain continues. -->

Probe whether the package is already importable:

```bash
python3 -c "import coordinator_whoami" 2>/dev/null
```

**If import succeeds:** emit status row `coordinator_whoami: ready`. No mutation. (Re-using an existing install is invisible to the status table; the idempotency contract is satisfied.)

**If import fails:**

- Under `--check-only`: emit status row `coordinator_whoami: would write`. No mutation. Exit Step 6.
- Otherwise: run the editable install:

```bash
python3 -m pip install -e "${CLAUDE_PLUGIN_ROOT}/coordinator/whoami/"
```

Capture the exit code.

- On exit 0: emit status row `coordinator_whoami: ready`.
- On non-zero exit: emit status row `coordinator_whoami: failed`. Log the pip stderr tail separately (do NOT encode reason into the status value — `failed` is a bare token per the schema). **Do not halt the setup chain** — surface the failure in the status table and continue. This step is not a hard precondition like the `machine-local` substrate in Step 1 (which issues FATAL and aborts). Missing `coordinator_whoami` is operationally visible but not chain-blocking.

Under `--non-interactive`: behavior is identical to the default interactive path — the install fires without prompting. There is no prompt site in this step.

Add a `coordinator_whoami` row to the Phase 7 status table.

**See:** `docs/wiki/coordinator-doctor.md` — post-install probe P-5 (package importable) verifies this step's outcome on the live system.

---

## Phase 4 — Meta-repo doctrine

### `~/.claude` git tracking

The meta-repo doctrine, plugins, and accumulated wikis benefit from version control — `git log` becomes the audit trail for how the operator's working methodology evolved. Check whether `~/.claude` is a git repo:

```bash
git -C ~/.claude rev-parse --show-toplevel 2>/dev/null || echo "not_a_repo"
```

- **If a repo:** ready. Optionally note whether a remote is configured (`git -C ~/.claude remote -v`) — if no remote, surface a one-line suggestion: *"Consider configuring a private remote so history survives machine loss."*
- **If not a repo and not `--check-only`:** offer to initialize:

  <!-- D4 annotation: default-with-warning — default to Skip under --non-interactive. Rationale: git init is reversible (rm -rf .git), but defaulting to init creates persistent metadata the operator may not want; Skip is the safer unattended default. Emit status row: claude_git_tracking: skipped (non-interactive default). -->

  Under `--non-interactive`: skip the AskUserQuestion, apply the **Skip** default, and emit status row `claude_git_tracking: skipped (non-interactive default)`. Do NOT run `git init`.

  Under interactive (default): ask via `AskUserQuestion`:

  > Your `~/.claude` directory isn't currently git-tracked. The coordinator setup recommends version-controlling this environment so the evolution of your collaboration doctrine, plugins, and wikis is auditable. Initialize a git repo at `~/.claude`?

  Two options via `AskUserQuestion`:
  - **Initialize (Recommended)** — runs `git init ~/.claude`, creates a starter `.gitignore` from the coordinator template (if one ships at `templates/dotgitignore.tmpl`, otherwise leave gitignore generation to a follow-up), commits a `chore: initialize Claude Central` baseline.
  - **Skip** — don't initialize; reissue this recommendation on next `/setup` run.

  Do NOT push to a remote automatically — that's the user's decision.

- **If not a repo and `--check-only`:** report `not_a_repo` and note that a non-check run would offer to initialize.

---

## Phase 5 — Project-local

### coordinator.local.md

Check if `coordinator.local.md` exists at the repo root:

```bash
test -f coordinator.local.md && echo "exists" || echo "missing"
```

**If it exists:** Read it and report the current `project_type` (and `project_subtypes` if present). Check for legacy values — if `project_type` is `unreal`, `meta`, or bare `web`, emit a one-line warning:

> ⚠ Legacy project_type detected: `{value}`. Suggested migration: set `project_type: game-dev` + `project_subtypes: [unreal]` (or `project_type: general` for `meta`, `project_type: web-dev` for `web`). Edit `coordinator.local.md` manually — this command does not auto-rewrite.

No other changes when file exists.

**If missing and not `--check-only`:** Ask the user what kind of project this is:

<!-- D4 annotation (project_type prompt): fail-loud — wrong project_type silently mis-routes domain agents downstream; failure is louder than silent mis-route. Note: this prompt only fires when coordinator.local.md is absent — the annotation governs what happens when it would fire under --non-interactive. -->

Under `--non-interactive`: fail-loud — emit: *"--non-interactive cannot create coordinator.local.md: project_type requires operator input (no safe default). Create coordinator.local.md manually with `project_type: general` (or the appropriate type) and re-run."* Stop this phase.

Under interactive (default):

> What type of project is this? This controls which domain specialists are available for routing.
>
> - **general** — Software project (the Staff Engineer for code review, standard workflow)
> - **game-dev** — Game development project (adds the Game Dev Reviewer reviewer, game-dev domain agents)
> - **web-dev** — Web project (adds the Front-End Reviewer for front-end review, the UX Reviewer for UX)
> - **data-science** — ML/data project (adds the Data Science Reviewer for data science review)

Then ask:

<!-- D4 annotation (project_subtypes prompt): default-with-warning — subtypes are advisory routing tags; empty is the documented neutral default. Under --non-interactive, write coordinator.local.md without a project_subtypes field and emit status row: coordinator_local_md: created (project_subtypes defaulted to empty, non-interactive). -->

Under `--non-interactive`: skip the subtypes prompt, apply the **empty subtypes** default (omit `project_subtypes:` from the file), and emit status row `coordinator_local_md: created (project_subtypes defaulted to empty, non-interactive)`.

Under interactive (default):

> Any subtypes? These are free-form advisory tags — no validation, no controlled vocabulary. Downstream routing does best-effort matching; mismatches simply don't trigger subtype-specific blocks. Examples: `unreal`, `unity` under game-dev; `react`, `nextjs` under web-dev. Comma-separated, or leave blank.

Create `coordinator.local.md` based on their answers:

```markdown
---
project_type: {type}
---
```

When subtypes were provided, include the `project_subtypes` field:

```markdown
---
project_type: {type}
project_subtypes: [{subtype1}, {subtype2}]
---
```

---

## Phase 6 — Optional

### Persona Customization

<!-- D4 annotation (persona customization prompt): default-with-warning — customization is opt-in cosmetic; Keep defaults is the canonical baseline. Under --non-interactive, skip the prompt, apply Keep defaults, and emit status row: persona_customization: skipped (non-interactive default: keep defaults). -->

After the core setup, ask once:

Under `--non-interactive`: skip the AskUserQuestion, apply **Keep defaults**, and emit status row `persona_customization: skipped (non-interactive default: keep defaults)`. Skip if `--check-only` too.

Under interactive (default):

> The coordinator includes named reviewer personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering). Would you like to customize their names?
>
> - **Keep defaults** — Use the built-in persona names
> - **Customize** — Choose your own names for the reviewers

If the user wants to customize, note that a `rename-personas.sh` helper is not currently shipped. Customization requires hand-editing the persona names in the agent files (one file per persona) and any prompts/skills that reference them by name. The canonical persona-to-role vocabulary lives in the `NAME_TO_ROLE` table in `plugins/coordinator/bin/depersonalize-for-publish.sh`; that table is the source of truth for which strings are persona-named and what their role labels are. Search-and-replace each persona name across the plugin tree (excluding the depersonalize script itself, which would self-corrupt).

This is a one-time cosmetic choice. Skip if `--check-only`. A future helper to automate this is queued; for now it's manual.

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

After install, the coordinator plugin ships its operating doctrine as wiki guides at `<plugin-install-path>/docs/wiki/`. Skim a few to see how the EM operates:

- `delegate-execution.md` — how the EM dispatches Sonnet executors against enriched specs.
- `receiving-code-review.md` — how the EM processes review feedback (no performative agreement; triage tables; verify-then-implement).
- `daily-branch-discipline.md` — one branch per machine per day, never branch off main mid-session.
- `tiered-context-loading.md` — how the EM picks between Tier 1 (curated) ↔ Tier 4 (Sonnet scout) for codebase questions.

These wikis are referenced from plugin files (CLAUDE.md, skills, commands) and travel with the plugin install — they update atomically with `claude plugin update coordinator`.

If any **required** items are missing (git), note them prominently.
If any **recommended** items are missing (Agent Teams, CLAUDE.md import), list concrete next steps.

**Hard-precondition rows.** The four Machine-local rows are non-optional: any `FATAL` value means Phase 3 halted the chain (the table is partial) and downstream skills will not function. The `Registry seed` row is informational only — neither absence nor decline blocks downstream skills, since `bin/machine-local` is registry-agnostic at the file level (operators can author keys later by hand-editing or copying `.example` → real).

End with: _"`/setup` is environment-only. Run `/project-onboarding` to scaffold a new project (CLAUDE.md, tracker, sessions directory, lessons file). Then run `/session-start` to begin work."_

If `--check-only`, show the table but note what *would* be created/configured without the flag.
