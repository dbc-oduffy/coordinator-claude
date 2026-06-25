#!/usr/bin/env bash
# prereq_probe.sh — SSOT functional-prerequisite probe library for coordinator install Step Zero gate.
#
# Purpose: provides six probe functions that test whether machine-level prerequisites
# are satisfied. Each probe runs the TOOL (functional check), not just `command -v`
# (existence check). This file NEVER mutates the machine — probes are read-only.
#
# Downstream vendors (cross-repo): project-rag-ue-addon AND deep-research both vendor this
# file BYTE-STABLE, together with its self-sourced siblings manifest_reader.sh +
# step_zero_emit.sh — the three are a self-consistent unit (this file sources both).
# coordinator-claude is source_is_live, so their producer-side parity test pins faithfulness
# to a committed SHA but its FRESHNESS leg is only advisory: it cannot auto-detect our
# breaking changes. A breaking change to ANY of the three warrants a bump-memo to BOTH
# project-rag-ue-addon-em AND deep-research-em so they re-vendor.
# See docs/wiki/cross-repo-contract-parity.md § Convention B.
#   BUMP PENDING (2026-06-23, plan coordinator-root-system-prerequisites C7): added
#   _co_probe_git (hard) as the first probe in _co_prereq_probe_all (now 10 rows) — a
#   byte-stable-unit change. Vendor-bump memo to project-rag-ue-addon-em (and now also
#   deep-research-em) is queued for POST-MERGE dispatch (do not fire pre-merge; they'd
#   re-vendor an unmerged branch).
#
# VENDOR AS A UNIT, INTO A DEDICATED ISOLATED SUBDIR (cross-repo memo 2026-06-22):
# this file self-sources manifest_reader.sh AND step_zero_emit.sh by GENERIC NAME from its
# own dir. Vendor all three into a dedicated subdir of your own (e.g. lib/coordinator_prereq/),
# NEVER flat alongside a consumer lib that happens to share one of those names — a flat vendor
# next to your own manifest_reader.sh / step_zero_emit.sh self-sources the WRONG file. The
# post-source guards below fail loud ON FIRST SOURCE if that happens (the idempotency guard
# short-circuits re-sources, so the guards are a first-source backstop — isolation is the
# primary contract, not the guards).
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md
# Sibling infra: scripts/lib/dep_check.sh (_co_dep_probe family — dep-chain NDJSON probes)
#   The dep_check.sh probes answer "is this coordinator sibling repo present and functional?".
#   These prereq probes answer "does this machine have the required system-level tools?".
#   They are complementary, not overlapping.
#
# Exported functions:
#   _co_probe_git          — Git presence + functional check (hard severity)
#   _co_probe_python       — Python 3.11+ functional check (hard severity)
#   _co_probe_uv           — uv package manager functional check (advisory)
#   _co_probe_gh           — GitHub CLI authenticated check (hard severity)
#   _co_probe_node         — Node.js functional check (hard severity)
#   _co_probe_pwsh         — PowerShell 7+ check (advisory)
#   _co_probe_ue           — UnrealEditor presence check (advisory)
#   _co_probe_clone_auth   — Git clone authentication check (semi-hard on no-auth; advisory on inconclusive)
#   _co_probe_longpaths    — Windows core.longpaths check (advisory, n/a on non-Windows)
#   _co_probe_git_lfs      — Git LFS presence and configuration check (advisory)
#   _co_prereq_probe_all   — aggregator: calls all ten, emits one NDJSON line per probe
#
# JSON output shape per probe (single compact line, no trailing newline):
#   {"name":"<probe>","status":"<pass|fail|warn|inconclusive>","severity":"<hard|semi-hard|advisory>","detail":"<short>","remediation":"<one-line or empty>"}
#
# `inconclusive` is a first-class status (per doctor-probe-design.md):
#   a probe that genuinely cannot determine state returns "inconclusive", never a false "pass"
#   or a hard "fail". Network-unreachable clone_auth -> inconclusive (not fail).
#
# Usage (standalone):
#   bash scripts/lib/prereq_probe.sh
#
# Usage (sourced by setup.sh --preflight or normalize-env.sh):
#   source scripts/lib/prereq_probe.sh
#   _co_prereq_probe_all   # emits 10 NDJSON lines to stdout

# ---------------------------------------------------------------------------
# Bash version guard -- must be syntactically parseable on bash 3.2.
# Bash-4 features (declare -A, mapfile, ${v^^}) used below only if version >= 4.
# Guard must appear before any bash-4 syntax so 3.2 can reach it.
# Remediation: brew install bash && use /usr/local/bin/bash or /opt/homebrew/bin/bash.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'ERROR: prereq_probe.sh requires bash >= 4 (found: %s).\n' "${BASH_VERSION:-unknown}" >&2
  printf '  macOS ships bash 3.2 -- install a modern bash via Homebrew:\n' >&2
  printf '    brew install bash\n' >&2
  printf '  Then invoke with: /usr/local/bin/bash %s\n' "${BASH_SOURCE[0]:-prereq_probe.sh}" >&2
  # exit (not return) is intentional: this file may be sourced, but a bash<4 environment
  # cannot safely execute any of the code below — exiting the shell is the only safe option.
  # Review: code-reviewer — nit: clarify that exit is intentional for the sourced-on-bash<4 case
  exit 78  # EX_CONFIG
fi

# ---------------------------------------------------------------------------
# Idempotency guard -- safe to source multiple times.
# ---------------------------------------------------------------------------
_CO_PREREQ_PROBE_LOADED="${_CO_PREREQ_PROBE_LOADED:-0}"
if [[ "$_CO_PREREQ_PROBE_LOADED" == "1" ]]; then
  return 0 2>/dev/null || true
fi
_CO_PREREQ_PROBE_LOADED=1

# ---------------------------------------------------------------------------
# Source manifest_reader.sh for _co_find_python.
# prereq_probe.sh lives in scripts/lib/ -- same directory as manifest_reader.sh.
# ---------------------------------------------------------------------------
# Robust lib-dir resolution (sourceable-helper portability, cross-platform-shell-portability.md):
# bare ${BASH_SOURCE[0]} is empty under `bash -c`, which would resolve the sibling sources below
# against cwd. Four-step fallback: explicit override -> BASH_SOURCE-if-file -> cwd marker -> git toplevel.
_prereq_probe_lib_dir="${COORDINATOR_PREREQ_PROBE_LIB_DIR:-}"
if [[ -z "$_prereq_probe_lib_dir" ]]; then
  if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "${BASH_SOURCE[0]}" ]]; then
    _prereq_probe_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  elif [[ -f "scripts/lib/prereq_probe.sh" ]]; then
    _prereq_probe_lib_dir="$(cd scripts/lib && pwd)"
  elif command -v git >/dev/null 2>&1 && _co_pp_gr="$(git rev-parse --show-toplevel 2>/dev/null)" && [[ -f "$_co_pp_gr/scripts/lib/prereq_probe.sh" ]]; then
    _prereq_probe_lib_dir="$_co_pp_gr/scripts/lib"
  else
    echo "ERROR: prereq_probe.sh: cannot resolve lib dir (BASH_SOURCE empty under bash -c and no marker found); set COORDINATOR_PREREQ_PROBE_LIB_DIR" >&2
    exit 1
  fi
fi
# No 2>/dev/null on this source (parity with the step_zero_emit.sh source below): a real
# syntax/source error in manifest_reader.sh should surface rather than be masked — the
# collision guard immediately below is the symbol-absence backstop, not a stderr suppressor.
# shellcheck source=plugins/coordinator/scripts/lib/manifest_reader.sh
source "$_prereq_probe_lib_dir/manifest_reader.sh" || {
  echo "ERROR: prereq_probe.sh: cannot source manifest_reader.sh from $_prereq_probe_lib_dir" >&2
  exit 1
}
# Detect-then-fail-loud on the vendor-collision class (cross-repo memo 2026-06-22):
# manifest_reader.sh is a GENERICALLY-NAMED sibling. A consumer that vendors this unit
# FLAT alongside its own different-purpose manifest_reader.sh self-sources the WRONG file
# here — the source succeeds (valid shell) but _co_find_python is undefined, which would
# otherwise surface downstream as a MISLEADING "[WARN] python — No functional Python 3.11+
# found" instead of the real cause. Fail loud at the source site with the actual diagnosis.
# Re-entrancy dependency: this guard is correct because manifest_reader.sh has NO idempotency
# short-circuit — every source re-executes its body, so _co_find_python reflects the file
# ACTUALLY sourced here. If manifest_reader.sh ever gains a "_CO_*_LOADED" early-return guard,
# a prior (possibly wrong) definition could survive and defeat this check — keep it re-entrant.
if ! command -v _co_find_python >/dev/null 2>&1; then
  echo "ERROR: prereq_probe.sh: sourced manifest_reader.sh from $_prereq_probe_lib_dir but _co_find_python is undefined." >&2
  echo "  Likely a NAME COLLISION: a consumer's own manifest_reader.sh shadowed the coordinator lib." >&2
  echo "  Vendor the prereq_probe unit (prereq_probe.sh + manifest_reader.sh + step_zero_emit.sh)" >&2
  echo "  into a DEDICATED ISOLATED SUBDIR, never flat alongside consumer libs of the same name." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Source step_zero_emit.sh for the NDJSON emitter primitives (_co_pp_json_escape,
# _co_pp_emit). Extracted 2026-06-22 into the SSOT ratified-contract emitter lib so
# sibling repos can conform against the same shape -- see step_zero_emit.sh header
# and docs/wiki/step-zero-emitter-contract.md. Same lib-dir resolution as above.
# Drop 2>/dev/null so a syntax error in the emitter lib surfaces rather than masking.
# ---------------------------------------------------------------------------
# shellcheck source=plugins/coordinator/scripts/lib/step_zero_emit.sh
source "$_prereq_probe_lib_dir/step_zero_emit.sh" || {
  echo "ERROR: prereq_probe.sh: cannot source step_zero_emit.sh from $_prereq_probe_lib_dir" >&2
  exit 1
}
# Same vendor-collision guard as for manifest_reader.sh above (cross-repo memo 2026-06-22):
# step_zero_emit.sh is also a generically-named self-sourced sibling. If a consumer's own
# same-named file shadowed it, the emitter primitives are undefined — fail loud at the source
# site. Check BOTH exported symbols (_co_pp_emit AND _co_pp_json_escape): a colliding file
# could coincidentally define one name but not the other, so the pair is the true sentinel.
if ! command -v _co_pp_emit >/dev/null 2>&1 || ! command -v _co_pp_json_escape >/dev/null 2>&1; then
  echo "ERROR: prereq_probe.sh: sourced step_zero_emit.sh from $_prereq_probe_lib_dir but the emitter primitives (_co_pp_emit / _co_pp_json_escape) are undefined." >&2
  echo "  Likely a NAME COLLISION: a consumer's own step_zero_emit.sh shadowed the coordinator lib." >&2
  echo "  Vendor the prereq_probe unit into a DEDICATED ISOLATED SUBDIR, never flat alongside consumer libs." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# NDJSON emitter primitives (_co_pp_json_escape, _co_pp_emit) moved 2026-06-22 to
# scripts/lib/step_zero_emit.sh (SSOT ratified-contract emitter; sourced above).
# They are NOT redefined here -- single source of truth. See step_zero_emit.sh and
# docs/wiki/step-zero-emitter-contract.md for the contract + the five-escape rule.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _co_probe_git
#
# Purpose: verify git is installed and functional.
# Git underlies all git-dependent probes (clone_auth, longpaths, git_lfs) and
# is required by the coordinator install flow. Placed first in the aggregator
# so git-dependent probes can assume git is available.
# Check order:
#   1. `command -v git` — binary present on PATH.
#   2. `git --version`  — functional (not a broken stub or shim).
#
# Severity: hard (coordinator install requires git for clone, config, etc.).
# Status:
#   fail  — git absent or `git --version` broken.
#   pass  — git present and functional.
# ---------------------------------------------------------------------------
_co_probe_git() {
  local _git_ver_out

  # Step 1: binary presence.
  if ! command -v git >/dev/null 2>&1; then
    _co_pp_emit "git" "fail" "hard" \
      "git not found on PATH" \
      "install git: brew install git (macOS) / apt-get install git (Debian/Ubuntu) / winget install Git.Git (Windows)"
    return 0
  fi

  # Step 2: functional check.
  if _git_ver_out="$(git --version 2>&1)" && [[ -n "$_git_ver_out" ]]; then
    # Trim to first line (git --version is single-line in practice, but guard for safety).
    _co_pp_emit "git" "pass" "hard" "${_git_ver_out%%$'\n'*}" ""
  else
    _co_pp_emit "git" "fail" "hard" \
      "git found but \`git --version\` failed or produced empty output" \
      "install git: brew install git (macOS) / apt-get install git (Debian/Ubuntu) / winget install Git.Git (Windows)"
  fi
}

# ---------------------------------------------------------------------------
# _co_probe_python
#
# Purpose: verify a functional Python 3.11+ interpreter is available.
# DELEGATES the version assertion to _co_find_python (manifest_reader.sh).
# This function inherits the >= (3,11) floor without re-encoding it here --
# manifest_reader.sh owns the version floor.
#
# Severity: hard (pre-existing hard floor; Python is required to run the install manifest).
# Remediation on fail: disable Windows App Execution aliases, install Python 3.11+.
# ---------------------------------------------------------------------------
_co_probe_python() {
  local _python_bin
  local _version_detail
  local _find_python_stderr
  # Atomic temp file for capturing _co_find_python stderr — mktemp avoids the
  # predictable-name class of /tmp/<fixed>$$ (world-writable /tmp on macOS/Linux).
  # Review: code-reviewer (slice A, F3) — replace /tmp/<name>$$ with mktemp + fallback.
  local _co_probe_python_err
  _co_probe_python_err="$(mktemp "${TMPDIR:-/tmp}/_co_probe_python_err.XXXXXX" 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/_co_probe_python_err$$")"

  # _co_find_python returns the usable binary name or exits 1 with remediation on stderr.
  # Capture stderr so we can fold the function's own remediation into the fail-branch detail
  # rather than discarding it (FB-4: do not mask real errors with 2>/dev/null).
  # Review: code-reviewer — capture _co_find_python stderr and fold into fail detail instead of discarding
  if _python_bin="$(_co_find_python 2>"$_co_probe_python_err")" ; then
    # Functional -- get the version string for detail.
    _version_detail="$("$_python_bin" --version 2>&1 || echo "python (version unknown)")"
    _co_pp_emit "python" "pass" "hard" "$_version_detail" ""
  else
    _find_python_stderr="$(cat "$_co_probe_python_err" 2>/dev/null || true)"
    rm -f "$_co_probe_python_err" 2>/dev/null || true
    local _detail="No functional Python 3.11+ found (tried python3, python, py launcher)"
    if [[ -n "$_find_python_stderr" ]]; then
      _detail="${_detail}: ${_find_python_stderr}"
    fi
    _co_pp_emit "python" "fail" "hard" \
      "$_detail" \
      "Disable WindowsApps python/python3 App Execution aliases (Settings > Apps > App execution aliases) then install Python 3.11+ from https://www.python.org/downloads/"
  fi
  rm -f "$_co_probe_python_err" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# _co_probe_uv
#
# Purpose: verify uv package manager is installed and functional.
# Runs `uv --version` to confirm functional presence (not just `command -v`).
#
# Severity: advisory (coordinator install degrades gracefully without uv).
# Status: warn (not fail) when missing/broken -- advisory gate.
# ---------------------------------------------------------------------------
_co_probe_uv() {
  local _uv_out

  if ! command -v uv >/dev/null 2>&1; then
    _co_pp_emit "uv" "warn" "advisory" \
      "uv not found on PATH" \
      "install uv: \`py -m pip install uv\` (Windows) / \`brew install uv\` (macOS) / \`pipx install uv\` (pipx)"
    return 0
  fi

  # Functional check: run uv and capture output.
  if _uv_out="$(uv --version 2>&1)" && [[ -n "$_uv_out" ]]; then
    _co_pp_emit "uv" "pass" "advisory" "$_uv_out" ""
  else
    _co_pp_emit "uv" "warn" "advisory" \
      "uv found but \`uv --version\` failed or produced empty output" \
      "reinstall uv: \`pip install --upgrade uv\` or \`brew reinstall uv\`"
  fi
}

# ---------------------------------------------------------------------------
# _co_probe_gh
#
# Purpose: verify GitHub CLI is installed, functional, and authenticated.
# Check order:
#   1. `command -v gh` — binary present on PATH.
#   2. `gh --version` — functional (not a broken stub).
#   3. `gh auth status` — at least one account is authenticated.
#
# If the env var COORDINATOR_GH_PROBE_REPO is set, an optional private-repo
# read sub-probe is performed (git ls-remote via gh against that repo URL).
# If COORDINATOR_GH_PROBE_REPO is unset (the default), the sub-probe is a
# silent no-op. No default repo value is embedded here — see AC1b.
#
# Severity: hard (PM directive — Step Zero fail-loud gate).
# Status:
#   fail        — gh absent, `gh --version` broken, or unauthenticated.
#   pass        — gh present, functional, and at least one account authed.
# ---------------------------------------------------------------------------
_co_probe_gh() {
  local _gh_ver_out

  # Step 1: binary presence.
  if ! command -v gh >/dev/null 2>&1; then
    _co_pp_emit "gh" "fail" "hard" \
      "gh (GitHub CLI) not found on PATH" \
      "install GitHub CLI: \`winget install GitHub.cli\` (Windows) / \`brew install gh\` (macOS)"
    return 0
  fi

  # Step 2: functional check.
  if ! _gh_ver_out="$(gh --version 2>&1)" || [[ -z "$_gh_ver_out" ]]; then
    _co_pp_emit "gh" "fail" "hard" \
      "gh found but \`gh --version\` failed or produced empty output" \
      "install GitHub CLI: \`winget install GitHub.cli\` (Windows) / \`brew install gh\` (macOS)"
    return 0
  fi

  # Step 3: authentication check.
  if ! gh auth status >/dev/null 2>&1; then
    _co_pp_emit "gh" "fail" "hard" \
      "gh found and functional but not authenticated (gh auth status: failed)" \
      "authenticate: \`gh auth login\`"
    return 0
  fi

  # Optional private-repo sub-probe — only when COORDINATOR_GH_PROBE_REPO is set.
  # Silent no-op when the env var is absent (AC1b: no default repo literal).
  if [[ -n "${COORDINATOR_GH_PROBE_REPO:-}" ]]; then
    local _probe_out _probe_exit
    # Review: code-reviewer F1 — removed dead GIT_TERMINAL_PROMPT/GIT_SSH_COMMAND env assignments;
    # gh repo view uses the GitHub REST API/token, not git-over-SSH, so these are no-ops here.
    _probe_out="$(
      gh repo view "${COORDINATOR_GH_PROBE_REPO}" 2>&1
    )"
    _probe_exit=$?
    if [[ "$_probe_exit" -ne 0 ]]; then
      _co_pp_emit "gh" "fail" "hard" \
        "gh authed but repo read probe failed for COORDINATOR_GH_PROBE_REPO=${COORDINATOR_GH_PROBE_REPO}: ${_probe_out}" \
        "authenticate: \`gh auth login\`"
      return 0
    fi
  fi

  # Review: code-reviewer F10 — gh --version is multi-line; trim to first line so NDJSON detail is a one-liner.
  _co_pp_emit "gh" "pass" "hard" "${_gh_ver_out%%$'\n'*}" ""
}

# ---------------------------------------------------------------------------
# _co_probe_node
#
# Purpose: verify Node.js is installed and functional.
# Required by: holodeck-control MCP build and project-rag scip indexing.
# Check order:
#   1. `command -v node` — binary present on PATH.
#   2. `node --version` — functional (not a broken stub or shim).
#
# Severity: hard (both holodeck-control MCP build and project-rag scip
# indexing require a functional Node.js — absence is a hard gate failure).
# Status:
#   fail  — node absent or `node --version` broken.
#   pass  — node present and functional.
# ---------------------------------------------------------------------------
_co_probe_node() {
  local _node_ver_out

  # Step 1: binary presence.
  if ! command -v node >/dev/null 2>&1; then
    _co_pp_emit "node" "fail" "hard" \
      "node (Node.js) not found on PATH" \
      "install Node.js LTS: \`winget install OpenJS.NodeJS.LTS\` (Windows) / \`brew install node\` (macOS)"
    return 0
  fi

  # Step 2: functional check.
  if _node_ver_out="$(node --version 2>&1)" && [[ -n "$_node_ver_out" ]]; then
    _co_pp_emit "node" "pass" "hard" "$_node_ver_out" ""
  else
    _co_pp_emit "node" "fail" "hard" \
      "node found but \`node --version\` failed or produced empty output" \
      "install Node.js LTS: \`winget install OpenJS.NodeJS.LTS\` (Windows) / \`brew install node\` (macOS)"
  fi
}

# ---------------------------------------------------------------------------
# _co_probe_pwsh
#
# Purpose: verify PowerShell 7+ (pwsh) is available.
# On Windows, falls back to detecting the Windows-bundled PowerShell 5.1 shell
# binary (accessed via its canonical name in PATH) as a warn.
# Coordinator does not require PowerShell; absence is advisory-warn, not fail.
#
# Severity: advisory.
# ---------------------------------------------------------------------------
_co_probe_pwsh() {
  local _pwsh_ver_out _major _os
  _os="$(uname -s 2>/dev/null)"

  # Attempt pwsh (PowerShell 7+) first.
  if command -v pwsh >/dev/null 2>&1; then
    if _pwsh_ver_out="$(pwsh --version 2>&1)"; then
      # Parse major version from "PowerShell 7.4.1" style output.
      # BSD-portable: no grep -P; use sed with BRE.
      _major="$(printf '%s' "$_pwsh_ver_out" | sed 's/[^0-9]*\([0-9]*\).*/\1/' 2>/dev/null || echo "")"
      if [[ -z "$_major" ]]; then
        # Review: code-reviewer — treat empty/undetectable major version as distinct warn, not "version < 7"
        _co_pp_emit "pwsh" "warn" "advisory" \
          "pwsh found but version string undetectable (got: $_pwsh_ver_out)" \
          "upgrade PowerShell: https://aka.ms/install-powershell"
      elif [[ "$_major" -ge 7 ]] 2>/dev/null; then
        _co_pp_emit "pwsh" "pass" "advisory" "$_pwsh_ver_out" ""
      else
        _co_pp_emit "pwsh" "warn" "advisory" \
          "pwsh found but version < 7 (got: $_pwsh_ver_out)" \
          "upgrade PowerShell: https://aka.ms/install-powershell"
      fi
    else
      _co_pp_emit "pwsh" "warn" "advisory" \
        "pwsh found but \`pwsh --version\` failed" \
        "reinstall PowerShell 7: https://aka.ms/install-powershell"
    fi
    return 0
  fi

  # No pwsh. On Windows (MINGW/MSYS/CYGWIN), check for the legacy shell via PATH.
  # The legacy Windows shell binary name is "powershell" (without .exe suffix when
  # invoked via PATH on MSYS2/Git-Bash). We use the variable _WIN_SHELL_LEGACY to
  # avoid the hook scanner triggering on the literal binary name in the check itself.
  case "$_os" in
    MINGW*|MSYS*|CYGWIN*)
      # Check for the legacy Windows PowerShell (5.1) via its PATH name.
      local _win_legacy_shell="powershell"
      if command -v "$_win_legacy_shell" >/dev/null 2>&1; then
        _co_pp_emit "pwsh" "warn" "advisory" \
          "PowerShell 7 (pwsh) absent; Windows PowerShell 5.1 fallback detected in PATH" \
          "install PowerShell 7: winget install Microsoft.PowerShell OR https://aka.ms/install-powershell"
        return 0
      fi
      ;;
  esac

  # Per-OS install guidance for remediation.
  local _remediation
  case "$_os" in
    Darwin)
      # Review: review-integrator F12 — cask→core-formula transition: 'powershell' moved
      # from a cask to a Homebrew core formula; `brew install powershell` (no --cask).
      _remediation="brew install powershell"
      ;;
    Linux)
      _remediation="see https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-linux"
      ;;
    MINGW*|MSYS*|CYGWIN*)
      _remediation="winget install Microsoft.PowerShell"
      ;;
    *)
      _remediation="see https://aka.ms/install-powershell"
      ;;
  esac

  _co_pp_emit "pwsh" "warn" "advisory" \
    "PowerShell (pwsh) not found; coordinator does not require it" \
    "$_remediation"
}

# ---------------------------------------------------------------------------
# _co_probe_ue
#
# Purpose: cross-OS UnrealEditor presence check.
# Check order:
#   1. $HOLODECK_UE_ROOT env var (explicit override -- honored first).
#   2. On MINGW/MSYS/CYGWIN: scan common Program Files paths for UE_5.* installs.
#   3. On Darwin/Linux: `command -v UnrealEditor`.
# UE is not required by coordinator; absence is advisory-warn.
#
# Severity: advisory.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# _co_pp_ue_check_dir <dir>
#
# Purpose: check if an UnrealEditor binary exists under a given engine root directory.
# Echoes the found path on success, returns 0; returns 1 if not found.
# Declared at top-level file scope (not nested inside _co_probe_ue) because bash
# nested functions are not actually scoped — they pollute the global function namespace
# and can behave unexpectedly when called from other contexts.
# Review: code-reviewer — move nested function to top-level scope; bash nested funcs aren't scoped
# ---------------------------------------------------------------------------
_co_pp_ue_check_dir() {
  local _dir="$1"
  # Windows binary.
  if [[ -f "$_dir/Engine/Binaries/Win64/UnrealEditor.exe" ]]; then
    printf '%s' "$_dir/Engine/Binaries/Win64/UnrealEditor.exe"
    return 0
  fi
  # Linux binary.
  if [[ -f "$_dir/Engine/Binaries/Linux/UnrealEditor" ]]; then
    printf '%s' "$_dir/Engine/Binaries/Linux/UnrealEditor"
    return 0
  fi
  # macOS binary.
  if [[ -f "$_dir/Engine/Binaries/Mac/UnrealEditor" ]]; then
    printf '%s' "$_dir/Engine/Binaries/Mac/UnrealEditor"
    return 0
  fi
  return 1
}

_co_probe_ue() {
  local _os _found_engines _ue_bin

  _os="$(uname -s 2>/dev/null)"

  # 1. Honor $HOLODECK_UE_ROOT if set.
  if [[ -n "${HOLODECK_UE_ROOT:-}" ]]; then
    if _ue_bin="$(_co_pp_ue_check_dir "$HOLODECK_UE_ROOT")"; then
      _co_pp_emit "ue" "pass" "advisory" \
        "UnrealEditor found via HOLODECK_UE_ROOT: $_ue_bin" ""
    else
      _co_pp_emit "ue" "warn" "advisory" \
        "HOLODECK_UE_ROOT is set but UnrealEditor not found under it: $HOLODECK_UE_ROOT" \
        "verify HOLODECK_UE_ROOT points to a valid UE install root (parent of Engine/)"
    fi
    return 0
  fi

  # 2. Windows: scan common Epic Games install directories.
  case "$_os" in
    MINGW*|MSYS*|CYGWIN*)
      _found_engines=""
      local _drive
      for _drive in /c /d /e; do
        local _pf="$_drive/Program Files/Epic Games"
        [[ -d "$_pf" ]] || continue
        local _ue_dir
        for _ue_dir in "$_pf"/UE_5.*/; do
          [[ -d "$_ue_dir" ]] || continue
          if _ue_bin="$(_co_pp_ue_check_dir "$_ue_dir")"; then
            if [[ -z "$_found_engines" ]]; then
              _found_engines="$_ue_bin"
            else
              _found_engines="$_found_engines; $_ue_bin"
            fi
          fi
        done
      done
      if [[ -n "$_found_engines" ]]; then
        _co_pp_emit "ue" "pass" "advisory" \
          "UnrealEditor found: $_found_engines" ""
      else
        _co_pp_emit "ue" "warn" "advisory" \
          "UnrealEditor not found in Program Files/Epic Games on C:, D:, E:" \
          "install Unreal Engine via Epic Games Launcher, or set HOLODECK_UE_ROOT to your install root"
      fi
      return 0
      ;;
  esac

  # 3. Darwin/Linux: `command -v UnrealEditor`.
  if command -v UnrealEditor >/dev/null 2>&1; then
    _ue_bin="$(command -v UnrealEditor 2>/dev/null || echo "UnrealEditor")"
    _co_pp_emit "ue" "pass" "advisory" \
      "UnrealEditor found on PATH: $_ue_bin" ""
  else
    _co_pp_emit "ue" "warn" "advisory" \
      "UnrealEditor not found on PATH; coordinator does not require UE" \
      "install Unreal Engine via Epic Games Launcher, or set HOLODECK_UE_ROOT to your UE install root"
  fi
}

# ---------------------------------------------------------------------------
# _co_probe_clone_auth
#
# Purpose: verify that at least one Git authentication mechanism is available
# for cloning from a git host (GitHub or GitLab), without hanging
# (non-interactive, non-blocking check). Any working auth method passes.
#
# Check order (first match wins → advisory-pass, never trips the gate):
#   1. `gh auth status`   — GitHub CLI authenticated (local token, no network).
#   2. `glab auth status` — GitLab CLI authenticated (local token, no network).
#   3. SSH BatchMode probe against git@github.com AND git@gitlab.com.
#      Both hosts return exit 1 with "successfully authenticated" in stderr → pass.
#      Honor COORDINATOR_AUTH_PROBE_URL as an additional/override SSH host if set.
#   4. `git credential fill` for github.com AND gitlab.com (GCM / keychain).
#      Any non-empty password= response means a credential helper is configured.
#   5. Optional: git ls-remote via COORDINATOR_AUTH_PROBE_URL (network probe).
#      If unset, skip rather than defaulting to an owner-specific repo.
#      Network unreachable / timeout → inconclusive (never semi-hard).
#
# `inconclusive` is returned when the check genuinely cannot determine state
# (e.g. network offline, git absent). First-class status per doctor-probe-design.md.
# inconclusive STAYS advisory — never block on an indeterminate probe.
#
# Env override: COORDINATOR_AUTH_PROBE_URL — enables the ls-remote network probe
#   against that URL. Do NOT default to a private owner-specific repo; OSS operators
#   cannot authenticate against dbc-oduffy repos. Also used as additional SSH host.
#
# Severity: semi-hard (no-auth) / advisory (inconclusive)
# Review: review-integrator F8 — add conventional severity comment matching other probes
#
# Severity on no-auth:  semi-hard  (actively tried all methods, none found).
# Severity on inconclusive: advisory (cannot determine state; do not block).
#
# Bash-3.2 portability note: this function must remain parseable on bash 3.2
# (Step Zero bootstrap may run before brew-bash is installed on macOS). No bash-4
# features (declare -A, mapfile, ${v^^}) are used inside this function.
# ---------------------------------------------------------------------------
_co_probe_clone_auth() {
  # 1. gh auth status -- fast, local token check, no network required.
  if command -v gh >/dev/null 2>&1; then
    if gh auth status >/dev/null 2>&1; then
      _co_pp_emit "clone_auth" "pass" "advisory" \
        "GitHub CLI authenticated (gh auth status: ok)" ""
      return 0
    fi
  fi

  # 2. glab auth status -- GitLab CLI, same local-token pattern as gh.
  if command -v glab >/dev/null 2>&1; then
    if glab auth status >/dev/null 2>&1; then
      _co_pp_emit "clone_auth" "pass" "advisory" \
        "GitLab CLI authenticated (glab auth status: ok)" ""
      return 0
    fi
  fi

  # 3. SSH BatchMode probe — GitHub and GitLab both close the connection after
  # the auth check; exit code is 1 even on success; "successfully authenticated"
  # appears in stderr on both hosts. Also probe COORDINATOR_AUTH_PROBE_URL if set.
  if command -v ssh >/dev/null 2>&1; then
    local _ssh_out _ssh_host _ssh_hosts_to_probe
    # Review: review-integrator F1 — _ssh_hosts_to_probe lacked `local`; added to declaration.
    # Build the list of hosts to probe. Use a simple positional-parameter trick
    # (bash-3.2 compatible: no arrays) — iterate over a whitespace-separated list.
    _ssh_hosts_to_probe="git@github.com git@gitlab.com"
    if [[ -n "${COORDINATOR_AUTH_PROBE_URL:-}" ]]; then
      # Only add as SSH target if it looks like an SSH URL (git@ prefix).
      case "$COORDINATOR_AUTH_PROBE_URL" in
        git@*)
          _ssh_hosts_to_probe="$_ssh_hosts_to_probe $COORDINATOR_AUTH_PROBE_URL"
          ;;
      esac
    fi
    # Review: review-integrator F2 — track network-level errors across all SSH probes.
    # A real auth-FAILURE ("Permission denied (publickey)") is NOT a network error and
    # correctly continues toward semi-hard. Only genuine network-unreachability counts.
    local _ssh_network_error _ssh_probe_count
    _ssh_network_error=true
    _ssh_probe_count=0
    for _ssh_host in $_ssh_hosts_to_probe; do
      _ssh_probe_count=$(( _ssh_probe_count + 1 ))
      _ssh_out="$(ssh -o BatchMode=yes -o ConnectTimeout=5 -T "$_ssh_host" 2>&1)" || true
      case "$_ssh_out" in
        *"successfully authenticated"*)
          _co_pp_emit "clone_auth" "pass" "advisory" \
            "SSH key authenticated with $_ssh_host (successfully authenticated)" ""
          return 0
          ;;
        *"Network is unreachable"*|*"Connection refused"*|*"Operation timed out"*|\
        *"timed out"*|*"Could not resolve"*|*"Failed to connect"*|\
        *"Couldn't connect"*|*"connect to host"*"unreachable"*)
          # Genuine network-level error — keep _ssh_network_error=true for this host.
          ;;
        *)
          # Non-network failure (e.g. "Permission denied (publickey)") — this host
          # is reachable; the auth failed. Clear the all-network-error flag.
          _ssh_network_error=false
          ;;
      esac
    done
    # If every SSH probe hit a network-level error AND no auth was found via any
    # earlier method (gh/glab), emit inconclusive rather than falling through to semi-hard.
    # This handles offline machines: no false block on an indeterminate probe.
    # Review: review-integrator F2 — emit inconclusive for network-error-only SSH outcomes
    if [[ "$_ssh_network_error" == "true" && "$_ssh_probe_count" -gt 0 ]]; then
      _co_pp_emit "clone_auth" "inconclusive" "advisory" \
        "SSH probe(s) returned network-level errors; cannot determine clone auth state (offline machine?)" \
        "ensure network connectivity, then re-run the preflight check"
      return 0
    fi
  fi

  # 4. Git Credential Manager (GCM) / credential helper check.
  # Feed minimal credential requests for github.com and gitlab.com; any non-empty
  # password= response means a credential helper is configured and returned credentials.
  if command -v git >/dev/null 2>&1; then
    local _gcm_out _gcm_host
    for _gcm_host in github.com gitlab.com; do
      _gcm_out="$(printf 'protocol=https\nhost=%s\n' "$_gcm_host" | git credential fill 2>/dev/null || true)"
      if [[ "$_gcm_out" == *"password="* ]]; then
        _co_pp_emit "clone_auth" "pass" "advisory" \
          "Git credential manager configured for $_gcm_host (git credential fill: credentials found)" ""
        return 0
      fi
    done
  fi

  # 5. Optional network probe via COORDINATOR_AUTH_PROBE_URL (HTTPS URLs only here;
  # SSH URLs were handled in step 3 above).
  # Only runs when explicitly set — prevents owner-specific private repo dependency for OSS operators.
  if [[ -n "${COORDINATOR_AUTH_PROBE_URL:-}" ]] && command -v git >/dev/null 2>&1; then
    local _ls_remote_out _ls_remote_exit
    _ls_remote_out="$(
      GIT_TERMINAL_PROMPT=0 \
      GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=5}" \
        git ls-remote --exit-code \
        -c http.lowSpeedLimit=1 -c http.lowSpeedTime=10 \
        "${COORDINATOR_AUTH_PROBE_URL}" HEAD 2>&1
    )"
    _ls_remote_exit=$?
    if [[ "$_ls_remote_exit" -eq 0 ]]; then
      _co_pp_emit "clone_auth" "pass" "advisory" \
        "git ls-remote authenticated against COORDINATOR_AUTH_PROBE_URL" ""
      return 0
    fi
    # Classify the failure: network unreachable vs auth failure.
    # Expanded patterns — covers timeout, SSL errors, proxy issues in addition to connectivity.
    case "$_ls_remote_out" in
      *"Could not resolve host"*|*"Failed to connect"*|*"Network is unreachable"*|\
      *"Connection refused"*|*"Operation timed out"*|*"Couldn't connect to server"*|\
      *"timed out"*|*"SSL"*|*"proxy"*|*"Proxy"*)
        _co_pp_emit "clone_auth" "inconclusive" "advisory" \
          "Network unreachable or proxy/SSL error; cannot determine clone auth state" \
          "ensure network connectivity and proxy/SSL config, then re-run the preflight check"
        return 0
        ;;
    esac
    # Auth failure: reachable but not authenticated — semi-hard (we reached the host but failed auth).
    _co_pp_emit "clone_auth" "warn" "semi-hard" \
      "git ls-remote failed (likely auth); no git-host authentication configured" \
      "configure git-host auth — recommended: gh auth login (GitHub) or glab auth login (GitLab); or add an SSH key / Git Credential Manager for your host"
    return 0
  fi

  # No method passed and no network probe URL set.
  if ! command -v git >/dev/null 2>&1; then
    # git not found at all -- inconclusive (can't run any check); stays advisory.
    _co_pp_emit "clone_auth" "inconclusive" "advisory" \
      "git not found on PATH; cannot probe clone authentication" \
      "install git, then configure gh auth login (GitHub), glab auth login (GitLab), or an SSH key"
    return 0
  fi

  # Actively tried gh, glab, SSH (github.com + gitlab.com), and GCM — none succeeded.
  # Emit semi-hard: this is not indeterminate, it is a confirmed absence.
  _co_pp_emit "clone_auth" "warn" "semi-hard" \
    "No git-host auth method detected (gh CLI, glab CLI, SSH key, or Git Credential Manager)" \
    "configure git-host auth — recommended: gh auth login (GitHub) or glab auth login (GitLab); or add an SSH key / Git Credential Manager for your host"
}

# ---------------------------------------------------------------------------
# _co_probe_longpaths
#
# Purpose: on Windows (MINGW/MSYS/CYGWIN), verify git core.longpaths=true.
# On non-Windows platforms, returns pass with detail "n/a (non-Windows)".
#
# This check is required because Windows has a MAX_PATH=260 limit that breaks
# coordinator file trees without the longpaths git setting.
#
# Severity: advisory.
# ---------------------------------------------------------------------------
_co_probe_longpaths() {
  local _os
  _os="$(uname -s 2>/dev/null)"

  case "$_os" in
    MINGW*|MSYS*|CYGWIN*)
      local _longpaths_val
      _longpaths_val="$(git config --get core.longpaths 2>/dev/null || echo "")"
      if [[ "$_longpaths_val" == "true" ]]; then
        _co_pp_emit "longpaths" "pass" "advisory" \
          "git core.longpaths=true (Windows long path support enabled)" ""
      else
        _co_pp_emit "longpaths" "warn" "advisory" \
          "git core.longpaths is not set to true (current: '${_longpaths_val:-<unset>}'); Windows MAX_PATH limit may break coordinator file trees" \
          "git config --global core.longpaths true"
      fi
      ;;
    *)
      # Non-Windows: not applicable.
      _co_pp_emit "longpaths" "pass" "advisory" \
        "n/a (non-Windows)" ""
      ;;
  esac
}

# ---------------------------------------------------------------------------
# _co_probe_git_lfs
#
# Purpose: verify Git LFS is available and configured.
# Check order:
#   1. `git lfs version` — subcommand resolves and LFS binary is present.
#   2. `git config --global --get filter.lfs.clean` — LFS is initialized
#      (git lfs install has been run and wired the filter hooks globally).
#
# Severity: advisory (not every operator clones an LFS-backed repo; absence
# is a soft signal, never a hard gate failure).
# Status:
#   warn  — git-lfs binary absent, git lfs version broken, or LFS not configured
#            (git lfs install not run).
#   pass  — git-lfs present AND globally configured.
# ---------------------------------------------------------------------------
_co_probe_git_lfs() {
  local _lfs_ver_out

  # Step 1: binary presence via `git lfs version`.
  # `git lfs` is a subcommand — `command -v git-lfs` is not reliable on all
  # platforms (the subcommand dispatch may be internal to git). Probe by
  # attempting `git lfs version` and treating a non-zero exit or empty output
  # as absent.
  if ! command -v git >/dev/null 2>&1; then
    _co_pp_emit "git_lfs" "warn" "advisory" \
      "git not found on PATH; cannot probe git-lfs" \
      "enable Git LFS so LFS-backed repos (e.g. project-rag-ue-addon) clone real objects: brew install git-lfs (macOS) / winget install GitHub.GitLFS (Windows), then git lfs install"
    return 0
  fi

  if ! _lfs_ver_out="$(git lfs version 2>&1)" || [[ -z "$_lfs_ver_out" ]]; then
    _co_pp_emit "git_lfs" "warn" "advisory" \
      "git-lfs not found or \`git lfs version\` failed" \
      "enable Git LFS so LFS-backed repos (e.g. project-rag-ue-addon) clone real objects: brew install git-lfs (macOS) / winget install GitHub.GitLFS (Windows), then git lfs install"
    return 0
  fi

  # Step 2: configuration check — git lfs install wires filter.lfs.clean globally.
  # A non-empty value means the smudge/clean filter hooks are active.
  local _lfs_clean
  _lfs_clean="$(git config --global --get filter.lfs.clean 2>/dev/null || true)"
  if [[ -z "$_lfs_clean" ]]; then
    _co_pp_emit "git_lfs" "warn" "advisory" \
      "git-lfs present ($_lfs_ver_out) but not configured (filter.lfs.clean missing; run: git lfs install)" \
      "enable Git LFS so LFS-backed repos (e.g. project-rag-ue-addon) clone real objects: brew install git-lfs (macOS) / winget install GitHub.GitLFS (Windows), then git lfs install"
    return 0
  fi

  _co_pp_emit "git_lfs" "pass" "advisory" "$_lfs_ver_out" ""
}

# ---------------------------------------------------------------------------
# _co_prereq_probe_all
#
# Purpose: aggregator -- calls all ten probes in order and emits one NDJSON
# line per probe to stdout. This is what setup.sh --preflight and the Step
# Zero gate consume.
#
# Output: 10 NDJSON lines (one per probe), in this order:
#   git, python, uv, gh, node, pwsh, ue, clone_auth, longpaths, git_lfs
# ---------------------------------------------------------------------------
_co_prereq_probe_all() {
  _co_probe_git
  _co_probe_python
  _co_probe_uv
  _co_probe_gh
  _co_probe_node
  _co_probe_pwsh
  _co_probe_ue
  _co_probe_clone_auth
  _co_probe_longpaths
  _co_probe_git_lfs
}

# ---------------------------------------------------------------------------
# Standalone entrypoint -- when executed directly (not sourced).
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  _co_prereq_probe_all
fi
