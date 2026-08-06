---
description: "Installs the coordinator plugin — checks prereqs, configures project."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive] [--accept-no-git-auth]"
---

# Coordinator Install

Environment and project setup for the coordinator plugin. This is a **guided install** — you participate in the shape decisions; the agent moves fast on mechanism. Safe to re-run — skips anything already configured.

## You are here — prerequisites before running this

**This document is written for the POST-INSTALL RE-RUN path, and this is load-bearing, not
a preference.** Every command fence below is a single-line call into a settings-home forwarder
(`${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/<cli>`) — those forwarders
are written by Phase 3 Step 1 of a PRIOR run. This doc's per-phase blocks assume they already
exist; it does not stand up the substrate that creates them. If the coordinator plugin is already
wired (`CLAUDE_PLUGIN_ROOT` resolves, `/coordinator:install` is invokable), that's you — skip to
Step Zero.

**COLD machine → run `python3 coordinator/scripts/install-maximalist.py`** (self-resolving,
forwarder-independent — it derives its own root from `Path(__file__)` and drives the full
14-phase sequence without needing any of the forwarders this doc assumes). Do NOT hand-transcribe
this doc's fences on a cold machine — they will fail with an unresolved forwarder path, not a
helpful error. See root `INSTALL.md` for the full cold-bootstrap walkthrough.

Cold-bootstrap and re-run converge on the same substrate — the distinction is only which
entrypoint owns resolving `CLAUDE_PLUGIN_ROOT`/`CLAUDE_KLABAUTER_ROOT` before commands can run (F3): the
maximalist script resolves it itself in Python; this doc assumes a prior run already resolved it
and left forwarders behind.

**Reversing this install:** see `coordinator/commands/uninstall.md` — the tested, first-class symmetric counterpart to this command. It reverses every out-of-repo surface this install writes (settings.json hook block, shell shim/wrapper, machine-local registry keys, whoami/venv, `.doe-root` pointer, `~/.claude/bin/` forwarders, plugin wiring), snapshot-independent. The surface list is kept in lockstep between the two commands — a new surface added here gets a matching removal step there in the same change.

## Step Zero — Functional preflight and env-normalization

Before any phase, run a functional gate to verify prerequisites and fix what can be fixed automatically.

### 1. Preflight gate

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/scripts/setup.py" --preflight
```

**Precondition — `repos.claude_klabauter` must already resolve.** This script (`coordinator/scripts/setup.py`, post-migration claude-klabauter-resident) imports `_resolve_claude_klabauter_root()` before it can run at all — if `claude-klabauter` isn't cloned, or `repos.claude_klabauter` isn't registered in the machine-local registry (env `CLAUDE_KLABAUTER_ROOT`/`REPO_CLAUDE_KLABAUTER` override also accepted), this command fails loud immediately, not partway through. See the `claude-klabauter` requirement in **## Requirements** above for the remediation command. This is a **hard prerequisite the coordinator install path itself does not write** — its authoritative writer is `claude-klabauter`'s own installer, never chained from here. (`first-run` can also seed it opportunistically, but it is interactive and opt-out — do not rely on it.)

`--preflight` is a **superset of `--check`**: it runs manifest-dependency probes AND environment-prerequisite probes through a single tabling + NDJSON emitter. Exit behavior is severity-aware:

| Probe | Severity | Exit behavior |
|---|---|---|
| `python` | **hard** | Non-zero exit — install MUST stop until resolved |
| `uv` | advisory WARN | Logged; install continues |
| `clone_auth` | **semi-hard** | Blocks unless resolved or `--accept-no-git-auth` (exit 94) |
| `longpaths` | advisory WARN | Logged; install continues (Windows-only) |
| `pwsh` | advisory WARN | Logged; install continues — see PowerShell 5.1 note below |
| `ue` | advisory WARN | Logged; install continues |

The probe library is `coordinator_core.install.prereq_probe` (native Python port; claude-klabauter) — a read-only SSOT that never mutates state. The gate reads from it; the fixer (below) writes. Any `inconclusive` probe result is surfaced explicitly and treated as advisory WARN (not a hard failure).

**`clone_auth` semi-hard gate — interactive offer and non-interactive contract.**

When the `clone_auth` probe fires (no GitHub auth found), the gate behavior depends on mode:

- **Interactive (default):** offer to run `gh auth login` now (or, if the operator is on GitLab, point to `glab auth login`). On accept, re-run the `clone_auth` probe — if it passes, proceed. On decline or failure, instruct the operator to either configure auth manually and re-run, or pass `--accept-no-git-auth` to skip the gate and continue without git auth.

  ```
  clone_auth probe: no GitHub auth found.
  Offer: run `gh auth login` to authenticate now? [Y/n]
    → Y: runs `gh auth login`; re-probes; proceeds on pass.
    → N: re-run with --accept-no-git-auth to skip this gate, or configure auth manually first.
  ```

- **`--non-interactive` with no auth and no `--accept-no-git-auth`:** FAIL-LOUD — no TTY to run the offer; exit non-zero with remediation message. This matches the manifest hard-dep non-TTY pattern (exit-90 spirit). Status: `clone_auth: failed (no auth — re-run with --accept-no-git-auth or configure auth first)`.

- **`--accept-no-git-auth` (any mode):** skip the gate; emit advisory `clone_auth: skipped (--accept-no-git-auth)` and continue. Private repos that require auth will fail at clone time, not here.

- **`--check-only`:** report `clone_auth: semi-hard (would block without --accept-no-git-auth)` — do NOT exit non-zero. Check-only never mutates or blocks; it only reports what *would* happen.

**PowerShell 5.1 fallback (#03).** The `pwsh` probe checks for PowerShell 7+ (`pwsh`). If `pwsh` is absent or below version 7, the probe WARNs but does not block — the coordinator falls back to the inbuilt Windows PowerShell 5.1 (`powershell.exe`) for `.ps1` scripts that require it. `pwsh` 7+ is preferred (cross-platform, fully supported); 5.1 is the fallback, not the target. See `1c.2` below.

### 2. Env-normalization

If the preflight reports fixable advisory WARNs, run the env-normalizer **dry-run first** to preview mutations without applying them, then apply on consent:

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/scripts/normalize-env" --dry-run
```

Preview only — no changes made. Once reviewed, apply all consented mutations:

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/scripts/normalize-env" --yes
```

`normalize-env` is idempotent and consent-gated: it enumerates each proposed mutation and requires explicit acceptance per mutation. Blast-radius-last ordering applies (higher-impact mutations are offered last). On Windows, every mutation creates a backup and `--restore` reverts to the pre-run state. On macOS the script is offers-only EXCEPT for the single consent-gated bash-login-shell reconstruction (see § Login-shell orphan detection below); on Linux it is offers-only (no Windows-specific mutations run).

Proceed to Phase 1 after Step Zero. Any hard failure from `--preflight` must be resolved before continuing.

---

## Requirements

Phase 1 checks each item and fails loud (or warns) per the D4 contract.

- **bash ≥ 4.3** (hard requirement). Scripts use `declare -A` (bash 4.0+) and `local -n` namerefs (4.3+). macOS ships bash 3.2 — install via `brew install bash` and put it first on PATH. Linux/WSL/Git Bash ship 4.3+ already.
- **git** — branch management, commits, handoffs, auto-push.
- **Python 3** — hooks and JSON manipulation.
- **jq** — required for JSON output in `/workday-start` addon-health.
- **uv** — only for Pipeline D (NotebookLM media research); provides `uvx` to launch the Python MCP server (see §1d).
- **scc** — optional; powers code statistics in session orientation.
- **PowerShell 7+ (`pwsh`)** — default-on, all platforms. Windows hidden-spawn / auto-push / `.ps1` scripts target it (falling back to the inbuilt Windows PowerShell 5.1); offered on macOS, Linux, and Windows. Not a hard blocker.
- **Windows Terminal** — default-on, Windows only. Modern console host paired with `pwsh` 7 (no legacy conhost flash on hidden-spawn paths).
- **`claude-klabauter` cloned AND `repos.claude_klabauter` registered in the machine-local registry** — hard requirement, both platforms. This is NOT auto-discovered: `claude-klabauter` is an engine repo with no `.claude-plugin/marketplace.json` marker, so the rung-2 marker-autodiscovery scanner can never resolve it. The Step Zero preflight below (`scripts/setup.py --preflight`) resolves `CLAUDE_KLABAUTER_ROOT` before it can do anything else and fails loud if unresolved. If you have not already run `claude-klabauter`'s own `python3 scripts/setup.py` (its `register_claude_klabauter_root()` step, the AUTHORITATIVE writer of this key) with coordinator-claude's `machine-local` CLI already on PATH, do so now, or register the path by hand: `machine-local set repos.claude_klabauter /path/to/claude-klabauter`. `claude-klabauter` is currently a private repo — until it is open-sourced, the maintainer grants access directly on request, the same distribution model already used for `project-rag`.

## Execution dial and structural fork

**Execution dial:** Default is **agent-led** — prompts only where genuine decisions are needed. Pass `--non-interactive` to suppress all `AskUserQuestion` calls; see the **D4 Non-Interactive Contract** below for per-site fallback.

**Structural fork — three states:** Before any phase, classify the Claude home:

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/detect-existing-claude-home.py"
```

Emits one line: `state=<pristine|used-vanilla|configured> track=<A|B> reason: …`. The trusted-root
resolution and traversal guarding this block used to carry inline now live in the forwarder itself
(the settings-home forwarder resolves and validates the claude-klabauter root before exec'ing the CLI —
see `coordinator/snippets/resolve-coordinator-bin.md`).

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

Each prompt site is annotated: `skip-with-note` (skip, surface in status table), `default-with-warning` (apply safe default, surface value), or `fail-loud` (exit non-zero with remediation; no safe default). Unannotated sites default to `fail-loud`. `--check-only` prevents all mutation; `--non-interactive` controls only prompt fallback. Both are orthogonal and may be combined.

**Scope distinction:** This command sets up the coordinator *environment* (plugins, env vars, tools). For per-project scaffolding (CLAUDE.md, tracker, workstreams), use `/coordinator:repo-setup` after this.

## Phase 1 — Environment

Run all checks and collect results for the status table.

### 1a.0. Bash version (macOS portability — ratified policy: bash ≥ 4)

Scripts resolve via `#!/usr/bin/env bash` — check the PATH-resolved bash, not `/bin/bash`. The check is folded into `setup.py --preflight` (the Step Zero forwarder-resolved script, above), not run separately here: it resolves `bash` on PATH and, if none is found, reports `bash_version: failed (no bash on PATH)` — the same remediation as the `major < 4` case below; otherwise it reads the resolved binary's `BASH_VERSINFO` major/minor pair.

- **major ≥ 5, or (major == 4 and minor ≥ 3):** ready. Status: `bash_version: ready (<version> at <path>)`.
- **major == 4 and minor < 3:** `fail-loud` — `coordinator-safe-commit` uses `local -n` namerefs (4.3+) and hard-aborts on 4.0–4.2; every commit would abort. Status: `bash_version: failed (<version> below 4.3 nameref floor)`.
- **major < 4 (macOS stock bash 3.2):** `fail-loud`. The whole block below is gated on macOS so it is a silent no-op on Linux and Git-Bash on Windows:

macOS 3.2-bash remediation — brew presence, brew-bash install, and the login-rc shellenv
append — is entirely owned by `normalize-env` (the consent-gated bash-login-shell reconstruction
described at Step Zero above):

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/scripts/normalize-env" --yes
```

`normalize-env` enumerates each of the three offers (brew presence, `brew install bash`, login-rc
shellenv append) individually, consent-gated, blast-radius-last ordered, and emits the same
`brew_present` / `brew_bash_installed` / `shellenv_block` status rows this section used to compute
inline. On Windows, every mutation creates a backup and `--restore` reverts to the pre-run state.
Run `--dry-run` first (Step Zero above) to preview without applying. Under `--check-only`, run
`normalize-env` with no mutating flag to get a read-only report of what would change.

Status: `bash_version: failed (<version> — bash ≥ 4.3 required)`. Under `--check-only`, report the failed row without halting setup; otherwise a hard blocker for script-dependent phases.

#### Login-shell orphan detection and repair (macOS — post-offer step)

After the bash-version offers complete, if the `probe_shell_login_env` probe (in `coordinator_core.install.prereq_probe`, claude-klabauter) reports an orphaned bash login shell — meaning the user's login shell is `bash` but their `~/.bash_profile` does not carry `~/.local/bin` (where `claude` lives) — the install agent explains the situation in plain terms and offers repair:

> **claude will vanish in a fresh terminal** because your bash login shell's `~/.bash_profile` does not include `~/.local/bin`. This does NOT mean you need to change your login shell back to zsh — the existing `~/.bash_profile` is simply missing the PATH entry. Run `normalize-env` to reconstruct it.

Offer to run `normalize-env --yes` (the Step Zero forwarder-resolved script, above) to reconstruct `~/.bash_profile`. **No `chsh` is offered, implied, or executed** — this step repairs an already-bash login shell; it does not create one and does not prompt the user to change their login shell in either direction.

**Sentinel audit note.** Offer C's `case` statement and `normalize-env`'s reconstruction share a single fixed dedup-marker comment baked into the appended brew-shellenv block. A re-run where the login shell is already `bash` detects the reconstructed `~/.bash_profile` via the existing `grep -qF "$SENTINEL"` guard and stands down rather than appending a duplicate block.

#### 1a.0.1. Invoking-shell bash≥4 verification (install-completion check)

The offers above (A/B/C) repair the **login shell** — but the Claude Code **Bash tool's** invoking-shell resolution is a separate, undocumented mechanism (there is no `settings.json` override for it) that can still land on zsh or `/bin/bash` 3.2 even after Offer C succeeds. When that happens, a coordinator lifecycle skill that `source`s a bash≥4-guarded lib aborts mid-flow with an opaque `requires bash >=4 (found unknown)` error — a silent trap the operator only discovers later. (Historical example: `coordinator/lib/strangler-facade.sh`, killed 2026-07-21/22 in the bash-kill campaign — no lifecycle skill sources a bash-4-guarded lib live any more, but the risk class persists for any future bash lib.) Run the shared probe as a verification step so a fresh install that leaves the invoking shell at bash 3.2 WARNs loudly here instead of appearing to succeed silently. The probe itself is physics-irreducible (it reports on the shell that invoked IT — a child process cannot observe the invoking shell's own version) and stayed claude-klabauter-resident rather than porting: resolve the coordinator root via the trusted-root preamble (same traversal/trust checks as every other trusted-root invocation in this file), resolve `$_cc_claude_klabauter` via the same `_cc_claude_klabauter` seam idiom used elsewhere in this file, then run `sh "$_cc_claude_klabauter/coordinator/scripts/lib/invoking-shell-bash4-probe.sh" [--quiet]`.

- **Exit 0** (silent): invoking shell is bash≥4. Status: `invoking_shell_bash4: ready`.
- **Exit 1** (remediation printed to stderr): invoking shell is NOT bash≥4. Surface the printed remediation verbatim to the operator and add to the Phase 7 status table: `invoking_shell_bash4: failed (see remediation above — coordinator lifecycle skills will break until this is done)`. This is a WARN, not a hard installer blocker — Offers A/B/C above already ran; this check independently verifies the invoking-shell dimension they don't cover.

No SessionStart advisory re-checks drift (a later `chsh` back to zsh, a new terminal profile) on subsequent session starts: boot carries only the fast orientation injector, no guardrail/reminder/detector SessionStart hooks. This install-time check is therefore the sole enforcement point for the invoking-shell dimension. The durable fix — migrating the guarded-lib `source` callsites behind the `cc_invoke` seam so they no longer depend on the invoking shell's own bash version — is tracked on the engine's Python track, not here.

<!-- This step is read-only (writes no out-of-repo state), so it intentionally has no
     `uninstall.md` counterpart and is deliberately absent from the install/uninstall
     surface-symmetry list at line 32 above — this absence is not a gap. -->

### 1a. Git repository

Check via `git rev-parse --show-toplevel`.

- If not a git repo: warn that branch management, commits, and handoffs require git. Setup continues.
- If a git repo: note the repo root path.

### 1a.1. Git-config hardening (concurrent-EM lock safety)

Harden **this repo's** git config with two concurrent-EM mitigations: `gc.autoDetach false` (prevents detached GC child orphaning `.git/index.lock` on Git-for-Windows) and `core.checkStat minimal` (ignores NTFS-unstable `ctime/ino/dev` fields that cause phantom-dirty tree). Skip mutations under `--check-only` (report current values instead).

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-configure-git"
```

Idempotent. `gc.autoDetach` is scoped per-repo (not global — would change auto-gc in unrelated repos); spread via `/repo-setup` § 3f.5 and session-init. `core.checkStat minimal` is benign on all platforms — also set machine-wide (`git config --global core.checkStat minimal`).

### 1a.2. Operator `~/.claude` git-hook gates (conditional)

If the operator git-tracks their `~/.claude` (the template-recommended setup), install the meta-repo hook gates. One call installs both legs: the **sending-side** `pre-commit` gate registry and the **receiving-side** `post-merge` / `post-checkout` gates. Pass `"$HOME/.claude"` explicitly — the installer is cwd-independent and self-guards to the meta-repo identity, so it no-ops cleanly when `~/.claude` is not a git repo.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-meta-repo-precommit-hook" "$HOME/.claude"
```

Under `--check-only`, do NOT run the installer — the script has no check-only mode (it always mutates). Instead, omit the invocation and report each gate's current presence: for `$HOME/.claude/.git/hooks/{pre-commit,post-merge,post-checkout}`, list the `# --- Gate: <label> (<marker>) ---` regions found. The gate set is the installer's own registry, not a list to re-derive here — today's markers are `check-no-illegal-paths`, `coordinator-precommit-foreign-platform-check`, `coordinator-precommit-settings-tracking-check`, `detect-staged-rollback` (sending side) and `coordinator-postsync-marker-resync-check` (receiving side).

Idempotent (a present-and-current gate region is left alone; a stale one is re-spliced in place). This is the OSS-user analogue of `/repo-setup` § 3f.5.5: `/coordinator:install` is the surface every operator runs against their own `~/.claude`, so the gate must land here — `/repo-setup` only fires it against the consumer *project* repos it scaffolds, where the helper correctly no-ops.

### 1a.3. Git-LFS enablement (idempotent, harmless — proactive coverage)

Proactively enable Git LFS so that any LFS-backed repo the operator clones later (e.g. project-rag-ue-addon, example-game-repo with `*.uasset`/`*.umap`) materializes real binary content instead of silent ~130-byte pointers. This is the "cover it before they get there" move — `git lfs install` is a harmless, idempotent global config write even for operators who never clone an LFS repo. Reaching this step does NOT depend on `first-run` having run (which is the canonical fresh-clone bootstrap that also enables LFS, but is not traversed on every install path — e.g. coordinator already present on an existing machine).

This is **act-not-gate**: enable when the binary is present; emit advisory remediation when absent. It does NOT hard-fail — the `git_lfs` row in the `--preflight` gate (`coordinator_core.install.prereq_probe.probe_git_lfs`, claude-klabauter) is the advisory verifier and stays advisory. `setup.py --preflight` (the Step Zero forwarder-resolved script, above) is the read-only probe; it treats `git_lfs` as enabled only when BOTH the binary is present AND the global filter is wired (a bare `filter.lfs.clean` key can survive a partial/aborted install, so this is a functional check, not an existence check). Under `--check-only`, report that state and stop — never mutate. Otherwise, if the binary is present, enable it with a single idempotent `git lfs install` call (plain install, NOT `--force` — coexists with existing hooks); if the binary is absent, report it as an absent advisory with per-platform install remediation (macOS `brew install git-lfs` | Windows `winget install GitHub.GitLFS` | Linux `apt install git-lfs`).

Idempotent (re-running `git lfs install` is a no-op once the global filters are wired). The meta-repo `~/.claude` itself LFS-tracks nothing, so no materialization (`git lfs pull` + pointer-scan) runs here — that hard assert is the per-repo step-zero surface for repos that *do* LFS-track content (§ altitude split in the doctrine wiki). Add a `git_lfs` row to the Phase 7 status table.

### 1b. Agent Teams env var

Report the current value of `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` (default `not_set`).

- If `1`: ready.
- If not set: **required for staff sessions and all research pipelines.** If not `--check-only`, offer to add it:

Read `~/.claude/settings.json`. If an `env` block exists, check for the key. If missing, add it:

```json
"env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" }
```

Note: this takes effect on next Claude Code restart.

### 1b.1. Python 3 (real interpreter — not the Windows Store App-Execution-Alias stub)

<!-- D4 annotation: read-only check in Phase 1; the Phase 3 install-substrate.py remediation (python3.cmd shim + orphan-stub deletion) is where the fix lands. This row surfaces the condition early so the status table flags it before any python3-dependent step. -->

Hooks and config helpers call `python3`. On **Windows**, `python3` resolves by default to a Microsoft Store **App-Execution-Alias** — a 0-byte stub that errors on run and is invisible to Git Bash — so a bare `python3` check can read as "present" while every invocation fails. This is the `python` row of `setup.py --preflight` (the Step Zero forwarder-resolved script, above), hard-severity; Phase 3's `install-substrate.py`/its settings-home forwarder installs the `python3.cmd` shim and offers orphan-stub deletion. The probe resolves `python3` on PATH: if nothing resolves, it reports not-found; if the resolved binary runs and reports a version, it's ready; if it resolves but errors on `--version`, that's the App-Execution-Alias stub — it resolves but does not execute.

- **ready:** real interpreter present. Status: `python3: ready (<version> at <path>)`.
- **App-Execution-Alias stub detected (Windows):** `default-with-warning` — Phase 3 (`install-substrate.py`) lays a `python3.cmd` shim and detects/offers-to-delete the orphan AppX stub. Status: `python3: stub (will shim in Phase 3)`. Until then, recommend a real Python (`winget install Python.Python.3.13`) with `Python313\` ahead of `…\WindowsApps` on PATH.
- **not_found:** `fail-loud` — JSON manipulation and hooks need it. Status: `python3: failed (not on PATH)`. Install from https://python.org.

### 1c. Code statistics tool (scc)

Probe for it on PATH, falling back to `$HOME/bin/scc` (`command -v scc || command -v "$HOME/bin/scc"`).

- If found: ready. If not found: optional — install from https://github.com/boyter/scc if desired.

### 1c.1 JSON processor (jq)

Probe for it on PATH (`command -v jq`).

- If found: ready. Required for `orphan-branch-sweep.py --format json` (load-bearing in `/workday-start` Step 1.10).
- If not found: **required for JSON output**. Without `jq`, sweep falls back to `--format text` — downstream JSON consumers fail silently. Install: https://jqlang.org/download/.

### 1c.2 PowerShell 7+ (`pwsh`) — default-on, all platforms

<!-- D4 annotation: skip-with-note — install offer is elective; --non-interactive skips and notes status. -->

Coordinator's Windows hidden-process spawning (claude-klabauter `coordinator/lib/spawn-hidden.sh`, `bin/coordinator-auto-push`), machine-local shims, and `hooks/project-rag-detect.ps1` target PowerShell. On Windows these fall back to the inbuilt Windows PowerShell 5.1 (`powershell.exe`), but **PowerShell 7+ (`pwsh`) is the default-on target** — the supported cross-platform shell, superseding 5.1. Offered on macOS, Linux, and Windows; not a hard blocker.

The probe resolves `pwsh` on PATH (`command -v pwsh`) and, when found, reads its major
version from the leading component of `pwsh --version`'s output. This logic is not a
separate step to run — the `pwsh` row of `setup.py --preflight` (the Step Zero
forwarder-resolved script, above) already performs it, advisory-severity, at Step Zero.

- **`pwsh` present and major ≥ 7:** ready. Status: `powershell: ready ($PWSH_VER at $PWSH_BIN)`.
- **`pwsh` absent (or major < 7):** offer install per platform. Under `--check-only`: `powershell: not_found (would offer)`. Under `--non-interactive`: skip — `powershell: not_found (install offer suppressed — non-interactive)`. Under interactive, offer Y/n (default Y); on accept run the platform command, on decline emit `powershell: declined`:

  - **macOS (`$OSTYPE` = `darwin*`):** `brew install powershell` — **formula, not cask.** The legacy `--cask powershell` was removed from homebrew-cask; PowerShell now ships as a homebrew-core formula (depends on `dotnet`). Requires brew (Offer A above). On success: `powershell: installed ($(pwsh --version | awk '{print $2}'))`.
  - **Linux (`$OSTYPE` = `linux*`):** if `command -v snap` → `sudo snap install powershell --classic`; else doc pointer — `powershell: not_found (install: https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-linux)`. Distro package repos vary; a clean one-liner isn't portable.
  - **Windows (`$OSTYPE` = `msys`/`cygwin`):** if `command -v winget.exe` → `winget.exe install --id Microsoft.PowerShell --source winget --accept-package-agreements --accept-source-agreements`; else doc pointer `https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell-on-windows`. **New-shell caveat:** a winget install lands `pwsh` under `…\WindowsApps` (or the WinGet `Links` shim dir) which is NOT on the *current* shell's PATH — report `powershell: installed (open a NEW shell for it to appear on PATH)`, not a bare `ready`, so the operator doesn't expect `command -v pwsh` to resolve in-session.

### 1c.3 Windows Terminal (`wt`) — default-on, Windows only

<!-- D4 annotation: skip-with-note — Windows-only; silent no-op on macOS/Linux. -->

Windows-only. On macOS/Linux this check is a silent no-op (emit no row). On Windows, Windows Terminal is the **default-on** modern console host paired with PowerShell 7 — it gives the hidden-spawn and auto-push paths a host that doesn't flash a legacy conhost window.

On Windows (`$OSTYPE` = `msys`/`cygwin`) the probe resolves `wt.exe` on PATH; if absent, it
falls back to asking `winget.exe` whether Windows Terminal is already installed (`winget.exe
list --id Microsoft.WindowsTerminal`), treating a successful listing as present. Not
currently a `setup.py --preflight` row — the offer logic below still applies.

- **Present:** `windows_terminal: ready`.
- **Absent, interactive:** offer Y/n (default Y) → `winget.exe install --id Microsoft.WindowsTerminal --source winget --accept-package-agreements --accept-source-agreements`. On success `windows_terminal: installed (open a NEW shell / Terminal for it to appear on PATH)` — like `pwsh`, the winget shim is not on the current shell's PATH until a new shell starts, so don't report a bare `ready`; on decline `windows_terminal: declined`; no winget → `windows_terminal: not_found (install via Microsoft Store or https://aka.ms/terminal)`.
- **`--check-only`:** `windows_terminal: not_found (would offer)`. **`--non-interactive`:** skip — `windows_terminal: not_found (install offer suppressed — non-interactive)`.

### 1d. NotebookLM opt-in (Pipeline D)

Deep-research pipelines (web, semantic, multi-agent) are **bundled into coordinator** — they ship with the coordinator plugin and require no separate installation. There is no standalone deep-research plugin and no `--with-deep-research` flag.

The **only opt-in** in this section is **Pipeline D (NotebookLM media research)**, which is default-off. Pipeline D is powered by an **external, OSS, user-installed** MCP server — jacob-bd/notebooklm-mcp-cli, registered under the server name `notebooklm-mcp` (tool namespace `mcp__notebooklm-mcp__*`) — not a coordinator carrier plugin. Nothing in the coordinator plugin's own `enabledPlugins` set gates Pipeline D; the server lives entirely in the user's own Claude Code MCP configuration.

**Pipeline D prereqs** (check before offering):
- `uv`/`uvx` on PATH (the external server's own install path depends on `uv`)
- Google authentication completed (`nlm login`)

Check whether the external server is already registered — `grep -l "notebooklm-mcp"` against
`~/.claude/settings.json` and `.mcp.json`.

**If registered:** `notebooklm_mcp: registered`. Note that Pipeline D still requires `uv` on PATH and a completed `nlm login` (Google auth) to function at runtime.

**If not registered:** offer to walk the user through installing it (default-off — no offer in most installs). Do NOT offer UE/example-game-repo/game-dev stack or project-rag alongside it.

<!-- D4 annotation: skip-with-note — install offer is elective; --non-interactive skips and notes status. -->

Under `--non-interactive`: skip; emit `notebooklm_mcp: not_registered (offer suppressed — non-interactive)`. Under `--check-only`: emit `notebooklm_mcp: not_registered (would offer install)`.

Under interactive, offer Y/n (default N — Pipeline D is opt-in). On Y, guide the user through the external OSS install — this is a multi-step, restart-gated process the installer surfaces and walks, not one it completes silently in-session:
1. `uv tool install notebooklm-mcp-cli`
2. `nlm login` — interactive Google authentication; the **user** must complete this step, it cannot be automated
3. `nlm setup add claude-code` — registers the `notebooklm-mcp` server by writing the MCP config automatically
4. **Restart Claude Code** for the newly-registered server to come online

On n: skip.

NotebookLM opt-in status is an **explicit row** in the Phase 7 status table regardless of outcome.

### 1f. Global CLAUDE.md integration

`coordinator/CLAUDE.md` does not exist; its content lives in
`coordinator/snippets/em-operating-doctrine.md` (the EM-only channel) and in the global doctrine
at `~/.claude/CLAUDE.md`;
coordinator doctrine reaches the main EM session via a SessionStart hook whenever the
coordinator plugin is enabled, not an `@` import — see
`coordinator/templates/CLAUDE.md.tmpl` § Coordinator Operating Doctrine ("Do NOT re-add an
`@import`"). No manual wiring step is needed here: status `global_claude_md: ready (doctrine
delivered via SessionStart hook)`. If `~/.claude/CLAUDE.md` still carries a stale
`@~/.claude/plugins/coordinator/CLAUDE.md` import, flag it for removal — the
target no longer exists.

## Phase 2 — Operator identity

### Operator identity capture

Persists the operator's name to `~/.claude/coordinator-identity.yaml` so re-runs skip the prompt. Idempotent.

**Step 1 — Read identity file if present** (`test -f ~/.claude/coordinator-identity.yaml`).

- **`version: 1` and `operator_name` present** → use stored value; skip prompt. Status: `operator_identity: ready`. Proceed to Step 3.
- **`version:` > 1** → fail-loud (unsupported schema). Status: `operator_identity: failed (unknown schema version {N})`. Stop phase.
- **`version: 1` but `operator_name` missing (or `version:` absent)** → treat as absent; proceed to Step 2.

If `$ARGUMENTS` contains `--reconfigure`, treat the file as absent regardless.

**Step 2 — Capture identity if absent (or `--reconfigure`).** <!-- D4: fail-loud -->

- **Under `--non-interactive`:** fail-loud — identity file must exist. Status: `operator_identity: failed`. Stop phase.
- **Under interactive:** ask via `AskUserQuestion`: *"What name should coordinator address you by? (first name, handle, whatever fits.)"*

**Step 3 — Write identity file (skip under `--check-only`; emit `operator_identity: would write`).**

Write `~/.claude/coordinator-identity.yaml` atomically, via the identity-writer trampoline (atomic,
merge-not-replace, idempotent — see `coordinator_core.ops.write_identity_file`):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}/.claude" --operator-name "${OPERATOR_NAME}"
```

Status row: `operator_identity: ready`.

### Personal-layer doctrine seed (`~/.claude/CLAUDE.md`)

Seed the operator's global personal-layer file (`~/.claude/CLAUDE.md`) from `templates/CLAUDE.md.tmpl` — the Owner identity stub plus the universal First-Officer / Flag-Severity / Engagement-Modes / Operating-Assumptions doctrine and the editable Communication-Style stub. This is the seed a fresh install would otherwise never get: without it, the `coordinator/templates/CLAUDE.md.tmpl § Flag Severity → global CLAUDE.md § Flag Severity` cross-reference resolves to nothing (content lives at `coordinator/snippets/em-operating-doctrine.md § How to Decide`).

The write primitive itself owns the never-clobber decision: `render-template` (the `render_template` op primitive, live via the DoE trampoline) accepts a `--guard-sentinel <token>` flag that refuses to overwrite an existing non-empty output file lacking the sentinel (exit 3), fail-closed on an unreadable output file. This is the wall — there is no separate classifier layer behind it; the never-clobber semantics (write-if-absent-or-seeded, refuse-if-hand-authored) are the guard flag's own contract, not a richer judgment step this doc used to describe.

**Never-clobber guard.** The seed only writes when the file is absent or already carries the seed sentinel. If `~/.claude/CLAUDE.md` holds any other non-empty content — hand-authored doctrine, most commonly — the step is a no-op that preserves the operator's file, the same "never clobber `CLAUDE.md`" invariant that governs the whole install. This preserves hand-edits across every re-run.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/render-template" "${CLAUDE_PLUGIN_ROOT}/templates/CLAUDE.md.tmpl" -o "${CLAUDE_HOME:-$HOME}/.claude/CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" PM_NAME="${OPERATOR_NAME}"
```

`render-template`'s `--guard-sentinel` primitive owns the never-clobber decision directly: absent
or seed-sentinel-carrying output → writes (exit 0); non-empty output lacking the sentinel →
refuses (exit 3), preserving hand-authored content. On exit 3, treat as
`personal_layer_seed: skipped (existing hand-authored ~/.claude/CLAUDE.md preserved; merge
templates/CLAUDE.md.tmpl by hand if you want the seed doctrine)`; on exit 0,
`personal_layer_seed: written (~/.claude/CLAUDE.md)`; any other non-zero exit is fail-loud with
the forwarder's stderr — do NOT let the operator continue into a session with a broken
`Flag Severity` cross-reference. `render-template` has no `--check-only` flag — under `--check-only`, skip
this call entirely and report `personal_layer_seed: would write (~/.claude/CLAUDE.md)` when the
file is absent or seed-sentinel-carrying, else `personal_layer_seed: skipped (hand-authored
~/.claude/CLAUDE.md — not overwritten)`. The only render token in the template is `{{PM_NAME}}`
(substituted here from `OPERATOR_NAME`). Add a `personal_layer_seed` row to the Phase 7 status
table.

### Engagement posture capture

Persists the operator's preferred EM engagement posture to `~/.claude/coordinator-identity.yaml` alongside `operator_name`, and materializes the matching doctrine overlay into the invocation repo's EM-only channel (`.claude/em-context.md`, resolved via Step 3b-5 below) before the post-install restart (§ Phase 7 "Next step" tells the operator to restart — the overlay must be in place by then, not applied post-hoc on next boot). The overlay lands in that channel, never in the operator's global `~/.claude/CLAUDE.md`: the global file is read by every dispatched subagent, and posture prose about the operator↔EM working relationship has no audience there — a dispatched subagent has no operator and is not party to that relationship. `.claude/em-context.md` is delivered only to the main session, which is where this content belongs. This is a **mandatory gate, not an opt-in feature**: it is asked on every run that lacks a persisted value, interactive or `--non-interactive` alike. There is no skip-injection mode — opting out of the question means not running the installer. Persistence exists purely for re-run ergonomics (a repeat install doesn't re-ask), never as a way to bypass the first-run gate.

**Step 3b-1 — Read persisted posture if present.**

Reuse the `version: 1` frontmatter already read for operator identity (Step 1 above); check the same parsed document for an `engagement_posture` key.

- **`engagement_posture` present** (one of `precision` / `default` / `substrate-free`) → use stored value; skip the question below. Status: `engagement_posture: ready (<value>)`. Proceed to Step 3b-3 (repo-override cross-check).
- **`engagement_posture` absent** (fresh identity file, or an identity file written before this feature shipped) → proceed to Step 3b-2. `--reconfigure` (same flag as operator identity, Step 2 above) also forces re-asking here.

**Step 3b-2 — Ask the posture question (mandatory gate; fires under BOTH interactive and `--non-interactive`).**

- **Under interactive:** ask via `AskUserQuestion`, framing each anchor with a depersonalized archetype — never a named individual (this surface ships to end users; AC9):

  *"How do you want the coordinator EM to work with you day to day?"*
  - **Precision** — *"I want to be consulted often and closely, before things change, not just told after — whether that means reviewing diffs and weighing in on refactor mechanics, or simply wanting to see and approve what's about to change for my users before it ships."* (Fits either a hands-on technical founder who wants tight visibility into engineering detail, or a non-technical founder who can't read a diff but still wants to be asked before a change lands.)
  - **Default** — *"The standard First Officer partnership — the EM acts on engineering calls autonomously, surfaces tradeoffs before forks, and expects me to engage on planning and product direction."* (Today's default posture — most operators want this.)
  - **Substrate-free** — *"Brief me at milestones, minimize interruptions, surface only ship/product-level gates — I don't want engineering detail in my inbox."* (Fits a milestone-briefed executive who owns the vision, not the diffs.)

  These three anchors select **engagement distance** — how closely the operator wants to work with the EM day to day, from "consulted before most things change" (precision) through "informed at forks and milestones" (default) to "briefed only at outcomes" (substrate-free). It is the only axis in play.

  They are **not** a technical-skill or technical-altitude selector. An operator who cannot read a diff, and never wants to, still belongs on **precision** if what they want is to be asked before things change — the anchor is about how often and how closely, never about how much code the operator can read. Picking a farther anchor to avoid engineering detail, when what the operator actually wants is closer involvement, routes them to the opposite of their own preference.

- **Under `--non-interactive`:** honor an explicit `--posture <precision|default|substrate-free>` flag on `$ARGUMENTS` if supplied. If no prior key exists AND no `--posture` flag is supplied: **fail-loud** — the gate is mandatory and has no safe default. Status: `engagement_posture: failed (no prior value and no --posture flag under --non-interactive — re-run with --posture <precision|default|substrate-free>)`. Stop this step (does not need to halt the whole phase — see Step 3b-5 for the check-only/failure-tolerant framing).

**Resolve the repo root once, before Step 3b-3, for both Step 3b-3 and Step 3b-5 to reuse:**

```bash
git rev-parse --show-toplevel 2>/dev/null
```

Capture stdout as `_EM_CONTEXT_REPO_ROOT` (empty when the invocation directory is not inside a git repo).

If `_EM_CONTEXT_REPO_ROOT` is empty (the invocation directory is not inside a git repo), Step
3b-3 below falls back to `$PWD` — a non-repo directory has no true root to walk up to and no
`coordinator.local.md` to find either way, so the fallback changes nothing observable. Step
3b-5's own fail-loud check against this same variable still fires exactly where it did before —
hoisting the resolution does not move that check earlier.

**Step 3b-3 — Cross-check against a per-repo `coordinator.local.md` override, if one exists.**

If the current repo has a `coordinator.local.md` (§ "coordinator.local.md" below; this step runs from whatever repo the installer was invoked in, which may or may not be one), read any per-repo posture override via the shared resolver, using the repo root resolved above (so this still finds `coordinator.local.md` at the true repo root even when the installer was invoked from a subdirectory):

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/bin/coordinator-resolve-validation-cmd.py" --read-key "${_EM_CONTEXT_REPO_ROOT:-$PWD}" engagement_posture
```

Capture stdout as `_repo_posture` for the comparison below.

- **`_repo_posture` empty** → no per-repo override; the identity-file value (from Step 3b-1 or freshly captured in Step 3b-2) is authoritative. Proceed.
- **`_repo_posture` set and matches the identity-file value** → consistent; proceed, no note needed.
- **`_repo_posture` set and DIFFERS from the identity-file value** → **detect-then-fail-loud** (never silent-pick between the two). Status: `engagement_posture: conflict (identity.yaml=<value>, coordinator.local.md=<value>) — reconcile manually, then re-run`. Surface the conflict to the operator with both values named and stop this step; do not write the overlay in Step 3b-5 while the conflict is unresolved.

**Step 3b-4 — Write identity file (skip under `--check-only`; emit `engagement_posture: would write`).**

Extend the same atomic write used for operator identity — write `engagement_posture` into the same document, same mktemp+mv pattern (do not do a second separate write; fold this key into the Step 3 write above when both are being captured in the same run):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}/.claude" --operator-name "${OPERATOR_NAME}" --engagement-posture "${ENGAGEMENT_POSTURE}"
```

The trampoline merges both fields into the same document in one call — no second separate write.

Status row: `engagement_posture: ready (<value>)`.

**Step 3b-5 — Materialize the overlay pre-restart.** (Skip this step entirely if Step 3b-3 reported `engagement_posture: conflict` — do not write the overlay while the conflict is unresolved.) This step targets the EM-only channel of whatever repo the installer was invoked in (same invocation directory as Step 3b-3), using the `_EM_CONTEXT_REPO_ROOT` resolved once, before Step 3b-3.

- **If `_EM_CONTEXT_REPO_ROOT` is empty (invocation directory is not inside a git repo):** fail-loud rather than guessing a landing path. Status: `engagement_posture_overlay: failed (installer must be run from inside a git repo — the overlay lands at <repo-root>/.claude/em-context.md — re-run from inside a repo, or set one up first)`. Stop this step.
- **Otherwise:** invoke the C4 helper for the resolved posture, targeting `<repo-root>/.claude/em-context.md` — **for all three choices, including `default`** (the overlay call is unconditional; `default` is not treated as a no-op skip, since the helper owns whether `default` produces an overlay body or a minimal marker):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/render-posture-overlay" "${ENGAGEMENT_POSTURE}" "${_EM_CONTEXT_REPO_ROOT}/.claude/em-context.md"
```

  - **Under `--check-only`:** append `--check-only` as a third argument to the call above. This emits intent only — writes nothing to `.claude/em-context.md`. Status: `engagement_posture_overlay: would write (<value>)`.
  - **Otherwise:** run the helper without `--check-only`; it writes the overlay into `<repo-root>/.claude/em-context.md` before the terminal restart prompt (§ Phase 7 "Next step"). The op creates that file when it is absent — a repo has no `.claude/em-context.md` before its first install — so this step never needs to seed the target first. On non-zero exit: fail-loud with the helper's stderr — do not silently skip the overlay and let the operator restart into a stale doctrine surface. Status: `engagement_posture_overlay: written (<value>)`.

**Keep the overlay out of the repo's history — this is the step, not a footnote.** The target lands inside the working tree of a repo that may well be shared, and plenty of projects deliberately track `.claude/`. A committed `em-context.md` stops being one operator's posture and becomes everyone's: the EM channel resolves that path for *whoever* opens the repo, so a teammate's session would silently adopt the posture of whoever installed first. That is the same defect this whole channel exists to prevent — posture reaching a reader it was never about — just displaced from dispatched subagents to colleagues. So, before or right after rendering, ensure the path is ignored in the repo the overlay landed in:

First probe whether anything already ignores the path. This reads and mutates nothing, so it runs identically under `--check-only`:

```bash
git -C "${_EM_CONTEXT_REPO_ROOT}" check-ignore -q .claude/em-context.md
```

Note the exit code, and capture stderr if it is non-empty. **Then act on the exit code using your own file-editing tools — do not shell out to append.** The append is a one-line edit to `<repo-root>/.gitignore`, which you can make directly; routing it through a shell redirect buys nothing and turns a reviewable edit into an opaque payload. On exit `1`, and only on exit `1`, add these two lines to the end of that file:

```text
# Operator-local EM posture overlay — per-operator, never shared.
.claude/em-context.md
```

  - `check-ignore` is the right test rather than grepping `.gitignore`: the path may already be covered by a broader existing rule (a repo that ignores `.claude/` wholesale), and appending a redundant line to a file the operator maintains is noise. Only append when nothing already covers it.
  - `check-ignore -q` exits `0` when the path is already ignored, `1` when it is not, and anything greater than `1` on a fatal error (a corrupt repo, a broken git config). Those three exit codes are not the same as "safe to append" — only exit `1` is. Status: exit `0` → `engagement_posture_overlay_gitignore: already covered`, change nothing. Exit `1` → append, then `engagement_posture_overlay_gitignore: appended (<path>)`. Anything greater than `1` → fail loud, do not append: `engagement_posture_overlay_gitignore: failed (check-ignore errored — <stderr from the probe>)`.
  - **Under `--check-only`:** run the `check-ignore` probe — it reads and mutates nothing — and report what the append *would* do: `engagement_posture_overlay_gitignore: would append (<path>)` on exit `1`, `already covered` on exit `0`, `failed` on anything higher. Do not make the `.gitignore` edit. The check-only contract is honored by *you not performing the edit*, exactly as the sibling steps above honor it; there is deliberately no shell conditional guarding it, because nothing in this document sets such a variable in the reading agent's own shell (the `CHECK_ONLY` export named later applies to `bin/install-health/*.sh` drop-in subprocesses, not here) — a guard testing an always-unset variable would read as protection while appending every time.
  - If the repo has no `.gitignore`, the append creates one — a single-entry `.gitignore` is the correct outcome here, not an overreach. Do not `git add` it; whether to track their own ignore file is the operator's call, not the installer's.
  - This does not retroactively help a repo where a previous install already committed the file. If `git -C "${_EM_CONTEXT_REPO_ROOT}" ls-files --error-unmatch .claude/em-context.md` succeeds, the file is already tracked: say so plainly and tell the operator to `git rm --cached` it, because an ignore rule does not untrack an already-tracked path.

**Step 3b-6 — Record the invocation repo for uninstall (idempotent).** The four writes above
(`.claude/em-context.md`, the `.gitignore` append, and — later in this doc — `coordinator.local.md`
and the currency stamp) all land in `_EM_CONTEXT_REPO_ROOT`, but nothing records which repo that
was, so `/coordinator:uninstall` has no way to find and offer cleanup of them later. Close that gap
here, once `_EM_CONTEXT_REPO_ROOT` is resolved (skip entirely if it's empty — same precondition as
Step 3b-5):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" array-append coordinator.installed_repos "${_EM_CONTEXT_REPO_ROOT}"
```

`coordinator.installed_repos` is an append-only, dedup-on-write list key — appending an already-present path is a no-op. Skip mutations under `--check-only` (report `installed_repos_record: would append (<path>)`). Status: `installed_repos_record: recorded (<path>)` / `already recorded (<path>)`.

**Reaching repos onboarded after this run.** `engagement_posture` persists per-machine, in `~/.claude/coordinator-identity.yaml`, but the overlay it drives lands per-repo, in `.claude/em-context.md`. This step only ever touches the repo the installer was invoked in — a repo the operator starts working in later, onboarded via `coordinator:repo-setup` rather than a fresh full install, does not automatically pick up the persisted posture. The expected route is for repo-setup to render the overlay itself at onboarding time, reading the already-persisted `engagement_posture` value from `~/.claude/coordinator-identity.yaml` and invoking the same `render-posture-overlay` helper against that repo's own `.claude/em-context.md` — no re-asking the operator, since the choice was already made. If a later posture change (a re-run of this step with `--reconfigure`) only updates the repo the operator happens to be standing in, repos onboarded earlier keep carrying whichever overlay they last received until something re-renders them; that staleness is a known, bounded gap, not corruption — a repo with an older overlay still has a valid one, just not the current choice. The helper is safe to re-run at any time: it swaps its managed block in place rather than appending, so re-rendering the same or a different anchor into an already-overlaid `.claude/em-context.md` never produces a duplicate.

**Step 4 — Discover working repos.** Three-tier discovery (stop at first non-empty):

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/discover-working-repos.py"
```

Capture stdout as `WORKING_REPOS`.

Helper runs Tier A (`~/.claude/projects/` activity record, translating the `X--Foo`-style directory-name encoding back to a native Windows drive-letter path) then Tier B (`~/dev`, `~/Projects`, `/x`, etc.). Filters meta-repo, `AppData/Local/Temp`, bare drive roots. Returns up to 20 (A) or 30 (B) candidates.

**Tier C — Ask the operator** (if helper returned empty). <!-- D4: default-with-warning --> Under `--non-interactive`: skip; set placeholder; status `working_repos: defaulted to empty`. Under interactive: ask for a code folder via `AskUserQuestion`; re-probe Tier B inside it; if still empty, record the folder with a "no repos yet" note.

**Build `WORKING_REPOS` block.** Markdown list: `` - `<path>` — <one-line from README> ``. Tier A annotates top 3 `(active recently)`. Persist at `~/.claude/working-repos.yaml` (atomic mv). Status: `working_repos: ready (N from tier {A|B|C})`. Under `--check-only`, run Tiers A+B read-only, skip YAML write and Tier C prompt.

**Step 4b — Register discovered repos into `repos.*` (F16).** The manifest above is onboarding-only; cross-repo addressing (`cross-repo-memo --list-receivers`, sibling-path resolution) reads the machine-local `repos.*` registry instead, so bridge discovery into it:

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/register-discovered-repos.py" ${ARGUMENTS}
```

Pass `$ARGUMENTS` through wholesale — the CLI reads `--non-interactive`/`--check-only` from it
directly and ignores flags it doesn't recognize.

Only-if-absent (never overwrites an existing `repos.<key>` value) and tier-gated (registers only what `discover-working-repos.py` already qualified above — never a blanket scan). Status: `repos_registry: seeded (N registered)` / `repos_registry: would seed (N)` under `--check-only` / `repos_registry: none needed (all present)` when nothing to register.

## Phase 3 — Machine-local registry substrate

Lay down `~/.claude/machine-local/` substrate and `bin/{machine-local, claude-home}` resolvers. Idempotent — never overwrites live registry files. Sources of truth: `coordinator/templates/machine-local/README.md` and `coordinator/templates/machine-local/hardware.toml.example`, `coordinator/templates/bin/`, `coordinator/lib/claude-home/` (cross-repo contract surface — do not customize; see README). Skip mutations under `--check-only`; Step 3's seed prompt also skipped under `--non-interactive`.

### Step 1 — Run install-substrate helper

All mechanical work is encapsulated in `coordinator/lib/install-substrate.py`:

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/install-substrate.py"
```

This is the one call in this doc that is deliberately NOT a settings-home forwarder — it is the
step that WRITES those forwarders, so it cannot depend on one existing yet. It resolves
`claude-klabauter` via `REPO_CLAUDE_KLABAUTER`/`CLAUDE_KLABAUTER_ROOT` (already a hard install prerequisite —
see **## Requirements** above) with a same-directory-guess last resort; if neither env var is set
and the guess is wrong, run `machine-local get repos.claude_klabauter` first (or export
`REPO_CLAUDE_KLABAUTER` directly) before this call.

Helper: fails-loud on missing source-of-truth dirs; honors `CLAUDE_HOME` and `COORDINATOR_NON_INTERACTIVE=1`; preserves operator-customized files with one-line notices; skips Windows checks on non-Windows. Installs 7 bin/ artifacts (3 `machine-local`, 3 `claude-home`, 1 `python3.cmd` shim — shims prevent "Select an app" pickers on extensionless scripts). Orphan AppX stub deletion requires `[y/N]` consent.

**Step 3e — `claude` CLI on PATH (cross-platform, idempotent).** The helper also ensures the standalone `claude` binary's dir (native-installer convention: `~/.local/bin`) is on the user's shell PATH — a sentinel-guarded block in the login rc on macOS/Linux, the user PATH via PowerShell on Windows. This closes the most common desktop-app onboarding failure: installing plugins inside the Claude Code desktop app, then opening a terminal and finding `claude` is not a recognized command (the CLI dir was never on the shell PATH). If no CLI binary is found at the standard location, the helper emits a note pointing at the CLI install docs rather than guessing a path. Status row: `claude_on_path: ready (<dir>) | added (<dir> → <rc>) | not found (install CLI)`.

### Step 1b — Run the install-health orchestrator (drop-in scripts; each self-gates)

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-health-run" ${ARGUMENTS}
```

The orchestrator iterates `bin/install-health/*.sh` in lexicographic order, runs each in an isolated `bash` subprocess, and aggregates the failure count — it exits non-zero if any script failed, and stderr names each failing script with its exit code (it does NOT abort on the first failure — partial install completeness beats total bail). Each script self-gates on OS / preconditions and exits 0 silently when not applicable, so a clean run is silent. **Adding a new install-completion script is a directory drop into `bin/install-health/` — no edit to this command is required.** Scripts must be OS-self-gating, idempotent, and resolve libs via `CLAUDE_PLUGIN_ROOT`. **`CHECK_ONLY` is exported here (from `--check-only`) and inherited by every drop-in subprocess — a drop-in that mutates MUST honor it (report would-do, write nothing) to preserve the check-only no-mutation contract (:58, :127).**

**Ownership note:** this `install-health-run.py` orchestrator and its `bin/install-health/*.sh` glob-wiring contract stay DoE-side. The individual drop-in scripts under `bin/install-health/` are claude-klabauter-owned — do not naked-Python-port them from DoE-claude. The two bash drop-ins (`check-windows-ssh-binary.sh`, `ensure-python3-exe-shim.sh`) were killed outright rather than held pending a claude-klabauter-side port (PM directive: delete first, memo claude-klabauter to cover the replacement). `seed-skill-overrides.sh` (already a python3 trampoline, not bash) is the sole surviving drop-in.

### Step 1c — Windows Defender process-exclusion offer (Windows-only, admin-gated, declinable)

Implemented in `install-maximalist.py` (Phase 3 Step 1c), not `install-substrate.py` — sibling in style to the Step 1 AppX-stub-deletion consent prompt above (same `[y/N]` idiom, same default-declined posture, same `COORDINATOR_NON_INTERACTIVE`-awareness).

Defender real-time scanning re-scans every spawned coordinator interpreter process (`bash.exe`, `git.exe`, `sh.exe`, `python.exe`, `pythonw.exe`) on the hot dispatch path — measured `bash.exe` spawn p90 285ms → 19.5ms with process exclusions. `Add-MpPreference -ExclusionProcess` writes a machine-wide Defender policy per resolved toolchain member; paths are resolved live (`command -v`/the `COORDINATOR_PYTHON` env pin for python/pythonw, `command -v` for bash/git/sh) — never hardcoded — and `Add-MpPreference` writes require admin elevation.

**This is a genuine security-posture tradeoff, not a pure performance win:** a compromised copy of an excluded interpreter would then execute unscanned. The step:

- Skips silently on non-Windows.
- Skips (with a note) when `powershell.exe`/`pwsh` is unavailable, or the shell is not elevated (checked via `WindowsPrincipal.IsInRole(Administrator)`).
- Prints the one-line risk statement and the exact resolved exclusion targets before prompting.
- Prompts `[y/N]` — **default is DECLINED**; empty/Enter declines. Under `--non-interactive`/no TTY the exclusion is **never applied**.
- Applies exclusions only on explicit `y`/`Y` consent; a failed `Add-MpPreference` call logs a WARN and does not halt the install (non-fatal, idempotent — safe to re-run).

To roll back manually later, run `Remove-MpPreference -ExclusionProcess "<path>"` (elevated) for each resolved toolchain path this step excluded — a no-op, not an error, on a path that was never excluded. Re-running the installer is safe if a prior attempt partially failed: `Add-MpPreference` is itself idempotent per-path.

### Step 2 — Never overwrite live registry files

If `~/.claude/machine-local/registry.toml` or `registry.local.toml` exists, leave untouched regardless of `.example` updates. Same for any `<concern>.toml` / `<concern>.local.toml`.

### Step 3 — Optional seed prompt (declinable, interactive only)

<!-- D4 annotation (seed prompt): skip-with-note — seed is elective; --non-interactive skips it and notes that the operator should copy .example → real by hand. -->

**Skip entirely** if either registry file already exists (idempotency). Under `--non-interactive`: emit `machine_local_seed: skipped (non-interactive; copy .example files to seed manually)`. Under interactive: offer Y/n to seed the four standard `repos.*` keys via `machine-local set` (never hand-edit). After the `repos.*` seeds, also seed `coordinator.machine_slug` and `coordinator.contributor_slug` (both absent-only, idempotent) from `cs_compute_machine_live` and `cs_compute_contributor_live` respectively (hostname-derived / sanitized git `user.email`-derived; never from a transient env override). Each is guarded by a `machine-local has <key>` check and written only when absent, via `machine-local set <key> "<computed-slug>"` — never a hand-edit or heredoc. **On N:** leave both absent.

**Test surface** (expected; do not actually run setup): Fresh install → directory, all tracked files, all 7 bin/ artifacts present; seed prompt fires. Re-run → no overwrites, no prompts. `--non-interactive` → substrate laid, no seed prompt, no registry files. Operator-modified file → preserved with notice.

**See:** `coordinator/lib/install-substrate.py`, `coordinator/lib/claude-home/README.md`.

---

### Step 3.5 — Clone DoE repo and wire maximalist launch surface (idempotent)

The maximalist coordinator shape delivers skills/agents live-external from the DoE clone via
`--plugin-dir`, and hooks via `settings.json` absolute-path commands generated from `hooks.json`.
This step seeds the required artifacts and wires the persistent launch surface. Prerequisite:
the `clone_auth` gate (Step Zero) passed — git auth is present.

**Maximalist install shape (portable forward install-surface).** The complete install consists of
three coordinated artifacts, all derived from the registry (`repos.doe_claude`) as single source
of truth:

**Canonical launch trinity.**

1. **`.doe-root` pointer** (`<settings-home>/machine-local/.doe-root`, e.g.
   `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root`)
   — one-line cold-readable bootstrap cache projecting the DoE repo root; written atomically by
   `gen-doe-root-pointer.py` (step 3.5a.1) beside its sibling `.claude-klabauter-root`. A legacy
   `${CLAUDE_HOME:-$HOME}/.claude/.doe-root` read remains a fallback rung for machines installed
   before this pointer moved — it is no longer written, only read. Enables cold-terminal
   resolution with zero tool dependency. Also a new precedence tier in
   `lib/resolve-coordinator-clone.py` (reached via the `templates/bin/resolve-coordinator-clone`
   shim — the `.sh` trampoline it replaced is retired) — the ecosystem seam for peer repos.
2. **`claude-doe` wrapper** (`~/.local/bin/claude-doe`) — the underlying launch command;
   regenerates the settings.json hook block and execs `claude --plugin-dir <doe_clone>/coordinator`
   on every invocation (step 3.5b).
3. **`claude()` shell shim** (`~/.claude/shell/claude-doe-shim.sh` + one marked `source` line in
   the interactive rc) — shadows bare `claude` with `claude-doe`; written by `gen-claude-doe-shim.py`
   (step 3.5a.2). Resolves the DoE root via the settings-home `.doe-root` pointer first, falling
   back to the legacy `~/.claude/.doe-root` copy — no machine-local on cold PATH.

**Supersedes sandbox-only W4.1 `~/.claude`-canonical assumptions.** The W4.1 plan was authored and
validated in a `CLAUDE_HOME` sandbox where `~/.claude`-canonical paths sufficed. The forward
maximalist install ships the pointer + shim + resolver-pointer-tier so it is reproducible on any
machine including cold terminals where coordinator `bin/` dirs are not on PATH. The `.doe-root`
pointer is the cold-readable bootstrap artifact that breaks the chicken-and-egg: `machine-local`
(the registry reader) lives in the DoE clone, so it cannot be the resolver that *finds* the DoE
clone from a cold shell.

**3.5a — Clone the DoE repo (idempotent).**

Resolves the clone path from the registry (seeded in Step 3 above, or pre-populated via
`REPO_DOE_CLAUDE` env var) and clones when the target directory is absent (idempotent — no-op if
`.git` already present). Under `--check-only`, reports state without mutating. Under
`--non-interactive`, the registry must be pre-seeded (`machine-local set repos.doe_claude <path>`)
or `REPO_DOE_CLAUDE` must be set — fails loud if neither resolves:
`doe_clone: failed (repos.doe_claude not set — pre-seed the registry or set REPO_DOE_CLAUDE
before running --non-interactive install)`. Under interactive, if `DOE_CLONE` is still
unresolved, ask the operator for the DoE repo URL and target path via `AskUserQuestion`, then
`machine-local set repos.doe_claude <path>` before re-invoking. The CLI resolves the clone URL via
`REPO_DOE_CLAUDE_URL`/`repos.doe_claude_url` (the `clone_auth` gate from Step Zero must already
have passed).

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/ensure-doe-clone" ${ARGUMENTS}
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
a value): if `DOE_CLONE` is still empty and this isn't a `--check-only` run, fail loud — "repos.doe_claude
is unset — cannot proceed with maximalist install", with remediation pointing at
`machine-local set repos.doe_claude <path>` or `REPO_DOE_CLAUDE=<path>` — and exit 1.

**3.5a.1 — Write `.doe-root` pointer (idempotent).**

Project the DoE repo root from the registry into
`<settings-home>/machine-local/.doe-root` — a cold-readable, one-line bootstrap cache, written
beside its sibling `.claude-klabauter-root`. It used to be written into the git-tracked
`~/.claude/.doe-root` instead; that path syncs between machines, so each machine committed its
own absolute clone path over the last one's and the loser silently mis-resolved. The generator
now writes only the settings-home copy — `~/.claude/.doe-root` is read-only legacy fallback,
kept so a machine installed before this change keeps resolving until it re-runs install. The
`claude()` shim (step 3.5a.2) and the pointer tier in `lib/resolve-coordinator-clone.py` (reached
via the `templates/bin/resolve-coordinator-clone` shim — the `.sh` trampoline it replaced is
retired) read this file with a bare
`cat`, settings-home first then legacy, requiring zero tool dependency in a cold terminal.
Written atomically by `gen-doe-root-pointer.py`. Idempotent — no-op when content is unchanged.
Under `--check-only`, generates to a temp path and discards (the live settings-home
`.doe-root` is byte-unchanged after any check-only run — dry-run-safety lesson). Honors
`COORDINATOR_SETTINGS_HOME`/`CLAUDE_HOME` for sandbox isolation.

**Dual-seed with `plugin.mirrors.coordinator-claude.source_path`.** The same step that writes
`.doe-root` also seeds the machine-local registry key `plugin.mirrors.coordinator-claude.source_path`
from the identical resolved `$DOE_CLONE` value — the two keys must be written together so they
never drift apart (source_path re-derivation elsewhere assumes `.doe-root` and this registry key
name the same repo root; see step D3b).

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-doe-root-pointer" ${ARGUMENTS} --graceful-skip-unresolved
```

Status rows: `doe_root_pointer: written | ready (no-op) | would write (check-only) | skipped (clone absent) | failed`.
Status rows: `plugin_mirror_source_path: written | ready (no-op) | skipped (machine-local not found)`.

Add a `.doe-root pointer` row to the Phase 7 status table.

**3.5a.2 — Install `claude()` shim (idempotent).**

Write the `claude()` shell function into `~/.claude/shell/claude-doe-shim.sh` and ensure exactly
one marked `source` line in the operator's interactive rc (`~/.zshrc` for zsh, `~/.bashrc` for
bash, `$SHELL`-detected; override with `COORDINATOR_SHIM_RC=<path>` or `--rc <path>` for
divergent login-vs-interactive shell cases). The shim reads the settings-home `.doe-root`
pointer first, falling back to the legacy `~/.claude/.doe-root` copy, and delegates to
`claude-doe` — no machine-local on cold PATH, no hardcoded machine-specific path.

Generated by `gen-claude-doe-shim.py`. Sentinel-guarded idempotency — does NOT silently overwrite
a hand-modified marked region. Detects the legacy hand-bolted `~/.bashrc` stopgap (`# --- coordinator
maximalist launch ---` block) and surfaces a one-line migration note rather than silently
rewriting it. Under `--check-only`, generates to a temp path and discards — the live shim file
and rc are byte-unchanged (dry-run-safety lesson).

**Distinction from step 3.5b:** the `claude-doe` wrapper (step 3.5b) is the exec target and the
underlying persistent launch command; the `claude()` shim is a thin shadow that lets the operator
type bare `claude` without manual env-setting. Both are required; both are idempotent.

**Note:** this step depends on the `.doe-root` pointer from step 3.5a.1 — run 3.5a.1 first.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-claude-doe-shim" ${ARGUMENTS} --graceful-skip-unresolved
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
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-claude-doe-wrapper" ${ARGUMENTS}
```

Status rows: `claude_doe_wrapper: ready | installed | would install | failed (<reason>)`.

Add a `claude-doe wrapper` row to the Phase 7 status table.

**3.5b.1 — Install interactive-shell resource-cap guard (idempotent, graceful-absent).**

Backstop against a runaway-file class of incident — a mis-pasted blockquote hitting a live shell
as a `>` redirect, glob-matched, with `failglob` off and no file-size cap, once wrote a 365 GB junk
file. Claude-klabauter owns the pure stdout-emitter engine (`bin/shell-init-guard.py`, already
delivered); DoE owns this `~/.bashrc`/`~/.zshrc` eval seam that sources it.

Resolves the claude-klabauter repo root from the registry (the same idiom step 3.5a uses for
`repos.doe_claude`); if `claude-klabauter` is not checked out or the guard script is missing/not
executable, this is a graceful no-op — install continues, reporting `shell_init_guard: skipped
(claude-klabauter not found — no guard to source)`. Otherwise writes an idempotent
sentinel-guarded block into the interactive rc (`~/.zshrc` for zsh, `~/.bashrc` for bash,
`$SHELL`-detected — same rc-selection mechanism as the 3.5a.2 `claude()` shim). The resolved
Claude-klabauter path is baked into the written block, not re-resolved via `machine-local` at eval time
(cold terminals lack it on PATH — same principle as the `claude-doe` block baking
`$HOME/X/DoE-claude`). Appends after any existing content — never clobbers.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-shell-init-guard-seam" ${ARGUMENTS}
```

Status rows: `shell_init_guard: installed | ready (no-op) | would install (check-only) | skipped
(claude-klabauter not found) | failed (<reason>)`.

Add a `Shell-init guard` row to the Phase 7 status table.

**3.5c — Seed settings.json hook block (idempotent).**

Invoke `coordinator_core.install.gen_settings_hooks` (claude-klabauter) directly to write the generated hook
block into `settings.json` — this step no longer shells out to the retired `gen-settings-hooks.sh`
CLI trampoline (retained on disk but no longer called here — see that file's header for why). This wires all `type: command` entries from `hooks.json` (skipping `mcp_tool`
entries — in-process ops, not settings.json rails) with baked registry-absolute paths into the DoE
clone. The generator is idempotent — re-running over an already-seeded `settings.json` produces a
no-op diff. It honours `CLAUDE_HOME` for sandbox isolation. Skip under `--check-only` (emit a note).

**Note on boot semantics:**
`settings.json` hook definitions hot-reload mid-session, but a **SessionStart hook** fires only at
boot — an already-running session will not fire newly-seeded SessionStart hooks. Inform the
operator to restart Claude Code once for the seeded hooks to take effect. **Do NOT imply
SessionStart hooks fire mid-session** — that is a false claim that has misled installers before.

Exit-code contract, preserved from the retired trampoline (rc is never conflated across states):
`0` success (incl. kill-switch no-op), `1` generator business error, `3` CLAUDE_KLABAUTER_ROOT/import
transport failure — a claude-klabauter outage must never be misread as success or as a business error.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/gen-settings-hooks" ${ARGUMENTS}
```

Status rows: `settings_hooks_seed: seeded | skipped (check-only) | skipped (clone absent) | failed`.

Add a `Settings hooks seed` row to the Phase 7 status table.

**3.5c-2 — Seed marketplace-sibling enabledPlugins (idempotent).**

Run `seed-marketplace-enabledplugins.py` to seed `enabledPlugins["<plugin>@<marketplace>"] = true`
into `settings.local.json` for each present, manifest-bearing marketplace-sibling repo (whichever of
project-rag, project-rag-ue-addon, cockpit, example-game-workbench-repo, example-market-data-repo,
Example-store-repo, claude-klabauter are checked out on this machine). Idempotent — a second run is a
no-op — and merge-never-clobber against the **effective merged view** (committed `settings.json` ∪
`settings.local.json`): an explicit `true`/`false` on a key in either file wins and the seeder never
overwrites it. Resolves `settings.local.json` via `--settings-path` → `$CLAUDE_CONFIG_DIR` →
`${CLAUDE_HOME:-$HOME}/.claude/settings.local.json` — the same precedence used throughout this
command. No coordinator self-entry is ever seeded; only `true` is written, never `false`.

The script honors `--check-only`/`CHECK_ONLY` natively — it computes and reports what it would seed
without writing. This step re-derives check-only status from `$ARGUMENTS` in its own fenced block
(same idiom as steps 3.5a, 3.5a.1, 3.5a.2, 3.5b, 3.5c) and passes `--check-only` explicitly rather
than relying on the `CHECK_ONLY` export from Step 3's Phase-3 block (~400 lines earlier) surviving
into this subprocess — install.md's fenced blocks are not guaranteed to share shell state.

Separate step from 3.5c's `gen_settings_hooks` seed — different file (`settings.local.json`, a
per-machine file, not the committed `settings.json` hook block) and a different concern
(marketplace-sibling plugin enablement, not SessionStart hook wiring).

**This step seeds enablement only — it never runs a marketplace-add and is not evidence the
plugin is registered.** Setting `enabledPlugins["<plugin>@<marketplace>"] = true` can be true
while the named plugin was never added to a marketplace and has no manifest, no commands, no
hooks reachable — that combination reads as "installed" to a membership check while the
plugin's SessionStart hook never runs and its daemon never autostarts. Seeding this key does
not, by itself, make the plugin installed; registration is a separate condition this step does
not establish.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/seed-marketplace-enabledplugins" ${ARGUMENTS}
```

Status rows: `marketplace_enabledplugins_seed: seeded | would seed (check-only) | skipped (script
absent) | failed`.

Add a `Marketplace enabledPlugins seed` row to the Phase 7 status table.

**3.5d — Thin `~/.claude/plugins/` shape (design note — no mutation).**

Under the maximalist shape, `~/.claude/plugins/` holds pointer/config entries and harness-native
`bin/` artifacts — **it does NOT hold plugin source bytes**. The coordinator plugin source lives
in the DoE clone, resolved live via `--plugin-dir <doe_clone>/coordinator` on each `claude-doe`
invocation. No byte-copy to `~/.claude/plugins/coordinator-claude/` is performed or expected.

- **Anti-pattern:** byte-copying plugin source to `~/.claude/plugins/coordinator-claude/` is the
  failed directory-marketplace shape (runtime-proven FAIL). Do NOT do this.
- **Harness-native artifacts** (`machine-local`, `claude-home`, platform-localize) stay in
  `~/.claude/bin/` — these are machine-scope resolvers, not plugin source.
- **Hook delivery** is via the `settings.json` command-hook block seeded in step 3.5c above.
  `settings.local.json` hooks do NOT fire (runtime-proven).

This shape assertion is automatically satisfied by running steps 3.5a–3.5c without any byte-copy.
The install-singularity gate (Step 7.5) and doctor probe P-18 verify the canonical single-tree
shape on cadence.

**Sandbox clean-install test harness (see `bin/install-sandbox-check.py`).**

The full clean-install shape — thin `~/.claude` + cloned DoE + wired wrapper — is validated by:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/install-sandbox-check"
```

The harness creates an isolated sandbox (`CLAUDE_HOME` override), exercises steps 3.5a–3.5c
against it, and asserts the resulting shape. Validation runs in two tiers:

1. **Filesystem tier (automated):** thin-`~/.claude` shape, cloned-DoE dir present, wrapper
   installed, settings.json hook block seeded, no plugin-source byte-copy. This tier runs
   fully inside the harness.

2. **Running-in-Claude-Code tier (deferred — hardware/editor-gated):** that skills/agents resolve
   live from the DoE clone path via `--plugin-dir`, that hooks fire at boot from DoE-clone-absolute
   paths, and that `CLAUDE_PLUGIN_ROOT` is unset (self-resolution via `BASH_SOURCE`). This tier
   requires a real Claude Code boot against the sandbox — it CANNOT run inside a subagent. **The EM or PM must
   execute `claude-doe --dry-run` and then launch `claude --plugin-dir <sandbox>/coordinator`
   interactively to complete this tier before declaring the install surface complete.**

---

### Step 5 — Register coordinator plugin in `plugin.mirrors` (idempotent)

Coordinator's live install IS the canonical source (`~/.claude/` itself). Register in `registry.local.toml::plugin.mirrors` so `check-plugin-drift.py` surfaces it as `n/a-by-design`. Run under `--non-interactive`; pass `--check-only` when set.

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/register-coordinator-mirror.py" ${ARGUMENTS}
```

The helper is idempotent and atomic — safe under concurrent `/coordinator:install` invocations.

Add a `Coordinator plugin.mirrors` row to the Phase 7 status table.

---

### Step 6 — Coordinator venv / `coordinator_whoami` provisioning (native, folded into Step 1)

<!-- D4: default-with-warning — no prompt site; provisioning fires mechanically under --non-interactive same as interactive, as part of Step 1. -->

`bin/ensure-coordinator-venv.sh` no longer exists — venv provisioning is native. There is nothing
left for this step to shell out to: venv creation, `coordinator_whoami` installation, and the `coordinator.python`
registry pin now happen in-process inside `coordinator_core.install.substrate`'s `_c10a_steps`
(via `coordinator_core.install.ensure_venv`), which already ran above as part of **Phase 3 Step
1** (`install-substrate`). The venv is built **at install time**, not deferred to first bin
invocation — stdlib-only hot-path bins (e.g. `mint-deliverable-id`, `coordinator-doc-new`) run on
bare system python and never touch the `coordinator.python` pin; only the dependency-bearing
surface (`coordinator_whoami`, `pydantic`/`psutil`-backed ops) resolves through the pinned venv.

**Remediation entry point.** `_c10a_steps` is idempotent and mutex-protected, so re-running Phase
3 Step 1 is the correct fix for a broken or absent venv (e.g. per doctor probe P-5) — there is no
narrower venv-only flag exposed by `coordinator_core.install.substrate`'s CLI. Re-invoke the same
command shown at Step 1:

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/install-substrate.py"
```

Under `--check-only`, Step 1's own invocation already reports without mutating (§ Step 1 above)
— this step performs no independent check-only pass.

Map Step 1's own outcome to the Phase 7 status row (venv-rebuild failures surface through the
same exit code — `_c10a_steps` retains a fallback venv with a WARN when one exists, and fails
hard only when no safe fallback is available):

| Step 1 outcome | Phase 7 status |
|---|---|
| Step 1 succeeded | `coordinator_whoami: ready` |
| Step 1 succeeded (`--check-only`) | `coordinator_whoami: would ensure (folded into Step 1)` |
| Step 1 failed | `coordinator_whoami: failed (see Step 1 stderr above)` — do NOT halt chain |

On failure: Step 1's own stderr already carries the diagnostic; do NOT halt the install chain
(same non-halting contract as prior Steps).

Add row to Phase 7 table.

---

### Step 7 — Scaffold canonical document structure (idempotent)

Scaffold (eager entries from `canonical-structure.yaml`) into `~/.claude`, landing `cross-repo/` with its README. Skip mutations under `--check-only` (emit `canonical_structure: would scaffold`).

```bash
PYTHONPATH="${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}${PYTHONPATH:+:$PYTHONPATH}" "${COORDINATOR_PYTHON:-python3}" -m coordinator_core.install.scaffold_structure --root "${CLAUDE_HOME:-$HOME}/.claude" --manifest-root "${CLAUDE_PLUGIN_ROOT}/coordinator"
```

Idempotent — skips existing dirs/READMEs, never clobbers. On success: `canonical_structure: ready`. On non-zero: `canonical_structure: failed` (log stderr; do NOT halt — advisory, not hard infrastructure).

Add a `Canonical structure` row to the Phase 7 status table.

---

### Step 7.5 — Install singularity gate (canonical-locus integrity)

Verify the coordinator setup resolves to a single canonical coordinator tree — the canonical-locus invariant. Two shapes are recognized:

- **Pre-cutover (`~/.claude` shape):** canonical tree = `~/.claude/plugins/coordinator-claude`. Catches the split-install failure mode where multiple coordinator trees register divergently across `settings.json` / `settings.local.json` / `known_marketplaces.json` and the loaded skill silently resolves to a stale copy.
- **Maximalist post-W4.2 shape:** canonical tree = DoE clone resolved via `plugin.mirrors.coordinator-claude.live_path` in `registry.local.toml` (delivered live via `--plugin-dir`; `~/.claude/plugins/coordinator-claude` is **absent**). The live_path is the sole reachable tree — `_tree_count` reaches 1 and the split-detection test passes naturally.

In both cases, exactly one distinct canonical tree is expected. A genuine stray second tree (e.g. a `~/coordinator-claude` clone, a stale worktree) is always an accidental split. Also catches a doubled `.claude/.claude` venv pin and a `.claude`-suffixed `CLAUDE_HOME`.

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/check-install-singularity.py"
```

A single explicitly-exported `COORDINATOR_CLONE` / `COORDINATOR_ROOT` dev-loop override (`.git`-backed clone) is exempt — exits 0 with an INFO line. A non-zero exit means an **accidental** split (a genuine stray second tree): print the remediation, add an `Install singularity` row to the Phase 7 status table marked `failed`, and surface to the operator. On exit 0, the INFO line names the resolved canonical tree path (e.g. the DoE clone path under the maximalist shape). This is the install-time twin of doctor probe **P-18**, which re-checks the same invariant on cadence.

Add an `Install singularity` row to the Phase 7 status table.

---

### Step 8 — Write fan-out large-wave threshold (idempotent)

Write the cores-scaled soft ramp-reminder threshold (`3 × logical CPU count`, floored at 1) that claude-klabauter `coordinator/bin/fan-out-dispatch.py` reads before launching a large wave — a **speed-taper advisory, not a cap**. Never clobbers a manual override. Logic in `bin/capture-fan-out-threshold.py`:

Normal run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/capture-fan-out-threshold"`. Under `--check-only`, pass `--check-only` as the sole argument instead (emits `would write (N)`, writes nothing).

Add a `Fan-out threshold` row to the Phase 7 status table from the script's output (`written (N)` / `pre-existing` / `would write (N)`).

### Step 9 — Fire platform-localize once at install time

The `platform-localize.py` hook auto-fires on SessionStart, so the first new session after install will produce a valid `settings.local.json` + `known_marketplaces.json`. But running it eagerly here closes the window where `/plugin` fails with a "marketplace configuration corrupted" error before the user opens a new session.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/run-platform-localize" ${ARGUMENTS}
```

Idempotent. Adds row to Phase 7 status: `platform_localize: ran` / `skipped (check-only)` / `error (see stderr)`. Under maximalist, that row may read `platform_localize: ran (known_marketplaces.json not applicable — no local plugin dirs)` — this is expected, not an error (F9).

---

## Phase 4 — Meta-repo doctrine

### `~/.claude` git tracking

Check whether `~/.claude` is a git repo (`git -C ~/.claude rev-parse --show-toplevel 2>/dev/null || echo "not_a_repo"`).

- **Repo:** ready. If no remote, suggest adding one for machine-loss recovery. Also check that the per-machine state files are gitignored — probe all three of `coordinator-setup-state.yaml`, `settings.json`, and `bin/`, not just the first, since the latter two are the ones that break a second machine rather than merely clutter it: `grep -qE '^/?coordinator-setup-state\.yaml' ~/.claude/.gitignore 2>/dev/null`, `grep -qE '^/?settings\.json' ~/.claude/.gitignore 2>/dev/null`, `grep -qE '^/?bin/' ~/.claude/.gitignore 2>/dev/null`. If any is a `gap` (and not `--check-only`), offer to append the corresponding block from `templates/dotgitignore.tmpl` (do not auto-edit). Status row: `claude_gitignore: covered` only when all three probes pass, else `claude_gitignore: gap (offered: <paths>; declined: <paths>)` naming each missed path under whichever half of the tie applies to it (a path not yet offered stays out of both lists).

  **A gitignore rule alone does not fix an already-tracked path** — git keeps updating whatever is in the index regardless. So when the offer is accepted, also check `git -C ~/.claude ls-files --error-unmatch <path>` for each newly-ignored path and, where it is tracked, offer `git rm -r --cached <path>` alongside. Report the ignore-added-but-still-tracked case explicitly rather than reporting `covered`; a rule that is inert reads as protection while the leak continues.

- **Not a repo, not `--check-only`:** offer to initialize. <!-- D4: default-with-warning --> Under `--non-interactive`: skip (`claude_git_tracking: skipped`). Under interactive: **Initialize (Recommended)** — `git init ~/.claude`, starter `.gitignore`, commit `chore: initialize Claude Central`; or **Skip**. **The installer never creates a remote or pushes** — that is the user's call to make deliberately, not a side effect of running setup, and it is an outward-facing action on a directory that may still contain untriaged per-machine state. Adding a private remote afterwards is encouraged and covered in the getting-started tour; the two are not in tension.
- **Not a repo, `--check-only`:** report `not_a_repo`.

---

## Phase 5 — Project-local

### coordinator.local.md

Check if `coordinator.local.md` exists at the repo root (`test -f coordinator.local.md`).

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

**`fast_test_cmd` (optional).** Run by `/workday-complete` Step 1 and `/workweek-complete` Step 2 via `cs_resolve_fast_test_cmd`. Resolution order: `COORDINATOR_FAST_TEST_CMD` env var → this key → skip-with-notice. Must be a single command — no `&&`/`;`/pipe chaining. Multi-step validation goes in a wrapper script that accumulates exit codes explicitly (so a mid-list failure still returns non-zero and later runners still run). Single-command examples: `npm run test:fast`, `cargo test --lib`, etc.

### Currency stamp (idempotent)

<!-- D4: default-with-warning — stamp is written silently; skip-with-note under --check-only. -->

Record which `COORDINATOR_SCHEMA_VERSION` the current repo's scaffolding was set up against, enabling drift probe (doctor P-13, Wave-2). Under `--check-only`: report `currency_stamp: current (vN)` / `drift (vN->vM)` / `unstamped(legacy)` / `would write`. Otherwise (idempotent write):

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:-$HOME/claude-klabauter}}/coordinator/lib/coordinator_currency.py" write "$PWD" "${CLAUDE_PLUGIN_ROOT}"
```

Add a `Currency stamp` row to the Phase 7 status table (`written (vN)` / `current (vN)` / `failed — <reason>`).

---

## Phase 6 — Optional

### Persona Customization

<!-- D4: default-with-warning — Keep defaults is canonical baseline. -->

Under `--check-only`: apply **Keep defaults**, status `persona_customization: skipped (check-only)`.

Under `--non-interactive` (not `--check-only`): apply **Keep defaults**, status `persona_customization: skipped (non-interactive default: keep defaults)`.

Under interactive:

> The coordinator includes named reviewer personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering). Customize their names? **Keep defaults** / **Customize** — Choosing **Customize** renames the reviewer agents across the install (the EM runs `name-personas.sh` for you) and is reversible by re-running this install step.

If customize: run `name-personas.sh` — it handles the rename across agent files and prompts/skills. Or take the guided tour (Phase 7) where the EM walks you through it. Either way, exclude claude-klabauter `coordinator/bin/publish-time-transform-py` from search-replace (it carries the canonical `NAME_TO_ROLE` table and must not be altered).

### GitHub Auth via 1Password (optional opt-in)

<!-- D4: opt-in — default declined; no-ops cleanly on machines without 1Password. -->

Optionally wire GitHub auth + SSH commit signing through the **1Password SSH agent** on this
(interactive) machine — the recommended standard setup. This is fully
opt-in: it **no-ops with a clean exit** on machines without 1Password, so coordinator users who
don't use 1Password can decline or ignore it. Headless machines keep token HTTPS
(`gh auth setup-git`) — do not run this there.

Under `--non-interactive`: skip silently. Status row: `github_auth_1password: skipped (non-interactive)`.

Under `--check-only`: run the helper in report mode (no mutation) and read its final
machine-readable line, `STATUS: github_auth_1password=<token>`:

```bash
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:?engine repo root unresolved — register repos.claude_klabauter}}/coordinator/scripts/setup-github-auth-1password.py" --check
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
"${COORDINATOR_PYTHON:-python3}" "${REPO_CLAUDE_KLABAUTER:-${CLAUDE_KLABAUTER_ROOT:?engine repo root unresolved — register repos.claude_klabauter}}/coordinator/scripts/setup-github-auth-1password.py"
```

The helper detects 1Password, optionally installs the `op` CLI, routes `github.com` over
`ssh.github.com:443`, configures global SSH commit signing, and offers to flip the current repo's
`origin` to SSH. It backs up `~/.ssh/config` before editing and verifies `git ls-remote` before
keeping a remote change. Read its final `STATUS: github_auth_1password=<token>` line for the row:
`configured` → `configured`; `incomplete` → `declined` (1Password present but the operator declined
one or more offers); `n-a-no-1password` → `n/a (no 1Password — skipped)`.

### Percolation Setup (if applicable)

Check whether this repo is a percolation source: `coordinator/bin/publish.py` exists as a file AND a `setup` directory exists. If either is absent: skip silently (not a percolation source). If both are present: enumerate registered targets via `coordinator/lib/percolate/targets.py`'s `load_targets(setup_dir, ...)` (reads `setup/publish-targets.portable` as its primary tier; falls back to the machine-local registry, then the legacy `setup/publish-targets.sh` if present) and count the resolved rows.

- **`MISSING_TARGETS` or `TARGET_COUNT:0`:** Walk the operator through four steps inline, interactively — do not skip: (1) detect or scaffold the publish-target registry (`setup/publish-targets.portable`, falling back to the machine-local registry then the legacy `setup/publish-targets.sh`); (2) register a target — name, mode (`mirror` or `manifest`), `source_dir`, `dest_dir`; (3) audit and author `.percolate-ignore` at the source plugin root; (4) scaffold the hook directories.
- **All targets configured** (`.percolate-ignore` + hook dirs present): status `Percolation: N target(s) configured`.
- **Partially configured:** surface gap and offer to run setup for unconfigured target(s).

Under `--check-only`, report state only. Add a `Percolation` row to the Phase 7 status table.

---

## Phase 7 — Status Report

### Step 0 — Record setup-concluded receipt (idempotent)

<!-- D4: default-with-warning — no prompt site; fires mechanically under --non-interactive same as interactive. -->

Record the enduring `setup_concluded` milestone so sibling repos can confirm coordinator is ready. Idempotent. Skip mutations under `--check-only` (emit `setup_state_receipt: would record`).

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-setup-state" record setup_concluded
```

Add a `Setup-state receipt` row to the status table (`recorded` / `pre-existing` / `would record`).

**Phase 7 status table — github_auth_1password row.** Driven from the Phase 6 GitHub Auth via 1Password step's outcome. Value-set: `configured` | `present` | `declined` | `absent (would offer)` | `n/a (no 1Password)` | `n/a (no 1Password — skipped)` | `skipped (non-interactive)`.

**Phase 7 status table — engagement_posture row.** Driven from Phase 2's Engagement posture capture step. Value-set: `ready (precision|default|substrate-free)` | `would write (precision|default|substrate-free)` (`--check-only`) | `failed (no prior value and no --posture flag under --non-interactive — re-run with --posture <precision|default|substrate-free>)` | `conflict (identity.yaml=<value>, coordinator.local.md=<value>) — reconcile manually, then re-run`. A companion `engagement_posture_overlay` row records the C4 helper's outcome: `written (<value>)` | `would write (<value>)` (`--check-only`) | `failed — <reason>`.

**Phase 7 status table — orientation row (F13(c)).** Driven from `coordinator-setup-state.py check orientation_completed`. Value-set: `PENDING` (default — `orientation_completed` is unset, the common post-restart-not-yet-run state; render this value visibly in the table body, not only in prose below it) | `completed` (the check exits 0) | `skipped (--check-only)`. This row is mandatory in every non-`--check-only` run — a skipped or not-yet-run orientation must never be silently absent from the table.

Present a summary table with one row per check above (including the `orientation` row immediately above).

### Plugin-bundled doctrine wikis

Plugin ships doctrine at `<plugin-install-path>/docs/wiki/`. If **required** items (git) are missing, note prominently. If recommended items (Agent Teams, CLAUDE.md import) are missing, list next steps.

**Hard-precondition rows.** Machine-local rows are non-optional: `FATAL` means Phase 3 halted (downstream skills won't function). `Registry seed` is informational only.

### Next step — guided onboarding (elective-when, not optional-whether)

<!-- "Elective-when" ≠ "optional-whether": skipping is a legitimate in-the-moment choice, not
     a hard gate, but the heading must not read as "skip freely, no cost" — see the
     terminal-message gate below for the enforcement half of this reframe. Do not revert this
     heading to a bare "Optional next step." -->

Skip under `--check-only`. After the status table, record `orientation_started` and offer: *"Want a walkthrough of what you just installed?"* On accept, facilitate three movements as a conversation, not a recital — calibrate to the operator's background first, then teach: (1) **Orient** — First Officer Doctrine (PM owns product direction, EM owns implementation), the plan → enrich → review → execute → review pipeline, the reviewer personas, the workday/workweek cadence, and where doctrine lives (`~/.claude/CLAUDE.md`, per-project `CLAUDE.md`, plugin wikis); (2) **Make it yours** — co-author `~/.claude/CLAUDE.md` with the operator rather than dumping the whole customization menu (persona names, `coordinator.local.md` project type); name `.claude/em-context.md`, in the repo the operator installs from, as the separate per-repo surface where engagement posture lives and is hand-tuned; all customization lands in the live `~/.claude` install (or that repo's `.claude/em-context.md`), never a separate clone of the source repo; (3) **Test drive** — run `/workstream-start` on one of the operator's real repos, then a small real plan through `/coordinator:plan`, a review dispatch, and `/workstream-complete` to close the loop. Record `orientation_completed` once the operator reaches the end (or signals they're done); the recording is first-occurrence-wins, so re-recording is safe. It's optional and re-runnable — if they'd rather learn by doing, point them at `/workstream-start` and stand down gracefully.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-setup-state" record orientation_started

```

**Refinement target close.** Include verbatim in every next-steps block (not under `--check-only`):

> Your `~/.claude` is the surface you evolve — git-track it and back it up; the coordinator
> plugin source lives in the DoE clone (`repos.doe_claude`), resolved live via `claude-doe`.
> Bare `claude` now works via the installed `claude()` shim (in `~/.claude/shell/claude-doe-shim.sh`,
> sourced from your interactive rc) — it reads the settings-home `.doe-root` pointer (falling
> back to the legacy `~/.claude/.doe-root` copy) and delegates to `claude-doe`
> automatically. If the shim is not yet active in your current shell (e.g. first install before
> sourcing the rc), run `claude-doe` directly or open a new terminal. `claude-doe` is the
> underlying wrapper; the shim is the convenience shadow. Never copy plugin source into
> `~/.claude/plugins/` — that is the failed byte-copy shape.

Under interactive AND NOT `--check-only` (after the status table has been shown), check `~/.claude/working-repos.yaml` for the discovered repo count (N). If N > 0, note: *"Or, if you have a project ready: `/coordinator:repo-setup`."* **Suppressed under `--non-interactive` or `--check-only`.** Status row: `bootstrap_offer: offered (N repos)` / `suppressed (--non-interactive|--check-only)` / `skipped (0 repos discovered)`.

**Terminal-message gate (F13(b)/(d)).** This closing message MUST NOT present unconditional success language while `orientation_completed` is unset — check the `orientation` status-table row above (or re-run `coordinator-setup-state.py check orientation_completed`) before choosing which line to print:

- **While `orientation` is `PENDING`** (the common case immediately after a fresh install): foreground the outstanding step ahead of any success framing —

  *"Setup wired your environment. Next required step — restart Claude Code, then say 'walk me through the coordinator' to finish tailoring it to you."*

- **Once `orientation_completed` is recorded** (this session ran the guided tour, or a prior session already did): the plain success framing is correct —

  *"You're all set up — say 'walk me through the coordinator,' or tell me what you want to build."*

A driver (human or autonomous agent) reading the terminal output must not be able to come away believing the install is fully complete while orientation is outstanding.
