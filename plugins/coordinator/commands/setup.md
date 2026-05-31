---
description: Set up the coordinator plugin — check prerequisites, verify environment, configure project. Safe to re-run.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive]"
---

# Coordinator Setup

<!-- spec-backlink: docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md -->

Environment and project setup for the coordinator plugin. This is a **guided install** — you participate in the shape decisions; the agent moves fast on mechanism. Safe to re-run — skips anything already configured.

## Execution dial and structural fork

**Execution dial:** The default mode is **agent-led** — the agent drives all mechanical steps, prompting only where a genuine decision is needed. Pass `--non-interactive` to suppress all `AskUserQuestion` calls (useful in scripted or CI contexts); see the **D4 Non-Interactive Contract** below for per-site fallback behaviour.

**Structural fork — Track A / Track B:** Before any phase, detect which track applies:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/detect-existing-claude-home.sh"
# Emits: track=A  (fresh install — ~/.claude is empty or absent)
#     or track=B  (existing setup — ~/.claude already has content)
```

- **Track A (fresh install):** Proceed through all phases below. Every step runs from zero — no merge, no cherry-pick, no selective adoption.
- **Track B (existing setup):** Surface a minimal-honest message at the top of the status report:

  > **Existing `~/.claude` detected.** This guided install sets up the coordinator from zero. If you have an existing setup you want to keep, the merge is yours to do — this command does not cherry-pick or partially adopt. Re-running `/setup` is safe; it skips anything already present. To see environment state without changes, run `/setup --check-only`.

  Then continue through all phases as normal (idempotency guards mean no existing content is overwritten). Do NOT offer a merge engine or selective-adoption UI.

## Check-only mode

If `$ARGUMENTS` contains `--check-only`: report environment state without making any changes. Every phase runs its read-only checks and emits status rows, then stops before any mutation. Combine with `--non-interactive` freely — both flags are orthogonal.

## D4 Non-Interactive Contract

<!-- spec-backlink: D4 in docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md -->

Each prompt site is annotated: `skip-with-note` (skip, surface in status table), `default-with-warning` (apply safe default, surface value), or `fail-loud` (exit non-zero with remediation; no safe default). Unannotated sites default to `fail-loud`. `--check-only` prevents all mutation; `--non-interactive` controls only prompt fallback. Both are orthogonal and may be combined.

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

### 1a.1. Git-config hardening (concurrent-EM lock safety)

Harden **this repo's** git config with `gc.autoDetach false` so git's auto-maintenance runs synchronously instead of detaching into a background process — the detached child is the contributor to orphaned `.git/index.lock` files under concurrent-EM on Git-for-Windows (root-cause in `docs/wiki/concurrent-em-hazards.md` § H21). Skip under `--check-only` (report the current value instead).

```bash
"$HOME/.claude/plugins/coordinator/bin/coordinator-configure-git"
```

Idempotent. Scoped per-repo by design — the breadth comes from `/project-onboarding` § 3f.5 (new repos) and every coordinator session boot (`session-init.sh` asserts it in whatever repo a session opens), so every coordinator-managed repo self-hardens without touching the user's unrelated repos. The helper also accepts `--global` if an operator deliberately wants the machine-wide default, but `/setup` does not set it globally (avoids changing auto-gc behavior in non-coordinator repos).

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

### 1c.1 JSON processor (jq)

```bash
command -v jq 2>/dev/null || echo "not_found"
```

- If found: ready. Required for `orphan-branch-sweep.sh --format json` (load-bearing in `/workday-start` Step 1.10 Addon Health).
- If not found: **required for JSON output** (strongly recommended). Without `jq`, `orphan-branch-sweep.sh` auto-falls-back to `--format text`, so `/workday-start` still classifies severities — but any downstream consumer that JSON-parses the sweep output will fail silently on the text fallback. Install from https://jqlang.org/download/.

### 1d. Deep research plugin

Check if the deep-research plugin is installed:

```bash
ls ~/.claude/plugins/deep-research/commands/web.md 2>/dev/null || \
ls ~/.claude/plugins/cache/*/deep-research/*/commands/web.md 2>/dev/null || \
echo "not_found"
```

**If found:** ready. Note which pipelines are available. Also check:
- Agent Teams env var (already checked above — if missing, flag it as **required** here, not just recommended)
- NotebookLM sub-plugin: check for `notebooklm/.mcp.json` in the deep-research plugin directory. If present, note that Pipeline D (media research) requires the `notebooklm-mcp-cli` package and Google authentication (`nlm login`).

**If not found:** the deep-research plugin is **default-on** — offer to install from `https://github.com/dbc-oduffy/deep-research-claude` into `~/.claude/plugins/deep-research/`. Do NOT offer the UE/holodeck/game-dev stack or project-rag alongside it.

<!-- D4 annotation: skip-with-note — install offer is elective; --non-interactive skips and notes status. -->

Under `--non-interactive`: skip; emit `deep_research_plugin: not_found (install offer suppressed — non-interactive)`. Under `--check-only`: emit `deep_research_plugin: not_found (would offer install)`.

Under interactive, offer Y/n (default Y). On Y: clone/install; if clone fails, report and continue. On n: skip, note manual install later.

Deep-research presence/absence is an **explicit row** in the Phase 7 status table regardless of outcome.

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

- **Under `--non-interactive`:** fail-loud — *"--non-interactive requires `~/.claude/coordinator-identity.yaml` to exist (`version: 1`, `operator_name: <string>`). Run `/setup` interactively first."* Status: `operator_identity: failed (--non-interactive without identity file)`. Stop phase.

- **Under interactive:** ask via `AskUserQuestion` once: *"What name should the meta-repo collaboration doctrine address you by? (Substituted as `PM_NAME` in `CLAUDE.local.md` — first name, handle, whatever fits.)"* Open-ended, no suggested options.

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
WORKING_REPOS=$(bash "${CLAUDE_PLUGIN_ROOT}/lib/discover-working-repos.sh")
```

Helper runs Tier A (`~/.claude/projects/` activity record, `X--Foo` → `X:\Foo`) then Tier B (`~/dev`, `~/Projects`, `/x`, etc.). Filters meta-repo, `AppData/Local/Temp`, bare drive roots. Returns up to 20 (A) or 30 (B) candidates.

**Tier C — Ask the operator** (if helper returned empty). <!-- D4: default-with-warning — empty list is documented neutral default. --> Under `--non-interactive`: skip; set `WORKING_REPOS` to placeholder (*"No working repos discovered at install time. Edit this section to list your projects."*); status `working_repos: defaulted to empty (non-interactive)`. Under interactive: ask for a code folder (e.g. `~/dev`, `C:\code`) via `AskUserQuestion`; re-probe Tier B inside it; if still empty, record the named folder with a "no repos yet" note.

**Build `WORKING_REPOS` block.** Markdown list: `` - `<path>` — <one-line from README> ``. Tier A annotates top 3 `(active recently)`. Persist at `~/.claude/working-repos.yaml` (atomic mv; schema: version/discovered_at/discovery_tier/repos[path+source]). Status: `working_repos: ready (N from tier {A|B|C})`. Under `--check-only`, run Tiers A+B read-only, skip YAML write and Tier C prompt.

**Step 5 — Render `~/.claude/CLAUDE.local.md`.**

Check existence (`test -f ~/.claude/CLAUDE.local.md`). Under `--check-only`: emit `meta_repo_doctrine: would write` (missing) or `ready` (present) and skip. Otherwise invoke the render-template helper:

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

All mechanical work (directory creation, tracked-file install, bin/ resolver install, Windows PATH integration, Python-resolution health check) is encapsulated in `coordinator/lib/install-substrate.sh`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/install-substrate.sh"
```

Helper: fails-loud on missing source-of-truth dirs (hard precondition — `machine-local` is shelled out by project-rag, holodeck, deep-research); honors `CLAUDE_HOME` (`docs/wiki/machine-local-registry.md § 4a`) and `COORDINATOR_NON_INTERACTIVE=1`; preserves operator-customized files with one-line notices; skips Windows checks on non-Windows. Installs 7 bin/ artifacts (3 `machine-local`, 3 `claude-home`, 1 `python3.cmd` shim) — `.cmd` shims prevent "Select an app" pickers on extensionless scripts (`docs/wiki/windows-cmd-shims.md`). Orphan AppX stub deletion requires `[y/N]` consent.

### Step 2 — Never overwrite live registry files

If `~/.claude/machine-local/registry.toml` or `~/.claude/machine-local/registry.local.toml` exists, leave both untouched regardless of `.example` updates. Same rule for any `<concern>.toml` and `<concern>.local.toml`. The operator's machine-local values are theirs.

### Step 3 — Optional seed prompt (declinable, interactive only)

<!-- D4 annotation (seed prompt): skip-with-note — seed is elective; --non-interactive skips it and notes that the operator should copy .example → real by hand. -->

Full interactive script (prompt text, On Y write procedure, `machine-local set` invocations, On N): `docs/wiki/setup-reference-detail.md` § Phase 3 Step 3.

**Skip entirely** if either registry file already exists (idempotency). Under `--non-interactive`: skip; emit `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`. Under interactive: offer Y/n to seed the four standard `repos.*` keys; write declarations to `registry.toml` and path values to `registry.local.toml` via `machine-local set` (never by hand-edit). **On N:** leave both absent.

**Test surface** (expected; do not actually run setup): Fresh install → directory, all tracked files, all 7 bin/ artifacts present; seed prompt fires. Re-run → no overwrites, no prompts. `--non-interactive` → substrate laid, no seed prompt, no registry files. Operator-modified file → preserved with notice. **See:** `docs/wiki/machine-local-registry.md`, `coordinator/lib/install-substrate.sh`, `coordinator/lib/claude-home/README.md`, `docs/wiki/coordinator-doctor.md`.

### Step 5 — Register coordinator plugin in `plugin.mirrors` (idempotent)

<!-- spec-backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 / AC-7 -->

Coordinator's live install IS the canonical source — `~/.claude/` itself. No inward propagation step is needed; edits flow outward via `publish.sh`. Register this in `registry.local.toml::plugin.mirrors` so `check-plugin-drift.sh` surfaces it as `n/a-by-design`.

Run under `--non-interactive`. Pass `--check-only` when `$ARGUMENTS` contains it.

```bash
_mirror_flag=""
[[ "${ARGUMENTS:-}" == *"--check-only"* ]] && _mirror_flag="--check-only"
bash "${CLAUDE_PLUGIN_ROOT}/lib/register-coordinator-mirror.sh" $_mirror_flag
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
python3 -m pip install -e "${CLAUDE_PLUGIN_ROOT}/whoami/"
```

On exit 0: `coordinator_whoami: ready`. On non-zero: `coordinator_whoami: failed` (log pip stderr tail separately; do NOT halt the chain — this isn't a hard precondition like Step 1). Add row to Phase 7 table. Post-install probe P-5 in `docs/wiki/coordinator-doctor.md`.

---

### Step 7 — Scaffold canonical document structure (idempotent)

<!-- spec-backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 6 -->
<!-- the Director of Engineering F5: pass --root explicitly so the scaffold targets the coordinator install root, not whatever cwd is at invocation time. -->

Scaffold the canonical directory structure (eager entries from `canonical-structure.yaml`) into the coordinator meta-repo (`~/.claude`). This lands `cross-repo/` with its schema-documenting README so the inbound cross-repo memo surface is discoverable from day 1.

Resolve the coordinator install root the same way other Phase 3 steps do — via `CLAUDE_HOME`:

```bash
_scaffold_root="${CLAUDE_HOME:-$HOME/.claude}"
_scaffold_script="${CLAUDE_PLUGIN_ROOT}/bin/scaffold-canonical-structure.sh"
```

Skip mutations under `--check-only` (emit status row `canonical_structure: would scaffold`).

Under normal or `--non-interactive` run:

```bash
bash "$_scaffold_script" --root "$_scaffold_root"
```

The script is idempotent — silently skips dirs and READMEs that already exist, never clobbers existing content. On success: status row `canonical_structure: ready`. On non-zero exit: status row `canonical_structure: failed` (log stderr; do NOT halt the chain — scaffold is advisory, not hard infrastructure).

Add a `Canonical structure` row to the Phase 7 status table.

---

### Step 8 — Write fan-out large-wave threshold (idempotent)

<!-- spec-backlink: docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md § C6 -->

Write the cores-scaled soft ramp-reminder threshold (`3 × logical CPU count`, floored at 1) that `fan-out-dispatch.sh` reads before launching a large wave — a **speed-taper advisory, not a cap**. Never clobbers a manual override — idempotency guard uses `machine-local keys` (registry layers only), not `machine-local has`. Logic lives in `bin/capture-fan-out-threshold.sh` (covered by `bin/capture-fan-out-threshold.test.sh`):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-fan-out-threshold.sh"           # normal run
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-fan-out-threshold.sh" --check-only  # check-only: emits would write (N)
```

Add a `Fan-out threshold` row to the Phase 7 status table from the script's output (`written (N)` / `pre-existing` / `would write (N)`).

---

## Phase 4 — Meta-repo doctrine

### `~/.claude` git tracking

Check whether `~/.claude` is a git repo (`git -C ~/.claude rev-parse --show-toplevel 2>/dev/null || echo "not_a_repo"`).

- **Repo:** ready. If no remote, suggest adding one for machine-loss recovery. Also check that per-machine state files are gitignored: `grep -qE '^/?coordinator-setup-state\.yaml' ~/.claude/.gitignore 2>/dev/null`. If `gap` (and not `--check-only`), offer to append the `# --- Coordinator per-machine state ---` block from `templates/dotgitignore.tmpl` (do not auto-edit). Status row: `claude_gitignore: covered` / `gap (offered)` / `gap (declined)`.

- **Not a repo, not `--check-only`:** offer to initialize. <!-- D4: default-with-warning — defaults to Skip under --non-interactive. Status: `claude_git_tracking: skipped (non-interactive default)`. --> Under `--non-interactive`: skip. Under interactive: **Initialize (Recommended)** — `git init ~/.claude`, lay down starter `.gitignore` if absent, commit `chore: initialize Claude Central` baseline; or **Skip** (re-asks next run). Do NOT push to a remote.

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
fast_test_cmd: "<your-project-fast-test-command>"  # optional; omit when not applicable
---
```

**`fast_test_cmd` (optional).** Command run by `/workday-complete` Step 1 and `/workweek-complete` Step 2 via `cs_resolve_fast_test_cmd` (sourced from `lib/coordinator-resolve-validation-cmd.sh`). Resolution order: `COORDINATOR_FAST_TEST_CMD` env var → this key → skip-with-notice. When absent: `Validation: skipped`. Any shell-valid form: `npm run test:fast`, `cargo test --lib`, `python scripts/run-tests.py --tier fast`, etc.

### Currency stamp (idempotent)

<!-- spec-backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1 -->
<!-- D4: default-with-warning — stamp is written silently; skip-with-note under --check-only. -->

Record which `COORDINATOR_SCHEMA_VERSION` the current repo's coordinator scaffolding was set up against.
This enables the drift probe (doctor P-13, Wave-2) to detect when scaffolding has fallen behind the live plugin.

Under `--check-only`: read the stamp if present and report `currency_stamp: current (vN)` / `currency_stamp: drift (vN->vM)` / `currency_stamp: unstamped(legacy)` / `currency_stamp: would write`. No mutation.

Otherwise (idempotent write):

```bash
PLUGIN_ROOT="${CLAUDE_HOME}/plugins/coordinator-claude/coordinator"
source "${PLUGIN_ROOT}/lib/coordinator-currency.sh"
coordinator_currency_write "$(pwd)" "${PLUGIN_ROOT}"
```

Add a `Currency stamp` row to the Phase 7 status table (`written (vN)` / `current (vN)` / `failed — <reason>`).

---

## Phase 6 — Optional

### Persona Customization

<!-- D4: default-with-warning — Keep defaults is canonical baseline. -->

Under `--non-interactive` or `--check-only`: apply **Keep defaults**, status `persona_customization: skipped (non-interactive default: keep defaults)`.

Under interactive:

> The coordinator includes named reviewer personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering). Customize their names? **Keep defaults** / **Customize**

If customize: no `rename-personas.sh` helper currently ships — hand-edit persona names across agent files and prompts/skills referencing them. Canonical persona-to-role vocabulary in `NAME_TO_ROLE` table at `plugins/coordinator/bin/publish-time-transform.sh` (exclude that file from search-replace to avoid self-corruption). One-time cosmetic choice; automation queued.

---

### Percolation Setup (if applicable)

Check `test -f setup/publish.sh`. If absent: skip silently (not a percolation source). If present: check registered targets via `source setup/publish-targets.sh && echo "TARGET_COUNT:${#TARGETS[@]}"`.

- **`MISSING_TARGETS` or `TARGET_COUNT:0`:** Walk `docs/wiki/percolate-setup.md` Steps 1–4 inline (register target, scaffold `.percolate-ignore` and hook dirs). Interactive; do not skip.
- **All targets configured** (`.percolate-ignore` + hook dirs present): status `Percolation: N target(s) configured`.
- **Partially configured:** surface gap and offer to run setup for unconfigured target(s).

Under `--check-only`, report state only. Add a `Percolation` row to the Phase 7 status table.

---

## Phase 7 — Status Report

### Step 0 — Record setup-concluded receipt (idempotent)

<!-- spec-backlink: docs/wiki/coordinator-setup-state-receipt.md -->
<!-- D4: default-with-warning — no prompt site; fires mechanically under --non-interactive same as interactive. -->

Record the enduring `setup_concluded` milestone so sibling repos can confirm coordinator is ready before chaining their own setup/orientation. Idempotent — first occurrence wins.

Skip under `--check-only` (emit status row `setup_state_receipt: would record`).

Otherwise:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/coordinator-setup-state.sh" record setup_concluded
```

Add a `Setup-state receipt` row to the status table (`recorded` / `pre-existing` / `would record`).

Present a summary table with one row per check above. Full status-row value-sets and available-commands list: `docs/wiki/setup-reference-detail.md` § Phase 7.

### Plugin-bundled doctrine wikis

After install, the plugin ships doctrine as wiki guides at `<plugin-install-path>/docs/wiki/` (`delegate-execution.md`, `receiving-code-review.md`, `daily-branch-discipline.md`, `tiered-context-loading.md`). If any **required** items are missing (git), note prominently. If recommended items (Agent Teams, CLAUDE.md import) are missing, list concrete next steps.

**Hard-precondition rows.** The four Machine-local rows are non-optional: `FATAL` means Phase 3 halted (table partial; downstream skills won't function). `Registry seed` is informational only.

### Optional next step — guided onboarding

Skip under `--check-only`. After the status table, offer: *"Want a guided tour? Just say **'walk me through the coordinator.'**"* If accepted, record `orientation_started` then read `docs/wiki/getting-started.md` (plugin-relative) and facilitate the three movements (Orient → Make it yours → Test drive). The guide's `## For the EM facilitating this` section is your playbook; it records `orientation_completed`. All customizations land in `~/.claude` — never a source-repo clone. If declined, point to `/session-start`.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/coordinator-setup-state.sh" record orientation_started
```

End with: _"`/setup` is environment-only. Run `/project-onboarding` to scaffold a new project (CLAUDE.md, tracker, sessions directory, lessons file). Then run `/session-start` to begin work — or say "walk me through the coordinator" for a guided tour first."_ If `--check-only`, show the table but note what *would* be created/configured without the flag.

**Refinement target close.** Include this line verbatim in every next-steps block (not under `--check-only`):

> Your `~/.claude` is the surface you evolve — git-track it and back it up; never edit the coordinator clone.

### Optional next step — bootstrap repo scaffolding

<!-- spec-backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 4 / AC8 -->
<!-- D4 annotation: skip-with-note — elective offer; suppressed under --non-interactive and --check-only. -->

**Suppressed under `--non-interactive` or `--check-only`.** Status row: `bootstrap_offer: suppressed (--non-interactive|--check-only)`. No `AskUserQuestion`, no `/bootstrap-repos` invocation, no offer text.

Under interactive (after the status table has been shown), read `~/.claude/working-repos.yaml` to get the discovered repo count (N). If N > 0, offer:

> Discovered **N** working repo(s) in `working-repos.yaml`. Want to bootstrap coordinator scaffolding into them? Run `/bootstrap-repos` — Express mode applies to all, Custom mode lets you pick per-repo. 0% destructive; every change is git-revertible.

If the operator accepts, instruct them to run `/bootstrap-repos` (do NOT inline the scaffolding here — `/setup` is environment-only; `/bootstrap-repos` owns per-project scaffolding). If declined or N = 0, skip silently.

Status row: `bootstrap_offer: offered (N repos)` (after offer shown) / `suppressed (--non-interactive|--check-only)` / `skipped (0 repos discovered)`.
