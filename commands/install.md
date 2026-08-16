---
description: "Installs the coordinator plugin — checks prereqs, configures project."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive] [--accept-no-git-auth]"
---

# Coordinator Install

Guided install — agent runs mechanism, operator decides shape. Re-run anytime; skips what's configured.

If `/coordinator:install` already resolves, skip to Step Zero. COLD machine (nothing wired): run `python3 coordinator/scripts/install-maximalist.py` instead — do not hand-transcribe this doc's fences there (wiki). Reverses via `coordinator/commands/uninstall.md`.

Every `${...}`-forwarder fence below resolves `$COORDINATOR_PYTHON`/`$REPO_CLAUDE_KLABAUTER`/`$CLAUDE_KLABAUTER_ROOT`/`$COORDINATOR_SETTINGS_HOME` the same way; not restated per step. All unset: resolve the registry first, `export REPO_CLAUDE_KLABAUTER="$(machine-local get repos.claude_klabauter)"`, before running any fence below.

**Windows.** Bare `${...}` forwarder names are not invocable from PowerShell/cmd — resolution fails silently, no output and no error. Append `.cmd` to every settings-home forwarder call.

## Step Zero — preflight and env-normalization

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/scripts/chain-walk.py" --preflight
```

`scripts/setup.py` is a deprecated shim forwarding to this file — call `chain-walk.py` directly. Needs `repos.claude_klabauter` registered first (`machine-local set repos.claude_klabauter <path>`). `python` probe hard-fails the install; `clone_auth` blocks unless `--accept-no-git-auth` or resolved interactively (`gh auth login`); rest advisory. `--non-interactive` + no auth + no `--accept-no-git-auth`: fail-loud. `--check-only`: report only. Full probe table and PowerShell-5.1-fallback note: wiki.

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/scripts/normalize-env.py" --dry-run
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/scripts/normalize-env.py" --yes
```

Preview, then apply — consent-gated per mutation. `--check-only`: no mutating flag.

Resolve hard `--preflight` failures before Phase 1.

---

## Requirements

- bash ≥ 4.3 (hard; macOS ships 3.2 — `brew install bash`).
- git, Python 3, jq.
- uv (Pipeline D), scc (optional), PowerShell 7+ / Windows Terminal (default-on, not hard blockers).
- Engine repo cloned AND `repos.claude_klabauter` registered (hard, not auto-discovered): `machine-local set repos.claude_klabauter <path>`. Private repo — maintainer grants access on request.

## Structural fork

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/detect-existing-claude-home.py"
```

Emits `state=<pristine|used-vanilla|configured>`. `configured`: surface "existing setup — merge is yours"; else proceed with no/light note. Never clobbers `CLAUDE.md`/`settings.json`/registry regardless of state (wiki).

## Flags

| Flag | Effect |
|---|---|
| `--check-only` | Read-only report — no mutations. |
| `--non-interactive` | Suppresses `AskUserQuestion`; per-site fallback is skip-with-note / default-with-warning / fail-loud (unannotated = fail-loud). |
| `--accept-no-git-auth` | Skips `clone_auth`. |

Both `--check-only`/`--non-interactive` combine freely. Environment-only here — `/coordinator:repo-setup` handles per-project scaffolding after this.

## Phase 1 — Environment

**Bash version.** ≥5, or 4.x≥3: ready. <4.3: fail-loud (`local -n` needs 4.3+). macOS 3.2: fail-loud, remediate via `normalize-env --yes` (same command as Step Zero). If `probe_shell_login_env` (`coordinator_core.install.prereq_probe`) then reports an orphaned bash login shell (bash login shell, `~/.bash_profile` missing `~/.local/bin`), offer the same `normalize-env --yes` to reconstruct it — detail: wiki.

```bash
sh "$_cc_claude_klabauter/coordinator/scripts/lib/invoking-shell-bash4-probe.sh" [--quiet]
```

Exit 1: surface the printed remediation verbatim (WARN, not a hard blocker).

**Git.** `git rev-parse --show-toplevel` — not a repo: warn, proceed.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-configure-git"
```

Sets `gc.autoDetach false`/`core.checkStat minimal`; idempotent; skip under `--check-only`.

If the operator git-tracks `~/.claude`:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-meta-repo-precommit-hook" "$HOME/.claude"
```

No-ops if not a git repo. Under `--check-only`, don't run it — report gate-marker presence instead.

Git-LFS: if the binary is present, `git lfs install`; else advisory per-platform remediation (wiki).

**Agent Teams.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` unset, not `--check-only`: offer to add `"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}` to `~/.claude/settings.json`.

**Python3.** Resolves and runs `--version`: ready. Not on PATH: fail-loud. Resolves but errors on `--version` (Windows App-Execution-Alias stub): warn — Phase 3 places a real interpreter.

**scc** (optional), **jq** (`command -v jq` — required for JSON output, else text fallback), **pwsh 7+**/**Windows Terminal** (offer install per-platform if absent, interactive only; commands: wiki) — presence checks only, no branch beyond offer-or-skip.

**NotebookLM (Pipeline D).** Check `grep -l "notebooklm-mcp"` in `~/.claude/settings.json` / `~/.claude.json` / `.mcp.json`. Not registered, interactive, `uv` present: offer to walk:

```bash
uv tool install notebooklm-mcp-cli
nlm login
nlm setup add claude-code
```

Then restart Claude Code. `uv` absent: offer defaults to decline. `--non-interactive`/`--check-only`: skip.

**Global CLAUDE.md.** No manual wiring — doctrine reaches the EM via SessionStart hook. Flag a stale `@…/coordinator/CLAUDE.md` import for removal if present.

## Phase 2 — Operator identity

Read `~/.claude/coordinator-identity.yaml`. `operator_name` present: use it. Absent (or `--reconfigure`): ask via `AskUserQuestion`. `--non-interactive` with none stored: fail-loud.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}/.claude" --operator-name "${OPERATOR_NAME}"
```

Skip under `--check-only`.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/render-template" "${CLAUDE_PLUGIN_ROOT}/templates/CLAUDE.md.tmpl" -o "${CLAUDE_HOME:-$HOME}/.claude/CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" PM_NAME="${OPERATOR_NAME}"
```

Never-clobber is the `--guard-sentinel` flag's own contract (exit 3 = hand-authored file preserved, skip). No `--check-only` flag on the primitive — skip the call there instead.

**Engagement posture (mandatory gate, both modes).** Reuse the identity read; `engagement_posture` present: use it. Absent: interactive asks precision/default/substrate-free (question text: wiki — these select engagement DISTANCE only, never technical skill); `--non-interactive` honors `--posture <value>`, else fail-loud.

```bash
git rev-parse --show-toplevel 2>/dev/null
```
→ `_EM_CONTEXT_REPO_ROOT` (falls back to `$PWD`).

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/bin/coordinator-resolve-validation-cmd.py" --read-key "${_EM_CONTEXT_REPO_ROOT:-$PWD}" engagement_posture
```

Differs from the identity-file value: fail-loud, don't write the overlay. Empty output (repo has no posture set): not a difference — proceed, treat as absent.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}/.claude" --operator-name "${OPERATOR_NAME}" --engagement-posture "${ENGAGEMENT_POSTURE}"
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/render-posture-overlay" "${ENGAGEMENT_POSTURE}" "${_EM_CONTEXT_REPO_ROOT}/.claude/em-context.md"
```

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
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" array-append coordinator.installed_repos "${_EM_CONTEXT_REPO_ROOT}"
```

Skip under `--check-only`. A repo onboarded later re-renders this overlay via `repo-setup` from the persisted value (wiki).

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/discover-working-repos.py"
```

→ `WORKING_REPOS` (Tier A/B; Tier C asks if empty and interactive). Persist at `~/.claude/working-repos.yaml`. `--check-only`: read-only, no write, no Tier C.

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/register-discovered-repos.py" ${ARGUMENTS}
```

Only-if-absent, tier-gated to what discovery qualified.

## Phase 3 — Machine-local registry substrate

Idempotent throughout; skip mutations under `--check-only`; never overwrite an existing `registry.toml`/`registry.local.toml`. `install-substrate.py`, `register-coordinator-mirror.py`, and `check-install-singularity.py` below derive their plugin root from their own on-disk location — since they live in the engine repo, that resolution is wrong; set `CLAUDE_PLUGIN_ROOT` explicitly (the harness-provided value from line 116's `render-template` fence) before calling any of the three.

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/install-substrate.py"
```

Writes the settings-home forwarders themselves (not one itself). Also builds the coordinator venv/`coordinator_whoami` and ensures `claude` CLI's dir is on shell PATH. Re-run this exact call to repair a broken venv.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-health-run" ${ARGUMENTS}
```

Runs `bin/install-health/*.sh`, each self-gating; aggregates failures without aborting on first.

Windows Defender process-exclusion offer (Windows-only, admin-gated, `[y/N]` default DECLINED, never applied non-interactively): implemented in `install-maximalist.py`, not a separate call here (rollback: wiki).

Optional interactive seed prompt (declinable, skipped if a registry file already exists): offers to seed the standard `repos.*` keys and machine/contributor slugs via `machine-local set`.

**Doctrine-plane clone and launch surface** (idempotent, one command per artifact):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/ensure-doe-clone" ${ARGUMENTS}
```

Resolves target from `repos.doe_claude`/`REPO_DOE_CLAUDE`; interactive asks if unresolved; `--non-interactive` with neither: fail-loud, as does an unresolved `DOE_CLONE` post-prompt.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-doe-root-pointer" ${ARGUMENTS} --graceful-skip-unresolved
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-claude-doe-shim" ${ARGUMENTS} --graceful-skip-unresolved
```

Windows-only, additionally (skip on macOS/Linux):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-claude-doe-shim" --shell powershell --rc "$HOME/Documents/PowerShell/profile.ps1" --template "${DOE_CLONE}/coordinator/templates/shell/claude-doe-shim.ps1.tmpl" --graceful-skip-unresolved
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-claude-doe-shim" --shell powershell --rc "$HOME/Documents/WindowsPowerShell/profile.ps1" --template "${DOE_CLONE}/coordinator/templates/shell/claude-doe-shim.ps1.tmpl" --graceful-skip-unresolved
```

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-claude-doe-wrapper" ${ARGUMENTS}
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-shell-init-guard-seam" ${ARGUMENTS}
```

Second call is a graceful no-op if the engine repo isn't checked out.

**Windows dogfood shape — verify the launch shape after rendering, not before.** The launchers and
the `claude` shim are only correct if the interactive `claude.exe` ends up a DIRECT child of the
invoking shell; an interposed `cmd.exe`/`python.exe` corrupts the console input mode and the only
mitigation is disabling the shim, which strips the plugin from every session. Run
`python -m pytest coordinator/tests/test_dogfood_launch_shape.py` from the DoE clone — it reads the
rendered artifacts these two calls just wrote and walks the real Win32 process tree to prove
parentage. Self-skips off the dogfood shape. Rule: `docs/wiki/windows-process-spawn-and-console.md` § 4.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-settings-hooks" ${ARGUMENTS}
```

Restart Claude Code once — seeded SessionStart hooks do not fire mid-session.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/seed-marketplace-enabledplugins" ${ARGUMENTS}
```

Merge-never-clobber against `settings.json` ∪ `settings.local.json`; only `true` is ever written.

`~/.claude/plugins/` stays thin under this shape (pointer/config only, no plugin-source byte-copy) automatically — no separate mutation, verified by the singularity gate below.

**Required verification, not a subagent step.** `bin/install-sandbox-check.py`'s filesystem tier runs automated; its running-in-Claude-Code tier (live skill/hook resolution via `--plugin-dir`) CANNOT run inside a subagent — the EM or PM must run `claude-doe --dry-run` then launch `claude --plugin-dir <sandbox>/coordinator` interactively before declaring the install surface complete. Windows: the bare `claude-doe` isn't PowerShell/cmd-invocable — run `claude-doe.cmd --dry-run` (cmd.exe) or `claude-doe.ps1 --dry-run` (PowerShell) instead; both intercept `--dry-run` themselves and never forward it to `claude`.

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/register-coordinator-mirror.py" ${ARGUMENTS}
```

```bash
PYTHONPATH="${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}${PYTHONPATH:+:$PYTHONPATH}" "${COORDINATOR_PYTHON:-python3}" -m coordinator_core.install.scaffold_structure --root "${CLAUDE_HOME:-$HOME}/.claude" --manifest-root "${CLAUDE_PLUGIN_ROOT}"
```

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/check-install-singularity.py"
```

Verifies exactly one canonical coordinator tree; non-zero exit is a genuine accidental split — print remediation. Exempt: an explicitly-exported `COORDINATOR_CLONE`/`COORDINATOR_ROOT` dev override.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/capture-fan-out-threshold"
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/run-platform-localize" ${ARGUMENTS}
```

First writes the fan-out soft-threshold (`--check-only` as sole arg for a dry report); second closes the `/plugin` marketplace-corruption window before the operator's first new session.

## Phase 4 — Meta-repo doctrine

`git -C ~/.claude rev-parse --show-toplevel`. Not a repo, interactive, not `--check-only`: offer to `git init ~/.claude` + starter `.gitignore` + initial commit — never creates a remote or pushes. Is a repo: probe `.gitignore` coverage of `coordinator-setup-state.yaml`/`settings.json`/`bin/`, offer to append missing entries and `git rm --cached` anything already tracked despite the new rule.

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
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/coordinator_currency.py" write "$PWD" "${CLAUDE_PLUGIN_ROOT}"
```

## Phase 6 — Optional

**Persona customization.** `--check-only`/`--non-interactive`: keep defaults. Interactive: offer **Customize** (runs `name-personas.sh`, reversible; exclude the engine repo's `publish-time-transform-py` from search-replace).

**GitHub Auth via 1Password.** Opt-in, `--non-interactive` skips silently.

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:?engine repo root unresolved — register repos.claude_klabauter}}/coordinator/scripts/setup-github-auth-1password.py" --check
```

`--check-only` uses `--check`; interactive on Y runs the same command without `--check` (offers each change individually, backs up `~/.ssh/config`).

**Percolation setup.** `coordinator/bin/publish.py` file AND `setup/` dir both present → percolation source; else skip. No targets registered: walk detect/scaffold → register target → author `.percolate-ignore` → scaffold hook dirs, interactively.

## Phase 7 — Status Report

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-setup-state" record setup_concluded
```

Present a status table, one row per check above plus `orientation` (`PENDING` default). Not `--check-only`: offer a guided walkthrough (three movements — Orient, make `~/.claude/CLAUDE.md` yours, test-drive on a real repo; text: wiki):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-setup-state" record orientation_started
```

Record `orientation_completed` at the end. Standing sign-off note and the `/coordinator:repo-setup` bootstrap offer (when `working-repos.yaml` has N>0): wiki.

**Terminal-message gate.** Never present unconditional success language while `orientation` is `PENDING` — foreground "restart, then say 'walk me through the coordinator'" until `orientation_completed` is recorded (exact phrasing: wiki).
