#!/usr/bin/env bash
# reconcile-completion-commits.sh — DR-210 facade router: completion.reconcile_commits
#
# Purpose: closes the post-summary accounting gap when work continues after
# /workstream-complete Step 4 prints its summary, producing commits the entry
# never accounts for. Routes the --append write through the native example-orchestration-hub op
# (completion.reconcile_commits) when the seam is present; detect-only mode
# stays facade-side (no write op). Invoked by the terminal ceremonies
# (workday-complete, handoff exit) and the release-ceremony backstops
# (merge-to-main, workweek-complete).
#
# Usage: reconcile-completion-commits.sh [--append] [--session-id <id>] <entry-path>
#
# Three-state routing (--append mode only):
#   State 1 (seam absent)    -> legacy_reconcile_commits: bash awk/mv file write.
#   State 2 (seam present)   -> cc_invoke dispatches completion.reconcile_commits.
#   State 3 (transport fail) -> cc_invoke exits 2; propagated, no legacy fallback.
#
# Zone split (DR-216 strangler facade, strang-10):
#   ZONE A (facade-side): arg parsing, session-id resolution (cs_resolve_session_id),
#     chain expansion, merge-base + git-log SHA collection, delta computation.
#   MODE GATE: detect-only branch stays entirely facade-side (no write op).
#   ZONE B (write — dispatched via strangle_route on --append path only):
#     legacy_reconcile_commits holds the verbatim awk/mv write body from pre-facade.
#
# Spec backlink: docs/plans/2026-06-27-post-summary-completion-loop-closure.md § C1
# Session-scope pattern: docs/wiki/workstream-complete-review.md § Session-scoped diff via --session-id
#
# Session-id allowlist mirrors review-brightline-gate.sh: ^[a-zA-Z0-9][a-zA-Z0-9_-]*$
# Note: the literal string "null" passes this regex but is explicitly rejected (step 3 caller guard).
#
# Exit codes:
#   0  — normal exit: no-op skip (released entry), delta=0 OK, delta printed, or appended
#   1  — argument / validation error (bad session-id, malformed frontmatter, etc.)
#   2  — entry-path absent or unreadable
#
# NEVER commits or stages files. NEVER writes the prose body.
# Caller owns all git operations after --append mode mutates the entry file.

set -euo pipefail

# Shared allowlist regex for session-id / chain-slug / chain-session-id guards below
# (prevents ERE-injection into --grep). Single source of truth so the three call
# sites can't silently diverge in strictness.
# Review: code-reviewer — extracted triplicated allowlist regex to one readonly var.
readonly _ID_ALLOWLIST_RE='^[a-zA-Z0-9][a-zA-Z0-9_-]*$'

# ---------------------------------------------------------------------------
# DR-210 facade router -- source shared helper (must precede legacy_reconcile_commits).
# Cold-fallback self-location note (Design pin 4): legacy_reconcile_commits
# receives its required data as positional args — it does NOT re-resolve paths
# via machine-local or CLI seams.
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"

# Source state-root seam — routes per-repo state/ refs through coordinator_state_root
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4 / AC4
_CSR_LIB_DIR="${_FACADE_SCRIPT_DIR}/../lib"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"
# shellcheck source=lib/coordinator-session.sh
source "${_CSR_LIB_DIR}/coordinator-session.sh"

# ---------------------------------------------------------------------------
# legacy_reconcile_commits -- the --append write body, preserved verbatim.
# Called ONLY on State 1 (coordinator_core.invoke absent on disk) when
# in --append mode. Never called on detect-only mode (MODE GATE, see below).
#
# Args:
#   $1  entry_path   — absolute path to the completion entry file.
#   $2  delta_shorts — newline-delimited short SHAs missing from the entry.
#   $3  delta_count  — count of missing SHAs (integer string).
#   $4  stored_shas  — newline-delimited short SHAs already in the entry,
#                      used by the compare-before-write concurrent-write guard.
# ---------------------------------------------------------------------------
legacy_reconcile_commits() {
  local entry_path="$1"
  local delta_shorts="$2"
  local delta_count="$3"
  local stored_shas="$4"

  # --append mode: insert each missing SHA into commits: list
  # Preserves quote style (double-quotes, matching exemplar format) and ordering
  # NEVER touches the prose body; NEVER commits or stages
  local new_shas_file
  new_shas_file=$(mktemp)
  while IFS= read -r sha; do
    [[ -z "${sha}" ]] && continue
    printf '  - "%s"\n' "${sha}" >> "${new_shas_file}"
  done <<DELTA_SHAS_DELIM
${delta_shorts}
DELTA_SHAS_DELIM

  # same-dir mktemp ensures atomic mv (avoids cross-fs copy+unlink on Linux/CI)
  local tmp_out
  tmp_out=$(mktemp "${entry_path}.XXXXXX")

  # Two-file awk pattern: first file = new SHA lines (FNR==NR), second = entry
  # Buffers the commits: list items, then flushes buffer + new lines when
  # the commits block ends (next key) or frontmatter closes (second ---)
  # pre-initialize awk_rc so set -e cannot kill the script before || captures the code
  local awk_rc=0
  awk '
FNR == NR {
  new_lines[FNR] = $0
  n_new = FNR
  next
}

/^---$/ {
  fm_n++
  if (fm_n == 2) {
    if (in_commits) {
      printf "%s", commits_buf
      for (i = 1; i <= n_new; i++) print new_lines[i]
      commits_buf = ""
      in_commits = 0
    }
    print; next
  }
  print; next
}

fm_n == 1 && /^commits:[[:space:]]*\[\][[:space:]]*(#.*)?$/ {
  # Inline empty list: convert to multi-line and insert new SHAs
  print "commits:"
  for (i = 1; i <= n_new; i++) print new_lines[i]
  in_commits = 0
  next
}

fm_n == 1 && /^commits:/ {
  in_commits = 1
  print; next
}

fm_n == 1 && in_commits && /^[[:space:]]+-[[:space:]]/ {
  commits_buf = commits_buf $0 "\n"
  next
}

fm_n == 1 && in_commits {
  # Exiting commits block (next frontmatter key or unexpected line)
  printf "%s", commits_buf
  for (i = 1; i <= n_new; i++) print new_lines[i]
  commits_buf = ""
  in_commits = 0
  print; next
}

{ print }
' "${new_shas_file}" "${entry_path}" > "${tmp_out}" || awk_rc=$?

  rm -f "${new_shas_file}"

  if [[ ${awk_rc} -ne 0 ]]; then
    rm -f "${tmp_out}"
    printf 'reconcile-completion-commits.sh: awk rewrite failed (exit %d)\n' "${awk_rc}" >&2
    exit 1
  fi

  # Compare-before-write guard: re-read the entry's commits: set and compare to what was
  # captured at Step 5. A mismatch means a concurrent session modified the entry while the
  # awk rewrite was in flight (race on the cross-machine dead path) — discard tmp_out and
  # exit non-blocking so the concurrent writer's fold is not overwritten.
  local current_shas_recheck
  current_shas_recheck=$(awk '
  /^---$/ { n++; if (n == 2) exit; next }
  n == 1 {
    if (/^commits:/) { in_commits = 1; next }
    if (in_commits) {
      if (/^[[:space:]]+-[[:space:]]/) {
        line = $0
        sub(/^[[:space:]]*-[[:space:]]*/, "", line)
        sub(/[[:space:]]+#.*$/, "", line)
        gsub(/^["'"'"']|["'"'"']$/, "", line)
        if (line != "") print line
        next
      }
      if (/^[[:alpha:]]/) { in_commits = 0 }
    }
  }
' "${entry_path}" 2>/dev/null || true)
  if [[ "${current_shas_recheck}" != "${stored_shas}" ]]; then
    rm -f "${tmp_out}"
    printf 'WARN: reconcile-completion-commits.sh: concurrent write detected for %s — skipping to avoid overwrite\n' "${entry_path}" >&2
    exit 0
  fi

  mv "${tmp_out}" "${entry_path}"
  printf 'appended=%d\n' "${delta_count}"
  exit 0
}

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
append_mode=false
session_id_flag=""

while [[ $# -gt 0 ]]; do
  case "${1:-}" in
    --append)
      append_mode=true
      shift
      ;;
    --session-id)
      if [[ -z "${2:-}" ]]; then
        printf 'reconcile-completion-commits.sh: --session-id requires an argument\n' >&2
        exit 1
      fi
      session_id_flag="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      printf 'reconcile-completion-commits.sh: unknown flag: %s\n' "$1" >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  printf 'reconcile-completion-commits.sh: missing required <entry-path>\n' >&2
  printf 'Usage: reconcile-completion-commits.sh [--append] [--session-id <id>] <entry-path>\n' >&2
  exit 1
fi
if [[ $# -ne 1 ]]; then
  printf 'reconcile-completion-commits.sh: too many positional args (expected exactly one <entry-path>)\n' >&2
  printf 'Usage: reconcile-completion-commits.sh [--append] [--session-id <id>] <entry-path>\n' >&2
  exit 1
fi

entry_path="$1"

# ---------------------------------------------------------------------------
# Step 1: Resolve entry-path; fail loud (exit 2) if absent or unreadable
# ---------------------------------------------------------------------------
if [[ ! -f "${entry_path}" ]] || [[ ! -r "${entry_path}" ]]; then
  printf 'reconcile-completion-commits.sh: entry not found or unreadable: %s\n' "${entry_path}" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Step 2: Released-entry guard — parse frontmatter status:
#   if != pending-release: print status=<x> SKIP to stderr, exit 0 (no-op)
# ---------------------------------------------------------------------------
status_val=$(awk '
  /^---$/ { n++; if (n == 2) exit; next }
  n == 1 && /^status:/ {
    sub(/^status:[[:space:]]*/, "")
    print
    exit
  }
' "${entry_path}")

if [[ -z "${status_val}" ]]; then
  printf 'reconcile-completion-commits.sh: cannot parse status: from frontmatter in %s\n' "${entry_path}" >&2
  exit 1
fi

if [[ "${status_val}" != "pending-release" ]]; then
  printf 'status=%s SKIP\n' "${status_val}" >&2
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 3: Resolve session-id
#   Resolution order: --session-id flag → $CLAUDE_CODE_SESSION_ID →
#   .git/coordinator-sessions/.current-session-id
#   Caller guard: reject empty or the literal string "null" (null passes the
#   allowlist regex ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ but grep-matches zero commits
#   → silent false-OK; callers must skip null authored_by entries upstream)
# ---------------------------------------------------------------------------
sid="${session_id_flag}"

if [[ -z "${sid}" ]]; then
  sid="${CLAUDE_CODE_SESSION_ID:-}"
fi

if [[ -z "${sid}" ]]; then
  # Route sentinel read through the public ambiguity-aware wrapper so that
  # concurrent sessions return empty (fail-empty) instead of a wrong peer id.
  # cs_resolve_session_id honours env tiers 1-3 first, then applies the
  # ambiguity guard on tier-4 (.current-session-id).
  # Spec: docs/plans/2026-07-06-racy-sentinel-tier4-fail-empty.md § C3b
  sid=$(cs_resolve_session_id)
fi

# Caller guard: reject null or empty
if [[ -z "${sid}" ]] || [[ "${sid}" = "null" ]]; then
  printf 'reconcile-completion-commits.sh: session-id is empty or null — pass --session-id explicitly, or run: export CLAUDE_SESSION_ID=<harness-id>\n' >&2
  exit 1
fi

# Allowlist validation (prevents ERE-injection into --grep)
if [[ ! "${sid}" =~ ${_ID_ALLOWLIST_RE} ]]; then
  printf 'reconcile-completion-commits.sh: session-id must match %s: %s\n' "${_ID_ALLOWLIST_RE}" "${sid}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 3.5: Resolve chain's session-id set (Axis 1 — commit-collection widening)
#   If the entry carries chain: <slug>, enumerate all authored_by: values from
#   sibling completion entries and all consumed_by: values from chain handoffs
#   to build a union of session-ids covering the full multi-session workstream.
#   The union always includes the passed ${sid} as the anchor.
#
#   (a) authored_by: from archive/completed/**/*.md entries sharing chain: slug
#   (b) consumed_by: from handoffs in state/handoffs/ and archive/handoffs/
#       with workstream: <slug> — forward-only via consumed_by; do NOT walk
#       chain_starting_handoff: via predecessor: (backward-only pointer).
#
#   A chain member session that produced neither a completion entry nor a
#   handoff consumed_by record is an unrecoverable residual (rare, tolerated).
#
# Spec backlink: docs/plans/2026-06-29-chain-scoped-reconcile-and-liveness-gate.md § C6 Axis 1
# ---------------------------------------------------------------------------
chain_slug=$(awk '
  /^---$/ { n++; if (n == 2) exit; next }
  n == 1 && /^chain:/ {
    sub(/^chain:[[:space:]]*/, "")
    gsub(/^["'"'"']|["'"'"']$/, "")
    print
    exit
  }
' "${entry_path}")

# Normalize "null" or empty to empty (treat as no-chain)
[[ "${chain_slug}" = "null" ]] && chain_slug=""

# Allowlist-validate chain_slug before injecting into grep patterns — a slug containing
# BRE metacharacters (. * [ etc.) would false-match unrelated entries. Reject and skip
# chain resolution if the slug doesn't conform; callers control slug authorship via YAML.
if [[ -n "${chain_slug}" ]] && [[ ! "${chain_slug}" =~ ${_ID_ALLOWLIST_RE} ]]; then
  printf 'WARN: chain slug %s fails allowlist — chain resolution skipped\n' "${chain_slug}" >&2
  chain_slug=""
fi

# Build the chain session-id set; always seed with the passed ${sid}
chain_sids="${sid}"$'\n'

if [[ -n "${chain_slug}" ]]; then
  git_root=$(git rev-parse --show-toplevel 2>/dev/null) || git_root=""
  if [[ -n "${git_root}" ]]; then
    # (a) authored_by: from all completion entries sharing the same chain: slug.
    #     Grep matches both bare (chain: slug) and quoted (chain: "slug") forms.
    while IFS= read -r comp_entry; do
      [[ -f "${comp_entry}" ]] || continue
      ab=$(awk '
        /^---$/ { n++; if (n == 2) exit; next }
        n == 1 && /^authored_by:/ {
          sub(/^authored_by:[[:space:]]*/, "")
          sub(/[[:space:]]*#.*$/, "")   # strip trailing inline YAML comment (e.g. "# forensic tracing only")
          print; exit
        }
      ' "${comp_entry}" 2>/dev/null) || true
      [[ -n "${ab}" && "${ab}" != "null" ]] && chain_sids="${chain_sids}${ab}"$'\n'
    done < <(
      {
        grep -rl "^chain: ${chain_slug}$" "${git_root}/archive/completed/" 2>/dev/null || true
        grep -rl "^chain: \"${chain_slug}\"$" "${git_root}/archive/completed/" 2>/dev/null || true
      } | sort -u
    )

    # (b) consumed_by: from handoffs sharing workstream: <slug>.
    #     Search state/handoffs/ and archive/handoffs/ forward-only via consumed_by.
    for _hdir in "$(coordinator_state_root)/handoffs" "${git_root}/archive/handoffs"; do
      [[ -d "${_hdir}" ]] || continue
      while IFS= read -r hf; do
        [[ -f "${hf}" ]] || continue
        cb=$(awk '
          /^---$/ { n++; if (n == 2) exit; next }
          n == 1 && /^consumed_by:/ {
            sub(/^consumed_by:[[:space:]]*/, "")
            print; exit
          }
        ' "${hf}" 2>/dev/null) || true
        [[ -n "${cb}" && "${cb}" != "null" ]] && chain_sids="${chain_sids}${cb}"$'\n'
      done < <(grep -rl "^workstream: ${chain_slug}$" "${_hdir}" 2>/dev/null || true)
    done
  fi
fi

# Dedup and validate all collected session-ids (same allowlist as ${sid})
chain_sids_dedup=""
while IFS= read -r csid; do
  [[ -z "${csid}" ]] && continue
  [[ "${csid}" = "null" ]] && continue
  # Allowlist validation (prevents ERE-injection into --grep)
  if [[ ! "${csid}" =~ ${_ID_ALLOWLIST_RE} ]]; then
    printf 'WARN: chain session-id %s fails allowlist — skipped\n' "${csid}" >&2
    continue
  fi
  # Dedup: skip if already in set
  if ! printf '%s\n' "${chain_sids_dedup}" | grep -qxF "${csid}"; then
    chain_sids_dedup="${chain_sids_dedup}${csid}"$'\n'
  fi
done <<CHAIN_SIDS_DELIM
${chain_sids}
CHAIN_SIDS_DELIM

# ---------------------------------------------------------------------------
# Step 4: Guard git merge-base; collect session SHAs for all chain sessions
#   If merge-base unresolvable (stale / absent origin/main): emit stderr
#   diagnostic and exit 0 (non-blocking — the calling ceremony still completes)
# ---------------------------------------------------------------------------
merge_base=$(git merge-base origin/main HEAD 2>/dev/null) || merge_base=""

if [[ -z "${merge_base}" ]]; then
  printf 'merge-base unresolved — reconcile skipped\n' >&2
  exit 0
fi

# Collect commits across all chain session-ids (Axis 1 widened scope).
# Each session's commits are appended; dedup happens at the delta-computation
# stage (stored_full_set comparison). A commit can carry exactly one
# Session-Id: trailer so cross-session duplicates are impossible in practice.
session_log=""
while IFS= read -r csid; do
  [[ -z "${csid}" ]] && continue
  _csid_log=$(git log --pretty='%h %H' --grep="^Session-Id: ${csid}$" "${merge_base}..HEAD" 2>/dev/null) || true
  [[ -n "${_csid_log}" ]] && session_log="${session_log}${_csid_log}"$'\n'
done <<CHAIN_LOG_DELIM
${chain_sids_dedup}
CHAIN_LOG_DELIM

# ---------------------------------------------------------------------------
# Step 5: Parse the entry's commits: YAML list (quoted short-SHAs)
# ---------------------------------------------------------------------------

# Absence of commits: key = malformed frontmatter (fail loud)
has_commits_key=$(awk '
  /^---$/ { n++; if (n == 2) exit; next }
  n == 1 && /^commits:/ { print "yes"; exit }
' "${entry_path}")

if [[ "${has_commits_key}" != "yes" ]]; then
  printf 'reconcile-completion-commits.sh: malformed frontmatter — commits: key absent in %s\n' "${entry_path}" >&2
  exit 1
fi

# Extract stored short-SHAs from commits: list (handles quoted or bare entries)
stored_shas=$(awk '
  /^---$/ { n++; if (n == 2) exit; next }
  n == 1 {
    if (/^commits:/) { in_commits = 1; next }
    if (in_commits) {
      if (/^[[:space:]]+-[[:space:]]/) {
        line = $0
        sub(/^[[:space:]]*-[[:space:]]*/, "", line)
        sub(/[[:space:]]+#.*$/, "", line)
        gsub(/^["'"'"']|["'"'"']$/, "", line)
        if (line != "") print line
        next
      }
      # Next top-level key or end-of-block
      if (/^[[:alpha:]]/) { in_commits = 0 }
    }
  }
' "${entry_path}")

# ---------------------------------------------------------------------------
# Build set of stored full-SHAs via git rev-parse canonicalization
# (so a 7-char stored SHA matches a full %H log line)
# On rev-parse failure (ambiguous / unknown ref): treat as UNMATCHED,
# emit stderr WARN — never crash, never false-fold
# ---------------------------------------------------------------------------
stored_full_set=""
if [[ -n "${stored_shas}" ]]; then
  while IFS= read -r sha; do
    [[ -z "${sha}" ]] && continue
    resolved=$(git rev-parse --verify "${sha}^{commit}" 2>/dev/null) || {
      printf 'WARN: rev-parse failed for %s — treating as unmatched\n' "${sha}" >&2
      continue
    }
    stored_full_set="${stored_full_set}${resolved}"$'\n'
  done <<STORED_SHAS_DELIM
${stored_shas}
STORED_SHAS_DELIM
fi

# ---------------------------------------------------------------------------
# Compute delta: session SHAs (from log) not already in stored_full_set
# ---------------------------------------------------------------------------
# delta_shorts is newest-first (git log default order); intentional
delta_shorts=""
delta_count=0

if [[ -n "${session_log}" ]]; then
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    short_sha="${line%% *}"
    full_sha="${line##* }"
    # Use exact-line match to avoid partial-SHA false positives
    if ! printf '%s' "${stored_full_set}" | grep -qxF "${full_sha}"; then
      delta_shorts="${delta_shorts}${short_sha}"$'\n'
      delta_count=$((delta_count + 1))
    fi
  done <<SESSION_LOG_DELIM
${session_log}
SESSION_LOG_DELIM
fi

# ---------------------------------------------------------------------------
# Step 6: Zero delta → print delta=0 OK to stdout, exit 0
#
# Id-provenance-mismatch guard: delta_count==0 is ambiguous between (a) the
# legitimate "session's commits are all already recorded" case and (b) NO
# commit in merge_base..HEAD carries a Session-Id: trailer matching any chain
# session-id, even though the range DOES contain Session-Id:-trailered
# commits (whose id simply doesn't match — the entry's authored_by is wrong).
# Probe only fires when session_log is empty, so it discriminates the two
# zero cases without changing the non-blocking delta=0 OK / exit-0 contract.
# Fires in both detect and append modes (placed before the line-509 fork).
# Spec backlink: cross-repo/archive/2026-07-06-2026-07-06-workstream-complete-tooling-friction.md #2
# ---------------------------------------------------------------------------
if [[ ${delta_count} -eq 0 ]]; then
  if [[ -z "${session_log}" ]]; then
    if git log --pretty='%H' --grep='^Session-Id: ' "${merge_base}..HEAD" 2>/dev/null | grep -q .; then
      printf 'WARN: reconcile-completion-commits.sh: %s carries Session-Id: trailer(s) in %s..HEAD but NONE match the entry authored_by/chain set (%s) — id-provenance mismatch; commits: NOT reconciled. Check authored_by.\n' \
        "$(git rev-list --count "${merge_base}..HEAD" 2>/dev/null)" "${merge_base}" \
        "$(printf '%s' "${chain_sids_dedup}" | tr '\n' ',' | sed 's/,$//')" >&2
    fi
  fi
  printf 'delta=0 OK\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 7: Non-zero delta
# ---------------------------------------------------------------------------
if [[ "${append_mode}" = "false" ]]; then
  # detect mode (default): print delta=N then missing short-SHAs one per line
  # MODE GATE: detect-only branch stays ENTIRELY facade-side (no write op).
  # The op covers ONLY the --append WRITE; detect-only never dispatches.
  printf 'delta=%d\n' "${delta_count}"
  printf '%s' "${delta_shorts}"
  exit 0
fi

# --append mode: MODE GATE — dispatch write via the native op (DR-210 strang-10).
# Build params JSON: plan_path = entry_path, commits = delta_shorts as JSON array.
# awk 'NF' filters blank lines (BSD-portable); jq -R converts each line to a JSON
# string; jq -s collects into an array. Matches op param names exactly (DR-216 D2).
_commits_json="$(printf '%s' "${delta_shorts}" | awk 'NF' | jq -R . | jq -s .)"
_PARAMS="$(jq -cn \
  --arg plan_path "${entry_path}" \
  --argjson commits "${_commits_json}" \
  '{plan_path: $plan_path, commits: $commits}')"

# Three-state facade dispatch — stdout captured for output-format normalization.
# strangle_route decides: seam-absent -> legacy_reconcile_commits (State 1);
#                         seam-present -> cc_invoke dispatches completion.reconcile_commits.
# legacy-args (State 1 only): entry_path, delta_shorts, delta_count, stored_shas.
#
# Output normalization: legacy path emits bash format ("appended=N"); native path emits
# JSON ({"appended": N, ...}). Callers and the existing test suite depend on "appended=N",
# so we translate the JSON result to bash format to preserve the output contract.
_sr_rc=0
_sr_out="$(strangle_route_mutation "completion.reconcile_commits" legacy_reconcile_commits "$_PARAMS" \
  "${entry_path}" "${delta_shorts}" "${delta_count}" "${stored_shas}")" || _sr_rc=$?

if [[ $_sr_rc -eq 0 ]]; then
  # Detect native JSON result: if top-level object with "appended" key, translate to bash format.
  # Legacy output ("appended=N") passes through unchanged (jq cannot parse it as an object).
  _appended_val=""
  _appended_val="$(printf '%s' "${_sr_out}" | \
    jq -r 'if (type == "object") and has("appended") then .appended else empty end' \
    2>/dev/null)" || true
  if [[ -n "${_appended_val}" ]]; then
    printf 'appended=%s\n' "${_appended_val}"
  else
    # Legacy format or empty (concurrent-write guard silent exit) — pass through.
    [[ -n "${_sr_out}" ]] && printf '%s\n' "${_sr_out}"
  fi
fi
exit $_sr_rc
