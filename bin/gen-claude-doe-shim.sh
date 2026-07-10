#!/usr/bin/env bash
# gen-claude-doe-shim.sh — render the claude() shim and wire one source line into
# the operator's interactive rc.
#
# Purpose: writes ${CLAUDE_HOME:-$HOME}/.claude/shell/claude-doe-shim.sh from
#   the coordinator template, then ensures exactly ONE sentinel-guarded source
#   block in the $SHELL-detected interactive rc (zsh → ~/.zshrc, bash → ~/.bashrc).
#
# Spec backlink: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md § C2
#
# Idempotency:  safe to re-run — sentinel-guarded rc block, atomic writes;
#               re-running when unchanged is a no-op.
# Dry-run safe: --check-only renders to temp, discards, never touches live files.
# Migration:    detects the legacy # --- coordinator maximalist launch --- block
#               and surfaces a one-line migration note; does NOT silently rewrite it.
# Override:     COORDINATOR_SHIM_RC=<path> env var or --rc <path> flag selects
#               the rc directly (escape hatch when $SHELL detection is wrong).
#
# DR-148: requires bash >= 4; emitted shim body is POSIX-sh safe (no bashisms).
# Portability:  no GNU-isms — no sed -i, no realpath, no grep -P.

# ---- bash >=4 guard (block must parse on bash 3.2) ----
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  printf 'ERROR: gen-claude-doe-shim.sh requires bash >= 4.\n' >&2
  printf 'Remediation: brew install bash  (then relaunch your shell or prefix with /opt/homebrew/bin/bash)\n' >&2
  exit 1
fi

set -euo pipefail

# ---- sentinel constants ----
readonly SENTINEL_BEGIN="# --- coordinator claude-doe shim [generated] ---"
readonly SENTINEL_END="# --- end coordinator claude-doe shim ---"
# The legacy stopgap written by hand during the 2026-07-04 maximalist bringup.
readonly LEGACY_MARKER="# --- coordinator maximalist launch ---"

# ---- helpers ----
die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
Usage: gen-claude-doe-shim.sh [OPTIONS]

Writes ~/.claude/shell/claude-doe-shim.sh from the coordinator template and
ensures exactly one marked source block in the interactive rc file.

Options:
  --rc <path>         Target interactive rc file (overrides COORDINATOR_SHIM_RC
                      env var and $SHELL-based detection)
  --check-only        Validate without mutating any live file (renders to a
                      temp path, discards it, exits 0 on success)
  --template <path>   Override template source path (default: auto-resolved
                      relative to this script; useful for tests)
  -h, --help          Show this help and exit

Environment:
  COORDINATOR_SHIM_RC    Override target rc path (--rc flag takes precedence)
  CLAUDE_HOME            Claude home BASE directory, i.e. the parent of .claude/
                         (default: $HOME; shim lands at $CLAUDE_HOME/.claude/shell/)
EOF
}

# ---- arg parse ----
RC_OVERRIDE=""
CHECK_ONLY=0
TEMPLATE_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rc)         RC_OVERRIDE="$2";       shift 2 ;;
    --check-only) CHECK_ONLY=1;           shift   ;;
    --template)   TEMPLATE_OVERRIDE="$2"; shift 2 ;;
    -h|--help)    usage; exit 0 ;;
    *)            die "Unknown argument: $1. Run with --help for usage." ;;
  esac
done

# ---- resolve paths ----
# CLAUDE_HOME is the parent directory of .claude/ (same semantics as the shim template:
# pointer lives at ${CLAUDE_HOME:-$HOME}/.claude/.doe-root).
CLAUDE_HOME_BASE="${CLAUDE_HOME:-$HOME}"
CLAUDE_DIR="${CLAUDE_HOME_BASE}/.claude"
SHELL_DIR="${CLAUDE_DIR}/shell"
SHIM_DEST="${SHELL_DIR}/claude-doe-shim.sh"

# Resolve template relative to this script's directory (no realpath — BSD portable).
if [[ -n "$TEMPLATE_OVERRIDE" ]]; then
  TMPL_PATH="$TEMPLATE_OVERRIDE"
else
  _script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  TMPL_PATH="${_script_dir}/../templates/shell/claude-doe-shim.sh.tmpl"
fi
# Canonicalise without realpath (portable: cd to dir + pwd).
_tmpl_dir="$(cd "$(dirname "$TMPL_PATH")" && pwd)"
TMPL_PATH="${_tmpl_dir}/$(basename "$TMPL_PATH")"
[[ -f "$TMPL_PATH" ]] || die "Template not found: $TMPL_PATH"

# ---- detect legacy stopgap ----
# The hand-bolted claude() block added during the 2026-07-04 maximalist bringup.
# Emit a migration note; do NOT silently rewrite it.  The coordinator-uninstall
# spinoff is responsible for removing it.
_bashrc="$HOME/.bashrc"
if [[ -f "$_bashrc" ]] && grep -qF "$LEGACY_MARKER" "$_bashrc"; then
  printf 'NOTE (migration): legacy coordinator maximalist launch claude() block detected in %s.\n' \
    "$_bashrc" >&2
  printf '  This block is superseded by the new shim. To clean up, remove the\n' >&2
  printf '  block between "%s" and its end marker from %s\n' "$LEGACY_MARKER" "$_bashrc" >&2
  printf '  (or run coordinator-uninstall when available — it handles this surface).\n' >&2
fi

# ---- resolve target rc ----
# Precedence: --rc flag > COORDINATOR_SHIM_RC env > $SHELL detection.
if [[ -n "$RC_OVERRIDE" ]]; then
  TARGET_RC="$RC_OVERRIDE"
elif [[ -n "${COORDINATOR_SHIM_RC:-}" ]]; then
  TARGET_RC="$COORDINATOR_SHIM_RC"
else
  # $SHELL is the login shell from the passwd entry — correct for the target
  # machine class (macOS + zsh primary).  For divergent cases (e.g., zsh
  # interactive under a bash login shell) use --rc to select directly.
  case "${SHELL:-}" in
    */zsh)  TARGET_RC="$HOME/.zshrc"  ;;
    */bash) TARGET_RC="$HOME/.bashrc" ;;
    *)
      printf 'WARN: $SHELL="%s" not recognised; defaulting to ~/.zshrc. Use --rc to override.\n' \
        "${SHELL:-<unset>}" >&2
      TARGET_RC="$HOME/.zshrc"
      ;;
  esac
fi

# The source line emitted into the rc.  Uses $HOME (not ~) as a literal shell
# variable reference so the line is machine-independent in the rc file itself.
# POSIX parameter expansion ${CLAUDE_HOME:-$HOME} mirrors the shim template.
# The -f guard prevents rc errors if the shim is ever absent.
EXPECTED_SOURCE_LINE='[ -f "${CLAUDE_HOME:-$HOME}/.claude/shell/claude-doe-shim.sh" ] && source "${CLAUDE_HOME:-$HOME}/.claude/shell/claude-doe-shim.sh"'

# ---- check-only path ----
# Render to a temp file to validate the template is readable and well-formed;
# describe what would be done to the rc.  No live files are touched.
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  _tmp_shim="$(mktemp /tmp/claude-doe-shim-check.XXXXXX)"
  cp "$TMPL_PATH" "$_tmp_shim"
  _shim_lines="$(wc -l < "$_tmp_shim" | tr -d ' ')"
  printf '[check-only] Template valid: %s (%s lines) -> would write to %s (discarded)\n' \
    "$TMPL_PATH" "$_shim_lines" "$SHIM_DEST" >&2
  rm -f "$_tmp_shim"

  if [[ -f "$TARGET_RC" ]] && grep -qF "$SENTINEL_BEGIN" "$TARGET_RC"; then
    # Check if the block is hand-modified (same logic as live path, read-only).
    _body="$(awk -v b="$SENTINEL_BEGIN" -v e="$SENTINEL_END" \
      '$0 == b {f=1; next} $0 == e {f=0} f {print}' "$TARGET_RC")"
    _body_trimmed="$(printf '%s' "$_body" | awk 'NF')"
    _expected_trimmed="$(printf '%s' "$EXPECTED_SOURCE_LINE" | awk 'NF')"
    if [[ "$_body_trimmed" == "$_expected_trimmed" ]]; then
      printf '[check-only] rc %s: sentinel block present and unmodified (would be no-op)\n' \
        "$TARGET_RC" >&2
    else
      printf '[check-only] rc %s: sentinel block present but HAND-MODIFIED — would fail-loud\n' \
        "$TARGET_RC" >&2
      printf '  Expected: %s\n' "$_expected_trimmed" >&2
      printf '  Found:    %s\n' "$_body_trimmed" >&2
      exit 1
    fi
  else
    printf '[check-only] rc %s: sentinel absent — would add source block\n' "$TARGET_RC" >&2
  fi
  exit 0
fi

# ---- render shim (atomic) ----
mkdir -p "$SHELL_DIR"
_tmp_shim="${SHIM_DEST}.tmp.$$"
cp "$TMPL_PATH" "$_tmp_shim"
mv -f "$_tmp_shim" "$SHIM_DEST"
printf 'Wrote shim: %s\n' "$SHIM_DEST" >&2

# ---- wire source line into rc (sentinel-guarded, detect-then-fail-loud on hand-mod) ----
# Ensure the rc file exists.
if [[ ! -f "$TARGET_RC" ]]; then
  touch "$TARGET_RC" || die "Cannot create rc file: $TARGET_RC"
  printf 'Created rc file: %s\n' "$TARGET_RC" >&2
fi

if grep -qF "$SENTINEL_BEGIN" "$TARGET_RC"; then
  # Sentinel already present — check for hand-modification.
  _body="$(awk -v b="$SENTINEL_BEGIN" -v e="$SENTINEL_END" \
    '$0 == b {f=1; next} $0 == e {f=0} f {print}' "$TARGET_RC")"
  # Strip blank lines for comparison (awk 'NF' is portable; no grep -P).
  _body_trimmed="$(printf '%s' "$_body" | awk 'NF')"
  _expected_trimmed="$(printf '%s' "$EXPECTED_SOURCE_LINE" | awk 'NF')"

  if [[ "$_body_trimmed" == "$_expected_trimmed" ]]; then
    printf 'rc %s: sentinel block unchanged (no-op)\n' "$TARGET_RC" >&2
  else
    printf 'ERROR: sentinel block in %s has been hand-modified.\n' "$TARGET_RC" >&2
    printf '  Expected body: %s\n' "$_expected_trimmed" >&2
    printf '  Found body:    %s\n' "$_body_trimmed" >&2
    printf '  To reset: remove the block between "%s" and "%s" from %s and re-run.\n' \
      "$SENTINEL_BEGIN" "$SENTINEL_END" "$TARGET_RC" >&2
    exit 1
  fi
else
  # Sentinel absent — append the source block atomically.
  _tmp_rc="${TARGET_RC}.tmp.$$"
  cp "$TARGET_RC" "$_tmp_rc"
  printf '\n%s\n%s\n%s\n' \
    "$SENTINEL_BEGIN" \
    "$EXPECTED_SOURCE_LINE" \
    "$SENTINEL_END" >> "$_tmp_rc"
  mv -f "$_tmp_rc" "$TARGET_RC"
  printf 'rc %s: source block added\n' "$TARGET_RC" >&2
fi

printf 'Done. Open a new terminal (or run: source %s) for claude() to take effect.\n' "$TARGET_RC" >&2
