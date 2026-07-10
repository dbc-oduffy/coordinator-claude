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
#   DISTINCT from _cs_stable_pid_alive: that helper gates on the separate comm-verified
#   `stable_pid` field (=$PPID, the long-lived claude session process) + lstart identity
#   and IS the legitimate session-liveness signal. This function operates on the meta
#   `pid` field (=$$ of a dying hook subshell) and is explicitly prohibited from liveness.
_cs_pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

# _cs_stable_pid_alive <pid> <stored_lstart> <stored_start_epoch>
#   Returns 0 (alive, same process) iff:
#     1. The process still exists (ps -p returns a non-empty lstart), AND
#     2. Its birth instant matches the stored value (same process, not a
#        recycled PID that happened to reuse the number after the original died).
#
#   Uses ps -o lstart= for BOTH existence and identity — sidesteps kill -0
#   ESRCH/EPERM ambiguity entirely:
#     - ESRCH (no such process): ps returns empty → returns 1 (dead). Correct.
#     - EPERM (process exists but owned by different uid — possible in future
#       container/namespace builds): ps still reports the process lstart →
#       identity comparison proceeds → correct result. No false-dead.
#
#   Identity comparison — TZ-invariant path (preferred):
#     When <stored_start_epoch> is non-empty and non-zero, the current lstart
#     string is parsed to an epoch under the CURRENT TZ (render+parse share "now",
#     so the conversion is self-consistent). That epoch is compared to the stored
#     epoch, which was computed at capture time — both are absolute UTC seconds,
#     so the comparison is TZ-invariant regardless of locale drift between capture
#     and verify. The stored lstart STRING is never re-parsed here; it has lost its
#     origin TZ and any attempt to parse it would be TZ-vulnerable.
#
#   Legacy fallback (string compare):
#     When no stored epoch is present (pre-upgrade meta.json) or the current-lstart
#     parse misses (transient failure), the function falls back to a direct lstart
#     string comparison. This is TZ-vulnerable but self-heals: the next cs_init
#     writes stable_pid_start_epoch and future calls take the epoch path.
#
#   This helper is called ONLY from _cs_session_live. It is NOT _cs_pid_alive on
#   the `pid` ($$) field — that path is prohibited from session liveness. This
#   helper keys on the separate `stable_pid` field (comm-verified $PPID, the
#   long-lived claude session process) captured at cs_init time.
#
#   Spec: docs/plans/2026-06-27-liveness-first-claim-staleness.md § _cs_stable_pid_alive
_cs_stable_pid_alive() {
  local pid="${1:-}" stored_lstart="${2:-}" stored_start_epoch="${3:-}"
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] || return 1
  local now_lstart
  now_lstart=$(ps -p "$pid" -o lstart= 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  [[ -z "$now_lstart" ]] && return 1     # process gone (ESRCH) or ps failed
  # TZ-invariant path: when a stored start-epoch is present, compare epochs. The current
  # process's lstart is parsed under the CURRENT TZ (render+parse share "now"); the stored
  # epoch was computed at capture under the capture TZ — both are absolute, so the compare
  # is TZ-invariant. NEVER parse the STORED lstart string here (it has lost its origin TZ).
  if [[ -n "$stored_start_epoch" && "$stored_start_epoch" != 0 ]]; then
    local now_epoch
    now_epoch=$(_cs_lstart_to_epoch "$now_lstart")
    if [[ -n "$now_epoch" && "$now_epoch" != 0 ]]; then
      [[ "$now_epoch" == "$stored_start_epoch" ]]  # same birth instant = same process; mismatch = recycled = dead
      return $?
    fi
    # current-lstart parse failed (not a dead process) → fall through to legacy string compare
    # rather than asserting dead (avoids a false-dead on a transient parse miss).
  fi
  # Legacy fallback (pre-upgrade meta with no epoch, or parse miss): TZ-vulnerable string
  # compare, self-heals when the session's next cs_init writes stable_pid_start_epoch.
  [[ -n "$stored_lstart" ]] || return 1
  [[ "$now_lstart" == "$stored_lstart" ]]
}

# _cs_resolve_session_id
#   Resolve THIS session's id via the canonical 4-tier chain:
#     1. $COORDINATOR_SESSION_ID  (explicit test override)
#     2. $CLAUDE_SESSION_ID       (explicit override slot)
#     3. $CLAUDE_CODE_SESSION_ID  (platform-injected, Claude Code ≥ ~2.1.150)
#     4. .git/coordinator-sessions/.current-session-id sentinel (old Claude Code)
#   The sentinel is anchored to the running (cwd) session — never a baton repo.
#   Mirror note: coordinator-safe-commit's resolve_session_id is a parallel
#   inline copy of this chain (a sibling chunk routes it through this function).
#   cs_claim_artifact no longer inlines — it delegates to _cs_resolve_session_id.
#
#   Tier-4 ambiguity semantics (C2 — docs/plans/2026-07-06-racy-sentinel-tier4-fail-empty.md):
#   The sentinel is a last-writer-wins file; under concurrent sessions it names
#   whichever session most recently initialized, not the caller's. Tier-4 therefore
#   returns empty (the canonical "unresolvable" signal) under concurrency ambiguity:
#     - ≥2 live sessions (always ambiguous)
#     - exactly 1 live but sentinel ∉ live set (stale/phantom writer)
#     - 0 live but sentinel names an existing session dir (dead/racing-writer)
#   It returns the sentinel only when unambiguous:
#     - 0 live AND no session dirs exist (true legacy — tier-4's designed case)
#     - 1 live AND sentinel ∈ live (solo session, no ambiguity)
#   Tiers 1-3 (env vars) are byte-for-byte unchanged; the ambiguity guard
#   applies only on the tier-4 sentinel path.
#   Always returns 0; prints the empty string when no session id is resolvable
#   (callers gate on empty, including the _cs_git_root-failure path).
_cs_resolve_session_id() {
  local sid="${COORDINATOR_SESSION_ID:-}"
  [[ -z "$sid" ]] && sid="${CLAUDE_SESSION_ID:-}"
  [[ -z "$sid" ]] && sid="${CLAUDE_CODE_SESSION_ID:-}"
  if [[ -z "$sid" ]]; then
    local root sentinel_file
    root=$(_cs_git_root) || { echo ""; return 0; }
    sentinel_file="${root}/.git/coordinator-sessions/.current-session-id"
    [[ -f "$sentinel_file" ]] && sid=$(cat "$sentinel_file" 2>/dev/null)
    # Ambiguity-aware sentinel trust (F2/F1 — fail-empty under concurrency).
    # Performance note (F1): cs_live_session_ids is O(n) over session dirs,
    # paid as one Python startup + in-process scan (~860ms / 74 dirs measured
    # 2026-07-06; ~200ms one-time startup cost dominates at low dir-counts).
    # Tier-4 is the detached-bash common case, so this scan runs on every
    # detached-bash cs_* resolution.
    # Review: code-reviewer — F1: updated from stale per-dir cost model (200ms/dir)
    # to AC8-measured single-Python-invocation figure (~860ms / 74 dirs, 2026-07-06).
    #
    # Memoization-within-a-resolution was evaluated and rejected (AC8): a cached
    # live set goes stale as sessions spawn/die and reopens the wrong-attribution
    # race. The real latency lever is cs_live_session_ids' Python startup cost;
    # see state/bug-backlog/2026-07-06-cs-live-session-ids-scan-cost.yaml.
    # Review: code-reviewer — F2: replaced open memoization suggestion (which AC8
    # explicitly rejected) with the correct disposition; the prior text presented a
    # dangerous rejected approach as a valid future mitigation.
    if [[ -n "$sid" ]]; then
      local live live_count sentinel_dir
      live="$(cs_live_session_ids 2>/dev/null)"
      if [[ -n "$live" ]]; then
        live_count=$(printf '%s\n' "$live" | grep -c .)
      else
        live_count=0
      fi
      sentinel_dir="${root}/.git/coordinator-sessions/${sid}"
      if (( live_count >= 2 )); then
        # ≥2 live sessions: ambiguous under concurrency — return empty.
        sid=""
      elif (( live_count == 1 )); then
        # 1 live: trust sentinel only if it is the sole live session.
        if ! printf '%s\n' "$live" | grep -Fxq -- "$sid"; then
          sid=""
        fi
      else
        # 0 live: trust sentinel only when no session dir exists (true legacy).
        # If sentinel_dir exists (dead/racing-writer not counted live), fail-empty.
        if [[ -d "$sentinel_dir" ]]; then
          sid=""
        fi
      fi
    fi
  fi
  echo "$sid"
}

# cs_resolve_session_id: public alias for the canonical 4-tier session-id resolver.
# Session-terminator skills source this lib and call cs_resolve_session_id; the private
# _cs_resolve_session_id and its internal callers are unchanged (additive exposure only).
# Spec: docs/plans/2026-06-30-session-terminator-mechanism-unification.md C1.
cs_resolve_session_id() { _cs_resolve_session_id "$@"; }

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
    if [[ ! -f "$_lib" ]]; then
      _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
      if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
      _lib="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/lib/resolve-python.sh"
      # shellcheck source=/dev/null
      source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
      coordinator_trusted_root_guard --mode=fail-loud --root="$_lib" --site="$0"
    fi
    # shellcheck source=/dev/null
    [[ -f "$_lib" ]] && source "$_lib"
    if [[ -n "$PYTHON_BIN" ]]; then
      epoch=$(CS_ISO_TS="${iso%Z}" "$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "import os,datetime; print(int(datetime.datetime.fromisoformat(os.environ['CS_ISO_TS']).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null) \
        || epoch=0
    fi
  fi
  echo "$epoch"
}

# _cs_lstart_to_epoch <lstart>: convert ps -o lstart= string to epoch seconds
#
# PURPOSE: Parse a ps-rendered local-time string (e.g. "Sat Jun 27 22:41:38 2026")
# into epoch seconds, interpreted in LOCAL TZ (no -u / UTC coercion on any branch).
#
# LOCAL vs UTC contrast with _cs_iso_to_epoch: _cs_iso_to_epoch receives an explicit
# "...Z" UTC string and passes -u to date / uses .replace(tzinfo=datetime.timezone.utc)
# in python. This helper is the OPPOSITE — ps lstart carries no TZ marker and is
# rendered in the machine's local zone, so every branch parses WITHOUT -u and WITHOUT
# UTC tzinfo injection.
#
# BSD space-pad: BSD/macOS ps formats single-digit days with a leading space (%e),
# producing "Sat Jun  7 22:41:38 2026" (double space). Collapse with tr -s ' ' before
# parsing so both GNU and BSD date -f accept the string; normalization happens inside
# this helper only, not on stored values.
#
# Accepted residual: a process born in the zone's fall-back DST repeated hour renders
# an ambiguous local-time string; disambiguation may be ±3600s — negligible, strictly
# better than the status-quo false-dead on any TZ shift.
_cs_lstart_to_epoch() {
  local s="${1:-}"
  if [[ -z "$s" ]]; then echo 0; return; fi
  # Collapse BSD double-space (single-digit %e day pad) before any parsing attempt
  s=$(echo "$s" | tr -s ' ')
  local epoch
  # GNU date: parse in LOCAL TZ (no -u flag)
  epoch=$(date -d "$s" +%s 2>/dev/null) \
    || epoch=$(date -j -f "%a %b %d %H:%M:%S %Y" "$s" +%s 2>/dev/null) \
    || epoch=0
  # epoch==0 is treated as "failed parse" → try the python branch. A real process
  # birth at the Unix epoch (1970) is impossible, so conflating a 0-result with
  # a parse failure is safe here. (review F5)
  if [[ "$epoch" == 0 ]]; then
    # Resolve via shared lib so Windows uses pythonw.exe (no console flash).
    local _lib="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
    if [[ ! -f "$_lib" ]]; then
      _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
      if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
      _lib="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/lib/resolve-python.sh"
      # shellcheck source=/dev/null
      source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
      coordinator_trusted_root_guard --mode=fail-loud --root="$_lib" --site="$0"
    fi
    # shellcheck source=/dev/null
    [[ -f "$_lib" ]] && source "$_lib"
    if [[ -n "$PYTHON_BIN" ]]; then
      # strptime + .timestamp() interprets as LOCAL time — do NOT add tzinfo here
      epoch=$(CS_LSTART="$s" "$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "import os,datetime; print(int(datetime.datetime.strptime(os.environ['CS_LSTART'], '%a %b %d %H:%M:%S %Y').timestamp()))" 2>/dev/null) \
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
  if [[ -z "${_CS_FORCE_NO_JQ:-}" ]] && command -v jq &>/dev/null; then
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
  if [[ -z "${_CS_FORCE_NO_JQ:-}" ]] && command -v jq &>/dev/null; then
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
    # A-F3: detect missing-field case (sed substitution silently no-ops when the
    # field is absent from an existing meta.json — ADDING a new field like
    # stable_pid/stable_pid_lstart on the refresh path requires an explicit append).
    if ! grep -qF "\"${field}\"" "$meta" 2>/dev/null; then
      local _tmp2
      _tmp2=$(mktemp) && \
        _CS_F="$field" _CS_V="$value" awk '
          BEGIN { ins = ",\"" ENVIRON["_CS_F"] "\": \"" ENVIRON["_CS_V"] "\""; done=0 }
          /^}[[:space:]]*$/ && !done { print ins; done=1 }
          { print }
        ' "$meta" > "$_tmp2" 2>/dev/null && \
        mv "$_tmp2" "$meta" || { rm -f "$_tmp2"; true; }
    fi
  fi
}

# _cs_is_confined_findings_agent <subagent_type>
#   Returns 0 (true) if <subagent_type> is a member of the confined findings-agent
#   SET; returns 1 otherwise.
#
#   PURPOSE: Single source of truth for the guard-before-grant set consumed by
#   block-reviewer-write-outside-sidecar.sh and block-reviewer-bash-outside-allowlist.sh.
#   Both hooks source this lib and call this predicate for the primary (agent_type) and
#   secondary (back-pointer-resolved subagent_type) legs of the OR-resolver. Having the
#   SET in one place means adding a new confined type requires exactly one edit here,
#   not two hook edits that can drift.
#
#   CONFINED SET — now a single member:
#     coordinator:code-reviewer              — Sonnet code-reviewer (self-persists via snippet)
#
#   Review personas (coordinator:staff-eng, coordinator:eng-director, coordinator:vp-product,
#   coordinator:senior-front-end, coordinator:staff-ux, coordinator:staff-data-sci) were REMOVED
#   from this set on 2026-07-01.  They are trusted full-tool Opus agents given clear
#   review-and-return instructions; unconditional agent_type confinement broke their
#   legitimate authoring/analysis roles (empirically: a synthesizer-mode eng-director was
#   confined out of writing its own plan, 2026-07-01).  They self-persist via
#   snippets/findings-self-persist-bash.md, not enforced tool-stripping.
#
#   NOT IN SET (run domain tools + Bash freely):
#     security-audit-worker, dep-cve-auditor, test-evidence-parser, all review personas
#
#   Spec backlink: docs/plans/2026-07-01-findings-agents-self-persist.md § OR-resolver
_cs_is_confined_findings_agent() {
  local t="${1:-}"
  case "$t" in
    coordinator:code-reviewer)
      return 0 ;;
    *)
      return 1 ;;
  esac
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

  # Guard 1 — comm-verify $PPID before storing as stable_pid.
  # Require exact match `claude` (NOT a prefix like `claude*`): Linux truncates comm
  # to 15 chars; `claude` is 6 chars, safe. A false-positive prefix-match (e.g.
  # `claude-helper`) would store the wrong stable_pid and defeat Guard 1's skip-safe
  # purpose. If comm != `claude` (e.g. a shell, CI runner, or future binary), leave
  # stable_pid empty → recency-only fallback → zero regression for non-harness runs.
  local stable_pid="" stable_pid_lstart="" stable_pid_start_epoch=""
  # Single atomic ps call: comm= and lstart= in one invocation — avoids a PID-recycling
  # race between two separate ps calls (guard 2 exists to prevent this; don't replicate
  # the gap in the very call that captures the guard 2 anchor). Both BSD/macOS and
  # GNU/Linux support the `-o comm=,lstart=` multi-field spec. (A-F4)
  local _ppid_line _ppid_comm _ppid_lstart
  _ppid_line=$(ps -p "$PPID" -o comm=,lstart= 2>/dev/null || true)
  # Split: first whitespace-delimited word = comm; everything after first space = lstart.
  # `read -r A B` assigns first field to A and the remainder (all remaining fields) to B —
  # handles lstart's internal spaces ("Fri Jun 27 12:34:56 2026") without re-splitting.
  read -r _ppid_comm _ppid_lstart <<< "$_ppid_line"
  _ppid_comm=$(printf '%s' "${_ppid_comm:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  if [[ "$_ppid_comm" == "claude" ]]; then
    stable_pid="$PPID"
    # Capture absolute start-timestamp string (BSD/macOS + GNU/Linux both support lstart;
    # constant for a process's lifetime — string equality at verify sidesteps all etime
    # parsing complexity and is portable). Guard 2 (PID-recycling defense) is then a
    # string compare: same lstart = same process; different = PID recycled = dead.
    stable_pid_lstart=$(printf '%s' "${_ppid_lstart:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    # If lstart capture failed for any reason, fall back to recency-only (clear both)
    if [[ -z "$stable_pid_lstart" ]]; then
      stable_pid=""
      stable_pid_lstart=""
    fi
    # TZ-invariant identity key: epoch computed at capture in the rendering TZ (see
    # _cs_lstart_to_epoch). Empty/0 (parse fail) → omit; verify side falls back to lstart string.
    if [[ -n "$stable_pid_lstart" ]]; then
      stable_pid_start_epoch=$(_cs_lstart_to_epoch "$stable_pid_lstart")
      [[ "$stable_pid_start_epoch" == 0 ]] && stable_pid_start_epoch=""
    fi
  fi

  if [[ -f "${sdir}/meta.json" ]]; then
    existing_goal=$(_cs_read_meta_field "$sdir" "goal")
    [[ -z "$goal" ]] && goal="$existing_goal"
    _cs_update_meta_field "$sdir" "pid" "$pid"
    _cs_update_meta_field "$sdir" "last_activity" "$now"
    _cs_update_meta_field "$sdir" "branch" "$branch"
    # Conditional-omit: _cs_update_meta_field has `value="${3:?}"` — it hard-errors on
    # empty. Only write stable_pid/lstart when Guard 1 succeeded (non-empty).
    [[ -n "$stable_pid" ]] && _cs_update_meta_field "$sdir" "stable_pid" "$stable_pid"
    [[ -n "$stable_pid_lstart" ]] && _cs_update_meta_field "$sdir" "stable_pid_lstart" "$stable_pid_lstart"
    [[ -n "$stable_pid_start_epoch" ]] && _cs_update_meta_field "$sdir" "stable_pid_start_epoch" "$stable_pid_start_epoch"
  else
    if [[ -z "${_CS_FORCE_NO_JQ:-}" ]] && command -v jq >/dev/null 2>&1; then
      # Build stable_pid args conditionally — omit fields entirely when Guard 1 missed.
      local jq_stable_args=()
      local jq_stable_expr=''
      if [[ -n "$stable_pid" ]]; then
        jq_stable_args+=(--arg stable_pid "$stable_pid" --arg stable_pid_lstart "$stable_pid_lstart")
        jq_stable_expr=' | .stable_pid = $stable_pid | .stable_pid_lstart = $stable_pid_lstart'
        # Write epoch only when non-empty — matches the update path's guard so all
        # three meta-write paths share one contract: field ABSENT when no epoch. (review F6)
        if [[ -n "$stable_pid_start_epoch" ]]; then
          jq_stable_args+=(--arg stable_pid_start_epoch "$stable_pid_start_epoch")
          jq_stable_expr="${jq_stable_expr} | .stable_pid_start_epoch = \$stable_pid_start_epoch"
        fi
      fi
      jq -n \
        --arg sid "$sid" \
        --arg branch "$branch" \
        --arg pid "$pid" \
        --arg now "$now" \
        --arg goal "$goal" \
        "${jq_stable_args[@]}" \
        "{session_id: \$sid, branch: \$branch, pid: \$pid, last_activity: \$now, goal: \$goal}${jq_stable_expr}" \
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
      # Non-jq fallback: conditionally append stable_pid/lstart lines
      local stable_pid_lines=""
      if [[ -n "$stable_pid" ]]; then
        local spid_escaped slstart_escaped
        spid_escaped=$(_cs_json_escape "$stable_pid")
        slstart_escaped=$(_cs_json_escape "$stable_pid_lstart")
        stable_pid_lines="  \"stable_pid\": \"${spid_escaped}\",
  \"stable_pid_lstart\": \"${slstart_escaped}\","
        # Write epoch only when non-empty — consistent with the jq + update paths
        # (field ABSENT when no epoch, not present-but-empty). (review F6)
        if [[ -n "$stable_pid_start_epoch" ]]; then
          local sepoch_escaped
          sepoch_escaped=$(_cs_json_escape "$stable_pid_start_epoch")
          stable_pid_lines="${stable_pid_lines}
  \"stable_pid_start_epoch\": \"${sepoch_escaped}\","
        fi
      fi
      if [[ -n "$stable_pid_lines" ]]; then
        cat > "${sdir}/meta.json" <<METAJSON
{
  "session_id": "${sid_escaped}",
  "branch": "${branch_escaped}",
  "pid": "${pid_escaped}",
  "last_activity": "${now_escaped}",
  "goal": "${goal_escaped}",
${stable_pid_lines%,}
}
METAJSON
      else
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
        if [[ ! -f "$_lib" ]]; then
          _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
          if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
          _lib="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/lib/resolve-python.sh"
          # shellcheck source=/dev/null
          source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
          coordinator_trusted_root_guard --mode=fail-loud --root="$_lib" --site="$0"
        fi
        # shellcheck source=/dev/null
        [[ -f "$_lib" ]] && source "$_lib"
        if [[ -n "$PYTHON_BIN" ]]; then
          # realpath resolves symlinks on both sides before relpath so that macOS
          # /var→/private/var doesn't cause a prefix mismatch (git resolves the
          # repo root through /private/var while the incoming fpath may still use
          # /var).  os.path.realpath handles non-existent paths (canonicalises the
          # existing prefix), so untracked files are safe.
          rel=$("$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "import os,sys; print(os.path.relpath(os.path.realpath(sys.argv[1]), os.path.realpath(sys.argv[2])).replace(os.sep,'/'))" \
                "$fpath" "$root" 2>/dev/null) || rel=""
        else
          rel=""
        fi
      fi
    fi
    # Fall back to as-is if normalization failed
    [[ -n "$rel" ]] && fpath="$rel"
  fi

  # Guard: skip if fpath is STILL absolute after the normalization attempt (e.g. Python
  # unavailable, path outside repo) — an absolute path in touched.txt corrupts the
  # relative-path scope set.  Fail-open: skip.
  # Review: code-reviewer — F1: old guard ([[ -z "$fpath" ]]) was dead code; fpath is always
  # non-empty (bound via ${2:?}). When normalization fails, fpath retains the original absolute
  # value, so the correct guard skips on a STILL-absolute path, not an empty one.
  [[ "$fpath" == /* || "$fpath" == [A-Za-z]:* ]] && return 0

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
#     inactive_for > 24h AND session is not live per `_cs_session_live` (stable_pid-authoritative + recency fallback) AND
#     no commits referencing this scope in last 24h
# Review: code-reviewer — Condition-2 was updated (C4) from "no alive PID in meta.json" to
#   "_cs_session_live"; header docstring updated to match current implementation.
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

    # Condition 2: session is not live (single canonical liveness key — _cs_session_live).
    # Layer-1 stable_pid-authoritative when present, Layer-2 recency fallback. Replaces the
    # old _cs_pid_alive(meta pid) check, which was always-false in-harness ($$ is a dead
    # hook subshell) and therefore wrongly archived a >24h-idle session that still holds a
    # LIVE stable_pid (a real long-running Claude process). Reuses _cs_session_live so the
    # reaper agrees with the claim layer on what "live" means (single-liveness-key invariant).
    # → RAW-PID-LIVENESS: never ps -p / kill -0 a stored pid; go through _cs_session_live.
    # Cost: _cs_session_live spawns subshells (meta reads + ps) vs old kill -0 builtin — acceptable; reaper is session-init-gated (infrequent) and >24h-idle sessions are rare.
    if _cs_session_live "$sid"; then
      continue  # session still live — do not archive
    fi

    # All conditions met — archive it
    if cs_archive "$sid"; then
      echo "reaped ${sid}"
    fi
  done
}

# cs_reap_stale_claims [baton_repo_root] [class]
#   Reap orphaned artifact claims left by cs_claim_artifact (handoff + memo + plan classes).
#   Because the claim dir is basename-only (<base>/<class>-claims/<basename>/, NOT under
#   <sid>/), cs_archive's session-dir move no longer carries it away — this is its release path.
#
#   Class coverage: a NO-ARG call sweeps BOTH handoff-claims AND memo-claims AND plan-claims
#   (so the existing no-arg session-init call site reaps all three classes with zero edits).
#   An optional <class> second arg narrows to one subdir (handoff | memo | plan).
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
    subdirs="handoff-claims memo-claims plan-claims"
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
#   Pure recency gate — Layer 2 of the two-layer liveness model.
#   Returns 0 (true) when the session should be considered Live by recency alone:
#   elapsed_sec < 30 minutes. Signature (pid, elapsed_sec) is UNCHANGED.
#   The <pid> argument is retained for signature stability and diagnostic
#   display but is DELIBERATELY NOT part of the liveness decision.
#
#   TWO-LAYER LIVENESS MODEL (as of 2026-06-27):
#   Layer 1 — PPID-authoritative process-aliveness (when stable_pid is present):
#     _cs_session_live reads `stable_pid` and `stable_pid_lstart` from meta.json.
#     If stable_pid is non-empty, _cs_stable_pid_alive decides: process alive +
#     lstart matches → LIVE (authoritative; recency NOT consulted); process gone or
#     lstart mismatch (PID recycled) → DEAD (reapable within seconds of process exit).
#     This is the new "liveness-first" signal that closes the SIGKILL-before-
#     PostToolUse residual documented below.
#   Layer 2 — recency fallback (when stable_pid is absent/empty):
#     Falls through to THIS function (_cs_is_session_live). elapsed_sec < 30 min
#     → live. This is the unchanged path for: non-harness runs (stable_pid never
#     captured), legacy meta.json without stable_pid, and Guard 1 comm-miss (PPID
#     comm != `claude` → stable_pid left empty → recency-only fallback, zero
#     regression).
#   The PPID logic lives ONLY in _cs_session_live + _cs_stable_pid_alive. It does
#   NOT appear in cs_claim_artifact, cs_reap_stale_claims, or cs_sweep_actioned_memos
#   — those still route through _cs_claim_holder_live → _cs_session_live (single-
#   liveness-key invariant preserved). cs_active_sessions and cs_live_session_ids
#   also route through _cs_session_live (two-layer, not _cs_is_session_live directly
#   — A-F2; single-liveness-key invariant applies to enumeration too).
#   Spec: docs/plans/2026-06-27-liveness-first-claim-staleness.md.
#
#   IMPORTANT — `stable_pid` vs `pid` (the prohibition stands, augmented):
#   The meta `pid` field (=$$ of the dying hook subshell) is STILL PROHIBITED from
#   the liveness decision — nothing about this two-layer model changes that. The new
#   `stable_pid` is a SEPARATE field: it is the comm-verified PPID ($PPID, the
#   long-lived claude session process), verified at cs_init via Guard 1. Do NOT
#   conflate `stable_pid`=PPID (legitimate) with `pid`=$$ (prohibited). Reading
#   the 2026-06-23 history: the wrongful-takeover regression was caused by keying
#   liveness on `pid` (=$$ of the hook subshell, dead within seconds). That decision
#   explicitly closed the `$$` door. The new `stable_pid` route uses a DIFFERENT PID
#   from a DIFFERENT source — it was never evaluated in the 2026-06-23 work.
#   Spec: state/handoffs/2026-06-23_153742_claim-lock-pid-death-false-positive.md.
#
#   Why pid is not the key (in-harness reality): every Claude Code Bash/hook tool
#   call runs in a separate OS process with a fresh $$. cs_init writes meta.json's
#   `pid` as $$ of the hook subshell, which is dead within seconds of session open
#   (session-init.sh § "session_alive=true via PID is structurally unreachable";
#   session-heartbeat.sh). A kill -0 liveness gate on `pid` therefore reports EVERY
#   session dead, including the one actively running right now. The signal that
#   actually tracks a live session is last_activity, refreshed on every
#   PreToolUse:Bash by session-heartbeat.sh (60s throttle). This is the same recency
#   rule the session-init.sh orphan sweep already trusts (its ALIVE_WINDOW is 10m;
#   the 30m here is the documented session-liveness threshold surfaced by
#   cs_active_sessions and consumed by the claim layer).
#
#   BOUNDED EDGE (the Staff Engineer F0, closed 2026-06-23 by PostToolUse heartbeat; SIGKILL
#   residual NOW CLOSED by stable_pid gate): the heartbeat was originally
#   PreToolUse:Bash ONLY, so last_activity was stamped at the START of a Bash call
#   and frozen for its duration. CLOSED 2026-06-23: session-heartbeat.sh registered
#   on PostToolUse:Bash (hooks.json) — recency stamped at BOTH ends; only a session
#   idle >30 min BETWEEN commands ages out. Prior residual (accepted at the time):
#   a command KILLED (SIGKILL/OOM) before its PostToolUse leg fires left last_activity
#   at the PreToolUse stamp, indistinguishable from a truly-dead session for up to 30
#   min. THAT RESIDUAL IS NOW CLOSED by the stable_pid Layer 1: kill/OOM terminates
#   the `claude` process, making ps return empty for stable_pid within seconds →
#   Layer 1 returns DEAD immediately. The wrongful-takeover window after SIGKILL is
#   now seconds (ps latency), not ≤30 min. Spec:
#   state/handoffs/2026-06-23_233740_claim-liveness-hardening-r2.md (prior residual);
#   docs/plans/2026-06-27-liveness-first-claim-staleness.md (this closure).
#
#   Single-source-of-truth: cs_active_sessions, cs_live_session_ids (fast-path and
#   fallback), _cs_session_live (claim takeover / release / reaper), and any future
#   callers route through _cs_session_live → this helper (Layer 2 arm) to stay in
#   sync. Do NOT reintroduce a _cs_pid_alive gate on the `pid` field anywhere —
#   it silently zeroes the live set in-harness (the 2026-06-23 regression).
_cs_is_session_live() {
  local pid="${1:-}" elapsed_sec="${2:-0}"  # pid: diagnostic only — see header
  local thirty_min=$(( 30 * 60 ))
  [[ "$elapsed_sec" =~ ^[0-9]+$ ]] || return 1
  [[ "$elapsed_sec" -lt "$thirty_min" ]]
}

# _cs_session_live <session_id>
#   exit 0 iff <session_id> is a LIVE session. THE shared key for the claim layer.
#   O(1) single-session lookup: reads that one session's meta.json directly,
#   rather than scanning every dir (that is cs_live_session_ids' job).
#
#   Two-layer decision (see _cs_is_session_live header for full model):
#   Layer 1 (PPID-authoritative): if stable_pid is non-empty in meta.json, call
#     _cs_stable_pid_alive. Alive + lstart match → LIVE (return 0; recency NOT
#     consulted). Gone or lstart mismatch → DEAD (return 1; faster than recency).
#   Layer 2 (recency fallback): if stable_pid is empty/absent, fall through to
#     _cs_is_session_live(pid, elapsed) — the unchanged recency rule.
#
#   Empty/unknown sid, missing session dir, or missing/unparseable last_activity
#   → not live. Claim takeover, release holder-check, and the reaper all call
#   through here so they provably agree on what "stale" means.
_cs_session_live() {
  local sid="${1:-}"
  [[ -n "$sid" ]] || return 1
  local sdir
  sdir=$(_cs_session_dir "$sid" 2>/dev/null) || return 1
  [[ -d "$sdir" ]] || return 1

  # Layer 1: PPID-authoritative process check (when stable_pid was captured at cs_init).
  # _cs_stable_pid_alive is called ONLY here — never in cs_claim_artifact,
  # cs_reap_stale_claims, or cs_sweep_actioned_memos (single-liveness-key invariant).
  local stable_pid stable_pid_lstart stable_pid_start_epoch
  stable_pid=$(_cs_read_meta_field "$sdir" "stable_pid")
  if [[ -n "$stable_pid" ]]; then
    stable_pid_lstart=$(_cs_read_meta_field "$sdir" "stable_pid_lstart")
    stable_pid_start_epoch=$(_cs_read_meta_field "$sdir" "stable_pid_start_epoch")
    # lstart absent (partial write / TOCTOU between the two meta writes at :285-286)
    # ≠ process dead — fall through to Layer 2 to preserve the safety net. (A-F1)
    if [[ -n "$stable_pid_lstart" ]]; then
      # Authoritative: if process alive + lstart matches → LIVE (recency ignored).
      # If gone or lstart mismatch (PID recycled) → DEAD (return 1 immediately).
      _cs_stable_pid_alive "$stable_pid" "$stable_pid_lstart" "$stable_pid_start_epoch"
      return $?
    fi
    # stable_pid present but lstart absent — fall through to Layer 2 recency
  fi

  # Layer 2: recency fallback — stable_pid absent (Guard 1 comm-miss, legacy meta.json,
  # or non-harness run). Unchanged from pre-2026-06-27 behavior; zero regression.
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

    # Liveness: delegated to _cs_session_live (two-layer: PPID-authoritative when
    # stable_pid present, recency fallback otherwise) — PID is diagnostic-only.
    # (A-F2: was _cs_is_session_live; now consistent with claim layer.) (A-F6 doc)
    if _cs_session_live "$sid"; then
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
#   Print one live session id per line — liveness delegated to _cs_session_live
#   (two-layer: Layer 1 PPID-authoritative when stable_pid present, Layer 2 recency
#   fallback otherwise). PID is diagnostic only (see _cs_is_session_live header for
#   why kill -0 on meta `pid` is structurally dead in-harness). (A-F5 doc)
#   No formatting, no headers. Structured-data sibling of cs_active_sessions.
#   Consumed by coordinator-safe-commit's agent-id-union candidate-set build
#   (Issue A, archive/specs/2026-05-05-issue-a-agent-id-linkage.md).
#
# Liveness criterion delegated to _cs_session_live (both this function and
# cs_active_sessions route through _cs_session_live — no duplication, consistent
# with the claim layer). (A-F2)
cs_live_session_ids() {
  # Scan-set size is bounded by cs_reap_stale (session-init gated-reaper cadence), which
  # archives dead >24h sessions before this function's O(n) dir scan runs.
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
  if [[ ! -f "$_lib_rp" ]]; then
    _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
    if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
    _lib_rp="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/lib/resolve-python.sh"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$_lib_rp" --site="$0"
  fi
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
        # A-F2: emit stable_pid as 4th field so bash can route to _cs_session_live
        # (two-layer) for sessions that have it, vs Layer-2-only for those that don't.
        stable_pid = str(d.get('stable_pid', '') or '')
        sys.stdout.write(f"{sid}\t{pid}\t{ep}\t{stable_pid}\n")
    except Exception:
        pass
PYEOF
)
    if [[ -n "$tsv" ]]; then
      local sid pid last_epoch stable_pid elapsed
      while IFS=$'\t' read -r sid pid last_epoch stable_pid; do
        [[ -z "$sid" ]] && continue
        # Strip trailing CR — Python's text-mode stdout on Windows writes \r\n,
        # and bash `read` strips \n but not \r, leaving the last field with a
        # trailing carriage return. ONLY the last TSV field carries the CR
        # (interior fields are split clean by IFS=$'\t'). stable_pid is now the
        # last field (A-F2 added it after last_epoch — CR strip moved here per the
        # comment above warning "if a future column is appended ... move the strip").
        stable_pid="${stable_pid%$'\r'}"
        [[ -z "$last_epoch" || ! "$last_epoch" =~ ^[0-9]+$ ]] && last_epoch=0
        elapsed=$(( now_epoch - last_epoch ))
        # A-F2: if stable_pid is non-empty, delegate to _cs_session_live (two-layer:
        # Layer 1 PPID-authoritative). If empty, use Layer-2 recency-only — same as
        # before this change for Guard-1-miss / legacy sessions. (correctness > speed)
        if [[ -n "$stable_pid" ]]; then
          if _cs_session_live "$sid"; then
            echo "$sid"
          fi
        elif _cs_is_session_live "$pid" "$elapsed"; then
          echo "$sid"
        fi
      done <<< "$tsv"
    fi
    return 0
  fi

  # Fallback path (no Python): per-dir scan — two-layer liveness via _cs_session_live.
  # A-F2: was _cs_is_session_live (Layer-2-only); now delegates to _cs_session_live
  # (two-layer), consistent with the claim layer and cs_active_sessions.
  for sdir in "${base}"/*/; do
    [[ -d "$sdir" ]] || continue
    local sid
    sid=$(basename "$sdir")
    [[ "$sid" == ".archive" ]] && continue
    [[ "$sid" == ".agents" ]] && continue

    if _cs_session_live "$sid"; then
      echo "$sid"
    fi
  done
}

# cs_claim_holder_live <claim_dir>
#   Public wrapper over _cs_claim_holder_live. exit 0 iff the session holding
#   <claim_dir> is live; exit 1 otherwise. The canonical EM-facing liveness
#   predicate for claim-layer stand-down decisions.
#
#   Liveness verdict is pid-free ONLY for session_id-bearing claim dirs (today's
#   standard): the holder is cross-referenced against the session-registry
#   meta.json via _cs_session_live (two-layer: PPID-authoritative on stable_pid
#   + stable_pid_lstart when present, recency fallback otherwise). Legacy
#   pid-only claim dirs (no session_id file, pre-upgrade) fall back to
#   _cs_pid_alive on the ephemeral pid field — that path is structurally
#   "always dead in-harness" — and self-heal to session_id on first takeover.
#   NEVER call ps -p / kill -0 on a stored pid directly as a liveness gate;
#   the stored pid is a dead hook-subshell $$. → RAW-PID-LIVENESS
#   (docs/wiki/coordinator-tripwires.md).
#
#   Same-repo verdict boundary: _cs_session_live resolves the session dir via
#   the cwd git-root's .git/coordinator-sessions registry. For same-repo
#   plan/handoff claims on the shared work/* branch — the EM stand-down
#   predicate's target — claim and registry always coincide. Cross-repo holder
#   resolution (foreign-baton claim in a different repo from the holder's
#   cwd) is a future registry-resolution parameter to be threaded into
#   _cs_session_live and this wrapper; it is NOT duplicated claim state (see
#   docs/plans/2026-06-27-pickup-liveness-canonical-helper.md § Decision:
#   spec #5 — that design was explicitly rejected to preserve the
#   single-liveness-key invariant).
#
#   Routing provenance: → docs/wiki/spinoff-handoffs.md § Claim liveness
#   (authoritative single-liveness-key routing contract).
#
#   Delegates entirely to _cs_claim_holder_live — do NOT reimplement liveness
#   here. (A-F6)
cs_claim_holder_live() {
  _cs_claim_holder_live "$@"
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
#   On EEXIST — liveness is evaluated against the HOLDER (the claim dir's OWN metadata),
#   never the caller: held_pid/held_sid are read from the claim dir's OWN files.
#   EXCEPTION — plan-class re-entrance: a plan is claimed at two seams (execute-plan +
#   workstream-complete), which may occur in the SAME session. cs_claim_artifact inserts
#   a self-identity check (_cs_claim_held_by_me) BEFORE the liveness branch, so a session
#   re-claiming its OWN plan claim returns 0 (re-entrant success). This branch is
#   byte-for-byte unchanged for handoff/memo — those never re-claim the same basename in
#   a session, so they never reach the self-check branch either.
#   Do NOT refactor the LIVENESS evaluation to use $$/$sid — that reintroduces the
#   per-session bug. The self-identity check (_cs_claim_held_by_me) is the ONLY place
#   that legitimately reads held metadata vs the resolved sid — the same "evaluate against
#   the holder" discipline cs_release_artifact already uses. These are distinct operations.
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
#   Spec backlinks: archive/specs/2026-06/2026-06-17-foreign-cwd-pickup-hardening.md § C1;
#                   archive/specs/2026-06/2026-06-17-concurrent-pickup-guard-sid-regression.md § C1;
#                   archive/specs/2026-06/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C1;
#                   docs/plans/2026-06-26-cs-claim-plan-execution-lock.md § C1
cs_claim_artifact() {
  local class="${1:?artifact class required}"
  local basename="${2:?basename required}"
  local baton_repo_root="${3:-}"
  # Canonical 4-tier resolution (override → CLAUDE_SESSION_ID → CLAUDE_CODE_SESSION_ID
  # → cwd sentinel). sid is a property of the running (cwd) session; only the lock
  # LOCATION follows the baton, so the sentinel read stays anchored to cwd.
  local sid
  sid=$(_cs_resolve_session_id)
  [[ -z "$sid" ]] && { echo "cs_claim_${class}: session id unresolvable under concurrency — run: export CLAUDE_SESSION_ID=<harness-id>" >&2; return 1; }

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

  # Re-entrant self-claim (PLAN CLASS ONLY): if THIS session already holds the claim,
  # succeed immediately. SCOPED to the plan class deliberately — see below.
  # Motivation: the plan class is claimed at two seams — execute-plan AND workstream-complete
  # — which may both run in the same session. Without this branch, the second seam would hit
  # the liveness check below (holder IS live — it's us!) and fail loud against itself.
  # WHY class-scoped (`$class == plan`), NOT global: handoff/memo are claimed ONCE per session,
  # and their existing contract is "a same-session re-claim is REJECTED" — encoded by tests
  # T16a/T18c (the claim-pid-death false-positive regression net, spec
  # 2026-06-23_153742_claim-lock-pid-death-false-positive). A global re-entrant branch would
  # silently flip that to return-0 and break byte-for-byte compatibility (it does — that is
  # exactly the T16a/T18c regression this guard prevents). Scoping to `plan` keeps handoff/memo
  # behaviour identical (they never reach the return-0 path) AND confines the new behaviour to
  # the class that actually needs it. It also sidesteps `_cs_claim_held_by_me`'s legacy pid-only
  # fallback (pid==$$), which is a false-positive in-process for a same-process re-claim — plan
  # claims always carry a session_id file (written at creation below), so the session_id branch
  # of _cs_claim_held_by_me is always the one taken for the plan class.
  # Compaction note: a compacted session gets a NEW session-id, so it re-acquires the claim
  # via the normal stale-takeover path below (its old sid is now "stale"), NOT this re-entrant
  # branch (which fires only when the SAME sid holds BOTH seams in one live session).
  # Do NOT hand-roll a held_sid == $sid string compare here — that skips the
  # session_id-vs-legacy-pid discrimination and the internal TOCTOU re-read that
  # _cs_claim_held_by_me provides. Pass $sid so both reads key off ONE resolved identity.
  # Grep-confirmed: no same-session double-claim call site exists for cs_claim_handoff or
  # cs_claim_memo in this codebase — re-entrancy at those classes is correctly rejected (C1 item 7).
  # Review: code-reviewer — F6: grep-evidence note re-added after class-scope rewrite dropped it.
  if [[ "$class" == "plan" ]] && _cs_claim_held_by_me "$claim_dir" "$sid"; then return 0; fi

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

# cs_claim_plan <basename>
#   ONE-arg wrapper (memo-class precedent: cs_claim_memo <basename> [baton_repo_root]).
#   Plan execution is always in-repo; cwd-default via _cs_sessions_dir guarantees an
#   identical claim base across the execute-plan and workstream-complete seams (both run
#   in the ~/.claude cwd). The baton_repo_root arg is deliberately OMITTED — passing "$@"
#   would silently absorb a stray extra arg from the caller and write the lock into the
#   wrong repo. ONE arg only; the plan class never needs a foreign-baton lock location.
cs_claim_plan() {
  cs_claim_artifact plan "$1" || return $?
  # C3 — plan-claim instrumentation: record plan.path + plan.scope_mode into
  # session-shape.json at the moment the claim succeeds. Best-effort / non-fatal;
  # a write failure here must NOT break the plan claim (rc=0 already returned above).
  # plan.scope_mode is the write-time fact from plan frontmatter; light|full sizing
  # is a deferred read-time ceremony derivation, NOT stored here (plan F4 fix).
  # Spec backlink: docs/plans/2026-07-02-ceremony-as-pipeline-v1-session-state-co.md § C3
  local _c3_slug="$1" _c3_sid _c3_root _c3_rel _c3_scope _c3_frag
  _c3_sid=$(_cs_resolve_session_id) || true
  if [[ -n "$_c3_sid" ]]; then
    _c3_root=$(_cs_git_root) || true
    _c3_rel="docs/plans/${_c3_slug}.md"
    _c3_scope=""
    if [[ -n "$_c3_root" && -f "${_c3_root}/${_c3_rel}" ]]; then
      _c3_scope=$(grep '^scope_mode:' "${_c3_root}/${_c3_rel}" 2>/dev/null \
        | head -1 \
        | sed 's/^scope_mode:[[:space:]]*//' \
        | sed 's/[[:space:]]*$//' \
        | tr -d '"' | tr -d "'") || true
    fi
    # JSON-escape path and scope_mode (guard against embedded quotes / backslashes)
    _c3_rel="${_c3_rel//\\/\\\\}"; _c3_rel="${_c3_rel//\"/\\\"}"
    if [[ -n "$_c3_scope" ]]; then
      _c3_scope="${_c3_scope//\\/\\\\}"; _c3_scope="${_c3_scope//\"/\\\"}"
      _c3_frag="{\"plan\":{\"path\":\"${_c3_rel}\",\"scope_mode\":\"${_c3_scope}\"}}"
    else
      _c3_frag="{\"plan\":{\"path\":\"${_c3_rel}\",\"scope_mode\":null}}"
    fi
    cs_session_shape_set "$_c3_sid" "$_c3_frag" 2>/dev/null || true
  fi
}

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

# cs_clear_claim_if_dead <class> <basename> [baton_repo_root]
#   Single-named-claim sibling of cs_reap_stale_claims — clear-only (does NOT
#   re-claim). Intended for the manual EM-driven claim-clear / takeover path:
#   forces the caller through a liveness gate before any rm -rf. The claim is
#   removed only when the holder is DEAD; a live holder triggers a non-zero return
#   with a stderr message naming the holder. Clear and re-claim are separate
#   operations — do NOT bundle them (see Anti-scope in plan § C2).
#
#   LIVENESS: delegates entirely to _cs_claim_holder_live (the canonical liveness predicate). NEVER ps -p / kill -0 on a stored pid directly.
#   Review: code-reviewer R2 — F4 comment claimed "via public wrapper cs_claim_holder_live" but code calls _cs_claim_holder_live directly
#   → RAW-PID-LIVENESS (docs/wiki/coordinator-tripwires.md).
#   The single-liveness-key invariant (one predicate, all claim-layer callers)
#   is preserved; do NOT reimplement liveness here.
#
#   LEGACY PID-ONLY RESIDUAL (plan F2): a claim dir with no session_id file
#   (pre-upgrade era) routes _cs_claim_holder_live to the ephemeral-pid test,
#   which reads "structurally always dead in-harness." A legacy pid-only claim
#   whose session is LIVE will therefore be classified DEAD and cleared (false-
#   dead stomp via this door). When clearing such a dir (session_id file absent),
#   a DISTINCT stderr note is emitted so the caller is not falsely reassured.
#   The human stand-down discipline still matters for legacy dirs.
#
#   BATON-ROOT CONTRACT: if baton_repo_root (arg 3) is supplied, a missing .git
#   dir is a FAIL-LOUD error — mirrors cs_claim_artifact :1427-1431, NOT the
#   reaper's silent || return 0 at :831. This function is EM-callable and must
#   surface errors explicitly.
#
#   TOCTOU: two sequential _cs_claim_holder_live calls (matching the double-read
#   pattern in cs_reap_stale_claims :855/:861 and cs_release_artifact :1570/:1577)
#   bracket the rm -rf. If a concurrent takeover lands between reads (rm + mkdir +
#   new live session_id), the second read sees the NEW live holder and aborts.
#
#   Spec backlink: docs/plans/2026-06-30-claim-clear-liveness-gate.md § C2
cs_clear_claim_if_dead() {
  local class="${1:?class required}"
  local basename="${2:?basename required}"
  local baton_repo_root="${3:-}"

  # Class validation: restrict to the three canonical artifact classes.
  case "$class" in
    handoff|memo|plan) ;;
    *)
      echo "cs_clear_claim_if_dead: invalid class '${class}' (must be handoff, memo, or plan)" >&2
      return 1
      ;;
  esac

  # Base resolution: fail-loud on a bad/absent baton root (mirrors cs_claim_artifact
  # :1427-1431 — NOT the reaper's silent || return 0; this function is EM-callable).
  local base
  if [[ -n "$baton_repo_root" ]]; then
    if [[ ! -d "${baton_repo_root}/.git" ]]; then
      echo "cs_clear_claim_if_dead: baton repo root <${baton_repo_root}> is not a git repo" >&2
      return 1
    fi
    base="${baton_repo_root}/.git/coordinator-sessions"
  else
    # Review: code-reviewer R2 — F2 || return 0 (not 1): missing sessions dir → no claim can exist → idempotent success per AC3
    base=$(_cs_sessions_dir) || return 0
  fi

  local claim_dir="${base}/${class}-claims/${basename}"

  # Idempotent on absent claim dir — non-fatal, return 0.
  [[ -d "$claim_dir" ]] || return 0

  # Liveness gate — read 1: refuse if the holder is still live.
  if _cs_claim_holder_live "$claim_dir"; then
    local holder
    holder=$(cat "${claim_dir}/session_id" 2>/dev/null || cat "${claim_dir}/pid" 2>/dev/null || echo "unknown")
    echo "cs_clear_claim_if_dead: refusing to clear claim '${basename}' — holder is live (session: ${holder})" >&2
    return 1
  fi

  # TOCTOU re-read — read 2 (mirrors cs_reap_stale_claims :855/:861): if a concurrent
  # takeover landed between reads (rm + mkdir + new live session_id), the new live holder
  # is detected here and the clear is aborted.
  if _cs_claim_holder_live "$claim_dir"; then
    local holder
    holder=$(cat "${claim_dir}/session_id" 2>/dev/null || cat "${claim_dir}/pid" 2>/dev/null || echo "unknown")
    echo "cs_clear_claim_if_dead: aborting clear of '${basename}' — holder became live after TOCTOU re-read (session: ${holder})" >&2
    return 1
  fi

  # Emit a distinct note for legacy pid-only claim dirs (no session_id) — liveness
  # fell back to the ephemeral-pid test (always dead in-harness); the caller cannot
  # be certain the session was truly dead.
  if [[ ! -f "${claim_dir}/session_id" ]]; then
    echo "note: cleared a legacy pid-only claim (no session_id) — liveness could not be session-verified" >&2
  fi

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
  if [[ ! -f "$QR" ]]; then
    _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
    if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
    QR="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/bin/query-records.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$QR" --site="$0"
  fi
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
  if [[ ! -f "$QR" ]]; then
    _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
    if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
    QR="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/bin/query-records.js"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$QR" --site="$0"
  fi
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
  #
  # Resolve handoffs directory via state-root seam (C4 per-repo repoint).
  # When git_root is the coordinator meta-repo (~/.claude), handoffs live in
  # the example-orchestration-hub state root (migrated). Otherwise they stay in ${git_root}/state.
  # Uses coordinator_is_meta_repo / coordinator_example_orchestration_hub_root when available
  # (pre-sourced upstream); falls back to machine-local get repos.example_orchestration_hub_repo.
  # FLAG: coordinator-session.sh does NOT source coordinator-state-root.sh at file
  # scope — its file-scope set -uo pipefail would propagate through this broadly-
  # sourced 2600+ line lib (no circular dep exists; inline path chosen instead).
  # Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4
  local _cts_handoffs_dir="${git_root}/state/handoffs"
  if command -v coordinator_is_meta_repo >/dev/null 2>&1 \
      && coordinator_is_meta_repo "$git_root" 2>/dev/null; then
    local _cts_mr=""
    if command -v coordinator_example_orchestration_hub_root >/dev/null 2>&1; then
      _cts_mr="$(coordinator_example_orchestration_hub_root 2>/dev/null || true)"
    else
      _cts_mr="$(machine-local get repos.example_orchestration_hub_repo 2>/dev/null || true)"
    fi
    [[ -n "$_cts_mr" ]] && _cts_handoffs_dir="${_cts_mr}/state/handoffs"
  fi
  local active_handoff_refs=""
  if [[ -d "$_cts_handoffs_dir" ]]; then
    local hfile hstatus hbody
    for hfile in "${_cts_handoffs_dir}/"*.md; do
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

# ---------------------------------------------------------------------------
# Teammate identity resolution — shared canonical-id contract
# Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C7
# ---------------------------------------------------------------------------

# CS_CANONICAL_AGENT_ID_RE — single source of truth for the bare-hex reviewer-guard
# agent_id format predicate.  The reviewer-write guard
# (hooks/scripts/block-reviewer-write-outside-sidecar.sh) branches on this format
# to identify unnamed reviewer subagents; pinning it here ensures a format divergence
# between the guard and the e2e harness assertions is caught structurally, not at runtime.
#
# Format: lowercase hex, ≥12 chars.  Probe 0.1 captured 17-char hex ids for unnamed
# agents — this regex is the de-facto contract the D3 23/0 unit test pins.
# Named-agent ids (produced by cs_build_canonical_agent_id) use a different shape:
#   <name>@session-<short_session> — those are NOT matched by this predicate.
#
# Spec backlink: docs/plans/2026-06-30-reviewer-findings-self-persist.md § D3, AC4
CS_CANONICAL_AGENT_ID_RE='^[a-f0-9]{12,}$'

# _cs_canonical_agent_id_format_ok <id>
#   Returns 0 when <id> matches CS_CANONICAL_AGENT_ID_RE; 1 otherwise.
#   Shared predicate — the reviewer-write guard and the e2e harness both call this,
#   so a regex change in CS_CANONICAL_AGENT_ID_RE propagates to all callers atomically.
#   Pure function — no filesystem I/O; safe on the hook hot path.
_cs_canonical_agent_id_format_ok() {
  [[ "$1" =~ $CS_CANONICAL_AGENT_ID_RE ]]
}

# cs_build_canonical_agent_id <name> <short_session>
#   Echoes the canonical EM-side agent id: "<name>@session-<short_session>".
#   SHARED CONTRACT: this is the ONE place where the teammate canonical-id format
#   string is constructed.  Called ONLY on the subagent-side reconstruction path by
#   resolve_subagent_identity (below).  The EM-side writer (track-dispatched-agents.sh,
#   C1) receives the canonical id directly from the harness (tool_response.agent_id)
#   and records it verbatim — it does NOT call this builder.
#
#   Forward-compat caveat: the <name>@session-<short> shape is probe-confirmed against
#   harness 2.1.185.  A format change must update ALL THREE surfaces: (1) this builder,
#   (2) the harness-protocol expectation in resolve_subagent_identity, AND (3) the
#   format guard in track-dispatched-agents.sh (the @session- value-guard regex at
#   the `^[A-Za-z0-9_.-]+@session-` check).
#
#   Pure function — no filesystem I/O, no side effects; safe on the hook hot path.
cs_build_canonical_agent_id() {
  local name="${1:?name required}"
  local short_session="${2:?short_session required}"
  echo "${name}@session-${short_session}"
}

# resolve_subagent_identity <agent_id> <session_id>
#   Translates a subagent-side agent_id to the canonical EM-side id, or echoes empty
#   on no-match (fail-closed).  Three paths:
#
#   (a) Bare hex  ^[a-f0-9]{12,}$  — unnamed agent fast path.  Echoes agent_id
#       unchanged; session_id is ignored.  Byte-identical to today's behaviour —
#       no regression risk for unnamed background/foreground dispatches.
#
#   (b) Named teammate  ^a(.+)-[a-f0-9]{16}$  — strip leading 'a' and fixed-length
#       16-hex suffix to extract <name> (robust even when the name contains dashes,
#       e.g. aprobe2-teammate-64cd7f42c270a899 → probe2-teammate).  Requires:
#       non-empty extracted name AND session_id with ≥ 8 chars.  On success
#       echoes cs_build_canonical_agent_id "$name" "${session_id:0:8}".  On failure
#       echoes empty (fail-closed).
#
#   (c) Anything else → echo empty (fail-closed).
#
#   Forward-compat caveat: the subagent-side grammar a<name>-<16hex> is
#   probe-confirmed against harness 2.1.185.  If a future harness changes the
#   subagent session_id shape or the a<name>-<16hex> prefix this function fails
#   closed (path (c)) rather than silently mapping to a wrong id — callers must
#   handle empty as "unknown agent / treat as unnamed".  Do NOT parse agent_type
#   for the name; the a<name>-<16hex> parse is self-contained.
#
#   Pure function — no filesystem I/O, no side effects; safe on the hook hot path.
resolve_subagent_identity() {
  local agent_id="${1:-}"
  local session_id="${2:-}"

  # (a) Bare hex — unnamed agent fast path; session_id ignored.
  if [[ "$agent_id" =~ ^[a-f0-9]{12,}$ ]]; then
    echo "$agent_id"
    return 0
  fi

  # (b) Named teammate: a<name>-<16hex>
  if [[ "$agent_id" =~ ^a(.+)-[a-f0-9]{16}$ ]]; then
    local name="${BASH_REMATCH[1]}"

    # Require session_id with at least 8 chars.
    # (.+) in the regex guarantees non-empty name — the -z "$name" branch is unreachable.
    if [[ ${#session_id} -lt 8 ]]; then
      echo ""
      return 0
    fi

    local short="${session_id:0:8}"
    cs_build_canonical_agent_id "$name" "$short"
    return 0
  fi

  # (c) Unrecognised shape — fail-closed.
  echo ""
  return 0
}

# ---------------------------------------------------------------------------
# session-shape.json writer/reader (C1 — spine root)
#
# Spec backlink: docs/plans/2026-07-02-ceremony-as-pipeline-v1-session-state-co.md § C1
# Schema: schemas/session-shape.schema.json
#
# Purpose: write and read .git/coordinator-sessions/<sid>/session-shape.json,
# the per-session observable that records pickup / memo-action / plan-claim
# write-moment facts so ceremonies can do a single file read instead of grep/infer.
#
# Locking: mkdir-based cross-process lock (NOT flock — unavailable on Windows
# Git Bash) that spans the ENTIRE read→merge→write critical section.
# Stale-lock reaping delegates to _cs_claim_holder_live (same liveness rule as
# cs_reap_stale_claims) — RAW-PID-LIVENESS prohibition applies here too.
#
# Merge: field-level deep-merge (actioned_memos array APPENDED, not replaced;
# pickup and plan keys SET). Honors _CS_FORCE_NO_JQ convention: falls back to
# Python (via resolve-python.sh), then best-effort awk.
# ---------------------------------------------------------------------------

# _cs_shape_lock_live <lock_dir>
#   Returns 0 (live) if the session-shape lock at <lock_dir> was claimed
#   recently enough that its holder is presumed still running the merge.
#   Uses the lock's own "claimed_at" timestamp (written at lock acquisition)
#   rather than _cs_claim_holder_live / _cs_session_live, because:
#     - The session may not have been cs_init'd (no meta.json / last_activity),
#       which causes _cs_session_live's recency gate to always return "stale" and
#       falsely reap the lock while the holder is actively in its critical section.
#     - A merge operation completes in well under 1s; 30s is a very generous bound.
#   Returns 1 (stale/dead) if lock is absent, has no timestamp, or timestamp is
#   older than _CS_SHAPE_LOCK_STALE_SEC seconds (default: 30).
#   Internal — called only from cs_session_shape_set.
_cs_shape_lock_live() {
  local lock_dir="${1:?}"
  [[ -d "$lock_dir" ]] || return 1
  local claimed_at_file="${lock_dir}/claimed_at"
  [[ -f "$claimed_at_file" ]] || return 1
  local claimed_iso claimed_epoch now_epoch elapsed
  claimed_iso=$(cat "$claimed_at_file" 2>/dev/null) || return 1
  [[ -z "$claimed_iso" ]] && return 1
  claimed_epoch=$(_cs_iso_to_epoch "$claimed_iso" 2>/dev/null) || return 1
  [[ -z "$claimed_epoch" || "$claimed_epoch" == "0" ]] && return 1
  now_epoch=$(_cs_now_epoch)
  elapsed=$(( now_epoch - claimed_epoch ))
  (( elapsed < 0 )) && elapsed=0
  local stale_sec="${_CS_SHAPE_LOCK_STALE_SEC:-30}"
  (( elapsed < stale_sec ))
}

# _cs_shape_merge_nojq <existing_json> <fragment_json> <sid>
#   No-jq field-level merge helper. Falls back to Python then awk.
#   Internal — do not call directly; called only from cs_session_shape_set.
_cs_shape_merge_nojq() {
  local existing="$1" fragment="$2" sid="$3"

  # Python path (resolve inline so callers don't have to pre-source)
  local _py_bin="${PYTHON_BIN:-}"
  if [[ -z "$_py_bin" ]]; then
    local _lib
    _lib="$(dirname "${BASH_SOURCE[0]}")/resolve-python.sh"
    if [[ ! -f "$_lib" ]]; then
      _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
      if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2; return 1 2>/dev/null || exit 1; fi
      _lib="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/lib/resolve-python.sh"
      # shellcheck source=/dev/null
      source "$(dirname "${BASH_SOURCE[0]}")/coordinator-trusted-root-guard.sh"
      coordinator_trusted_root_guard --mode=fail-loud --root="$_lib" --site="$0"
    fi
    # shellcheck source=/dev/null
    [[ -f "$_lib" ]] && { source "$_lib" 2>/dev/null || true; }
    _py_bin="${PYTHON_BIN:-}"
  fi
  local _py_args=()
  if [[ -n "${PYTHON_ARGS[*]:-}" ]]; then
    _py_args=("${PYTHON_ARGS[@]}")
  fi

  if [[ -n "$_py_bin" ]]; then
    CS_SHAPE_EXISTING="$existing" CS_SHAPE_FRAGMENT="$fragment" \
      "$_py_bin" "${_py_args[@]}" -c '
import json, os, sys
frag_str = os.environ.get("CS_SHAPE_FRAGMENT", "{}")
base_str = os.environ.get("CS_SHAPE_EXISTING", "{}")
try:
    frag = json.loads(frag_str)
except Exception:
    sys.stderr.write("cs_session_shape_set: invalid fragment JSON\n")
    sys.exit(1)
try:
    base = json.loads(base_str)
except Exception:
    base = {}
for key, val in frag.items():
    if key == "actioned_memos" and isinstance(val, list):
        existing_memos = base.get("actioned_memos") if isinstance(base.get("actioned_memos"), list) else []
        base["actioned_memos"] = existing_memos + val
    else:
        base[key] = val
sys.stdout.write(json.dumps(base))
' 2>/dev/null
    return $?
  fi

  # Pure awk fallback — handles the bounded set of single-key fragment types
  # (pickup object, plan object/null, actioned_memos single-element array).
  # Does NOT handle general JSON; sufficient for the known write-moment callers.
  #
  # Strategy: detect which top-level key the fragment sets, then use awk to
  # either replace that key's value (pickup, plan) or append to the array
  # (actioned_memos), operating on the existing flat JSON structure.
  #
  # Limitation: multi-key fragments are not supported on this path. All
  # known callers send single-key fragments, so this is correct in practice.
  local frag_key
  # Extract first key name from fragment (e.g. {"pickup":...} → "pickup")
  frag_key=$(printf '%s' "$fragment" | awk 'match($0, /"([^"]+)"[[:space:]]*:/, arr) { print arr[1]; exit }' 2>/dev/null) || frag_key=""

  if [[ -z "$frag_key" ]]; then
    # Cannot determine key — emit existing unchanged (safe no-op merge)
    printf '%s\n' "$existing"
    return 0
  fi

  # Extract the fragment value (everything after the first colon-space up to end)
  local frag_val
  frag_val=$(printf '%s' "$fragment" | awk -v key="\"${frag_key}\"" '
    BEGIN { found=0; depth=0; result="" }
    {
      line=$0
      if (!found) {
        idx=index(line, key ":")
        if (idx == 0) idx=index(line, key " :")
        if (idx > 0) {
          # Everything after the colon is the value (trim leading space, strip trailing })
          val=substr(line, idx+length(key)+1)
          gsub(/^[[:space:]]+/, "", val)
          # Remove trailing }
          sub(/[[:space:]]*}[[:space:]]*$/, "", val)
          result=val
          found=1
        }
      }
    }
    END { print result }
  ' 2>/dev/null) || frag_val=""

  if [[ "$frag_key" == "actioned_memos" ]]; then
    # Append to existing array. frag_val is "[{...}]" style.
    # Extract the item object from frag_val (strip outer brackets)
    local frag_item
    frag_item=$(printf '%s' "$frag_val" | awk '{
      s=$0; gsub(/^[[:space:]]*\[/, "", s); gsub(/\][[:space:]]*$/, "", s); print s
    }' 2>/dev/null)
    printf '%s\n' "$existing" | awk -v item="$frag_item" '
      {
        line=$0
        if (match(line, /"actioned_memos"[[:space:]]*:[[:space:]]*\[/)) {
          # Insert item before closing ]
          if (match(line, /\]/)) {
            pre=substr(line, 1, RSTART-1)
            post=substr(line, RSTART)
            # If array not empty, add comma
            if (match(pre, /[^[[:space:]]]/)) {
              print pre "," item post
            } else {
              print pre item post
            }
          } else {
            print line
          }
        } else {
          print line
        }
      }
    ' 2>/dev/null
    return 0
  fi

  # For pickup and plan: replace or insert the key.
  local replaced=0
  local result
  result=$(printf '%s\n' "$existing" | awk -v key="\"${frag_key}\"" -v val="$frag_val" '
    {
      line=$0
      kpos=index(line, key ":")
      if (kpos == 0) kpos=index(line, key " :")
      if (kpos > 0) {
        # Find where value ends (simplified: find the key offset and replace to end of object)
        pre=substr(line, 1, kpos-1)
        print pre key ": " val "}"
        replaced=1
      } else {
        # Check if this is the closing line (contains just })
        stripped=line
        gsub(/[[:space:]]/, "", stripped)
        if (stripped == "}") {
          print "," key ": " val "}"
        } else {
          print line
        }
      }
    }
  ' 2>/dev/null)
  printf '%s\n' "$result"
}

# cs_session_shape_set <sid> <json-merge-fragment>
#   Merge <json-merge-fragment> into .git/coordinator-sessions/<sid>/session-shape.json.
#
#   Field-level deep-merge contract:
#     - "actioned_memos": fragment's array items are APPENDED to existing array.
#     - All other top-level keys (pickup, plan, …): fragment value REPLACES.
#     - schema_version and session_id in the base are never overwritten by the fragment
#       (the base always wins for these identity fields — the fragment should not include them).
#
#   Atomicity (AC2):
#     (1) mkdir-based lock at <sdir>/session-shape.lock/ spans read→merge→write.
#         Not flock — unavailable on Windows Git Bash.
#     (2) Staging file via mktemp in the session dir; mv into place.
#     (3) Stale-lock reaping: bounded retry; reap via _cs_claim_holder_live liveness
#         check (mirrors cs_reap_stale_claims; RAW-PID-LIVENESS prohibition applies).
#
#   Idempotent / create-if-absent: initializes
#     {"schema_version":1,"session_id":"<sid>"} when the file is missing.
#
#   Honors _CS_FORCE_NO_JQ: falls back to Python then awk when jq unavailable.
#
#   Returns 0 on success, 1 on lock-acquisition failure.
#
#   Spec backlink: docs/plans/2026-07-02-ceremony-as-pipeline-v1-session-state-co.md § C1 (AC2)
cs_session_shape_set() {
  local sid="${1:?session_id required}"
  local fragment="${2:?json fragment required}"

  local sdir
  sdir=$(_cs_session_dir "$sid") || return 1
  # Session dir must exist (caller is responsible for cs_init; this defensively creates)
  [[ -d "$sdir" ]] || mkdir -p "$sdir" 2>/dev/null || return 1

  local shape_file="${sdir}/session-shape.json"
  local lock_dir="${sdir}/session-shape.lock"

  # ---------- Acquire mkdir-based lock (spans ENTIRE read→merge→write) ----------
  # Lock metadata includes "claimed_at" timestamp so _cs_shape_lock_live can
  # discriminate a live critical section from a crashed holder — see _cs_shape_lock_live
  # for why we use our own recency gate rather than _cs_claim_holder_live here.
  local _lock_acquired=0 attempts=0 max_attempts=20
  while (( attempts < max_attempts )); do
    if mkdir "$lock_dir" 2>/dev/null; then
      echo "$$"            > "${lock_dir}/pid"
      echo "$sid"          > "${lock_dir}/session_id"
      _cs_now_iso          > "${lock_dir}/claimed_at"
      _lock_acquired=1
      break
    fi
    # Lock held — check if holder is still in its critical section
    if ! _cs_shape_lock_live "$lock_dir" 2>/dev/null; then
      # Stale/crashed holder — reap and retry immediately (mirrors cs_reap_stale_claims)
      rm -rf "$lock_dir" 2>/dev/null || true
      if mkdir "$lock_dir" 2>/dev/null; then
        echo "$$"          > "${lock_dir}/pid"
        echo "$sid"        > "${lock_dir}/session_id"
        _cs_now_iso        > "${lock_dir}/claimed_at"
        _lock_acquired=1
        break
      fi
    fi
    attempts=$(( attempts + 1 ))
    sleep 0.1 2>/dev/null || true
  done

  if [[ "$_lock_acquired" != "1" ]]; then
    echo "cs_session_shape_set: failed to acquire lock for session ${sid}" >&2
    return 1
  fi

  # ---------- Read existing or initialize ----------
  local existing=""
  if [[ -f "$shape_file" ]]; then
    existing=$(cat "$shape_file" 2>/dev/null) || existing=""
  fi
  if [[ -z "$existing" ]]; then
    # Create-if-absent: escape sid for safe JSON embedding
    local sid_escaped="${sid//\\/\\\\}"
    sid_escaped="${sid_escaped//\"/\\\"}"
    existing="{\"schema_version\":1,\"session_id\":\"${sid_escaped}\"}"
  fi

  # ---------- Merge fragment (field-level deep-merge) ----------
  local merged=""
  if [[ -z "${_CS_FORCE_NO_JQ:-}" ]] && command -v jq >/dev/null 2>&1; then
    # jq path: use * operator for deep-merge, but override actioned_memos to append
    merged=$(printf '%s\n%s\n' "$existing" "$fragment" | jq -s '
      .[0] as $base | .[1] as $frag |
      ($base + $frag) |
      if ($base.actioned_memos != null and $frag.actioned_memos != null)
      then .actioned_memos = ($base.actioned_memos + $frag.actioned_memos)
      else . end
    ' 2>/dev/null) || { rm -rf "$lock_dir" 2>/dev/null; return 1; }
  else
    # No-jq fallback: Python then awk (see _cs_shape_merge_nojq)
    merged=$(_cs_shape_merge_nojq "$existing" "$fragment" "$sid") \
      || { rm -rf "$lock_dir" 2>/dev/null; return 1; }
  fi

  if [[ -z "$merged" ]]; then
    rm -rf "$lock_dir" 2>/dev/null
    return 1
  fi

  # ---------- Atomic write: mktemp in session dir, then mv ----------
  local tmp
  tmp=$(mktemp "${shape_file}.XXXXXX" 2>/dev/null) || tmp=$(mktemp) || {
    rm -rf "$lock_dir" 2>/dev/null; return 1
  }
  printf '%s\n' "$merged" > "$tmp" 2>/dev/null || {
    rm -f "$tmp" 2>/dev/null
    rm -rf "$lock_dir" 2>/dev/null
    return 1
  }
  mv "$tmp" "$shape_file" 2>/dev/null || {
    rm -f "$tmp" 2>/dev/null
    rm -rf "$lock_dir" 2>/dev/null
    return 1
  }

  # Release lock
  rm -rf "$lock_dir" 2>/dev/null || true
  return 0
}

# cs_session_shape_read <sid>
#   Emit the persisted session-shape.json as raw JSON (stdout).
#   If the file is absent, emits the default skeleton:
#     {"schema_version":1,"session_id":"<sid>"}
#   Magnitude fields (commits_since_start, files_touched) are NOT derived here —
#   that is C5's responsibility (cs_session_shape_magnitude / the C6 CLI).
#
#   Returns 0 always (fail-open: if the session dir is unresolvable, emits skeleton).
#
#   Spec backlink: docs/plans/2026-07-02-ceremony-as-pipeline-v1-session-state-co.md § C1
cs_session_shape_read() {
  local sid="${1:?session_id required}"

  local sdir
  sdir=$(_cs_session_dir "$sid" 2>/dev/null) || {
    local sid_escaped="${sid//\\/\\\\}"; sid_escaped="${sid_escaped//\"/\\\"}"
    printf '{"schema_version":1,"session_id":"%s"}\n' "$sid_escaped"
    return 0
  }

  local shape_file="${sdir}/session-shape.json"
  if [[ -f "$shape_file" ]]; then
    cat "$shape_file"
  else
    local sid_escaped="${sid//\\/\\\\}"; sid_escaped="${sid_escaped//\"/\\\"}"
    printf '{"schema_version":1,"session_id":"%s"}\n' "$sid_escaped"
  fi
}

# cs_session_shape_magnitude <sid>
#   Derive and emit the magnitude fields for the session as a JSON object on stdout.
#   Fields are computed on-demand from session-dir artefacts — this function NEVER
#   writes to session-shape.json or calls cs_session_shape_set.
#
#   commits_since_start:
#     Read head_at_start from the session dir; count commits reachable from HEAD
#     but not from head_at_start via `git rev-list --count <head_at_start>..HEAD`.
#     Guard: if head_at_start is absent, empty, "unknown", or not a valid commit
#     object → emits 0.
#
#   files_touched:
#     Count DISTINCT paths in <sdir>/touched.txt (deduplicated with sort -u).
#     Guard: absent touched.txt → 0.
#
#   Output shape (always, even on guard fallbacks):
#     {"commits_since_start":<int>,"files_touched":<int>}
#
#   Honors _CS_FORCE_NO_JQ convention: vacuously — output is built with printf,
#   no jq is used.
#
#   Returns 0 always (fail-open: individual guard zeroes ensure a valid JSON object).
#
#   Spec backlink: docs/plans/2026-07-02-ceremony-as-pipeline-v1-session-state-co.md § C5
cs_session_shape_magnitude() {
  local sid="${1:?session_id required}"

  local sdir
  sdir=$(_cs_session_dir "$sid" 2>/dev/null) || {
    printf '{"commits_since_start":0,"files_touched":0}\n'
    return 0
  }

  # ---- commits_since_start ----
  local commits=0
  local head_file="${sdir}/head_at_start"
  if [[ -f "$head_file" ]]; then
    local head_sha
    head_sha=$(cat "$head_file" 2>/dev/null)
    # Trim whitespace (BSD cat may trail newline; Windows may add \r)
    head_sha="${head_sha//[$'\r\n ']/}"
    if [[ -n "$head_sha" && "$head_sha" != "unknown" ]]; then
      # Verify it resolves to a commit object before handing it to rev-list.
      # git cat-file -e exits 0 if the object exists; ^{commit} peels to commit.
      if git cat-file -e "${head_sha}^{commit}" 2>/dev/null; then
        local n
        n=$(git rev-list --count "${head_sha}..HEAD" 2>/dev/null) || n=0
        [[ "$n" =~ ^[0-9]+$ ]] && commits="$n" || commits=0
      fi
    fi
  fi

  # ---- files_touched ----
  local touched=0
  local touched_file="${sdir}/touched.txt"
  if [[ -f "$touched_file" ]]; then
    local n
    # sort -u deduplicates; wc -l counts lines; tr strips BSD leading spaces.
    n=$(sort -u "$touched_file" 2>/dev/null | wc -l | tr -d '[:space:]') || n=0
    [[ "$n" =~ ^[0-9]+$ ]] && touched="$n" || touched=0
  fi

  printf '{"commits_since_start":%d,"files_touched":%d}\n' "$commits" "$touched"
}

# ---------------------------------------------------------------------------
# Review-claim lifecycle helpers RETIRED
# Spec backlink: cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md
#
# cs_write_review_claim and cs_reap_stale_review_claims were part of Mode B
# (agent_id-keyed marker file confinement).  Mode B is retired; confinement is
# now Mode A only (type-keyed directory prefix).  The state/review-claims/
# directory and the session-init reaper call are inert on repos that have not
# yet been pruned; the command-v guard in session-init.sh silently skips the
# call when this function is absent.
# ---------------------------------------------------------------------------
