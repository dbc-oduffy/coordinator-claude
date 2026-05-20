#!/bin/bash
# aggregate-chain-loe.sh — Chain-walk aggregator: traverse a handoff predecessor chain,
# parse all Session Ledger blocks encountered, and emit summed LoE metrics.
#
# Purpose: given the terminal handoff of a multi-session chain (the one consumed by
# the chain-terminal /session-end), walks the predecessor: chain backward to root,
# collects every Session Ledger block from every handoff visited, deduplicates by
# session_id, and emits summed (agent_dispatches, opus_dispatches, em_tokens) +
# unioned commits + recomputed t-shirt. Consumed by /session-end Step 2.6 on the
# chain-terminal path (Chunk 3 wiring).
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
# § Chunk 5 — bin/aggregate-chain-loe.sh chain-walk + aggregator (plan lines 190–232).
#
# Concurrency posture: read-only against handoff files in tasks/handoffs/ and
#   tasks/handoffs/archive/**/. Handoff files are append-only (new Session Ledger
#   blocks are appended, never overwritten). Safe under concurrent reads; no locking
#   required. Chain-walk is deterministic once the predecessor links are stable.
# Idempotency posture: deterministic given a fixed terminal-handoff and fixed handoff
#   content; same input => same output every invocation. No side effects; nothing written.
# Resume strategy: stateless — re-running with the same --terminal-handoff always
#   produces identical output as long as handoff files haven't changed. No checkpoint
#   needed; re-run is free.

set -uo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

TERMINAL_HANDOFF=""
FORMAT="yaml-frontmatter"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

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
  loe:
    agent_dispatches: 87
    opus_dispatches: 12
    em_tokens: 1847000
    tshirt: XL
  chain_sessions: 6
  chain_sessions_with_ledger: 6 of 6
  chain_span_days: 14
  chain_starting_handoff: tasks/handoffs/2026-05-05_141200_chain-root.md

Output json example:
  {"loe": {"agent_dispatches": 87, ...}, "chain_sessions": 6, ...}

Termination signals (recorded as chain_walk_terminated_early):
  missing-link  — predecessor path not found in tasks/handoffs/ or archive
  cycle-detected — predecessor path already visited

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

HANDOFFS_DIR="${GIT_ROOT}/tasks/handoffs"
ARCHIVE_DIR="${HANDOFFS_DIR}/archive"

# ---------------------------------------------------------------------------
# Resolve a predecessor path to an absolute file path.
# Searches: 1) as-is (absolute or relative to cwd), 2) under tasks/handoffs/,
#           3) recursively under tasks/handoffs/archive/**/.
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

  # 3. Basename under tasks/handoffs/
  local basename; basename="$(basename "$raw")"
  local in_handoffs="${HANDOFFS_DIR}/${basename}"
  if [[ -f "$in_handoffs" ]]; then
    echo "$in_handoffs"
    return 0
  fi

  # 4. Recursive search under tasks/handoffs/archive/**/
  if [[ -d "$ARCHIVE_DIR" ]]; then
    local found
    found=$(find "$ARCHIVE_DIR" -name "$basename" -type f 2>/dev/null | head -1)
    if [[ -n "$found" ]]; then
      echo "$found"
      return 0
    fi
    # Also try full path suffix match (in case predecessor field is a relative path
    # like tasks/handoffs/archive/2026-05/foo.md).
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
  awk -v field="$field" '
    /^---/ { if (in_fm) exit; in_fm=1; next }
    in_fm && /^[[:space:]]*[^#]/ {
      if (match($0, "^[[:space:]]*" field "[[:space:]]*:[[:space:]]*(.*)$", a)) {
        val = a[1]
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
        # Strip surrounding quotes
        if (match(val, /^"(.*)"$/, q)) val = q[1]
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
  "L  30 3 600000"
  "M  15 2 300000"
  "S   5 1 150000"
  "XS  0 0 50000"
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
    tier="${tier//[[:space:]]/}"

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
# Chain walk
# ---------------------------------------------------------------------------

declare -A VISITED_PATHS   # visited set (keyed by resolved absolute path)
CHAIN_ORDER=()             # ordered list of resolved paths (terminal → root)
WALK_TERMINATED_EARLY=""   # empty | "missing-link" | "cycle-detected"

CURRENT="$TERMINAL_ABS"

while [[ -n "$CURRENT" ]]; do
  # Cycle guard
  if [[ -n "${VISITED_PATHS[$CURRENT]+_}" ]]; then
    WALK_TERMINATED_EARLY="cycle-detected"
    break
  fi

  VISITED_PATHS["$CURRENT"]=1
  CHAIN_ORDER+=("$CURRENT")

  # Extract predecessor field
  predecessor=$(extract_frontmatter_field "$CURRENT" "predecessor")

  # Termination conditions: null / none / empty
  if [[ -z "$predecessor" || "$predecessor" == "null" || "$predecessor" == "none" ]]; then
    break
  fi

  # Resolve predecessor
  next_abs=$(resolve_handoff_path "$predecessor")
  if [[ -z "$next_abs" ]]; then
    WALK_TERMINATED_EARLY="missing-link"
    break
  fi

  CURRENT="$next_abs"
done

CHAIN_TOTAL="${#CHAIN_ORDER[@]}"

# ---------------------------------------------------------------------------
# Aggregate Session Ledger blocks across all handoffs in the chain
# ---------------------------------------------------------------------------

TOTAL_AD=0
TOTAL_OD=0
TOTAL_TOK=""
COMMITS_SET=()
SEEN_SESSION_IDS=()

HANDOFFS_WITH_LEDGER=0

for hpath in "${CHAIN_ORDER[@]}"; do
  # Parse all Session Ledger blocks from this handoff
  local_ledger_count=0

  while IFS= read -r record; do
    [[ -z "$record" ]] && continue
    local_ledger_count=$(( local_ledger_count + 1 ))

    # Parse each key=value pair in the record
    local_sid=""
    local_ad=0
    local_od=0
    local_tok=""
    local_commits=""

    for kv in $record; do
      key="${kv%%=*}"
      val="${kv#*=}"
      case "$key" in
        session_id)       local_sid="$val" ;;
        agent_dispatches) local_ad="$val" ;;
        opus_dispatches)  local_od="$val" ;;
        em_tokens)        [[ "$val" != "null" && -n "$val" ]] && local_tok="$val" ;;
        commits)          local_commits="$val" ;;
      esac
    done

    # Deduplication: skip if this session_id was already seen
    if [[ -n "$local_sid" ]]; then
      already_seen=false
      for seen in "${SEEN_SESSION_IDS[@]}"; do
        if [[ "$seen" == "$local_sid" ]]; then
          already_seen=true
          break
        fi
      done
      if [[ "$already_seen" == true ]]; then
        continue
      fi
      SEEN_SESSION_IDS+=("$local_sid")
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
        TOTAL_TOK=$(( TOTAL_TOK + clean_tok ))
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

  [[ "$local_ledger_count" -gt 0 ]] && HANDOFFS_WITH_LEDGER=$(( HANDOFFS_WITH_LEDGER + 1 ))
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
    # Degrade gracefully if date doesn't support --date (BSD vs GNU).
    first_epoch=$(date -d "$first_date" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$first_date" +%s 2>/dev/null || echo "")
    last_epoch=$(date -d "$last_date" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$last_date" +%s 2>/dev/null || echo "")

    if [[ -n "$first_epoch" && -n "$last_epoch" ]]; then
      diff_secs=$(( last_epoch - first_epoch ))
      # Allow negative (last < first) to be reported as 0 (same-day chain)
      [[ $diff_secs -lt 0 ]] && diff_secs=0
      CHAIN_SPAN_DAYS=$(( diff_secs / 86400 ))
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
    # so session-end can keep the terminal session's own per-session `loe:`
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
        [[ -n "$_c" ]] && printf '  - %s\n' "$_c"
      done
    fi
    printf 'chain_sessions_with_ledger: "%s"\n' "$CHAIN_SESSIONS_WITH_LEDGER"
    if [[ -n "$CHAIN_SPAN_DAYS" ]]; then
      printf 'chain_span_days: %d\n' "$CHAIN_SPAN_DAYS"
    else
      printf 'chain_span_days: null\n'
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
      commits_json="\"${COMMITS_OUT}\""
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
