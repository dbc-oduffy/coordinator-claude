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

The rendered `CLAUDE.local.md` includes a "Your working repos" section so the EM (operating as DoE in the meta-repo) knows which sibling projects exist. Three-tier discovery, stop at first non-empty result:

**Tier A — Claude Code's own activity record (preferred).** `~/.claude/projects/` contains one directory per folder Claude Code has been active in, encoded path-as-name (`:` `\` `/` `.` → `-`; drive roots therefore look like `X--Foo` for `X:\Foo`, `C--Users-oduffy--claude` for `C:\Users\oduffy\.claude`). mtime ≈ most recent activity.

```bash
# Enumerate, decode heuristically, filter to existing dirs that look like working repos
ls -1dt ~/.claude/projects/*/ 2>/dev/null | head -50 | while read -r p; do
    base="$(basename "$p")"
    # Heuristic decoder: single dash → path separator; leading "X--" → "X:\".
    # Reverse the encoding by replacing dashes with backslashes, then collapse "\\." → "\." patterns.
    # (Lossy — verify with -d test below.)
    case "$base" in
        [A-Za-z]--*) decoded="${base:0:1}:\\${base:3}"; decoded="${decoded//-/\\}";;
        *) decoded="${base//-/\\}";;
    esac
    # Convert Windows path to /-form for test (Git-Bash/WSL)
    posix="$(echo "$decoded" | sed -E 's|^([A-Za-z]):\\|/\L\1/|; s|\\|/|g')"
    [[ -d "$posix" ]] && echo "$decoded"
done | sort -u
```

Filter out the meta-repo itself (`~/.claude`), `AppData/Local/Temp`, and any bare drive root (e.g. `X:\` with no subdir) — these aren't working repos. Keep at most ~20 most-recent candidates.

**Tier B — Common dev-folder layouts (if Tier A empty).** Probe a small set of conventional locations for git/GitHub repos:

```bash
for cand in ~/dev ~/Dev ~/code ~/Code ~/src ~/Source ~/Projects ~/projects ~/workspace ~/repos ~/Documents/GitHub /c/dev /d/dev /e/dev /x; do
    [[ -d "$cand" ]] && find "$cand" -maxdepth 2 -name .git -type d 2>/dev/null | sed 's|/\.git$||'
done | sort -u | head -30
```

If any results: surface them and use as the working-repos list.

**Tier C — Ask the operator (if both empty).** The operator is likely new to coding or keeps their work somewhere non-standard.

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

Lay down the `~/.claude/machine-local/` substrate and the `bin/machine-local` reader. Idempotent — safe to re-run; never overwrites a live `registry.toml` or `registry.local.toml`.

**Source of truth:** `coordinator/templates/machine-local/` (the canonical plugin-tree templates authored by Task 1) and `coordinator/templates/bin/` (the reader, authored by Task 2). The installer copies from these template paths into the operator's `~/.claude/` install location.

**Steps (each step idempotent on re-run):**

### Step 1 — Check-and-create the directory

If `~/.claude/machine-local/` is absent, create it. If present, no-op.

```bash
mkdir -p ~/.claude/machine-local
```

If `${CLAUDE_PLUGIN_ROOT}/coordinator/templates/machine-local/` does not exist, emit a clear error and skip the remaining steps of this phase:

> Phase 3 error: coordinator template directory not found at ${CLAUDE_PLUGIN_ROOT}/coordinator/templates/machine-local/. Cannot lay down machine-local substrate. Ensure the coordinator plugin is fully installed and CLAUDE_PLUGIN_ROOT is set correctly.

### Step 2 — Lay down tracked files if absent

For each of `README.md`, `.gitignore`, `registry.toml.example`, `registry.local.toml.example`:

- Compare live file at `~/.claude/machine-local/<file>` against `${CLAUDE_PLUGIN_ROOT}/coordinator/templates/machine-local/<file>`.
- If absent or identical → copy template → live.
- If differ → leave live untouched, emit one-line notice:

  > [machine-local] operator-customized `<file>` preserved; template at `${CLAUDE_PLUGIN_ROOT}/coordinator/templates/machine-local/<file>` for diff reference.

```bash
_ml_src="${CLAUDE_PLUGIN_ROOT}/coordinator/templates/machine-local"
_ml_dst="$HOME/.claude/machine-local"
for _f in README.md .gitignore registry.toml.example registry.local.toml.example; do
    if [[ ! -f "${_ml_dst}/${_f}" ]]; then
        cp "${_ml_src}/${_f}" "${_ml_dst}/${_f}"
    elif ! diff -q "${_ml_src}/${_f}" "${_ml_dst}/${_f}" >/dev/null 2>&1; then
        echo "[machine-local] operator-customized ${_f} preserved; template at ${_ml_src}/${_f} for diff reference"
    fi
done
```

### Step 3 — Drop the reader

For each of `bin/machine-local`, `bin/_machine_local.py`, `bin/machine-local.cmd`, and `bin/python3.cmd`:

- Compare live file at `~/.claude/bin/<file>` against `${CLAUDE_PLUGIN_ROOT}/coordinator/templates/bin/<file>`.
- If absent or identical → copy template → live. Apply `chmod +x` after copy for `bin/machine-local`.
- If differ → leave live untouched + notice (same format as Step 2).

The two `.cmd` files are Windows shims for the extensionless `machine-local` script and the `python3` name. They prevent the "Select an app to open 'machine-local'/'python3'" picker that fires when Windows `ShellExecute` falls back to file-association lookup. Harmless to drop on Linux/macOS (they sit unused). Reason captured at `coordinator/docs/wiki/windows-cmd-shims.md`.

```bash
_bin_src="${CLAUDE_PLUGIN_ROOT}/coordinator/templates/bin"
_bin_dst="$HOME/.claude/bin"
mkdir -p "${_bin_dst}"
for _f in machine-local _machine_local.py machine-local.cmd python3.cmd; do
    if [[ ! -f "${_bin_dst}/${_f}" ]]; then
        cp "${_bin_src}/${_f}" "${_bin_dst}/${_f}"
        [[ "${_f}" == "machine-local" ]] && chmod +x "${_bin_dst}/${_f}"
    elif diff -q "${_bin_src}/${_f}" "${_bin_dst}/${_f}" >/dev/null 2>&1; then
        [[ "${_f}" == "machine-local" ]] && chmod +x "${_bin_dst}/${_f}"
    else
        echo "[machine-local] operator-customized ${_f} preserved; template at ${_bin_src}/${_f} for diff reference"
    fi
done
```

### Step 3b — Windows PATH integration (Windows operators only)

The `.cmd` shims dropped in Step 3 only help if `~/.claude/bin` is on the **Windows user PATH** (not just the MSYS/git-bash PATH). On Windows, check and add:

```bash
# $OSTYPE == "msys" / "cygwin"  → git-bash / MSYS2 on Windows
# $OS == "Windows_NT"           → native cmd.exe / PowerShell execution (no $OSTYPE set)
# WSL or plain Linux            → $OSTYPE matches "linux*", $OS unset, guard skips
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    # Push path-equality test to PowerShell — bash glob over a Windows-PATH string
    # is fragile under separator/case drift between re-runs.
    _already_set=$(powershell.exe -NoProfile -Command \
        "\$p=[Environment]::GetEnvironmentVariable('PATH','User'); \
         \$t=\$env:USERPROFILE+'\.claude\bin'; \
         if (\$p -split ';' | Where-Object {\$_ -ieq \$t}) {'yes'} else {'no'}" \
        2>/dev/null | tr -d '\r')
    if [[ "$_already_set" != "yes" ]]; then
        powershell.exe -NoProfile -Command "\$p = [Environment]::GetEnvironmentVariable('PATH','User'); [Environment]::SetEnvironmentVariable('PATH', \"\$env:USERPROFILE\.claude\bin;\$p\", 'User')"
        echo "[setup] added ~/.claude/bin to Windows user PATH — restart shells/Claude sessions for it to take effect"
    fi
fi
```

Skip on non-Windows operators (idempotent: the conditional guard handles re-runs cleanly).

### Step 3c — Windows Python-resolution health check (Windows operators only)

The `.cmd` shims and PATH integration in Steps 3 + 3b only help if the AppX App-Execution-Alias subsystem doesn't intercept `python3` first (per `docs/wiki/windows-cmd-shims.md`). Three configurations cause the picker to fire even after Steps 3 + 3b:

1. **Orphan AppX stub** — zero-byte reparse-point at `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe` (or `python.exe`) from an uninstalled Store Python package. Windows still consults the stub before PATH on `ShellExecute("python3")`. Cleanest fix: delete the stub. Reversible (regenerates if Store Python is reinstalled).
2. **Store-alias on MSYS PATH** — `WindowsApps` directory on git-bash's PATH means `command -v python3` returns the alias path. Runtime scripts that don't filter `WindowsApps` paths invoke the alias → picker.
3. **No Python at all** — neither `py.exe` (Python Launcher) nor a real `python.exe` is reachable. Shims can't help because they need an underlying interpreter to call.

Detect and surface remediation. Do NOT delete the stub silently — offer with explicit consent.

```bash
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OS" == "Windows_NT" ]]; then
    # 1. Orphan AppX stub detection
    # NOTE on escaping: in the powershell.exe -Command "..." strings below, `\$` escapes the
    # $ from bash (passing literal $ to PowerShell). Single backslashes before path components
    # like \Microsoft \WindowsApps are LITERAL — not bash escapes — and reach PowerShell as
    # valid backslash separators. Do NOT double them to \\Microsoft \\WindowsApps; that would
    # produce double-backslash PowerShell paths. The single \\${_stub_name} below IS doubled
    # because that one bash-expands ${_stub_name}, so the \\ collapses to one backslash.
    for _stub_name in python.exe python3.exe; do
        _stub_path=$(powershell.exe -NoProfile -Command \
            "\$p = \"\$env:LOCALAPPDATA\Microsoft\WindowsApps\\${_stub_name}\"; \
             if (Test-Path -LiteralPath \$p) { \$i = Get-Item -LiteralPath \$p -Force; \
             if (\$i.Length -eq 0 -and \$i.LinkType -eq 'ReparsePoint' -and -not \$i.Target) { Write-Output \$p } }" \
            2>/dev/null | tr -d '\r')
        if [[ -n "$_stub_path" ]]; then
            echo "[setup] Detected orphan AppX stub: ${_stub_path}"
            echo "[setup]   This zero-byte reparse-point is left over from an uninstalled"
            echo "[setup]   Microsoft Store Python package. It intercepts python3/python"
            echo "[setup]   invocations via the AppX App-Execution-Alias system and pops"
            echo "[setup]   the Windows 'Select an app to open' picker (no PATH lookup runs)."
            echo "[setup]   If you reinstall Store Python, the stub will regenerate."
            # Guard: tty present AND not running under COORDINATOR_NON_INTERACTIVE.
            # `read -p` blocks indefinitely when stdin is not a terminal (Claude Bash tool
            # context, CI, here-doc invocation), so check [[ -t 0 ]] before prompting.
            if [[ -t 0 ]] && [[ -z "$COORDINATOR_NON_INTERACTIVE" ]]; then
                read -r -p "[setup] Delete this orphan stub? [y/N] " _consent
                if [[ "$_consent" =~ ^[Yy] ]]; then
                    # Pass stub path into a PowerShell variable rather than interpolating into
                    # the outer double-quoted command string — confines bash expansion to a
                    # single-quoted PS assignment, avoiding quote-injection edge cases.
                    powershell.exe -NoProfile -Command "\$p='${_stub_path}'; Remove-Item -LiteralPath \$p -Force"
                    echo "[setup]   Deleted."
                fi
            else
                echo "[setup]   (non-interactive context: skipping deletion; re-run /setup in an interactive shell"
                echo "[setup]    without COORDINATOR_NON_INTERACTIVE set to clean up)"
            fi
        fi
    done

    # 2. Store-alias-on-PATH detection
    _py_resolved=$(powershell.exe -NoProfile -Command \
        "\$c = Get-Command python3 -ErrorAction SilentlyContinue; \
         if (-not \$c) { \$c = Get-Command python -ErrorAction SilentlyContinue }; \
         if (\$c) { Write-Output \$c.Source }" 2>/dev/null | tr -d '\r')
    case "$_py_resolved" in
        *WindowsApps*)
            echo "[setup] WARNING: python/python3 resolves under WindowsApps: ${_py_resolved}"
            echo "[setup]   Runtime scripts that don't filter WindowsApps paths may invoke"
            echo "[setup]   the Store alias and pop the picker. Recommended: install Python"
            echo "[setup]   from python.org so a real python.exe takes precedence on PATH,"
            echo "[setup]   OR disable App Execution Aliases for python.exe/python3.exe via"
            echo "[setup]   Settings → Apps → Advanced app settings → App execution aliases."
            ;;
    esac

    # 3. No-Python detection (must have py.exe OR a real python on PATH)
    _have_py=$(powershell.exe -NoProfile -Command \
        "\$p = Get-Command py -ErrorAction SilentlyContinue; \
         if (\$p) { Write-Output 'yes' } else { Write-Output 'no' }" 2>/dev/null | tr -d '\r')
    if [[ "$_have_py" != "yes" && -z "$_py_resolved" ]]; then
        echo "[setup] WARNING: neither py.exe (Python Launcher) nor python/python3 found."
        echo "[setup]   Install Python 3 from https://www.python.org/downloads/windows/ —"
        echo "[setup]   the installer ships py.exe by default. Without one of these, the"
        echo "[setup]   ~/.claude/bin/python3.cmd shim has nothing to call."
    fi
fi
```

Skip on non-Windows operators. Honors `COORDINATOR_NON_INTERACTIVE=1` for unattended re-runs.

### Step 4 — Never overwrite live registry files

If `~/.claude/machine-local/registry.toml` or `~/.claude/machine-local/registry.local.toml` exists, leave both untouched regardless of `.example` updates. Same rule for any `<concern>.toml` and `<concern>.local.toml`. The operator's machine-local values are theirs.

### Step 5 — Optional seed prompt (declinable, interactive mode only)

<!-- D4 annotation (seed prompt): skip-with-note — seed is elective; --non-interactive skips it and notes that the operator should copy .example → real by hand. -->

**Condition:** Skip entirely if either `~/.claude/machine-local/registry.toml` or `~/.claude/machine-local/registry.local.toml` exists (idempotency — never re-prompt once seeded).

Under `--non-interactive`: skip the prompt, emit status row `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`. Do NOT create `registry.toml` or `registry.local.toml`.

Under interactive (default), if neither file exists, ask via `AskUserQuestion`:

> Would you like to seed the registry with the four most common `repos.*` keys (coordinator, project-rag, project-rag-ue-addon, claude-unreal-holodeck)? You can fill paths now or leave them blank to edit later. Key declarations go to `registry.toml` (shared, tracked); your machine's path values go to `registry.local.toml` (per-machine, gitignored). Single-machine operators who don't share their `~/.claude` across machines may put everything in `registry.toml` — no harm in that. [Y/n]

**On Y:** write `~/.claude/machine-local/registry.toml` with the four key declarations + `schema = 1`, and `~/.claude/machine-local/registry.local.toml` with the operator's typed paths (or empty strings on skip-per-key). For each key, ask the path inline — operator may leave blank to fill later.

**On N:** leave both absent — operator copies `.example` → real by hand later.

### Step 6 — Idempotency contract

Re-running `/coordinator:setup` must be safe:

- No destructive overwrites of operator-customized files.
- No duplicate prompts — skip seed prompt entirely if either `registry.toml` or `registry.local.toml` exists.
- No error if operator authored either file by hand before running setup.
- `--check-only` reports what exists and what would be created without creating anything.

### Step 7 — `--non-interactive` mode

Skip the seed prompt. Lay down all tracked files (README.md, .gitignore, both `.example` files, reader and its Python module). Do NOT create `registry.toml` or `registry.local.toml`. Suitable for CI / scripted re-runs.

**Test surface (expected behavior — do not actually run setup):**

- **(a) Fresh install on scratch HOME:** directory, README, .gitignore, both .example files, `bin/machine-local`, `bin/_machine_local.py` all present after phase. Seed prompt fires (interactive). On Y, both `registry.toml` + `registry.local.toml` written. On N, neither written.
- **(b) Re-run on populated install:** no overwrites, no prompts, all idempotency checks pass.
- **(c) `--non-interactive` on fresh install:** substrate laid down, no seed prompt, no `registry.toml`, no `registry.local.toml`.
- **(d) Operator-modified-file detection:** pre-placed modified `README.md` preserved; one-line notice emitted; no overwrite.

**See:** `docs/wiki/machine-local-registry.md` for the substrate doctrine; `bin/machine-local` for the reader contract; `docs/wiki/coordinator-doctor.md` for post-install verification probes (P-1 through P-4 cover this substrate).

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

End with: _"`/setup` is environment-only. Run `/project-onboarding` to scaffold a new project (CLAUDE.md, tracker, sessions directory, lessons file). Then run `/session-start` to begin work."_

If `--check-only`, show the table but note what *would* be created/configured without the flag.
