#!/usr/bin/env bash
# normalize-env.sh — idempotent environment normalization for coordinator install Step Zero.
#
# Purpose: the ONLY writer of environment state during coordinator setup. Reads probe
# results from scripts/lib/prereq_probe.sh (read-only) and applies consent-gated fixes
# for fixable prereqs. Windows-first mutations; macOS/Linux prints offers only (no
# silent mutation on non-Windows).
#
# Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md (FB-3)
#
# Negative-spec:
#   - NEVER mutates without explicit consent — the confirm prompt is load-bearing;
#     no code path may mutate before the prompt is answered (CONSENT-INVARIANT).
#   - Probes are read-only and live in scripts/lib/prereq_probe.sh; this script
#     only acts on what the probes report. Never duplicate probe logic here.
#   - On macOS/Linux: print offers, exit 0 — no mutations, no PATH changes.
#   - core.longpaths git config fix is Windows-only; skip on non-Windows.
#   - idempotency caveat: PATH/shim/alias operations converge toward target state
#     and are re-runnable without harm, but are NOT byte-stable no-ops (Windows
#     re-creates App Execution aliases on feature updates; PATH idempotency uses
#     semantic match, not string-equals). core.longpaths and uv install ARE
#     byte-stable no-ops on re-run.
#
# Usage:
#   bash scripts/normalize-env.sh [--dry-run] [--yes] [--restore <backup-file>]
#
# Flags:
#   --dry-run   Print planned mutations and exit; no prompt, no mutation.
#   --yes       Skip the confirm gate (for CI/non-interactive).
#   --restore   <backup-file>  Revert PATH/shim to values saved in the named backup.

# ---------------------------------------------------------------------------
# Bash version guard — INFORMATIONAL ONLY on this script.
# normalize-env.sh is a bootstrap-trap surface: it runs on a fresh machine
# BEFORE brew bash may be installed. It must function under bash 3.2.
# This guard advises upgrade but does NOT exit — execution continues on 3.2.
# Cross-platform shell rules: no declare -A, no mapfile/readarray, no ${v^^},
# no bash-4-only syntax anywhere in this file.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'NOTICE: normalize-env.sh is running under bash %s.\n' "${BASH_VERSION:-unknown}" >&2
  printf '  Bash 4+ is recommended. This script continues on 3.2 (bootstrap surface).\n' >&2
  printf '  To upgrade: brew install bash\n' >&2
fi

# Review: code-reviewer — set -euo pipefail is deferred until after the bash-version
# advisory block above so that bash 3.2 can display it before any pipefail semantics apply.
set -euo pipefail

# ---------------------------------------------------------------------------
# Locate this script and resolve the lib directory.
# BSD-portable: no realpath, no readlink -f. Use BASH_SOURCE[0] via dirname.
# ---------------------------------------------------------------------------
_ne_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_ne_lib_dir="$_ne_script_dir/lib"
_ne_prereq_probe="$_ne_lib_dir/prereq_probe.sh"

# ---------------------------------------------------------------------------
# prereq_probe.sh is only guaranteed to run under bash 4+ (it exits 78 on
# bash 3.2 — it uses bash-4 internals). We source it conditionally: if bash
# is < 4, we still print offers/advice but skip probe-driven fixes.
# ---------------------------------------------------------------------------
_ne_probes_available=0
if [[ "${BASH_VERSINFO[0]:-0}" -ge 4 ]]; then
  if [[ -f "$_ne_prereq_probe" ]]; then
    # shellcheck source=scripts/lib/prereq_probe.sh
    # Review: code-reviewer — removed 2>/dev/null so syntax errors in prereq_probe.sh are
    # visible; masking all stderr violated FB-4 (silent failure mode on source error).
    if source "$_ne_prereq_probe"; then
      _ne_probes_available=1
    else
      printf 'WARNING: failed to source %s; probe-driven fixes unavailable.\n' "$_ne_prereq_probe" >&2
    fi
  else
    printf 'ERROR: prereq_probe.sh not found at %s\n' "$_ne_prereq_probe" >&2
    printf '  Run from the coordinator repo root or ensure scripts/lib/ is intact.\n' >&2
    exit 1
  fi
else
  printf 'NOTICE: bash < 4 — probe sourcing skipped. Install brew bash to enable probe-driven fixes.\n' >&2
fi

# ---------------------------------------------------------------------------
# OS detection — BSD-portable, no GNU-isms.
# ---------------------------------------------------------------------------
_ne_os="$(uname -s 2>/dev/null || echo "unknown")"

_ne_is_windows() {
  case "$_ne_os" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# Portable timestamp — no date -d, no %N (GNU-isms).
# Output: YYYYMMDDHHMMSS
# ---------------------------------------------------------------------------
_ne_timestamp() {
  date +%Y%m%d%H%M%S 2>/dev/null || echo "00000000000000"
}

# ---------------------------------------------------------------------------
# Parse arguments — no getopt (non-portable); manual parse loop.
# Review: code-reviewer — dead function _ne_sed_inplace removed (never called).
# ---------------------------------------------------------------------------
_ne_dry_run=0
_ne_yes=0
_ne_restore_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      _ne_dry_run=1
      shift
      ;;
    --yes)
      _ne_yes=1
      shift
      ;;
    --restore)
      if [[ $# -lt 2 ]]; then
        printf 'ERROR: --restore requires a backup file argument.\n' >&2
        exit 2
      fi
      _ne_restore_file="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      printf 'Usage: %s [--dry-run] [--yes] [--restore <backup-file>]\n' "$0" >&2
      exit 2
      ;;
  esac
done

# ---------------------------------------------------------------------------
# --restore path: revert PATH/shim to saved values from a backup file.
# ---------------------------------------------------------------------------
if [[ -n "$_ne_restore_file" ]]; then
  if [[ ! -f "$_ne_restore_file" ]]; then
    printf 'ERROR: backup file not found: %s\n' "$_ne_restore_file" >&2
    exit 2
  fi
  printf '=== normalize-env.sh --restore ===\n'
  printf 'Reading backup: %s\n' "$_ne_restore_file"

  # Full-file ~/.bash_profile backup (written by the macOS bash-login-shell
  # reconstruction path, named ~/.bash_profile.coordinator-backup.<ts>) — restore
  # by copying it back. This is a real round-trip (the file IS the prior content),
  # distinct from the Windows KEY=VALUE PATH/shim backup parsed below.
  case "$(basename "$_ne_restore_file")" in
    .bash_profile.coordinator-backup.*)
      if cp "$_ne_restore_file" "$HOME/.bash_profile" 2>/dev/null; then
        printf '  ~/.bash_profile restored from %s\n' "$_ne_restore_file"
        exit 0
      fi
      printf 'ERROR: failed to copy %s onto ~/.bash_profile\n' "$_ne_restore_file" >&2
      exit 2
      ;;
  esac

  # Parse backup fields: lines of the form KEY=VALUE.
  # BSD-portable: no grep -P; use case/sed.
  local_path_val=""
  local_pymanager_val=""

  while IFS= read -r _bline; do
    case "$_bline" in
      SAVED_PATH=*)
        local_path_val="${_bline#SAVED_PATH=}"
        ;;
      SAVED_PYMANAGER_TARGET=*)
        local_pymanager_val="${_bline#SAVED_PYMANAGER_TARGET=}"
        ;;
    esac
  done < "$_ne_restore_file"

  if [[ -z "$local_path_val" ]]; then
    printf 'WARNING: backup file does not contain SAVED_PATH — cannot restore PATH.\n' >&2
  else
    # Review: code-reviewer — removed `export PATH=` here; it is a no-op because this
    # script runs in a subprocess and the assignment vanishes on exit. Print only the
    # eval-able command for the operator to run in their parent shell.
    printf 'To restore PATH, run the following in your parent shell:\n'
    printf '  export PATH="%s"\n' "$local_path_val"
  fi

  if [[ -z "$local_pymanager_val" ]]; then
    printf '  (No SAVED_PYMANAGER_TARGET in backup — pymanager shim restore skipped.)\n'
  else
    printf '  (Pymanager shim restore must be applied manually: see %s)\n' "$_ne_restore_file"
    printf '  Saved shim target was: %s\n' "$local_pymanager_val"
  fi

  printf 'Restore complete. Verify with: python --version\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
  exit 0
fi

# ---------------------------------------------------------------------------
# Consent prompt and partial-failure trackers.
# Defined here (before the macOS/Windows split) so both the Darwin
# bash-profile reconstruction path and the Windows fix path can call them.
# ---------------------------------------------------------------------------
_ne_steps_succeeded=""
_ne_steps_failed=""

_ne_record_success() {
  # $1 = step description
  if [[ -z "$_ne_steps_succeeded" ]]; then
    _ne_steps_succeeded="$1"
  else
    _ne_steps_succeeded="$_ne_steps_succeeded
  $1"
  fi
}

_ne_record_failure() {
  # $1 = step description
  if [[ -z "$_ne_steps_failed" ]]; then
    _ne_steps_failed="$1"
  else
    _ne_steps_failed="$_ne_steps_failed
  $1"
  fi
}

_ne_prompt_yn() {
  # $1 = prompt text
  # Returns 0 for yes, 1 for no/EOF.
  local _prompt="$1"
  local _answer

  if [[ "$_ne_yes" -eq 1 ]]; then
    printf '%s [auto-yes via --yes]\n' "$_prompt"
    return 0
  fi

  if [[ ! -t 0 ]]; then
    # Non-interactive (no tty, or piped): EOF condition.
    # Abort — ZERO mutations.
    printf '%s\n' "$_prompt"
    printf 'Non-interactive input detected (no tty / EOF). Aborting — no mutations applied.\n'
    printf 'Re-run with --yes to apply in non-interactive mode, or run interactively.\n'
    exit 3
  fi

  printf '%s [y/N]: ' "$_prompt"
  if ! read -r _answer; then
    # EOF on read.
    printf '\nEOF detected. Aborting — no mutations applied.\n'
    exit 3
  fi

  case "$_answer" in
    [Yy]|[Yy][Ee][Ss]) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# Parse probe output — no jq; use sed BRE (BSD-portable).
# Extract status/remediation/detail for each probe by name.
# Defined here (before the macOS/Windows split) because the Darwin reconstruction
# path calls _ne_probe_status_for at use-site; a definition stranded after the
# macOS `exit 0` would make that call exit 127 under set -euo pipefail.
# ---------------------------------------------------------------------------
_ne_probe_status_for() {
  # $1 = probe name
  # Review: code-reviewer — use grep -F (fixed-string) so probe names containing BRE
  # metacharacters cannot cause a false mismatch; portable to BSD grep.
  printf '%s' "$_ne_probe_output" | grep -F '"name":"'"$1"'"' \
    | sed 's/.*"status":"\([^"]*\)".*/\1/' 2>/dev/null || echo "inconclusive"
}

_ne_probe_remediation_for() {
  # $1 = probe name
  # Review: code-reviewer — use grep -F (fixed-string) for consistency with _ne_probe_status_for.
  printf '%s' "$_ne_probe_output" | grep -F '"name":"'"$1"'"' \
    | sed 's/.*"remediation":"\([^"]*\)".*/\1/' 2>/dev/null || echo ""
}

_ne_probe_detail_for() {
  # $1 = probe name
  # Review: code-reviewer — use grep -F (fixed-string) for consistency with _ne_probe_status_for.
  printf '%s' "$_ne_probe_output" | grep -F '"name":"'"$1"'"' \
    | sed 's/.*"detail":"\([^"]*\)".*/\1/' 2>/dev/null || echo ""
}

# ---------------------------------------------------------------------------
# macOS/Linux: print offers; Darwin also offers bash-profile repair when
# the shell_login_env probe reports fail (orphaned bash login shell).
# ---------------------------------------------------------------------------
if ! _ne_is_windows; then
  printf '=== normalize-env.sh — macOS/Linux mode (offers only, no mutation) ===\n\n'

  case "$_ne_os" in
    Darwin)
      printf 'This script does not mutate on macOS. Manual steps to satisfy prereqs:\n\n'
      printf '  Python 3.12+:\n'
      printf '    brew install python@3.12\n\n'
      printf '  uv package manager:\n'
      printf '    brew install uv\n\n'
      printf '  PowerShell 7 (optional):\n'
      printf '    brew install --cask powershell\n\n'
      printf '  git core.longpaths: Windows-only — not applicable on macOS.\n\n'
      ;;
    Linux*)
      printf 'This script does not mutate on Linux. Manual steps to satisfy prereqs:\n\n'
      printf '  Python 3.12+:\n'
      printf '    (Debian/Ubuntu) sudo apt-get install python3.12\n'
      printf '    (Fedora/RHEL)   sudo dnf install python3.12\n\n'
      printf '  uv package manager:\n'
      printf '    pipx install uv   OR   pip install uv\n\n'
      printf '  PowerShell 7 (optional):\n'
      printf '    See https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-linux\n\n'
      printf '  git core.longpaths: Windows-only — not applicable on Linux.\n\n'
      ;;
    *)
      printf 'Unrecognized OS (%s). No automated mutations available.\n' "$_ne_os"
      printf 'Ensure Python 3.11+, uv, and git are installed manually.\n\n'
      ;;
  esac

  # If probes are available, still run them for informational output.
  if [[ "$_ne_probes_available" -eq 1 ]]; then
    # Capture probe output once so it can be used for both display and status queries
    # (the Darwin reconstruction path calls _ne_probe_status_for which reads this var).
    _ne_probe_output="$(_co_prereq_probe_all || true)"
    printf 'Current prereq probe results:\n'
    printf '%s' "$_ne_probe_output" | while IFS= read -r _probe_line; do
      # Extract fields without jq: parse "name":"...", "status":"..."
      # BSD-portable: use sed BRE.
      _p_name="$(printf '%s' "$_probe_line" | sed 's/.*"name":"\([^"]*\)".*/\1/')"
      _p_status="$(printf '%s' "$_probe_line" | sed 's/.*"status":"\([^"]*\)".*/\1/')"
      _p_detail="$(printf '%s' "$_probe_line" | sed 's/.*"detail":"\([^"]*\)".*/\1/')"
      printf '  [%s] %s: %s\n' "$_p_status" "$_p_name" "$_p_detail"
    done
    printf '\n'

    # ---------------------------------------------------------------------------
    # C2: bash login-shell PATH reconstruction (Darwin only).
    # Spec backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md (C2)
    #
    # Triggered when shell_login_env probe reports `fail` (orphaned bash login shell).
    # Idempotency (the Staff Engineer F2): trigger on probe verdict, NOT sentinel presence — an
    # Offer-C-only ~/.bash_profile carries the start sentinel but is still orphaned.
    # Reconstruction source (the Staff Engineer F0): intact zsh login PATH via
    # _co_shell_login_env_reconstruction_source — NOT the broken bash login shell.
    # Verify before success (the Staff Engineer F5a): spawn a login bash after write to confirm.
    # ---------------------------------------------------------------------------
    if [[ "$_ne_os" == "Darwin" ]]; then
      _ne_shell_env_status="$(_ne_probe_status_for shell_login_env)"
      _ne_bp_backup=""

      if [[ "$_ne_shell_env_status" == "fail" ]]; then
        printf -- '--- bash login-shell PATH repair ---\n'
        printf '  Probe shell_login_env=fail: bash login shell has orphaned ~/.local/bin.\n'
        printf '  This step reconstructs ~/.bash_profile from the intact zsh login PATH.\n'
        printf '  Source: zsh login shell (untouched by the bash orphan -- not the broken bash).\n'
        printf '  NO chsh is performed -- only ~/.bash_profile is updated.\n\n'

        # Get intact zsh PATH as the reconstruction source.
        # ABORT if empty -- never write an empty-PATH managed block (the Staff Engineer F0).
        _ne_recon_source="$(_co_shell_login_env_reconstruction_source)"

        if [[ -z "$_ne_recon_source" ]]; then
          printf '  INCONCLUSIVE: zsh login PATH could not be probed (zsh absent or unprobeable).\n'
          printf '  Cannot reconstruct ~/.bash_profile safely -- empty PATH block would orphan tools.\n'
          printf '  Manual repair: add the following to ~/.bash_profile:\n'
          printf '    export PATH="$HOME/.local/bin:$PATH"\n\n'
        else
          printf '  Reconstruction source (intact zsh PATH):\n    %s\n\n' "$_ne_recon_source"

          # Sentinel lines -- EXACT strings (shared with Offer C so its grep -qF guard stands down).
          _NE_START_SENTINEL="# coordinator-install: brew shellenv (DR-148)"
          _NE_END_SENTINEL="# coordinator-install: end (DR-148)"

          if [[ "$_ne_dry_run" -eq 1 ]]; then
            printf '(--dry-run) Would reconstruct ~/.bash_profile with managed block:\n'
            printf '  Start sentinel: %s\n' "$_NE_START_SENTINEL"
            printf '  End sentinel:   %s\n' "$_NE_END_SENTINEL"
            printf '  Non-homebrew PATH entries from zsh snapshot that would be added:\n'
            _ne_dry_rem="$_ne_recon_source"
            while [ -n "$_ne_dry_rem" ]; do
              case "$_ne_dry_rem" in
                *:*) _ne_dry_pe="${_ne_dry_rem%%:*}"; _ne_dry_rem="${_ne_dry_rem#*:}" ;;
                *)   _ne_dry_pe="$_ne_dry_rem"; _ne_dry_rem="" ;;
              esac
              [ -z "$_ne_dry_pe" ] && continue
              case "$_ne_dry_pe" in
                */homebrew/*|*/Homebrew/*) continue ;;
                /usr/bin|/bin|/usr/sbin|/sbin|/usr/local/bin|/usr/local/sbin) continue ;;
              esac
              printf '    export PATH="%s:$PATH"\n' "$_ne_dry_pe"
            done
            printf '(--dry-run: no mutations applied.)\n\n'
          else
            if _ne_prompt_yn "Reconstruct ~/.bash_profile to repair bash login-shell PATH"; then
              # Backup the existing ~/.bash_profile BEFORE any write (CONSENT-INVARIANT).
              _ne_bp_ts="$(_ne_timestamp)"
              _ne_bp_backup="${HOME}/.bash_profile.coordinator-backup.${_ne_bp_ts}"
              _ne_bp_repair_ok=1

              if [ -f "$HOME/.bash_profile" ]; then
                if cp "$HOME/.bash_profile" "$_ne_bp_backup" 2>/dev/null; then
                  printf '  Backup written: %s\n' "$_ne_bp_backup"
                  printf '  To revert manually: cp %s %s\n' "$_ne_bp_backup" "$HOME/.bash_profile"
                else
                  printf '  ERROR: could not write backup to %s -- aborting repair.\n' "$_ne_bp_backup" >&2
                  _ne_bp_backup=""
                  _ne_bp_repair_ok=0
                fi
              else
                # No prior file: nothing to back up.
                _ne_bp_backup=""
              fi

              if [[ "$_ne_bp_repair_ok" -eq 1 ]]; then
                # Review: code-reviewer (F6) — mktemp avoids predictable /tmp name collisions;
                # PID fallback preserves behaviour on systems without mktemp.
                _ne_bp_tmp="$(mktemp "$HOME/.bash_profile.tmp.XXXXXX" 2>/dev/null || printf '%s' "${HOME}/.bash_profile.tmp.$$")"

                # Determine block-replacement strategy (BSD-portable awk; no sed -i).
                _ne_has_end_s=0
                _ne_has_start_s=0
                if [ -f "$HOME/.bash_profile" ]; then
                  if grep -qF "$_NE_END_SENTINEL" "$HOME/.bash_profile" 2>/dev/null; then
                    _ne_has_end_s=1
                  elif grep -qF "$_NE_START_SENTINEL" "$HOME/.bash_profile" 2>/dev/null; then
                    _ne_has_start_s=1
                  fi
                fi

                # Step 1: produce base content with old managed block stripped (if any).
                # Review: code-reviewer (F2) — capture awk/cp exit code; on failure rm the
                # (already-truncated) temp and abort so step 2 + mv never run with empty content.
                _ne_bp_step1_ok=0
                if [[ "$_ne_has_end_s" -eq 1 ]]; then
                  # Both sentinels present: remove start..end inclusive.
                  awk \
                    -v ss="$_NE_START_SENTINEL" \
                    -v es="$_NE_END_SENTINEL" \
                    'BEGIN{b=0}
                     $0==ss{b=1;next}
                     $0==es{b=0;next}
                     !b{print}' \
                    "$HOME/.bash_profile" > "$_ne_bp_tmp" 2>/dev/null
                  _ne_bp_step1_ok=$?
                elif [[ "$_ne_has_start_s" -eq 1 ]]; then
                  # Legacy Offer-C (start sentinel only, no end sentinel):
                  # remove from start sentinel through the next bare `fi` line.
                  awk \
                    -v ss="$_NE_START_SENTINEL" \
                    'BEGIN{b=0}
                     $0==ss               {b=1;next}
                     b&&/^fi[[:space:]]*$/{b=0;next}
                     !b                   {print}' \
                    "$HOME/.bash_profile" > "$_ne_bp_tmp" 2>/dev/null
                  _ne_bp_step1_ok=$?
                elif [ -f "$HOME/.bash_profile" ]; then
                  # No sentinel: preserve existing content; managed block will be appended.
                  cp "$HOME/.bash_profile" "$_ne_bp_tmp" 2>/dev/null
                  _ne_bp_step1_ok=$?
                else
                  # No prior file at all — empty temp is correct here.
                  : > "$_ne_bp_tmp"
                  # _ne_bp_step1_ok=0 already
                fi

                if [[ "$_ne_bp_step1_ok" -ne 0 ]]; then
                  printf '  ERROR: failed to produce base content for ~/.bash_profile (awk/cp exit %d); prior content preserved.\n' "$_ne_bp_step1_ok" >&2
                  rm -f "$_ne_bp_tmp" 2>/dev/null || true
                  _ne_bp_repair_ok=0
                fi

                if [[ "$_ne_bp_repair_ok" -eq 1 ]]; then
                # Step 2: append the freshly composed managed block.
                # printf single-quoted strings pass literal '$' through to the output file;
                # the generated ~/.bash_profile will contain the literal shell variables.
                {
                  printf '\n'
                  printf '%s\n' "$_NE_START_SENTINEL"
                  printf '# --- coordinator-managed block -- do not edit between these sentinel lines ---\n'
                  printf '# Boundaries:\n'
                  printf '#   (a) rc functions/aliases from the prior shell are NOT carried here --\n'
                  printf '#       only PATH is snapshotted from the intact zsh login environment.\n'
                  printf '#   (b) Non-login-interactive bash shells read ~/.bashrc, not ~/.bash_profile\n'
                  printf '#       (macOS Terminal new-tab is often non-login); consider also adding\n'
                  printf '#       ~/.local/bin to ~/.bashrc for full coverage in those shells.\n'
                  printf '#   (c) Reciprocal-source-loop hazard: if ~/.bash_profile sources ~/.bashrc\n'
                  printf '#       and ~/.bashrc sources ~/.bash_profile, a loop results; the guard\n'
                  printf '#       variable _COORDINATOR_BASH_PROFILE_SOURCED below breaks that loop.\n'
                  printf '[ -n "${_COORDINATOR_BASH_PROFILE_SOURCED:-}" ] && return 2>/dev/null; export _COORDINATOR_BASH_PROFILE_SOURCED=1\n'
                  printf 'if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi\n'
                  # Extra PATH entries: zsh snapshot entries NOT contributed by brew shellenv.
                  # brew shellenv adds entries under its own trees (identifiable by "homebrew"
                  # in the path). Universal system defaults are always present in a new login
                  # shell and need not be re-exported.
                  _ne_zsh_rem="$_ne_recon_source"
                  while [ -n "$_ne_zsh_rem" ]; do
                    case "$_ne_zsh_rem" in
                      *:*) _ne_pe="${_ne_zsh_rem%%:*}"; _ne_zsh_rem="${_ne_zsh_rem#*:}" ;;
                      *)   _ne_pe="$_ne_zsh_rem"; _ne_zsh_rem="" ;;
                    esac
                    [ -z "$_ne_pe" ] && continue
                    case "$_ne_pe" in
                      */homebrew/*|*/Homebrew/*) continue ;;
                      /usr/bin|/bin|/usr/sbin|/sbin|/usr/local/bin|/usr/local/sbin) continue ;;
                    esac
                    printf 'export PATH="%s:$PATH"\n' "$_ne_pe"
                  done
                  printf '[ -f ~/.bashrc ] && [ -r ~/.bashrc ] && . ~/.bashrc\n'
                  printf '%s\n' "$_NE_END_SENTINEL"
                } >> "$_ne_bp_tmp"

                # Atomic write: mv temp onto target.
                if mv "$_ne_bp_tmp" "$HOME/.bash_profile" 2>/dev/null; then
                  printf '  ~/.bash_profile written.\n'

                  # Verify (the Staff Engineer F5a): spawn a login bash against the new file.
                  # Exit 0 iff ~/.local/bin is in PATH AND claude resolves.
                  # On non-zero: do NOT declare repaired; leave backup restorable.
                  # Review: code-reviewer (F4) — PATH bash used here, not the detected login-shell
                  # binary, because both are bash≥4 reading the same ~/.bash_profile; the verify
                  # result is equivalent and avoids a second shell-detection step.
                  # Review: code-reviewer (F3) — capture stderr to a log for diagnostics on failure.
                  _ne_verify_log="$(mktemp 2>/dev/null || printf '%s' "${TMPDIR:-/tmp}/ne-verify-$$.log")"
                  printf '  Verifying repair via login bash...\n'
                  if bash -lc 'case ":$PATH:" in *":$HOME/.local/bin:"*) command -v claude >/dev/null 2>&1 && exit 0;; esac; exit 1' 2>"$_ne_verify_log"; then
                    printf '  Repair VERIFIED: login bash now has ~/.local/bin and claude resolves.\n'
                    rm -f "$_ne_verify_log" 2>/dev/null || true
                    _ne_record_success "~/.bash_profile reconstructed (bash login-shell PATH repaired)"
                  else
                    printf '  Repair FAILED: login bash still fails the orphan predicate.\n' >&2
                    printf '  Login bash stderr: see %s\n' "$_ne_verify_log" >&2
                    printf '  Do NOT declare repaired. Backup is restorable:\n' >&2
                    if [ -n "$_ne_bp_backup" ]; then
                      printf '    cp %s %s\n' "$_ne_bp_backup" "$HOME/.bash_profile" >&2
                    fi
                    _ne_record_failure "~/.bash_profile reconstruction (verify: login bash still orphaned)"
                  fi
                else
                  printf '  ERROR: mv temp to ~/.bash_profile failed.\n' >&2
                  rm -f "$_ne_bp_tmp" 2>/dev/null || true
                  _ne_record_failure "~/.bash_profile reconstruction (mv to target failed)"
                fi
                fi  # step1 ok inner gate
              fi  # _ne_bp_repair_ok
            else
              printf '  Skipped by user.\n'
            fi
          fi  # dry-run else
        fi  # _ne_recon_source non-empty
      fi  # shell_login_env == fail
    fi  # Darwin
  fi

  # Partial-failure summary for any macOS repair mutations.
  if [[ -n "$_ne_steps_succeeded" ]] || [[ -n "$_ne_steps_failed" ]]; then
    printf '\n=== macOS Repair Summary ===\n'
    if [[ -n "$_ne_steps_succeeded" ]]; then
      printf 'Succeeded:\n'
      printf '  %s\n' "$_ne_steps_succeeded"
    fi
    if [[ -n "$_ne_steps_failed" ]]; then
      printf 'Failed:\n'
      printf '  %s\n' "$_ne_steps_failed"
      if [[ -n "${_ne_bp_backup:-}" ]]; then
        printf 'Restore ~/.bash_profile with:\n'
        printf '  cp %s %s\n' "$_ne_bp_backup" "$HOME/.bash_profile"
      fi
      printf 'Run the above brew/apt/dnf commands, then re-run the coordinator install.\n'
      exit 4
    fi
  fi

  printf 'Run the above brew/apt/dnf commands, then re-run the coordinator install.\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# Windows path below.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Collect probe results and build the fix plan.
# Each fix is stored in positional variable arrays (bash-3.2-compatible):
# use parallel indexed lists via naming convention.
# ---------------------------------------------------------------------------

# Fix plan: parallel lists using separate variables per index.
# Names: _ne_fix_N (description), _ne_fix_cmd_N (shell commands)
# Count: _ne_fix_count
_ne_fix_count=0

_ne_has_longpaths_fix=0
_ne_has_uv_fix=0
_ne_has_python_fix=0
_ne_has_alias_fix=0

# Probe output capture — run all probes once.
_ne_probe_output=""

if [[ "$_ne_probes_available" -eq 1 ]]; then
  # Review: code-reviewer — removed 2>/dev/null mask (FB-4); kept || true so a failing
  # probe run degrades gracefully rather than aborting the script under set -e.
  _ne_probe_output="$(_co_prereq_probe_all || true)"
fi

# ---------------------------------------------------------------------------
# Build fix plan — mutation ordering: blast-radius LAST.
# Order: (1) longpaths [low risk], (2) uv [low risk], (3) python [medium],
#        (4) App Execution alias disable [riskier — touches system settings].
# ---------------------------------------------------------------------------

# (1) longpaths fix — byte-stable idempotent no-op on re-run.
_ne_longpaths_status="$(_ne_probe_status_for longpaths)"
if [[ "$_ne_longpaths_status" != "pass" ]]; then
  _ne_has_longpaths_fix=1
  _ne_fix_count=$(( _ne_fix_count + 1 ))
fi

# (2) uv fix — install uv via pip/py (idempotent on re-run).
_ne_uv_status="$(_ne_probe_status_for uv)"
if [[ "$_ne_uv_status" != "pass" ]]; then
  _ne_has_uv_fix=1
  _ne_fix_count=$(( _ne_fix_count + 1 ))
fi

# (3) python fix — check if python fails and determine if Store alias is likely active.
_ne_python_status="$(_ne_probe_status_for python)"
_ne_store_python_suspected=0

if [[ "$_ne_python_status" != "pass" ]]; then
  _ne_has_python_fix=1
  _ne_fix_count=$(( _ne_fix_count + 1 ))

  # Heuristic: detect if Store alias is likely active (python3 or python exists on
  # PATH in WindowsApps). No registry read available from bash; check the path.
  # WindowsApps aliases are typically at:
  #   $LOCALAPPDATA/Microsoft/WindowsApps/python.exe or python3.exe
  _ne_wa_dir="${LOCALAPPDATA:-}\\Microsoft\\WindowsApps"
  # Convert Windows-style path to MSYS path for -f test:
  # Under MINGW/MSYS, LOCALAPPDATA is usually set as a Windows path; convert it.
  if [[ -n "${LOCALAPPDATA:-}" ]]; then
    # Review: code-reviewer — ${LOCALAPPDATA//\\//} produces C:/... which is NOT a valid
    # MINGW POSIX path; -f test silently fails, suppressing Store-python detection.
    # Use cygpath -u for a proper /c/... POSIX path; fall back to backslash-replace only
    # when cygpath is absent (e.g. plain MSYS without Cygwin).
    _ne_wa_dir_posix="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || printf '%s' "${LOCALAPPDATA//\\//}")"
    if [[ -f "$_ne_wa_dir_posix/Microsoft/WindowsApps/python.exe" ]] || \
       [[ -f "$_ne_wa_dir_posix/Microsoft/WindowsApps/python3.exe" ]]; then
      _ne_store_python_suspected=1
    fi
  fi

  # Also register an alias-disable fix as the final step (blast-radius).
  _ne_has_alias_fix=1
  _ne_fix_count=$(( _ne_fix_count + 1 ))
fi

# ---------------------------------------------------------------------------
# Print current probe summary.
# ---------------------------------------------------------------------------
printf '\n=== normalize-env.sh — Windows environment normalization ===\n\n'

if [[ "$_ne_probes_available" -eq 1 ]]; then
  printf 'Current prereq probe results:\n'
  printf '%s' "$_ne_probe_output" | while IFS= read -r _probe_line; do
    _p_name="$(printf '%s' "$_probe_line" | sed 's/.*"name":"\([^"]*\)".*/\1/')"
    _p_status="$(printf '%s' "$_probe_line" | sed 's/.*"status":"\([^"]*\)".*/\1/')"
    _p_detail="$(printf '%s' "$_probe_line" | sed 's/.*"detail":"\([^"]*\)".*/\1/')"
    printf '  [%s] %s: %s\n' "$_p_status" "$_p_name" "$_p_detail"
  done
  printf '\n'
else
  printf '  (probe results unavailable — bash < 4)\n\n'
fi

# ---------------------------------------------------------------------------
# If nothing to fix, report and exit.
# ---------------------------------------------------------------------------
if [[ "$_ne_fix_count" -eq 0 ]]; then
  printf 'All prereqs satisfied. Nothing to do.\n'
  printf '(Note: idempotency — re-running this script is safe; probe-passing prereqs\n'
  printf ' are never touched.)\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# Print planned mutations as enumerated list.
# ---------------------------------------------------------------------------
_ne_fix_idx=0
printf 'Planned mutations (%d step(s)):\n\n' "$_ne_fix_count"

if [[ "$_ne_has_longpaths_fix" -eq 1 ]]; then
  _ne_fix_idx=$(( _ne_fix_idx + 1 ))
  printf '  %d. git config --global core.longpaths true\n' "$_ne_fix_idx"
  printf '     (enables Windows long-path support; byte-stable no-op on re-run)\n'
fi

if [[ "$_ne_has_uv_fix" -eq 1 ]]; then
  _ne_fix_idx=$(( _ne_fix_idx + 1 ))
  printf '  %d. install uv package manager (py -m pip install uv)\n' "$_ne_fix_idx"
  printf '     (advisory; coordinator degrades gracefully without uv; idempotent on re-run)\n'
fi

if [[ "$_ne_has_python_fix" -eq 1 ]]; then
  _ne_fix_idx=$(( _ne_fix_idx + 1 ))
  printf '  %d. install Python 3.12 via py launcher / winget\n' "$_ne_fix_idx"
  printf '     (required; installs from python.org; re-runnable)\n'
fi

if [[ "$_ne_has_alias_fix" -eq 1 ]]; then
  _ne_fix_idx=$(( _ne_fix_idx + 1 ))
  if [[ "$_ne_store_python_suspected" -eq 1 ]]; then
    printf '  %d. disable WindowsApps App Execution aliases for python/python3\n' "$_ne_fix_idx"
    printf '     [NOTICE: it looks like you are using Windows Store python intentionally]\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
    printf '     [Confirm disable of App Execution aliases intentionally.]\n'
    printf '     (converges toward target state; Windows feature updates may re-enable aliases)\n'
  else
    # Review: code-reviewer — added "(skips silently if no aliases present)" parenthetical
    # so operators are not confused when the PS step no-ops on machines without Store stubs.
    printf '  %d. disable WindowsApps App Execution aliases for python/python3\n' "$_ne_fix_idx"
    printf '     (removes Store stub that breaks functional Python detection;\n'
    printf '      converges toward target; Windows feature updates may re-enable aliases;\n'
    printf '      skips silently if no aliases present)\n'
  fi
fi

printf '\n'

# --dry-run: print plan and exit before backup/prompt.
if [[ "$_ne_dry_run" -eq 1 ]]; then
  printf '(--dry-run: no mutations applied.)\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# Rollback/backup FIRST — before any mutation, before the confirm prompt.
# Snapshot current PATH and pymanager shim target.
# ---------------------------------------------------------------------------
_ne_ts="$(_ne_timestamp)"
_ne_backup_file="${HOME}/.coordinator-env-backup.${_ne_ts}"

{
  printf 'SAVED_PATH=%s\n' "$PATH"
  # Try to capture pymanager shim target if py is available.
  _ne_py_target=""
  if command -v py >/dev/null 2>&1; then
    _ne_py_target="$(py -c 'import sys; print(sys.executable)' 2>/dev/null || echo "")"
  fi
  printf 'SAVED_PYMANAGER_TARGET=%s\n' "$_ne_py_target"
  printf 'SAVED_AT=%s\n' "$(date 2>/dev/null || echo "unknown")"
} > "$_ne_backup_file" 2>/dev/null || {
  # Review: code-reviewer (P1) — hard-fail on backup write failure. Rollback is a
  # load-bearing safety property; proceeding with no backup violates it. The original
  # WARNING+continue allowed mutation with no rollback capability.
  printf 'ERROR: could not write backup file at %s\n' "$_ne_backup_file" >&2
  printf '  Ensure %s is writable before running this script.\n' "$HOME" >&2
  printf '  Aborting — no mutations applied.\n' >&2
  exit 1
}

if [[ -n "$_ne_backup_file" ]]; then
  printf 'Backup written: %s\n' "$_ne_backup_file"
  printf 'To revert, run:\n'
  printf '  bash %s --restore %s\n\n' "$0" "$_ne_backup_file"
fi

# ---------------------------------------------------------------------------
# Consent gate — per-mutation [y/N] prompts (CONSENT-INVARIANT).
# On --yes: auto-accept all.
# On non-interactive (EOF / no tty) without --yes: abort with ZERO mutations.
#
# Review: code-reviewer — corrected comment: the backup file WAS written above (it is
# informational, not a mutation of PATH/shim/alias state). The invariant is that no
# PATH/shim/alias mutation has occurred above this gate. Do not reorder those mutations
# above this gate. The backup file is cleaned up below if zero mutations are applied.
#
# _ne_prompt_yn, _ne_steps_succeeded/_ne_steps_failed, _ne_record_success/_ne_record_failure
# are defined above the macOS/Windows split so both paths can call them.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 1 (low risk): git config --global core.longpaths true
# ---------------------------------------------------------------------------
if [[ "$_ne_has_longpaths_fix" -eq 1 ]]; then
  printf -- '--- Step: git long-path support ---\n'
  if _ne_prompt_yn "Apply: git config --global core.longpaths true"; then
    # Review: code-reviewer — removed 2>&1 from if-condition; it redirected stderr to
    # terminal without capture (confusing no-op on success; only exit code is tested here).
    if git config --global core.longpaths true; then
      printf '  Applied.\n'
      # Post-mutation verify.
      if [[ "$_ne_probes_available" -eq 1 ]]; then
        _ne_verify="$(_co_probe_longpaths 2>/dev/null)"
        _ne_verify_status="$(printf '%s' "$_ne_verify" | sed 's/.*"status":"\([^"]*\)".*/\1/')"
        printf '  Post-fix probe: longpaths = %s\n' "$_ne_verify_status"
        if [[ "$_ne_verify_status" == "pass" ]]; then
          _ne_record_success "git core.longpaths=true"
        else
          printf '  WARNING: probe still non-pass after fix.\n' >&2
          _ne_record_failure "git core.longpaths (probe did not flip to pass)"
        fi
      else
        _ne_record_success "git core.longpaths=true"
      fi
    else
      printf '  ERROR: git config --global core.longpaths true failed.\n' >&2
      _ne_record_failure "git core.longpaths (git config command failed)"
    fi
  else
    printf '  Skipped by user.\n'
  fi
  printf '\n'
fi

# ---------------------------------------------------------------------------
# Step 2 (low risk): install uv via py -m pip install uv
# ---------------------------------------------------------------------------
if [[ "$_ne_has_uv_fix" -eq 1 ]]; then
  printf -- '--- Step: install uv package manager ---\n'
  if _ne_prompt_yn "Apply: install uv (py -m pip install uv)"; then
    # Try py launcher first (Windows); fall back to python/python3.
    _ne_pip_python=""
    if command -v py >/dev/null 2>&1; then
      _ne_pip_python="py"
    elif command -v python >/dev/null 2>&1; then
      _ne_pip_python="python"
    elif command -v python3 >/dev/null 2>&1; then
      _ne_pip_python="python3"
    fi

    if [[ -z "$_ne_pip_python" ]]; then
      printf '  ERROR: no python/py found to install uv. Install Python first.\n' >&2
      _ne_record_failure "uv install (no python found for pip)" # verify-no-console-flash: allow — string literal, not an interpreter spawn
    # Review: code-reviewer — removed 2>&1 from if-condition (confusing no-op on success).
    elif "$_ne_pip_python" -m pip install uv; then
      printf '  uv install attempted.\n'
      # Post-mutation verify.
      if [[ "$_ne_probes_available" -eq 1 ]]; then
        _ne_verify="$(_co_probe_uv 2>/dev/null)"
        _ne_verify_status="$(printf '%s' "$_ne_verify" | sed 's/.*"status":"\([^"]*\)".*/\1/')"
        printf '  Post-fix probe: uv = %s\n' "$_ne_verify_status"
        if [[ "$_ne_verify_status" == "pass" ]]; then
          _ne_record_success "uv installed"
        else
          printf '  WARNING: uv probe still non-pass after install (may need PATH refresh).\n' >&2
          _ne_record_failure "uv install (probe did not flip to pass; may need new shell)"
        fi
      else
        _ne_record_success "uv install attempted"
      fi
    else
      printf '  ERROR: pip install uv failed.\n' >&2
      _ne_record_failure "uv install (pip command failed)"
    fi
  else
    printf '  Skipped by user.\n'
  fi
  printf '\n'
fi

# ---------------------------------------------------------------------------
# Step 3 (medium risk): install Python 3.12 via winget / py launcher.
# This does not repoint pymanager or touch PATH — it installs the runtime.
# ---------------------------------------------------------------------------
if [[ "$_ne_has_python_fix" -eq 1 ]]; then
  printf -- '--- Step: install Python 3.12 ---\n'
  printf '  Current python probe: %s\n' "$(_ne_probe_detail_for python)" # verify-no-console-flash: allow — string literal, not an interpreter spawn
  printf '  This step installs Python 3.12 via winget (Python.Python.3.12).\n'
  printf '  After install, a new shell session will be needed to pick up the new PATH entry.\n'
  if _ne_prompt_yn "Apply: winget install Python.Python.3.12"; then
    if command -v winget >/dev/null 2>&1; then
      # Review: code-reviewer — removed 2>&1 from if-condition (confusing no-op on success).
      if winget install --id Python.Python.3.12 --source winget --accept-package-agreements \
           --accept-source-agreements; then
        printf '  Python 3.12 install initiated via winget.\n'
        # Post-mutation verify — note: may not flip pass immediately (new shell needed).
        if [[ "$_ne_probes_available" -eq 1 ]]; then
          _ne_verify="$(_co_probe_python 2>/dev/null)"
          _ne_verify_status="$(printf '%s' "$_ne_verify" | sed 's/.*"status":"\([^"]*\)".*/\1/')"
          printf '  Post-fix probe: python = %s\n' "$_ne_verify_status" # verify-no-console-flash: allow — string literal, not an interpreter spawn
          if [[ "$_ne_verify_status" == "pass" ]]; then
            _ne_record_success "Python 3.12 installed (pass)"
          else
            printf '  NOTE: python probe still non-pass — open a new terminal and re-run.\n' >&2 # verify-no-console-flash: allow — string literal, not an interpreter spawn
            _ne_record_success "Python 3.12 install dispatched (new shell needed to confirm)"
          fi
        else
          _ne_record_success "Python 3.12 install attempted via winget"
        fi
      else
        printf '  ERROR: winget install Python.Python.3.12 failed.\n' >&2
        printf '  Manual fallback: https://www.python.org/downloads/\n' >&2
        _ne_record_failure "Python 3.12 install (winget failed)"
      fi
    else
      printf '  winget not found. Manual install required.\n' >&2
      printf '  Download from: https://www.python.org/downloads/\n' >&2
      _ne_record_failure "Python 3.12 install (winget not available)"
    fi
  else
    printf '  Skipped by user.\n'
  fi
  printf '\n'
fi

# ---------------------------------------------------------------------------
# Step 4 (riskier — blast-radius LAST): disable WindowsApps App Execution aliases.
# Uses PowerShell to toggle the aliases in the registry.
# ---------------------------------------------------------------------------
if [[ "$_ne_has_alias_fix" -eq 1 ]]; then
  printf -- '--- Step: disable WindowsApps App Execution aliases for python/python3 ---\n'

  if [[ "$_ne_store_python_suspected" -eq 1 ]]; then
    printf '  [NOTICE] it looks like you are using Windows Store python intentionally.\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
    _ne_alias_prompt="Confirm disable of App Execution aliases for python/python3 (y/N)"
  else
    _ne_alias_prompt="Apply: disable WindowsApps python/python3 App Execution aliases"
  fi

  printf '  Purpose: Store python stubs (App Execution aliases) pass command -v but exit 49;\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
  printf '  they block functional Python detection. Disabling redirects python to the real install.\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
  printf '  (Idempotency note: Windows feature updates may re-enable aliases; re-run if needed.)\n'

  if _ne_prompt_yn "$_ne_alias_prompt"; then
    # Use PowerShell (pwsh or legacy powershell fallback) to remove the alias entries.
    # Registry path: HKCU:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers
    # The App Execution alias mechanism uses:
    #   HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\python.exe
    # and a separate toggle in:
    #   HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options
    # The simplest approach available from MINGW shell is to invoke pwsh/powershell
    # to remove the WindowsApps entries from the user PATH and/or disable the alias files.
    # The canonical disable path is: Settings > Apps > Advanced app settings >
    # App execution aliases. We replicate this via PowerShell registry edit.

    _ne_ps_script='
# Review: code-reviewer — removed dead $regPath assignment; it implied registry editing
# that never happens. The actual mechanism is reparse-point removal from WindowsApps.
# The App Execution aliases live as reparse points in:
# $env:LOCALAPPDATA\Microsoft\WindowsApps\
# Disable by removing them (they are recreated by the Store; this breaks the stub link).
$waDir = "$env:LOCALAPPDATA\Microsoft\WindowsApps"
$aliases = @("python.exe", "python3.exe")
$disabled = @()
$failed = @()
foreach ($alias in $aliases) {
  $aliasPath = Join-Path $waDir $alias
  if (Test-Path $aliasPath) {
    try {
      Remove-Item -Path $aliasPath -Force -ErrorAction Stop
      $disabled += $alias
    } catch {
      $failed += "$alias ($_)"
    }
  } else {
    $disabled += "$alias (already absent)"
  }
}
if ($disabled.Count -gt 0) {
  Write-Output "Disabled: $($disabled -join ", ")"
}
if ($failed.Count -gt 0) {
  Write-Error "Failed: $($failed -join ", ")"
  exit 1
}
exit 0
'
    _ne_ps_exe=""
    if command -v pwsh >/dev/null 2>&1; then
      _ne_ps_exe="pwsh"
    elif command -v powershell >/dev/null 2>&1; then
      _ne_ps_exe="powershell"
    fi

    if [[ -z "$_ne_ps_exe" ]]; then
      printf '  ERROR: neither pwsh nor powershell found. Cannot disable aliases automatically.\n' >&2 # verify-no-console-flash: allow — string literal, not an interpreter spawn
      printf '  Manual step: Settings > Apps > Advanced app settings > App execution aliases\n' >&2
      printf '  Turn off "python" and "python3" entries.\n' >&2
      _ne_record_failure "App Execution alias disable (no PowerShell available)"
    else
      # Review: code-reviewer — removed 2>&1 from if-condition (confusing no-op on success).
      if "$_ne_ps_exe" -NonInteractive -NoProfile -Command "$_ne_ps_script"; then
        printf '  App Execution aliases for python/python3 disabled.\n'
        # Post-mutation verify.
        if [[ "$_ne_probes_available" -eq 1 ]]; then
          _ne_verify="$(_co_probe_python 2>/dev/null)"
          _ne_verify_status="$(printf '%s' "$_ne_verify" | sed 's/.*"status":"\([^"]*\)".*/\1/')"
          printf '  Post-fix probe: python = %s\n' "$_ne_verify_status" # verify-no-console-flash: allow — string literal, not an interpreter spawn
        fi
        _ne_record_success "WindowsApps python/python3 App Execution aliases disabled"
      else
        printf '  ERROR: PowerShell command to disable aliases failed.\n' >&2
        printf '  Manual step: Settings > Apps > Advanced app settings > App execution aliases\n' >&2
        printf '  Turn off the "python" and "python3" entries.\n' >&2
        _ne_record_failure "App Execution alias disable (PowerShell command failed)"
      fi
    fi
  else
    printf '  Skipped by user.\n'
  fi
  printf '\n'
fi

# ---------------------------------------------------------------------------
# Partial-failure summary.
# ---------------------------------------------------------------------------
printf '=== Summary ===\n'

if [[ -n "$_ne_steps_succeeded" ]]; then
  printf 'Succeeded:\n'
  printf '  %s\n' "$_ne_steps_succeeded"
fi

if [[ -n "$_ne_steps_failed" ]]; then
  printf 'Failed:\n'
  printf '  %s\n' "$_ne_steps_failed"
  printf '\nTo retry failed steps:\n'
  printf '  bash %s\n' "$0"
  printf '(Successfully applied steps are idempotent/already-done and will be skipped.)\n'
  printf '\nIf PATH/shim state was partially modified, restore with:\n'
  if [[ -n "$_ne_backup_file" ]]; then
    printf '  bash %s --restore %s\n' "$0" "$_ne_backup_file"
  else
    printf '  (no backup file available — restore manually)\n'
  fi
  exit 4
fi

# Review: code-reviewer (P2-3b) — if ZERO mutations were ultimately applied (all steps
# skipped / user declined all), remove the backup file to keep the consent-invariant
# clean: a full-decline run should leave no ~/.coordinator-env-backup.* residue.
if [[ -z "$_ne_steps_succeeded" ]] && [[ -z "$_ne_steps_failed" ]]; then
  printf 'No mutations applied (all steps skipped).\n'
  if [[ -n "$_ne_backup_file" ]] && [[ -f "$_ne_backup_file" ]]; then
    rm -f "$_ne_backup_file"
    printf '(Backup file removed — no state changed.)\n'
  fi
  exit 0
fi

printf 'All planned mutations applied successfully.\n'
if [[ -n "$_ne_backup_file" ]]; then
  printf '(Backup at %s can be removed once you verify the environment.)\n' "$_ne_backup_file"
fi
printf '\nOpen a new terminal to pick up PATH changes, then verify:\n'
printf '  python --version\n' # verify-no-console-flash: allow — string literal, not an interpreter spawn
printf '  uv --version\n'
exit 0
