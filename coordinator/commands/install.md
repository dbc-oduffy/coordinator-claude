---
description: Install the coordinator plugin — check prerequisites, verify environment, configure project. Safe to re-run.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive]"
---

# Coordinator Install

<!-- spec-backlink: docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md -->

Environment and project setup for the coordinator plugin. This is a **guided install** — you participate in the shape decisions; the agent moves fast on mechanism. Safe to re-run — skips anything already configured.

## Requirements

Phase 1 checks each item and fails loud (or warns) per the D4 contract.

- **bash ≥ 4.3** (hard requirement). Scripts use `declare -A` (bash 4.0+) and `local -n` namerefs (4.3+). macOS ships bash 3.2 — install via `brew install bash` and put it first on PATH. Linux/WSL/Git Bash ship 4.3+ already. Policy: `docs/decisions/DR-148-require-bash4-on-macos.md`.
- **git** — branch management, commits, handoffs, auto-push.
- **Python 3** — hooks and JSON manipulation.
- **jq** — required for JSON output in `/workday-start` addon-health.
- **Node 18+** — only for NotebookLM deep-research add-on.
- **scc** — optional; powers code statistics in session orientation.

## Execution dial and structural fork

**Execution dial:** Default is **agent-led** — prompts only where genuine decisions are needed. Pass `--non-interactive` to suppress all `AskUserQuestion` calls; see the **D4 Non-Interactive Contract** below for per-site fallback.

**Structural fork — Track A / Track B:** Before any phase, detect which track applies:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/detect-existing-claude-home.sh"
# Emits: track=A  (fresh install — ~/.claude is empty or absent)
#     or track=B  (existing setup — ~/.claude already has content)
```

- **Track A (fresh install):** Proceed through all phases. Every step runs from zero — no merge, no cherry-pick.
- **Track B (existing setup):** Surface at top of status report:

  > **Existing `~/.claude` detected.** This installs from zero; merge is yours. Re-running is safe; it skips anything already present. Use `--check-only` to see state without changes.

  Continue through all phases as normal (idempotency guards prevent overwrites). Do NOT offer a merge engine or selective-adoption UI.

## Check-only mode

If `$ARGUMENTS` contains `--check-only`: report environment state without making any changes. Every phase runs its read-only checks and emits status rows, then stops before any mutation. Combine with `--non-interactive` freely — both flags are orthogonal.

## D4 Non-Interactive Contract

<!-- spec-backlink: D4 in docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md -->

Each prompt site is annotated: `skip-with-note` (skip, surface in status table), `default-with-warning` (apply safe default, surface value), or `fail-loud` (exit non-zero with remediation; no safe default). Unannotated sites default to `fail-loud`. `--check-only` prevents all mutation; `--non-interactive` controls only prompt fallback. Both are orthogonal and may be combined.

**Scope distinction:** This command sets up the coordinator *environment* (plugins, env vars, tools). For per-project scaffolding (CLAUDE.md, tracker, workstreams), use `/repo-setup` after this.

## Phase 1 — Environment

Run all checks and collect results for the status table.

### 1a.0. Bash version (macOS portability — ratified policy: bash ≥ 4)

Policy: `plugins/coordinator/docs/wiki/cross-platform-shell-portability.md` § support matrix + DR-148. Scripts resolve via `#!/usr/bin/env bash` — check the PATH-resolved bash, not `/bin/bash`:

```bash
PATHBASH="$(command -v bash)"
if [[ -z "$PATHBASH" ]]; then
  echo "ERROR: no \`bash\` found on PATH — coordinator requires bash ≥ 4.3." >&2
else
  "$PATHBASH" -c 'printf "%s.%s\n" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}"'
fi
```

(Empty `PATHBASH` — no bash on PATH at all — is itself a `fail-loud` row: `bash_version: failed (no bash on PATH)`, same remediation as the `major < 4` case below.)

- **major ≥ 5, or (major == 4 and minor ≥ 3):** ready. Status: `bash_version: ready (<version> at <path>)`.
- **major == 4 and minor < 3:** `fail-loud` — `coordinator-safe-commit` uses `local -n` namerefs (4.3+) and hard-aborts on 4.0–4.2; every commit would abort. Status: `bash_version: failed (<version> below 4.3 nameref floor)`.
- **major < 4 (macOS stock bash 3.2):** `fail-loud`. The whole block below is gated on macOS so it is a silent no-op on Linux and Git-Bash on Windows:

```bash
if [[ "$OSTYPE" == darwin* ]]; then
  # ── Offer A — brew presence (precondition for B and C) ─────────────────────
  # default-with-warning: emit brew_present row; subsequent offers skip if brew absent.
  BREW_BIN=""
  if [ -x /opt/homebrew/bin/brew ]; then
    BREW_BIN=/opt/homebrew/bin/brew        # Apple Silicon
  elif [ -x /usr/local/bin/brew ]; then
    BREW_BIN=/usr/local/bin/brew           # Intel
  fi

  if [ -z "$BREW_BIN" ]; then
    STATUS: brew_present: failed (Homebrew not installed)
    echo "Install Homebrew first: https://brew.sh — then re-run coordinator:install."
  else
    STATUS: brew_present: ready

    # ── Offer B — install brew bash ──────────────────────────────────────────
    # default-with-warning: prompt Y/n; apply on accept; emit row on decline/error.
    BREW_BASH_VER=""
    if "$BREW_BIN" list bash &>/dev/null; then
      BREW_BASH_VER="$("$BREW_BIN" list --versions bash | awk '{print $2}')"
    fi

    BREW_BASH_MAJOR="${BREW_BASH_VER%%.*}"
    # Review: code-reviewer F4 — BREW_BASH_MINOR only matters when MAJOR == 4 (the -gt 4 branch short-circuits below).
    # cut on empty string returns empty; ${BREW_BASH_MINOR:-0} normalizes that.
    BREW_BASH_MINOR="$([ -n "$BREW_BASH_VER" ] && echo "$BREW_BASH_VER" | cut -d. -f2 || echo "")"

    if [ -n "$BREW_BASH_VER" ] && \
       { [ "$BREW_BASH_MAJOR" -gt 4 ] || { [ "$BREW_BASH_MAJOR" -eq 4 ] && [ "${BREW_BASH_MINOR:-0}" -ge 3 ]; }; }; then
      # brew bash already installed and ≥ 4.3 — idempotent, proceed to Offer C
      STATUS: brew_bash_installed: ready ($BREW_BASH_VER at $("$BREW_BIN" --prefix)/bin/bash)
      OFFER_B_SUCCESS=1
    elif [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
      STATUS: brew_bash_installed: would write (offer-B)
      OFFER_B_SUCCESS=0
    else
      # Offer B prompt
      # AskUserQuestion: "Offer: brew install bash [Y/n]  (installs brew bash ≥ 4.3, required for coordinator scripts)"
      if <user_accepted_offer_B>; then
        if "$BREW_BIN" install bash; then
          BREW_BASH_NEW_VER="$("$BREW_BIN" list --versions bash | awk '{print $2}')"
          STATUS: brew_bash_installed: ready ($BREW_BASH_NEW_VER at $("$BREW_BIN" --prefix)/bin/bash)
          OFFER_B_SUCCESS=1
        else
          STATUS: brew_bash_installed: failed (brew install bash error: <stderr tail>)
          # Original remediation (decline/error fallback):
          echo ""
          echo "ERROR: coordinator requires bash 4.3 or later. Detected: bash <version> at <path>."
          echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it FIRST on PATH:"
          echo "      brew install bash"
          echo "      export PATH=\"\$(brew --prefix)/bin:\$PATH\"   # add to ~/.zshrc or ~/.bashrc"
          OFFER_B_SUCCESS=0
        fi
      else
        STATUS: brew_bash_installed: failed (declined)
        # Original remediation (decline/error fallback):
        echo ""
        echo "ERROR: coordinator requires bash 4.3 or later. Detected: bash <version> at <path>."
        echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it FIRST on PATH:"
        echo "      brew install bash"
        echo "      export PATH=\"\$(brew --prefix)/bin:\$PATH\"   # add to ~/.zshrc or ~/.bashrc"
        OFFER_B_SUCCESS=0
      fi
    fi

    # ── Offer C — append shellenv block to login rc ───────────────────────────
    # Fires ONLY after a successful Offer B (or pre-existing brew bash ≥ 4.3).
    # default-with-warning: prompt Y/n; append on accept; emit row on decline/error.
    # Review: code-reviewer F10 — under --check-only, Offer C must always enter to emit
    # shellenv_block: would write (offer-C, target: <rc-path>) per AC12. The inner
    # --check-only branch handles the would-write emission when reached.
    if [ "${OFFER_B_SUCCESS:-0}" -eq 1 ] || [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
      case "$SHELL" in
        */zsh)  RC="$HOME/.zprofile" ;;
        */bash) RC="$HOME/.bash_profile" ;;
        *)      RC="$HOME/.zprofile" ;;
      esac

      SENTINEL="# coordinator-install: brew shellenv (DR-148)"

      if [ -f "$RC" ] && grep -qF "$SENTINEL" "$RC"; then
        # Review: code-reviewer F1 — --check-only must not spawn interactive subshell; strict read-only semantics.
        if [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
          STATUS: shellenv_block: ready (sentinel present — eval status unprobed in check-only mode)
        else
          # Sentinel present — probe whether the eval line is actually live.
          PROBE_BASH="$(zsh -lc 'command -v bash' 2>/dev/null || bash -lc 'command -v bash' 2>/dev/null)"
          case "$PROBE_BASH" in
            /opt/homebrew/*|/usr/local/*)
              STATUS: shellenv_block: ready (already present in $RC)
              ;;
            *)
              STATUS: shellenv_block: failed (sentinel present, eval not active — inspect $RC)
              ;;
          esac
        fi
      else
        if [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
          STATUS: shellenv_block: would write (offer-C, target: $RC)
        else
          # Pre-write writability check (BEFORE prompting):
          if [ -e "$RC" ] && [ ! -w "$RC" ]; then
            STATUS: shellenv_block: failed (rc not writable: $RC)
          elif [ ! -e "$RC" ] && [ ! -w "$(dirname "$RC")" ]; then
            STATUS: shellenv_block: failed (rc parent dir not writable: $(dirname "$RC"))
          else
            # Show block, then prompt Y/n
            BLOCK="${SENTINEL}
if [ -x /opt/homebrew/bin/brew ]; then
  eval \"\$(/opt/homebrew/bin/brew shellenv)\"
elif [ -x /usr/local/bin/brew ]; then
  eval \"\$(/usr/local/bin/brew shellenv)\"
fi"
            echo "Offer C: append the following block to $RC:"
            echo ""
            printf '%s\n' "$BLOCK"
            echo ""
            # AskUserQuestion: "Append shellenv block to $RC? [Y/n]"
            if <user_accepted_offer_C>; then
              # Review: code-reviewer F2 — mutually exclusive branches; failed append must not fall through to sentinel re-check.
              if printf '%s\n' "$BLOCK" >> "$RC"; then
                if grep -qF "$SENTINEL" "$RC" 2>/dev/null; then
                  STATUS: shellenv_block: ready (appended to $RC)
                  echo ""
                  echo "Open a new shell or \`source $RC\` for the change to take effect — this Claude Code session inherits the stale PATH."
                else
                  STATUS: shellenv_block: failed (append succeeded but sentinel absent — inspect $RC)
                fi
              else
                STATUS: shellenv_block: failed (append failed mid-write — inspect $RC for partial sentinel)
              fi
            else
              STATUS: shellenv_block: failed (declined)
            fi
          fi
        fi
      fi
    fi
  fi
fi
```

Status: `bash_version: failed (<version> — bash ≥ 4.3 required)`. Under `--check-only`, report the failed row without halting setup; otherwise a hard blocker for script-dependent phases.

### 1a. Git repository

```bash
git rev-parse --show-toplevel 2>/dev/null
```

- If not a git repo: warn that branch management, commits, and handoffs require git. Setup continues.
- If a git repo: note the repo root path.

### 1a.1. Git-config hardening (concurrent-EM lock safety)

Harden **this repo's** git config with two concurrent-EM mitigations (root-causes: `docs/wiki/concurrent-em-hazards.md` § H21–H22): `gc.autoDetach false` (prevents detached GC child orphaning `.git/index.lock` on Git-for-Windows) and `core.checkStat minimal` (ignores NTFS-unstable `ctime/ino/dev` fields that cause phantom-dirty tree). Skip mutations under `--check-only` (report current values instead).

```bash
"$HOME/.claude/plugins/coordinator/bin/coordinator-configure-git"
```

Idempotent. `gc.autoDetach` is scoped per-repo (not global — would change auto-gc in unrelated repos); spread via `/repo-setup` § 3f.5 and `session-init.sh`. `core.checkStat minimal` is benign on all platforms — also set machine-wide:

```bash
git config --global core.checkStat minimal
```

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

- If found: ready. If not found: optional — install from https://github.com/boyter/scc if desired.

### 1c.1 JSON processor (jq)

```bash
command -v jq 2>/dev/null || echo "not_found"
```

- If found: ready. Required for `orphan-branch-sweep.sh --format json` (load-bearing in `/workday-start` Step 1.10).
- If not found: **required for JSON output**. Without `jq`, sweep falls back to `--format text` — downstream JSON consumers fail silently. Install: https://jqlang.org/download/.

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

- If found: ready. If not found: recommend adding to `~/.claude/CLAUDE.md`:
  ```
  @~/.claude/plugins/coordinator/CLAUDE.md
  ```
  Or point to the cache path if installed from marketplace.

## Phase 2 — Operator identity

### Operator identity capture

Persists the operator's name to `~/.claude/coordinator-identity.yaml` so re-runs skip the prompt. Idempotent.

**Step 1 — Read identity file if present.**

```bash
test -f ~/.claude/coordinator-identity.yaml && echo "exists" || echo "missing"
```

- **`version: 1` and `operator_name` present** → use stored value; skip prompt. Status: `operator_identity: ready`. Proceed to Step 3.
- **`version:` > 1** → fail-loud (unsupported schema). Status: `operator_identity: failed (unknown schema version {N})`. Stop phase.
- **`version: 1` but `operator_name` missing (or `version:` absent)** → treat as absent; proceed to Step 2.

If `$ARGUMENTS` contains `--reconfigure`, treat the file as absent regardless.

**Step 2 — Capture identity if absent (or `--reconfigure`).** <!-- D4: fail-loud -->

- **Under `--non-interactive`:** fail-loud — identity file must exist. Status: `operator_identity: failed`. Stop phase.
- **Under interactive:** ask via `AskUserQuestion`: *"What name should the meta-repo doctrine address you by? (As `PM_NAME` in `CLAUDE.local.md` — first name, handle, whatever fits.)"*

**Step 3 — Write identity file (skip under `--check-only`; emit `operator_identity: would write`).**

Write `~/.claude/coordinator-identity.yaml` atomically:

```bash
_tmp="$(mktemp ~/.claude/coordinator-identity.yaml.XXXXXX)"
cat > "$_tmp" <<EOF
# ~/.claude/coordinator-identity.yaml — operator-local, NEVER a publish target
version: 1
operator_name: ${OPERATOR_NAME}
EOF
mv "$_tmp" ~/.claude/coordinator-identity.yaml
```

Status row: `operator_identity: ready`.

**Step 4 — Discover working repos.** Three-tier discovery (stop at first non-empty):

```bash
WORKING_REPOS=$(bash "${CLAUDE_PLUGIN_ROOT}/lib/discover-working-repos.sh")
```

Helper runs Tier A (`~/.claude/projects/` activity record, `X--Foo` → `X:\Foo`) then Tier B (`~/dev`, `~/Projects`, `/x`, etc.). Filters meta-repo, `AppData/Local/Temp`, bare drive roots. Returns up to 20 (A) or 30 (B) candidates.

**Tier C — Ask the operator** (if helper returned empty). <!-- D4: default-with-warning --> Under `--non-interactive`: skip; set placeholder; status `working_repos: defaulted to empty`. Under interactive: ask for a code folder via `AskUserQuestion`; re-probe Tier B inside it; if still empty, record the folder with a "no repos yet" note.

**Build `WORKING_REPOS` block.** Markdown list: `` - `<path>` — <one-line from README> ``. Tier A annotates top 3 `(active recently)`. Persist at `~/.claude/working-repos.yaml` (atomic mv). Status: `working_repos: ready (N from tier {A|B|C})`. Under `--check-only`, run Tiers A+B read-only, skip YAML write and Tier C prompt.

**Step 5 — Render `~/.claude/CLAUDE.local.md`.** Under `--check-only`: emit `meta_repo_doctrine: would write` / `ready` and skip. Otherwise:

```bash
bash ~/.claude/plugins/coordinator/bin/render-template.sh \
  ~/.claude/plugins/coordinator/templates/CLAUDE.local.md.tmpl \
  -o ~/.claude/CLAUDE.local.md \
  PM_NAME="${OPERATOR_NAME}" \
  WORKING_REPOS="${WORKING_REPOS}"
```

On non-zero exit: fail-loud with helper's stderr. On success: `Meta-repo doctrine installed at ~/.claude/CLAUDE.local.md.`

## Phase 3 — Machine-local registry substrate

Lay down `~/.claude/machine-local/` substrate and `bin/{machine-local, claude-home}` resolvers. Idempotent — never overwrites live registry files. Sources of truth: `coordinator/templates/machine-local/`, `coordinator/templates/bin/`, `coordinator/lib/claude-home/` (cross-repo contract surface — do not customize; see README). Skip mutations under `--check-only`; Step 3's seed prompt also skipped under `--non-interactive`.

### Step 1 — Run install-substrate helper

All mechanical work is encapsulated in `coordinator/lib/install-substrate.sh`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/install-substrate.sh"
```

Helper: fails-loud on missing source-of-truth dirs; honors `CLAUDE_HOME` (`docs/wiki/machine-local-registry.md § 4a`) and `COORDINATOR_NON_INTERACTIVE=1`; preserves operator-customized files with one-line notices; skips Windows checks on non-Windows. Installs 7 bin/ artifacts (3 `machine-local`, 3 `claude-home`, 1 `python3.cmd` shim — shims prevent "Select an app" pickers on extensionless scripts). Orphan AppX stub deletion requires `[y/N]` consent.

### Step 2 — Never overwrite live registry files

If `~/.claude/machine-local/registry.toml` or `registry.local.toml` exists, leave untouched regardless of `.example` updates. Same for any `<concern>.toml` / `<concern>.local.toml`.

### Step 3 — Optional seed prompt (declinable, interactive only)

<!-- D4 annotation (seed prompt): skip-with-note — seed is elective; --non-interactive skips it and notes that the operator should copy .example → real by hand. -->

Full interactive script (prompt text, On Y write procedure, `machine-local set` invocations, On N): `docs/wiki/setup-reference-detail.md` § Phase 3 Step 3.

**Skip entirely** if either registry file already exists (idempotency). Under `--non-interactive`: emit `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`. Under interactive: offer Y/n to seed the four standard `repos.*` keys via `machine-local set` (never hand-edit). **On N:** leave both absent.

<!-- Review: chunk-1 Finding 7 — restored "Test surface" block removed in spec trim; inline spec is more immediately accessible than linked doc for test authors. -->
**Test surface** (expected; do not actually run setup): Fresh install → directory, all tracked files, all 7 bin/ artifacts present; seed prompt fires. Re-run → no overwrites, no prompts. `--non-interactive` → substrate laid, no seed prompt, no registry files. Operator-modified file → preserved with notice.

**See:** `docs/wiki/machine-local-registry.md`, `coordinator/lib/install-substrate.sh`, `coordinator/lib/claude-home/README.md`, `docs/wiki/coordinator-doctor.md`.

### Step 5 — Register coordinator plugin in `plugin.mirrors` (idempotent)

<!-- spec-backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md § Chunk 5 / AC-7 -->

Coordinator's live install IS the canonical source (`~/.claude/` itself). Register in `registry.local.toml::plugin.mirrors` so `check-plugin-drift.sh` surfaces it as `n/a-by-design`. Run under `--non-interactive`; pass `--check-only` when set.

```bash
_mirror_flag=""
[[ "${ARGUMENTS:-}" == *"--check-only"* ]] && _mirror_flag="--check-only"
bash "${CLAUDE_PLUGIN_ROOT}/lib/register-coordinator-mirror.sh" $_mirror_flag
```

The helper is idempotent and atomic — safe under concurrent `/coordinator:install` invocations.

Add a `Coordinator plugin.mirrors` row to the Phase 7 status table.

---

### Step 6 — Install `coordinator_whoami` package (idempotent)

<!-- spec-backlink: docs/plans/2026-05-21-whoami-first-class-substrate.md § Chunk 1 / AC-1, AC-2, AC-3, AC-15 -->
<!-- D4: default-with-warning — no prompt site; install fires mechanically under --non-interactive same as interactive. -->

```bash
python3 -c "import coordinator_whoami" 2>/dev/null
```

- **Import succeeds:** status `coordinator_whoami: ready`. No mutation.
- **`--check-only`:** status `coordinator_whoami: would write`. Exit step.
- **Otherwise:** `python3 -m pip install -e "${CLAUDE_PLUGIN_ROOT}/whoami/"`. On exit 0: `ready`. On non-zero: `failed` (log pip stderr; do NOT halt chain). Post-install probe P-5 in `docs/wiki/coordinator-doctor.md`.

Add row to Phase 7 table.

---

### Step 7 — Scaffold canonical document structure (idempotent)

<!-- spec-backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 6 -->
<!-- the Director of Engineering F5: pass --root explicitly so the scaffold targets the coordinator install root, not whatever cwd is at invocation time. -->

Scaffold (eager entries from `canonical-structure.yaml`) into `~/.claude`, landing `cross-repo/` with its README. Skip mutations under `--check-only` (emit `canonical_structure: would scaffold`).

```bash
_scaffold_root="${CLAUDE_HOME:-$HOME/.claude}"
_scaffold_script="${CLAUDE_PLUGIN_ROOT}/bin/scaffold-canonical-structure.sh"
bash "$_scaffold_script" --root "$_scaffold_root"
```

Idempotent — skips existing dirs/READMEs, never clobbers. On success: `canonical_structure: ready`. On non-zero: `canonical_structure: failed` (log stderr; do NOT halt — advisory, not hard infrastructure).

Add a `Canonical structure` row to the Phase 7 status table.

---

### Step 8 — Write fan-out large-wave threshold (idempotent)

<!-- spec-backlink: docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md § C6 -->

Write the cores-scaled soft ramp-reminder threshold (`3 × logical CPU count`, floored at 1) that `fan-out-dispatch.sh` reads before launching a large wave — a **speed-taper advisory, not a cap**. Never clobbers a manual override. Logic in `bin/capture-fan-out-threshold.sh`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-fan-out-threshold.sh"           # normal run
bash "${CLAUDE_PLUGIN_ROOT}/bin/capture-fan-out-threshold.sh" --check-only  # check-only: emits would write (N)
```

Add a `Fan-out threshold` row to the Phase 7 status table from the script's output (`written (N)` / `pre-existing` / `would write (N)`).

### Step 9 — Fire platform-localize once at install time

The `platform-localize.sh` hook auto-fires on SessionStart, so the first new session after install will produce a valid `settings.local.json` + `known_marketplaces.json`. But running it eagerly here closes the window where `/plugin` fails with a "marketplace configuration corrupted" error before the user opens a new session — a real-world failure surfaced 2026-06-14.

```bash
if [[ "${CHECK_ONLY:-0}" == "1" ]]; then
  # check-only: report whether the file would change, do not write
  echo "platform-localize: skipped (check-only mode)"
else
  bash "$HOME/.claude/bin/platform-localize.sh"
  # Confirm the output is schema-valid before continuing
  if [[ -f .github/scripts/validate-json-schemas.py ]] && [[ -f "$HOME/.claude/plugins/known_marketplaces.json" ]]; then
    python .github/scripts/validate-json-schemas.py 2>&1 | grep -E '(known_marketplaces|passed)' | head -3
  fi
fi
```

Idempotent. Adds row to Phase 7 status: `platform_localize: ran` / `skipped (check-only)` / `error (see stderr)`.

---

## Phase 4 — Meta-repo doctrine

### `~/.claude` git tracking

Check whether `~/.claude` is a git repo (`git -C ~/.claude rev-parse --show-toplevel 2>/dev/null || echo "not_a_repo"`).

- **Repo:** ready. If no remote, suggest adding one for machine-loss recovery. Also check that per-machine state files are gitignored: `grep -qE '^/?coordinator-setup-state\.yaml' ~/.claude/.gitignore 2>/dev/null`. If `gap` (and not `--check-only`), offer to append the `# --- Coordinator per-machine state ---` block from `templates/dotgitignore.tmpl` (do not auto-edit). Status row: `claude_gitignore: covered` / `gap (offered)` / `gap (declined)`.

- **Not a repo, not `--check-only`:** offer to initialize. <!-- D4: default-with-warning --> Under `--non-interactive`: skip (`claude_git_tracking: skipped`). Under interactive: **Initialize (Recommended)** — `git init ~/.claude`, starter `.gitignore`, commit `chore: initialize Claude Central`; or **Skip**. Do NOT push to remote.
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

Then ask for subtypes (empty default; under `--non-interactive` skip, status `coordinator_local_md: created (project_subtypes defaulted to empty)`):

> Any subtypes? Free-form advisory tags — no validation. Examples: `unreal` under game-dev; `react`, `nextjs` under web-dev. Comma-separated, or blank.

Write `coordinator.local.md`:

```markdown
---
project_type: {type}
project_subtypes: [{subtype1}, {subtype2}]   # omit field when blank
fast_test_cmd: "<your-project-fast-test-command>"  # optional; omit when not applicable
---
```

**`fast_test_cmd` (optional).** Run by `/workday-complete` Step 1 and `/workweek-complete` Step 2 via `cs_resolve_fast_test_cmd`. Resolution order: `COORDINATOR_FAST_TEST_CMD` env var → this key → skip-with-notice. Any shell-valid form: `npm run test:fast`, `cargo test --lib`, etc.

### Currency stamp (idempotent)

<!-- spec-backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1 -->
<!-- D4: default-with-warning — stamp is written silently; skip-with-note under --check-only. -->

Record which `COORDINATOR_SCHEMA_VERSION` the current repo's scaffolding was set up against, enabling drift probe (doctor P-13, Wave-2). Under `--check-only`: report `currency_stamp: current (vN)` / `drift (vN->vM)` / `unstamped(legacy)` / `would write`. Otherwise (idempotent write):

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

If customize: no `rename-personas.sh` ships yet — hand-edit names across agent files and prompts/skills. Exclude `bin/publish-time-transform.sh` from search-replace (it carries the canonical `NAME_TO_ROLE` table). One-time cosmetic choice; automation queued.

### Codex Integration (optional opt-in)

<!-- D4: opt-in — default declined; only --check-only reports state. -->
<!-- Spec backlink: docs/plans/2026-06-14-codex-reviewer-integration-opt-in.md -->
<!-- Sync: Leg-A and Leg-B Python heredocs below are mirrored verbatim in tests/plugin-ecosystem/platform-localize-marketplaces.test.js — any change here MUST be mirrored there. -->

Register the `openai-codex` marketplace + `codex@openai-codex` plugin as an optional second-opinion reviewer for `/workweek-complete` Step 7.4 and `/bug-sweep --codex-verify`. Default declined; opt-in is per-user.

Under `--non-interactive`: skip silently. Status row: `codex_integration: skipped (non-interactive)`.

Under `--check-only`: read `~/.claude/settings.json`. If `extraKnownMarketplaces["openai-codex"]` does not exist → `codex_integration: absent (would offer)`. If it exists with canonical shape `{"source": {"source": "git", "url": "..."}}` → `codex_integration: present`. If it exists with any other shape → `codex_integration: present (existing entry preserved — shape may differ from canonical)`. Do not mutate disk.

Under interactive:

> Install openai-codex marketplace? This registers the `codex@openai-codex` plugin (Claude Code wrapper over OpenAI Codex CLI), used as an independent-model second-opinion reviewer in `/workweek-complete` Step 7.4 (default-on, advisory) and `/bug-sweep --codex-verify` (opt-in flag). Prerequisite: Codex CLI installed and authenticated (`codex login`). The plugin will be registered user-global, but enablement is per-project — run `/plugin enable codex@openai-codex` from any project you want it active in (or this step will best-effort enable in the current project if cwd has a `.claude/` directory). **[y/N]**

**Soft prereq warning:** if `codex --version` fails, note *"Codex CLI not detected — you can install it separately at https://github.com/openai/codex; the marketplace registration is independent of CLI install."* Do NOT block — the marketplace can be registered ahead of installing the CLI.

**On NO:** status row `codex_integration: declined`.

**On YES:** two-leg idempotent edit, multi-OS safe via Python stdlib. Doctrine: `plugin-extraction-and-distribution.md` § 7 (marketplace registration is user-global; enablement is per-project).

**Two-surface model.** Leg-A writes the marketplace registration to user-global `~/.claude/settings.json`. `platform-localize.sh` separately manages `~/.claude/settings.local.json`'s `extraKnownMarketplaces` from a directory-scan of `~/.claude/plugins/<dir>/.claude-plugin/marketplace.json`. The two files are merged by Claude Code at load; the codex entry living only in `settings.json` is the intended steady state (we do not bundle a local `~/.claude/plugins/openai-codex/` mirror).

**Idempotency.** `setdefault` preserves existing entries with any shape — this is the desired no-clobber behavior, but it can mask stale or legacy entries written by older Claude Code versions (see status-row value `present (existing entry preserved — shape may differ from canonical)`).

**Canonical source shape.** GitHub-hosted remote marketplaces use `{"source": "git", "url": "..."}` — NOT `{"source": "github", "repo": "..."}` (the `github+repo` form is a legacy artifact observed only in negatively-labeled test fixtures; the live `claude-plugins-official` entry in `~/.claude/settings.json` uses `git+url`).

**Leg A — marketplace registration (user-global, MANDATORY).** Run:

```bash
python3 - <<'PY'
import json, pathlib, tempfile, os, sys
p = pathlib.Path.home() / ".claude" / "settings.json"
try:
    s = json.loads(p.read_text()) if p.exists() else {}
except (json.JSONDecodeError, OSError) as e:
    print(f"FATAL: existing settings.json malformed ({e}) — skipping codex opt-in. Repair and re-run.", file=sys.stderr)
    sys.exit(1)
mkts = s.setdefault("extraKnownMarketplaces", {})
mkts.setdefault("openai-codex", {"source": {"source": "git", "url": "https://github.com/openai/codex-plugin-cc.git"}})
# Per plugin-extraction-and-distribution.md § 7, enablement does NOT belong in user-global settings.json.
# Do NOT write enabledPlugins here.
fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(fd, "w", newline="\n") as f:
        f.write(json.dumps(s, indent=2) + "\n")
    os.replace(tmp_path, p)
except Exception:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    raise
PY
bash "$HOME/.claude/bin/platform-localize.sh"
```

**Leg B — best-effort project enablement (project-local, optional).** Skips silently when install is run from the meta-repo (`cwd == ~/.claude`) or from a directory without a `.claude/` subdir; writes when cwd has a project Claude directory.

```bash
python3 - <<'PY'
import json, pathlib, os, tempfile, sys
cwd = pathlib.Path(os.getcwd()).resolve()
home_claude = (pathlib.Path.home() / ".claude").resolve()
if cwd == home_claude:
    print("install run from meta-repo — skipping leg-B project-enablement write")
    sys.exit(0)
proj_settings = pathlib.Path(os.getcwd()) / ".claude" / "settings.local.json"
is_claude_project = (
    proj_settings.exists()
    or (proj_settings.parent / "settings.json").exists()
    or (proj_settings.parent.parent / "CLAUDE.md").exists()
)
if proj_settings.parent.exists() and is_claude_project:
    try:
        s = json.loads(proj_settings.read_text()) if proj_settings.exists() else {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"FATAL: existing {proj_settings} malformed ({e}) — skipping project enablement. Repair and re-run.", file=sys.stderr)
        sys.exit(1)
    plugins = s.setdefault("enabledPlugins", {})
    plugins.setdefault("codex@openai-codex", True)
    fd, tmp_path = tempfile.mkstemp(dir=proj_settings.parent, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="\n") as f:
            f.write(json.dumps(s, indent=2) + "\n")
        os.replace(tmp_path, proj_settings)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    print(f"codex enabled in project: {proj_settings.parent.parent}")
else:
    print("no recognizable Claude project at cwd (.claude/ absent or empty of Claude markers) — run /plugin enable codex@openai-codex from any project that wants it active")
PY
```

**Status row.** `codex_integration: installed (registered; enabled in <project>)` when Leg B fired with a write; `installed (registered; no project detected — run /plugin enable)` when Leg B was a meta-repo skip or no-cwd-project; `present` for an existing canonical entry; `present (existing entry preserved — shape may differ from canonical)` when an existing entry was preserved but its shape diverges from `git+url`.

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

Record the enduring `setup_concluded` milestone so sibling repos can confirm coordinator is ready. Idempotent. Skip mutations under `--check-only` (emit `setup_state_receipt: would record`).

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/coordinator-setup-state.sh" record setup_concluded
```

Add a `Setup-state receipt` row to the status table (`recorded` / `pre-existing` / `would record`).

**Phase 7 status table — codex_integration row.** Driven from the Phase 6 Codex Integration step's outcome. Value-set: `installed (registered; enabled in <project>)` | `installed (registered; no project detected — run /plugin enable)` | `declined` | `present` | `present (existing entry preserved — shape may differ from canonical)` | `absent (would offer)` | `skipped (non-interactive)`.

Present a summary table with one row per check above. Full status-row value-sets and available-commands list: `docs/wiki/setup-reference-detail.md` § Phase 7.

### Plugin-bundled doctrine wikis

Plugin ships doctrine at `<plugin-install-path>/docs/wiki/`. If **required** items (git) are missing, note prominently. If recommended items (Agent Teams, CLAUDE.md import) are missing, list next steps.

**Hard-precondition rows.** Machine-local rows are non-optional: `FATAL` means Phase 3 halted (downstream skills won't function). `Registry seed` is informational only.

### Optional next step — guided onboarding

Skip under `--check-only`. After the status table, offer: *"Want a guided tour? Just say **'walk me through the coordinator.'**"* If accepted, record `orientation_started`, read `docs/wiki/getting-started.md` (plugin-relative), and facilitate the three movements (Orient → Make it yours → Test drive). The guide's `## For the EM facilitating this` section is your playbook; records `orientation_completed`. If declined, point to `/workstream-start`.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/coordinator-setup-state.sh" record orientation_started
```

End with: _"`/coordinator:install` is environment-only. Run `/coordinator:setup` to scaffold a new project, then `/workstream-start` to begin work."_ If `--check-only`, show the table but note what *would* be created/configured without the flag.

**Refinement target close.** Include verbatim in every next-steps block (not under `--check-only`):

> Your `~/.claude` is the surface you evolve — git-track it and back it up; never edit the coordinator clone.

### Optional next step — bootstrap repo scaffolding

<!-- spec-backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 4 / AC8 -->
<!-- D4 annotation: skip-with-note — elective offer; suppressed under --non-interactive and --check-only. -->

**Suppressed under `--non-interactive` or `--check-only`.** Status row: `repo_setup_offer: suppressed (--non-interactive|--check-only)`. No `AskUserQuestion`, no `/repo-setup --batch` invocation, no offer text.

Under interactive (after the status table has been shown), read `~/.claude/working-repos.yaml` to get the discovered repo count (N). If N > 0, offer:

> Discovered **N** working repo(s) in `working-repos.yaml`. Want to bootstrap coordinator scaffolding into them? Run `/repo-setup --batch` — Express mode applies to all, Custom mode lets you pick per-repo. 0% destructive; every change is git-revertible.

If accepted, instruct them to run `/coordinator:setup --batch` (do NOT inline scaffolding here — `/coordinator:install` is environment-only). If declined or N = 0, skip silently.

Status row: `bootstrap_offer: offered (N repos)` (after offer shown) / `suppressed (--non-interactive|--check-only)` / `skipped (0 repos discovered)`.
