#!/bin/bash
# coordinator-session.sh — Session tracking library for scoped safety commits
#
# Provides functions for:
#   - Session lifecycle: init, archive, reap
#   - Touch tracking: append-deduped file paths to per-session touched.txt
#   - Scope computation: MY_SCOPE = (touched ∪ mtime_dirty) − other_sessions
#   - Orphan detection: dirty files claimed by no session
#   - Active session list with Live/Stale liveness classification
#
# Source this file, then call the functions below. All functions require
# COORDINATOR_SESSION_ID to be set (export it before sourcing, or pass -s <id>).
#
# Session store layout:
#   .git/coordinator-sessions/
#   ├── <session-id>/
#   │   ├── started_at      ISO-8601 timestamp of session start
#   │   ├── head_at_start   git SHA at session start
#   │   ├── touched.txt     one repo-relative path per line (append-only, deduped)
#   │   └── meta.json       { "session_id", "branch", "pid", "last_activity", "goal" }
#   └── .archive/
#       └── <session-id>-<YYYY-MM-DD>/   archived after session-end or handoff
#
# Designed to be sourced, not executed directly. Safe to source multiple times.
# Bash only — no jq dependency on the hot path (touch append). jq used only in
# functions where it's available and where sed fallback is provided.

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# _cs_git_root: print the git root for the current directory, or empty on fail
_cs_git_root() {
  git rev-parse --show-toplevel 2>/dev/null || true
}

# _cs_sessions_dir: print path to .git/coordinator-sessions/
_cs_sessions_dir() {
  local root
  root=$(_cs_git_root)
  if [[ -z "$root" ]]; then
    echo "" ; return 1
  fi
  echo "${root}/.git/coordinator-sessions"
}

# _cs_session_dir <session_id>: print path to a specific session's directory
_cs_session_dir() {
  local sid="${1:?session_id required}"
  local base
  base=$(_cs_sessions_dir) || return 1
  echo "${base}/${sid}"
}

# _cs_now_iso: ISO-8601 timestamp (seconds resolution, UTC)
_cs_now_iso() {
  date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ"
}

# _cs_now_epoch: seconds since epoch
_cs_now_epoch() {
  date +%s 2>/dev/null || echo 0
}

# _cs_pid_alive <pid>: exit 0 if PID is alive, 1 if not
_cs_pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

# _cs_mtime_epoch <file>: print mtime as epoch seconds, cross-platform
_cs_mtime_epoch() {
  local f="${1:?file required}"
  [[ -f "$f" ]] || { echo 0; return; }
  if [[ "$OSTYPE" == darwin* ]]; then
    stat -f %m "$f" 2>/dev/null || echo 0
  else
    stat -c %Y "$f" 2>/dev/null || echo 0
  fi
}

# _cs_iso_to_epoch <iso>: convert ISO-8601 to epoch seconds
# Supports YYYY-MM-DDTHH:MM:SSZ format only (our output format).
_cs_iso_to_epoch() {
  local iso="${1:-}"
  if [[ -z "$iso" ]]; then echo 0; return; fi
  # Try GNU date first, then BSD date, then fall back to python
  local epoch
  epoch=$(date -u -d "$iso" +%s 2>/dev/null) \
    || epoch=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null) \
    || epoch=$(python3 -c 'import sys, datetime; iso=sys.argv[1]; iso = iso[:-1] if iso.endswith("Z") else iso; print(int(datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.timezone.utc).timestamp()))' "$iso" 2>/dev/null) \
    || epoch=0
  echo "$epoch"
}

# _cs_read_meta_field <session_dir> <field>: extract a JSON field from meta.json
# Uses jq if available, otherwise sed fallback.
_cs_read_meta_field() {
  local sdir="${1:?}" field="${2:?}"
  local meta="${sdir}/meta.json"
  [[ -f "$meta" ]] || { echo ""; return; }
  if command -v jq &>/dev/null; then
    # W6.2: pass field via --arg to jq (no shell interpolation into jq filter).
    jq --arg f "$field" -r '.[$f] // empty' "$meta" 2>/dev/null || true
  else
    # W6.4: sed fallback — used only when jq is unavailable. The regex
    # interpolates ${field} into the pattern; callers MUST ensure $field is a
    # safe identifier (matching ^[a-zA-Z_][a-zA-Z0-9_]*$). The internal API
    # only uses literal field names ("pid", "started_at"), never user input.
    # If a future caller passes user-controlled field names, switch to a
    # python/awk fallback or hard-fail.
    sed -n "s/.*\"${field}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$meta" | head -1
  fi
}

# _cs_update_meta_field <session_dir> <field> <value>: update one field in meta.json
# Rewrites the file — only called on low-frequency paths (touch records, not the
# hot append path).
_cs_update_meta_field() {
  local sdir="${1:?}" field="${2:?}" value="${3:?}"
  local meta="${sdir}/meta.json"
  [[ -f "$meta" ]] || return 1
  if command -v jq &>/dev/null; then
    # W6.3: pass both field and value via --arg (no shell interpolation into jq filter).
    local tmp
    tmp=$(jq --arg f "$field" --arg v "$value" '.[$f] = $v' "$meta" 2>/dev/null) && echo "$tmp" > "$meta"
  else
    # W6.4: sed in-place fallback — used only when jq is unavailable. ${field}
    # and ${value} are interpolated into the regex/replacement; callers MUST
    # ensure neither contains regex metacharacters or sed delimiter characters.
    # The internal API only writes literal field names + sanitized session
    # values (PIDs, ISO timestamps), never user input. If a future caller
    # passes user-controlled values, switch to a python/awk fallback.
    sed -i "s/\"${field}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"/\"${field}\": \"${value}\"/" "$meta" 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# cs_init <session_id> [goal]
#   Create session directory and write initial files.
#   Idempotent: if session dir already exists, refreshes meta.json activity only.
#   Returns 0 on success, 1 on failure (not in a git repo, etc.)
cs_init() {
  local sid="${1:?session_id required}"
  local goal="${2:-}"
  local base sdir
  base=$(_cs_sessions_dir) || return 1
  sdir="${base}/${sid}"

  mkdir -p "$sdir"

  # started_at — write only if missing (idempotent)
  if [[ ! -f "${sdir}/started_at" ]]; then
    _cs_now_iso > "${sdir}/started_at"
  fi

  # head_at_start — write only if missing
  if [[ ! -f "${sdir}/head_at_start" ]]; then
    git rev-parse HEAD 2>/dev/null > "${sdir}/head_at_start" || echo "unknown" > "${sdir}/head_at_start"
  fi

  # touched.txt — create if missing
  if [[ ! -f "${sdir}/touched.txt" ]]; then
    touch "${sdir}/touched.txt"
  fi

  # meta.json — always refresh pid and last_activity; write goal only on first create
  local branch now pid existing_goal
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  now=$(_cs_now_iso)
  pid=$$

  if [[ -f "${sdir}/meta.json" ]]; then
    existing_goal=$(_cs_read_meta_field "$sdir" "goal")
    [[ -z "$goal" ]] && goal="$existing_goal"
    _cs_update_meta_field "$sdir" "pid" "$pid"
    _cs_update_meta_field "$sdir" "last_activity" "$now"
    _cs_update_meta_field "$sdir" "branch" "$branch"
  else
    cat > "${sdir}/meta.json" <<METAJSON
{
  "session_id": "${sid}",
  "branch": "${branch}",
  "pid": "${pid}",
  "last_activity": "${now}",
  "goal": "${goal}"
}
METAJSON
  fi

  return 0
}

# cs_write_sentinel <session_id>
#   Atomically write the sentinel file (.current-session-id) so readers never
#   observe a partial write. Uses tempfile + mv -f (rename is atomic on most
#   POSIX filesystems). On Windows + Git Bash, antivirus may lock the sentinel
#   target during the rename window; in that case, fall back to a direct write
#   and emit a warning so the caller can log the degraded-atomicity path.
#
#   W1.4 spec backlink: plan — atomic sentinel writes with locked-file fallback.
#
#   Returns 0 on success (including the fallback path). Returns 1 only if the
#   sessions directory cannot be determined (no git repo).
cs_write_sentinel() {
  local sid="${1:?session_id required}"
  local base
  base=$(_cs_sessions_dir) || return 1

  local sentinel="${base}/.current-session-id"
  local tmp="${base}/.current-session-id.${$}"

  # Ensure sessions dir exists
  mkdir -p "$base"

  # Write to tempfile first, then rename for atomicity
  if printf '%s\n' "$sid" > "$tmp" 2>/dev/null; then
    if mv -f "$tmp" "$sentinel" 2>/dev/null; then
      return 0
    else
      # mv failed — likely AV locking on Windows + Git Bash
      rm -f "$tmp" 2>/dev/null || true
      echo "[coordinator-session] WARN: sentinel rename failed (target may be AV-locked); used direct write — partial-read race possible" >&2
      printf '%s\n' "$sid" > "$sentinel" 2>/dev/null || return 0
    fi
  else
    # tempfile write failed — fall back to direct write
    echo "[coordinator-session] WARN: sentinel rename failed (target may be AV-locked); used direct write — partial-read race possible" >&2
    printf '%s\n' "$sid" > "$sentinel" 2>/dev/null || return 0
  fi

  return 0
}

# cs_touch <session_id> <path>
#   Append a repo-relative file path to this session's touched.txt.
#   Deduplication: only appends if the path is not already present.
#   Normalizes absolute paths to repo-relative.
#   Hot path — no jq dependency, no subshells beyond the git root lookup.
#   Returns 0 always (fail-open: touch tracking is best-effort).
cs_touch() {
  local sid="${1:?session_id required}"
  local fpath="${2:?file_path required}"
  local sdir

  sdir=$(_cs_session_dir "$sid") || return 0

  # Normalize to repo-relative path.
  # On Windows/Git Bash the git root is a Windows-style path (C:/...) but
  # incoming paths from hooks may use /mnt/... or /tmp/... POSIX forms.
  # Strategy: if the path is absolute, ask git to resolve it to repo-relative.
  # git ls-files --full-name handles tracked files. For untracked paths we fall
  # back to python3/python realpath if available, then to a best-effort prefix strip.
  if [[ "$fpath" == /* || "$fpath" == [A-Za-z]:* ]]; then
    local rel
    # Try git's own normalization first (works for tracked + staged files)
    rel=$(git ls-files --full-name -- "$fpath" 2>/dev/null | head -1)
    if [[ -z "$rel" ]]; then
      # Untracked file — use Python for a cross-platform relpath
      local root
      root=$(_cs_git_root)
      if [[ -n "$root" ]]; then
        rel=$(python3 -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]).replace(os.sep,'/'))" \
              "$fpath" "$root" 2>/dev/null) \
          || rel=$(python -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]).replace(os.sep,'/'))" \
              "$fpath" "$root" 2>/dev/null) \
          || rel=""
      fi
    fi
    # Fall back to as-is if normalization failed
    [[ -n "$rel" ]] && fpath="$rel"
  fi

  local touched="${sdir}/touched.txt"

  # Create session dir on first touch if cs_init was skipped (fail-safe)
  if [[ ! -d "$sdir" ]]; then
    cs_init "$sid" 2>/dev/null || true
  fi

  # Dedup: only append if not already in file
  # grep -qxF is O(n) but touched.txt is typically small (< 100 paths).
  if [[ -f "$touched" ]] && grep -qxF "$fpath" "$touched" 2>/dev/null; then
    return 0
  fi

  echo "$fpath" >> "$touched"

  # Update last_activity in meta.json (best-effort, no failure on error)
  local now
  now=$(_cs_now_iso)
  _cs_update_meta_field "$sdir" "last_activity" "$now" 2>/dev/null || true

  return 0
}

# cs_compute_scope <session_id>
#   Compute the scoped staging set for this session:
#     MY_SCOPE = (touched.txt ∪ mtime_dirty_since_started_at) − ⋃(other_sessions.touched.txt)
#
#   Prints one repo-relative path per line to stdout.
#   Also prints to stderr:
#     "skipping <path> — owned by session <other_id>" for each cross-session subtraction
#     "orphan: <path>" for dirty files claimed by no session
#
#   Returns 0 always.
cs_compute_scope() {
  local sid="${1:?session_id required}"
  local sdir base

  sdir=$(_cs_session_dir "$sid") || return 0
  base=$(_cs_sessions_dir) || return 0

  # --- Step 1: Build my candidate set (touched.txt) ---
  local touched_set=()
  if [[ -f "${sdir}/touched.txt" ]]; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && touched_set+=("$line")
    done < "${sdir}/touched.txt"
  fi

  # --- Step 2: mtime fallback — add dirty files modified after started_at ---
  local started_at_iso started_at_epoch
  started_at_iso=$(cat "${sdir}/started_at" 2>/dev/null || echo "")
  started_at_epoch=$(_cs_iso_to_epoch "$started_at_iso")

  # Get all dirty files (modified tracked + untracked, with explicit individual paths).
  # git status --porcelain collapses untracked directories to dir/ which loses
  # individual filenames. Use two commands:
  #   1. git diff --name-only HEAD  — tracked files modified vs HEAD (staged or unstaged)
  #   2. git ls-files --others --exclude-standard  — untracked files, one per line
  local dirty_files=()
  while IFS= read -r dfile; do
    [[ -n "$dfile" ]] && dirty_files+=("$dfile")
  done < <(
    { git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } \
      | sort -u
  )

  # Add dirty files whose mtime is after started_at
  local root
  root=$(_cs_git_root)
  for dfile in "${dirty_files[@]:-}"; do
    [[ -z "$dfile" ]] && continue
    local abs_path="${root}/${dfile}"
    local file_mtime
    file_mtime=$(_cs_mtime_epoch "$abs_path")
    if [[ "$file_mtime" -ge "$started_at_epoch" ]]; then
      # Only add if not already in touched_set
      local already=false
      for t in "${touched_set[@]:-}"; do
        [[ "$t" == "$dfile" ]] && { already=true; break; }
      done
      [[ "$already" == false ]] && touched_set+=("$dfile")
    fi
  done

  # --- Step 3: Build other sessions' claim sets ---
  declare -A other_claims  # path -> session_id
  if [[ -d "$base" ]]; then
    for other_sdir in "${base}"/*/; do
      [[ -d "$other_sdir" ]] || continue
      local other_id
      other_id=$(basename "$other_sdir")
      [[ "$other_id" == "$sid" ]] && continue
      [[ "$other_id" == ".archive" ]] && continue

      if [[ -f "${other_sdir}/touched.txt" ]]; then
        while IFS= read -r opath; do
          [[ -n "$opath" ]] && other_claims["$opath"]="$other_id"
        done < "${other_sdir}/touched.txt"
      fi
    done
  fi

  # --- Step 4: Apply subtraction and emit MY_SCOPE ---
  # W3 (Patrik R1 finding #1): distinguish "another session owns this" from
  # "stale self-claim" when CLAUDE_SESSION_ID is set but resolution diverged.
  # Append "(your session=<resolved>)" for disambiguation in the normal case.
  local my_scope=()
  local env_sid="${CLAUDE_SESSION_ID:-}"
  local excluded_count=0
  for candidate in "${touched_set[@]:-}"; do
    [[ -z "$candidate" ]] && continue
    if [[ -v "other_claims[$candidate]" ]]; then
      local claim_sid="${other_claims[$candidate]}"
      if [[ -n "$env_sid" && "$claim_sid" == "$env_sid" ]]; then
        echo "skipping ${candidate} — stale self-claim from this session (resolved=${sid}, env=${env_sid}) — investigate session ID resolution" >&2
      else
        echo "skipping ${candidate} — owned by session ${claim_sid} (your session=${sid})" >&2
      fi
      (( excluded_count++ )) || true
    else
      my_scope+=("$candidate")
    fi
  done

  # W3 epilogue: when ≥1 file was excluded, point the user at the right diagnostic.
  if (( excluded_count > 0 )); then
    echo "  hint: if your files are being skipped as 'owned by another session' but you wrote them, your session ID resolution is wrong (see ~/.claude/docs/wiki/scoped-safety-commits.md troubleshooting)" >&2
  fi

  # --- Step 5: Orphan detection ---
  for dfile in "${dirty_files[@]:-}"; do
    [[ -z "$dfile" ]] && continue
    # Orphan: dirty, not in my scope, not claimed by any other session
    local in_mine=false
    for m in "${my_scope[@]:-}"; do
      [[ "$m" == "$dfile" ]] && { in_mine=true; break; }
    done
    [[ "$in_mine" == true ]] && continue

    if [[ -v "other_claims[$dfile]" ]]; then
      : # owned by another session — not an orphan, skip silently
    else
      # Dirty, not claimed — orphan
      echo "orphan: ${dfile}" >&2
    fi
  done

  # --- Output: one path per line ---
  for path in "${my_scope[@]:-}"; do
    echo "$path"
  done

  return 0
}

# cs_archive <session_id>
#   Move session directory to .git/coordinator-sessions/.archive/<id>-<YYYY-MM-DD>/
#   Should be called AFTER the final commit completes (per plan: archive-after-commit).
#   Idempotent: if already archived, returns 0.
#   Returns 0 on success, 1 on failure.
cs_archive() {
  local sid="${1:?session_id required}"
  local base sdir archive_dir today

  base=$(_cs_sessions_dir) || return 1
  sdir="${base}/${sid}"

  if [[ ! -d "$sdir" ]]; then
    return 0  # already archived or never existed — idempotent
  fi

  today=$(date +%Y-%m-%d 2>/dev/null || echo "unknown")
  archive_dir="${base}/.archive/${sid}-${today}"

  mkdir -p "${base}/.archive"
  mv "$sdir" "$archive_dir" 2>/dev/null || return 1
  return 0
}

# cs_reap_stale
#   Archive sessions meeting the reaper criterion:
#     inactive_for > 24h AND no alive PID in meta.json AND
#     no commits referencing this scope in last 24h
#   The third condition (git log check) is skipped if too expensive — the first
#   two conditions are the primary guard.
#   Prints "reaped <session_id>" to stdout for each archived session.
cs_reap_stale() {
  local base
  base=$(_cs_sessions_dir) || return 0
  [[ -d "$base" ]] || return 0

  local now_epoch
  now_epoch=$(_cs_now_epoch)
  local threshold_seconds=$(( 24 * 3600 ))

  for sdir in "${base}"/*/; do
    [[ -d "$sdir" ]] || continue
    local sid
    sid=$(basename "$sdir")
    [[ "$sid" == ".archive" ]] && continue

    # Condition 1: inactive_for > 24h
    local last_activity_iso last_activity_epoch
    last_activity_iso=$(_cs_read_meta_field "$sdir" "last_activity")
    last_activity_epoch=$(_cs_iso_to_epoch "$last_activity_iso")
    local inactive_for=$(( now_epoch - last_activity_epoch ))
    if [[ "$inactive_for" -le "$threshold_seconds" ]]; then
      continue  # still active
    fi

    # Condition 2: no alive PID
    local pid
    pid=$(_cs_read_meta_field "$sdir" "pid")
    if _cs_pid_alive "$pid"; then
      continue  # process still running
    fi

    # All conditions met — archive it
    if cs_archive "$sid"; then
      echo "reaped ${sid}"
    fi
  done
}

# cs_active_sessions
#   List all active (non-archived) sessions with liveness classification.
#   Output format (one line per session):
#     <session_id>  Live (last activity Nm ago)
#     <session_id>  Stale (last activity Nh ago, candidate for reap)
#
#   Thresholds:
#     Live: PID alive AND last_activity < 30 minutes ago
#     Stale: no alive PID OR last_activity >= 30 minutes ago (but < 24h = reap threshold)
cs_active_sessions() {
  local base
  base=$(_cs_sessions_dir) || return 0
  [[ -d "$base" ]] || { echo "(no coordinator-sessions dir yet)"; return 0; }

  local found=false
  local now_epoch
  now_epoch=$(_cs_now_epoch)

  for sdir in "${base}"/*/; do
    [[ -d "$sdir" ]] || continue
    local sid
    sid=$(basename "$sdir")
    [[ "$sid" == ".archive" ]] && continue
    found=true

    local pid last_activity_iso last_activity_epoch elapsed_sec elapsed_label

    pid=$(_cs_read_meta_field "$sdir" "pid")
    last_activity_iso=$(_cs_read_meta_field "$sdir" "last_activity")
    last_activity_epoch=$(_cs_iso_to_epoch "$last_activity_iso")
    elapsed_sec=$(( now_epoch - last_activity_epoch ))

    # Human-readable elapsed time
    if [[ "$elapsed_sec" -lt 60 ]]; then
      elapsed_label="${elapsed_sec}s ago"
    elif [[ "$elapsed_sec" -lt 3600 ]]; then
      elapsed_label="$(( elapsed_sec / 60 ))m ago"
    elif [[ "$elapsed_sec" -lt 86400 ]]; then
      elapsed_label="$(( elapsed_sec / 3600 ))h ago"
    else
      elapsed_label="$(( elapsed_sec / 86400 ))d ago"
    fi

    # Liveness: Live requires alive PID AND < 30 min since last activity
    local thirty_min=$(( 30 * 60 ))
    if _cs_pid_alive "$pid" && [[ "$elapsed_sec" -lt "$thirty_min" ]]; then
      printf "%-60s  Live (last activity %s)\n" "$sid" "$elapsed_label"
    else
      printf "%-60s  Stale (last activity %s, candidate for reap)\n" "$sid" "$elapsed_label"
    fi
  done

  if [[ "$found" == false ]]; then
    echo "(no active sessions)"
  fi
}
