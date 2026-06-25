#!/usr/bin/env bash
# scripts/first-run.sh — Fresh-machine first-run entrypoint for coordinator-claude.
#
# Purpose: lands a freshly git-cloned ~/.claude on a new machine. Installs the
# toolchain (Homebrew, bash>=4.3, python@3.12, node, uv, git-lfs), then re-execs
# under the new bash and delegates to the post-toolchain orchestration (C1b).
#
# Parse-on-3.2 discipline: this entire file MUST parse cleanly under stock macOS
# /bin/bash (bash 3.2). No bash-4 syntax at parse scope — no heredoc-in-command-
# substitution, no associative arrays (declare -A), no mapfile/readarray, no
# ${v^^}/${v,,}. Bash-4 constructs are confined to functions called only on the
# --post-toolchain path, and those functions still parse on 3.2.
#
# Spec backlink: docs/plans/2026-06-23-first-run-entrypoint-c1a-skeleton.md
# Re-exec discipline: all re-execs use "$SELF" (absolute path set in the prologue),
# never bare "$0" — bare $0 is relative under `bash scripts/first-run.sh` and
# breaks when the script chdirs internally.

# ---------------------------------------------------------------------------
# ABSOLUTE SELF-PATH PROLOGUE (first executable lines).
# Use cd/pwd — POSIX, bash-3.2 safe. realpath is absent on stock macOS.
# ---------------------------------------------------------------------------
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
SELF="$SELF_DIR/$(basename "$0")"

# ---------------------------------------------------------------------------
# ARG PARSING
# Flags: --plan / --dry-run, --confirm / --yes, --no-git-lfs,
#        --post-toolchain (internal re-exec marker), --non-interactive.
# COORDINATOR_NON_INTERACTIVE env var maps to non-interactive mode.
# ---------------------------------------------------------------------------
_FR_DRY_RUN=0
_FR_CONFIRM=0
_FR_NO_GIT_LFS=0
_FR_POST_TOOLCHAIN=0
_FR_NON_INTERACTIVE=0

if [ -n "${COORDINATOR_NON_INTERACTIVE:-}" ]; then
  _FR_NON_INTERACTIVE=1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --plan|--dry-run)
      _FR_DRY_RUN=1
      ;;
    --confirm|--yes)
      _FR_CONFIRM=1
      ;;
    --no-git-lfs)
      _FR_NO_GIT_LFS=1
      ;;
    --post-toolchain)
      _FR_POST_TOOLCHAIN=1
      ;;
    --non-interactive)
      _FR_NON_INTERACTIVE=1
      ;;
    *)
      printf 'first-run: unknown argument: %s\n' "$1" >&2
      printf 'Usage: %s [--plan|--dry-run] [--confirm|--yes] [--no-git-lfs] [--non-interactive]\n' "$0" >&2
      exit 1
      ;;
  esac
  shift
done

# Review: F1 — alias must be assigned immediately after arg-parse, before any function
# that reads it is defined or called. Previously placed after _fr_build_plan definition,
# which caused --plan preview to always omit git-lfs regardless of the flag.
_fr_no_git_lfs="$_FR_NO_GIT_LFS"

# ---------------------------------------------------------------------------
# POST-TOOLCHAIN HANDLER (C1b).
# Reached only when re-exec'd under bash>=4.3 with --post-toolchain, OR
# when bash>=4.3 was already present (inline path at bottom of file).
# Must appear BEFORE the detection block so the re-exec exits cleanly here
# without re-running detection/install.
#
# Bash-4 features are permitted inside this block — it is only executed
# under bash>=4.3. File still parses clean on bash 3.2.
# ---------------------------------------------------------------------------
_fr_run_post_toolchain() {
  # ------------------------------------------------------------------
  # Step 1: derive PLUGIN_ROOT from SELF_DIR.
  # first-run.sh lives at .../coordinator/scripts/first-run.sh, so
  # PLUGIN_ROOT = .../coordinator  (one level up from scripts/).
  # ------------------------------------------------------------------
  local PLUGIN_ROOT
  PLUGIN_ROOT="$(cd "$SELF_DIR/.." && pwd)"
  export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"

  printf '[post-toolchain] PLUGIN_ROOT=%s\n' "$PLUGIN_ROOT"

  # ------------------------------------------------------------------
  # Step 2: optional preflight via setup.sh --preflight (non-fatal).
  # ------------------------------------------------------------------
  local _setup_sh="$PLUGIN_ROOT/scripts/setup.sh"
  if [ -x "$_setup_sh" ]; then
    printf '[post-toolchain] Running setup.sh --preflight (toolchain status, non-fatal)...\n'
    "$_setup_sh" --preflight || true
  fi

  # ------------------------------------------------------------------
  # Step 3: seed machine-local registry from discover-working-repos.sh.
  # The discover script prints one repo path per line to stdout.
  # For each, derive a sane lowercase key from the basename and register
  # it via `machine-local set repos.<key> <path>`.
  # Idempotent: `machine-local set` is a write-or-overwrite.
  # ------------------------------------------------------------------
  local _discover_sh="$PLUGIN_ROOT/lib/discover-working-repos.sh"
  local _machine_local_bin="$PLUGIN_ROOT/bin/machine-local"

  printf '[post-toolchain] Seeding machine-local registry...\n'

  if [ ! -x "$_discover_sh" ]; then
    printf '[post-toolchain] WARNING: discover-working-repos.sh not found/executable at %s\n' "$_discover_sh" >&2
    printf '  Register repos manually later: machine-local set repos.<name> <path>\n'
  elif [ ! -x "$_machine_local_bin" ]; then
    printf '[post-toolchain] WARNING: machine-local CLI not found/executable at %s\n' "$_machine_local_bin" >&2
    printf '  Register repos manually later: machine-local set repos.<name> <path>\n'
  else
    # Prompt unless in non-interactive / confirm mode.
    local _do_seed=1
    if [ "$_FR_CONFIRM" = 0 ] && [ "$_FR_NON_INTERACTIVE" = 0 ] && [ -t 0 ]; then
      printf 'Seed machine-local registry with discovered repos? [Y/n] '
      local _seed_reply
      read -r _seed_reply
      case "$_seed_reply" in
        ''|[Yy]|[Yy][Ee][Ss])
          _do_seed=1
          ;;
        *)
          _do_seed=0
          printf '[post-toolchain] Registry seeding skipped. Register later: machine-local set repos.<name> <path>\n'
          ;;
      esac
    fi

    if [ "$_do_seed" = 1 ]; then
      local _found_any=0
      local _repo_path
      local _repo_key
      local _repo_base
      while IFS= read -r _repo_path; do
        [ -z "$_repo_path" ] && continue
        _found_any=1
        # Derive sane lowercase key from basename.
        _repo_base="$(basename "$_repo_path")"
        # Lowercase: use tr for 3.2-safe portable lowercase.
        _repo_key="$(printf '%s' "$_repo_base" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"
        printf '[post-toolchain] Registering repos.%s = %s\n' "$_repo_key" "$_repo_path"
        "$_machine_local_bin" set "repos.$_repo_key" "$_repo_path" || {
          printf '[post-toolchain] WARNING: failed to register repos.%s — skipping.\n' "$_repo_key" >&2
        }
      # Review: F8 — process substitution `<(...)` is bash-2.x+ and parses cleanly on
      # bash 3.2. The 3.2 parse-trap is heredoc-inside-$(...), not process substitution.
      done < <("$_discover_sh")
      if [ "$_found_any" = 0 ]; then
        printf '[post-toolchain] No repos discovered. Register later: machine-local set repos.<name> <path>\n'
      fi
    fi
  fi

  # ------------------------------------------------------------------
  # Step 4: regenerate per-machine state IN ORDER.
  # a) install-substrate  (requires CLAUDE_PLUGIN_ROOT exported above)
  # b) ensure-coordinator-venv  (needs machine-local CLI on PATH)
  # c) platform-localize
  # Each is idempotent; fail-loud on any non-zero exit.
  # ------------------------------------------------------------------
  local _substrate_sh="$PLUGIN_ROOT/lib/install-substrate.sh"
  local _venv_sh="$PLUGIN_ROOT/bin/ensure-coordinator-venv.sh"
  local _localize_sh="$PLUGIN_ROOT/bin/platform-localize.sh"

  printf '[post-toolchain] Step 4a: install-substrate...\n'
  if [ ! -f "$_substrate_sh" ]; then
    printf '[post-toolchain] ERROR: install-substrate.sh not found at %s\n' "$_substrate_sh" >&2
    exit 1
  fi
  # Review: reviewer F9 — bare `bash` may resolve to stock 3.2 on PATH; use $BASH (the
  # >=4.3 interpreter already running post-re-exec) to delegate to these scripts.
  "$BASH" "$_substrate_sh" || {
    printf '[post-toolchain] ERROR: install-substrate.sh exited non-zero. Aborting.\n' >&2
    exit 1
  }
  printf '[post-toolchain] install-substrate: done.\n'

  printf '[post-toolchain] Step 4b: ensure-coordinator-venv...\n'
  if [ ! -f "$_venv_sh" ]; then
    printf '[post-toolchain] ERROR: ensure-coordinator-venv.sh not found at %s\n' "$_venv_sh" >&2
    exit 1
  fi
  "$BASH" "$_venv_sh" || {
    printf '[post-toolchain] ERROR: ensure-coordinator-venv.sh exited non-zero. Aborting.\n' >&2
    exit 1
  }
  printf '[post-toolchain] ensure-coordinator-venv: done.\n'

  printf '[post-toolchain] Step 4c: platform-localize...\n'
  if [ ! -f "$_localize_sh" ]; then
    printf '[post-toolchain] ERROR: platform-localize.sh not found at %s\n' "$_localize_sh" >&2
    exit 1
  fi
  "$BASH" "$_localize_sh" || {
    printf '[post-toolchain] ERROR: platform-localize.sh exited non-zero. Aborting.\n' >&2
    exit 1
  }
  printf '[post-toolchain] platform-localize: done.\n'

  # ------------------------------------------------------------------
  # Step 5: git-lfs (unless --no-git-lfs).
  # `git lfs install` is idempotent (global config write).
  # ------------------------------------------------------------------
  if [ "$_FR_NO_GIT_LFS" = 1 ]; then
    printf '[post-toolchain] Skipping git lfs install (--no-git-lfs). LFS-backed clones will be pointer-only.\n'
  else
    printf '[post-toolchain] Running: git lfs install (global, idempotent)...\n'
    git lfs install || {
      printf '[post-toolchain] WARNING: git lfs install failed (is git-lfs installed?). Continuing.\n' >&2
    }
    printf '[post-toolchain] git lfs install: done.\n'
  fi

  # ------------------------------------------------------------------
  # Step 6: closing instruction.
  # ------------------------------------------------------------------
  printf '\n'
  printf '================================================================\n'
  printf '  first-run complete.\n'
  printf '\n'
  printf '  Next step: in Claude Code, run:\n'
  printf '    /reload-plugins\n'
  printf '\n'
  printf '  (Do NOT restart Claude Code — /reload-plugins is sufficient.\n'
  printf '   Note: a SessionStart hook cannot register into the session\n'
  printf '   that is already running, so one /reload-plugins lag is\n'
  printf '   inherent — this is expected.)\n'
  printf '================================================================\n'
}

if [ "$_FR_POST_TOOLCHAIN" = 1 ]; then
  _fr_run_post_toolchain
  exit 0
fi

# ---------------------------------------------------------------------------
# 3.2-SAFE DETECTION
# Own minimal probes — do NOT source prereq_probe.sh (requires bash>=4).
# Build a list of missing tools; used by preview and install phases.
# ---------------------------------------------------------------------------

# Detect bash version using BASH_VERSINFO array (available in bash 3.2+).
_fr_bash_major="${BASH_VERSINFO[0]:-0}"
_fr_bash_minor="${BASH_VERSINFO[1]:-0}"
_fr_bash_ok=0
if [ "$_fr_bash_major" -gt 4 ] 2>/dev/null; then
  _fr_bash_ok=1
elif [ "$_fr_bash_major" = 4 ] && [ "$_fr_bash_minor" -ge 3 ] 2>/dev/null; then
  _fr_bash_ok=1
fi

# Detect python3>=3.11. The probe below is a version check invocation, not a
# Windows subprocess spawn — no AllocConsole risk. # popup-safe-env-suppressed
_fr_python_ok=0
if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then # verify-no-console-flash: allow — one-shot setup tool, not interactive-session hot-path
    _fr_python_ok=1
  fi
fi

# Detect node
_fr_node_ok=0
if command -v node >/dev/null 2>&1; then
  _fr_node_ok=1
fi

# Detect uv
_fr_uv_ok=0
if command -v uv >/dev/null 2>&1; then
  _fr_uv_ok=1
fi

# Detect git-lfs
_fr_git_lfs_ok=0
if git lfs version >/dev/null 2>&1; then
  _fr_git_lfs_ok=1
fi

# Detect Homebrew
_fr_brew_ok=0
if command -v brew >/dev/null 2>&1; then
  _fr_brew_ok=1
fi

# ---------------------------------------------------------------------------
# BUILD ACTION PLAN (shared between --plan preview and confirm-gate output).
# Uses a plain numbered list — no bash-4 arrays, plain shell variables.
# ---------------------------------------------------------------------------
_fr_plan_step=0

_fr_next_step() {
  _fr_plan_step=$(( _fr_plan_step + 1 ))
  printf '  [%s] %s\n' "$_fr_plan_step" "$1"
}

_fr_build_plan() {
  _fr_plan_step=0
  printf 'about to:\n'
  if [ "$_fr_brew_ok" = 0 ]; then
    _fr_next_step 'install Homebrew (absent on this machine)'
  fi
  if [ "$_fr_bash_ok" = 0 ]; then
    _fr_next_step 'brew install bash  (>=4.3 required; stock macOS is 3.2)'
  fi
  if [ "$_fr_python_ok" = 0 ]; then
    _fr_next_step 'brew install python@3.12  (Python 3.11+ required)'
  fi
  if [ "$_fr_node_ok" = 0 ]; then
    _fr_next_step 'brew install node'
  fi
  if [ "$_fr_uv_ok" = 0 ]; then
    _fr_next_step 'brew install uv'
  fi
  if [ "$_fr_no_git_lfs" = 0 ] && [ "$_fr_git_lfs_ok" = 0 ]; then
    _fr_next_step 'brew install git-lfs  then  git lfs install  (global, idempotent)'
  elif [ "$_fr_no_git_lfs" = 1 ]; then
    _fr_next_step 'git-lfs SKIPPED (--no-git-lfs passed; LFS-backed clones will be pointer-only)'
  fi
  if [ "$_fr_bash_ok" = 0 ]; then
    _fr_next_step 're-exec under newly-installed bash>=4.3 with --post-toolchain'
  fi
  # Review: F5 — reordered to match _fr_run_post_toolchain execution order:
  # seed registry (Step 3) runs BEFORE substrate chain (Step 4).
  _fr_next_step 'seed machine-local registry  (post-toolchain, C1b, Step 3)'
  _fr_next_step 'run install-substrate -> ensure-coordinator-venv -> platform-localize  (post-toolchain, C1b, Step 4)'
  _fr_next_step 'tell you to /reload-plugins'
}

# ---------------------------------------------------------------------------
# FIRST-CLASS --plan / --dry-run PREVIEW
# Print the action plan and exit 0 without mutating anything.
# ---------------------------------------------------------------------------
if [ "$_FR_DRY_RUN" = 1 ]; then
  printf '\nfirst-run.sh — dry run (no changes will be made)\n\n'
  _fr_build_plan
  printf '\nExiting (--dry-run / --plan). Re-run without the flag to proceed.\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# PREVIEW-THEN-CONFIRM FLOW
# Always print the action plan before any mutation.
# Interactive (default, TTY): prompt read -r "Proceed? [Y/n]".
# --confirm / --yes or COORDINATOR_NON_INTERACTIVE: skip prompt.
# Design-as-offers: lead with what it will do.
# ---------------------------------------------------------------------------
printf '\nfirst-run.sh — new-machine first-run setup\n\n'
_fr_build_plan
printf '\n'

_fr_should_proceed=0

# Review: F3 — confirm-gate model (plan D3):
#   --confirm/--yes                     → execute (agent has confirmed)
#   interactive TTY, no flags           → print plan + read -r prompt
#   COORDINATOR_NON_INTERACTIVE alone   → print plan + exit 0 (agent reads it, re-invokes with --confirm)
#   raw non-TTY, neither NI nor --confirm → exit 1 (genuinely unsafe to proceed)
if [ "$_FR_CONFIRM" = 1 ]; then
  # Agent or operator has explicitly confirmed. Proceed.
  printf 'Proceeding (--confirm / --yes).\n\n'
  _fr_should_proceed=1
elif [ -t 0 ]; then
  # Interactive TTY — prompt.
  printf 'Proceed? [Y/n] '
  read -r _fr_reply
  case "$_fr_reply" in
    ''|[Yy]|[Yy][Ee][Ss])
      _fr_should_proceed=1
      ;;
    *)
      printf 'Aborted.\n'
      exit 0
      ;;
  esac
elif [ "$_FR_NON_INTERACTIVE" = 1 ]; then
  # Non-interactive agent context without --confirm: print the plan and exit 0 so
  # the agent can read it and re-invoke with --confirm to execute.
  printf 'Non-interactive mode (COORDINATOR_NON_INTERACTIVE set) without --confirm.\n'
  printf 'Action plan printed above. Re-run with --confirm (or --yes) to execute.\n'
  exit 0
else
  # Raw non-TTY with neither NI nor --confirm: cannot proceed safely.
  printf 'first-run: non-interactive shell detected and --confirm not passed.\n' >&2
  printf 'Re-run with --confirm (or --yes) to proceed without a prompt.\n' >&2
  exit 1
fi

if [ "$_fr_should_proceed" = 0 ]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# HOMEBREW INSTALL (when absent, macOS only).
# Uses NONINTERACTIVE=1 to suppress the interactive installer prompt.
# Adds brew to PATH after install (Apple Silicon: /opt/homebrew; Intel: /usr/local).
# Idempotent: guarded by the _fr_brew_ok flag set during detection.
# ---------------------------------------------------------------------------
if [ "$_fr_brew_ok" = 0 ]; then
  printf '[first-run] Installing Homebrew...\n'
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Add brew to PATH for this session (Apple Silicon path first, then Intel fallback).
  # Review: F10 — add || true so a non-zero shellenv exit (e.g. first-install timing)
  # does not abort the script under set -e callers.
  if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)" || true
  elif [ -f /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)" || true
  fi

  if ! command -v brew >/dev/null 2>&1; then
    printf '[first-run] ERROR: Homebrew install succeeded but brew not found on PATH.\n' >&2
    printf '  Add Homebrew to your PATH and re-run.\n' >&2
    exit 1
  fi
  printf '[first-run] Homebrew installed.\n'
fi

# ---------------------------------------------------------------------------
# BREW OFFERS
# Install bash>=4.3, python@3.12 (one pinned formula — not multiple python
# versions), node, uv, and (unless --no-git-lfs) git-lfs.
# Each action is printed before running. Idempotent (brew install is a no-op
# when already present at a sufficient version).
# ---------------------------------------------------------------------------

# bash>=4.3
if [ "$_fr_bash_ok" = 0 ]; then
  printf '[first-run] brew install bash (>=4.3)...\n'
  brew install bash
  printf '[first-run] bash installed.\n'
fi

# python@3.12 — one pinned formula only
if [ "$_fr_python_ok" = 0 ]; then
  printf '[first-run] brew install python@3.12...\n'
  brew install python@3.12
  printf '[first-run] python@3.12 installed.\n'
fi

# node
if [ "$_fr_node_ok" = 0 ]; then
  printf '[first-run] brew install node...\n'
  brew install node
  printf '[first-run] node installed.\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
fi

# uv
if [ "$_fr_uv_ok" = 0 ]; then
  printf '[first-run] brew install uv...\n'
  brew install uv
  printf '[first-run] uv installed.\n'
fi

# git-lfs (unless --no-git-lfs)
if [ "$_FR_NO_GIT_LFS" = 1 ]; then
  printf '[first-run] Skipping git-lfs (--no-git-lfs). LFS-backed clones will be pointer-only.\n'
elif [ "$_fr_git_lfs_ok" = 0 ]; then
  printf '[first-run] brew install git-lfs...\n'
  brew install git-lfs
  # Review: F4 — git lfs install runs in _fr_run_post_toolchain Step 5 (after the
  # substrate chain), not here. Spec order: substrate→venv→localize→git lfs install.
  printf '[first-run] git-lfs brew formula installed. `git lfs install` runs in post-toolchain Step 5.\n'
fi

# ---------------------------------------------------------------------------
# RE-EXEC UNDER BASH>=4.3
# Only re-exec if the current bash is <4.3 AND we are NOT already on the
# --post-toolchain path (infinite-loop guard).
# NEW_BASH is the brew-installed path.
# ---------------------------------------------------------------------------
if [ "$_fr_bash_ok" = 0 ]; then
  _fr_new_bash="$(brew --prefix)/bin/bash"
  if [ ! -x "$_fr_new_bash" ]; then
    printf '[first-run] ERROR: expected bash>=4.3 at %s but not found/executable.\n' "$_fr_new_bash" >&2
    exit 1
  fi
  printf '[first-run] Re-execing under bash>=4.3: %s\n' "$_fr_new_bash"
  # Review: F2 — $@ is empty after the shift loop; reconstruct flags from parsed vars
  # so --no-git-lfs / --confirm / --non-interactive survive across the re-exec boundary.
  _fr_reexec_args=""
  if [ "$_FR_NO_GIT_LFS" = 1 ];       then _fr_reexec_args="$_fr_reexec_args --no-git-lfs"; fi
  if [ "$_FR_CONFIRM" = 1 ];           then _fr_reexec_args="$_fr_reexec_args --confirm"; fi
  if [ "$_FR_NON_INTERACTIVE" = 1 ];   then _fr_reexec_args="$_fr_reexec_args --non-interactive"; fi
  # shellcheck disable=SC2086  — word-splitting is intentional here (positional args)
  exec "$_fr_new_bash" "$SELF" --post-toolchain $_fr_reexec_args
  # exec replaces this process; the line below is unreachable.
  exit 127
fi

# ---------------------------------------------------------------------------
# ALREADY ON BASH>=4.3 (no re-exec needed).
# Run the post-toolchain phase inline — same function used by the re-exec path.
# ---------------------------------------------------------------------------
printf '[first-run] bash>=4.3 already present; running post-toolchain phase inline.\n'
_fr_run_post_toolchain
exit 0
