#!/usr/bin/env bash
# verify-ps51-clean.sh — Repo-agnostic smoke check that asserts PowerShell .ps1
# setup/install legs are Windows PowerShell 5.1-clean: they PARSE under the 5.1
# engine (powershell.exe, NOT pwsh 7) and contain no pwsh-7-only syntax patterns.
#
# Four-way per-file classification:
#   OK            — file parses cleanly under PS 5.1 (optional WARN for advisory patterns)
#   FAIL          — file has PS 5.1 parse errors AND does NOT declare a PS7 requires floor;
#                   this is the accidental-incompatibility case (real defect to fix)
#   EXPECTED-PS7  — file has PS 5.1 parse errors AND declares "#requires -Version 7.0"
#                   (or higher); the 5.1 failure is by-design, not a defect
#   WARN          — advisory pwsh7-only syntax patterns caught by bash static scan;
#                   file still counts as parse-clean (OK), does not trigger exit 1
#
# Only genuine FAIL triggers exit 1. EXPECTED-PS7 and WARN do not fail the check.
# This distinction matters: FAIL is an accidental incompatibility; EXPECTED-PS7
# is a deliberate PS7+ floor declaration.
#
# Shared home in coordinator bin/; each consuming repo (coordinator,
# example-game-workbench-repo) calls it pointing at its own .ps1 set.
#
# Spec backlink: state/handoffs/2026-06-22_215618_windows-clean-install-verification.md
# (Part B). Path is relative to the ~/.claude meta-repo root; not present in distributed installs.
#
# Usage: verify-ps51-clean.sh <path-or-dir> [<path-or-dir> ...]
#   Each arg is a .ps1 file OR a directory (recurse for *.ps1, excluding
#   node_modules/ and .git/ paths).
# Exit:  0 if all files parse-clean under PS 5.1 (WARN/EXPECTED-PS7 are still 0);
#        1 if any file has an unexpected 5.1 parse error (genuine FAIL);
#        2 if called with no arguments (usage error).
#
# DR-148: cross-platform bash — runs on bash >= 4 + BSD/GNU coreutils.

set -euo pipefail

# DR-148 bash version guard — must be reachable on 3.2 syntax (no declare -A here yet)
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Usage guard
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
  echo "Usage: $(basename "$0") <path-or-dir> [<path-or-dir> ...]" >&2
  echo "  Each arg is a .ps1 file or a directory (recursed for *.ps1, excluding node_modules/ and .git/)." >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Engine resolution — locate Windows PowerShell 5.1 via PATH lookup
# (command -v is a PATH check only — no console window opened here)
# ---------------------------------------------------------------------------
PS51_EXE=""
if command -v powershell.exe >/dev/null 2>&1; then  # popup-safe-env-suppressed
  PS51_EXE=$(command -v powershell.exe)              # popup-safe-env-suppressed
fi

if [[ -z "$PS51_EXE" ]]; then
  echo "SKIP: powershell.exe (Windows PowerShell 5.1) not present — PS5.1 cleanliness is a Windows-only check"
  exit 0
fi

# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------
# Collect all .ps1 files from arguments (files directly; directories recursed).
# BSD-safe: no GNU-isms. find with -print0 / sort -z for safe filename handling.
declare -a PS1_FILES=()

for arg in "$@"; do
  if [[ -f "$arg" ]]; then
    # Single file — accept if .ps1
    if [[ "$arg" == *.ps1 ]]; then
      PS1_FILES+=("$arg")
    fi
  elif [[ -d "$arg" ]]; then
    # Directory — recurse, excluding node_modules and .git
    while IFS= read -r -d '' f; do
      PS1_FILES+=("$f")
    done < <(find "$arg" -name '*.ps1' \
      -not -path '*/node_modules/*' \
      -not -path '*/.git/*' \
      -print0 2>/dev/null | sort -z)
  else
    echo "WARN: path not found, skipping: $arg" >&2
  fi
done

if [[ ${#PS1_FILES[@]} -eq 0 ]]; then
  echo "No .ps1 files found in the specified paths."
  echo "0/0 parse-clean, 0 failed, 0 expected-ps7 (PS7-floored), 0 warned"
  exit 0
fi

# ---------------------------------------------------------------------------
# pwsh-7-only syntax patterns (static bash scan, advisory WARN, not FAIL)
# ---------------------------------------------------------------------------
# These patterns are absent from PS 5.1 and flag advisory warnings.
# We flag conservatively — patterns inside strings/comments may be false
# positives but we still emit WARN (not FAIL).
#
# Pattern list:
#   ??  / ??=    — null-coalescing operators
#   ?.  / ?[     — null-conditional operators
#   &&  / ||     — pipeline chain operators (PS 5.1 rejects these)
#   ForEach-Object -Parallel — parallel pipeline parameter

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
COUNT_OK=0
COUNT_FAIL=0
COUNT_EXPECTED_PS7=0
COUNT_WARN=0
TOTAL=${#PS1_FILES[@]}

# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------
for ps1 in "${PS1_FILES[@]}"; do
  # ------------------------------------------------------------------
  # Step 0: Detect PowerShell PS7+ requires floor.
  # Match lines of the exact form: ^[whitespace]#requires[whitespace] ... -Version N...
  # where N >= 7. Only the PowerShell #requires directive counts — not
  # arbitrary comments that happen to contain the word "requires".
  # ------------------------------------------------------------------
  is_ps7_floored=0
  # requires_version_str is set inside the loop when is_ps7_floored becomes 1;
  # no initializer needed (reading it is only reachable when is_ps7_floored=1).
  while IFS= read -r line; do
    # Strip a leading UTF-8 BOM (EF BB BF) so the #requires regex matches on
    # BOM-encoded .ps1 files (Windows mandates BOM on non-ASCII .ps1 for PS 5.1).
    # ${line#...} strips only a leading match → no-op on non-BOM/mid-line.
    line="${line#$'\xef\xbb\xbf'}"
    # The #requires directive: optional leading whitespace, then #requires (case-insensitive
    # per PS rules), then at least one whitespace character before any parameters.
    if [[ "$line" =~ ^[[:space:]]*#[Rr][Ee][Qq][Uu][Ii][Rr][Ee][Ss][[:space:]] ]]; then
      # Check for -Version with a major version number >= 7
      if [[ "$line" =~ -[Vv]ersion[[:space:]]+([0-9]+) ]]; then
        major="${BASH_REMATCH[1]}"
        if [[ "$major" -ge 7 ]]; then
          is_ps7_floored=1
          # Capture the full version string for the verdict message
          if [[ "$line" =~ -[Vv]ersion[[:space:]]+([0-9]+(\.[0-9]+)*) ]]; then
            requires_version_str="${BASH_REMATCH[1]}"
          fi
          break
        fi
      fi
    fi
  done < "$ps1"

  # ------------------------------------------------------------------
  # Step 1: PS 5.1 parse check via AST — NO execution of the target script.
  # The PS engine uses -WindowStyle Hidden to suppress console flash.
  # -Command calls [Parser]::ParseFile() and prints PARSE_ERRORS=<n>.
  # popup-intentional-last-resort
  # ------------------------------------------------------------------

  # Resolve to Windows-native absolute path for the PS 5.1 engine.
  # pwd -W (Git Bash / MSYS2 / Cygwin) emits the native form (C:/...).
  # On Linux/macOS this code is never reached (engine absent → early SKIP).
  win_dir=$(cd "$(dirname "$ps1")" && { pwd -W 2>/dev/null || pwd; })
  win_path_fwd="${win_dir}/$(basename "$ps1")"

  # Escape single quotes for PowerShell single-quoted string ('' = literal ').
  ps_escaped_path="${win_path_fwd//\'/\'\'}"
  # Convert forward slashes to backslashes for the Windows path expected by PS 5.1.
  win_path_bs="${ps_escaped_path//\//\\}"

  ps_command="\$errs = \$null; \$null = [System.Management.Automation.Language.Parser]::ParseFile('${win_path_bs}', [ref]\$null, [ref]\$errs); \$n = \$errs.Count; Write-Output \"PARSE_ERRORS=\$n\"; if (\$n -gt 0) { Write-Output \"FIRST_ERROR=\$(\$errs[0].Message) @line \$(\$errs[0].Extent.StartLineNumber)\" }"

  # Encode the PS command as Base64 UTF-16LE for -EncodedCommand, avoiding fragile
  # literal-quote passing through bash→MSYS2→PowerShell. Review: code-reviewer — F1.
  encoded=$(printf '%s' "$ps_command" | iconv -t UTF-16LE | base64 -w 0)
  parse_out=""
  parse_rc=0
  parse_out=$(powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand "$encoded" 2>/dev/null) || parse_rc=$?  # popup-intentional-last-resort

  # Strip Windows CRLF (\r) from captured output
  parse_out="${parse_out//$'\r'/}"

  parse_error_count=0
  first_error_msg=""

  if [[ $parse_rc -ne 0 ]]; then
    # The PS engine itself failed to run — treat as parse failure.
    parse_error_count=1
    first_error_msg="powershell.exe invocation failed (exit ${parse_rc})"
  else
    # Extract PARSE_ERRORS=<n>
    if [[ "$parse_out" =~ PARSE_ERRORS=([0-9]+) ]]; then
      parse_error_count="${BASH_REMATCH[1]}"
    fi
    # Extract FIRST_ERROR=<msg>
    if [[ "$parse_out" =~ FIRST_ERROR=(.+) ]]; then
      first_error_msg="${BASH_REMATCH[1]}"
    fi
  fi

  # ------------------------------------------------------------------
  # Step 2: Static pwsh-7-only syntax scan (bash, advisory WARN)
  # Only runs for parse-clean files: EXPECTED-PS7 files intentionally use pwsh7
  # syntax (the scan output would be meaningless noise), and FAIL files already
  # have a primary parse-error verdict — the static scan is deliberately skipped
  # for both to avoid wasted computation.
  # ------------------------------------------------------------------
  warn_tokens=()
  if [[ $parse_error_count -eq 0 ]]; then
  lineno=0
  while IFS= read -r line; do
    # Strip a leading UTF-8 BOM (EF BB BF) — consistency with the #requires scan above.
    line="${line#$'\xef\xbb\xbf'}"
    lineno=$(( lineno + 1 ))
    # Check ??= before ?? to avoid double-reporting the same operator.
    if [[ "$line" =~ \?\?= ]]; then
      warn_tokens+=("??= @line ${lineno}")
    # Null-coalescing ??
    elif [[ "$line" =~ \?\? ]]; then
      warn_tokens+=("?? @line ${lineno}")
    fi
    # Null-conditional ?. or ?[
    if [[ "$line" =~ \?\. ]] || [[ "$line" =~ \?\[ ]]; then
      warn_tokens+=("?./\?[ @line ${lineno}")
    fi
    # Pipeline chain operators && or ||
    if [[ "$line" =~ \&\& ]] || [[ "$line" =~ \|\| ]]; then
      warn_tokens+=("&&/|| @line ${lineno}")
    fi
    # ForEach-Object -Parallel
    if [[ "$line" =~ ForEach-Object[[:space:]]+-Parallel ]]; then
      warn_tokens+=("ForEach-Object -Parallel @line ${lineno}")
    fi
  done < "$ps1"
  fi  # end: if [[ $parse_error_count -eq 0 ]]

  # ------------------------------------------------------------------
  # Step 3: Emit per-file verdict
  # ------------------------------------------------------------------
  if [[ $parse_error_count -gt 0 ]]; then
    if [[ $is_ps7_floored -eq 1 ]]; then
      # Parse failure is by-design: the script explicitly requires PS7+
      echo "EXPECTED-PS7 ${ps1} — declares '#requires -Version ${requires_version_str}'; 5.1 parse errors are by-design"
      COUNT_EXPECTED_PS7=$(( COUNT_EXPECTED_PS7 + 1 ))
    else
      # Parse failure without a PS7 floor — genuine accidental incompatibility
      echo "FAIL ${ps1} — ${parse_error_count} parse error(s): ${first_error_msg}"
      COUNT_FAIL=$(( COUNT_FAIL + 1 ))
    fi
  else
    if [[ ${#warn_tokens[@]} -gt 0 ]]; then
      for tok in "${warn_tokens[@]}"; do
        echo "WARN ${ps1} — pwsh7-syntax: ${tok}"
      done
      COUNT_WARN=$(( COUNT_WARN + 1 ))
      COUNT_OK=$(( COUNT_OK + 1 ))
    else
      echo "OK ${ps1}"
      COUNT_OK=$(( COUNT_OK + 1 ))
    fi
  fi
done

# ---------------------------------------------------------------------------
# Summary footer (4-way tally)
# ---------------------------------------------------------------------------
echo ""
echo "${COUNT_OK}/${TOTAL} parse-clean (incl. ${COUNT_WARN} with advisory warnings), ${COUNT_FAIL} failed, ${COUNT_EXPECTED_PS7} expected-ps7 (PS7-floored)"

# Exit non-zero only for genuine unexpected parse failures
if [[ $COUNT_FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
