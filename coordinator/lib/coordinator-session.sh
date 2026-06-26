#!/usr/bin/env bash
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
#       └── <session-id>-<YYYY-MM-DD>/   archived after workstream-complete or handoff
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
#   NOTE: NOT a session-liveness signal in-harness — every Bash/hook tool call has
#   a fresh, short-lived $$ (see _cs_is_session_live header). Retained only for the
#   legacy pid-only claim-dir fallback and diagnostics; never gate session liveness
#   on this.
_cs_pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

# _cs_resolve_session_id
#   Resolve THIS session's id via the canonical 4-tier chain, mirroring the
#   in-line resolution in cs_claim_artifact and coordinator-safe-commit's
#   resolve_session_id:
#     1. $COORDINATOR_SESSION_ID  (explicit test override)
#     2. $CLAUDE_SESSION_ID       (explicit override slot)
#     3. $CLAUDE_CODE_SESSION_ID  (platform-injected, Claude Code ≥ ~2.1.150)
#     4. .git/coordinator-sessions/.current-session-id sentinel (old Claude Code)
#   The sentinel is anchored to the running (cwd) session — never a baton repo.
#   Always returns 0; prints the empty string when no session id is resolvable
#   (callers gate on empty, including the _cs_git_root-failure path).
_cs_resolve_session_id() {
  local sid="${COORDINATOR_SESSION_ID:-}"
  [[ -z "$sid" ]] && sid="${CLAUDE_SESSION_ID:-}"
  [[ -z "$sid" ]] && sid="${CLAUDE_CODE_SESSION_ID:-}"
  if [[ -z "$sid" ]]; then
    local root sentinel
    root=$(_cs_git_root) || { echo ""; return 0; }
    sentinel="${root}/.git/coordinator-sessions/.current-session-id"
    [[ -f "$sentinel" ]] && sid=$(cat "$sentinel" 2>/dev/null)
  fi
  echo "$sid"
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
    || epoch=0
  if [[ "$epoch" == 0 ]]; then
    # Resolve via shared lib so Windows uses pythonw.exe (no console flash).
    local _lib="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
    [[ ! -f "$_lib" ]] && _lib="${HOME}/.claude/plugins/coordinator/lib/resolve-python.sh"
    # shellcheck source=/dev/null
    [[ -f "$_lib" ]] && source "$_lib"
    if [[ -n "$PYTHON_BIN" ]]; then
      epoch=$(CS_ISO_TS="${iso%Z}" "$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "import os,datetime; print(int(datetime.datetime.fromisoformat(os.environ['CS_ISO_TS']).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null) \
        || epoch=0
    fi
  fi
  echo "$epoch"
}

# _cs_read_meta_field <session_dir> <field>: extract a JSON field from meta.json
# Uses jq if available, otherwise sed fallback.
_cs_read_meta_field() {
  local sdir="${1:?}" field="${2:?}"
  local meta="${sdir}/meta.json"
  [[ -f "$meta" ]] || { echo ""; return; }
  if command -v jq &>/dev/null; then
    jq -r ".${field} // empty" "$meta" 2>/dev/null || true
  else
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
    # Atomic rewrite: jq -> tempfile next to target -> mv. The prior
    # `tmp=$(jq ...) && echo "$tmp" > "$meta"` pattern is non-atomic — a
    # concurrent reader could see a truncated meta.json mid-write, and two
    # writers race on the redirect. mktemp+mv mirrors the sed-fallback path.
    local _tmp
    _tmp=$(mktemp "${meta}.XXXXXX" 2>/dev/null) || _tmp=$(mktemp) || return 1
    if jq --arg v "$value" ".${field} = \$v" "$meta" > "$_tmp" 2>/dev/null; then
      mv "$_tmp" "$meta" 2>/dev/null || { rm -f "$_tmp"; return 1; }
    else
      rm -f "$_tmp"
      return 1
    fi
  else
    # sed tempfile fallback — portable across BSD/macOS and GNU sed.
    # Escape value for sed RHS: `\`, `&`, `/` must be backslash-escaped or
    # they corrupt the replacement (e.g. branch name containing `/`).
    local _sed_escaped
    _sed_escaped=$(printf '%s' "$value" | sed 's/[&/\\]/\\&/g')
    local _tmp
    _tmp=$(mktemp) && \
      sed "s/\"${field}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"/\"${field}\": \"${_sed_escaped}\"/" "$meta" > "$_tmp" 2>/dev/null && \
      mv "$_tmp" "$meta" || { rm -f "$_tmp"; true; }
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
    if command -v jq >/dev/null 2>&1; then
      jq -n \
        --arg sid "$sid" \
        --arg branch "$branch" \
        --arg pid "$pid" \
        --arg now "$now" \
        --arg goal "$goal" \
        '{session_id: $sid, branch: $branch, pid: $pid, last_activity: $now, goal: $goal}' \
        > "${sdir}/meta.json"
    else
      # Escape every interpolated field — `\` -> `\\`, `"` -> `\"`. Previously
      # only `goal` was escaped; a branch name containing `"` or `\` would
      # corrupt meta.json. Inline helper kept simple to avoid sourcing order.
      _cs_json_escape() {
        local _v="${1//\\/\\\\}"
        _v="${_v//\"/\\\"}"
        printf '%s' "$_v"
      }
      local sid_escaped branch_escaped pid_escaped now_escaped goal_escaped
      sid_escaped=$(_cs_json_escape "$sid")
      branch_escaped=$(_cs_json_escape "$branch")
      pid_escaped=$(_cs_json_escape "$pid")
      now_escaped=$(_cs_json_escape "$now")
      goal_escaped=$(_cs_json_escape "$goal")
      cat > "${sdir}/meta.json" <<METAJSON
{
  "session_id": "${sid_escaped}",
  "branch": "${branch_escaped}",
  "pid": "${pid_escaped}",
  "last_activity": "${now_escaped}",
  "goal": "${goal_escaped}"
}
METAJSON
    fi
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
        # Resolve via shared lib so Windows uses pythonw.exe (no console flash).
        local _lib="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
        [[ ! -f "$_lib" ]] && _lib="${HOME}/.claude/plugins/coordinator/lib/resolve-python.sh"
        # shellcheck source=/dev/null
        [[ -f "$_lib" ]] && source "$_lib"
        if [[ -n "$PYTHON_BIN" ]]; then
          rel=$("$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]).replace(os.sep,'/'))" \
                "$fpath" "$root" 2>/dev/null) || rel=""
        else
          rel=""
        fi
      fi
    fi
    # Fall back to as-is if normalization failed
    [[ -n "$rel" ]] && fpath="$rel"
  fi

  # Guard: if normalization returned empty (e.g. Python unavailable, path outside
  # repo) and the original fpath was absolute, fpath stays absolute — an absolute
  # path in touched.txt corrupts the relative-path scope set.  Fail-open: skip.
  [[ -z "$fpath" ]] && return 0

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
  if (( ${#dirty_files[@]} > 0 )); then
    for dfile in "${dirty_files[@]}"; do
      [[ -z "$dfile" ]] && continue
      local abs_path="${root}/${dfile}"
      local file_mtime
      file_mtime=$(_cs_mtime_epoch "$abs_path")
      if [[ "$file_mtime" -ge "$started_at_epoch" ]]; then
        # Only add if not already in touched_set
        local already=false
        if (( ${#touched_set[@]} > 0 )); then
          for t in "${touched_set[@]}"; do
            [[ "$t" == "$dfile" ]] && { already=true; break; }
          done
        fi
        [[ "$already" == false ]] && touched_set+=("$dfile")
      fi
    done
  fi

  # --- Step 3: Build other sessions' claim sets ---
  # Bash 3.2-safe: two parallel arrays (keys + values) replace associative array.
  # Lookup is O(n) linear scan over other_claim_paths; touched.txt is small (<100).
  local other_claim_paths=()   # parallel array: path claimed by another session
  local other_claim_sids=()    # parallel array: which session owns that path
  if [[ -d "$base" ]]; then
    for other_sdir in "${base}"/*/; do
      [[ -d "$other_sdir" ]] || continue
      local other_id
      other_id=$(basename "$other_sdir")
      [[ "$other_id" == "$sid" ]] && continue
      [[ "$other_id" == ".archive" ]] && continue
      [[ "$other_id" == ".agents" ]] && continue

      if [[ -f "${other_sdir}/touched.txt" ]]; then
        while IFS= read -r opath; do
          if [[ -n "$opath" ]]; then
            other_claim_paths+=("$opath")
            other_claim_sids+=("$other_id")
          fi
        done < "${other_sdir}/touched.txt"
      fi
    done
  fi

  # Helper: _cs_other_claim_owner <path> → prints owner sid or empty string
  _cs_other_claim_owner() {
    local needle="$1" i
    for (( i=0; i<${#other_claim_paths[@]}; i++ )); do
      if [[ "${other_claim_paths[$i]}" == "$needle" ]]; then
        echo "${other_claim_sids[$i]}"
        return
      fi
    done
  }

  # --- Step 4: Apply subtraction and emit MY_SCOPE ---
  local my_scope=()
  if (( ${#touched_set[@]} > 0 )); then
    for candidate in "${touched_set[@]}"; do
      [[ -z "$candidate" ]] && continue
      local owner
      owner=$(_cs_other_claim_owner "$candidate")
      if [[ -n "$owner" ]]; then
        echo "skipping ${candidate} — owned by session ${owner}" >&2
      else
        my_scope+=("$candidate")
      fi
    done
  fi

  # --- Step 5: Orphan detection ---
  if (( ${#dirty_files[@]} > 0 )); then
    for dfile in "${dirty_files[@]}"; do
      [[ -z "$dfile" ]] && continue
      # Orphan: dirty, not in my scope, not claimed by any other session
      local in_mine=false
      if (( ${#my_scope[@]} > 0 )); then
        for m in "${my_scope[@]}"; do
          [[ "$m" == "$dfile" ]] && { in_mine=true; break; }
        done
      fi
      [[ "$in_mine" == true ]] && continue

      local dfile_owner
      dfile_owner=$(_cs_other_claim_owner "$dfile")
      if [[ -n "$dfile_owner" ]]; then
        : # owned by another session — not an orphan, skip silently
      else
        # Dirty, not claimed — orphan
        echo "orphan: ${dfile}" >&2
      fi
    done
  fi

  # --- Output: one path per line ---
  if (( ${#my_scope[@]} > 0 )); then
    for path in "${my_scope[@]}"; do
      echo "$path"
    done
  fi

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
#   The third condition (git log check) is not implemented — the first two
#   conditions are sufficient in practice; a git log scan would add O(n) commit
#   graph traversal per session.
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
    [[ "$sid" == ".agents" ]] && continue

    # Condition 1: inactive_for > 24h
    local last_activity_iso last_activity_epoch
    last_activity_iso=$(_cs_read_meta_field "$sdir" "last_activity")
    last_activity_epoch=$(_cs_iso_to_epoch "$last_activity_iso")
    # epoch=0 means timestamp was empty/unparseable; treat as unknown, not stale.
    if [[ "$last_activity_epoch" -eq 0 ]]; then
      continue  # unknown timestamp — skip reap
    fi
    local inactive_for=$(( now_epoch - last_activity_epoch ))
    # Clamp against clock skew (NTP jump, VM resume, DST) — mirrors cs_active_sessions;
    # a negative inactive_for must read as "just active", never wrap to a large value.
    (( inactive_for < 0 )) && inactive_for=0
    if [[ "$inactive_for" -le "$threshold_seconds" ]]; then
      continue  # still active
    fi

    # Condition 2: no alive PID.
    # In-harness this is ALWAYS true (meta.json pid is a dead hook $$), so the 24h
    # inactivity gate above is the real reaper trigger — this check only adds protection
    # in the rare non-harness case where a long-lived outer shell calls cs_init directly
    # and keeps that PID. NOT the session-liveness key (that is last_activity recency,
    # _cs_is_session_live); kept here as a conservative belt-and-braces over the 24h gate.
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

# cs_reap_stale_claims [baton_repo_root] [class]
#   Reap orphaned artifact claims left by cs_claim_artifact (handoff + memo classes).
#   Because the claim dir is basename-only (<base>/<class>-claims/<basename>/, NOT under
#   <sid>/), cs_archive's session-dir move no longer carries it away — this is its release path.
#
#   Class coverage: a NO-ARG call sweeps BOTH handoff-claims AND memo-claims (so the existing
#   no-arg session-init call site reaps memo claims with zero edits). An optional <class>
#   second arg narrows to one subdir (handoff | memo).
#
#   Liveness rule: reap iff the holding SESSION is not live by the canonical recency
#   rule (_cs_session_live: last_activity < 30 min). NO separate age check — a live
#   holder is NEVER reaped regardless of how long it has held the claim (a /pickup can
#   hold a workstream open across a workday, AS LONG AS the session keeps touching tools
#   so its heartbeat stays fresh). This matches cs_claim_artifact's inline takeover; the
#   two paths share _cs_session_live so they MUST agree on what "stale" means. The held
#   PID is NOT the key — it is a dead per-Bash-call $$ in-harness (see _cs_is_session_live
#   header); a pid-only LEGACY claim dir (pre-upgrade, no session_id file) falls back to
#   the old dead-PID test for that dir only.
#
#   TOCTOU: re-read the held session_id (or pid, legacy) immediately before rm -rf and
#   skip if it changed or is now live — closes the rm-vs-inline-takeover race (reaper
#   reads stale holder, a concurrent pickup takes over writing a live sid, reaper would
#   otherwise delete the live claim). Best-effort; never fatal to caller (session-init
#   wraps it || true).
#
#   <baton_repo_root> (optional): reap a foreign baton repo's claims; defaults to cwd.
#   FOREIGN-BATON NON-COVERAGE (memo parity with cs_claim_artifact's note): a memo claim
#   written under a foreign BATON_REPO is NOT reached by session-init's no-arg reaper
#   (which fires on the cwd repo via _cs_sessions_dir). For cross-repo memo pickup — the
#   primary use case — such claims are cleaned up by inline dead-PID takeover on the next
#   pickup of the same baton, or by an explicit cs_reap_stale_claims <baton-root> call.
#
#   Spec backlink: docs/plans/2026-06-17-concurrent-pickup-guard-sid-regression.md § C2;
#                  docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C1
cs_reap_stale_claims() {
  # Review: code-reviewer — silent return (not fail-loud) is intentional: the reaper is
  # best-effort; contrast with cs_claim_artifact which fails loud on a bad baton root.
  local baton_repo_root="${1:-}"
  local class_filter="${2:-}"
  local base
  if [[ -n "$baton_repo_root" ]]; then
    [[ -d "${baton_repo_root}/.git" ]] || return 0
    base="${baton_repo_root}/.git/coordinator-sessions"
  else
    base=$(_cs_sessions_dir) || return 0
  fi

  # No-arg sweeps both classes; a class filter narrows to one subdir.
  local subdirs
  if [[ -n "$class_filter" ]]; then
    subdirs="${class_filter}-claims"
  else
    subdirs="handoff-claims memo-claims"
  fi

  local sub claims_dir claim
  for sub in $subdirs; do
    claims_dir="${base}/${sub}"
    [[ -d "$claims_dir" ]] || continue
    for claim in "${claims_dir}"/*/; do
      [[ -d "$claim" ]] || continue
      # Reapable iff the holding SESSION is not live — the SAME key (_cs_claim_holder_live)
      # as cs_claim_artifact's takeover and cs_sweep_actioned_memos, so all agree on "stale"
      # (this function's contract demands that agreement). The helper carries the canonical
      # session_id-recency key + the legacy pid-only fallback.
      _cs_claim_holder_live "$claim" && continue       # holder live — skip
      # TOCTOU re-read: if a concurrent pickup took over between the two reads (rm + mkdir +
      # a live session_id), the second read sees the NEW holder and returns live, so we skip
      # — the claim is now protected by its new live holder. (The guard is liveness-of-current-
      # holder, not identity-change detection: a takeover to another stale holder still reaps,
      # which is correct.)
      _cs_claim_holder_live "$claim" && continue
      # Review: code-reviewer — && is intentional: echo fires only on successful rm;
      # a failed rm (lost the race to another reaper) is silently skipped, not fatal.
      # Review: code-reviewer — rm -rf on an already-absent dir is idempotent (returns 0
      # on BSD/macOS), so a concurrent double-reaper run is safe: the second reaper gets
      # a harmless extra "reaped claim" echo at worst. Mirrors the cs_reap_stale mv/ENOENT
      # idempotency note.
      rm -rf "$claim" 2>/dev/null && echo "reaped claim $(basename "${claim%/}")"
    done
  done
}

# _cs_is_session_live <pid> <elapsed_sec>
#   Returns 0 (true) when the session should be considered Live, 1 otherwise.
#
#   LIVENESS KEY: last_activity recency ONLY — elapsed_sec < 30 minutes.
#   The <pid> argument is retained for signature stability and diagnostic
#   display but is DELIBERATELY NOT part of the liveness decision.
#
#   Why pid is not the key (in-harness reality): every Claude Code Bash/hook tool
#   call runs in a separate OS process with a fresh $$. cs_init writes meta.json's
#   `pid` as $$ of the hook subshell, which is dead within seconds of session open
#   (session-init.sh § "session_alive=true via PID is structurally unreachable";
#   session-heartbeat.sh). A kill -0 liveness gate therefore reports EVERY session
#   dead, including the one actively running right now. The signal that actually
#   tracks a live session is last_activity, refreshed on every PreToolUse:Bash by
#   session-heartbeat.sh (60s throttle). This is the same recency rule the
#   session-init.sh orphan sweep already trusts (its ALIVE_WINDOW is 10m; the
#   30m here is the documented session-liveness threshold surfaced by
#   cs_active_sessions and consumed by the claim layer).
#
#   BOUNDED EDGE (the Staff Engineer F0, closed 2026-06-23): the heartbeat was originally
#   PreToolUse:Bash ONLY, so last_activity was stamped at the START of a Bash call and
#   frozen for its duration. A genuinely-live session inside a SINGLE Bash command longer
#   than 30 min (a UE build, a large extraction) crossed this threshold mid-command, making
#   its claim wrongly takeable/reapable. CLOSED by registering session-heartbeat.sh on
#   PostToolUse:Bash as well (hooks.json): recency is now stamped at BOTH ends of every Bash
#   command, so only a session idle >30 min BETWEEN commands ages out. Residual (accepted):
#   a single command that runs >30 min AND emits no intervening tool calls is bounded by the
#   command's own duration — at completion the PostToolUse leg re-stamps and the claim is
#   live again; the wrongful-takeover window is at most the tail of one long command (or the
#   full 30-min window if the command is KILLED before its PostToolUse leg fires — SIGKILL/OOM
#   leaves last_activity at the PreToolUse stamp, indistinguishable from a truly-dead session),
#   not unbounded idle. Spec: state/handoffs/2026-06-23_233740_claim-liveness-hardening-r2.md.
#
#   Single-source-of-truth: cs_active_sessions, cs_live_session_ids (fast-path and
#   fallback), _cs_session_live (claim takeover / release / reaper), and any future
#   callers route through this helper to stay in sync. Do NOT reintroduce a
#   _cs_pid_alive gate here — it silently zeroes the live set in-harness, which
#   removed the concurrent-pickup guard entirely (the 2026-06-23 wrongful-takeover
#   regression this fix addresses). Spec: state/handoffs/2026-06-23_153742_claim-lock-pid-death-false-positive.md.
_cs_is_session_live() {
  local pid="${1:-}" elapsed_sec="${2:-0}"  # pid: diagnostic only — see header
  local thirty_min=$(( 30 * 60 ))
  [[ "$elapsed_sec" =~ ^[0-9]+$ ]] || return 1
  [[ "$elapsed_sec" -lt "$thirty_min" ]]
}

# _cs_session_live <session_id>
#   exit 0 iff <session_id> is a LIVE session by the canonical recency rule
#   (_cs_is_session_live). O(1) single-session lookup: reads that one session's
#   meta.json directly, rather than scanning every dir (that is cs_live_session_ids'
#   job). This is THE shared key for the claim layer — claim takeover, release
#   holder-check, and the reaper all call through here so they provably agree on
#   what "stale" means (cs_reap_stale_claims' own comment mandates that agreement).
#   Empty/unknown sid, missing session dir, or missing/unparseable last_activity
#   → not live.
_cs_session_live() {
  local sid="${1:-}"
  [[ -n "$sid" ]] || return 1
  local sdir
  sdir=$(_cs_session_dir "$sid" 2>/dev/null) || return 1
  [[ -d "$sdir" ]] || return 1
  local pid last_iso last_epoch now_epoch elapsed
  pid=$(_cs_read_meta_field "$sdir" "pid")
  last_iso=$(_cs_read_meta_field "$sdir" "last_activity")
  last_epoch=$(_cs_iso_to_epoch "$last_iso")
  now_epoch=$(_cs_now_epoch)
  elapsed=$(( now_epoch - last_epoch ))
  (( elapsed < 0 )) && elapsed=0
  _cs_is_session_live "$pid" "$elapsed"
}

# _cs_claim_holder_live <claim_dir>
#   exit 0 iff the session HOLDING this claim is live. THE single liveness decision for
#   the claim layer's stale/takeable/reapable question — shared by cs_claim_artifact
#   (takeover), cs_reap_stale_claims, and cs_sweep_actioned_memos so all provably agree.
#   Canonical key: held session_id recency (_cs_session_live). LEGACY fallback: a pid-only
#   claim dir (pre-upgrade, no session_id file) uses the dead-PID test for that dir only.
#   Consolidates the previously hand-copied `[[ -f session_id ]]` discriminator (one rule,
#   one site — the drift surface that previously let cs_sweep_actioned_memos keep the old
#   pid key, code-reviewer F2 / the Staff Engineer F3, 2026-06-23).
_cs_claim_holder_live() {
  local cdir="${1:?claim_dir required}"
  if [[ -f "${cdir}/session_id" ]]; then
    # `|| echo ""`: defensive TOCTOU — the file can be rm'd between the -f test and the cat
    # (a concurrent takeover/reaper); empty sid → _cs_session_live returns not-live (safe).
    _cs_session_live "$(cat "${cdir}/session_id" 2>/dev/null || echo "")"
  else
    _cs_pid_alive "$(cat "${cdir}/pid" 2>/dev/null || echo "")"
  fi
}

# _cs_claim_held_by_me <claim_dir> [my_sid]
#   exit 0 iff THIS session is the holder of this claim — the identity predicate for
#   cs_release_artifact (distinct from _cs_claim_holder_live's liveness predicate). Keyed
#   on session_id == my resolved id, NOT $$ (the recorded pid is a dead per-Bash $$
#   in-harness — lesson a167aa66).
#   <my_sid> (optional): the caller's PRE-RESOLVED session id. Pass it so a two-call TOCTOU
#   sequence keys both reads off ONE identity — the second read then varies only on the
#   claim-dir CONTENT (the actual race), never on a re-resolution of my own id. If omitted,
#   resolves via _cs_resolve_session_id. Re-reads the dir on each call, so calling it twice
#   IS the release TOCTOU re-read.
#   LEGACY pid-only fallback (no session_id file): compares the recorded pid to $$. This is a
#   PERMANENT no-op in-harness (every Bash call has a fresh $$), so a pre-upgrade pid-only
#   claim is released only via inline takeover or cs_reap_stale_claims — never via
#   cs_release_artifact. Preserved as-is; pid-only dirs self-heal to session_id on first takeover.
_cs_claim_held_by_me() {
  local cdir="${1:?claim_dir required}"
  local my="${2:-}"
  [[ -z "$my" ]] && my=$(_cs_resolve_session_id)
  if [[ -f "${cdir}/session_id" ]]; then
    [[ -n "$my" && "$(cat "${cdir}/session_id" 2>/dev/null || echo "")" == "$my" ]]
  else
    [[ "$(cat "${cdir}/pid" 2>/dev/null || echo "")" == "$$" ]]
  fi
}

# cs_active_sessions
#   List all active (non-archived) sessions with liveness classification.
#   Output format (one line per session):
#     <session_id>  Live (last activity Nm ago)
#     <session_id>  Stale (last activity Nh ago, candidate for reap)
#
#   Thresholds (PID is NOT part of the liveness key — see _cs_is_session_live header):
#     Live:  last_activity < 30 minutes ago
#     Stale: last_activity >= 30 minutes ago
#   NOTE: "Stale" here (the 30-min liveness boundary) is NOT the reap threshold —
#   cs_reap_stale (session archival) requires 24h inactivity. A 30m–24h session shows
#   Stale but is not yet reapable.
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
    [[ "$sid" == ".agents" ]] && continue
    found=true

    local pid last_activity_iso last_activity_epoch elapsed_sec elapsed_label

    pid=$(_cs_read_meta_field "$sdir" "pid")
    last_activity_iso=$(_cs_read_meta_field "$sdir" "last_activity")
    last_activity_epoch=$(_cs_iso_to_epoch "$last_activity_iso")
    elapsed_sec=$(( now_epoch - last_activity_epoch ))
    # Clamp against clock skew (NTP jump, VM resume, DST): negative elapsed
    # would make every session appear Live with a misleading "-Xs ago" label.
    (( elapsed_sec < 0 )) && elapsed_sec=0

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

    # Liveness: Live iff last_activity < 30 min (PID is diagnostic-only — see _cs_is_session_live)
    if _cs_is_session_live "$pid" "$elapsed_sec"; then
      printf "%-60s  Live (last activity %s)\n" "$sid" "$elapsed_label"
    else
      printf "%-60s  Stale (last activity %s, reap threshold is 24h)\n" "$sid" "$elapsed_label"
    fi
  done

  if [[ "$found" == false ]]; then
    echo "(no active sessions)"
  fi
}

# cs_live_session_ids
#   Print one live session id per line — liveness keyed on last_activity recency
#   (<30 min) ONLY, via _cs_is_session_live; PID is diagnostic, not part of the key
#   (see _cs_is_session_live header for why kill -0 is structurally dead in-harness).
#   No formatting, no headers. Structured-data sibling of cs_active_sessions.
#   Consumed by coordinator-safe-commit's agent-id-union candidate-set build
#   (Issue A, archive/specs/2026-05-05-issue-a-agent-id-linkage.md).
#
# Liveness criterion delegated to _cs_is_session_live (defined above cs_active_sessions);
# both functions call through that helper — no duplication.
cs_live_session_ids() {
  local base
  base=$(_cs_sessions_dir) || return 0
  [[ -d "$base" ]] || return 0
  local now_epoch
  now_epoch=$(_cs_now_epoch)

  # Fast path: one Python invocation parses every meta.json + computes the
  # last_activity epoch in-process, replacing the per-dir
  #   _cs_read_meta_field × 2  (sed|head subprocesses) +
  #   _cs_iso_to_epoch         (date or python subprocess)
  # — 3 subprocess spawns per dir. On Windows that ran ~200ms/dir, so a 250-dir
  # accumulation took 29s. The Python startup is paid once (~200ms total);
  # bash then applies the elapsed filter and the (subprocess-free) kill -0
  # builtin in a tight loop. Falls back to the per-dir scan below when Python
  # is unavailable.
  local _lib_rp="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
  [[ ! -f "$_lib_rp" ]] && _lib_rp="${HOME}/.claude/plugins/coordinator/lib/resolve-python.sh"
  if [[ -f "$_lib_rp" ]]; then
    # shellcheck source=/dev/null
    source "$_lib_rp"
  fi
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    local tsv
    # `-` reads script from stdin; "$base" lands in sys.argv[1] (Git Bash
    # auto-translates the POSIX path to a Windows path for native .exe binaries
    # invoked via Git Bash — applies to python.exe and pythonw.exe, but the `py`
    # launcher receives the raw POSIX path (relevant on the py -3 PYTHON_ARGS path)).
    tsv=$("$PYTHON_BIN" "${PYTHON_ARGS[@]}" - "$base" <<'PYEOF' 2>/dev/null
import sys, os, glob, json, datetime
base = sys.argv[1]
for meta in glob.glob(os.path.join(base, '*', 'meta.json')):
    sid = os.path.basename(os.path.dirname(meta))
    if sid in ('.archive', '.agents'):
        continue
    try:
        with open(meta, encoding='utf-8') as f:
            d = json.load(f)
        pid = str(d.get('pid', '') or '')
        la = (d.get('last_activity', '') or '').rstrip('Z')
        try:
            ep = int(datetime.datetime.fromisoformat(la)
                       .replace(tzinfo=datetime.timezone.utc).timestamp())
        except Exception:
            ep = 0
        sys.stdout.write(f"{sid}\t{pid}\t{ep}\n")
    except Exception:
        pass
PYEOF
)
    if [[ -n "$tsv" ]]; then
      local sid pid last_epoch elapsed
      while IFS=$'\t' read -r sid pid last_epoch; do
        [[ -z "$sid" ]] && continue
        # Strip trailing CR — Python's text-mode stdout on Windows writes \r\n,
        # and bash `read` strips \n but not \r, leaving the last field with a
        # trailing carriage return that breaks the arithmetic below. ONLY the
        # last TSV field carries the CR (interior fields are split clean by
        # IFS=$'\t'). If a future column is appended after last_epoch, the strip
        # must be moved to the new last field — not left here on last_epoch.
        last_epoch="${last_epoch%$'\r'}"
        [[ -z "$last_epoch" || ! "$last_epoch" =~ ^[0-9]+$ ]] && last_epoch=0
        elapsed=$(( now_epoch - last_epoch ))
        if _cs_is_session_live "$pid" "$elapsed"; then
          echo "$sid"
        fi
      done <<< "$tsv"
    fi
    return 0
  fi

  # Fallback path (no Python): per-dir sed-based parse — preserves the original
  # behavior on hosts where resolve-python.sh finds no interpreter.
  for sdir in "${base}"/*/; do
    [[ -d "$sdir" ]] || continue
    local sid
    sid=$(basename "$sdir")
    [[ "$sid" == ".archive" ]] && continue
    [[ "$sid" == ".agents" ]] && continue

    local pid last_iso last_epoch elapsed
    pid=$(_cs_read_meta_field "$sdir" "pid")
    last_iso=$(_cs_read_meta_field "$sdir" "last_activity")
    last_epoch=$(_cs_iso_to_epoch "$last_iso")
    elapsed=$(( now_epoch - last_epoch ))

    # Cheap-check ordering: _cs_is_session_live checks elapsed first (pure bash
    # arithmetic), then kill -0 (bash builtin) — same per-dir cost as before for
    # the fallback, but skips kill on stale sessions for a small additional saving.
    if _cs_is_session_live "$pid" "$elapsed"; then
      echo "$sid"
    fi
  done
}

# cs_self_claim <path>
#   Record <path> in the current session's touched.txt (best-effort attribution
#   for tools that edit files outside the Edit/Write hook path — e.g. the
#   verify-*-sync.sh fixers and check-mcp-versions.sh).
#
#   Resolution prefers the platform-injected session id ($CLAUDE_SESSION_ID
#   override, then $CLAUDE_CODE_SESSION_ID — Claude Code ≥ ~2.1.150). That is
#   O(1) and unambiguous: no need to enumerate live sessions. Only when neither
#   env var is set (old Claude Code) does it fall back to cs_live_session_ids,
#   which is O(n) over every session dir — hundreds, with subprocess spawns each,
#   tens of seconds on Windows — and claims only when exactly one session is live.
#
#   Always returns 0 (fail-open): attribution is advisory, never blocks the caller.
#   Replaces the byte-identical _cs_claim_if_session that was copy-pasted across
#   8 sync scripts.
cs_self_claim() {
  local path="${1:?path required}"

  # Fast path: platform tells us our own session id directly.
  local sid="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-}}"
  if [[ -n "$sid" ]]; then
    local sdir
    sdir=$(_cs_session_dir "$sid" 2>/dev/null) || return 0
    [[ -d "$sdir" ]] || return 0  # session dir gone — nothing to claim against
    cs_atomic_dedup_append "${sdir}/touched.txt" "$path" 2>/dev/null || return 0
    return 0
  fi

  # Fallback (no session env var): enumerate live sessions; claim only when
  # exactly one is live (otherwise attribution is ambiguous — skip).
  local sids
  sids="$(cs_live_session_ids 2>/dev/null)" || return 0
  local count
  if [[ -z "$sids" ]]; then count=0
  else count=$(echo "$sids" | wc -l | tr -d ' \n'); fi
  if [[ "$count" -eq 0 ]]; then
    echo "coordinator-session: no active session found — skipping self-claim for $path" >&2
    return 0
  fi
  if [[ "$count" -gt 1 ]]; then
    echo "coordinator-session: ${count} live sessions (ambiguous) — skipping self-claim for $path" >&2
    return 0
  fi
  sid=$(echo "$sids" | head -1)
  local sdir
  sdir=$(_cs_session_dir "$sid" 2>/dev/null) || return 0
  cs_atomic_dedup_append "${sdir}/touched.txt" "$path" 2>/dev/null || return 0
}

# cs_atomic_dedup_append <touched-file> <new-entry>
#   Append new-entry to touched-file only if it is not already present.
#
# Spec backlink: plans/safe-commit-fixes.md § Phase 3a
#
# Fix for lost-update race (T21): the prior mktemp+sort+mv pattern let N
# concurrent writers each read-then-overwrite, so the last mv won and
# earlier merges were silently dropped (distinct-path writers lost).
#
# Replacement: append-only write.
#   1. Fast-exit if already present (cheap grep, non-atomic — a false negative
#      just falls through; the append is idempotent at consumption via sort -u).
#   2. printf '%s\n' >> touched-file   — single-line append < PIPE_BUF (4096).
#      On POSIX, single short writes to O_APPEND files are atomic.
#      On Windows NTFS (Git Bash), file-append writes are serialized by the FS
#      driver; concurrent appends interleave correctly and do not corrupt.
#
# Duplicates can still appear if two writers both pass the fast-exit before
# either appends (the window is tiny but non-zero). Dedup-on-read at
# consumption time is the correctness backstop: coordinator-safe-commit builds
# a dict from the array, which collapses duplicates automatically, AND the
# sort -u pass below guarantees the file stays clean after first read.
#
# Silent-failure contract: returns 0 on any error so the hook never blocks
# tool calls (advisory hook). No mktemp, no mv, no flock — nothing that can
# fail silently on cross-drive or Windows paths.
cs_atomic_dedup_append() {
  local touched="${1:?touched-file required}"
  local entry="${2:?new-entry required}"

  # Fast-exit: already present (non-atomic read is fine — false negative just
  # falls through to the append, where a duplicate may land; cleaned at next
  # consumption-time sort -u).
  if grep -qxF "$entry" "$touched" 2>/dev/null; then
    return 0
  fi

  # Append-only write — atomic for single short lines on POSIX + Windows NTFS.
  printf '%s\n' "$entry" >> "$touched" 2>/dev/null || return 0

  return 0
}

# cs_claim_artifact <class> <basename> [baton_repo_root]
#   Atomic mkdir-based claim primitive for concurrent /pickup race detection, shared by
#   both pickup artifact classes. <class> is `handoff` or `memo`; it selects the claims
#   subdir (<class>-claims) and the log-message prefix. cs_claim_handoff / cs_claim_memo
#   are thin wrappers below. Generalized 2026-06-21 (memo-pickup claim-lock parity); the
#   handoff call site behaves byte-for-byte as before (cs_claim_handoff handoff "$@").
#   Claim directory: <root>/.git/coordinator-sessions/<class>-claims/<basename>/
#
#   BASENAME-ONLY, NOT sid-namespaced: all sessions sharing a <root> contend for ONE
#   lock per artifact. That shared-path mkdir IS the same-machine concurrent-pickup
#   guard (DR-110). It was sid-namespaced until 2026-06-17, which silently defeated
#   the guard once Claude Code moved to per-session CLAUDE_CODE_SESSION_ID (two
#   same-machine sessions held distinct sids → distinct paths → never collided).
#
#   <baton_repo_root> (optional): the git repo that OWNS the baton being picked up.
#   When supplied, the claim directory lives under the baton repo's .git, so two
#   concurrent /pickup sessions of the SAME baton contest the same mkdir regardless
#   of each session's cwd (foreign-cwd pickup of a ~/.claude baton). When absent
#   (legacy one-arg call), the claim lives under the cwd repo — byte-for-byte the
#   prior behavior. A SUPPLIED-but-non-git root fails loud (detect-then-fail-loud,
#   never a silent cwd fallback). NOTE: only the lock LOCATION follows the baton —
#   session-id resolution (incl. the sentinel read below) stays anchored to the
#   running (cwd) session, because .current-session-id is written into the cwd
#   session's .git by session-init.sh, never into the baton repo.
#
#   On EEXIST (the holder is ALWAYS a different session — this session just attempted
#   mkdir and hit EEXIST, so by definition it does not hold the lock; the lock is
#   basename-only shared): held_pid/held_sid are read from the claim
#   dir's OWN metadata, so liveness is evaluated against the HOLDER, not the caller.
#   Do NOT refactor this to use $$/$sid — that reintroduces the per-session bug.
#     - If the holding SESSION is live (_cs_session_live: last_activity < 30 min)
#                                              → exit 1 with held-by message.
#     - If the holding session is dead/idle    → log warning, rm -rf and recreate.
#     - LEGACY pid-only claim dir (no session_id file) → fall back to the dead-PID test.
#
#   On success, writes pid, session_id, claimed_at inside the claim directory.
#   IMPORTANT — PID recorded is $$ of the CALLER, which MUST be a long-lived process
#   (skill shell, interactive shell). Do NOT call cs_claim_artifact from a hook
#   subprocess — the hook's $$ exits within seconds, making the claim appear immediately
#   dead to the reaper. Review: code-reviewer.
#   Release/cleanup: basename-only claims are NOT carried by cs_archive (no longer
#   under <sid>/) — they are reaped by cs_reap_stale_claims (dead-PID only, wired
#   into the session-init gated reaper). A crashed session's claim persists until
#   the next reaper pass OR until the next pickup of the same baton takes it over
#   inline (dead-PID) — bounded, best-effort. NOTE on foreign-baton coverage: a claim
#   written under a foreign <baton_repo_root> is NOT reached by session-init's reaper
#   (which fires on the cwd repo via _cs_sessions_dir) — it is cleaned up on next
#   contention via the inline dead-PID takeover, or by an explicit
#   cs_reap_stale_claims <baton-root> call. Review: code-reviewer.
#
#   Spec backlinks: docs/plans/2026-06-17-foreign-cwd-pickup-hardening.md § C1;
#                   docs/plans/2026-06-17-concurrent-pickup-guard-sid-regression.md § C1;
#                   docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C1
cs_claim_artifact() {
  local class="${1:?artifact class required}"
  local basename="${2:?basename required}"
  local baton_repo_root="${3:-}"
  # Canonical 4-tier resolution (override → CLAUDE_SESSION_ID → CLAUDE_CODE_SESSION_ID
  # → cwd sentinel). sid is a property of the running (cwd) session; only the lock
  # LOCATION follows the baton, so the sentinel read stays anchored to cwd.
  local sid
  sid=$(_cs_resolve_session_id)
  [[ -z "$sid" ]] && { echo "cs_claim_${class}: no session_id available" >&2; return 1; }

  local base claims_dir claim_dir
  if [[ -n "$baton_repo_root" ]]; then
    # Baton-repo mode REQUESTED (arg present) — fail loud on an unresolvable root
    # rather than silently writing the lock into the wrong (cwd) repo.
    if [[ ! -d "${baton_repo_root}/.git" ]]; then
      echo "cs_claim_${class}: baton repo root <${baton_repo_root}> is not a git repo" >&2
      return 1
    fi
    base="${baton_repo_root}/.git/coordinator-sessions"
  else
    base=$(_cs_sessions_dir) || return 1
  fi
  # Basename-only (NOT ${base}/${sid}/...): the shared path is the same-machine guard —
  # distinct-sid sessions must contend for ONE lock per artifact. The session-id is still
  # recorded in the claim metadata below (for the held-by message), just not in the path.
  claims_dir="${base}/${class}-claims"
  claim_dir="${claims_dir}/${basename}"

  mkdir -p "$claims_dir" 2>/dev/null || true

  # Attempt atomic mkdir — POSIX mkdir is atomic; fails EEXIST if already present
  if mkdir "$claim_dir" 2>/dev/null; then
    # Success — write claim metadata
    local now
    now=$(_cs_now_iso)
    echo "$$"    > "${claim_dir}/pid"
    echo "$sid"  > "${claim_dir}/session_id"
    echo "$now"  > "${claim_dir}/claimed_at"
    return 0
  fi

  # EEXIST — inspect existing claim. Liveness is evaluated against the HOLDER (the claim
  # dir's OWN metadata via _cs_claim_holder_live), never the caller — do NOT refactor to
  # $$/$sid (that reintroduces the per-session bug). The helper carries the canonical
  # session_id-recency key + the legacy pid-only fallback (one rule, shared with the reaper
  # and the memo sweep). held_pid/held_sid are read only for the diagnostic messages.
  local held_pid held_sid
  held_pid=$(cat "${claim_dir}/pid" 2>/dev/null || echo "")
  held_sid=$(cat "${claim_dir}/session_id" 2>/dev/null || echo "")

  if _cs_claim_holder_live "$claim_dir"; then
    echo "cs_claim_${class}: ${basename} held by session ${held_sid:-?} (PID ${held_pid:-?}) — concurrent /pickup detected" >&2
    return 1
  fi

  # Holder is dead or >30 min idle — stale claim; take over. (Atomic rm + mkdir below
  # is itself the race guard: a peer that re-claims between them makes our mkdir fail.)
  echo "cs_claim_${class}: stale claim on ${basename} (session ${held_sid:-?}, PID ${held_pid:-?} not live) — taking over" >&2
  rm -rf "$claim_dir" 2>/dev/null || true
  if mkdir "$claim_dir" 2>/dev/null; then
    local now
    now=$(_cs_now_iso)
    echo "$$"    > "${claim_dir}/pid"
    echo "$sid"  > "${claim_dir}/session_id"
    echo "$now"  > "${claim_dir}/claimed_at"
    return 0
  fi

  echo "cs_claim_${class}: failed to create claim dir for ${basename} after stale takeover" >&2
  return 1
}

# cs_claim_handoff <basename> [baton_repo_root]
# cs_claim_memo    <basename> [baton_repo_root]
#   Thin class-bound wrappers over cs_claim_artifact. The handoff wrapper preserves the
#   exact two-arg (basename, baton_repo_root) contract every existing call site uses —
#   byte-for-byte behavior. The memo wrapper is the parity addition for memo-pickup
#   (Memo Branch M2.5 of skills/pickup/SKILL.md).
cs_claim_handoff() { cs_claim_artifact handoff "$@"; }
cs_claim_memo()    { cs_claim_artifact memo "$@"; }

# cs_release_artifact <class> <basename> [baton_repo_root]
#   Explicit, holder-identity-checked release of a claim. Unlike handoffs (dead-PID
#   reaping only), memo-pickup reaches meaningful NON-TERMINAL dispositions while still
#   alive (Decline, Surface-to-PM) — those must release the claim so a legitimate
#   re-pickup is not blocked until the PID dies. SAFETY: release only if THIS session is
#   the holder (claim-dir pid == $$); if not the holder, or the claim is already absent,
#   it is a NO-OP (return 0). A bare rm without this check would race inline dead-PID
#   takeover and could delete a live peer's claim — the exact TOCTOU class cs_reap_stale_claims
#   guards against. Mirrors the held-pid-from-claim-metadata discipline above.
#
#   ORDERING CONTRACT (enforced by the caller, not here): the caller MUST revert the
#   artifact's frontmatter (status in_progress → open, clear stamps) BEFORE calling this.
#   That way a crash between the two steps leaves a recoverable "open but claim-held" state
#   (reaper / inline-takeover cleans up); the reverse (claim freed, status still in_progress)
#   would re-admit two sessions — the bug this whole workstream fixes.
#
#   Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C1 (the Staff Engineer #1)
cs_release_artifact() {
  local class="${1:?artifact class required}"
  local basename="${2:?basename required}"
  local baton_repo_root="${3:-}"

  local base
  if [[ -n "$baton_repo_root" ]]; then
    [[ -d "${baton_repo_root}/.git" ]] || return 0
    base="${baton_repo_root}/.git/coordinator-sessions"
  else
    base=$(_cs_sessions_dir) || return 0
  fi
  local claim_dir="${base}/${class}-claims/${basename}"
  [[ -d "$claim_dir" ]] || return 0   # already absent — no-op

  # Holder-identity check: only the session that holds the claim may release it
  # (_cs_claim_held_by_me — keyed on session_id == my id, NOT $$; the recorded pid is a
  # dead per-Bash $$ in-harness, so a $$ compare was a permanent no-op — lesson a167aa66).
  # Resolve my id ONCE and pass it to both TOCTOU reads, so the second read varies only on
  # the claim-dir content (the actual race), not on a re-resolution of my own id (F1).
  local my_sid; my_sid=$(_cs_resolve_session_id)
  _cs_claim_held_by_me "$claim_dir" "$my_sid" || return 0   # not the holder — no-op

  # TOCTOU re-read before rm: _cs_claim_held_by_me re-reads the dir, so calling it a second
  # time IS the two-read discipline. If an inline takeover (rm + mkdir + new session_id)
  # slipped in after the first check, the recheck no longer matches our id and we skip —
  # never delete a live peer's claim. The conservative outcome (return 0, never delete)
  # also covers the upgrade-era dir-vanished-between-checks race.
  _cs_claim_held_by_me "$claim_dir" "$my_sid" || return 0

  rm -rf "$claim_dir" 2>/dev/null || true
  return 0
}

# _cs_my_agent_touched <session_id> [mode]
#   Print (one per line) every repo-relative path touched by a sub-agent whose
#   .agents/<aid>/em-session-id.txt back-pointer is in the candidate set for
#   <session_id>.
#
#   mode (optional, default: broadened):
#     broadened — candidate set = {session_id} ∪ {all live session ids via
#                 cs_live_session_ids}.  Recovers the EM's own fan-out output on
#                 old Claude Code where executor SessionStart can pollute the
#                 .current-session-id sentinel (Issue-A, APPROVED_WITH_NOTES v3).
#                 Safe for the default (do_scoped) path because cs_compute_scope
#                 re-subtracts other_sessions downstream, so any over-reach is
#                 self-correcting.
#     exact     — candidate set = {session_id} only.  Use on the blanket path
#                 where broadening would scoop a sibling EM's own sub-agent
#                 back-pointer into "own", causing the blanket to absorb the
#                 sibling's in-flight files — the exact contamination the
#                 foreign-subtract is designed to prevent.
#
#   Returns 0 always (fail-open: attribution is advisory, never blocks the caller).
#
# Spec backlink: docs/plans/2026-06-22-authorized-blanket-orphan-capture-not-sibling-sweep.md § C1a Step 1.
_cs_my_agent_touched() {
  local session_id="${1:?session_id required}"
  local mode="${2:-broadened}"
  local base
  base=$(_cs_sessions_dir) || return 0
  [[ -d "${base}/.agents" ]] || return 0

  # Build the candidate set of EM session ids whose agents count as "mine".
  # broadened: own sid + all live sibling sids (sentinel-pollution recovery).
  # exact:     own sid only (blanket path — must not absorb sibling sub-agents).
  local -a _candidates=("$session_id")
  if [[ "$mode" == "broadened" ]]; then
    local _lsid
    while IFS= read -r _lsid; do
      [[ -n "$_lsid" ]] && _candidates+=("$_lsid")
    done < <(cs_live_session_ids 2>/dev/null || true)
  fi

  # Helper: returns 0 if <em_sid> is in _candidates array, 1 otherwise.
  # Linear scan — _candidates is typically 1-3 entries.
  _cmat_in_candidates() {
    local needle="$1" c
    for c in "${_candidates[@]}"; do
      [[ "$c" == "$needle" ]] && return 0
    done
    return 1
  }

  local agent_dir backptr em_sid agent_touched fpath
  for agent_dir in "${base}/.agents"/*/; do
    [[ -d "$agent_dir" ]] || continue
    backptr="${agent_dir}em-session-id.txt"
    [[ -f "$backptr" ]] || continue
    em_sid=$(head -1 "$backptr" 2>/dev/null)
    [[ -z "$em_sid" ]] && continue           # malformed back-pointer; soft-skip
    _cmat_in_candidates "$em_sid" || continue
    agent_touched="${agent_dir}touched.txt"
    [[ -f "$agent_touched" ]] || continue
    while IFS= read -r fpath; do
      [[ -n "$fpath" ]] && echo "$fpath"
    done < "$agent_touched"
  done
  return 0
}

# cs_sweep_actioned_memos <git_root>
#   Archive terminal (status: actioned) cross-repo memos out of cross-repo/inbox/
#   into cross-repo/archive/ (flat — memo convention, NOT <YYYY-MM>/ subfolders like
#   handoffs). Generalizes the consumed-handoff sweep in session-init.sh for the memo
#   class: memos reach `status: actioned` in place (pickup Memo Branch M4) but, unlike
#   handoffs, have no successor-archival moment, so they leaked into the inbox forever
#   (43 piled up before the 2026-06-22 manual sweep).
#
#   Contract: enumerate → skip → `git mv` (which STAGES the move) → echo the moved count
#   to stdout. This function does NOT commit — the caller owns the commit so each context
#   uses the right shape:
#     • session-init.sh   — gpgsign=false explicit-path commit (TTY-less hook).
#     • workstream-complete Step 2.65 — folds the staged moves into its Step 3 commit (signed).
#
#   Skips: README.md, any non-actioned status (open/in_progress — in_progress means a live
#   session holds a claim), live-claimed memos (defensive against a mid-flip race), and any
#   memo whose destination already exists (idempotent — a second run finds nothing to move).
#   Silent on the happy path; honors INIT_SKIP_SWEEP (set by the caller's branch guard).
#   Best-effort: returns 0 always, never blocks the caller.
#
#   Spec backlink: state/handoffs/2026-06-22_232810_unified-terminal-artifact-archival-sweep.md
cs_sweep_actioned_memos() {
  local git_root="${1:-}"
  [[ -z "$git_root" ]] && git_root=$(_cs_git_root 2>/dev/null)
  [[ -z "$git_root" ]] && { echo 0; return 0; }
  [[ -n "${INIT_SKIP_SWEEP:-}" ]] && { echo 0; return 0; }
  [[ -d "${git_root}/cross-repo/inbox" ]] || { echo 0; return 0; }
  command -v node &>/dev/null || { echo 0; return 0; }

  # Resolve query-records.js relative to this lib first (sibling/non-~/.claude installs),
  # falling back to the canonical ~/.claude path. Same resolution shape as the stamp lib
  # in session-init's orphan-handoff sweep.
  local QR
  QR="$(dirname "${BASH_SOURCE[0]}")/../bin/query-records.js"
  [[ -f "$QR" ]] || QR="${HOME}/.claude/plugins/coordinator/bin/query-records.js"
  [[ -f "$QR" ]] || { echo 0; return 0; }

  local actioned_paths
  actioned_paths=$(node "$QR" --type cross-repo-memo --where "status=actioned" --format paths --root "$git_root" 2>/dev/null || true)
  [[ -z "$actioned_paths" ]] && { echo 0; return 0; }

  mkdir -p "${git_root}/cross-repo/archive" 2>/dev/null || true

  local moved=0 fpath fname claim_dir
  while IFS= read -r fpath; do
    [[ -z "$fpath" ]] && continue
    fname=$(basename "$fpath")
    [[ "$fname" == "README.md" ]] && continue

    # Claim safety: skip if a LIVE session holds the memo claim (_cs_claim_holder_live —
    # the SAME key as the claim takeover and the reaper). An actioned memo is terminal so
    # this should never collide, but the defensive skip is cheap insurance against a
    # mid-flip race. Keying on the holder's session-recency (not _cs_pid_alive) is load-
    # bearing: the recorded pid is a dead per-Bash-call $$ in-harness, so a pid check here
    # was a permanent no-op that would have archived a memo out from under a live claim
    # (code-reviewer F2, 2026-06-23). LEGACY fallback (pid-only dir) lives in the helper.
    claim_dir="${git_root}/.git/coordinator-sessions/memo-claims/${fname}"
    [[ -d "$claim_dir" ]] && _cs_claim_holder_live "$claim_dir" && continue

    # Idempotency / collision guard: never clobber an existing archived file.
    [[ -e "${git_root}/cross-repo/archive/${fname}" ]] && continue

    if git -C "$git_root" mv "cross-repo/inbox/${fname}" "cross-repo/archive/${fname}" 2>/dev/null; then
      moved=$((moved + 1))
    fi
  done <<< "$actioned_paths"

  echo "$moved"
  return 0
}

# cs_sweep_terminal_plans <git_root>
#   Archives docs/plans/*.md files whose frontmatter status is one of the
#   terminal values (implemented, superseded, abandoned) into
#   archive/specs/YYYY-MM/ keyed off the date in the plan filename.
#
#   Mirrors cs_sweep_actioned_memos in structure: guard chain, query-records.js
#   resolution, git mv staging, echo-count, caller-owns-commit, return-0-always.
#
#   Skips:
#     • Plans whose status is not in {implemented, superseded, abandoned}.
#     • Plans referenced by an ACTIVE handoff in state/handoffs/*.md (any
#       handoff whose frontmatter status is NOT consumed or superseded).
#     • Plans referenced by a LIVE plan in docs/plans/*.md (any plan whose
#       frontmatter status is NOT in {implemented, superseded, abandoned}).
#       Review sidecars (<plan-stem>.<tag>.md) are NOT counted as live plans —
#       they cite their parent's filename, which would otherwise make every
#       plan with a sidecar hold itself and never archive.
#     • Plans whose archive destination already exists (idempotent).
#   Only live handoffs + live plans gate the move; spec_backlink references in
#   CLAUDE.md / docs/wiki / skills are NOT a skip reason.
#
#   Sidecar pattern: every file matching ${basename_without_ext}.*.md in
#   docs/plans/ is moved alongside the primary plan file.
#
#   Consumer-project guard: repos without docs/plans/ return 0 silently.
#   Silent on the happy path; honors INIT_SKIP_SWEEP.
#   Best-effort: returns 0 always, never blocks the caller.
#
#   Spec backlink: state/handoffs/2026-06-22_232810_unified-terminal-artifact-archival-sweep.md
cs_sweep_terminal_plans() {
  local git_root="${1:-}"
  [[ -z "$git_root" ]] && git_root=$(_cs_git_root 2>/dev/null)
  [[ -z "$git_root" ]] && { echo 0; return 0; }
  [[ -n "${INIT_SKIP_SWEEP:-}" ]] && { echo 0; return 0; }
  [[ -d "${git_root}/docs/plans" ]] || { echo 0; return 0; }
  command -v node &>/dev/null || { echo 0; return 0; }

  # Resolve query-records.js relative to this lib first (sibling/non-~/.claude installs),
  # falling back to the canonical ~/.claude path. Same resolution shape as the stamp lib
  # in session-init's orphan-handoff sweep.
  local QR
  QR="$(dirname "${BASH_SOURCE[0]}")/../bin/query-records.js"
  [[ -f "$QR" ]] || QR="${HOME}/.claude/plugins/coordinator/bin/query-records.js"
  [[ -f "$QR" ]] || { echo 0; return 0; }

  # Resolve spawn-hidden.sh; fall back to bare node when absent (partial install or
  # non-Windows path where suppression is a no-op anyway).
  # Review: reviewer — no fallback guard meant missing spawn-hidden.sh caused all three
  #   calls to fail silently and cs_sweep_terminal_plans returned 0 with no work done.
  local _SPAWN_HIDDEN
  _SPAWN_HIDDEN="$(dirname "${BASH_SOURCE[0]}")/spawn-hidden.sh"

  # query-records --where supports AND only, no OR. Use three separate calls and
  # union+dedup the resulting paths.
  local raw_paths all_paths
  if [[ -f "$_SPAWN_HIDDEN" ]]; then
    raw_paths=$(
      {
        bash "$_SPAWN_HIDDEN" --stdin-mode=safe node "$QR" --type plan --where "status=implemented" --format paths --root "$git_root" 2>/dev/null || true # verify-no-console-flash: allow — routed via spawn-hidden.sh (variable $_SPAWN_HIDDEN; literal text absent but routing is identical)
        bash "$_SPAWN_HIDDEN" --stdin-mode=safe node "$QR" --type plan --where "status=superseded"  --format paths --root "$git_root" 2>/dev/null || true # verify-no-console-flash: allow — routed via spawn-hidden.sh (variable form)
        bash "$_SPAWN_HIDDEN" --stdin-mode=safe node "$QR" --type plan --where "status=abandoned"   --format paths --root "$git_root" 2>/dev/null || true # verify-no-console-flash: allow — routed via spawn-hidden.sh (variable form)
      } | sort -u
    )
  else
    # spawn-hidden absent (partial install); bare node is behavior-equivalent on
    # non-Windows (no conhost suppression needed) and on Windows (nodew.exe is
    # unavailable regardless, so windowsHide cannot be achieved at shell level).
    raw_paths=$(
      {
        node "$QR" --type plan --where "status=implemented" --format paths --root "$git_root" 2>/dev/null || true # verify-no-console-flash: allow — fallback when spawn-hidden absent; node has no windowless equiv
        node "$QR" --type plan --where "status=superseded"  --format paths --root "$git_root" 2>/dev/null || true # verify-no-console-flash: allow — fallback when spawn-hidden absent; node has no windowless equiv
        node "$QR" --type plan --where "status=abandoned"   --format paths --root "$git_root" 2>/dev/null || true # verify-no-console-flash: allow — fallback when spawn-hidden absent; node has no windowless equiv
      } | sort -u
    )
  fi
  [[ -z "$raw_paths" ]] && { echo 0; return 0; }

  # Build a set of basenames from ACTIVE handoffs (status not consumed/superseded).
  # A hit in this set → skip the plan.
  local active_handoff_refs=""
  if [[ -d "${git_root}/state/handoffs" ]]; then
    local hfile hstatus hbody
    for hfile in "${git_root}/state/handoffs/"*.md; do
      [[ -f "$hfile" ]] || continue
      # Extract frontmatter status (first occurrence, between --- delimiters).
      hstatus=$(awk '/^---/{f++} f==1 && /^status:/{print $2; exit}' "$hfile" 2>/dev/null || true)
      # superseded: retired handoff status (2026-06-26) — tolerated for legacy/external records, never written anew
      [[ "$hstatus" == "consumed" || "$hstatus" == "superseded" ]] && continue
      # This is a live handoff — collect basenames it references.
      hbody=$(cat "$hfile" 2>/dev/null || true)
      active_handoff_refs="${active_handoff_refs}
${hbody}"
    done
  fi

  # Build a set of basenames from LIVE plans (status not in terminal set).
  # Exclude review sidecars (<plan-stem>.<tag>.md): they carry no terminal
  # status yet their bodies cite the parent plan's filename, so counting them
  # as live plans would make every plan with a review sidecar hold ITSELF and
  # never archive. A plan filename is YYYY-MM-DD-slug.md (kebab slug, no dots),
  # so a name whose stem still contains a '.' after stripping .md is a sidecar.
  # query-records --type plan applies the same exclusion to the terminal set.
  # (Both sidecar shapes have a dot-containing stripped stem and are excluded:
  #  <plan-stem>.<tag>.md and <plan-stem>.md.<tag>.md.)
  local live_plan_refs=""
  local lfile lstatus lstem
  for lfile in "${git_root}/docs/plans/"*.md; do
    [[ -f "$lfile" ]] || continue
    lstem=$(basename "$lfile"); lstem="${lstem%.md}"
    [[ "$lstem" == *.* ]] && continue   # sidecar (<plan-stem>.<tag>), not a plan
    lstatus=$(awk '/^---/{f++} f==1 && /^status:/{print $2; exit}' "$lfile" 2>/dev/null || true)
    [[ "$lstatus" == "implemented" || "$lstatus" == "superseded" || "$lstatus" == "abandoned" ]] && continue
    local lbody
    lbody=$(cat "$lfile" 2>/dev/null || true)
    live_plan_refs="${live_plan_refs}
${lbody}"
  done

  local moved=0 rel_path fname basename_noext yyyy_mm arch_dir sidecar
  while IFS= read -r rel_path; do
    [[ -z "$rel_path" ]] && continue
    fname=$(basename "$rel_path")

    # Derive YYYY-MM from the leading date in the filename (e.g. 2026-06-23-foo.md → 2026-06).
    yyyy_mm=$(echo "$fname" | grep -oE '^[0-9]{4}-[0-9]{2}' || true)
    [[ -z "$yyyy_mm" ]] && continue   # filename has no date prefix — skip

    arch_dir="${git_root}/archive/specs/${yyyy_mm}"
    basename_noext="${fname%.md}"

    # Idempotency guard.
    [[ -e "${arch_dir}/${fname}" ]] && continue

    # Skip if referenced by a live handoff.
    if echo "$active_handoff_refs" | grep -qF "$fname" 2>/dev/null; then
      continue
    fi

    # Skip if referenced by a live plan.
    if echo "$live_plan_refs" | grep -qF "$fname" 2>/dev/null; then
      continue
    fi

    mkdir -p "$arch_dir" 2>/dev/null || true

    # Move primary plan file.
    git -C "$git_root" mv "docs/plans/${fname}" "archive/specs/${yyyy_mm}/${fname}" 2>/dev/null || continue
    moved=$((moved + 1))

    # Move any sidecar files matching ${basename_noext}.*.md in docs/plans/.
    # Enumerate via `find` (not a bare for-glob): a bare glob aborts under zsh's
    # default `nomatch` when a plan has no sidecars. The production caller
    # (session-init.sh) is bash, but workstream-complete's snippet runs through
    # whatever shell the EM is in — so keep this shell-agnostic.
    local scar_fname
    while IFS= read -r sidecar; do
      [[ -n "$sidecar" && -f "$sidecar" ]] || continue
      scar_fname=$(basename "$sidecar")
      [[ -e "${arch_dir}/${scar_fname}" ]] && continue
      git -C "$git_root" mv "docs/plans/${scar_fname}" "archive/specs/${yyyy_mm}/${scar_fname}" 2>/dev/null || true
    done < <(find "${git_root}/docs/plans" -maxdepth 1 -name "${basename_noext}.*.md" 2>/dev/null)
  done <<< "$raw_paths"

  echo "$moved"
  return 0
}

# cs_reap_agents
#   Companion to cs_reap_stale: archives .agents/<aid>/ subdirs whose
#   touched.txt mtime is older than 24h. Bounds the agent-id index from
#   unbounded growth.
#
# Issue A, archive/specs/2026-05-05-issue-a-agent-id-linkage.md.
cs_reap_agents() {
  local base
  base=$(_cs_sessions_dir) || return 0
  local agents_base="${base}/.agents"
  [[ -d "$agents_base" ]] || return 0
  local now_epoch
  now_epoch=$(_cs_now_epoch)
  local threshold=$(( 24 * 3600 ))
  local archive_root="${base}/.archive"
  mkdir -p "$archive_root" 2>/dev/null
  for adir in "$agents_base"/*/; do
    [[ -d "$adir" ]] || continue
    local touched="${adir}touched.txt"
    if [[ ! -f "$touched" ]]; then
      rmdir "$adir" 2>/dev/null
      continue
    fi
    local mtime
    mtime=$(_cs_mtime_epoch "$touched")
    if [[ $(( now_epoch - mtime )) -gt "$threshold" ]]; then
      local aid
      aid=$(basename "$adir")
      local target="${archive_root}/_agents-${aid}-$(date +%Y%m%d 2>/dev/null || echo unknown)"
      if mv "$adir" "$target" 2>/dev/null; then
        echo "reaped agent ${aid}"
      else
        rm -rf "$adir" 2>/dev/null
      fi
    fi
  done
}
