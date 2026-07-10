---
description: Install the coordinator plugin — check prerequisites, verify environment, configure project. Safe to re-run.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive] [--accept-no-git-auth]"
---

# Coordinator Install

<!-- spec-backlink: archive/specs/2026-05/2026-05-19-coordinator-installer-redesign-implementation.md -->

Environment and project setup for the coordinator plugin. This is a **guided install** — you participate in the shape decisions; the agent moves fast on mechanism. Safe to re-run — skips anything already configured.

## You are here — prerequisites before running this

This document is written for the **POST-INSTALL RE-RUN path**: the coordinator plugin is
already wired (`CLAUDE_PLUGIN_ROOT` resolves, `/coordinator:install` is invokable), and every
`${CLAUDE_PLUGIN_ROOT}/...` reference below just works. If that's you, skip to Step Zero.

If you're doing the **COLD-BOOTSTRAP path** — a fresh machine, nothing installed yet, no
`/coordinator:install` slash command available — this doc is not your entry point. See root
`INSTALL.md` first. In short, either:

- run the one-shot orchestrator from the repo root: `bash coordinator/scripts/install-maximalist.sh`
  (drives the full phase sequence with its own root resolution, no env setup needed); or
- if you want to hand-walk this doc's phases from a bare clone, first
  `export CLAUDE_PLUGIN_ROOT="<path-to-DoE-claude-clone>/coordinator"` once per shell session, then
  every `${CLAUDE_PLUGIN_ROOT}/...` path and relative `scripts/...` reference below resolves correctly.

Cold-bootstrap and re-run converge on the same substrate — the distinction is only about how
`CLAUDE_PLUGIN_ROOT` gets resolved before this doc's commands can run (F3).

**Reversing this install:** see `coordinator/commands/uninstall.md` — the tested, first-class symmetric counterpart to this command. It reverses every out-of-repo surface this install writes (settings.json hook block, shell shim/wrapper, machine-local registry keys, whoami/venv, `.doe-root` pointer, `~/.claude/bin/` forwarders, plugin wiring), snapshot-independent. Surface list kept in lockstep between the two commands per `coordinator/docs/wiki/external-plugin-live-resolution.md § Install/uninstall surface symmetry — canonical cross-links`.

## Step Zero — Functional preflight and env-normalization

<!-- spec-backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md -->

Before any phase, run a functional gate to verify prerequisites and fix what can be fixed automatically.

### 1. Preflight gate

<!-- Review: code-reviewer F8 — bare bash invocation trains the 3.2 antipattern on macOS; operator must have bash ≥ 4 on PATH first -->
> **macOS prerequisite:** `bash scripts/setup.sh --preflight` requires bash ≥ 4 on PATH. macOS ships bash 3.2 at `/bin/bash` — install a current bash first: `brew install bash` (adds `/opt/homebrew/bin/bash`). Once brew bash is on your PATH, `bash --version` will report 5.x and the command below will work correctly.

```bash
bash scripts/setup.sh --preflight
```

`--preflight` is a **superset of `--check`**: it runs manifest-dependency probes AND environment-prerequisite probes through a single tabling + NDJSON emitter. Exit behavior is severity-aware:

| Probe | Severity | Exit behavior |
|---|---|---|
| `python` | **hard** | Non-zero exit — install MUST stop until resolved |
| `uv` | advisory WARN | Logged; install continues |
| `clone_auth` | **semi-hard** | Blocks unless resolved or `--accept-no-git-auth` (exit 94 — see `agent-install-contract.md` exit-code table) |
| `longpaths` | advisory WARN | Logged; install continues (Windows-only) |
| `pwsh` | advisory WARN | Logged; install continues — see PowerShell 5.1 note below |
| `ue` | advisory WARN | Logged; install continues |

The probe library is `scripts/lib/prereq_probe.sh` — a read-only SSOT that never mutates state. The gate reads from it; the fixer (below) writes. Any `inconclusive` probe result is surfaced explicitly and treated as advisory WARN (not a hard failure).

**`clone_auth` semi-hard gate — interactive offer and non-interactive contract.**

When the `clone_auth` probe fires (no GitHub auth found), the gate behavior depends on mode:

- **Interactive (default):** offer to run `gh auth login` now (or, if the operator is on GitLab, point to `glab auth login`). On accept, re-run the `clone_auth` probe — if it passes, proceed. On decline or failure, instruct the operator to either configure auth manually and re-run, or pass `--accept-no-git-auth` to skip the gate and continue without git auth.

  ```
  clone_auth probe: no GitHub auth found.
  Offer: run `gh auth login` to authenticate now? [Y/n]
    → Y: runs `gh auth login`; re-probes; proceeds on pass.
    → N: re-run with --accept-no-git-auth to skip this gate, or configure auth manually first.
  ```

- **`--non-interactive` with no auth and no `--accept-no-git-auth`:** FAIL-LOUD — no TTY to run the offer; exit non-zero with remediation message. This matches the manifest hard-dep non-TTY pattern (exit-90 spirit). Cite: `docs/wiki/coordinator-installer-shape.md § --non-interactive contract`. Status: `clone_auth: failed (no auth — re-run with --accept-no-git-auth or configure auth first)`.

- **`--accept-no-git-auth` (any mode):** skip the gate; emit advisory `clone_auth: skipped (--accept-no-git-auth)` and continue. Private repos that require auth will fail at clone time, not here.

- **`--check-only`:** report `clone_auth: semi-hard (would block without --accept-no-git-auth)` — do NOT exit non-zero. Check-only never mutates or blocks; it only reports what *would* happen.

**PowerShell 5.1 fallback (#03).** The `pwsh` probe checks for PowerShell 7+ (`pwsh`). If `pwsh` is absent or below version 7, the probe WARNs but does not block — the coordinator falls back to the inbuilt Windows PowerShell 5.1 (`powershell.exe`) for `.ps1` scripts that require it. `pwsh` 7+ is preferred (cross-platform, fully supported); 5.1 is the fallback, not the target. See `1c.2` below and `docs/wiki/coordinator-installer-shape.md` § Step Zero.

### 2. Env-normalization

If the preflight reports fixable advisory WARNs, run the env-normalizer **dry-run first** to preview mutations without applying them:

```bash
# Preview only — no changes made
bash scripts/normalize-env.sh --dry-run

# Apply all consented mutations
bash scripts/normalize-env.sh --yes
```

`normalize-env.sh` is idempotent and consent-gated: it enumerates each proposed mutation and requires explicit acceptance per mutation. Blast-radius-last ordering applies (higher-impact mutations are offered last). On Windows, every mutation creates a backup and `--restore` reverts to the pre-run state. On macOS the script is offers-only EXCEPT for the single consent-gated bash-login-shell reconstruction (see § Login-shell orphan detection below); on Linux it is offers-only (no Windows-specific mutations run).

Proceed to Phase 1 after Step Zero. Any hard failure from `--preflight` must be resolved before continuing.

---

## Requirements

Phase 1 checks each item and fails loud (or warns) per the D4 contract.

- **bash ≥ 4.3** (hard requirement). Scripts use `declare -A` (bash 4.0+) and `local -n` namerefs (4.3+). macOS ships bash 3.2 — install via `brew install bash` and put it first on PATH. Linux/WSL/Git Bash ship 4.3+ already. Policy: `docs/decisions/DR-148-require-bash4-on-macos.md`.
- **git** — branch management, commits, handoffs, auto-push.
- **Python 3** — hooks and JSON manipulation.
- **jq** — required for JSON output in `/workday-start` addon-health.
- **uv** — only for Pipeline D (NotebookLM media research); provides `uvx` to launch the Python MCP server (see §1d).
- **scc** — optional; powers code statistics in session orientation.
- **PowerShell 7+ (`pwsh`)** — default-on, all platforms. Windows hidden-spawn / auto-push / `.ps1` scripts target it (falling back to the inbuilt Windows PowerShell 5.1); offered on macOS, Linux, and Windows. Not a hard blocker.
- **Windows Terminal** — default-on, Windows only. Modern console host paired with `pwsh` 7 (no legacy conhost flash on hidden-spawn paths).

## Execution dial and structural fork

**Execution dial:** Default is **agent-led** — prompts only where genuine decisions are needed. Pass `--non-interactive` to suppress all `AskUserQuestion` calls; see the **D4 Non-Interactive Contract** below for per-site fallback.

**Structural fork — three states:** Before any phase, classify the Claude home:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/lib/detect-existing-claude-home.sh"
# Emits one line: state=<pristine|used-vanilla|configured> track=<A|B> reason: …
```

Branch on **`state=`** (the `track=` field is a backward-compat binary alias —
`configured → B`, else `A` — kept only for older callers; do not key new logic on it):

- **`pristine`** — Claude Code has never run here; no artifacts at all. Proceed through all phases from zero. No caveat in the status report — there is nothing to merge or collide with.

- **`used-vanilla`** — Claude Code HAS been run, but nothing opinionated was set up (no git, no installed plugins, no coordinator infra — only session history, Claude-Code-managed `plugins/` scaffolding, and/or a hand-edited `CLAUDE.md`). Proceed through all phases from effectively zero. Surface a *light, non-alarming* note:

  > **Existing Claude Code usage detected (no custom setup).** Installing the coordinator on top — your sessions and any `CLAUDE.md` edits are preserved, not overwritten. Re-running is safe. Use `--check-only` to preview.

  Do NOT show the "your setup may collide / merge is yours" warning — there is no opinionated setup to collide with. This is the state a freshly-installed machine lands in, and it MUST NOT read as a clobber risk.

- **`configured`** — an opinionated, deliberately-customized home (git-tracked, installed plugins, or coordinator infrastructure — "a setup like ours"). Surface at top of status report:

  > **Existing `~/.claude` setup detected.** This installs from zero; merge is yours. Re-running is safe; it skips anything already present. Use `--check-only` to see state without changes.

  Continue through all phases as normal. Do NOT offer a merge engine or selective-adoption UI.

**Invariant across all three states:** idempotency guards (never clobber `CLAUDE.md`, `settings.json`, machine-local registry files) hold regardless of the classified state. The state drives *posture and messaging*, never whether file-level overwrites are permitted — they never are.

**Status-table row:** surface the classification as the first row of the Phase 7 status table — `home_state: <pristine|used-vanilla|configured>` — so the report records which posture was taken.

## Check-only mode

If `$ARGUMENTS` contains `--check-only`: report environment state without making any changes. Every phase runs its read-only checks and emits status rows, then stops before any mutation. Combine with `--non-interactive` freely — both flags are orthogonal.

## Flags reference

| Flag | Effect |
|---|---|
| `--check-only` | Read-only report pass — no mutations. Orthogonal to `--non-interactive`. |
| `--non-interactive` | Suppresses all `AskUserQuestion` prompts; per-site D4 fallback applies (`skip-with-note` / `default-with-warning` / `fail-loud`). |
| `--accept-no-git-auth` | Skips the `clone_auth` semi-hard gate. Use when git auth is intentionally absent (e.g. public-only repos, CI installs, headless machines with no interactive auth flow). Without this flag, `--non-interactive` with no git auth is a `fail-loud` exit. |

## D4 Non-Interactive Contract

<!-- spec-backlink: D4 in archive/specs/2026-05/2026-05-19-coordinator-installer-redesign-implementation.md -->

Each prompt site is annotated: `skip-with-note` (skip, surface in status table), `default-with-warning` (apply safe default, surface value), or `fail-loud` (exit non-zero with remediation; no safe default). Unannotated sites default to `fail-loud`. `--check-only` prevents all mutation; `--non-interactive` controls only prompt fallback. Both are orthogonal and may be combined.

**Scope distinction:** This command sets up the coordinator *environment* (plugins, env vars, tools). For per-project scaffolding (CLAUDE.md, tracker, workstreams), use `/coordinator:repo-setup` after this.

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
          # Remediation (decline/error fallback):
          echo ""
          echo "ERROR: coordinator requires bash 4.3 or later. Detected: bash <version> at <path>."
          echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it FIRST on PATH:"
          echo "      brew install bash"
          echo "      export PATH=\"\$(brew --prefix)/bin:\$PATH\"   # add to your login shell rc (~/.zprofile if your login shell is zsh, the macOS default)"
          echo "  You do NOT need to change your login shell to bash — coordinator runs scripts via PATH, not via your login shell."
          OFFER_B_SUCCESS=0
        fi
      else
        STATUS: brew_bash_installed: failed (declined)
        # Remediation (decline/error fallback):
        echo ""
        echo "ERROR: coordinator requires bash 4.3 or later. Detected: bash <version> at <path>."
        echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it FIRST on PATH:"
        echo "      brew install bash"
        echo "      export PATH=\"\$(brew --prefix)/bin:\$PATH\"   # add to your login shell rc (~/.zprofile if your login shell is zsh, the macOS default)"
        echo "  You do NOT need to change your login shell to bash — coordinator runs scripts via PATH, not via your login shell."
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
                  echo "  (macOS: a new terminal tab is often a non-login shell and will not source $RC automatically. Restart the terminal app to ensure the value is inherited.)"
                  echo "  brew bash is now first on PATH; you do NOT need to make bash your login shell — coordinator runs scripts via PATH, not via your login shell."
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

#### Login-shell orphan detection and repair (macOS — post-offer step)

After the bash-version offers complete, if the `_co_probe_shell_login_env` probe (in `scripts/lib/prereq_probe.sh`) reports an orphaned bash login shell — meaning the user's login shell is `bash` but their `~/.bash_profile` does not carry `~/.local/bin` (where `claude` lives) — the install agent explains the situation in plain terms and offers repair:

> **claude will vanish in a fresh terminal** because your bash login shell's `~/.bash_profile` does not include `~/.local/bin`. This does NOT mean you need to change your login shell back to zsh — the existing `~/.bash_profile` is simply missing the PATH entry. Run `normalize-env.sh` to reconstruct it.

Offer to run `bash scripts/normalize-env.sh --yes` to reconstruct `~/.bash_profile`. **No `chsh` is offered, implied, or executed** — this step repairs an already-bash login shell; it does not create one and does not prompt the user to change their login shell in either direction.

**Sentinel audit note.** Offer C's `case` statement and `normalize-env.sh`'s reconstruction share the single sentinel `# coordinator-install: brew shellenv (DR-148)`. A re-run where the login shell is already `bash` detects the reconstructed `~/.bash_profile` via the existing `grep -qF "$SENTINEL"` guard and stands down rather than appending a duplicate block.

#### 1a.0.1. Invoking-shell bash≥4 verification (install-completion check)

The offers above (A/B/C) repair the **login shell** — but the Claude Code **Bash tool's** invoking-shell resolution is a separate, undocumented mechanism (there is no `settings.json` override for it) that can still land on zsh or `/bin/bash` 3.2 even after Offer C succeeds. When that happens, coordinator lifecycle skills that `source` a bash≥4-guarded lib (e.g. `/pickup`'s consume block sourcing `strangler-facade.sh`) abort mid-flow with an opaque `requires bash >=4 (found unknown)` error — a silent trap the operator only discovers later. Run the shared probe as a verification step so a fresh install that leaves the invoking shell at bash 3.2 WARNs loudly here instead of appearing to succeed silently:

```bash
sh "${CLAUDE_PLUGIN_ROOT}/scripts/lib/invoking-shell-bash4-probe.sh"
```

- **Exit 0** (silent): invoking shell is bash≥4. Status: `invoking_shell_bash4: ready`.
- **Exit 1** (remediation printed to stderr): invoking shell is NOT bash≥4. Surface the printed remediation verbatim to the operator and add to the Phase 7 status table: `invoking_shell_bash4: failed (see remediation above — coordinator lifecycle skills will break until this is done)`. This is a WARN, not a hard installer blocker — Offers A/B/C above already ran; this check independently verifies the invoking-shell dimension they don't cover.

This is the install-time counterpart of the SessionStart advisory (`hooks/scripts/nudge-invoking-shell-bash4.sh`) — the install check runs once at setup; the session hook re-checks cheaply on every session start so drift (a later `chsh` back to zsh, a new terminal profile) is still caught. Durable fix — migrating the guarded-lib `source` callsites behind the `cc_invoke` seam so they no longer depend on the invoking shell's own bash version — is tracked on the pcore Python track via a separate example-orchestration-hub consult, not here.

<!-- Review: code-reviewer -- this step is read-only (writes no out-of-repo state), so it
     intentionally has no `uninstall.md` counterpart and is deliberately absent from the
     install/uninstall surface-symmetry list at line 32 above. Noted here so a future
     symmetry auditor doesn't misread the absence as a gap. -->

### 1a. Git repository

```bash
git rev-parse --show-toplevel 2>/dev/null
```

- If not a git repo: warn that branch management, commits, and handoffs require git. Setup continues.
- If a git repo: note the repo root path.

### 1a.1. Git-config hardening (concurrent-EM lock safety)

Harden **this repo's** git config with two concurrent-EM mitigations (root-causes: `docs/wiki/concurrent-em-hazards.md` § H21–H22): `gc.autoDetach false` (prevents detached GC child orphaning `.git/index.lock` on Git-for-Windows) and `core.checkStat minimal` (ignores NTFS-unstable `ctime/ino/dev` fields that cause phantom-dirty tree). Skip mutations under `--check-only` (report current values instead).

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
"$_cc_root/bin/coordinator-configure-git"
```

Idempotent. `gc.autoDetach` is scoped per-repo (not global — would change auto-gc in unrelated repos); spread via `/repo-setup` § 3f.5 and `session-init.sh`. `core.checkStat minimal` is benign on all platforms — also set machine-wide:

```bash
git config --global core.checkStat minimal
```

### 1a.2. Operator `~/.claude` exec-bit pre-commit gate (conditional)

If the operator git-tracks their `~/.claude` (the template-recommended setup), install the exec-bit drift gate into `~/.claude/.git/hooks/pre-commit` so a shebanged script can never be committed at `100644` (the failure mode that ships a non-functional install to anyone cloning that tree on Unix). Pass `"$HOME/.claude"` explicitly — the installer is cwd-independent and self-guards to the meta-repo identity, so it no-ops cleanly when `~/.claude` is not a git repo.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
"$_cc_root/bin/install-meta-repo-precommit-hook.sh" "$HOME/.claude"
```

Under `--check-only`, do NOT run the installer — the script has no check-only mode (it always mutates). Instead, omit the invocation and report the gate's current presence:

```bash
[ -f "$HOME/.claude/.git/hooks/pre-commit" ] && grep -q coordinator-precommit-exec-bit-check "$HOME/.claude/.git/hooks/pre-commit" && echo "exec-bit gate: present" || echo "exec-bit gate: absent (would install)"
```

Idempotent (no-op if the gate marker is already present). This is the OSS-user analogue of `/repo-setup` § 3f.5.5: `/coordinator:install` is the surface every operator runs against their own `~/.claude`, so the gate must land here — `/repo-setup` only fires it against the consumer *project* repos it scaffolds, where the helper correctly no-ops.

### 1a.3. Git-LFS enablement (idempotent, harmless — proactive coverage)

Proactively enable Git LFS so that any LFS-backed repo the operator clones later (e.g. project-rag-ue-addon, example-game-repo with `*.uasset`/`*.umap`) materializes real binary content instead of silent ~130-byte pointers. This is the "cover it before they get there" move — `git lfs install` is a harmless, idempotent global config write even for operators who never clone an LFS repo. Reaching this step does NOT depend on `first-run.sh` having run (which is the canonical fresh-clone bootstrap that also enables LFS, but is not traversed on every install path — e.g. coordinator already present on an existing machine). Doctrine: `docs/wiki/install-surface-completeness.md` § Git-LFS materialization.

This is **act-not-gate**: enable when the binary is present; emit advisory remediation when absent. It does NOT hard-fail — the `git_lfs` row in the `--preflight` gate (`scripts/lib/prereq_probe.sh _co_probe_git_lfs`) is the advisory verifier and stays advisory (PM-decided 2026-06-24, AC10). The `--check-only` branch comes first and never mutates — it reports state and returns, matching the inline check-only pattern used elsewhere in Phase 1.

```bash
if [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
  # FB-2 functional-not-existence: binary present AND global filter wired (a bare
  # filter.lfs.clean key can survive a partial/aborted install).
  if git lfs version >/dev/null 2>&1 && [ -n "$(git config --global --get filter.lfs.clean 2>/dev/null)" ]; then
    echo "git_lfs: enabled"
  else
    echo "git_lfs: not enabled (would enable)"
  fi
elif git lfs version >/dev/null 2>&1; then
  # Plain `install`, NOT `--force` — coexists with existing pre-push/post-commit hooks.
  if git lfs install 2>/tmp/coordinator-lfs-install.err; then
    echo "git_lfs: enabled (global, idempotent)"
  else
    echo "git_lfs: git lfs install failed — re-run after resolving git-lfs setup" >&2
    cat /tmp/coordinator-lfs-install.err >&2
    echo "git_lfs: failed (see stderr)"
  fi
else
  echo "git_lfs: absent (advisory) — install git-lfs to materialize LFS-backed clones — macOS: brew install git-lfs | Windows: winget install GitHub.GitLFS | Linux: apt install git-lfs (or distro equivalent) — then re-run /coordinator:install" >&2
  echo "git_lfs: absent (advisory)"
fi
```

Idempotent (re-running `git lfs install` is a no-op once the global filters are wired). The meta-repo `~/.claude` itself LFS-tracks nothing, so no materialization (`git lfs pull` + pointer-scan) runs here — that hard assert is the per-repo step-zero surface for repos that *do* LFS-track content (§ altitude split in the doctrine wiki). Add a `git_lfs` row to the Phase 7 status table.

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

### 1b.1. Python 3 (real interpreter — not the Windows Store App-Execution-Alias stub)

<!-- D4 annotation: read-only check in Phase 1; the Phase 3 install-substrate.sh remediation (python3.cmd shim + orphan-stub deletion) is where the fix lands. This row surfaces the condition early so the status table flags it before any python3-dependent step. -->

Hooks and config helpers call `python3`. On **Windows**, `python3` resolves by default to a Microsoft Store **App-Execution-Alias** — a 0-byte stub that errors on run and is invisible to Git Bash — so a bare `python3` check can read as "present" while every invocation fails. Probe the real interpreter:

```bash
PY3="$(command -v python3 2>/dev/null || true)"
if [ -z "$PY3" ]; then
  echo "python3: not_found"
elif python3 --version >/dev/null 2>&1; then
  # `--version` (not `python3 -c …`) avoids tripping the Windows console-popup
  # advisory hook during the install ceremony; it also exits non-zero on the
  # App-Execution-Alias stub, so it doubles as the stub detector.
  echo "python3: ready ($(python3 --version 2>&1 | cut -d' ' -f2) at $PY3)"
else
  # Resolves but does not execute → the Windows App-Execution-Alias stub
  echo "python3: App-Execution-Alias stub detected ($PY3) — Phase 3 install-substrate.sh installs a python3.cmd shim and offers to delete the orphan stub"
fi
```

- **ready:** real interpreter present. Status: `python3: ready (<version> at <path>)`.
- **App-Execution-Alias stub detected (Windows):** `default-with-warning` — Phase 3 (`install-substrate.sh`) lays a `python3.cmd` shim and detects/offers-to-delete the orphan AppX stub. Status: `python3: stub (will shim in Phase 3)`. Until then, recommend a real Python (`winget install Python.Python.3.13`) with `Python313\` ahead of `…\WindowsApps` on PATH.
- **not_found:** `fail-loud` — JSON manipulation and hooks need it. Status: `python3: failed (not on PATH)`. Install from https://python.org.

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

### 1c.2 PowerShell 7+ (`pwsh`) — default-on, all platforms

<!-- D4 annotation: skip-with-note — install offer is elective; --non-interactive skips and notes status. -->

Coordinator's Windows hidden-process spawning (`lib/spawn-hidden.sh`, `bin/coordinator-auto-push`), machine-local shims, and `hooks/project-rag-detect.ps1` target PowerShell. On Windows these fall back to the inbuilt Windows PowerShell 5.1 (`powershell.exe`), but **PowerShell 7+ (`pwsh`) is the default-on target** — the supported cross-platform shell, superseding 5.1. Offered on macOS, Linux, and Windows; not a hard blocker.

```bash
PWSH_BIN="$(command -v pwsh 2>/dev/null || true)"
PWSH_VER=""
[ -n "$PWSH_BIN" ] && PWSH_VER="$("$PWSH_BIN" --version 2>/dev/null | awk '{print $2}')"
PWSH_MAJOR="${PWSH_VER%%.*}"
```

- **`pwsh` present and major ≥ 7:** ready. Status: `powershell: ready ($PWSH_VER at $PWSH_BIN)`.
- **`pwsh` absent (or major < 7):** offer install per platform. Under `--check-only`: `powershell: not_found (would offer)`. Under `--non-interactive`: skip — `powershell: not_found (install offer suppressed — non-interactive)`. Under interactive, offer Y/n (default Y); on accept run the platform command, on decline emit `powershell: declined`:

  - **macOS (`$OSTYPE` = `darwin*`):** `brew install powershell` — **formula, not cask.** The legacy `--cask powershell` was removed from homebrew-cask; PowerShell now ships as a homebrew-core formula (depends on `dotnet`). Requires brew (Offer A above). On success: `powershell: installed ($(pwsh --version | awk '{print $2}'))`.
  - **Linux (`$OSTYPE` = `linux*`):** if `command -v snap` → `sudo snap install powershell --classic`; else doc pointer — `powershell: not_found (install: https://learn.microsoft.com/powershell/scripting/install/install-on-linux)`. Distro package repos vary; a clean one-liner isn't portable.
  - **Windows (`$OSTYPE` = `msys`/`cygwin`):** if `command -v winget.exe` → `winget.exe install --id Microsoft.PowerShell --source winget --accept-package-agreements --accept-source-agreements`; else doc pointer `https://learn.microsoft.com/powershell/scripting/install/install-on-windows`. **New-shell caveat:** a winget install lands `pwsh` under `…\WindowsApps` (or the WinGet `Links` shim dir) which is NOT on the *current* shell's PATH — report `powershell: installed (open a NEW shell for it to appear on PATH)`, not a bare `ready`, so the operator doesn't expect `command -v pwsh` to resolve in-session.

### 1c.3 Windows Terminal (`wt`) — default-on, Windows only

<!-- D4 annotation: skip-with-note — Windows-only; silent no-op on macOS/Linux. -->

Windows-only. On macOS/Linux this check is a silent no-op (emit no row). On Windows, Windows Terminal is the **default-on** modern console host paired with PowerShell 7 — it gives the hidden-spawn and auto-push paths a host that doesn't flash a legacy conhost window.

```bash
if [[ "$OSTYPE" == msys || "$OSTYPE" == cygwin ]]; then
  WT_PRESENT="$(command -v wt.exe 2>/dev/null || true)"
  # winget is the authority when wt is not yet on PATH:
  [ -z "$WT_PRESENT" ] && command -v winget.exe >/dev/null 2>&1 && \
    winget.exe list --id Microsoft.WindowsTerminal >/dev/null 2>&1 && WT_PRESENT="installed (winget)"
fi
```

- **Present:** `windows_terminal: ready`.
- **Absent, interactive:** offer Y/n (default Y) → `winget.exe install --id Microsoft.WindowsTerminal --source winget --accept-package-agreements --accept-source-agreements`. On success `windows_terminal: installed (open a NEW shell / Terminal for it to appear on PATH)` — like `pwsh`, the winget shim is not on the current shell's PATH until a new shell starts, so don't report a bare `ready`; on decline `windows_terminal: declined`; no winget → `windows_terminal: not_found (install via Microsoft Store or https://aka.ms/terminal)`.
- **`--check-only`:** `windows_terminal: not_found (would offer)`. **`--non-interactive`:** skip — `windows_terminal: not_found (install offer suppressed — non-interactive)`.

### 1d. NotebookLM opt-in (Pipeline D)

Deep-research pipelines (web, semantic, multi-agent) are **bundled into coordinator** — they ship with the coordinator plugin and require no separate installation. There is no standalone deep-research plugin and no `--with-deep-research` flag.

The **only opt-in** in this section is **Pipeline D (NotebookLM media research)**, which is default-off. Pipeline D is carried by a dedicated `notebooklm` MCP plugin (`notebooklm@coordinator-claude` in `enabledPlugins`). Enabling it adds its `.mcp.json` NotebookLM MCP server to the session.

**Pipeline D prereqs** (check before offering):
- `uv`/`uvx` on PATH (the server is launched via `uvx --from notebooklm-mcp-cli notebooklm-mcp`)
- Google authentication completed (`nlm login`)

Check whether the notebooklm plugin is already enabled:

```bash
grep -r "notebooklm" ~/.claude/settings.json 2>/dev/null | grep -q "enabledPlugins" && echo "enabled" || echo "not_enabled"
```

**If enabled:** `notebooklm_plugin: enabled`. Note that Pipeline D requires `uv` on PATH and `nlm login` (Google auth) to function.

**If not enabled:** offer to enable the notebooklm plugin (default-off — no offer in most installs). Do NOT offer UE/example-game-repo/game-dev stack or project-rag alongside it.

<!-- D4 annotation: skip-with-note — install offer is elective; --non-interactive skips and notes status. -->

Under `--non-interactive`: skip; emit `notebooklm_plugin: not_enabled (offer suppressed — non-interactive)`. Under `--check-only`: emit `notebooklm_plugin: not_enabled (would offer enable)`.

Under interactive, offer Y/n (default N — Pipeline D is opt-in). On Y: add `notebooklm@coordinator-claude` to `enabledPlugins` in `~/.claude/settings.json`; note that `uv` and `nlm login` are still required before first use. On n: skip.

NotebookLM opt-in status is an **explicit row** in the Phase 7 status table regardless of outcome.

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

### Engagement posture capture

<!-- spec-backlink: archive/specs/2026-07/2026-07-09-coordinator-end-user-modes.md -->

Persists the operator's preferred EM engagement posture to `~/.claude/coordinator-identity.yaml` alongside `operator_name`, and materializes the matching doctrine overlay into `~/.claude/CLAUDE.md` before the post-install restart (§ Phase 7 "Next step" tells the operator to restart — the overlay must be in place by then, not applied post-hoc on next boot). This is a **mandatory gate, not an opt-in feature**: it is asked on every run that lacks a persisted value, interactive or `--non-interactive` alike. There is no skip-injection mode — opting out of the question means not running the installer. Persistence exists purely for re-run ergonomics (a repeat install doesn't re-ask), never as a way to bypass the first-run gate.

**Step 3b-1 — Read persisted posture if present.**

Reuse the `version: 1` frontmatter already read for operator identity (Step 1 above); check the same parsed document for an `engagement_posture` key.

- **`engagement_posture` present** (one of `precision` / `default` / `substrate-free`) → use stored value; skip the question below. Status: `engagement_posture: ready (<value>)`. Proceed to Step 3b-3 (repo-override cross-check).
- **`engagement_posture` absent** (fresh identity file, or an identity file written before this feature shipped) → proceed to Step 3b-2. `--reconfigure` (same flag as operator identity, Step 2 above) also forces re-asking here.

**Step 3b-2 — Ask the posture question (mandatory gate; fires under BOTH interactive and `--non-interactive`).**

- **Under interactive:** ask via `AskUserQuestion`, framing each anchor with a depersonalized archetype — never a named individual (this surface ships to end users; AC9):

  *"How do you want the coordinator EM to work with you day to day?"*
  - **Precision** — *"I want to stay hands-on: review diffs, weigh in on internal naming and refactor mechanics, be consulted before non-trivial calls."* (Fits a hands-on technical founder or researcher who wants tight visibility into engineering detail.)
  - **Default** — *"The standard First Officer partnership — the EM acts on engineering calls autonomously, surfaces tradeoffs before forks, and expects me to engage on planning and product direction."* (Today's default posture — most operators want this.)
  - **Substrate-free** — *"Brief me at milestones, minimize interruptions, surface only ship/product-level gates — I don't want engineering detail in my inbox."* (Fits a milestone-briefed executive who owns the vision, not the diffs.)

- **Under `--non-interactive`:** honor an explicit `--posture <precision|default|substrate-free>` flag on `$ARGUMENTS` if supplied. If no prior key exists AND no `--posture` flag is supplied: **fail-loud** — the gate is mandatory and has no safe default. Status: `engagement_posture: failed (no prior value and no --posture flag under --non-interactive — re-run with --posture <precision|default|substrate-free>)`. Stop this step (does not need to halt the whole phase — see Step 3b-5 for the check-only/failure-tolerant framing).

**Step 3b-3 — Cross-check against a per-repo `coordinator.local.md` override, if one exists.**

If the current repo has a `coordinator.local.md` (§ "coordinator.local.md" below; this step runs from whatever repo the installer was invoked in, which may or may not be one), read any per-repo posture override via the shared resolver:

```bash
source "${CLAUDE_PLUGIN_ROOT}/lib/coordinator-resolve-validation-cmd.sh"
_repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
_repo_posture="$(cs_read_local_md_key "$_repo_root" "engagement_posture")"
```

- **`_repo_posture` empty** → no per-repo override; the identity-file value (from Step 3b-1 or freshly captured in Step 3b-2) is authoritative. Proceed.
- **`_repo_posture` set and matches the identity-file value** → consistent; proceed, no note needed.
- **`_repo_posture` set and DIFFERS from the identity-file value** → **detect-then-fail-loud** (never silent-pick between the two). Status: `engagement_posture: conflict (identity.yaml=<value>, coordinator.local.md=<value>) — reconcile manually, then re-run`. Surface the conflict to the operator with both values named and stop this step; do not write the overlay in Step 3b-5 while the conflict is unresolved.

**Step 3b-4 — Write identity file (skip under `--check-only`; emit `engagement_posture: would write`).**

Extend the same atomic write used for operator identity — write `engagement_posture` into the same document, same mktemp+mv pattern (do not do a second separate write; fold this key into the Step 3 write above when both are being captured in the same run):

```bash
_tmp="$(mktemp ~/.claude/coordinator-identity.yaml.XXXXXX)"
cat > "$_tmp" <<EOF
# ~/.claude/coordinator-identity.yaml — operator-local, NEVER a publish target
version: 1
operator_name: ${OPERATOR_NAME}
engagement_posture: ${ENGAGEMENT_POSTURE}
EOF
mv "$_tmp" ~/.claude/coordinator-identity.yaml
```

Status row: `engagement_posture: ready (<value>)`.

**Step 3b-5 — Materialize the overlay pre-restart.** (Skip this step entirely if Step 3b-3 reported `engagement_posture: conflict` — do not write the overlay while the conflict is unresolved.) Invoke the C4 helper for the resolved posture — **for all three choices, including `default`** (the overlay call is unconditional; `default` is not treated as a no-op skip, since the helper owns whether `default` produces an overlay body or a minimal marker):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/render-posture-overlay.sh" "${ENGAGEMENT_POSTURE}" "$HOME/.claude/CLAUDE.md"
```

- **Under `--check-only`:** append `--check-only`, i.e. `bash "${CLAUDE_PLUGIN_ROOT}/bin/render-posture-overlay.sh" "${ENGAGEMENT_POSTURE}" "$HOME/.claude/CLAUDE.md" --check-only`. This emits intent only — writes nothing to `~/.claude/CLAUDE.md`. Status: `engagement_posture_overlay: would write (<value>)`.
- **Otherwise:** run the helper without `--check-only`; it writes the overlay into `~/.claude/CLAUDE.md` before the terminal restart prompt (§ Phase 7 "Next step"). On non-zero exit: fail-loud with the helper's stderr — do not silently skip the overlay and let the operator restart into a stale doctrine surface. Status: `engagement_posture_overlay: written (<value>)`.

**Step 4 — Discover working repos.** Three-tier discovery (stop at first non-empty):

```bash
WORKING_REPOS=$(bash "${CLAUDE_PLUGIN_ROOT}/lib/discover-working-repos.sh")
```

Helper runs Tier A (`~/.claude/projects/` activity record, `X--Foo` → `X:\Foo`) then Tier B (`~/dev`, `~/Projects`, `/x`, etc.). Filters meta-repo, `AppData/Local/Temp`, bare drive roots. Returns up to 20 (A) or 30 (B) candidates.

**Tier C — Ask the operator** (if helper returned empty). <!-- D4: default-with-warning --> Under `--non-interactive`: skip; set placeholder; status `working_repos: defaulted to empty`. Under interactive: ask for a code folder via `AskUserQuestion`; re-probe Tier B inside it; if still empty, record the folder with a "no repos yet" note.

**Build `WORKING_REPOS` block.** Markdown list: `` - `<path>` — <one-line from README> ``. Tier A annotates top 3 `(active recently)`. Persist at `~/.claude/working-repos.yaml` (atomic mv). Status: `working_repos: ready (N from tier {A|B|C})`. Under `--check-only`, run Tiers A+B read-only, skip YAML write and Tier C prompt.

**Step 4b — Register discovered repos into `repos.*` (F16).** The manifest above is onboarding-only; cross-repo addressing (`cross-repo-memo --list-receivers`, sibling-path resolution) reads the machine-local `repos.*` registry instead, so bridge discovery into it:

```bash
_rd_flags=""
[[ "${ARGUMENTS:-}" == *"--non-interactive"* ]] && _rd_flags="$_rd_flags --non-interactive"
[[ "${ARGUMENTS:-}" == *"--check-only"* ]] && _rd_flags="$_rd_flags --check-only"
bash "${CLAUDE_PLUGIN_ROOT}/lib/register-discovered-repos.sh" $_rd_flags
```

Only-if-absent (never overwrites an existing `repos.<key>` value) and tier-gated (registers only what `discover-working-repos.sh` already qualified above — never a blanket scan). Status: `repos_registry: seeded (N registered)` / `repos_registry: would seed (N)` under `--check-only` / `repos_registry: none needed (all present)` when nothing to register.

**Step 5 — Render `~/.claude/CLAUDE.local.md`.** Under `--check-only`: emit `meta_repo_doctrine: would write` / `ready` and skip. Otherwise:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/render-template.sh" \
  "$_cc_root/templates/CLAUDE.local.md.tmpl" \
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

**Step 3e — `claude` CLI on PATH (cross-platform, idempotent).** The helper also ensures the standalone `claude` binary's dir (native-installer convention: `~/.local/bin`) is on the user's shell PATH — a sentinel-guarded block in the login rc on macOS/Linux, the user PATH via PowerShell on Windows. This closes the most common desktop-app onboarding failure: installing plugins inside the Claude Code desktop app, then opening a terminal and finding `claude` is not a recognized command (the CLI dir was never on the shell PATH). If no CLI binary is found at the standard location, the helper emits a note pointing at the CLI install docs rather than guessing a path. Status row: `claude_on_path: ready (<dir>) | added (<dir> → <rc>) | not found (install CLI)`.

### Step 1b — Run the install-health orchestrator (drop-in scripts; each self-gates)

```bash
# Propagate check-only to drop-ins via inherited env: under --check-only a drop-in
# that would mutate (e.g. seed-skill-overrides.sh writing settings.json) must instead
# report would-do and write nothing. Drop-ins read $CHECK_ONLY and self-suppress.
if [[ "$ARGUMENTS" == *"--check-only"* ]]; then export CHECK_ONLY=1; else export CHECK_ONLY=; fi
# Review: code-reviewer F3 — replaced A && B || C anti-pattern; if the middle command
# ever fails, C (export CHECK_ONLY=) fires despite A being true, clearing CHECK_ONLY.
bash "${CLAUDE_PLUGIN_ROOT}/bin/install-health-run.sh"
```

The orchestrator iterates `bin/install-health/*.sh` in lexicographic order, runs each in an isolated `bash` subprocess, and aggregates the failure count — it exits non-zero if any script failed, and stderr names each failing script with its exit code (it does NOT abort on the first failure — partial install completeness beats total bail). Each script self-gates on OS / preconditions and exits 0 silently when not applicable, so a clean run is silent. **Adding a new install-completion script is a directory drop into `bin/install-health/` — no edit to this command is required.** Scripts must be OS-self-gating, idempotent, and resolve libs via `CLAUDE_PLUGIN_ROOT`. **`CHECK_ONLY` is exported here (from `--check-only`) and inherited by every drop-in subprocess — a drop-in that mutates MUST honor it (report would-do, write nothing) to preserve the check-only no-mutation contract (:58, :127).**

### Step 2 — Never overwrite live registry files

If `~/.claude/machine-local/registry.toml` or `registry.local.toml` exists, leave untouched regardless of `.example` updates. Same for any `<concern>.toml` / `<concern>.local.toml`.

### Step 3 — Optional seed prompt (declinable, interactive only)

<!-- D4 annotation (seed prompt): skip-with-note — seed is elective; --non-interactive skips it and notes that the operator should copy .example → real by hand. -->

Full interactive script (prompt text, On Y write procedure, `machine-local set` invocations, On N): `docs/wiki/setup-reference-detail.md` § Phase 3 Step 3.

**Skip entirely** if either registry file already exists (idempotency). Under `--non-interactive`: emit `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`. Under interactive: offer Y/n to seed the four standard `repos.*` keys via `machine-local set` (never hand-edit). After the `repos.*` seeds, also seed `coordinator.machine_slug` and `coordinator.contributor_slug` (both absent-only, idempotent) from `cs_compute_machine_live` and `cs_compute_contributor_live` respectively (hostname-derived / sanitized git `user.email`-derived; never from a transient env override — see `setup-reference-detail.md § Phase 3 Step 3` for the exact commands). **On N:** leave both absent.

<!-- Review: chunk-1 Finding 7 — restored "Test surface" block removed in spec trim; inline spec is more immediately accessible than linked doc for test authors. -->
**Test surface** (expected; do not actually run setup): Fresh install → directory, all tracked files, all 7 bin/ artifacts present; seed prompt fires. Re-run → no overwrites, no prompts. `--non-interactive` → substrate laid, no seed prompt, no registry files. Operator-modified file → preserved with notice.

**See:** `docs/wiki/machine-local-registry.md`, `coordinator/lib/install-substrate.sh`, `coordinator/lib/claude-home/README.md`, `docs/wiki/coordinator-doctor.md`.

---

### Step 3.5 — Clone DoE repo and wire maximalist launch surface (idempotent)

<!-- spec-backlink: docs/plans/2026-07-04-doe-maximalist-execution-plugin-dir.md § W4.1 -->
<!-- spec-backlink: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md (portable forward install-surface) -->
<!-- Mechanism record: coordinator/docs/wiki/external-plugin-live-resolution.md § Hook-delivery -->

The maximalist coordinator shape delivers skills/agents live-external from the DoE clone via
`--plugin-dir`, and hooks via `settings.json` absolute-path commands generated from `hooks.json`.
This step seeds the required artifacts and wires the persistent launch surface. Prerequisite:
the `clone_auth` gate (Step Zero) passed — git auth is present.

**Maximalist install shape (portable forward install-surface).** The complete install consists of
three coordinated artifacts, all derived from the registry (`repos.doe_claude`) as single source
of truth:

**Canonical launch trinity.**

1. **`.doe-root` pointer** (`~/.claude/.doe-root`) — one-line cold-readable bootstrap cache
   projecting the DoE repo root; written atomically by `gen-doe-root-pointer.sh` (step 3.5a.1).
   Enables cold-terminal resolution with zero tool dependency. Also a new precedence tier in
   `resolve-coordinator-clone.sh` — the ecosystem seam for peer repos.
2. **`claude-doe` wrapper** (`~/.local/bin/claude-doe`) — the underlying launch command;
   regenerates the settings.json hook block and execs `claude --plugin-dir <doe_clone>/coordinator`
   on every invocation (step 3.5b).
3. **`claude()` shell shim** (`~/.claude/shell/claude-doe-shim.sh` + one marked `source` line in
   the interactive rc) — shadows bare `claude` with `claude-doe`; written by `gen-claude-doe-shim.sh`
   (step 3.5a.2). Resolves the DoE root via the `.doe-root` pointer — no machine-local on cold PATH.

**Supersedes sandbox-only W4.1 `~/.claude`-canonical assumptions.** The W4.1 plan was authored and
validated in a `CLAUDE_HOME` sandbox where `~/.claude`-canonical paths sufficed. The forward
maximalist install ships the pointer + shim + resolver-pointer-tier so it is reproducible on any
machine including cold terminals where coordinator `bin/` dirs are not on PATH. The `.doe-root`
pointer is the cold-readable bootstrap artifact that breaks the chicken-and-egg: `machine-local`
(the registry reader) lives in the DoE clone, so it cannot be the resolver that *finds* the DoE
clone from a cold shell.

**3.5a — Clone the DoE repo (idempotent).**

Resolve the clone path from the registry (seeded in Step 3 above, or pre-populated via
`REPO_DOE_CLAUDE` env var). Under `--check-only`, report state without mutating. Under
`--non-interactive`, the registry must be pre-seeded (`machine-local set repos.doe_claude <path>`)
or `REPO_DOE_CLAUDE` must be set — fail-loud if neither resolves.

```bash
DOE_CLONE="${REPO_DOE_CLAUDE:-}"
if [[ -z "$DOE_CLONE" ]] && command -v machine-local >/dev/null 2>&1; then
  DOE_CLONE="$(machine-local get repos.doe_claude 2>/dev/null || true)"
fi
```

If `DOE_CLONE` is still empty after the above resolution:
- **`--check-only`:** emit `doe_clone: skipped (repos.doe_claude not set)`.
- **Interactive:** ask the operator for the DoE repo URL and target path via `AskUserQuestion`;
  then `machine-local set repos.doe_claude <path>` and set `DOE_CLONE`.
- **`--non-interactive`:** fail-loud — `doe_clone: failed (repos.doe_claude not set — pre-seed
  the registry or set REPO_DOE_CLAUDE before running --non-interactive install)`.

Clone when the target directory is absent (idempotent — no-op if `.git` already present):

```bash
if [[ -n "$DOE_CLONE" ]] && [[ ! -d "$DOE_CLONE/.git" ]]; then
  # clone_auth gate (Step Zero) already validated; clone using the registry-resolved URL
  # or a well-known URL if the operator provided the path only (ask for URL if needed).
  DOE_REPO_URL="<operator-supplied or coordinated from repos.doe_claude_url registry key>"
  git clone "$DOE_REPO_URL" "$DOE_CLONE"
fi
```

Status rows:
- `doe_clone: ready (<path>)` — already present (`.git` exists)
- `doe_clone: cloned (<path>)` — cloned this run
- `doe_clone: would clone (<path>)` — check-only
- `doe_clone: skipped (repos.doe_claude not set)` — registry miss in check-only
- `doe_clone: failed (<reason>)` — clone error or non-interactive registry miss

Add a `DoE clone` row to the Phase 7 status table.

**P0 fail-loud guard — maximalist path requires `repos.doe_claude`.**

After the interactive prompt / non-interactive check above, verify `DOE_CLONE` is resolved before
the pointer and shim steps. The non-interactive branch already fails loud; this guard catches any
remaining empty-state on the interactive path (e.g. operator skipped the prompt without providing
a value):

```bash
if [[ -z "${DOE_CLONE:-}" ]] && [[ "${ARGUMENTS:-}" != *"--check-only"* ]]; then
  echo "ERROR: repos.doe_claude is unset — cannot proceed with maximalist install." >&2
  echo "  Pre-seed the registry: machine-local set repos.doe_claude <path>" >&2
  echo "  Or set REPO_DOE_CLAUDE=<path> before running." >&2
  exit 1
fi
```

**3.5a.1 — Write `.doe-root` pointer (idempotent).**

<!-- Lesson: state/lessons/2026-07-04-maximalist-launch-shim-needs-a-registry.yaml (cold-PATH / registry-projection) -->
<!-- Lesson: state/lessons/2026-07-04-path-independent-resolution-sibling-path.yaml (path-independent resolution) -->
<!-- Lesson: state/lessons/2026-07-04-a-dry-run-preview-that-regenerates-confi.yaml (dry-run must not mutate live config) -->

Project the DoE repo root from the registry into `~/.claude/.doe-root` — a cold-readable,
one-line bootstrap cache. The `claude()` shim (step 3.5a.2) and the pointer tier in
`resolve-coordinator-clone.sh` read this file with a bare `cat`, requiring zero tool dependency
in a cold terminal. Written atomically by `gen-doe-root-pointer.sh`. Idempotent — no-op when
content is unchanged. Under `--check-only`, generates to a temp path and discards (the live
`~/.claude/.doe-root` is byte-unchanged after any check-only run — dry-run-safety lesson).
Honors `CLAUDE_HOME` for sandbox isolation.

**Dual-seed with `plugin.mirrors.coordinator-claude.source_path`.** The same step that writes
`.doe-root` also seeds the machine-local registry key `plugin.mirrors.coordinator-claude.source_path`
from the identical resolved `$DOE_CLONE` value — the two keys must be written together so they
never drift apart (source_path re-derivation elsewhere assumes `.doe-root` and this registry key
name the same repo root; see step D3b).

```bash
_gen_pointer="${CLAUDE_PLUGIN_ROOT}/bin/gen-doe-root-pointer.sh"
if [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
  # check-only: validate (generate to temp, discard) — live file is NOT written
  if bash "$_gen_pointer" --check-only; then
    echo "doe_root_pointer: would write (${CLAUDE_HOME:-$HOME}/.claude/.doe-root)"
  else
    echo "doe_root_pointer: failed in check-only validation (see stderr)"
  fi
elif [[ -n "${DOE_CLONE:-}" ]]; then
  if bash "$_gen_pointer"; then
    echo "doe_root_pointer: written (${CLAUDE_HOME:-$HOME}/.claude/.doe-root)"
    # Seed the mirrored registry key from the same resolved DOE_CLONE value — absent-only,
    # idempotent, consistent with the surrounding Phase-3 seeding style.
    if command -v machine-local >/dev/null 2>&1; then
      if [[ -z "$(machine-local get plugin.mirrors.coordinator-claude.source_path 2>/dev/null || true)" ]]; then
        machine-local set plugin.mirrors.coordinator-claude.source_path "$DOE_CLONE"
        echo "plugin_mirror_source_path: written (${DOE_CLONE})"
      else
        echo "plugin_mirror_source_path: ready (no-op)"
      fi
    else
      echo "plugin_mirror_source_path: skipped (machine-local not found)"
    fi
  else
    echo "doe_root_pointer: failed (see stderr for gen-doe-root-pointer.sh output)" >&2
    echo "gen-doe-root-pointer.sh exited non-zero" >&2
  fi
else
  echo "doe_root_pointer: skipped (DoE clone not resolved — complete step 3.5a first)"
fi
```

Status rows: `doe_root_pointer: written | ready (no-op) | would write (check-only) | skipped (clone absent) | failed`.
Status rows: `plugin_mirror_source_path: written | ready (no-op) | skipped (machine-local not found)`.

Add a `.doe-root pointer` row to the Phase 7 status table.

**3.5a.2 — Install `claude()` shim (idempotent).**

Write the `claude()` shell function into `~/.claude/shell/claude-doe-shim.sh` and ensure exactly
one marked `source` line in the operator's interactive rc (`~/.zshrc` for zsh, `~/.bashrc` for
bash, `$SHELL`-detected; override with `COORDINATOR_SHIM_RC=<path>` or `--rc <path>` for
divergent login-vs-interactive shell cases). The shim reads `~/.claude/.doe-root` and delegates
to `claude-doe` — no machine-local on cold PATH, no hardcoded machine-specific path.

Generated by `gen-claude-doe-shim.sh`. Sentinel-guarded idempotency — does NOT silently overwrite
a hand-modified marked region. Detects the legacy hand-bolted `~/.bashrc` stopgap (`# --- coordinator
maximalist launch ---` block) and surfaces a one-line migration note rather than silently
rewriting it. Under `--check-only`, generates to a temp path and discards — the live shim file
and rc are byte-unchanged (dry-run-safety lesson).

**Distinction from step 3.5b:** the `claude-doe` wrapper (step 3.5b) is the exec target and the
underlying persistent launch command; the `claude()` shim is a thin shadow that lets the operator
type bare `claude` without manual env-setting. Both are required; both are idempotent.

**Note:** this step depends on the `.doe-root` pointer from step 3.5a.1 — run 3.5a.1 first.

```bash
_gen_shim="${CLAUDE_PLUGIN_ROOT}/bin/gen-claude-doe-shim.sh"
if [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
  # check-only: validate (generate to temp, discard) — live shim and rc are NOT written
  if bash "$_gen_shim" --check-only; then
    echo "claude_shim: would install (${CLAUDE_HOME:-$HOME}/.claude/shell/claude-doe-shim.sh)"
  else
    echo "claude_shim: failed in check-only validation (see stderr)"
  fi
elif [[ -n "${DOE_CLONE:-}" ]]; then
  if bash "$_gen_shim"; then
    echo "claude_shim: installed (${CLAUDE_HOME:-$HOME}/.claude/shell/claude-doe-shim.sh)"
  else
    echo "claude_shim: failed (see stderr for gen-claude-doe-shim.sh output)" >&2
    echo "gen-claude-doe-shim.sh exited non-zero" >&2
  fi
else
  echo "claude_shim: skipped (DoE clone not resolved — complete step 3.5a first)"
fi
```

Status rows: `claude_shim: installed | ready (no-op) | would install (check-only) | skipped (clone absent) | failed`.

Add a `claude() shim` row to the Phase 7 status table.

**3.5b — Install the `claude-doe` wrapper onto PATH (idempotent).**

The wrapper (`bin/claude-doe` in the coordinator tree) is the persistent launch surface — it
regenerates the settings.json hook block and execs `claude --plugin-dir <doe_clone>/coordinator`
on every invocation. Install it to `~/.local/bin/` (the native-installer standard directory,
already on PATH after Step 3e). If `~/.local/bin` is not on PATH, emit an advisory remediation
note (not a hard fail).

```bash
_wrapper_src="${CLAUDE_PLUGIN_ROOT}/bin/claude-doe"
_wrapper_dst="${CLAUDE_HOME:-$HOME}/.local/bin/claude-doe"
_local_bin="$(dirname "$_wrapper_dst")"

if [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
  if [ -f "$_wrapper_dst" ]; then
    echo "claude_doe_wrapper: ready ($_wrapper_dst)"
  else
    echo "claude_doe_wrapper: would install ($_wrapper_dst)"
  fi
else
  mkdir -p "$_local_bin"
  cp -p "$_wrapper_src" "$_wrapper_dst"
  chmod +x "$_wrapper_dst"
  echo "claude_doe_wrapper: installed ($_wrapper_dst)"
  if ! printf ':%s:' "${PATH}" | grep -qF ":${_local_bin}:"; then
    echo "  NOTE: ${_local_bin} is not yet on PATH — add to login rc for new terminals:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\"  # e.g. append to ~/.zprofile"
  fi
fi
```

Status rows: `claude_doe_wrapper: ready | installed | would install | failed (<reason>)`.

Add a `claude-doe wrapper` row to the Phase 7 status table.

**3.5c — Seed settings.json hook block (idempotent).**

Run `gen-settings-hooks.sh` to write the generated hook block into `settings.json`. This wires
all `type: command` entries from `hooks.json` (skipping `mcp_tool` entries — in-process ops, not
settings.json rails) with baked registry-absolute paths into the DoE clone. The generator is
idempotent — re-running over an already-seeded `settings.json` produces a no-op diff. It honours
`CLAUDE_HOME` for sandbox isolation. Skip under `--check-only` (emit a note).

**Note on boot semantics (per `install-surface-completeness.md § Running-in-Claude-Code`):**
`settings.json` hook definitions hot-reload mid-session, but a **SessionStart hook** fires only at
boot — an already-running session will not fire newly-seeded SessionStart hooks. Inform the
operator to restart Claude Code once for the seeded hooks to take effect. **Do NOT imply
SessionStart hooks fire mid-session** — that is a false claim that has misled installers before.

```bash
_gen_hooks="${CLAUDE_PLUGIN_ROOT}/bin/gen-settings-hooks.sh"
if [[ "${ARGUMENTS:-}" == *"--check-only"* ]]; then
  echo "settings_hooks_seed: skipped (check-only — would run gen-settings-hooks.sh)"
elif [[ -n "${DOE_CLONE:-}" ]] && [[ -d "$DOE_CLONE" ]]; then
  if bash "$_gen_hooks"; then
    echo "settings_hooks_seed: seeded"
    echo "  NOTE: SessionStart hooks take effect at next Claude Code boot (settings.json"
    echo "  hot-reloads hook definitions, but SessionStart fires only at session start)."
  else
    # Review: code-reviewer F6 — status row must go to stdout so the Phase 7 table captures it;
    # diagnostic detail goes to stderr. Pattern matches all other install.md status rows.
    echo "settings_hooks_seed: failed (see stderr for gen-settings-hooks.sh output)"
    echo "settings_hooks_seed: gen-settings-hooks.sh exited non-zero" >&2
  fi
else
  echo "settings_hooks_seed: skipped (DoE clone not resolved — complete step 3.5a first)"
fi
```

Status rows: `settings_hooks_seed: seeded | skipped (check-only) | skipped (clone absent) | failed`.

Add a `Settings hooks seed` row to the Phase 7 status table.

**3.5d — Thin `~/.claude/plugins/` shape (design note — no mutation).**

Under the maximalist shape, `~/.claude/plugins/` holds pointer/config entries and harness-native
`bin/` artifacts — **it does NOT hold plugin source bytes**. The coordinator plugin source lives
in the DoE clone, resolved live via `--plugin-dir <doe_clone>/coordinator` on each `claude-doe`
invocation. No byte-copy to `~/.claude/plugins/coordinator-claude/` is performed or expected.

- **Anti-pattern:** byte-copying plugin source to `~/.claude/plugins/coordinator-claude/` is the
  failed directory-marketplace shape (runtime-proven FAIL; recorded in
  `coordinator/docs/wiki/external-plugin-live-resolution.md § Disposition`). Do NOT do this.
- **Harness-native artifacts** (`machine-local`, `claude-home`, platform-localize) stay in
  `~/.claude/bin/` — these are machine-scope resolvers, not plugin source.
- **Hook delivery** is via the `settings.json` command-hook block seeded in step 3.5c above.
  `settings.local.json` hooks do NOT fire (runtime-proven — see `external-plugin-live-resolution.md`).

This shape assertion is automatically satisfied by running steps 3.5a–3.5c without any byte-copy.
The install-singularity gate (Step 7.5) and doctor probe P-18 verify the canonical single-tree
shape on cadence.

**Sandbox clean-install test harness (see `bin/install-sandbox-check.sh`).**

The full clean-install shape — thin `~/.claude` + cloned DoE + wired wrapper — is validated by:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/install-sandbox-check.sh"
```

The harness creates an isolated sandbox (`CLAUDE_HOME` override), exercises steps 3.5a–3.5c
against it, and asserts the resulting shape. Validation runs in two tiers:

1. **Filesystem tier (automated):** thin-`~/.claude` shape, cloned-DoE dir present, wrapper
   installed, settings.json hook block seeded, no plugin-source byte-copy. This tier runs
   fully inside the harness.

2. **Running-in-Claude-Code tier (deferred — hardware/editor-gated):** that skills/agents resolve
   live from the DoE clone path via `--plugin-dir`, that hooks fire at boot from DoE-clone-absolute
   paths, and that `CLAUDE_PLUGIN_ROOT` is unset (self-resolution via `BASH_SOURCE`). Per
   `docs/wiki/install-surface-completeness.md § Running-in-Claude-Code`, this tier requires a real
   Claude Code boot against the sandbox — it CANNOT run inside a subagent. **The EM or PM must
   execute `claude-doe --dry-run` and then launch `claude --plugin-dir <sandbox>/coordinator`
   interactively to complete this tier before declaring the install surface complete.**

---

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

<!-- spec-backlink: archive/specs/2026-05/2026-05-21-whoami-first-class-substrate.md § Chunk 1 / AC-1, AC-2, AC-3, AC-15 — superseded for Step 6 by the 2026-06-20 plan below; these ACs no longer address the Step 6 implementation shape. -->
<!-- spec-backlink: docs/plans/2026-06-20-whoami-durable-install-surface.md (durable venv install surface) -->
<!-- D4: default-with-warning — no prompt site; install fires mechanically under --non-interactive same as interactive. -->

**Sequencing note:** Step 6 MUST run after Phase 3 Step 1 (the `install-substrate.sh` run that places the `machine-local` CLI on PATH). The ensure script writes the venv python pin via `machine-local set coordinator.python`; if the CLI is absent it degrades gracefully (venv is still built and usable via `COORDINATOR_PYTHON`), but proper ordering is required.

Delegate all venv creation, `coordinator_whoami` installation, and registry pinning to `ensure-coordinator-venv.sh`. The script is idempotent, mutex-protected, and resolves the system Python at runtime — no binding to a specific interpreter version, no PEP-668 bare-pip conflict.

```bash
# Normal mode — create/validate venv, install package, pin registry
bash "${CLAUDE_PLUGIN_ROOT}/bin/ensure-coordinator-venv.sh"

# Check-only mode — report without mutating
bash "${CLAUDE_PLUGIN_ROOT}/bin/ensure-coordinator-venv.sh" --check
```

Under `--check-only`, invoke with `--check`. Under normal install, invoke without flags.

Map the script's stdout to the Phase 7 status row:

| Script output | Phase 7 status |
|---|---|
| `ready` | `coordinator_whoami: ready` |
| `ready` (check mode, venv healthy) | `coordinator_whoami: ready` |
| `rebuilt` | `coordinator_whoami: rebuilt` |
| `would write` (check mode, venv absent or broken) | `coordinator_whoami: would write` |
| non-zero exit | `coordinator_whoami: failed (<first line of stderr>)` — do NOT halt chain |
<!-- Review: code-reviewer F1 — collapsed the prior would-write/would-rebuild split into a single `would write` token per the pinned contract; added check-mode-healthy `ready` row per F3. -->

On non-zero exit: log the script's stderr for diagnostics; do NOT halt the install chain (same non-halting contract as prior Steps). Post-install probe P-5 in `docs/wiki/coordinator-doctor.md`.

Add row to Phase 7 table.

---

### Step 7 — Scaffold canonical document structure (idempotent)

<!-- spec-backlink: archive/specs/2026-05/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 6 -->
<!-- the Director of Engineering F5: pass --root explicitly so the scaffold targets the coordinator install root, not whatever cwd is at invocation time. -->

Scaffold (eager entries from `canonical-structure.yaml`) into `~/.claude`, landing `cross-repo/` with its README. Skip mutations under `--check-only` (emit `canonical_structure: would scaffold`).

```bash
_scaffold_root="${CLAUDE_HOME:-$HOME}/.claude"
_scaffold_script="${CLAUDE_PLUGIN_ROOT}/bin/scaffold-canonical-structure.sh"
bash "$_scaffold_script" --root "$_scaffold_root"
```

Idempotent — skips existing dirs/READMEs, never clobbers. On success: `canonical_structure: ready`. On non-zero: `canonical_structure: failed` (log stderr; do NOT halt — advisory, not hard infrastructure).

Add a `Canonical structure` row to the Phase 7 status table.

---

### Step 7.5 — Install singularity gate (canonical-locus integrity)

Verify the coordinator setup resolves to a single canonical coordinator tree — the canonical-locus invariant. Two shapes are recognized:

- **Pre-cutover (`~/.claude` shape):** canonical tree = `~/.claude/plugins/coordinator-claude`. Catches the split-install failure mode where multiple coordinator trees register divergently across `settings.json` / `settings.local.json` / `known_marketplaces.json` and the loaded skill silently resolves to a stale copy (the 2026-06-26 three-tree failure).
- **Maximalist post-W4.2 shape:** canonical tree = DoE clone resolved via `plugin.mirrors.coordinator-claude.live_path` in `registry.local.toml` (delivered live via `--plugin-dir`; `~/.claude/plugins/coordinator-claude` is **absent**). The live_path is the sole reachable tree — `_tree_count` reaches 1 and the split-detection test passes naturally.

In both cases, exactly one distinct canonical tree is expected. A genuine stray second tree (e.g. a `~/coordinator-claude` clone, a stale worktree) is always an accidental split. Also catches a doubled `.claude/.claude` venv pin and a `.claude`-suffixed `CLAUDE_HOME`.

```bash
_singularity_check="${CLAUDE_PLUGIN_ROOT}/lib/check-install-singularity.sh"
bash "$_singularity_check"
```

A single explicitly-exported `COORDINATOR_CLONE` / `COORDINATOR_ROOT` dev-loop override (`.git`-backed clone) is exempt — exits 0 with an INFO line. A non-zero exit means an **accidental** split (a genuine stray second tree): print the remediation, add an `Install singularity` row to the Phase 7 status table marked `failed`, and surface to the operator. On exit 0, the INFO line names the resolved canonical tree path (e.g. the DoE clone path under the maximalist shape). This is the install-time twin of doctor probe **P-18** (`coordinator-doctor.md` §3), which re-checks the same invariant on cadence.

Add an `Install singularity` row to the Phase 7 status table.

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
if [[ -n "${CHECK_ONLY:-}" ]]; then
  # check-only: report whether the file would change, do not write
  # Review: code-reviewer F6 — standardize on -n form; "== 1" would miss CHECK_ONLY=true
  # and any other non-empty value; drop-ins already use -n "${CHECK_ONLY:-}".
  echo "platform-localize: skipped (check-only mode)"
else
  bash "$HOME/.claude/bin/platform-localize.sh"
  # Confirm the output is schema-valid before continuing — but only when there's
  # something to validate. Under the maximalist live-resolution shape, plugins are
  # resolved live via --plugin-dir and never byte-copied under ~/.claude/plugins/,
  # so platform-localize.sh has nothing to localize there and legitimately writes
  # no known_marketplaces.json (F9). Its absence is a correct outcome, not a failure —
  # do not read a skipped validation block as a broken install.
  if [[ -f .github/scripts/validate-json-schemas.py ]] && [[ -f "$HOME/.claude/plugins/known_marketplaces.json" ]]; then
    # python3-first resolver — `python` is absent on modern macOS / many Linux.
    PY="$(command -v python3 || command -v python)"; [ -n "$PY" ] || { echo "no python3/python on PATH" >&2; exit 1; }
    "$PY" .github/scripts/validate-json-schemas.py 2>&1 | grep -E '(known_marketplaces|passed)' | head -3
  elif [[ ! -d "$HOME/.claude/plugins" ]] || [[ -z "$(ls -A "$HOME/.claude/plugins" 2>/dev/null)" ]]; then
    echo "known_marketplaces.json: not present — expected under maximalist live-resolution (no local plugin dirs under ~/.claude/plugins/); not a failure"
  fi
fi
```

Idempotent. Adds row to Phase 7 status: `platform_localize: ran` / `skipped (check-only)` / `error (see stderr)`. Under maximalist, that row may read `platform_localize: ran (known_marketplaces.json not applicable — no local plugin dirs)` — this is expected, not an error (F9).

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

<!-- spec-backlink: archive/specs/2026-05/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1 -->
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

Under `--check-only`: apply **Keep defaults**, status `persona_customization: skipped (check-only)`.

Under `--non-interactive` (not `--check-only`): apply **Keep defaults**, status `persona_customization: skipped (non-interactive default: keep defaults)`.
<!-- Review: code-reviewer — split token so --check-only vs --non-interactive are distinguishable in output -->

Under interactive:

> The coordinator includes named reviewer personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering). Customize their names? **Keep defaults** / **Customize** — Choosing **Customize** renames the reviewer agents across the install (the EM runs `name-personas.sh` for you) and is reversible by re-running this install step.

If customize: run `name-personas.sh` — it handles the rename across agent files and prompts/skills. Or take the guided tour (Phase 7) where the EM walks you through it. Either way, exclude `bin/publish-time-transform.sh` from search-replace (it carries the canonical `NAME_TO_ROLE` table and must not be altered).

### Codex Integration (optional opt-in)

<!-- D4: opt-in — default declined; only --check-only reports state. -->
<!-- Spec backlink: archive/specs/2026-06/2026-06-14-codex-reviewer-integration-opt-in.md -->
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

### GitHub Auth via 1Password (optional opt-in)

<!-- D4: opt-in — default declined; no-ops cleanly on machines without 1Password. -->
<!-- Doctrine: docs/wiki/github-auth-setup.md (Tier-1 interactive recipe). -->

Optionally wire GitHub auth + SSH commit signing through the **1Password SSH agent** on this
(interactive) machine — the Tier-1 standard in `docs/wiki/github-auth-setup.md`. This is fully
opt-in: it **no-ops with a clean exit** on machines without 1Password, so coordinator users who
don't use 1Password can decline or ignore it. Headless machines keep token HTTPS
(`gh auth setup-git`) — do not run this there.

Under `--non-interactive`: skip silently. Status row: `github_auth_1password: skipped (non-interactive)`.

Under `--check-only`: run the helper in report mode (no mutation) and read its final
machine-readable line, `STATUS: github_auth_1password=<token>`:

```bash
bash scripts/setup-github-auth-1password.sh --check | sed -n 's/^STATUS: github_auth_1password=//p'
```

Map the token to the status row: `present` → `present`; `absent` → `absent (would offer)`
(1Password detected but not yet wired); `n-a-no-1password` → `n/a (no 1Password)`.

Under interactive:

> Set up GitHub auth + commit signing via 1Password (SSH agent over port 443, `op-ssh-sign`
> signing)? Recommended for interactive dev machines; offers to install the `op` CLI if absent.
> Skip if you don't use 1Password — headless machines should use `gh auth setup-git` instead. **[y/N]**

**On NO:** status row `github_auth_1password: declined`.

**On YES:** run the consent-gated, idempotent helper (it offers each change individually):

```bash
bash scripts/setup-github-auth-1password.sh
```

The helper detects 1Password, optionally installs the `op` CLI, routes `github.com` over
`ssh.github.com:443`, configures global SSH commit signing, and offers to flip the current repo's
`origin` to SSH. It backs up `~/.ssh/config` before editing and verifies `git ls-remote` before
keeping a remote change. Read its final `STATUS: github_auth_1password=<token>` line for the row:
`configured` → `configured`; `incomplete` → `declined` (1Password present but the operator declined
one or more offers); `n-a-no-1password` → `n/a (no 1Password — skipped)`.

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

**Phase 7 status table — github_auth_1password row.** Driven from the Phase 6 GitHub Auth via 1Password step's outcome. Value-set: `configured` | `present` | `declined` | `absent (would offer)` | `n/a (no 1Password)` | `n/a (no 1Password — skipped)` | `skipped (non-interactive)`.

**Phase 7 status table — engagement_posture row.** Driven from Phase 2's Engagement posture capture step. Value-set: `ready (precision|default|substrate-free)` | `would write (precision|default|substrate-free)` (`--check-only`) | `failed (no prior value and no --posture flag under --non-interactive — re-run with --posture <precision|default|substrate-free>)` | `conflict (identity.yaml=<value>, coordinator.local.md=<value>) — reconcile manually, then re-run`. A companion `engagement_posture_overlay` row records the C4 helper's outcome: `written (<value>)` | `would write (<value>)` (`--check-only`) | `failed — <reason>`.

**Phase 7 status table — orientation row (F13(c)).** <!-- spec-backlink: tasks/2026-07-08-install-dogfood-friction.md § F13 --> Driven from `coordinator-setup-state.sh check orientation_completed`. Value-set: `PENDING` (default — `orientation_completed` is unset, the common post-restart-not-yet-run state; render this value visibly in the table body, not only in prose below it) | `completed` (the check exits 0) | `skipped (--check-only)`. This row is mandatory in every non-`--check-only` run — a skipped or not-yet-run orientation must never be silently absent from the table.

Present a summary table with one row per check above (including the `orientation` row immediately above). Full status-row value-sets and available-commands list: `docs/wiki/setup-reference-detail.md` § Phase 7.

### Plugin-bundled doctrine wikis

Plugin ships doctrine at `<plugin-install-path>/docs/wiki/`. If **required** items (git) are missing, note prominently. If recommended items (Agent Teams, CLAUDE.md import) are missing, list next steps.

**Hard-precondition rows.** Machine-local rows are non-optional: `FATAL` means Phase 3 halted (downstream skills won't function). `Registry seed` is informational only.

### Next step — guided onboarding (elective-when, not optional-whether)

<!-- F13 root-cause #3: "elective-when ≠ optional-whether" — this heading previously read bare
     "Optional next step," which buried the lede per F13's own critique. Skipping is still a
     legitimate in-the-moment choice; it is not a hard gate. But the operator should not read
     the heading as "skip freely, no cost" — see the terminal-message gate below for the
     enforcement half of this reframe. -->


<!-- spec-backlink: archive/specs/2026-05/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 4 / AC8 -->

Skip under `--check-only`. After the status table, record `orientation_started` and read `docs/wiki/getting-started.md` (plugin-relative) to facilitate the three movements (Orient → Make it yours → Test drive). The guide's `## For the EM facilitating this` section is your playbook; records `orientation_completed`.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/bin/coordinator-setup-state.sh" record orientation_started
```

**Refinement target close.** Include verbatim in every next-steps block (not under `--check-only`):

> Your `~/.claude` is the surface you evolve — git-track it and back it up; the coordinator
> plugin source lives in the DoE clone (`repos.doe_claude`), resolved live via `claude-doe`.
> Bare `claude` now works via the installed `claude()` shim (in `~/.claude/shell/claude-doe-shim.sh`,
> sourced from your interactive rc) — it reads `~/.claude/.doe-root` and delegates to `claude-doe`
> automatically. If the shim is not yet active in your current shell (e.g. first install before
> sourcing the rc), run `claude-doe` directly or open a new terminal. `claude-doe` is the
> underlying wrapper; the shim is the convenience shadow. Never copy plugin source into
> `~/.claude/plugins/` — that is the failed byte-copy shape.

Under interactive AND NOT `--check-only` (after the status table has been shown), check `~/.claude/working-repos.yaml` for the discovered repo count (N). If N > 0, note: *"Or, if you have a project ready: `/coordinator:repo-setup`."* **Suppressed under `--non-interactive` or `--check-only`.** Status row: `bootstrap_offer: offered (N repos)` / `suppressed (--non-interactive|--check-only)` / `skipped (0 repos discovered)`.
<!-- Review: code-reviewer — primary condition rephrased to "interactive AND NOT --check-only" so the contract is unambiguous in one clause -->

**Terminal-message gate (F13(b)/(d)).** <!-- spec-backlink: tasks/2026-07-08-install-dogfood-friction.md § F13 --> This closing message MUST NOT present unconditional success language while `orientation_completed` is unset — check the `orientation` status-table row above (or re-run `coordinator-setup-state.sh check orientation_completed`) before choosing which line to print:

- **While `orientation` is `PENDING`** (the common case immediately after a fresh install): foreground the outstanding step ahead of any success framing —

  *"Setup wired your environment. Next required step — restart Claude Code, then say 'walk me through the coordinator' to finish tailoring it to you."*

- **Once `orientation_completed` is recorded** (this session ran the guided tour, or a prior session already did): the plain success framing is correct —

  *"You're all set up — say 'walk me through the coordinator,' or tell me what you want to build."*

A driver (human or autonomous agent) reading the terminal output must not be able to come away believing the install is fully complete while orientation is outstanding.
