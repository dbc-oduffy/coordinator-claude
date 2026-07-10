#!/usr/bin/env bash
# repoint-central-state-refs.sh — Idempotent repoint script: rewrites glued-literal
# central state path patterns in shell scripts to use coordinator_state_root --central,
# and ensures each rewritten script sources lib/coordinator-state-root.sh.
#
# Purpose: Mechanically convert the "glued-literal central state refs" identified
# in the stop-the-rot plan (Phase 1, C3) so that every central state path resolves
# through the coordinator_state_root --central seam rather than being hardcoded.
#
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C3 / AC3
# Ref: docs/wiki/migration-script-conventions.md section 1 (find -type f, not grep --include)
# Ref: docs/wiki/cleanup-sweep-hazards.md section 10 (two-phase; producer-side completes before delete)
#
# Patterns replaced (shell scripts only):
#   $HOME/.claude/**/state/handoffs/ -> $(coordinator_state_root)/handoffs/
#   $HOME/.claude/state/             -> $(coordinator_state_root --central)/
#   ${HOME}/.claude/state/           -> $(coordinator_state_root --central)/
#   $CLAUDE_HOME/state/              -> $(coordinator_state_root --central)/
#   ${CLAUDE_HOME}/state/            -> $(coordinator_state_root --central)/
#   ~/.claude/state/                 -> $(coordinator_state_root --central)/
#
# Source-line injection: after each rewrite, if the file does not already source
# coordinator-state-root.sh, the source block is injected after the shebang/comments.
#
# EXCLUSIONS (never touched):
#   bin/coordinator-lesson-promote   -- owned by C12 (parallel chunk)
#   bin/coordinator-queue-append     -- owned by C12 (parallel chunk)
#   bin/migrate-state-to-example-orchestration-hub.sh   -- legitimately dual-path (both ~/.claude and example-orchestration-hub)
#   lib/coordinator-state-root.sh    -- the seam itself
#   lib/coordinator-example-orchestration-hub-root.sh   -- the EXAMPLE_ORCHESTRATION_HUB_ROOT resolver primitive
#   lib/coordinator-is-meta-repo.sh  -- the meta-repo discriminator
#   bin/repoint-central-state-refs.sh -- this script itself
#
# Idempotency: a file already using coordinator_state_root --central is skipped.
# Re-running on an already-converted file is a no-op.
#
# Non-collision with the install-baton rendezvous (settings-home, a DISTINCT root
# from central example-orchestration-hub state — see docs/wiki/state-placement-law.md): the
# "$(coordinator-settings-home)/state/handoffs/" reference introduced by
# docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md does NOT match
# any PATTERNS entry below — none of the six literal-prefix patterns
# (~/.claude/**/state/handoffs/, ~/.claude/state/, $CLAUDE_HOME/state/, etc.) match
# a "$(coordinator-settings-home)/..." string, since that string never contains the
# literal "~/.claude" or "$HOME/.claude"/"${HOME}/.claude" substrings the PATTERNS
# list keys off of. A fixture containing only a settings-home ref therefore returns
# rc=2 (no change) from do_substitutions() below — verified 2026-07-08 (C3).
# Spec backlink: docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md § C3
#
# Cross-platform: bash >=4 + BSD coreutils; uses python3 for substitutions
# (avoids BSD vs GNU sed -i incompatibility).
#
# Usage: bash repoint-central-state-refs.sh [--dry-run] [--verbose]
#   --dry-run   Show what would change without modifying files.
#   --verbose   Print each file examined (not just those changed).

set -uo pipefail

# ---------------------------------------------------------------------------
# Bash >=4 guard (stock macOS /bin/bash is 3.2; brew bash is required)
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# python3 guard
PYTHON3="$(command -v python3 2>/dev/null || true)"
if [[ -z "$PYTHON3" ]]; then
  echo "ERROR: python3 is required for text substitutions. Install python3 first." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
DRY_RUN=0
VERBOSE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --verbose) VERBOSE=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Script location -- coordinator plugin root
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Exclusion paths (absolute)
# ---------------------------------------------------------------------------
declare -a EXCLUSIONS=(
  "${SCRIPT_DIR}/coordinator-lesson-promote"
  "${SCRIPT_DIR}/coordinator-queue-append"
  "${SCRIPT_DIR}/coordinator-queue-append.test.py"  # test for C12-owned script
  "${SCRIPT_DIR}/migrate-state-to-example-orchestration-hub.sh"
  "${COORDINATOR_ROOT}/lib/coordinator-state-root.sh"
  "${COORDINATOR_ROOT}/lib/coordinator-example-orchestration-hub-root.sh"
  "${COORDINATOR_ROOT}/lib/coordinator-is-meta-repo.sh"
  "${SCRIPT_DIR}/repoint-central-state-refs.sh"
  "${COORDINATOR_ROOT}/tests/handoff-transition.bats"  # ref is in single-quoted fixture string (not a path)
)

is_excluded() {
  local f="$1" excl
  for excl in "${EXCLUSIONS[@]}"; do
    [[ "$f" == "$excl" ]] && return 0
  done
  return 1
}

# ---------------------------------------------------------------------------
# Python substitution helper
# Prints the substituted file content to stdout.
# Exits 2 when NO substitutions were made (sentinel for caller).
# ---------------------------------------------------------------------------
SUBST_PY='
import sys

path = sys.argv[1]
try:
    fh = open(path, encoding="utf-8", errors="replace")
    lines = fh.readlines()
    fh.close()
except Exception as e:
    sys.stderr.write("ERROR reading %s: %s\n" % (path, e))
    sys.exit(1)

# Apply substitutions only on non-comment code lines.
# Comment lines (first non-whitespace char is #) are left untouched so that
# files where the pattern only appears in comments return rc=2 (no change).
PATTERNS = [
    ("${HOME}/.claude/**/state/handoffs/", "$(coordinator_state_root)/handoffs/"),
    ("$HOME/.claude/**/state/handoffs/",   "$(coordinator_state_root)/handoffs/"),
    ("${HOME}/.claude/state/",             "$(coordinator_state_root --central)/"),
    ("$HOME/.claude/state/",               "$(coordinator_state_root --central)/"),
    ("${CLAUDE_HOME}/state/",              "$(coordinator_state_root --central)/"),
    ("$CLAUDE_HOME/state/",                "$(coordinator_state_root --central)/"),
    ("~/.claude/state/",                   "$(coordinator_state_root --central)/"),
]

changed = False
new_lines = []
for line in lines:
    stripped = line.lstrip()
    if stripped.startswith("#"):
        # Comment line -- do not rewrite
        new_lines.append(line)
        continue
    new_line = line
    for (old, new) in PATTERNS:
        new_line = new_line.replace(old, new)
    if new_line != line:
        changed = True
    new_lines.append(new_line)

if not changed:
    sys.exit(2)

sys.stdout.write("".join(new_lines))
sys.exit(0)
'

do_substitutions() {
  local fpath="$1"
  "$PYTHON3" -c "$SUBST_PY" "$fpath"
}

# ---------------------------------------------------------------------------
# Source-line injection helper
# Inserts the source block after shebang + initial comment block.
# ---------------------------------------------------------------------------
INJECT_PY_TEMPLATE='
import sys

path = sys.argv[1]
rel_to_lib = sys.argv[2]

source_block = (
    "# Source the state-root seam -- must precede coordinator_state_root calls"
    " (added by repoint-central-state-refs.sh C3)\n"
    "_CSR_LIB_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/" + "{rel}" + "\" 2>/dev/null && pwd)\"\n"
    "# shellcheck source=lib/coordinator-state-root.sh\n"
    "source \"${_CSR_LIB_DIR}/coordinator-state-root.sh\"\n"
    "\n"
)

fh = open(path, encoding="utf-8", errors="replace")
lines = fh.readlines()
fh.close()

# Find insertion point: after shebang and leading comment block.
insert_after = 0
if lines and lines[0].startswith("#!"):
    insert_after = 1

i = insert_after
while i < len(lines):
    stripped = lines[i].rstrip()
    if stripped == "" or stripped.startswith("#"):
        i += 1
    else:
        break
insert_after = i

new_lines = lines[:insert_after] + [source_block] + lines[insert_after:]
fh = open(path, "w", encoding="utf-8")
fh.writelines(new_lines)
fh.close()
'

inject_source_line() {
  local fpath="$1"
  local fdir
  fdir="$(dirname "$fpath")"

  local rel_to_lib
  case "$fdir" in
    "${COORDINATOR_ROOT}/bin") rel_to_lib="../lib" ;;
    "${COORDINATOR_ROOT}/lib") return 0 ;;
    "${COORDINATOR_ROOT}/hooks/scripts") rel_to_lib="../../lib" ;;
    "${COORDINATOR_ROOT}/hooks") rel_to_lib="../lib" ;;
    "${COORDINATOR_ROOT}/tests/cockpit-tc3") rel_to_lib="../../lib" ;;
    "${COORDINATOR_ROOT}/tests") rel_to_lib="../lib" ;;
    *) rel_to_lib="../lib" ;;
  esac

  # Build the inject script with rel_to_lib substituted
  local inject_py
  inject_py="${INJECT_PY_TEMPLATE/\{rel\}/$rel_to_lib}"
  "$PYTHON3" -c "$inject_py" "$fpath" "$rel_to_lib"
}

# ---------------------------------------------------------------------------
# Main enumeration loop
# Use find -type f (not grep --include) per migration-script-conventions.md section 1.
# Scope: bin/, lib/, hooks/, tests/ (skills/agents are C5 prose scope).
# ---------------------------------------------------------------------------
CHANGED_COUNT=0
SKIPPED_COUNT=0
EXAMINED_COUNT=0

while IFS= read -r fpath; do
  [[ -f "$fpath" ]] || continue

  # Shell-file filter: .sh/.bash extension OR bash/sh shebang
  local_ext="${fpath##*.}"
  is_shell=0
  case "$local_ext" in
    sh|bash) is_shell=1 ;;
    *)
      first_line="$(head -1 "$fpath" 2>/dev/null || true)"
      case "$first_line" in
        "#!/"*"bash"*|"#!/"*"/sh"|"#!/"*"/sh "*) is_shell=1 ;;
      esac
      ;;
  esac
  if [[ "$is_shell" -eq 0 ]]; then
    [[ "$VERBOSE" -eq 1 ]] && echo "SKIP (non-shell): $fpath"
    continue
  fi

  if is_excluded "$fpath"; then
    [[ "$VERBOSE" -eq 1 ]] && echo "SKIP (excluded): $fpath"
    continue
  fi

  EXAMINED_COUNT=$((EXAMINED_COUNT + 1))

  # Fast pre-filter: any central state pattern?
  has_pattern=0
  if grep -qF '$HOME/.claude/state/' "$fpath" 2>/dev/null || \
     grep -qF '${HOME}/.claude/state/' "$fpath" 2>/dev/null || \
     grep -qF '$CLAUDE_HOME/state/' "$fpath" 2>/dev/null || \
     grep -qF '${CLAUDE_HOME}/state/' "$fpath" 2>/dev/null || \
     grep -qF '~/.claude/state/' "$fpath" 2>/dev/null || \
     grep -qF '$HOME/.claude/**/state/' "$fpath" 2>/dev/null; then
    has_pattern=1
  fi

  if [[ "$has_pattern" -eq 0 ]]; then
    [[ "$VERBOSE" -eq 1 ]] && echo "SKIP (no pattern): $fpath"
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  # Idempotency: already converted?
  if grep -q 'coordinator_state_root --central' "$fpath" 2>/dev/null; then
    [[ "$VERBOSE" -eq 1 ]] && echo "SKIP (already converted): $fpath"
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN would repoint: $fpath"
    CHANGED_COUNT=$((CHANGED_COUNT + 1))
    continue
  fi

  # Perform substitutions
  tmp_out="$(mktemp "${TMPDIR:-/tmp}/repoint-central-XXXXXX")"

  set +e
  do_substitutions "$fpath" > "$tmp_out"
  py_rc=$?
  set -e

  if [[ "$py_rc" -eq 2 ]]; then
    rm -f "$tmp_out"
    [[ "$VERBOSE" -eq 1 ]] && echo "SKIP (pattern in grep but not found by python): $fpath"
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    continue
  fi

  if [[ "$py_rc" -ne 0 ]]; then
    echo "ERROR: python3 substitution failed for $fpath (rc=$py_rc)" >&2
    rm -f "$tmp_out"
    continue
  fi

  cp "$tmp_out" "$fpath"
  rm -f "$tmp_out"

  echo "REPOINTED: $fpath"

  # Inject source line if not already present
  if ! grep -q 'coordinator-state-root\.sh' "$fpath" 2>/dev/null; then
    inject_source_line "$fpath"
    echo "  + SOURCE LINE injected"
  else
    echo "  (source line already present)"
  fi

  CHANGED_COUNT=$((CHANGED_COUNT + 1))

done < <(
  find \
    "${COORDINATOR_ROOT}/bin" \
    "${COORDINATOR_ROOT}/lib" \
    "${COORDINATOR_ROOT}/hooks" \
    "${COORDINATOR_ROOT}/tests" \
    -type f 2>/dev/null
)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "repoint-central-state-refs.sh summary:"
echo "  Files examined : $EXAMINED_COUNT"
echo "  Files repointed: $CHANGED_COUNT"
echo "  Files skipped  : $SKIPPED_COUNT"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "  (DRY-RUN -- no files were modified)"
fi
