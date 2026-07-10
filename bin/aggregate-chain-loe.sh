#!/usr/bin/env bash
# aggregate-chain-loe.sh — Chain-walk aggregator: traverse a handoff predecessor chain,
# parse all Session Ledger blocks encountered, and emit summed LoE metrics.
#
# Purpose: given the terminal handoff of a multi-session chain (the one consumed by
# the chain-terminal /workstream-complete), walks the predecessor: chain backward to root,
# collects every Session Ledger block from every handoff visited, deduplicates by
# session_id, and emits summed (agent_dispatches, opus_dispatches, em_tokens) +
# unioned commits + recomputed t-shirt. Consumed by /workstream-complete Step 2.6 on the
# chain-terminal path (Chunk 3 wiring).
#
# Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C2
# Review: code-reviewer (F9) — updated from stale 2026-05-19 plan reference (now archived/absent).
#
# Concurrency posture: read-only against handoff files in state/handoffs/ and
#   state/handoffs/archive/**/. Handoff files are append-only (new Session Ledger
#   blocks are appended, never overwritten). Safe under concurrent reads; no locking
#   required. Chain-walk is deterministic once the predecessor links are stable.
# Idempotency posture: deterministic given a fixed terminal-handoff and fixed handoff
#   content; same input => same output every invocation. No side effects; nothing written.
# Resume strategy: stateless — re-running with the same --terminal-handoff always
#   produces identical output as long as handoff files haven't changed. No checkpoint
#   needed; re-run is free.

set -uo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
    echo "ERROR: aggregate-chain-loe.sh requires bash 4.0 or later (associative arrays)." >&2
    echo "       Detected: bash ${BASH_VERSION:-unknown}" >&2
    echo "  macOS ships bash 3.2 as /bin/bash. Install a current bash and put it first on PATH:" >&2
    echo "      brew install bash" >&2
    echo '      export PATH="$(brew --prefix)/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc' >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

TERMINAL_HANDOFF=""
FORMAT="yaml-frontmatter"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source state-root seam — C4/stop-the-rot: per-repo state refs route through coordinator_state_root.
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4
# shellcheck source=../lib/coordinator-state-root.sh
source "${COORDINATOR_DIR}/lib/coordinator-state-root.sh"

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --terminal-handoff)
      TERMINAL_HANDOFF="$2"; shift 2 ;;
    --format)
      FORMAT="$2"; shift 2 ;;
    -h|--help)
      cat <<'EOF'
Usage: aggregate-chain-loe.sh --terminal-handoff <path> [OPTIONS]

Options:
  --terminal-handoff <path>        Path to the handoff being consumed by the
                                   chain-terminal session (the immediate predecessor).
                                   Absolute or relative to cwd. Required.
  --format <yaml-frontmatter|json> Output format (default: yaml-frontmatter)
  -h, --help                       Show this help

Output yaml-frontmatter example:
  chain_loe:
    sessions: 6
    agent_dispatches: 87
    opus_dispatches: 12
    em_tokens: 1847000
    tshirt: "XL"
  commits:
    - "abc1234"
  chain_sessions_with_ledger: "6 of 6"
  chain_span_days: 14
  chain_starting_handoff: "state/handoffs/2026-05-05_141200_chain-root.md"

Output json example:
  {"chain_loe": {"sessions": 6, "agent_dispatches": 87, ...}, "commits": ["abc1234"], ...}
(Review: code-reviewer F5 — updated from stale loe:/chain_sessions: shape to match actual chain_loe: output)

Termination signals (recorded as chain_walk_terminated_early):
  missing-link   — one or more edge targets could not be resolved; walk continues on other edges
  lineage-cycle  — a genuine back-edge (authoring error) was detected; benign diamonds are NOT flagged

Exit codes:
  0 — success (possibly with partial aggregate if walk terminated early)
  1 — fatal argument or environment error
EOF
      exit 0 ;;
    *)
      echo "Error: unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$TERMINAL_HANDOFF" ]]; then
  echo "Error: --terminal-handoff is required" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve git root and handoff search roots
# ---------------------------------------------------------------------------

GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "Error: not inside a git repo" >&2; exit 1
}

# On Git Bash (Windows), git returns 'C:/...' style paths; normalise to '/c/...' POSIX form
# so subsequent bash string operations are consistent with pwd-computed paths.
# No-op on macOS/Linux where cygpath is absent.
if command -v cygpath >/dev/null 2>&1; then
  GIT_ROOT=$(cygpath -u "$GIT_ROOT" 2>/dev/null || echo "$GIT_ROOT")
fi

# Resolve state root through the seam (C4: meta-repo → example-orchestration-hub/state; sibling → $GIT_ROOT/state).
STATE_ROOT="$(coordinator_state_root)"
HANDOFFS_DIR="${STATE_ROOT}/handoffs"
ARCHIVE_DIR="${GIT_ROOT}/archive/handoffs"  # Review: code-reviewer (F6) — was ${HANDOFFS_DIR}/archive (state/handoffs/archive, non-existent); real archive is archive/handoffs/

# ---------------------------------------------------------------------------
# Resolve a predecessor path to an absolute file path.
# Searches: 1) as-is (absolute or relative to cwd), 2) under state/handoffs/,
#           3) recursively under state/handoffs/archive/**/.
# Returns the resolved absolute path via stdout, or empty string if not found.
# ---------------------------------------------------------------------------

resolve_handoff_path() {
  local raw="$1"

  # Trim whitespace
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"

  [[ -z "$raw" ]] && return 0

  # 1. As-is (absolute path or relative to cwd)
  if [[ -f "$raw" ]]; then
    # shellcheck disable=SC2155
    local abs; abs="$(cd "$(dirname "$raw")" && pwd)/$(basename "$raw")"
    echo "$abs"
    return 0
  fi

  # 2. Relative to git root
  local from_root="${GIT_ROOT}/${raw}"
  if [[ -f "$from_root" ]]; then
    echo "$from_root"
    return 0
  fi

  # 3. Basename under state/handoffs/
  local basename; basename="$(basename "$raw")"
  local in_handoffs="${HANDOFFS_DIR}/${basename}"
  if [[ -f "$in_handoffs" ]]; then
    echo "$in_handoffs"
    return 0
  fi

  # 4. Recursive search under state/handoffs/archive/**/
  if [[ -d "$ARCHIVE_DIR" ]]; then
    local found
    found=$(find "$ARCHIVE_DIR" -name "$basename" -type f 2>/dev/null | head -1)
    if [[ -n "$found" ]]; then
      echo "$found"
      return 0
    fi
    # Also try full path suffix match (in case predecessor field is a relative path
    # like state/handoffs/archive/2026-05/foo.md).
    local suffix_match
    suffix_match=$(find "$ARCHIVE_DIR" -name "*.md" -type f 2>/dev/null | while read -r f; do
      if [[ "$f" == *"$raw" ]] || [[ "$f" == *"$(basename "$raw")" ]]; then
        echo "$f"
        break
      fi
    done | head -1)
    if [[ -n "$suffix_match" ]]; then
      echo "$suffix_match"
      return 0
    fi
  fi

  # Not found
  echo ""
}

# ---------------------------------------------------------------------------
# Extract a single frontmatter field value from a handoff file.
# Handles: "field: value", "field: null", "field: none".
# Outputs the raw value (trimmed). Empty string if absent.
# ---------------------------------------------------------------------------

extract_frontmatter_field() {
  local file="$1"
  local field="$2"

  # Read between the first pair of --- delimiters (YAML frontmatter block).
  # Use awk: after first ---, collect lines until next ---.
  #
  # BSD awk (macOS /usr/bin/awk) does NOT support the 3-argument form of match()
  # (that is a gawk extension). Use 2-arg match() + RSTART/RLENGTH to extract
  # the value portion instead of relying on capture groups. Cross-platform fix.
  awk -v field="$field" '
    /^---/ { if (in_fm) exit; in_fm=1; next }
    in_fm && /^[[:space:]]*[^#]/ {
      if (match($0, "^[[:space:]]*" field "[[:space:]]*:[[:space:]]*")) {
        val = substr($0, RSTART + RLENGTH)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
        # Strip surrounding double-quotes (no 3-arg match; use explicit substr check)
        if (length(val) >= 2 && substr(val, 1, 1) == "\"" && substr(val, length(val), 1) == "\"") {
          val = substr(val, 2, length(val) - 2)
        }
        print val
        exit
      }
    }
  ' "$file" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Parse ALL ## Session Ledger blocks from a handoff file body.
# Outputs one JSON-like record per block to stdout (newline-delimited):
#   session_id=<val> agent_dispatches=<N> opus_dispatches=<N> em_tokens=<val> commits=<val> created=<val>
# Each block is separated by a blank line or the next "## Session Ledger" heading.
# ---------------------------------------------------------------------------

parse_session_ledgers() {
  local file="$1"

  # Use awk to find all "## Session Ledger" sections and extract their table rows.
  # Table format:
  #   | Field          | Value     |
  #   |----------------|-----------|
  #   | agent_dispatches | 26      |
  #   ...
  awk '
    BEGIN {
      in_ledger = 0
      agent_dispatches = ""
      opus_dispatches  = ""
      em_tokens        = ""
      commits          = ""
      session_id       = ""
      created          = ""
    }

    function flush_record() {
      if (session_id != "") {
        printf "session_id=%s agent_dispatches=%s opus_dispatches=%s em_tokens=%s commits=%s created=%s\n",
          session_id,
          (agent_dispatches != "" ? agent_dispatches : "0"),
          (opus_dispatches  != "" ? opus_dispatches  : "0"),
          (em_tokens        != "" ? em_tokens        : "null"),
          (commits          != "" ? commits          : ""),
          (created          != "" ? created          : "")
      }
    }

    /^## Session Ledger/ {
      # Flush any prior record before starting a new one
      flush_record()
      in_ledger = 1
      agent_dispatches = ""
      opus_dispatches  = ""
      em_tokens        = ""
      commits          = ""
      session_id       = ""
      created          = ""
      next
    }

    # Any new ## heading (other than Session Ledger itself) ends the ledger block
    /^## / && in_ledger && !/^## Session Ledger/ {
      flush_record()
      in_ledger = 0
      agent_dispatches = ""
      opus_dispatches  = ""
      em_tokens        = ""
      commits          = ""
      session_id       = ""
      created          = ""
      next
    }

    in_ledger && /^\|/ {
      # Parse markdown table row: | Field | Value |
      # Strip leading/trailing pipe and spaces
      line = $0
      gsub(/^\|[[:space:]]*/, "", line)
      gsub(/[[:space:]]*\|[[:space:]]*$/, "", line)
      # Split on " | " — the cell separator
      n = split(line, cells, /[[:space:]]*\|[[:space:]]*/)
      if (n < 2) next
      field = cells[1]
      value = cells[2]
      # Trim field and value
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", field)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      # Skip header/separator rows
      if (field == "Field" || field ~ /^-+$/) next

      if (field == "agent_dispatches") agent_dispatches = value
      else if (field == "opus_dispatches")  opus_dispatches  = value
      else if (field == "em_tokens")        em_tokens        = value
      else if (field == "commits")          commits          = value
      else if (field == "session_id")       session_id       = value
      else if (field == "created")          created          = value
    }

    END {
      if (in_ledger) flush_record()
    }
  ' "$file" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# T-shirt computation — same threshold table as coordinator-session-loe.sh.
# Inline copy to avoid requiring a YAML parser; must match config/loe-thresholds.yaml.
# Format: "tier ad_threshold od_threshold tok_threshold" ordered HIGHEST to LOWEST.
# ---------------------------------------------------------------------------

TSHIRT_TABLE=(
  "XL 50 6 1000000"
  "L 30 3 600000"
  "M 15 2 300000"
  "S 5 1 150000"
  "XS 0 0 50000"
)
# Must match config/loe-thresholds.yaml and coordinator-session-loe.sh.
# Dogfood-fix 2026-05-19 propagation: S.od 0->1, M.od 1->2 — see lessons.md
# § "Any-criterion threshold tables with >=0 floors collapse tier reachability".
# Code-reviewer F1: prior shape carried unfixed S.od=0 → every chain qualified
# for S regardless of opus count; XS unreachable for chain-aggregate sizing.

compute_tshirt() {
  local ad="$1"   # agent_dispatches
  local od="$2"   # opus_dispatches
  local tok="$3"  # em_tokens (empty = unknown)

  local tshirt="XS"
  for entry in "${TSHIRT_TABLE[@]}"; do
    local tier ad_thresh od_thresh tok_thresh
    read -r tier ad_thresh od_thresh tok_thresh <<< "$entry"

    local qualifies=false
    (( ad >= ad_thresh ))  && qualifies=true
    (( od >= od_thresh ))  && qualifies=true
    if [[ -n "$tok" ]] && [[ "$tok" =~ ^[0-9]+$ ]] && (( tok >= tok_thresh )); then
      qualifies=true
    fi

    if [[ "$qualifies" == true ]]; then
      tshirt="$tier"
      break
    fi
  done

  echo "$tshirt"
}

# ---------------------------------------------------------------------------
# Resolve the starting file path
# ---------------------------------------------------------------------------

TERMINAL_ABS=$(resolve_handoff_path "$TERMINAL_HANDOFF")
if [[ -z "$TERMINAL_ABS" ]]; then
  echo "Error: terminal handoff not found: ${TERMINAL_HANDOFF}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Chain walk — via shared DAG traversal primitive (C0: walk-handoff-dag.js)
# ---------------------------------------------------------------------------
# The primitive handles path-level diamond dedup (replacing the former
# VISITED_PATHS bash associative array), DFS gray/black cycle detection
# (terminatedEarly='lineage-cycle' on a genuine back-edge; benign diamond
# convergence is a continue, NOT abort), and missing-link skip-and-continue
# (terminatedEarly='missing-link' recorded but frontier continues on other edges).
#
# forked_from is NOT in the edge-kind set: it is lineage/render-only and
# excluded from LoE aggregation per DR-014 effort-isolation.
#
# Spec: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C2

CHAIN_ORDER=()             # ordered list of resolved paths (terminal → root)
WALK_TERMINATED_EARLY=""   # '' | 'lineage-cycle' | 'missing-link'

WALK_PRIMITIVE="${SCRIPT_DIR}/lib/walk-handoff-dag.js"
if ! command -v node >/dev/null 2>&1; then
  echo "Error: 'node' not found on PATH — walk-handoff-dag.js requires Node.js" >&2
  exit 1
fi

# On Git Bash (Windows), Node.js requires Windows-native paths (C:\...) rather than
# Git Bash POSIX paths (/c/..., /tmp/...). cygpath -w converts for the --start arg;
# cygpath -u converts returned Windows paths back to POSIX for downstream bash operations.
# Both are no-ops on macOS/Linux where cygpath is absent.
_TERM_FOR_NODE="$TERMINAL_ABS"
if command -v cygpath >/dev/null 2>&1; then
  _TERM_FOR_NODE=$(cygpath -w "$TERMINAL_ABS" 2>/dev/null || echo "$TERMINAL_ABS")
fi

while IFS= read -r _dag_line; do
  case "$_dag_line" in
    terminatedEarly=*)
      WALK_TERMINATED_EARLY="${_dag_line#terminatedEarly=}"
      ;;
    "")
      # Skip blank lines (primitive emits none, but guard for robustness)
      ;;
    *)
      # Convert Node-returned path back to POSIX so bash string ops (GIT_ROOT prefix
      # strip, file reads) work identically on Windows and macOS/Linux.
      if command -v cygpath >/dev/null 2>&1; then
        CHAIN_ORDER+=("$(cygpath -u "$_dag_line" 2>/dev/null || echo "$_dag_line")")
      else
        CHAIN_ORDER+=("$_dag_line")
      fi
      ;;
  esac
done < <(node "$WALK_PRIMITIVE" \
  --start "$_TERM_FOR_NODE" \
  --edge-kinds "predecessor,additional_predecessors" \
  --format paths)
# Review: code-reviewer (F3) — dropped 2>/dev/null so node crash messages reach the caller.
# set -e does not fire for process substitution; the guard below catches the crash case.

if [[ "${#CHAIN_ORDER[@]}" -eq 0 ]]; then
  echo "Error: walk-handoff-dag returned empty output (node crash or missing module)" >&2
  exit 1
fi

CHAIN_TOTAL="${#CHAIN_ORDER[@]}"

# ---------------------------------------------------------------------------
# Aggregate Session Ledger blocks across all handoffs in the chain
# ---------------------------------------------------------------------------

TOTAL_AD=0
TOTAL_OD=0
TOTAL_TOK=""
COMMITS_SET=()
declare -A SEEN_SESSION_IDS_MAP=()  # Review: code-reviewer (F10) — O(1) assoc-array replaces O(N²) linear scan; bash-4 guard at line 27 ensures declare -A is available

HANDOFFS_WITH_LEDGER=0

# ---------------------------------------------------------------------------
# Helper: extract a single named field from a parse_session_ledgers record line.
# Record format (emitted by awk flush_record):
#   session_id=<val> agent_dispatches=<N> opus_dispatches=<N> em_tokens=<val> commits=<val> created=<val>
# Values may contain spaces (e.g. commits="sha1, sha2") so word-splitting on the
# record is brittle. This helper finds "key=..." and strips at the next known-key
# boundary, preserving internal spaces. BS-2026-05-19-006 fix.
# ---------------------------------------------------------------------------

_extract_loe_field() {
  local rec="$1" k="$2"
  # Strip the prefix up to (and including) "k="
  local after="${rec#*"${k}="}"
  # If the key was not present, after == rec (no substitution occurred)
  [[ "$after" == "$rec" ]] && { echo ""; return 0; }
  # Trim at next known-key boundary: remove everything from first " knownkey=" onward
  # Invariant: values must not contain a space followed by another known field-name=substring.
  # All six known field values (short SHAs, integers, ISO dates, session IDs, comma-joined commits)
  # satisfy this. Documents the implicit assumption for future field additions.
  echo "$after" | sed -E 's/ (session_id|agent_dispatches|opus_dispatches|em_tokens|commits|created)=.*$//'
}

for hpath in "${CHAIN_ORDER[@]}"; do
  # Parse all Session Ledger blocks from this handoff
  local_ledger_count=0

  while IFS= read -r record; do
    [[ -z "$record" ]] && continue
    # $(( )) expansion is safe under set -uo pipefail (only standalone (( )) exits non-zero when result is 0).
    # || true is forward-defensive and distinguishes intent from the pattern-match guards below.
    local_ledger_count=$(( local_ledger_count + 1 )) || true

    # Parse each named field from the record without word-splitting.
    # BS-2026-05-19-006: for kv in $record was brittle to spaces in values.
    local_sid=""
    local_ad=0
    local_od=0
    local_tok=""
    local_commits=""

    local_sid="$(_extract_loe_field "$record" "session_id")"
    local_ad="$(_extract_loe_field  "$record" "agent_dispatches")"
    local_od="$(_extract_loe_field  "$record" "opus_dispatches")"
    _tok_raw="$(_extract_loe_field  "$record" "em_tokens")"
    [[ "$_tok_raw" != "null" && -n "$_tok_raw" ]] && local_tok="$_tok_raw"
    local_commits="$(_extract_loe_field "$record" "commits")"

    # Sanitize numeric fields — default to 0 if non-numeric
    [[ "$local_ad" =~ ^[0-9]+$ ]] || local_ad=0
    [[ "$local_od" =~ ^[0-9]+$ ]] || local_od=0

    # Deduplication: skip if this session_id was already seen (O(1) assoc-array lookup)
    if [[ -n "$local_sid" ]]; then
      if [[ "${SEEN_SESSION_IDS_MAP["$local_sid"]+isset}" == "isset" ]]; then
        continue
      fi
      SEEN_SESSION_IDS_MAP["$local_sid"]=1
    fi

    # Accumulate
    [[ "$local_ad" =~ ^[0-9]+$ ]] && TOTAL_AD=$(( TOTAL_AD + local_ad )) || true
    [[ "$local_od" =~ ^[0-9]+$ ]] && TOTAL_OD=$(( TOTAL_OD + local_od )) || true
    if [[ -n "$local_tok" && "$local_tok" =~ ^[0-9,_]+$ ]]; then
      # Strip comma/underscore separators that may appear in human-written values
      clean_tok="${local_tok//,/}"
      clean_tok="${clean_tok//_/}"
      if [[ -z "$TOTAL_TOK" ]]; then
        TOTAL_TOK="$clean_tok"
      else
        [[ "$TOTAL_TOK" =~ ^[0-9]+$ ]] || TOTAL_TOK=0
        [[ "$clean_tok"  =~ ^[0-9]+$ ]] || clean_tok=0
        TOTAL_TOK=$(( TOTAL_TOK + clean_tok )) || true
      fi
    fi

    # Union commits (comma-separated list in value)
    if [[ -n "$local_commits" ]]; then
      IFS=',' read -ra clist <<< "$local_commits"
      for c in "${clist[@]}"; do
        c="${c// /}"
        [[ -z "$c" ]] && continue
        already_have=false
        for have in "${COMMITS_SET[@]}"; do
          [[ "$have" == "$c" ]] && { already_have=true; break; }
        done
        [[ "$already_have" == false ]] && COMMITS_SET+=("$c")
      done
    fi

  done < <(parse_session_ledgers "$hpath")

  [[ "$local_ledger_count" -gt 0 ]] && HANDOFFS_WITH_LEDGER=$(( HANDOFFS_WITH_LEDGER + 1 )) || true
done

CHAIN_SESSIONS_WITH_LEDGER="${HANDOFFS_WITH_LEDGER} of ${CHAIN_TOTAL}"

# ---------------------------------------------------------------------------
# Compute chain_span_days: difference in 'created' dates from first and last
# handoff in chain that we can read. Degrade gracefully to null.
# ---------------------------------------------------------------------------

CHAIN_SPAN_DAYS=""

if [[ "${#CHAIN_ORDER[@]}" -ge 1 ]]; then
  FIRST_HANDOFF="${CHAIN_ORDER[${#CHAIN_ORDER[@]}-1]}"  # chain root (last element = walked deepest)
  LAST_HANDOFF="${CHAIN_ORDER[0]}"                        # terminal (first element)

  first_created=$(extract_frontmatter_field "$FIRST_HANDOFF" "created")
  last_created=$(extract_frontmatter_field  "$LAST_HANDOFF"  "created")

  # Compute difference in days if both are parseable YYYY-MM-DD or YYYY-MM-DDThh... dates
  if [[ -n "$first_created" && -n "$last_created" ]]; then
    # Normalize to YYYY-MM-DD (strip time component if present)
    first_date="${first_created:0:10}"
    last_date="${last_created:0:10}"

    # Convert dates to epoch seconds using date command.
    # GNU date uses -d; BSD/macOS date uses -j -f; degrade to empty if neither works.
    first_epoch=$(date -d "$first_date" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$first_date" +%s 2>/dev/null || echo "")
    last_epoch=$(date -d "$last_date" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$last_date" +%s 2>/dev/null || echo "")

    if [[ -n "$first_epoch" && -n "$last_epoch" ]] &&
       [[ "$first_epoch" =~ ^-?[0-9]+$ ]] && [[ "$last_epoch" =~ ^-?[0-9]+$ ]]; then
      diff_secs=$(( last_epoch - first_epoch )) || true
      # Allow negative (last < first) to be reported as 0 (same-day chain)
      [[ $diff_secs -lt 0 ]] && diff_secs=0
      [[ "$diff_secs" =~ ^[0-9]+$ ]] && CHAIN_SPAN_DAYS=$(( diff_secs / 86400 )) || true
    fi
  fi
fi

# Relative path of chain starting handoff for display
CHAIN_STARTING_HANDOFF=""
if [[ "${#CHAIN_ORDER[@]}" -ge 1 ]]; then
  root_abs="${CHAIN_ORDER[${#CHAIN_ORDER[@]}-1]}"
  # Make relative to git root if possible
  if [[ "$root_abs" == "$GIT_ROOT"* ]]; then
    CHAIN_STARTING_HANDOFF="${root_abs#"$GIT_ROOT/"}"
  else
    CHAIN_STARTING_HANDOFF="$root_abs"
  fi
fi

# ---------------------------------------------------------------------------
# Compute t-shirt from summed totals
# ---------------------------------------------------------------------------

TSHIRT=$(compute_tshirt "$TOTAL_AD" "$TOTAL_OD" "$TOTAL_TOK")

# ---------------------------------------------------------------------------
# Format em_tokens for output
# ---------------------------------------------------------------------------

if [[ -n "$TOTAL_TOK" ]]; then
  EM_TOKENS_OUT="$TOTAL_TOK"
else
  EM_TOKENS_OUT="null"
fi

# Format commits as comma-joined string or null
if [[ "${#COMMITS_SET[@]}" -gt 0 ]]; then
  COMMITS_OUT=$(IFS=', '; echo "${COMMITS_SET[*]}")
else
  COMMITS_OUT=""
fi

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

case "$FORMAT" in
  yaml-frontmatter)
    # Emit chain-aggregate values as `chain_loe:` nested block (NOT `loe:`)
    # so workstream-complete can keep the terminal session's own per-session `loe:`
    # alongside the chain-aggregate. Wiki + workweek-complete reference
    # chain_loe.tshirt as the XL-surfacing field. Code-reviewer F2/F3/F7 fix.
    cat <<EOF
chain_loe:
  sessions: ${CHAIN_TOTAL}
  agent_dispatches: ${TOTAL_AD}
  opus_dispatches: ${TOTAL_OD}
  em_tokens: ${EM_TOKENS_OUT}
  tshirt: "${TSHIRT}"
EOF
    if [[ -n "$COMMITS_OUT" ]]; then
      # commits is a top-level schema field (list-of-string), not nested under loe/chain_loe.
      # Emit at indent-0 as a YAML list — one item per line.
      printf 'commits:\n'
      IFS=',' read -ra _commits_arr <<< "$COMMITS_OUT"
      for _c in "${_commits_arr[@]}"; do
        _c="${_c## }"; _c="${_c%% }"
        [[ -n "$_c" ]] && printf '  - "%s"\n' "$_c"
      done
    fi
    printf 'chain_sessions_with_ledger: "%s"\n' "$CHAIN_SESSIONS_WITH_LEDGER"
    if [[ -n "$CHAIN_SPAN_DAYS" ]]; then
      printf 'chain_span_days: %d\n' "$CHAIN_SPAN_DAYS"
    fi
    if [[ -n "$CHAIN_STARTING_HANDOFF" ]]; then
      printf 'chain_starting_handoff: "%s"\n' "$CHAIN_STARTING_HANDOFF"
    fi
    if [[ -n "$WALK_TERMINATED_EARLY" ]]; then
      printf 'chain_walk_terminated_early: "%s"\n' "$WALK_TERMINATED_EARLY"
    fi
    ;;

  json)
    # Emit em_tokens as JSON number or null
    if [[ "$EM_TOKENS_OUT" == "null" ]]; then
      tok_json="null"
    else
      tok_json="$EM_TOKENS_OUT"
    fi

    if [[ -n "$COMMITS_OUT" ]]; then
      # Review: code-reviewer (F4) — emit JSON array (not quoted string) so consumers can iterate
      commits_json=$(printf '%s\n' "$COMMITS_OUT" | \
        awk '{n=split($0,a,", "); printf "["; for(i=1;i<=n;i++){printf "\"%s\"",a[i]; if(i<n)printf ","}; printf "]"}')
    else
      commits_json="null"
    fi

    if [[ -n "$CHAIN_SPAN_DAYS" ]]; then
      span_json="$CHAIN_SPAN_DAYS"
    else
      span_json="null"
    fi

    if [[ -n "$WALK_TERMINATED_EARLY" ]]; then
      terminated_json=", \"chain_walk_terminated_early\": \"${WALK_TERMINATED_EARLY}\""
    else
      terminated_json=""
    fi

    printf '{'
    # Aggregate values live under "chain_loe" to keep them disjoint from the
    # terminal session's per-session "loe" block. Code-reviewer F2 fix.
    printf '"chain_loe": {"sessions": %d, "agent_dispatches": %d, "opus_dispatches": %d, "em_tokens": %s, "tshirt": "%s"}, ' \
      "$CHAIN_TOTAL" "$TOTAL_AD" "$TOTAL_OD" "$tok_json" "$TSHIRT"
    if [[ -n "$COMMITS_OUT" ]]; then
      printf '"commits": %s, ' "$commits_json"
    fi
    printf '"chain_sessions_with_ledger": "%s", "chain_span_days": %s' \
      "$CHAIN_SESSIONS_WITH_LEDGER" "$span_json"
    if [[ -n "$CHAIN_STARTING_HANDOFF" ]]; then
      printf ', "chain_starting_handoff": "%s"' "$CHAIN_STARTING_HANDOFF"
    fi
    printf '%s' "$terminated_json"
    printf '}\n'
    ;;

  *)
    echo "Error: unknown format '${FORMAT}'. Use: yaml-frontmatter | json" >&2
    exit 1
    ;;
esac
