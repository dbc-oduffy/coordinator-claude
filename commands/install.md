---
description: "Installs the coordinator plugin — checks prereqs, configures project."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive] [--accept-no-git-auth]"
---

# Coordinator Install

Guided install — agent runs mechanism, operator decides shape. Re-run anytime; skips what's configured.

If `/coordinator:install` already resolves, skip to Step Zero.
Reverses via `coordinator/commands/uninstall.md`, which stays in lockstep: a write surface added here gets its disposition there in the same change.

Every fence below resolves the same ladder, not restated per step: `COORDINATOR_PYTHON` (interpreter); `REPO_CLAUDE_KLABAUTER` (repo-identity override, stays first); then the engine-root rung itself — `COORDINATOR_ENGINE_ROOT`; and `COORDINATOR_SETTINGS_HOME`. All unset: resolve the registry first, then reuse the result for the rest of the run.

**PowerShell hosts (rung 0, Shape W — `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`).** `${...}` POSIX expansion is not runnable at all here. Every fence below ships a paired ```powershell block, one command per fence. **Assign these ONCE per shell session, before the fences — not per fence.** The PowerShell fences below consume them by name and show no inline assignment; if you are running each fence in a fresh shell, re-run the assignments in it first, and stop if one comes back empty rather than letting an empty root concatenate into a path:
- `$pythonExe` = `$env:COORDINATOR_PYTHON`, else `python3` (real interpreter, guaranteed by Phase 3's install step).
- `$engineRoot` = `& $pythonExe "$env:CLAUDE_PLUGIN_ROOT\hooks\scripts\_engine_root.py"` — the ratified resolver. It owns the whole ladder, including the `REPO_CLAUDE_KLABAUTER`/`COORDINATOR_ENGINE_ROOT` live-tree overrides, and lands on the **published engine mirror**. Never re-derive that order by hand.
- `$claudeHome` = `$env:CLAUDE_HOME ?? $HOME`.


**POSIX hosts (macOS/Linux, rungs 1-2).** Every fence below consumes `COORDINATOR_SETTINGS_HOME`/`ENGINE_ROOT` by bare name and shows no inline re-resolution — a `${VAR:-default}` shell-parameter expansion reaching a settings-home forwarder inline, per fence, is out of scope for this doctrine surface (`resolve-coordinator-bin.md` rung 0). **Assign these two ONCE per shell session, before any fence below — not per fence.** If you are running a fence in a fresh shell, re-run both assignments in it first, and stop if one comes back empty rather than letting an empty root concatenate into a path:
- `COORDINATOR_SETTINGS_HOME`: default `$HOME/.coordinator-claude-settings` if not already set, then `export` it.
- `ENGINE_ROOT`: set to the output of running `"${COORDINATOR_PYTHON:-python3}" "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_engine_root.py"`, then `export` it — the ratified resolver; owns the whole ladder including the `REPO_CLAUDE_KLABAUTER`/`COORDINATOR_ENGINE_ROOT` live-tree overrides, and lands on the **published engine mirror**. Never re-derive that order by hand.



---

## Requirements

- bash: no version floor — macOS's stock 3.2 is fine.
- git, Python 3, jq.
- uv (Pipeline D), scc (optional), PowerShell 7+ / Windows Terminal (default-on, not hard blockers).
- Engine repo cloned (hard, not auto-discovered).
- **Sequence, exactly:** (1) clone the engine repo; (2) run this coordinator install; (3) restart Claude Code; (4) only then run the engine repo's own installer. Steps 1 and 2 read as circular only if "clone" and "install" are conflated — they are not the same step, and the engine's installer legitimately depends on coordinator already being installed.

## Structural fork

```bash
"${COORDINATOR_PYTHON:-python3}" "${ENGINE_ROOT:?ENGINE_ROOT unset — run the POSIX preamble above first (the resolver prints an empty line on a total miss — see § Backing script)}/coordinator/lib/detect-existing-claude-home.py"
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\lib\detect-existing-claude-home.py"`

Emits `state=<pristine|used-vanilla|configured>`. `configured`: surface "existing setup — merge is yours"; else proceed with no/light note. Never clobbers `CLAUDE.md`/`settings.json`/registry regardless of state (wiki).

## Flags

| Flag | Effect |
|---|---|
| `--check-only` | Read-only report — no mutations. |
| `--non-interactive` | Suppresses `AskUserQuestion`; per-site fallback is skip-with-note / default-with-warning / fail-loud (unannotated = fail-loud). |
| `--accept-no-git-auth` | Skips `clone_auth`. |

Both `--check-only`/`--non-interactive` combine freely. Environment-only here — `/coordinator:repo-setup` handles per-project scaffolding after this.

## Phase 1 — Environment

**Bash version.** No floor — any bash, including macOS's stock 3.2, is ready. If `probe_shell_login_env` (`coordinator_core.install.prereq_probe`) reports an orphaned bash login shell (bash login shell, `~/.bash_profile` missing `~/.local/bin`), offer `normalize-env --yes` to reconstruct it — detail: wiki.

```bash
sh "$_cc_claude_klabauter/coordinator/scripts/lib/invoking-shell-bash4-probe.sh" [--quiet]
```

Exit 1: surface the printed remediation verbatim (WARN, not a hard blocker).

**Git.** `git rev-parse --show-toplevel` — not a repo: warn, proceed.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/coordinator-configure-git"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-configure-git.exe"`

Sets `gc.auto 0`/`core.checkStat minimal`/`maintenance.strategy incremental`/
`maintenance.auto false`/`maintenance.prefetch.enabled false`; idempotent; skip under
`--check-only`.
**Cwd repo only** — it takes no repo argument. Every other registered worktree is reached by the
Phase 3 git-perf-config fleet sweep (Step 3.5a.1c), not by this call.

If the operator git-tracks `~/.claude`:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/install-meta-repo-precommit-hook" "$HOME/.claude"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\install-meta-repo-precommit-hook.exe" "$HOME\.claude"`

No-ops if not a git repo. Under `--check-only`, don't run it — report gate-marker presence instead.

Git-LFS: report presence only — never `git lfs install` (no flags) against a coordinator-hooked repo: it refuses to overwrite coordinator's own committed hooks and only offers `--force`, which would clobber them, so a per-repo hook install is permanently a no-op here and must not be attempted. Binary present: offer `git lfs install --skip-repo` (global filter config only, never touches repo hooks). Binary absent: advisory per-platform remediation (wiki). Always report which branch ran — never silent.

**Settings env values.** `python "$CLAUDE_PLUGIN_ROOT/bin/check-settings-env.py" --apply` asserts `settings.json`'s `env` block against `templates/settings-manifest.md` § Environment Variables — **values, not key presence**: a key at the wrong value gates a tool out of every session on the box while reading as configured. `--apply` writes only the all-machines rows; machine-specific ones are reported, never auto-written. Under `--check-only`, drop `--apply`. Env is read at process start — a repair lands on the next session, not this one.

**Python3.** Resolves and runs `--version`: ready. Not on PATH: fail-loud. Resolves but errors on `--version` (Windows App-Execution-Alias stub): warn — Phase 3 places a real interpreter.

**scc** (optional), **jq** (`command -v jq` — required for JSON output, else text fallback), **pwsh 7+**/**Windows Terminal** (offer install per-platform if absent, interactive only; commands: wiki) — presence checks only, no branch beyond offer-or-skip.

**NotebookLM (Pipeline D).** Check `grep -l "notebooklm-mcp"` in `~/.claude/settings.json` / `~/.claude.json` / `.mcp.json`. Not registered, interactive, `uv` present: offer to walk:

Install the CLI:

```bash
uv tool install notebooklm-mcp-cli
```

Authenticate:

```bash
nlm login
```

Register the MCP server:

```bash
nlm setup add claude-code
```

Then restart Claude Code. `uv` absent: offer defaults to decline. `--non-interactive`/`--check-only`: skip.

**Global CLAUDE.md.** No manual wiring — doctrine reaches the EM via SessionStart hook. Flag a stale `@…/coordinator/CLAUDE.md` import for removal if present.

## Phase 2 — Operator identity

Read `~/.claude/coordinator-identity.yaml`. `operator_name` present: use it. Absent (or `--reconfigure`): ask via `AskUserQuestion`. `--non-interactive` with none stored: fail-loud.

`--claude-home` takes the resolved `${CLAUDE_HOME:-$HOME}`, never `$HOME/.claude` — the op appends `.claude` itself, so passing the deeper path writes to `~/.claude/.claude/` and the file the next run reads stays absent.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}" --operator-name "${OPERATOR_NAME}"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\write-identity-file.exe" --claude-home "$claudeHome" --operator-name "$OPERATOR_NAME"`

Skip under `--check-only`.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/render-template" "${CLAUDE_PLUGIN_ROOT}/templates/CLAUDE.md.tmpl" -o "${CLAUDE_HOME:-$HOME}/.claude/CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" PM_NAME="${OPERATOR_NAME}"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\render-template.exe" "$env:CLAUDE_PLUGIN_ROOT\templates\CLAUDE.md.tmpl" -o "$claudeHome\.claude\CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" "PM_NAME=$OPERATOR_NAME"`

Never-clobber is the `--guard-sentinel` flag's own contract (exit 3 = hand-authored file preserved, skip). No `--check-only` flag on the primitive — skip the call there instead.

**Engagement posture (mandatory gate, both modes).** Reuse the identity read; `engagement_posture` present: use it. Absent: interactive asks precision/default/substrate-free (question text: wiki — these select engagement DISTANCE only, never technical skill); `--non-interactive` honors `--posture <value>`, else fail-loud.

```bash
git rev-parse --show-toplevel 2>/dev/null
```
→ `_EM_CONTEXT_REPO_ROOT` (falls back to `$PWD`).

```bash
"$COORDINATOR_PYTHON" "$REPO_CLAUDE_KLABAUTER/coordinator/bin/coordinator-resolve-validation-cmd.py" --read-key "${_EM_CONTEXT_REPO_ROOT:-$PWD}" engagement_posture
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\bin\coordinator-resolve-validation-cmd.py" --read-key ($_EM_CONTEXT_REPO_ROOT ?? $PWD) engagement_posture`

Differs from the identity-file value: fail-loud, don't write the overlay. Empty output (repo has no posture set): not a difference — proceed, treat as absent.

Persist the posture to the identity file:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}" --operator-name "${OPERATOR_NAME}" --engagement-posture "${ENGAGEMENT_POSTURE}"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\write-identity-file.exe" --claude-home "$claudeHome" --operator-name "$OPERATOR_NAME" --engagement-posture "$ENGAGEMENT_POSTURE"`

Render the overlay:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/render-posture-overlay" "${ENGAGEMENT_POSTURE}" "${_EM_CONTEXT_REPO_ROOT}/.claude/em-context.md"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\render-posture-overlay.exe" "$ENGAGEMENT_POSTURE" "$_EM_CONTEXT_REPO_ROOT\.claude\em-context.md"`

`--check-only`: append `--check-only` to the overlay call, writes nothing. Fail-loud if `_EM_CONTEXT_REPO_ROOT` is empty (must run inside a git repo).

```bash
git -C "${_EM_CONTEXT_REPO_ROOT}" check-ignore -q .claude/em-context.md
```

Exit 1: append (via Edit, never a shell redirect) to `.gitignore`:
```text
# Operator-local EM posture overlay — per-operator, never shared.
.claude/em-context.md
```
Exit >1: fail-loud, don't append. Already tracked: tell the operator to `git rm --cached` it.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/machine-local" array-append coordinator.installed_repos "${_EM_CONTEXT_REPO_ROOT}"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\machine-local.cmd" array-append coordinator.installed_repos "$_EM_CONTEXT_REPO_ROOT"`

Skip under `--check-only`. A repo onboarded later re-renders this overlay via `repo-setup` from the persisted value (wiki).

```bash
"${COORDINATOR_PYTHON:-python3}" "${ENGINE_ROOT:?ENGINE_ROOT unset — run the POSIX preamble above first (the resolver prints an empty line on a total miss — see § Backing script)}/coordinator/lib/discover-working-repos.py"
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\lib\discover-working-repos.py"`

→ `WORKING_REPOS` (Tier A/B; Tier C asks if empty and interactive). **No file is persisted here** — `discover-working-repos.py` only prints candidate paths to stdout; nothing under this skill writes `~/.claude/working-repos.yaml`. The step below (`register-discovered-repos.py`) is the actual persistence: only-if-absent registration of each candidate into the machine-local `repos.*` registry, not a YAML manifest. `--check-only`: read-only, no write, no Tier C.

```bash
"${COORDINATOR_PYTHON:-python3}" "${ENGINE_ROOT:?ENGINE_ROOT unset — run the POSIX preamble above first (the resolver prints an empty line on a total miss — see § Backing script)}/coordinator/lib/register-discovered-repos.py" ${ARGUMENTS}
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\lib\register-discovered-repos.py" $ARGUMENTS`

Only-if-absent, tier-gated to what discovery qualified. Registers into the machine-local `repos.*` registry — this, not a `~/.claude/working-repos.yaml` file, is the actual persistence for `WORKING_REPOS`.

## Phase 3 — Machine-local registry substrate

Idempotent throughout; skip mutations under `--check-only`; never overwrite an existing `registry.toml`/`registry.local.toml`. `install-substrate.py`, `register-coordinator-mirror.py`, and `check-install-singularity.py` below derive their plugin root from their own on-disk location — since they live in the engine repo, that resolution is wrong; set `CLAUDE_PLUGIN_ROOT` explicitly (the harness-provided value from line 116's `render-template` fence) before calling any of the three.

```bash
"${COORDINATOR_PYTHON:-python3}" "${ENGINE_ROOT:?ENGINE_ROOT unset — run the POSIX preamble above first (the resolver prints an empty line on a total miss — see § Backing script)}/coordinator/lib/install-substrate.py"
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\lib\install-substrate.py"`

Writes the settings-home forwarders themselves (not one itself). Also builds the coordinator venv and ensures `claude` CLI's dir is on shell PATH. Re-run this exact call to repair a broken venv.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/install-health-run" ${ARGUMENTS}
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\install-health-run.exe" $ARGUMENTS`

Runs `bin/install-health/*.sh`, each self-gating; aggregates failures without aborting on first.


Optional interactive seed prompt (declinable, skipped if a registry file already exists): offers to seed the standard `repos.*` keys and machine/contributor slugs via `machine-local set`.


```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/gen-settings-hooks" ${ARGUMENTS}
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\gen-settings-hooks.exe" $ARGUMENTS`

Restart Claude Code once — seeded SessionStart hooks do not fire mid-session.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/seed-marketplace-enabledplugins" ${ARGUMENTS}
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\seed-marketplace-enabledplugins.exe" $ARGUMENTS`

Merge-never-clobber against `settings.json` ∪ `settings.local.json`; only `true` is ever written.

`~/.claude/plugins/` stays thin under this shape (pointer/config only, no plugin-source byte-copy) automatically — no separate mutation, verified by the singularity gate below.

**Required verification, not a subagent step.** `bin/install-sandbox-check.py`'s filesystem tier runs automated; its running-in-Claude-Code tier (live skill/hook resolution via `--plugin-dir`) CANNOT run inside a subagent — the EM or PM must launch `claude --plugin-dir <sandbox>/coordinator` interactively before declaring the install surface complete.

```bash
"${COORDINATOR_PYTHON:-python3}" "${ENGINE_ROOT:?ENGINE_ROOT unset — run the POSIX preamble above first (the resolver prints an empty line on a total miss — see § Backing script)}/coordinator/lib/register-coordinator-mirror.py" ${ARGUMENTS}
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\lib\register-coordinator-mirror.py" $ARGUMENTS`

**No canonical-structure scaffold runs here.** `canonical-structure.yaml` describes a
coordinator-managed *project repo* (`CLAUDE.md`, `docs/exec-summary.md`, `state/handoffs/`,
`.git/hooks/post-commit`), and `~/.claude` is not one — it is harness config and backup, holding no
coordinator working data, so the `guard-repo-setup-claude-home-refusal` bash guard refuses a
scaffold write targeting it. Per-project scaffolding is `/coordinator:repo-setup`'s, run from
inside the project. Report this step as guard-blocked/no-op rather than running it.

```bash
"${COORDINATOR_PYTHON:-python3}" "${ENGINE_ROOT:?ENGINE_ROOT unset — run the POSIX preamble above first (the resolver prints an empty line on a total miss — see § Backing script)}/coordinator/lib/check-install-singularity.py"
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\lib\check-install-singularity.py"`

Verifies exactly one canonical coordinator tree; non-zero exit is a genuine accidental split — print remediation. Exempt: an explicitly-exported `COORDINATOR_CLONE`/`COORDINATOR_ROOT` dev override.

Writes the fan-out soft-threshold (`--check-only` as sole arg for a dry report):

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/capture-fan-out-threshold"
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\capture-fan-out-threshold.exe"`

Closes the `/plugin` marketplace-corruption window before the operator's first new session:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/run-platform-localize" ${ARGUMENTS}
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\run-platform-localize.exe" $ARGUMENTS`

## Phase 4 — Meta-repo doctrine

`git -C ~/.claude rev-parse --show-toplevel`. Not a repo, interactive, not `--check-only`: offer to `git init ~/.claude` + starter `.gitignore` (derived from `templates/dotgitignore.tmpl` at that moment) + initial commit — never creates a remote or pushes. Is a repo: run `<plugin-root>/bin/check-gitignore-template-drift.py` --apply — it owns deriving the live-`.gitignore`-vs-`templates/dotgitignore.tmpl` diff and applying it, on both this install run and its own recurring ceremony-gate cadence. **This call is the ONLY delivery path an existing install has** for a template rule added after `git init` laid the starter file down, since that starter file is never re-applied outside this gate. **Derive the list from the template; never hardcode one here** — a fixed enumeration has to be extended by whoever next edits the template, which is a rule discharged by memory, and memory is what failed: the box that AUTHORS the template was measured nine rules behind it, including the shape-matched credential rules (`*-token-key`, `*-token.json`, `*.pem`) that exist so a plugin installed later is covered the day it first writes a key — deriving from `templates/dotgitignore.tmpl` propagates every future rule with nothing to remember. Then `git rm --cached` anything already tracked despite a newly-added rule. Two entries the gate's diff surfaces are not plain appends and need naming here: Probe the auto-memory re-inclusion too (`projects/**` plus its three `!` lines): an operator whose `.gitignore` carries a bare `projects/` is silently discarding the auto-memory store the workstream-complete drain gate empties to zero at every close. **This one entry is REPLACE, not append — appending is inert.** Delete the existing bare `projects/` line and write the four-line chain in its place: git does not descend into an excluded directory, so a chain appended BELOW a surviving `projects/` is never reached and stages nothing, which is the exact silent failure the probe is here to repair. Every existing install is in that state by construction. Then `git add` the store — an ignore FIX does not retroactively track what was never committed. Warn the operator that the store becomes committed content: it is model-authored prose about their work, so it wants a read-through before any remote is added. Full policy and rationale: `docs/wiki/claude-home-tracking-policy.md`. Anchor the last two (`/machine-local`, `/.claude/`) — a tracked `machine-local` is re-materialised as a real directory on every checkout, which permanently blocks Phase 3's settings-home migration from reaching its terminal symlink and ships one box's resolved pointers to every peer machine. Write `/machine-local` with NO trailing slash: `dir/` matches only a real directory, so the slashed form walks past the symlink the path becomes once that migration completes — the rule reads as present and matches nothing.

## Phase 5 — Project-local

`test -f coordinator.local.md`. Exists: report `project_type` (flag legacy values for manual migration). Missing, not `--check-only`: `--non-interactive` fails loud (no safe default); interactive asks `project_type`/subtypes, writes:

```markdown
---
project_type: {type}
project_subtypes: [{subtype1}, {subtype2}]   # omit field when blank
fast_test_cmd: "<your-project-fast-test-command>"  # optional, single command only
---
```

```bash
"${COORDINATOR_PYTHON:-python3}" "${ENGINE_ROOT:?ENGINE_ROOT unset — run the POSIX preamble above first (the resolver prints an empty line on a total miss — see § Backing script)}/coordinator/lib/coordinator_currency.py" write "$PWD" "${CLAUDE_PLUGIN_ROOT}"
```

PowerShell host (rung 0):

    `& $pythonExe "$engineRoot\coordinator\lib\coordinator_currency.py" write "$PWD" "$env:CLAUDE_PLUGIN_ROOT"`

## Phase 6 — Optional

**Persona customization.** `--check-only`/`--non-interactive`: keep defaults. Interactive: offer **Customize** (runs `name-personas.sh`, reversible; exclude the engine repo's `publish-time-transform-py` from search-replace).


**Git Bash fast profile.** Windows only — a POSIX host has no Git-for-Windows `/etc/profile`
and skips silently. The Bash tool invokes `bash -c -l`, so the stock profile is sourced and
discarded once per Bash call — ~800ms measured, and the tool's own contract states shell state
does not persist between calls. The block reproduces that environment spawn-free, gated on a
non-interactive shell carrying `CLAUDECODE`, so an interactive Git Bash keeps its prompt.

    `& $pythonExe "$env:CLAUDE_PLUGIN_ROOT\templates\bin\install-git-bash-fast-profile.py" --check`

Exits 0 installed, 1 absent, 2 if Git's `/etc/profile` is unlocatable. `--check-only`/
`--non-interactive`: report only. Interactive on rc 1: hand the operator the same command
without `--check` to run **elevated** — `/etc/profile` is inside the Git install root, so this
step cannot self-elevate and is never reported as done. Re-offer every run; a Git update
removes the block silently.

**Percolation setup.** A `coordinator/bin/publish.py` file in the repo under setup AND a `setup/` dir both present → percolation source; else skip. No targets registered: walk detect/scaffold → register target → author `.percolate-ignore` → scaffold hook dirs, interactively.

## Phase 7 — Status Report

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/coordinator-setup-state" record setup_concluded
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-setup-state.exe" record setup_concluded`

Present a status table, one row per check above plus `orientation` (`PENDING` default). Status vocabulary: `RAN` | `SKIPPED` (mode-gated, e.g. `--check-only`) | `DISABLED` (a deliberate operator opt-out marker, e.g. `~/.claude/.coordinator-hooks-disabled` — distinct from a failure) | `INHERITED` (the step's target already held the right value before this run, rather than being freshly written by it — never collapse this into a bare pass: presence is not provenance, and a crashed writer that left a correct pre-existing value must read differently from one that actually ran). Not `--check-only`: offer a guided walkthrough (four movements — Orient, make `~/.claude/CLAUDE.md` yours, test-drive on a real repo, onboard their first project via `/coordinator:repo-setup` or `/coordinator:new-project`; text: wiki):

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/coordinator-setup-state" record orientation_started
```

PowerShell host (rung 0):

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-setup-state.exe" record orientation_started`

Record `orientation_completed` at the end. Standing sign-off note and the `/coordinator:repo-setup` bootstrap offer (gated on `repos.*` having ≥1 newly-registered entry from this run, not a `working-repos.yaml` file — none is written): wiki.

**Terminal-message gate.** Never present unconditional success language while `orientation` is `PENDING` — foreground "restart, then say 'walk me through the coordinator'" until `orientation_completed` is recorded (exact phrasing: wiki).
