#!/usr/bin/env bash
# cruft-sweep.sh — Layer 1 autonomous cruft pruner for ~/.claude state.
#
# Purpose: prune stale harness session state (projects/<repo>/<uuid>/, *.jsonl,
#          file-history/<uuid>/) on a configurable retention threshold, with an
#          active-handoff predecessor pre-flight to avoid deleting referenced work.
#          Phase B prunes stale in-repo scratch directories by name-anchored list.
#
# Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C1, § C2
#
# Usage:
#   cruft-sweep.sh [OPTIONS]
#
# Options:
#   --days N               Retention threshold in days (default: 14; reads
#                          cruft_sweep.harness_retention_days from machine-local
#                          registry if present; flag overrides)
#   --apply                Delete matching items (default: dry-run)
#   --dry-run              Report only, no deletions (default)
#   --class harness|scratch|orphans|all
#                          Which class to sweep (default: all)
#                          Phase A implements 'harness'; Phase B implements
#                          'scratch'; orphans emits "phase not yet implemented"
#                          and exits 0 (C2b fills it in)
#   --json                 With --dry-run, emit JSONL records on stdout
#                          (schema: {class, path, name, size_bytes, mtime,
#                          disposition, evidence})
#   --projects-root <path>  Default: ~/.claude/projects
#   --file-history-root <path>  Default: ~/.claude/file-history
#   --handoffs-glob <glob>  Glob for active handoff files
#                           Default: $(coordinator_state_root)/handoffs/*.md — resolves to
#                           the CURRENT git root's state/handoffs/ under default (no-flag)
#                           invocation; this is NEVER the install-baton rendezvous
#                           ($(coordinator-settings-home)/state/handoffs/) unless a future
#                           caller explicitly points --handoffs-glob or --parent-root at
#                           settings-home (see C3 forward-guard, Phase C below, and the
#                           comment in _build_uuid_blocklist()).
#   --log-path <path>       Sweep log path (default: ~/.claude/state/cruft-sweep-log.md)
#   --parent-root <path>    (repeatable; when given, replaces default X:/ and E:/dev/
#                           roots for Phase C orphan scan; tests pass tmp_path overrides)
#   --scratch-age-days N    Scratch retention threshold in days (default: 7)
#   --repo-root <path>      Scratch scan root (default: enclosing git repo root,
#                           or cwd if not in a git repo); useful for tests
#   --quiet                 Suppress human-readable banner
#
# Exit codes:
#   0  success or lock contention (contention exits silently)
#   1  unexpected error
#   2  invalid flags
#
# Portability: macOS bash 3.2 + BSD coreutils. No mapfile, no sed -i,
#   no realpath/readlink -f, no date -d, no stat -c/stat -f, no du -sb,
#   no find -printf, no ${v^^}.
#
# Concurrency: exclusive lock via mkdir at LOCK_DIR. On contention, exit 0
#   silently — the other run owns the work. Log-append is inside the lock.
#
# Negative-spec: does NOT scan beyond --parent-root roots speculatively.
#   Does NOT emit JSONL for non-name-matched parent-altitude dirs (silent).
#   Does NOT use flock(1) (not portable to BSD by default).
#   Does NOT use set -e (breaks find -exec and mkdir lock check semantics).
#   Does NOT reap the install-baton rendezvous ($(coordinator-settings-home)/state/
#   handoffs/) under default (no --parent-root) invocation — the default parent
#   roots are machine-local repo parent dirs, never settings-home. Does NOT reap it
#   even under an explicit --parent-root pointed at settings-home (or its 'state'
#   subdir) — Phase C hard-excludes the rendezvous folder by resolved-path compare
#   (C3 forward-guard, see _sweep_orphans()).

# Source the state-root seam -- must precede coordinator_state_root calls (added by repoint-central-state-refs.sh C3)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"
# Source the settings-home seam -- provides _coordinator_settings_home() for machine-local
# dir resolution; replaces hardcoded ~/.claude/machine-local reads (C2b).
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2b
# shellcheck source=lib/settings-home.sh
source "${_CSR_LIB_DIR}/settings-home.sh"

set -u

# ---------------------------------------------------------------------------
# Resolve coordinator content root early (needed by _default_parent_roots).
# Portable resolver: CLAUDE_PLUGIN_ROOT → COORDINATOR_ROOT → registry clone
# → versioned cache → flat layout. Defensive: fall back to flat if absent.
# ---------------------------------------------------------------------------
_rcc_resolver="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/resolve-coordinator-clone.sh"
if [[ -f "$_rcc_resolver" ]]; then
    # shellcheck source=../lib/resolve-coordinator-clone.sh
    source "$_rcc_resolver" 2>/dev/null || true
fi
if [[ -z "${COORDINATOR_CONTENT_ROOT:-}" ]]; then
    _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
    if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then
      echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2
      exit 1
    fi
    COORDINATOR_CONTENT_ROOT="${CLAUDE_PLUGIN_ROOT:-$_doe_root/coordinator}"
    # shellcheck source=lib/coordinator-trusted-root-guard.sh
    source "${_CSR_LIB_DIR}/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$COORDINATOR_CONTENT_ROOT" --site="$0"
fi

# ---------------------------------------------------------------------------
# Source portable timeout / cooperative watchdog library.
# Provides cs_timeout, cs_watchdog_reset, cs_watchdog_check.
# Guard: if the lib is absent (fresh machine, bash < 4) no-op stubs below
# degrade gracefully — rm operations fall back to unbounded behaviour.
# Spec backlink: docs/plans/2026-06-27-coordinator-watchdog.md
# ---------------------------------------------------------------------------
_watchdog_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/coordinator-watchdog.sh"
if [[ -f "$_watchdog_lib" ]]; then
    # shellcheck source=../lib/coordinator-watchdog.sh
    source "$_watchdog_lib" 2>/dev/null || true
fi
# No-op stubs when the lib failed to load (file absent, or source errored — e.g. bash<4 if the lib uses bash-4 features).
# Review: code-reviewer S2 — (F5) stub fires on declare -f miss; cause is file-absent or source-errored, not bash-version alone.
if ! declare -f cs_timeout >/dev/null 2>&1; then
    cs_timeout() { shift; [[ "${1:-}" == "--" ]] && shift; "$@"; }
fi
if ! declare -f cs_watchdog_reset >/dev/null 2>&1; then
    cs_watchdog_reset() { :; }
fi
if ! declare -f cs_watchdog_check >/dev/null 2>&1; then
    cs_watchdog_check() { return 0; }
fi

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DAYS=14
APPLY=0
CLASS="all"
JSON_MODE=0
QUIET=0
PROJECTS_ROOT="${HOME}/.claude/projects"
FILE_HISTORY_ROOT="${HOME}/.claude/file-history"
HANDOFFS_GLOB="$(coordinator_state_root)/handoffs/*.md"
LOG_PATH="$(coordinator_state_root --central)/cruft-sweep-log.md"
LOCK_DIR="$(coordinator_state_root --central)/cruft-sweep.lock.d"

# Accumulate --parent-root values (accepted, no-op in Phase A).
# Review: reviewer — bash 3.2 indexed array to support paths with spaces (F10 fix).
PARENT_ROOTS=()

# Phase B: scratch sweep settings
SCRATCH_AGE_DAYS=7
REPO_ROOT=""

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --days requires a value" >&2
        exit 2
      fi
      DAYS="$2"
      shift 2
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --dry-run)
      APPLY=0
      shift
      ;;
    --class)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --class requires a value" >&2
        exit 2
      fi
      case "$2" in
        harness|scratch|orphans|all) CLASS="$2" ;;
        *)
          echo "cruft-sweep.sh: unknown class '$2' (expected: harness, scratch, orphans, all)" >&2
          exit 2
          ;;
      esac
      shift 2
      ;;
    --json)
      JSON_MODE=1
      shift
      ;;
    --projects-root)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --projects-root requires a value" >&2
        exit 2
      fi
      PROJECTS_ROOT="$2"
      shift 2
      ;;
    --file-history-root)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --file-history-root requires a value" >&2
        exit 2
      fi
      FILE_HISTORY_ROOT="$2"
      shift 2
      ;;
    --handoffs-glob)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --handoffs-glob requires a value" >&2
        exit 2
      fi
      HANDOFFS_GLOB="$2"
      shift 2
      ;;
    --log-path)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --log-path requires a value" >&2
        exit 2
      fi
      LOG_PATH="$2"
      shift 2
      ;;
    --parent-root)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --parent-root requires a value" >&2
        exit 2
      fi
      # Repeatable; replaces default X:/ and E:/dev/ roots when any value given
      PARENT_ROOTS+=("$2")
      shift 2
      ;;
    --scratch-age-days)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --scratch-age-days requires a value" >&2
        exit 2
      fi
      SCRATCH_AGE_DAYS="$2"
      shift 2
      ;;
    --repo-root)
      if [[ -z "${2:-}" ]]; then
        echo "cruft-sweep.sh: --repo-root requires a value" >&2
        exit 2
      fi
      REPO_ROOT="$2"
      shift 2
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    -h|--help)
      grep '^#' "$0" | grep -v '^#!/' | sed 's/^# \{0,1\}//' | head -60
      exit 0
      ;;
    *)
      echo "cruft-sweep.sh: unknown flag '$1'" >&2
      echo "  Use --help for usage." >&2
      exit 2
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Try to read harness_retention_days from machine-local registry
# (fall through to --days default if absent or machine-local not installed)
# ---------------------------------------------------------------------------
if command -v machine-local >/dev/null 2>&1; then
  _ml_days=$(machine-local get cruft_sweep.harness_retention_days 2>/dev/null) && {
    if [[ -n "$_ml_days" && "$_ml_days" =~ ^[0-9]+$ ]]; then
      DAYS="$_ml_days"
    fi
  } || true
fi

# ---------------------------------------------------------------------------
# Concurrency lock — mkdir is atomic on POSIX + Windows Git-Bash
# On contention, exit 0 silently.
# ---------------------------------------------------------------------------
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  # Another run holds the lock — it will do the work
  exit 0
fi

# Trap to release lock on exit (any path)
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# ---------------------------------------------------------------------------
# Helper: get mtime as epoch seconds (POSIX portable)
# BSD stat uses -f %m; GNU stat uses -c %Y.
# Fall back to python if neither works.
# ---------------------------------------------------------------------------
_get_mtime() {
  local target="$1"
  local _mt
  # Try BSD stat first (macOS). stat is used in try-each-flavor pattern with non-empty
  # validation — Review: reviewer — guard against empty string from stat failure (F7 fix).
  _mt=$(stat -f %m "$target" 2>/dev/null) && [[ -n "$_mt" ]] && { echo "$_mt"; return; }
  # Try GNU stat
  _mt=$(stat -c %Y "$target" 2>/dev/null) && [[ -n "$_mt" ]] && { echo "$_mt"; return; }
  # Fall back to python
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import os,sys; print(int(os.path.getmtime(sys.argv[1])))" -- "$target" 2>/dev/null && return # verify-no-console-flash: allow — on-demand cruft sweep utility, not session-hot-path
  elif command -v python >/dev/null 2>&1; then
    python -c "import os,sys; print(int(os.path.getmtime(sys.argv[1])))" -- "$target" 2>/dev/null && return # verify-no-console-flash: allow — on-demand cruft sweep utility, not session-hot-path
  fi
  echo "0"
}

# ---------------------------------------------------------------------------
# Helper: get file size in bytes (wc -c, POSIX portable)
# ---------------------------------------------------------------------------
_file_size() {
  local f="$1"
  wc -c < "$f" 2>/dev/null | tr -d ' \t' || echo "0"
}

# ---------------------------------------------------------------------------
# Helper: get directory size in bytes (du -sk gives kilobytes; multiply by 1024)
# Note: approximate (1024-multiple rounding).
# ---------------------------------------------------------------------------
_dir_size_bytes() {
  local d="$1"
  local _kb
  _kb=$(du -sk "$d" 2>/dev/null | awk '{print $1}') || _kb=0
  echo $(( _kb * 1024 ))
}

# ---------------------------------------------------------------------------
# Helper: emit a JSONL record to stdout
# Uses python for correct JSON escaping.
# ---------------------------------------------------------------------------
_emit_jsonl() {
  local class="$1"
  local path="$2"
  local name="$3"
  local size_bytes="$4"
  local mtime="$5"
  local disposition="$6"
  local evidence="$7"

  local _py=""
  if command -v python3 >/dev/null 2>&1; then
    _py=python3
  elif command -v python >/dev/null 2>&1; then
    _py=python
  fi

  if [[ -n "$_py" ]]; then
    "$_py" - "$class" "$path" "$name" "$size_bytes" "$mtime" "$disposition" "$evidence" <<'PYEOF'
import json, sys
args = sys.argv[1:]
rec = {
    "class": args[0],
    "path": args[1],
    "name": args[2],
    "size_bytes": int(args[3]) if args[3].lstrip('-').isdigit() else 0,
    "mtime": int(args[4]) if args[4].lstrip('-').isdigit() else 0,
    "disposition": args[5],
    "evidence": args[6],
}
print(json.dumps(rec))
PYEOF
  else
    # Review: reviewer — naive fallback emits invalid JSON on paths containing backslashes
    # (Windows) or double-quotes; only used when no python3/python2 available. (F12 fix)
    echo "[cruft-sweep] WARNING: no python available; JSONL output may be malformed on special-char paths" >&2
    printf '{"class":"%s","path":"%s","name":"%s","size_bytes":%s,"mtime":%s,"disposition":"%s","evidence":"%s"}\n' \
      "$class" "$path" "$name" "$size_bytes" "$mtime" "$disposition" "$evidence"
  fi
}

# ---------------------------------------------------------------------------
# Pre-flight: build a UUID block-list from active handoffs
# Grep handoffs matching HANDOFFS_GLOB for predecessor: <uuid> patterns.
# Writes result to the variable named by $1 (nameref-free, bash 3.2 compat).
#
# HANDOFFS_GLOB defaults to "$(coordinator_state_root)/handoffs/*.md" (set above at
# the Defaults block) — the CURRENT git root's state/handoffs/, resolved via the
# coordinator_state_root seam. This is distinct from, and does NOT reach, the
# install-baton rendezvous at $(coordinator-settings-home)/state/handoffs/ under
# default invocation; that folder is only reachable via an explicit
# --handoffs-glob/--parent-root override (C3 forward-guard).
# Spec backlink: docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md § C3
# ---------------------------------------------------------------------------
_build_uuid_blocklist() {
  # Strip trailing wildcard component to get the search root directory.
  # HANDOFFS_GLOB may be e.g. /tmp/handoffs/*.md or the resolved
  # $(coordinator_state_root)/handoffs/*.md default (test fixtures may also pass a
  # literal legacy-style path via --handoffs-glob).
  # We strip the last path component (the *.md part) to get the dir.
  local glob="$HANDOFFS_GLOB"

  # Remove the trailing /... or \... component after the last separator
  # Works on both forward-slash and backslash paths.
  local glob_dir
  # Use parameter expansion to strip from the last / or \ onward
  # For portability: strip everything from the last slash
  glob_dir="${glob%/*}"
  # Also handle backslash paths (Windows)
  if [[ "$glob_dir" == "$glob" ]]; then
    # No forward slash found — try stripping from last backslash
    glob_dir="${glob%\\*}"
  fi

  if [[ ! -d "$glob_dir" ]]; then
    # Directory doesn't exist (e.g. no-handoffs test fixture) — empty block-list
    echo ""
    return
  fi

  # Find all .md files and grep for predecessor UUID patterns.
  # Review: reviewer — BSD xargs has no -r; write find output to a temp file and
  # iterate to avoid hang when find returns zero results on macOS/BSD.
  local _md_list
  _md_list=$(mktemp 2>/dev/null) || _md_list="${TMPDIR:-/tmp}/_cruft_handoffs_$$"
  find "$glob_dir" -name "*.md" -type f 2>/dev/null > "$_md_list"
  if [[ -s "$_md_list" ]]; then
    while IFS= read -r _mf; do
      grep -hE '^predecessor:[[:space:]]*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$_mf" 2>/dev/null || true
    done < "$_md_list" \
      | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' \
      | sort -u \
      || true
  fi
  rm -f "$_md_list" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Helper: check if a UUID is in the block-list (newline-separated string)
# ---------------------------------------------------------------------------
_is_blocked() {
  local uuid="$1"
  local blocklist="$2"
  # Review: reviewer — guard against empty uuid or blocklist to prevent false matches (F8 fix).
  [[ -z "$uuid" || -z "$blocklist" ]] && return 1
  # Use printf + grep to avoid echo interpretation of special chars
  printf '%s\n' "$blocklist" | grep -qF "$uuid" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Phase A: harness retention sweep
# Sets global HARNESS_BYTES and HARNESS_ITEMS (avoids command substitution
# swallowing JSONL stdout).
# ---------------------------------------------------------------------------
HARNESS_BYTES=0
HARNESS_ITEMS=0

_sweep_harness() {
  local apply="$1"
  local json_mode="$2"

  local now
  now=$(date +%s)
  # Review: reviewer — split local+arithmetic into two lines for bash 3.2 safe-pattern
  # uniformity (arithmetic is safe here; style for review-trail consistency). (F14)
  local threshold_sec
  threshold_sec=$(( DAYS * 86400 ))

  # Build UUID block-list from active handoffs
  local blocklist
  blocklist=$(_build_uuid_blocklist)

  # Counters
  local pruned_dirs=0
  local pruned_jsonl=0
  local pruned_fh_dirs=0
  local total_bytes=0
  local skipped_blocked=0

  # -------------------------------------------------------------------------
  # Sweep 1: projects/<repo>/<uuid>/ directories
  # -------------------------------------------------------------------------
  # Watchdog: per-rm cap (cs_timeout) + cooperative wall-clock ceiling bail.
  # Best-effort bail — a D-state rm may also block cs_timeout; loop cannot
  # return until the kernel clears it.
  # Review: code-reviewer S2 — (F1,F3) updated ceiling/stall wording; reframed D-state guarantee.
  local _wd_uuid_bail=0
  local _wd_uuid_cnt=0
  cs_watchdog_reset
  if [[ -d "$PROJECTS_ROOT" ]]; then
    for repo_dir in "$PROJECTS_ROOT"/*/; do
      [[ -d "$repo_dir" ]] || continue
      # Skip remaining repos if watchdog already bailed on uuid sweep
      [[ "$_wd_uuid_bail" -eq 0 ]] || continue

      for uuid_dir in "$repo_dir"*/; do
        # Cooperative watchdog check — wall-clock ceiling bail (300s); stall arm is
        # intentionally dormant here (counter advances every iteration, so probe
        # output always changes and the stall threshold never fires).
        # Review: code-reviewer S2 — (F1) clarified ceiling-only operative; stall arm dormant.
        if ! cs_watchdog_check 300 6 5 printf '%s' "$_wd_uuid_cnt"; then
          printf '[cruft-sweep] wall-clock ceiling bail on harness uuid sweep after %d candidates examined; current repo jsonl and subsequent repos skipped — will finish next run\n' "$_wd_uuid_cnt" >&2
          _wd_uuid_bail=1
          break
        fi
        _wd_uuid_cnt=$(( _wd_uuid_cnt + 1 ))
        [[ -d "$uuid_dir" ]] || continue

        local dir_name
        dir_name=$(basename "$uuid_dir")

        # Only consider UUID-shaped names
        if ! echo "$dir_name" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
          continue
        fi

        local mtime
        mtime=$(_get_mtime "$uuid_dir")
        local age_sec
        age_sec=$(( now - mtime ))

        if [[ "$age_sec" -le "$threshold_sec" ]]; then
          continue
        fi

        # Check block-list
        if _is_blocked "$dir_name" "$blocklist"; then
          skipped_blocked=$(( skipped_blocked + 1 ))
          if [[ "$json_mode" -eq 1 ]]; then
            local size_bytes
            size_bytes=$(_dir_size_bytes "$uuid_dir")
            _emit_jsonl "harness" "$uuid_dir" "$dir_name" "$size_bytes" "$mtime" "skip" "predecessor uuid in active handoff"
          fi
          continue
        fi

        local size_bytes
        size_bytes=$(_dir_size_bytes "$uuid_dir")
        total_bytes=$(( total_bytes + size_bytes ))
        pruned_dirs=$(( pruned_dirs + 1 ))

        # Review: reviewer — emit auto-prune record unconditionally in json_mode; previously
        # suppressed in apply mode, breaking --apply --json audit-pipeline consumers.
        if [[ "$json_mode" -eq 1 ]]; then
          _emit_jsonl "harness" "$uuid_dir" "$dir_name" "$size_bytes" "$mtime" "auto-prune" "projects dir mtime ${age_sec}s > threshold ${threshold_sec}s"
        fi

        if [[ "$apply" -eq 1 ]]; then
          # 60s cap per rm — >60s means wedged; partial dir left is fine (idempotent)
          cs_timeout 60 -- rm -rf "$uuid_dir" 2>/dev/null || true
        fi
      done

      # -----------------------------------------------------------------------
      # Sweep 2: projects/<repo>/<uuid>.jsonl files
      # -----------------------------------------------------------------------
      # Review: code-reviewer S2 — (F2) guard added: if uuid bail fired for THIS repo's
      # uuid loop, skip its jsonl sweep too; the outer-repo continue at line 440 only
      # covers SUBSEQUENT repos.
      [[ "$_wd_uuid_bail" -eq 0 ]] || continue
      for jsonl_file in "$repo_dir"*.jsonl; do
        [[ -f "$jsonl_file" ]] || continue

        local file_name
        file_name=$(basename "$jsonl_file" .jsonl)

        if ! echo "$file_name" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
          continue
        fi

        local mtime
        mtime=$(_get_mtime "$jsonl_file")
        local age_sec
        age_sec=$(( now - mtime ))

        if [[ "$age_sec" -le "$threshold_sec" ]]; then
          continue
        fi

        if _is_blocked "$file_name" "$blocklist"; then
          skipped_blocked=$(( skipped_blocked + 1 ))
          if [[ "$json_mode" -eq 1 ]]; then
            local fsize
            fsize=$(_file_size "$jsonl_file")
            _emit_jsonl "harness" "$jsonl_file" "${file_name}.jsonl" "$fsize" "$mtime" "skip" "predecessor uuid in active handoff"
          fi
          continue
        fi

        local fsize
        fsize=$(_file_size "$jsonl_file")
        total_bytes=$(( total_bytes + fsize ))
        pruned_jsonl=$(( pruned_jsonl + 1 ))

        # Review: reviewer — emit auto-prune record unconditionally in json_mode (F1 fix).
        if [[ "$json_mode" -eq 1 ]]; then
          _emit_jsonl "harness" "$jsonl_file" "${file_name}.jsonl" "$fsize" "$mtime" "auto-prune" "transcript mtime ${age_sec}s > threshold ${threshold_sec}s"
        fi

        if [[ "$apply" -eq 1 ]]; then
          rm -f "$jsonl_file" 2>/dev/null || true
        fi
      done
    done
  fi

  # -------------------------------------------------------------------------
  # Sweep 3: file-history/<uuid>/ directories
  # -------------------------------------------------------------------------
  # Watchdog: independent ceiling/stall guard for fh-dir sweep.
  local _wd_fh_cnt=0
  cs_watchdog_reset
  if [[ -d "$FILE_HISTORY_ROOT" ]]; then
    for fh_dir in "$FILE_HISTORY_ROOT"/*/; do
      # Cooperative watchdog check — wall-clock ceiling bail (300s); stall arm is
      # intentionally dormant here (counter advances every iteration).
      # Review: code-reviewer S2 — (F1,F4) ceiling-only; "candidates examined".
      if ! cs_watchdog_check 300 6 5 printf '%s' "$_wd_fh_cnt"; then
        printf '[cruft-sweep] wall-clock ceiling bail on harness fh-dir sweep after %d candidates examined; will finish next run\n' "$_wd_fh_cnt" >&2
        break
      fi
      _wd_fh_cnt=$(( _wd_fh_cnt + 1 ))
      [[ -d "$fh_dir" ]] || continue

      local dir_name
      dir_name=$(basename "$fh_dir")

      if ! echo "$dir_name" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
        continue
      fi

      local mtime
      mtime=$(_get_mtime "$fh_dir")
      local age_sec
      age_sec=$(( now - mtime ))

      if [[ "$age_sec" -le "$threshold_sec" ]]; then
        continue
      fi

      if _is_blocked "$dir_name" "$blocklist"; then
        skipped_blocked=$(( skipped_blocked + 1 ))
        if [[ "$json_mode" -eq 1 ]]; then
          local size_bytes
          size_bytes=$(_dir_size_bytes "$fh_dir")
          _emit_jsonl "harness" "$fh_dir" "$dir_name" "$size_bytes" "$mtime" "skip" "predecessor uuid in active handoff"
        fi
        continue
      fi

      local size_bytes
      size_bytes=$(_dir_size_bytes "$fh_dir")
      total_bytes=$(( total_bytes + size_bytes ))
      pruned_fh_dirs=$(( pruned_fh_dirs + 1 ))

      # Review: reviewer — emit auto-prune record unconditionally in json_mode (F1 fix).
      if [[ "$json_mode" -eq 1 ]]; then
        _emit_jsonl "harness" "$fh_dir" "$dir_name" "$size_bytes" "$mtime" "auto-prune" "file-history dir mtime ${age_sec}s > threshold ${threshold_sec}s"
      fi

      if [[ "$apply" -eq 1 ]]; then
        # 60s cap per rm — >60s means wedged; partial dir left is fine (idempotent)
        cs_timeout 60 -- rm -rf "$fh_dir" 2>/dev/null || true
      fi
    done
  fi

  # -------------------------------------------------------------------------
  # Human-readable output (not with --json --dry-run)
  # -------------------------------------------------------------------------
  local total_items
  total_items=$(( pruned_dirs + pruned_jsonl + pruned_fh_dirs ))
  local total_mb
  total_mb=$(( total_bytes / 1048576 ))

  if [[ "$json_mode" -eq 0 && "$QUIET" -eq 0 ]]; then
    local mode_label="DRY-RUN"
    [[ "$apply" -eq 1 ]] && mode_label="APPLY"
    echo "[cruft-sweep] harness (${mode_label}, >${DAYS}d): ${total_items} items (${pruned_dirs} dirs + ${pruned_jsonl} jsonl + ${pruned_fh_dirs} fh-dirs), ~${total_mb} MB reclaimable${skipped_blocked:+, ${skipped_blocked} skipped (active handoff)}" >&2
  fi

  # -------------------------------------------------------------------------
  # Log append (apply mode only, inside the lock)
  # -------------------------------------------------------------------------
  if [[ "$apply" -eq 1 && "$total_items" -gt 0 ]]; then
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    local log_dir
    log_dir=$(dirname "$LOG_PATH")
    if [[ ! -d "$log_dir" ]]; then
      mkdir -p "$log_dir" 2>/dev/null || true
    fi
    printf '| %s | harness | %s bytes | %s items |\n' \
      "$ts" "$total_bytes" "$total_items" >> "$LOG_PATH" 2>/dev/null || true
  fi

  # Store results in globals (avoids command substitution eating JSONL stdout)
  HARNESS_BYTES="$total_bytes"
  HARNESS_ITEMS="$total_items"
}

# ---------------------------------------------------------------------------
# Phase B: in-repo scratch sweep
#
# Auto-prune list (name-anchored — exact directory names only):
#   tmp-cc/, nonexistent/, fake/, single-char [a-z]/, chain'd identical [a-z]/
#
# Pre-conditions for auto-prune (ALL must hold):
#   1. Untracked by git (ls-files --error-unmatch fails) OR git not available
#   2. mtime older than SCRATCH_AGE_DAYS (default 7)
#   3. NOT inside a .git/ boundary (any parent component is literally .git)
#   4. NOT in negative-spec list (archive, tasks, state, docs, node_modules,
#      .venv, __pycache__ as path components)
#   5. NOT a legitimate-backup class:
#      - name starts with _ (underscore-prefix)
#      - name matches *.bak* glob
#      - name matches *-bak-* glob
#      - name matches *.preisource-bak-* glob
#
# Confirm-needed names (REPORT ONLY — never auto-prune):
#   tmp/, scratch/, output/
#
# Sets globals SCRATCH_BYTES and SCRATCH_ITEMS (avoids command substitution
# swallowing JSONL stdout).
# ---------------------------------------------------------------------------
SCRATCH_BYTES=0
SCRATCH_ITEMS=0

# Helper: check if a directory name matches the auto-prune list
_is_auto_prune_name() {
  local name="$1"
  case "$name" in
    tmp-cc|nonexistent|fake)
      return 0
      ;;
    ?)
      # Single ASCII lowercase letter
      case "$name" in
        [a-z]) return 0 ;;
      esac
      ;;
  esac
  return 1
}

# Helper: check if a directory name matches the confirm-needed list
_is_confirm_needed_name() {
  local name="$1"
  case "$name" in
    tmp|scratch|output) return 0 ;;
  esac
  return 1
}

# Helper: check if a directory name is a legitimate-backup class (skip)
_is_backup_name() {
  local name="$1"
  # Underscore-prefix
  case "$name" in
    _*) return 0 ;;
  esac
  # *.bak* — contains ".bak" anywhere
  case "$name" in
    *.bak*) return 0 ;;
  esac
  # *-bak-* — contains "-bak-" anywhere
  case "$name" in
    *-bak-*) return 0 ;;
  esac
  # *.preisource-bak-* — contains ".preisource-bak-" anywhere
  case "$name" in
    *.preisource-bak-*) return 0 ;;
  esac
  return 1
}

# Helper: check if a path has any component that is literally ".git"
_has_git_boundary() {
  local path="$1"
  # Review: reviewer — normalize backslash paths (Windows Git-Bash) before IFS split (F5 fix).
  path="${path//\\//}"
  # Split path on / and check each component
  local oldIFS="$IFS"
  IFS="/"
  local part
  local found=1
  for part in $path; do
    if [[ "$part" = ".git" ]]; then
      found=0
      break
    fi
  done
  IFS="$oldIFS"
  return $found
}

# Helper: check if a path has any component in the negative-spec list
_has_negative_spec_component() {
  local path="$1"
  # Review: reviewer — normalize backslash paths (Windows Git-Bash) before IFS split (F5 fix).
  path="${path//\\//}"
  local oldIFS="$IFS"
  IFS="/"
  local part
  local found=1
  for part in $path; do
    case "$part" in
      archive|tasks|state|docs|node_modules|.venv|__pycache__)
        found=0
        break
        ;;
    esac
  done
  IFS="$oldIFS"
  return $found
}

# Helper: check if a chained single-char dir (e.g. z/z/z/) is auto-prune.
# A dir is a chained identical single-char dir if it is itself a [a-z] dir
# that contains only another [a-z]/ dir (recursively, to any depth).
# We only need to detect that the top-level single-char dir qualifies —
# _is_auto_prune_name already matches [a-z], so chain detection means
# we prune the entire tree when the top-level is a single-char [a-z] name.
# No additional function needed — _is_auto_prune_name handles [a-z].

# Helper: check if a path is untracked by git (returns 0 if untracked/not-in-repo)
_is_untracked() {
  local repo_root="$1"
  local path="$2"
  # If git isn't available, treat as untracked
  if ! command -v git >/dev/null 2>&1; then
    return 0
  fi
  # If the directory isn't a git repo, treat as untracked
  if ! git -C "$repo_root" rev-parse --git-dir >/dev/null 2>&1; then
    return 0
  fi
  # ls-files --error-unmatch exits non-zero if path is untracked
  local rel_path="${path#${repo_root}/}"
  if git -C "$repo_root" ls-files --error-unmatch "$rel_path" >/dev/null 2>&1; then
    # Tracked by git — NOT untracked
    return 1
  fi
  # Check if it's explicitly ignored
  if git -C "$repo_root" check-ignore -q "$path" 2>/dev/null; then
    return 0
  fi
  # Not tracked and not explicitly ignored — still treat as untracked
  # (git ls-files --error-unmatch failed = untracked)
  return 0
}

_sweep_scratch() {
  local apply="$1"
  local json_mode="$2"

  local now
  now=$(date +%s)
  local threshold_sec
  threshold_sec=$(( SCRATCH_AGE_DAYS * 86400 ))

  # Resolve repo root: use --repo-root override, else git rev-parse, else cwd
  local repo_root
  if [[ -n "$REPO_ROOT" ]]; then
    repo_root="$REPO_ROOT"
  else
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || repo_root="$(pwd)"
  fi

  local total_bytes=0
  local pruned_items=0
  local confirm_needed_count=0

  # Enumerate candidate directories into a temp file to avoid subshell
  # variable-loss when using find | while pipelines.
  local _scratch_dir_list
  _scratch_dir_list=$(mktemp 2>/dev/null) || _scratch_dir_list="${TMPDIR:-/tmp}/_cruft_scratch_$$"
  # Review: reviewer — ASCII sort guarantees parent-before-child ordering, which is required
  # by the pruned-parents skip logic downstream (child paths sort after their parent prefix). (F11)
  find "$repo_root" -mindepth 1 -type d -print 2>/dev/null | sort > "$_scratch_dir_list"

  # Track already-queued-for-prune parents to skip their children
  local _pruned_parents_file
  _pruned_parents_file=$(mktemp 2>/dev/null) || _pruned_parents_file="${TMPDIR:-/tmp}/_cruft_pruned_$$"

  # Watchdog: independent wall-clock ceiling bail for scratch sweep (stall arm dormant).
  # Review: code-reviewer S2 — (F1) ceiling-only; stall arm intentionally dormant.
  local _wd_scratch_cnt=0
  cs_watchdog_reset
  while IFS= read -r dir_path; do
    # Cooperative watchdog check — wall-clock ceiling bail (300s); stall arm dormant.
    if ! cs_watchdog_check 300 6 5 printf '%s' "$_wd_scratch_cnt"; then
      printf '[cruft-sweep] wall-clock ceiling bail on scratch sweep after %d candidates examined; will finish next run\n' "$_wd_scratch_cnt" >&2
      break
    fi
    _wd_scratch_cnt=$(( _wd_scratch_cnt + 1 ))

    # Skip if a parent of this path has already been queued for pruning
    # (i.e. rm -rf of the parent will delete this child too)
    local _is_child=0
    while IFS= read -r _parent; do
      case "$dir_path" in
        "${_parent}/"*) _is_child=1; break ;;
      esac
    done < "$_pruned_parents_file"
    if [[ "$_is_child" -eq 1 ]]; then
      continue
    fi

    local dir_name
    dir_name=$(basename "$dir_path")

    # Pre-condition 3: NOT inside a .git/ boundary
    if _has_git_boundary "$dir_path"; then
      continue
    fi

    # Pre-condition 4: NOT in negative-spec list (check path components)
    if _has_negative_spec_component "$dir_path"; then
      continue
    fi

    # Pre-condition 5: NOT a legitimate-backup class
    if _is_backup_name "$dir_name"; then
      # Emit skip record only if the name would otherwise match auto-prune/confirm
      if _is_auto_prune_name "$dir_name" || _is_confirm_needed_name "$dir_name"; then
        local mtime size_bytes
        mtime=$(_get_mtime "$dir_path")
        size_bytes=$(_dir_size_bytes "$dir_path")
        if [[ "$json_mode" -eq 1 ]]; then
          _emit_jsonl "scratch" "$dir_path" "$dir_name" "$size_bytes" "$mtime" "skip" "legitimate-backup name class"
        fi
      fi
      continue
    fi

    # Check confirm-needed list — report but never auto-prune
    if _is_confirm_needed_name "$dir_name"; then
      local mtime size_bytes
      mtime=$(_get_mtime "$dir_path")
      size_bytes=$(_dir_size_bytes "$dir_path")
      if [[ "$json_mode" -eq 1 ]]; then
        _emit_jsonl "scratch" "$dir_path" "$dir_name" "$size_bytes" "$mtime" "confirm-needed" "name in confirm-list — Layer 2 owns"
      fi
      confirm_needed_count=$(( confirm_needed_count + 1 ))
      continue
    fi

    # Check auto-prune list
    if _is_auto_prune_name "$dir_name"; then
      local mtime age_sec
      mtime=$(_get_mtime "$dir_path")

      # Review: reviewer F3 — fail-safe when mtime resolution fails on platforms
      # without stat or Python (e.g. Windows Git-Bash without Python on PATH).
      # mtime=0 would produce a huge age_sec, bypassing all gates and silently
      # deleting. Skip with stderr notice instead (preserve-on-doubt).
      if [[ "$mtime" -eq 0 ]]; then
        if [[ "$QUIET" -eq 0 ]]; then
          printf '[cruft-sweep] mtime-resolution-failed skip: %s\n' "$dir_path" >&2
        fi
        continue
      fi

      age_sec=$(( now - mtime ))

      # Consolidated age gate (RD-2, F1+F2):
      #   effective_threshold = max(configured_threshold, 24h hard floor)
      # The 24h floor is a HARD minimum regardless of --scratch-age configuration
      # (mirrors handoff-archival.md § "Mechanical mtime veto"; prevents deletion of
      # in-flight scratch dirs during handoff/pickup gaps). Using max() keeps the
      # floor always load-bearing even with --scratch-age 0 or --scratch-age 1, where
      # the old two-gate approach made the floor unreachable.
      # Spec: docs/plans/2026-06-14-deep-research-workdir-out-of-killzone.md RD-2.
      local effective_threshold
      effective_threshold=$(( threshold_sec > 86400 ? threshold_sec : 86400 ))

      if [[ "$age_sec" -le "$effective_threshold" ]]; then
        if [[ "$json_mode" -eq 1 ]]; then
          local size_bytes
          size_bytes=$(_dir_size_bytes "$dir_path")
          # Discriminate skip reason: floor is the operative gate when age <= 24h
          # (the 24h floor is the intended defense; age-threshold is the normal
          # configured gate). A dir <= 24h always cites mtime-floor even when the
          # configured threshold also covers it — this makes the floor visible to
          # --json callers and test assertions.
          if [[ "$age_sec" -le 86400 ]]; then
            _emit_jsonl "scratch" "$dir_path" "$dir_name" "$size_bytes" "$mtime" "skip" "mtime ${age_sec}s <= 86400s (mtime-floor)"
          else
            _emit_jsonl "scratch" "$dir_path" "$dir_name" "$size_bytes" "$mtime" "skip" "mtime ${age_sec}s <= threshold ${threshold_sec}s (age-threshold)"
          fi
        fi
        continue
      fi

      # Pre-condition 1: untracked by git
      if ! _is_untracked "$repo_root" "$dir_path"; then
        if [[ "$json_mode" -eq 1 ]]; then
          local size_bytes
          size_bytes=$(_dir_size_bytes "$dir_path")
          _emit_jsonl "scratch" "$dir_path" "$dir_name" "$size_bytes" "$mtime" "skip" "tracked by git"
        fi
        continue
      fi

      # All gates passed — compute size once for the prunable path
      local size_bytes
      size_bytes=$(_dir_size_bytes "$dir_path")
      total_bytes=$(( total_bytes + size_bytes ))
      pruned_items=$(( pruned_items + 1 ))

      # Record this parent so we skip its children in subsequent iterations
      printf '%s\n' "$dir_path" >> "$_pruned_parents_file"

      if [[ "$json_mode" -eq 1 ]]; then
        _emit_jsonl "scratch" "$dir_path" "$dir_name" "$size_bytes" "$mtime" "auto-prune" "name in auto-prune list; mtime ${age_sec}s > effective_threshold ${effective_threshold}s"
      fi

      if [[ "$apply" -eq 1 ]]; then
        # 60s cap per rm — >60s means wedged; partial dir left is fine (idempotent)
        cs_timeout 60 -- rm -rf "$dir_path" 2>/dev/null || true
      fi
    fi

  done < "$_scratch_dir_list"

  rm -f "$_scratch_dir_list" "$_pruned_parents_file" 2>/dev/null || true

  # -------------------------------------------------------------------------
  # Human-readable output (not with --json --dry-run)
  # -------------------------------------------------------------------------
  local total_mb
  total_mb=$(( total_bytes / 1048576 ))

  if [[ "$json_mode" -eq 0 && "$QUIET" -eq 0 ]]; then
    local mode_label="DRY-RUN"
    [[ "$apply" -eq 1 ]] && mode_label="APPLY"
    echo "[cruft-sweep] scratch (${mode_label}, >${SCRATCH_AGE_DAYS}d): ${pruned_items} items auto-pruned, ${confirm_needed_count} confirm-needed, ~${total_mb} MB reclaimable" >&2
    if [[ "$confirm_needed_count" -gt 0 ]]; then
      echo "[cruft-sweep] scratch: ${confirm_needed_count} confirm-needed item(s) require Layer 2 review (run with --class scratch --json to enumerate)" >&2
    fi
  fi

  # -------------------------------------------------------------------------
  # Log append (apply mode only, inside the lock)
  # -------------------------------------------------------------------------
  if [[ "$apply" -eq 1 && "$pruned_items" -gt 0 ]]; then
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    local log_dir
    log_dir=$(dirname "$LOG_PATH")
    if [[ ! -d "$log_dir" ]]; then
      mkdir -p "$log_dir" 2>/dev/null || true
    fi
    printf '| %s | scratch | %s bytes | %s items |\n' \
      "$ts" "$total_bytes" "$pruned_items" >> "$LOG_PATH" 2>/dev/null || true
  fi

  # Store results in globals
  SCRATCH_BYTES="$total_bytes"
  SCRATCH_ITEMS="$pruned_items"
}

# ---------------------------------------------------------------------------
# Phase C: parent-altitude orphan sweep
#
# Scans top-level children of each parent root. Auto-prunes ONLY when BOTH:
#   1. Name match — literal cruft list: nonexistent, tmp, tmp-cc, fake, null,
#      undefined, untitled* (glob), or single-char [a-z]
#   2. Fingerprint match — child contains at least one sonnet-default artifact:
#      - vector/store/chroma.sqlite3
#      - project/Saved/ProjectRag/vector_store/chroma.sqlite3
#      - lone mcp_queries.jsonl (file at child root, no other significant files)
#
# Hard-exclude (NEVER swept, checked BEFORE the gate, even if name+fingerprint
# both match — per the Staff Engineer review requirement):
#   - Child name is literally: state, docs, archive
#   - Child contains CLAUDE.md or CLAUDE.local.md at its root
#   - Child name is: $RECYCLE.BIN, System Volume Information, .github-private
#   - Child appears in machine-local registry parent_whitelist
#
# Skip (emits JSONL record but does NOT prune) when name matches but
# fingerprint does NOT. Silent when name does NOT match.
#
# Default parent roots: X:/ and E:/dev/ (forward-slash, Windows convention).
# Override: --parent-root <path> (repeatable; replaces defaults entirely).
#
# Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C2 Phase C
#
# Sets globals ORPHANS_BYTES and ORPHANS_ITEMS.
# ---------------------------------------------------------------------------
ORPHANS_BYTES=0
ORPHANS_ITEMS=0

# Helper: check if a child name matches the orphan auto-prune name list
_is_orphan_name_match() {
  local name="$1"
  case "$name" in
    nonexistent|tmp|tmp-cc|fake|null|undefined)
      return 0
      ;;
    untitled*)
      return 0
      ;;
    ?)
      # Single ASCII lowercase letter
      case "$name" in
        [a-z]) return 0 ;;
      esac
      ;;
  esac
  return 1
}

# Helper: check if a child directory has a sonnet-default fingerprint.
# Returns 0 (match) if any fingerprint artifact is found.
_has_sonnet_fingerprint() {
  local child="$1"

  # Fingerprint 1: vector/store/chroma.sqlite3
  if [[ -f "${child}/vector/store/chroma.sqlite3" ]]; then
    return 0
  fi

  # Fingerprint 2: project/Saved/ProjectRag/vector_store/chroma.sqlite3
  if [[ -f "${child}/project/Saved/ProjectRag/vector_store/chroma.sqlite3" ]]; then
    return 0
  fi

  # Fingerprint 3: lone mcp_queries.jsonl at top of child (no other significant files)
  if [[ -f "${child}/mcp_queries.jsonl" ]]; then
    # "Lone" means no other significant files at top level.
    # Count non-hidden top-level entries; tolerate only the one .jsonl.
    local _count=0
    local _entry
    # Use find with -maxdepth 1 to list only direct children
    for _entry in "${child}/"*; do
      # Skip glob no-match
      [[ -e "$_entry" ]] || continue
      _count=$(( _count + 1 ))
    done
    if [[ "$_count" -le 1 ]]; then
      return 0
    fi
  fi

  return 1
}

# Helper: read machine-local registry parent_whitelist (lossy grep approach)
_get_parent_whitelist() {
  # Resolve machine-local dir via the settings-home seam (C1); no hardcoded ~/.claude path.
  # Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2b
  local _registry="$(_coordinator_settings_home)/machine-local/registry.local.toml"
  if [[ ! -f "$_registry" ]]; then
    echo ""
    return
  fi
  # Grep for parent_whitelist = [...] and extract quoted strings inside brackets.
  # Lossy: handles only simple single-line arrays like parent_whitelist = ["foo", "bar"].
  # Review: reviewer — multi-line TOML arrays are NOT parsed — entries on continuation
  # lines will be silently ignored. Write parent_whitelist as a single-line array. (F15)
  local _raw
  _raw=$(grep 'parent_whitelist' "$_registry" 2>/dev/null | grep -oE '"[^"]*"' | tr -d '"' || true)
  if [[ -z "$_raw" ]] && grep -q 'parent_whitelist' "$_registry" 2>/dev/null; then
    echo "cruft-sweep: WARNING: parent_whitelist found in registry but yielded no entries — if using multi-line TOML syntax, entries are silently ignored. Use single-line: parent_whitelist = [\"name\"]" >&2
  fi
  echo "$_raw"
}

# Portable default parent roots: the unique parent directories of registered
# machine-local [repos]. Replaces the former hardcoded ("X:/" "E:/dev/") single-machine
# default that resolved to nothing on every other machine (2026-06-19 portability sweep).
# Emits one path per line; empty if machine-local is unavailable (caller's [[ -d ]] guard
# then no-ops, as it did with the absent hardcoded drives).
_default_parent_roots() {
  local _ml="${COORDINATOR_CONTENT_ROOT}/bin/machine-local"
  [[ -x "$_ml" ]] || return 0
  local _key _p
  while IFS= read -r _key; do
    [[ -n "$_key" ]] || continue
    _p="$("$_ml" get "$_key" 2>/dev/null || true)"
    [[ -n "$_p" ]] || continue
    dirname "$_p"
  done < <("$_ml" keys 2>/dev/null | grep '^repos\.' || true) | awk '!seen[$0]++'
}

_sweep_orphans() {
  local apply="$1"
  local json_mode="$2"

  # Determine parent roots.
  # Review: reviewer — use array to support paths with spaces (F10 fix).
  local _roots_arr=()
  if [[ "${#PARENT_ROOTS[@]}" -gt 0 ]]; then
    _roots_arr=("${PARENT_ROOTS[@]}")
  else
    # Portable default: parent dirs of registered machine-local [repos] (was hardcoded
    # single-machine drives "X:/" "E:/dev/"). --parent-root still overrides.
    local _r
    while IFS= read -r _r; do
      [[ -n "$_r" ]] && _roots_arr+=("$_r")
    done < <(_default_parent_roots)
  fi

  # Load machine-local whitelist (newline-separated names)
  local _whitelist
  _whitelist=$(_get_parent_whitelist)

  local total_bytes=0
  local pruned_items=0
  # Review: reviewer — track name-matched-but-no-fingerprint skips for banner (F6 fix).
  local skipped_name_match=0

  # Process each parent root
  # Watchdog: per-rm cap (cs_timeout) + cooperative wall-clock ceiling bail (stall arm dormant).
  # Review: code-reviewer S2 — (F1) ceiling-only; stall arm intentionally dormant.
  local _wd_bail=0
  local _wd_cnt=0
  cs_watchdog_reset
  local _root
  for _root in "${_roots_arr[@]}"; do
    [[ -n "$_root" ]] || continue
    [[ -d "$_root" ]] || continue
    # Skip remaining roots if watchdog already bailed on orphan sweep
    [[ "$_wd_bail" -eq 0 ]] || continue

    # Enumerate top-level children only (one level deep)
    for child_path in "${_root%/}"/*/; do
      # Cooperative watchdog check — wall-clock ceiling bail (300s); stall arm dormant.
      if ! cs_watchdog_check 300 6 5 printf '%s' "$_wd_cnt"; then
        printf '[cruft-sweep] wall-clock ceiling bail on orphan sweep after %d candidates examined; will finish next run\n' "$_wd_cnt" >&2
        _wd_bail=1
        break
      fi
      _wd_cnt=$(( _wd_cnt + 1 ))
      # Handle case where glob matches nothing
      [[ -d "$child_path" ]] || continue

      local child_name
      child_name=$(basename "$child_path")

      # --- Hard-exclude: system / reserved names ---
      case "$child_name" in
        'state'|'docs'|'archive'|\
        '$RECYCLE.BIN'|'System Volume Information'|'.github-private')
          # Hard-excluded — always silent. At parent-altitude, 'docs' is the child
          # name that covers the docs/wiki/ hard-exclude requirement — Phase C does
          # not recurse. Gate fires before the name-match check. (F3 clarification)
          continue
          ;;
      esac

      # --- Hard-exclude (C3 forward-guard): install-baton rendezvous folder ---
      # PARENT_ROOTS defaults are machine-local repo parent dirs (Phase A) — a
      # settings-home path never reaches here under DEFAULT invocation, so this
      # branch is a no-op today. But --parent-root is user-overridable, so IF a
      # future invocation ever passes settings-home (or its 'state' subdir)
      # directly as --parent-root, the literal 'state' name-exclude above only
      # protects the one-level-deep case (parent-root == settings-home root).
      # This explicit path-compare additionally protects the rendezvous folder
      # itself (parent-root == settings-home/state, making 'handoffs' the
      # top-level child) and stays correct even if Phase C is ever deepened past
      # one level of recursion. Resolution failure (resolver missing/unset) is
      # fail-safe here: the guard simply does not fire, matching the seam's
      # own fail-open contract elsewhere in this script — it does not mask an
      # otherwise-required resolution, since Phase C's default parent roots
      # never include settings-home in the first place.
      # Spec backlink: docs/plans/2026-07-08-install-baton-rendezvous-off-dotclaude.md § C3
      # Review: code-reviewer — scope these scratch vars local, matching the
      # function's own local-declaration convention (avoids leaking into
      # enclosing scope after the function returns).
      local _cs_settings_home _cs_rendezvous_dir _cs_settings_state_dir _cs_child_norm
      if _cs_settings_home="$(_coordinator_settings_home 2>/dev/null)" && [[ -n "$_cs_settings_home" ]]; then
        _cs_rendezvous_dir="${_cs_settings_home%/}/state/handoffs"
        _cs_settings_state_dir="${_cs_settings_home%/}/state"
        _cs_child_norm="${child_path%/}"
        case "$_cs_child_norm" in
          "$_cs_rendezvous_dir"|"$_cs_settings_state_dir")
            continue
            ;;
        esac
      fi

      # --- Hard-exclude: machine-local whitelist ---
      if [[ -n "$_whitelist" ]] && printf '%s\n' "$_whitelist" | grep -qxF "$child_name" 2>/dev/null; then
        continue
      fi

      # --- Hard-exclude: CLAUDE.md or CLAUDE.local.md at child root ---
      if [[ -f "${child_path}CLAUDE.md" || -f "${child_path}CLAUDE.local.md" ]]; then
        continue
      fi

      # --- Name match check ---
      if ! _is_orphan_name_match "$child_name"; then
        # Not name-matched — silent (per spec: do NOT emit any record)
        continue
      fi

      # Name matched — now check fingerprint
      local size_bytes mtime
      size_bytes=$(_dir_size_bytes "$child_path")
      mtime=$(_get_mtime "$child_path")

      if ! _has_sonnet_fingerprint "$child_path"; then
        # Name matched but no fingerprint — emit skip record; count for banner (F6 fix).
        skipped_name_match=$(( skipped_name_match + 1 ))
        if [[ "$json_mode" -eq 1 ]]; then
          _emit_jsonl "orphans" "$child_path" "$child_name" "$size_bytes" "$mtime" \
            "skip" "name matched but no sonnet-fingerprint contents — Layer 2 broader scan owns"
        fi
        continue
      fi

      # Both name AND fingerprint match — auto-prune candidate
      total_bytes=$(( total_bytes + size_bytes ))
      pruned_items=$(( pruned_items + 1 ))

      if [[ "$json_mode" -eq 1 && "$apply" -eq 0 ]]; then
        _emit_jsonl "orphans" "$child_path" "$child_name" "$size_bytes" "$mtime" \
          "auto-prune" "name in orphan cruft list; sonnet-fingerprint contents confirmed"
      fi

      if [[ "$apply" -eq 1 ]]; then
        if [[ "$json_mode" -eq 1 ]]; then
          _emit_jsonl "orphans" "$child_path" "$child_name" "$size_bytes" "$mtime" \
            "auto-prune" "name in orphan cruft list; sonnet-fingerprint contents confirmed"
        fi
        # 60s cap per rm — >60s means wedged; partial dir left is fine (idempotent)
        cs_timeout 60 -- rm -rf "$child_path" 2>/dev/null || true
      fi
    done
  done

  # -------------------------------------------------------------------------
  # Human-readable output (not with --json --dry-run)
  # -------------------------------------------------------------------------
  local total_mb
  total_mb=$(( total_bytes / 1048576 ))

  if [[ "$json_mode" -eq 0 && "$QUIET" -eq 0 ]]; then
    local mode_label="DRY-RUN"
    [[ "$apply" -eq 1 ]] && mode_label="APPLY"
    # Review: reviewer — include name-matched-no-fingerprint count in banner (F6 fix).
    echo "[cruft-sweep] orphans (${mode_label}): ${pruned_items} items auto-pruned, ${skipped_name_match} name-matched-no-fingerprint, ~${total_mb} MB reclaimable" >&2
  fi

  # -------------------------------------------------------------------------
  # Log append (apply mode only, inside the lock)
  # -------------------------------------------------------------------------
  if [[ "$apply" -eq 1 && "$pruned_items" -gt 0 ]]; then
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    local log_dir
    log_dir=$(dirname "$LOG_PATH")
    if [[ ! -d "$log_dir" ]]; then
      mkdir -p "$log_dir" 2>/dev/null || true
    fi
    printf '| %s | orphans | %s bytes | %s items |\n' \
      "$ts" "$total_bytes" "$pruned_items" >> "$LOG_PATH" 2>/dev/null || true
  fi

  # Store results in globals
  ORPHANS_BYTES="$total_bytes"
  ORPHANS_ITEMS="$pruned_items"
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

case "$CLASS" in
  harness)
    _sweep_harness "$APPLY" "$JSON_MODE"
    ;;
  scratch)
    _sweep_scratch "$APPLY" "$JSON_MODE"
    ;;
  orphans)
    _sweep_orphans "$APPLY" "$JSON_MODE"
    ;;
  all)
    # Phase A: harness
    _sweep_harness "$APPLY" "$JSON_MODE"
    # Phase B: scratch
    _sweep_scratch "$APPLY" "$JSON_MODE"
    # Phase C: orphans
    _sweep_orphans "$APPLY" "$JSON_MODE"
    ;;
esac

# Grand total banner — emitted to stderr in all modes EXCEPT --json (which owns stdout).
# Under --quiet the per-class banners are suppressed (see lines 550, 869, 1106) but the
# grand total IS still emitted: it is the only signal /workday-start Step 1.11 reads to
# check the 1 GB advisory threshold. Suppressing it under --quiet (the prior bug)
# silently broke the briefing's threshold detector — empirical: 2.7 GB sitting
# reclaimable with the morning briefing reading "0 reclaimable" — see
# docs/wiki/cruft-sweep-cadence.md § --quiet output contract.
_total_all_bytes=$(( HARNESS_BYTES + SCRATCH_BYTES + ORPHANS_BYTES ))
_total_all_items=$(( ${HARNESS_ITEMS:-0} + ${SCRATCH_ITEMS:-0} + ${ORPHANS_ITEMS:-0} ))
if [[ "$JSON_MODE" -eq 0 ]]; then
  _total_all_mb=$(( _total_all_bytes / 1048576 ))
  echo "[cruft-sweep] grand total: ~${_total_all_mb} MB reclaimable across all classes" >&2
fi

# Run-marker log row — written unconditionally on --apply runs, even when zero items
# were pruned. /workday-start Step 1.11's staleness arm reads `tail -1 cruft-sweep-log.md`
# and treats file-absent OR oldest-row > 14d as stale. Without a marker row, every
# /workday-complete Step 1.5 sweep on a clean machine leaves the staleness clock
# unfed — the morning advisory would fire the staleness branch every day after 14d
# even though sweeps ran nightly and found nothing. Per-class rows above remain
# items-gated (forensic detail); this trailing row is the staleness signal.
# Reviewer-flagged 2026-06-14 (F4); see workday-complete Step 1.5 cadence rationale.
if [[ "$APPLY" -eq 1 && "$JSON_MODE" -eq 0 ]]; then
  _marker_ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  _marker_log_dir=$(dirname "$LOG_PATH")
  [[ -d "$_marker_log_dir" ]] || mkdir -p "$_marker_log_dir" 2>/dev/null || true
  printf '| %s | run-marker | %s bytes | %s items |\n' \
    "$_marker_ts" "$_total_all_bytes" "$_total_all_items" >> "$LOG_PATH" 2>/dev/null || true
fi

exit 0
